"""SQLite writer funding snapshot DB reference transaction tests.

All tests use tmp SQLite DBs, tmp forward observations, and tmp CSVs only. They
never touch /srv, production DBs, shadow DBs, or forward_obs.
"""

from __future__ import annotations

import json
import sqlite3
from pathlib import Path
from typing import Any

import pytest

from quantbot.core.determinism import sha256_file
from quantbot.paper.db import connect_readonly
from quantbot.paper.sqlite_writer import (
    STATUS_CORRUPT_LEDGER,
    STATUS_OK,
    run_sqlite_accounting,
)
from tests.test_paper_sqlite_writer_source_snapshot_emission import (
    NOW,
    _assert_no_durable_mutation,
    _funding_times_with_endpoint_offset,
    _run_writer,
    _snapshot_files,
)


@pytest.fixture(autouse=True)
def _freeze_writer_now(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("quantbot.paper.sqlite_writer._now", lambda: NOW)


def _latest_batch_snapshot_reference(db_path: Path) -> dict[str, Any]:
    conn = connect_readonly(db_path)
    try:
        row = conn.execute(
            """
            SELECT
                funding_source_snapshot_path,
                funding_source_snapshot_sha256,
                funding_source_snapshot_bundle_sha256,
                funding_source_snapshot_schema_version,
                funding_source_snapshot_write_state,
                funding_source_snapshot_created_at
            FROM ledger_batches
            ORDER BY batch_id DESC
            LIMIT 1
            """
        ).fetchone()
    finally:
        conn.close()
    assert row is not None
    return dict(row)


def _load_single_snapshot(db_path: Path) -> tuple[Path, dict[str, Any]]:
    files = _snapshot_files(db_path)
    assert len(files) == 1, f"expected exactly one snapshot, got {files}"
    path = files[0]
    return path, json.loads(path.read_text(encoding="utf-8"))


def _ledger_batch_count(db_path: Path) -> int:
    conn = connect_readonly(db_path)
    try:
        return int(conn.execute("SELECT COUNT(*) FROM ledger_batches").fetchone()[0])
    finally:
        conn.close()


def test_writer_stores_all_committed_snapshot_reference_fields(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    status, msg, db_path = _run_writer(
        tmp_path,
        monkeypatch,
        funding_times_ms=_funding_times_with_endpoint_offset(),
    )

    assert status == STATUS_OK, msg
    snapshot_path, envelope = _load_single_snapshot(db_path)
    payload = envelope["snapshot_payload"]
    reference = _latest_batch_snapshot_reference(db_path)

    assert reference == {
        "funding_source_snapshot_path": str(snapshot_path),
        "funding_source_snapshot_sha256": sha256_file(snapshot_path),
        "funding_source_snapshot_bundle_sha256": payload["source_bundle_sha256"],
        "funding_source_snapshot_schema_version": payload["schema_version"],
        "funding_source_snapshot_write_state": "committed",
        "funding_source_snapshot_created_at": payload["generated_at_utc"],
    }
    assert payload["write_state"] == "committed"
    assert payload["snapshot_metadata"]["write_state"] == "committed"
    assert payload["snapshot_metadata"]["ledger_batch_id"] == "1"
    assert payload["snapshot_metadata"]["batch_identity_matches"] is True
    assert envelope["snapshot_sha256"]
    assert envelope["snapshot_sha256"] != reference["funding_source_snapshot_sha256"]


def test_explicit_db_path_stores_reference_under_db_parent(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    explicit_db_path = tmp_path / "manual-db-root" / "manual_paper_ledger.db"
    env_output_dir = tmp_path / "env-output-dir"

    status, msg, db_path = _run_writer(
        tmp_path,
        monkeypatch,
        funding_times_ms=_funding_times_with_endpoint_offset(),
        db_path=explicit_db_path,
        config_dir=env_output_dir,
    )

    assert status == STATUS_OK, msg
    reference = _latest_batch_snapshot_reference(db_path)
    snapshot_path = Path(reference["funding_source_snapshot_path"])
    assert snapshot_path.parent == explicit_db_path.parent / "funding_source_snapshots"
    assert reference["funding_source_snapshot_sha256"] == sha256_file(snapshot_path)
    assert not (env_output_dir / "funding_source_snapshots").exists()


def test_forced_db_transaction_failure_rolls_back_rows_but_may_leave_pending_sidecar(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def _forced_failure(*args: Any, **kwargs: Any) -> list[str]:
        return ["forced tx failure"]

    monkeypatch.setattr(
        "quantbot.paper.sqlite_writer._reconcile_batch_inside_tx",
        _forced_failure,
    )

    status, msg, db_path = _run_writer(
        tmp_path,
        monkeypatch,
        funding_times_ms=_funding_times_with_endpoint_offset(),
    )

    assert status == STATUS_CORRUPT_LEDGER, msg
    assert "forced tx failure" in msg
    _assert_no_durable_mutation(db_path)
    snapshot_path, envelope = _load_single_snapshot(db_path)
    assert snapshot_path.exists()
    assert envelope["snapshot_payload"]["write_state"] == "pending"


def test_committed_sidecar_rewrite_failure_leaves_db_reference_pending_and_caveated(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import quantbot.paper.sqlite_writer as sqlite_writer

    original_write = sqlite_writer._write_json_atomic

    def _fail_committed_rewrite(path: Path, value: dict[str, Any]) -> None:
        payload = value.get("snapshot_payload") or {}
        if payload.get("write_state") == "committed":
            raise OSError("forced committed rewrite failure")
        original_write(path, value)

    monkeypatch.setattr(
        "quantbot.paper.sqlite_writer._write_json_atomic",
        _fail_committed_rewrite,
    )

    status, msg, db_path = _run_writer(
        tmp_path,
        monkeypatch,
        funding_times_ms=_funding_times_with_endpoint_offset(),
    )

    assert status == STATUS_OK, msg
    assert "FUNDING_SOURCE_SNAPSHOT_COMMIT_MARKER_FAILED" in msg
    assert "CAVEATED_ENGINE_SEMANTICS" in msg
    snapshot_path, envelope = _load_single_snapshot(db_path)
    reference = _latest_batch_snapshot_reference(db_path)
    assert envelope["snapshot_payload"]["write_state"] == "pending"
    assert reference["funding_source_snapshot_write_state"] == "pending"
    assert reference["funding_source_snapshot_sha256"] == sha256_file(snapshot_path)


def test_committed_db_reference_update_failure_leaves_hash_state_mismatch_caveated(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def _raise_db_update(*args: Any, **kwargs: Any) -> None:
        raise sqlite3.OperationalError("forced db reference update failure")

    monkeypatch.setattr(
        "quantbot.paper.sqlite_writer._mark_funding_source_snapshot_db_reference_committed",
        _raise_db_update,
    )

    status, msg, db_path = _run_writer(
        tmp_path,
        monkeypatch,
        funding_times_ms=_funding_times_with_endpoint_offset(),
    )

    assert status == STATUS_OK, msg
    assert "FUNDING_SOURCE_SNAPSHOT_DB_REFERENCE_COMMIT_MARK_FAILED" in msg
    assert "CAVEATED_ENGINE_SEMANTICS" in msg
    snapshot_path, envelope = _load_single_snapshot(db_path)
    reference = _latest_batch_snapshot_reference(db_path)
    assert envelope["snapshot_payload"]["write_state"] == "committed"
    assert reference["funding_source_snapshot_write_state"] == "pending"
    assert reference["funding_source_snapshot_sha256"] != sha256_file(snapshot_path)


def test_pending_snapshot_builder_failure_still_aborts_before_db_mutation(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def _raise(*args: Any, **kwargs: Any) -> dict[str, Any]:
        raise RuntimeError("forced builder failure")

    monkeypatch.setattr(
        "quantbot.paper.sqlite_writer.build_funding_source_snapshot_payload_v1",
        _raise,
    )

    status, _msg, db_path = _run_writer(
        tmp_path,
        monkeypatch,
        funding_times_ms=_funding_times_with_endpoint_offset(),
    )

    assert status != STATUS_OK
    assert _ledger_batch_count(db_path) == 0
    _assert_no_durable_mutation(db_path)
    assert _snapshot_files(db_path) == []


def test_old_rows_with_null_snapshot_fields_remain_valid(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    status, msg, db_path = _run_writer(
        tmp_path,
        monkeypatch,
        funding_times_ms=_funding_times_with_endpoint_offset(),
    )
    assert status == STATUS_OK, msg

    conn = sqlite3.connect(str(db_path))
    try:
        conn.execute(
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
        conn.commit()
    finally:
        conn.close()

    conn_ro = connect_readonly(db_path)
    try:
        row = conn_ro.execute(
            """
            SELECT
                funding_source_snapshot_path,
                funding_source_snapshot_sha256,
                funding_source_snapshot_bundle_sha256,
                funding_source_snapshot_schema_version,
                funding_source_snapshot_write_state,
                funding_source_snapshot_created_at
            FROM ledger_batches
            ORDER BY batch_id DESC
            LIMIT 1
            """
        ).fetchone()
    finally:
        conn_ro.close()

    assert row is not None
    assert all(value is None for value in row)
