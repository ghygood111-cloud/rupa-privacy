"""Allocate configured numerical and categorical privacy budgets."""

import numpy as np

from ..accounting import convert_laplace_rdp_to_dp
from ..models import AllocationResult, DataSchema, PrivacyConfig, RiskResult, UtilityResult
from .optimizer import solve_convex_rupa
from .balanced import solve_balanced_rupa


def allocate_privacy_budget(
    schema: DataSchema,
    privacy: PrivacyConfig,
    risk: RiskResult,
    utility: UtilityResult,
):
    epsilon = {name: 0.0 for name in schema.released_columns}
    sensitivities = {
        name: float(schema.public_bounds[name][1] - schema.public_bounds[name][0])
        if name in schema.numeric_columns
        else 1.0
        for name in schema.released_columns
    }
    details = {}
    if schema.numeric_columns:
        numeric_risk = np.array(
            [risk.augmented_risk[name] for name in schema.numeric_columns], dtype=float
        )
        numeric_utility = np.array(
            [utility.utility_weights[name] for name in schema.numeric_columns], dtype=float
        )
        numeric_sensitivity = np.array(
            [sensitivities[name] for name in schema.numeric_columns], dtype=float
        )
        if privacy.numeric_budget_strategy == "balanced_rupa":
            numeric_epsilon, details = solve_balanced_rupa(
                numeric_risk, numeric_utility, privacy.epsilon_numeric,
                privacy.numeric_risk_smoothing, privacy.numeric_stability_weight,
                privacy.numeric_min_uniform_fraction, privacy.numeric_max_uniform_multiple,
            )
        elif privacy.numeric_budget_strategy == "uniform":
            numeric_epsilon, details = solve_balanced_rupa(
                numeric_risk, numeric_utility, privacy.epsilon_numeric,
                min_uniform_fraction=1.0, max_uniform_multiple=1.0,
            )
            details["strategy"] = "uniform"
        else:
            knee_grid = np.linspace(0.0, 1.0, privacy.knee_grid_points)
            numeric_epsilon, details = solve_convex_rupa(
                numeric_risk,
                numeric_utility,
                numeric_sensitivity,
                privacy.epsilon_numeric,
                knee_grid=knee_grid,
            )
        epsilon.update(
            {name: float(value) for name, value in zip(schema.numeric_columns, numeric_epsilon)}
        )
    else:
        numeric_epsilon = np.array([], dtype=float)

    if privacy.categorical_mode == "randomized_response" and schema.categorical_columns:
        if privacy.categorical_budget_strategy == "uniform":
            scores = np.ones(len(schema.categorical_columns), dtype=float)
        else:
            scores = np.array(
                [
                    utility.utility_weights[name]
                    / (
                        risk.single_scores[name]
                        + privacy.categorical_risk_smoothing
                    )
                    for name in schema.categorical_columns
                ],
                dtype=float,
            )
        category_epsilon = privacy.epsilon_categorical * scores / scores.sum()
        epsilon.update(
            {name: float(value) for name, value in zip(schema.categorical_columns, category_epsilon)}
        )

    basic = float(sum(epsilon.values()))
    diagnostic_epsilon, diagnostic_order = convert_laplace_rdp_to_dp(
        numeric_epsilon, privacy.delta
    )
    details = dict(details)
    details["categorical_budget_strategy"] = privacy.categorical_budget_strategy
    details["categorical_risk_smoothing"] = float(
        privacy.categorical_risk_smoothing
    )
    details["categorical_allocation_note"] = (
        "heuristic risk-utility categorical budget allocation; no optimality claim"
        if privacy.categorical_budget_strategy == "heuristic_risk_utility"
        else "uniform categorical budget allocation"
    )
    details["accounting_note"] = (
        "Basic sequential composition covers numerical Laplace and categorical randomized "
        "response. The RDP value is a numerical Laplace-only diagnostic."
    )
    return AllocationResult(
        epsilon=epsilon,
        sensitivities=sensitivities,
        numeric_budget=float(privacy.epsilon_numeric),
        categorical_budget=float(privacy.epsilon_categorical),
        basic_composition_epsilon=basic,
        numerical_rdp_diagnostic_epsilon=diagnostic_epsilon,
        numerical_rdp_order=diagnostic_order,
        mixed_rdp_strict_bound_established=False,
        optimizer_details=details,
    )
