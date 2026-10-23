"""Optional allocation must preserve budgets, safety gates and the legacy default."""
from dataclasses import replace
from pathlib import Path
from types import SimpleNamespace

import numpy as np
import pandas as pd
import pytest

from rupa_privacy import RUPAPipeline
from rupa_privacy.allocation.balanced import solve_balanced_rupa
from rupa_privacy.allocation.optimizer import risk_exposure
from rupa_privacy.exceptions import BudgetOptimizationError, ConfigurationError, PrivacySafetyError
from rupa_privacy.io import load_pipeline_config
from rupa_privacy.validation import validate_configuration

ROOT = Path(__file__).resolve().parents[1]
PARAMETERS = ("numeric_risk_smoothing", "numeric_stability_weight",
              "numeric_min_uniform_fraction", "numeric_max_uniform_multiple")


@pytest.mark.parametrize("name", PARAMETERS)
@pytest.mark.parametrize("value", [float("nan"), float("inf"), float("-inf"), True, "0.5"])
def test_new_allocation_settings_reject_invalid_scalar_at_boundary(name, value):
    schema, privacy, constraints, prior, adjacency, accounting = load_pipeline_config(ROOT / "examples/official/config.yaml")
    with pytest.raises(ConfigurationError):
        validate_configuration(schema, replace(privacy, **{name: value}), constraints, prior, adjacency, accounting)


@pytest.mark.parametrize("name,value", [("numeric_risk_smoothing", 0), ("numeric_risk_smoothing", -1),
    ("numeric_stability_weight", -.1), ("numeric_min_uniform_fraction", 0),
    ("numeric_min_uniform_fraction", 1.1), ("numeric_max_uniform_multiple", .9)])
def test_new_allocation_settings_ranges(name, value):
    schema, privacy, constraints, prior, adjacency, accounting = load_pipeline_config(ROOT / "examples/official/config.yaml")
    with pytest.raises(ConfigurationError):
        validate_configuration(schema, replace(privacy, **{name: value}), constraints, prior, adjacency, accounting)


@pytest.mark.parametrize("seed", [1, 2, 3, 4, 5, 6, 7, 8])
def test_balanced_solution_has_guardrails_and_no_more_raw_surrogate_exposure(seed):
    rng = np.random.default_rng(seed)
    risk, utility = rng.uniform(0, 1, 14), rng.uniform(.01, 1, 14)
    risk[0] = 0
    epsilon, info = solve_balanced_rupa(risk, utility, 4.3)
    uniform = np.full(14, 4.3 / 14)
    assert epsilon.sum() == pytest.approx(4.3, abs=1e-9)
    assert np.all(epsilon >= .5 * uniform - 1e-10)
    assert np.all(epsilon <= 2 * uniform + 1e-10)
    assert risk_exposure(epsilon, risk) <= risk_exposure(uniform, risk) + 1e-9
    assert info["normalized_utility_surrogate"] <= info["uniform_utility_surrogate"] + 1e-9


@pytest.mark.parametrize("risk", [[0, 0, 0], [.2, .2, .2]])
def test_equal_risk_analytically_returns_uniform(risk):
    epsilon, info = solve_balanced_rupa(risk, [.2, .4, .8], 3)
    np.testing.assert_array_equal(epsilon, [1, 1, 1])
    assert info["termination"] == "analytic_uniform_optimum"


def test_solver_failure_remains_fail_closed(monkeypatch):
    import rupa_privacy.allocation.balanced as module
    monkeypatch.setattr(module, "minimize", lambda *a, **k: SimpleNamespace(success=False, message="forced failure"))
    with pytest.raises(BudgetOptimizationError, match="solver failed"):
        solve_balanced_rupa([.1, .2, 0], [.8, .1, .1], 3)


def test_forged_solver_success_is_rejected(monkeypatch):
    import rupa_privacy.allocation.balanced as module
    monkeypatch.setattr(module, "minimize", lambda *a, **k: SimpleNamespace(success=True, x=np.array([float("nan"), 1, 1]), nit=1))
    with pytest.raises(BudgetOptimizationError):
        solve_balanced_rupa([.1, .2, 0], [.8, .1, .1], 3)


