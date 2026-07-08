"""Spec-first tests for immutable funding-source bundle semantics.

This file pins the observable contract described in
``docs/specs/funding_source_immutable_bundle_semantics_v0.md`` (planned in
PR #105) **before** implementation. It adds no production verifier/writer/
reporter behavior.

Two kinds of tests live here:

* Passing today (helper-only / regression-guard): canonical-serialization
  determinism against the existing snapshot primitives, and a reproduction of
  the PR #104 live-CSV drift flip that motivates bundle mode.
* Planned-behavior, marked ``xfail(strict=True)`` with reason
  ``immutable source bundle semantics not implemented yet``: bundle-mode
  verifier behavior. These fail today because bundle mode does not exist; when
  the implementation lands they will XPASS and ``strict=True`` will force the
  ``xfail`` marks to be removed.

All fixtures are tmp SQLite DBs, tmp CSVs, and tmp snapshot sidecars only. The
tests never touch /srv, never run prod/shadow writers, never mutate a real DB,
official report, live CSV, or service/timer.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

from quantbot.paper.funding_source_snapshot import (
    _canonical_row_sort_key,
    canonical_json,
    sha256_text,
)
from quantbot.paper.funding_status import (
    CAVEATED_ENGINE_SEMANTICS,
    CLEAN_NET_OF_CARRY,
)
from quantbot.paper.sqlite_verify import (
    FUNDING_CLEAN_CARRY_STATUS_CLEAN,
    FUNDING_CLEAN_CARRY_STATUS_REFUSED_DIGEST_MISMATCH,
    STATUS_OK,
    verify_database,
)
from tests.test_paper_sqlite_verifier_clean_net_of_carry_gate import (
    _add_latest_equity_snapshot,
    _clean_report,
    _committed_snapshot,
    _db_with_complete_source,
    _set_latest_batch_snapshot_reference,
    _write_snapshot,
)

# Marker for behavior the follow-on implementation PR must satisfy. strict=True
# means: when bundle mode is implemented and the test starts passing, pytest
# reports XPASS as a failure, forcing this mark to be removed.
XFAIL_REASON = "immutable source bundle semantics not implemented yet"
planned = pytest.mark.xfail(strict=True, reason=XFAIL_REASON)

# Planned report/contract vocabulary (see the spec doc). Referenced as literals
# so this module imports cleanly today; the implementation PR must honor them.
PLANNED_MODE_BUNDLE = "bundle"
PLANNED_MODE_LIVE_CURRENT = "live-current"
PLANNED_REASON_BUNDLE_MISSING = "funding_source_bundle_missing"
PLANNED_REASON_BUNDLE_CORRUPT = "funding_source_bundle_corrupt"
PLANNED_REASON_BUNDLE_HASH_MISMATCH = "funding_source_bundle_hash_mismatch"
PLANNED_REASON_BUNDLE_INCOMPLETE_WINDOW = "funding_source_bundle_incomplete_window"
PLANNED_REASON_RESUM_MISMATCH = "funding_resum_mismatch"

_DIGEST_MISMATCH_REASONS = {
    "funding_source_file_digest_mismatch",
    "funding_source_row_digest_mismatch",
    "funding_source_snapshot_digest_mismatch",
}


def _drift_live_sol_funding_rate(db_path: Path) -> None:
    """Mutate the live SOL funding CSV so its bytes drift from the committed
    snapshot without touching ``fundingTime`` (coverage stays complete; only the
    source digest changes). Reproduces the PR #104 scheduled-refresh race."""
    path = db_path.parent / "data" / "SOLUSDT_8h_funding.csv"
    lines = path.read_text().strip().splitlines()
    header, data = lines[0], lines[1:]
    assert data, "expected at least one SOL funding row"
    fields = data[0].split(",")
    # columns: fundingTime,fundingRate,markPrice -> drift the rate only.
    fields[1] = "0.00099999"
    data[0] = ",".join(fields)
    path.write_text("\n".join([header, *data]) + "\n", encoding="utf-8")


def _clean_setup(tmp_path: Path) -> Path:
    """A tmp DB + committed snapshot + DB reference that returns
    CLEAN_NET_OF_CARRY under the current verifier (mirrors the passing case in
    the clean-carry gate suite)."""
    db_path = _db_with_complete_source(tmp_path)
    _add_latest_equity_snapshot(db_path)
    envelope = _committed_snapshot(db_path)
    snapshot_path = _write_snapshot(db_path, envelope)
    _set_latest_batch_snapshot_reference(db_path, snapshot_path, envelope)
    return db_path


# ---------------------------------------------------------------------------
# Passing today: canonical serialization determinism (spec §"Canonical
# serialization constraints"). These pin the determinism guarantees the bundle
# hash will rely on, using the existing snapshot primitives.
# ---------------------------------------------------------------------------


def _canonical_rows(rows: list[dict[str, Any]]) -> str:
    ordered = sorted(rows, key=_canonical_row_sort_key)
    return canonical_json(ordered)


