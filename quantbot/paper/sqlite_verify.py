"""Read-only SQLite paper ledger verifier (Phase 3).

Opens ``paper_ledger.db`` read-only (URI ``mode=ro`` + ``PRAGMA query_only=ON``)
and validates the committed DB state from the typed tables. The verifier never
writes the DB and never touches VM / live output.

Two entry points:

  - :func:`verify_database` — the pure read-only check. Returns a ``VerifyResult``
    and writes NOTHING.
  - :func:`verify_and_publish` — the authoritative publisher. Pins one read-only
    SQLite snapshot for validation + digesting, then writes its OWN artifacts
    (``paper_verify_report.json`` + ``paper_verify_receipt.md`` +
    ``paper_verify_log.jsonl``) atomically next to the DB. This is the only
    component allowed to publish an authoritative paper status.

Authority model (ADR 0001): the committed DB and the accounting writer's returned
status code are RAW accounting artifacts / a runner status only. The single
authoritative paper status is the latest ``paper_verify_report.json`` for its exact
recorded SQLite snapshot digest; a paper run is trusted IFF that report's
``status == OK``. If the DB is mutated after an OK, the next verification recomputes
the consistency invariants + content digests from the then-current DB and fails
closed -> CORRUPT.

It is a parallel implementation to the JSONL verifier in ``verify.py``; it does
NOT reuse the JSONL snapshot / trusted-baseline authority logic. The committed DB
is the record; this verifier reports on it.

Funding coverage (after this PR):
  After the existing arithmetic verdict is decided, the verifier stamps
  ``funding_coverage`` / ``funding_coverage_verdict`` /
  ``funding_coverage_diagnostic_label`` onto the report dict via the shared
  ``check_funding_coverage_from_rows`` helper. The stamp is **additive**: it
  does NOT change ``status``, does NOT touch the connection mode (``ro`` /
  ``query_only=1``), and does NOT add any write to the DB. When the existing
  arithmetic verdict is not ``STATUS_OK`` the stamp collapses to ``FAIL`` /
  empty label; otherwise it follows the COMPLETE / NOT_REQUIRED vs PARTIAL /
  MISSING decision per the gate plan §4.

Funding source snapshots:
  The verifier reads writer-emitted ``funding_source_snapshots`` sidecars and,
  when a committed ledger batch carries DB-linked snapshot references, uses
  those DB references as the deterministic clean-carry selector. Directory scans
  remain diagnostic/provenance context only.

Statuses / exit codes:
  OK            0   DB verified consistent
  CONFIG_ERROR  3   DB/config identity invalid
  CORRUPT       4   a verification invariant failed
  PRE_START     5   valid DB, no committed eligible bars yet

Verifier v1 scope (see disclaimer ``VERIFIER_DISCLAIMER``): it validates SQLite
ledger integrity and internal accounting consistency. It does NOT independently
rederive OHLCV marks / unrealized PnL / exposure from source price data, and it
does NOT re-derive ``source_observation_digest`` from a canonical source JSON
(Phase 2 does not persist the full source observation row — only the consumed
subset). See ``docs/ADR/0001-paper-sqlite-ledger.md``.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import re
import sqlite3
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping

from quantbot.core.determinism import sha256_file
from quantbot.paper import (
    BASELINE_LABEL,
    PAPER_ENGINE_VERSION,
    SCHEMA_VERSION,
)
from quantbot.paper import ledger
from quantbot.paper.freshness import parse_bar_utc
from quantbot.paper.db import (
    DB_SCHEMA_VERSION,
    config_hash_from_row,
    connect_readonly,
    get_paper_db_path,
)
from quantbot.paper.lane_config_hash import config_hash_v2
from quantbot.paper.lane_identity import LaneIdentity
from quantbot.paper.funding_coverage import (
    check_funding_coverage_from_rows,
)
from quantbot.paper.funding_source_snapshot import (
    build_canonical_row_subset_digest,
    build_source_file_digest,
    clean_mode_decision_from_snapshot_v1,
    validate_funding_source_snapshot_envelope_v1,
)
from quantbot.paper.funding_source_bundle import (
    BUNDLE_REFUSAL_REASONS,
    resolve_funding_source_bundle,
)
from quantbot.paper.funding_status import (
    CAVEATED_ENGINE_SEMANTICS,
    CAVEATED_ENGINE_SEMANTICS_LABEL,
    CLEAN_NET_OF_CARRY,
    COVERAGE_COMPLETE,
    COVERAGE_NOT_REQUIRED,
    FAIL,
)

# ---------------------------------------------------------------------------
# Statuses / exit codes
# ---------------------------------------------------------------------------

STATUS_OK = "OK"
STATUS_CONFIG_ERROR = "CONFIG_ERROR"
STATUS_CORRUPT = "CORRUPT"
STATUS_PRE_START = "PRE_START"

FUNDING_SOURCE_SNAPSHOT_STATUS_MISSING = "missing"
FUNDING_SOURCE_SNAPSHOT_STATUS_PRESENT_VALID = "present_valid"
FUNDING_SOURCE_SNAPSHOT_STATUS_DIGEST_MISMATCH = "present_digest_mismatch"
FUNDING_SOURCE_SNAPSHOT_STATUS_SCHEMA_UNSUPPORTED = "present_schema_unsupported"
FUNDING_SOURCE_SNAPSHOT_STATUS_PAYLOAD_INVALID = "present_payload_invalid"
FUNDING_SOURCE_SNAPSHOT_STATUS_DB_OR_LANE_MISMATCH = "present_db_or_lane_mismatch"
FUNDING_SOURCE_SNAPSHOT_STATUS_PENDING_OR_ORPHANED = "present_pending_or_orphaned"
FUNDING_SOURCE_SNAPSHOT_STATUS_AMBIGUOUS_MULTIPLE = "present_ambiguous_multiple"

FUNDING_SOURCE_SNAPSHOT_DIAGNOSTIC_NOTE = (
    "Funding source snapshot read support is diagnostic/provenance-only. It does "
    "not change the arithmetic verifier status. CLEAN_NET_OF_CARRY is decided "
    "only by the strict funding_clean_carry_* gate."
)

FUNDING_CLEAN_CARRY_STATUS_CLEAN = "clean_net_of_carry"
FUNDING_CLEAN_CARRY_STATUS_CAVEATED = "caveated_engine_semantics"
FUNDING_CLEAN_CARRY_STATUS_REFUSED_MISSING_SNAPSHOT = "refused_missing_snapshot"
FUNDING_CLEAN_CARRY_STATUS_REFUSED_DIGEST_MISMATCH = "refused_digest_mismatch"
FUNDING_CLEAN_CARRY_STATUS_REFUSED_SCHEMA_UNSUPPORTED = "refused_schema_unsupported"
FUNDING_CLEAN_CARRY_STATUS_REFUSED_DB_OR_LANE_MISMATCH = (
    "refused_db_or_lane_mismatch"
)
FUNDING_CLEAN_CARRY_STATUS_REFUSED_PENDING_OR_ORPHANED = (
    "refused_pending_or_orphaned"
)
FUNDING_CLEAN_CARRY_STATUS_REFUSED_AMBIGUOUS_MULTIPLE = (
    "refused_ambiguous_multiple_snapshots"
)
FUNDING_CLEAN_CARRY_STATUS_REFUSED_SOURCE_COVERAGE = (
    "refused_source_coverage_issue"
)
FUNDING_CLEAN_CARRY_STATUS_REFUSED_RESUM_MISMATCH = "refused_resum_mismatch"
FUNDING_CLEAN_CARRY_STATUS_REFUSED_BUNDLE = "refused_bundle"

# Source-resolution modes for the clean-carry gate. ``live-current`` (default)
# resolves funding digests from the live, mutable CSVs and still detects current
# drift, exactly as before. ``bundle`` resolves from a pinned immutable,
# content-addressed source bundle so scheduled CSV refreshes cannot flip a
# recorded verdict (see funding_source_bundle + the immutable-bundle spec).
SOURCE_MODE_LIVE_CURRENT = "live-current"
SOURCE_MODE_BUNDLE = "bundle"
SOURCE_RESOLUTION_MODES = frozenset({SOURCE_MODE_LIVE_CURRENT, SOURCE_MODE_BUNDLE})

FUNDING_CLEAN_CARRY_NOTE = (
    "Arithmetic OK and complete source coverage are necessary but not sufficient "
    "for CLEAN_NET_OF_CARRY. The clean label requires one committed, DB-linked, "
    "digest-valid funding source snapshot plus an independent funding re-sum. "
    "Missing, pending, orphaned, ambiguous, or mismatched snapshots preserve "
    "CAVEATED_ENGINE_SEMANTICS."
)

FUNDING_CLEAN_CARRY_REASON_ARITHMETIC_NOT_OK = "funding_arithmetic_status_not_ok"
FUNDING_CLEAN_CARRY_REASON_SOURCE_COVERAGE_NOT_COMPLETE = (
    "funding_source_coverage_not_complete"
)
FUNDING_CLEAN_CARRY_REASON_AMBIGUOUS_MULTIPLE = (
    "funding_source_snapshot_ambiguous_multiple"
)
FUNDING_CLEAN_CARRY_REASON_PAYLOAD_INVALID = "funding_source_snapshot_payload_invalid"
FUNDING_CLEAN_CARRY_REASON_BATCH_WINDOW_MISMATCH = (
    "funding_source_batch_window_mismatch"
)
SOURCE_PATH_RESOLUTION_MODE_EXPLICIT_DATA_DIR = "explicit_data_dir"
SOURCE_PATH_RESOLUTION_MODE_SNAPSHOT_PROVENANCE = "snapshot_provenance"
SOURCE_PATH_RESOLUTION_MODE_UNAVAILABLE = "unavailable"
SOURCE_PATH_UNAVAILABLE_REASON = "source_path_unavailable"

EXIT_CODE: dict[str, int] = {
    STATUS_OK: 0,
    STATUS_CONFIG_ERROR: 3,
    STATUS_CORRUPT: 4,
    STATUS_PRE_START: 5,
}

VERIFIER_DISCLAIMER = (
    "Verifier v1 validates SQLite ledger integrity and internal accounting "
    "consistency. It does not independently rederive OHLCV marks/unrealized "
    "PnL/exposure from source price data."
)

# Authoritative-publication layer (ADR 0001 authority model). The committed DB and the
# writer's returned status code are RAW accounting artifacts / a runner status only. The
# single authoritative paper status is the latest paper_verify_report.json, written ONLY by
# this read-only verifier. The verifier reads the DB read-only and writes only its own
# paper_verify_* artifacts next to the DB (never the DB, never any runner artifact).
SQLITE_VERIFIER_VERSION = "1.0.0"
REPORT_FILE = "paper_verify_report.json"   # authoritative latest terminal report
RECEIPT_FILE = "paper_verify_receipt.md"   # human receipt for the latest verdict
LOG_FILE = "paper_verify_log.jsonl"        # append-only audit trail (NON-gating)

# Numeric tolerances
_ABS_TOL = 1e-6
_TIGHT_TOL = 1e-8

# Required tables / triggers / indexes expected from the Phase 1 substrate.
_REQUIRED_TABLES = [
    "paper_config",
    "ledger_batches",
    "ledger_events",
    "signal_snapshots",
    "fills",
    "trades",
    "funding",
    "position_snapshots",
    "position_snapshot_symbols",
    "equity_snapshots",
    "ledger_state",
    "open_positions",
]

_APPEND_ONLY_TABLES = [
    "paper_config",
    "ledger_events",
    "signal_snapshots",
    "fills",
    "trades",
    "funding",
    "position_snapshots",
    "position_snapshot_symbols",
    "equity_snapshots",
]

_REQUIRED_INDEXES = [
    "idx_ledger_events_event_type",
    "idx_ledger_events_bar_ts",
    "idx_ledger_events_symbol",
    "idx_ledger_events_batch_id",
]

# event_type -> typed table
_EVENT_TABLE: dict[str, str] = {
    "signal_snapshot": "signal_snapshots",
    "funding": "funding",
    "fill": "fills",
    "trade": "trades",
    "position_snapshot": "position_snapshots",
    "equity_snapshot": "equity_snapshots",
}

_EVENT_TYPES = list(_EVENT_TABLE.keys())

_HEX64 = re.compile(r"^[0-9a-f]{64}$")
_HEX16 = re.compile(r"^[0-9a-f]{16}$")


# ---------------------------------------------------------------------------
# Result container
# ---------------------------------------------------------------------------

@dataclass
class VerifyResult:
    status: str
    failures: list[str] = field(default_factory=list)
    report: dict[str, Any] = field(default_factory=dict)

    @property
    def exit_code(self) -> int:
        return EXIT_CODE[self.status]

    @property
    def ok(self) -> bool:
        return self.status == STATUS_OK


@dataclass(frozen=True)
class FundingSourcePathResolution:
    mode: str
    resolved_dir: Path | None
    available: bool

    def report_fields(self) -> dict[str, Any]:
        return {
            "resolved_funding_source_dir": (
                str(self.resolved_dir) if self.resolved_dir is not None else None
            ),
            "source_path_resolution_mode": self.mode,
            "source_path_available": self.available,
        }


# ---------------------------------------------------------------------------
# Small helpers
# ---------------------------------------------------------------------------

def _rows(conn: sqlite3.Connection, sql: str, params: tuple = ()) -> list[dict]:
    return [dict(r) for r in conn.execute(sql, params).fetchall()]


def _scalar(conn: sqlite3.Connection, sql: str, params: tuple = ()) -> Any:
    row = conn.execute(sql, params).fetchone()
    if row is None:
        return None
    return row[0]


def _column_exists(conn: sqlite3.Connection, table: str, column: str) -> bool:
    """True if *table* has *column*. Used to tolerate older DBs that predate an
    additive column (no ALTER/migration) — e.g. ``ledger_batches.lane_id``."""
    return any(
        r["name"] == column
        for r in conn.execute(f"PRAGMA table_info({table})").fetchall()
    )


def _close(value: float | None, expected: float | None, tol: float = _ABS_TOL) -> bool:
    if value is None or expected is None:
        return value is expected
    return abs(value - expected) <= tol


# ---------------------------------------------------------------------------
# Structural / identity validation
# ---------------------------------------------------------------------------

def _validate_schema_presence(conn: sqlite3.Connection) -> list[str]:
    """Return failures for missing tables, append-only triggers, or indexes."""
    failures: list[str] = []
    names = {
        r["name"]
        for r in conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table'"
        ).fetchall()
    }
    for tbl in _REQUIRED_TABLES:
        if tbl not in names:
            failures.append(f"Missing required table: {tbl}")

    trigger_names = {
        r["name"]
        for r in conn.execute(
            "SELECT name FROM sqlite_master WHERE type='trigger'"
        ).fetchall()
    }
    for tbl in _APPEND_ONLY_TABLES:
        for action in ("update", "delete"):
            trg = f"trg_{tbl}_deny_{action}"
            if trg not in trigger_names:
                failures.append(f"Missing append-only trigger: {trg}")

    index_names = {
        r["name"]
        for r in conn.execute(
            "SELECT name FROM sqlite_master WHERE type='index'"
        ).fetchall()
    }
    for idx in _REQUIRED_INDEXES:
        if idx not in index_names:
            failures.append(f"Missing required index: {idx}")

    return failures


def _validate_identity(conn: sqlite3.Connection) -> tuple[dict | None, list[str]]:
    """Validate paper_config identity. Returns (config_row, failures)."""
    failures: list[str] = []
    row = conn.execute("SELECT * FROM paper_config WHERE id = 1").fetchone()
    if row is None:
        return None, ["paper_config row (id=1) not found"]
    cfg = dict(row)

    if cfg.get("db_schema_version") != DB_SCHEMA_VERSION:
        failures.append(
            f"db_schema_version mismatch: stored={cfg.get('db_schema_version')!r}, "
            f"expected={DB_SCHEMA_VERSION!r}"
        )
    if cfg.get("paper_contract_version") != SCHEMA_VERSION:
        failures.append(
            f"paper_contract_version mismatch: stored={cfg.get('paper_contract_version')!r}, "
            f"expected={SCHEMA_VERSION!r}"
        )
    if cfg.get("paper_engine_version") != PAPER_ENGINE_VERSION:
        failures.append(
            f"paper_engine_version mismatch: stored={cfg.get('paper_engine_version')!r}, "
            f"expected={PAPER_ENGINE_VERSION!r}"
        )
    if cfg.get("baseline_label") != BASELINE_LABEL:
        failures.append(
            f"baseline_label mismatch: stored={cfg.get('baseline_label')!r}, "
            f"expected={BASELINE_LABEL!r}"
        )

    try:
        recomputed = config_hash_from_row(row)
    except Exception as exc:  # noqa: BLE001 - report, do not crash
        recomputed = None
        failures.append(f"config_hash recomputation failed: {type(exc).__name__}: {exc}")
    if recomputed is not None and cfg.get("config_hash") != recomputed:
        failures.append(
            f"config_hash mismatch: stored={cfg.get('config_hash')!r}, "
            f"recomputed={recomputed!r}"
        )

    # Dual-mode lane identity validation (runs after the v1 accounting checks above,
    # which apply in BOTH modes). v1 baseline DBs (no/NULL lane fields) add no failures.
    failures.extend(_validate_lane_identity(cfg))

    return cfg, failures


# The four core lane-identity columns. Any one non-NULL routes the row to v2/new-lane
# mode, where ALL four are required — so a partially-populated row fails closed instead
# of silently degrading to v1.
_LANE_IDENTITY_FIELDS = ("lane_id", "strategy_id", "strategy_version", "config_hash_v2")


def _validate_lane_identity(cfg: dict) -> list[str]:
    """Dual-mode lane identity validation (VERIFIER_DUAL_MODE_LANE_IDENTITY_PHASE3_PLAN).

    v1 mode — all four core lane fields NULL/absent: no additional checks, so the
    baseline behavior is byte-identical and the golden v1 hash path is untouched.

    v2/new-lane mode — any core lane field present: require all four, validate
    ``LaneIdentity`` (which rejects invalid and baseline-impersonating ids), and
    recompute ``config_hash_v2`` from the frozen v1 ``config_hash`` + identity,
    comparing to the stored value.

    ``pre_registration_hash`` must be NULL in this phase (generation is deferred), in
    either mode — a non-NULL value is never legitimate yet. ``ledger_batches.lane_id``
    is intentionally NOT checked here (batch stamping is a deferred phase).
    """
    failures: list[str] = []

    present = {f: cfg.get(f) for f in _LANE_IDENTITY_FIELDS}
    any_present = any(v is not None for v in present.values())

    # Deferred-generation guard: a stored pre_registration_hash is never valid yet.
    # This also fails the partial v1-mode case where only this column is set.
    if cfg.get("pre_registration_hash") is not None:
        failures.append(
            "pre_registration_hash must be NULL in this phase "
            f"(stored={cfg.get('pre_registration_hash')!r}); generation is deferred"
        )

    if not any_present:
        return failures  # v1 mode — nothing further to validate.

    # v2/new-lane mode — fail closed on any missing core field.
    missing = [f for f, v in present.items() if v is None]
    if missing:
        failures.append(
            "new-lane paper_config has partial lane identity; "
            f"missing non-NULL field(s): {missing}"
        )
        return failures  # cannot validate identity/hash without all fields.

    # Validate the lane identity model (rejects invalid + baseline-impersonating ids).
    try:
        identity = LaneIdentity(
            lane_id=present["lane_id"],
            strategy_id=present["strategy_id"],
            strategy_version=present["strategy_version"],
        )
    except Exception as exc:  # noqa: BLE001 - report, do not crash the verifier
        failures.append(f"invalid lane identity: {type(exc).__name__}: {exc}")
        return failures

    # Recompute config_hash_v2 from the frozen v1 accounting hash + identity.
    try:
        recomputed_v2 = config_hash_v2(cfg.get("config_hash"), identity)
    except Exception as exc:  # noqa: BLE001
        failures.append(
            f"config_hash_v2 recomputation failed: {type(exc).__name__}: {exc}"
        )
        return failures
    if present["config_hash_v2"] != recomputed_v2:
        failures.append(
            f"config_hash_v2 mismatch: stored={present['config_hash_v2']!r}, "
            f"recomputed={recomputed_v2!r}"
        )

    return failures


# ---------------------------------------------------------------------------
# Event-chain validation
# ---------------------------------------------------------------------------

def _validate_event_chain(conn: sqlite3.Connection) -> list[str]:
    failures: list[str] = []
    events = _rows(
        conn,
        "SELECT seq, batch_id, event_type, event_key, bar_ts, prev_seq "
        "FROM ledger_events ORDER BY seq",
    )
    if not events:
        return failures

    # Deterministic chain via prev_seq. seq gaps are NOT corruption — the chain is.
    prev: int | None = None
    seen_seq: set[int] = set()
    for i, ev in enumerate(events):
        seq = ev["seq"]
        if seq in seen_seq:
            failures.append(f"Duplicate event seq={seq}")
        seen_seq.add(seq)
        if i == 0:
            if ev["prev_seq"] is not None:
                failures.append(
                    f"First event seq={seq} has non-NULL prev_seq={ev['prev_seq']}"
                )
        else:
            if ev["prev_seq"] != prev:
                failures.append(
                    f"Event seq={seq} prev_seq={ev['prev_seq']} != immediately "
                    f"preceding seq {prev}"
                )
        prev = seq

    # Event type enum
    for ev in events:
        if ev["event_type"] not in _EVENT_TABLE:
            failures.append(
                f"Event seq={ev['seq']} has unknown event_type {ev['event_type']!r}"
            )

    # Unique event identity (event_type, event_key)
    identity_dupes = _rows(
        conn,
        "SELECT event_type, event_key, COUNT(*) AS cnt FROM ledger_events "
        "GROUP BY event_type, event_key HAVING cnt > 1",
    )
    for d in identity_dupes:
        failures.append(
            f"Duplicate event identity ({d['event_type']}, {d['event_key']}) x{d['cnt']}"
        )

    # 1:1 event <-> typed row.
    for et, table in _EVENT_TABLE.items():
        event_count = _scalar(
            conn,
            "SELECT COUNT(*) FROM ledger_events WHERE event_type = ?",
            (et,),
        )
        typed_count = _scalar(conn, f"SELECT COUNT(*) FROM {table}")
        if event_count != typed_count:
            failures.append(
                f"Event/typed count mismatch for {et}: events={event_count}, "
                f"typed={typed_count}"
            )
        # event without typed row
        orphan_events = _scalar(
            conn,
            f"""
            SELECT COUNT(*) FROM ledger_events e
            WHERE e.event_type = ?
              AND e.seq NOT IN (SELECT seq FROM {table})
            """,
            (et,),
        )
        if orphan_events:
            failures.append(f"{orphan_events} {et} event(s) without a {table} row")
        # typed row without matching event of this type
        orphan_typed = _scalar(
            conn,
            f"""
            SELECT COUNT(*) FROM {table} t
            WHERE t.seq NOT IN (
                SELECT seq FROM ledger_events WHERE event_type = ?
            )
            """,
            (et,),
        )
        if orphan_typed:
            failures.append(f"{orphan_typed} {table} row(s) without a matching {et} event")

    return failures


def _validate_batches(conn: sqlite3.Connection) -> list[str]:
    failures: list[str] = []
    batches = _rows(conn, "SELECT * FROM ledger_batches ORDER BY batch_id")
    for b in batches:
        bid = b["batch_id"]
        actual_count = _scalar(
            conn, "SELECT COUNT(*) FROM ledger_events WHERE batch_id = ?", (bid,)
        )
        # A committed batch must carry at least one event: an empty committed
        # batch is corruption, not a healthy no-op (the writer rolls back when
        # there is nothing to commit).
        if b["committed_at"] is not None and actual_count == 0:
            failures.append(f"Batch {bid} committed with zero events")
        if b["event_count"] != actual_count:
            failures.append(
                f"Batch {bid} event_count={b['event_count']} != actual "
                f"events {actual_count}"
            )
        # first/last event seq consistency (only for committed batches with events)
        if actual_count and b["committed_at"] is not None:
            seqs = _rows(
                conn,
                "SELECT MIN(seq) AS lo, MAX(seq) AS hi FROM ledger_events "
                "WHERE batch_id = ?",
                (bid,),
            )[0]
            if b["first_event_seq"] != seqs["lo"]:
                failures.append(
                    f"Batch {bid} first_event_seq={b['first_event_seq']} != "
                    f"min seq {seqs['lo']}"
                )
            if b["last_event_seq"] != seqs["hi"]:
                failures.append(
                    f"Batch {bid} last_event_seq={b['last_event_seq']} != "
                    f"max seq {seqs['hi']}"
                )
            # committed_bar_count == distinct equity bars in batch
            eq_bars = _scalar(
                conn,
                "SELECT COUNT(*) FROM equity_snapshots WHERE batch_id = ?",
                (bid,),
            )
            if b["committed_bar_count"] != eq_bars:
                failures.append(
                    f"Batch {bid} committed_bar_count={b['committed_bar_count']} != "
                    f"equity rows {eq_bars}"
                )
        # engine version / config hash consistency with paper_config
        cfg = conn.execute(
            "SELECT paper_engine_version, config_hash FROM paper_config WHERE id = 1"
        ).fetchone()
        if cfg is not None:
            if b["paper_engine_version"] != cfg["paper_engine_version"]:
                failures.append(
                    f"Batch {bid} paper_engine_version {b['paper_engine_version']!r} != "
                    f"config {cfg['paper_engine_version']!r}"
                )
            if b["config_hash"] != cfg["config_hash"]:
                failures.append(
                    f"Batch {bid} config_hash {b['config_hash']!r} != "
                    f"config {cfg['config_hash']!r}"
                )
    failures.extend(_validate_batch_lane_stamping(conn, batches))
    return failures


def _validate_batch_lane_stamping(
    conn: sqlite3.Connection, batches: list[dict]
) -> list[str]:
    """Dual-mode batch lane stamping check (LEDGER_BATCH_LANE_STAMPING_PHASE3_PLAN).

    Lane mode (``paper_config.lane_id`` non-NULL): the DB is a new lane, so it MUST
    have the additive ``ledger_batches.lane_id`` column and EVERY committed batch must be
    stamped with that exact lane id — a NULL or mismatched batch lane fails closed.

    v1 mode (``paper_config.lane_id`` NULL or its column absent): the baseline. An older
    DB without the batch ``lane_id`` column passes; a DB that has the column but leaves
    every batch NULL passes; a committed batch carrying a non-NULL lane in v1 mode is
    unexpected and fails closed. ``source_data_digest`` is out of scope.
    """
    failures: list[str] = []

    cfg_lane_id = None
    if _column_exists(conn, "paper_config", "lane_id"):
        row = conn.execute("SELECT lane_id FROM paper_config WHERE id = 1").fetchone()
        if row is not None:
            cfg_lane_id = row["lane_id"]
    batch_has_lane_col = _column_exists(conn, "ledger_batches", "lane_id")

    # Only committed batch rows are asserted; the writer commits a batch atomically
    # within its insert transaction, so a persisted row is committed in practice.
    committed = [b for b in batches if b.get("committed_at") is not None]

    if cfg_lane_id is not None:
        # Lane mode — require the column and full, exact stamping.
        if not batch_has_lane_col:
            failures.append(
                f"new-lane DB (paper_config.lane_id={cfg_lane_id!r}) but ledger_batches "
                "has no lane_id column; cannot verify batch lane stamping"
            )
            return failures
        for b in committed:
            bid = b["batch_id"]
            blane = b.get("lane_id")
            if blane is None:
                failures.append(
                    f"Batch {bid} lane_id is NULL but paper_config.lane_id="
                    f"{cfg_lane_id!r} (a new lane must stamp every batch)"
                )
            elif blane != cfg_lane_id:
                failures.append(
                    f"Batch {bid} lane_id {blane!r} != paper_config.lane_id "
                    f"{cfg_lane_id!r}"
                )
    elif batch_has_lane_col:
        # v1 mode with the column present — every committed batch must be NULL.
        for b in committed:
            blane = b.get("lane_id")
            if blane is not None:
                failures.append(
                    f"Batch {b['batch_id']} lane_id {blane!r} present but "
                    "paper_config.lane_id is NULL (a v1/baseline DB must not stamp "
                    "batch lanes)"
                )
    # else: v1 mode, no batch lane column at all — legacy DB, nothing to check.

    return failures


# ---------------------------------------------------------------------------
# Accounting-invariant validation
# ---------------------------------------------------------------------------

def _validate_arithmetic(
    conn: sqlite3.Connection, cfg: dict
) -> list[str]:
    failures: list[str] = []
    fee_bps = float(cfg["fee_bps"])
    fee_rate = fee_bps / 10_000.0
    forward_start = cfg["forward_start_ts"]
    notional = float(cfg["notional_usd"])

    # --- fills: no fill before forward_start_ts; fee arithmetic; fixed-notional baseline
    # The forward-start floor is enforced on the signal bar (the bar that produced
    # the order); the T+1 fill timestamp is derived from the next available bar and
    # is intentionally not floored here (it can precede the signal bar in out-of-
    # order/synthetic data) — this matches the Phase 2 writer reconcile check.
    fills = _rows(conn, "SELECT * FROM fills")
    # Parse the boundary once; compare instants, not raw strings. A boundary fill stores a
    # naive signal_bar_ts ('...T00:00:00') while forward_start_ts carries a trailing Z, so a
    # lexicographic compare would wrongly flag a fill AT forward_start_ts as before it.
    forward_start_dt = parse_bar_utc(forward_start)
    for f in fills:
        try:
            before_boundary = parse_bar_utc(f["signal_bar_ts"]) < forward_start_dt
        except (TypeError, ValueError):
            before_boundary = True  # unparseable signal_bar_ts -> fail closed
        if before_boundary:
            failures.append(
                f"Fill {f['fill_id']} signal_bar_ts {f['signal_bar_ts']} "
                f"< forward_start_ts {forward_start}"
            )
        expected_fee = f["fill_price"] * f["qty"] * fee_rate
        if not _close(f["fee"], expected_fee):
            failures.append(
                f"Fill {f['fill_id']} fee {f['fee']:.8f} != expected "
                f"{expected_fee:.8f}"
            )
        # fixed-notional baseline: no shorts (entry=BUY/exit=SELL), positive qty
        if f["qty"] <= 0:
            failures.append(f"Fill {f['fill_id']} non-positive qty {f['qty']}")
        if f["kind"] == "entry" and f["side"] != "BUY":
            failures.append(
                f"Fill {f['fill_id']} entry side {f['side']} != BUY (short detected)"
            )
        if f["kind"] == "exit" and f["side"] != "SELL":
            failures.append(
                f"Fill {f['fill_id']} exit side {f['side']} != SELL (short detected)"
            )
        # fixed-notional, no compounding: entry notional == config notional
        if f["kind"] == "entry":
            entry_notional = f["fill_price"] * f["qty"]
            if not _close(entry_notional, notional, tol=1e-4):
                failures.append(
                    f"Fill {f['fill_id']} entry notional {entry_notional:.6f} != "
                    f"fixed notional {notional:.6f} (compounding/sizing drift)"
                )

    # NOTE: trade lifecycle arithmetic lives in _validate_trades (it derives
    # gross/fees/funding from the underlying fills + funding ledger, not from the
    # trade row's own self-consistent fields). Equity cumulative reconciliation
    # lives in _validate_equity_cumulative (it recomputes realized/fees/funding
    # from history rather than trusting the equity row's own fields).

    # --- funding: amount arithmetic (when rate available)
    funding_rows = _rows(conn, "SELECT * FROM funding")
    for fr in funding_rows:
        if fr["rate_available"]:
            expected_amount = fr["notional_usd"] * fr["funding_rate"]
            if not _close(fr["funding_amount"], expected_amount):
                failures.append(
                    f"Funding {fr['funding_id']} amount {fr['funding_amount']:.8f} != "
                    f"notional*rate {expected_amount:.8f}"
                )
        else:
            if not _close(fr["funding_amount"], 0.0):
                failures.append(
                    f"Funding {fr['funding_id']} amount {fr['funding_amount']:.8f} != 0 "
                    f"with rate_available=0"
                )

    return failures


def _validate_trades(conn: sqlite3.Connection) -> list[str]:
    """Verify the full trade lifecycle from the underlying fills + funding ledger.

    A trade row is NOT trusted on its own fields: every component is re-derived
    from the entry/exit fills it references and from the funding ledger for the
    held interval. Fabricated trades (fake fill ids, arbitrary gross/funding)
    therefore fail even when the trade row is internally self-consistent.
    """
    failures: list[str] = []
    fills_by_id = {f["fill_id"]: f for f in _rows(conn, "SELECT * FROM fills")}
    trades = _rows(conn, "SELECT * FROM trades")

    for t in trades:
        tid = t["trade_id"]
        entry = fills_by_id.get(t["entry_fill_id"])
        exit_ = fills_by_id.get(t["exit_fill_id"])

        if entry is None:
            failures.append(
                f"Trade {tid} entry_fill_id {t['entry_fill_id']!r} not found in fills"
            )
        if exit_ is None:
            failures.append(
                f"Trade {tid} exit_fill_id {t['exit_fill_id']!r} not found in fills"
            )

        if entry is not None:
            if entry["kind"] != "entry" or entry["side"] != "BUY":
                failures.append(
                    f"Trade {tid} entry fill {entry['fill_id']} is not (entry, BUY): "
                    f"kind={entry['kind']!r}, side={entry['side']!r}"
                )
            if entry["symbol"] != t["symbol"]:
                failures.append(
                    f"Trade {tid} entry fill symbol {entry['symbol']!r} != trade "
                    f"symbol {t['symbol']!r}"
                )
            if not _close(t["qty"], entry["qty"], tol=_TIGHT_TOL):
                failures.append(
                    f"Trade {tid} qty {t['qty']} != entry fill qty {entry['qty']}"
                )
        if exit_ is not None:
            if exit_["kind"] != "exit" or exit_["side"] != "SELL":
                failures.append(
                    f"Trade {tid} exit fill {exit_['fill_id']} is not (exit, SELL): "
                    f"kind={exit_['kind']!r}, side={exit_['side']!r}"
                )
            if exit_["symbol"] != t["symbol"]:
                failures.append(
                    f"Trade {tid} exit fill symbol {exit_['symbol']!r} != trade "
                    f"symbol {t['symbol']!r}"
                )
            if not _close(t["qty"], exit_["qty"], tol=_TIGHT_TOL):
                failures.append(
                    f"Trade {tid} qty {t['qty']} != exit fill qty {exit_['qty']}"
                )

        if entry is not None and exit_ is not None:
            # gross_pnl derived from fill prices (long-only baseline).
            expected_gross = (exit_["fill_price"] - entry["fill_price"]) * t["qty"]
            if not _close(t["gross_pnl"], expected_gross):
                failures.append(
                    f"Trade {tid} gross_pnl {t['gross_pnl']:.8f} != "
                    f"(exit_price-entry_price)*qty {expected_gross:.8f}"
                )
            # fees = entry fee + exit fee.
            expected_fees = entry["fee"] + exit_["fee"]
            if not _close(t["fees"], expected_fees):
                failures.append(
                    f"Trade {tid} fees {t['fees']:.8f} != entry_fee+exit_fee "
                    f"{expected_fees:.8f}"
                )

        # funding = aggregation of the funding ledger over the held interval
        # (entry_bar_ts, exit_bar_ts] for this symbol (v1 semantics: a single
        # position per symbol, so the windows of sequential trades are disjoint).
        agg = _scalar(
            conn,
            """
            SELECT COALESCE(SUM(funding_amount), 0.0) FROM funding
            WHERE symbol = ? AND bar_ts > ? AND bar_ts <= ?
            """,
            (t["symbol"], t["entry_bar_ts"], t["exit_bar_ts"]),
        )
        if not _close(t["funding"], agg):
            failures.append(
                f"Trade {tid} funding {t['funding']:.8f} != funding-ledger "
                f"aggregation over ({t['entry_bar_ts']}, {t['exit_bar_ts']}] "
                f"{agg:.8f}"
            )

        # net = gross - fees - funding (using the trade's own components).
        expected_net = t["gross_pnl"] - t["fees"] - t["funding"]
        if not _close(t["net_pnl"], expected_net):
            failures.append(
                f"Trade {tid} net_pnl {t['net_pnl']:.8f} != gross-fees-funding "
                f"{expected_net:.8f}"
            )

    return failures


def _validate_equity_cumulative(conn: sqlite3.Connection, cfg: dict) -> list[str]:
    """Reconcile each equity row's cumulative fields against ledger history.

    The equity row's realized_gross_pnl / fees_cum / funding_cum are NOT trusted:
    they are recomputed from the trade / fill / funding ledgers up to each bar, so
    a coordinated mutation of realized PnL + equity + peak cannot pass. The
    unrealized mark is taken from the row as-is (the verifier does not rederive
    OHLCV marks — see VERIFIER_DISCLAIMER), but every other input is rederived.

    Cumulative semantics match the engine's per-bar ordering: the equity snapshot
    for bar B is taken PRE-fill, so it reflects fills/realized strictly before B,
    and funding accrued up to and including B.
    """
    failures: list[str] = []
    initial_equity = float(cfg["initial_equity_usd"])
    eq = _rows(conn, "SELECT * FROM equity_snapshots ORDER BY bar_ts")
    peak = initial_equity
    for e in eq:
        bar = e["bar_ts"]
        realized = _scalar(
            conn,
            "SELECT COALESCE(SUM(gross_pnl), 0.0) FROM trades WHERE exit_bar_ts < ?",
            (bar,),
        )
        fees_cum = _scalar(
            conn,
            "SELECT COALESCE(SUM(fee), 0.0) FROM fills WHERE signal_bar_ts < ?",
            (bar,),
        )
        funding_cum = _scalar(
            conn,
            "SELECT COALESCE(SUM(funding_amount), 0.0) FROM funding WHERE bar_ts <= ?",
            (bar,),
        )
        if not _close(e["realized_gross_pnl"], realized):
            failures.append(
                f"Equity@{bar} realized_gross_pnl {e['realized_gross_pnl']:.8f} != "
                f"SUM(trades.gross_pnl WHERE exit_bar_ts<{bar}) {realized:.8f}"
            )
        if not _close(e["fees_cum"], fees_cum):
            failures.append(
                f"Equity@{bar} fees_cum {e['fees_cum']:.8f} != "
                f"SUM(fills.fee WHERE signal_bar_ts<{bar}) {fees_cum:.8f}"
            )
        if not _close(e["funding_cum"], funding_cum):
            failures.append(
                f"Equity@{bar} funding_cum {e['funding_cum']:.8f} != "
                f"SUM(funding WHERE bar_ts<={bar}) {funding_cum:.8f}"
            )
        expected_equity = (
            initial_equity + realized - fees_cum - funding_cum + e["unrealized_pnl"]
        )
        if not _close(e["equity"], expected_equity):
            failures.append(
                f"Equity@{bar} {e['equity']:.8f} != initial+realized-fees-funding+"
                f"unrealized {expected_equity:.8f} (recomputed from history)"
            )
        if expected_equity > peak:
            peak = expected_equity
        expected_dd = (peak - expected_equity) / peak if peak > 0 else 0.0
        if not _close(e["drawdown"], expected_dd):
            failures.append(
                f"Drawdown@{bar} {e['drawdown']:.8f} != expected {expected_dd:.8f}"
            )

    return failures


def _validate_state(conn: sqlite3.Connection, cfg: dict) -> list[str]:
    failures: list[str] = []
    state = conn.execute("SELECT * FROM ledger_state WHERE id = 1").fetchone()
    if state is None:
        return ["ledger_state row (id=1) not found"]
    state = dict(state)

    eq = _rows(conn, "SELECT * FROM equity_snapshots ORDER BY seq")
    if not eq:
        return failures

    initial_equity = float(cfg["initial_equity_usd"])

    # watermark equals the latest committed equity bar
    latest_bar = max(e["bar_ts"] for e in eq)
    if state["watermark_bar_ts"] != latest_bar:
        failures.append(
            f"ledger_state.watermark_bar_ts {state['watermark_bar_ts']!r} != latest "
            f"committed equity bar {latest_bar!r}"
        )

    # Accumulators are POST-everything (the engine applies a bar's fills after its
    # pre-fill equity snapshot), so they reconcile against the full ledger-table
    # sums, not the final (pre-fill) equity snapshot.
    total_fees = _scalar(conn, "SELECT COALESCE(SUM(fee), 0.0) FROM fills")
    total_realized = _scalar(conn, "SELECT COALESCE(SUM(gross_pnl), 0.0) FROM trades")
    total_funding = _scalar(
        conn, "SELECT COALESCE(SUM(funding_amount), 0.0) FROM funding"
    )
    if not _close(state["realized_gross"], total_realized):
        failures.append(
            f"ledger_state.realized_gross {state['realized_gross']:.8f} != "
            f"SUM(trades.gross_pnl) {total_realized:.8f}"
        )
    if not _close(state["fees_cum"], total_fees):
        failures.append(
            f"ledger_state.fees_cum {state['fees_cum']:.8f} != "
            f"SUM(fills.fee) {total_fees:.8f}"
        )
    if not _close(state["funding_cum"], total_funding):
        failures.append(
            f"ledger_state.funding_cum {state['funding_cum']:.8f} != "
            f"SUM(funding.funding_amount) {total_funding:.8f}"
        )

    # peak equity matches running max over equity snapshots (and initial)
    peak = initial_equity
    for e in eq:
        if e["equity"] > peak:
            peak = e["equity"]
    if not _close(state["peak_equity"], peak):
        failures.append(
            f"ledger_state.peak_equity {state['peak_equity']:.8f} != reconstructed "
            f"peak {peak:.8f}"
        )

    return failures


def _validate_open_positions(conn: sqlite3.Connection) -> list[str]:
    """Reconstruct the open book from the ledger and compare to the cache.

    Every field the engine needs to resume a position across runs is rederived
    and checked: qty, entry_price, entry_fill_id, entry_bar_ts, entry_fill_ts,
    entry_fee, funding_accrued and hold_bars. The reconstruction is taken from
    the fill book, the funding ledger and the equity bar count — NOT from the
    open_positions row — so a tampered restart cache is caught.
    """
    failures: list[str] = []

    # Reconstruct open book by replaying fills in (signal-bar, seq) order.
    fills = _rows(conn, "SELECT * FROM fills ORDER BY signal_bar_ts, seq")
    book: dict[str, dict] = {}
    for f in fills:
        sym = f["symbol"]
        if f["kind"] == "entry":
            book[sym] = {
                "qty": f["qty"],
                "entry_price": f["fill_price"],
                "entry_fill_id": f["fill_id"],
                "entry_bar_ts": f["signal_bar_ts"],
                "entry_fill_ts": f["fill_ts"],
                "entry_fee": f["fee"],
            }
        elif f["kind"] == "exit":
            book.pop(sym, None)

    db_positions = {
        r["symbol"]: r for r in _rows(conn, "SELECT * FROM open_positions")
    }

    # symbols present in one but not the other
    for sym in db_positions.keys() - book.keys():
        failures.append(f"open_positions has {sym} not in reconstructed open book")
    for sym in book.keys() - db_positions.keys():
        failures.append(f"Reconstructed open book has {sym} missing from open_positions")

    for sym in db_positions.keys() & book.keys():
        dbp = db_positions[sym]
        recon = book[sym]
        if not _close(dbp["qty"], recon["qty"], tol=_TIGHT_TOL):
            failures.append(f"open_positions {sym} qty {dbp['qty']} != {recon['qty']}")
        if not _close(dbp["entry_price"], recon["entry_price"], tol=_TIGHT_TOL):
            failures.append(
                f"open_positions {sym} entry_price {dbp['entry_price']} != "
                f"{recon['entry_price']}"
            )
        if dbp["entry_fill_id"] != recon["entry_fill_id"]:
            failures.append(
                f"open_positions {sym} entry_fill_id {dbp['entry_fill_id']!r} != "
                f"{recon['entry_fill_id']!r}"
            )
        if dbp["entry_bar_ts"] != recon["entry_bar_ts"]:
            failures.append(
                f"open_positions {sym} entry_bar_ts {dbp['entry_bar_ts']!r} != "
                f"{recon['entry_bar_ts']!r}"
            )
        if dbp["entry_fill_ts"] != recon["entry_fill_ts"]:
            failures.append(
                f"open_positions {sym} entry_fill_ts {dbp['entry_fill_ts']!r} != "
                f"{recon['entry_fill_ts']!r}"
            )
        # entry_fee rebuilt from the entry fill the engine resumes against.
        if not _close(dbp["entry_fee"], recon["entry_fee"], tol=_TIGHT_TOL):
            failures.append(
                f"open_positions {sym} entry_fee {dbp['entry_fee']} != entry fill fee "
                f"{recon['entry_fee']}"
            )
        # hold_bars = number of committed equity bars after the entry signal bar
        # (the engine increments hold_bars on every PRE-fill snapshot the position
        # is in the book, i.e. bars strictly after entry_bar_ts).
        recon_hold = _scalar(
            conn,
            "SELECT COUNT(*) FROM equity_snapshots WHERE bar_ts > ?",
            (recon["entry_bar_ts"],),
        )
        if dbp["hold_bars"] != recon_hold:
            failures.append(
                f"open_positions {sym} hold_bars {dbp['hold_bars']} != equity bars "
                f"after entry {recon_hold}"
            )
        # funding_accrued = funding ledger for this symbol since the entry bar
        # (no exit-tail yet — the position is still open).
        recon_funding = _scalar(
            conn,
            "SELECT COALESCE(SUM(funding_amount), 0.0) FROM funding "
            "WHERE symbol = ? AND bar_ts > ?",
            (sym, recon["entry_bar_ts"]),
        )
        if not _close(dbp["funding_accrued"], recon_funding):
            failures.append(
                f"open_positions {sym} funding_accrued {dbp['funding_accrued']:.8f} != "
                f"funding ledger since entry {recon_funding:.8f}"
            )

    return failures


def _validate_snapshot_identity(conn: sqlite3.Connection) -> list[str]:
    """Validate bar_commit_id agreement across all rows for a bar + digest form.

    NOTE: the full canonical source observation JSON is NOT persisted by the
    Phase 2 writer (only the consumed subset), so the verifier cannot
    independently recompute ``source_observation_digest`` from source data. It
    validates well-formedness and cross-row commit-id agreement instead. See
    VERIFIER_DISCLAIMER.
    """
    failures: list[str] = []

    snaps = _rows(
        conn,
        "SELECT bar_ts, snapshot_id, bar_commit_id, source_observation_digest "
        "FROM signal_snapshots",
    )
    commit_by_bar: dict[str, str] = {}
    for s in snaps:
        commit_by_bar[s["bar_ts"]] = s["bar_commit_id"]
        # writer v1 invariant: snapshot_id == bar_commit_id
        if s["snapshot_id"] != s["bar_commit_id"]:
            failures.append(
                f"signal_snapshot@{s['bar_ts']} snapshot_id {s['snapshot_id']!r} != "
                f"bar_commit_id {s['bar_commit_id']!r}"
            )
        if not _HEX16.match(s["bar_commit_id"] or ""):
            failures.append(
                f"signal_snapshot@{s['bar_ts']} bar_commit_id {s['bar_commit_id']!r} "
                f"is not a 16-char hex digest"
            )
        if not _HEX64.match(s["source_observation_digest"] or ""):
            failures.append(
                f"signal_snapshot@{s['bar_ts']} source_observation_digest "
                f"{s['source_observation_digest']!r} is not a 64-char hex digest"
            )

    # Cross-row bar_commit_id agreement: every typed row for a bar must carry the
    # same bar_commit_id as that bar's signal snapshot.
    checks = [
        ("funding", "bar_ts"),
        ("fills", "signal_bar_ts"),
        ("trades", "exit_bar_ts"),
        ("position_snapshots", "bar_ts"),
        ("equity_snapshots", "bar_ts"),
    ]
    for table, bar_col in checks:
        for r in _rows(conn, f"SELECT {bar_col} AS bar, bar_commit_id FROM {table}"):
            expected = commit_by_bar.get(r["bar"])
            if expected is None:
                failures.append(
                    f"{table} row at bar {r['bar']!r} has no matching signal snapshot"
                )
            elif r["bar_commit_id"] != expected:
                failures.append(
                    f"{table} row at bar {r['bar']!r} bar_commit_id "
                    f"{r['bar_commit_id']!r} != signal snapshot {expected!r}"
                )

    return failures


# ---------------------------------------------------------------------------
# Durable event <-> typed-row relationship validation
# ---------------------------------------------------------------------------

# event_type -> (typed table, natural-key column or None, bar column, symbol column)
_TYPED_KEY: dict[str, tuple[str, str | None, str, str | None]] = {
    "signal_snapshot": ("signal_snapshots", "snapshot_id", "bar_ts", None),
    "funding": ("funding", "funding_id", "bar_ts", "symbol"),
    "fill": ("fills", "fill_id", "signal_bar_ts", "symbol"),
    "trade": ("trades", "trade_id", "exit_bar_ts", "symbol"),
    "position_snapshot": ("position_snapshots", None, "bar_ts", None),
    "equity_snapshot": ("equity_snapshots", None, "bar_ts", None),
}


def _validate_event_typed_consistency(conn: sqlite3.Connection) -> list[str]:
    """Validate that each event's key/batch/bar/symbol match its typed row.

    Beyond seq/type presence (already covered by the event-chain check) this
    confirms the event_key equals the typed row's natural key, that the event's
    batch_id / bar_ts / symbol agree with the typed row, so an event cannot be
    silently re-pointed at a different row of the same type.
    """
    failures: list[str] = []
    for et, (table, keycol, barcol, symcol) in _TYPED_KEY.items():
        rows = _rows(
            conn,
            f"""
            SELECT e.seq AS eseq, e.event_key AS ekey, e.bar_ts AS ebar,
                   e.symbol AS esym, e.batch_id AS ebatch, t.*
            FROM ledger_events e
            JOIN {table} t ON t.seq = e.seq
            WHERE e.event_type = ?
            """,
            (et,),
        )
        for r in rows:
            seq = r["eseq"]
            if keycol is not None:
                natural = r[keycol]
            else:
                prefix = "pos" if et == "position_snapshot" else "eq"
                natural = f"{prefix}|{r['bar_ts']}"
            if r["ekey"] != natural:
                failures.append(
                    f"{et} event seq={seq} event_key {r['ekey']!r} != natural key "
                    f"{natural!r}"
                )
            if r["ebatch"] != r["batch_id"]:
                failures.append(
                    f"{et} event seq={seq} batch_id {r['ebatch']} != typed row "
                    f"batch_id {r['batch_id']}"
                )
            if r["ebar"] != r[barcol]:
                failures.append(
                    f"{et} event seq={seq} bar_ts {r['ebar']!r} != typed row "
                    f"{barcol} {r[barcol]!r}"
                )
            if symcol is not None:
                if r["esym"] != r[symcol]:
                    failures.append(
                        f"{et} event seq={seq} symbol {r['esym']!r} != typed row "
                        f"symbol {r[symcol]!r}"
                    )
            else:
                if r["esym"] is not None:
                    failures.append(
                        f"{et} event seq={seq} symbol {r['esym']!r} should be NULL"
                    )
    return failures


def _validate_position_snapshots(conn: sqlite3.Connection) -> list[str]:
    """Validate each position_snapshot against its child symbol rows + the book.

    For every position_snapshot: ``num_open`` equals both the open_symbols JSON
    length and the child-row count; the child symbols equal the open_symbols
    JSON; and each child row's (qty, entry_price, entry_fill_id, entry_bar_ts)
    matches the pre-fill open book reconstructed from the fill ledger at that bar.

    The child ``unrealized_gross`` / position exposure are NOT re-derived (they
    depend on OHLCV marks the verifier does not rederive — see
    VERIFIER_DISCLAIMER); only the structural / fill-derived fields are checked.
    """
    failures: list[str] = []
    ps_rows = _rows(conn, "SELECT * FROM position_snapshots ORDER BY bar_ts")
    children: dict[int, list[dict]] = {}
    for c in _rows(conn, "SELECT * FROM position_snapshot_symbols"):
        children.setdefault(c["snapshot_seq"], []).append(c)

    fills_by_bar: dict[str, list[dict]] = {}
    for f in _rows(conn, "SELECT * FROM fills ORDER BY signal_bar_ts, seq"):
        fills_by_bar.setdefault(f["signal_bar_ts"], []).append(f)

    book: dict[str, dict] = {}
    for ps in ps_rows:
        bar = ps["bar_ts"]
        try:
            open_symbols = json.loads(ps["open_symbols"])
        except (ValueError, TypeError):
            failures.append(f"position_snapshot@{bar} open_symbols is not valid JSON")
            open_symbols = []
        child = children.get(ps["seq"], [])
        child_syms = sorted(c["symbol"] for c in child)

        if ps["num_open"] != len(open_symbols):
            failures.append(
                f"position_snapshot@{bar} num_open {ps['num_open']} != "
                f"len(open_symbols) {len(open_symbols)}"
            )
        if ps["num_open"] != len(child):
            failures.append(
                f"position_snapshot@{bar} num_open {ps['num_open']} != "
                f"position_snapshot_symbols count {len(child)}"
            )
        if child_syms != sorted(open_symbols):
            failures.append(
                f"position_snapshot@{bar} child symbols {child_syms} != "
                f"open_symbols {sorted(open_symbols)}"
            )
        # open_symbols must equal the reconstructed pre-fill book at this bar.
        if sorted(book.keys()) != sorted(open_symbols):
            failures.append(
                f"position_snapshot@{bar} open_symbols {sorted(open_symbols)} != "
                f"reconstructed open book {sorted(book.keys())}"
            )

        child_by_sym = {c["symbol"]: c for c in child}
        for sym, pos in book.items():
            c = child_by_sym.get(sym)
            if c is None:
                continue  # already flagged via child_syms mismatch
            if not _close(c["qty"], pos["qty"], tol=_TIGHT_TOL):
                failures.append(
                    f"position_snapshot@{bar} {sym} qty {c['qty']} != {pos['qty']}"
                )
            if not _close(c["entry_price"], pos["entry_price"], tol=_TIGHT_TOL):
                failures.append(
                    f"position_snapshot@{bar} {sym} entry_price {c['entry_price']} != "
                    f"{pos['entry_price']}"
                )
            if c["entry_fill_id"] != pos["entry_fill_id"]:
                failures.append(
                    f"position_snapshot@{bar} {sym} entry_fill_id "
                    f"{c['entry_fill_id']!r} != {pos['entry_fill_id']!r}"
                )
            if c["entry_bar_ts"] != pos["entry_bar_ts"]:
                failures.append(
                    f"position_snapshot@{bar} {sym} entry_bar_ts "
                    f"{c['entry_bar_ts']!r} != {pos['entry_bar_ts']!r}"
                )

        # Advance the book by this bar's fills (exits then entries, matching the
        # engine) so the NEXT bar's pre-fill snapshot reconstructs correctly.
        bar_fills = fills_by_bar.get(bar, [])
        for f in bar_fills:
            if f["kind"] == "exit":
                book.pop(f["symbol"], None)
        for f in bar_fills:
            if f["kind"] == "entry":
                book[f["symbol"]] = {
                    "qty": f["qty"],
                    "entry_price": f["fill_price"],
                    "entry_fill_id": f["fill_id"],
                    "entry_bar_ts": f["signal_bar_ts"],
                }

    return failures


def _validate_foreign_keys(conn: sqlite3.Connection) -> list[str]:
    """Run SQLite's own foreign-key integrity check over the whole DB."""
    failures: list[str] = []
    for row in conn.execute("PRAGMA foreign_key_check").fetchall():
        # columns: (table, rowid, parent, fkid)
        failures.append(
            f"Foreign key violation: table {row[0]!r} rowid {row[1]} -> "
            f"{row[2]!r} (fk #{row[3]})"
        )
    return failures


