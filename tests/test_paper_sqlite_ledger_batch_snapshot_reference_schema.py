"""Test-only spec for ledger batch funding snapshot reference columns.

All tests use tmp SQLite DBs and tmp funding source snapshot sidecars only. They
never run prod/shadow writers, never touch /srv, and never mutate forward_obs.
Current production may xfail until the DB-linked selector implementation PR.
"""

from __future__ import annotations

import sqlite3
from pathlib import Path
from typing import Any

import pytest

from quantbot.paper.config import build_config
from quantbot.paper.db import initialize_database
from quantbot.paper.funding_status import (
    CAVEATED_ENGINE_SEMANTICS,
    CLEAN_NET_OF_CARRY,
)
from quantbot.paper.sqlite_verify import (
    FUNDING_CLEAN_CARRY_STATUS_CLEAN,
    FUNDING_CLEAN_CARRY_STATUS_REFUSED_DIGEST_MISMATCH,
    FUNDING_CLEAN_CARRY_STATUS_REFUSED_MISSING_SNAPSHOT,
    STATUS_OK,
    verify_database,
)
from tests.test_paper_sqlite_verifier_clean_net_of_carry_gate import (
    _add_latest_equity_snapshot,
    _committed_snapshot,
    _db_with_complete_source,
    _write_snapshot,
)

IMPLEMENTATION_PENDING_REASON = (
    "ledger batch snapshot reference schema not implemented yet"
)

implementation_pending = pytest.mark.xfail(
    raises=AssertionError,
    reason=IMPLEMENTATION_PENDING_REASON,
    strict=True,
)

REQUIRED_SNAPSHOT_REFERENCE_COLUMNS = {
    "funding_source_snapshot_path": "TEXT",
    "funding_source_snapshot_sha256": "TEXT",
    "funding_source_snapshot_bundle_sha256": "TEXT",
    "funding_source_snapshot_schema_version": "TEXT",
    "funding_source_snapshot_write_state": "TEXT",
    "funding_source_snapshot_created_at": "TEXT",
}

OPTIONAL_LATER_SNAPSHOT_REFERENCE_COLUMNS = {
    "funding_source_snapshot_payload_sha256",
    "funding_source_snapshot_reason_codes_json",
}

EXISTING_LEDGER_BATCHES_COLUMN_CONTRACT = {
    "batch_id": ("INTEGER", 0),
    "created_at": ("TEXT", 1),
    "started_at": ("TEXT", 0),
    "committed_at": ("TEXT", 0),
    "git_sha": ("TEXT", 0),
    "prior_watermark_bar_ts": ("TEXT", 0),
    "new_watermark_bar_ts": ("TEXT", 0),
    "first_event_seq": ("INTEGER", 0),
    "last_event_seq": ("INTEGER", 0),
    "event_count": ("INTEGER", 1),
    "committed_bar_count": ("INTEGER", 1),
    "paper_engine_version": ("TEXT", 1),
    "config_hash": ("TEXT", 1),
    "lane_id": ("TEXT", 0),
}


def _empty_db(tmp_path: Path) -> Path:
    db_path = tmp_path / "paper" / "paper_ledger.db"
    db_path.parent.mkdir(parents=True, exist_ok=True)
    config = build_config(
        forward_start_ts="2026-06-14T00:00:00",
        initial_equity_usd=10000.0,
        notional_usd=1000.0,
        fee_bps=5.0,
        slippage_bps=5.0,
        max_bar_staleness_hours=72.0,
    )
    initialize_database(db_path, config)
    return db_path


def _ledger_batches_schema(db_path: Path) -> dict[str, dict[str, Any]]:
    conn = sqlite3.connect(str(db_path))
    try:
        rows = conn.execute("PRAGMA table_info(ledger_batches)").fetchall()
    finally:
        conn.close()

    schema: dict[str, dict[str, Any]] = {}
    for _cid, name, declared_type, notnull, default_value, pk in rows:
        schema[str(name)] = {
            "type": str(declared_type).upper(),
            "notnull": int(notnull),
            "default": default_value,
            "pk": int(pk),
        }
    return schema


def _require_snapshot_reference_schema(db_path: Path) -> dict[str, dict[str, Any]]:
    schema = _ledger_batches_schema(db_path)
    missing = [
        name for name in REQUIRED_SNAPSHOT_REFERENCE_COLUMNS if name not in schema
    ]
    assert missing == []
    for name, declared_type in REQUIRED_SNAPSHOT_REFERENCE_COLUMNS.items():
        assert schema[name]["type"] == declared_type
        assert schema[name]["notnull"] == 0
    return schema


def _add_test_only_snapshot_reference_columns(db_path: Path) -> None:
    existing = _ledger_batches_schema(db_path)
    conn = sqlite3.connect(str(db_path))
    try:
        for name in REQUIRED_SNAPSHOT_REFERENCE_COLUMNS:
            if name not in existing:
                conn.execute(f"ALTER TABLE ledger_batches ADD COLUMN {name} TEXT")
        conn.commit()
    finally:
        conn.close()


