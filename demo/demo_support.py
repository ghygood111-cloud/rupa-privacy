"""Non-visual helpers for the local RUPA Streamlit demonstration."""

from __future__ import annotations

import hashlib
import io
import json
import time
import zipfile
from copy import deepcopy
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Dict, Iterable, List, Mapping, Optional, Tuple

import numpy as np
import pandas as pd
import yaml

from rupa_privacy.exceptions import ConfigurationError, PrivacySafetyError
from rupa_privacy.io import load_table
from rupa_privacy.io.run import create_run_id, validate_public_run, write_public_run
from rupa_privacy.models import (
    AdjacencyConfig,
    DataSchema,
    PhysicalConstraint,
    PrivacyAccountingConfig,
    PrivacyConfig,
)
from rupa_privacy.physics.validation import validate_physical_constraints
from rupa_privacy.pipeline import RUPAPipeline
from rupa_privacy.validation import validate_calibration_data, validate_release_data
from resource_paths import resource_path, resource_root, user_data_root


PROJECT_ROOT = resource_root()
DEMO_ROOT = resource_path("demo")
RUNS_ROOT = user_data_root() / "runs"
WORKSPACE_ROOT = user_data_root() / "workspace"

EXAMPLE_PATHS = {
    "official": {
        "name": "Official synthetic example",
        "calibration": resource_path("examples/official/calibration.csv"),
        "release": resource_path("examples/official/release.csv"),
        "config": resource_path("examples/official/config.yaml"),
    },
    "water": {
        "name": "Water-treatment semi-synthetic example",
        "calibration": resource_path("examples/water_treatment/calibration.csv"),
        "release": resource_path("examples/water_treatment/release.csv"),
        "config": resource_path("examples/water_treatment/config_reproducibility.yaml"),
    },
    "hazardous_waste": {
        "name": "Hazardous-waste synthetic enterprise-year example",
        "calibration": resource_path("examples/hazardous_waste/calibration.csv"),
        "release": resource_path("examples/hazardous_waste/release.csv"),
        "config": resource_path("examples/hazardous_waste/config_reproducibility.yaml"),
    },
}


@dataclass
class DemoRun:
    run_id: str
    run_directory: Path
    inspection: dict
    result: object
    schema: DataSchema
    privacy: PrivacyConfig
    constraints: List[PhysicalConstraint]
    adjacency: AdjacencyConfig
    accounting: PrivacyAccountingConfig
    runtime_seconds: float


PUBLIC_CSV_ARTIFACTS = {
    "release_data.csv",
    "risk_scores.csv",
    "joint_risk.csv",
    "utility_weights.csv",
    "epsilon_allocation.csv",
}

PUBLIC_JSON_ARTIFACTS = {
    "metadata.json",
    "privacy_metrics.json",
    "physical_metrics.json",
    "utility_metrics.json",
    "attack_metrics.json",
    "governance_metrics.json",
    "run_config.json",
}

FORBIDDEN_PUBLIC_NAMES = {
    ".internal_audit",
    "calibration_data.csv",
    "raw_data.csv",
    "original_data.csv",
    "noisy_data.csv",
    "projected_data.csv",
    "repaired_internal.csv",
}


def load_yaml(path: Path) -> dict:
    with Path(path).open("r", encoding="utf-8") as handle:
        values = yaml.safe_load(handle)
    if not isinstance(values, dict):
        raise ConfigurationError("Configuration root must be a mapping")
    return values


def write_yaml(path: Path, values: Mapping) -> Path:
    destination = Path(path)
    destination.parent.mkdir(parents=True, exist_ok=True)
    with destination.open("w", encoding="utf-8") as handle:
        yaml.safe_dump(dict(values), handle, sort_keys=False, allow_unicode=True)
    return destination


