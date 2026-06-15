"""Receipt schema, deterministic hashing, read-only enforcement, and DEFERRED paths.

All fixtures are built in ``tmp_path``; nothing here touches ``/srv/qnty`` or calls
``systemctl``. The fixture DB reuses the real ledger DDL (``_SCHEMA_SQL``) so column/table
assumptions stay honest, but is populated with a handful of deterministic rows.
"""

from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest

from quantbot.core.determinism import sha256_file
from quantbot.paper.db import _SCHEMA_SQL, connect_writer
from quantbot.paper.ledger import write_json_atomic
from quantbot.sidecars import ledger_ro
from quantbot.sidecars.ledger_ro import (
    LedgerLocked,
    open_ro,
    physical_metadata,
    read_head_ro,
)
from quantbot.sidecars.receipt import (
    build_health_receipt,
    build_watchdog_receipt,
)
from quantbot.sidecars.time_bars import evaluate_watchdog

import scripts.health_receipt as health
import scripts.watermark_watchdog as watchdog


# --------------------------------------------------------------------------------------------
# Fixtures
# --------------------------------------------------------------------------------------------

def _make_ledger_fixture(
    db_path: Path,
    *,
    watermark: str = "2026-06-15T08:00:00",
    equity: float = 10000.5,
    drawdown: float = -12.25,
) -> Path:
    """Build a minimal but schema-faithful paper ledger with deterministic rows."""
    db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = connect_writer(db_path)
    try:
        conn.executescript(_SCHEMA_SQL)  # real DDL; append-only triggers intentionally omitted
        conn.execute(
            "INSERT INTO ledger_batches (batch_id, created_at, event_count, "
            "committed_bar_count, paper_engine_version, config_hash) "
            "VALUES (1, ?, 0, 1, '0.3.0', 'cfg')",
            ("2026-06-15T08:20:00Z",),
        )
        # Two generic events, then the equity event whose seq the equity snapshot references.
        for et, key in (("signal_snapshot", "s1"), ("fill", "f1")):
            conn.execute(
                "INSERT INTO ledger_events (batch_id, event_type, event_key, recorded_at, "
                "bar_ts) VALUES (1, ?, ?, '2026-06-15T08:20:00Z', ?)",
                (et, key, watermark),
            )
        cur = conn.execute(
            "INSERT INTO ledger_events (batch_id, event_type, event_key, recorded_at, bar_ts) "
            "VALUES (1, 'equity_snapshot', 'e1', '2026-06-15T08:20:00Z', ?)",
            (watermark,),
        )
        eq_seq = cur.lastrowid
        conn.execute(
            "INSERT INTO equity_snapshots (seq, batch_id, bar_ts, bar_commit_id, "
            "realized_gross_pnl, unrealized_pnl, funding_cum, fees_cum, equity, drawdown, "
            "num_open) VALUES (?, 1, ?, 'commit1', 0.0, 0.0, 0.0, 0.0, ?, ?, 0)",
            (eq_seq, watermark, equity, drawdown),
        )
        conn.execute(
            "INSERT INTO ledger_state (id, watermark_bar_ts, updated_at) "
            "VALUES (1, ?, '2026-06-15T08:20:00Z')",
            (watermark,),
        )
        conn.commit()
    finally:
        conn.close()
    return db_path


def _make_report(paper_dir: Path) -> Path:
    """Write a deterministic paper_verify_report.json fixture."""
    paper_dir.mkdir(parents=True, exist_ok=True)
    report = {
        "schema_version": 1,
        "status": "OK",
        "exit_code": 0,
        "failure_count": 0,
        "batches": 5,
        "events": 39,
        "equity_rows": 5,
        "watermark_bar_ts": "2026-06-15T08:00:00",
        "content_sha256": "deadbeef",
    }
    path = paper_dir / "paper_verify_report.json"
    write_json_atomic(path, report)
    return path


# --------------------------------------------------------------------------------------------
# Deterministic hashing & reproducible fingerprint
# --------------------------------------------------------------------------------------------

def test_report_hash_is_deterministic(tmp_path: Path) -> None:
    report_path = _make_report(tmp_path / "paper")
    assert sha256_file(report_path) == sha256_file(report_path)


def test_head_fingerprint_reproducible_across_two_reads(tmp_path: Path) -> None:
    db_path = _make_ledger_fixture(tmp_path / "paper" / "paper_ledger.db")
    first = read_head_ro(db_path)
    second = read_head_ro(db_path)
    assert first["head_fingerprint"] == second["head_fingerprint"]
    # The fingerprint reflects the stable logical head, not the physical file.
    assert first["components"]["watermark_bar_ts"] == "2026-06-15T08:00:00"
    assert first["components"]["latest_equity"]["equity"] == pytest.approx(10000.5)
    assert first["components"]["counts"]["equity_snapshots"] == 1