# ---------------------------------------------------------------------------
# PRE_START state validation
# ---------------------------------------------------------------------------

_LEDGER_TABLES = [
    "ledger_batches",
    "ledger_events",
    "signal_snapshots",
    "fills",
    "trades",
    "funding",
    "position_snapshots",
    "position_snapshot_symbols",
    "equity_snapshots",
    "open_positions",
]


def _ledger_table_counts(conn: sqlite3.Connection) -> dict[str, int]:
    return {t: _scalar(conn, f"SELECT COUNT(*) FROM {t}") for t in _LEDGER_TABLES}


def _validate_initial_state(conn: sqlite3.Connection, cfg: dict) -> list[str]:
    """A PRE_START DB must hold a valid INITIAL ledger_state singleton.

    Corrupt pre-start state (non-NULL watermark, non-zero accumulators, wrong
    peak) must NOT be reported as PRE_START — it is CORRUPT.
    """
    failures: list[str] = []
    state = conn.execute("SELECT * FROM ledger_state WHERE id = 1").fetchone()
    if state is None:
        return ["ledger_state row (id=1) not found"]
    state = dict(state)
    initial_equity = float(cfg["initial_equity_usd"])
    if state["watermark_bar_ts"] is not None:
        failures.append(
            f"pre-start ledger_state.watermark_bar_ts {state['watermark_bar_ts']!r} "
            f"!= NULL"
        )
    for col in ("realized_gross", "fees_cum", "funding_cum"):
        if not _close(state[col], 0.0):
            failures.append(f"pre-start ledger_state.{col} {state[col]:.8f} != 0")
    if not _close(state["peak_equity"], initial_equity):
        failures.append(
            f"pre-start ledger_state.peak_equity {state['peak_equity']:.8f} != "
            f"initial_equity {initial_equity:.8f}"
        )
    return failures


