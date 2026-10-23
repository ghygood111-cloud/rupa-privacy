"""Prespecified public-data application of the installed, unchanged RUPA API."""
import argparse
import hashlib
import importlib.metadata
import importlib.util
import json
from pathlib import Path
import platform
import sys
import time
import traceback
import xml.etree.ElementTree as ET
from dataclasses import replace

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

from rupa_privacy import RUPAPipeline
from rupa_privacy.io import load_pipeline_config, save_config, write_public_run, validate_public_run

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
EXAMPLE = ROOT / "examples" / "ontario_registration"
FIELDS = ("handles_liquid", "handles_solid")
UNIT = "public_registration_id"
spec = importlib.util.spec_from_file_location("ontario_public_analysis", EXAMPLE / "analysis.py")
analysis = importlib.util.module_from_spec(spec)
spec.loader.exec_module(analysis)


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def core_hashes():
    return {p.relative_to(ROOT).as_posix(): sha(p)
            for p in sorted((ROOT / "src" / "rupa_privacy").rglob("*.py"))}


def dump(path, values):
    Path(path).write_text(json.dumps(values, indent=2, allow_nan=False), encoding="utf-8")


def require_passing_baseline(path):
    xml = ET.parse(path)
    cases = list(xml.iter("testcase"))
    if len(cases) < 255 or list(xml.iter("failure")) or list(xml.iter("error")):
        raise RuntimeError("The complete pre-experiment baseline must pass first")
    return {"test_cases": len(cases), "junit_sha256": sha(path), "junit_file": str(path)}


