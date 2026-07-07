"""Pin funding-source digest/window clean-carry semantics (tests only).

These tests pin the CURRENT verifier digest/window semantics before any
operational snapshot rebuild, recommit, DB mutation, or official report
promotion. They are pure and deterministic: no SQLite, no prod/shadow DBs,
no ``/srv``, no VM, no writer/trader/live code, no network, and no coupling
to the wall clock. Only tmp CSV bytes and in-memory snapshot payloads are used.

They pin the diagnosis recorded in
``docs/status/funding_source_digest_window_mismatch_diagnosis_2026-07-07.md``:

  * source files changed after a committed snapshot (a "source refresh")
    -> ``funding_source_file_digest_mismatch``
    (``CURRENT_SOURCE_FILES_CHANGED_AFTER_SNAPSHOT``)
  * a batch-scoped evaluation window can match the latest batch window yet
    still fail the full-ledger clean-carry gate
    -> ``funding_source_snapshot_window_mismatch``
    (``SNAPSHOT_WINDOW_DOES_NOT_COVER_LEDGER`` /
    ``WINDOW_OK_BUT_VERIFIER_RULE_STRICT``)
  * a full-ledger-scoped snapshot with matching source digests clears both
    the window and digest gates.

No profitability or edge claim is made or changed by these tests. The strategy
edge remains ``EDGE_UNPROVEN``, live integration remains
``BLOCK_LIVE_INTEGRATION``, and the full-ledger funding clean-carry decision
remains ``CAVEATED_ENGINE_SEMANTICS`` while any digest/window caveat is present.
Only an empty reason set is promotable to an official ``CLEAN_NET_OF_CARRY``
label; these tests pin that any digest/window reason code blocks that promotion.
"""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import pytest

from quantbot.paper.funding_source_snapshot import (
    build_funding_source_snapshot_envelope_v1,
    build_funding_source_snapshot_payload_v1,
    build_source_file_digest,
    clean_mode_decision_from_snapshot_v1,
)
from quantbot.paper.funding_status import (
    CAVEATED_ENGINE_SEMANTICS,
    CLEAN_NET_OF_CARRY,
)
from quantbot.paper.sqlite_verify import (
    FUNDING_CLEAN_CARRY_STATUS_CLEAN,
    FUNDING_CLEAN_CARRY_STATUS_REFUSED_DB_OR_LANE_MISMATCH,
    FUNDING_CLEAN_CARRY_STATUS_REFUSED_DIGEST_MISMATCH,
    _clean_carry_status_from_reasons,
)

_SYMBOL = "SOLUSDT"
_GENERATED_AT = "2026-07-05T17:00:00Z"
_GIT_SHA = "41bbc86246489c393c53c46349b8e8f5d5967522"

# Windows taken verbatim from the 2026-07-07 digest/window mismatch diagnosis.
_BATCH_WINDOW = {"start": "2026-07-03T08:00:00Z", "end": "2026-07-05T16:00:00Z"}
_FULL_LEDGER_WINDOW = {"start": "2026-06-25T08:00:00Z", "end": "2026-07-05T16:00:00Z"}

# One 8h funding coverage window whose endpoint coincides with the shared
# window end. A single source row placed exactly at the endpoint yields a
# complete-coverage snapshot with no coverage reason codes, so the tests below
# isolate purely the digest and window gates.
_COVERAGE_WINDOW_START = "2026-07-05T08:00:00Z"
_COVERAGE_WINDOW_END = "2026-07-05T16:00:00Z"


def _ms(iso: str) -> int:
    dt = datetime.fromisoformat(iso.replace("Z", "+00:00"))
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return int(dt.timestamp() * 1000)


def _write_source_csv(tmp_path: Path, *, rate: str = "0.00010000") -> Path:
    data_dir = tmp_path / "data"
    data_dir.mkdir(parents=True, exist_ok=True)
    path = data_dir / f"{_SYMBOL}_8h_funding.csv"
    path.write_text(
        "fundingTime,fundingRate\n" f"{_ms(_COVERAGE_WINDOW_END)},{rate}\n",
        encoding="utf-8",
    )
    return path


