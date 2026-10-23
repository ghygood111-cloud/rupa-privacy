"""Utility weighting extracted from the current root step 3 implementation."""

import numpy as np
import pandas as pd

from ..models import DataSchema, UtilityResult


def compute_utility_weights(
    calibration_data: pd.DataFrame,
    schema: DataSchema,
    regulatory_prior,
    alpha=0.6,
):
    entropy_information = {}
    for name in schema.released_columns:
        if name in schema.categorical_columns:
            _, counts = np.unique(calibration_data[name].to_numpy(), return_counts=True)
            if len(counts) <= 1:
                entropy = 0.0
            else:
                probabilities = counts / counts.sum()
                entropy = -np.sum(probabilities * np.log(probabilities + 1e-10)) / np.log(len(counts))
        else:
            values = calibration_data[name].to_numpy(dtype=float)
            span = values.max() - values.min()
            if span <= 0:
                entropy = 0.0
            else:
                normalized = (values - values.min()) / span + 1e-10
                histogram, _ = np.histogram(normalized, bins=10)
                probabilities = histogram / histogram.sum()
                entropy = -np.sum(probabilities * np.log(probabilities + 1e-10)) / np.log(10)
        entropy_information[name] = float(1.0 - entropy)

    entropy_total = sum(entropy_information.values())
    if entropy_total <= 0:
        entropy_weights = {
            name: 1.0 / len(schema.released_columns)
            for name in schema.released_columns
        }
    else:
        entropy_weights = {
            name: entropy_information[name] / entropy_total
            for name in schema.released_columns
        }

    fused = {
        name: float(alpha) * float(regulatory_prior[name])
        + (1.0 - float(alpha)) * entropy_weights[name]
        for name in schema.released_columns
    }
    fused_total = sum(fused.values())
    utility_weights = {name: fused[name] / fused_total for name in schema.released_columns}
    return UtilityResult(
        prior_weights={name: float(regulatory_prior[name]) for name in schema.released_columns},
        entropy_weights=entropy_weights,
        utility_weights=utility_weights,
        alpha=float(alpha),
    )

