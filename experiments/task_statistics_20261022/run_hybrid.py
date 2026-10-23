"""Equal-total-budget row-table comparison of protected-view reconstruction."""
import argparse
from dataclasses import replace
from pathlib import Path
import time
import traceback
import xml.etree.ElementTree as ET
import json

import numpy as np
import pandas as pd

from rupa_privacy import RUPAPipeline
from rupa_privacy.physics.projection import build_constraint_system
from rupa_privacy.physics.reconstruction import reconstruct_from_protected_views
from experiments.review_revision_20261021.run import dump, sha, core_hashes
from .run import cases
from .study import prepare_statistics, allocate, draw_statistics, stage_metrics

HERE = Path(__file__).resolve().parent


def evaluate(prepared, released, source, names):
    values = released[names].to_numpy(float)
    metrics = stage_metrics(prepared, values.sum(axis=0))
    ranges = prepared["delta"]
    original = source[names].to_numpy(float)
    metrics["row_mae_range"] = float(np.mean(abs(values - original) / ranges))
    true_sd, sd = original.std(axis=0), values.std(axis=0)
    defined = true_sd > 1e-12
    metrics["median_standard_deviation_ratio"] = float(np.median(sd[defined] / true_sd[defined]))
    metrics["undefined_standard_deviation_fields"] = int(np.sum(~defined))
    raw_sum = prepared["raw_input_total"]
    metrics["raw_reference_mean_relative_error_percent"] = float(np.mean(100 * abs(values.sum(axis=0) - raw_sum) / np.maximum(abs(raw_sum), 1e-12)))
    residual = values @ prepared["matrix"].T - prepared["rhs"] / prepared["rows"]
    metrics["maximum_row_equality_residual"] = float(np.max(abs(residual))) if residual.size else 0.0
    return metrics, sd / np.maximum(true_sd, 1e-12)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--pytest-xml", type=Path, required=True)
    args = parser.parse_args()
    gate = ET.parse(args.pytest_xml)
    if len(list(gate.iter("testcase"))) < 397 or list(gate.iter("failure")) or list(gate.iter("error")):
        raise ValueError("Fresh full passing regression gate required")
    if time.time() - args.pytest_xml.stat().st_mtime > 86400:
        raise ValueError("Test gate expired")
    out = args.output.resolve()
    out.mkdir(parents=True, exist_ok=False)
    public = out / "public_runs"
    public.mkdir()
    protocol = json.loads((HERE / "hybrid_protocol.json").read_text())
    generator_protocol = json.loads((HERE / "protocol.json").read_text())
    manifest = {"protocol_sha256": sha(HERE / "hybrid_protocol.json"), "core_before": core_hashes(),
        "driver_sha256": sha(__file__), "pytest_sha256": sha(args.pytest_xml), "randomness_mode": "reproducibility",
        "production_supported": False, "failures": [], "runs": [], "datasets": []}
    rows, field_records = [], []
    started = time.perf_counter()
    for dataset, case, evidence, calibration, release, settings in cases(generator_protocol, out):
        schema, base, constraints, prior, adjacency, accounting = settings
        try:
            prepared = prepare_statistics(calibration, release, settings)
            numeric_fraction = base.epsilon_numeric / base.epsilon_total
            epsilon_numeric = 5 * numeric_fraction
            epsilon_categories = 5 - epsilon_numeric
            row_part = epsilon_numeric * (1 - protocol["hybrid_total_view_fraction_of_numeric_budget"])
            total_part = epsilon_numeric - row_part
            full_privacy = replace(base, epsilon_total=5, epsilon_numeric=epsilon_numeric,
                epsilon_categorical=epsilon_categories, numeric_budget_strategy="uniform", categorical_budget_strategy="uniform")
            partial_privacy = replace(full_privacy, epsilon_total=row_part + epsilon_categories,
                epsilon_numeric=row_part, repair_alpha=0)
            full = RUPAPipeline(schema, full_privacy, constraints, prior, adjacency, accounting).fit(calibration)
            partial = RUPAPipeline(schema, partial_privacy, constraints, prior, adjacency, accounting).fit(calibration)
            manifest["datasets"].append({"dataset": dataset, "case": case, "calibration_rows": len(calibration),
                "release_rows": len(release), "row_epsilon": row_part, "total_epsilon": total_part,
                "category_epsilon": epsilon_categories, "total": row_part + total_part + epsilon_categories})
            matrix, rhs = build_constraint_system(schema, constraints)
            for seed in range(protocol["seeds"]["first"], protocol["seeds"]["first"] + protocol["seeds"]["count"]):
                baseline = full.transform(release, seed=seed)
                row_view = partial.transform(release, seed=seed)
                for strategy in protocol["strategies"]:
                    run_id = "{0}_{1}_s{2}".format(dataset, strategy, seed)
                    try:
                        if strategy == "uniform_row_projection":
                            frame = baseline.release_data
                            diagnostics = {"composed_epsilon": baseline.allocation_result.basic_composition_epsilon}
                        else:
                            query_strategy = "uniform_statistics" if strategy == "hybrid_uniform" else "workload_rupa"
                            epsilon, _ = allocate(prepared, total_part, query_strategy)
                            protected = draw_statistics(prepared, epsilon, seed + protocol["seeds"]["aggregate_seed_offset"])
                            lower = np.array([schema.public_bounds[name][0] for name in schema.numeric_columns])
                            upper = np.array([schema.public_bounds[name][1] for name in schema.numeric_columns])
                            values, diagnostics = reconstruct_from_protected_views(
                                row_view.noisy_data[schema.numeric_columns].to_numpy(float), protected["noisy"],
                                lower, upper, matrix, rhs)
                            frame = row_view.release_data.copy()
                            frame.loc[:, schema.numeric_columns] = values
                            diagnostics["composed_epsilon"] = row_view.allocation_result.basic_composition_epsilon + epsilon.sum()
                        if not np.isclose(diagnostics["composed_epsilon"], 5, rtol=1e-10, atol=1e-12):
                            raise ValueError("Joint-view privacy budget mismatch")
                        assert frame.columns.tolist() == [adjacency.privacy_unit_id] + schema.released_columns
                        assert schema.sensitive_target not in frame.columns
                        metrics, ratios = evaluate(prepared, frame, release, schema.numeric_columns)
                        rows.append(dict(run_id=run_id, dataset=dataset, case=case, strategy=strategy, seed=seed, **metrics))
                        for name, ratio in zip(schema.numeric_columns, ratios):
                            field_records.append(dict(run_id=run_id, field=name, released_original_std_ratio=float(ratio)))
                        if seed == protocol["seeds"]["first"]:
                            file = public / (run_id + ".csv")
                            frame.to_csv(file, index=False)
                            dump(public / (run_id + ".json"), {"run_id": run_id, "epsilon_total": 5,
                                "row_epsilon": epsilon_numeric if strategy == "uniform_row_projection" else row_part,
                                "total_query_epsilon": 0 if strategy == "uniform_row_projection" else total_part,
                                "category_epsilon": epsilon_categories, "data_sha256": sha(file),
                                "mode": "research-only synthetic/public", "postprocessing": diagnostics})
                        manifest["runs"].append({"run_id": run_id, "epsilon_composition": float(diagnostics["composed_epsilon"])})
                    except Exception as exc:
                        manifest["failures"].append({"run_id": run_id, "error": str(exc), "traceback": traceback.format_exc()})
        except Exception as exc:
            manifest["failures"].append({"dataset": dataset, "error": str(exc), "traceback": traceback.format_exc()})
        dump(out / "manifest.json", manifest)
        print(dataset, "completed", len(manifest["runs"]), "failures", len(manifest["failures"]), flush=True)
    raw = pd.DataFrame(rows)
    raw.to_csv(out / "raw_metrics.csv", index=False)
    pd.DataFrame(field_records).to_csv(out / "field_variance.csv", index=False)
    metrics = [name for name in raw.columns if name not in {"run_id", "dataset", "case", "strategy", "seed"}]
    raw.groupby(["dataset", "case", "strategy"])[metrics].agg(["mean", "median", "min", "max"]).to_csv(out / "summary.csv")
    manifest.update(core_after=core_hashes(), elapsed_seconds=time.perf_counter() - started)
    manifest["expected_runs"] = 25 * 30 * 3
    manifest["status"] = "PASS" if len(manifest["runs"]) == manifest["expected_runs"] and not manifest["failures"] and manifest["core_before"] == manifest["core_after"] else "FAIL"
    dump(out / "manifest.json", manifest)
    print(manifest["status"], "runs", len(manifest["runs"]), "failures", len(manifest["failures"]), flush=True)
    if manifest["status"] != "PASS":
        raise SystemExit(1)


if __name__ == "__main__":
    main()
