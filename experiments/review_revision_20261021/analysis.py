"""Public/synthetic task diagnostics; not part of the production release writer."""
from dataclasses import replace

import numpy as np
from scipy.stats import ks_2samp, wasserstein_distance

from rupa_privacy.accounting import convert_laplace_rdp_to_dp


def require_research_inputs(privacy):
    if privacy.randomness_mode != "reproducibility":
        raise ValueError("This offline evaluation requires reproducibility mode")
    if privacy.release_data_mode not in {"synthetic", "public_demonstration"}:
        raise ValueError("Confidential release inputs cannot be used by this evaluation")
    if privacy.release_data_mode == "public_demonstration" and not privacy.release_public_confirmed:
        raise ValueError("Public release data must be explicitly confirmed")
    if privacy.calibration_mode not in {"synthetic", "public"}:
        raise ValueError("Private calibration cannot be used by this evaluation")
    if privacy.calibration_mode == "public" and not privacy.calibration_public_confirmed:
        raise ValueError("Public calibration must be explicitly confirmed")


def uniform_numeric_allocation(schema, fitted_allocation, delta=1e-5):
    """Experiment-only equal numerical budgets; retain identical category budgets."""
    names = schema.numeric_columns
    if not names:
        raise ValueError("Numerical fields required")
    epsilon = dict(fitted_allocation.epsilon)
    each = fitted_allocation.numeric_budget / len(names)
    epsilon.update({name: each for name in names})
    diagnostic, order = convert_laplace_rdp_to_dp(np.full(len(names), each), delta)
    return replace(fitted_allocation, epsilon=epsilon,
                   basic_composition_epsilon=float(sum(epsilon.values())),
                   numerical_rdp_diagnostic_epsilon=float(diagnostic),
                   numerical_rdp_order=float(order),
                   optimizer_details={"strategy": "experiment_only_uniform_numeric", "category_budgets_held_constant": True})


def clipped_laplace_moments(values, lower, upper, epsilon):
    """Exact expectation and clipping probability for ideal bounded-input Laplace."""
    if not np.isfinite([lower, upper, epsilon]).all() or upper <= lower or epsilon <= 0:
        raise ValueError("Finite ordered bounds and positive epsilon required")
    x = np.clip(np.asarray(values, dtype=float), lower, upper)
    if not np.isfinite(x).all() or x.size == 0:
        raise ValueError("Finite nonempty values required")
    scale = (upper - lower) / epsilon
    left = np.exp(-(x - lower) / scale)
    right = np.exp(-(upper - x) / scale)
    expected = x + .5 * scale * (left - right)
    return expected, .5 * (left + right)


def numerical_metrics(original, released, schema):
    columns = schema.numeric_columns
    x = original[columns].to_numpy(dtype=float)
    y = released[columns].to_numpy(dtype=float)
    ranges = np.array([schema.public_bounds[n][1] - schema.public_bounds[n][0] for n in columns])
    totals = x.sum(axis=0)
    if np.any(np.abs(totals) < 1e-12):
        raise ValueError("Relative total error is undefined for zero reference totals")
    relative = 100 * np.abs(y.sum(axis=0) - totals) / np.abs(totals)
    truth_share = original.cross_region_transferred_t.sum() / original.transferred_total_t.sum()
    denominator = released.transferred_total_t.sum()
    if denominator <= 0:
        raise ValueError("Released transfer-share denominator is nonpositive")
    share = released.cross_region_transferred_t.sum() / denominator
    lower = np.array([schema.public_bounds[n][0] for n in columns])
    upper = np.array([schema.public_bounds[n][1] for n in columns])
    return {
        "median_field_total_error_percent": float(np.median(relative)),
        "max_field_total_error_percent": float(np.max(relative)),
        "cross_share_error_pp": float(100 * abs(share - truth_share)),
        "released_cross_share_percent": float(100 * share),
        "reference_cross_share_percent": float(100 * truth_share),
        "mae_range": float(np.mean(np.abs(y - x) / ranges)),
        "wasserstein_range": float(np.mean([wasserstein_distance(x[:, j], y[:, j]) / ranges[j] for j in range(len(columns))])),
        "mean_ks": float(np.mean([ks_2samp(x[:, j], y[:, j]).statistic for j in range(len(columns))])),
        "boundary_fraction": float(np.mean(np.isclose(y, lower) | np.isclose(y, upper))),
    }


def bootstrap_mean_difference(a, b, seed=20261021, replicates=5000):
    a, b = np.asarray(a, dtype=float), np.asarray(b, dtype=float)
    if a.shape != b.shape or a.ndim != 1 or a.size < 2 or not np.isfinite(a - b).all():
        raise ValueError("Matched finite vectors with at least two observations required")
    difference = a - b
    rng = np.random.default_rng(seed)
    means = difference[rng.integers(0, len(difference), size=(replicates, len(difference)))].mean(axis=1)
    lo, hi = np.quantile(means, [.025, .975])
    return {"mean_difference": float(difference.mean()), "ci95_lower": float(lo), "ci95_upper": float(hi),
            "pairs": int(len(difference)), "interpretation": "A minus B; descriptive paired bootstrap interval"}
