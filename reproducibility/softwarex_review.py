"""Exercise shipped examples via the existing CLI and plot verified public artifacts.

This is a review/example runner, not a privacy mechanism or performance benchmark.
It never reads historical experiment outputs or raw-dependent internal audits.
"""

import argparse
import hashlib
import importlib.metadata
import json
import platform
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd

from rupa_privacy import __version__
from rupa_privacy.io import load_pipeline_config, validate_public_run


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "demo"))
from result_presentation import physical_stage_table  # noqa: E402


EXAMPLES = (
    ("official", "examples/official", "config.yaml"),
    ("water-treatment", "examples/water_treatment", "config_reproducibility.yaml"),
    ("reuse-fixture", "examples/third_party_reuse", "config.yaml"),
)


def sha256(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def core_hashes():
    return {
        path.relative_to(ROOT).as_posix(): sha256(path)
        for path in sorted((ROOT / "src" / "rupa_privacy").rglob("*.py"))
    }


def write_json(path, values):
    path.write_text(json.dumps(values, indent=2, allow_nan=False) + "\n", encoding="utf-8")


def cli(arguments, log_path):
    started = time.perf_counter()
    command = [sys.executable, "-m", "rupa_privacy", *map(str, arguments)]
    process = subprocess.run(command, cwd=str(ROOT), capture_output=True, text=True)
    log_path.write_text(
        "$ " + subprocess.list2cmdline(command) + "\n" + process.stdout + process.stderr,
        encoding="utf-8",
    )
    if process.returncode:
        raise RuntimeError("CLI failed; see " + str(log_path))
    return time.perf_counter() - started


def plot_results(allocation, stages, destination):
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    plt.rcParams.update({
        "font.size": 9, "axes.spines.top": False, "axes.spines.right": False,
        "svg.fonttype": "none", "pdf.fonttype": 42,
    })
    figure, axes = plt.subplots(1, 3, figsize=(12, 4.6), layout="constrained")
    for axis, (name, _, _) in zip(axes, EXAMPLES):
        values = allocation.loc[allocation["example"] == name]
        colors = ["#174A7E" if kind == "numerical" else "#168A83" for kind in values["kind"]]
        axis.barh(values["feature"], values["epsilon"], color=colors)
        axis.invert_yaxis()
        axis.set_xlabel("Allocated epsilon")
        axis.set_title(name)
    for suffix in ("png", "pdf", "svg"):
        figure.savefig(destination / ("field_budgets." + suffix), dpi=300)
    plt.close(figure)

    figure, axis = plt.subplots(figsize=(7.2, 3.8), layout="constrained")
    for color, (name, _, _) in zip(("#174A7E", "#168A83", "#C47A18"), EXAMPLES):
        values = stages.loc[stages["example"] == name].dropna(subset=["NRMS"])
        axis.plot(values["Order"], values["NRMS"], marker="o", label=name, color=color)
    axis.set_xticks([1, 2, 3, 4], ["DP perturbation", "Full projection", "Interpolation", "Final clipping"])
    axis.set_ylabel("Normalized residual RMS")
    axis.set_ylim(bottom=0)
    axis.legend(frameon=False)
    for suffix in ("png", "pdf", "svg"):
        figure.savefig(destination / ("constraint_stages." + suffix), dpi=300)
    plt.close(figure)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True, help="New directory; refuses overwrites")
    args = parser.parse_args(argv)
    output = args.output.resolve()
    if output.exists():
        parser.error("Output directory already exists; choose a new path")
    output.mkdir(parents=True)
    (output / "logs").mkdir()
    (output / "figures").mkdir()
    started = time.perf_counter()
    before = core_hashes()
    evidence = {
        "created_utc": datetime.now(timezone.utc).isoformat(),
        "software_version": __version__,
        "python": platform.python_version(),
        "os": platform.platform(),
        "source_commit": subprocess.check_output(
            ["git", "rev-parse", "HEAD"], cwd=str(ROOT), text=True
        ).strip() if (ROOT / ".git").exists() else None,
        "source_core_sha256": before,
        "dependencies": {
            item.metadata["Name"]: item.version for item in importlib.metadata.distributions()
        },
        "scope": "New illustrative runs only; not multi-seed comparison or scalability validation",
        "examples": [],
    }
    budgets, residuals = [], []
    try:
        for name, relative, config_name in EXAMPLES:
            inputs = ROOT / relative
            config = inputs / config_name
            schema, privacy, _, _, _, _ = load_pipeline_config(config)
            if privacy.randomness_mode != "reproducibility":
                raise RuntimeError("Review examples require reproducibility mode")
            arguments = [
                "--calibration", inputs / "calibration.csv",
                "--release", inputs / "release.csv", "--config", config,
            ]
            validation_time = cli(["validate", *arguments], output / "logs" / (name + "_validate.txt"))
            runtime = cli(
                ["run", *arguments, "--output", output / "runs", "--run-id", name],
                output / "logs" / (name + "_run.txt"),
            )
            run = output / "runs" / name
            cli(["inspect-run", run, "--sensitive-target", schema.sensitive_target],
                output / "logs" / (name + "_inspect.txt"))
            inspection = validate_public_run(run, schema.sensitive_target)
            release_columns = pd.read_csv(run / "release_data.csv", nrows=0).columns.tolist()
            if schema.sensitive_target in release_columns:
                raise RuntimeError("Sensitive target in public release")
            allocation = pd.read_csv(run / "epsilon_allocation.csv")
            if set(allocation["run_id"]) != {name}:
                raise RuntimeError("Allocation run_id mismatch")
            allocation["example"] = name
            allocation["kind"] = allocation["feature"].map(
                lambda field: "numerical" if field in schema.numeric_columns else "categorical"
            )
            budgets.append(allocation)
            physical = json.loads((run / "physical_metrics.json").read_text(encoding="utf-8"))
            stages = physical_stage_table(physical).assign(example=name, run_id=name)
            residuals.append(stages)
            evidence["examples"].append({
                "name": name, "inspection": inspection,
                "input_sha256": {
                    path.relative_to(ROOT).as_posix(): sha256(path)
                    for path in (config, inputs / "calibration.csv", inputs / "release.csv")
                },
                "randomness_mode": privacy.randomness_mode, "random_seed": privacy.random_seed,
                "epsilon_total": privacy.epsilon_total,
                "epsilon_sum": float(allocation["epsilon"].sum()),
                "release_columns": release_columns,
                "target_excluded": schema.sensitive_target not in release_columns,
                "manifest_sha256": sha256(run / "manifest.json"),
                "validation_seconds": validation_time, "cli_run_seconds": runtime,
                "timing_note": "Single local invocation including interpreter startup; not a benchmark",
                "independent_reuse_observed": False,
            })
            print(name + ": validate/run/inspect PASS", flush=True)
        allocation = pd.concat(budgets, ignore_index=True)
        stages = pd.concat(residuals, ignore_index=True)
        allocation.to_csv(output / "field_budgets.csv", index=False)
        stages.to_csv(output / "constraint_stages.csv", index=False)
        plot_results(allocation, stages, output / "figures")
        if before != core_hashes():
            raise RuntimeError("Core source changed during review")
        evidence["core_unchanged_during_run"] = True
        evidence["status"] = "PASS"
    except Exception as exc:
        evidence["status"] = "FAIL"
        evidence["failure"] = str(exc)
        raise
    finally:
        evidence["total_seconds"] = time.perf_counter() - started
        evidence["generated_artifact_sha256"] = {
            path.relative_to(output).as_posix(): sha256(path)
            for path in sorted(output.rglob("*")) if path.is_file()
        }
        write_json(output / "review_manifest.json", evidence)
    print("New-run figure evidence: " + str(output))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
