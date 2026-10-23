"""Self-executed clean-room CLI check, not independent user adoption."""
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys

import pandas as pd

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
EXAMPLE = ROOT / "examples" / "ontario_registration"
PYTHON = HERE / ".venv-clean" / "Scripts" / "python.exe"
CLI = HERE / ".venv-clean" / "Scripts" / "rupa-privacy.exe"


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def main():
    work = HERE / "clean_room"
    work.mkdir(exist_ok=False)
    environment = dict(os.environ)
    environment.pop("PYTHONPATH", None)
    environment["PYTHONUTF8"] = "1"
    commands = []

    def execute(label, arguments):
        result = subprocess.run([str(a) for a in arguments], cwd=work, env=environment,
                                capture_output=True, text=True, encoding="utf-8", errors="replace")
        (work / (label + ".txt")).write_text(
            "COMMAND: " + subprocess.list2cmdline([str(a) for a in arguments]) + "\n"
            + result.stdout + result.stderr, encoding="utf-8")
        commands.append({"label": label, "returncode": result.returncode})
        print(label, "returncode", result.returncode, flush=True)
        if result.returncode:
            raise RuntimeError(label + " failed; inspect the captured command log")
        return result.stdout

    module_probe = execute("module_probe", [PYTHON, "-c",
        "import json,pathlib,rupa_privacy; print(json.dumps({'module':str(pathlib.Path(rupa_privacy.__file__).resolve())}))"])
    installed = Path(json.loads(module_probe)["module"]).parent
    assert ".venv-clean" in installed.parts and "site-packages" in installed.parts
    source_hashes = {p.relative_to(ROOT / "src" / "rupa_privacy").as_posix(): sha(p)
                     for p in (ROOT / "src" / "rupa_privacy").rglob("*.py")}
    installed_hashes = {p.relative_to(installed).as_posix(): sha(p) for p in installed.rglob("*.py")}
    assert source_hashes == installed_hashes
    common = ["--calibration", EXAMPLE / "calibration.csv", "--release", EXAMPLE / "release.csv",
              "--config", EXAMPLE / "config_reproducibility.yaml"]
    execute("validate", [CLI, "validate"] + common)
    run_id = "ontario_clean_uniform_eps2_seed20262000"
    execute("run", [CLI, "run"] + common + ["--output", work / "runs", "--run-id", run_id])
    run = work / "runs" / run_id
    execute("inspect", [CLI, "inspect-run", run, "--sensitive-target", "registered_class_count"])
    execute("analysis", [PYTHON, EXAMPLE / "analysis.py", run, "--output", work / "public_analysis.json"])
    reference = HERE / "results" / "runs" / "ontario_uniform_eps2_seed20262000"
    actual = pd.read_csv(run / "release_data.csv")
    expected = pd.read_csv(reference / "release_data.csv")
    pd.testing.assert_frame_equal(actual, expected)
    assert actual.columns.tolist() == ["public_registration_id", "handles_liquid", "handles_solid"]
    differences = {}
    for file, value in [("risk_scores.csv", "single_nmi"), ("risk_scores.csv", "joint_penalty"),
                        ("utility_weights.csv", "utility_weight"), ("epsilon_allocation.csv", "epsilon")]:
        a = pd.read_csv(run / file).set_index("feature")[value].sort_index()
        b = pd.read_csv(reference / file).set_index("feature")[value].sort_index()
        differences[value] = float((a - b).abs().max())
        assert differences[value] == 0
    assert sha(run / "release_data.csv") == sha(reference / "release_data.csv")
    result = {
        "status": "PASS", "scope": "Self-executed new-venv installed-wheel CLI reproduction; not an independent human user study.",
        "commands": commands, "installed_module": str(installed), "core_files_equal": len(source_hashes),
        "wheel_sha256": sha(HERE / "wheel" / "rupa_privacy-0.1.0-py3-none-any.whl"),
        "rows": len(actual), "columns": actual.columns.tolist(), "differences": differences,
        "release_sha256": sha(run / "release_data.csv"), "reference_release_digest_equal": True,
        "approved_run": str(run), "core_scientific_code_modified": False,
    }
    (work / "verification.json").write_text(json.dumps(result, indent=2), encoding="utf-8")
    print(json.dumps(result, indent=2), flush=True)


if __name__ == "__main__":
    main()
