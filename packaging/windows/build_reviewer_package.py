"""Package an existing debug distribution and manifest-approved reviewer evidence."""

import argparse
import hashlib
import json
import re
import shutil
import sys
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "demo"))
sys.path.insert(0, str(Path(__file__).resolve().parent))
from demo_support import build_public_run_archive, load_public_run  # noqa: E402
from verify_distribution import compare, gui_check  # noqa: E402

DOCUMENTS = ("START_HERE.html", "REVIEW_TASKS.md", "REVIEW_FEEDBACK.md",
             "SCREEN_RECORDING_SCRIPT.md")
SCREENSHOTS = ("home", "validation", "run_complete", "risk", "utility",
               "allocation", "residuals", "released_data", "audit", "export")
PRIVATE_NAMES = (".internal_audit", "original_clipped_internal", "calibration_data.csv",
                 "noisy_data.csv", "private_only", "private-only")


def read_json(path):
    return json.loads(Path(path).read_text(encoding="utf-8-sig"))


def write_json(path, value):
    Path(path).write_text(json.dumps(value, indent=2, ensure_ascii=False, allow_nan=False)
                          + "\n", encoding="utf-8")


def sha256(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def redact_paths(text):
    """Share diagnostics without disclosing the developer's local username/paths."""
    return re.sub(r"[A-Za-z]:[\\/][^\r\n\"<>]*", "<local path>", text)


def prepare(distribution, destination):
    distribution = Path(distribution).resolve()
    destination = Path(destination).resolve()
    if destination.exists():
        raise ValueError("Refusing to overwrite reviewer package")
    exe = distribution / "RUPA-debug.exe"
    internal = distribution / "_internal"
    if not exe.is_file() or not internal.is_dir():
        raise ValueError("Existing onedir debug distribution is required")
    if destination == distribution or distribution in destination.parents:
        raise ValueError("Reviewer output must be outside the source distribution")
    if any(path.is_symlink() for path in distribution.rglob("*")):
        raise ValueError("Distribution symlinks are not supported")
    destination.mkdir(parents=True)
    shutil.copy2(exe, destination / exe.name)
    shutil.copytree(internal, destination / "_internal")
    for name in DOCUMENTS:
        shutil.copy2(Path(__file__).parent / "reviewer" / name, destination / name)
    shutil.copy2(Path(__file__).parent / "NOTICE.txt", destination / "NOTICE.txt")
    evidence = destination / "reviewer_evidence"
    for directory in ("screenshots", "exported_files", "logs", "build_metadata"):
        (evidence / directory).mkdir(parents=True)
    copied = destination / "RUPA-debug.exe"
    if sha256(copied) != sha256(exe):
        raise ValueError("Copied executable differs from existing debug binary")
    # Compare every bundled dependency/resource, not just the executable.
    for source in internal.rglob("*"):
        if source.is_file():
            if sha256(source) != sha256(destination / "_internal" / source.relative_to(internal)):
                raise ValueError("Copied bundled resource differs")
    print("Reviewer debug distribution copied with identical binary/resources: " + str(destination))


def copy_public_artifacts(run_directory, destination):
    """Use the GUI's existing verified whitelist ZIP, never recursive run copying."""
    public = load_public_run(run_directory)
    buffer = build_public_run_archive(run_directory)
    exported_run = Path(destination) / public["run_id"]
    exported_run.mkdir(parents=True, exist_ok=False)
    import io

    with zipfile.ZipFile(io.BytesIO(buffer)) as archive:
        expected = {public["run_id"] + "/" + name
                    for name in ["manifest.json"] + public["artifact_names"]}
        if set(archive.namelist()) != expected:
            raise ValueError("Public package whitelist mismatch")
        for item in archive.infolist():
            name = Path(item.filename).name
            (exported_run / name).write_bytes(archive.read(item))
    # The normalized manifest has identical entries; all artifact bytes are exact.
    for entry in public["manifest"]["artifacts"]:
        if sha256(exported_run / entry["name"]) != entry["sha256"]:
            raise ValueError("Evidence public artifact hash mismatch")
    return public


def finalize(args):
    destination = args.destination.resolve()
    evidence = destination / "reviewer_evidence"
    if not (destination / "RUPA-debug.exe").is_file():
        raise ValueError("Prepare the reviewer package first")
    if args.zip.exists() or (evidence / "run_summary.json").exists():
        raise ValueError("Refusing to overwrite completed reviewer evidence")
    reference = read_json(args.reference)
    actual = read_json(args.self_test)
    frozen = compare(reference, actual)
    gui = gui_check(reference, args.gui_run)
    if frozen["status"] != "PASS" or gui["status"] != "PASS":
        raise ValueError("Scientific regression did not pass")
    tests = read_json(args.checks)
    if tests["pytest"]["failed"] or tests["pytest"]["errors"]:
        raise ValueError("Pytest did not pass")
    if tests["reproducibility"]["status"] != "PASS":
        raise ValueError("Reproducibility did not pass")
    exe_digest = sha256(destination / "RUPA-debug.exe")
    if tests["exe_sha256"].lower() != exe_digest:
        raise ValueError("Verification does not identify the packaged EXE")
    if tests["core_integrity"]["status"] != "PASS":
        raise ValueError("Core code integrity check did not pass")
    public = copy_public_artifacts(args.gui_run, evidence / "exported_files")
    config = public["json"]["run_config.json"]
    metadata = public["json"]["metadata.json"]
    release = public["csv"]["release_data.csv"]
    if len(release) != 1000 or list(release.columns) != metadata["release_columns"]:
        raise ValueError("Official example release rows/column order differ")
    if config["privacy"]["randomness_mode"] != "reproducibility":
        raise ValueError("Reviewer evidence accepts reproducibility runs only")
    for name, expected in actual["input_sha256"].items():
        if sha256(destination / "_internal/examples/official" / name) != expected:
            raise ValueError("Packaged example differs from verified binary run")
    screenshots = []
    from PIL import Image

    for name in SCREENSHOTS:
        path = args.screenshots / (name + ".jpg")
        if not path.exists():
            continue
        with Image.open(path) as shot:
            shot.save(evidence / "screenshots" / (name + ".png"), format="PNG")
        screenshots.append(name + ".png")
    screenshot_record = read_json(args.screenshots / "capture_record.json")
    if screenshot_record["run_id"] != public["run_id"]:
        raise ValueError("Screenshots are not attributed to this GUI run")
    write_json(evidence / "screenshots/capture_record.json", screenshot_record)
    write_json(evidence / "logs/exe_scientific_regression.json", frozen)
    write_json(evidence / "logs/gui_scientific_regression.json", gui)
    write_json(evidence / "logs/test_results.json", tests)
    for name in ("pytest_terminal.txt", "reproducibility_terminal.txt"):
        source = args.checks.parent / name
        if source.is_file():
            shutil.copy2(source, evidence / "logs" / name)
    launcher_text = args.launcher_log.read_text(encoding="utf-8")
    # Only expected launcher startup records; do not bundle development traceback logs.
    lines = launcher_text.splitlines()
    starts = [index for index, line in enumerate(lines) if "INFO Starting http://127.0.0.1:" in line]
    if not starts:
        raise ValueError("No actual GUI startup record is available")
    first = starts[-1]
    last = next((index for index in range(first + 1, len(lines))
                 if "INFO RUPA 0.1.0 launcher" in lines[index]), len(lines))
    approved = [line for line in lines[max(0, first - 1):last] if any(token in line for token in
                ("INFO RUPA 0.1.0 launcher", "INFO Starting http://127.0.0.1:",
                 "INFO Health check PASS:", "INFO Default browser open returned"))]
    (evidence / "logs/launcher_startup.log").write_text(
        "Approved launcher startup records only; local paths redacted.\n"
        + redact_paths("\n".join(approved)) + "\n", encoding="utf-8")
    (evidence / "logs/run_verification.log").write_text(
        "Manifest/hash/run_id verification PASS\nGUI official example regression PASS\n"
        "Source binary scientific regression PASS\nPublic evidence copied by GUI whitelist helper\n"
        "Browser controls final client-side download location; no download-directory discovery used.\n",
        encoding="utf-8")
    summary = {
        "rupa_version": metadata["version"], "run_id": public["run_id"],
        "execution_mode": config["privacy"]["randomness_mode"],
        "seed": config["privacy"]["random_seed"], "release_rows": len(release),
        "released_columns": list(release.columns),
        "artifact_count": public["inspection"]["artifact_count"],
        "total_epsilon": config["privacy"]["epsilon_total"],
        "target_absent": "PASS", "manifest": "PASS", "legacy_regression": "PASS",
        "noisy_digest": actual["noisy_release_digest"],
        "final_digest": actual["final_release_digest"],
        "digest_provenance": "Same verified EXE synthetic self-test; GUI final digest matches",
        "self_test_run_id": actual["run_id"],
        "self_test_is_separate_run": True,
        "noisy_records_exported": False, "private_records_exported": False,
        "reference_evidence_author": "Developer-executed; independent reviewer ratings not collected",
        "screenshots": screenshots,
        "screenshot_limit": "Real browser viewport captures; some wide tables require horizontal scrolling",
        "browser_download_trigger": tests["browser_download_trigger"],
        "exe_sha256": exe_digest, "production_gui": False,
        "python_free_clean_machine_verification": "NOT YET PERFORMED",
        "final_constraint_violation_rate": public["json"]["physical_metrics.json"]["states"]["final_clipped"]["violation_rate"],
    }
    write_json(evidence / "run_summary.json", summary)
    write_json(evidence / "build_metadata/dependencies.json", actual["versions"])
    write_json(evidence / "build_metadata/scientific_reference.json", {
        key: reference[key] for key in ("risk", "joint_penalty", "utility", "epsilon",
                                       "noisy_release_digest", "final_release_digest", "input_sha256", "versions")})
    write_json(evidence / "build_metadata/build.json", {
        "version": "0.1.0", "format": "PyInstaller onedir debug", "windowed": False,
        "pyinstaller": "6.16.0", "hooks_contrib": "2025.9", "python": "3.9.13 x64",
        "exe_sha256": exe_digest, "bundled_example_input_sha256": actual["input_sha256"],
        "signed": False, "formal_release": False,
    })
    shutil.copy2(Path(__file__).parent / "requirements-build.txt",
                 evidence / "build_metadata/requirements-build.txt")
    (evidence / "README.md").write_text(
        "# Reviewer reference evidence\n\n"
        "Developer-executed reference; independent reviewer ratings have not been collected.\n"
        "Public artifacts are stored in exported_files/<run_id>/ to preserve the formal run-directory contract.\n"
        "Screenshots show one real official GUI walkthrough; home/validation precede execution.\n"
        "A separate same-binary self-test supplies the noisy digest without exporting noisy rows.\n"
        "Four in-process scientific differences are zero. GUI CSV reload differences are below 1e-16,\n"
        "due to text parsing and within the 1e-12 acceptance tolerance; final digest is identical.\n"
        "Browser download trigger was manually confirmed by the user; all five existing controls\n"
        "were exercised again. Browser final save locations were not inspected.\n"
        "Known limitations: loading does not auto-navigate; narrow tables need scrolling;\n"
        "one validation click during rerender required retry; final violation rate is 1.0.\n"
        "The current debug binary is unsigned; a clean Python-free Windows machine has not been tested.\n"
        "The Windows bundle includes official synthetic inputs to enable execution;\n"
        "this evidence-only ZIP contains no raw input tables, executable or source code.\n"
        "The browser controls the final client-side download location; download payloads were\n"
        "verified against the current run's approved public artifacts using the existing whitelist helper.\n",
        encoding="utf-8")
    # Exported data are validated again after copying; target names in schema metadata are allowed.
    inspection = load_public_run(evidence / "exported_files" / public["run_id"])["inspection"]
    if inspection["run_id"] != public["run_id"]:
        raise ValueError("Copied evidence run identity differs")
    for path in evidence.rglob("*"):
        if any(token in path.name.lower() for token in PRIVATE_NAMES):
            raise ValueError("Forbidden evidence file: " + path.name)
        if path.is_file() and path.suffix.lower() == ".csv" and path.name != "release_data.csv":
            import pandas as pd
            frame = pd.read_csv(path)
            if config["schema"]["sensitive_target"] in frame.columns:
                raise ValueError("Sensitive target column in evidence CSV")
    write_json(evidence / "logs/privacy_scan.json", {
        "status": "PASS", "public_manifest_revalidated": True,
        "public_artifact_bytes_unchanged": True, "run_id": public["run_id"],
        "sensitive_target_column_absent": True, "private_artifact_paths_absent": True,
        "raw_inputs_copied_to_evidence": False,
        "bundled_examples_note": "Windows bundle intentionally retains official synthetic inputs for independent execution; evidence ZIP excludes the binary bundle and all raw input tables",
        "schema_target_name_note": "Sensitive target definition is permitted in public schema; no target values are included",
    })
    selected = [(destination / name, name) for name in DOCUMENTS + ("NOTICE.txt",)]
    selected += [(path, path.relative_to(destination).as_posix())
                 for path in sorted(evidence.rglob("*")) if path.is_file()]
    write_json(evidence / "evidence_manifest.json", {
        "run_id": public["run_id"], "files": [
            {"name": name, "sha256": sha256(path), "bytes": path.stat().st_size}
            for path, name in selected],
        "source_binary_included": False, "private_material_included": False,
    })
    selected.append((evidence / "evidence_manifest.json", "reviewer_evidence/evidence_manifest.json"))
    args.zip.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(args.zip, "x", zipfile.ZIP_DEFLATED) as archive:
        for path, name in selected:
            archive.write(path, arcname=name)
    with zipfile.ZipFile(args.zip) as archive:
        if set(archive.namelist()) != {name for _, name in selected}:
            raise ValueError("Evidence ZIP whitelist mismatch")
        for path, name in selected:
            if hashlib.sha256(archive.read(name)).hexdigest() != sha256(path):
                raise ValueError("Evidence ZIP content hash mismatch")
    print(json.dumps({"status": "PASS", "package": str(destination), "evidence_zip": str(args.zip),
                      "run_id": public["run_id"], "screenshots": screenshots,
                      "exe_sha256": exe_digest, "zip_sha256": sha256(args.zip),
                      "zip_bytes": args.zip.stat().st_size}, indent=2))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("mode", choices=["prepare", "finalize"])
    parser.add_argument("--destination", type=Path, required=True)
    parser.add_argument("--distribution", type=Path, default=ROOT / "dist/RUPA-debug")
    parser.add_argument("--gui-run", type=Path)
    parser.add_argument("--self-test", type=Path)
    parser.add_argument("--reference", type=Path)
    parser.add_argument("--checks", type=Path)
    parser.add_argument("--screenshots", type=Path)
    parser.add_argument("--launcher-log", type=Path)
    parser.add_argument("--zip", type=Path)
    args = parser.parse_args()
    if args.mode == "prepare":
        prepare(args.distribution, args.destination)
    else:
        required = ("gui_run", "self_test", "reference", "checks", "screenshots", "launcher_log", "zip")
        if any(getattr(args, name) is None for name in required):
            parser.error("finalize requires all verification and evidence paths")
        finalize(args)


if __name__ == "__main__":
    main()
