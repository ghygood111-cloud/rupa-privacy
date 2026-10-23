"""Verify files actually saved by the GUI against one approved public run."""

import argparse
import hashlib
import io
import json
import math
import sys
import zipfile
from datetime import datetime
from pathlib import Path, PurePosixPath

import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "demo"))
from demo_support import load_public_run  # noqa: E402
from result_presentation import physical_stage_table  # noqa: E402


def file_hash(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def require_current_download(path, public):
    created = public["json"]["metadata.json"].get("created_utc")
    if created and Path(path).stat().st_mtime < datetime.fromisoformat(created).timestamp() - 5:
        raise ValueError("Saved file predates this run; download the current result")


def check_release(path, public):
    require_current_download(path, public)
    expected = public["csv"]["release_data.csv"]
    actual = pd.read_csv(path)
    target = public["json"]["run_config.json"]["schema"]["sensitive_target"]
    if actual.columns.tolist() != expected.columns.tolist() or len(actual) != len(expected):
        raise ValueError("Downloaded release has the wrong schema or row count")
    if target in actual.columns:
        raise ValueError("Sensitive target is present in the downloaded release")
    original = public["run_directory"] / "release_data.csv"
    if file_hash(path) != file_hash(original):
        raise ValueError("Downloaded CSV does not match the current GUI public artifact")
    return {"status": "PASS", "path": str(Path(path).resolve()), "rows": len(actual),
            "columns": actual.columns.tolist(), "sha256": file_hash(path),
            "sensitive_target_absent": True, "matches_public_artifact": True}


def check_residuals(path, public):
    require_current_download(path, public)
    actual = pd.read_csv(path)
    expected = physical_stage_table(public["json"]["physical_metrics.json"])
    allowed = set(expected.columns) | {"run_id"}
    if set(actual.columns) != allowed or len(actual) != len(expected):
        raise ValueError("Residual download has unexpected columns or incomplete stages")
    if set(actual["run_id"].astype(str)) != {public["run_id"]}:
        raise ValueError("Residual download belongs to a different run")
    for column in ("State", "Stage"):
        if actual[column].tolist() != expected[column].tolist():
            raise ValueError("Residual processing stages are incomplete or reordered")
    for column in ("Order", "RMS", "NRMS", "Max absolute residual", "Violation rate"):
        for downloaded, saved in zip(actual[column], expected[column]):
            if not math.isfinite(float(downloaded)) or not math.isclose(
                float(downloaded), float(saved), rel_tol=1e-12, abs_tol=1e-15
            ):
                raise ValueError("Residual value mismatch: " + column)
    return {"status": "PASS", "path": str(Path(path).resolve()), "run_id": public["run_id"],
            "stages": actual["State"].tolist(), "sha256": file_hash(path),
            "nrms": actual["NRMS"].tolist(), "violation_rate": actual["Violation rate"].tolist(),
            "row_level_records_present": False}


def check_package(path, public):
    require_current_download(path, public)
    expected_names = {"manifest.json"} | set(public["artifact_names"])
    prefix = public["run_id"]
    with zipfile.ZipFile(path) as archive:
        infos = archive.infolist()
        names = [item.filename for item in infos]
        if len(names) != len(set(names)):
            raise ValueError("Duplicate ZIP members")
        parsed = [PurePosixPath(name) for name in names]
        if any(item.is_absolute() or ".." in item.parts or len(item.parts) != 2
               or item.parts[0] != prefix for item in parsed):
            raise ValueError("Unexpected ZIP member path")
        if {item.name for item in parsed} != expected_names:
            raise ValueError("ZIP contains missing or non-public artifacts")
        if sum(item.file_size for item in infos) > 2 * sum(
            (public["run_directory"] / name).stat().st_size for name in expected_names
        ):
            raise ValueError("Unexpected ZIP decompressed size")
        for item in infos:
            filename = PurePosixPath(item.filename).name
            data = archive.read(item)
            if filename == "manifest.json":
                if json.loads(data) != public["manifest"]:
                    raise ValueError("ZIP manifest differs from the verified public manifest")
            elif hashlib.sha256(data).hexdigest() != file_hash(public["run_directory"] / filename):
                raise ValueError("ZIP public artifact mismatch: " + filename)
        release_member = archive.read(prefix + "/release_data.csv")
        release = pd.read_csv(io.BytesIO(release_member))
        target = public["json"]["run_config.json"]["schema"]["sensitive_target"]
        if target in release:
            raise ValueError("ZIP contains a sensitive target column")
    return {"status": "PASS", "path": str(Path(path).resolve()), "sha256": file_hash(path),
            "members": names, "internal_artifacts_present": False,
            "all_public_bytes_verified": True}


def find_downloads(directory, public):
    """Search saved files only; never manufacture a downloaded file."""
    directory = Path(directory)
    files = sorted((item for item in directory.iterdir() if item.is_file()),
                   key=lambda item: item.stat().st_mtime, reverse=True)
    matches = {}
    for kind, checker, pattern in (
        ("release_data.csv", check_release, lambda name: name.startswith("release_data") and name.endswith(".csv")),
        ("residual_data", check_residuals, lambda name: name.startswith(public["run_id"]) and "constraint_stages" in name and name.endswith(".csv")),
        ("public_package", check_package, lambda name: name.startswith(public["run_id"]) and "public" in name and name.endswith(".zip")),
    ):
        rejected = []
        for item in files:
            if not pattern(item.name):
                continue
            try:
                matches[kind] = checker(item, public)
                break
            except (ValueError, OSError, KeyError, zipfile.BadZipFile, pd.errors.ParserError) as exc:
                rejected.append({"path": str(item), "reason": str(exc)})
        else:
            matches[kind] = {"status": "NOT_FOUND", "rejected_candidates": rejected}
    return matches


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run", type=Path, required=True)
    parser.add_argument("--downloads", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    public = load_public_run(args.run)
    checks = find_downloads(args.downloads, public)
    report = {"run_id": public["run_id"], "downloads": checks,
              "status": "PASS" if all(item["status"] == "PASS" for item in checks.values()) else "PARTIAL"}
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2, allow_nan=False), encoding="utf-8")
    print(json.dumps(report, indent=2))
    return 0 if report["status"] == "PASS" else 2


if __name__ == "__main__":
    raise SystemExit(main())
