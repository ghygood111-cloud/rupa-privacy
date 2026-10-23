import sqlite3
from concurrent.futures import ThreadPoolExecutor

import pytest

from rupa_privacy.exceptions import LedgerError
from rupa_privacy.ledger import PrivacyLedger


def _begin(ledger, run_id, epsilon=5.0, maximum=10.0):
    return ledger.begin_release(
        dataset_id="industrial_2026_q2",
        dataset_version_hash="dataset-hash",
        privacy_unit_id="enterprise_id",
        adjacency="fixed_roster_replace_one",
        release_schema_hash="schema-hash",
        epsilon_total=epsilon,
        epsilon_numeric=epsilon - 0.4,
        epsilon_categorical=0.4,
        mechanism_summary="laplace+grr+public-linear-equality-postprocessing",
        run_id=run_id,
        maximum_cumulative_epsilon=maximum,
        randomness_mode="production",
    )


def test_first_and_repeated_releases_accumulate_epsilon(tmp_path):
    ledger = PrivacyLedger(tmp_path / "ledger.sqlite3")
    _begin(ledger, "run_1")
    first = ledger.mark_released("run_1", "1" * 64)
    _begin(ledger, "run_2")
    second = ledger.mark_released("run_2", "2" * 64)
    assert first["cumulative_epsilon"] == 5.0
    assert second["cumulative_epsilon"] == 10.0
    check = ledger.check_budget("industrial_2026_q2", 10.0)
    assert check["released_epsilon"] == 10.0
    assert check["allowed"] is True


def test_over_budget_attempt_is_rejected_and_audited(tmp_path):
    ledger = PrivacyLedger(tmp_path / "ledger.sqlite3")
    _begin(ledger, "released")
    ledger.mark_released("released", "a" * 64)
    with pytest.raises(LedgerError, match="exceeds maximum"):
        _begin(ledger, "over_budget", epsilon=6.0)
    row = ledger.show()[-1]
    assert row["run_id"] == "over_budget"
    assert row["release_status"] == "failed"
    assert ledger.check_budget("industrial_2026_q2", 10.0)["released_epsilon"] == 5.0


def test_failed_run_does_not_consume_budget(tmp_path):
    ledger = PrivacyLedger(tmp_path / "ledger.sqlite3")
    _begin(ledger, "failed_run")
    ledger.mark_failed("failed_run", "simulated mechanism failure")
    check = ledger.check_budget("industrial_2026_q2", 10.0)
    assert check["released_epsilon"] == 0.0
    assert check["pending_epsilon"] == 0.0


def test_duplicate_run_id_cannot_be_counted_twice(tmp_path):
    ledger = PrivacyLedger(tmp_path / "ledger.sqlite3")
    _begin(ledger, "same_run")
    with pytest.raises(LedgerError, match="already present"):
        _begin(ledger, "same_run")


def test_ledger_hash_chain_and_record_payload_are_verified(tmp_path):
    path = tmp_path / "ledger.sqlite3"
    ledger = PrivacyLedger(path)
    _begin(ledger, "verified")
    ledger.mark_released("verified", "b" * 64)
    assert ledger.verify()["status"] == "PASS"

    with sqlite3.connect(path) as connection:
        connection.execute(
            "UPDATE releases SET epsilon_total=99 WHERE run_id='verified'"
        )
    with pytest.raises(LedgerError, match="payload does not match"):
        ledger.verify()


def test_concurrent_reservations_are_serialized(tmp_path):
    ledger = PrivacyLedger(tmp_path / "ledger.sqlite3")

    def reserve(run_id):
        try:
            _begin(ledger, run_id, maximum=5.0)
            return "pending"
        except LedgerError:
            return "failed"

    with ThreadPoolExecutor(max_workers=2) as pool:
        outcomes = list(pool.map(reserve, ["concurrent_a", "concurrent_b"]))
    assert sorted(outcomes) == ["failed", "pending"]
    statuses = sorted(row["release_status"] for row in ledger.show())
    assert statuses == ["failed", "pending"]


def test_only_production_mode_can_reserve_budget(tmp_path):
    ledger = PrivacyLedger(tmp_path / "ledger.sqlite3")
    with pytest.raises(LedgerError, match="Only production"):
        ledger.begin_release(
            dataset_id="dataset",
            dataset_version_hash="hash",
            privacy_unit_id="enterprise_id",
            adjacency="fixed_roster_replace_one",
            release_schema_hash="schema",
            epsilon_total=1.0,
            epsilon_numeric=1.0,
            epsilon_categorical=0.0,
            mechanism_summary="test",
            run_id="repro",
            maximum_cumulative_epsilon=2.0,
            randomness_mode="reproducibility",
        )
