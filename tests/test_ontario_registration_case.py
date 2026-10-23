"""The external example and its downstream decoder never replace core logic."""
import importlib.util
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from rupa_privacy import RUPAPipeline
from rupa_privacy.models import DataSchema, PrivacyConfig, AdjacencyConfig, PrivacyAccountingConfig
from rupa_privacy.io import write_public_run, validate_public_run

ROOT = Path(__file__).resolve().parents[1]


def load_example_module(name):
    path = ROOT / "examples" / "ontario_registration" / (name + ".py")
    spec = importlib.util.spec_from_file_location("ontario_" + name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_registration_aggregation_preserves_leading_zero_and_splits_units():
    prepare = load_example_module("prepare")
    raw = pd.DataFrame({
        "GENERATOR_NUMBER": ["001", "001", "1", "02", "03", "04", "05", "06", None],
        "WASTE_CLASS_CODE": ["111", "112", "121", "121", "141", "141", "151", "151", "0"],
        "PHYSICAL_STATE": ["Liquid", "Solid", "Solid", "Gas", "Liquid", "Solid", "Liquid", "Solid", "Gas"],
    })
    extras = [{"GENERATOR_NUMBER": "T" + str(i), "WASTE_CLASS_CODE": str(j),
               "PHYSICAL_STATE": "Liquid"}
              for i in range(100) for j in range(1 + i % 2)]
    raw = pd.concat([raw, pd.DataFrame(extras)], ignore_index=True)
    calibration, release, diagnostics = prepare.prepare_frame(raw)
    assert diagnostics["registration_units"] == 107
    assert diagnostics["missing_registration_rows_excluded"] == 1
    assert set(calibration.public_registration_id).isdisjoint(release.public_registration_id)
    assert len(calibration) + len(release) == 107
    assert "registered_class_count" not in release
    assert "GENERATOR_NUMBER" not in calibration
    assert "COMPANY_LEGAL_PRIMARY_NAME" not in release


@pytest.mark.parametrize("epsilon", [0, -1, float("nan"), float("inf"), float("-inf")])
def test_downstream_decoder_rejects_invalid_field_epsilon(epsilon):
    with pytest.raises(ValueError):
        load_example_module("analysis").binary_parameters(epsilon)


def test_inverse_grr_channels_recover_marginals_and_joint_in_expectation():
    analysis = load_example_module("analysis")
    epsilons = (.6, 1.4)
    probabilities = (.1, .2, .3, .4)
    input_rows = [(0, 0), (0, 1), (1, 0), (1, 1)]
    decoded_marginal = np.zeros(2)
    decoded_both = 0.
    for (a, b), probability in zip(input_rows, probabilities):
        for y1, y2 in input_rows:
            weights, channel_probability = [], probability
            for epsilon, original, output in zip(epsilons, (a, b), (y1, y2)):
                p, q, gap = analysis.binary_parameters(epsilon)
                channel_probability *= p if original == output else q
                weights.append((output - q) / gap)
            decoded_marginal += channel_probability * np.asarray(weights)
            decoded_both += channel_probability * weights[0] * weights[1]
    np.testing.assert_allclose(decoded_marginal, [.7, .6], atol=1e-12)
    assert decoded_both == pytest.approx(.4)


@pytest.mark.parametrize("strategy", ["uniform", "heuristic_risk_utility"])
def test_category_only_public_api_and_actual_public_only_analysis(tmp_path, strategy):
    prepare, analysis = load_example_module("prepare"), load_example_module("analysis")
    values = prepare.config()
    schema = DataSchema.from_dict(values["schema"])
    privacy = PrivacyConfig.from_dict({**values["privacy"], "categorical_budget_strategy": strategy})
    adjacency = AdjacencyConfig.from_dict(values["adjacency"])
    accounting = PrivacyAccountingConfig.from_dict(values["privacy_accounting"])
    calibration = pd.DataFrame({
        "public_registration_id": ["CAL" + str(i) for i in range(20)],
        "handles_liquid": ["no", "yes"] * 10,
        "handles_solid": ["yes", "no", "yes", "yes"] * 5,
        "registered_class_count": list(range(1, 21)),
    })
    source = pd.DataFrame({
        "public_registration_id": ["REL" + str(i) for i in range(30)],
        "handles_liquid": ["no", "yes", "yes"] * 10,
        "handles_solid": ["yes", "no"] * 15,
    })
    pipeline = RUPAPipeline(schema, privacy, [], values["regulatory_prior"], adjacency, accounting).fit(calibration)
    result = pipeline.transform(source)
    run = write_public_run(result, schema, privacy, [], values["regulatory_prior"], adjacency,
                           accounting, tmp_path, run_id="ontario_test")
    assert validate_public_run(run, "registered_class_count")["release_rows"] == 30
    decoded = analysis.analyze_run(run)
    assert decoded["run_id"] == "ontario_test"
    assert decoded["rows"] == 30
    assert sum(result.allocation_result.epsilon.values()) == pytest.approx(2.0)
    assert list(pd.read_csv(run / "release_data.csv")) == ["public_registration_id", "handles_liquid", "handles_solid"]
    assert not (run / ".internal_audit").exists()
    for field in analysis.FIELDS:
        item = decoded["marginals"][field]
        assert np.isfinite(item["decoded_proportion_unclipped"])
        assert 0 <= item["simultaneous_95_lower"] <= item["simultaneous_95_upper"] <= 1


def test_decoder_retains_out_of_range_estimates_instead_of_hiding_them():
    analysis = load_example_module("analysis")
    public = pd.DataFrame({name: ["no"] * 10 for name in analysis.FIELDS})
    result = analysis.analyze_public_release(public, {name: 1. for name in analysis.FIELDS})
    for item in result["marginals"].values():
        assert item["decoded_proportion_unclipped"] < 0
        assert item["decoded_proportion_clipped_for_display"] == 0
