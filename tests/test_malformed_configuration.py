from pathlib import Path

import pytest
import yaml

from rupa_privacy.cli import main
from rupa_privacy.data import generate_example_pair


def _write_inputs(tmp_path):
    calibration, release = generate_example_pair(n_calibration=30, n_release=20)
    calibration_path = tmp_path / "calibration.csv"
    release_path = tmp_path / "release.csv"
    calibration.to_csv(calibration_path, index=False)
    release.drop(columns=["production"]).to_csv(release_path, index=False)
    return calibration_path, release_path


def _base_config():
    return yaml.safe_load(Path("configs/example.yaml").read_text(encoding="utf-8"))


def _apply_case(values, case):
    if case == "short_bounds":
        values["schema"]["public_bounds"]["wastewater"] = [0]
    elif case == "bounds_type":
        values["schema"]["public_bounds"]["wastewater"] = "abc"
    elif case == "constraint_row_shape":
        values["constraints"][0]["coefficients"] = [1.0, -1.0]
    elif case == "scalar_type":
        values["privacy"]["epsilon_total"] = "hello"
    elif case == "category_domain_type":
        values["schema"]["public_categories"]["province"] = "hebei"
    elif case == "missing_required_field":
        del values["schema"]["sensitive_target"]
    elif case == "nested_structure":
        values["privacy"] = []
    else:
        raise AssertionError("unknown test case")


@pytest.mark.parametrize(
    "case",
    [
        "short_bounds",
        "bounds_type",
        "constraint_row_shape",
        "scalar_type",
        "category_domain_type",
        "missing_required_field",
        "nested_structure",
    ],
)
def test_malformed_configuration_returns_cli_error_without_traceback(
    tmp_path, capsys, case
):
    calibration_path, release_path = _write_inputs(tmp_path)
    values = _base_config()
    _apply_case(values, case)
    config_path = tmp_path / (case + ".yaml")
    config_path.write_text(
        yaml.safe_dump(values, sort_keys=False), encoding="utf-8"
    )
    result = main(
        [
            "validate",
            "--calibration",
            str(calibration_path),
            "--release",
            str(release_path),
            "--config",
            str(config_path),
        ]
    )
    captured = capsys.readouterr()
    assert result == 2
    assert captured.err.startswith("ERROR: ")
    assert "Traceback" not in captured.err


def test_invalid_yaml_syntax_returns_cli_error_without_traceback(tmp_path, capsys):
    calibration_path, release_path = _write_inputs(tmp_path)
    config_path = tmp_path / "broken.yaml"
    config_path.write_text("schema: [unterminated", encoding="utf-8")
    result = main(
        [
            "validate",
            "--calibration",
            str(calibration_path),
            "--release",
            str(release_path),
            "--config",
            str(config_path),
        ]
    )
    captured = capsys.readouterr()
    assert result == 2
    assert captured.err.startswith("ERROR: Could not parse configuration:")
    assert "Traceback" not in captured.err
