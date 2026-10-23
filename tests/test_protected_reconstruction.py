import numpy as np
import pytest

from rupa_privacy.exceptions import ConstraintValidationError
from rupa_privacy.physics.reconstruction import reconstruct_from_protected_views


def test_protected_totals_and_public_equalities_are_jointly_preserved():
    rng = np.random.default_rng(1)
    rows = rng.uniform(0, 10, size=(100, 4))
    matrix = np.array([[1, -1, -1, 0.]])
    result, diagnostics = reconstruct_from_protected_views(rows, [700, 300, 400, 250],
        np.zeros(4), np.full(4, 10.), matrix, np.array([0.]))
    assert np.all(result >= 0) and np.all(result <= 10)
    np.testing.assert_allclose(result @ matrix.T, 0, atol=1e-7)
    np.testing.assert_allclose(result.sum(axis=0), diagnostics["projected_total_target"], atol=1e-7)
    assert diagnostics["maximum_normalized_total_mismatch"] < 1e-10


def test_zero_target_only_collapses_its_public_connected_block():
    rows = np.array([[0, 0], [1, 1], [2, 2.]])
    result, info = reconstruct_from_protected_views(rows, [0, 3], [0, 0], [2, 2], np.empty((0, 2)), np.empty(0))
    np.testing.assert_array_equal(result[:, 0], 0)
    assert np.std(result[:, 1]) > .1
    assert info["contractions"][0]["factor"] == 0


@pytest.mark.parametrize("bad", [np.nan, np.inf, -np.inf])
def test_invalid_protected_total_fails_closed(bad):
    with pytest.raises(ConstraintValidationError):
        reconstruct_from_protected_views([[1, 2]], [bad, 2], [0, 0], [10, 10], np.empty((0, 2)), np.empty(0))


def test_infeasible_public_equations_fail_closed():
    with pytest.raises(ConstraintValidationError, match="did not converge"):
        reconstruct_from_protected_views([[.5]], [.5], [0], [1], [[1]], [2], max_iterations=10)
