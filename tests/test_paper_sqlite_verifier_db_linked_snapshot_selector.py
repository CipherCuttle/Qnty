"""Verifier DB-linked funding snapshot selector tests.

All tests use tmp SQLite DBs and tmp sidecars only. They never run a writer,
never touch /srv, and never mutate production/shadow DBs or forward_obs.
"""

from __future__ import annotations

import copy
import json
import sqlite3
from pathlib import Path
from typing import Any

from quantbot.core.determinism import sha256_file
from quantbot.paper.funding_source_snapshot import (
    build_funding_source_snapshot_envelope_v1,
)
from quantbot.paper.funding_status import (
    CAVEATED_ENGINE_SEMANTICS,
    CLEAN_NET_OF_CARRY,
)
from quantbot.paper.sqlite_verify import (
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
    verify_database,
)
from tests.test_paper_sqlite_verifier_clean_net_of_carry_gate import (
    _add_latest_equity_snapshot,
    _clean_report,
    _committed_snapshot,
    _db_with_complete_source,
    _rewrite_sol_csv,
    _set_latest_batch_snapshot_reference,
    _write_snapshot,
)


def _db_ready_for_db_linked_clean(tmp_path: Path) -> Path:
    db_path = _db_with_complete_source(tmp_path)
    _add_latest_equity_snapshot(db_path)
    return db_path


def _attach_snapshot(
    db_path: Path,
    envelope: dict[str, Any],
    *,
    suffix: str | None = None,
    **overrides: Any,
) -> Path:
    snapshot_path = _write_snapshot(db_path, envelope, suffix=suffix)
    _set_latest_batch_snapshot_reference(
        db_path,
        snapshot_path,
        envelope,
        **overrides,
    )
    return snapshot_path


def _latest_snapshot_report(db_path: Path) -> dict[str, Any]:
    result = verify_database(db_path)
    return result.report["funding_source_snapshot"]


def test_null_db_snapshot_references_refuse_clean(tmp_path: Path) -> None:
    db_path = _db_ready_for_db_linked_clean(tmp_path)
    _write_snapshot(db_path, _committed_snapshot(db_path))

    clean = _clean_report(db_path)

    assert clean["decision"] == CAVEATED_ENGINE_SEMANTICS
    assert clean["status"] == FUNDING_CLEAN_CARRY_STATUS_REFUSED_MISSING_SNAPSHOT
    assert "funding_source_snapshot_missing" in clean["reason_codes"]


def test_incomplete_db_snapshot_references_refuse_clean(tmp_path: Path) -> None:
    db_path = _db_ready_for_db_linked_clean(tmp_path)
    envelope = _committed_snapshot(db_path)
    _attach_snapshot(
        db_path,
        envelope,
        funding_source_snapshot_bundle_sha256=None,
        funding_source_snapshot_schema_version=None,
    )

    clean = _clean_report(db_path)

    assert clean["decision"] == CAVEATED_ENGINE_SEMANTICS
    assert clean["status"] == FUNDING_CLEAN_CARRY_STATUS_REFUSED_MISSING_SNAPSHOT
    assert "funding_source_snapshot_missing" in clean["reason_codes"]


def test_missing_referenced_sidecar_refuses_clean(tmp_path: Path) -> None:
    db_path = _db_ready_for_db_linked_clean(tmp_path)
    envelope = _committed_snapshot(db_path)
    snapshot_path = _attach_snapshot(db_path, envelope)
    snapshot_path.unlink()

    clean = _clean_report(db_path)

    assert clean["status"] == FUNDING_CLEAN_CARRY_STATUS_REFUSED_MISSING_SNAPSHOT
    assert "funding_source_snapshot_missing" in clean["reason_codes"]


def test_reference_outside_snapshot_dir_refuses_clean(tmp_path: Path) -> None:
    db_path = _db_ready_for_db_linked_clean(tmp_path)
    envelope = _committed_snapshot(db_path)
    outside = tmp_path / "outside_snapshot.json"
    outside.write_text(json.dumps(envelope), encoding="utf-8")
    _attach_snapshot(
        db_path,
        envelope,
        funding_source_snapshot_path=str(outside),
        funding_source_snapshot_sha256=sha256_file(outside),
    )

    clean = _clean_report(db_path)
    snapshot = _latest_snapshot_report(db_path)

    assert clean["status"] == FUNDING_CLEAN_CARRY_STATUS_REFUSED_MISSING_SNAPSHOT
    assert "funding_source_snapshot_path_outside_snapshot_dir" in (
        snapshot["reason_codes"]
    )


def test_reference_path_traversal_refuses_clean(tmp_path: Path) -> None:
    db_path = _db_ready_for_db_linked_clean(tmp_path)
    envelope = _committed_snapshot(db_path)
    snapshot_path = _attach_snapshot(
        db_path,
        envelope,
        funding_source_snapshot_path="../outside_snapshot.json",
    )

    clean = _clean_report(db_path)
    snapshot = _latest_snapshot_report(db_path)

    assert snapshot_path.exists()
    assert clean["status"] == FUNDING_CLEAN_CARRY_STATUS_REFUSED_MISSING_SNAPSHOT
    assert (
        "funding_source_snapshot_path_outside_snapshot_dir"
        in snapshot["reason_codes"]
    )


