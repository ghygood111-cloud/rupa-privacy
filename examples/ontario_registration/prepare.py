"""Prepare an attributed public registration benchmark, not confidential data."""
import hashlib
import json
from pathlib import Path
from urllib.request import urlopen

import pandas as pd
import yaml

HERE = Path(__file__).resolve().parent
CATALOGUE_API = (
    "https://data.ontario.ca/api/3/action/package_show"
    "?id=hazardous-waste-public-information"
)
SOURCE_URL = (
    "https://files.ontario.ca/moe_mapping/downloads/3Land/HWIN_by_year/"
    "2002-2022_Waste_Generator_Registration-Numbers_Classes_Database.csv"
)
EXPECTED_SOURCE_SHA256 = "d9da99e6f4c6e7227290ef74b68646f4d12e9471a1bbdffa1b6b30caf9bd771d"
FIELDS = ["handles_liquid", "handles_solid"]
TARGET = "registered_class_count"
UNIT = "public_registration_id"


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def prepare_frame(source):
    """Aggregate first, then split whole registration units deterministically."""
    source = source.copy()
    identifiers = source["GENERATOR_NUMBER"].fillna("").astype(str).str.strip()
    valid = identifiers.ne("")
    source = source.loc[valid].copy()
    source["GENERATOR_NUMBER"] = identifiers.loc[valid]
    state = source["PHYSICAL_STATE"].fillna("").astype(str).str.strip().str.lower()
    source["liquid_flag"] = state.eq("liquid")
    source["solid_flag"] = state.eq("solid")
    grouped = source.groupby("GENERATOR_NUMBER", sort=True)
    frame = grouped[["liquid_flag", "solid_flag"]].any()
    frame[TARGET] = grouped["WASTE_CLASS_CODE"].nunique(dropna=True)
    frame[UNIT] = ["ONT-{0:08d}".format(i) for i in range(len(frame))]
    frame["handles_liquid"] = frame.liquid_flag.map({False: "no", True: "yes"})
    frame["handles_solid"] = frame.solid_flag.map({False: "no", True: "yes"})
    calibration_mask = [
        int(hashlib.sha256(str(value).encode("utf-8")).hexdigest(), 16) % 5 == 0
        for value in frame.index
    ]
    calibration = frame.loc[calibration_mask, [UNIT] + FIELDS + [TARGET]].reset_index(drop=True)
    release = frame.loc[[not value for value in calibration_mask], [UNIT] + FIELDS].reset_index(drop=True)
    if set(calibration[UNIT]) & set(release[UNIT]):
        raise AssertionError("Calibration/release registration overlap")
    if calibration[TARGET].nunique() < 2:
        raise ValueError("Public calibration complexity proxy is degenerate")
    diagnostics = {
        "source_rows": int(len(identifiers)),
        "missing_registration_rows_excluded": int((~valid).sum()),
        "registration_units": int(len(frame)),
        "calibration_rows": int(len(calibration)),
        "release_rows": int(len(release)),
        "source_physical_state_row_counts": state.value_counts(dropna=False).to_dict(),
        "unit_overlap": 0,
    }
    return calibration, release, diagnostics


def config():
    return {
        "schema": {
            "sensitive_target": TARGET,
            "numeric_columns": [],
            "categorical_columns": FIELDS,
            "excluded_columns": [UNIT, TARGET],
            "released_columns": FIELDS,
            "public_bounds": {},
            "public_categories": {name: ["no", "yes"] for name in FIELDS},
        },
        "privacy": {
            "epsilon_total": 2.0, "epsilon_numeric": 0.0, "epsilon_categorical": 2.0,
            "delta": 0.00001, "utility_alpha": 0.6, "repair_alpha": 0.0,
            "randomness_mode": "reproducibility", "random_seed": 20262000,
            "calibration_mode": "public", "calibration_public_confirmed": True,
            "calibration_source": "Public Ontario historical registration partition; provenance.json",
            "release_data_mode": "public_demonstration", "release_public_confirmed": True,
            "release_source": "Public Ontario historical registration partition; provenance.json",
            "categorical_mode": "randomized_response", "categorical_budget_strategy": "uniform",
            "categorical_risk_smoothing": 0.05,
            "nmi_bins": 10, "joint_bins": 5, "joint_nmi_diagnostic": False,
            "knee_grid_points": 21,
        },
        "regulatory_prior": {name: 0.5 for name in FIELDS},
        "constraints": [],
        "adjacency": {
            "type": "fixed_roster_replace_one", "privacy_unit_id": UNIT,
            "roster_is_public": True, "one_row_per_unit": True,
        },
        "privacy_accounting": {
            "dataset_id": "ontario_public_registration_coverage_2002_2022",
            "maximum_cumulative_epsilon": 10.0, "ledger_path": "privacy_ledger.sqlite3",
        },
    }


