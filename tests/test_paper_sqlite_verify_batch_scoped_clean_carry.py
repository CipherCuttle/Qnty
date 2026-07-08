"""Test-only contract for future batch-scoped clean-carry verification.

These tests specify additive future semantics only. They use tmp SQLite DBs,
tmp CSVs, and tmp funding-source sidecars; they do not run prod/shadow writers,
do not touch /srv, and do not mutate forward_obs.

The existing full-ledger clean-carry fields remain full-ledger scoped:

  - funding_clean_carry_decision
  - funding_clean_carry_status
  - funding_clean_carry_reason_codes
  - funding_clean_carry

The future batch-scoped gate must expose separate fields:

  - funding_clean_carry_batch_decision
  - funding_clean_carry_batch_status
  - funding_clean_carry_batch_reason_codes
  - funding_clean_carry_batch

Batch-scoped CLEAN_NET_OF_CARRY may apply only to the latest DB-linked ledger
batch and must not relabel the full historical ledger or prod/current ledgers
as CLEAN_NET_OF_CARRY.
"""

from __future__ import annotations

import sqlite3
from pathlib import Path
from typing import Any

import pytest

from quantbot.paper.funding_source_snapshot import (
    build_funding_source_snapshot_envelope_v1,
    build_funding_source_snapshot_payload_v1,
)
from quantbot.paper.funding_status import (
    CAVEATED_ENGINE_SEMANTICS,
    CLEAN_NET_OF_CARRY,
)
from quantbot.paper.funding_source_bundle import (
    BUNDLE_REASON_CORRUPT,
    BUNDLE_REASON_HASH_MISMATCH,
    BUNDLE_REASON_MISSING,
)
from quantbot.paper.sqlite_verify import (
    FUNDING_CLEAN_CARRY_STATUS_CLEAN,
    FUNDING_CLEAN_CARRY_STATUS_REFUSED_BUNDLE,
    FUNDING_CLEAN_CARRY_STATUS_REFUSED_DB_OR_LANE_MISMATCH,
    FUNDING_CLEAN_CARRY_STATUS_REFUSED_DIGEST_MISMATCH,
    FUNDING_CLEAN_CARRY_STATUS_REFUSED_MISSING_SNAPSHOT,
    FUNDING_CLEAN_CARRY_STATUS_REFUSED_PENDING_OR_ORPHANED,
    FUNDING_CLEAN_CARRY_STATUS_REFUSED_SCHEMA_UNSUPPORTED,
    FUNDING_CLEAN_CARRY_STATUS_REFUSED_SOURCE_COVERAGE,
    SOURCE_MODE_BUNDLE,
    SOURCE_MODE_LIVE_CURRENT,
    STATUS_OK,
    verify_database,
    verify_database_readonly_cli,
)
from tests.test_funding_source_immutable_bundle_semantics import (
    _build_planned_bundle,
    _drift_live_sol_funding_rate,
)
from tests.test_paper_sqlite_funding_coverage import _funding_rows_complete
from tests.test_paper_sqlite_verifier_clean_net_of_carry_gate import (
    _GENERATED_AT,
    _GIT_SHA,
    _add_latest_equity_snapshot,
    _db_with_complete_source,
    _read_source_rows,
    _rewrite_sol_csv,
    _set_latest_batch_snapshot_reference,
    _write_snapshot,
)


_BATCH_START = "2026-06-15T00:00:00"
_BATCH_END = "2026-06-15T08:00:00"
_BATCH_WINDOW = {
    "start": "2026-06-15T00:00:00Z",
    "end": "2026-06-15T08:00:00Z",
}
_FULL_LEDGER_WINDOW = {
    "start": "2026-06-14T00:00:00Z",
    "end": "2026-06-15T08:00:00Z",
}
_BATCH_FIELDS = {
    "funding_clean_carry_batch_decision",
    "funding_clean_carry_batch_status",
    "funding_clean_carry_batch_reason_codes",
    "funding_clean_carry_batch",
}