def _sample_rows() -> list[dict[str, Any]]:
    return [
        {
            "symbol": "SOLUSDT",
            "window_end": "2026-06-14T16:00:00Z",
            "fundingTime_ms": 1_000,
            "source_file_path": "data/SOLUSDT_8h_funding.csv",
            "row_index": 1,
            "funding_rate": "0.0001",
        },
        {
            "symbol": "BTCUSDT",
            "window_end": "2026-06-14T08:00:00Z",
            "fundingTime_ms": 2_000,
            "source_file_path": "data/BTCUSDT_8h_funding.csv",
            "row_index": 1,
            "funding_rate": "0.0002",
        },
    ]


def test_canonical_serialization_is_deterministic_regardless_of_input_row_order() -> None:
    rows = _sample_rows()
    reordered = list(reversed(rows))

    forward = sha256_text(_canonical_rows(rows))
    backward = sha256_text(_canonical_rows(reordered))

    assert forward == backward


def test_source_bundle_sha_reproduces_over_frozen_rows() -> None:
    rows = _sample_rows()

    first = sha256_text(_canonical_rows(rows))
    second = sha256_text(_canonical_rows(list(rows)))

    assert first == second
    # Changing a recorded funding rate must change the bundle identity.
    drifted = [dict(row) for row in rows]
    drifted[0]["funding_rate"] = "0.9999"
    assert sha256_text(_canonical_rows(drifted)) != first


# ---------------------------------------------------------------------------
# Passing today: regression guard reproducing the PR #104 flaw that motivates
# bundle mode. The current verifier resolves from live CSVs, so drift after
# commit flips a clean ledger to a digest-mismatch refusal. This is the
# "live-current mode still detects current CSV drift" half of the contract.
# ---------------------------------------------------------------------------


def test_current_default_mode_flips_clean_to_refused_when_live_csv_drifts(
    tmp_path: Path,
) -> None:
    db_path = _clean_setup(tmp_path)

    before = verify_database(db_path)
    assert before.status == STATUS_OK, before.failures
    assert before.report["funding_clean_carry_status"] == (
        FUNDING_CLEAN_CARRY_STATUS_CLEAN
    )
    assert before.report["funding_clean_carry_decision"] == CLEAN_NET_OF_CARRY

    _drift_live_sol_funding_rate(db_path)

    after = _clean_report(db_path)
    assert after["decision"] != CLEAN_NET_OF_CARRY
    assert after["status"] != FUNDING_CLEAN_CARRY_STATUS_CLEAN
    assert set(after["reason_codes"]) & _DIGEST_MISMATCH_REASONS


# ---------------------------------------------------------------------------
# Planned behavior (xfail until bundle mode is implemented). Each test drives
# the verifier in an explicit source mode that does not exist yet, so it fails
# today; strict=True forces removal of the mark once implemented.
# ---------------------------------------------------------------------------


def _build_planned_bundle(db_path: Path, envelope: dict[str, Any]) -> Path:
    """Planned helper: capture an immutable, content-addressed source bundle
    from a committed snapshot envelope. Imported lazily because the module does
    not exist yet (its absence is the expected xfail cause)."""
    from quantbot.paper.funding_source_bundle import (  # noqa: PLC0415
        build_funding_source_bundle_v1,
        write_funding_source_bundle,
    )

    bundle = build_funding_source_bundle_v1(envelope)
    return write_funding_source_bundle(bundle, db_path.parent / "funding_source_bundles")


def _verify_bundle_mode(db_path: Path) -> dict[str, Any]:
    result = verify_database(db_path, source_mode=PLANNED_MODE_BUNDLE)
    return result.report["funding_clean_carry"]


@planned
def test_bundle_mode_survives_live_csv_drift(tmp_path: Path) -> None:
    db_path = _clean_setup(tmp_path)
    envelope = _committed_snapshot(db_path)
    _build_planned_bundle(db_path, envelope)

    # Live CSVs drift after the bundle is frozen (scheduled refresh analogue).
    _drift_live_sol_funding_rate(db_path)

    report = _verify_bundle_mode(db_path)

    # Bundle-mode validates the frozen bytes, so the drift is irrelevant.
    assert report["source_resolution_mode"] == PLANNED_MODE_BUNDLE
    assert report["status"] == FUNDING_CLEAN_CARRY_STATUS_CLEAN
    assert report["decision"] == CLEAN_NET_OF_CARRY


@planned
def test_missing_bundle_refuses_clean_in_bundle_mode(tmp_path: Path) -> None:
    db_path = _clean_setup(tmp_path)
    # No bundle captured, but bundle mode is requested with a recorded reference.
    report = _verify_bundle_mode(db_path)

    assert report["source_resolution_mode"] == PLANNED_MODE_BUNDLE
    assert report["decision"] != CLEAN_NET_OF_CARRY
    assert PLANNED_REASON_BUNDLE_MISSING in report["reason_codes"]


