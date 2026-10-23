import sqlite3
from pathlib import Path

import numpy as np
import pytest
import yaml

from rupa_privacy import RUPAPipeline
from rupa_privacy.accounting import convert_laplace_rdp_to_dp
from rupa_privacy.cli import main
from rupa_privacy.data import (
    example_adjacency_config,
    example_constraints,
    example_privacy_accounting_config,
    example_privacy_config,
    example_regulatory_prior,
    example_schema,
)
from rupa_privacy.exceptions import ConfigurationError, LedgerError, PrivacySafetyError
from rupa_privacy.io import load_pipeline_config
from rupa_privacy.ledger import PrivacyLedger
from rupa_privacy.mechanisms import (
    add_bounded_laplace_noise,
    generalized_randomized_response,
)
from rupa_privacy.physics import apply_physical_projection
from rupa_privacy.randomness import create_random_source


def _construct_pipeline(privacy=None, accounting=None):
    return RUPAPipeline(
        example_schema(),
        privacy or example_privacy_config(),
        example_constraints(),
        example_regulatory_prior(),
        example_adjacency_config(),
        accounting or example_privacy_accounting_config(),
    )


@pytest.mark.parametrize("value", [float("nan"), float("inf"), float("-inf")])
@pytest.mark.parametrize(
    "field",
    [
        "epsilon_total",
        "epsilon_numeric",
        "epsilon_categorical",
        "delta",
        "utility_alpha",
        "repair_alpha",
        "categorical_risk_smoothing",
    ],
)
def test_direct_config_rejects_nonfinite_privacy_scalars(field, value):
    privacy = example_privacy_config()
    setattr(privacy, field, value)
    with pytest.raises(ConfigurationError, match=field + " must be finite"):
        _construct_pipeline(privacy=privacy)


@pytest.mark.parametrize("value", [float("nan"), float("inf"), float("-inf"), 0.0, -1.0])
def test_direct_config_rejects_invalid_total_epsilon(value):
    privacy = example_privacy_config()
    privacy.epsilon_total = value
    message = "finite" if not np.isfinite(value) else "positive"
    with pytest.raises(ConfigurationError, match=message):
        _construct_pipeline(privacy=privacy)


def test_zero_group_epsilon_follows_existing_field_semantics():
    privacy = example_privacy_config()
    privacy.epsilon_numeric = 0.0
    privacy.epsilon_total = privacy.epsilon_categorical
    with pytest.raises(ConfigurationError, match="positive epsilon_numeric"):
        _construct_pipeline(privacy=privacy)

    privacy = example_privacy_config()
    privacy.epsilon_categorical = 0.0
    privacy.epsilon_total = privacy.epsilon_numeric
    with pytest.raises(ConfigurationError, match="positive epsilon_categorical"):
        _construct_pipeline(privacy=privacy)


@pytest.mark.parametrize("field", ["epsilon_numeric", "epsilon_categorical"])
def test_negative_group_epsilon_is_rejected(field):
    privacy = example_privacy_config()
    setattr(privacy, field, -1.0)
    with pytest.raises(ConfigurationError, match="Privacy budgets"):
        _construct_pipeline(privacy=privacy)


@pytest.mark.parametrize("value", [float("nan"), float("inf"), float("-inf"), 0.0, -1.0])
def test_cumulative_budget_cap_is_finite_and_positive(value):
    accounting = example_privacy_accounting_config()
    accounting.maximum_cumulative_epsilon = value
    message = "finite" if not np.isfinite(value) else "positive"
    with pytest.raises(ConfigurationError, match=message):
        _construct_pipeline(accounting=accounting)


@pytest.mark.parametrize("field", ["nmi_bins", "joint_bins", "knee_grid_points"])
@pytest.mark.parametrize("value", [float("nan"), float("inf"), 2.5, "10"])
def test_count_parameters_require_integer_types(field, value):
    privacy = example_privacy_config()
    setattr(privacy, field, value)
    with pytest.raises(ConfigurationError, match=field):
        _construct_pipeline(privacy=privacy)


@pytest.mark.parametrize("value", [float("nan"), float("inf"), float("-inf"), 1.5, -1])
def test_random_seed_type_and_range_are_validated(value):
    privacy = example_privacy_config()
    privacy.random_seed = value
    with pytest.raises(ConfigurationError, match="random_seed"):
        _construct_pipeline(privacy=privacy)


@pytest.mark.parametrize("value", [float("nan"), float("inf"), float("-inf")])
def test_yaml_nonfinite_budget_fails_at_pipeline_validation(tmp_path, value):
    values = yaml.safe_load(Path("configs/example.yaml").read_text(encoding="utf-8"))
    values["privacy"]["epsilon_total"] = value
    path = tmp_path / "invalid.yaml"
    path.write_text(yaml.safe_dump(values, sort_keys=False), encoding="utf-8")
    schema, privacy, constraints, prior, adjacency, accounting = load_pipeline_config(path)
    with pytest.raises(ConfigurationError, match="epsilon_total must be finite"):
        RUPAPipeline(schema, privacy, constraints, prior, adjacency, accounting)


