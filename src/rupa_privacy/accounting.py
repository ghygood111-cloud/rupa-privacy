"""Privacy accounting with explicit separation of formal and diagnostic scopes."""

import numpy as np
from scipy.optimize import minimize_scalar


def _validated_epsilons(epsilons):
    try:
        values = np.asarray(epsilons, dtype=float)
    except (TypeError, ValueError, OverflowError) as exc:
        raise ValueError("epsilons must contain real numbers") from exc
    if not np.isfinite(values).all():
        raise ValueError("epsilons must contain only finite values")
    if np.any(values < 0):
        raise ValueError("epsilons must be non-negative")
    return values


def laplace_rdp_epsilon(alpha, epsilons):
    """RDP diagnostic for independent numerical Laplace mechanisms only."""
    try:
        alpha = float(alpha)
    except (TypeError, ValueError, OverflowError) as exc:
        raise ValueError("alpha must be a real number") from exc
    if not np.isfinite(alpha) or alpha <= 1:
        raise ValueError("alpha must be finite and greater than 1")
    total = 0.0
    for epsilon in _validated_epsilons(epsilons):
        if epsilon <= 1e-12:
            continue
        first = alpha / (2 * alpha - 1) * np.exp((alpha - 1) * epsilon)
        second = (alpha - 1) / (2 * alpha - 1) * np.exp(-alpha * epsilon)
        total += np.log(first + second) / (alpha - 1)
    return total


def convert_laplace_rdp_to_dp(epsilons, delta):
    """Convert the numerical Laplace-only RDP diagnostic to (epsilon, delta)."""
    try:
        delta = float(delta)
    except (TypeError, ValueError, OverflowError) as exc:
        raise ValueError("delta must be a real number") from exc
    if not np.isfinite(delta) or not 0 < delta < 1:
        raise ValueError("delta must be finite and lie in (0, 1)")
    epsilons = _validated_epsilons(epsilons)
    epsilons = epsilons[epsilons > 1e-12]
    if len(epsilons) == 0:
        return 0.0, 2.0

    def objective(alpha):
        return laplace_rdp_epsilon(alpha, epsilons) + np.log(1.0 / delta) / (alpha - 1)

    result = minimize_scalar(objective, bounds=(1.1, 100.0), method="bounded")
    return float(result.fun), float(result.x)


def convert_rdp_to_dp(epsilons, delta):
    """Backward-compatible name for the numerical Laplace-only diagnostic."""
    return convert_laplace_rdp_to_dp(epsilons, delta)

