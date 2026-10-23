import importlib.util
import json
import os
import shutil
import sys
import zipfile
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "demo"))
from demo_support import build_public_run_archive, execute_demo, load_example, load_public_run  # noqa: E402
from result_presentation import physical_stage_table  # noqa: E402

spec = importlib.util.spec_from_file_location("download_verification", ROOT / "packaging/windows/verify_downloads.py")
checker = importlib.util.module_from_spec(spec)
spec.loader.exec_module(checker)


@pytest.fixture(scope="module")
def public_run(tmp_path_factory):
    example = load_example("official")
    run = execute_demo(example["config"], example["calibration"], example["release"],
                       output_root=tmp_path_factory.mktemp("public-run"))
    return load_public_run(run.run_directory)


def test_missing_downloads_are_not_manufactured(public_run, tmp_path):
    result = checker.find_downloads(tmp_path, public_run)
    assert all(item["status"] == "NOT_FOUND" for item in result.values())
    assert list(tmp_path.iterdir()) == []


def test_saved_public_csv_is_verified_by_exact_bytes(public_run, tmp_path):
    saved = tmp_path / "release_data.csv"
    shutil.copyfile(public_run["run_directory"] / "release_data.csv", saved)
    assert checker.check_release(saved, public_run)["status"] == "PASS"
    saved.write_bytes(saved.read_bytes() + b"\n")
    with pytest.raises(ValueError, match="does not match"):
        checker.check_release(saved, public_run)


def test_old_csv_is_not_counted_as_a_new_gui_download(public_run, tmp_path):
    saved = tmp_path / "release_data.csv"
    shutil.copyfile(public_run["run_directory"] / "release_data.csv", saved)
    os.utime(saved, (1, 1))
    with pytest.raises(ValueError, match="predates"):
        checker.check_release(saved, public_run)


def test_residual_stages_and_violation_rate_remain_visible(public_run, tmp_path):
    frame = physical_stage_table(public_run["json"]["physical_metrics.json"])
    frame["run_id"] = public_run["run_id"]
    saved = tmp_path / (public_run["run_id"] + "_constraint_stages.csv")
    frame.to_csv(saved, index=False)
    result = checker.check_residuals(saved, public_run)
    assert result["status"] == "PASS"
    assert result["violation_rate"][-1] == 1.0
    frame.loc[frame["State"] == "final_clipped", "Violation rate"] = 0.0
    frame.to_csv(saved, index=False)
    with pytest.raises(ValueError, match="Violation rate"):
        checker.check_residuals(saved, public_run)


def test_residual_file_from_another_run_is_rejected(public_run, tmp_path):
    frame = physical_stage_table(public_run["json"]["physical_metrics.json"]).assign(run_id="wrong-run")
    saved = tmp_path / "stages.csv"
    frame.to_csv(saved, index=False)
    with pytest.raises(ValueError, match="different run"):
        checker.check_residuals(saved, public_run)


def test_whitelisted_public_package_is_verified(public_run, tmp_path):
    saved = tmp_path / (public_run["run_id"] + "_public.zip")
    saved.write_bytes(build_public_run_archive(public_run["run_directory"]))
    result = checker.check_package(saved, public_run)
    assert result["status"] == "PASS"
    assert result["internal_artifacts_present"] is False
    with zipfile.ZipFile(saved, "a") as archive:
        archive.writestr(public_run["run_id"] + "/raw_data.csv", "secret\n1\n")
    with pytest.raises(ValueError, match="non-public"):
        checker.check_package(saved, public_run)


def test_zip_traversal_is_rejected_without_extraction(public_run, tmp_path):
    saved = tmp_path / "unsafe.zip"
    with zipfile.ZipFile(saved, "w") as archive:
        archive.writestr("../outside.txt", "not an approved artifact")
    with pytest.raises(ValueError, match="member path"):
        checker.check_package(saved, public_run)
    assert not (tmp_path.parent / "outside.txt").exists()
