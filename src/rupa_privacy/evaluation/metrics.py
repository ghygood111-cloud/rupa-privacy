"""Numerical and categorical aggregate utility metrics."""

import numpy as np
from scipy.stats import ks_2samp, wasserstein_distance

from ..models import DataSchema


def _categorical_distribution(values, domain):
    values = np.asarray(values)
    return np.array([np.mean(values == item) for item in domain], dtype=float)


def evaluate_release_utility(original, released, schema: DataSchema):
    """Compare protected fields without copying private records into the audit."""
    numerical = {}
    for name in schema.numeric_columns:
        raw = original[name].to_numpy(dtype=float)
        protected = released[name].to_numpy(dtype=float)
        span = schema.public_bounds[name][1] - schema.public_bounds[name][0]
        numerical[name] = {
            "mean_absolute_relative_error": float(
                abs(raw.mean() - protected.mean()) / max(abs(raw.mean()), 0.01)
            ),
            "individual_mae_normalized_by_public_range": float(
                np.mean(np.abs(raw - protected)) / span
            ),
            "rmse_normalized_by_public_range": float(
                np.sqrt(np.mean((raw - protected) ** 2)) / span
            ),
            "standard_deviation_relative_error": float(
                abs(raw.std() - protected.std()) / max(raw.std(), 1e-12)
            ),
            "wasserstein_normalized_by_public_range": float(
                wasserstein_distance(raw, protected) / span
            ),
            "ks_statistic": float(ks_2samp(raw, protected).statistic),
        }

    categorical = {}
    for name in schema.categorical_columns:
        if name not in released.columns:
            continue
        raw = original[name].to_numpy()
        protected = released[name].to_numpy()
        domain = schema.public_categories[name]
        raw_distribution = _categorical_distribution(raw, domain)
        released_distribution = _categorical_distribution(protected, domain)
        total_variation = 0.5 * np.abs(raw_distribution - released_distribution).sum()
        categorical[name] = {
            "total_variation_distance": float(total_variation),
            "distribution_l1_error": float(2.0 * total_variation),
            "randomized_response_retention_rate": float(np.mean(raw == protected)),
        }

    numeric_mae = [
        values["individual_mae_normalized_by_public_range"]
        for values in numerical.values()
    ]
    category_tv = [values["total_variation_distance"] for values in categorical.values()]
    return {
        "numerical": numerical,
        "categorical": categorical,
        "summary": {
            "mean_numeric_individual_mae_by_public_range": float(np.mean(numeric_mae))
            if numeric_mae
            else 0.0,
            "mean_categorical_total_variation": float(np.mean(category_tv))
            if category_tv
            else 0.0,
        },
        "publication_note": (
            "Metrics are aggregate diagnostics. Decide separately whether an audit derived "
            "from raw confidential records is suitable for public release."
        ),
    }