def load_example(key: str) -> dict:
    if key not in EXAMPLE_PATHS:
        raise ConfigurationError("Unknown demonstration example: " + str(key))
    paths = EXAMPLE_PATHS[key]
    missing = [str(path) for name, path in paths.items() if name != "name" and not path.is_file()]
    if missing:
        raise ConfigurationError("Example files are missing: " + ", ".join(missing))
    return {
        "name": paths["name"],
        "calibration_path": paths["calibration"],
        "release_path": paths["release"],
        "config_path": paths["config"],
        "calibration": load_table(paths["calibration"]),
        "release": load_table(paths["release"]),
        "config": load_yaml(paths["config"]),
        "source": key,
    }


def objects_from_config(values: Mapping):
    try:
        schema = DataSchema.from_dict(values["schema"])
        privacy = PrivacyConfig.from_dict(values["privacy"])
        constraints = [
            PhysicalConstraint.from_dict(item) for item in values.get("constraints", [])
        ]
        prior = {
            str(name): float(weight)
            for name, weight in values["regulatory_prior"].items()
        }
        adjacency = AdjacencyConfig.from_dict(values["adjacency"])
        accounting = PrivacyAccountingConfig.from_dict(values["privacy_accounting"])
    except (KeyError, TypeError, ValueError) as exc:
        raise ConfigurationError("Configuration contains invalid field values") from exc
    return schema, privacy, constraints, prior, adjacency, accounting


def blank_config(columns: Iterable[str]) -> dict:
    """Create a deliberately incomplete manual template without private-domain inference."""
    return {
        "schema": {
            "sensitive_target": "",
            "numeric_columns": [],
            "categorical_columns": [],
            "excluded_columns": list(columns),
            "released_columns": [],
            "public_bounds": {},
            "public_categories": {},
        },
        "privacy": {
            "epsilon_total": 5.0,
            "epsilon_numeric": 4.5,
            "epsilon_categorical": 0.5,
            "delta": 0.00001,
            "utility_alpha": 0.6,
            "repair_alpha": 0.98,
            "randomness_mode": "reproducibility",
            "random_seed": 123,
            "calibration_mode": "public",
            "calibration_source": "",
            "calibration_public_confirmed": False,
            "release_data_mode": "public_demonstration",
            "release_source": "",
            "release_public_confirmed": False,
            "categorical_mode": "randomized_response",
            "categorical_budget_strategy": "heuristic_risk_utility",
            "categorical_risk_smoothing": 0.05,
            "nmi_bins": 10,
            "joint_bins": 5,
            "joint_nmi_diagnostic": True,
            "knee_grid_points": 21,
        },
        "adjacency": {
            "type": "fixed_roster_replace_one",
            "privacy_unit_id": "",
            "roster_is_public": True,
            "one_row_per_unit": True,
        },
        "privacy_accounting": {
            "dataset_id": "local_demo_dataset",
            "maximum_cumulative_epsilon": 10.0,
            "ledger_path": "privacy_ledger.sqlite3",
        },
        "regulatory_prior": {},
        "constraints": [],
    }


def field_rows(config: Mapping, columns: Iterable[str]) -> pd.DataFrame:
    schema = config.get("schema", {})
    adjacency = config.get("adjacency", {})
    prior = config.get("regulatory_prior", {})
    numeric = set(schema.get("numeric_columns", []))
    categorical = set(schema.get("categorical_columns", []))
    released = set(schema.get("released_columns", []))
    target = schema.get("sensitive_target", "")
    unit_id = adjacency.get("privacy_unit_id", "")
    bounds = schema.get("public_bounds", {})
    domains = schema.get("public_categories", {})
    rows = []
    for name in columns:
        field_type = "Numeric" if name in numeric else "Categorical" if name in categorical else "Excluded"
        public_min, public_max = (None, None)
        if name in bounds and len(bounds[name]) == 2:
            public_min, public_max = bounds[name]
        rows.append(
            {
                "Field": name,
                "Type": field_type,
                "Release": name in released,
                "Public Min": public_min,
                "Public Max": public_max,
                "Public Categories": ", ".join(str(value) for value in domains.get(name, [])),
                "Sensitive Target": name == target,
                "Privacy Unit ID": name == unit_id,
                "Regulatory Prior": prior.get(name, None),
            }
        )
    return pd.DataFrame(rows)


