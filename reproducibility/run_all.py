"""Run the principal RUPA SoftwareX reproduction checks in one command."""

import csv
import json
import subprocess
import sys
import tempfile
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
EXPECTED = ROOT / "reproducibility" / "expected"


def _run(command):
    completed = subprocess.run(
        [str(part) for part in command],
        cwd=str(ROOT),
        text=True,
        capture_output=True,
    )
    if completed.returncode != 0:
        detail = (completed.stdout + "\n" + completed.stderr).strip()
        raise RuntimeError("Command failed: {0}\n{1}".format(" ".join(command), detail))
    return completed.stdout


def _cli(*arguments):
    return _run([sys.executable, "-m", "rupa_privacy", *arguments])


def _exercise_example(name, calibration, release, config, target, output_root):
    _cli(
        "validate",
        "--calibration",
        calibration,
        "--release",
        release,
        "--config",
        config,
    )
    _cli(
        "run",
        "--calibration",
        calibration,
        "--release",
        release,
        "--config",
        config,
        "--output",
        output_root,
        "--run-id",
        name,
    )
    _cli(
        "inspect-run",
        str(Path(output_root) / name),
        "--sensitive-target",
        target,
    )


def _verify_regression(comparison_path):
    expected_summary = json.loads(
        (EXPECTED / "regression_summary.json").read_text(encoding="utf-8")
    )
    expected_hashes = json.loads(
        (EXPECTED / "expected_hashes.json").read_text(encoding="utf-8")
    )
    with comparison_path.open(newline="", encoding="utf-8") as handle:
        rows = {row["quantity"]: row for row in csv.DictReader(handle)}

    for quantity, expectation in expected_summary.items():
        actual = float(rows[quantity]["value"])
        expected = float(expectation["expected_max_absolute_difference"])
        tolerance = float(expectation["tolerance"])
        if abs(actual - expected) > tolerance or rows[quantity]["status"] != "PASS":
            raise RuntimeError("Locked regression mismatch for " + quantity)

    for quantity, expected in expected_hashes.items():
        if rows[quantity]["value"] != expected or rows[quantity]["status"] != "PASS":
            raise RuntimeError("Release digest mismatch for " + quantity)


def main():
    checks = []
    try:
        release_metadata = json.loads(
            (EXPECTED / "release_metadata.json").read_text(encoding="utf-8")
        )
        installed_version = _cli("version").strip()
        if installed_version != release_metadata["version"]:
            raise RuntimeError(
                "Installed version {0} does not match expected version {1}".format(
                    installed_version, release_metadata["version"]
                )
            )
        checks.append(("Package version", "PASS"))

        with tempfile.TemporaryDirectory(prefix="rupa-softwarex-") as temporary:
            work = Path(temporary)
            official = work / "official_inputs"
            runs = work / "runs"

            _cli("generate-example", "--output", str(official))
            _exercise_example(
                "official",
                str(official / "calibration.csv"),
                str(official / "release.csv"),
                str(official / "config.yaml"),
                "production",
                str(runs),
            )
            checks.append(("Official example", "PASS"))

            water = ROOT / "examples" / "water_treatment"
            _exercise_example(
                "water-treatment",
                str(water / "calibration.csv"),
                str(water / "release.csv"),
                str(water / "config_reproducibility.yaml"),
                "operating_cost_index",
                str(runs),
            )
            checks.append(("Water-treatment", "PASS"))

            reuse = ROOT / "examples" / "third_party_reuse"
            _exercise_example(
                "third-party-reuse",
                str(reuse / "calibration.csv"),
                str(reuse / "release.csv"),
                str(reuse / "config.yaml"),
                "energy_cost_index",
                str(runs),
            )
            checks.append(("Third-party reuse", "PASS"))
            checks.append(("Manifest validation", "PASS"))

            comparison = work / "legacy_comparison.csv"
            _run(
                [
                    sys.executable,
                    str(ROOT / "scripts" / "compare_legacy_package.py"),
                    "--output",
                    str(comparison),
                ]
            )
            _verify_regression(comparison)
            checks.extend(
                [
                    ("Legacy risk regression", "PASS"),
                    ("Legacy joint-penalty regression", "PASS"),
                    ("Legacy utility regression", "PASS"),
                    ("Legacy epsilon regression", "PASS"),
                    ("Release hash verification", "PASS"),
                ]
            )
    except Exception as exc:
        print("RUPA SoftwareX reproduction")
        print("--------------------------------")
        for name, status in checks:
            print("{0}: {1}".format(name, status))
        print("Failure: " + str(exc))
        print("\nOverall: FAIL")
        return 1

    print("RUPA SoftwareX reproduction")
    print("--------------------------------")
    for name, status in checks:
        print("{0}: {1}".format(name, status))
    print("\nOverall: PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
