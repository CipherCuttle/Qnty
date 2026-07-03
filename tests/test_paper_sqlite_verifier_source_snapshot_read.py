"""SQLite verifier funding source snapshot sidecar read tests.

All tests use tmp SQLite DBs and tmp sidecar directories only. They never run a
writer, never touch /srv, and never mutate production/shadow DBs or forward_obs.
"""

from __future__ import annotations

import copy
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from quantbot.paper.config import build_config, write_config_once
from quantbot.paper.db import initialize_database
from quantbot.paper.funding_source_snapshot import (
    build_funding_source_snapshot_envelope_v1,
    build_funding_source_snapshot_payload_v1,
)
from quantbot.paper.sqlite_verify import (
    FUNDING_SOURCE_SNAPSHOT_STATUS_AMBIGUOUS_MULTIPLE,
    FUNDING_SOURCE_SNAPSHOT_STATUS_DB_OR_LANE_MISMATCH,
    FUNDING_SOURCE_SNAPSHOT_STATUS_DIGEST_MISMATCH,
    FUNDING_SOURCE_SNAPSHOT_STATUS_MISSING,
    FUNDING_SOURCE_SNAPSHOT_STATUS_PAYLOAD_INVALID,
    FUNDING_SOURCE_SNAPSHOT_STATUS_PENDING_OR_ORPHANED,
    FUNDING_SOURCE_SNAPSHOT_STATUS_PRESENT_VALID,
    FUNDING_SOURCE_SNAPSHOT_STATUS_SCHEMA_UNSUPPORTED,
    STATUS_PRE_START,
    verify_database,
)

_WINDOW_START = "2026-06-14T16:00:00Z"
_WINDOW_END = "2026-06-15T00:00:00Z"
_GENERATED_AT = "2026-06-15T00:01:00Z"
_GIT_SHA = "41bbc86246489c393c53c46349b8e8f5d5967522"


def _init_pre_start_db(tmp_path: Path) -> Path:
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
    write_config_once(config, output_dir=db_path.parent)
    initialize_database(db_path, config)
    return db_path


def _ms_at(raw: str, *, offset_ms: int = 0) -> int:
    dt = datetime.fromisoformat(raw.replace("Z", "+00:00"))
    return int(dt.astimezone(timezone.utc).timestamp() * 1000) + offset_ms


def _required_window(symbol: str = "SOLUSDT") -> dict[str, Any]:
    return {
        "symbol": symbol,
        "window_start": _WINDOW_START,
        "window_end": _WINDOW_END,
        "required_by": "paper_engine_funding_interval",
    }


def _source_row(source_path: str, *, symbol: str = "SOLUSDT") -> dict[str, Any]:
    return {
        "symbol": symbol,
        "window_end": _WINDOW_END,
        "fundingTime_ms": _ms_at(_WINDOW_END, offset_ms=5),
        "source_file_path": source_path,
        "row_index": 1,
        "funding_rate": "0.0001",
    }


def _valid_envelope(
    db_path: Path,
    *,
    write_state: str = "pending",
    lane_id: str = "paper_pnl_v1",
    output_dir: str | None = None,
    db_path_reference: str | None = None,
    source_path: str = "data/SOLUSDT_8h_funding.csv",
) -> dict[str, Any]:
    row = _source_row(source_path)
    csv_text = (
        "fundingTime,fundingRate,markPrice\n"
        f"{row['fundingTime_ms']},0.0001,100.0\n"
    )
    committed = write_state == "committed"
    payload = build_funding_source_snapshot_payload_v1(
        source_rows=[row],
        source_file_contents_by_path={source_path: csv_text},
        required_windows=[_required_window()],
        generated_at_utc=_GENERATED_AT,
        lane_id=lane_id,
        output_dir=output_dir or str(db_path.parent),
        writer_or_verifier_command="qnty-paper-sqlite-verify --diagnostic-only",
        qnty_git_commit=_GIT_SHA,
        write_state=write_state,
        db_identity_hash_before="test-db-identity-before",
        pending_batch_id="pending-test-batch",
        ledger_batch_id="ledger-test-batch" if committed else None,
        batch_identity_matches=committed,
        evaluation_identity_matches=True,
        db_path_reference=(
            db_path_reference if db_path_reference is not None else str(db_path)
        ),
        batch_start_watermark=None,
        batch_end_watermark="2026-06-15T00:00:00",
        sanitized_host_user_label="local-test",
    )
    return build_funding_source_snapshot_envelope_v1(payload)