def _optional_float(value):
    if value is None or (isinstance(value, float) and np.isnan(value)):
        return None
    text = str(value).strip()
    return None if not text else float(text)


def apply_field_rows(config: Mapping, rows: pd.DataFrame) -> dict:
    values = deepcopy(dict(config))
    targets = rows.loc[rows["Sensitive Target"].astype(bool), "Field"].astype(str).tolist()
    unit_ids = rows.loc[rows["Privacy Unit ID"].astype(bool), "Field"].astype(str).tolist()
    if len(targets) != 1:
        raise ConfigurationError("Exactly one Sensitive Target must be selected")
    if len(unit_ids) != 1:
        raise ConfigurationError("Exactly one Privacy Unit ID must be selected")
    if targets[0] == unit_ids[0]:
        raise ConfigurationError("Sensitive Target and Privacy Unit ID must be different fields")

    released_rows = rows.loc[rows["Release"].astype(bool)].copy()
    invalid_types = released_rows.loc[~released_rows["Type"].isin(["Numeric", "Categorical"]), "Field"]
    if len(invalid_types):
        raise ConfigurationError("Released fields require Numeric or Categorical type: " + ", ".join(invalid_types.astype(str)))

    numeric = released_rows.loc[released_rows["Type"] == "Numeric", "Field"].astype(str).tolist()
    categorical = released_rows.loc[released_rows["Type"] == "Categorical", "Field"].astype(str).tolist()
    released = numeric + categorical
    if targets[0] in released or unit_ids[0] in released:
        raise ConfigurationError("Sensitive Target and Privacy Unit ID cannot be protected release fields")

    public_bounds = {}
    public_categories = {}
    regulatory_prior = {}
    row_by_field = {str(row["Field"]): row for _, row in rows.iterrows()}
    for name in numeric:
        lo = _optional_float(row_by_field[name]["Public Min"])
        hi = _optional_float(row_by_field[name]["Public Max"])
        if lo is not None and hi is not None:
            public_bounds[name] = [lo, hi]
    for name in categorical:
        text = str(row_by_field[name]["Public Categories"] or "")
        domain = [item.strip() for item in text.split(",") if item.strip()]
        if domain:
            public_categories[name] = domain
    for name in released:
        weight = _optional_float(row_by_field[name]["Regulatory Prior"])
        if weight is not None:
            regulatory_prior[name] = weight

    all_fields = rows["Field"].astype(str).tolist()
    values["schema"] = {
        "sensitive_target": targets[0],
        "numeric_columns": numeric,
        "categorical_columns": categorical,
        "excluded_columns": [name for name in all_fields if name not in released],
        "released_columns": released,
        "public_bounds": public_bounds,
        "public_categories": public_categories,
    }
    values.setdefault("adjacency", {})["privacy_unit_id"] = unit_ids[0]
    values["regulatory_prior"] = regulatory_prior
    return values


def constraint_expression(constraint: Mapping) -> str:
    terms = []
    for field, raw_coefficient in constraint.get("coefficients", {}).items():
        coefficient = float(raw_coefficient)
        absolute = abs(coefficient)
        label = str(field) if np.isclose(absolute, 1.0) else "{0:g} x {1}".format(absolute, field)
        if not terms:
            terms.append(("-" if coefficient < 0 else "") + label)
        else:
            terms.append((" - " if coefficient < 0 else " + ") + label)
    return "".join(terms) + " = {0:g}".format(float(constraint.get("rhs", 0.0)))