def _latest_batch_id(db_path: Path) -> int:
    conn = sqlite3.connect(str(db_path))
    try:
        row = conn.execute(
            "SELECT batch_id FROM ledger_batches ORDER BY batch_id DESC LIMIT 1"
        ).fetchone()
        assert row is not None
        return int(row[0])
    finally:
        conn.close()


def _set_latest_batch_watermarks(
    db_path: Path,
    *,
    prior: str | None = _BATCH_START,
    new: str | None = _BATCH_END,
) -> None:
    conn = sqlite3.connect(str(db_path))
    try:
        conn.execute(
            """
            UPDATE ledger_batches
            SET prior_watermark_bar_ts = ?,
                new_watermark_bar_ts = ?
            WHERE batch_id = (
                SELECT batch_id FROM ledger_batches ORDER BY batch_id DESC LIMIT 1
            )
            """,
            (prior, new),
        )
        conn.commit()
    finally:
        conn.close()


def _batch_required_windows(
    *,
    start: str = _BATCH_START,
    end: str = _BATCH_END,
) -> list[dict[str, Any]]:
    return [
        {
            "symbol": row["symbol"],
            "window_start": row["window_start"],
            "window_end": row["window_end"],
            "required_by": "paper_engine_funding_interval",
        }
        for row in _funding_rows_complete()
        if row["window_start"] >= start and row["window_end"] <= end
    ]


def _db_with_latest_batch_window(tmp_path: Path) -> Path:
    db_path = _db_with_complete_source(tmp_path)
    _add_latest_equity_snapshot(db_path)
    _set_latest_batch_watermarks(db_path)
    return db_path


def _batch_scoped_snapshot(
    db_path: Path,
    *,
    write_state: str = "committed",
    batch_start_watermark: str | None = _BATCH_START,
    batch_end_watermark: str | None = _BATCH_END,
    evaluation_window: dict[str, str] | None = None,
    schema_version: str | None = None,
    batch_identity_matches: bool = True,
    evaluation_identity_matches: bool = True,
) -> dict[str, Any]:
    source_rows, source_paths = _read_source_rows(db_path)
    payload = build_funding_source_snapshot_payload_v1(
        source_rows=source_rows,
        source_file_paths=source_paths,
        required_windows=_batch_required_windows(),
        generated_at_utc=_GENERATED_AT,
        lane_id="paper_pnl_v1",
        output_dir=str(db_path.parent),
        writer_or_verifier_command=(
            "local synthetic batch-scoped clean-carry verifier test"
        ),
        qnty_git_commit=_GIT_SHA,
        write_state=write_state,
        db_identity_hash_before="local-synthetic-before",
        pending_batch_id="pending-local-synthetic",
        ledger_batch_id=(
            str(_latest_batch_id(db_path)) if write_state == "committed" else None
        ),
        batch_identity_matches=batch_identity_matches,
        evaluation_identity_matches=evaluation_identity_matches,
        evaluation_window=evaluation_window,
        db_path_reference=str(db_path),
        batch_start_watermark=batch_start_watermark,
        batch_end_watermark=batch_end_watermark,
        sanitized_host_user_label="local-test",
    )
    if schema_version is not None:
        payload["schema_version"] = schema_version
    return build_funding_source_snapshot_envelope_v1(payload)


def _attach_latest_batch_snapshot(
    db_path: Path,
    envelope: dict[str, Any],
    *,
    suffix: str = "batch",
    **reference_overrides: Any,
) -> Path:
    snapshot_path = _write_snapshot(db_path, envelope, suffix=suffix)
    _set_latest_batch_snapshot_reference(
        db_path,
        snapshot_path,
        envelope,
        **reference_overrides,
    )
    return snapshot_path


def _verify_with_explicit_data_dir(db_path: Path) -> dict[str, Any]:
    result = verify_database_readonly_cli(
        db_path,
        data_dir=(db_path.parent / "data").resolve(),
    )
    assert result.status == STATUS_OK, result.failures
    assert result.report["source_path_resolution_mode"] == "explicit_data_dir"
    return result.report


def _assert_batch_fields_present(report: dict[str, Any]) -> None:
    missing = _BATCH_FIELDS - set(report)
    assert missing == set()