@planned
def test_corrupt_bundle_refuses_clean(tmp_path: Path) -> None:
    db_path = _clean_setup(tmp_path)
    envelope = _committed_snapshot(db_path)
    bundle_path = _build_planned_bundle(db_path, envelope)
    bundle_path.write_text("{ not valid bundle json", encoding="utf-8")

    report = _verify_bundle_mode(db_path)

    assert report["decision"] != CLEAN_NET_OF_CARRY
    assert PLANNED_REASON_BUNDLE_CORRUPT in report["reason_codes"]


@planned
def test_bundle_hash_mismatch_refuses_clean(tmp_path: Path) -> None:
    db_path = _clean_setup(tmp_path)
    envelope = _committed_snapshot(db_path)
    bundle_path = _build_planned_bundle(db_path, envelope)
    # Alter the bundle bytes so the recorded source_bundle_sha256 no longer
    # recomputes, while keeping it parseable JSON.
    text = bundle_path.read_text(encoding="utf-8")
    bundle_path.write_text(text.replace("0.0001", "0.0009", 1), encoding="utf-8")

    report = _verify_bundle_mode(db_path)

    assert report["decision"] != CLEAN_NET_OF_CARRY
    assert PLANNED_REASON_BUNDLE_HASH_MISMATCH in report["reason_codes"]


@planned
def test_incomplete_window_bundle_refuses_clean(tmp_path: Path) -> None:
    db_path = _clean_setup(tmp_path)
    # A bundle that covers less than the full-ledger funding window must refuse.
    from quantbot.paper.funding_source_bundle import (  # noqa: PLC0415
        build_funding_source_bundle_v1,
        write_funding_source_bundle,
    )

    envelope = _committed_snapshot(db_path)
    bundle = build_funding_source_bundle_v1(envelope)
    rows = bundle["bundle_payload"]["canonical_rows"]
    bundle["bundle_payload"]["canonical_rows"] = rows[:-1]
    write_funding_source_bundle(bundle, db_path.parent / "funding_source_bundles")

    report = _verify_bundle_mode(db_path)

    assert report["decision"] != CLEAN_NET_OF_CARRY
    assert PLANNED_REASON_BUNDLE_INCOMPLETE_WINDOW in report["reason_codes"]


@planned
def test_funding_resum_mismatch_over_bundle_refuses_clean(tmp_path: Path) -> None:
    import sqlite3  # noqa: PLC0415

    db_path = _clean_setup(tmp_path)
    envelope = _committed_snapshot(db_path)
    _build_planned_bundle(db_path, envelope)

    # Perturb the ledger funding total so the bundle re-sum disagrees.
    conn = sqlite3.connect(str(db_path))
    try:
        conn.execute(
            "UPDATE ledger_state SET funding_cum = funding_cum + 1.0 WHERE id = 1"
        )
        conn.commit()
    finally:
        conn.close()

    report = _verify_bundle_mode(db_path)

    assert report["decision"] != CLEAN_NET_OF_CARRY
    assert PLANNED_REASON_RESUM_MISMATCH in report["reason_codes"]


@planned
def test_live_current_mode_labels_resolution_and_still_detects_drift(
    tmp_path: Path,
) -> None:
    db_path = _clean_setup(tmp_path)
    _drift_live_sol_funding_rate(db_path)

    result = verify_database(db_path, source_mode=PLANNED_MODE_LIVE_CURRENT)
    report = result.report["funding_clean_carry"]

    assert report["source_resolution_mode"] == PLANNED_MODE_LIVE_CURRENT
    assert report["decision"] != CLEAN_NET_OF_CARRY
    assert report["status"] == FUNDING_CLEAN_CARRY_STATUS_REFUSED_DIGEST_MISMATCH
    assert set(report["reason_codes"]) & _DIGEST_MISMATCH_REASONS


@planned
def test_report_exposes_source_resolution_mode_and_source_identity(
    tmp_path: Path,
) -> None:
    db_path = _clean_setup(tmp_path)
    envelope = _committed_snapshot(db_path)
    bundle_path = _build_planned_bundle(db_path, envelope)

    bundle_result = verify_database(db_path, source_mode=PLANNED_MODE_BUNDLE)
    bundle_report = bundle_result.report["funding_clean_carry"]
    assert bundle_report["source_resolution_mode"] == PLANNED_MODE_BUNDLE
    # Bundle identity is recorded: the exact frozen bytes that were validated.
    assert bundle_report["bundle_path"] == str(bundle_path)
    assert bundle_report["source_bundle_sha256"]
    assert bundle_report["original_source_digests"]

    live_result = verify_database(db_path, source_mode=PLANNED_MODE_LIVE_CURRENT)
    live_report = live_result.report["funding_clean_carry"]
    assert live_report["source_resolution_mode"] == PLANNED_MODE_LIVE_CURRENT
    # Live mode records the live CSV paths + digests it actually validated.
    assert live_report["live_source_digests"]