def _db_ready_for_clean_gate_with_reference_columns(tmp_path: Path) -> Path:
    db_path = _db_with_complete_source(tmp_path)
    _add_latest_equity_snapshot(db_path)
    _add_test_only_snapshot_reference_columns(db_path)
    return db_path


def _latest_batch_id(db_path: Path) -> int:
    conn = sqlite3.connect(str(db_path))
    try:
        row = conn.execute(
            "SELECT batch_id FROM ledger_batches ORDER BY batch_id DESC LIMIT 1"
        ).fetchone()
    finally:
        conn.close()
    assert row is not None
    return int(row[0])


def _insert_old_style_ledger_batch(conn: sqlite3.Connection) -> int:
    cur = conn.execute(
        """
        INSERT INTO ledger_batches (
            created_at, started_at, prior_watermark_bar_ts,
            paper_engine_version, config_hash
        ) VALUES (?, ?, ?, ?, ?)
        """,
        (
            "2026-06-15T09:00:00Z",
            "2026-06-15T09:00:00Z",
            None,
            "test-engine",
            "test-config-hash",
        ),
    )
    return int(cur.lastrowid)


def _set_latest_batch_snapshot_reference(
    db_path: Path,
    path: Path,
    envelope: dict[str, Any],
    **overrides: Any,
) -> None:
    payload = envelope["snapshot_payload"]
    values = {
        "funding_source_snapshot_path": str(path),
        "funding_source_snapshot_sha256": envelope["snapshot_sha256"],
        "funding_source_snapshot_bundle_sha256": payload["source_bundle_sha256"],
        "funding_source_snapshot_schema_version": payload["schema_version"],
        "funding_source_snapshot_write_state": payload["write_state"],
        "funding_source_snapshot_created_at": payload["generated_at_utc"],
    }
    values.update(overrides)

    assignments = ", ".join(f"{name} = ?" for name in values)
    params = [values[name] for name in values]
    params.append(_latest_batch_id(db_path))
    conn = sqlite3.connect(str(db_path))
    try:
        conn.execute(
            f"UPDATE ledger_batches SET {assignments} WHERE batch_id = ?",
            params,
        )
        conn.commit()
    finally:
        conn.close()


def _clean_carry_report(db_path: Path) -> dict[str, Any]:
    result = verify_database(db_path)
    assert result.status == STATUS_OK, result.failures
    return result.report["funding_clean_carry"]


def test_only_spec_optional_later_snapshot_reference_columns_are_not_required_yet() -> None:
    assert OPTIONAL_LATER_SNAPSHOT_REFERENCE_COLUMNS.isdisjoint(
        REQUIRED_SNAPSHOT_REFERENCE_COLUMNS
    )


@implementation_pending
def test_only_spec_current_production_may_xfail_new_schema_includes_all_six_nullable_snapshot_reference_columns(
    tmp_path: Path,
) -> None:
    db_path = _empty_db(tmp_path)

    schema = _require_snapshot_reference_schema(db_path)

    assert set(REQUIRED_SNAPSHOT_REFERENCE_COLUMNS) <= set(schema)


@implementation_pending
def test_only_spec_current_production_may_xfail_snapshot_reference_columns_are_nullable_for_historical_rows(
    tmp_path: Path,
) -> None:
    db_path = _empty_db(tmp_path)

    schema = _require_snapshot_reference_schema(db_path)

    for name in REQUIRED_SNAPSHOT_REFERENCE_COLUMNS:
        assert schema[name]["notnull"] == 0


@implementation_pending
def test_only_spec_current_production_may_xfail_existing_insert_path_can_create_old_style_batch_with_null_snapshot_refs(
    tmp_path: Path,
) -> None:
    db_path = _empty_db(tmp_path)
    _require_snapshot_reference_schema(db_path)
    conn = sqlite3.connect(str(db_path))
    try:
        batch_id = _insert_old_style_ledger_batch(conn)
        conn.commit()
        row = conn.execute(
            "SELECT "
            + ", ".join(REQUIRED_SNAPSHOT_REFERENCE_COLUMNS)
            + " FROM ledger_batches WHERE batch_id = ?",
            (batch_id,),
        ).fetchone()
    finally:
        conn.close()

    assert row is not None
    assert all(value is None for value in row)


@implementation_pending
def test_only_spec_current_production_may_xfail_old_null_snapshot_reference_row_stays_caveated_even_with_sidecar(
    tmp_path: Path,
) -> None:
    db_path = _db_ready_for_clean_gate_with_reference_columns(tmp_path)
    _write_snapshot(db_path, _committed_snapshot(db_path))

    clean = _clean_carry_report(db_path)

    assert clean["decision"] == CAVEATED_ENGINE_SEMANTICS
    assert clean["decision"] != CLEAN_NET_OF_CARRY
    assert clean["status"] == FUNDING_CLEAN_CARRY_STATUS_REFUSED_MISSING_SNAPSHOT
    assert "funding_source_snapshot_missing" in clean["reason_codes"]


