"""Execute the frozen reviewer experiments with unchanged RUPA components."""
import argparse
from dataclasses import replace
import hashlib
import importlib.metadata
import inspect
import json
from pathlib import Path
import platform
import sys
import time
import traceback
import warnings
import xml.etree.ElementTree as ET

import numpy as np
import pandas as pd

from rupa_privacy import RUPAPipeline
from rupa_privacy.io import load_pipeline_config, save_config, validate_public_run, write_public_run
from rupa_privacy.mechanisms import perturb_release_data
from rupa_privacy.physics import apply_physical_projection

from .analysis import bootstrap_mean_difference, clipped_laplace_moments, numerical_metrics, require_research_inputs, uniform_numeric_allocation

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def digest(frame):
    keyword = "lineterminator" if "lineterminator" in inspect.signature(frame.to_csv).parameters else "line_terminator"
    return hashlib.sha256(frame.to_csv(index=False, float_format="%.17g", **{keyword: "\n"}).encode()).hexdigest()


def dump(path, value):
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    Path(path).write_text(json.dumps(value, indent=2, allow_nan=False,
                                   default=lambda v: v.item() if isinstance(v, np.generic) else v.tolist()), encoding="utf-8")


def core_hashes():
    return {p.relative_to(ROOT).as_posix(): sha(p) for p in sorted((ROOT / "src/rupa_privacy").rglob("*.py"))}


def start_run(args):
    tree = ET.parse(args.pytest_xml)
    cases = list(tree.iter("testcase"))
    if len(cases) < 277 or list(tree.iter("failure")) or list(tree.iter("error")):
        raise RuntimeError("A passing complete pytest baseline with at least 277 tests is required")
    if time.time() - args.pytest_xml.stat().st_mtime > 86400:
        raise RuntimeError("Pytest gate is older than 24 hours; rerun full pytest")
    args.output.mkdir(parents=True, exist_ok=False)
    versions = {n: importlib.metadata.version(n) for n in ("rupa-privacy", "numpy", "scipy", "pandas", "scikit-learn", "matplotlib", "PyYAML")}
    manifest = {"section": args.section, "protocol_sha256": sha(HERE / "protocol.json"),
                "script_hashes": {p.name: sha(p) for p in (Path(__file__), HERE / "analysis.py")},
                "core_before": core_hashes(), "python": sys.version, "platform": platform.platform(),
                "dependencies": versions, "pytest_cases": len(cases), "pytest_sha256": sha(args.pytest_xml),
                "randomness_mode": "reproducibility", "runs": [], "failures": [], "warnings": []}
    dump(args.output / "manifest.json", manifest)
    return manifest


def record_config(out, run_id, values):
    save_config(out / "configs" / (run_id + ".json"), *values)


