"""Tests of offline reviewer metrics, not extra privacy mechanisms."""
import numpy as np
import pytest

from experiments.two_view_review_20261022.metrics import evaluate_rows, aggregate_metrics
from experiments.two_view_review_20261022.run import feasible_totals
from rupa_privacy.physics.reconstruction import reconstruct_from_protected_views


def prepared():
    return {"names": ["a", "b"], "delta": np.array([10., 10.]), "rows": 3,
        "truth": np.array([6., 6.]), "scale": np.array([6., 6.]),
        "matrix": np.empty((0, 2)), "rhs": np.empty(0)}


def test_identity_preserves_all_defined_metrics():
    x = np.array([[1., 3.], [2., 2.], [3., 1.]])
    result, fields, correlations = evaluate_rows(x, x, prepared(), [])
    for key in ("normalized_total_squared_error", "wasserstein_range", "row_mae_range",
                "row_rmse_range", "standard_deviation_relative_error_percent", "quantile_mean_error_range",
                "correlation_mae_defined_pairs"):
        assert result[key] == pytest.approx(0)
    assert result["standard_deviation_ratio"] == pytest.approx(1)
    assert result["violating_row_fraction"] is None
    assert len(fields) == 2 and len(correlations) == 1


def test_constant_reconstruction_is_not_reported_as_good_correlation():
    x = np.array([[1., 3.], [2., 2.], [3., 1.]])
    y = np.full((3, 2), 2.)
    result, fields, correlations = evaluate_rows(y, x, prepared(), [])
    assert result["normalized_total_squared_error"] == 0
    assert result["standard_deviation_relative_error_percent"] == 100
    assert result["constant_output_fields"] == 2
    assert result["output_undefined_correlation_pairs"] == 1
    assert result["correlation_mae_defined_pairs"] is None
    assert correlations[0]["absolute_error"] is None
    assert result["row_mae_range"] > 0


def test_zero_reference_does_not_become_a_zero_relative_error():
    p = prepared()
    p["truth"] = np.zeros(2)
    result = aggregate_metrics(np.ones(2), np.zeros((3, 2)), p)
    assert result["mean_total_relative_error_percent"] is None
    assert result["undefined_total_relative_fields"] == 2
    assert "row_mae_range" not in result
    result, fields, _ = evaluate_rows(np.ones((3, 2)), np.zeros((3, 2)), p, [])
    assert result["undefined_standard_deviation_fields"] == 2
    assert fields[0]["mean_relative_error_percent"] is None


def test_aggregate_and_reconstruction_use_exactly_same_protected_target():
    p = prepared()
    p["matrix"], p["rhs"] = np.array([[1., -1.]]), np.array([0.])
    lower, upper = np.zeros(2), np.full(2, 10.)
    protected_totals = np.array([2., 19.])
    target = feasible_totals(p, protected_totals, lower, upper)
    rows, _ = reconstruct_from_protected_views(np.array([[1., 4.], [2., 5.], [6., 1.]]),
        protected_totals, lower, upper, p["matrix"], p["rhs"] / 3)
    assert np.allclose(target, rows.sum(axis=0), atol=1e-10)
    assert np.allclose(rows @ p["matrix"].T, 0, atol=1e-10)


def test_misaligned_rows_are_rejected():
    with pytest.raises(ValueError, match="aligned"):
        evaluate_rows(np.ones((2, 2)), np.ones((3, 2)), prepared(), [])