@implementation_pending
def test_only_spec_current_production_may_xfail_populated_reference_selects_batch_snapshot_deterministically(
    tmp_path: Path,
) -> None:
    db_path = _db_ready_for_clean_gate_with_reference_columns(tmp_path)
    envelope = _committed_snapshot(db_path)
    selected_path = _write_snapshot(db_path, envelope, suffix="selected")
    _write_snapshot(db_path, _committed_snapshot(db_path), suffix="extra")
    _set_latest_batch_snapshot_reference(db_path, selected_path, envelope)

    result = verify_database(db_path)
    clean = result.report["funding_clean_carry"]
    snapshot = result.report.get("funding_source_snapshot", {})

    assert result.status == STATUS_OK, result.failures
    assert snapshot.get("selected_snapshot_path") == str(selected_path)
    assert snapshot.get("snapshot_sha256") == envelope["snapshot_sha256"]
    assert clean["status"] == FUNDING_CLEAN_CARRY_STATUS_CLEAN
    assert clean["decision"] == CLEAN_NET_OF_CARRY


@implementation_pending
def test_only_spec_current_production_may_xfail_snapshot_sha_is_exact_selector_not_directory_scan_fallback(
    tmp_path: Path,
) -> None:
    db_path = _db_ready_for_clean_gate_with_reference_columns(tmp_path)
    envelope = _committed_snapshot(db_path)
    selected_path = _write_snapshot(db_path, envelope)
    _set_latest_batch_snapshot_reference(
        db_path,
        selected_path,
        envelope,
        funding_source_snapshot_sha256="0" * 64,
    )

    clean = _clean_carry_report(db_path)

    assert clean["decision"] == CAVEATED_ENGINE_SEMANTICS
    assert clean["decision"] != CLEAN_NET_OF_CARRY
    assert clean["status"] == FUNDING_CLEAN_CARRY_STATUS_REFUSED_DIGEST_MISMATCH
    assert "funding_source_snapshot_digest_mismatch" in clean["reason_codes"]


@implementation_pending
def test_only_spec_current_production_may_xfail_multiple_sidecars_do_not_matter_when_db_reference_is_exact(
    tmp_path: Path,
) -> None:
    db_path = _db_ready_for_clean_gate_with_reference_columns(tmp_path)
    envelope = _committed_snapshot(db_path)
    selected_path = _write_snapshot(db_path, envelope, suffix="selected")
    _write_snapshot(
        db_path,
        _committed_snapshot(db_path, lane_id="other_lane"),
        suffix="unrelated",
    )
    _set_latest_batch_snapshot_reference(db_path, selected_path, envelope)

    clean = _clean_carry_report(db_path)

    assert clean["status"] == FUNDING_CLEAN_CARRY_STATUS_CLEAN
    assert clean["decision"] == CLEAN_NET_OF_CARRY
    assert clean["snapshot_sha256"] == envelope["snapshot_sha256"]


@implementation_pending
def test_only_spec_current_production_may_xfail_missing_db_reference_fields_refuse_clean_net_of_carry(
    tmp_path: Path,
) -> None:
    db_path = _db_ready_for_clean_gate_with_reference_columns(tmp_path)
    envelope = _committed_snapshot(db_path)
    selected_path = _write_snapshot(db_path, envelope)
    _set_latest_batch_snapshot_reference(
        db_path,
        selected_path,
        envelope,
        funding_source_snapshot_bundle_sha256=None,
        funding_source_snapshot_schema_version=None,
        funding_source_snapshot_write_state=None,
        funding_source_snapshot_created_at=None,
    )

    clean = _clean_carry_report(db_path)

    assert clean["decision"] == CAVEATED_ENGINE_SEMANTICS
    assert clean["decision"] != CLEAN_NET_OF_CARRY
    assert clean["status"] == FUNDING_CLEAN_CARRY_STATUS_REFUSED_MISSING_SNAPSHOT
    assert "funding_source_snapshot_missing" in clean["reason_codes"]


@implementation_pending
def test_only_spec_current_production_may_xfail_snapshot_schema_change_is_additive_only(
    tmp_path: Path,
) -> None:
    db_path = _empty_db(tmp_path)
    schema = _require_snapshot_reference_schema(db_path)

    for name, (declared_type, notnull) in EXISTING_LEDGER_BATCHES_COLUMN_CONTRACT.items():
        assert name in schema
        assert schema[name]["type"] == declared_type
        assert schema[name]["notnull"] == notnull

    assert OPTIONAL_LATER_SNAPSHOT_REFERENCE_COLUMNS.isdisjoint(schema)