def test_legacy_remains_default_and_strategy_is_validated():
    schema, privacy, constraints, prior, adjacency, accounting = load_pipeline_config(ROOT / "examples/official/config.yaml")
    assert privacy.numeric_budget_strategy == "legacy_rupa"
    with pytest.raises(ConfigurationError, match="numeric_budget_strategy"):
        validate_configuration(schema, replace(privacy, numeric_budget_strategy="not_a_strategy"), constraints, prior, adjacency, accounting)


@pytest.mark.parametrize("strategy", ["legacy_rupa", "balanced_rupa", "uniform"])
def test_all_strategies_run_through_shared_pipeline(strategy):
    folder = ROOT / "examples/hazardous_waste"
    schema, privacy, constraints, prior, adjacency, accounting = load_pipeline_config(folder / "config_reproducibility.yaml")
    privacy = replace(privacy, numeric_budget_strategy=strategy)
    fitted = RUPAPipeline(schema, privacy, constraints, prior, adjacency, accounting).fit(pd.read_csv(folder / "calibration.csv"))
    result = fitted.transform(pd.read_csv(folder / "release.csv").iloc[:10])
    assert result.allocation_result.basic_composition_epsilon == pytest.approx(5)
    assert result.release_data.columns.tolist() == [adjacency.privacy_unit_id] + schema.released_columns
    assert schema.sensitive_target not in result.release_data
    if strategy == "balanced_rupa":
        assert max(result.allocation_result.epsilon[n] for n in schema.numeric_columns) <= 2 * privacy.epsilon_numeric / len(schema.numeric_columns) + 1e-9


@pytest.mark.parametrize("name", PARAMETERS)
def test_cli_rejects_nonfinite_new_setting_without_traceback(tmp_path, capsys, name):
    import yaml
    from rupa_privacy.cli import main
    values = yaml.safe_load((ROOT / "examples/official/config.yaml").read_text())
    values["privacy"].update(numeric_budget_strategy="balanced_rupa", **{name: float("inf")})
    config = tmp_path / "invalid.yaml"
    config.write_text(yaml.safe_dump(values), encoding="utf-8")
    code = main(["validate", "--calibration", str(ROOT / "examples/official/calibration.csv"),
                 "--release", str(ROOT / "examples/official/release.csv"), "--config", str(config)])
    output = capsys.readouterr()
    assert code == 2 and name + " must be finite" in output.err
    assert "Traceback" not in output.err


def test_balanced_production_still_requires_ledger_authorization():
    folder = ROOT / "examples/hazardous_waste"
    schema, privacy, constraints, prior, adjacency, accounting = load_pipeline_config(folder / "config_reproducibility.yaml")
    privacy = replace(privacy, numeric_budget_strategy="balanced_rupa", randomness_mode="production",
                      random_seed=None, release_data_mode="confidential")
    pipeline = RUPAPipeline(schema, privacy, constraints, prior, adjacency, accounting).fit(pd.read_csv(folder / "calibration.csv"))
    with pytest.raises(PrivacySafetyError, match="ledger"):
        pipeline.transform(pd.read_csv(folder / "release.csv"))


def test_gui_strategy_roundtrip_does_not_mutate_existing_config():
    import yaml
    from demo.demo_support import apply_basic_config
    values = yaml.safe_load((ROOT / "examples/official/config.yaml").read_text())
    p = values["privacy"]
    updated = apply_basic_config(values, epsilon_total=p["epsilon_total"], epsilon_numeric=p["epsilon_numeric"],
        epsilon_categorical=p["epsilon_categorical"], utility_alpha=p["utility_alpha"], repair_alpha=p["repair_alpha"],
        random_seed=p["random_seed"], sensitive_target=values["schema"]["sensitive_target"],
        privacy_unit_id=values["adjacency"]["privacy_unit_id"], numeric_budget_strategy="balanced_rupa")
    assert updated["privacy"]["numeric_budget_strategy"] == "balanced_rupa"
    assert "numeric_budget_strategy" not in values["privacy"]
