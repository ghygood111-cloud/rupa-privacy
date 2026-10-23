"""Apply one configured mechanism per released field without estimating metadata."""

import pandas as pd

from ..models import AllocationResult, DataSchema, PrivacyConfig
from ..randomness import create_random_source
from .categorical import generalized_randomized_response
from .numerical import add_bounded_laplace_noise


def perturb_release_data(
    release_data: pd.DataFrame,
    schema: DataSchema,
    privacy: PrivacyConfig,
    allocation: AllocationResult,
    seed=None,
):
    rng = create_random_source(privacy, seed_override=seed)
    output = pd.DataFrame(index=release_data.index)
    for name in schema.released_columns:
        if name in schema.numeric_columns:
            output[name] = add_bounded_laplace_noise(
                release_data[name].to_numpy(dtype=float),
                allocation.epsilon[name],
                schema.public_bounds[name],
                rng,
            )
        elif privacy.categorical_mode == "randomized_response":
            output[name] = generalized_randomized_response(
                release_data[name].to_numpy(),
                allocation.epsilon[name],
                schema.public_categories[name],
                rng,
            )
    return output