def _source_rows(path: Path, *, rate: str = "0.00010000") -> list[dict[str, Any]]:
    return [
        {
            "symbol": _SYMBOL,
            "fundingTime_ms": _ms(_COVERAGE_WINDOW_END),
            "source_file_path": str(path),
            "row_index": 1,
            "funding_rate": rate,
        }
    ]


def _required_windows() -> list[dict[str, Any]]:
    return [
        {
            "symbol": _SYMBOL,
            "window_start": _COVERAGE_WINDOW_START,
            "window_end": _COVERAGE_WINDOW_END,
            "required_by": "paper_engine_funding_interval",
        }
    ]


def _build_snapshot(
    path: Path,
    *,
    evaluation_window: dict[str, str],
    rate: str = "0.00010000",
) -> dict[str, Any]:
    payload = build_funding_source_snapshot_payload_v1(
        source_rows=_source_rows(path, rate=rate),
        source_file_paths=[path],
        required_windows=_required_windows(),
        generated_at_utc=_GENERATED_AT,
        lane_id="paper_pnl_v1",
        output_dir=str(path.parent.parent),
        writer_or_verifier_command=(
            "local synthetic funding-source digest/window semantics test"
        ),
        qnty_git_commit=_GIT_SHA,
        write_state="committed",
        db_identity_hash_before="local-synthetic-before",
        pending_batch_id="pending-local-synthetic",
        ledger_batch_id="1",
        evaluation_window=evaluation_window,
        db_path_reference=str(path.parent.parent / "paper.sqlite"),
        sanitized_host_user_label="local-test",
    )
    return build_funding_source_snapshot_envelope_v1(payload)


def _status_for(reason_codes: list[str]) -> str:
    return _clean_carry_status_from_reasons(sorted(set(reason_codes)))


def _decision_for(reason_codes: list[str]) -> str:
    # Mirrors quantbot.paper.sqlite_verify._build_funding_clean_carry_stamp:
    # only an empty reason set (STATUS_CLEAN) is promotable to CLEAN_NET_OF_CARRY.
    status = _status_for(reason_codes)
    return (
        CLEAN_NET_OF_CARRY
        if status == FUNDING_CLEAN_CARRY_STATUS_CLEAN
        else CAVEATED_ENGINE_SEMANTICS
    )


# Test A -- stale source digest refusal.
def test_stale_source_file_digest_refuses_clean_carry(tmp_path: Path) -> None:
    path = _write_source_csv(tmp_path)
    envelope = _build_snapshot(path, evaluation_window=_FULL_LEDGER_WINDOW)

    # Source file bytes change after the snapshot was committed (a refresh).
    refreshed = _write_source_csv(tmp_path, rate="0.00020000")
    assert refreshed == path
    refreshed_expectation = {str(path): build_source_file_digest(path)}

    decision = clean_mode_decision_from_snapshot_v1(
        envelope,
        expected_evaluation_window=_FULL_LEDGER_WINDOW,
        expected_source_file_sha256_by_path=refreshed_expectation,
    )

    assert "funding_source_file_digest_mismatch" in decision["reason_codes"]
    assert decision["clean_net_of_carry_allowed"] is False
    assert _status_for(decision["reason_codes"]) == (
        FUNDING_CLEAN_CARRY_STATUS_REFUSED_DIGEST_MISMATCH
    )
    assert _decision_for(decision["reason_codes"]) == CAVEATED_ENGINE_SEMANTICS


# Test B -- batch window valid, full-ledger window invalid.
def test_batch_window_valid_but_full_ledger_window_mismatch(tmp_path: Path) -> None:
    path = _write_source_csv(tmp_path)
    envelope = _build_snapshot(path, evaluation_window=_BATCH_WINDOW)
    file_expectation = {str(path): build_source_file_digest(path)}

    batch = clean_mode_decision_from_snapshot_v1(
        envelope,
        expected_evaluation_window=_BATCH_WINDOW,
        expected_source_file_sha256_by_path=file_expectation,
    )
    full = clean_mode_decision_from_snapshot_v1(
        envelope,
        expected_evaluation_window=_FULL_LEDGER_WINDOW,
        expected_source_file_sha256_by_path=file_expectation,
    )

    # Batch path: the snapshot window matches the expected batch window.
    assert "funding_source_snapshot_window_mismatch" not in batch["reason_codes"]

    # Full-ledger path: the batch-scoped snapshot cannot cover the full-ledger
    # window, so the strict-equality window gate fails.
    assert "funding_source_snapshot_window_mismatch" in full["reason_codes"]
    assert full["clean_net_of_carry_allowed"] is False
    assert _decision_for(full["reason_codes"]) == CAVEATED_ENGINE_SEMANTICS


