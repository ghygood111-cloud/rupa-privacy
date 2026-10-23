"""Four output-object paths at equal numerical privacy budget; research only."""
import argparse
from dataclasses import replace
import hashlib
import importlib.metadata
import json
from pathlib import Path
import platform
import time
import traceback
import xml.etree.ElementTree as ET

import numpy as np
import pandas as pd

from rupa_privacy import RUPAPipeline
from rupa_privacy.io import load_pipeline_config
from rupa_privacy.models import DataSchema, PrivacyConfig, AdjacencyConfig, PrivacyAccountingConfig
from rupa_privacy.physics.reconstruction import reconstruct_from_protected_views
from rupa_privacy.research import prepare_statistics, allocate_statistics, draw_statistics
from examples.hazardous_waste.generate_data import generate_enterprise_year
from examples.water_treatment.generate_data import generate_water_treatment
from .metrics import aggregate_metrics, evaluate_rows

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
PREVIOUS = HERE.parent / "task_statistics_20261022"


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def core_hashes():
    return {p.relative_to(ROOT).as_posix(): sha(p) for p in sorted((ROOT / "src/rupa_privacy").rglob("*.py"))}


def dump(path, value):
    Path(path).write_text(json.dumps(value, indent=2, ensure_ascii=False, allow_nan=False), encoding="utf-8")


def cases():
    protocol = json.loads((PREVIOUS / "protocol.json").read_text())
    for case in protocol["synthetic_cases"]:
        settings = load_pipeline_config(ROOT / "examples" / case / "config_reproducibility.yaml")
        counts = (240, 320) if case == "hazardous_waste" else (1500, 2000)
        generator = generate_enterprise_year if case == "hazardous_waste" else generate_water_treatment
        for pair in range(protocol["independent_generated_pairs_per_case"]):
            seed = protocol["calibration_seed_first"] + 1000 * (case == "water_treatment") + 2 * pair
            name = case + "_pair" + str(pair)
            calibration = generator(counts[0], seed, name + "_CAL-")
            release = generator(counts[1], seed + 1, name + "_REL-").drop(columns=[settings[0].sensitive_target])
            yield name, case, calibration, release, settings
    external = json.loads((PREVIOUS / "external/schema.json").read_text())
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
        source = PREVIOUS / "external" / ("block_" + str(block))
        yield "uci_concrete_block" + str(block), "uci_concrete", pd.read_csv(source / "calibration.csv"), pd.read_csv(source / "release.csv"), settings


def numerical_settings(settings):
    schema, privacy, constraints, prior, adjacency, accounting = settings
    names = schema.numeric_columns
    numeric_schema = DataSchema(schema.sensitive_target, names, [], public_bounds={n: schema.public_bounds[n] for n in names})
    total_prior = sum(prior[n] for n in names)
    numeric_prior = {n: prior[n] / total_prior for n in names}
    base = replace(privacy, epsilon_total=5, epsilon_numeric=5, epsilon_categorical=0,
        numeric_budget_strategy="uniform", categorical_budget_strategy="uniform")
    return numeric_schema, base, constraints, numeric_prior, adjacency, accounting