def _assert_full_ledger_stays_caveated(report: dict[str, Any]) -> None:
    assert report["funding_clean_carry_decision"] == CAVEATED_ENGINE_SEMANTICS
    assert report["funding_clean_carry_decision"] != CLEAN_NET_OF_CARRY
    assert report["funding_clean_carry"]["decision"] == CAVEATED_ENGINE_SEMANTICS
    assert report["funding_clean_carry"]["decision"] != CLEAN_NET_OF_CARRY


def test_latest_batch_can_be_clean_net_of_carry_batch_while_full_ledger_remains_caveated(
    tmp_path: Path,
) -> None:
    db_path = _db_with_latest_batch_window(tmp_path)
    envelope = _batch_scoped_snapshot(db_path)
    _attach_latest_batch_snapshot(db_path, envelope)

    report = _verify_with_explicit_data_dir(db_path)

    _assert_batch_fields_present(report)
    _assert_full_ledger_stays_caveated(report)
    assert report["funding_clean_carry_batch_decision"] == CLEAN_NET_OF_CARRY
    assert report["funding_clean_carry_batch_status"] == (
        FUNDING_CLEAN_CARRY_STATUS_CLEAN
    )
    assert report["funding_clean_carry_batch_reason_codes"] == []
    batch = report["funding_clean_carry_batch"]
    assert batch["decision"] == CLEAN_NET_OF_CARRY
    assert batch["target_batch_id"] == _latest_batch_id(db_path)
    assert batch["evaluation_window"] == _BATCH_WINDOW
    assert batch["full_ledger_evaluation_window"] == _FULL_LEDGER_WINDOW


def test_batch_scope_compares_snapshot_window_to_latest_batch_watermarks_not_full_funding_span(
    tmp_path: Path,
) -> None:
    db_path = _db_with_latest_batch_window(tmp_path)
    envelope = _batch_scoped_snapshot(db_path)
    _attach_latest_batch_snapshot(db_path, envelope)

    report = _verify_with_explicit_data_dir(db_path)

    _assert_batch_fields_present(report)
    assert "funding_source_snapshot_window_mismatch" in (
        report["funding_clean_carry_reason_codes"]
    )
    assert "funding_source_snapshot_window_mismatch" not in (
        report["funding_clean_carry_batch_reason_codes"]
    )
    assert report["funding_clean_carry_batch_decision"] == CLEAN_NET_OF_CARRY
    assert report["funding_clean_carry_batch"]["evaluation_window"] == _BATCH_WINDOW
    _assert_full_ledger_stays_caveated(report)


def test_batch_scope_refuses_window_mismatch(tmp_path: Path) -> None:
    """Snapshot window that does NOT cover the batch window is refused.

    Under covering-superset semantics, the snapshot evaluation window must
    start <= batch start AND end >= batch end. Here the snapshot window
    starts AFTER the batch start AND ends BEFORE the batch end, so it is
    a strict subset — not a covering superset — and must be refused.
    """
    db_path = _db_with_latest_batch_window(tmp_path)
    envelope = _batch_scoped_snapshot(
        db_path,
        batch_start_watermark="2026-06-15T01:00:00",
        evaluation_window={
            "start": "2026-06-15T01:00:00",
            "end": "2026-06-15T07:00:00",
        },
    )
    _attach_latest_batch_snapshot(db_path, envelope)

    report = _verify_with_explicit_data_dir(db_path)

    _assert_batch_fields_present(report)
    assert report["funding_clean_carry_batch_decision"] == CAVEATED_ENGINE_SEMANTICS
    assert report["funding_clean_carry_batch_status"] == (
        FUNDING_CLEAN_CARRY_STATUS_REFUSED_DB_OR_LANE_MISMATCH
    )
    assert "funding_source_batch_window_mismatch" in (
        report["funding_clean_carry_batch_reason_codes"]
    )
    _assert_full_ledger_stays_caveated(report)


