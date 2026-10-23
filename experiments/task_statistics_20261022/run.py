"""Run the frozen matched statistical task; never overwrite accepted results."""
import argparse
from dataclasses import replace
import hashlib
import importlib.metadata
import json
from pathlib import Path
import platform
import time
import traceback
import warnings
import xml.etree.ElementTree as ET

import numpy as np
import pandas as pd

from rupa_privacy.io import load_pipeline_config
from rupa_privacy.models import DataSchema, PrivacyConfig, AdjacencyConfig, PrivacyAccountingConfig
from examples.hazardous_waste.generate_data import generate_enterprise_year
from examples.water_treatment.generate_data import generate_water_treatment
from experiments.review_revision_20261021.run import dump, sha, core_hashes, digest
from .study import prepare_statistics, allocate, draw_statistics, stage_metrics, official_laplace

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]


def cases(protocol, output):
    folder = output / "inputs"
    folder.mkdir()
    for case in protocol["synthetic_cases"]:
        settings = load_pipeline_config(ROOT / "examples" / case / "config_reproducibility.yaml")
        counts = (240, 320) if case == "hazardous_waste" else (1500, 2000)
        generator = generate_enterprise_year if case == "hazardous_waste" else generate_water_treatment
        for pair in range(protocol["independent_generated_pairs_per_case"]):
            seed = protocol["calibration_seed_first"] + 1000 * (case == "water_treatment") + 2 * pair
            name = case + "_pair" + str(pair)
            cal = generator(counts[0], seed, name + "_CAL-")
            rel = generator(counts[1], seed + 1, name + "_REL-").drop(columns=[settings[0].sensitive_target])
            current = folder / name
            current.mkdir()
            cal.to_csv(current / "calibration.csv", index=False)
            rel.to_csv(current / "release.csv", index=False)
            yield name, case, "independent_generated_pair", cal, rel, settings
    external = json.loads((HERE / "external/schema.json").read_text())
    names = external["fields"]
    schema = DataSchema(external["target"], names, [], public_bounds=external["public_bounds"])
    privacy = PrivacyConfig(epsilon_total=5, epsilon_numeric=5, epsilon_categorical=0,
        numeric_budget_strategy="uniform", calibration_mode="public", calibration_public_confirmed=True,
        calibration_source="UCI Concrete CC BY 4.0 disjoint recipe groups",
        release_data_mode="public_demonstration", release_public_confirmed=True,
        release_source="UCI Concrete already public benchmark")
    adjacency = AdjacencyConfig("fixed_roster_replace_one", "specimen_id", True, True)
    accounting = PrivacyAccountingConfig("uci_concrete_research_only", 20, "not_used_in_research.sqlite3")
    settings = (schema, privacy, [], {name: 1 / len(names) for name in names}, adjacency, accounting)
    for block in range(protocol["public_external_dataset"]["disjoint_blocks"]):
        source = HERE / "external" / ("block_" + str(block))
        yield "uci_concrete_block" + str(block), "uci_concrete", "external_public_disjoint_block", pd.read_csv(source / "calibration.csv"), pd.read_csv(source / "release.csv"), settings


def summarize(raw, expected, output):
    keys = ["dataset", "case", "evidence_type", "epsilon", "strategy", "stage"]
    columns = ["normalized_squared_error", "median_relative_error_percent", "mean_relative_error_percent", "maximum_relative_error_percent", "nrms"]
    grouped = raw.groupby(keys)
    rows = []
    for key, frame in grouped:
        row = dict(zip(keys, key))
        row["runs"] = len(frame)
        for column in columns:
            values = frame[column].to_numpy()
            row[column + "_mean"] = float(values.mean())
            row[column + "_median"] = float(np.median(values))
            row[column + "_p10"], row[column + "_p90"] = np.quantile(values, [.1, .9])
        rows.append(row)
    summary = pd.DataFrame(rows)
    summary.to_csv(output / "summary.csv", index=False)
    paired = []
    rng = np.random.default_rng(20261022)
    for key, frame in raw.groupby(["dataset", "case", "epsilon", "stage"]):
        baseline = frame[frame.strategy == "uniform_statistics"].sort_values("seed")
        for strategy in ("workload_rupa", "workload_without_risk_cap"):
            current = frame[frame.strategy == strategy].sort_values("seed")
            assert current.seed.tolist() == baseline.seed.tolist()
            for column in columns[:3]:
                delta = current[column].to_numpy() - baseline[column].to_numpy()
                means = delta[rng.integers(0, len(delta), size=(2000, len(delta)))].mean(axis=1)
                lo, hi = np.quantile(means, [.025, .975])
                paired.append(dict(zip(["dataset", "case", "epsilon", "stage"], key), strategy=strategy,
                    metric=column, mean_difference=float(delta.mean()), ci95_lower=float(lo), ci95_upper=float(hi),
                    mean_loss_ratio=float(current[column].mean() / baseline[column].mean()),
                    paired_win_fraction=float(np.mean(delta < 0))))
    pd.DataFrame(paired).to_csv(output / "paired_differences.csv", index=False)
    expected.to_csv(output / "expected_loss.csv", index=False)
    # Keep dataset-level variability separate from within-table seed variability.
    ratios = expected[expected.strategy == "workload_rupa"].copy()
    ratios.groupby(["case", "epsilon"])["expected_loss_ratio"].agg(["count", "median", "min", "max"]).to_csv(output / "between_dataset_expected_ratios.csv")
    plot(summary, ratios, output)


