"""Write and validate one public, self-contained RUPA run directory."""

import hashlib
import json
import re
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4

import numpy as np
import pandas as pd

from ..exceptions import ConfigurationError, PrivacySafetyError
from ..version import __version__


RUN_ID_PATTERN = re.compile(r"^[A-Za-z0-9_.-]+$")


def create_run_id(randomness_mode, seed=None):
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
    if randomness_mode == "reproducibility":
        if seed is None:
            raise ConfigurationError(
                "Reproducibility mode requires an explicit random_seed"
            )
        return "{0}_repro_seed{1}_{2}".format(timestamp, int(seed), uuid4().hex[:8])
    return "{0}_production_{1}".format(timestamp, uuid4().hex[:12])


def validate_run_id(run_id):
    value = str(run_id)
    if (
        value in {".", ".."}
        or not RUN_ID_PATTERN.fullmatch(value)
        or Path(value).name != value
    ):
        raise ConfigurationError(
            "run_id may contain only letters, numbers, dot, dash, and underscore "
            "and cannot be a relative path"
        )
    return value


def _json_ready(value):
    if isinstance(value, dict):
        return {str(key): _json_ready(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_json_ready(item) for item in value]
    if isinstance(value, np.ndarray):
        return [_json_ready(item) for item in value.tolist()]
    if isinstance(value, np.generic):
        return value.item()
    return value


def _write_json(path, run_id, payload):
    document = {"run_id": run_id}
    document.update(_json_ready(payload))
    with path.open("w", encoding="utf-8") as handle:
        json.dump(document, handle, indent=2, ensure_ascii=True, sort_keys=True)


def _sha256(path):
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def artifact_sha256(path):
    return _sha256(Path(path))


def write_internal_audit(output_root, run_id, payload):
    """Write non-public governance/failure metadata without record identifiers."""
    directory = Path(output_root).expanduser().resolve() / ".internal_audit"
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / (str(run_id) + ".json")
    document = {
        "run_id": str(run_id),
        "created_utc": datetime.now(timezone.utc).isoformat(),
    }
    document.update(_json_ready(payload))
    with path.open("w", encoding="utf-8") as handle:
        json.dump(document, handle, indent=2, ensure_ascii=True, sort_keys=True)
    return path


def write_public_run(
    result,
    schema,
    privacy,
    constraints,
    regulatory_prior,
    adjacency,
    privacy_accounting,
    output_root,
    run_id=None,
    production_authorization=None,
):
    """Write publishable artifacts without raw/calibration/intermediate records."""
    if privacy.randomness_mode == "production":
        if production_authorization is None or getattr(
            production_authorization, "status", None
        ) != "pending":
            raise PrivacySafetyError(
                "Production public export requires an active privacy-ledger reservation"
            )
        if getattr(production_authorization, "run_id", None) != run_id:
            raise PrivacySafetyError("Production run_id does not match its ledger reservation")
    run_id = run_id or create_run_id(
        privacy.randomness_mode, privacy.random_seed
    )
    run_id = validate_run_id(run_id)
    output_root = Path(output_root).expanduser().resolve()
    run_directory = output_root / run_id
    if run_directory.exists():
        raise ConfigurationError("Run directory already exists: " + str(run_directory))
    run_directory.mkdir(parents=True)

    if schema.sensitive_target in result.release_data.columns:
        raise PrivacySafetyError("Sensitive target appeared in release_data")
    expected_columns = {adjacency.privacy_unit_id} | set(schema.released_columns)
    unexpected = set(result.release_data.columns) - expected_columns
    if unexpected:
        raise PrivacySafetyError("Release contains undeclared fields: " + ", ".join(sorted(unexpected)))

    result.release_data.to_csv(run_directory / "release_data.csv", index=False)

    calibration_parameters_public = privacy.calibration_mode in {"synthetic", "public"}
    if calibration_parameters_public:
        risk_rows = []
        for name in schema.released_columns:
            bin_diagnostic = result.risk_result.bin_diagnostics.get(
                "feature:" + name, {}
            )
            risk_rows.append(
                {
                    "run_id": run_id,
                    "feature": name,
                    "single_nmi": result.risk_result.single_scores[name],
                    "joint_penalty": result.risk_result.joint_penalty[name],
                    "augmented_risk": result.risk_result.augmented_risk[name],
                    "requested_bins": bin_diagnostic.get("requested_bins"),
                    "effective_bins": bin_diagnostic.get("effective_bins"),
                    "bin_collapse_severity": bin_diagnostic.get(
                        "collapse_severity"
                    ),
                    "bin_warning": bin_diagnostic.get("warning"),
                }
            )
        pd.DataFrame(risk_rows).to_csv(run_directory / "risk_scores.csv", index=False)

        if result.risk_result.joint_records:
            joint_rows = []
            for item in result.risk_result.joint_records:
                bin_diagnostic = result.risk_result.bin_diagnostics.get(
                    "joint:{0}|{1}".format(item.first, item.second), {}
                )
                effective_bins = bin_diagnostic.get("effective_bins", [None, None])
                joint_rows.append({
                    "run_id": run_id,
                    "first": item.first,
                    "second": item.second,
                    "joint_nmi": item.joint_nmi,
                    "max_single_nmi": item.max_single_nmi,
                    "excess": item.excess,
                    "requested_bins": bin_diagnostic.get("requested_bins"),
                    "effective_bins_first": effective_bins[0],
                    "effective_bins_second": effective_bins[1],
                    "effective_joint_labels": bin_diagnostic.get(
                        "effective_joint_labels"
                    ),
                    "bin_warning": bin_diagnostic.get("warning"),
                })
            pd.DataFrame(joint_rows).to_csv(
                run_directory / "joint_risk.csv", index=False
            )

        utility_rows = []
        for name in schema.released_columns:
            utility_rows.append(
                {
                    "run_id": run_id,
                    "feature": name,
                    "regulatory_prior": result.utility_result.prior_weights[name],
                    "entropy_weight": result.utility_result.entropy_weights[name],
                    "utility_weight": result.utility_result.utility_weights[name],
                }
            )
        pd.DataFrame(utility_rows).to_csv(run_directory / "utility_weights.csv", index=False)

        allocation_rows = []
        for name in schema.released_columns:
            allocation_rows.append(
                {
                    "run_id": run_id,
                    "feature": name,
                    "epsilon": result.allocation_result.epsilon[name],
                    "public_sensitivity": result.allocation_result.sensitivities[name],
                }
            )
        pd.DataFrame(allocation_rows).to_csv(
            run_directory / "epsilon_allocation.csv", index=False
        )

    public_physical = dict(result.physical_audit)
    public_physical["states"] = {
        name: values
        for name, values in result.physical_audit["states"].items()
        if name != "original_clipped_internal"
    }
    public_physical.pop("publication_note", None)
    _write_json(run_directory / "privacy_metrics.json", run_id, result.privacy_audit)
    _write_json(run_directory / "physical_metrics.json", run_id, public_physical)
    _write_json(
        run_directory / "utility_metrics.json",
        run_id,
        {
            "status": "withheld_from_public_run",
            "reason": "Current utility audit compares against raw release records.",
        },
    )
    _write_json(run_directory / "attack_metrics.json", run_id, result.attack_audit)
    public_governance = {
        "adjacency": result.governance_audit["adjacency"],
        "privacy_unit_id": result.governance_audit["privacy_unit_id"],
        "roster_is_public": True,
        "one_row_per_unit": True,
        "roster_preserved": result.governance_audit["roster_preserved"],
        "calibration_mode": result.governance_audit["calibration_mode"],
        "calibration_unit_count": result.governance_audit["calibration_unit_count"],
        "release_unit_count": result.governance_audit["release_unit_count"],
        "calibration_release_disjoint_check": result.governance_audit[
            "calibration_release_disjoint_check"
        ],
        "protection_scope": result.governance_audit["protection_scope"],
    }
    _write_json(run_directory / "governance_metrics.json", run_id, public_governance)
    public_privacy = privacy.to_public_dict()
    if privacy.calibration_mode == "disjoint_private":
        public_privacy["calibration_source"] = "private source withheld"
        public_privacy.pop("calibration_public_confirmed", None)
    public_accounting = {
        "dataset_id": privacy_accounting.dataset_id,
        "maximum_cumulative_epsilon": privacy_accounting.maximum_cumulative_epsilon,
    }
    _write_json(
        run_directory / "run_config.json",
        run_id,
        {
            "schema": schema.to_dict(),
            "privacy": public_privacy,
            "regulatory_prior": dict(regulatory_prior),
            "constraints": [constraint.to_dict() for constraint in constraints],
            "adjacency": adjacency.to_dict(),
            "privacy_accounting": public_accounting,
        },
    )
    _write_json(
        run_directory / "metadata.json",
        run_id,
        {
            "software": "RUPA Physical-Constraint-Aware Privacy Release",
            "version": __version__,
            "created_utc": datetime.now(timezone.utc).isoformat(),
            "release_rows": int(len(result.release_data)),
            "release_columns": list(result.release_data.columns),
            "sensitive_target_released": False,
            "calibration_mode": privacy.calibration_mode,
            "randomness_mode": privacy.randomness_mode,
            "adjacency": adjacency.type,
            "release_type": "fixed-roster, row-preserving microdata release",
            "release_notice": result.metadata["release_notice"],
            "calibration_parameters_public": calibration_parameters_public,
            "public_output_policy": (
                "No raw input, calibration table, sensitive target values, noisy records, "
                "or raw-dependent utility metrics are written."
            ),
        },
    )
    notice = result.metadata["release_notice"] + "\n"
    notice += (
        "Physical post-processing reduces residuals for configured public linear "
        "equalities. It does not guarantee zero final residual when repair_alpha < 1 "
        "or public-bound clipping is active.\n"
    )
    (run_directory / "NOTICE.txt").write_text(notice, encoding="utf-8")

    artifacts = []
    for path in sorted(run_directory.iterdir()):
        if path.name == "manifest.json" or not path.is_file():
            continue
        artifacts.append(
            {"name": path.name, "sha256": _sha256(path), "size_bytes": path.stat().st_size}
        )
    _write_json(
        run_directory / "manifest.json",
        run_id,
        {
            "artifacts": artifacts,
            "randomness_mode": privacy.randomness_mode,
            "release_notice": result.metadata["release_notice"],
        },
    )
    return run_directory


def validate_public_run(run_directory, sensitive_target=None):
    """Validate run identity, hashes, and release-column safety."""
    run_directory = Path(run_directory).expanduser().resolve()
    manifest_path = run_directory / "manifest.json"
    if not manifest_path.is_file():
        raise ConfigurationError("Run manifest is missing")
    with manifest_path.open("r", encoding="utf-8") as handle:
        manifest = json.load(handle)
    run_id = manifest.get("run_id")
    if run_id != run_directory.name:
        raise ConfigurationError("Manifest run_id does not match its directory")

    for entry in manifest.get("artifacts", []):
        path = run_directory / entry["name"]
        if not path.is_file() or _sha256(path) != entry["sha256"]:
            raise ConfigurationError("Artifact hash mismatch: " + entry["name"])
        if path.suffix.lower() == ".json":
            with path.open("r", encoding="utf-8") as handle:
                if json.load(handle).get("run_id") != run_id:
                    raise ConfigurationError("Artifact run_id mismatch: " + entry["name"])
        elif path.suffix.lower() == ".csv" and path.name != "release_data.csv":
            frame = pd.read_csv(path)
            if "run_id" not in frame or (
                len(frame) > 0 and set(frame["run_id"].astype(str)) != {run_id}
            ):
                raise ConfigurationError("Artifact run_id mismatch: " + entry["name"])

    release = pd.read_csv(run_directory / "release_data.csv")
    if sensitive_target and sensitive_target in release.columns:
        raise PrivacySafetyError("Sensitive target is present in the public release")
    forbidden_names = {
        "calibration_data.csv",
        "raw_data.csv",
        "original_data.csv",
        "noisy_data.csv",
        "repaired_internal.csv",
    }
    present = forbidden_names & {path.name for path in run_directory.iterdir()}
    if present:
        raise PrivacySafetyError("Forbidden internal artifacts are present: " + ", ".join(sorted(present)))
    if manifest.get("randomness_mode") == "production":
        for entry in manifest.get("artifacts", []):
            path = run_directory / entry["name"]
            if path.suffix.lower() == ".json":
                content = path.read_text(encoding="utf-8").lower()
                if '"random_seed"' in content or '"seed"' in content:
                    raise PrivacySafetyError("Production public output contains a seed field")
    return {
        "run_id": run_id,
        "artifact_count": len(manifest["artifacts"]),
        "release_rows": len(release),
        "randomness_mode": manifest.get("randomness_mode"),
    }