def test_batch_scope_refuses_missing_latest_batch_snapshot_reference(
    tmp_path: Path,
) -> None:
    db_path = _db_with_latest_batch_window(tmp_path)

    report = _verify_with_explicit_data_dir(db_path)

    _assert_batch_fields_present(report)
    assert report["funding_clean_carry_batch_decision"] == CAVEATED_ENGINE_SEMANTICS
    assert report["funding_clean_carry_batch_status"] == (
        FUNDING_CLEAN_CARRY_STATUS_REFUSED_MISSING_SNAPSHOT
    )
    assert "funding_source_snapshot_missing" in (
        report["funding_clean_carry_batch_reason_codes"]
    )
    _assert_full_ledger_stays_caveated(report)


@pytest.mark.parametrize(
    ("case", "expected_status", "expected_reason"),
    [
        (
            "pending",
            FUNDING_CLEAN_CARRY_STATUS_REFUSED_PENDING_OR_ORPHANED,
            "funding_source_snapshot_unreferenced_or_orphaned",
        ),
        (
            "orphaned",
            FUNDING_CLEAN_CARRY_STATUS_REFUSED_PENDING_OR_ORPHANED,
            "funding_source_snapshot_unreferenced_or_orphaned",
        ),
        (
            "digest_mismatch",
            FUNDING_CLEAN_CARRY_STATUS_REFUSED_DIGEST_MISMATCH,
            "funding_source_snapshot_digest_mismatch",
        ),
        (
            "schema_unsupported",
            FUNDING_CLEAN_CARRY_STATUS_REFUSED_SCHEMA_UNSUPPORTED,
            "funding_source_snapshot_schema_unsupported",
        ),
        (
            "source_incomplete",
            FUNDING_CLEAN_CARRY_STATUS_REFUSED_SOURCE_COVERAGE,
            "funding_source_missing",
        ),
    ],
)
def test_batch_scope_refuses_pending_orphaned_digest_mismatched_schema_unsupported_source_incomplete_snapshots(
    tmp_path: Path,
    case: str,
    expected_status: str,
    expected_reason: str,
) -> None:
    db_path = _db_with_latest_batch_window(tmp_path)
    overrides: dict[str, Any] = {}
    write_state = "committed"
    schema_version: str | None = None

    if case in {"pending", "orphaned"}:
        write_state = case
    elif case == "digest_mismatch":
        overrides["funding_source_snapshot_sha256"] = "0" * 64
    elif case == "schema_unsupported":
        schema_version = "FUNDING_SOURCE_SNAPSHOT_SCHEMA_V2"
    elif case == "source_incomplete":
        _rewrite_sol_csv(db_path, "missing")

    envelope = _batch_scoped_snapshot(
        db_path,
        write_state=write_state,
        schema_version=schema_version,
    )
    _attach_latest_batch_snapshot(
        db_path,
        envelope,
        suffix=case,
        **overrides,
    )

    report = _verify_with_explicit_data_dir(db_path)

    _assert_batch_fields_present(report)
    assert report["funding_clean_carry_batch_decision"] == CAVEATED_ENGINE_SEMANTICS
    assert report["funding_clean_carry_batch_status"] == expected_status
    assert expected_reason in report["funding_clean_carry_batch_reason_codes"]
    assert report["funding_clean_carry_batch"]["target_batch_id"] == _latest_batch_id(
        db_path
    )


def test_batch_scope_preserves_existing_full_ledger_clean_carry_fields(
    tmp_path: Path,
) -> None:
    db_path = _db_with_latest_batch_window(tmp_path)
    envelope = _batch_scoped_snapshot(db_path)
    _attach_latest_batch_snapshot(db_path, envelope)

    report = _verify_with_explicit_data_dir(db_path)

    for key in (
        "funding_clean_carry_decision",
        "funding_clean_carry_status",
        "funding_clean_carry_reason_codes",
        "funding_clean_carry",
    ):
        assert key in report
    _assert_batch_fields_present(report)
    assert report["funding_clean_carry"] is not report["funding_clean_carry_batch"]
    assert report["funding_clean_carry_decision"] == CAVEATED_ENGINE_SEMANTICS
    assert report["funding_clean_carry_batch_decision"] == CLEAN_NET_OF_CARRY
    assert "funding_source_snapshot_window_mismatch" in (
        report["funding_clean_carry_reason_codes"]
    )
    assert report["funding_clean_carry_batch_reason_codes"] == []


