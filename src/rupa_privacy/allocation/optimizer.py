"""Convex risk-constrained utility allocation used by the current RUPA code."""

import warnings

import numpy as np
from scipy.optimize import minimize

from ..exceptions import BudgetOptimizationError


def utility_loss(epsilon, utility_coeff):
    epsilon = np.maximum(np.asarray(epsilon, dtype=float), 1e-12)
    return float(np.sum(utility_coeff / epsilon**2))


def risk_exposure(epsilon, risk):
    epsilon = np.asarray(epsilon, dtype=float)
    return float(np.sum(risk * epsilon**2))


def _validate_candidate(epsilon, budget, bounds, risk, risk_cap):
    epsilon = np.asarray(epsilon, dtype=float)
    reasons = []
    if not np.isfinite(epsilon).all():
        reasons.append("epsilon contains non-finite values")
        return False, reasons
    if np.any(epsilon <= 0):
        reasons.append("epsilon values must be strictly positive")
    for index, (lower, upper) in enumerate(bounds):
        if epsilon[index] < lower - 1e-12 or epsilon[index] > upper + 1e-12:
            reasons.append("epsilon violates field bounds")
            break
    budget_error = abs(float(epsilon.sum()) - float(budget))
    budget_tolerance = max(1e-9, abs(float(budget)) * 1e-9)
    if budget_error > budget_tolerance:
        reasons.append("epsilon sum violates the total budget equality")
    exposure = risk_exposure(epsilon, risk)
    risk_tolerance = max(1e-10, abs(float(risk_cap)) * 1e-8)
    if not np.isfinite(exposure) or exposure > float(risk_cap) + risk_tolerance:
        reasons.append("epsilon violates the risk cap")
    return not reasons, reasons


def solve_convex_rupa(risk, utility_weights, sensitivities, budget, knee_grid=None):
    risk = np.asarray(risk, dtype=float)
    utility_weights = np.asarray(utility_weights, dtype=float)
    sensitivities = np.asarray(sensitivities, dtype=float)
    try:
        budget = float(budget)
    except (TypeError, ValueError, OverflowError) as exc:
        raise BudgetOptimizationError(
            "Numerical privacy budget must be finite and positive"
        ) from exc
    if budget <= 0 or not np.isfinite(budget):
        raise BudgetOptimizationError("Numerical privacy budget must be finite and positive")
    if not np.isfinite(risk).all() or np.any(risk < 0):
        raise BudgetOptimizationError("Risk scores must be finite and non-negative")
    if not np.isfinite(utility_weights).all() or np.any(utility_weights < 0):
        raise BudgetOptimizationError("Utility weights must be finite and non-negative")
    if not np.isfinite(sensitivities).all() or np.any(sensitivities <= 0):
        raise BudgetOptimizationError("Sensitivities must be finite and positive")
    risk = np.maximum(risk, 1e-8)
    utility_weights = np.maximum(utility_weights, 1e-12)
    if len(sensitivities) != len(risk):
        raise BudgetOptimizationError("sensitivities must align with risk scores")
    if len(utility_weights) != len(risk) or len(risk) == 0:
        raise BudgetOptimizationError("Risk and utility vectors must be non-empty and aligned")
    utility_coeff = 2.0 * utility_weights

    n_features = len(risk)
    floor = max(float(budget) * 1e-6 / max(n_features, 1), 1e-9)
    bounds = [(floor, float(budget))] * n_features
    inv_risk = 1.0 / risk
    eps_risk = inv_risk / inv_risk.sum() * budget
    utility_score = np.power(utility_coeff + 1e-18, 1.0 / 3.0)
    eps_utility = utility_score / utility_score.sum() * budget

    risk_min = risk_exposure(eps_risk, risk)
    risk_at_utility = risk_exposure(eps_utility, risk)
    utility_min = utility_loss(eps_utility, utility_coeff)
    utility_at_risk = utility_loss(eps_risk, utility_coeff)
    if knee_grid is None:
        knee_grid = np.linspace(0.0, 1.0, 21)
    else:
        try:
            knee_grid = np.asarray(knee_grid, dtype=float)
        except (TypeError, ValueError, OverflowError) as exc:
            raise BudgetOptimizationError(
                "Knee-grid values must be finite"
            ) from exc
        if not np.isfinite(knee_grid).all():
            raise BudgetOptimizationError("Knee-grid values must be finite")

    candidates = []
    rejected = []
    for fraction in knee_grid:
        risk_cap = risk_min + fraction * (risk_at_utility - risk_min)
        x0 = (1.0 - fraction) * eps_risk + fraction * eps_utility
        constraints = [
            {"type": "eq", "fun": lambda eps: np.sum(eps) - budget},
            {
                "type": "ineq",
                "fun": lambda eps, cap=risk_cap: cap - risk_exposure(eps, risk),
            },
        ]
        with warnings.catch_warnings():
            warnings.filterwarnings(
                "ignore",
                message="Values in x were outside bounds during a minimize step",
                category=RuntimeWarning,
            )
            result = minimize(
                lambda eps: utility_loss(eps, utility_coeff),
                x0,
                method="SLSQP",
                bounds=bounds,
                constraints=constraints,
                options={"maxiter": 1000, "ftol": 1e-11, "disp": False},
            )
        if not result.success:
            rejected.append(
                {
                    "fraction": float(fraction),
                    "reason": "solver failure: "
                    + str(getattr(result, "message", "unknown failure")),
                }
            )
            continue
        epsilon = np.asarray(result.x, dtype=float)
        epsilon = np.maximum(epsilon, floor)
        epsilon *= budget / epsilon.sum()
        valid, reasons = _validate_candidate(
            epsilon, budget, bounds, risk, risk_cap
        )
        if not valid:
            rejected.append(
                {
                    "fraction": float(fraction),
                    "reason": "; ".join(reasons),
                }
            )
            continue
        u_value = utility_loss(epsilon, utility_coeff)
        r_value = risk_exposure(epsilon, risk)
        u_norm = (u_value - utility_min) / max(utility_at_risk - utility_min, 1e-12)
        r_norm = (r_value - risk_min) / max(risk_at_utility - risk_min, 1e-12)
        candidates.append(
            {
                "fraction": float(fraction),
                "epsilon": epsilon,
                "risk_cap": float(risk_cap),
                "risk_exposure": float(r_value),
                "utility_loss": float(u_value),
                "knee_distance": float(np.hypot(u_norm, r_norm)),
                "optimizer_success": bool(result.success),
            }
        )

    if not candidates:
        raise BudgetOptimizationError(
            "No SLSQP candidate satisfied all privacy-budget constraints",
            diagnostics={"rejected_candidates": rejected},
        )
    chosen = min(candidates, key=lambda item: item["knee_distance"])
    details = {
        "knee_fraction": chosen["fraction"],
        "risk_cap": chosen["risk_cap"],
        "risk_exposure": chosen["risk_exposure"],
        "utility_loss": chosen["utility_loss"],
        "risk_min": risk_min,
        "risk_at_utility": risk_at_utility,
        "utility_min": utility_min,
        "utility_at_risk": utility_at_risk,
        "optimizer_success": chosen["optimizer_success"],
        "valid_candidate_count": len(candidates),
        "rejected_candidate_count": len(rejected),
        "rejected_candidates": rejected,
    }
    valid, reasons = _validate_candidate(
        chosen["epsilon"], budget, bounds, risk, chosen["risk_cap"]
    )
    if not valid:
        raise BudgetOptimizationError(
            "Chosen privacy-budget candidate failed final validation",
            diagnostics={"reasons": reasons, "details": details},
        )
    return chosen["epsilon"], details
