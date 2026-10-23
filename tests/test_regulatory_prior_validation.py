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
from rupa_privacy.exceptions import ConfigurationError
from rupa_privacy.utility import compute_utility_weights


def _pipeline_with_prior(prior):
    return RUPAPipeline(
        example_schema(),
        example_privacy_config(),
        example_constraints(),
        prior,
        example_adjacency_config(),
        example_privacy_accounting_config(),
    )


def test_prior_sum_exactly_one_passes():
    pipeline = _pipeline_with_prior(example_regulatory_prior())
    assert sum(pipeline.regulatory_prior.values()) == pytest.approx(1.0)


def test_prior_sum_with_small_rounding_error_passes():
    prior = example_regulatory_prior()
    prior["wastewater"] += 5e-7
    pipeline = _pipeline_with_prior(prior)
    assert sum(pipeline.regulatory_prior.values()) == pytest.approx(1.0000005)


@pytest.mark.parametrize("total", [10.0, 0.9, 1.1])
def test_prior_sum_outside_tolerance_fails(total):
    prior = example_regulatory_prior()
    scale = total / sum(prior.values())
    prior = {name: value * scale for name, value in prior.items()}
    with pytest.raises(
        ConfigurationError,
        match=r"regulatory_prior must sum to 1; got",
    ):
        _pipeline_with_prior(prior)


@pytest.mark.parametrize(
    ("value", "message"),
    [
        (-0.01, "must be non-negative"),
        (float("nan"), "must be finite"),
        (float("inf"), "must be finite"),
        (True, "must be real numbers"),
        ("0.15", "must be real numbers"),
    ],
)
def test_invalid_prior_value_fails(value, message):
    prior = example_regulatory_prior()
    prior["wastewater"] = value
    with pytest.raises(ConfigurationError, match=message):
        _pipeline_with_prior(prior)


def test_all_zero_prior_fails():
    prior = {name: 0.0 for name in example_regulatory_prior()}
    with pytest.raises(ConfigurationError, match="must not all be zero"):
        _pipeline_with_prior(prior)


def test_alpha_zero_is_entropy_only():
    calibration, _ = generate_example_pair(n_calibration=120, n_release=20)
    result = compute_utility_weights(
        calibration,
        example_schema(),
        example_regulatory_prior(),
        alpha=0.0,
    )
    assert result.utility_weights == pytest.approx(result.entropy_weights)


def test_alpha_one_is_prior_only():
    calibration, _ = generate_example_pair(n_calibration=120, n_release=20)
    prior = example_regulatory_prior()
    result = compute_utility_weights(
        calibration, example_schema(), prior, alpha=1.0
    )
    assert result.utility_weights == pytest.approx(prior)


def test_interior_alpha_has_direct_mixture_meaning():
    calibration, _ = generate_example_pair(n_calibration=120, n_release=20)
    prior = example_regulatory_prior()
    alpha = 0.6
    result = compute_utility_weights(
        calibration, example_schema(), prior, alpha=alpha
    )
    expected = {
        name: alpha * prior[name] + (1.0 - alpha) * result.entropy_weights[name]
        for name in example_schema().released_columns
    }
    assert np.isclose(sum(result.entropy_weights.values()), 1.0)
    assert np.isclose(sum(expected.values()), 1.0)
    assert result.utility_weights == pytest.approx(expected)
