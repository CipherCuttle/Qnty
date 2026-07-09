"""Full-window funding-source snapshot semantics (PR #119 follow-up).

These tests pin the explicit ``snapshot_scope`` discriminator, the full-window
snapshot builder, the absolute ``resolved_funding_source_dir`` provenance field,
and the scope-aware clean-carry decision + bundle carry-through. Together they
show, purely, why a prod-like ledger with only 8h batch snapshots cannot reach
full-ledger CLEAN_NET_OF_CARRY and how an explicit full-window snapshot makes it
reachable — without weakening any binding or digest check.
"""

from __future__ import annotations

import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import pytest

from quantbot.paper.funding_source_bundle import (
    build_funding_source_bundle_v1,
    bundle_window_reasons,
)
from quantbot.paper.funding_source_snapshot import (
    SNAPSHOT_SCOPE_BATCH,
    SNAPSHOT_SCOPE_FULL_WINDOW,
    build_full_window_funding_source_snapshot_payload_v1,
    build_funding_source_snapshot_envelope_v1,
    build_funding_source_snapshot_payload_v1,
    clean_mode_decision_from_snapshot_v1,
    validate_funding_source_snapshot_envelope_v1,
)
from quantbot.paper.sqlite_verify import _full_ledger_requires_full_window_scope

_LANE_ID = "paper_pnl_v1"
_DB_IDENTITY = "paper-ledger-db-identity-sha256"
_GENERATED_AT = "2026-07-05T16:01:00Z"
_QNTY_GIT_COMMIT = "41bbc86246489c393c53c46349b8e8f5d5967522"
_COMMAND = "qnty-paper-sqlite-verify --clean-mode"
_SOURCE_PATH = "data/SOLUSDT_8h_funding.csv"
_RESOLVED_DIR = "/srv/qnty/repo/data"

# Three consecutive 8h windows -> a full-ledger span across multiple batches.
_W1 = ("2026-06-14T16:00:00Z", "2026-06-15T00:00:00Z")
_W2 = ("2026-06-15T00:00:00Z", "2026-06-15T08:00:00Z")
_W3 = ("2026-06-15T08:00:00Z", "2026-06-15T16:00:00Z")
_FULL_LEDGER_WINDOW = {"start": _W1[0], "end": _W3[1]}


def _ms_at(raw: str, *, offset_ms: int = 0) -> int:
    dt = datetime.fromisoformat(raw.replace("Z", "+00:00")).astimezone(timezone.utc)
    return int(dt.timestamp() * 1000) + offset_ms


def _window(start: str, end: str) -> dict[str, Any]:
    return {"symbol": "SOL", "window_start": start, "window_end": end}


def _row(window_end: str, *, row_index: int) -> dict[str, Any]:
    # Accepted at the window's canonical endpoint (small positive offset).
    return {
        "symbol": "SOL",
        "fundingTime_ms": _ms_at(window_end, offset_ms=5),
        "source_file_path": _SOURCE_PATH,
        "row_index": row_index,
        "funding_rate": "0.0001",
    }


_SOURCE_CONTENTS = {_SOURCE_PATH: "fundingTime,fundingRate,markPrice\n"}


def _batch_payload(**overrides: Any) -> dict[str, Any]:
    """A single-8h-window (batch-scope, default) snapshot payload."""
    kwargs: dict[str, Any] = dict(
        source_rows=[_row(_W3[1], row_index=3)],
        required_windows=[_window(*_W3)],
        source_file_contents_by_path=_SOURCE_CONTENTS,
        generated_at_utc=_GENERATED_AT,
        lane_id=_LANE_ID,
        output_dir=f"/sanitized/{_LANE_ID}",
        writer_or_verifier_command=_COMMAND,
        qnty_git_commit=_QNTY_GIT_COMMIT,
        db_identity_hash_before=_DB_IDENTITY,
        ledger_batch_id="batch-3",
    )
    kwargs.update(overrides)
    return build_funding_source_snapshot_payload_v1(**kwargs)


