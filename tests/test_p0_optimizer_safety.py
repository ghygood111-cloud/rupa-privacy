from types import SimpleNamespace

import numpy as np
import pytest

import rupa_privacy.allocation.optimizer as optimizer
from rupa_privacy.exceptions import BudgetOptimizationError


def test_successful_optimizer_candidate_satisfies_all_constraints():
    risk = np.array([0.1, 0.4, 0.9, 0.2])
    utility = np.array([0.2, 0.3, 0.1, 0.4])
    epsilon, details = optimizer.solve_convex_rupa(
        risk,
        utility,
        np.ones(4),
        4.6,
        knee_grid=np.linspace(0.0, 1.0, 7),
    )
    assert np.isfinite(epsilon).all()
    assert np.all(epsilon > 0)
    assert np.isclose(epsilon.sum(), 4.6, rtol=0.0, atol=1e-9)
    assert optimizer.risk_exposure(epsilon, risk) <= details["risk_cap"] + 1e-8
    assert details["valid_candidate_count"] >= 1


def test_extreme_risk_and_utility_weights_remain_feasible():
    epsilon, details = optimizer.solve_convex_rupa(
        np.array([1e-8, 1e6, 1.0]),
        np.array([1e-12, 1.0, 1e6]),
        np.ones(3),
        3.0,
        knee_grid=np.linspace(0.0, 1.0, 9),
    )
    assert np.isfinite(epsilon).all()
    assert np.all(epsilon > 0)
    assert np.isclose(epsilon.sum(), 3.0, atol=1e-9)
    assert details["optimizer_success"] is True


def test_solver_failure_raises_without_fallback(monkeypatch):
    monkeypatch.setattr(
        optimizer,
        "minimize",
        lambda *args, **kwargs: SimpleNamespace(success=False, message="simulated"),
    )
    with pytest.raises(BudgetOptimizationError, match="No SLSQP candidate") as exc:
        optimizer.solve_convex_rupa(
            np.array([0.2, 0.8]),
            np.array([0.5, 0.5]),
            np.ones(2),
            2.0,
            knee_grid=[0.0, 0.5, 1.0],
        )
    assert len(exc.value.diagnostics["rejected_candidates"]) == 3


def test_success_flag_cannot_bypass_risk_cap(monkeypatch):
    monkeypatch.setattr(
        optimizer,
        "minimize",
        lambda *args, **kwargs: SimpleNamespace(
            success=True, message="fake success", x=np.array([2.0, 0.0])
        ),
    )
    with pytest.raises(BudgetOptimizationError, match="No SLSQP candidate"):
        optimizer.solve_convex_rupa(
            np.array([100.0, 1.0]),
            np.array([0.5, 0.5]),
            np.ones(2),
            2.0,
            knee_grid=[0.0, 0.5, 1.0],
        )


@pytest.mark.parametrize(
    "budget,risk,utility,sensitivity",
    [
        (0.0, [0.2, 0.8], [0.5, 0.5], [1.0, 1.0]),
        (2.0, [np.nan, 0.8], [0.5, 0.5], [1.0, 1.0]),
        (2.0, [0.2, 0.8], [0.5], [1.0, 1.0]),
        (2.0, [0.2, 0.8], [0.5, 0.5], [1.0, -1.0]),
    ],
)
def test_infeasible_or_invalid_inputs_raise_clear_error(
    budget, risk, utility, sensitivity
):
    with pytest.raises(BudgetOptimizationError):
        optimizer.solve_convex_rupa(
            np.asarray(risk),
            np.asarray(utility),
            np.asarray(sensitivity),
            budget,
        )