def numeric(args, protocol, manifest):
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    tools = HERE / "tools"
    if tools.is_dir():
        sys.path.insert(0, str(tools))
    from diffprivlib.mechanisms import Laplace
    manifest["external_mechanism_version"] = importlib.metadata.version("diffprivlib")
    ex = ROOT / protocol["example"]
    calibration, release = (pd.read_csv(ex / name) for name in ("calibration.csv", "release.csv"))
    schema, base, constraints, prior, adjacency, accounting = load_pipeline_config(ex / "config_reproducibility.yaml")
    require_research_inputs(base)
    manifest["inputs"] = {name: sha(ex / name) for name in ("calibration.csv", "release.csv", "config_reproducibility.yaml")}
    records, field_records, predictions, paired = [], [], [], []
    settings = [(1, e) for e in protocol["epsilon_total"]] + [(2, 5)]
    seeds = range(protocol["seeds"]["first"], protocol["seeds"]["first"] + protocol["seeds"]["count"])
    for width, epsilon in settings:
        bounded = replace(schema, public_bounds={n: (l, l + width * (u - l)) for n, (l, u) in schema.public_bounds.items()})
        privacy = replace(base, epsilon_total=float(epsilon), epsilon_numeric=.86 * epsilon,
                          epsilon_categorical=.14 * epsilon, categorical_budget_strategy="uniform")
        pipeline = RUPAPipeline(bounded, privacy, constraints, prior, adjacency, accounting).fit(calibration)
        fitted = pipeline.fitted_state_.allocation_result
        allocations = {"rupa": fitted, "uniform": uniform_numeric_allocation(bounded, fitted, privacy.delta)}
        for strategy, allocation in allocations.items():
            assert np.isclose(sum(allocation.epsilon.values()), epsilon)
            for field in bounded.numeric_columns:
                l, u = bounded.public_bounds[field]
                expected, probability = clipped_laplace_moments(release[field], l, u, allocation.epsilon[field])
                predictions.append({"width_multiplier": width, "epsilon": epsilon, "allocation": strategy, "field": field,
                                    "epsilon_field": allocation.epsilon[field], "noise_scale_over_public_width": 1 / allocation.epsilon[field],
                                    "reference_mean": float(release[field].mean()), "expected_clipped_mean": float(expected.mean()),
                                    "expected_boundary_fraction": float(probability.mean()),
                                    "ideal_unclipped_total_sd": float(np.sqrt(2 * len(release)) * (u - l) / allocation.epsilon[field])})
        for seed in seeds:
            for strategy, allocation in allocations.items():
                t = time.perf_counter()
                run_id = "num_w{0}_e{1}_{2}_s{3}".format(width, epsilon, strategy, seed)
                try:
                    noisy = perturb_release_data(release[bounded.released_columns], bounded, privacy, allocation, seed=seed)
                    if seed == seeds.start:
                        repeated = perturb_release_data(release[bounded.released_columns], bounded, privacy, allocation, seed=seed)
                        assert digest(repeated) == digest(noisy)
                    sources = [(strategy, noisy, allocation)]
                    if strategy == "uniform" and width == 1:
                        external = noisy.copy()
                        for j, name in enumerate(bounded.numeric_columns):
                            l, u = bounded.public_bounds[name]
                            mechanism = Laplace(epsilon=allocation.epsilon[name], delta=0, sensitivity=u - l,
                                                random_state=seed + 100000 + j)
                            external[name] = np.clip([mechanism.randomise(float(x)) for x in np.clip(release[name], l, u)], l, u)
                        sources.append(("diffprivlib_uniform", external, allocation))
                    for method, perturbed, allocated in sources:
                        for alpha in protocol["postprocessing_alpha"]:
                            variant_id = run_id.replace(strategy, method) + "_a" + str(alpha)
                            projected, interpolated, final, audit = apply_physical_projection(
                                release, perturbed, bounded, constraints, allocated, alpha)
                            metrics = numerical_metrics(release, final, bounded)
                            row = {"run_id": variant_id, "width_multiplier": width, "epsilon": epsilon, "method": method,
                                   "repair_alpha": alpha, "seed": seed, **metrics,
                                   "final_nrms": audit["states"]["final_clipped"]["nrms"],
                                   "violation_rate": audit["states"]["final_clipped"]["violation_rate"],
                                   "noisy_nrms": audit["states"]["noisy"]["nrms"],
                                   "projection_nrms": audit["states"]["full_projection"]["nrms"],
                                   "interpolated_nrms": audit["states"]["interpolated"]["nrms"],
                                   "elapsed_seconds": time.perf_counter() - t}
                            records.append(row)
                            record_config(args.output, variant_id, (bounded, replace(privacy, random_seed=seed, repair_alpha=alpha), constraints, prior, adjacency, accounting))
                            manifest["runs"].append({"run_id": variant_id, "allocation_adapter": method,
                                                     "noisy_digest": digest(perturbed), "final_digest": digest(final)})
                            if seed == seeds.start:
                                for name in bounded.numeric_columns:
                                    field_records.append({"run_id": variant_id, "field": name,
                                                          "reference_total": float(release[name].sum()), "released_total": float(final[name].sum()),
                                                          "epsilon": allocated.epsilon[name]})
                        if method == "rupa" and seed == seeds.start:
                            result = pipeline.transform(release, seed=seed)
                            assert digest(result.release_data[bounded.released_columns]) == digest(final)
                            pub = write_public_run(result, bounded, replace(privacy, random_seed=seed), constraints, prior, adjacency,
                                                   accounting, args.output / "public_runs", run_id=run_id)
                            validate_public_run(pub, bounded.sensitive_target)
                except Exception as exc:
                    manifest["failures"].append({"run_id": run_id, "error": str(exc), "traceback": traceback.format_exc()})
            if (seed - seeds.start + 1) % 10 == 0:
                print("numeric", width, epsilon, "seeds", seed - seeds.start + 1, "/30", flush=True)
        dump(args.output / "manifest.json", manifest)
    raw = pd.DataFrame(records)
    evaluation = args.output / "evaluation"
    evaluation.mkdir()
    raw.to_csv(evaluation / "raw_metrics.csv", index=False)
    pd.DataFrame(field_records).to_csv(evaluation / "first_seed_field_totals.csv", index=False)
    pd.DataFrame(predictions).to_csv(evaluation / "clipping_diagnostics.csv", index=False)
    metrics = ["median_field_total_error_percent", "cross_share_error_pp", "mae_range", "wasserstein_range", "mean_ks", "final_nrms", "boundary_fraction"]
    summary = raw.groupby(["width_multiplier", "epsilon", "method", "repair_alpha"])[metrics].agg(["median", lambda a: a.quantile(.1), lambda a: a.quantile(.9)])
    summary.columns = [a + "_" + ({"<lambda_0>": "p10", "<lambda_1>": "p90"}.get(b, b)) for a, b in summary.columns]
    summary.reset_index().to_csv(evaluation / "summary.csv", index=False)
    for width, epsilon in settings:
        frame = raw[(raw.width_multiplier == width) & (raw.epsilon == epsilon)]
        for alpha in protocol["postprocessing_alpha"]:
            a = frame[(frame.method == "rupa") & (frame.repair_alpha == alpha)].sort_values("seed")
            b = frame[(frame.method == "uniform") & (frame.repair_alpha == alpha)].sort_values("seed")
            if len(a) == len(b) == 30:
                for metric in metrics:
                    paired.append({"width_multiplier": width, "epsilon": epsilon, "repair_alpha": alpha, "metric": metric,
                                   **bootstrap_mean_difference(a[metric], b[metric])})
    pd.DataFrame(paired).to_csv(evaluation / "paired_rupa_minus_uniform.csv", index=False)
    fig, axes = plt.subplots(1, 3, figsize=(10, 3.3), layout="constrained")
    for method, color in (("uniform", "#536C7B"), ("rupa", "#167D8D"), ("diffprivlib_uniform", "#B87B28")):
        for alpha, style in ((0, "--"), (.98, "-")):
            group = raw[(raw.width_multiplier == 1) & (raw.method == method) & (raw.repair_alpha == alpha)]
            for ax, metric in zip(axes, metrics[:2] + ["final_nrms"]):
                med = group.groupby("epsilon")[metric].median()
                ax.plot(med.index, med, linestyle=style, marker="o", color=color, label=method + (" + post" if alpha else " no post"))
    for ax, label, letter in zip(axes, ("Median field-total error (%)", "Transfer-share error (pp)", "Final constraint NRMS"), "abc"):
        ax.set_xlabel("Total epsilon")
        ax.set_ylabel(label)
        ax.set_xticks([1, 5, 20])
        ax.spines[["top", "right"]].set_visible(False)
        ax.grid(axis="y", alpha=.2)
        ax.text(-.15, 1.04, letter, transform=ax.transAxes, weight="bold")
    axes[0].legend(fontsize=6, frameon=False)
    fig.savefig(args.output / "numeric_comparison.png", dpi=300)
    plt.close(fig)