# ---------------------------------------------------------------------------
# source_mode="bundle" semantics for the batch-scoped stamp.
#
# The batch stamp must honor ``source_mode`` the same way the full-ledger gate
# already does: in bundle mode it resolves funding-source digest expectations
# from the pinned immutable bundle instead of the mutable live ``data/*.csv``,
# so bundle-mode reports are internally consistent and the additive batch stamp
# never reads drifted live CSVs. ``live-current`` (default) is unchanged.
#
# These setups build a batch-scoped snapshot + DB reference AND a bundle frozen
# from that same batch envelope, then drive the verifier via ``verify_database``
# (which threads ``source_mode`` end-to-end). All fixtures are tmp DBs / CSVs /
# sidecars / bundles; nothing touches /srv, prod, or real services.
# ---------------------------------------------------------------------------


def _batch_snapshot_setup(tmp_path: Path) -> tuple[Path, dict[str, Any]]:
    db_path = _db_with_latest_batch_window(tmp_path)
    envelope = _batch_scoped_snapshot(db_path)
    _attach_latest_batch_snapshot(db_path, envelope)
    return db_path, envelope


def _batch_stamp(db_path: Path, source_mode: str) -> dict[str, Any]:
    result = verify_database(db_path, source_mode=source_mode)
    assert result.status == STATUS_OK, result.failures
    return result.report["funding_clean_carry_batch"]


def test_batch_stamp_live_current_still_detects_live_csv_drift(
    tmp_path: Path,
) -> None:
    """(1) live-current batch stamp must still flip on live CSV drift."""
    db_path, _envelope = _batch_snapshot_setup(tmp_path)

    _drift_live_sol_funding_rate(db_path)

    batch = _batch_stamp(db_path, SOURCE_MODE_LIVE_CURRENT)
    assert batch["source_resolution_mode"] == SOURCE_MODE_LIVE_CURRENT
    assert batch["decision"] == CAVEATED_ENGINE_SEMANTICS
    assert batch["status"] == FUNDING_CLEAN_CARRY_STATUS_REFUSED_DIGEST_MISMATCH
    assert "funding_source_file_digest_mismatch" in batch["reason_codes"]


def test_batch_stamp_bundle_mode_survives_live_csv_drift(tmp_path: Path) -> None:
    """(2) bundle-mode batch stamp survives live CSV drift with a valid bundle."""
    db_path, envelope = _batch_snapshot_setup(tmp_path)
    _build_planned_bundle(db_path, envelope)

    # Live CSVs drift after the bundle is frozen (scheduled-refresh analogue).
    _drift_live_sol_funding_rate(db_path)

    batch = _batch_stamp(db_path, SOURCE_MODE_BUNDLE)
    assert batch["source_resolution_mode"] == SOURCE_MODE_BUNDLE
    assert batch["decision"] == CLEAN_NET_OF_CARRY
    assert batch["status"] == FUNDING_CLEAN_CARRY_STATUS_CLEAN
    assert "funding_source_file_digest_mismatch" not in batch["reason_codes"]
    # Bundle identity is recorded on the batch stamp, not live CSV digests.
    assert batch["source_bundle_sha256"]
    assert "live_source_digests" not in batch


def test_batch_stamp_bundle_mode_refuses_missing_bundle(tmp_path: Path) -> None:
    """(3a) bundle mode refuses when no bundle exists for the snapshot."""
    db_path, _envelope = _batch_snapshot_setup(tmp_path)
    # No bundle captured; live CSVs still match the snapshot digests.

    batch = _batch_stamp(db_path, SOURCE_MODE_BUNDLE)
    assert batch["source_resolution_mode"] == SOURCE_MODE_BUNDLE
    assert batch["decision"] == CAVEATED_ENGINE_SEMANTICS
    assert batch["status"] == FUNDING_CLEAN_CARRY_STATUS_REFUSED_BUNDLE
    assert BUNDLE_REASON_MISSING in batch["reason_codes"]


