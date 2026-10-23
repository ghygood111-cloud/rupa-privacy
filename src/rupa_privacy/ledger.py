"""Persistent, append-audited privacy accounting for production releases."""

import hashlib
import json
import math
import sqlite3
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import quote

from .exceptions import LedgerError


RELEASE_STATUSES = {"pending", "released", "failed", "cancelled"}


def _finite_ledger_number(name, value):
    if isinstance(value, bool):
        raise LedgerError(name + " must be a real number")
    try:
        number = float(value)
    except (TypeError, ValueError, OverflowError) as exc:
        raise LedgerError(name + " must be a real number") from exc
    if not math.isfinite(number):
        raise LedgerError(name + " must be finite")
    return number


@dataclass(frozen=True)
class LedgerReservation:
    run_id: str
    dataset_id: str
    dataset_version_hash: str
    expected_cumulative_epsilon: float
    status: str = "pending"


def _utc_now():
    return datetime.now(timezone.utc).isoformat()


def _event_hash(previous_hash, payload):
    encoded = json.dumps(
        payload, sort_keys=True, separators=(",", ":"), ensure_ascii=True
    ).encode("utf-8")
    return hashlib.sha256(previous_hash.encode("ascii") + encoded).hexdigest()


class PrivacyLedger:
    """SQLite ledger with serialized budget reservations and a hash-chained event log."""

    def __init__(self, path, create=True):
        self.path = Path(path).expanduser().resolve()
        self.read_only = not bool(create)
        if self.read_only:
            if not self.path.is_file():
                raise LedgerError("Privacy ledger does not exist: " + str(self.path))
        else:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            self._initialize()

    def _connect(self):
        if self.read_only:
            uri = "file:" + quote(self.path.as_posix(), safe="/:") + "?mode=ro"
            connection = sqlite3.connect(uri, timeout=30.0, uri=True)
        else:
            connection = sqlite3.connect(str(self.path), timeout=30.0)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA busy_timeout=30000")
        if self.read_only:
            connection.execute("PRAGMA query_only=ON")
        else:
            connection.execute("PRAGMA journal_mode=WAL")
            connection.execute("PRAGMA synchronous=FULL")
        return connection

    def _require_writable(self):
        if self.read_only:
            raise LedgerError("This privacy-ledger handle is read-only")

    def _initialize(self):
        with self._connect() as connection:
            connection.executescript(
                """
                CREATE TABLE IF NOT EXISTS releases (
                    sequence INTEGER PRIMARY KEY AUTOINCREMENT,
                    dataset_id TEXT NOT NULL,
                    dataset_version_hash TEXT NOT NULL,
                    privacy_unit_id TEXT NOT NULL,
                    adjacency TEXT NOT NULL,
                    release_schema_hash TEXT NOT NULL,
                    epsilon_total REAL NOT NULL,
                    epsilon_numeric REAL NOT NULL,
                    epsilon_categorical REAL NOT NULL,
                    mechanism_summary TEXT NOT NULL,
                    run_id TEXT NOT NULL UNIQUE,
                    timestamp_utc TEXT NOT NULL,
                    release_artifact_hash TEXT,
                    cumulative_epsilon REAL NOT NULL,
                    release_status TEXT NOT NULL,
                    randomness_mode TEXT NOT NULL,
                    failure_reason TEXT
                );
                CREATE INDEX IF NOT EXISTS releases_dataset_status
                    ON releases(dataset_id, release_status);
                CREATE TABLE IF NOT EXISTS ledger_events (
                    event_sequence INTEGER PRIMARY KEY AUTOINCREMENT,
                    run_id TEXT NOT NULL,
                    event_timestamp_utc TEXT NOT NULL,
                    event_payload TEXT NOT NULL,
                    previous_hash TEXT NOT NULL,
                    record_hash TEXT NOT NULL UNIQUE
                );
                """
            )

    @staticmethod
    def _row_payload(row):
        epsilon_total = _finite_ledger_number("stored epsilon_total", row["epsilon_total"])
        epsilon_numeric = _finite_ledger_number(
            "stored epsilon_numeric", row["epsilon_numeric"]
        )
        epsilon_categorical = _finite_ledger_number(
            "stored epsilon_categorical", row["epsilon_categorical"]
        )
        cumulative_epsilon = _finite_ledger_number(
            "stored cumulative_epsilon", row["cumulative_epsilon"]
        )
        return {
            "dataset_id": row["dataset_id"],
            "dataset_version_hash": row["dataset_version_hash"],
            "privacy_unit_id": row["privacy_unit_id"],
            "adjacency": row["adjacency"],
            "release_schema_hash": row["release_schema_hash"],
            "epsilon_total": epsilon_total,
            "epsilon_numeric": epsilon_numeric,
            "epsilon_categorical": epsilon_categorical,
            "mechanism_summary": row["mechanism_summary"],
            "run_id": row["run_id"],
            "timestamp_utc": row["timestamp_utc"],
            "release_artifact_hash": row["release_artifact_hash"],
            "cumulative_epsilon": cumulative_epsilon,
            "release_status": row["release_status"],
            "randomness_mode": row["randomness_mode"],
            "failure_reason": row["failure_reason"],
        }

    def _append_event(self, connection, row):
        last = connection.execute(
            "SELECT record_hash FROM ledger_events ORDER BY event_sequence DESC LIMIT 1"
        ).fetchone()
        previous_hash = last["record_hash"] if last else "0" * 64
        payload = self._row_payload(row)
        payload_text = json.dumps(
            payload, sort_keys=True, separators=(",", ":"), ensure_ascii=True
        )
        record_hash = _event_hash(previous_hash, payload)
        connection.execute(
            """
            INSERT INTO ledger_events(
                run_id, event_timestamp_utc, event_payload, previous_hash, record_hash
            ) VALUES (?, ?, ?, ?, ?)
            """,
            (row["run_id"], _utc_now(), payload_text, previous_hash, record_hash),
        )

    @staticmethod
    def _totals(connection, dataset_id):
        released = connection.execute(
            """
            SELECT COALESCE(SUM(epsilon_total), 0.0) AS value
            FROM releases WHERE dataset_id=? AND release_status='released'
            """,
            (dataset_id,),
        ).fetchone()["value"]
        pending = connection.execute(
            """
            SELECT COALESCE(SUM(epsilon_total), 0.0) AS value
            FROM releases WHERE dataset_id=? AND release_status='pending'
            """,
            (dataset_id,),
        ).fetchone()["value"]
        released = _finite_ledger_number("stored released epsilon", released)
        pending = _finite_ledger_number("stored pending epsilon", pending)
        if released < 0 or pending < 0:
            raise LedgerError("Stored privacy-ledger epsilon totals must be non-negative")
        return released, pending

    def begin_release(
        self,
        *,
        dataset_id,
        dataset_version_hash,
        privacy_unit_id,
        adjacency,
        release_schema_hash,
        epsilon_total,
        epsilon_numeric,
        epsilon_categorical,
        mechanism_summary,
        run_id,
        maximum_cumulative_epsilon,
        randomness_mode,
    ):
        self._require_writable()
        if randomness_mode != "production":
            raise LedgerError("Only production releases may reserve persistent budget")
        epsilon_total = _finite_ledger_number("epsilon_total", epsilon_total)
        epsilon_numeric = _finite_ledger_number("epsilon_numeric", epsilon_numeric)
        epsilon_categorical = _finite_ledger_number(
            "epsilon_categorical", epsilon_categorical
        )
        maximum_cumulative_epsilon = _finite_ledger_number(
            "maximum_cumulative_epsilon", maximum_cumulative_epsilon
        )
        if epsilon_total <= 0:
            raise LedgerError("epsilon_total must be positive")
        if epsilon_numeric < 0 or epsilon_categorical < 0:
            raise LedgerError("Group privacy budgets must be non-negative")
        if not math.isclose(
            epsilon_numeric + epsilon_categorical,
            epsilon_total,
            rel_tol=0.0,
            abs_tol=1e-12,
        ):
            raise LedgerError(
                "epsilon_numeric + epsilon_categorical must equal epsilon_total"
            )
        if maximum_cumulative_epsilon <= 0:
            raise LedgerError("maximum_cumulative_epsilon must be positive")
        connection = self._connect()
        try:
            connection.execute("BEGIN IMMEDIATE")
            if connection.execute(
                "SELECT 1 FROM releases WHERE run_id=?", (run_id,)
            ).fetchone():
                raise LedgerError("run_id is already present in the privacy ledger: " + run_id)
            released, pending = self._totals(connection, dataset_id)
            expected = released + pending + epsilon_total
            if not math.isfinite(expected):
                raise LedgerError("Projected cumulative epsilon must be finite")
            status = "pending"
            failure_reason = None
            cumulative = expected
            if expected > maximum_cumulative_epsilon + 1e-12:
                status = "failed"
                failure_reason = (
                    "Projected cumulative epsilon {0:.12g} exceeds maximum {1:.12g}".format(
                        expected, maximum_cumulative_epsilon
                    )
                )
                cumulative = released
            timestamp = _utc_now()
            connection.execute(
                """
                INSERT INTO releases(
                    dataset_id, dataset_version_hash, privacy_unit_id, adjacency,
                    release_schema_hash, epsilon_total, epsilon_numeric,
                    epsilon_categorical, mechanism_summary, run_id, timestamp_utc,
                    release_artifact_hash, cumulative_epsilon, release_status,
                    randomness_mode, failure_reason
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, NULL, ?, ?, ?, ?)
                """,
                (
                    dataset_id,
                    dataset_version_hash,
                    privacy_unit_id,
                    adjacency,
                    release_schema_hash,
                    epsilon_total,
                    epsilon_numeric,
                    epsilon_categorical,
                    mechanism_summary,
                    run_id,
                    timestamp,
                    cumulative,
                    status,
                    randomness_mode,
                    failure_reason,
                ),
            )
            row = connection.execute(
                "SELECT * FROM releases WHERE run_id=?", (run_id,)
            ).fetchone()
            self._append_event(connection, row)
            connection.commit()
            if status == "failed":
                raise LedgerError(failure_reason)
            return LedgerReservation(
                run_id=run_id,
                dataset_id=dataset_id,
                dataset_version_hash=dataset_version_hash,
                expected_cumulative_epsilon=expected,
            )
        except Exception:
            if connection.in_transaction:
                connection.rollback()
            raise
        finally:
            connection.close()

    def mark_released(self, run_id, release_artifact_hash):
        self._require_writable()
        if not release_artifact_hash:
            raise LedgerError("A release artifact hash is required before ledger commit")
        connection = self._connect()
        try:
            connection.execute("BEGIN IMMEDIATE")
            row = connection.execute(
                "SELECT * FROM releases WHERE run_id=?", (run_id,)
            ).fetchone()
            if row is None or row["release_status"] != "pending":
                raise LedgerError("Only a pending run can be committed as released")
            released, _ = self._totals(connection, row["dataset_id"])
            stored_epsilon = _finite_ledger_number(
                "stored epsilon_total", row["epsilon_total"]
            )
            cumulative = released + stored_epsilon
            if not math.isfinite(cumulative):
                raise LedgerError("Committed cumulative epsilon must be finite")
            connection.execute(
                """
                UPDATE releases
                SET release_status='released', release_artifact_hash=?,
                    cumulative_epsilon=?, failure_reason=NULL
                WHERE run_id=?
                """,
                (release_artifact_hash, cumulative, run_id),
            )
            updated = connection.execute(
                "SELECT * FROM releases WHERE run_id=?", (run_id,)
            ).fetchone()
            self._append_event(connection, updated)
            connection.commit()
            return self._row_payload(updated)
        except Exception:
            if connection.in_transaction:
                connection.rollback()
            raise
        finally:
            connection.close()

    def mark_failed(self, run_id, reason, status="failed"):
        self._require_writable()
        if status not in {"failed", "cancelled"}:
            raise LedgerError("Failure status must be failed or cancelled")
        connection = self._connect()
        try:
            connection.execute("BEGIN IMMEDIATE")
            row = connection.execute(
                "SELECT * FROM releases WHERE run_id=?", (run_id,)
            ).fetchone()
            if row is None:
                raise LedgerError("Cannot mark an unknown run as failed")
            if row["release_status"] != "pending":
                raise LedgerError("Only a pending run can transition to failure")
            released, _ = self._totals(connection, row["dataset_id"])
            connection.execute(
                """
                UPDATE releases
                SET release_status=?, cumulative_epsilon=?, failure_reason=?
                WHERE run_id=?
                """,
                (status, released, str(reason)[:2000], run_id),
            )
            updated = connection.execute(
                "SELECT * FROM releases WHERE run_id=?", (run_id,)
            ).fetchone()
            self._append_event(connection, updated)
            connection.commit()
            return self._row_payload(updated)
        except Exception:
            if connection.in_transaction:
                connection.rollback()
            raise
        finally:
            connection.close()

    def show(self, dataset_id=None):
        query = "SELECT * FROM releases"
        values = ()
        if dataset_id:
            query += " WHERE dataset_id=?"
            values = (dataset_id,)
        query += " ORDER BY sequence"
        with self._connect() as connection:
            return [self._row_payload(row) for row in connection.execute(query, values)]

    def check_budget(self, dataset_id, maximum_cumulative_epsilon, additional_epsilon=0.0):
        maximum_cumulative_epsilon = _finite_ledger_number(
            "maximum_cumulative_epsilon", maximum_cumulative_epsilon
        )
        additional_epsilon = _finite_ledger_number(
            "additional_epsilon", additional_epsilon
        )
        if maximum_cumulative_epsilon <= 0:
            raise LedgerError("maximum_cumulative_epsilon must be positive")
        if additional_epsilon < 0:
            raise LedgerError("additional_epsilon must be non-negative")
        with self._connect() as connection:
            released, pending = self._totals(connection, dataset_id)
        projected = released + pending + additional_epsilon
        if not math.isfinite(projected):
            raise LedgerError("Projected cumulative epsilon must be finite")
        return {
            "dataset_id": dataset_id,
            "released_epsilon": released,
            "pending_epsilon": pending,
            "additional_epsilon": additional_epsilon,
            "projected_epsilon": projected,
            "maximum_cumulative_epsilon": maximum_cumulative_epsilon,
            "allowed": projected <= maximum_cumulative_epsilon + 1e-12,
        }

    def verify(self):
        with self._connect() as connection:
            events = connection.execute(
                "SELECT * FROM ledger_events ORDER BY event_sequence"
            ).fetchall()
            previous_hash = "0" * 64
            last_payload = {}
            for event in events:
                payload = json.loads(event["event_payload"])
                expected = _event_hash(previous_hash, payload)
                if event["previous_hash"] != previous_hash or event["record_hash"] != expected:
                    raise LedgerError(
                        "Ledger hash-chain verification failed at event {0}".format(
                            event["event_sequence"]
                        )
                    )
                previous_hash = event["record_hash"]
                last_payload[event["run_id"]] = payload
            rows = connection.execute("SELECT * FROM releases").fetchall()
            for row in rows:
                current_payload = self._row_payload(row)
                if last_payload.get(row["run_id"]) != current_payload:
                    raise LedgerError(
                        "Ledger event payload does not match release record: "
                        + row["run_id"]
                    )
        return {
            "status": "PASS",
            "release_records": len(rows),
            "events": len(events),
            "head_hash": previous_hash,
        }