def sample(args, protocol, manifest):
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    ex = ROOT / protocol["example"]
    calibration, release = (pd.read_csv(ex / name) for name in ("calibration.csv", "release.csv"))
    schema, base, constraints, prior, adjacency, accounting = load_pipeline_config(ex / "config_reproducibility.yaml")
    require_research_inputs(base)
    unit = adjacency.privacy_unit_id
    order = sorted(range(len(release)), key=lambda i: hashlib.sha256((str(release.iloc[i][unit]) + "review-size-20261021").encode()).digest())
    manifest["inputs"] = {n: sha(ex / n) for n in ("calibration.csv", "release.csv", "config_reproducibility.yaml")}
    records = []
    seeds = range(protocol["seeds"]["first"], protocol["seeds"]["first"] + protocol["seeds"]["count"])
    for epsilon in protocol["epsilon_total"]:
        privacy = replace(base, epsilon_total=float(epsilon), epsilon_categorical=float(epsilon), categorical_budget_strategy="uniform")
        fitted = RUPAPipeline(schema, privacy, constraints, prior, adjacency, accounting).fit(calibration)
        for size in protocol["sizes"]:
            subset = release.iloc[order[:size]].reset_index(drop=True)
            truth = {n: float(subset[n].eq("yes").mean()) for n in schema.categorical_columns}
            for seed in seeds:
                run_id = "size_n{0}_e{1}_s{2}".format(size, epsilon, seed)
                try:
                    t = time.perf_counter()
                    result = fitted.transform(subset, seed=seed)
                    errors, outside = [], 0
                    for name in schema.categorical_columns:
                        e = result.allocation_result.epsilon[name]
                        p = 1 / (1 + np.exp(-e))
                        q = 1 - p
                        estimate = (float(result.release_data[name].eq("yes").mean()) - q) / (p - q)
                        errors.append(100 * abs(estimate - truth[name]))
                        outside += int(estimate < 0 or estimate > 1)
                    records.append({"run_id": run_id, "rows": size, "epsilon": epsilon, "seed": seed,
                                    "max_marginal_error_pp": max(errors), "out_of_range_marginals": outside,
                                    "elapsed_seconds": time.perf_counter() - t})
                    record_config(args.output, run_id, (schema, replace(privacy, random_seed=seed), constraints, prior, adjacency, accounting))
                    manifest["runs"].append({"run_id": run_id, "subset_roster_digest": digest(subset[[unit]]),
                                             "release_digest": digest(result.release_data), "rows": size})
                    if seed == seeds.start:
                        pub = write_public_run(result, schema, replace(privacy, random_seed=seed), constraints, prior, adjacency,
                                               accounting, args.output / "public_runs", run_id=run_id)
                        validate_public_run(pub, schema.sensitive_target)
                except Exception as exc:
                    manifest["failures"].append({"run_id": run_id, "error": str(exc), "traceback": traceback.format_exc()})
            print("sample", epsilon, size, "completed 30 seeds", flush=True)
            dump(args.output / "manifest.json", manifest)
    raw = pd.DataFrame(records)
    (args.output / "evaluation").mkdir()
    raw.to_csv(args.output / "evaluation/raw_metrics.csv", index=False)
    summary = raw.groupby(["rows", "epsilon"]).agg(median_error_pp=("max_marginal_error_pp", "median"),
                p90_error_pp=("max_marginal_error_pp", lambda s: s.quantile(.9)),
                out_of_range_marginals=("out_of_range_marginals", "sum"), runs=("run_id", "count")).reset_index()
    summary.to_csv(args.output / "evaluation/summary.csv", index=False)
    fig, ax = plt.subplots(figsize=(5.7, 3.6), layout="constrained")
    for epsilon, color in ((1, "#AB6532"), (2, "#236C99"), (5, "#208470")):
        frame = summary[summary.epsilon == epsilon]
        ax.plot(frame.rows, frame.median_error_pp, marker="o", color=color, label="epsilon " + str(epsilon))
        ax.plot(frame.rows, frame.p90_error_pp, linestyle="--", color=color)
    ax.set_xscale("log")
    ax.set_xlabel("Evaluation rows (nested public-key subsets)")
    ax.set_ylabel("Maximum marginal absolute error (pp)")
    ax.spines[["top", "right"]].set_visible(False)
    ax.grid(axis="y", alpha=.2)
    ax.legend(frameon=False)
    fig.savefig(args.output / "sample_size_sensitivity.png", dpi=300)
    plt.close(fig)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--section", choices=("numeric", "sample"), required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--pytest-xml", type=Path, required=True)
    args = parser.parse_args()
    args.output = args.output.resolve()
    manifest = start_run(args)
    protocol = json.loads((HERE / "protocol.json").read_text(encoding="utf-8"))
    started = time.perf_counter()
    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always")
        try:
            key = "sample_size" if args.section == "sample" else "numeric"
            {"numeric": numeric, "sample": sample}[args.section](args, protocol[key], manifest)
        except Exception as exc:
            manifest["failures"].append({"stage": "driver", "error": str(exc), "traceback": traceback.format_exc()})
            manifest["status"] = "FAIL"
            dump(args.output / "manifest.json", manifest)
            raise
    manifest["warnings"] = sorted(set(str(w.message) for w in caught))
    manifest["elapsed_seconds"] = time.perf_counter() - started
    manifest["core_after"] = core_hashes()
    manifest["core_unchanged"] = manifest["core_before"] == manifest["core_after"]
    expected = 660 if args.section == "numeric" else 450
    manifest["expected_runs"] = expected
    manifest["status"] = "PASS" if not manifest["failures"] and manifest["core_unchanged"] and len(manifest["runs"]) == expected else "FAIL"
    dump(args.output / "manifest.json", manifest)
    print(manifest["status"], "runs", len(manifest["runs"]), "failures", len(manifest["failures"]), flush=True)
    if manifest["status"] != "PASS":
        raise SystemExit(1)


if __name__ == "__main__":
    main()