def test_head_fingerprint_changes_when_watermark_changes(tmp_path: Path) -> None:
    a = read_head_ro(_make_ledger_fixture(tmp_path / "a" / "paper_ledger.db"))
    b = read_head_ro(
        _make_ledger_fixture(tmp_path / "b" / "paper_ledger.db", watermark="2026-06-15T16:00:00")
    )
    assert a["head_fingerprint"] != b["head_fingerprint"]


def test_physical_metadata_records_no_raw_db_hash(tmp_path: Path) -> None:
    db_path = _make_ledger_fixture(tmp_path / "paper" / "paper_ledger.db")
    meta = physical_metadata(db_path)
    assert meta["db_size_bytes"] > 0
    assert meta["db_mtime_utc"] is not None
    assert "wal_present" in meta
    # Forensic metadata must NOT contain a hash of the .db file.
    assert not any("sha" in k.lower() or "hash" in k.lower() for k in meta)


# --------------------------------------------------------------------------------------------
# Read-only enforcement
# --------------------------------------------------------------------------------------------

def test_open_ro_rejects_writes(tmp_path: Path) -> None:
    db_path = _make_ledger_fixture(tmp_path / "paper" / "paper_ledger.db")
    conn = open_ro(db_path)
    try:
        with pytest.raises(sqlite3.OperationalError):
            conn.execute(
                "INSERT INTO ledger_state (id, watermark_bar_ts, updated_at) "
                "VALUES (2, 'x', 'y')"
            )
    finally:
        conn.close()


# --------------------------------------------------------------------------------------------
# Receipt schema — required keys
# --------------------------------------------------------------------------------------------

REQUIRED_HEALTH_KEYS = {
    "receipt_type", "schema_version", "generated_at_utc", "generator_commit",
    "expected_commit", "commit_matches_expected", "working_tree_clean", "paper_report",
    "paper_report_sha256", "ledger_head", "ledger_physical", "services", "host", "overall",
}

REQUIRED_WATCHDOG_KEYS = {
    "receipt_type", "schema_version", "generated_at_utc", "generator_commit", "status",
    "overall", "now_utc", "grace_minutes", "processing_lag_bars", "latest_boundary",
    "expected_min_watermark", "observed_watermark",
}


def test_health_receipt_has_required_keys(tmp_path: Path) -> None:
    db_path = _make_ledger_fixture(tmp_path / "paper" / "paper_ledger.db")
    head = read_head_ro(db_path)
    receipt = build_health_receipt(
        generator_commit="abc123",
        expected_commit=None,
        paper_report={"status": "OK", "exit_code": 0, "failure_count": 0, "batches": 5,
                      "events": 39, "equity_rows": 5, "watermark_bar_ts": "2026-06-15T08:00:00"},
        paper_report_sha256="feed",
        ledger_head=head,
        ledger_physical=physical_metadata(db_path),
        services={"qnty-paper-pnl.service": "unknown"},
        host={"disk_free_bytes": "unknown"},
        overall="OK",
        tree_clean=True,
    )
    assert REQUIRED_HEALTH_KEYS <= set(receipt)
    assert receipt["commit_matches_expected"] is None  # no expected commit supplied
    assert receipt["receipt_type"] == "health"


def test_health_commit_match_is_boolean_when_expected_supplied() -> None:
    match = build_health_receipt(
        generator_commit="abc", expected_commit="abc", paper_report=None,
        paper_report_sha256=None, ledger_head=None, ledger_physical=None,
        services={}, host={}, overall="OK", tree_clean=True,
    )
    mismatch = build_health_receipt(
        generator_commit="abc", expected_commit="zzz", paper_report=None,
        paper_report_sha256=None, ledger_head=None, ledger_physical=None,
        services={}, host={}, overall="WARN", tree_clean=True,
    )
    assert match["commit_matches_expected"] is True
    assert mismatch["commit_matches_expected"] is False


def test_watchdog_receipt_has_required_keys() -> None:
    from datetime import datetime, timezone

    status, detail = evaluate_watchdog(
        "2026-06-15T08:00:00", datetime(2026, 6, 15, 12, tzinfo=timezone.utc), 60
    )
    receipt = build_watchdog_receipt(
        status=status, overall=status, detail=detail, generator_commit="abc123"
    )
    assert REQUIRED_WATCHDOG_KEYS <= set(receipt)
    assert receipt["receipt_type"] == "watchdog"
    assert receipt["status"] == "OK"
    assert receipt["processing_lag_bars"] == 1


