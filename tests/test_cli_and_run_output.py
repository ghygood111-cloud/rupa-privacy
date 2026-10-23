import json
import pkgutil
import subprocess
import sys

import pandas as pd
import pytest

import rupa_privacy
from rupa_privacy.cli import main
from rupa_privacy.io import validate_public_run


def test_global_version_flag(capsys):
    with pytest.raises(SystemExit) as exc:
        main(["--version"])
    assert exc.value.code == 0
    assert capsys.readouterr().out.strip() == rupa_privacy.__version__


def test_cli_end_to_end_and_public_run_safety(tmp_path):
    inputs = tmp_path / "inputs"
    runs = tmp_path / "runs"
    assert main(["generate-example", "--output", str(inputs), "--release-rows", "80", "--calibration-rows", "100"]) == 0
    common = [
        "--calibration", str(inputs / "calibration.csv"),
        "--release", str(inputs / "release.csv"),
        "--config", str(inputs / "config.yaml"),
    ]
    assert main(["validate"] + common) == 0
    assert main(["run"] + common + ["--output", str(runs), "--run-id", "pytest_seed123"]) == 0
    run_directory = runs / "pytest_seed123"
    summary = validate_public_run(run_directory, sensitive_target="production")
    assert summary == {
        "run_id": "pytest_seed123",
        "artifact_count": 13,
        "release_rows": 80,
        "randomness_mode": "reproducibility",
    }

    release = pd.read_csv(run_directory / "release_data.csv")
    raw = pd.read_csv(inputs / "release.csv")
    assert "production" not in release
    assert not release.equals(raw)
    raw_rows = {tuple(row) for row in raw.itertuples(index=False, name=None)}
    protected_rows = {tuple(row) for row in release.itertuples(index=False, name=None)}
    assert raw_rows.isdisjoint(protected_rows)
    assert not any("calibration" in path.name or "raw" in path.name for path in run_directory.iterdir())
    with (run_directory / "utility_metrics.json").open(encoding="utf-8") as handle:
        assert json.load(handle)["status"] == "withheld_from_public_run"


def test_all_manifested_outputs_share_one_run_id(tmp_path):
    assert main(["reproduce-example", "--output", str(tmp_path), "--run-id", "one_run"]) == 0
    run_directory = tmp_path / "one_run"
    with (run_directory / "manifest.json").open(encoding="utf-8") as handle:
        manifest = json.load(handle)
    assert manifest["run_id"] == "one_run"
    for entry in manifest["artifacts"]:
        path = run_directory / entry["name"]
        if path.suffix == ".json":
            with path.open(encoding="utf-8") as handle:
                assert json.load(handle)["run_id"] == "one_run"
        elif path.suffix == ".csv" and path.name != "release_data.csv":
            assert set(pd.read_csv(path)["run_id"]) == {"one_run"}


def test_importing_every_distributed_module_has_no_execution_side_effect(tmp_path):
    module_names = [
        item.name
        for item in pkgutil.walk_packages(rupa_privacy.__path__, rupa_privacy.__name__ + ".")
    ]
    code = "import importlib\n" + "\n".join(
        "importlib.import_module({0!r})".format(name) for name in module_names
    )
    completed = subprocess.run(
        [sys.executable, "-c", code], cwd=tmp_path, capture_output=True, text=True, check=False
    )
    assert completed.returncode == 0
    assert completed.stdout == ""
    assert completed.stderr == ""
    assert list(tmp_path.iterdir()) == []


def test_core_package_contains_no_legacy_archive_dependency():
    package_root = next(iter(rupa_privacy.__path__))
    for path in __import__("pathlib").Path(package_root).rglob("*.py"):
        assert ".np" + "z" not in path.read_text(encoding="utf-8")


def test_run_id_cannot_escape_output_directory(tmp_path):
    inputs = tmp_path / "inputs"
    runs = tmp_path / "runs"
    sentinel = tmp_path / "sentinel.txt"
    sentinel.write_text("keep", encoding="utf-8")
    assert main(["generate-example", "--output", str(inputs)]) == 0
    result = main(
        [
            "run",
            "--calibration",
            str(inputs / "calibration.csv"),
            "--release",
            str(inputs / "release.csv"),
            "--config",
            str(inputs / "config.yaml"),
            "--output",
            str(runs),
            "--run-id",
            "..",
        ]
    )
    assert result == 2
    assert sentinel.read_text(encoding="utf-8") == "keep"
    assert not runs.exists()


def test_rejected_duplicate_run_id_preserves_existing_public_run(tmp_path):
    inputs = tmp_path / "inputs"
    runs = tmp_path / "runs"
    assert main(["generate-example", "--output", str(inputs)]) == 0
    common = [
        "--calibration",
        str(inputs / "calibration.csv"),
        "--release",
        str(inputs / "release.csv"),
        "--config",
        str(inputs / "config.yaml"),
        "--output",
        str(runs),
        "--run-id",
        "preserve_me",
    ]
    assert main(["run"] + common) == 0
    run_directory = runs / "preserve_me"
    release_before = (run_directory / "release_data.csv").read_bytes()

    assert main(["run"] + common) == 2

    assert (run_directory / "manifest.json").is_file()
    assert (run_directory / "release_data.csv").read_bytes() == release_before
    assert validate_public_run(run_directory, sensitive_target="production")[
        "run_id"
    ] == "preserve_me"