def _full_window_payload(**overrides: Any) -> dict[str, Any]:
    """A full-window snapshot payload spanning all three windows."""
    kwargs: dict[str, Any] = dict(
        source_rows=[
            _row(_W1[1], row_index=1),
            _row(_W2[1], row_index=2),
            _row(_W3[1], row_index=3),
        ],
        required_windows=[_window(*_W1), _window(*_W2), _window(*_W3)],
        full_ledger_evaluation_window=_FULL_LEDGER_WINDOW,
        source_file_contents_by_path=_SOURCE_CONTENTS,
        generated_at_utc=_GENERATED_AT,
        lane_id=_LANE_ID,
        output_dir=f"/sanitized/{_LANE_ID}",
        resolved_funding_source_dir=_RESOLVED_DIR,
        writer_or_verifier_command=_COMMAND,
        qnty_git_commit=_QNTY_GIT_COMMIT,
        db_identity_hash_before=_DB_IDENTITY,
        ledger_batch_id="batch-3",
    )
    kwargs.update(overrides)
    return build_full_window_funding_source_snapshot_payload_v1(**kwargs)


def _digests(payload: dict[str, Any]) -> tuple[dict[str, str], dict[str, str]]:
    files = {
        str(item["path"]): item for item in payload["source_files"]
    }
    file_sha = {p: str(i["full_file_sha256"]) for p, i in files.items()}
    row_sha = {p: str(i["canonical_row_subset_sha256"]) for p, i in files.items()}
    return file_sha, row_sha


def _clean_full_window_decision(payload: dict[str, Any], **overrides: Any) -> dict[str, Any]:
    file_sha, row_sha = _digests(payload)
    envelope = build_funding_source_snapshot_envelope_v1(payload)
    kwargs: dict[str, Any] = dict(
        expected_evaluation_window=_FULL_LEDGER_WINDOW,
        expected_lane_id=_LANE_ID,
        expected_db_identity_hash_before=_DB_IDENTITY,
        expected_source_file_sha256_by_path=file_sha,
        expected_row_subset_sha256_by_path=row_sha,
        expected_snapshot_scope=SNAPSHOT_SCOPE_FULL_WINDOW,
    )
    kwargs.update(overrides)
    return clean_mode_decision_from_snapshot_v1(envelope, **kwargs)


# --- 1. existing batch snapshot fixture still validates ---------------------


def test_batch_snapshot_still_validates_and_defaults_to_batch_scope() -> None:
    payload = _batch_payload()
    envelope = build_funding_source_snapshot_envelope_v1(payload)
    assert validate_funding_source_snapshot_envelope_v1(envelope) == []
    assert payload["snapshot_scope"] == SNAPSHOT_SCOPE_BATCH
    assert payload["coverage_decision"] == "complete"


# --- 2/3. full-window snapshot fixture (with absolute dir) validates --------


def test_full_window_snapshot_validates_with_absolute_resolved_dir() -> None:
    payload = _full_window_payload()
    envelope = build_funding_source_snapshot_envelope_v1(payload)
    assert validate_funding_source_snapshot_envelope_v1(envelope) == []
    assert payload["snapshot_scope"] == SNAPSHOT_SCOPE_FULL_WINDOW
    resolution = payload["provenance"]["source_path_resolution"]
    assert resolution["resolved_funding_source_dir"] == _RESOLVED_DIR
    assert Path(resolution["resolved_funding_source_dir"]).is_absolute()
    assert payload["evaluation_window"] == {
        "start": "2026-06-14T16:00:00Z",
        "end": "2026-06-15T16:00:00Z",
    }


# --- 4. full-window snapshot covers full-ledger window and passes -----------


def test_full_window_snapshot_passes_full_ledger_window_check() -> None:
    decision = _clean_full_window_decision(_full_window_payload())
    assert decision == {"clean_net_of_carry_allowed": True, "reason_codes": []}


# --- 5. 8h batch snapshot refuses full-ledger window ------------------------


def test_batch_snapshot_refuses_full_ledger_window_mismatch() -> None:
    file_sha, row_sha = _digests(_batch_payload())
    envelope = build_funding_source_snapshot_envelope_v1(_batch_payload())
    decision = clean_mode_decision_from_snapshot_v1(
        envelope,
        expected_evaluation_window=_FULL_LEDGER_WINDOW,
        expected_lane_id=_LANE_ID,
        expected_db_identity_hash_before=_DB_IDENTITY,
        expected_source_file_sha256_by_path=file_sha,
        expected_row_subset_sha256_by_path=row_sha,
        expected_snapshot_scope=SNAPSHOT_SCOPE_FULL_WINDOW,
    )
    assert decision["clean_net_of_carry_allowed"] is False
    assert "funding_source_snapshot_window_mismatch" in decision["reason_codes"]
    # Scope is explicit: a batch snapshot never satisfies a full-window gate.
    assert "funding_source_snapshot_scope_mismatch" in decision["reason_codes"]