def constraint_rows(config: Mapping) -> pd.DataFrame:
    rows = []
    for constraint in config.get("constraints", []):
        coefficient_text = ", ".join(
            "{0}: {1:g}".format(name, float(value))
            for name, value in constraint.get("coefficients", {}).items()
        )
        rows.append(
            {
                "Name": constraint.get("name", ""),
                "Coefficients": coefficient_text,
                "RHS": constraint.get("rhs", 0.0),
                "Tolerance": constraint.get("tolerance", 0.01),
                "Type": constraint.get("type", "equality"),
                "Provenance": constraint.get("provenance", "public"),
            }
        )
    return pd.DataFrame(rows, columns=["Name", "Coefficients", "RHS", "Tolerance", "Type", "Provenance"])


def _parse_coefficients(text: str) -> Dict[str, float]:
    result = {}
    for item in str(text).split(","):
        item = item.strip()
        if not item:
            continue
        if ":" not in item:
            raise ConfigurationError("Constraint coefficients must use field: value pairs")
        name, value = item.split(":", 1)
        result[name.strip()] = float(value.strip())
    return result


def apply_constraint_rows(config: Mapping, rows: pd.DataFrame) -> dict:
    values = deepcopy(dict(config))
    constraints = []
    for _, row in rows.iterrows():
        name = str(row.get("Name", "")).strip()
        coefficient_text = str(row.get("Coefficients", "")).strip()
        if not name and not coefficient_text:
            continue
        if not name:
            raise ConfigurationError("Every constraint requires a name")
        constraints.append(
            {
                "name": name,
                "coefficients": _parse_coefficients(coefficient_text),
                "rhs": float(row.get("RHS", 0.0)),
                "tolerance": float(row.get("Tolerance", 0.01)),
                "type": str(row.get("Type", "equality")),
                "provenance": str(row.get("Provenance", "public")),
            }
        )
    values["constraints"] = constraints
    return values


def constraint_matrix(config: Mapping) -> Tuple[pd.DataFrame, pd.Series]:
    numeric = list(config.get("schema", {}).get("numeric_columns", []))
    constraints = list(config.get("constraints", []))
    matrix = pd.DataFrame(
        0.0,
        index=[item.get("name", "constraint") for item in constraints],
        columns=numeric,
    )
    rhs = pd.Series(index=matrix.index, dtype=float, name="b")
    for item in constraints:
        name = item.get("name", "constraint")
        for field, coefficient in item.get("coefficients", {}).items():
            if field in matrix.columns:
                matrix.loc[name, field] = float(coefficient)
        rhs.loc[name] = float(item.get("rhs", 0.0))
    return matrix, rhs


def validate_demo(config: Mapping, calibration: pd.DataFrame, release: pd.DataFrame) -> dict:
    schema, privacy, constraints, prior, adjacency, accounting = objects_from_config(config)
    if privacy.randomness_mode != "reproducibility":
        raise PrivacySafetyError(
            "The research GUI supports reproducibility mode only. "
            "Use the ledger-controlled CLI for production releases."
        )
    pipeline = RUPAPipeline(schema, privacy, constraints, prior, adjacency, accounting)
    validate_calibration_data(calibration, schema, adjacency)
    validate_release_data(release, schema, adjacency)
    diagnostics = pipeline.constraint_validation_.to_dict()
    return {
        "pipeline": pipeline,
        "schema": schema,
        "privacy": privacy,
        "constraints": constraints,
        "prior": prior,
        "adjacency": adjacency,
        "accounting": accounting,
        "constraint_validation": diagnostics,
        "calibration_rows": int(len(calibration)),
        "release_rows": int(len(release)),
        "released_columns": list(schema.released_columns),
    }


def constraint_precheck(config: Mapping) -> dict:
    schema_values = config.get("schema", {})
    schema = DataSchema.from_dict(schema_values)
    constraints = [PhysicalConstraint.from_dict(item) for item in config.get("constraints", [])]
    return validate_physical_constraints(schema, constraints).to_dict()


