"""Opt-in bounded allocation with a uniform-anchored risk-surrogate constraint."""
import numpy as np
from scipy.optimize import minimize

from ..exceptions import BudgetOptimizationError
from .optimizer import _validate_candidate, risk_exposure


def solve_balanced_rupa(risk, utility, budget, risk_smoothing=0.05,
                        stability_weight=0.1, min_uniform_fraction=0.5,
                        max_uniform_multiple=2.0):
    """Minimize a strictly convex normalized utility surrogate, not task error.

    Shares z_j = epsilon_j / (budget / d) have mean one. The smoothed-risk
    exposure cannot exceed uniform, and fixed share bounds prevent starvation.
    Settings and fitted vectors must be independent of the protected release.
    """
    try:
        risk, utility = np.asarray(risk, dtype=float), np.asarray(utility, dtype=float)
        budget, smoothing, weight, lower, upper = map(float, (
            budget, risk_smoothing, stability_weight, min_uniform_fraction,
            max_uniform_multiple))
    except (TypeError, ValueError, OverflowError) as exc:
        raise BudgetOptimizationError("Balanced allocation requires finite numeric inputs") from exc
    if (risk.ndim != 1 or utility.shape != risk.shape or not risk.size
            or not np.isfinite(risk).all() or not np.isfinite(utility).all()
            or np.any(risk < 0) or np.any(utility < 0)):
        raise BudgetOptimizationError("Balanced risk and utility must be aligned finite non-negative vectors")
    if (not np.isfinite([budget, smoothing, weight, lower, upper]).all()
            or budget <= 0 or smoothing <= 0 or weight < 0
            or not 0 < lower <= 1 or upper < 1):
        raise BudgetOptimizationError("Invalid balanced allocation settings")
    d = len(risk)
    baseline = budget / d
    w = np.maximum(utility, 1e-12)
    w = (w / w.max()) / (w / w.max()).sum()
    r = risk + smoothing
    if not np.isfinite(r).all():
        raise BudgetOptimizationError("Smoothed risk overflow")
    q = (r / r.max()) / (r / r.max()).sum()

    def objective(z):
        return float(np.sum(w / z**2) + weight * np.mean((z - 1)**2))

    def gradient(z):
        return -2 * w / z**3 + 2 * weight * (z - 1) / d

    uniform = np.ones(d)
    analytic = d == 1 or lower == 1 or upper == 1 or np.all(risk == risk[0]) or np.all(utility == utility[0])
    if analytic:
        z, iterations, reason = uniform, 0, "analytic_uniform_optimum"
    else:
        result = minimize(objective, uniform, jac=gradient, method="SLSQP",
                          bounds=[(lower, upper)] * d,
                          constraints=[
                              {"type": "eq", "fun": lambda z: float(z.mean() - 1),
                               "jac": lambda z: np.ones(d) / d},
                              {"type": "ineq", "fun": lambda z: float(1 - np.sum(q * z**2)),
                               "jac": lambda z: -2 * q * z},
                          ], options={"maxiter": 1000, "ftol": 1e-12, "disp": False})
        if not result.success:
            raise BudgetOptimizationError("Balanced allocation solver failed: " + str(result.message))
        z, iterations, reason = np.asarray(result.x), int(result.nit), "SLSQP_converged"
    epsilon = baseline * z
    uniform_risk = risk_exposure(np.full(d, baseline), risk)
    actual_risk = risk_exposure(epsilon, risk)
    if not np.isfinite([uniform_risk, actual_risk]).all():
        raise BudgetOptimizationError("Balanced risk exposure overflow")
    valid, reasons = _validate_candidate(epsilon, budget, [(baseline * lower, baseline * upper)] * d,
                                         risk, uniform_risk)
    if (not valid or np.sum(q * z**2) > 1 + 1e-8
            or objective(z) > objective(uniform) + 1e-9):
        raise BudgetOptimizationError("Balanced allocation failed final checks", diagnostics={"reasons": reasons})
    return epsilon, {
        "strategy": "balanced_rupa", "optimizer_success": True, "iterations": iterations,
        "termination": reason, "risk_exposure": actual_risk, "uniform_risk_exposure": uniform_risk,
        "smoothed_exposure_ratio": float(np.sum(q * z**2)),
        "normalized_utility_surrogate": objective(z), "uniform_utility_surrogate": objective(uniform),
        "risk_smoothing": smoothing, "stability_weight": weight,
        "min_uniform_fraction": lower, "max_uniform_multiple": upper,
        "max_field_budget_share": float(epsilon.max() / budget),
        "scope": "Convex surrogate allocation; no optimal downstream accuracy or privacy-attack claim",
    }
