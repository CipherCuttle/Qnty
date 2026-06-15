"""8h-boundary / processing-lag / grace-window logic for the watermark watchdog.

Covers QNTY's intentional one-cycle processing lag, the extra tolerance within grace, stale
watermarks, and the exact-grace-boundary edge that pins the ``>= grace`` rule.
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


def test_within_grace_expects_two_cycles_behind_latest_boundary() -> None:
    # One intentional lag bar plus one grace bar.
    now = _utc("2026-06-15T08:30:00")
    assert expected_min_watermark(now, grace_minutes=60) == _utc("2026-06-14T16:00:00")


def test_outside_grace_expects_one_cycle_behind_latest_boundary() -> None:
    # Outside grace, only the intentional one-bar processing lag remains.
    now = _utc("2026-06-15T12:00:00")
    assert expected_min_watermark(now, grace_minutes=60) == _utc("2026-06-15T00:00:00")


def test_exact_grace_boundary_is_outside_grace() -> None:
    # now - latest == grace exactly -> only the intentional one-bar lag applies.
    now = _utc("2026-06-15T09:00:00")  # exactly 60 min after 08:00
    assert expected_min_watermark(now, grace_minutes=60) == _utc("2026-06-15T00:00:00")


def test_deployed_receipt_watermark_is_ok_with_one_cycle_lag() -> None:
    status, detail = evaluate_watchdog(
        "2026-06-15T08:00:00Z", _utc("2026-06-15T20:08:19"), grace_minutes=60
    )
    assert status == "OK"
    assert detail["expected_min_watermark"] == "2026-06-15T08:00:00Z"
    assert detail["processing_lag_bars"] == 1


def test_deployed_receipt_previous_watermark_is_stale() -> None:
    status, detail = evaluate_watchdog(
        "2026-06-15T00:00:00Z", _utc("2026-06-15T20:08:19"), grace_minutes=60
    )
    assert status == "STALE"
    assert detail["expected_min_watermark"] == "2026-06-15T08:00:00Z"


@pytest.mark.parametrize(
    ("now", "observed", "grace", "status"),
    [
        # Within grace, watermark two boundaries behind -> OK.
        ("2026-06-15T08:30:00", "2026-06-14T16:00:00", 60, "OK"),
        # Within grace, watermark at previous boundary -> OK (ahead of minimum).
        ("2026-06-15T08:30:00", "2026-06-15T00:00:00", 60, "OK"),
        # Outside grace, intentional one-cycle lag -> OK.
        ("2026-06-15T12:00:00", "2026-06-15T00:00:00", 60, "OK"),
        # Outside grace, two cycles behind -> STALE.
        ("2026-06-15T12:00:00", "2026-06-14T16:00:00", 60, "STALE"),
        # Exact grace boundary uses only the intentional one-cycle lag.
        ("2026-06-15T09:00:00", "2026-06-14T16:00:00", 60, "STALE"),
        # Missing watermark -> STALE.
        ("2026-06-15T12:00:00", None, 60, "STALE"),
    ],
)
def test_evaluate_watchdog_status(now: str, observed, grace: int, status: str) -> None:
    result, detail = evaluate_watchdog(observed, _utc(now), grace_minutes=grace)
    assert result == status
    # Detail always carries the boundary context used for the verdict.
    assert detail["grace_minutes"] == grace
    assert detail["processing_lag_bars"] == 1
    assert detail["expected_min_watermark"] is not None
    assert detail["latest_boundary"] is not None


def test_evaluate_watchdog_accepts_trailing_z_watermark() -> None:
    status, detail = evaluate_watchdog(
        "2026-06-15T00:00:00Z", _utc("2026-06-15T12:00:00"), grace_minutes=60
    )
    assert status == "OK"
    assert detail["observed_watermark"] == "2026-06-15T00:00:00Z"