def test_batch_stamp_bundle_mode_refuses_corrupt_bundle(tmp_path: Path) -> None:
    """(3b) bundle mode refuses when the bundle file is corrupt."""
    db_path, envelope = _batch_snapshot_setup(tmp_path)
    bundle_path = _build_planned_bundle(db_path, envelope)
    bundle_path.write_text("{ not valid bundle json", encoding="utf-8")

    batch = _batch_stamp(db_path, SOURCE_MODE_BUNDLE)
    assert batch["decision"] == CAVEATED_ENGINE_SEMANTICS
    assert batch["status"] == FUNDING_CLEAN_CARRY_STATUS_REFUSED_BUNDLE
    assert BUNDLE_REASON_CORRUPT in batch["reason_codes"]


def test_batch_stamp_bundle_mode_refuses_hash_mismatch(tmp_path: Path) -> None:
    """(3c) bundle mode refuses when the bundle bytes no longer recompute."""
    db_path, envelope = _batch_snapshot_setup(tmp_path)
    bundle_path = _build_planned_bundle(db_path, envelope)
    text = bundle_path.read_text(encoding="utf-8")
    bundle_path.write_text(text.replace("0.0001", "0.0009", 1), encoding="utf-8")

    batch = _batch_stamp(db_path, SOURCE_MODE_BUNDLE)
    assert batch["decision"] == CAVEATED_ENGINE_SEMANTICS
    assert batch["status"] == FUNDING_CLEAN_CARRY_STATUS_REFUSED_BUNDLE
    assert BUNDLE_REASON_HASH_MISMATCH in batch["reason_codes"]


def test_batch_stamp_default_mode_is_live_current_and_labeled(
    tmp_path: Path,
) -> None:
    """(5) default (no source_mode) stays live-current and labels the mode."""
    db_path, _envelope = _batch_snapshot_setup(tmp_path)

    report = _verify_with_explicit_data_dir(db_path)
    batch = report["funding_clean_carry_batch"]
    assert batch["source_resolution_mode"] == SOURCE_MODE_LIVE_CURRENT
    assert report["funding_clean_carry_batch_decision"] == CLEAN_NET_OF_CARRY
    assert report["funding_clean_carry_batch_status"] == (
        FUNDING_CLEAN_CARRY_STATUS_CLEAN
    )


def test_bundle_mode_does_not_weaken_full_ledger_gate(tmp_path: Path) -> None:
    """(4) full-ledger gate semantics are unchanged by the batch-stamp change.

    The full-ledger clean-carry gate already honored bundle mode; threading
    ``source_mode`` through the additive batch stamp must not alter it. With a
    batch-scoped snapshot (whose window != the full-ledger span), the full-ledger
    gate stays CAVEATED on a window mismatch even under bundle mode, while the
    batch stamp is CLEAN.
    """
    db_path, envelope = _batch_snapshot_setup(tmp_path)
    _build_planned_bundle(db_path, envelope)
    _drift_live_sol_funding_rate(db_path)

    result = verify_database(db_path, source_mode=SOURCE_MODE_BUNDLE)
    assert result.status == STATUS_OK, result.failures
    report = result.report

    assert report["funding_clean_carry_batch_decision"] == CLEAN_NET_OF_CARRY
    # Full-ledger gate still refuses: the batch-scoped snapshot window does not
    # cover the full funding span, independent of source_mode.
    assert report["funding_clean_carry_decision"] == CAVEATED_ENGINE_SEMANTICS
    assert report["funding_clean_carry"]["source_resolution_mode"] == (
        SOURCE_MODE_BUNDLE
    )


# ---------------------------------------------------------------------------
# Covering-superset window semantics tests.
#
# The window comparison in clean_mode_decision_from_snapshot_v1() was changed
# from strict equality to covering-superset semantics:
#
#   Before: snapshot evaluation window must exactly equal expected window
#   After:  snapshot evaluation window must cover (start <= expected_start
#           AND end >= expected_end) the expected window
#
# These tests validate the new semantics and guard against regressions.
# ---------------------------------------------------------------------------


