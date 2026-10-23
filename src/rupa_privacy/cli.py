"""Command-line interface for the installed RUPA core package."""

import argparse
import json
import shutil
import sys
from pathlib import Path

from .data import (
    example_adjacency_config,
    example_constraints,
    example_privacy_accounting_config,
    example_privacy_config,
    example_regulatory_prior,
    example_schema,
    generate_example_pair,
)
from .exceptions import RUPAError
from .io import (
    artifact_sha256,
    create_run_id,
    load_pipeline_config,
    load_table,
    save_config,
    validate_public_run,
    validate_run_id,
    write_internal_audit,
    write_public_run,
)
from .pipeline import RUPAPipeline
from .governance import dataframe_version_hash, release_schema_hash
from .ledger import PrivacyLedger
from .validation import validate_calibration_data, validate_release_data
from .version import __version__


def _add_input_arguments(parser):
    parser.add_argument("--calibration", required=True, help="Calibration CSV/XLSX/Parquet")
    parser.add_argument("--release", required=True, help="Release CSV/XLSX/Parquet")
    parser.add_argument("--config", required=True, help="RUPA JSON/YAML configuration")


def build_parser():
    parser = argparse.ArgumentParser(
        prog="rupa-privacy",
        description=(
            "Configurable differential privacy release for fixed-roster, "
            "row-preserving industrial microdata"
        ),
    )
    parser.add_argument("--version", action="version", version=__version__)
    subparsers = parser.add_subparsers(dest="command", required=True)

    version = subparsers.add_parser("version", help="Print the installed version")
    version.set_defaults(handler=_version)

    generate = subparsers.add_parser("generate-example", help="Write synthetic example inputs")
    generate.add_argument("--output", required=True)
    generate.add_argument("--release-rows", type=int, default=1000)
    generate.add_argument("--calibration-rows", type=int, default=1000)
    generate.set_defaults(handler=_generate_example)

    validate = subparsers.add_parser("validate", help="Validate configuration and input tables")
    _add_input_arguments(validate)
    validate.set_defaults(handler=_validate)

    run = subparsers.add_parser(
        "run", help="Run the configured workflow and write one public run directory"
    )
    _add_input_arguments(run)
    run.add_argument("--output", required=True, help="Parent directory for run_id outputs")
    run.add_argument("--run-id", help="Optional explicit run identifier")
    run.add_argument("--seed", type=int, help="Override the configured mechanism seed")
    run.set_defaults(handler=_run)

    reproduce = subparsers.add_parser(
        "reproduce-example", help="Run the complete fixed-seed synthetic example"
    )
    reproduce.add_argument("--output", required=True, help="Parent directory for run output")
    reproduce.add_argument("--run-id", help="Optional explicit run identifier")
    reproduce.set_defaults(handler=_reproduce_example)

    inspect = subparsers.add_parser("inspect-run", help="Validate one public run directory")
    inspect.add_argument("run_directory")
    inspect.add_argument("--sensitive-target", default="production")
    inspect.set_defaults(handler=_inspect_run)

    ledger = subparsers.add_parser(
        "ledger", help="Read and verify persistent production privacy accounting"
    )
    ledger_commands = ledger.add_subparsers(dest="ledger_command", required=True)
    ledger_show = ledger_commands.add_parser("show", help="Show ledger release records")
    ledger_show.add_argument("--ledger", default="privacy_ledger.sqlite3")
    ledger_show.add_argument("--dataset-id")
    ledger_show.set_defaults(handler=_ledger_show)
    ledger_check = ledger_commands.add_parser("check", help="Check projected cumulative epsilon")
    ledger_check.add_argument("--ledger", default="privacy_ledger.sqlite3")
    ledger_check.add_argument("--dataset-id")
    ledger_check.add_argument("--maximum-cumulative-epsilon", type=float)
    ledger_check.add_argument("--additional-epsilon", type=float, default=0.0)
    ledger_check.set_defaults(handler=_ledger_check)
    ledger_verify = ledger_commands.add_parser("verify", help="Verify the ledger event hash chain")
    ledger_verify.add_argument("--ledger", default="privacy_ledger.sqlite3")
    ledger_verify.set_defaults(handler=_ledger_verify)
    return parser