# --- 6. missing full-window snapshot emits a clear reason code --------------


def test_missing_full_window_snapshot_reason_code() -> None:
    decision = clean_mode_decision_from_snapshot_v1(
        None, expected_snapshot_scope=SNAPSHOT_SCOPE_FULL_WINDOW
    )
    assert decision == {
        "clean_net_of_carry_allowed": False,
        "reason_codes": ["funding_source_full_window_snapshot_missing"],
    }


# --- 7. wrong lane / DB binding refuses -------------------------------------


def test_full_window_snapshot_wrong_lane_binding_refuses() -> None:
    decision = _clean_full_window_decision(
        _full_window_payload(), expected_lane_id="paper_pnl_null_shadow_v0"
    )
    assert decision["clean_net_of_carry_allowed"] is False
    assert "funding_source_snapshot_db_mismatch" in decision["reason_codes"]


def test_full_window_snapshot_wrong_db_identity_refuses() -> None:
    decision = _clean_full_window_decision(
        _full_window_payload(), expected_db_identity_hash_before="0" * 64
    )
    assert decision["clean_net_of_carry_allowed"] is False
    assert "funding_source_snapshot_db_mismatch" in decision["reason_codes"]


# --- 8/9. digest mismatches refuse ------------------------------------------


def test_full_window_snapshot_row_digest_mismatch_refuses() -> None:
    decision = _clean_full_window_decision(
        _full_window_payload(),
        expected_row_subset_sha256_by_path={_SOURCE_PATH: "0" * 64},
    )
    assert decision["clean_net_of_carry_allowed"] is False
    assert "funding_source_row_digest_mismatch" in decision["reason_codes"]


def test_full_window_snapshot_file_digest_mismatch_refuses() -> None:
    decision = _clean_full_window_decision(
        _full_window_payload(),
        expected_source_file_sha256_by_path={_SOURCE_PATH: "0" * 64},
    )
    assert decision["clean_net_of_carry_allowed"] is False
    assert "funding_source_file_digest_mismatch" in decision["reason_codes"]


# --- 10/11. bundle carry-through --------------------------------------------


def test_full_window_snapshot_yields_full_window_bundle() -> None:
    payload = _full_window_payload()
    envelope = build_funding_source_snapshot_envelope_v1(payload)
    bundle = build_funding_source_bundle_v1(envelope)
    bp = bundle["bundle_payload"]
    assert bp["snapshot_scope"] == SNAPSHOT_SCOPE_FULL_WINDOW
    assert bp["resolved_funding_source_dir"] == _RESOLVED_DIR
    # The frozen rows cover every required full-ledger window (no ambiguity).
    assert bundle_window_reasons(bp) == []
    assert bp["row_counts"]["total"] == 3


def test_batch_bundle_scope_unchanged_default_batch() -> None:
    payload = _batch_payload()
    envelope = build_funding_source_snapshot_envelope_v1(payload)
    bundle = build_funding_source_bundle_v1(envelope)
    bp = bundle["bundle_payload"]
    assert bp["snapshot_scope"] == SNAPSHOT_SCOPE_BATCH
    assert bp["resolved_funding_source_dir"] is None
    assert bundle_window_reasons(bp) == []


def test_bundle_identity_hash_ignores_new_fields() -> None:
    # source_bundle_sha256 content-addresses only canonical_rows, so the added
    # scope/dir fields must not change bundle identity for the same frozen rows.
    payload = _batch_payload()
    envelope = build_funding_source_snapshot_envelope_v1(payload)
    bp = build_funding_source_bundle_v1(envelope)["bundle_payload"]
    from quantbot.paper.funding_source_bundle import recompute_bundle_sha256

    assert recompute_bundle_sha256(bp) == bp["source_bundle_sha256"]


# --- 12. builder input validation -------------------------------------------


def test_relative_resolved_dir_rejected() -> None:
    with pytest.raises(ValueError, match="must be absolute"):
        build_funding_source_snapshot_payload_v1(
            source_rows=[],
            required_windows=[],
            generated_at_utc=_GENERATED_AT,
            lane_id=_LANE_ID,
            output_dir="/x",
            writer_or_verifier_command=_COMMAND,
            qnty_git_commit=_QNTY_GIT_COMMIT,
            resolved_funding_source_dir="data",
        )


