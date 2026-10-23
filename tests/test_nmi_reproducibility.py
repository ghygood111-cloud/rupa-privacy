import numpy as np
import pandas as pd
import pytest

from rupa_privacy import RUPAPipeline
from rupa_privacy.data import (
    example_adjacency_config,
    example_constraints,
    example_privacy_accounting_config,
    example_privacy_config,
    example_regulatory_prior,
    example_schema,
    generate_example_pair,
)
from rupa_privacy.models import DataSchema
from rupa_privacy.risk import compute_risk
from rupa_privacy.risk.nmi import discretize_1d


def _compact_schema():
    return DataSchema(
        sensitive_target="target",
        numeric_columns=["numeric"],
        categorical_columns=["category"],
        released_columns=["numeric", "category"],
        public_bounds={"numeric": (0.0, 1000.0)},
        public_categories={"category": ["a", "b", "c"]},
    )


def test_small_numeric_and_categorical_risk_are_deterministic():
    rows = 500
    data = pd.DataFrame(
        {
            "target": np.arange(rows, dtype=float) % 37,
            "numeric": np.arange(rows, dtype=float) % 23,
            "category": np.array(["a", "b", "c"])[np.arange(rows) % 3],
        }
    )
    first = compute_risk(data, _compact_schema(), nmi_bins=10)
    second = compute_risk(data, _compact_schema(), nmi_bins=10)
    assert first.single_scores == second.single_scores
    assert first.bin_diagnostics == second.bin_diagnostics


@pytest.mark.slow
def test_more_than_200000_rows_are_deterministic_without_subsampling():
    rows = 200_001
    index = np.arange(rows)
    data = pd.DataFrame(
        {
            "target": (index % 997).astype(float),
            "numeric": (index % 53).astype(float),
            "category": np.array(["a", "b", "c"])[index % 3],
        }
    )
    first = compute_risk(data, _compact_schema(), nmi_bins=10)
    second = compute_risk(data, _compact_schema(), nmi_bins=10)
    assert first.single_scores == second.single_scores
    assert first.augmented_risk == second.augmented_risk
    assert first.bin_diagnostics == second.bin_diagnostics
    assert first.bin_diagnostics["feature:numeric"]["subsample"] is None
    assert first.bin_diagnostics["feature:numeric"]["random_state"] == 0


def test_tied_values_report_effective_bin_collapse():
    values = np.array([1.0] * 20 + [2.0] * 20 + [3.0] * 20)
    labels, diagnostic = discretize_1d(
        values, n_bins=10, return_diagnostics=True
    )
    assert len(labels) == len(values)
    assert diagnostic["requested_bins"] == 10
    assert diagnostic["effective_bins"] < 10
    assert diagnostic["collapse_severity"] in {"mild", "severe"}
    assert diagnostic["warning"]


def test_extreme_ties_report_degenerate_field_diagnostic():
    values = np.array([1.0] * 50 + [2.0] * 2 + [3.0] * 2)
    _, diagnostic = discretize_1d(values, n_bins=10, return_diagnostics=True)
    assert diagnostic["effective_bins"] == 1
    assert diagnostic["collapse_severity"] == "degenerate"
    assert diagnostic["warning"]


def test_joint_effective_bins_are_recorded():
    rows = 120
    index = np.arange(rows)
    schema = DataSchema(
        sensitive_target="target",
        numeric_columns=["first", "second"],
        categorical_columns=[],
        released_columns=["first", "second"],
        public_bounds={"first": (0.0, 5.0), "second": (0.0, 5.0)},
    )
    data = pd.DataFrame(
        {
            "target": (index % 11).astype(float),
            "first": (index % 3).astype(float),
            "second": (index % 2).astype(float),
        }
    )
    result = compute_risk(data, schema, nmi_bins=10, joint_bins=5)
    diagnostic = result.bin_diagnostics["joint:first|second"]
    assert diagnostic["requested_bins"] == 5
    assert len(diagnostic["effective_bins"]) == 2
    assert diagnostic["warning"]


def test_rupa_seed_does_not_change_deterministic_risk_preprocessing():
    calibration, _ = generate_example_pair(n_calibration=300, n_release=20)
    scores = []
    for seed in (7, 7, 99):
        privacy = example_privacy_config()
        privacy.random_seed = seed
        pipeline = RUPAPipeline(
            example_schema(),
            privacy,
            example_constraints(),
            example_regulatory_prior(),
            example_adjacency_config(),
            example_privacy_accounting_config(),
        ).fit(calibration)
        scores.append(pipeline.fitted_state_.risk_result.single_scores)
    assert scores[0] == scores[1] == scores[2]
