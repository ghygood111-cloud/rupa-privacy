import numpy as np
import pytest

from rupa_privacy.data import (
    example_adjacency_config,
    example_schema,
    generate_example_pair,
)
from rupa_privacy.exceptions import DataValidationError
from rupa_privacy.validation import validate_calibration_data


def _calibration(rows=20):
    calibration, _ = generate_example_pair(n_calibration=rows, n_release=10)
    return calibration


@pytest.mark.parametrize("value", [1, 1.25])
def test_constant_integer_or_float_target_is_rejected(value):
    calibration = _calibration()
    calibration["production"] = value
    with pytest.raises(
        DataValidationError,
        match="calibration target must contain at least two distinct finite values",
    ):
        validate_calibration_data(
            calibration, example_schema(), example_adjacency_config()
        )


def test_single_row_calibration_is_rejected_before_target_analysis():
    calibration = _calibration().iloc[:1].copy()
    with pytest.raises(DataValidationError, match="at least two rows"):
        validate_calibration_data(
            calibration, example_schema(), example_adjacency_config()
        )


def test_nonfinite_target_is_rejected_before_distinct_count():
    calibration = _calibration()
    calibration["production"] = 1.0
    calibration.loc[calibration.index[-1], "production"] = np.nan
    with pytest.raises(DataValidationError, match="missing or non-finite"):
        validate_calibration_data(
            calibration, example_schema(), example_adjacency_config()
        )


def test_two_distinct_target_values_pass():
    calibration = _calibration()
    calibration["production"] = np.where(
        np.arange(len(calibration)) == 0, 2.0, 1.0
    )
    validate_calibration_data(
        calibration, example_schema(), example_adjacency_config()
    )


def test_continuous_target_passes():
    calibration = _calibration()
    calibration["production"] = np.linspace(1.0, 2.0, len(calibration))
    validate_calibration_data(
        calibration, example_schema(), example_adjacency_config()
    )