def test_batch_scope_accepts_covering_superset_window(tmp_path: Path) -> None:
    """PR #114 regression: bundle/source evaluation window that is a covering
    superset of the batch window is accepted.

    Snapshot window: 2026-06-25T08:00:00Z → 2026-07-05T16:00:00Z
    Batch window:    2026-07-03T08:00:00Z → 2026-07-05T16:00:00Z

    The snapshot window starts before the batch window (covers earlier) and
    ends at the same time, so it is a covering superset → should pass.
    """
    db_path = _db_with_latest_batch_window(tmp_path)
    # Override DB watermarks to match the PR #114 scenario batch window.
    _set_latest_batch_watermarks(
        db_path,
        prior="2026-07-03T08:00:00",
        new="2026-07-05T16:00:00",
    )
    envelope = _batch_scoped_snapshot(
        db_path,
        batch_start_watermark="2026-07-03T08:00:00",
        batch_end_watermark="2026-07-05T16:00:00",
        evaluation_window={
            "start": "2026-06-25T08:00:00Z",
            "end": "2026-07-05T16:00:00Z",
        },
    )
    _attach_latest_batch_snapshot(db_path, envelope)

    report = _verify_with_explicit_data_dir(db_path)

    _assert_batch_fields_present(report)
    assert report["funding_clean_carry_batch_decision"] == CLEAN_NET_OF_CARRY
    assert report["funding_clean_carry_batch_status"] == (
        FUNDING_CLEAN_CARRY_STATUS_CLEAN
    )
    assert "funding_source_batch_window_mismatch" not in (
        report["funding_clean_carry_batch_reason_codes"]
    )
    _assert_full_ledger_stays_caveated(report)


def test_batch_scope_accepts_exact_window(tmp_path: Path) -> None:
    """Exact window match still works (regression guard)."""
    db_path = _db_with_latest_batch_window(tmp_path)
    envelope = _batch_scoped_snapshot(db_path)
    _attach_latest_batch_snapshot(db_path, envelope)

    report = _verify_with_explicit_data_dir(db_path)

    _assert_batch_fields_present(report)
    assert report["funding_clean_carry_batch_decision"] == CLEAN_NET_OF_CARRY
    assert report["funding_clean_carry_batch_status"] == (
        FUNDING_CLEAN_CARRY_STATUS_CLEAN
    )
    assert report["funding_clean_carry_batch_reason_codes"] == []
    _assert_full_ledger_stays_caveated(report)


def test_batch_scope_refuses_window_start_after_batch_start(tmp_path: Path) -> None:
    """Snapshot window starts after batch window start → refused.

    The snapshot window starts at 01:00 (after batch start 00:00) and ends
    at 08:00 (same as batch end). Since start > batch start, it does not
    cover the batch window.
    """
    db_path = _db_with_latest_batch_window(tmp_path)
    envelope = _batch_scoped_snapshot(
        db_path,
        batch_start_watermark="2026-06-15T01:00:00",
        evaluation_window={
            "start": "2026-06-15T01:00:00",
            "end": _BATCH_END,
        },
    )
    _attach_latest_batch_snapshot(db_path, envelope)

    report = _verify_with_explicit_data_dir(db_path)

    _assert_batch_fields_present(report)
    assert report["funding_clean_carry_batch_decision"] == CAVEATED_ENGINE_SEMANTICS
    assert report["funding_clean_carry_batch_status"] == (
        FUNDING_CLEAN_CARRY_STATUS_REFUSED_DB_OR_LANE_MISMATCH
    )
    assert "funding_source_batch_window_mismatch" in (
        report["funding_clean_carry_batch_reason_codes"]
    )
    _assert_full_ledger_stays_caveated(report)


def test_batch_scope_refuses_window_end_before_batch_end(tmp_path: Path) -> None:
    """Snapshot window ends before batch window end → refused.

    The snapshot window starts at 00:00 (same as batch start) but ends at
    07:00 (before batch end 08:00). Since end < batch end, it does not
    cover the batch window.
    """
    db_path = _db_with_latest_batch_window(tmp_path)
    envelope = _batch_scoped_snapshot(
        db_path,
        batch_start_watermark=_BATCH_START,
        evaluation_window={
            "start": _BATCH_START,
            "end": "2026-06-15T07:00:00",
        },
    )
    _attach_latest_batch_snapshot(db_path, envelope)

    report = _verify_with_explicit_data_dir(db_path)

    _assert_batch_fields_present(report)
    assert report["funding_clean_carry_batch_decision"] == CAVEATED_ENGINE_SEMANTICS
    assert report["funding_clean_carry_batch_status"] == (
        FUNDING_CLEAN_CARRY_STATUS_REFUSED_DB_OR_LANE_MISMATCH
    )
    assert "funding_source_batch_window_mismatch" in (
        report["funding_clean_carry_batch_reason_codes"]
    )
    _assert_full_ledger_stays_caveated(report)