# --------------------------------------------------------------------------------------------
# DEFERRED-on-lock paths (simulated) — never spin-retry, always exit 0
# --------------------------------------------------------------------------------------------

def test_health_main_deferred_on_lock(tmp_path: Path, monkeypatch) -> None:
    db_path = _make_ledger_fixture(tmp_path / "paper" / "paper_ledger.db")
    _make_report(tmp_path / "paper")
    out_dir = tmp_path / "receipts" / "health"

    def _locked(_db):
        raise LedgerLocked("database is locked")

    monkeypatch.setattr(health, "read_head_ro", _locked)
    # No systemctl in tests.
    monkeypatch.setattr(health, "service_status", lambda units: {u: "unknown" for u in units})

    rc = health.main([
        "--paper-output-dir", str(tmp_path / "paper"),
        "--db-path", str(db_path),
        "--out-dir", str(out_dir),
    ])
    assert rc == 0
    receipt = _read_json(out_dir / "health_receipt.json")
    assert receipt["overall"] == "DEFERRED"


def test_watchdog_main_deferred_on_lock(tmp_path: Path, monkeypatch) -> None:
    out_dir = tmp_path / "receipts" / "watchdog"

    def _locked(_db):
        raise LedgerLocked("database is locked")

    monkeypatch.setattr(watchdog, "read_head_ro", _locked)

    rc = watchdog.main([
        "--db-path", str(tmp_path / "paper" / "paper_ledger.db"),
        "--out-dir", str(out_dir),
        "--now", "2026-06-15T12:00:00+00:00",
    ])
    assert rc == 0  # DEFERRED exits 0
    receipt = _read_json(out_dir / "watchdog_receipt.json")
    assert receipt["overall"] == "DEFERRED"
    assert receipt["status"] == "DEFERRED"


# --------------------------------------------------------------------------------------------
# End-to-end OK / STALE via the CLI mains (temp paths only)
# --------------------------------------------------------------------------------------------

def test_health_main_ok_end_to_end(tmp_path: Path, monkeypatch) -> None:
    db_path = _make_ledger_fixture(tmp_path / "paper" / "paper_ledger.db")
    _make_report(tmp_path / "paper")
    out_dir = tmp_path / "receipts" / "health"
    monkeypatch.setattr(health, "service_status", lambda units: {u: "unknown" for u in units})

    rc = health.main([
        "--paper-output-dir", str(tmp_path / "paper"),
        "--db-path", str(db_path),
        "--out-dir", str(out_dir),
    ])
    assert rc == 0
    receipt = _read_json(out_dir / "health_receipt.json")
    assert receipt["overall"] in {"OK", "WARN"}
    assert receipt["paper_report"]["batches"] == 5
    assert receipt["paper_report_sha256"] is not None
    assert receipt["ledger_head"]["head_fingerprint"]


def test_watchdog_main_stale_exits_nonzero(tmp_path: Path) -> None:
    # Watermark two cycles behind the latest boundary outside grace -> STALE -> exit 1.
    db_path = _make_ledger_fixture(
        tmp_path / "paper" / "paper_ledger.db", watermark="2026-06-14T16:00:00"
    )
    out_dir = tmp_path / "receipts" / "watchdog"
    rc = watchdog.main([
        "--db-path", str(db_path),
        "--out-dir", str(out_dir),
        "--now", "2026-06-15T12:00:00+00:00",
    ])
    assert rc == 1
    receipt = _read_json(out_dir / "watchdog_receipt.json")
    assert receipt["status"] == "STALE"


def test_watchdog_main_ok_exits_zero(tmp_path: Path) -> None:
    db_path = _make_ledger_fixture(
        tmp_path / "paper" / "paper_ledger.db", watermark="2026-06-15T00:00:00"
    )
    out_dir = tmp_path / "receipts" / "watchdog"
    rc = watchdog.main([
        "--db-path", str(db_path),
        "--out-dir", str(out_dir),
        "--now", "2026-06-15T12:00:00+00:00",
    ])
    assert rc == 0
    receipt = _read_json(out_dir / "watchdog_receipt.json")
    assert receipt["status"] == "OK"
    assert receipt["processing_lag_bars"] == 1


def _read_json(path: Path) -> dict:
    import json

    with open(path, encoding="utf-8") as fh:
        return json.load(fh)
