"""Experimental DP-output-only reconstruction with protected column totals.

No raw records are accepted. Callers must privatize both the row view and total
view and compose their budgets before invoking this postprocessor.
"""
import numpy as np
from scipy.sparse import csr_matrix
from scipy.sparse.csgraph import connected_components

from ..exceptions import ConstraintValidationError


def reconstruct_from_protected_views(noisy_rows, noisy_totals, lower, upper, matrix, rhs,
                                     tolerance=1e-12, max_iterations=10000):
    arrays = [np.asarray(value, dtype=float) for value in (noisy_rows, noisy_totals, lower, upper, matrix, rhs)]
    rows, totals, lower, upper, matrix, rhs = arrays
    if rows.ndim != 2 or min(rows.shape) < 1:
        raise ConstraintValidationError("Nonempty protected row matrix required")
    n, d = rows.shape
    if (any(value.shape != (d,) for value in (totals, lower, upper))
            or matrix.ndim != 2 or matrix.shape[1] != d or rhs.shape != (matrix.shape[0],)
            or not all(np.isfinite(value).all() for value in arrays) or np.any(upper <= lower)):
        raise ConstraintValidationError("Invalid reconstruction dimensions or public bounds")
    if (not np.isfinite(tolerance) or not 0 < tolerance <= 1e-6
            or isinstance(max_iterations, bool) or not isinstance(max_iterations, int) or max_iterations < 1):
        raise ConstraintValidationError("Invalid reconstruction convergence settings")
    width = upper - lower
    normalized_rows = (rows - lower) / width
    mean = (totals / n - lower) / width
    c = matrix * width
    target = rhs - matrix @ lower
    if len(c):
        norm = np.linalg.norm(c, axis=1)
        if np.any(norm == 0) or np.linalg.matrix_rank(c) != len(c):
            raise ConstraintValidationError("Reconstruction requires independent nonzero public equalities")
        c, target = c / norm[:, None], target / norm
        inverse = np.linalg.solve(c @ c.T, np.eye(len(c)))
        kernel = np.eye(d) - c.T @ inverse @ c
        # Dykstra projection of a protected mean onto public bounds/equalities.
        p, q = np.zeros(d), np.zeros(d)
        for iteration in range(1, max_iterations + 1):
            previous = mean.copy()
            value = mean + p
            bounded = np.clip(value, 0, 1)
            p = value - bounded
            value = bounded + q
            mean = value - c.T @ inverse @ (c @ value - target)
            q = value - mean
            if (max(float(np.max(-mean)), float(np.max(mean - 1)), 0) <= tolerance
                    and np.max(abs(mean - previous)) <= tolerance):
                break
        else:
            raise ConstraintValidationError("Protected-total reconstruction did not converge; no release permitted")
        graph = csr_matrix((abs(c).T @ abs(c)) > 0)
        _, labels = connected_components(graph, directed=False)
    else:
        mean, kernel, labels, iteration = np.clip(mean, 0, 1), np.eye(d), np.arange(d), 0
    mean = np.clip(mean, 0, 1)
    variations = (normalized_rows - normalized_rows.mean(axis=0)) @ kernel.T
    variations -= variations.mean(axis=0)
    contractions = []
    for label in np.unique(labels):
        indices = np.flatnonzero(labels == label)
        values = variations[:, indices]
        limits = np.full(values.shape, np.inf)
        np.divide(1 - mean[indices], values, out=limits, where=values > 0)
        np.divide(-mean[indices], values, out=limits, where=values < 0)
        contraction = max(0, min(1, float(limits.min()))) * (1 - 1e-12)
        variations[:, indices] *= contraction
        contractions.append({"fields": indices.tolist(), "factor": contraction})
    result = lower + width * (mean + variations)
    result = np.clip(result, lower, upper)
    protected_target = n * (lower + width * mean)
    equality_error = float(np.max(abs(result @ matrix.T - rhs))) if len(matrix) else 0.0
    total_error = float(np.max(abs(result.sum(axis=0) - protected_target) / (n * width)))
    # Only DP-output/public-coefficient checks participate in acceptance.
    public_equality_scale = float(np.max(abs(matrix) @ width)) if len(matrix) else 1.0
    if (not np.isfinite(result).all() or total_error > 1e-10
            or equality_error > 1e-9 * max(1, public_equality_scale)):
        raise ConstraintValidationError("Protected-view reconstruction failed final checks")
    return result, {"projected_total_target": protected_target.tolist(),
        "maximum_public_equality_residual": equality_error, "maximum_normalized_total_mismatch": total_error,
        "mean_projection_iterations": iteration, "contractions": contractions,
        "scope": "DP-view postprocessing; accurate totals do not imply recovered private rows or preserved variance"}
