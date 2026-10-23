import numpy as np
import pytest

from rupa_privacy.accounting import convert_laplace_rdp_to_dp
from rupa_privacy.exceptions import DataValidationError
from rupa_privacy.mechanisms import generalized_randomized_response


def test_accounting_scopes_are_separated(example_run):
    _, _, _, result = example_run
    audit = result.privacy_audit
    assert np.isclose(audit["basic_composition_epsilon"], 5.0)
    assert audit["numerical_laplace_rdp_diagnostic"]["scope"] == "numerical Laplace mechanisms only"
    assert audit["mixed_laplace_randomized_response_rdp_bound_established"] is False
    numeric_eps = [
        result.allocation_result.epsilon[name]
        for name in result.noisy_data.columns
        if name not in {"province", "scale"}
    ]
    expected, _ = convert_laplace_rdp_to_dp(numeric_eps, 1e-5)
    assert np.isclose(audit["numerical_laplace_rdp_diagnostic"]["epsilon"], expected)


def test_randomized_response_rejects_unknown_private_category():
    rng = np.random.default_rng(1)
    with pytest.raises(DataValidationError, match="outside the configured public domain"):
        generalized_randomized_response(["known", "secret"], 1.0, ["known", "other"], rng)


def test_randomized_response_matches_theoretical_retention_probability():
    rng = np.random.default_rng(7)
    values = np.array(["a"] * 20000)
    epsilon = 1.2
    categories = ["a", "b", "c"]
    released = generalized_randomized_response(values, epsilon, categories, rng)
    empirical = np.mean(released == values)
    theoretical = np.exp(epsilon) / (np.exp(epsilon) + len(categories) - 1)
    assert abs(empirical - theoretical) < 0.015