# Test case 3 -- a batch-scoped snapshot whose evaluation window matches the
# batch window must not raise a window mismatch and (with matching digests and
# complete coverage) is clean on the batch path.
def test_batch_scoped_snapshot_matching_batch_window_has_no_window_mismatch(
    tmp_path: Path,
) -> None:
    path = _write_source_csv(tmp_path)
    envelope = _build_snapshot(path, evaluation_window=_BATCH_WINDOW)
    file_expectation = {str(path): build_source_file_digest(path)}

    batch = clean_mode_decision_from_snapshot_v1(
        envelope,
        expected_evaluation_window=_BATCH_WINDOW,
        expected_source_file_sha256_by_path=file_expectation,
    )

    assert "funding_source_snapshot_window_mismatch" not in batch["reason_codes"]
    assert "funding_source_file_digest_mismatch" not in batch["reason_codes"]
    assert batch["reason_codes"] == []
    assert batch["clean_net_of_carry_allowed"] is True


# Test C -- a full-ledger-scoped snapshot with matching digests clears both the
# window and digest gates.
def test_full_ledger_snapshot_clears_window_and_digest_gates(tmp_path: Path) -> None:
    path = _write_source_csv(tmp_path)
    envelope = _build_snapshot(path, evaluation_window=_FULL_LEDGER_WINDOW)
    file_expectation = {str(path): build_source_file_digest(path)}

    decision = clean_mode_decision_from_snapshot_v1(
        envelope,
        expected_evaluation_window=_FULL_LEDGER_WINDOW,
        expected_source_file_sha256_by_path=file_expectation,
    )

    # Digest/window reason codes are specifically absent.
    assert "funding_source_snapshot_window_mismatch" not in decision["reason_codes"]
    assert "funding_source_file_digest_mismatch" not in decision["reason_codes"]
    # No other caveats remain under this pure fixture.
    assert decision["reason_codes"] == []
    assert decision["clean_net_of_carry_allowed"] is True


# Test D -- official report promotion remains blocked while any digest/window
# caveat is present. Only an empty reason set maps to the promotable clean
# status; any digest/window reason code keeps the decision CAVEATED and
# therefore non-promotable. This pins the existing helper without adding any
# production code.
@pytest.mark.parametrize(
    ("reason_code", "expected_status"),
    [
        (
            "funding_source_file_digest_mismatch",
            FUNDING_CLEAN_CARRY_STATUS_REFUSED_DIGEST_MISMATCH,
        ),
        (
            "funding_source_snapshot_window_mismatch",
            FUNDING_CLEAN_CARRY_STATUS_REFUSED_DB_OR_LANE_MISMATCH,
        ),
    ],
)
def test_digest_or_window_caveat_blocks_promotion(
    reason_code: str,
    expected_status: str,
) -> None:
    status = _clean_carry_status_from_reasons([reason_code])

    assert status == expected_status
    assert status != FUNDING_CLEAN_CARRY_STATUS_CLEAN
    decision = _decision_for([reason_code])
    assert decision == CAVEATED_ENGINE_SEMANTICS
    assert decision != CLEAN_NET_OF_CARRY


def test_only_empty_reason_set_is_promotable_to_clean() -> None:
    assert _clean_carry_status_from_reasons([]) == FUNDING_CLEAN_CARRY_STATUS_CLEAN
    assert _decision_for([]) == CLEAN_NET_OF_CARRY

    # A lone digest or window caveat is never promotable to an official clean
    # / CLEAN_NET_OF_CARRY label.
    for reason_code in (
        "funding_source_file_digest_mismatch",
        "funding_source_snapshot_window_mismatch",
    ):
        assert (
            _clean_carry_status_from_reasons([reason_code])
            != FUNDING_CLEAN_CARRY_STATUS_CLEAN
        )
        assert _decision_for([reason_code]) != CLEAN_NET_OF_CARRY