def test_unsupported_scope_rejected() -> None:
    with pytest.raises(ValueError, match="snapshot_scope"):
        build_funding_source_snapshot_payload_v1(
            source_rows=[],
            required_windows=[],
            generated_at_utc=_GENERATED_AT,
            lane_id=_LANE_ID,
            output_dir="/x",
            writer_or_verifier_command=_COMMAND,
            qnty_git_commit=_QNTY_GIT_COMMIT,
            snapshot_scope="ledger",
        )


# --- 13. explicit-scope strictness ------------------------------------------


def test_batch_scope_with_widened_window_still_refused_by_scope() -> None:
    # Even if a batch snapshot's evaluation_window is (wrongly) wide enough to
    # cover the full-ledger span, the explicit scope discriminator refuses it:
    # an 8h snapshot is never silently reinterpreted as a full-window snapshot.
    widened = _batch_payload(evaluation_window=_FULL_LEDGER_WINDOW)
    assert widened["snapshot_scope"] == SNAPSHOT_SCOPE_BATCH
    file_sha, row_sha = _digests(widened)
    decision = clean_mode_decision_from_snapshot_v1(
        build_funding_source_snapshot_envelope_v1(widened),
        expected_evaluation_window=_FULL_LEDGER_WINDOW,
        expected_lane_id=_LANE_ID,
        expected_db_identity_hash_before=_DB_IDENTITY,
        expected_source_file_sha256_by_path=file_sha,
        expected_row_subset_sha256_by_path=row_sha,
        expected_snapshot_scope=SNAPSHOT_SCOPE_FULL_WINDOW,
    )
    assert decision["clean_net_of_carry_allowed"] is False
    assert "funding_source_snapshot_scope_mismatch" in decision["reason_codes"]


# --- 14. PR #119 regression -------------------------------------------------


def test_pr119_regression_full_window_unblocks_full_ledger_clean() -> None:
    # Prod-like: only an 8h batch snapshot -> cannot reach full-ledger clean.
    file_sha, row_sha = _digests(_batch_payload())
    batch_decision = clean_mode_decision_from_snapshot_v1(
        build_funding_source_snapshot_envelope_v1(_batch_payload()),
        expected_evaluation_window=_FULL_LEDGER_WINDOW,
        expected_lane_id=_LANE_ID,
        expected_db_identity_hash_before=_DB_IDENTITY,
        expected_source_file_sha256_by_path=file_sha,
        expected_row_subset_sha256_by_path=row_sha,
        expected_snapshot_scope=SNAPSHOT_SCOPE_FULL_WINDOW,
    )
    assert batch_decision["clean_net_of_carry_allowed"] is False

    # Adding an explicit full-window snapshot makes full-ledger clean reachable.
    full_decision = _clean_full_window_decision(_full_window_payload())
    assert full_decision == {"clean_net_of_carry_allowed": True, "reason_codes": []}


# --- verifier trigger: single-batch unchanged, multi-batch requires scope ---


def _mk_ledger_batches_db(path: Path, committed: int) -> Path:
    conn = sqlite3.connect(path)
    conn.execute(
        "CREATE TABLE ledger_batches (batch_id INTEGER PRIMARY KEY, "
        "committed_at TEXT)"
    )
    for i in range(1, committed + 1):
        conn.execute(
            "INSERT INTO ledger_batches (batch_id, committed_at) VALUES (?, ?)",
            (i, f"2026-06-15T0{i}:00:00Z"),
        )
    # An uncommitted (pending) batch must not count.
    conn.execute(
        "INSERT INTO ledger_batches (batch_id, committed_at) VALUES (?, NULL)",
        (committed + 1,),
    )
    conn.commit()
    return path


def test_single_committed_batch_does_not_require_full_window_scope(
    tmp_path: Path,
) -> None:
    db = _mk_ledger_batches_db(tmp_path / "one.db", committed=1)
    conn = sqlite3.connect(db)
    conn.row_factory = sqlite3.Row
    try:
        assert _full_ledger_requires_full_window_scope(conn) is False
    finally:
        conn.close()


def test_multi_committed_batch_requires_full_window_scope(tmp_path: Path) -> None:
    db = _mk_ledger_batches_db(tmp_path / "many.db", committed=3)
    conn = sqlite3.connect(db)
    conn.row_factory = sqlite3.Row
    try:
        assert _full_ledger_requires_full_window_scope(conn) is True
    finally:
        conn.close()
