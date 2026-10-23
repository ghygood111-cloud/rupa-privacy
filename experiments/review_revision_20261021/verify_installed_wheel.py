"""Verify the installed wheel from a clean working directory, not the source path."""
import argparse
import csv
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import time
import zipfile


HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]


def sha(data):
    return hashlib.sha256(data).hexdigest()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--wheel", type=Path, default=HERE / "release/wheel/rupa_privacy-0.1.0-py3-none-any.whl")
    args = parser.parse_args()
    out = args.output.resolve()
    out.mkdir(parents=True, exist_ok=False)
    work = out / "clean_cwd"
    work.mkdir()
    env = dict(os.environ, PYTHONPATH="", PYTHONNOUSERSITE="1")
    evidence = {"python": sys.executable, "commands": [], "local_controlled_test_only": True,
                "independent_human_test": False, "cross_platform_test": False}

    def execute(parts, name):
        start = time.perf_counter()
        result = subprocess.run([str(x) for x in parts], cwd=work, env=env, capture_output=True, text=True, encoding="utf-8")
        (out / (name + ".log")).write_text(result.stdout + result.stderr, encoding="utf-8")
        evidence["commands"].append({"name": name, "argv": [str(x) for x in parts], "exit_code": result.returncode,
                                      "seconds": time.perf_counter() - start})
        if result.returncode:
            raise RuntimeError(name + " failed: " + result.stderr)
        return result.stdout

    location = execute([sys.executable, "-c", "import rupa_privacy; print(rupa_privacy.__file__)"], "import_location").strip()
    assert "site-packages" in location and "src" not in Path(location).parts
    evidence["installed_module"] = location
    wheel = args.wheel.resolve()
    with zipfile.ZipFile(wheel) as archive:
        members = [n for n in archive.namelist() if n.startswith("rupa_privacy/") and n.endswith(".py")]
        assert len(members) == len(list((ROOT / "src/rupa_privacy").rglob("*.py")))
        assert not any(n.endswith(("studio.py", "project.py")) for n in members)
        evidence["wheel_core_hash_match"] = all(sha(archive.read(n)) == sha((ROOT / "src" / n).read_bytes()) for n in members)
        assert evidence["wheel_core_hash_match"]
        evidence["wheel_python_files"] = len(members)
    evidence["wheel_sha256"] = sha(wheel.read_bytes())
    execute([sys.executable, "-m", "pip", "freeze"], "installed_dependencies")
    execute([sys.executable, "-m", "rupa_privacy", "--help"], "cli_help")
    examples = [
        ("official", "config.yaml", "production"),
        ("water_treatment", "config_reproducibility.yaml", "operating_cost_index"),
        ("third_party_reuse", "config.yaml", "sensitive_target"),
        ("hazardous_waste", "config_reproducibility.yaml", "confidential_cost_index"),
        ("ontario_registration", "config_reproducibility.yaml", "registered_waste_class_count"),
    ]
    # Use declared targets rather than assuming a naming convention.
    import yaml
    for name, config_name, _ in examples:
        folder = ROOT / "examples" / name
        config = folder / config_name
        target = yaml.safe_load(config.read_text(encoding="utf-8"))["schema"]["sensitive_target"]
        common = ["--calibration", folder / "calibration.csv", "--release", folder / "release.csv", "--config", config]
        execute([sys.executable, "-m", "rupa_privacy", "validate", *common], name + "_validate")
        execute([sys.executable, "-m", "rupa_privacy", "run", *common, "--output", out / "runs", "--run-id", "wheel_" + name], name + "_run")
        execute([sys.executable, "-m", "rupa_privacy", "inspect-run", out / "runs" / ("wheel_" + name), "--sensitive-target", target], name + "_inspect")
    if any(n.endswith("allocation/balanced.py") for n in members):
        folder = ROOT / "examples/hazardous_waste"
        values = yaml.safe_load((folder / "config_reproducibility.yaml").read_text())
        values["privacy"]["numeric_budget_strategy"] = "balanced_rupa"
        config = out / "balanced_config.yaml"
        config.write_text(yaml.safe_dump(values), encoding="utf-8")
        common = ["--calibration", folder / "calibration.csv", "--release", folder / "release.csv", "--config", config]
        execute([sys.executable, "-m", "rupa_privacy", "validate", *common], "balanced_validate")
        execute([sys.executable, "-m", "rupa_privacy", "run", *common, "--output", out / "runs", "--run-id", "wheel_balanced"], "balanced_run")
        execute([sys.executable, "-m", "rupa_privacy", "inspect-run", out / "runs/wheel_balanced", "--sensitive-target", values["schema"]["sensitive_target"]], "balanced_inspect")
    regression = out / "legacy_comparison.csv"
    execute([sys.executable, ROOT / "scripts/compare_legacy_package.py", "--output", regression], "legacy_regression")
    with regression.open(encoding="utf-8", newline="") as handle:
        evidence["legacy_regression"] = list(csv.DictReader(handle))
    assert all(row["status"] == "PASS" for row in evidence["legacy_regression"])
    evidence["status"] = "PASS"
    (out / "manifest.json").write_text(json.dumps(evidence, indent=2), encoding="utf-8")
    print(json.dumps({"status": "PASS", "installed_module": location, "wheel_core_files": len(members),
                      "examples": len(examples), "legacy": evidence["legacy_regression"]}, indent=2))


if __name__ == "__main__":
    main()