def execute_demo(
    config: Mapping,
    calibration: pd.DataFrame,
    release: pd.DataFrame,
    output_root: Path = RUNS_ROOT,
    progress: Optional[Callable[[str, str], None]] = None,
) -> DemoRun:
    started_at = time.perf_counter()
    progress = progress or (lambda _stage, _status: None)
    progress("Configuration and data validation", "running")
    validated = validate_demo(config, calibration, release)
    privacy = validated["privacy"]
    if privacy.randomness_mode != "reproducibility":
        raise PrivacySafetyError(
            "The local tutorial runs only in reproducibility mode. Production releases must use the ledger-controlled CLI workflow."
        )
    progress("Configuration and data validation", "complete")

    pipeline = validated["pipeline"]
    progress("Calibration, risk / utility, and budget allocation", "running")
    pipeline.fit(calibration)
    progress("Calibration, risk / utility, and budget allocation", "complete")

    progress("DP perturbation and constraint-aware post-processing", "running")
    result = pipeline.transform(release)
    progress("DP perturbation and constraint-aware post-processing", "complete")

    progress("Release packaging", "running")
    run_id = create_run_id(privacy.randomness_mode, privacy.random_seed)
    run_directory = write_public_run(
        result,
        validated["schema"],
        privacy,
        validated["constraints"],
        validated["prior"],
        validated["adjacency"],
        validated["accounting"],
        output_root,
        run_id=run_id,
    )
    progress("Release packaging", "complete")

    progress("Public artifact inspection", "running")
    inspection = validate_public_run(run_directory, validated["schema"].sensitive_target)
    progress("Public artifact inspection", "complete")
    return DemoRun(
        run_id=run_id,
        run_directory=run_directory,
        inspection=inspection,
        result=result,
        schema=validated["schema"],
        privacy=privacy,
        constraints=validated["constraints"],
        adjacency=validated["adjacency"],
        accounting=validated["accounting"],
        runtime_seconds=float(time.perf_counter() - started_at),
    )


def read_json(path: Path) -> dict:
    with Path(path).open("r", encoding="utf-8") as handle:
        return json.load(handle)


def apply_basic_config(
    config: Mapping,
    *,
    epsilon_total: float,
    epsilon_numeric: float,
    epsilon_categorical: float,
    utility_alpha: float,
    repair_alpha: float,
    random_seed: int,
    sensitive_target: str,
    privacy_unit_id: str,
    numeric_budget_strategy: Optional[str] = None,
) -> dict:
    """Update common GUI fields without replacing the formal validator."""
    values = deepcopy(dict(config))
    privacy = values.setdefault("privacy", {})
    privacy.update(
        {
            "epsilon_total": float(epsilon_total),
            "epsilon_numeric": float(epsilon_numeric),
            "epsilon_categorical": float(epsilon_categorical),
            "utility_alpha": float(utility_alpha),
            "repair_alpha": float(repair_alpha),
            "randomness_mode": "reproducibility",
            "random_seed": int(random_seed),
        }
    )
    if numeric_budget_strategy is not None:
        privacy["numeric_budget_strategy"] = str(numeric_budget_strategy)
    values.setdefault("schema", {})["sensitive_target"] = str(sensitive_target)
    values.setdefault("adjacency", {})["privacy_unit_id"] = str(privacy_unit_id)
    return values


def sanitized_calibration_preview(
    calibration: pd.DataFrame, config: Mapping, rows: int = 10
) -> pd.DataFrame:
    """Return a preview that never exposes sensitive-target values."""
    target = str(config.get("schema", {}).get("sensitive_target", ""))
    preview = calibration.head(rows).copy()
    if target and target in preview.columns:
        preview = preview.drop(columns=[target])
    return preview