def test_cli_reports_nonfinite_yaml_as_configuration_error(tmp_path, capsys):
    inputs = tmp_path / "inputs"
    assert main(["generate-example", "--output", str(inputs)]) == 0
    capsys.readouterr()
    path = inputs / "config.yaml"
    values = yaml.safe_load(path.read_text(encoding="utf-8"))
    values["privacy"]["epsilon_total"] = float("nan")
    path.write_text(yaml.safe_dump(values, sort_keys=False), encoding="utf-8")
    result = main(
        [
            "validate",
            "--calibration",
            str(inputs / "calibration.csv"),
            "--release",
            str(inputs / "release.csv"),
            "--config",
            str(path),
        ]
    )
    captured = capsys.readouterr()
    assert result == 2
    assert captured.err.strip() == "ERROR: epsilon_total must be finite"
    assert "Traceback" not in captured.err


def _ledger_arguments(run_id="run"):
    return {
        "dataset_id": "dataset",
        "dataset_version_hash": "dataset-hash",
        "privacy_unit_id": "enterprise_id",
        "adjacency": "fixed_roster_replace_one",
        "release_schema_hash": "schema-hash",
        "epsilon_total": 5.0,
        "epsilon_numeric": 4.6,
        "epsilon_categorical": 0.4,
        "mechanism_summary": "laplace+grr",
        "run_id": run_id,
        "maximum_cumulative_epsilon": 10.0,
        "randomness_mode": "production",
    }


@pytest.mark.parametrize(
    "field",
    [
        "epsilon_total",
        "epsilon_numeric",
        "epsilon_categorical",
        "maximum_cumulative_epsilon",
    ],
)
@pytest.mark.parametrize("value", [float("nan"), float("inf"), float("-inf")])
def test_ledger_rejects_nonfinite_reservation_values(tmp_path, field, value):
    ledger = PrivacyLedger(tmp_path / "ledger.sqlite3")
    arguments = _ledger_arguments()
    arguments[field] = value
    with pytest.raises(LedgerError, match=field + " must be finite"):
        ledger.begin_release(**arguments)
    assert ledger.show() == []


@pytest.mark.parametrize("value", [float("nan"), float("inf"), float("-inf"), 0.0, -1.0])
def test_ledger_rejects_invalid_cumulative_cap(tmp_path, value):
    ledger = PrivacyLedger(tmp_path / "ledger.sqlite3")
    arguments = _ledger_arguments()
    arguments["maximum_cumulative_epsilon"] = value
    with pytest.raises(LedgerError):
        ledger.begin_release(**arguments)
    assert ledger.show() == []


@pytest.mark.parametrize("field", ["maximum_cumulative_epsilon", "additional_epsilon"])
@pytest.mark.parametrize("value", [float("nan"), float("inf"), float("-inf")])
def test_ledger_budget_check_rejects_nonfinite_inputs(tmp_path, field, value):
    ledger = PrivacyLedger(tmp_path / "ledger.sqlite3")
    arguments = {
        "dataset_id": "dataset",
        "maximum_cumulative_epsilon": 10.0,
        "additional_epsilon": 0.0,
    }
    arguments[field] = value
    with pytest.raises(LedgerError, match=field + " must be finite"):
        ledger.check_budget(**arguments)


def test_ledger_fails_closed_when_stored_total_is_nonfinite(tmp_path):
    path = tmp_path / "ledger.sqlite3"
    ledger = PrivacyLedger(path)
    ledger.begin_release(**_ledger_arguments("released"))
    ledger.mark_released("released", "a" * 64)
    with sqlite3.connect(path) as connection:
        connection.execute(
            "UPDATE releases SET epsilon_total=? WHERE run_id='released'",
            (float("inf"),),
        )
    with pytest.raises(LedgerError, match="stored released epsilon must be finite"):
        ledger.check_budget("dataset", 10.0)


@pytest.mark.parametrize("value", [float("nan"), float("inf"), float("-inf"), 0.0, -1.0])
def test_laplace_mechanism_rejects_invalid_epsilon(value):
    with pytest.raises(ValueError, match="epsilon"):
        add_bounded_laplace_noise(
            [1.0, 2.0], value, (0.0, 3.0), np.random.default_rng(1)
        )


@pytest.mark.parametrize("value", [float("nan"), float("inf"), float("-inf"), -1.0])
def test_grr_rejects_invalid_epsilon(value):
    with pytest.raises(ValueError, match="epsilon"):
        generalized_randomized_response(
            ["a", "b"], value, ["a", "b"], np.random.default_rng(1)
        )


def test_grr_preserves_existing_zero_epsilon_semantics():
    released = generalized_randomized_response(
        ["a", "b"], 0.0, ["a", "b"], np.random.default_rng(1)
    )
    assert set(released).issubset({"a", "b"})


@pytest.mark.parametrize("value", [float("nan"), float("inf"), float("-inf")])
def test_rdp_diagnostic_rejects_nonfinite_delta(value):
    with pytest.raises(ValueError, match="delta"):
        convert_laplace_rdp_to_dp([1.0], value)


def test_projection_defensively_rejects_nonfinite_repair_alpha(example_run):
    pipeline, _, release, result = example_run
    with pytest.raises(ValueError, match="repair_alpha must be finite"):
        apply_physical_projection(
            release,
            result.noisy_data,
            pipeline.schema,
            pipeline.physical_constraints,
            result.allocation_result,
            float("nan"),
        )


@pytest.mark.parametrize("value", [float("nan"), float("inf"), 1.5, -1])
def test_random_source_defensively_rejects_invalid_seed(value):
    with pytest.raises(PrivacySafetyError, match="random_seed"):
        create_random_source(example_privacy_config(), seed_override=value)
