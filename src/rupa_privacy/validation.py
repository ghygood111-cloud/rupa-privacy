"""Validation that prevents private metadata inference during transformation."""

from numbers import Integral, Real
from typing import Iterable, Sequence

import numpy as np
import pandas as pd
from pandas.api.types import is_numeric_dtype

from .exceptions import ConfigurationError, DataValidationError
from .models import (
    ADJACENCY_TYPES,
    CALIBRATION_MODES,
    CATEGORICAL_BUDGET_STRATEGIES,
    NUMERIC_BUDGET_STRATEGIES,
    RANDOMNESS_MODES,
    RELEASE_DATA_MODES,
    AdjacencyConfig,
    DataSchema,
    PhysicalConstraint,
    PrivacyAccountingConfig,
    PrivacyConfig,
)
from .physics.validation import require_valid_physical_constraints


REGULATORY_PRIOR_SUM_ATOL = 1e-6


def _duplicates(values: Sequence[str]):
    return sorted({value for value in values if values.count(value) > 1})


def _require_finite_real(name, value):
    if isinstance(value, (bool, np.bool_)) or not isinstance(value, Real):
        raise ConfigurationError(name + " must be a real number")
    if not np.isfinite(float(value)):
        raise ConfigurationError(name + " must be finite")
    return float(value)


def _require_integer(name, value):
    if isinstance(value, (bool, np.bool_)) or not isinstance(value, Integral):
        raise ConfigurationError(name + " must be an integer")
    return int(value)


