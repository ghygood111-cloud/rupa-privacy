"""Compare the installed package with immutable fixed-seed legacy references."""

import argparse
import csv
import hashlib
import json
from pathlib import Path

import numpy as np

from rupa_privacy import RUPAPipeline
from rupa_privacy.data import (
    example_adjacency_config,
    example_constraints,
    example_privacy_accounting_config,
    example_privacy_config,
    example_regulatory_prior,
    example_schema,
    generate_example_pair,
)


ROOT = Path(__file__).resolve().parents[1]
REFERENCE = ROOT / "migration" / "legacy_fixed_seed_reference.json"
DESTINATION = ROOT / "migration" / "legacy_vs_package_comparison.csv"


def frame_digest(frame, schema):
    """Hash a stable eight-decimal representation of a mixed release table."""
    digest = hashlib.sha256()
    for name in schema.released_columns:
        digest.update(name.encode("utf-8"))
        digest.update(b"\0")
        if name in schema.numeric_columns:
            values = np.round(frame[name].to_numpy(dtype=float), 8).astype("<f8")
            digest.update(values.tobytes())
        else:
            values = frame[name].astype(str).tolist()
            digest.update(
                json.dumps(values, ensure_ascii=True, separators=(",", ":")).encode("utf-8")
            )
        digest.update(b"\0")
    return digest.hexdigest()


def _difference(actual, expected):
    return float(
        np.max(np.abs(np.asarray(actual, dtype=float) - np.asarray(expected, dtype=float)))
    )


def _parse_args(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--output",
        type=Path,
        default=DESTINATION,
        help="Destination CSV (default: migration/legacy_vs_package_comparison.csv)",
    )
    return parser.parse_args(argv)


def main(argv=None):
    args = _parse_args(argv)
    with REFERENCE.open("r", encoding="utf-8") as handle:
        reference = json.load(handle)
    schema = example_schema()
    privacy = example_privacy_config()
    calibration, release = generate_example_pair()
    result = RUPAPipeline(
        schema,
        privacy,
        example_constraints(),
        example_regulatory_prior(),
        example_adjacency_config(),
        example_privacy_accounting_config(),
    ).fit_transform(calibration, release)

    comparisons = [
        ("single_risk_scores", _difference(list(result.risk_result.single_scores.values()), reference["risk_scores"]), 1e-12),
        ("joint_penalty", _difference(list(result.risk_result.joint_penalty.values()), reference["joint_penalty"]), 1e-12),
        ("utility_weights", _difference(list(result.utility_result.utility_weights.values()), reference["utility_weights"]), 1e-12),
        ("epsilon_allocation", _difference(list(result.allocation_result.epsilon.values()), reference["epsilon"]), 1e-10),
    ]
    rows = [
        {
            "quantity": name,
            "comparison": "max_absolute_difference",
            "value": value,
            "tolerance": tolerance,
            "status": "PASS" if value <= tolerance else "FAIL",
        }
        for name, value, tolerance in comparisons
    ]
    for name, value in [
        ("noisy_release_digest", frame_digest(result.noisy_data, schema)),
        ("final_release_digest", frame_digest(result.release_data, schema)),
    ]:
        expected = reference[name]
        rows.append(
            {
                "quantity": name,
                "comparison": "sha256_of_rounded_fixed_seed_table",
                "value": value,
                "tolerance": expected,
                "status": "PASS" if value == expected else "FAIL",
            }
        )

    destination = args.output.resolve()
    destination.parent.mkdir(parents=True, exist_ok=True)
    with destination.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=rows[0].keys())
        writer.writeheader()
        writer.writerows(rows)
    for row in rows:
        print("{status:4s} {quantity}: {value}".format(**row))
    print("Comparison written to " + str(destination))
    return 0 if all(row["status"] == "PASS" for row in rows) else 1


if __name__ == "__main__":
    raise SystemExit(main())