def _snapshot_dir(db_path: Path) -> Path:
    return db_path.parent / "funding_source_snapshots"


def _write_snapshot(
    db_path: Path,
    envelope: dict[str, Any] | str,
    *,
    suffix: str | None = None,
) -> Path:
    snapshot_dir = _snapshot_dir(db_path)
    snapshot_dir.mkdir(parents=True, exist_ok=True)
    if isinstance(envelope, dict):
        payload = envelope.get("snapshot_payload") or {}
        suffix = suffix or str(payload.get("source_bundle_sha256") or "invalid")
        text = json.dumps(envelope, indent=2, sort_keys=True) + "\n"
    else:
        suffix = suffix or "malformed"
        text = envelope
    path = snapshot_dir / f"funding_source_snapshot_v1_{suffix}.json"
    path.write_text(text, encoding="utf-8")
    return path


def _snapshot_report(db_path: Path) -> dict[str, Any]:
    result = verify_database(db_path)
    assert result.status == STATUS_PRE_START, result.failures
    return result.report["funding_source_snapshot"]


def test_no_snapshot_dir_reports_missing(tmp_path: Path) -> None:
    db_path = _init_pre_start_db(tmp_path)

    snapshot = _snapshot_report(db_path)

    assert snapshot["status"] == FUNDING_SOURCE_SNAPSHOT_STATUS_MISSING
    assert snapshot["snapshot_dir_exists"] is False
    assert snapshot["candidate_count"] == 0


def test_empty_snapshot_dir_reports_missing(tmp_path: Path) -> None:
    db_path = _init_pre_start_db(tmp_path)
    _snapshot_dir(db_path).mkdir()

    snapshot = _snapshot_report(db_path)

    assert snapshot["status"] == FUNDING_SOURCE_SNAPSHOT_STATUS_MISSING
    assert snapshot["snapshot_dir_exists"] is True
    assert snapshot["candidate_count"] == 0


def test_one_valid_pending_snapshot_reports_pending_or_orphaned(tmp_path: Path) -> None:
    db_path = _init_pre_start_db(tmp_path)
    _write_snapshot(db_path, _valid_envelope(db_path, write_state="pending"))

    snapshot = _snapshot_report(db_path)

    assert snapshot["status"] == FUNDING_SOURCE_SNAPSHOT_STATUS_PENDING_OR_ORPHANED
    assert snapshot["diagnostic_only"] is True
    assert snapshot["clean_mode_gate"] == "not_implemented"
    assert "CAVEATED_ENGINE_SEMANTICS" in snapshot["caveat"]
    assert "funding_source_snapshot_unreferenced_or_orphaned" in (
        snapshot["future_clean_mode_reason_codes"]
    )


def test_one_valid_committed_snapshot_reports_present_valid(tmp_path: Path) -> None:
    db_path = _init_pre_start_db(tmp_path)
    _write_snapshot(db_path, _valid_envelope(db_path, write_state="committed"))

    snapshot = _snapshot_report(db_path)

    assert snapshot["status"] == FUNDING_SOURCE_SNAPSHOT_STATUS_PRESENT_VALID
    assert snapshot["future_clean_mode_reason_codes"] == []
    assert snapshot["write_state"] == "committed"


def test_digest_mismatch_reports_digest_mismatch(tmp_path: Path) -> None:
    db_path = _init_pre_start_db(tmp_path)
    envelope = _valid_envelope(db_path)
    envelope["snapshot_sha256"] = "0" * 64
    _write_snapshot(db_path, envelope)

    snapshot = _snapshot_report(db_path)

    assert snapshot["status"] == FUNDING_SOURCE_SNAPSHOT_STATUS_DIGEST_MISMATCH
    assert snapshot["candidates"][0]["validation_reason_codes"] == [
        "funding_source_snapshot_digest_mismatch"
    ]