def plot_results(raw, marginals, truth, truth_both, folder):
    figure, axes = plt.subplots(1, 2, figsize=(9.2, 3.7), layout="constrained")
    chosen_id = "ontario_uniform_eps2_seed20262000"
    representative = marginals[marginals.run_id == chosen_id]
    representative_run = raw[raw.run_id == chosen_id].iloc[0]
    x = np.arange(3)
    reference = [truth[name] for name in FIELDS] + [truth_both]
    observed = [float(representative[representative.field == name].observed_proportion.iloc[0])
                for name in FIELDS] + [representative_run.both_states_observed]
    decoded = [float(representative[representative.field == name].decoded_proportion_unclipped.iloc[0])
               for name in FIELDS] + [representative_run.both_states_decoded_unclipped]
    for offset, values, color, label in [
        (-0.25, reference, "#616A73", "Public reference"),
        (0.0, observed, "#CE8D32", "Raw GRR proportions"),
        (0.25, decoded, "#218269", "Decoded from public GRR")]:
        axes[0].bar(x + offset, 100 * np.asarray(values), width=.23, color=color, label=label)
    axes[0].set_xticks(x, ["Any liquid", "Any solid", "Both states"])
    axes[0].set_ylabel("Share of registration units (%)")
    axes[0].set_title("One prespecified run: total epsilon = 2", fontsize=10)
    axes[0].legend(fontsize=7, frameon=False)
    for strategy, color, label in [
        ("uniform", "#23669A", "Uniform category budgets"),
        ("heuristic_risk_utility", "#92554C", "Current heuristic budgets")]:
        g = raw[raw.strategy == strategy].groupby("epsilon").max_marginal_error_pp
        med, q90 = g.median(), g.quantile(.9)
        axes[1].plot(med.index, med, marker="o", color=color, label=label)
        axes[1].plot(q90.index, q90, linestyle="--", color=color, linewidth=1.1)
    axes[1].axhline(2.0, color="#5D6870", linestyle=":", linewidth=1.2)
    axes[1].set_xticks([1, 2, 5])
    axes[1].set_xlabel("Total privacy budget epsilon")
    axes[1].set_ylabel("Maximum marginal absolute error (pp)")
    axes[1].set_title("30 seeds: solid = median; dashed = 90th percentile", fontsize=9)
    axes[1].legend(fontsize=7, frameon=False)
    for letter, ax in zip("ab", axes):
        ax.set_axisbelow(True)
        ax.grid(axis="y", color="#E3E7EB", linewidth=.6)
        ax.spines[["top", "right"]].set_visible(False)
        ax.text(-.13, 1.06, letter, transform=ax.transAxes, weight="bold")
        ax.tick_params(labelsize=8)
    folder.mkdir(exist_ok=True)
    figure.savefig(folder / "registration_coverage.png", dpi=320)
    plt.close(figure)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=HERE / "results")
    parser.add_argument("--pytest-xml", type=Path, default=HERE / "pytest_before.xml")
    args = parser.parse_args()
    baseline = require_passing_baseline(args.pytest_xml)
    protocol = json.loads((HERE / "protocol.json").read_text(encoding="utf-8"))
    before = core_hashes()
    out = args.output.resolve()
    out.mkdir(exist_ok=False)
    manifest = {
        "protocol_sha256": sha(HERE / "protocol.json"),
        "source_scripts_sha256": {str(p.relative_to(ROOT)): sha(p) for p in
                                  [Path(__file__), EXAMPLE / "prepare.py", EXAMPLE / "analysis.py"]},
        "baseline": baseline, "core_before": before,
        "python": platform.python_version(), "python_executable": sys.executable,
        "platform": platform.platform(),
        "dependencies": {name: importlib.metadata.version(name) for name in
                         ["rupa-privacy", "numpy", "scipy", "pandas", "scikit-learn", "matplotlib", "PyYAML"]},
        "source_provenance_sha256": sha(EXAMPLE / "provenance.json"),
        "inputs": {name: sha(EXAMPLE / name) for name in
                   ["calibration.csv", "release.csv", "config_reproducibility.yaml"]},
        "runs": [], "failures": [],
    }
    dump(out / "manifest.json", manifest)
    calibration = pd.read_csv(EXAMPLE / "calibration.csv")
    release = pd.read_csv(EXAMPLE / "release.csv")
    assert set(calibration[UNIT]).isdisjoint(release[UNIT])
    assert calibration[UNIT].is_unique and release[UNIT].is_unique
    truth = {name: float(release[name].eq("yes").mean()) for name in FIELDS}
    truth_both = float(release[list(FIELDS)].eq("yes").all(axis=1).mean())
    dump(out / "public_reference_aggregates.json", {
        "notice": "Ground truth from already public source; never a confidential-data export helper.",
        "rows": len(release), "calibration_rows": len(calibration),
        "marginals": truth, "both": truth_both,
        "data_free_midpoint_max_error_pp": 100 * max(abs(v - .5) for v in truth.values()),
    })
    schema, base, constraints, prior, adjacency, accounting = load_pipeline_config(
        EXAMPLE / "config_reproducibility.yaml")
    records, marginal_records = [], []
    start_all = time.perf_counter()
    for strategy in protocol["allocation_strategies"]:
        for epsilon in protocol["epsilon_total"]:
            privacy = replace(base, epsilon_total=epsilon, epsilon_categorical=epsilon,
                              categorical_budget_strategy=strategy)
            fit_start = time.perf_counter()
            fitted = RUPAPipeline(schema, privacy, constraints, prior, adjacency, accounting).fit(calibration)
            fit_seconds = time.perf_counter() - fit_start
            first = protocol["seeds"]["first"]
            for seed in range(first, first + protocol["seeds"]["count"]):
                run_id = "ontario_{0}_eps{1:g}_seed{2}".format(strategy, epsilon, seed)
                start = time.perf_counter()
                try:
                    run_privacy = replace(privacy, random_seed=seed)
                    # fit() is release-independent; reuse its frozen public calibration.
                    result = fitted.transform(release, seed=seed)
                    config_path = out / "configs" / (run_id + ".json")
                    save_config(config_path, schema, run_privacy, constraints, prior, adjacency, accounting)
                    run = write_public_run(result, schema, run_privacy, constraints, prior, adjacency,
                                           accounting, out / "runs", run_id=run_id)
                    inspection = validate_public_run(run, schema.sensitive_target)
                    protected = pd.read_csv(run / "release_data.csv")
                    assert protected.columns.tolist() == [UNIT] + list(FIELDS)
                    assert protected[UNIT].tolist() == release[UNIT].tolist()
                    assert np.isclose(sum(result.allocation_result.epsilon.values()), epsilon, rtol=0, atol=1e-12)
                    assert not (run / ".internal_audit").exists()
                    evaluated = analysis.analyze_run(run)
                    errors, raw_errors, interval_covers = [], [], []
                    for field in FIELDS:
                        values = evaluated["marginals"][field]
                        decoded_error = 100 * abs(values["decoded_proportion_unclipped"] - truth[field])
                        raw_error = 100 * abs(values["observed_proportion"] - truth[field])
                        cover = values["simultaneous_95_lower"] <= truth[field] <= values["simultaneous_95_upper"]
                        errors.append(decoded_error)
                        raw_errors.append(raw_error)
                        interval_covers.append(cover)
                        marginal_records.append({
                            "run_id": run_id, "strategy": strategy, "epsilon": epsilon,
                            "seed": seed, "field": field, "public_reference_proportion": truth[field],
                            **values, "decoded_absolute_error_pp": decoded_error,
                            "raw_absolute_error_pp": raw_error, "interval_covers": bool(cover),
                            "retention": float(protected[field].eq(release[field]).mean()),
                        })
                    record = {
                        "run_id": run_id, "strategy": strategy, "epsilon": epsilon, "seed": seed,
                        "max_marginal_error_pp": max(errors), "mean_marginal_error_pp": float(np.mean(errors)),
                        "max_raw_marginal_error_pp": max(raw_errors),
                        "both_states_observed": evaluated["both_states_observed"],
                        "both_states_decoded_unclipped": evaluated["both_states_decoded_unclipped"],
                        "both_states_error_pp": 100 * abs(evaluated["both_states_decoded_unclipped"] - truth_both),
                        "both_marginal_intervals_cover": bool(all(interval_covers)),
                        "epsilon_liquid": evaluated["marginals"][FIELDS[0]]["epsilon"],
                        "epsilon_solid": evaluated["marginals"][FIELDS[1]]["epsilon"],
                        "fit_seconds": fit_seconds, "run_and_inspection_seconds": time.perf_counter() - start,
                    }
                    records.append(record)
                    manifest["runs"].append({
                        "run_id": run_id, "config_sha256": sha(config_path),
                        "manifest_sha256": sha(run / "manifest.json"),
                        "release_sha256": sha(run / "release_data.csv"), "inspection": inspection,
                    })
                    if seed == first:
                        dump(out / (run_id + "_public_analysis.json"), evaluated)
                except Exception as exc:
                    manifest["failures"].append({"run_id": run_id, "type": type(exc).__name__,
                                                 "error": str(exc), "traceback": traceback.format_exc()})
                    print(run_id, "FAIL", repr(exc), flush=True)
                if (seed - first + 1) % 10 == 0:
                    print(strategy, epsilon, "completed", seed - first + 1, "/", protocol["seeds"]["count"], flush=True)
    raw = pd.DataFrame(records)
    marginals = pd.DataFrame(marginal_records)
    raw.to_csv(out / "raw_run_metrics.csv", index=False)
    marginals.to_csv(out / "marginal_metrics.csv", index=False)
    summary = []
    for (strategy, epsilon), frame in raw.groupby(["strategy", "epsilon"]):
        row = {"strategy": strategy, "epsilon": epsilon, "successful_runs": len(frame)}
        for name in ["max_marginal_error_pp", "max_raw_marginal_error_pp", "both_states_error_pp"]:
            for suffix, value in [("median", frame[name].median()), ("p90", frame[name].quantile(.9)),
                                  ("min", frame[name].min()), ("max", frame[name].max())]:
                row[name + "_" + suffix] = float(value)
        row["simultaneous_interval_empirical_coverage"] = float(frame.both_marginal_intervals_cover.mean())
        row["epsilon_liquid"] = float(frame.epsilon_liquid.iloc[0])
        row["epsilon_solid"] = float(frame.epsilon_solid.iloc[0])
        summary.append(row)
    summary = pd.DataFrame(summary)
    summary.to_csv(out / "summary.csv", index=False)
    manifest.update({"seconds": time.perf_counter() - start_all,
                     "successful_runs": len(raw), "core_unchanged": core_hashes() == before,
                     "core_after": core_hashes()})
    main_row = summary[(summary.strategy == "uniform") & (summary.epsilon == 2)].iloc[0]
    manifest["primary_acceptance_pass"] = bool(main_row.max_marginal_error_pp_p90 <= 2)
    manifest["secondary_acceptance_pass"] = bool(main_row.both_states_error_pp_p90 <= 5)
    manifest["statistical_note"] = "Observed quantiles over 30 randomization seeds are not confidence intervals or evidence of independent deployments."
    dump(out / "manifest.json", manifest)
    if manifest["failures"] or len(raw) != 180 or not manifest["core_unchanged"]:
        raise RuntimeError("Incomplete case; see results/manifest.json")
    plot_results(raw, marginals, truth, truth_both, out / "figures")
    print(summary.to_string(index=False), flush=True)
    print("Primary tolerance PASS:", manifest["primary_acceptance_pass"],
          "Secondary tolerance PASS:", manifest["secondary_acceptance_pass"],
          "Core unchanged:", manifest["core_unchanged"], flush=True)


if __name__ == "__main__":
    main()
