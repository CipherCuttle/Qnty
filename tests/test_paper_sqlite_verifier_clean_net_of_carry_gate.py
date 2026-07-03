"""Strict SQLite verifier clean-carry gate tests.

All fixtures are tmp SQLite DBs, tmp CSVs, and tmp snapshot sidecars only. The
tests never touch /srv, never run prod/shadow writers, and never mutate
forward_obs.
"""

from __future__ import annotations

import csv
import copy
import json
import sqlite3
from pathlib import Path
from typing import Any

from quantbot.paper.db import _TRIGGER_SQL
from quantbot.paper.funding_source_snapshot import (
    build_funding_source_snapshot_envelope_v1,
    build_funding_source_snapshot_payload_v1,
)
from quantbot.paper.funding_status import (
    CAVEATED_ENGINE_SEMANTICS,
    CLEAN_NET_OF_CARRY,
)
from quantbot.paper.sqlite_verify import (
    FUNDING_CLEAN_CARRY_REASON_AMBIGUOUS_MULTIPLE,
    FUNDING_CLEAN_CARRY_STATUS_CLEAN,
    FUNDING_CLEAN_CARRY_STATUS_REFUSED_AMBIGUOUS_MULTIPLE,
    FUNDING_CLEAN_CARRY_STATUS_REFUSED_DB_OR_LANE_MISMATCH,
    FUNDING_CLEAN_CARRY_STATUS_REFUSED_DIGEST_MISMATCH,
    FUNDING_CLEAN_CARRY_STATUS_REFUSED_MISSING_SNAPSHOT,
    FUNDING_CLEAN_CARRY_STATUS_REFUSED_PENDING_OR_ORPHANED,
    FUNDING_CLEAN_CARRY_STATUS_REFUSED_RESUM_MISMATCH,
    FUNDING_CLEAN_CARRY_STATUS_REFUSED_SCHEMA_UNSUPPORTED,
    FUNDING_CLEAN_CARRY_STATUS_REFUSED_SOURCE_COVERAGE,
    STATUS_CORRUPT,
    STATUS_OK,
    verify_and_publish,
    verify_database,
)
from tests.test_paper_sqlite_funding_coverage import (
    _build_funding_db,
    _funding_rows_complete,
    _publish_csvs,
    _tmp_csv_complete,
)

_GENERATED_AT = "2026-06-15T09:00:00Z"
_GIT_SHA = "41bbc86246489c393c53c46349b8e8f5d5967522"


def _snapshot_dir(db_path: Path) -> Path:
    return db_path.parent / "funding_source_snapshots"


def _write_snapshot(
    db_path: Path,
    envelope: dict[str, Any],
    *,
    suffix: str | None = None,
) -> Path:
    snapshot_dir = _snapshot_dir(db_path)
    snapshot_dir.mkdir(parents=True, exist_ok=True)
    payload = envelope.get("snapshot_payload") or {}
    suffix = suffix or str(payload.get("source_bundle_sha256") or "invalid")
    path = snapshot_dir / f"funding_source_snapshot_v1_{suffix}.json"
    path.write_text(json.dumps(envelope, indent=2, sort_keys=True) + "\n")
    return path


def _required_windows() -> list[dict[str, Any]]:
    return [
        {
            "symbol": row["symbol"],
            "window_start": row["window_start"],
            "window_end": row["window_end"],
            "required_by": "paper_engine_funding_interval",
        }
        for row in _funding_rows_complete()
    ]


def _read_source_rows(db_path: Path) -> tuple[list[dict[str, Any]], list[Path]]:
    source_rows: list[dict[str, Any]] = []
    source_paths = sorted((db_path.parent / "data").glob("*_8h_funding.csv"))
    for path in source_paths:
        symbol = path.name.removesuffix("_8h_funding.csv")
        with path.open("r", newline="", encoding="utf-8") as fh:
            reader = csv.DictReader(fh)
            for row_index, row in enumerate(reader, start=1):
                source_rows.append(
                    {
                        "symbol": symbol,
                        "fundingTime_ms": int(row["fundingTime"]),
                        "source_file_path": str(path),
                        "row_index": row_index,
                        "funding_rate": str(row["fundingRate"]),
                    }
                )
    return source_rows, source_paths


