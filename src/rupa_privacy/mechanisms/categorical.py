"""Generalized randomized response over a configured public category domain."""

import numpy as np

from ..exceptions import DataValidationError


def generalized_randomized_response(values, epsilon, categories, rng):
    try:
        epsilon = float(epsilon)
    except (TypeError, ValueError, OverflowError) as exc:
        raise ValueError("epsilon must be a real number for randomized response") from exc
    if not np.isfinite(epsilon):
        raise ValueError("epsilon must be finite for randomized response")
    if epsilon < 0:
        raise ValueError("epsilon must be non-negative for randomized response")
    values = np.asarray(values)
    categories = np.asarray(list(categories))
    unknown = set(values.tolist()) - set(categories.tolist())
    if unknown:
        raise DataValidationError(
            "Categorical values fall outside the configured public domain: "
            + ", ".join(sorted(str(value) for value in unknown))
        )
    category_count = len(categories)
    if category_count <= 1 or epsilon == 0:
        return rng.choice(categories, size=len(values))
    keep_probability = np.exp(epsilon) / (np.exp(epsilon) + category_count - 1)
    keep = rng.random(len(values)) < keep_probability
    released = values.copy()
    for index in np.where(~keep)[0]:
        alternatives = categories[categories != values[index]]
        released[index] = rng.choice(alternatives)
    return released

