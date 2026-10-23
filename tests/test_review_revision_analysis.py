"""Offline reviewer diagnostics must not alter the production release contract."""
from dataclasses import replace
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from rupa_privacy.io import load_pipeline_config
from experiments.review_revision_20261021.analysis import (
    bootstrap_mean_difference, clipped_laplace_moments, numerical_metrics,
    require_research_inputs, uniform_numeric_allocation,
)

ROOT = Path(__file__).resolve().parents[1]


@pytest.mark.parametrize("epsilon", [float("nan"), float("inf"), float("-inf"), 0, -1])
def test_clipping_diagnostic_rejects_invalid_epsilon(epsilon):
    with pytest.raises(ValueError):
        clipped_laplace_moments([.5], 0, 1, epsilon)


@pytest.mark.parametrize("bounds", [(0, 0), (1, 0), (0, float("inf")), (float("nan"), 1)])
def test_clipping_diagnostic_requires_finite_public_bounds(bounds):
    with pytest.raises(ValueError):
        clipped_laplace_moments([.5], *bounds, 1)


def test_exact_clipping_expectation_matches_monte_carlo():
    x = np.array([0, .1, .5, .9, 1])
    expected, probability = clipped_laplace_moments(x, 0, 1, .5)
    noisy = np.clip(x + np.random.default_rng(19).laplace(0, 2, size=(300000, 5)), 0, 1)
    np.testing.assert_allclose(noisy.mean(axis=0), expected, atol=.003)
    np.testing.assert_allclose(((noisy == 0) | (noisy == 1)).mean(axis=0), probability, atol=.003)
    assert expected[2] == pytest.approx(.5)


@pytest.mark.parametrize("changes", [
    {"randomness_mode": "production"}, {"release_data_mode": "confidential"},
    {"calibration_mode": "disjoint_private"},
    {"release_data_mode": "public_demonstration", "release_public_confirmed": False},
    {"calibration_mode": "public", "calibration_public_confirmed": False},
])
def test_offline_evaluation_refuses_private_or_unconfirmed_inputs(changes):
    _, privacy, *_ = load_pipeline_config(ROOT / "examples/hazardous_waste/config_reproducibility.yaml")
    with pytest.raises(ValueError):
        require_research_inputs(replace(privacy, **changes))


@pytest.mark.parametrize("example", ["hazardous_waste", "ontario_registration"])
def test_offline_evaluation_accepts_declared_research_examples(example):
    _, privacy, *_ = load_pipeline_config(ROOT / "examples" / example / "config_reproducibility.yaml")
    require_research_inputs(privacy)


def test_paired_bootstrap_keeps_identical_seed_pairs():
    a = np.arange(30, dtype=float)
    result = bootstrap_mean_difference(a, a)
    assert result["mean_difference"] == result["ci95_lower"] == result["ci95_upper"] == 0
    assert result["pairs"] == 30


def test_paired_bootstrap_rejects_unmatched_vectors():
    with pytest.raises(ValueError):
        bootstrap_mean_difference([1, 2], [1])


def test_identity_release_has_zero_task_error():
    schema, *_ = load_pipeline_config(ROOT / "examples/hazardous_waste/config_reproducibility.yaml")
    frame = pd.read_csv(ROOT / "examples/hazardous_waste/release.csv")
    metrics = numerical_metrics(frame, frame, schema)
    for name in ("median_field_total_error_percent", "cross_share_error_pp", "mae_range", "wasserstein_range", "mean_ks"):
        assert metrics[name] == 0


def test_undefined_relative_error_is_not_silently_zeroed():
    schema, *_ = load_pipeline_config(ROOT / "examples/hazardous_waste/config_reproducibility.yaml")
    frame = pd.read_csv(ROOT / "examples/hazardous_waste/release.csv")
    frame[schema.numeric_columns[0]] = 0
    with pytest.raises(ValueError, match="undefined"):
        numerical_metrics(frame, frame, schema)


def test_release_digest_is_portable_to_locked_pandas_api():
    from experiments.review_revision_20261021.run import digest
    frame = pd.DataFrame({"x": [.25, .5], "category": ["a", "b"]})
    assert digest(frame) == digest(frame.copy())
    assert len(digest(frame)) == 64


@pytest.mark.parametrize("section,key", [("numeric", "numeric"), ("sample", "sample_size")])
def test_protocol_section_names_match_driver_modes(section, key):
    import json
    protocol = json.loads((ROOT / "experiments/review_revision_20261021/protocol.json").read_text())
    actual_key = "sample_size" if section == "sample" else "numeric"
    assert actual_key == key and key in protocol


@pytest.mark.parametrize("name,filename", [("official", "config.yaml"), ("third_party_reuse", "config.yaml"),
    ("water_treatment", "config_reproducibility.yaml"), ("hazardous_waste", "config_reproducibility.yaml"),
    ("ontario_registration", "config_reproducibility.yaml")])
def test_clean_wheel_harness_uses_existing_example_files(name, filename):
    folder = ROOT / "examples" / name
    assert all((folder / x).is_file() for x in (filename, "calibration.csv", "release.csv"))
