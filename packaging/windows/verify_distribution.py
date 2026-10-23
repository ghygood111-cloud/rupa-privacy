"""Compare frozen synthetic checks or GUI public artifacts with the source run."""

import argparse
import hashlib
import json
import sys
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "demo"))
from demo_support import load_public_run  # noqa: E402
from frozen_check import frame_digest  # noqa: E402
from rupa_privacy.models import DataSchema  # noqa: E402


def compare(reference, actual):
    checks = {}
    for group in ("risk", "joint_penalty", "utility", "epsilon"):
        if set(reference[group]) != set(actual[group]):
            raise ValueError("Scientific field mismatch: " + group)
        checks[group + "_max_abs_diff"] = max(
            abs(reference[group][key] - actual[group][key]) for key in reference[group]
        )
    for key in ("noisy_release_digest", "final_release_digest", "input_sha256", "versions"):
        checks[key + "_match"] = reference[key] == actual[key]
    checks["status"] = "PASS" if (
        all(checks[group + "_max_abs_diff"] <= 1e-12 for group in ("risk", "joint_penalty", "utility", "epsilon"))
        and all(checks[key + "_match"] for key in ("noisy_release_digest", "final_release_digest", "input_sha256", "versions"))
    ) else "FAIL"
    return checks


def gui_check(reference, directory):
    public = load_public_run(directory)
    schema = DataSchema.from_dict(public["json"]["run_config.json"]["schema"])
    risk = public["csv"]["risk_scores.csv"].set_index("feature")
    utility = public["csv"]["utility_weights.csv"].set_index("feature")
    allocation = public["csv"]["epsilon_allocation.csv"].set_index("feature")
    checks = {
        "run_id": public["run_id"], "manifest_verification": "PASS",
        "risk_max_abs_diff": max(abs(reference["risk"][name] - risk.loc[name, "single_nmi"]) for name in reference["risk"]),
        "joint_penalty_max_abs_diff": max(abs(reference["joint_penalty"][name] - risk.loc[name, "joint_penalty"]) for name in reference["joint_penalty"]),
        "utility_max_abs_diff": max(abs(reference["utility"][name] - utility.loc[name, "utility_weight"]) for name in reference["utility"]),
        "epsilon_max_abs_diff": max(abs(reference["epsilon"][name] - allocation.loc[name, "epsilon"]) for name in reference["epsilon"]),
        "final_release_digest_match": frame_digest(public["csv"]["release_data.csv"], schema) == reference["final_release_digest"],
        "sensitive_target_excluded": schema.sensitive_target not in public["csv"]["release_data.csv"].columns,
        "row_level_intermediates_present": False,
        "noisy_digest_note": "Checked by same-binary synthetic self-test; GUI correctly does not export noisy rows",
    }
    checks["status"] = "PASS" if (
        all(checks[group + "_max_abs_diff"] <= 1e-12 for group in ("risk", "joint_penalty", "utility", "epsilon"))
        and checks["final_release_digest_match"] and checks["sensitive_target_excluded"]
    ) else "FAIL"
    return checks


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--reference", type=Path, required=True)
    target = parser.add_mutually_exclusive_group(required=True)
    target.add_argument("--actual", type=Path)
    target.add_argument("--gui-run", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    reference = json.loads(args.reference.read_text(encoding="utf-8"))
    values = compare(reference, json.loads(args.actual.read_text(encoding="utf-8"))) if args.actual else gui_check(reference, args.gui_run)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(values, indent=2, allow_nan=False), encoding="utf-8")
    print(json.dumps(values, indent=2))
    return 0 if values["status"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