def validate_configuration(
    schema: DataSchema,
    privacy: PrivacyConfig,
    constraints: Iterable[PhysicalConstraint],
    regulatory_prior,
    adjacency: AdjacencyConfig,
    privacy_accounting: PrivacyAccountingConfig,
):
    for name in (
        "randomness_mode",
        "calibration_mode",
        "calibration_source",
        "release_data_mode",
        "release_source",
        "categorical_mode",
        "categorical_budget_strategy",
        "numeric_budget_strategy",
    ):
        if not isinstance(getattr(privacy, name), str):
            raise ConfigurationError(name + " must be a string")
    for name in ("calibration_public_confirmed", "release_public_confirmed"):
        if not isinstance(getattr(privacy, name), bool):
            raise ConfigurationError(name + " must be true or false")
    for name in ("dataset_id", "ledger_path"):
        if not isinstance(getattr(privacy_accounting, name), str):
            raise ConfigurationError("privacy_accounting." + name + " must be a string")
    if not isinstance(adjacency.privacy_unit_id, str):
        raise ConfigurationError("adjacency.privacy_unit_id must be a string")

    for name in (
        "epsilon_total",
        "epsilon_numeric",
        "epsilon_categorical",
        "delta",
        "utility_alpha",
        "repair_alpha",
        "categorical_risk_smoothing",
        "numeric_risk_smoothing",
        "numeric_stability_weight",
        "numeric_min_uniform_fraction",
        "numeric_max_uniform_multiple",
    ):
        _require_finite_real(name, getattr(privacy, name))
    _require_finite_real(
        "maximum_cumulative_epsilon",
        privacy_accounting.maximum_cumulative_epsilon,
    )
    for name in ("nmi_bins", "joint_bins", "knee_grid_points"):
        _require_integer(name, getattr(privacy, name))
    if privacy.random_seed is not None:
        _require_finite_real("random_seed", privacy.random_seed)
        if _require_integer("random_seed", privacy.random_seed) < 0:
            raise ConfigurationError("random_seed must be non-negative")

    groups = schema.numeric_columns + schema.categorical_columns
    duplicates = _duplicates(groups)
    if duplicates:
        raise ConfigurationError("Fields cannot be both numeric/categorical or repeated: " + ", ".join(duplicates))
    if not schema.sensitive_target:
        raise ConfigurationError("sensitive_target must be declared")
    if schema.sensitive_target in schema.released_columns:
        raise ConfigurationError("The sensitive target cannot appear in released_columns")
    overlap = set(schema.excluded_columns) & set(schema.released_columns)
    if overlap:
        raise ConfigurationError("Excluded fields cannot be released: " + ", ".join(sorted(overlap)))
    undeclared = set(schema.released_columns) - set(groups)
    if undeclared:
        raise ConfigurationError("Released fields must be declared numeric or categorical: " + ", ".join(sorted(undeclared)))
    if set(groups) != set(schema.released_columns):
        missing = set(groups) - set(schema.released_columns)
        raise ConfigurationError("All protected fields must be listed in released_columns: " + ", ".join(sorted(missing)))
    if adjacency.privacy_unit_id in set(groups) | {schema.sensitive_target}:
        raise ConfigurationError(
            "privacy_unit_id is a public roster key and cannot be a protected field or sensitive target"
        )
    if adjacency.type not in ADJACENCY_TYPES:
        raise ConfigurationError(
            "Only fixed_roster_replace_one adjacency is supported"
        )
    if not adjacency.privacy_unit_id.strip():
        raise ConfigurationError("adjacency.privacy_unit_id must be non-empty")
    if adjacency.roster_is_public is not True:
        raise ConfigurationError("fixed-roster release requires roster_is_public=true")
    if adjacency.one_row_per_unit is not True:
        raise ConfigurationError("fixed-roster release requires one_row_per_unit=true")

    for name in schema.numeric_columns:
        if name not in schema.public_bounds:
            raise ConfigurationError("Missing public bounds for numerical field: " + name)
        lo, hi = schema.public_bounds[name]
        if not np.isfinite([lo, hi]).all() or lo >= hi:
            raise ConfigurationError("Invalid public bounds for numerical field: " + name)
    extra_bounds = set(schema.public_bounds) - set(schema.numeric_columns)
    if extra_bounds:
        raise ConfigurationError("Bounds configured for non-numerical fields: " + ", ".join(sorted(extra_bounds)))

    for name in schema.categorical_columns:
        domain = schema.public_categories.get(name)
        if not domain:
            raise ConfigurationError("Missing non-empty public category domain for: " + name)
        if len(domain) != len({str(value) for value in domain}):
            raise ConfigurationError("Public category domain contains duplicates for: " + name)
    extra_domains = set(schema.public_categories) - set(schema.categorical_columns)
    if extra_domains:
        raise ConfigurationError("Category domains configured for non-categorical fields: " + ", ".join(sorted(extra_domains)))

    if privacy.epsilon_total <= 0 or privacy.epsilon_numeric < 0 or privacy.epsilon_categorical < 0:
        raise ConfigurationError("Privacy budgets must be non-negative and epsilon_total must be positive")
    if not np.isclose(
        privacy.epsilon_numeric + privacy.epsilon_categorical,
        privacy.epsilon_total,
        rtol=0.0,
        atol=1e-12,
    ):
        raise ConfigurationError("epsilon_numeric + epsilon_categorical must equal epsilon_total")
    if schema.numeric_columns and privacy.epsilon_numeric <= 0:
        raise ConfigurationError("Numerical fields require a positive epsilon_numeric")
    if schema.categorical_columns and privacy.categorical_mode == "randomized_response" and privacy.epsilon_categorical <= 0:
        raise ConfigurationError("Categorical randomized response requires a positive epsilon_categorical")
    if privacy.categorical_mode not in {"randomized_response", "drop"}:
        raise ConfigurationError("categorical_mode must be randomized_response or drop")
    if privacy.categorical_budget_strategy not in CATEGORICAL_BUDGET_STRATEGIES:
        raise ConfigurationError(
            "categorical_budget_strategy must be heuristic_risk_utility or uniform"
        )
    if privacy.categorical_risk_smoothing <= 0:
        raise ConfigurationError(
            "categorical_risk_smoothing must be finite and positive"
        )
    if privacy.numeric_budget_strategy not in NUMERIC_BUDGET_STRATEGIES:
        raise ConfigurationError(
            "numeric_budget_strategy must be legacy_rupa, balanced_rupa or uniform"
        )
    if privacy.numeric_risk_smoothing <= 0:
        raise ConfigurationError("numeric_risk_smoothing must be positive")
    if privacy.numeric_stability_weight < 0:
        raise ConfigurationError("numeric_stability_weight must be non-negative")
    if not 0 < privacy.numeric_min_uniform_fraction <= 1:
        raise ConfigurationError("numeric_min_uniform_fraction must lie in (0, 1]")
    if privacy.numeric_max_uniform_multiple < 1:
        raise ConfigurationError("numeric_max_uniform_multiple must be at least 1")
    if not isinstance(privacy.joint_nmi_diagnostic, bool):
        raise ConfigurationError("joint_nmi_diagnostic must be true or false")
    if privacy.categorical_mode == "drop" and privacy.epsilon_categorical != 0:
        raise ConfigurationError(
            "categorical_mode=drop requires epsilon_categorical=0; assign the total budget explicitly"
        )
    if privacy.calibration_mode not in CALIBRATION_MODES:
        raise ConfigurationError("calibration_mode must be public, synthetic, or disjoint_private")
    if privacy.randomness_mode not in RANDOMNESS_MODES:
        raise ConfigurationError("randomness_mode must be reproducibility or production")
    if privacy.release_data_mode not in RELEASE_DATA_MODES:
        raise ConfigurationError(
            "release_data_mode must be synthetic, public_demonstration, or confidential"
        )
    if privacy.randomness_mode == "production":
        if privacy.random_seed is not None:
            raise ConfigurationError("Production mode rejects fixed random_seed values")
        if privacy.release_data_mode != "confidential":
            raise ConfigurationError(
                "Production mode requires release_data_mode=confidential"
            )
    else:
        if privacy.random_seed is None:
            raise ConfigurationError(
                "Reproducibility mode requires an explicit fixed random_seed"
            )
        if privacy.calibration_mode not in {"synthetic", "public"}:
            raise ConfigurationError(
                "Reproducibility mode permits only synthetic or confirmed public calibration"
            )
        if privacy.release_data_mode not in {"synthetic", "public_demonstration"}:
            raise ConfigurationError(
                "Reproducibility mode is not permitted for confidential data release"
            )
    if privacy.calibration_mode == "public":
        if not privacy.calibration_public_confirmed or not privacy.calibration_source.strip():
            raise ConfigurationError(
                "Public calibration requires explicit confirmation and a source description"
            )
    if privacy.release_data_mode == "public_demonstration":
        if not privacy.release_public_confirmed or not privacy.release_source.strip():
            raise ConfigurationError(
                "Public demonstration release requires explicit confirmation and a source description"
            )
    if not privacy_accounting.dataset_id.strip():
        raise ConfigurationError("privacy_accounting.dataset_id must be non-empty")
    if privacy_accounting.maximum_cumulative_epsilon <= 0:
        raise ConfigurationError(
            "maximum_cumulative_epsilon must be positive"
        )
    if not privacy_accounting.ledger_path.strip():
        raise ConfigurationError("privacy_accounting.ledger_path must be non-empty")
    if not 0.0 <= privacy.utility_alpha <= 1.0:
        raise ConfigurationError("utility_alpha must lie in [0, 1]")
    if not 0.0 <= privacy.repair_alpha <= 1.0:
        raise ConfigurationError("repair_alpha must lie in [0, 1]")
    if privacy.delta <= 0 or privacy.delta >= 1:
        raise ConfigurationError("delta must lie in (0, 1)")
    if privacy.nmi_bins < 2 or privacy.joint_bins < 2 or privacy.knee_grid_points < 2:
        raise ConfigurationError("NMI bins and knee_grid_points must be at least 2")

    expected = set(schema.released_columns)
    prior_fields = set(regulatory_prior)
    if prior_fields != expected:
        missing = expected - prior_fields
        extra = prior_fields - expected
        raise ConfigurationError(
            "Regulatory prior must match released fields; missing={0}, extra={1}".format(
                sorted(missing), sorted(extra)
            )
        )
    raw_prior_values = list(regulatory_prior.values())
    if any(
        isinstance(value, (bool, np.bool_)) or not isinstance(value, Real)
        for value in raw_prior_values
    ):
        raise ConfigurationError("Regulatory prior values must be real numbers")
    prior_values = np.asarray(raw_prior_values, dtype=float)
    if not np.isfinite(prior_values).all():
        raise ConfigurationError("Regulatory prior values must be finite")
    if np.any(prior_values < 0):
        raise ConfigurationError("Regulatory prior values must be non-negative")
    prior_sum = float(prior_values.sum())
    if prior_sum <= 0:
        raise ConfigurationError("Regulatory prior values must not all be zero")
    if not np.isclose(
        prior_sum, 1.0, rtol=0.0, atol=REGULATORY_PRIOR_SUM_ATOL
    ):
        raise ConfigurationError(
            "regulatory_prior must sum to 1; got {0:.12g}".format(prior_sum)
        )

    return require_valid_physical_constraints(schema, constraints)


