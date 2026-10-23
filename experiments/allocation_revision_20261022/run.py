"""Evaluate all official numeric strategies through the same public pipeline."""
import argparse
from dataclasses import replace
import importlib.metadata
import json
from pathlib import Path
import platform
import sys
import time
import traceback
import warnings
import xml.etree.ElementTree as ET

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from scipy.stats import wasserstein_distance

from rupa_privacy import RUPAPipeline
from rupa_privacy.io import load_pipeline_config, save_config, write_public_run, validate_public_run
from rupa_privacy.allocation.optimizer import risk_exposure
from experiments.review_revision_20261021.analysis import bootstrap_mean_difference, require_research_inputs
from experiments.review_revision_20261021.run import digest, dump, sha, core_hashes
from examples.hazardous_waste.generate_data import generate_enterprise_year

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]


def metrics(original, final, schema):
    names = schema.numeric_columns
    x, y = original[names].to_numpy(float), final[names].to_numpy(float)
    totals = x.sum(axis=0)
    if np.any(np.abs(totals) < 1e-12):
        raise ValueError("Undefined relative error for zero total")
    ranges = np.array([schema.public_bounds[n][1] - schema.public_bounds[n][0] for n in names])
    return {"median_field_total_error_percent": float(np.median(100 * np.abs(y.sum(axis=0) - totals) / np.abs(totals))),
            "mae_range": float(np.mean(np.abs(y - x) / ranges)),
            "wasserstein_range": float(np.mean([wasserstein_distance(x[:, j], y[:, j]) / ranges[j] for j in range(len(names))]))}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--pytest-xml", type=Path, required=True)
    args = parser.parse_args()
    xml = ET.parse(args.pytest_xml)
    if len(list(xml.iter("testcase"))) < 348 or list(xml.iter("failure")) or list(xml.iter("error")):
        raise RuntimeError("A fresh complete passing test gate is required")
    if time.time() - args.pytest_xml.stat().st_mtime > 86400:
        raise RuntimeError("Test gate too old")
    out = args.output.resolve()
    out.mkdir(parents=True, exist_ok=False)
    protocol = json.loads((HERE / "protocol.json").read_text())
    manifest = {"protocol_sha256": sha(HERE / "protocol.json"), "core_before": core_hashes(),
                "script_sha256": sha(__file__), "python": sys.version, "platform": platform.platform(),
                "dependencies": {n: importlib.metadata.version(n) for n in ("rupa-privacy", "numpy", "pandas", "scipy", "scikit-learn")},
                "pytest_sha256": sha(args.pytest_xml), "inputs": {}, "runs": [], "failures": [],
                "randomness_mode": "reproducibility", "settings_frozen_before_new_results": True}
    records, paired, budgets = [], [], []
    started = time.perf_counter()
    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always")
        for case in protocol["cases"]:
            folder = ROOT / "examples" / ("hazardous_waste" if case.endswith("holdout") else case)
            schema, base, constraints, prior, adjacency, accounting = load_pipeline_config(folder / "config_reproducibility.yaml")
            require_research_inputs(base)
            calibration = pd.read_csv(folder / "calibration.csv")
            if case.endswith("holdout"):
                holdout = protocol["holdout"]
                release = generate_enterprise_year(holdout["rows"], holdout["seed"], holdout["prefix"]).drop(columns=[schema.sensitive_target])
            else:
                release = pd.read_csv(folder / "release.csv")
            manifest["inputs"][case] = {"calibration_sha256": sha(folder / "calibration.csv"), "release_digest": digest(release),
                                         "rows": len(release), "config_sha256": sha(folder / "config_reproducibility.yaml")}
            if case.endswith("holdout"):
                manifest["inputs"][case]["unchanged_generator_sha256"] = sha(ROOT / protocol["holdout"]["unchanged_generator"])
            for epsilon in protocol["epsilon_total"]:
                ratio = base.epsilon_numeric / base.epsilon_total
                for strategy in protocol["strategies"]:
                    privacy = replace(base, epsilon_total=float(epsilon), epsilon_numeric=ratio * epsilon,
                                      epsilon_categorical=(1 - ratio) * epsilon, categorical_budget_strategy="uniform",
                                      numeric_budget_strategy=strategy, **protocol["balanced_settings"])
                    pipeline = RUPAPipeline(schema, privacy, constraints, prior, adjacency, accounting).fit(calibration)
                    allocation = pipeline.fitted_state_.allocation_result
                    r = np.array([pipeline.fitted_state_.risk_result.augmented_risk[n] for n in schema.numeric_columns])
                    eps = np.array([allocation.epsilon[n] for n in schema.numeric_columns])
                    uniform_risk = risk_exposure(np.full(len(r), privacy.epsilon_numeric / len(r)), r)
                    exposure = risk_exposure(eps, r)
                    for name, e in zip(schema.numeric_columns, eps):
                        budgets.append({"case": case, "epsilon_total": epsilon, "strategy": strategy, "field": name, "epsilon_field": e})
                    if strategy == "balanced_rupa":
                        assert exposure <= uniform_risk + max(1e-9, uniform_risk * 1e-8)
                    first = protocol["seeds"]["first"]
                    for seed in range(first, first + protocol["seeds"]["count"]):
                        for alpha in protocol["repair_alpha"]:
                            run_id = "{0}_e{1}_{2}_a{3}_s{4}".format(case, epsilon, strategy, alpha, seed)
                            try:
                                runner = RUPAPipeline(schema, replace(privacy, repair_alpha=alpha, random_seed=seed), constraints, prior, adjacency, accounting)
                                runner.fitted_state_ = pipeline.fitted_state_
                                result = runner.transform(release, seed=seed)
                                record = {"run_id": run_id, "case": case, "epsilon": epsilon, "strategy": strategy,
                                          "repair_alpha": alpha, "seed": seed, **metrics(release, result.release_data, schema),
                                          "final_nrms": result.physical_audit["states"]["final_clipped"]["nrms"],
                                          "violation_rate": result.physical_audit["states"]["final_clipped"]["violation_rate"],
                                          "max_numeric_budget_share": float(eps.max() / privacy.epsilon_numeric),
                                          "risk_exposure": exposure, "uniform_risk_exposure": uniform_risk}
                                records.append(record)
                                manifest["runs"].append({"run_id": run_id, "noisy_digest": digest(result.noisy_data), "final_digest": digest(result.release_data)})
                                if seed == first:
                                    config = out / "configs" / (run_id + ".json")
                                    save_config(config, schema, runner.privacy_config, constraints, prior, adjacency, accounting)
                                    run = write_public_run(result, schema, runner.privacy_config, constraints, prior, adjacency, accounting,
                                                           out / "public_runs", run_id=run_id)
                                    validate_public_run(run, schema.sensitive_target)
                            except Exception as exc:
                                manifest["failures"].append({"run_id": run_id, "error": str(exc), "traceback": traceback.format_exc()})
                    print(case, epsilon, strategy, "completed 30 paired seeds", flush=True)
                    dump(out / "manifest.json", manifest)
    raw = pd.DataFrame(records)
    raw.to_csv(out / "raw_metrics.csv", index=False)
    pd.DataFrame(budgets).to_csv(out / "field_budgets.csv", index=False)
    metric_names = ["median_field_total_error_percent", "mae_range", "wasserstein_range", "final_nrms", "max_numeric_budget_share"]
    summary = raw.groupby(["case", "epsilon", "strategy", "repair_alpha"])[metric_names].median().reset_index()
    summary.to_csv(out / "summary.csv", index=False)
    for (case, epsilon, alpha), frame in raw.groupby(["case", "epsilon", "repair_alpha"]):
        for baseline in ("legacy_rupa", "uniform"):
            a = frame[frame.strategy == "balanced_rupa"].sort_values("seed")
            b = frame[frame.strategy == baseline].sort_values("seed")
            if len(a) == len(b) == 30:
                for metric in metric_names[:4]:
                    paired.append({"case": case, "epsilon": epsilon, "repair_alpha": alpha, "baseline": baseline, "metric": metric,
                                   **bootstrap_mean_difference(a[metric], b[metric])})
    pd.DataFrame(paired).to_csv(out / "paired_differences.csv", index=False)
    fig, axes = plt.subplots(1, 3, figsize=(10, 3.4), layout="constrained")
    for ax, case, letter in zip(axes, protocol["cases"], "abc"):
        for strategy, color in (("legacy_rupa", "#B57336"), ("uniform", "#5F7180"), ("balanced_rupa", "#158070")):
            frame = summary[(summary.case == case) & (summary.strategy == strategy) & (summary.repair_alpha == .98)]
            ax.plot(frame.epsilon, frame.median_field_total_error_percent, marker="o", color=color, label=strategy)
        ax.set_title(case.replace("_", " "), fontsize=9)
        ax.set_xlabel("Total epsilon")
        ax.set_ylabel("Median field-total error (%)")
        ax.spines[["top", "right"]].set_visible(False)
        ax.grid(axis="y", alpha=.2)
        ax.text(-.15, 1.05, letter, transform=ax.transAxes, weight="bold")
    axes[0].legend(frameon=False, fontsize=7)
    fig.savefig(out / "balanced_allocation_comparison.png", dpi=300)
    plt.close(fig)
    manifest.update(core_after=core_hashes(), warnings=sorted(set(str(w.message) for w in caught)), elapsed_seconds=time.perf_counter() - started)
    manifest["core_unchanged_during_experiment"] = manifest["core_before"] == manifest["core_after"]
    manifest["expected_runs"] = 1620
    manifest["status"] = "PASS" if len(manifest["runs"]) == 1620 and not manifest["failures"] and manifest["core_unchanged_during_experiment"] else "FAIL"
    dump(out / "manifest.json", manifest)
    print(manifest["status"], "runs", len(manifest["runs"]), "failures", len(manifest["failures"]), flush=True)
    if manifest["status"] != "PASS":
        raise SystemExit(1)


if __name__ == "__main__":
    main()
