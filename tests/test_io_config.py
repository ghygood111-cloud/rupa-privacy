import json

import pandas as pd
import pytest

from rupa_privacy import RUPAPipeline
from rupa_privacy.data import generate_example_pair
from rupa_privacy.exceptions import DataValidationError
from rupa_privacy.io import load_pipeline_config, load_table, save_config


def test_example_yaml_runs_end_to_end():
    schema, privacy, constraints, prior, adjacency, accounting = load_pipeline_config(
        "configs/example.yaml"
    )
    calibration, release = generate_example_pair(n_release=60, n_calibration=80)
    result = RUPAPipeline(
        schema, privacy, constraints, prior, adjacency, accounting
    ).fit_transform(
        calibration, release
    )
    assert result.release_data.shape == (60, 11)
    assert "production" not in result.release_data


def test_csv_and_xlsx_loading(tmp_path):
    frame = pd.DataFrame({"a": [1, 2], "b": ["x", "y"]})
    csv_path = tmp_path / "input.csv"
    xlsx_path = tmp_path / "input.xlsx"
    frame.to_csv(csv_path, index=False)
    frame.to_excel(xlsx_path, index=False)
    pd.testing.assert_frame_equal(load_table(csv_path), frame)
    pd.testing.assert_frame_equal(load_table(xlsx_path), frame)


def test_json_configuration_round_trip(tmp_path):
    schema, privacy, constraints, prior, adjacency, accounting = load_pipeline_config(
        "configs/example.yaml"
    )
    path = tmp_path / "config.json"
    save_config(path, schema, privacy, constraints, prior, adjacency, accounting)
    (
        loaded_schema,
        loaded_privacy,
        loaded_constraints,
        loaded_prior,
        loaded_adjacency,
        loaded_accounting,
    ) = load_pipeline_config(path)
    assert loaded_schema.to_dict() == schema.to_dict()
    assert loaded_privacy.to_dict() == privacy.to_dict()
    assert [item.to_dict() for item in loaded_constraints] == [item.to_dict() for item in constraints]
    assert loaded_prior == prior
    assert loaded_adjacency.to_dict() == adjacency.to_dict()
    assert loaded_accounting.to_dict() == accounting.to_dict()


def test_unsupported_data_extension_is_rejected(tmp_path):
    path = tmp_path / "input.txt"
    path.write_text("a\n1\n", encoding="utf-8")
    with pytest.raises(DataValidationError, match="Unsupported data format"):
        load_table(path)