def test_malformed_json_reports_payload_invalid(tmp_path: Path) -> None:
    db_path = _init_pre_start_db(tmp_path)
    _write_snapshot(db_path, "{not json", suffix="malformed")

    snapshot = _snapshot_report(db_path)

    assert snapshot["status"] == FUNDING_SOURCE_SNAPSHOT_STATUS_PAYLOAD_INVALID
    assert snapshot["candidates"][0]["error"].startswith("JSONDecodeError:")


def test_unsupported_schema_reports_schema_unsupported(tmp_path: Path) -> None:
    db_path = _init_pre_start_db(tmp_path)
    envelope = _valid_envelope(db_path)
    payload = copy.deepcopy(envelope["snapshot_payload"])
    payload["schema_version"] = "funding_source_snapshot_v2"
    _write_snapshot(db_path, build_funding_source_snapshot_envelope_v1(payload))

    snapshot = _snapshot_report(db_path)

    assert snapshot["status"] == FUNDING_SOURCE_SNAPSHOT_STATUS_SCHEMA_UNSUPPORTED
    assert snapshot["candidates"][0]["validation_reason_codes"] == [
        "funding_source_snapshot_schema_unsupported"
    ]


def test_db_or_lane_mismatch_reports_db_or_lane_mismatch(tmp_path: Path) -> None:
    db_path = _init_pre_start_db(tmp_path)
    envelope = _valid_envelope(db_path, lane_id="other_lane")
    _write_snapshot(db_path, envelope)

    snapshot = _snapshot_report(db_path)

    assert snapshot["status"] == FUNDING_SOURCE_SNAPSHOT_STATUS_DB_OR_LANE_MISMATCH
    assert snapshot["mismatch_reasons"]


def test_multiple_valid_snapshots_reports_ambiguous_multiple(tmp_path: Path) -> None:
    db_path = _init_pre_start_db(tmp_path)
    _write_snapshot(
        db_path,
        _valid_envelope(db_path, source_path="data/a/SOLUSDT_8h_funding.csv"),
    )
    _write_snapshot(
        db_path,
        _valid_envelope(db_path, source_path="data/b/SOLUSDT_8h_funding.csv"),
    )

    snapshot = _snapshot_report(db_path)

    assert snapshot["status"] == FUNDING_SOURCE_SNAPSHOT_STATUS_AMBIGUOUS_MULTIPLE
    assert snapshot["candidate_count"] == 2
    assert "source_bundle_sha256" not in snapshot
    assert "no durable selector" in snapshot["reason"]


def test_arithmetic_status_remains_unchanged_by_snapshot_diagnostics(
    tmp_path: Path,
) -> None:
    db_path = _init_pre_start_db(tmp_path)
    baseline = verify_database(db_path)
    envelope = _valid_envelope(db_path)
    envelope["snapshot_sha256"] = "f" * 64
    _write_snapshot(db_path, envelope)

    result = verify_database(db_path)

    assert baseline.status == STATUS_PRE_START
    assert result.status == baseline.status
    assert result.report["funding_source_snapshot_status"] == (
        FUNDING_SOURCE_SNAPSHOT_STATUS_DIGEST_MISMATCH
    )


def test_snapshot_report_includes_source_bundle_sha_and_snapshot_sha(
    tmp_path: Path,
) -> None:
    db_path = _init_pre_start_db(tmp_path)
    envelope = _valid_envelope(db_path, write_state="pending")
    path = _write_snapshot(db_path, envelope)

    snapshot = _snapshot_report(db_path)

    assert snapshot["selected_snapshot_path"] == str(path)
    assert snapshot["source_bundle_sha256"] == (
        envelope["snapshot_payload"]["source_bundle_sha256"]
    )
    assert snapshot["snapshot_sha256"] == envelope["snapshot_sha256"]
