import json

import pandas as pd

import rupa_privacy.allocation.optimizer as optimizer
from rupa_privacy.cli import main
from rupa_privacy.io import load_pipeline_config, save_config, validate_public_run
from rupa_privacy.ledger import PrivacyLedger


class _FailedSolverResult:
    success = False
    message = "simulated SLSQP failure"


def _production_inputs(tmp_path, calibration_mode="synthetic", maximum=20.0):
    inputs = tmp_path / "inputs"
    assert (
        main(
            [
                "generate-example",
                "--output",
                str(inputs),
                "--release-rows",
                "60",
                "--calibration-rows",
                "80",
            ]
        )
        == 0
    )
    config_path = inputs / "config.yaml"
    schema, privacy, constraints, prior, adjacency, accounting = load_pipeline_config(
        config_path
    )
    privacy.randomness_mode = "production"
    privacy.random_seed = None
    privacy.calibration_mode = calibration_mode
    privacy.release_data_mode = "confidential"
    privacy.release_source = "confidential pytest release table"
    if calibration_mode == "disjoint_private":
        privacy.calibration_source = "private calibration cohort"
    accounting.maximum_cumulative_epsilon = maximum
    accounting.ledger_path = "privacy_ledger.sqlite3"
    save_config(
        config_path,
        schema,
        privacy,
        constraints,
        prior,
        adjacency,
        accounting,
    )
    common = [
        "--calibration",
        str(inputs / "calibration.csv"),
        "--release",
        str(inputs / "release.csv"),
        "--config",
        str(config_path),
    ]
    return inputs, config_path, common


def test_production_cli_uses_nonreplayable_output_and_exports_no_seed(tmp_path):
    inputs, config_path, common = _production_inputs(tmp_path)
    runs = tmp_path / "runs"
    assert main(["run"] + common + ["--output", str(runs), "--run-id", "prod_a"]) == 0
    assert main(["run"] + common + ["--output", str(runs), "--run-id", "prod_b"]) == 0

    first = pd.read_csv(runs / "prod_a" / "release_data.csv")
    second = pd.read_csv(runs / "prod_b" / "release_data.csv")
    assert not first.equals(second)
    for run_id in ("prod_a", "prod_b"):
        summary = validate_public_run(runs / run_id, sensitive_target="production")
        assert summary["randomness_mode"] == "production"
        with (runs / run_id / "manifest.json").open(encoding="utf-8") as handle:
            assert json.load(handle)["randomness_mode"] == "production"
        for path in (runs / run_id).glob("*.json"):
            content = path.read_text(encoding="utf-8").lower()
            assert '"seed"' not in content
            assert '"random_seed"' not in content

    ledger = PrivacyLedger(inputs / "privacy_ledger.sqlite3")
    rows = ledger.show()
    assert [row["release_status"] for row in rows] == ["released", "released"]
    assert rows[-1]["cumulative_epsilon"] == 10.0


def test_disjoint_private_public_output_withholds_calibration_derivatives(tmp_path):
    inputs, _, common = _production_inputs(tmp_path, calibration_mode="disjoint_private")
    runs = tmp_path / "runs"
    assert (
        main(["run"] + common + ["--output", str(runs), "--run-id", "private_cal"])
        == 0
    )
    public = runs / "private_cal"
    names = {path.name for path in public.iterdir()}
    assert "risk_scores.csv" not in names
    assert "joint_risk.csv" not in names
    assert "utility_weights.csv" not in names
    assert "epsilon_allocation.csv" not in names

    governance = json.loads((public / "governance_metrics.json").read_text(encoding="utf-8"))
    assert governance["calibration_release_disjoint_check"] == "PASS"
    assert "overlap_count" not in governance
    assert not any("enterprise_314159" in path.read_text(encoding="utf-8") for path in public.glob("*.*"))

    run_config = json.loads((public / "run_config.json").read_text(encoding="utf-8"))
    assert run_config["privacy"]["calibration_source"] == "private source withheld"
    assert "ledger_path" not in run_config["privacy_accounting"]
    internal = json.loads(
        (runs / ".internal_audit" / "private_cal.json").read_text(encoding="utf-8")
    )
    assert internal["calibration_release_disjoint_check"] == "PASS"
    assert internal["overlap_count"] == 0


def test_optimizer_failure_creates_no_public_success_and_does_not_spend_budget(
    tmp_path, monkeypatch
):
    inputs, _, common = _production_inputs(tmp_path, maximum=10.0)
    runs = tmp_path / "runs"
    monkeypatch.setattr(
        optimizer, "minimize", lambda *args, **kwargs: _FailedSolverResult()
    )
    assert (
        main(["run"] + common + ["--output", str(runs), "--run-id", "solver_fail"])
        == 2
    )
    assert not (runs / "solver_fail").exists()
    audit = json.loads(
        (runs / ".internal_audit" / "solver_fail.json").read_text(encoding="utf-8")
    )
    assert audit["status"] == "failed"
    assert audit["error_type"] == "BudgetOptimizationError"
    assert audit["optimizer_diagnostics"]["rejected_candidates"]

    ledger = PrivacyLedger(inputs / "privacy_ledger.sqlite3")
    rows = ledger.show()
    assert len(rows) == 1
    assert rows[0]["release_status"] == "failed"
    assert ledger.check_budget(rows[0]["dataset_id"], 10.0)["released_epsilon"] == 0.0


def test_cli_ledger_show_check_and_verify_are_read_only(tmp_path):
    inputs, _, common = _production_inputs(tmp_path)
    runs = tmp_path / "runs"
    assert main(["run"] + common + ["--output", str(runs), "--run-id", "ledger_cli"]) == 0
    ledger_path = inputs / "privacy_ledger.sqlite3"
    before = PrivacyLedger(ledger_path).show()
    assert main(["ledger", "show", "--ledger", str(ledger_path)]) == 0
    assert (
        main(
            [
                "ledger",
                "check",
                "--ledger",
                str(ledger_path),
                "--dataset-id",
                before[0]["dataset_id"],
                "--maximum-cumulative-epsilon",
                "20",
                "--additional-epsilon",
                "5",
            ]
        )
        == 0
    )
    assert main(["ledger", "verify", "--ledger", str(ledger_path)]) == 0
    assert PrivacyLedger(ledger_path).show() == before


def test_read_only_ledger_cli_does_not_create_missing_database(tmp_path):
    missing = tmp_path / "missing.sqlite3"
    assert main(["ledger", "show", "--ledger", str(missing)]) == 2
    assert not missing.exists()