def _validate_table(
    data: pd.DataFrame,
    schema: DataSchema,
    adjacency: AdjacencyConfig,
    require_target: bool,
    label: str,
):
    if not isinstance(data, pd.DataFrame):
        raise DataValidationError(label + " must be a pandas DataFrame")
    required = set(schema.released_columns)
    required.add(adjacency.privacy_unit_id)
    if require_target:
        required.add(schema.sensitive_target)
    missing = required - set(data.columns)
    if missing:
        raise DataValidationError(label + " is missing fields: " + ", ".join(sorted(missing)))
    if len(data) < 2:
        raise DataValidationError(label + " must contain at least two rows")
    unit_ids = data[adjacency.privacy_unit_id]
    if unit_ids.isna().any():
        raise DataValidationError(label + " contains missing privacy_unit_id values")
    if unit_ids.duplicated().any():
        raise DataValidationError(
            label + " must contain exactly one row per privacy unit"
        )
    for name in schema.numeric_columns:
        if not is_numeric_dtype(data[name]):
            raise DataValidationError("Numerical field has a non-numeric dtype: " + name)
        values = data[name].to_numpy(dtype=float)
        if not np.isfinite(values).all():
            raise DataValidationError("Numerical field contains missing or non-finite values: " + name)
    if require_target:
        if not is_numeric_dtype(data[schema.sensitive_target]):
            raise DataValidationError("Sensitive target must be numeric for the current NMI and attack workflow")
        target = data[schema.sensitive_target].to_numpy(dtype=float)
        if not np.isfinite(target).all():
            raise DataValidationError("Sensitive target contains missing or non-finite values")
        if len(np.unique(target)) < 2:
            raise DataValidationError(
                "calibration target must contain at least two distinct finite values"
            )
    for name in schema.categorical_columns:
        if data[name].isna().any():
            raise DataValidationError("Categorical field contains missing values: " + name)


def validate_calibration_data(data, schema, adjacency):
    _validate_table(
        data, schema, adjacency, require_target=True, label="calibration_data"
    )


def validate_release_data(data, schema, adjacency):
    _validate_table(
        data, schema, adjacency, require_target=False, label="release_data"
    )
    for name in schema.categorical_columns:
        allowed = set(schema.public_categories[name])
        observed = set(data[name].unique().tolist())
        unknown = observed - allowed
        if unknown:
            raise DataValidationError(
                "Release field {0} contains values outside its public category domain: {1}".format(
                    name, sorted(str(value) for value in unknown)
                )
            )