def plot(summary, ratios, output):
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    colors = {"uniform_statistics": "#65717C", "workload_rupa": "#137E72", "workload_without_risk_cap": "#B16E33"}
    fig, axes = plt.subplots(2, 3, figsize=(11, 6.3), layout="constrained")
    for column, case in enumerate(["hazardous_waste", "water_treatment", "uci_concrete"]):
        frame = summary[(summary.case == case) & (summary.stage == "final_clipped") & (summary.epsilon == 5)]
        for strategy, color in colors.items():
            values = frame[frame.strategy == strategy].normalized_squared_error_mean.to_numpy()
            x = list(colors).index(strategy)
            axes[0, column].scatter(np.full(len(values), x), values, color=color, s=24, alpha=.8)
            axes[0, column].plot([x - .18, x + .18], [np.median(values)] * 2, color="black", linewidth=1.5)
        axes[0, column].set_xticks([0, 1, 2], ["Uniform", "Task + risk", "Task only"], fontsize=8)
        axes[0, column].set_title(case.replace("_", " "), fontsize=10)
        axes[0, column].set_ylabel("Mean normalized squared error\n(final clipping, epsilon = 5)", fontsize=8)
        data = ratios[(ratios.case == case) & (ratios.epsilon == 5)]
        axes[1, column].scatter(np.arange(len(data)) + 1, data.expected_loss_ratio, color=colors["workload_rupa"], s=27)
        axes[1, column].axhline(1, color=colors["uniform_statistics"], linestyle="--", linewidth=1)
        axes[1, column].set_ylim(0, 1.1)
        axes[1, column].set_xlabel("Disjoint block" if case == "uci_concrete" else "New calibration/release pair", fontsize=8)
        axes[1, column].set_ylabel("Expected projected loss / uniform", fontsize=8)
        for row in range(2):
            ax = axes[row, column]
            ax.spines[["top", "right"]].set_visible(False)
            ax.grid(axis="y", alpha=.2)
            ax.text(-.18, 1.04, "abcdef"[row * 3 + column], transform=ax.transAxes, weight="bold")
    fig.savefig(output / "task_statistics_validation.png", dpi=300)
    fig.savefig(output / "task_statistics_validation.pdf")
    plt.close(fig)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--pytest-xml", type=Path, required=True)
    args = parser.parse_args()
    gate = ET.parse(args.pytest_xml)
    if len(list(gate.iter("testcase"))) < 391 or list(gate.iter("failure")) or list(gate.iter("error")):
        raise ValueError("Complete passing test gate required")
    if time.time() - args.pytest_xml.stat().st_mtime > 86400:
        raise ValueError("Test gate expired")
    output = args.output.resolve()
    output.mkdir(parents=True, exist_ok=False)
    official_laplace()
    protocol = json.loads((HERE / "protocol.json").read_text())
    manifest = {"protocol_sha256": sha(HERE / "protocol.json"), "core_before": core_hashes(),
        "source_sha256": {name: sha(HERE / name) for name in ["run.py", "study.py", "prepare_external.py"]},
        "python": platform.python_version(), "platform": platform.platform(),
        "dependencies": {name: importlib.metadata.version(name) for name in ["numpy", "scipy", "pandas", "scikit-learn", "diffprivlib"]},
        "external_provenance": json.loads((HERE / "external/provenance.json").read_text()),
        "pytest_sha256": sha(args.pytest_xml), "datasets": [], "failures": [], "completed_release_draws": 0,
        "randomness_mode": "reproducibility", "production_supported": False}
    records, theory, field_records = [], [], []
    public = output / "public_statistics"
    public.mkdir()
    started = time.perf_counter()
    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always")
        for dataset, case, evidence_type, calibration, release, settings in cases(protocol, output):
            try:
                prepared = prepare_statistics(calibration, release, settings)
                manifest["datasets"].append({"dataset": dataset, "case": case, "evidence_type": evidence_type,
                    "calibration_hash": digest(calibration), "release_hash": digest(release), "calibration_rows": len(calibration),
                    "release_rows": len(release), "clipped_input_fraction": prepared["clipped_input_fraction"]})
                for epsilon in protocol["epsilon_total"]:
                    for strategy in protocol["strategies"]:
                        allocation, diagnostics = allocate(prepared, epsilon, strategy)
                        loss = diagnostics["expected_noise_loss"] + prepared["projection_bias_loss"]
                        uniform_loss = diagnostics["uniform_expected_noise_loss"] + prepared["projection_bias_loss"]
                        theory.append(dict(dataset=dataset, case=case, epsilon=epsilon, strategy=strategy,
                            expected_noise_loss=diagnostics["expected_noise_loss"], expected_total_loss=loss,
                            expected_loss_ratio=loss / uniform_loss, projection_bias_loss=prepared["projection_bias_loss"]))
                        field_samples = {stage: [] for stage in ("noisy", "projected", "final_clipped")}
                        for seed in range(protocol["mechanism_seeds"]["first"], protocol["mechanism_seeds"]["first"] + protocol["mechanism_seeds"]["count"]):
                            run_id = "{0}_e{1}_{2}_s{3}".format(dataset, epsilon, strategy, seed)
                            try:
                                states = draw_statistics(prepared, allocation, seed)
                                for stage, values in states.items():
                                    records.append(dict(run_id=run_id, dataset=dataset, case=case, evidence_type=evidence_type,
                                        epsilon=epsilon, strategy=strategy, seed=seed, stage=stage, **stage_metrics(prepared, values)))
                                    field_samples[stage].append(values)
                                manifest["completed_release_draws"] += 1
                                if seed == protocol["mechanism_seeds"]["first"]:
                                    pd.DataFrame({"field": prepared["names"], "total_estimate": states["final_clipped"],
                                        "mean_estimate": states["final_clipped"] / prepared["rows"], "epsilon": allocation,
                                        "public_rows": prepared["rows"], "run_id": run_id}).to_csv(public / (run_id + ".csv"), index=False)
                            except Exception as exc:
                                manifest["failures"].append({"run_id": run_id, "error": str(exc), "traceback": traceback.format_exc()})
                        for stage, samples in field_samples.items():
                            errors = abs(np.stack(samples) - prepared["truth"]) / prepared["scale"]
                            for index, name in enumerate(prepared["names"]):
                                field_records.append(dict(dataset=dataset, epsilon=epsilon, strategy=strategy, stage=stage, field=name,
                                    normalized_absolute_error_mean=float(errors[:, index].mean()),
                                    normalized_absolute_error_p10=float(np.quantile(errors[:, index], .1)),
                                    normalized_absolute_error_p90=float(np.quantile(errors[:, index], .9)), epsilon_field=float(allocation[index])))
            except Exception as exc:
                manifest["failures"].append({"dataset": dataset, "error": str(exc), "traceback": traceback.format_exc()})
            dump(output / "manifest.json", manifest)
            print(dataset, "completed draws", manifest["completed_release_draws"], "failures", len(manifest["failures"]), flush=True)
    evaluation = output / "evaluation"
    evaluation.mkdir()
    raw = pd.DataFrame(records)
    raw.to_csv(evaluation / "raw_metrics.csv", index=False)
    pd.DataFrame(field_records).to_csv(evaluation / "field_metrics.csv", index=False)
    summarize(raw, pd.DataFrame(theory), evaluation)
    manifest.update(core_after=core_hashes(), warnings=sorted(set(str(w.message) for w in caught)), elapsed_seconds=time.perf_counter() - started)
    expected_draws = 25 * 3 * 3 * 200
    manifest["expected_release_draws"] = expected_draws
    manifest["status"] = "PASS" if manifest["completed_release_draws"] == expected_draws and not manifest["failures"] and manifest["core_before"] == manifest["core_after"] else "FAIL"
    dump(output / "manifest.json", manifest)
    print(manifest["status"], "draws", manifest["completed_release_draws"], "stage rows", len(raw), "failures", len(manifest["failures"]), flush=True)
    if manifest["status"] != "PASS":
        raise SystemExit(1)


if __name__ == "__main__":
    main()