def _version(_args):
    print(__version__)
    return 0


def _generate_example(args):
    destination = Path(args.output)
    if destination.exists() and any(destination.iterdir()):
        raise RUPAError("Example output directory must be absent or empty: " + str(destination))
    destination.mkdir(parents=True, exist_ok=True)
    calibration, release = generate_example_pair(
        n_release=args.release_rows, n_calibration=args.calibration_rows
    )
    schema = example_schema()
    calibration.to_csv(destination / "calibration.csv", index=False)
    release.drop(columns=[schema.sensitive_target]).to_csv(
        destination / "release.csv", index=False
    )
    save_config(
        destination / "config.yaml",
        schema,
        example_privacy_config(),
        example_constraints(),
        example_regulatory_prior(),
        example_adjacency_config(),
        example_privacy_accounting_config("privacy_ledger.sqlite3"),
    )
    print("Example inputs written to " + str(destination.resolve()))
    return 0


def _load_inputs(args):
    schema, privacy, constraints, prior, adjacency, accounting = load_pipeline_config(
        args.config
    )
    calibration = load_table(args.calibration)
    release = load_table(args.release)
    return (
        schema,
        privacy,
        constraints,
        prior,
        adjacency,
        accounting,
        calibration,
        release,
    )


def _validate(args):
    schema, privacy, constraints, prior, adjacency, accounting, calibration, release = _load_inputs(args)
    pipeline = RUPAPipeline(
        schema, privacy, constraints, prior, adjacency, accounting
    )
    validate_calibration_data(calibration, schema, adjacency)
    validate_release_data(release, schema, adjacency)
    constraint_validation = pipeline.constraint_validation_
    print(
        "Validation passed: calibration_rows={0}, release_rows={1}, "
        "released_columns={2}, constraints={3}, rank={4}/{5}, condition_number={6:.6g}".format(
            len(calibration),
            len(release),
            len(schema.released_columns),
            constraint_validation.decision,
            constraint_validation.rank,
            constraint_validation.expected_rank,
            constraint_validation.condition_number,
        )
    )
    return 0


def _resolved_ledger_path(accounting, config_path):
    path = Path(accounting.ledger_path).expanduser()
    if not path.is_absolute():
        path = Path(config_path).expanduser().resolve().parent / path
    return path.resolve()


def _run(args):
    schema, privacy, constraints, prior, adjacency, accounting, calibration, release = _load_inputs(args)
    if args.seed is not None:
        privacy.random_seed = args.seed
    run_id = args.run_id or create_run_id(
        privacy.randomness_mode, privacy.random_seed
    )
    run_id = validate_run_id(run_id)
    reservation = None
    ledger = None
    run_directory = None
    dataset_hash = None
    output_root = Path(args.output).expanduser().resolve()
    candidate_run_directory = (output_root / run_id).resolve()
    run_directory_preexisted = candidate_run_directory.exists()
    try:
        pipeline = RUPAPipeline(
            schema, privacy, constraints, prior, adjacency, accounting
        )
        dataset_hash = dataframe_version_hash(
            release, [adjacency.privacy_unit_id] + schema.released_columns
        )
        if privacy.randomness_mode == "production":
            ledger = PrivacyLedger(_resolved_ledger_path(accounting, args.config))
            reservation = ledger.begin_release(
                dataset_id=accounting.dataset_id,
                dataset_version_hash=dataset_hash,
                privacy_unit_id=adjacency.privacy_unit_id,
                adjacency=adjacency.type,
                release_schema_hash=release_schema_hash(schema, adjacency),
                epsilon_total=privacy.epsilon_total,
                epsilon_numeric=privacy.epsilon_numeric,
                epsilon_categorical=privacy.epsilon_categorical,
                mechanism_summary=(
                    "numeric=range-calibrated-laplace;categorical=generalized-randomized-"
                    "response;postprocessing=public-linear-equality-residual-reduction"
                ),
                run_id=run_id,
                maximum_cumulative_epsilon=accounting.maximum_cumulative_epsilon,
                randomness_mode=privacy.randomness_mode,
            )
        result = pipeline.fit_transform(
            calibration,
            release,
            production_authorization=reservation,
        )
        run_directory = write_public_run(
            result,
            schema,
            privacy,
            constraints,
            prior,
            adjacency,
            accounting,
            args.output,
            run_id=run_id,
            production_authorization=reservation,
        )
        if ledger is not None:
            release_hash = artifact_sha256(run_directory / "release_data.csv")
            write_internal_audit(
                args.output,
                run_id,
                {
                    "status": "mechanism_completed_pending_ledger_commit",
                    "dataset_id": accounting.dataset_id,
                    "dataset_version_hash": dataset_hash,
                    "adjacency": adjacency.type,
                    "privacy_unit_id": adjacency.privacy_unit_id,
                    "calibration_mode": privacy.calibration_mode,
                    "calibration_unit_count": result.governance_audit[
                        "calibration_unit_count"
                    ],
                    "release_unit_count": result.governance_audit[
                        "release_unit_count"
                    ],
                    "calibration_release_disjoint_check": result.governance_audit[
                        "calibration_release_disjoint_check"
                    ],
                    "overlap_count": result.governance_audit[
                        "overlap_count_internal"
                    ],
                },
            )
            ledger.mark_released(run_id, release_hash)
    except Exception as exc:
        if (
            not run_directory_preexisted
            and candidate_run_directory.parent == output_root
            and candidate_run_directory.exists()
        ):
            shutil.rmtree(candidate_run_directory)
        if ledger is not None and reservation is not None:
            try:
                ledger.mark_failed(run_id, str(exc))
            except Exception:
                pass
        write_internal_audit(
            args.output,
            run_id,
            {
                "status": "failed",
                "dataset_id": accounting.dataset_id,
                "dataset_version_hash": dataset_hash,
                "adjacency": adjacency.type,
                "error_type": type(exc).__name__,
                "error": str(exc),
                "optimizer_diagnostics": getattr(exc, "diagnostics", {}),
            },
        )
        raise
    print("Run completed: " + str(run_directory))
    return 0


