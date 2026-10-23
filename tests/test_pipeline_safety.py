from copy import deepcopy

import pytest

from rupa_privacy import RUPAPipeline
from rupa_privacy.data import (
    example_adjacency_config,
    example_constraints,
    example_privacy_accounting_config,
    example_privacy_config,
    example_regulatory_prior,
    example_schema,
    generate_example_pair,
)
from rupa_privacy.exceptions import ConfigurationError, DataValidationError, NotFittedError


def _pipeline(schema=None, privacy=None):
    return RUPAPipeline(
        schema or example_schema(),
        privacy or example_privacy_config(),
        example_constraints(),
        example_regulatory_prior(),
        example_adjacency_config(),
        example_privacy_accounting_config(),
    )


def test_transform_requires_fit():
    _, release = generate_example_pair(n_release=20, n_calibration=20)
    with pytest.raises(NotFittedError):
        _pipeline().transform(release)


def test_sensitive_target_is_never_released(example_run):
    pipeline, _, _, result = example_run
    assert pipeline.schema.sensitive_target not in result.release_data.columns
    assert result.metadata["sensitive_target_released"] is False
    assert list(result.release_data.columns) == [
        pipeline.adjacency_config.privacy_unit_id
    ] + pipeline.schema.released_columns


def test_release_category_must_belong_to_public_domain(example_run):
    pipeline, _, release, _ = example_run
    invalid = release.copy()
    invalid.loc[0, "province"] = "private_new_category"
    with pytest.raises(DataValidationError, match="outside its public category domain"):
        pipeline.transform(invalid)


def test_missing_public_category_domain_is_rejected():
    schema = example_schema()
    del schema.public_categories["province"]
    with pytest.raises(ConfigurationError, match="Missing non-empty public category domain"):
        _pipeline(schema=schema)


def test_budget_partition_must_sum_to_total():
    privacy = example_privacy_config()
    privacy.epsilon_numeric = 4.5
    with pytest.raises(ConfigurationError, match="must equal epsilon_total"):
        _pipeline(privacy=privacy)


def test_private_calibration_mode_reports_scope_warning():
    calibration, _ = generate_example_pair(n_release=40, n_calibration=40)
    privacy = example_privacy_config()
    privacy.randomness_mode = "production"
    privacy.random_seed = None
    privacy.calibration_mode = "disjoint_private"
    privacy.calibration_source = "separately collected private calibration cohort"
    privacy.release_data_mode = "confidential"
    privacy.release_public_confirmed = False
    pipeline = _pipeline(privacy=privacy).fit(calibration)
    assert "disjoint" in pipeline.fitted_state_.warnings[0]


def test_categorical_drop_requires_zero_categorical_budget():
    privacy = example_privacy_config()
    privacy.categorical_mode = "drop"
    with pytest.raises(ConfigurationError, match="requires epsilon_categorical=0"):
        _pipeline(privacy=privacy)


def test_transform_uses_configured_bounds_and_full_public_category_domain(example_run):
    pipeline, _, release, _ = example_run
    narrow = release.copy()
    narrow["wastewater"] = 3000.0
    narrow["province"] = "hebei"
    result = pipeline.transform(narrow)
    assert result.allocation_result.sensitivities["wastewater"] == 6000.0
    assert set(result.noisy_data["province"]) - {"hebei"}
