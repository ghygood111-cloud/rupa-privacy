from copy import deepcopy
import json

import numpy as np
import pytest
import pandas as pd
import yaml

from rupa_privacy import RUPAPipeline
from rupa_privacy.data import (
    example_adjacency_config,
    example_constraints,
    example_privacy_accounting_config,
    example_privacy_config,
    example_regulatory_prior,
    example_schema,
)
from rupa_privacy.exceptions import ConstraintValidationError
from rupa_privacy.cli import main
from rupa_privacy.models import PhysicalConstraint
from rupa_privacy.physics import (
    apply_physical_projection,
    build_constraint_system,
    validate_physical_constraints,
)


def _pipeline(constraints):
    return RUPAPipeline(
        example_schema(),
        example_privacy_config(),
        constraints,
        example_regulatory_prior(),
        example_adjacency_config(),
        example_privacy_accounting_config(),
    )


def test_normal_constraint_system_reports_structured_pass():
    result = validate_physical_constraints(example_schema(), example_constraints())
    assert result.decision == "PASS"
    assert result.rank == result.expected_rank == 4
    assert result.feasibility_status == "FEASIBLE_WITHIN_PUBLIC_BOUNDS"
    assert result.redundant_rows == []
    assert result.conflicting_rows == []
    assert "runtime" in result.zero_columns
    assert set(result.to_dict()) >= {
        "rank",
        "expected_rank",
        "condition_number",
        "redundant_rows",
        "conflicting_rows",
        "feasibility_status",
        "warnings",
        "decision",
    }


def test_no_constraint_system_is_supported_with_warning():
    result = validate_physical_constraints(example_schema(), [])
    assert result.decision == "PASS"
    assert result.feasibility_status == "NOT_APPLICABLE"
    assert "No physical constraints" in result.warnings[0]


@pytest.mark.parametrize(
    "constraints, message",
    [
        (
            example_constraints()
            + [deepcopy(example_constraints()[0])],
            "Redundant or linearly dependent",
        ),
        (
            [
                PhysicalConstraint("first", {"wastewater": 1.0}, rhs=1000.0),
                PhysicalConstraint("conflict", {"wastewater": 2.0}, rhs=3000.0),
            ],
            "algebraically conflicting",
        ),
        (
            [
                PhysicalConstraint("first", {"wastewater": 1.0}),
                PhysicalConstraint(
                    "near_singular", {"wastewater": 1.0, "cod": 1e-12}
                ),
            ],
            "condition number exceeds",
        ),
        (
            [PhysicalConstraint("outside_bounds", {"wastewater": 1.0}, rhs=9000.0)],
            "no feasible solution",
        ),
        (
            [
                PhysicalConstraint(
                    "unsupported", {"wastewater": 1.0}, type="inequality"
                )
            ],
            "only public linear equality constraints",
        ),
        (
            [
                PhysicalConstraint(
                    "private_learned",
                    {"wastewater": 1.0},
                    provenance="learned_from_private_release",
                )
            ],
            "unsupported provenance",
        ),
        (
            [PhysicalConstraint("nonfinite", {"wastewater": float("nan")})],
            "finite values",
        ),
    ],
)
def test_unsafe_constraint_systems_fail_closed(constraints, message):
    result = validate_physical_constraints(example_schema(), constraints)
    assert result.decision == "FAIL"
    assert any(message in error for error in result.errors)
    with pytest.raises(ConstraintValidationError):
        _pipeline(constraints)


def test_projection_defensively_rejects_bad_constraints(example_run):
    pipeline, _, release, result = example_run
    bad = example_constraints() + [deepcopy(example_constraints()[0])]
    with pytest.raises(ConstraintValidationError):
        apply_physical_projection(
            release.loc[:, pipeline.schema.released_columns],
            result.noisy_data,
            pipeline.schema,
            bad,
            result.allocation_result,
            pipeline.privacy_config.repair_alpha,
        )