def _committed_snapshot(
    db_path: Path,
    *,
    write_state: str = "committed",
    lane_id: str = "paper_pnl_v1",
    batch_identity_matches: bool = True,
    evaluation_identity_matches: bool = True,
) -> dict[str, Any]:
    source_rows, source_paths = _read_source_rows(db_path)
    payload = build_funding_source_snapshot_payload_v1(
        source_rows=source_rows,
        source_file_paths=source_paths,
        required_windows=_required_windows(),
        generated_at_utc=_GENERATED_AT,
        lane_id=lane_id,
        output_dir=str(db_path.parent),
        writer_or_verifier_command="local synthetic verifier clean-carry test",
        qnty_git_commit=_GIT_SHA,
        write_state=write_state,
        db_identity_hash_before="local-synthetic-before",
        pending_batch_id="pending-local-synthetic",
        ledger_batch_id="1" if write_state == "committed" else None,
        batch_identity_matches=batch_identity_matches,
        evaluation_identity_matches=evaluation_identity_matches,
        db_path_reference=str(db_path),
        batch_start_watermark=None,
        batch_end_watermark="2026-06-15T08:00:00",
        sanitized_host_user_label="local-test",
    )
    return build_funding_source_snapshot_envelope_v1(payload)


def _db_with_complete_source(tmp_path: Path) -> Path:
    db_path = _build_funding_db(tmp_path, _funding_rows_complete())
    _publish_csvs(db_path, _tmp_csv_complete(tmp_path))
    return db_path


def _add_latest_equity_snapshot(db_path: Path) -> None:
    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    try:
        for (name,) in conn.execute(
            "SELECT name FROM sqlite_master WHERE type='trigger'"
        ).fetchall():
            conn.execute(f"DROP TRIGGER IF EXISTS {name}")

        funding_sum = conn.execute(
            "SELECT COALESCE(SUM(funding_amount), 0.0) FROM funding"
        ).fetchone()[0]
        bar_ts = conn.execute("SELECT MAX(bar_ts) FROM funding").fetchone()[0]
        batch_id = conn.execute(
            "SELECT batch_id FROM ledger_batches ORDER BY batch_id DESC LIMIT 1"
        ).fetchone()[0]
        commit = conn.execute(
            "SELECT bar_commit_id FROM signal_snapshots WHERE bar_ts = ?",
            (bar_ts,),
        ).fetchone()[0]
        prev_seq = conn.execute("SELECT MAX(seq) FROM ledger_events").fetchone()[0]
        initial_equity = conn.execute(
            "SELECT initial_equity_usd FROM paper_config WHERE id = 1"
        ).fetchone()[0]
        equity = initial_equity - funding_sum
        drawdown = (initial_equity - equity) / initial_equity

        cur = conn.execute(
            "INSERT INTO ledger_events (batch_id, event_type, event_key, "
            "recorded_at, bar_ts, symbol, prev_seq) VALUES "
            "(?, 'equity_snapshot', ?, '2026-06-15T09:00:00', ?, NULL, ?)",
            (batch_id, f"eq|{bar_ts}", bar_ts, prev_seq),
        )
        seq = cur.lastrowid
        conn.execute(
            "INSERT INTO equity_snapshots (seq, batch_id, bar_ts, bar_commit_id, "
            "realized_gross_pnl, unrealized_pnl, funding_cum, fees_cum, equity, "
            "drawdown, num_open) VALUES (?, ?, ?, ?, 0.0, 0.0, ?, 0.0, ?, ?, 0)",
            (seq, batch_id, bar_ts, commit, funding_sum, equity, drawdown),
        )
        conn.execute(
            "UPDATE ledger_batches SET event_count = event_count + 1, "
            "committed_bar_count = committed_bar_count + 1, last_event_seq = ?, "
            "new_watermark_bar_ts = ? WHERE batch_id = ?",
            (seq, bar_ts, batch_id),
        )
        conn.execute(
            "UPDATE ledger_state SET watermark_bar_ts = ?, funding_cum = ?, "
            "peak_equity = ?, updated_at = '2026-06-15T09:00:00' WHERE id = 1",
            (bar_ts, funding_sum, initial_equity),
        )
        conn.executescript(_TRIGGER_SQL)
        conn.commit()
    finally:
        conn.close()


def _rewrite_sol_csv(db_path: Path, mutate: str) -> None:
    path = db_path.parent / "data" / "SOLUSDT_8h_funding.csv"
    rows = path.read_text().strip().splitlines()
    header, data = rows[0], rows[1:]
    if mutate == "duplicate":
        data = [data[0], data[0], *data[1:]]
    elif mutate == "outside":
        first = data[0].split(",")
        first[0] = str(int(first[0]) + 1000)
        data = [",".join(first), *data[1:]]
    elif mutate == "missing":
        data = []
    else:
        raise AssertionError(f"unknown mutation {mutate!r}")
    path.write_text("\n".join([header, *data]) + "\n", encoding="utf-8")


