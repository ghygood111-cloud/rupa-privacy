"""Experimental two-view workflow for confirmed public or synthetic research.

This is not a production release/ledger entry point. Both views consume budget.
No source rows or unprotected totals are returned by run_two_view_research.
"""
from dataclasses import replace

import numpy as np
import pandas as pd

from .allocation.workload import allocate_linear_workload_budget
from .exceptions import PrivacySafetyError
from .governance import privacy_unit_tokens
from .physics.projection import build_constraint_system
from .physics.reconstruction import reconstruct_from_protected_views
from .pipeline import RUPAPipeline
from .validation import validate_release_data


def require_research_inputs(privacy):
    if privacy.randomness_mode != "reproducibility":
        raise ValueError("This research workflow requires reproducibility mode")
    if privacy.release_data_mode not in {"synthetic", "public_demonstration"}:
        raise ValueError("Confidential release inputs cannot be used by this research workflow")
    if privacy.release_data_mode == "public_demonstration" and not privacy.release_public_confirmed:
        raise ValueError("Public release data must be explicitly confirmed")
    if privacy.calibration_mode not in {"synthetic", "public"}:
        raise ValueError("Private calibration cannot be used by this research workflow")
    if privacy.calibration_mode == "public" and not privacy.calibration_public_confirmed:
        raise ValueError("Public calibration must be explicitly confirmed")


def prepare_statistics(calibration, release, settings):
    """Internal query state; never serialize this object as a public artifact."""
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
        weighted = delta[:, None] ** 2 * matrix.T
        inverse = np.linalg.solve(matrix @ weighted, np.eye(len(matrix)))
        projection = np.eye(d) - weighted @ inverse @ matrix
        offset = weighted @ inverse @ (rhs * n)
    else:
        projection, offset = np.eye(d), np.zeros(d)
    workload = projection / (np.sqrt(d) * scale[:, None])
    truth = clipped.sum(axis=0)
    bias = float(np.mean(((projection @ truth + offset - truth) / scale) ** 2))
    return {"privacy": privacy, "names": names, "risk": np.array([
        pipeline.fitted_state_.risk_result.augmented_risk[name] for name in names]),
        "delta": delta, "lower": lower * n, "upper": upper * n,
        "projection": projection, "offset": offset, "matrix": matrix, "rhs": rhs * n,
        "scale": scale, "workload": workload, "truth": truth, "rows": n,
        "calibration_rows": len(calibration), "projection_bias_loss": bias,
        "raw_input_total": observed.sum(axis=0),
        "clipped_input_fraction": float(np.mean(clipped != observed))}


def allocate_statistics(prepared, epsilon, strategy):
    from numbers import Real
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
    from diffprivlib.mechanisms import Laplace
    rng = np.random.RandomState(int(seed))
    noise = np.array([Laplace(epsilon=float(e), delta=0.0, sensitivity=float(s),
        random_state=rng).randomise(0.0) for e, s in zip(vector, prepared["delta"])])
    noisy = prepared["truth"] + noise
    projected = prepared["projection"] @ noisy + prepared["offset"]
    return {"noisy": noisy, "projected": projected,
            "final_clipped": np.clip(projected, prepared["lower"], prepared["upper"])}


def run_two_view_research(calibration, release, settings, strategy="hybrid_workload", progress=None):
    """Return DP-view-derived presentation data; production inputs are rejected."""
    schema, privacy, constraints, prior, adjacency, accounting = settings
    require_research_inputs(privacy)
    if strategy not in {"hybrid_uniform", "hybrid_workload"}:
        raise ValueError("Choose hybrid_uniform or hybrid_workload")
    progress = progress or (lambda _stage, _state: None)
    progress("Calibration and fixed statistical workload", "running")
    prepared = prepare_statistics(calibration, release, settings)
    progress("Calibration and fixed statistical workload", "complete")
    row_part = privacy.epsilon_numeric * .5
    total_part = privacy.epsilon_numeric - row_part
    partial = replace(privacy, epsilon_total=row_part + privacy.epsilon_categorical,
        epsilon_numeric=row_part, numeric_budget_strategy="uniform",
        categorical_budget_strategy="uniform", repair_alpha=0)
    progress("Protected row view", "running")
    pipeline = RUPAPipeline(schema, partial, constraints, prior, adjacency, accounting).fit(calibration)
    row_view = pipeline.transform(release, seed=privacy.random_seed)
    progress("Protected row view", "complete")
    progress("Protected total view and allocation", "running")
    query_strategy = "uniform_statistics" if strategy == "hybrid_uniform" else "workload_rupa"
    epsilon, details = allocate_statistics(prepared, total_part, query_strategy)
    protected = draw_statistics(prepared, epsilon, int(privacy.random_seed) + 1000000)
    composed = row_view.allocation_result.basic_composition_epsilon + float(epsilon.sum())
    if not np.isclose(composed, privacy.epsilon_total, rtol=1e-10, atol=1e-12):
        raise PrivacySafetyError("Two-view privacy budget mismatch")
    progress("Protected total view and allocation", "complete")
    progress("DP-view-only reconstruction", "running")
    matrix, rhs = build_constraint_system(schema, constraints)
    lower = np.array([schema.public_bounds[name][0] for name in schema.numeric_columns])
    upper = np.array([schema.public_bounds[name][1] for name in schema.numeric_columns])
    noisy_rows = row_view.noisy_data[schema.numeric_columns].to_numpy(float)
    values, diagnostics = reconstruct_from_protected_views(noisy_rows, protected["noisy"], lower, upper, matrix, rhs)
    frame = row_view.release_data.copy()
    frame.loc[:, schema.numeric_columns] = values
    if frame.columns.tolist() != [adjacency.privacy_unit_id] + schema.released_columns or schema.sensitive_target in frame:
        raise PrivacySafetyError("Unexpected research release columns")
    before = noisy_rows @ matrix.T - rhs
    after = values @ matrix.T - rhs
    diagnostics.update({"before_reconstruction_rms": float(np.sqrt(np.mean(before**2))) if before.size else None,
        "after_reconstruction_rms": float(np.sqrt(np.mean(after**2))) if after.size else None,
        "composed_epsilon": composed, "strategy": strategy,
        "row_epsilon": row_part, "total_query_epsilon": total_part,
        "category_epsilon": privacy.epsilon_categorical,
        "release_notice": "Experimental public/synthetic reproducibility only; variance and individual accuracy are not guaranteed"})
    allocation = []
    for name in schema.released_columns:
        row_e = row_view.allocation_result.epsilon[name]
        total_e = float(epsilon[schema.numeric_columns.index(name)]) if name in schema.numeric_columns else 0.0
        allocation.append({"feature": name, "row_view_epsilon": row_e,
            "total_view_epsilon": total_e, "composed_epsilon": row_e + total_e})
    progress("DP-view-only reconstruction", "complete")
    return {"release_data": frame, "allocation": pd.DataFrame(allocation),
        "diagnostics": diagnostics, "allocation_diagnostics": details}