def test_batch_scope_refuses_missing_window_boundaries(tmp_path: Path) -> None:
    """Snapshot window with None/missing start or end → refused.

    The payload builder validates evaluation_window values, so we build a
    valid envelope first, then corrupt the evaluation_window in the written
    JSON file to simulate a None boundary.
    """
    import json

    db_path = _db_with_latest_batch_window(tmp_path)
    # Build a valid envelope first.
    envelope = _batch_scoped_snapshot(db_path)
    # Corrupt the evaluation_window start to None in the payload.
    envelope["snapshot_payload"]["evaluation_window"] = {
        "start": None,
        "end": _BATCH_END,
    }
    # Recompute the SHA256 since we mutated the payload.
    from quantbot.paper.funding_source_snapshot import canonical_json, sha256_text

    envelope["snapshot_sha256"] = sha256_text(
        canonical_json(envelope["snapshot_payload"])
    )
    _attach_latest_batch_snapshot(db_path, envelope)

    report = _verify_with_explicit_data_dir(db_path)

    _assert_batch_fields_present(report)
    assert report["funding_clean_carry_batch_decision"] == CAVEATED_ENGINE_SEMANTICS
    assert report["funding_clean_carry_batch_status"] == (
        FUNDING_CLEAN_CARRY_STATUS_REFUSED_DB_OR_LANE_MISMATCH
    )
    assert "funding_source_batch_window_mismatch" in (
        report["funding_clean_carry_batch_reason_codes"]
    )
    _assert_full_ledger_stays_caveated(report)


def test_full_ledger_clean_carry_unchanged(tmp_path: Path) -> None:
    """Full-ledger clean-carry behavior remains unchanged.

    The full-ledger gate still uses strict equality semantics and is not
    affected by the covering-superset change. A batch-scoped snapshot whose
    window does not match the full funding span should still produce
    CAVEATED on the full-ledger fields.
    """
    db_path = _db_with_latest_batch_window(tmp_path)
    envelope = _batch_scoped_snapshot(db_path)
    _attach_latest_batch_snapshot(db_path, envelope)

    report = _verify_with_explicit_data_dir(db_path)

    _assert_full_ledger_stays_caveated(report)
    assert "funding_source_snapshot_window_mismatch" in (
        report["funding_clean_carry_reason_codes"]
    )
    # Batch-scoped fields are clean (covering-superset passes)
    assert report["funding_clean_carry_batch_decision"] == CLEAN_NET_OF_CARRY
    assert report["funding_clean_carry_batch_reason_codes"] == []


def test_batch_stamp_live_current_compatible(tmp_path: Path) -> None:
    """Live-current/default mode remains compatible with existing expectations.

    A clean batch-scoped snapshot with live-current source mode should
    produce CLEAN_NET_OF_CARRY on the batch stamp and CAVEATED on the
    full-ledger fields.
    """
    db_path = _db_with_latest_batch_window(tmp_path)
    envelope = _batch_scoped_snapshot(db_path)
    _attach_latest_batch_snapshot(db_path, envelope)

    report = _verify_with_explicit_data_dir(db_path)

    _assert_batch_fields_present(report)
    _assert_full_ledger_stays_caveated(report)
    assert report["funding_clean_carry_batch_decision"] == CLEAN_NET_OF_CARRY
    assert report["funding_clean_carry_batch_status"] == (
        FUNDING_CLEAN_CARRY_STATUS_CLEAN
    )
    assert report["funding_clean_carry_batch_reason_codes"] == []
    batch = report["funding_clean_carry_batch"]
    assert batch["source_resolution_mode"] == SOURCE_MODE_LIVE_CURRENT