def test_stable_solve_matches_frozen_explicit_inverse(example_run):
    pipeline, _, _, result = example_run
    schema = pipeline.schema
    constraints = pipeline.physical_constraints
    matrix, rhs = build_constraint_system(schema, constraints)
    numeric_names = schema.numeric_columns
    noisy = result.noisy_data[numeric_names].to_numpy(dtype=float)
    epsilon = np.array(
        [result.allocation_result.epsilon[name] for name in numeric_names], dtype=float
    )
    sensitivity = np.array(
        [result.allocation_result.sensitivities[name] for name in numeric_names],
        dtype=float,
    )
    precision = epsilon ** 2 / (sensitivity ** 2 + 1e-10)
    inverse_weight = np.diag(1.0 / np.maximum(precision, 1e-15))
    middle = matrix @ inverse_weight @ matrix.T
    residual = noisy @ matrix.T - rhs
    correction = (
        residual
        @ np.linalg.inv(middle + np.eye(len(constraints)) * 1e-12).T
        @ matrix
        @ inverse_weight
    )
    expected = noisy - correction
    actual = result.projected_data[numeric_names].to_numpy(dtype=float)
    np.testing.assert_allclose(actual, expected, rtol=0.0, atol=1e-9)
    assert result.physical_audit["constraint_validation"]["decision"] == "PASS"


def test_joint_nmi_can_be_disabled_without_changing_single_scores():
    privacy = example_privacy_config()
    privacy.joint_nmi_diagnostic = False
    pipeline = _pipeline(example_constraints())
    pipeline.privacy_config = privacy
    from rupa_privacy.data import generate_example_pair

    calibration, _ = generate_example_pair(n_release=30, n_calibration=80)
    pipeline.fit(calibration)
    assert pipeline.fitted_state_.risk_result.joint_records == []
    assert all(
        value == 0.0
        for value in pipeline.fitted_state_.risk_result.joint_penalty.values()
    )


def test_uniform_categorical_budget_is_available_as_conservative_baseline():
    privacy = example_privacy_config()
    privacy.categorical_budget_strategy = "uniform"
    pipeline = RUPAPipeline(
        example_schema(),
        privacy,
        example_constraints(),
        example_regulatory_prior(),
        example_adjacency_config(),
        example_privacy_accounting_config(),
    )
    from rupa_privacy.data import generate_example_pair

    calibration, _ = generate_example_pair(n_release=30, n_calibration=80)
    pipeline.fit(calibration)
    epsilon = pipeline.fitted_state_.allocation_result.epsilon
    assert epsilon["province"] == pytest.approx(epsilon["scale"])
    assert (
        pipeline.fitted_state_.allocation_result.optimizer_details[
            "categorical_budget_strategy"
        ]
        == "uniform"
    )


def test_disabled_joint_diagnostic_writes_no_unbound_empty_artifact(tmp_path):
    inputs = tmp_path / "inputs"
    runs = tmp_path / "runs"
    assert main(["generate-example", "--output", str(inputs)]) == 0
    config_path = inputs / "config.yaml"
    config = yaml.safe_load(config_path.read_text(encoding="utf-8"))
    config["privacy"]["joint_nmi_diagnostic"] = False
    config_path.write_text(
        yaml.safe_dump(config, sort_keys=False), encoding="utf-8"
    )
    common = [
        "--calibration",
        str(inputs / "calibration.csv"),
        "--release",
        str(inputs / "release.csv"),
        "--config",
        str(config_path),
    ]
    assert main(
        ["run"]
        + common
        + ["--output", str(runs), "--run-id", "no_joint"]
    ) == 0
    run_directory = runs / "no_joint"
    assert not (run_directory / "joint_risk.csv").exists()
    with (run_directory / "manifest.json").open(encoding="utf-8") as handle:
        manifest = json.load(handle)
    assert all(item["name"] != "joint_risk.csv" for item in manifest["artifacts"])
    for entry in manifest["artifacts"]:
        path = run_directory / entry["name"]
        if path.suffix == ".json":
            with path.open(encoding="utf-8") as handle:
                assert json.load(handle)["run_id"] == "no_joint"
        elif path.suffix == ".csv" and path.name != "release_data.csv":
            assert set(pd.read_csv(path)["run_id"]) == {"no_joint"}
