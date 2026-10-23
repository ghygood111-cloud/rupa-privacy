"""Acceptance checks for the synthetic hazardous-waste GUI example."""

import sys
from pathlib import Path

import numpy as np
import pandas as pd


DEMO_ROOT = Path(__file__).resolve().parents[1] / "demo"
if str(DEMO_ROOT) not in sys.path:
    sys.path.insert(0, str(DEMO_ROOT))

from demo_support import execute_demo, field_rows, load_example, validate_demo  # noqa: E402


SCREENSHOT_METADATA = {
    "qyid", "zzjgdm", "dwmc", "dwszqxz", "dwdz", "hylbdm",
    "lxr", "lxrsj", "gljhid", "year",
}


def test_hazardous_waste_example_schema_and_synthetic_balances():
    example = load_example("hazardous_waste")
    calibration, release, config = (
        example["calibration"], example["release"], example["config"]
    )
    schema = config["schema"]
    assert len(calibration) == 240
    assert len(release) == 320
    assert len(schema["numeric_columns"]) == 14
    assert len(schema["categorical_columns"]) == 4
    assert set(calibration["public_enterprise_period_id"]).isdisjoint(
        release["public_enterprise_period_id"]
    )
    assert SCREENSHOT_METADATA <= set(release.columns)
    assert not SCREENSHOT_METADATA.intersection(schema["released_columns"])
    assert schema["sensitive_target"] in calibration.columns
    assert schema["sensitive_target"] not in release.columns
    assert release["qyid"].str.startswith("SYN-").all()
    assert set(release["lxrsj"]) == {"not_collected"}
    assert np.allclose(
        release["generated_total_t"],
        release[[
            "waste_acid_t", "distillation_residue_t",
            "incineration_fly_ash_t", "surface_treatment_waste_t",
        ]].sum(axis=1),
    )
    assert np.allclose(
        release["transferred_total_t"],
        release["cross_region_transferred_t"] + release["within_region_transferred_t"],
    )
    assert np.allclose(
        release["generated_total_t"],
        release["transferred_total_t"] + release["on_site_treated_t"]
        + release["retained_for_next_period_t"],
    )
    assert (
        release["manifest_total_count"]
        == release["cross_region_manifest_count"] + release["within_region_manifest_count"]
    ).all()
    rows = field_rows(config, release.columns)
    assert int(rows["Release"].sum()) == 18
    assert not rows.loc[rows["Field"].isin(SCREENSHOT_METADATA), "Release"].any()
    assert validate_demo(config, calibration, release)["constraint_validation"]["decision"] == "PASS"


def test_hazardous_waste_public_release_excludes_source_metadata(tmp_path):
    example = load_example("hazardous_waste")
    run = execute_demo(
        example["config"], example["calibration"], example["release"], tmp_path
    )
    released = pd.read_csv(run.run_directory / "release_data.csv")
    expected = {"public_enterprise_period_id"} | set(
        example["config"]["schema"]["released_columns"]
    )
    assert len(released) == 320
    assert set(released.columns) == expected
    assert not SCREENSHOT_METADATA.intersection(released.columns)
    assert "confidential_cost_index" not in released.columns
    assert run.inspection["release_rows"] == 320
    assert np.isclose(sum(run.result.allocation_result.epsilon.values()), 5.0)
