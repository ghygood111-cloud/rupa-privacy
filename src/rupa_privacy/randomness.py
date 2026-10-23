"""Random sources with separate research-reproduction and production policies."""

import secrets
from numbers import Integral

import numpy as np

from .exceptions import PrivacySafetyError


class SecureRandomSource:
    """Array-oriented adapter over ``secrets.SystemRandom``.

    ``SystemRandom`` obtains randomness from the operating system. It is slower than
    NumPy's deterministic PCG generator, but it does not expose a replay seed and is
    suitable for the current local production threat model. This is not a substitute
    for a hardened, independently audited DP noise library.
    """

    def __init__(self):
        self._rng = secrets.SystemRandom()

    def random(self, size=None):
        if size is None:
            return self._rng.random()
        count = int(np.prod(size)) if isinstance(size, tuple) else int(size)
        values = np.fromiter((self._rng.random() for _ in range(count)), dtype=float)
        return values.reshape(size) if isinstance(size, tuple) else values

    def laplace(self, loc, scale, size):
        if scale < 0:
            raise ValueError("Laplace scale must be non-negative")
        uniform = self.random(size) - 0.5
        samples = -float(scale) * np.sign(uniform) * np.log1p(-2.0 * np.abs(uniform))
        return float(loc) + samples

    def choice(self, values, size=None):
        values = np.asarray(values)
        if len(values) == 0:
            raise ValueError("Cannot sample from an empty collection")
        if size is None:
            return values[self._rng.randrange(len(values))]
        count = int(np.prod(size)) if isinstance(size, tuple) else int(size)
        selected = np.fromiter(
            (self._rng.randrange(len(values)) for _ in range(count)), dtype=np.int64
        )
        output = values[selected]
        return output.reshape(size) if isinstance(size, tuple) else output


def create_random_source(privacy, seed_override=None):
    """Create a source that enforces the configured randomness policy."""
    if privacy.randomness_mode == "production":
        if privacy.random_seed is not None or seed_override is not None:
            raise PrivacySafetyError(
                "Production mode rejects fixed seeds and seed overrides"
            )
        return SecureRandomSource()
    seed = privacy.random_seed if seed_override is None else seed_override
    if seed is None:
        raise PrivacySafetyError(
            "Reproducibility mode requires an explicit fixed random_seed"
        )
    if isinstance(seed, (bool, np.bool_)) or not isinstance(seed, Integral):
        raise PrivacySafetyError("Reproducibility random_seed must be an integer")
    if int(seed) < 0:
        raise PrivacySafetyError("Reproducibility random_seed must be non-negative")
    return np.random.default_rng(int(seed))