# ---------------------------------------------------------------------------
# Funding-coverage stamp (additive; does NOT change status)
# ---------------------------------------------------------------------------

def _snapshot_payload_from_report(
    snapshot_report: Mapping[str, Any] | None,
) -> dict[str, Any]:
    if not isinstance(snapshot_report, Mapping):
        return {}
    selected_path = snapshot_report.get("selected_snapshot_path")
    if not selected_path:
        return {}
    try:
        envelope = json.loads(Path(str(selected_path)).read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return {}
    return _payload_dict(envelope)


def _single_absolute_parent(paths: list[Path]) -> Path | None:
    parents = {path.parent for path in paths if path.is_absolute()}
    if len(parents) == 1:
        return next(iter(parents))
    return None


def _snapshot_provenance_source_dir(payload: Mapping[str, Any]) -> Path | None:
    provenance = payload.get("provenance")
    if not isinstance(provenance, Mapping):
        return None

    resolution = provenance.get("source_path_resolution")
    if isinstance(resolution, Mapping):
        raw_dir = resolution.get("resolved_funding_source_dir")
        if raw_dir:
            path = Path(str(raw_dir))
            if path.is_absolute():
                return path

    paths: list[Path] = []
    source_files = payload.get("source_files")
    if isinstance(source_files, list):
        for item in source_files:
            if isinstance(item, Mapping) and item.get("path"):
                paths.append(Path(str(item["path"])))

    entity_inputs = provenance.get("entity_inputs")
    if isinstance(entity_inputs, list):
        for item in entity_inputs:
            if isinstance(item, Mapping) and item.get("source_csv_path"):
                paths.append(Path(str(item["source_csv_path"])))

    return _single_absolute_parent(paths)


def _resolve_funding_source_dir(
    db_path: Path,
    *,
    explicit_data_dir: Path | None,
    snapshot_report: Mapping[str, Any] | None,
    allow_db_relative_data: bool,
) -> FundingSourcePathResolution:
    if explicit_data_dir is not None:
        return FundingSourcePathResolution(
            mode=SOURCE_PATH_RESOLUTION_MODE_EXPLICIT_DATA_DIR,
            resolved_dir=explicit_data_dir,
            available=explicit_data_dir.is_dir(),
        )

    snapshot_dir = _snapshot_provenance_source_dir(
        _snapshot_payload_from_report(snapshot_report)
    )
    if snapshot_dir is not None:
        return FundingSourcePathResolution(
            mode=SOURCE_PATH_RESOLUTION_MODE_SNAPSHOT_PROVENANCE,
            resolved_dir=snapshot_dir,
            available=snapshot_dir.is_dir(),
        )

    local_data = db_path.parent / "data"
    if allow_db_relative_data and local_data.is_dir():
        return FundingSourcePathResolution(
            mode=SOURCE_PATH_RESOLUTION_MODE_SNAPSHOT_PROVENANCE,
            resolved_dir=local_data,
            available=True,
        )

    return FundingSourcePathResolution(
        mode=SOURCE_PATH_RESOLUTION_MODE_UNAVAILABLE,
        resolved_dir=None,
        available=False,
    )


def _build_funding_coverage_stamp(
    conn: sqlite3.Connection,
    *,
    arithmetic_ok: bool,
    source_resolution: FundingSourcePathResolution,
) -> dict[str, Any]:
    """Compute the funding-coverage stamp using rows from the live ``funding`` table.

    Returns a dict with ``funding_coverage``, ``funding_coverage_verdict``,
    and ``funding_coverage_diagnostic_label`` keys, ready to be merged into
    the existing ``report`` dict. The arithmetic verdict decides the
    classification:

      - if the existing arithmetic verdict is NOT OK, the stamp collapses to
        ``FAIL`` / empty label (the gate plan §4 explicitly allows this).
      - otherwise the coverage decision drives ``CLEAN_NET_OF_CARRY`` vs
        ``CAVEATED_ENGINE_SEMANTICS``.

    Read-only: the function only reads from the pinned read-only connection.
    """
    funding_rows = _rows(conn, "SELECT * FROM funding")
    source_path_required = bool(funding_rows)
    if not source_resolution.available:
        rate_available_zero = sum(1 for row in funding_rows if not row["rate_available"])
        return {
            "funding_coverage": {
                "decision": (
                    SOURCE_PATH_UNAVAILABLE_REASON
                    if source_path_required
                    else COVERAGE_NOT_REQUIRED
                ),
                "per_symbol": {},
                "total_funding_rows": len(funding_rows),
                "total_rate_available_zero": rate_available_zero,
                "total_required_intervals": len(funding_rows),
                "missing_window_ids": [],
            },
            "funding_coverage_verdict": (
                FAIL if not arithmetic_ok else CAVEATED_ENGINE_SEMANTICS
            ),
            "funding_coverage_diagnostic_label": (
                CAVEATED_ENGINE_SEMANTICS_LABEL
                if arithmetic_ok and source_path_required
                else ""
            ),
            "source_path_required": source_path_required,
        }

    assert source_resolution.resolved_dir is not None
    coverage_report = check_funding_coverage_from_rows(
        funding_rows,
        source_resolution.resolved_dir,
    )

    if not arithmetic_ok:
        funding_coverage_verdict = FAIL
        funding_coverage_diagnostic_label = ""
    elif coverage_report.overall_decision in (COVERAGE_COMPLETE, COVERAGE_NOT_REQUIRED):
        funding_coverage_verdict = CLEAN_NET_OF_CARRY
        funding_coverage_diagnostic_label = ""
    else:
        funding_coverage_verdict = CAVEATED_ENGINE_SEMANTICS
        funding_coverage_diagnostic_label = CAVEATED_ENGINE_SEMANTICS_LABEL

    return {
        "funding_coverage": {
            "decision": coverage_report.overall_decision,
            "per_symbol": dict(coverage_report.per_symbol),
            "total_funding_rows": coverage_report.total_funding_rows,
            "total_rate_available_zero": coverage_report.total_rate_available_zero,
            "total_required_intervals": coverage_report.total_required_intervals,
            "missing_window_ids": [
                {
                    "funding_id": row.funding_id,
                    "symbol": row.symbol,
                    "bar_ts": row.bar_ts,
                    "window_start": row.window_start,
                    "window_end": row.window_end,
                    "source_issue": row.source_issue,
                }
                for row in coverage_report.missing_windows
            ],
        },
        "funding_coverage_verdict": funding_coverage_verdict,
        "funding_coverage_diagnostic_label": funding_coverage_diagnostic_label,
        "source_path_required": source_path_required,
    }


# ---------------------------------------------------------------------------
# Funding source snapshot stamp (additive; does NOT change status)
# ---------------------------------------------------------------------------

_FUNDING_SOURCE_SNAPSHOT_GLOB = "funding_source_snapshot_v1_*.json"


def _funding_source_snapshot_dir(db_path: Path) -> Path:
    return db_path.parent / "funding_source_snapshots"


def _payload_dict(envelope: Any) -> dict[str, Any]:
    if not isinstance(envelope, dict):
        return {}
    payload = envelope.get("snapshot_payload")
    if not isinstance(payload, dict):
        return {}
    return payload


def _snapshot_metadata_dict(payload: dict[str, Any]) -> dict[str, Any]:
    metadata = payload.get("snapshot_metadata")
    if not isinstance(metadata, dict):
        return {}
    return metadata


def _expected_snapshot_lane_id(cfg: dict[str, Any]) -> str:
    return str(cfg.get("lane_id") or "paper_pnl_v1")


_FUNDING_SOURCE_SNAPSHOT_REFERENCE_COLUMNS = (
    "funding_source_snapshot_path",
    "funding_source_snapshot_sha256",
    "funding_source_snapshot_bundle_sha256",
    "funding_source_snapshot_schema_version",
    "funding_source_snapshot_write_state",
    "funding_source_snapshot_created_at",
)


def _funding_clean_carry_target_batch(
    conn: sqlite3.Connection,
) -> dict[str, Any] | None:
    """Return the committed batch represented by the current verifier state.

    The SQLite verifier validates the whole committed ledger and reports the
    latest ledger_state/equity state. The matching clean-carry target is
    therefore the latest committed ledger batch, not an arbitrary sidecar file.
    """
    rows = _rows(
        conn,
        """
        SELECT *
        FROM ledger_batches
        WHERE committed_at IS NOT NULL
        ORDER BY batch_id DESC
        LIMIT 1
        """,
    )
    return rows[0] if rows else None


def _snapshot_reference_columns_present(conn: sqlite3.Connection) -> bool:
    return all(
        _column_exists(conn, "ledger_batches", name)
        for name in _FUNDING_SOURCE_SNAPSHOT_REFERENCE_COLUMNS
    )


def _db_snapshot_reference_values(batch: Mapping[str, Any]) -> dict[str, Any]:
    return {
        name: batch.get(name)
        for name in _FUNDING_SOURCE_SNAPSHOT_REFERENCE_COLUMNS
    }


def _incomplete_snapshot_reference_fields(
    reference: Mapping[str, Any],
) -> list[str]:
    return [
        name
        for name in _FUNDING_SOURCE_SNAPSHOT_REFERENCE_COLUMNS
        if reference.get(name) in (None, "")
    ]


def _resolve_db_linked_snapshot_path(
    db_path: Path,
    raw_snapshot_path: Any,
) -> tuple[Path | None, list[str]]:
    if raw_snapshot_path in (None, ""):
        return None, ["funding_source_snapshot_missing"]

    snapshot_dir = _funding_source_snapshot_dir(db_path).resolve()
    raw_path = Path(str(raw_snapshot_path))
    candidate = raw_path if raw_path.is_absolute() else db_path.parent / raw_path
    resolved = candidate.resolve()
    try:
        resolved.relative_to(snapshot_dir)
    except ValueError:
        return None, ["funding_source_snapshot_path_outside_snapshot_dir"]

    if resolved.name != candidate.name:
        return None, ["funding_source_snapshot_path_traversal"]
    if not resolved.exists():
        return None, ["funding_source_snapshot_missing"]
    if not resolved.is_file():
        return None, ["funding_source_snapshot_missing"]
    return resolved, []


def _duplicate_db_snapshot_reference_rows(
    conn: sqlite3.Connection,
    target_batch_id: int,
    snapshot_path: str,
) -> list[int]:
    return [
        int(row["batch_id"])
        for row in _rows(
            conn,
            """
            SELECT batch_id
            FROM ledger_batches
            WHERE batch_id != ?
              AND funding_source_snapshot_path = ?
            ORDER BY batch_id
            """,
            (target_batch_id, snapshot_path),
        )
    ]


def _status_from_db_linked_reason_codes(reason_codes: list[str]) -> str:
    reason_set = set(reason_codes)
    if "funding_source_snapshot_ambiguous_multiple" in reason_set:
        return FUNDING_SOURCE_SNAPSHOT_STATUS_AMBIGUOUS_MULTIPLE
    if (
        "funding_source_snapshot_missing" in reason_set
        or "funding_source_snapshot_path_outside_snapshot_dir" in reason_set
        or "funding_source_snapshot_path_traversal" in reason_set
    ):
        return FUNDING_SOURCE_SNAPSHOT_STATUS_MISSING
    if (
        "funding_source_snapshot_digest_mismatch" in reason_set
        or "funding_source_file_digest_mismatch" in reason_set
    ):
        return FUNDING_SOURCE_SNAPSHOT_STATUS_DIGEST_MISMATCH
    if "funding_source_snapshot_schema_unsupported" in reason_set:
        return FUNDING_SOURCE_SNAPSHOT_STATUS_SCHEMA_UNSUPPORTED
    if "funding_source_snapshot_payload_invalid" in reason_set:
        return FUNDING_SOURCE_SNAPSHOT_STATUS_PAYLOAD_INVALID
    if (
        "funding_source_snapshot_db_mismatch" in reason_set
        or "funding_source_snapshot_window_mismatch" in reason_set
    ):
        return FUNDING_SOURCE_SNAPSHOT_STATUS_DB_OR_LANE_MISMATCH
    if "funding_source_snapshot_unreferenced_or_orphaned" in reason_set:
        return FUNDING_SOURCE_SNAPSHOT_STATUS_PENDING_OR_ORPHANED
    return FUNDING_SOURCE_SNAPSHOT_STATUS_PRESENT_VALID


def _classify_db_linked_funding_source_snapshot(
    conn: sqlite3.Connection,
    db_path: Path,
    cfg: dict[str, Any],
    target_batch: Mapping[str, Any] | None,
) -> dict[str, Any] | None:
    if target_batch is None:
        return None

    target_batch_id = int(target_batch["batch_id"])
    reference = _db_snapshot_reference_values(target_batch)
    report: dict[str, Any] = {
        "selector": "ledger_batches",
        "target_batch_id": target_batch_id,
        "db_reference": reference,
    }

    reason_codes: list[str] = []
    if not _snapshot_reference_columns_present(conn):
        reason_codes.append("funding_source_snapshot_missing")
        report["missing_reference_columns"] = list(
            _FUNDING_SOURCE_SNAPSHOT_REFERENCE_COLUMNS
        )
    else:
        incomplete = _incomplete_snapshot_reference_fields(reference)
        if incomplete:
            reason_codes.append("funding_source_snapshot_missing")
            report["incomplete_reference_fields"] = incomplete

    selected_path: Path | None = None
    if not reason_codes:
        selected_path, path_reasons = _resolve_db_linked_snapshot_path(
            db_path,
            reference["funding_source_snapshot_path"],
        )
        reason_codes.extend(path_reasons)
        duplicate_batch_ids = _duplicate_db_snapshot_reference_rows(
            conn,
            target_batch_id,
            str(reference["funding_source_snapshot_path"]),
        )
        if duplicate_batch_ids:
            reason_codes.append("funding_source_snapshot_ambiguous_multiple")
            report["duplicate_reference_batch_ids"] = duplicate_batch_ids

    envelope: dict[str, Any] | None = None
    payload: dict[str, Any] = {}
    metadata: dict[str, Any] = {}
    if selected_path is not None and not reason_codes:
        report["selected_snapshot_path"] = str(selected_path)
        actual_file_sha = sha256_file(selected_path)
        report["file_sha256"] = actual_file_sha
        if actual_file_sha != reference["funding_source_snapshot_sha256"]:
            reason_codes.append("funding_source_snapshot_digest_mismatch")
            report["file_sha256_mismatch"] = {
                "db": reference["funding_source_snapshot_sha256"],
                "actual": actual_file_sha,
            }

        try:
            raw_envelope = json.loads(selected_path.read_text(encoding="utf-8"))
        except json.JSONDecodeError as exc:
            raw_envelope = None
            report["error"] = f"JSONDecodeError: {exc.msg}"
            reason_codes.append("funding_source_snapshot_payload_invalid")
        except OSError as exc:
            raw_envelope = None
            report["error"] = f"{type(exc).__name__}: {exc}"
            reason_codes.append("funding_source_snapshot_payload_invalid")

        if isinstance(raw_envelope, dict):
            envelope = raw_envelope
            validation_reasons = validate_funding_source_snapshot_envelope_v1(envelope)
            report["validation_reason_codes"] = list(validation_reasons)
            reason_codes.extend(str(reason) for reason in validation_reasons)
            payload = _payload_dict(envelope)
            metadata = _snapshot_metadata_dict(payload)
        else:
            reason_codes.append("funding_source_snapshot_payload_invalid")

    if envelope is not None:
        lane = payload.get("lane") if isinstance(payload.get("lane"), dict) else {}
        assert isinstance(lane, dict)
        report.update(
            {
                "snapshot_sha256": envelope.get("snapshot_sha256"),
                "source_bundle_sha256": payload.get("source_bundle_sha256"),
                "schema_version": payload.get("schema_version"),
                "write_state": payload.get("write_state"),
                "coverage_decision": payload.get("coverage_decision"),
                "payload_reason_codes": list(payload.get("reason_codes") or []),
                "lane_id": lane.get("lane_id"),
                "lane_output_dir": lane.get("output_dir"),
                "generated_at_utc": payload.get("generated_at_utc"),
                "db_path_reference": metadata.get("db_path_reference"),
                "batch_start_watermark": metadata.get("batch_start_watermark"),
                "batch_end_watermark": metadata.get("batch_end_watermark"),
                "pending_batch_id": metadata.get("pending_batch_id"),
                "ledger_batch_id": metadata.get("ledger_batch_id"),
                "batch_identity_matches": metadata.get("batch_identity_matches"),
                "evaluation_identity_matches": metadata.get(
                    "evaluation_identity_matches"
                ),
            }
        )

        if payload.get("source_bundle_sha256") != reference[
            "funding_source_snapshot_bundle_sha256"
        ]:
            reason_codes.append("funding_source_file_digest_mismatch")
        if payload.get("schema_version") != reference[
            "funding_source_snapshot_schema_version"
        ]:
            reason_codes.append("funding_source_snapshot_schema_unsupported")
        if reference["funding_source_snapshot_write_state"] != "committed":
            reason_codes.append("funding_source_snapshot_unreferenced_or_orphaned")
        if payload.get("write_state") != "committed":
            reason_codes.append("funding_source_snapshot_unreferenced_or_orphaned")
        if metadata.get("write_state") != "committed":
            reason_codes.append("funding_source_snapshot_unreferenced_or_orphaned")

        mismatch_reasons: list[str] = []
        expected_lane_id = _expected_snapshot_lane_id(cfg)
        if lane.get("lane_id") != expected_lane_id:
            mismatch_reasons.append(
                f"lane_id {lane.get('lane_id')!r} != expected {expected_lane_id!r}"
            )
        if lane.get("output_dir") != str(db_path.parent):
            mismatch_reasons.append(
                f"lane.output_dir {lane.get('output_dir')!r} != db directory "
                f"{str(db_path.parent)!r}"
            )
        if metadata.get("db_path_reference") != str(db_path):
            mismatch_reasons.append(
                "snapshot_metadata.db_path_reference "
                f"{metadata.get('db_path_reference')!r} != db_path {str(db_path)!r}"
            )
        if metadata.get("ledger_batch_id") != str(target_batch_id):
            reason_codes.append("funding_source_snapshot_unreferenced_or_orphaned")
            report.setdefault("orphan_reasons", []).append(
                "snapshot_metadata.ledger_batch_id "
                f"{metadata.get('ledger_batch_id')!r} != target batch "
                f"{str(target_batch_id)!r}"
            )
        if metadata.get("batch_identity_matches") is not True:
            reason_codes.append("funding_source_snapshot_unreferenced_or_orphaned")
            report.setdefault("orphan_reasons", []).append(
                "snapshot_metadata.batch_identity_matches is not true"
            )
        if metadata.get("evaluation_identity_matches") is not True:
            reason_codes.append("funding_source_snapshot_unreferenced_or_orphaned")
            report.setdefault("orphan_reasons", []).append(
                "snapshot_metadata.evaluation_identity_matches is not true"
            )
        if target_batch.get("prior_watermark_bar_ts") is not None and metadata.get(
            "batch_start_watermark"
        ) != target_batch.get("prior_watermark_bar_ts"):
            mismatch_reasons.append(
                "snapshot_metadata.batch_start_watermark "
                f"{metadata.get('batch_start_watermark')!r} != target batch "
                f"prior_watermark_bar_ts {target_batch.get('prior_watermark_bar_ts')!r}"
            )
        if target_batch.get("new_watermark_bar_ts") is not None and metadata.get(
            "batch_end_watermark"
        ) != target_batch.get("new_watermark_bar_ts"):
            mismatch_reasons.append(
                "snapshot_metadata.batch_end_watermark "
                f"{metadata.get('batch_end_watermark')!r} != target batch "
                f"new_watermark_bar_ts {target_batch.get('new_watermark_bar_ts')!r}"
            )
        if mismatch_reasons:
            report["mismatch_reasons"] = mismatch_reasons
            reason_codes.append("funding_source_snapshot_db_mismatch")

    deduped = sorted(set(reason_codes))
    status = _status_from_db_linked_reason_codes(deduped)
    report["status"] = status
    report["db_linked"] = True
    report["diagnostic_only"] = False
    report["clean_mode_gate"] = "db_linked_ledger_batches_reference"
    report["reason_codes"] = deduped
    if status != FUNDING_SOURCE_SNAPSHOT_STATUS_PRESENT_VALID:
        report["caveat"] = (
            "DB-linked snapshot reference is missing, pending, mismatched, "
            "unsafe, or ambiguous; preserving CAVEATED_ENGINE_SEMANTICS."
        )
    return report


def _classify_funding_source_snapshot_candidate(
    path: Path,
    *,
    db_path: Path,
    expected_lane_id: str,
) -> dict[str, Any]:
    candidate: dict[str, Any] = {
        "path": str(path),
        "file_name": path.name,
    }
    try:
        envelope = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        candidate.update(
            {
                "status": FUNDING_SOURCE_SNAPSHOT_STATUS_PAYLOAD_INVALID,
                "error": f"JSONDecodeError: {exc.msg}",
            }
        )
        return candidate
    except OSError as exc:
        candidate.update(
            {
                "status": FUNDING_SOURCE_SNAPSHOT_STATUS_PAYLOAD_INVALID,
                "error": f"{type(exc).__name__}: {exc}",
            }
        )
        return candidate

    if not isinstance(envelope, dict):
        candidate.update(
            {
                "status": FUNDING_SOURCE_SNAPSHOT_STATUS_PAYLOAD_INVALID,
                "error": "snapshot envelope JSON root is not an object",
            }
        )
        return candidate

    validation_reasons = validate_funding_source_snapshot_envelope_v1(envelope)
    candidate["validation_reason_codes"] = list(validation_reasons)
    if "funding_source_snapshot_digest_mismatch" in validation_reasons:
        candidate["status"] = FUNDING_SOURCE_SNAPSHOT_STATUS_DIGEST_MISMATCH
        return candidate
    if "funding_source_snapshot_schema_unsupported" in validation_reasons:
        candidate["status"] = FUNDING_SOURCE_SNAPSHOT_STATUS_SCHEMA_UNSUPPORTED
        return candidate
    if validation_reasons:
        candidate["status"] = FUNDING_SOURCE_SNAPSHOT_STATUS_PAYLOAD_INVALID
        return candidate

    payload = _payload_dict(envelope)
    metadata = _snapshot_metadata_dict(payload)
    lane = payload.get("lane") if isinstance(payload.get("lane"), dict) else {}
    assert isinstance(lane, dict)

    candidate.update(
        {
            "snapshot_sha256": envelope.get("snapshot_sha256"),
            "source_bundle_sha256": payload.get("source_bundle_sha256"),
            "schema_version": payload.get("schema_version"),
            "write_state": payload.get("write_state"),
            "coverage_decision": payload.get("coverage_decision"),
            "payload_reason_codes": list(payload.get("reason_codes") or []),
            "lane_id": lane.get("lane_id"),
            "lane_output_dir": lane.get("output_dir"),
            "generated_at_utc": payload.get("generated_at_utc"),
            "db_path_reference": metadata.get("db_path_reference"),
            "batch_start_watermark": metadata.get("batch_start_watermark"),
            "batch_end_watermark": metadata.get("batch_end_watermark"),
            "pending_batch_id": metadata.get("pending_batch_id"),
            "ledger_batch_id": metadata.get("ledger_batch_id"),
            "batch_identity_matches": metadata.get("batch_identity_matches"),
            "evaluation_identity_matches": metadata.get(
                "evaluation_identity_matches"
            ),
        }
    )

    mismatch_reasons: list[str] = []
    if lane.get("lane_id") != expected_lane_id:
        mismatch_reasons.append(
            f"lane_id {lane.get('lane_id')!r} != expected {expected_lane_id!r}"
        )
    if (
        lane.get("output_dir") is not None
        and lane.get("output_dir") != str(db_path.parent)
    ):
        mismatch_reasons.append(
            f"lane.output_dir {lane.get('output_dir')!r} != db directory "
            f"{str(db_path.parent)!r}"
        )
    db_path_reference = metadata.get("db_path_reference")
    if db_path_reference is not None and db_path_reference != str(db_path):
        mismatch_reasons.append(
            f"snapshot_metadata.db_path_reference {db_path_reference!r} != "
            f"db_path {str(db_path)!r}"
        )

    clean_decision = clean_mode_decision_from_snapshot_v1(
        envelope,
        expected_lane_id=expected_lane_id,
    )
    clean_reason_codes = list(clean_decision.get("reason_codes") or [])
    candidate["future_clean_mode_reason_codes"] = clean_reason_codes

    if mismatch_reasons or "funding_source_snapshot_db_mismatch" in clean_reason_codes:
        candidate["status"] = FUNDING_SOURCE_SNAPSHOT_STATUS_DB_OR_LANE_MISMATCH
        candidate["mismatch_reasons"] = mismatch_reasons
    elif "funding_source_snapshot_unreferenced_or_orphaned" in clean_reason_codes:
        candidate["status"] = FUNDING_SOURCE_SNAPSHOT_STATUS_PENDING_OR_ORPHANED
    else:
        candidate["status"] = FUNDING_SOURCE_SNAPSHOT_STATUS_PRESENT_VALID

    return candidate


def _build_funding_source_snapshot_stamp(
    conn: sqlite3.Connection,
    db_path: Path,
    cfg: dict[str, Any],
) -> dict[str, Any]:
    """Read sidecar snapshots and add selector/provenance stamp.

    Directory scanning remains diagnostic. When the verifier has a committed
    ledger batch target, clean-carry selection uses that batch's DB-linked
    snapshot reference instead.
    """
    snapshot_dir = _funding_source_snapshot_dir(db_path)
    files = (
        sorted(snapshot_dir.glob(_FUNDING_SOURCE_SNAPSHOT_GLOB))
        if snapshot_dir.is_dir()
        else []
    )
    expected_lane_id = _expected_snapshot_lane_id(cfg)
    candidates = [
        _classify_funding_source_snapshot_candidate(
            path,
            db_path=db_path,
            expected_lane_id=expected_lane_id,
        )
        for path in files
    ]

    directory_selected: dict[str, Any] | None = None
    if not files:
        directory_status = FUNDING_SOURCE_SNAPSHOT_STATUS_MISSING
    elif len(files) > 1:
        directory_status = FUNDING_SOURCE_SNAPSHOT_STATUS_AMBIGUOUS_MULTIPLE
    else:
        directory_selected = candidates[0]
        directory_status = str(directory_selected["status"])

    snapshot_report: dict[str, Any] = {
        "status": directory_status,
        "diagnostic_only": True,
        "clean_mode_gate": "see_funding_clean_carry_decision",
        "note": FUNDING_SOURCE_SNAPSHOT_DIAGNOSTIC_NOTE,
        "caveat": (
            "Missing, pending, orphaned, ambiguous, or mismatched source "
            "snapshots preserve CAVEATED_ENGINE_SEMANTICS."
        ),
        "snapshot_dir": str(snapshot_dir),
        "snapshot_dir_exists": snapshot_dir.is_dir(),
        "glob": _FUNDING_SOURCE_SNAPSHOT_GLOB,
        "candidate_count": len(files),
        "expected_lane_id": expected_lane_id,
        "candidates": candidates,
        "directory_status": directory_status,
    }

    if directory_status == FUNDING_SOURCE_SNAPSHOT_STATUS_AMBIGUOUS_MULTIPLE:
        snapshot_report["reason"] = (
            "multiple funding source snapshot sidecars found; directory scan has "
            "no durable selector and is diagnostic only. Clean evidence requires "
            "an exact DB-linked selector"
        )
    if directory_selected is not None:
        snapshot_report["selected_snapshot_path"] = directory_selected.get("path")
        for key in (
            "snapshot_sha256",
            "source_bundle_sha256",
            "write_state",
            "coverage_decision",
            "lane_id",
            "lane_output_dir",
            "generated_at_utc",
            "db_path_reference",
            "future_clean_mode_reason_codes",
            "mismatch_reasons",
        ):
            if key in directory_selected:
                snapshot_report[key] = directory_selected[key]

    target_batch = _funding_clean_carry_target_batch(conn)
    db_linked_report = _classify_db_linked_funding_source_snapshot(
        conn,
        db_path,
        cfg,
        target_batch,
    )
    if db_linked_report is not None:
        diagnostic_report = dict(snapshot_report)
        snapshot_report.update(db_linked_report)
        snapshot_report["directory_diagnostic"] = diagnostic_report
    elif target_batch is not None:
        snapshot_report.update(
            {
                "status": FUNDING_SOURCE_SNAPSHOT_STATUS_MISSING,
                "selector": "ledger_batches",
                "db_linked": True,
                "diagnostic_only": False,
                "clean_mode_gate": "db_linked_ledger_batches_reference",
                "target_batch_id": target_batch["batch_id"],
                "reason_codes": ["funding_source_snapshot_missing"],
            }
        )

    return {
        "funding_source_snapshot_status": snapshot_report["status"],
        "funding_source_snapshot": snapshot_report,
    }


# ---------------------------------------------------------------------------
# Strict funding clean-carry gate (additive; does NOT change arithmetic status)
# ---------------------------------------------------------------------------

def _funding_resum_check(conn: sqlite3.Connection) -> dict[str, Any]:
    """Independently re-sum funding and compare it to latest state/equity."""
    funding_sum = float(
        _scalar(conn, "SELECT COALESCE(SUM(funding_amount), 0.0) FROM funding")
        or 0.0
    )
    funding_rows = int(_scalar(conn, "SELECT COUNT(*) FROM funding") or 0)
    state_row = conn.execute(
        "SELECT funding_cum FROM ledger_state WHERE id = 1"
    ).fetchone()
    latest_equity = conn.execute(
        "SELECT bar_ts, funding_cum FROM equity_snapshots "
        "ORDER BY bar_ts DESC, seq DESC LIMIT 1"
    ).fetchone()

    state_value = float(state_row["funding_cum"]) if state_row is not None else None
    equity_value = (
        float(latest_equity["funding_cum"]) if latest_equity is not None else None
    )

    issues: list[str] = []
    if state_value is None or not _close(state_value, funding_sum):
        issues.append("ledger_state_funding_cum_mismatch")
    if funding_rows > 0 and equity_value is None:
        issues.append("latest_equity_funding_cum_missing")
    elif equity_value is not None and not _close(equity_value, funding_sum):
        issues.append("latest_equity_funding_cum_mismatch")

    return {
        "status": "ok" if not issues else "mismatch",
        "tolerance_abs": _ABS_TOL,
        "funding_rows": funding_rows,
        "funding_amount_sum": funding_sum,
        "ledger_state_funding_cum": state_value,
        "latest_equity_bar_ts": (
            latest_equity["bar_ts"] if latest_equity is not None else None
        ),
        "latest_equity_funding_cum": equity_value,
        "reason_codes": ["funding_resum_mismatch"] if issues else [],
        "issues": issues,
    }


def _funding_evaluation_window(conn: sqlite3.Connection) -> dict[str, Any] | None:
    row = conn.execute(
        "SELECT MIN(window_start) AS start, MAX(window_end) AS end FROM funding"
    ).fetchone()
    if row is None or row["start"] is None or row["end"] is None:
        return None
    return {"start": row["start"], "end": row["end"]}


def _batch_evaluation_window(conn: sqlite3.Connection) -> dict[str, Any] | None:
    """Return the evaluation window for the latest committed ledger batch.

    Uses the batch's ``prior_watermark_bar_ts`` and ``new_watermark_bar_ts``
    as the definitive batch-scoped window, NOT the full funding-table span.
    """
    row = conn.execute(
        """
        SELECT prior_watermark_bar_ts, new_watermark_bar_ts
        FROM ledger_batches
        WHERE committed_at IS NOT NULL
        ORDER BY batch_id DESC
        LIMIT 1
        """
    ).fetchone()
    if row is None:
        return None
    prior = row["prior_watermark_bar_ts"]
    new_ = row["new_watermark_bar_ts"]
    if prior is None or new_ is None:
        return None
    # Normalize to ISO Z format for consistency with snapshot payload windows
    start_dt = parse_bar_utc(prior)
    end_dt = parse_bar_utc(new_)
    return {
        "start": start_dt.strftime("%Y-%m-%dT%H:%M:%SZ"),
        "end": end_dt.strftime("%Y-%m-%dT%H:%M:%SZ"),
    }


def _snapshot_source_file_path(
    db_path: Path,
    source_path: str,
    *,
    source_resolution: FundingSourcePathResolution,
) -> Path:
    raw = Path(source_path)
    if source_resolution.resolved_dir is not None:
        source_dir = source_resolution.resolved_dir
        if raw.is_absolute():
            explicit_candidate = source_dir / raw.name
            if (
                source_resolution.mode == SOURCE_PATH_RESOLUTION_MODE_EXPLICIT_DATA_DIR
                and explicit_candidate.exists()
            ):
                return explicit_candidate
            return raw

        candidates: list[Path] = []
        if raw.parts and raw.parts[0] == "data":
            tail = Path(*raw.parts[1:]) if len(raw.parts) > 1 else Path(raw.name)
            candidates.append(source_dir / tail)
        candidates.append(source_dir / raw.name)
        candidates.append(source_dir / raw)
        for candidate in candidates:
            if candidate.exists():
                return candidate
        return candidates[0]

    if raw.is_absolute():
        return raw
    return db_path.parent / raw


def _source_symbol_from_snapshot_item(path: str, item: Mapping[str, Any]) -> str:
    symbol = item.get("symbol")
    if symbol:
        return str(symbol)
    name = Path(path).name
    if name.endswith("_8h_funding.csv"):
        return name.removesuffix("_8h_funding.csv")
    if "_" in name:
        return name.split("_", 1)[0]
    return Path(path).stem


def _read_snapshot_source_rows(
    *,
    db_path: Path,
    source_files: list[Mapping[str, Any]],
    source_resolution: FundingSourcePathResolution,
) -> tuple[list[dict[str, Any]], dict[str, str], list[str]]:
    rows: list[dict[str, Any]] = []
    full_file_sha256_by_path: dict[str, str] = {}
    reason_codes: list[str] = []

    for item in source_files:
        source_path = str(item.get("path") or "")
        if not source_path:
            reason_codes.append("funding_source_file_digest_mismatch")
            continue
        resolved = _snapshot_source_file_path(
            db_path,
            source_path,
            source_resolution=source_resolution,
        )
        try:
            full_file_sha256_by_path[source_path] = build_source_file_digest(resolved)
            with resolved.open("r", newline="", encoding="utf-8") as fh:
                reader = csv.DictReader(fh)
                if reader.fieldnames is None:
                    reason_codes.append("funding_source_row_digest_mismatch")
                    continue
                missing = {"fundingTime", "fundingRate"} - set(reader.fieldnames)
                if missing:
                    reason_codes.append("funding_source_row_digest_mismatch")
                    continue
                symbol = _source_symbol_from_snapshot_item(source_path, item)
                for row_index, row in enumerate(reader, start=1):
                    try:
                        funding_time_ms = int(row["fundingTime"])
                    except (TypeError, ValueError):
                        reason_codes.append("funding_source_row_digest_mismatch")
                        continue
                    rows.append(
                        {
                            "symbol": symbol,
                            "fundingTime_ms": funding_time_ms,
                            "source_file_path": source_path,
                            "row_index": row_index,
                            "funding_rate": str(row["fundingRate"]),
                        }
                    )
        except OSError:
            reason_codes.append("funding_source_file_digest_mismatch")

    return rows, full_file_sha256_by_path, sorted(set(reason_codes))


def _snapshot_source_digest_expectations(
    *,
    db_path: Path,
    payload: Mapping[str, Any],
    source_resolution: FundingSourcePathResolution,
) -> tuple[dict[str, str], dict[str, str], list[str]]:
    if not source_resolution.available:
        return {}, {}, [SOURCE_PATH_UNAVAILABLE_REASON]

    source_files_raw = payload.get("source_files")
    if not isinstance(source_files_raw, list):
        return {}, {}, ["funding_source_file_digest_mismatch"]
    source_files = [
        item for item in source_files_raw if isinstance(item, Mapping)
    ]
    required_windows_raw = payload.get("required_funding_windows")
    if not isinstance(required_windows_raw, list):
        return {}, {}, ["funding_source_row_digest_mismatch"]
    required_windows = [
        item for item in required_windows_raw if isinstance(item, Mapping)
    ]

    source_rows, full_file_sha_by_path, reason_codes = _read_snapshot_source_rows(
        db_path=db_path,
        source_files=source_files,
        source_resolution=source_resolution,
    )
    row_subset_sha_by_path: dict[str, str] = {}
    for item in source_files:
        source_path = str(item.get("path") or "")
        if not source_path:
            continue
        row_subset_sha_by_path[source_path] = build_canonical_row_subset_digest(
            source_rows,
            required_windows,
            source_file_path=source_path,
        )

    return full_file_sha_by_path, row_subset_sha_by_path, reason_codes


def _bundle_source_digest_expectations(
    *,
    db_path: Path,
    payload: Mapping[str, Any],
) -> tuple[dict[str, str] | None, dict[str, str] | None, list[str], dict[str, Any]]:
    """Resolve funding-source digests from the pinned immutable bundle.

    Unlike the live-current path, this never reads the mutable ``data/*.csv``
    files: it validates the frozen, content-addressed bundle bound to this
    committed snapshot and returns the captured digests. When the bundle is
    missing/corrupt/tampered/incomplete, it returns no expectations plus the
    refusal reason codes (which force clean-carry refusal).
    """
    bundle_dir = db_path.parent / "funding_source_bundles"
    expected_snapshot_bundle_sha256 = payload.get("source_bundle_sha256")
    bundle_payload, reason_codes, identity = resolve_funding_source_bundle(
        bundle_dir,
        str(expected_snapshot_bundle_sha256)
        if expected_snapshot_bundle_sha256 is not None
        else None,
    )
    if bundle_payload is None or reason_codes:
        return None, None, list(reason_codes), identity

    expected_file_sha_by_path = {
        str(path): str(sha)
        for path, sha in (bundle_payload.get("original_source_digests") or {}).items()
    }
    expected_row_sha_by_path = {
        str(path): str(sha)
        for path, sha in (bundle_payload.get("row_subset_digests") or {}).items()
    }
    return expected_file_sha_by_path, expected_row_sha_by_path, [], identity


def _read_snapshot_envelope_for_clean_gate(
    snapshot_report: Mapping[str, Any],
) -> tuple[dict[str, Any] | None, list[str]]:
    selected_path = snapshot_report.get("selected_snapshot_path")
    if not selected_path:
        return None, []
    try:
        envelope = json.loads(Path(str(selected_path)).read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return None, [FUNDING_CLEAN_CARRY_REASON_PAYLOAD_INVALID]
    if not isinstance(envelope, dict):
        return None, [FUNDING_CLEAN_CARRY_REASON_PAYLOAD_INVALID]
    return envelope, []


def _clean_carry_status_from_reasons(reason_codes: list[str]) -> str:
    reason_set = set(reason_codes)
    if not reason_set:
        return FUNDING_CLEAN_CARRY_STATUS_CLEAN
    if reason_set & BUNDLE_REFUSAL_REASONS:
        return FUNDING_CLEAN_CARRY_STATUS_REFUSED_BUNDLE
    if FUNDING_CLEAN_CARRY_REASON_AMBIGUOUS_MULTIPLE in reason_set:
        return FUNDING_CLEAN_CARRY_STATUS_REFUSED_AMBIGUOUS_MULTIPLE
    if "funding_source_snapshot_missing" in reason_set:
        return FUNDING_CLEAN_CARRY_STATUS_REFUSED_MISSING_SNAPSHOT
    if (
        "funding_source_snapshot_digest_mismatch" in reason_set
        or "funding_source_file_digest_mismatch" in reason_set
        or "funding_source_row_digest_mismatch" in reason_set
    ):
        return FUNDING_CLEAN_CARRY_STATUS_REFUSED_DIGEST_MISMATCH
    if (
        "funding_source_snapshot_schema_unsupported" in reason_set
        or FUNDING_CLEAN_CARRY_REASON_PAYLOAD_INVALID in reason_set
    ):
        return FUNDING_CLEAN_CARRY_STATUS_REFUSED_SCHEMA_UNSUPPORTED
    if (
        "funding_source_snapshot_db_mismatch" in reason_set
        or "funding_source_snapshot_window_mismatch" in reason_set
        or "funding_source_batch_window_mismatch" in reason_set
    ):
        return FUNDING_CLEAN_CARRY_STATUS_REFUSED_DB_OR_LANE_MISMATCH
    if "funding_source_snapshot_unreferenced_or_orphaned" in reason_set:
        return FUNDING_CLEAN_CARRY_STATUS_REFUSED_PENDING_OR_ORPHANED
    source_issue_codes = {
        FUNDING_CLEAN_CARRY_REASON_SOURCE_COVERAGE_NOT_COMPLETE,
        SOURCE_PATH_UNAVAILABLE_REASON,
        "funding_source_missing",
        "funding_source_partial",
        "funding_source_duplicate_ambiguous",
        "funding_timestamp_outside_tolerance",
        "funding_timestamp_open_boundary",
    }
    if reason_set & source_issue_codes:
        return FUNDING_CLEAN_CARRY_STATUS_REFUSED_SOURCE_COVERAGE
    if "funding_resum_mismatch" in reason_set:
        return FUNDING_CLEAN_CARRY_STATUS_REFUSED_RESUM_MISMATCH
    return FUNDING_CLEAN_CARRY_STATUS_CAVEATED


def _build_funding_clean_carry_stamp(
    conn: sqlite3.Connection,
    db_path: Path,
    cfg: dict[str, Any],
    report: Mapping[str, Any],
    *,
    arithmetic_ok: bool,
    source_resolution: FundingSourcePathResolution,
    source_mode: str = SOURCE_MODE_LIVE_CURRENT,
) -> dict[str, Any]:
    """Decide whether the strict clean-carry label is allowed for this report."""
    reason_codes: list[str] = []
    resolution_fields: dict[str, Any] = {"source_resolution_mode": source_mode}
    if not arithmetic_ok:
        reason_codes.append(FUNDING_CLEAN_CARRY_REASON_ARITHMETIC_NOT_OK)

    coverage = report.get("funding_coverage")
    coverage_decision = (
        coverage.get("decision") if isinstance(coverage, Mapping) else None
    )
    if report.get("source_path_required") and not source_resolution.available:
        reason_codes.append(SOURCE_PATH_UNAVAILABLE_REASON)
    elif coverage_decision != COVERAGE_COMPLETE:
        reason_codes.append(FUNDING_CLEAN_CARRY_REASON_SOURCE_COVERAGE_NOT_COMPLETE)

    snapshot_report = report.get("funding_source_snapshot")
    if not isinstance(snapshot_report, Mapping):
        snapshot_report = {}
    snapshot_status = snapshot_report.get("status")
    snapshot_reason_codes = snapshot_report.get("reason_codes")
    if isinstance(snapshot_reason_codes, list):
        reason_codes.extend(str(reason) for reason in snapshot_reason_codes)

    envelope: dict[str, Any] | None = None
    if snapshot_status == FUNDING_SOURCE_SNAPSHOT_STATUS_MISSING:
        reason_codes.append("funding_source_snapshot_missing")
    elif snapshot_status == FUNDING_SOURCE_SNAPSHOT_STATUS_AMBIGUOUS_MULTIPLE:
        reason_codes.append(FUNDING_CLEAN_CARRY_REASON_AMBIGUOUS_MULTIPLE)
    elif snapshot_status == FUNDING_SOURCE_SNAPSHOT_STATUS_DIGEST_MISMATCH:
        reason_codes.append("funding_source_snapshot_digest_mismatch")
    elif snapshot_status == FUNDING_SOURCE_SNAPSHOT_STATUS_SCHEMA_UNSUPPORTED:
        reason_codes.append("funding_source_snapshot_schema_unsupported")
    elif snapshot_status == FUNDING_SOURCE_SNAPSHOT_STATUS_PAYLOAD_INVALID:
        reason_codes.append(FUNDING_CLEAN_CARRY_REASON_PAYLOAD_INVALID)
    elif snapshot_status == FUNDING_SOURCE_SNAPSHOT_STATUS_DB_OR_LANE_MISMATCH:
        reason_codes.append("funding_source_snapshot_db_mismatch")
    elif snapshot_status == FUNDING_SOURCE_SNAPSHOT_STATUS_PENDING_OR_ORPHANED:
        reason_codes.append("funding_source_snapshot_unreferenced_or_orphaned")
    elif snapshot_status == FUNDING_SOURCE_SNAPSHOT_STATUS_PRESENT_VALID:
        envelope, read_reasons = _read_snapshot_envelope_for_clean_gate(
            snapshot_report
        )
        reason_codes.extend(read_reasons)
    else:
        reason_codes.append("funding_source_snapshot_missing")

    if envelope is not None:
        payload = _payload_dict(envelope)
        expected_file_sha_by_path: dict[str, str] | None = None
        expected_row_sha_by_path: dict[str, str] | None = None
        if isinstance(payload, Mapping):
            if source_mode == SOURCE_MODE_BUNDLE:
                (
                    expected_file_sha_by_path,
                    expected_row_sha_by_path,
                    bundle_reason_codes,
                    bundle_identity,
                ) = _bundle_source_digest_expectations(
                    db_path=db_path,
                    payload=payload,
                )
                reason_codes.extend(bundle_reason_codes)
                resolution_fields.update(bundle_identity)
            else:
                (
                    expected_file_sha_by_path,
                    expected_row_sha_by_path,
                    digest_reason_codes,
                ) = _snapshot_source_digest_expectations(
                    db_path=db_path,
                    payload=payload,
                    source_resolution=source_resolution,
                )
                reason_codes.extend(digest_reason_codes)
                resolution_fields["live_source_digests"] = (
                    expected_file_sha_by_path or {}
                )
        clean_decision = clean_mode_decision_from_snapshot_v1(
            envelope,
            expected_evaluation_window=_funding_evaluation_window(conn),
            expected_lane_id=_expected_snapshot_lane_id(cfg),
            expected_ledger_batch_id=(
                str(snapshot_report["target_batch_id"])
                if snapshot_report.get("target_batch_id") is not None
                else None
            ),
            expected_source_file_sha256_by_path=expected_file_sha_by_path,
            expected_row_subset_sha256_by_path=expected_row_sha_by_path,
        )
        reason_codes.extend(str(r) for r in clean_decision.get("reason_codes") or [])

    resum_check = _funding_resum_check(conn)
    reason_codes.extend(str(r) for r in resum_check.get("reason_codes") or [])

    deduped_reasons = sorted(set(reason_codes))
    status = _clean_carry_status_from_reasons(deduped_reasons)
    clean_allowed = status == FUNDING_CLEAN_CARRY_STATUS_CLEAN
    decision = CLEAN_NET_OF_CARRY if clean_allowed else CAVEATED_ENGINE_SEMANTICS

    clean_report = {
        "decision": decision,
        "status": status,
        "reason_codes": deduped_reasons,
        "arithmetic_status": STATUS_OK if arithmetic_ok else STATUS_CORRUPT,
        "arithmetic_ok": arithmetic_ok,
        "funding_coverage_decision": coverage_decision,
        "snapshot_status": snapshot_status,
        "snapshot_sha256": snapshot_report.get("snapshot_sha256"),
        "source_bundle_sha256": snapshot_report.get("source_bundle_sha256"),
        "resum_check": resum_check,
        "note": FUNDING_CLEAN_CARRY_NOTE,
    }
    clean_report.update(resolution_fields)
    return {
        "funding_clean_carry_decision": decision,
        "funding_clean_carry_status": status,
        "funding_clean_carry_reason_codes": deduped_reasons,
        "funding_clean_carry": clean_report,
    }


# ---------------------------------------------------------------------------
# Batch-scoped clean-carry gate (additive; does NOT change full-ledger fields)
# ---------------------------------------------------------------------------


def _build_funding_clean_carry_batch_stamp(
    conn: sqlite3.Connection,
    db_path: Path,
    cfg: dict[str, Any],
    report: Mapping[str, Any],
    *,
    arithmetic_ok: bool,
    source_resolution: FundingSourcePathResolution,
) -> dict[str, Any]:
    """Decide batch-scoped clean-carry for the latest DB-linked ledger batch.

    This is additive to the existing full-ledger clean-carry gate. It evaluates
    only the latest committed ``ledger_batches`` row and compares its DB-linked
    funding source snapshot against the batch's own watermark window
    (``prior_watermark_bar_ts`` -> ``new_watermark_bar_ts``), NOT the full
    funding-table span.

    Returns a dict with keys ``funding_clean_carry_batch_decision``,
    ``funding_clean_carry_batch_status``,
    ``funding_clean_carry_batch_reason_codes``, and
    ``funding_clean_carry_batch`` (detail sub-dict).
    """
    reason_codes: list[str] = []

    # --- 1. Get the latest committed batch ---------------------------------
    target_batch = _funding_clean_carry_target_batch(conn)
    if target_batch is None:
        reason_codes.append("funding_source_snapshot_missing")
        deduped = sorted(set(reason_codes))
        status = _clean_carry_status_from_reasons(deduped)
        decision = CAVEATED_ENGINE_SEMANTICS
        raw_ledger_window = _funding_evaluation_window(conn)
        if raw_ledger_window is not None:
            normalized_ledger_window = {
                "start": parse_bar_utc(raw_ledger_window["start"]).strftime(
                    "%Y-%m-%dT%H:%M:%SZ"
                ),
                "end": parse_bar_utc(raw_ledger_window["end"]).strftime(
                    "%Y-%m-%dT%H:%M:%SZ"
                ),
            }
        else:
            normalized_ledger_window = None
        batch_report = {
            "decision": decision,
            "status": status,
            "reason_codes": deduped,
            "target_batch_id": None,
            "evaluation_window": None,
            "full_ledger_evaluation_window": normalized_ledger_window,
            "arithmetic_ok": arithmetic_ok,
            "note": FUNDING_CLEAN_CARRY_NOTE,
        }
        return {
            "funding_clean_carry_batch_decision": decision,
            "funding_clean_carry_batch_status": status,
            "funding_clean_carry_batch_reason_codes": deduped,
            "funding_clean_carry_batch": batch_report,
        }

    target_batch_id = int(target_batch["batch_id"])

    # --- 2. Determine the batch-scoped evaluation window -------------------
    batch_window = _batch_evaluation_window(conn)
    if batch_window is None:
        reason_codes.append(FUNDING_CLEAN_CARRY_REASON_BATCH_WINDOW_MISMATCH)

    # --- 3. Arithmetic check -----------------------------------------------
    if not arithmetic_ok:
        reason_codes.append(FUNDING_CLEAN_CARRY_REASON_ARITHMETIC_NOT_OK)

    # --- 4. Coverage / source-path check -----------------------------------
    coverage = report.get("funding_coverage")
    coverage_decision = (
        coverage.get("decision") if isinstance(coverage, Mapping) else None
    )
    if report.get("source_path_required") and not source_resolution.available:
        reason_codes.append(SOURCE_PATH_UNAVAILABLE_REASON)
    elif coverage_decision != COVERAGE_COMPLETE:
        reason_codes.append(FUNDING_CLEAN_CARRY_REASON_SOURCE_COVERAGE_NOT_COMPLETE)

    # --- 5. Snapshot reference on latest batch ----------------------------
    reference = _db_snapshot_reference_values(target_batch)
    missing_fields = _incomplete_snapshot_reference_fields(reference)
    if missing_fields:
        reason_codes.append("funding_source_snapshot_missing")
    else:
        snapshot_path_str = str(reference.get("funding_source_snapshot_path") or "")
        expected_sha = str(reference.get("funding_source_snapshot_sha256") or "")

        # 5a. Resolve snapshot file path
        resolved_path, resolve_reasons = _resolve_db_linked_snapshot_path(
            db_path, snapshot_path_str
        )
        reason_codes.extend(resolve_reasons)

        if resolved_path is not None:
            # 5b. Verify on-disk SHA256 matches DB reference
            try:
                actual_sha = sha256_file(resolved_path)
                if actual_sha != expected_sha:
                    reason_codes.append("funding_source_snapshot_digest_mismatch")
            except (OSError, ValueError):
                reason_codes.append("funding_source_snapshot_missing")

            if "funding_source_snapshot_digest_mismatch" not in reason_codes:
                # 5c. Read and validate snapshot envelope
                try:
                    envelope_raw = json.loads(
                        resolved_path.read_text(encoding="utf-8")
                    )
                except (json.JSONDecodeError, OSError):
                    envelope_raw = None
                    reason_codes.append(FUNDING_CLEAN_CARRY_REASON_PAYLOAD_INVALID)

                if isinstance(envelope_raw, dict):
                    envelope: dict[str, Any] = envelope_raw
                    env_reasons = validate_funding_source_snapshot_envelope_v1(
                        envelope
                    )
                    reason_codes.extend(env_reasons)

                    if not env_reasons:
                        payload = _payload_dict(envelope)

                        # 5d. Source digest expectations
                        (
                            expected_file_sha_by_path,
                            expected_row_sha_by_path,
                            digest_reason_codes,
                        ) = _snapshot_source_digest_expectations(
                            db_path=db_path,
                            payload=payload,
                            source_resolution=source_resolution,
                        )
                        reason_codes.extend(digest_reason_codes)

                        # 5e. Validate against batch-scoped window
                        clean_decision = clean_mode_decision_from_snapshot_v1(
                            envelope,
                            expected_evaluation_window=batch_window,
                            expected_lane_id=_expected_snapshot_lane_id(cfg),
                            expected_ledger_batch_id=str(target_batch_id),
                            expected_source_file_sha256_by_path=(
                                expected_file_sha_by_path
                            ),
                            expected_row_subset_sha256_by_path=(
                                expected_row_sha_by_path
                            ),
                        )
                        decision_reasons = list(
                            str(r)
                            for r in clean_decision.get("reason_codes") or []
                        )

                        # Translate window-mismatch to batch-scoped code
                        for r in decision_reasons:
                            if r == "funding_source_snapshot_window_mismatch":
                                reason_codes.append(
                                    FUNDING_CLEAN_CARRY_REASON_BATCH_WINDOW_MISMATCH
                                )
                            else:
                                reason_codes.append(r)
                else:
                    reason_codes.append(FUNDING_CLEAN_CARRY_REASON_PAYLOAD_INVALID)

    # --- 6. Funding re-sum check -------------------------------------------
    resum_check = _funding_resum_check(conn)
    reason_codes.extend(str(r) for r in resum_check.get("reason_codes") or [])

    # --- 7. Compute final decision / status --------------------------------
    deduped_reasons = sorted(set(reason_codes))
    status = _clean_carry_status_from_reasons(deduped_reasons)
    clean_allowed = status == FUNDING_CLEAN_CARRY_STATUS_CLEAN
    decision = CLEAN_NET_OF_CARRY if clean_allowed else CAVEATED_ENGINE_SEMANTICS

    full_ledger_window = _funding_evaluation_window(conn)
    if full_ledger_window is not None:
        full_ledger_window = {
            "start": parse_bar_utc(full_ledger_window["start"]).strftime(
                "%Y-%m-%dT%H:%M:%SZ"
            ),
            "end": parse_bar_utc(full_ledger_window["end"]).strftime(
                "%Y-%m-%dT%H:%M:%SZ"
            ),
        }

    batch_report = {
        "decision": decision,
        "status": status,
        "reason_codes": deduped_reasons,
        "target_batch_id": target_batch_id,
        "evaluation_window": dict(batch_window) if batch_window else None,
        "full_ledger_evaluation_window": full_ledger_window,
        "arithmetic_ok": arithmetic_ok,
        "resum_check": dict(resum_check),
        "note": FUNDING_CLEAN_CARRY_NOTE,
    }

    return {
        "funding_clean_carry_batch_decision": decision,
        "funding_clean_carry_batch_status": status,
        "funding_clean_carry_batch_reason_codes": deduped_reasons,
        "funding_clean_carry_batch": batch_report,
    }


_GIT_PROVENANCE_MAX_IDS = 50


def _build_git_provenance_stamp(conn: sqlite3.Connection) -> dict[str, Any]:
    """Compute the git-SHA provenance stamp from ``ledger_batches`` (read-only).

    Provenance is operator-facing evidence, NOT a status gate: a committed batch
    with ``git_sha = NULL`` cannot self-attest which code produced it, but old
    rows predate the writer's git-SHA gate and are legitimate *historical
    unprovenanced* evidence — they must stay readable and OK, never flip the
    verdict to CORRUPT. (New batches can no longer be NULL: the writer fails
    closed.) The stamp surfaces, for the operator:

      - the latest batch's git_sha and whether it is missing;
      - whether ANY batch is missing git_sha, and how many;
      - a loud warning string when provenance is missing (latest = strong;
        historical-only = softer caveat).

    Read-only: only SELECTs against the pinned snapshot.
    """
    rows = _rows(conn, "SELECT batch_id, git_sha FROM ledger_batches ORDER BY batch_id")
    missing_ids = [r["batch_id"] for r in rows if not r["git_sha"]]
    latest = rows[-1] if rows else None
    latest_sha = latest["git_sha"] if latest else None
    latest_missing = latest is not None and not latest_sha

    warning: str | None = None
    if latest_missing:
        warning = (
            "UNPROVENANCED_LATEST_BATCH: the latest committed batch has no git_sha; "
            "the ledger cannot self-attest which code produced it. Treat downstream "
            "(comparator / promotion) trust as BLOCKED until provenance is present."
        )
    elif missing_ids:
        warning = (
            f"HISTORICAL_UNPROVENANCED_BATCHES: {len(missing_ids)} older batch(es) "
            "predate git_sha provenance and remain unprovenanced historical evidence "
            "(immutable; not a corruption)."
        )

    return {
        "git_provenance": {
            "latest_batch_id": (latest["batch_id"] if latest else None),
            "latest_batch_git_sha": latest_sha,
            "latest_batch_git_sha_missing": latest_missing,
            "batches_missing_git_sha": len(missing_ids),
            "any_batch_missing_git_sha": bool(missing_ids),
            "unprovenanced_batch_ids": missing_ids[:_GIT_PROVENANCE_MAX_IDS],
        },
        "git_provenance_warning": warning,
    }


# ---------------------------------------------------------------------------
# Main entry point
# ---------------------------------------------------------------------------

def _verify_connection(
    conn: sqlite3.Connection,
    db_path: Path,
    *,
    data_dir: Path | None = None,
    allow_db_relative_data: bool = True,
    fail_on_source_path_unavailable: bool = False,
    source_mode: str = SOURCE_MODE_LIVE_CURRENT,
) -> VerifyResult:
    """Verify the single read snapshot currently held by ``conn``."""
    report: dict[str, Any] = {
        "db_path": str(db_path),
        "disclaimer": VERIFIER_DISCLAIMER,
    }
    # Confirm query-only mode is active (defends against accidental writes).
    try:
        query_only = _scalar(conn, "PRAGMA query_only")
        report["query_only"] = int(query_only) if query_only is not None else None
        if not query_only:
            return VerifyResult(
                STATUS_CONFIG_ERROR,
                ["PRAGMA query_only is not ON on the verifier connection"],
                report,
            )

        structural = _validate_schema_presence(conn)
        if structural:
            return VerifyResult(STATUS_CORRUPT, structural, report)

        cfg, identity_failures = _validate_identity(conn)
        if identity_failures:
            return VerifyResult(STATUS_CONFIG_ERROR, identity_failures, report)
        assert cfg is not None
        report.update(_build_funding_source_snapshot_stamp(conn, db_path, cfg))
        source_resolution = _resolve_funding_source_dir(
            db_path,
            explicit_data_dir=data_dir,
            snapshot_report=report.get("funding_source_snapshot"),
            allow_db_relative_data=allow_db_relative_data,
        )
        report.update(source_resolution.report_fields())
    except sqlite3.DatabaseError as exc:
        return VerifyResult(
            STATUS_CONFIG_ERROR,
            [f"DB is not readable as a paper ledger: {type(exc).__name__}: {exc}"],
            report,
        )

    try:
        counts = _ledger_table_counts(conn)
        report["batches"] = counts["ledger_batches"]
        report["events"] = counts["ledger_events"]
        report["equity_rows"] = counts["equity_snapshots"]
        report["watermark_bar_ts"] = _scalar(
            conn, "SELECT watermark_bar_ts FROM ledger_state WHERE id = 1"
        )

        if all(v == 0 for v in counts.values()):
            state_failures = _validate_initial_state(conn, cfg)
            if state_failures:
                report["failure_count"] = len(state_failures)
                return VerifyResult(STATUS_CORRUPT, state_failures, report)
            report["forward_start_ts"] = cfg["forward_start_ts"]
            report["failure_count"] = 0
            return VerifyResult(STATUS_PRE_START, [], report)

        failures: list[str] = []
        failures += _validate_foreign_keys(conn)
        failures += _validate_event_chain(conn)
        failures += _validate_event_typed_consistency(conn)
        failures += _validate_batches(conn)
        failures += _validate_arithmetic(conn, cfg)
        failures += _validate_trades(conn)
        failures += _validate_equity_cumulative(conn, cfg)
        failures += _validate_state(conn, cfg)
        failures += _validate_open_positions(conn)
        failures += _validate_position_snapshots(conn)
        failures += _validate_snapshot_identity(conn)
    except (sqlite3.DatabaseError, ValueError, TypeError) as exc:
        return VerifyResult(
            STATUS_CORRUPT,
            [f"Verification query failed: {type(exc).__name__}: {exc}"],
            report,
        )

    # === FUNDING-COVERAGE GATE (additive stamp; does NOT change status) =========
    # Per docs/plans/FUNDING_COVERAGE_FAIL_CLOSED_GATE_PLAN.md §3-4. Mirrors the
    # legacy JSONL verifier's block at verify.py:601-634: runs ONLY when the
    # existing arithmetic verdict is OK; otherwise collapses to FAIL / empty
    # label. The status field, the trusted-baseline advancement rule (none in
    # the SQLite verifier; see ADR 0001), the connection mode (mode=ro,
    # query_only=1), the existing arithmetic check (lines 505-520), and the
    # content_digests keys are NOT touched. The stamp is read-only; no DB
    # mutation occurs.
    arithmetic_ok = not failures
    stamp = _build_funding_coverage_stamp(
        conn,
        arithmetic_ok=arithmetic_ok,
        source_resolution=source_resolution,
    )
    report.update(stamp)
    report["funding_source_coverage_verdict"] = report.get(
        "funding_coverage_verdict"
    )
    clean_carry_stamp = _build_funding_clean_carry_stamp(
        conn,
        db_path,
        cfg,
        report,
        arithmetic_ok=arithmetic_ok,
        source_resolution=source_resolution,
        source_mode=source_mode,
    )
    report.update(clean_carry_stamp)
    if arithmetic_ok:
        report["funding_coverage_verdict"] = report[
            "funding_clean_carry_decision"
        ]
        report["funding_coverage_diagnostic_label"] = (
            ""
            if report["funding_coverage_verdict"] == CLEAN_NET_OF_CARRY
            else CAVEATED_ENGINE_SEMANTICS_LABEL
        )

    # === BATCH-SCOPED CLEAN-CARRY STAMP (additive; does NOT change full-ledger) =
    batch_clean_carry_stamp = _build_funding_clean_carry_batch_stamp(
        conn,
        db_path,
        cfg,
        report,
        arithmetic_ok=arithmetic_ok,
        source_resolution=source_resolution,
    )
    report.update(batch_clean_carry_stamp)

    # === GIT-SHA PROVENANCE STAMP (additive; does NOT change status) ============
    # Operator-facing evidence of which code produced each committed batch. Like
    # the funding-coverage stamp, it is read-only and never flips the verdict:
    # historical git_sha=NULL rows are immutable unprovenanced evidence, not
    # corruption. New batches can no longer be NULL (writer fails closed).
    report.update(_build_git_provenance_stamp(conn))

    if (
        fail_on_source_path_unavailable
        and report.get("source_path_required")
        and not source_resolution.available
        and SOURCE_PATH_UNAVAILABLE_REASON not in failures
    ):
        failures.append(SOURCE_PATH_UNAVAILABLE_REASON)

    report["forward_start_ts"] = cfg["forward_start_ts"]
    report["failure_count"] = len(failures)
    if failures:
        return VerifyResult(STATUS_CORRUPT, failures, report)
    return VerifyResult(STATUS_OK, [], report)


def _open_snapshot(db_path: Path) -> sqlite3.Connection:
    """Open and pin one read-only SQLite snapshot for validation and digesting."""
    conn = connect_readonly(db_path)
    conn.execute("BEGIN")
    # The first read pins the WAL snapshot for all subsequent verifier queries.
    conn.execute("SELECT name FROM sqlite_master LIMIT 1").fetchone()
    return conn


def verify_database(
    db_path: str | Path | None = None,
    *,
    source_mode: str = SOURCE_MODE_LIVE_CURRENT,
) -> VerifyResult:
    """Verify one committed paper-ledger snapshot read-only. Never writes anything.

    ``source_mode`` selects how the clean-carry gate resolves funding-source
    evidence: ``live-current`` (default) reads the live CSVs and still detects
    drift; ``bundle`` validates against the pinned immutable source bundle.
    """
    if source_mode not in SOURCE_RESOLUTION_MODES:
        raise ValueError(f"unsupported source_mode: {source_mode!r}")
    db_path = get_paper_db_path(db_path)
    report = {"db_path": str(db_path), "disclaimer": VERIFIER_DISCLAIMER}
    if not Path(db_path).exists():
        report["error"] = "database file does not exist"
        return VerifyResult(STATUS_CONFIG_ERROR, [f"DB not found: {db_path}"], report)
    try:
        conn = _open_snapshot(Path(db_path))
    except sqlite3.Error as exc:
        return VerifyResult(
            STATUS_CONFIG_ERROR,
            [f"Could not open DB read-only: {type(exc).__name__}: {exc}"],
            report,
        )
    try:
        return _verify_connection(conn, Path(db_path), source_mode=source_mode)
    finally:
        conn.close()


# ---------------------------------------------------------------------------
# Authoritative publication (writes paper_verify_report.json / receipt / log)
# ---------------------------------------------------------------------------

def _now_utc_str(now: datetime | None = None) -> str:
    return (now or datetime.now(timezone.utc)).strftime("%Y-%m-%dT%H:%M:%SZ")


def _table_digest(conn: sqlite3.Connection, table: str) -> str:
    """Order-independent sha256 of every row in a committed table (read-only).

    Rows are canonicalized (sorted-key JSON) and then themselves sorted, so the digest is a
    stable fingerprint of the committed CONTENT regardless of physical rowid order. ``table``
    is always a hardcoded schema constant (never user input), so the f-string SQL is safe.
    """
    rows = [dict(r) for r in conn.execute(f"SELECT * FROM {table}").fetchall()]
    canon = sorted(json.dumps(r, sort_keys=True, default=str) for r in rows)
    h = hashlib.sha256()
    for line in canon:
        h.update(line.encode("utf-8"))
        h.update(b"\n")
    return h.hexdigest()


def _content_digests(conn: sqlite3.Connection) -> dict[str, str]:
    """Digest the same pinned read snapshot used for the verdict."""
    try:
        per_table: dict[str, str] = {}
        for table in _REQUIRED_TABLES:
            per_table[table] = _table_digest(conn, table)
    except sqlite3.DatabaseError:
        return {}
    combined = hashlib.sha256()
    for table in _REQUIRED_TABLES:
        combined.update(f"{table}:{per_table[table]}\n".encode("utf-8"))
    per_table["content_sha256"] = combined.hexdigest()
    return per_table


_VERDICT_LINE: dict[str, str] = {
    STATUS_OK: (
        "OK (simulation) — the committed SQLite paper ledger verified consistent read-only; "
        "this paper_verify_report.json is the authoritative paper status"
    ),
    STATUS_CORRUPT: "CORRUPT — integrity failure(s); the paper run is NOT trusted",
    STATUS_CONFIG_ERROR: (
        "CONFIG_ERROR — the DB/config identity is invalid/stale/unloadable; nothing can be "
        "verified against it"
    ),
    STATUS_PRE_START: (
        "PRE_START — a valid pre-start DB with no committed eligible bars yet; nothing to certify"
    ),
}


def _build_published_report(
    db_path: Path,
    result: VerifyResult,
    digests: dict[str, str],
    now: datetime | None,
) -> dict[str, Any]:
    """Wrap a VerifyResult in the authoritative report envelope (the on-disk report shape)."""
    status = result.status
    report: dict[str, Any] = {
        "schema_version": SCHEMA_VERSION,
        "verifier": "sqlite",
        "verifier_version": SQLITE_VERIFIER_VERSION,
        "authoritative": True,
        "verified_at": _now_utc_str(now),
        "db_path": str(db_path),
        "status": status,
        "exit_code": result.exit_code,
        # A paper run is trusted IFF this is true.
        "trusted": status == STATUS_OK,
        "failure_count": len(result.failures),
        "failures": list(result.failures),
        "content_digests": digests,
        "content_sha256": digests.get("content_sha256"),
        "snapshot_identity": {
            "content_sha256": digests.get("content_sha256"),
            "meaning": "authoritative verdict for this exact validated SQLite read snapshot",
        },
        "current_verdict": _VERDICT_LINE.get(status, status),
        "disclaimer": VERIFIER_DISCLAIMER,
    }
    # Carry forward the read-only metrics the core verifier collected (batches/events/equity/
    # watermark/forward_start_ts/config identity), without letting them shadow the envelope.
    for k, v in result.report.items():
        report.setdefault(k, v)
    return report


def _render_receipt(report: dict[str, Any]) -> str:
    status = report["status"]
    icon = {
        STATUS_OK: "✅",
        STATUS_CORRUPT: "🛑",
        STATUS_CONFIG_ERROR: "🛑",
        STATUS_PRE_START: "⏳",
    }.get(status, "❓")
    lines = [
        "# Paper PnL v1 — SQLite Verifier Receipt (AUTHORITATIVE)",
        "",
        f"> **{report['disclaimer']}**",
        "",
        f"## {icon} {status}",
        "",
        "- The latest `paper_verify_report.json` is the **authoritative** paper status. The "
        "committed `paper_ledger.db` and the accounting writer's returned status code are RAW "
        "accounting artifacts / a runner status only — NOT proof of a trusted run. A paper run "
        "is trusted **iff** this report's `status == OK`.",
        f"- Verified (UTC): {report['verified_at']}",
        f"- Verifier: {report['verifier']} v{report['verifier_version']}",
        f"- DB: {report['db_path']}",
        f"- Committed batches/events/equity rows: "
        f"{report.get('batches', '?')}/{report.get('events', '?')}/{report.get('equity_rows', '?')}",
        f"- forward_start_ts: {report.get('forward_start_ts', 'unknown')}",
        f"- Content digest: {report.get('content_sha256') or 'n/a'}",
        f"- Verdict: {report['current_verdict']}",
        "",
    ]
    if report["failures"]:
        lines.append(f"## Failures ({report['failure_count']})")
        for f in report["failures"]:
            lines.append(f"- {f}")
        lines.append("")
    # --- Funding coverage (additive stamp; does NOT change status) ---
    fc = report.get("funding_coverage")
    if fc is not None:
        fc_verdict = report.get("funding_coverage_verdict", "")
        fc_label = report.get("funding_coverage_diagnostic_label", "")
        fc_source_verdict = report.get("funding_source_coverage_verdict")
        lines.append("## Funding coverage")
        lines.append("")
        lines.append(f"- Verdict: {fc_verdict}")
        if fc_source_verdict is not None:
            lines.append(
                f"- Source coverage verdict before clean-carry gate: {fc_source_verdict}"
            )
        lines.append(
            f"- Diagnostic label: {fc_label if fc_label else '(empty)'}"
        )
        lines.append(f"- Decision: {fc.get('decision', 'n/a')}")
        lines.append(f"- Total funding rows: {fc.get('total_funding_rows', 0)}")
        lines.append(f"- Required intervals: {fc.get('total_required_intervals', 0)}")
        lines.append(
            f"- rate_available=0 rows: {fc.get('total_rate_available_zero', 0)}"
        )
        per_sym = fc.get("per_symbol") or {}
        if per_sym:
            lines.append(f"- Per-symbol coverage: {per_sym}")
        miss = fc.get("missing_window_ids") or []
        if miss:
            lines.append(f"- Missing windows ({len(miss)}):")
            for mw in miss:
                issue = mw.get("source_issue") or "n/a"
                lines.append(
                    f"  - {mw.get('symbol', '?')} @ bar_ts={mw.get('bar_ts', '?')} "
                    f"window=[{mw.get('window_start', '?')}, {mw.get('window_end', '?')}] "
                    f"source_issue={issue}"
                )
        lines.append("")
    # --- Strict funding clean-carry gate (additive; does NOT change status) ---
    fcc = report.get("funding_clean_carry")
    if isinstance(fcc, dict):
        lines.append("## Funding clean-carry gate")
        lines.append("")
        lines.append(f"- Decision: {fcc.get('decision', 'n/a')}")
        lines.append(f"- Status: {fcc.get('status', 'n/a')}")
        lines.append(f"- Reason codes: {fcc.get('reason_codes') or []}")
        lines.append(
            f"- Snapshot SHA-256: {fcc.get('snapshot_sha256') or '(none)'}"
        )
        lines.append(
            f"- Source bundle SHA-256: "
            f"{fcc.get('source_bundle_sha256') or '(none)'}"
        )
        resum = fcc.get("resum_check") or {}
        if isinstance(resum, dict):
            lines.append(f"- Re-sum status: {resum.get('status', 'n/a')}")
            lines.append(
                f"- Re-sum funding sum/state/equity: "
                f"{resum.get('funding_amount_sum')} / "
                f"{resum.get('ledger_state_funding_cum')} / "
                f"{resum.get('latest_equity_funding_cum')}"
            )
        lines.append(f"- Note: {fcc.get('note') or FUNDING_CLEAN_CARRY_NOTE}")
        lines.append("")
    # --- Funding source snapshot sidecars (diagnostic; does NOT change status) ---
    fss = report.get("funding_source_snapshot")
    if fss is not None:
        lines.append("## Funding source snapshot")
        lines.append("")
        lines.append(f"- Status: {fss.get('status', 'n/a')}")
        lines.append(f"- Diagnostic only: {fss.get('diagnostic_only') is True}")
        lines.append(f"- Clean-mode gate: {fss.get('clean_mode_gate', 'n/a')}")
        lines.append(f"- Candidate count: {fss.get('candidate_count', 0)}")
        lines.append(
            f"- Snapshot SHA-256: {fss.get('snapshot_sha256') or '(none)'}"
        )
        lines.append(
            f"- Source bundle SHA-256: "
            f"{fss.get('source_bundle_sha256') or '(none)'}"
        )
        lines.append(
            f"- Note: {fss.get('note') or FUNDING_SOURCE_SNAPSHOT_DIAGNOSTIC_NOTE}"
        )
        caveat = fss.get("caveat")
        if caveat:
            lines.append(f"- Caveat: {caveat}")
        reason = fss.get("reason")
        if reason:
            lines.append(f"- Reason: {reason}")
        reason_codes = fss.get("future_clean_mode_reason_codes") or []
        if reason_codes:
            lines.append(f"- Future clean-mode refusal codes: {reason_codes}")
        lines.append("")
    # --- Git-SHA provenance (additive stamp; does NOT change status) ---
    gp = report.get("git_provenance")
    if gp is not None:
        gp_warning = report.get("git_provenance_warning")
        lines.append("## Git provenance")
        lines.append("")
        latest_sha = gp.get("latest_batch_git_sha")
        lines.append(f"- Latest batch id: {gp.get('latest_batch_id')}")
        lines.append(f"- Latest batch git_sha: {latest_sha or '(missing)'}")
        lines.append(
            f"- Latest batch git_sha missing: {gp.get('latest_batch_git_sha_missing')}"
        )
        lines.append(
            f"- Batches missing git_sha: {gp.get('batches_missing_git_sha', 0)} "
            f"(any missing: {gp.get('any_batch_missing_git_sha')})"
        )
        unprov = gp.get("unprovenanced_batch_ids") or []
        if unprov:
            lines.append(f"- Unprovenanced batch ids: {unprov}")
        if gp_warning:
            lines.append(f"- ⚠️ {gp_warning}")
        lines.append("")
    return "\n".join(lines)


def verify_and_publish(
    db_path: str | Path | None = None,
    output_dir: str | Path | None = None,
    *,
    now: datetime | None = None,
    write_log: bool = True,
) -> VerifyResult:
    """Verify the DB read-only and PUBLISH the authoritative report/receipt/log atomically.

    This is the only component allowed to publish an authoritative paper status. It validates and
    computes content digests through one pinned read-only SQLite snapshot, then writes:

      - ``paper_verify_report.json``  (authoritative latest terminal report)
      - ``paper_verify_receipt.md``   (human receipt)
      - ``paper_verify_log.jsonl``    (append-only audit trail; NON-gating) when ``write_log``

    Artifacts go to ``output_dir`` (default: the DB's directory). The DB is only ever read
    (read-only / query-only); no runner artifact is mutated. The receipt is written first and the
    authoritative report last, so a crash mid-publish leaves the prior report in place rather than a
    truncated/false one. The returned ``VerifyResult.report`` is the published envelope.
    """
    db_path = get_paper_db_path(db_path)
    out = Path(output_dir) if output_dir is not None else Path(db_path).parent

    report_seed = {"db_path": str(db_path), "disclaimer": VERIFIER_DISCLAIMER}
    if not Path(db_path).exists():
        result = VerifyResult(STATUS_CONFIG_ERROR, [f"DB not found: {db_path}"], report_seed)
        digests: dict[str, str] = {}
    else:
        try:
            conn = _open_snapshot(Path(db_path))
        except sqlite3.Error as exc:
            result = VerifyResult(
                STATUS_CONFIG_ERROR,
                [f"Could not open DB read-only: {type(exc).__name__}: {exc}"],
                report_seed,
            )
            digests = {}
        else:
            try:
                result = _verify_connection(conn, Path(db_path))
                digests = _content_digests(conn)
                if result.status == STATUS_OK and not digests.get("content_sha256"):
                    result = VerifyResult(
                        STATUS_CORRUPT,
                        ["Could not digest the validated SQLite snapshot"],
                        result.report,
                    )
            finally:
                conn.close()
    report = _build_published_report(Path(db_path), result, digests, now)

    out.mkdir(parents=True, exist_ok=True)
    ledger.write_text_atomic(out / RECEIPT_FILE, _render_receipt(report))
    ledger.write_json_atomic(out / REPORT_FILE, report)
    if write_log:
        ledger.append_rows(
            out / LOG_FILE,
            [{
                "verified_at": report["verified_at"],
                "status": report["status"],
                "trusted": report["trusted"],
                "failure_count": report["failure_count"],
                "content_sha256": report.get("content_sha256"),
                "verifier_version": SQLITE_VERIFIER_VERSION,
            }],
        )

    result.report = report
    return result


# ---------------------------------------------------------------------------
# Read-only CLI
# (docs/plans/QNTY_READ_ONLY_PROD_DB_LINKED_SNAPSHOT_ACCEPTANCE_AUDIT.md contract,
# specified by tests/test_paper_sqlite_verify_read_only_cli_contract.py)
# ---------------------------------------------------------------------------

CLI_CONTRACT_VERSION = "1.0.0"


def _open_readonly_immutable_connection(db_path: Path) -> sqlite3.Connection:
    """Open *db_path* via the strict CLI read-only contract.

    Uses ``file:<abs>?mode=ro&immutable=1`` + ``PRAGMA query_only=ON``. Unlike
    :func:`quantbot.paper.db.connect_readonly` (plain ``mode=ro``, used by
    :func:`verify_database` via :func:`_open_snapshot`), ``immutable=1`` tells
    SQLite the file will never change for the life of the connection, so it
    skips WAL-index setup and never creates ``-wal``/``-shm`` sidecars even
    against a WAL-mode DB — the stronger no-side-effect guarantee this CLI
    makes for a prod DB-linked read-only audit.
    """
    conn = sqlite3.connect(f"file:{db_path}?mode=ro&immutable=1", uri=True)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA query_only=ON")
    return conn


def verify_database_readonly_cli(
    db_path: Path,
    *,
    data_dir: Path | None = None,
) -> VerifyResult:
    """CLI verification entry point.

    Reuses :func:`_verify_connection` — the same structural / arithmetic /
    funding clean-carry gate logic :func:`verify_database` uses — over a
    connection opened via the stricter immutable read-only URI above. Never
    runs schema-ensure helpers, migrations, or writer code.
    """
    report: dict[str, Any] = {"db_path": str(db_path)}
    if not db_path.exists():
        return VerifyResult(STATUS_CONFIG_ERROR, [f"DB not found: {db_path}"], report)
    try:
        conn = _open_readonly_immutable_connection(db_path)
    except sqlite3.Error as exc:
        return VerifyResult(
            STATUS_CONFIG_ERROR,
            [f"Could not open DB read-only: {type(exc).__name__}: {exc}"],
            report,
        )
    try:
        return _verify_connection(
            conn,
            db_path,
            data_dir=data_dir,
            allow_db_relative_data=True,
            fail_on_source_path_unavailable=True,
        )
    finally:
        conn.close()


def _build_cli_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="python -m quantbot.paper.sqlite_verify",
        description=(
            "Read-only SQLite paper-ledger verifier. Opens --db-path via "
            "file:<abs>?mode=ro&immutable=1 with PRAGMA query_only=ON, runs "
            "the existing structural/arithmetic/funding clean-carry gate "
            "read-only, and emits one JSON report. Never writes the DB, "
            "never runs schema-ensure/migration/writer code, and never "
            "creates -wal/-shm sidecars or paper_verify_report.json/receipt/"
            "log files (that is verify_and_publish's job, not this CLI's)."
        ),
    )
    parser.add_argument(
        "--db-path",
        required=True,
        help=(
            "Absolute path to paper_ledger.db. Required; there is no "
            "implicit prod DB path in this CLI mode, and relative paths "
            "are rejected."
        ),
    )
    parser.add_argument(
        "--read-only",
        action="store_true",
        required=True,
        help=(
            "Open the DB via the immutable read-only URI contract "
            "(file:<abs>?mode=ro&immutable=1) and PRAGMA query_only=ON. "
            "This CLI has no write mode; the flag is required so that is "
            "explicit at every call site."
        ),
    )
    parser.add_argument(
        "--json",
        action="store_true",
        required=True,
        help="Emit a single JSON verification report to stdout.",
    )
    parser.add_argument(
        "--data-dir",
        help=(
            "Absolute path to the directory containing source funding CSVs. "
            "Relative paths are rejected; missing absolute paths fail closed "
            "through the JSON report."
        ),
    )
    parser.add_argument(
        "--strict-clean-carry",
        action="store_true",
        help=(
            "Also fail closed (nonzero exit) when "
            "funding_clean_carry_decision is not CLEAN_NET_OF_CARRY. "
            "Diagnostic-only: never changes any report field, only the "
            "process exit code."
        ),
    )
    parser.add_argument(
        "--no-wal-checkpoint",
        action="store_true",
        help=(
            "No-op safety flag: this CLI never runs a WAL checkpoint, with "
            "or without this flag. Accepted for forward-compatible receipt "
            "tooling."
        ),
    )
    return parser


def _cli_report(result: VerifyResult, db_path: Path, *, read_only: bool) -> dict[str, Any]:
    report = dict(result.report)
    report["status"] = result.status
    report["read_only"] = read_only
    report["db_path"] = str(db_path)
    report["db_mutation_performed"] = False
    report["query_only_pragma_enabled"] = (
        bool(report["query_only"]) if "query_only" in report else read_only
    )
    report["wal_shm_files_created"] = False
    report["sqlite_open_mode"] = (
        "file_uri_mode_ro_immutable" if read_only else "file_uri_mode_ro"
    )
    report["verifier_cli_contract_version"] = CLI_CONTRACT_VERSION
    if result.failures:
        report["failures"] = result.failures
    return report


def main(argv: list[str] | None = None) -> int:
    parser = _build_cli_arg_parser()
    args = parser.parse_args(argv)

    db_path = Path(args.db_path)
    if not db_path.is_absolute():
        parser.error(f"--db-path must be an absolute path, got: {args.db_path!r}")

    data_dir = Path(args.data_dir) if args.data_dir else None
    if data_dir is not None and not data_dir.is_absolute():
        parser.error(f"--data-dir must be an absolute path, got: {args.data_dir!r}")

    result = verify_database_readonly_cli(db_path, data_dir=data_dir)
    report = _cli_report(result, db_path, read_only=bool(args.read_only))

    exit_code = result.exit_code
    if (
        args.strict_clean_carry
        and exit_code == EXIT_CODE[STATUS_OK]
        and report.get("funding_clean_carry_decision") != CLEAN_NET_OF_CARRY
    ):
        exit_code = EXIT_CODE[STATUS_CORRUPT]

    print(json.dumps(report, sort_keys=True, default=str))
    return exit_code


if __name__ == "__main__":
    raise SystemExit(main())


__all__ = [
    "STATUS_OK",
    "STATUS_CONFIG_ERROR",
    "STATUS_CORRUPT",
    "STATUS_PRE_START",
    "FUNDING_SOURCE_SNAPSHOT_STATUS_MISSING",
    "FUNDING_SOURCE_SNAPSHOT_STATUS_PRESENT_VALID",
    "FUNDING_SOURCE_SNAPSHOT_STATUS_DIGEST_MISMATCH",
    "FUNDING_SOURCE_SNAPSHOT_STATUS_SCHEMA_UNSUPPORTED",
    "FUNDING_SOURCE_SNAPSHOT_STATUS_PAYLOAD_INVALID",
    "FUNDING_SOURCE_SNAPSHOT_STATUS_DB_OR_LANE_MISMATCH",
    "FUNDING_SOURCE_SNAPSHOT_STATUS_PENDING_OR_ORPHANED",
    "FUNDING_SOURCE_SNAPSHOT_STATUS_AMBIGUOUS_MULTIPLE",
    "EXIT_CODE",
    "VERIFIER_DISCLAIMER",
    "SQLITE_VERIFIER_VERSION",
    "REPORT_FILE",
    "RECEIPT_FILE",
    "LOG_FILE",
    "VerifyResult",
    "verify_database",
    "verify_and_publish",
    "verify_database_readonly_cli",
    "CLI_CONTRACT_VERSION",
    "main",
]
