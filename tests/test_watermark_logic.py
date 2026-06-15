"""8h-boundary / grace-window logic for the watermark watchdog.

Covers the four cases from the PR brief: fresh-boundary (within grace), mid-cycle (outside
grace), stale (observed behind expected), and the exact-grace-boundary edge that pins the
``>= grace`` rule.
"""

from __future__ import annotations

from datetime import datetime, timezone

import pytest

from quantbot.sidecars.time_bars import (
    evaluate_watchdog,
    expected_min_watermark,
    latest_boundary,
    previous_boundary,
)


def _utc(s: str) -> datetime:
    return datetime.fromisoformat(s).replace(tzinfo=timezone.utc)


@pytest.mark.parametrize(
    ("now", "expected_latest"),
    [
        ("2026-06-15T00:00:00", "2026-06-15T00:00:00"),
        ("2026-06-15T07:59:59", "2026-06-15T00:00:00"),
        ("2026-06-15T08:00:00", "2026-06-15T08:00:00"),
        ("2026-06-15T15:59:59", "2026-06-15T08:00:00"),
        ("2026-06-15T16:00:00", "2026-06-15T16:00:00"),
        ("2026-06-15T23:59:59", "2026-06-15T16:00:00"),
    ],
)
def test_latest_boundary_floors_to_8h_grid(now: str, expected_latest: str) -> None:
    assert latest_boundary(_utc(now)) == _utc(expected_latest)


def test_previous_boundary_is_one_interval_back() -> None:
    assert previous_boundary(_utc("2026-06-15T08:30:00")) == _utc("2026-06-15T00:00:00")


def test_fresh_boundary_within_grace_expects_previous_boundary() -> None:
    # 30 min after the 08:00 boundary, grace 60 -> the 08:00 run may not have committed yet,
    # so only the previous (00:00) bar is required.
    now = _utc("2026-06-15T08:30:00")
    assert expected_min_watermark(now, grace_minutes=60) == _utc("2026-06-15T00:00:00")


def test_mid_cycle_outside_grace_expects_latest_boundary() -> None:
    # 4h into the cycle, well past grace -> the 08:00 bar must be committed.
    now = _utc("2026-06-15T12:00:00")
    assert expected_min_watermark(now, grace_minutes=60) == _utc("2026-06-15T08:00:00")


def test_exact_grace_boundary_is_outside_grace() -> None:
    # now - latest == grace exactly -> NOT within grace (strict <), so expect the latest boundary.
    now = _utc("2026-06-15T09:00:00")  # exactly 60 min after 08:00
    assert expected_min_watermark(now, grace_minutes=60) == _utc("2026-06-15T08:00:00")


@pytest.mark.parametrize(
    ("now", "observed", "grace", "status"),
    [
        # Fresh boundary, watermark at previous boundary -> OK.
        ("2026-06-15T08:30:00", "2026-06-15T00:00:00", 60, "OK"),
        # Fresh boundary, watermark already at the new boundary -> OK (ahead of minimum).
        ("2026-06-15T08:30:00", "2026-06-15T08:00:00", 60, "OK"),
        # Mid-cycle, watermark caught up to latest boundary -> OK.
        ("2026-06-15T12:00:00", "2026-06-15T08:00:00", 60, "OK"),
        # Mid-cycle, watermark stuck a full cycle behind -> STALE.
        ("2026-06-15T12:00:00", "2026-06-15T00:00:00", 60, "STALE"),
        # Exact grace boundary, watermark only at previous boundary -> STALE (latest required).
        ("2026-06-15T09:00:00", "2026-06-15T00:00:00", 60, "STALE"),
        # Missing watermark -> STALE.
        ("2026-06-15T12:00:00", None, 60, "STALE"),
    ],
)
def test_evaluate_watchdog_status(now: str, observed, grace: int, status: str) -> None:
    result, detail = evaluate_watchdog(observed, _utc(now), grace_minutes=grace)
    assert result == status
    # Detail always carries the boundary context used for the verdict.
    assert detail["grace_minutes"] == grace
    assert detail["expected_min_watermark"] is not None
    assert detail["latest_boundary"] is not None


def test_evaluate_watchdog_accepts_trailing_z_watermark() -> None:
    status, detail = evaluate_watchdog(
        "2026-06-15T08:00:00Z", _utc("2026-06-15T12:00:00"), grace_minutes=60
    )
    assert status == "OK"
    assert detail["observed_watermark"] == "2026-06-15T08:00:00Z"