def _clean_report(db_path: Path) -> dict[str, Any]:
    result = verify_database(db_path)
    return result.report["funding_clean_carry"]


def test_missing_snapshot_refuses_clean(tmp_path: Path) -> None:
    db_path = _db_with_complete_source(tmp_path)
    result = verify_database(db_path)

    assert result.status == STATUS_OK, result.failures
    assert result.report["funding_source_coverage_verdict"] == CLEAN_NET_OF_CARRY
    assert result.report["funding_coverage_verdict"] == CAVEATED_ENGINE_SEMANTICS
    assert result.report["funding_clean_carry_status"] == (
        FUNDING_CLEAN_CARRY_STATUS_REFUSED_MISSING_SNAPSHOT
    )
    assert "funding_source_snapshot_missing" in (
        result.report["funding_clean_carry_reason_codes"]
    )


def test_pending_snapshot_refuses_clean(tmp_path: Path) -> None:
    db_path = _db_with_complete_source(tmp_path)
    _write_snapshot(db_path, _committed_snapshot(db_path, write_state="pending"))

    report = _clean_report(db_path)

    assert report["decision"] == CAVEATED_ENGINE_SEMANTICS
    assert report["status"] == FUNDING_CLEAN_CARRY_STATUS_REFUSED_PENDING_OR_ORPHANED
    assert "funding_source_snapshot_unreferenced_or_orphaned" in report["reason_codes"]


def test_orphaned_snapshot_refuses_clean(tmp_path: Path) -> None:
    db_path = _db_with_complete_source(tmp_path)
    _write_snapshot(db_path, _committed_snapshot(db_path, write_state="orphaned"))

    report = _clean_report(db_path)

    assert report["status"] == FUNDING_CLEAN_CARRY_STATUS_REFUSED_PENDING_OR_ORPHANED
    assert "funding_source_snapshot_unreferenced_or_orphaned" in report["reason_codes"]


def test_digest_mismatch_refuses_clean(tmp_path: Path) -> None:
    db_path = _db_with_complete_source(tmp_path)
    envelope = _committed_snapshot(db_path)
    envelope["snapshot_sha256"] = "0" * 64
    _write_snapshot(db_path, envelope)

    report = _clean_report(db_path)

    assert report["status"] == FUNDING_CLEAN_CARRY_STATUS_REFUSED_DIGEST_MISMATCH
    assert "funding_source_snapshot_digest_mismatch" in report["reason_codes"]


def test_unsupported_schema_refuses_clean(tmp_path: Path) -> None:
    db_path = _db_with_complete_source(tmp_path)
    envelope = _committed_snapshot(db_path)
    payload = copy.deepcopy(envelope["snapshot_payload"])
    payload["schema_version"] = "FUNDING_SOURCE_SNAPSHOT_SCHEMA_V2"
    _write_snapshot(db_path, build_funding_source_snapshot_envelope_v1(payload))

    report = _clean_report(db_path)

    assert report["status"] == FUNDING_CLEAN_CARRY_STATUS_REFUSED_SCHEMA_UNSUPPORTED
    assert "funding_source_snapshot_schema_unsupported" in report["reason_codes"]


def test_db_lane_mismatch_refuses_clean(tmp_path: Path) -> None:
    db_path = _db_with_complete_source(tmp_path)
    _write_snapshot(db_path, _committed_snapshot(db_path, lane_id="other_lane"))

    report = _clean_report(db_path)

    assert report["status"] == FUNDING_CLEAN_CARRY_STATUS_REFUSED_DB_OR_LANE_MISMATCH
    assert "funding_source_snapshot_db_mismatch" in report["reason_codes"]


def test_multiple_snapshots_refuse_clean(tmp_path: Path) -> None:
    db_path = _db_with_complete_source(tmp_path)
    envelope = _committed_snapshot(db_path)
    _write_snapshot(db_path, envelope, suffix="a")
    _write_snapshot(db_path, envelope, suffix="b")

    report = _clean_report(db_path)

    assert report["status"] == FUNDING_CLEAN_CARRY_STATUS_REFUSED_AMBIGUOUS_MULTIPLE
    assert FUNDING_CLEAN_CARRY_REASON_AMBIGUOUS_MULTIPLE in report["reason_codes"]