def main():
    cache = HERE / "_source_cache"
    cache.mkdir(exist_ok=True)
    source = cache / "registration_source.csv"
    if not source.exists():
        print("Downloading the official public CSV...", flush=True)
        part = cache / "registration_source.csv.part"
        with urlopen(SOURCE_URL, timeout=90) as response, part.open("wb") as destination:
            if response.status != 200:
                raise RuntimeError("Expected full source download, got HTTP " + str(response.status))
            while True:
                chunk = response.read(1024 * 1024)
                if not chunk:
                    break
                destination.write(chunk)
        if part.stat().st_size < 10_000_000:
            raise RuntimeError("Unexpectedly small source; refusing a partial benchmark")
        part.replace(source)
    print("Source bytes:", source.stat().st_size, "SHA256:", sha(source), flush=True)
    if sha(source) != EXPECTED_SOURCE_SHA256:
        raise RuntimeError("Upstream source differs from the evaluated snapshot; review before regenerating inputs")
    with urlopen(CATALOGUE_API, timeout=40) as response:
        metadata_bytes = response.read()
    metadata = json.loads(metadata_bytes)["result"]
    if metadata["license_id"] != "OGL-ON-1.0":
        raise RuntimeError("Source licence differs from the documented licence")
    (cache / "catalogue_metadata.json").write_bytes(metadata_bytes)
    encoding = "utf-8-sig"
    columns = ["GENERATOR_NUMBER", "WASTE_CLASS_CODE", "PHYSICAL_STATE"]
    try:
        raw = pd.read_csv(source, usecols=columns, dtype=str, encoding=encoding)
    except UnicodeDecodeError:
        encoding = "latin1"
        raw = pd.read_csv(source, usecols=columns, dtype=str, encoding=encoding)
    calibration, release, diagnostics = prepare_frame(raw)
    calibration.to_csv(HERE / "calibration.csv", index=False)
    release.to_csv(HERE / "release.csv", index=False)
    (HERE / "config_reproducibility.yaml").write_text(
        yaml.safe_dump(config(), sort_keys=False), encoding="utf-8"
    )
    provenance = {
        "source_url": SOURCE_URL, "catalogue_api": CATALOGUE_API,
        "source_resource": "2002-2022 Generator Registration and Waste Classes",
        "publisher": "Ontario Ministry of the Environment, Conservation and Parks",
        "accessed_date": "2026-10-20", "license_id": metadata["license_id"],
        "license_url": metadata["license_url"],
        "attribution": "Contains information licensed under the Open Government Licence - Ontario.",
        "source_sha256": sha(source), "source_bytes": source.stat().st_size,
        "catalogue_metadata_sha256": sha(cache / "catalogue_metadata.json"),
        "source_encoding": encoding, "source_columns_read": columns,
        "derivation": "Any physical-state occurrence per literal registration; no waste-mass inference. Distinct class count used only as a public calibration proxy.",
        "public_roster_key": "ONT- plus zero-padded ordinal in lexical registration order; no identity-hiding claim.",
        "split": "SHA256(trimmed literal registration number) as integer modulo 5: 0 calibration; other residues release.",
        "public_domains": {name: ["no", "yes"] for name in FIELDS},
        "priority_note": "Equal analyst-selected coverage priorities, not official regulatory weights.",
        "physical_constraints": "None: categorical coverage has no numerical equality task.",
        "data_status": "Already public; historical combined inventory, not an annual/current census or confidential deployment.",
        "diagnostics": diagnostics,
        "prepared_sha256": {name: sha(HERE / name) for name in
                            ["calibration.csv", "release.csv", "config_reproducibility.yaml"]},
    }
    (HERE / "provenance.json").write_text(json.dumps(provenance, indent=2), encoding="utf-8")
    print(json.dumps(diagnostics, indent=2), flush=True)


if __name__ == "__main__":
    main()