def _manifest_artifact_paths(run_directory: Path) -> Tuple[dict, List[Path]]:
    run_directory = Path(run_directory).expanduser().resolve()
    manifest = read_json(run_directory / "manifest.json")
    paths = []
    for entry in manifest.get("artifacts", []):
        name = str(entry.get("name", ""))
        if not name or Path(name).name != name or name.startswith("."):
            raise PrivacySafetyError("Unsafe public artifact name: " + name)
        if name in FORBIDDEN_PUBLIC_NAMES or "internal" in name.lower():
            raise PrivacySafetyError("Internal artifact cannot be exported: " + name)
        path = (run_directory / name).resolve()
        if path.parent != run_directory or not path.is_file():
            raise PrivacySafetyError(
                "Public artifact is missing or escapes the run directory: " + name
            )
        digest = hashlib.sha256(path.read_bytes()).hexdigest()
        if digest != entry.get("sha256"):
            raise PrivacySafetyError("Public artifact hash mismatch: " + name)
        paths.append(path)
    return manifest, paths


def load_public_run(run_directory: Path) -> dict:
    """Load only manifest-authorized public artifacts for GUI presentation."""
    run_directory = Path(run_directory).expanduser().resolve()
    run_config = read_json(run_directory / "run_config.json")
    target = run_config.get("schema", {}).get("sensitive_target")
    manifest, paths = _manifest_artifact_paths(run_directory)
    inspection = validate_public_run(run_directory, target)
    artifact_names = {path.name for path in paths}

    csv_data = {}
    for name in sorted(PUBLIC_CSV_ARTIFACTS & artifact_names):
        csv_data[name] = pd.read_csv(run_directory / name)
    json_data = {}
    for name in sorted(PUBLIC_JSON_ARTIFACTS & artifact_names):
        json_data[name] = read_json(run_directory / name)

    release = csv_data.get("release_data.csv", pd.DataFrame())
    if target and target in release.columns:
        raise PrivacySafetyError("Sensitive target is present in the GUI public release")
    return {
        "run_directory": run_directory,
        "run_id": inspection["run_id"],
        "inspection": inspection,
        "manifest": manifest,
        "artifact_names": sorted(artifact_names),
        "csv": csv_data,
        "json": json_data,
    }


def build_public_run_archive(run_directory: Path) -> bytes:
    """Create an in-memory ZIP from the validated manifest whitelist only."""
    public_run = load_public_run(run_directory)
    manifest, paths = _manifest_artifact_paths(public_run["run_directory"])
    prefix = public_run["run_id"]
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        archive.writestr(
            prefix + "/manifest.json",
            json.dumps(manifest, indent=2, ensure_ascii=True, sort_keys=True) + "\n",
        )
        for path in paths:
            archive.write(path, arcname=prefix + "/" + path.name)
    return buffer.getvalue()


def reproduction_commands(
    calibration_name: str = "calibration.csv",
    release_name: str = "release.csv",
    config_name: str = "config.yaml",
    run_id: str = "reproduced_run",
) -> str:
    """Return a portable CLI recipe without embedding local absolute paths."""
    safe_names = []
    for name, fallback in (
        (calibration_name, "calibration.csv"),
        (release_name, "release.csv"),
        (config_name, "config.yaml"),
    ):
        candidate = Path(str(name)).name
        safe_names.append(candidate if candidate not in {"", "."} else fallback)
    return (
        "rupa-privacy validate --calibration {0} --release {1} --config {2}\n"
        "rupa-privacy run --calibration {0} --release {1} --config {2} "
        "--output runs --run-id {3}"
    ).format(safe_names[0], safe_names[1], safe_names[2], Path(str(run_id)).name)


def resolve_ledger_path(config_path: Optional[Path], configured_path: str) -> Path:
    path = Path(configured_path).expanduser()
    if path.is_absolute():
        return path.resolve()
    base = Path(config_path).resolve().parent if config_path else WORKSPACE_ROOT
    return (base / path).resolve()
