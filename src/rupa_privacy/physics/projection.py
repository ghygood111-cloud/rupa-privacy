"""Weighted projection using only DP data and public metadata."""

import numpy as np
import pandas as pd

from ..models import AllocationResult, DataSchema, PhysicalConstraint
from .validation import require_valid_physical_constraints


def build_constraint_system(schema, constraints):
    """Return ``A`` and ``b`` in the public equality system ``A x = b``."""
    names = list(schema.numeric_columns)
    name_to_index = {name: index for index, name in enumerate(names)}
    matrix = np.zeros((len(constraints), len(names)), dtype=float)
    rhs = np.zeros(len(constraints), dtype=float)
    for row, constraint in enumerate(constraints):
        for name, coefficient in constraint.coefficients.items():
            matrix[row, name_to_index[name]] = coefficient
        rhs[row] = constraint.rhs
    return matrix, rhs


def _constraint_metrics(values, matrix, rhs, constraints, schema):
    if matrix.shape[0] == 0:
        return {
            "rms": 0.0,
            "nrms": 0.0,
            "max_absolute_residual": 0.0,
            "violation_rate": 0.0,
            "per_constraint_rms": {},
        }
    residual = values @ matrix.T - rhs
    ranges = np.array(
        [schema.public_bounds[name][1] - schema.public_bounds[name][0] for name in schema.numeric_columns],
        dtype=float,
    )
    residual_scales = np.maximum(np.abs(matrix) @ ranges, 1e-12)
    normalized = residual / residual_scales
    tolerances = np.array([constraint.tolerance for constraint in constraints], dtype=float)
    violations = np.any(np.abs(residual) > tolerances, axis=1)
    return {
        "rms": float(np.sqrt(np.mean(residual ** 2))),
        "nrms": float(np.sqrt(np.mean(normalized ** 2))),
        "max_absolute_residual": float(np.max(np.abs(residual))),
        "violation_rate": float(np.mean(violations)),
        "per_constraint_rms": {
            constraint.name: float(np.sqrt(np.mean(residual[:, index] ** 2)))
            for index, constraint in enumerate(constraints)
        },
    }


def _frame_with_numeric_state(source, numeric_values, schema):
    output = source.copy()
    for index, name in enumerate(schema.numeric_columns):
        output[name] = numeric_values[:, index]
    available = [name for name in schema.released_columns if name in output.columns]
    return output.loc[:, available]


def apply_physical_projection(
    original_release: pd.DataFrame,
    noisy_data: pd.DataFrame,
    schema: DataSchema,
    constraints,
    allocation: AllocationResult,
    repair_alpha: float,
):
    """Return noisy, fully projected, interpolated, and clipped release states.

    The transformation uses only the DP output, fixed allocation, public bounds,
    and public constraints, so it is differential-privacy post-processing.
    """
    try:
        repair_alpha = float(repair_alpha)
    except (TypeError, ValueError, OverflowError) as exc:
        raise ValueError("repair_alpha must be a real number") from exc
    if not np.isfinite(repair_alpha):
        raise ValueError("repair_alpha must be finite")
    if not 0.0 <= repair_alpha <= 1.0:
        raise ValueError("repair_alpha must lie in [0, 1]")
    constraints = list(constraints)
    constraint_validation = require_valid_physical_constraints(schema, constraints)
    numeric_names = list(schema.numeric_columns)
    original_values = (
        np.column_stack([
            np.clip(
                original_release[name].to_numpy(dtype=float),
                schema.public_bounds[name][0],
                schema.public_bounds[name][1],
            )
            for name in numeric_names
        ])
        if numeric_names
        else np.empty((len(original_release), 0), dtype=float)
    )
    noisy_values = noisy_data[numeric_names].to_numpy(dtype=float)
    matrix, rhs = build_constraint_system(schema, constraints)

    if matrix.shape[0] == 0:
        projected_values = noisy_values.copy()
    else:
        epsilon = np.array([allocation.epsilon[name] for name in numeric_names], dtype=float)
        sensitivity = np.array(
            [allocation.sensitivities[name] for name in numeric_names], dtype=float
        )
        precision = epsilon ** 2 / (sensitivity ** 2 + 1e-10)
        inverse_weight = np.diag(1.0 / np.maximum(precision, 1e-15))
        middle = matrix @ inverse_weight @ matrix.T
        residual = noisy_values @ matrix.T - rhs
        solved_residual = np.linalg.solve(
            middle + np.eye(len(constraints)) * 1e-12,
            residual.T,
        ).T
        correction = solved_residual @ matrix @ inverse_weight
        projected_values = noisy_values - correction

    interpolated_values = noisy_values + repair_alpha * (
        projected_values - noisy_values
    )
    clipped_values = interpolated_values.copy()
    for index, name in enumerate(numeric_names):
        lower, upper = schema.public_bounds[name]
        clipped_values[:, index] = np.clip(clipped_values[:, index], lower, upper)

    projected_data = _frame_with_numeric_state(noisy_data, projected_values, schema)
    repaired_data = _frame_with_numeric_state(noisy_data, interpolated_values, schema)
    release_data = _frame_with_numeric_state(noisy_data, clipped_values, schema)
    states = {
        "original_clipped_internal": original_values,
        "noisy": noisy_values,
        "full_projection": projected_values,
        "interpolated": interpolated_values,
        "final_clipped": clipped_values,
    }
    audit = {
        "constraint_validation": constraint_validation.to_dict(),
        "states": {
            name: _constraint_metrics(values, matrix, rhs, constraints, schema)
            for name, values in states.items()
        },
        "repair_alpha": repair_alpha,
        "full_projection_targets_equalities": bool(matrix.shape[0] > 0),
        "privacy_note": (
            "Projection, interpolation, and clipping use only differentially private data "
            "and public metadata; they consume no additional privacy budget."
        ),
        "interpretation_note": (
            "repair_alpha below 1 does not force zero equality residual, and final public-"
            "bound clipping can reintroduce residual."
        ),
        "publication_note": (
            "The original_clipped_internal metrics depend on raw release records and are "
            "for internal audit only."
        ),
    }
    return projected_data, repaired_data, release_data, audit
