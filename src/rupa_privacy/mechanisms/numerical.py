"""Bounded numerical Laplace perturbation."""

import numpy as np


def add_bounded_laplace_noise(values, epsilon, public_bounds, rng):
    lower, upper = map(float, public_bounds)
    try:
        epsilon = float(epsilon)
    except (TypeError, ValueError, OverflowError) as exc:
        raise ValueError("epsilon must be a real number for Laplace perturbation") from exc
    if not np.isfinite(epsilon):
        raise ValueError("epsilon must be finite for Laplace perturbation")
    if epsilon <= 0:
        raise ValueError("epsilon must be positive for Laplace perturbation")
    if not np.isfinite([lower, upper]).all() or lower >= upper:
        raise ValueError("public_bounds must be finite and strictly increasing")
    clipped = np.clip(np.asarray(values, dtype=float), lower, upper)
    sensitivity = upper - lower
    noisy = clipped + rng.laplace(0.0, sensitivity / epsilon, size=len(clipped))
    return np.clip(noisy, lower, upper)