def test_duplicate_canonical_endpoint_reason_refuses_clean(tmp_path: Path) -> None:
    db_path = _db_with_complete_source(tmp_path)
    _rewrite_sol_csv(db_path, "duplicate")
    _write_snapshot(db_path, _committed_snapshot(db_path))

    report = _clean_report(db_path)

    assert report["status"] == FUNDING_CLEAN_CARRY_STATUS_REFUSED_SOURCE_COVERAGE
    assert "funding_source_duplicate_ambiguous" in report["reason_codes"]


def test_outside_same_second_reason_refuses_clean(tmp_path: Path) -> None:
    db_path = _db_with_complete_source(tmp_path)
    _rewrite_sol_csv(db_path, "outside")
    _write_snapshot(db_path, _committed_snapshot(db_path))

    report = _clean_report(db_path)

    assert report["status"] == FUNDING_CLEAN_CARRY_STATUS_REFUSED_SOURCE_COVERAGE
    assert "funding_timestamp_outside_tolerance" in report["reason_codes"]


def test_missing_source_row_reason_refuses_clean(tmp_path: Path) -> None:
    db_path = _db_with_complete_source(tmp_path)
    _rewrite_sol_csv(db_path, "missing")
    _write_snapshot(db_path, _committed_snapshot(db_path))

    report = _clean_report(db_path)

    assert report["status"] == FUNDING_CLEAN_CARRY_STATUS_REFUSED_SOURCE_COVERAGE
    assert "funding_source_missing" in report["reason_codes"]


def test_arithmetic_status_remains_separate_from_clean_decision(
    tmp_path: Path,
) -> None:
    db_path = _db_with_complete_source(tmp_path)

    result = verify_database(db_path)

    assert result.status == STATUS_OK, result.failures
    assert result.report["funding_clean_carry_decision"] == CAVEATED_ENGINE_SEMANTICS
    assert result.report["funding_clean_carry_decision"] != result.status


def test_valid_committed_snapshot_and_arithmetic_ok_can_return_clean(
    tmp_path: Path,
) -> None:
    db_path = _db_with_complete_source(tmp_path)
    _add_latest_equity_snapshot(db_path)
    _write_snapshot(db_path, _committed_snapshot(db_path))

    result = verify_database(db_path)

    assert result.status == STATUS_OK, result.failures
    assert result.report["funding_clean_carry_status"] == (
        FUNDING_CLEAN_CARRY_STATUS_CLEAN
    )
    assert result.report["funding_clean_carry_decision"] == CLEAN_NET_OF_CARRY
    assert result.report["funding_coverage_verdict"] == CLEAN_NET_OF_CARRY
    assert result.report["funding_clean_carry_reason_codes"] == []


def test_funding_resum_mismatch_refuses_clean(tmp_path: Path) -> None:
    db_path = _db_with_complete_source(tmp_path)
    _add_latest_equity_snapshot(db_path)
    _write_snapshot(db_path, _committed_snapshot(db_path))
    conn = sqlite3.connect(str(db_path))
    try:
        conn.execute(
            "UPDATE ledger_state SET funding_cum = funding_cum + 1.0 WHERE id = 1"
        )
        conn.commit()
    finally:
        conn.close()

    result = verify_database(db_path)

    assert result.status == STATUS_CORRUPT
    assert result.report["funding_clean_carry_status"] == (
        FUNDING_CLEAN_CARRY_STATUS_REFUSED_RESUM_MISMATCH
    )
    assert "funding_resum_mismatch" in (
        result.report["funding_clean_carry_reason_codes"]
    )
    assert result.report["funding_clean_carry_decision"] == CAVEATED_ENGINE_SEMANTICS


def test_report_includes_reason_codes_and_snapshot_hashes(tmp_path: Path) -> None:
    db_path = _db_with_complete_source(tmp_path)
    envelope = _committed_snapshot(db_path, write_state="pending")
    _write_snapshot(db_path, envelope)

    verify_and_publish(db_path)
    report = json.loads((db_path.parent / "paper_verify_report.json").read_text())

    clean = report["funding_clean_carry"]
    assert clean["reason_codes"]
    assert clean["snapshot_sha256"] == envelope["snapshot_sha256"]
    assert clean["source_bundle_sha256"] == (
        envelope["snapshot_payload"]["source_bundle_sha256"]
    )
    assert report["funding_clean_carry_reason_codes"] == clean["reason_codes"]