def test_db_file_sha_mismatch_refuses_clean(tmp_path: Path) -> None:
    db_path = _db_ready_for_db_linked_clean(tmp_path)
    envelope = _committed_snapshot(db_path)
    _attach_snapshot(db_path, envelope, funding_source_snapshot_sha256="0" * 64)

    clean = _clean_report(db_path)

    assert clean["status"] == FUNDING_CLEAN_CARRY_STATUS_REFUSED_DIGEST_MISMATCH
    assert "funding_source_snapshot_digest_mismatch" in clean["reason_codes"]


def test_envelope_payload_digest_mismatch_refuses_clean(tmp_path: Path) -> None:
    db_path = _db_ready_for_db_linked_clean(tmp_path)
    envelope = _committed_snapshot(db_path)
    envelope["snapshot_sha256"] = "0" * 64
    _attach_snapshot(db_path, envelope)

    clean = _clean_report(db_path)

    assert clean["status"] == FUNDING_CLEAN_CARRY_STATUS_REFUSED_DIGEST_MISMATCH
    assert "funding_source_snapshot_digest_mismatch" in clean["reason_codes"]


def test_bundle_sha_mismatch_refuses_clean(tmp_path: Path) -> None:
    db_path = _db_ready_for_db_linked_clean(tmp_path)
    envelope = _committed_snapshot(db_path)
    _attach_snapshot(
        db_path,
        envelope,
        funding_source_snapshot_bundle_sha256="1" * 64,
    )

    clean = _clean_report(db_path)

    assert clean["status"] == FUNDING_CLEAN_CARRY_STATUS_REFUSED_DIGEST_MISMATCH
    assert "funding_source_file_digest_mismatch" in clean["reason_codes"]


def test_schema_version_mismatch_refuses_clean(tmp_path: Path) -> None:
    db_path = _db_ready_for_db_linked_clean(tmp_path)
    envelope = _committed_snapshot(db_path)
    _attach_snapshot(
        db_path,
        envelope,
        funding_source_snapshot_schema_version="FUNDING_SOURCE_SNAPSHOT_SCHEMA_V2",
    )

    clean = _clean_report(db_path)

    assert clean["status"] == FUNDING_CLEAN_CARRY_STATUS_REFUSED_SCHEMA_UNSUPPORTED
    assert "funding_source_snapshot_schema_unsupported" in clean["reason_codes"]


def test_lane_identity_mismatch_refuses_clean(tmp_path: Path) -> None:
    db_path = _db_ready_for_db_linked_clean(tmp_path)
    envelope = _committed_snapshot(db_path, lane_id="other_lane")
    _attach_snapshot(db_path, envelope)

    clean = _clean_report(db_path)

    assert clean["status"] == FUNDING_CLEAN_CARRY_STATUS_REFUSED_DB_OR_LANE_MISMATCH
    assert "funding_source_snapshot_db_mismatch" in clean["reason_codes"]


def test_batch_identity_mismatch_refuses_clean(tmp_path: Path) -> None:
    db_path = _db_ready_for_db_linked_clean(tmp_path)
    envelope = _committed_snapshot(db_path)
    payload = copy.deepcopy(envelope["snapshot_payload"])
    payload["snapshot_metadata"]["ledger_batch_id"] = "999"
    envelope = build_funding_source_snapshot_envelope_v1(payload)
    _attach_snapshot(db_path, envelope)

    clean = _clean_report(db_path)

    assert clean["status"] == FUNDING_CLEAN_CARRY_STATUS_REFUSED_PENDING_OR_ORPHANED
    assert "funding_source_snapshot_unreferenced_or_orphaned" in clean["reason_codes"]


def test_db_write_state_pending_refuses_clean(tmp_path: Path) -> None:
    db_path = _db_ready_for_db_linked_clean(tmp_path)
    envelope = _committed_snapshot(db_path)
    _attach_snapshot(
        db_path,
        envelope,
        funding_source_snapshot_write_state="pending",
    )

    clean = _clean_report(db_path)

    assert clean["status"] == FUNDING_CLEAN_CARRY_STATUS_REFUSED_PENDING_OR_ORPHANED
    assert "funding_source_snapshot_unreferenced_or_orphaned" in clean["reason_codes"]


def test_sidecar_write_state_pending_refuses_clean(tmp_path: Path) -> None:
    db_path = _db_ready_for_db_linked_clean(tmp_path)
    envelope = _committed_snapshot(db_path, write_state="pending")
    _attach_snapshot(db_path, envelope)

    clean = _clean_report(db_path)

    assert clean["status"] == FUNDING_CLEAN_CARRY_STATUS_REFUSED_PENDING_OR_ORPHANED
    assert "funding_source_snapshot_unreferenced_or_orphaned" in clean["reason_codes"]


