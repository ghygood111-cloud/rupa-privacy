from copy import deepcopy

import numpy as np
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
from rupa_privacy.exceptions import (
    ConfigurationError,
    DataValidationError,
    PrivacySafetyError,
)
from rupa_privacy.governance import dataframe_version_hash, release_schema_hash
from rupa_privacy.ledger import PrivacyLedger


def _production_components(tmp_path, calibration_mode="synthetic"):
    schema = example_schema()
    privacy = example_privacy_config()
    privacy.randomness_mode = "production"
    privacy.random_seed = None
    privacy.calibration_mode = calibration_mode
    privacy.release_data_mode = "confidential"
    privacy.release_source = "confidential industrial release table"
    accounting = example_privacy_accounting_config(tmp_path / "ledger.sqlite3")
    accounting.maximum_cumulative_epsilon = 20.0
    return (
        schema,
        privacy,
        example_constraints(),
        example_regulatory_prior(),
        example_adjacency_config(),
        accounting,
    )


def _pipeline(components):
    return RUPAPipeline(*components)


def _reserve(components, release, run_id):
    schema, privacy, _, _, adjacency, accounting = components
    ledger = PrivacyLedger(accounting.ledger_path)
    reservation = ledger.begin_release(
        dataset_id=accounting.dataset_id,
        dataset_version_hash=dataframe_version_hash(
            release, [adjacency.privacy_unit_id] + schema.released_columns
        ),
        privacy_unit_id=adjacency.privacy_unit_id,
        adjacency=adjacency.type,
        release_schema_hash=release_schema_hash(schema, adjacency),
        epsilon_total=privacy.epsilon_total,
        epsilon_numeric=privacy.epsilon_numeric,
        epsilon_categorical=privacy.epsilon_categorical,
        mechanism_summary="pytest production mechanism",
        run_id=run_id,
        maximum_cumulative_epsilon=accounting.maximum_cumulative_epsilon,
        randomness_mode=privacy.randomness_mode,
    )
    return ledger, reservation


def test_production_rejects_configured_or_override_seed(tmp_path):
    components = list(_production_components(tmp_path))
    components[1].random_seed = 123
    with pytest.raises(ConfigurationError, match="rejects fixed random_seed"):
        _pipeline(components)

    components = _production_components(tmp_path)
    calibration, release = generate_example_pair(40, 50)
    pipeline = _pipeline(components).fit(calibration)
    _, reservation = _reserve(components, release, "seed_override")
    with pytest.raises(PrivacySafetyError, match="rejects fixed seeds"):
        pipeline.transform(release, seed=123, production_authorization=reservation)


def test_production_requires_ledger_authorization(tmp_path):
    components = _production_components(tmp_path)
    calibration, release = generate_example_pair(40, 50)
    pipeline = _pipeline(components).fit(calibration)
    with pytest.raises(PrivacySafetyError, match="ledger reservation"):
        pipeline.transform(release)


def test_production_repeated_input_is_not_replayable(tmp_path):
    components = _production_components(tmp_path)
    calibration, release = generate_example_pair(60, 80)
    pipeline = _pipeline(components).fit(calibration)
    ledger, first_reservation = _reserve(components, release, "production_first")
    first = pipeline.transform(release, production_authorization=first_reservation)
    ledger.mark_released("production_first", "a" * 64)
    _, second_reservation = _reserve(components, release, "production_second")
    second = pipeline.transform(release, production_authorization=second_reservation)
    assert not np.array_equal(
        first.release_data[components[0].numeric_columns].to_numpy(),
        second.release_data[components[0].numeric_columns].to_numpy(),
    )
    assert "seed" not in first.diagnostics


def test_reproducibility_mode_rejects_confidential_release():
    privacy = example_privacy_config()
    privacy.release_data_mode = "confidential"
    with pytest.raises(ConfigurationError, match="not permitted for confidential"):
        RUPAPipeline(
            example_schema(),
            privacy,
            example_constraints(),
            example_regulatory_prior(),
            example_adjacency_config(),
            example_privacy_accounting_config(),
        )


def test_privacy_unit_id_is_required_unique_and_nonmissing(example_run):
    pipeline, calibration, release, _ = example_run
    with pytest.raises(DataValidationError, match="missing fields"):
        pipeline.fit(calibration.drop(columns=["enterprise_id"]))

    duplicate = release.copy()
    duplicate.loc[1, "enterprise_id"] = duplicate.loc[0, "enterprise_id"]
    with pytest.raises(DataValidationError, match="exactly one row"):
        pipeline.transform(duplicate)

    missing = release.copy()
    missing.loc[0, "enterprise_id"] = None
    with pytest.raises(DataValidationError, match="missing privacy_unit_id"):
        pipeline.transform(missing)


@pytest.mark.parametrize(
    "field,value,message",
    [
        ("type", "add_remove", "Only fixed_roster_replace_one"),
        ("roster_is_public", False, "roster_is_public=true"),
        ("one_row_per_unit", False, "one_row_per_unit=true"),
    ],
)
def test_unsupported_adjacency_settings_are_rejected(field, value, message):
    adjacency = example_adjacency_config()
    setattr(adjacency, field, value)
    with pytest.raises(ConfigurationError, match=message):
        RUPAPipeline(
            example_schema(),
            example_privacy_config(),
            example_constraints(),
            example_regulatory_prior(),
            adjacency,
            example_privacy_accounting_config(),
        )


def test_disjoint_private_overlap_is_rejected_before_fit(tmp_path):
    components = _production_components(tmp_path, "disjoint_private")
    calibration, release = generate_example_pair(50, 60)
    overlap = release.copy()
    overlap.loc[0, "enterprise_id"] = calibration.loc[0, "enterprise_id"]
    with pytest.raises(PrivacySafetyError, match="overlaps release privacy units"):
        _pipeline(components).fit_transform(calibration, overlap)


def test_disjoint_private_subjects_pass_and_roster_is_preserved(tmp_path):
    components = _production_components(tmp_path, "disjoint_private")
    calibration, release = generate_example_pair(50, 60)
    _, reservation = _reserve(components, release, "disjoint_pass")
    result = _pipeline(components).fit_transform(
        calibration, release, production_authorization=reservation
    )
    assert result.governance_audit["calibration_release_disjoint_check"] == "PASS"
    assert result.governance_audit["overlap_count_internal"] == 0
    assert result.release_data["enterprise_id"].tolist() == release[
        "enterprise_id"
    ].tolist()


def test_public_calibration_requires_confirmation_and_source():
    privacy = example_privacy_config()
    privacy.calibration_mode = "public"
    privacy.calibration_source = ""
    privacy.calibration_public_confirmed = False
    with pytest.raises(ConfigurationError, match="explicit confirmation"):
        RUPAPipeline(
            example_schema(),
            privacy,
            example_constraints(),
            example_regulatory_prior(),
            example_adjacency_config(),
            example_privacy_accounting_config(),
        )
