import io
import json
import sys
import zipfile
from copy import deepcopy
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "demo"))
from demo_support import load_example
from research_support import execute_research, load_research_run, research_archive, PUBLIC_FILES


@pytest.mark.parametrize("domain", ["official", "water", "hazardous_waste"])
@pytest.mark.parametrize("strategy", ["hybrid_uniform", "hybrid_workload"])
def test_two_view_real_workflow_and_export_payload(domain, strategy, tmp_path):
    pytest.importorskip("diffprivlib")
    example = load_example(domain)
    run = execute_research(example["config"], example["calibration"], example["release"], tmp_path, strategy)
    assert len(run["data"]) == len(example["release"])
    target = example["config"]["schema"]["sensitive_target"]
    assert target not in run["data"].columns
    assert run["diagnostics"]["composed_epsilon"] == pytest.approx(example["config"]["privacy"]["epsilon_total"])
    assert run["allocation"].composed_epsilon.sum() == pytest.approx(run["diagnostics"]["composed_epsilon"])
    payload = research_archive(run["folder"])
    with zipfile.ZipFile(io.BytesIO(payload)) as archive:
        assert {Path(name).name for name in archive.namelist()} == PUBLIC_FILES | {"manifest.json"}
        assert not any("internal" in name or "original" in name for name in archive.namelist())
        data = pd.read_csv(archive.open(run["run_id"] + "/release_data.csv"))
        pd.testing.assert_frame_equal(data, run["data"])
        diagnostics = json.loads(archive.read(run["run_id"] + "/diagnostics.json"))
        assert "truth" not in diagnostics and "raw_input_total" not in diagnostics
    if example["config"].get("constraints"):
        assert run["diagnostics"]["maximum_public_equality_residual"] < 1e-6


def test_research_export_ignores_unapproved_adjacent_files_and_rejects_tampering(tmp_path):
    pytest.importorskip("diffprivlib")
    x = load_example("official")
    run = execute_research(x["config"], x["calibration"], x["release"], tmp_path)
    (run["folder"] / "original_private.csv").write_text("DO_NOT_EXPORT", encoding="utf-8")
    assert b"DO_NOT_EXPORT" not in research_archive(run["folder"])
    with (run["folder"] / "release_data.csv").open("a") as stream:
        stream.write("tampered")
    with pytest.raises(ValueError, match="integrity"):
        load_research_run(run["folder"])


@pytest.mark.parametrize("field,value", [("randomness_mode", "production"), ("release_data_mode", "confidential"),
                                         ("calibration_mode", "disjoint_private")])
def test_research_rejects_private_or_production_before_output(field, value, tmp_path):
    x = load_example("official")
    config = deepcopy(x["config"])
    config["privacy"][field] = value
    if field == "randomness_mode":
        config["privacy"]["random_seed"] = None
    with pytest.raises(ValueError, match="reproducibility|Confidential|Private"):
        execute_research(config, x["calibration"], x["release"], tmp_path)
    assert not list(tmp_path.iterdir())