def _reproduce_example(args):
    schema = example_schema()
    privacy = example_privacy_config()
    constraints = example_constraints()
    prior = example_regulatory_prior()
    adjacency = example_adjacency_config()
    accounting = example_privacy_accounting_config()
    calibration, release = generate_example_pair()
    result = RUPAPipeline(
        schema, privacy, constraints, prior, adjacency, accounting
    ).fit_transform(
        calibration, release
    )
    run_directory = write_public_run(
        result,
        schema,
        privacy,
        constraints,
        prior,
        adjacency,
        accounting,
        args.output,
        run_id=args.run_id,
    )
    print("Fixed-seed example completed: " + str(run_directory))
    return 0


def _inspect_run(args):
    summary = validate_public_run(args.run_directory, args.sensitive_target)
    print(
        "Run valid: run_id={run_id}, artifacts={artifact_count}, release_rows={release_rows}, randomness_mode={randomness_mode}".format(
            **summary
        )
    )
    return 0


def _ledger_show(args):
    rows = PrivacyLedger(args.ledger, create=False).show(dataset_id=args.dataset_id)
    print(json.dumps(rows, indent=2, ensure_ascii=True, sort_keys=True))
    return 0


def _ledger_check(args):
    ledger = PrivacyLedger(args.ledger, create=False)
    if args.dataset_id is None:
        rows = ledger.show()
        datasets = sorted({row["dataset_id"] for row in rows})
        print(json.dumps({"datasets": datasets, "release_records": len(rows)}, indent=2))
        return 0
    if args.maximum_cumulative_epsilon is None:
        raise RUPAError(
            "ledger check with --dataset-id requires --maximum-cumulative-epsilon"
        )
    result = ledger.check_budget(
        args.dataset_id,
        args.maximum_cumulative_epsilon,
        args.additional_epsilon,
    )
    print(json.dumps(result, indent=2, ensure_ascii=True, sort_keys=True))
    return 0 if result["allowed"] else 2


def _ledger_verify(args):
    result = PrivacyLedger(args.ledger, create=False).verify()
    print(json.dumps(result, indent=2, ensure_ascii=True, sort_keys=True))
    return 0


def main(argv=None):
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        return int(args.handler(args))
    except (RUPAError, OSError, ValueError) as exc:
        print("ERROR: " + str(exc), file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
