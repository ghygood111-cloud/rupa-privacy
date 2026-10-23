from dataclasses import replace
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from rupa_privacy.allocation.workload import allocate_linear_workload_budget
from rupa_privacy.exceptions import BudgetOptimizationError, PrivacySafetyError
from rupa_privacy.io import load_pipeline_config
from experiments.task_statistics_20261022.study import allocate, draw_statistics, prepare_statistics

ROOT = Path(__file__).resolve().parents[1]


@pytest.mark.parametrize("cap", [True, False])
@pytest.mark.parametrize("seed", range(6))
def test_workload_budget_and_exact_expected_loss_not_worse_than_uniform(cap, seed):
    rng = np.random.default_rng(seed)
    risk, delta = rng.uniform(0, 1, 6), rng.uniform(1, 50, 6)
    workload = rng.normal(size=(4, 6))
    epsilon, info = allocate_linear_workload_budget(risk, delta, workload, 5, enforce_risk_cap=cap)
    assert epsilon.sum() == pytest.approx(5, abs=1e-9)
    assert np.all(epsilon >= .5 * 5 / 6 - 1e-10) and np.all(epsilon <= 2 * 5 / 6 + 1e-10)
    coefficients = 2 * delta ** 2 * np.sum(workload ** 2, axis=0)
    assert info["expected_noise_loss"] == pytest.approx(sum(coefficients / epsilon ** 2))
    assert info["noise_loss_ratio_to_uniform"] <= 1 + 1e-8
    if cap:
        assert sum(risk * epsilon ** 2) <= sum(risk * (5 / 6) ** 2) + 1e-8


@pytest.mark.parametrize("cap", [True, False])
def test_homogeneous_task_correctly_returns_uniform_instead_of_forcing_a_difference(cap):
    epsilon, _ = allocate_linear_workload_budget([.1, .2, .3], [1, 1, 1], np.eye(3), 3, enforce_risk_cap=cap)
    np.testing.assert_allclose(epsilon, [1, 1, 1], atol=1e-10)


@pytest.mark.parametrize("setting", [float("nan"), float("inf"), float("-inf"), 0, -1, True, "5"])
def test_invalid_privacy_budget_stops_before_mechanisms(setting):
    with pytest.raises(BudgetOptimizationError):
        allocate_linear_workload_budget([.1, .2], [1, 1], np.eye(2), setting)


@pytest.mark.parametrize("bad", [np.nan, np.inf, -np.inf])
@pytest.mark.parametrize("field", ["risk", "sensitivities", "linear_workload"])
def test_nonfinite_workload_components_fail_closed(field, bad):
    values = {"risk": [.1, .2], "sensitivities": [1, 1], "linear_workload": np.eye(2)}
    if field == "linear_workload":
        values[field][0, 0] = bad
    else:
        values[field][0] = bad
    with pytest.raises(BudgetOptimizationError):
        allocate_linear_workload_budget(**values, budget=3)


def test_empty_workload_channel_is_rejected():
    with pytest.raises(BudgetOptimizationError):
        allocate_linear_workload_budget([.1, .2], [1, 1], [[1, 0]], 3)


def _prepared():
    folder = ROOT / "examples/hazardous_waste"
    settings = load_pipeline_config(folder / "config_reproducibility.yaml")
    return prepare_statistics(pd.read_csv(folder / "calibration.csv"), pd.read_csv(folder / "release.csv"), settings), settings


def test_statistical_adapter_uses_same_standardized_official_noise_for_paired_strategies():
    from experiments.task_statistics_20261022.study import official_laplace
    try:
        official_laplace()
    except ModuleNotFoundError as exc:
        if exc.name == "diffprivlib":
            pytest.skip("Install the optional statistical research requirements for the official-mechanism test")
        raise
    prepared, _ = _prepared()
    uniform, _ = allocate(prepared, 5, "uniform_statistics")
    optimized, _ = allocate(prepared, 5, "workload_rupa")
    a, b = draw_statistics(prepared, uniform, 31), draw_statistics(prepared, optimized, 31)
    np.testing.assert_allclose((a["noisy"] - prepared["truth"]) * uniform / prepared["delta"],
                               (b["noisy"] - prepared["truth"]) * optimized / prepared["delta"], atol=1e-12)
    assert a["final_clipped"].shape == uniform.shape


def test_allocation_does_not_read_release_values():
    prepared, _ = _prepared()
    epsilon, _ = allocate(prepared, 5, "workload_rupa")
    prepared["truth"] = prepared["truth"] * 1.5
    same, _ = allocate(prepared, 5, "workload_rupa")
    np.testing.assert_array_equal(epsilon, same)


@pytest.mark.parametrize("bad", [float("nan"), float("inf"), float("-inf"), 0, True])
def test_uniform_statistical_adapter_rejects_invalid_budget_too(bad):
    prepared, _ = _prepared()
    with pytest.raises(ValueError, match="Finite positive"):
        allocate(prepared, bad, "uniform_statistics")


def test_statistical_fitting_refuses_calibration_subject_reuse():
    folder = ROOT / "examples/hazardous_waste"
    settings = load_pipeline_config(folder / "config_reproducibility.yaml")
    calibration = pd.read_csv(folder / "calibration.csv")
    release = calibration.drop(columns=[settings[0].sensitive_target]).iloc[:3]
    with pytest.raises(PrivacySafetyError, match="disjoint"):
        prepare_statistics(calibration, release, settings)


@pytest.mark.parametrize("mode", ["production", "confidential", "private_calibration"])
def test_research_adapter_refuses_secret_or_production_release(mode):
    prepared, _ = _prepared()
    config = prepared["privacy"]
    if mode == "production":
        config = replace(config, randomness_mode="production", random_seed=None)
    elif mode == "confidential":
        config = replace(config, release_data_mode="confidential")
    else:
        config = replace(config, calibration_mode="disjoint_private")
    prepared["privacy"] = config
    with pytest.raises(ValueError):
        allocate(prepared, 5, "workload_rupa")
