import importlib.util
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "demo"))
sys.path.insert(0, str(ROOT / "packaging/windows"))
from demo_support import execute_demo, load_example, load_public_run  # noqa: E402

spec = importlib.util.spec_from_file_location(
    "reviewer_packaging", ROOT / "packaging/windows/build_reviewer_package.py"
)
builder = importlib.util.module_from_spec(spec)
spec.loader.exec_module(builder)


def test_reviewer_docs_describe_actual_non_auto_navigation():
    documents = ROOT / "packaging/windows/reviewer"
    html = (documents / "START_HERE.html").read_text(encoding="utf-8")
    assert "Load official synthetic example" in html
    assert "当前不会自动跳转" in html
    assert "RUPA-debug.exe" in html
    assert "violation rate" in html
    tasks = (documents / "REVIEW_TASKS.md").read_text(encoding="utf-8")
    assert "violation_rate is 1.0" in tasks
    assert "not an independent review" in tasks


def test_reviewer_package_refuses_overwrite(tmp_path):
    with pytest.raises(ValueError, match="overwrite"):
        builder.prepare(tmp_path / "missing", tmp_path)


def test_prepare_copies_only_binary_bundle_and_review_docs(tmp_path):
    distribution = tmp_path / "dist"
    distribution.mkdir()
    (distribution / "RUPA-debug.exe").write_bytes(b"test binary")
    (distribution / "_internal").mkdir()
    (distribution / "_internal/resource.txt").write_text("resource", encoding="utf-8")
    (distribution / "unapproved.log").write_text("private", encoding="utf-8")
    destination = tmp_path / "reviewer"
    builder.prepare(distribution, destination)
    assert (destination / "RUPA-debug.exe").read_bytes() == b"test binary"
    assert (destination / "_internal/resource.txt").read_text() == "resource"
    assert not (destination / "unapproved.log").exists()
    assert (destination / "REVIEW_FEEDBACK.md").is_file()


def test_public_evidence_uses_manifest_and_does_not_copy_internal_rows(tmp_path):
    example = load_example("official")
    run = execute_demo(example["config"], example["calibration"], example["release"],
                       output_root=tmp_path / "runs")
    internal = run.run_directory / ".internal_audit"
    internal.mkdir()
    (internal / "original_clipped_internal.csv").write_text("SECRET", encoding="utf-8")
    destination = tmp_path / "evidence"
    destination.mkdir()
    original = builder.copy_public_artifacts(run.run_directory, destination)
    expected = {"manifest.json"} | set(original["artifact_names"])
    exported_run = destination / run.run_id
    assert {path.name for path in exported_run.iterdir()} == expected
    assert not (exported_run / ".internal_audit").exists()
    copied = load_public_run(exported_run)
    assert copied["run_id"] == run.run_id
    assert run.schema.sensitive_target not in copied["csv"]["release_data.csv"].columns


def test_public_evidence_rejects_modified_artifacts(tmp_path):
    example = load_example("official")
    run = execute_demo(example["config"], example["calibration"], example["release"],
                       output_root=tmp_path / "runs")
    path = run.run_directory / "release_data.csv"
    path.write_bytes(path.read_bytes() + b"\n")
    destination = tmp_path / "evidence"
    destination.mkdir()
    with pytest.raises(Exception, match="hash mismatch"):
        builder.copy_public_artifacts(run.run_directory, destination)
    assert list(destination.iterdir()) == []


def test_redacted_launcher_log_removes_local_identity():
    text = "INFO writable root=C:\\Users\\a-private-user\\AppData\\Local\\RUPA\nHealth PASS\n"
    assert "a-private-user" not in builder.redact_paths(text)
    assert "Health PASS" in builder.redact_paths(text)
