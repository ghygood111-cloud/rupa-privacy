"""Experimental allocation for a fixed linear statistical workload.

This module allocates budgets; it does not authorize or implement a release.
The workload, sensitivities and fitted priorities must be independent of private
release values. Existing row-preserving pipeline defaults are unchanged.
"""
import numpy as np
from numbers import Real
from scipy.optimize import brentq

from ..exceptions import BudgetOptimizationError
from .balanced import solve_balanced_rupa


def allocate_linear_workload_budget(risk, sensitivities, linear_workload, budget, *,
                                   enforce_risk_cap=True, risk_smoothing=0.05,
                                   min_uniform_fraction=0.5, max_uniform_multiple=2.0):
    """Minimize exact independent-Laplace variance after a fixed linear map.

    For B=linear_workload and sensitivity Delta_j, the coefficients are
    a_j=2*Delta_j**2*sum_k(B[k,j]**2), and loss=sum_j(a_j/epsilon_j**2).
    A common deterministic bias from the fixed map does not change the optimum.
    This claim is before nonlinear clipping and does not cover row reconstruction.
    """
    if any(isinstance(value, (bool, np.bool_)) or not isinstance(value, Real)
           for value in (budget, risk_smoothing, min_uniform_fraction, max_uniform_multiple)):
        raise BudgetOptimizationError("Workload scalar settings must be real numbers, not strings or booleans")
    try:
        if any(np.asarray(value).dtype.kind not in "iuf" for value in (risk, sensitivities, linear_workload)):
            raise ValueError("Non-numeric workload input")
        r, delta, matrix = [np.asarray(value, dtype=float) for value in (risk, sensitivities, linear_workload)]
        settings = np.asarray([budget, risk_smoothing, min_uniform_fraction, max_uniform_multiple], dtype=float)
    except (ValueError, TypeError, OverflowError) as exc:
        raise BudgetOptimizationError("Workload allocation requires finite numeric inputs") from exc
    if (r.ndim != 1 or not r.size or delta.shape != r.shape or matrix.ndim != 2
            or matrix.shape[0] == 0 or matrix.shape[1] != r.size
            or not all(np.isfinite(value).all() for value in (r, delta, matrix, settings))
            or np.any(r < 0) or np.any(delta <= 0) or type(enforce_risk_cap) is not bool):
        raise BudgetOptimizationError("Invalid workload dimensions, finite values or risk-cap flag")
    budget, smoothing, lower, upper = settings
    if budget <= 0 or smoothing <= 0 or not 0 < lower <= 1 or upper < 1:
        raise BudgetOptimizationError("Invalid workload budget or allocation bounds")
    with np.errstate(over="ignore", invalid="ignore", under="ignore"):
        coefficients = 2 * np.sum((matrix * delta[None, :]) ** 2, axis=0)
    if not np.isfinite(coefficients).all() or np.any(coefficients <= 0):
        raise BudgetOptimizationError("Every released channel needs a finite positive workload coefficient")
    d = len(r)
    equal = np.full(d, budget / d)
    if enforce_risk_cap:
        epsilon, diagnostics = solve_balanced_rupa(
            r, coefficients, budget, risk_smoothing=smoothing, stability_weight=0,
            min_uniform_fraction=lower, max_uniform_multiple=upper)
    else:
        if d == 1 or lower == 1 or upper == 1 or np.all(coefficients == coefficients[0]):
            shares, reason = np.ones(d), "analytic_uniform_optimum"
        else:
            # Log-space water filling is the bounded cube-root optimum.
            log_a = np.log(coefficients) - np.log(coefficients.max())
            log_lower, log_upper = np.log(lower), np.log(upper)

            def shares_at(log_multiplier):
                return np.exp(np.clip((log_a - log_multiplier) / 3, log_lower, log_upper))

            multiplier = brentq(lambda value: shares_at(value).mean() - 1,
                                log_a.min() - 3 * log_upper - 1,
                                log_a.max() - 3 * log_lower + 1, xtol=1e-13)
            shares, reason = shares_at(multiplier), "bounded_cube_root_optimum"
        epsilon = equal * shares
        diagnostics = {"termination": reason, "optimizer_success": True}
    with np.errstate(over="ignore", invalid="ignore", divide="ignore"):
        expected = float(np.sum(coefficients / epsilon ** 2))
        uniform = float(np.sum(coefficients / equal ** 2))
    if (not np.isfinite(epsilon).all() or not np.isfinite([expected, uniform]).all()
            or not np.isclose(epsilon.sum(), budget, rtol=1e-10, atol=1e-12)
            or np.any(epsilon < lower * equal - 1e-10)
            or np.any(epsilon > upper * equal + 1e-10)
            or expected > uniform * (1 + 1e-8)):
        raise BudgetOptimizationError("Workload allocation failed final budget/loss checks")
    return epsilon, {**diagnostics, "strategy": "workload_rupa" if enforce_risk_cap else "workload_without_risk_cap",
        "coefficients": coefficients.tolist(), "expected_noise_loss": expected,
        "uniform_expected_noise_loss": uniform, "noise_loss_ratio_to_uniform": expected / uniform,
        "risk_cap_enforced": enforce_risk_cap,
        "scope": "Fixed linear statistical workload; pre-clipping expected noise MSE, not general microdata utility"}