def test_exact_committed_db_reference_can_return_clean_in_tmp_synthetic_db(
    tmp_path: Path,
) -> None:
    db_path = _db_ready_for_db_linked_clean(tmp_path)
    envelope = _committed_snapshot(db_path)
    snapshot_path = _attach_snapshot(db_path, envelope)

    result = verify_database(db_path)
    clean = result.report["funding_clean_carry"]
    snapshot = result.report["funding_source_snapshot"]

    assert result.status == STATUS_OK, result.failures
    assert snapshot["selector"] == "ledger_batches"
    assert snapshot["selected_snapshot_path"] == str(snapshot_path)
    assert snapshot["file_sha256"] == sha256_file(snapshot_path)
    assert snapshot["snapshot_sha256"] == envelope["snapshot_sha256"]
    assert clean["status"] == FUNDING_CLEAN_CARRY_STATUS_CLEAN
    assert clean["decision"] == CLEAN_NET_OF_CARRY


def test_unrelated_sidecars_do_not_confuse_exact_db_reference(tmp_path: Path) -> None:
    db_path = _db_ready_for_db_linked_clean(tmp_path)
    envelope = _committed_snapshot(db_path)
    selected_path = _attach_snapshot(db_path, envelope, suffix="selected")
    _write_snapshot(
        db_path,
        _committed_snapshot(db_path, lane_id="other_lane"),
        suffix="unrelated",
    )

    result = verify_database(db_path)
    clean = result.report["funding_clean_carry"]
    snapshot = result.report["funding_source_snapshot"]

    assert result.status == STATUS_OK, result.failures
    assert snapshot["selected_snapshot_path"] == str(selected_path)
    assert snapshot["directory_diagnostic"]["directory_status"] != snapshot["status"]
    assert clean["status"] == FUNDING_CLEAN_CARRY_STATUS_CLEAN
    assert clean["decision"] == CLEAN_NET_OF_CARRY


def test_duplicate_db_references_refuse_clean(tmp_path: Path) -> None:
    db_path = _db_ready_for_db_linked_clean(tmp_path)
    envelope = _committed_snapshot(db_path)
    snapshot_path = _attach_snapshot(db_path, envelope)

    conn = sqlite3.connect(str(db_path))
    try:
        cfg = conn.execute(
            "SELECT paper_engine_version, config_hash FROM paper_config WHERE id = 1"
        ).fetchone()
        conn.execute(
            """
            INSERT INTO ledger_batches (
                created_at, paper_engine_version, config_hash,
                funding_source_snapshot_path,
                funding_source_snapshot_sha256,
                funding_source_snapshot_bundle_sha256,
                funding_source_snapshot_schema_version,
                funding_source_snapshot_write_state,
                funding_source_snapshot_created_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                "2026-06-15T10:00:00Z",
                cfg[0],
                cfg[1],
                str(snapshot_path),
                sha256_file(snapshot_path),
                envelope["snapshot_payload"]["source_bundle_sha256"],
                envelope["snapshot_payload"]["schema_version"],
                "committed",
                envelope["snapshot_payload"]["generated_at_utc"],
            ),
        )
        conn.commit()
    finally:
        conn.close()

    clean = _clean_report(db_path)

    assert clean["status"] == FUNDING_CLEAN_CARRY_STATUS_REFUSED_AMBIGUOUS_MULTIPLE
    assert "funding_source_snapshot_ambiguous_multiple" in clean["reason_codes"]


def test_source_coverage_issue_refuses_clean(tmp_path: Path) -> None:
    db_path = _db_ready_for_db_linked_clean(tmp_path)
    _rewrite_sol_csv(db_path, "missing")
    envelope = _committed_snapshot(db_path)
    _attach_snapshot(db_path, envelope)

    clean = _clean_report(db_path)

    assert clean["status"] == FUNDING_CLEAN_CARRY_STATUS_REFUSED_SOURCE_COVERAGE
    assert "funding_source_missing" in clean["reason_codes"]


def test_funding_resum_mismatch_refuses_clean(tmp_path: Path) -> None:
    db_path = _db_ready_for_db_linked_clean(tmp_path)
    envelope = _committed_snapshot(db_path)
    _attach_snapshot(db_path, envelope)

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
    assert result.report["funding_clean_carry_decision"] == CAVEATED_ENGINE_SEMANTICS


def test_arithmetic_status_ok_remains_separate_from_clean_carry(tmp_path: Path) -> None:
    db_path = _db_ready_for_db_linked_clean(tmp_path)

    result = verify_database(db_path)
    clean = result.report["funding_clean_carry"]

    assert result.status == STATUS_OK, result.failures
    assert clean["arithmetic_status"] == STATUS_OK
    assert clean["decision"] == CAVEATED_ENGINE_SEMANTICS
    assert clean["decision"] != result.status