def feasible_totals(prepared, noisy, lower, upper):
    """Use the existing postprocessor with public constant rows, discarding rows."""
    n = prepared["rows"]
    public_rows = np.tile((lower + upper) / 2, (n, 1))
    _, diagnostics = reconstruct_from_protected_views(public_rows, noisy, lower, upper,
        prepared["matrix"], prepared["rhs"] / n)
    return np.asarray(diagnostics["projected_total_target"])


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--pytest-xml", type=Path, required=True)
    args = parser.parse_args()
    gate = ET.parse(args.pytest_xml)
    if (len(list(gate.iter("testcase"))) < 413 or list(gate.iter("failure")) or list(gate.iter("error"))
            or time.time() - args.pytest_xml.stat().st_mtime > 86400):
        raise ValueError("Fresh full passing pytest gate required")
    out = args.output.resolve()
    out.mkdir(parents=True, exist_ok=False)
    (out / "inputs").mkdir()
    protocol = json.loads((HERE / "protocol.json").read_text())
    before = core_hashes()
    manifest = {"protocol": protocol, "protocol_sha256": sha(HERE / "protocol.json"),
        "input_protocol_sha256": sha(PREVIOUS / "protocol.json"), "core_before": before,
        "source_sha256": {n: sha(HERE / n) for n in ["run.py", "metrics.py"]},
        "python": platform.python_version(), "platform": platform.platform(),
        "dependencies": {n: importlib.metadata.version(n) for n in ["numpy", "scipy", "pandas", "scikit-learn", "diffprivlib"]},
        "pytest_sha256": sha(args.pytest_xml), "datasets": [], "failures": [], "completed_seed_bundles": 0,
        "randomness_mode": "reproducibility", "production_authorized": False}
    raw, fields, pairs, budgets, recon_records = [], [], [], [], []
    started = time.perf_counter()
    for dataset, case, calibration, release, original_settings in cases():
        dataset_start = time.perf_counter()
        try:
            settings = numerical_settings(original_settings)
            schema, privacy, constraints, prior, adjacency, accounting = settings
            input_dir = out / "inputs" / dataset
            input_dir.mkdir()
            calibration.to_csv(input_dir / "calibration.csv", index=False)
            release.to_csv(input_dir / "release.csv", index=False)
            dump(input_dir / "settings.json", {"schema": schema.to_dict(), "privacy": privacy.to_dict(),
                "constraints": [c.to_dict() for c in constraints], "regulatory_prior": prior,
                "adjacency": adjacency.to_dict(), "accounting": accounting.to_dict()})
            prepared = prepare_statistics(calibration, release, settings)
            full = RUPAPipeline(schema, privacy, constraints, prior, adjacency, accounting).fit(calibration)
            half = RUPAPipeline(schema, replace(privacy, epsilon_total=2.5, epsilon_numeric=2.5, repair_alpha=0),
                constraints, prior, adjacency, accounting).fit(calibration)
            names = schema.numeric_columns
            original = release[names].to_numpy(float)
            lower = np.array([schema.public_bounds[n][0] for n in names])
            upper = lower + prepared["delta"]
            allocation = {(part, strategy): allocate_statistics(prepared, part, strategy)[0]
                for part in (2.5, 5.0) for strategy in protocol["allocations"]}
            manifest["datasets"].append({"dataset": dataset, "case": case,
                "calibration_rows": len(calibration), "release_rows": len(release), "fields": len(names),
                "calibration_sha256": sha(input_dir / "calibration.csv"), "release_sha256": sha(input_dir / "release.csv"),
                "input_clipping_fraction": prepared["clipped_input_fraction"]})
            for seed in range(protocol["seeds"]["first"], protocol["seeds"]["first"] + protocol["seeds"]["count"]):
                context = {"dataset": dataset, "case": case, "seed": seed}

                def record(path, strategy, stage, values, kind, row_epsilon, total_epsilon):
                    run_id = "{0}_{1}_{2}_{3}_s{4}".format(dataset, path, strategy, stage, seed)
                    metadata = dict(context, run_id=run_id, path=path, strategy=strategy, stage=stage,
                        output_kind=kind, row_epsilon=row_epsilon, total_query_epsilon=total_epsilon,
                        composed_epsilon=row_epsilon + total_epsilon)
                    if not np.isclose(metadata["composed_epsilon"], 5):
                        raise ValueError("Ablation composition must equal five")
                    if kind == "rows":
                        metrics, by_field, by_pair = evaluate_rows(values, original, prepared, constraints)
                        fields.extend(dict(metadata, **r) for r in by_field)
                        pairs.extend(dict(metadata, **r) for r in by_pair)
                    else:
                        metrics = aggregate_metrics(values, original, prepared)
                    raw.append(dict(metadata, **metrics))

                row_full, row_half = full.transform(release, seed=seed), half.transform(release, seed=seed)
                assert row_full.release_data.columns.tolist() == [adjacency.privacy_unit_id] + names
                assert row_half.release_data[adjacency.privacy_unit_id].tolist() == release[adjacency.privacy_unit_id].tolist()
                assert schema.sensitive_target not in row_full.release_data
                record("B", "uniform_rows", "clipped_noisy", row_full.noisy_data[names].to_numpy(float), "rows", 5, 0)
                record("B", "uniform_rows", "default_repair", row_full.release_data[names].to_numpy(float), "rows", 5, 0)
                for strategy in protocol["allocations"]:
                    for part in (5.0, 2.5):
                        vector = allocation[part, strategy]
                        protected = draw_statistics(prepared, vector, seed + protocol["seeds"]["aggregate_offset"])
                        feasible = feasible_totals(prepared, protected["noisy"], lower, upper)
                        path, row_e = ("A", 0) if part == 5 else ("C", 2.5)
                        record(path, strategy, "raw_totals", protected["noisy"], "totals", row_e, part)
                        record(path, strategy, "feasible_totals", feasible, "totals", row_e, part)
                        if part == 2.5:
                            noisy_rows = row_half.noisy_data[names].to_numpy(float)
                            record("C", strategy, "clipped_noisy", noisy_rows, "rows", 2.5, 2.5)
                            reconstructed, diagnostic = reconstruct_from_protected_views(noisy_rows, protected["noisy"], lower, upper,
                                prepared["matrix"], prepared["rhs"] / len(release))
                            mismatch = float(np.max(abs(reconstructed.sum(axis=0) - feasible) / (len(release) * prepared["delta"])))
                            if mismatch > 1e-10:
                                raise ValueError("Reconstructed sums differ from the existing aggregate target")
                            record("D", strategy, "reconstructed", reconstructed, "rows", 2.5, 2.5)
                            recon_records.append(dict(context, strategy=strategy, maximum_normalized_target_mismatch=mismatch, **diagnostic))
                        if seed == protocol["seeds"]["first"]:
                            for j, name in enumerate(names):
                                budgets.append(dict(dataset=dataset, path=path, strategy=strategy, field=name,
                                    row_epsilon=row_e / len(names), total_epsilon=float(vector[j]), composed_total=5))
                manifest["completed_seed_bundles"] += 1
        except Exception as exc:
            manifest["failures"].append({"dataset": dataset, "error": str(exc), "traceback": traceback.format_exc()})
        print(dataset, "bundles", manifest["completed_seed_bundles"], "failures", len(manifest["failures"]),
              "seconds", round(time.perf_counter() - dataset_start, 2), flush=True)
        dump(out / "manifest.json", manifest)
    pd.DataFrame(raw).to_csv(out / "raw_metrics.csv", index=False)
    pd.DataFrame(fields).to_csv(out / "field_metrics.csv", index=False)
    pd.DataFrame(pairs).to_csv(out / "correlation_metrics.csv", index=False)
    pd.DataFrame(budgets).to_csv(out / "field_budgets.csv", index=False)
    dump(out / "reconstruction_diagnostics.json", recon_records)
    manifest.update(core_after=core_hashes(), elapsed_seconds=time.perf_counter() - started,
        evaluated_output_states=len(raw), expected_output_states=25 * 30 * 14, expected_seed_bundles=750)
    manifest["status"] = "PASS" if (manifest["completed_seed_bundles"] == 750 and len(raw) == 10500
        and not manifest["failures"] and before == manifest["core_after"]) else "FAIL"
    dump(out / "manifest.json", manifest)
    print(manifest["status"], len(raw), "evaluated output states", flush=True)
    if manifest["status"] != "PASS":
        raise SystemExit(1)


if __name__ == "__main__":
    main()
