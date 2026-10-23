"""Research-only aggregate release using the official diffprivlib mechanism."""
from dataclasses import replace
from pathlib import Path
from numbers import Real
import sys

import numpy as np
import pandas as pd

from rupa_privacy import RUPAPipeline
from rupa_privacy.allocation.workload import allocate_linear_workload_budget
from rupa_privacy.governance import privacy_unit_tokens
from rupa_privacy.exceptions import PrivacySafetyError
from rupa_privacy.physics.projection import build_constraint_system
from rupa_privacy.validation import validate_release_data
from experiments.review_revision_20261021.analysis import require_research_inputs


def official_laplace():
    # Reuse the already verified optional external-tool environment if present.
    optional = Path(__file__).resolve().parents[1] / "review_revision_20261021/tools"
    if optional.is_dir() and str(optional) not in sys.path:
        sys.path.insert(0, str(optional))
    from diffprivlib.mechanisms import Laplace
    return Laplace


def prepare_statistics(calibration, release, settings):
    schema, privacy, constraints, prior, adjacency, accounting = settings
    require_research_inputs(privacy)
    validate_release_data(release, schema, adjacency)
    if set(privacy_unit_tokens(calibration, adjacency.privacy_unit_id)).intersection(
            privacy_unit_tokens(release, adjacency.privacy_unit_id)):
        raise PrivacySafetyError("Statistical evaluation requires disjoint calibration/release units")
    pipeline = RUPAPipeline(schema, replace(privacy, numeric_budget_strategy="uniform"),
                            constraints, prior, adjacency, accounting).fit(calibration)
    names = schema.numeric_columns
    if not names:
        raise ValueError("At least one numerical statistical query required")
    lower = np.array([schema.public_bounds[name][0] for name in names])
    upper = np.array([schema.public_bounds[name][1] for name in names])
    delta = upper - lower
    cal = np.clip(calibration[names].to_numpy(float), lower, upper)
    observed = release[names].to_numpy(float)
    clipped = np.clip(observed, lower, upper)
    n, d = clipped.shape
    scale = np.maximum(abs(cal.mean(axis=0)), .01 * delta) * n
    matrix, rhs = build_constraint_system(schema, constraints)
    if len(matrix):
        # Fix the projection independently of allocations so its variance is a
        # declared linear workload, shared by every comparator.
        weighted = delta[:, None] ** 2 * matrix.T
        inverse = np.linalg.solve(matrix @ weighted, np.eye(len(matrix)))
        projection = np.eye(d) - weighted @ inverse @ matrix
        offset = weighted @ inverse @ (rhs * n)
    else:
        projection, offset = np.eye(d), np.zeros(d)
    workload = projection / (np.sqrt(d) * scale[:, None])
    truth = clipped.sum(axis=0)
    projection_bias_loss = float(np.mean(((projection @ truth + offset - truth) / scale) ** 2))
    return {"privacy": privacy, "names": names, "risk": np.array([
        pipeline.fitted_state_.risk_result.augmented_risk[name] for name in names]),
        "delta": delta, "lower": lower * n, "upper": upper * n,
        "projection": projection, "offset": offset, "matrix": matrix, "rhs": rhs * n,
        "scale": scale, "workload": workload, "truth": truth, "rows": n,
        "calibration_rows": len(calibration), "projection_bias_loss": projection_bias_loss,
        "raw_input_total": observed.sum(axis=0),
        "clipped_input_fraction": float(np.mean(clipped != observed))}


def allocate(prepared, epsilon, strategy):
    require_research_inputs(prepared["privacy"])
    if isinstance(epsilon, (bool, np.bool_)) or not isinstance(epsilon, Real) or not np.isfinite(epsilon) or epsilon <= 0:
        raise ValueError("Finite positive statistical epsilon required")
    if strategy == "uniform_statistics":
        vector = np.full(len(prepared["names"]), epsilon / len(prepared["names"]))
        coefficients = 2 * np.sum((prepared["workload"] * prepared["delta"]) ** 2, axis=0)
        loss = float(np.sum(coefficients / vector ** 2))
        return vector, {"strategy": strategy, "expected_noise_loss": loss,
                        "uniform_expected_noise_loss": loss, "noise_loss_ratio_to_uniform": 1.0}
    if strategy not in {"workload_rupa", "workload_without_risk_cap"}:
        raise ValueError("Unknown statistical allocation strategy")
    return allocate_linear_workload_budget(prepared["risk"], prepared["delta"],
        prepared["workload"], epsilon, enforce_risk_cap=strategy == "workload_rupa")


def draw_statistics(prepared, epsilon, seed):
    require_research_inputs(prepared["privacy"])
    vector = np.asarray(epsilon, dtype=float)
    if vector.shape != prepared["delta"].shape or not np.isfinite(vector).all() or np.any(vector <= 0):
        raise ValueError("Finite positive field epsilon required")
    if isinstance(seed, bool) or not isinstance(seed, (int, np.integer)):
        raise ValueError("An explicit research seed is required")
    rng = np.random.RandomState(int(seed))
    mechanism = official_laplace()
    noise = np.array([mechanism(epsilon=float(e), delta=0.0, sensitivity=float(s),
        random_state=rng).randomise(0.0) for e, s in zip(vector, prepared["delta"])])
    noisy = prepared["truth"] + noise
    projected = prepared["projection"] @ noisy + prepared["offset"]
    final = np.clip(projected, prepared["lower"], prepared["upper"])
    return {"noisy": noisy, "projected": projected, "final_clipped": final}


def stage_metrics(prepared, values):
    error = values - prepared["truth"]
    defined = abs(prepared["truth"]) > 1e-12
    relative = np.full(len(error), np.nan)
    relative[defined] = 100 * abs(error[defined]) / abs(prepared["truth"][defined])
    residual = prepared["matrix"] @ values - prepared["rhs"]
    residual_scale = np.maximum(abs(prepared["matrix"]) @ (prepared["upper"] - prepared["lower"]), 1e-12)
    return {"normalized_squared_error": float(np.mean((error / prepared["scale"]) ** 2)),
        "median_relative_error_percent": float(np.nanmedian(relative)),
        "mean_relative_error_percent": float(np.nanmean(relative)),
        "maximum_relative_error_percent": float(np.nanmax(relative)),
        "undefined_relative_fields": int(np.sum(~defined)),
        "negative_estimates": int(np.sum(values < 0)),
        "out_of_bounds_estimates": int(np.sum((values < prepared["lower"]) | (values > prepared["upper"]))),
        "nrms": float(np.sqrt(np.mean((residual / residual_scale) ** 2))) if len(residual) else 0.0}
