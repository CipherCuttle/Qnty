"""Test-only spec for future funding timestamp normalization.

FUNDING_TIMESTAMP_NORMALIZATION_SPEC_V1 pins the intended timestamp contract
before the production engine/verifier implementation changes:

* funding intervals remain open-closed: (window_start, window_end]
* source rows at window_end, window_end + 5 ms, and window_end + 9 ms back
  that endpoint after canonicalization
* rows outside the accepted after-endpoint tolerance, missing rows, and duplicate
  canonical endpoint rows cannot earn clean carry classification
* rows jittered after window_start must not be moved into the next window

This file is intentionally test-local. The passing tests use a reference helper;
the xfail tests document where the current public coverage path still needs the
shared normalization implementation.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

import pytest

from quantbot.paper.funding_coverage import check_funding_coverage_from_rows
from quantbot.paper.funding_status import COVERAGE_COMPLETE

SPEC_NAME = "FUNDING_TIMESTAMP_NORMALIZATION_SPEC_V1"
PENDING_NORMALIZATION_REASON = (
    "pending shared funding timestamp normalization implementation"
)

_SYMBOL = "SOLUSDT"
_WINDOW_START = "2026-06-14T16:00:00"
_WINDOW_END = "2026-06-15T00:00:00"
_AFTER_ENDPOINT_TOLERANCE_MS = 10


@dataclass(frozen=True)
class _SpecWindowResult:
    spec_name: str
    clean_net_of_carry_allowed: bool
    reason: str
    canonical_endpoint: datetime | None = None


def _parse_iso_utc(raw: str) -> datetime:
    dt = datetime.fromisoformat(raw)
    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def _ms_at(raw: str, *, offset_ms: int = 0) -> int:
    return int(_parse_iso_utc(raw).timestamp() * 1000) + offset_ms


def _dt_from_ms(ms: int) -> datetime:
    return datetime.fromtimestamp(ms / 1000.0, tz=timezone.utc)


def _spec_normalize_funding_timestamp_v1(
    source_funding_times_ms: list[int],
    *,
    window_start: str = _WINDOW_START,
    window_end: str = _WINDOW_END,
    tolerance_ms: int = _AFTER_ENDPOINT_TOLERANCE_MS,
) -> _SpecWindowResult:
    """Reference-only classifier for one funding window.

    The production implementation will live elsewhere. This helper exists only
    to make the intended test contract executable before that implementation PR.
    """
    ws = _parse_iso_utc(window_start)
    we = _parse_iso_utc(window_end)
    canonical_hits_for_window: list[datetime] = []
    hit_open_boundary = False

    for raw_ms in source_funding_times_ms:
        source_ts = _dt_from_ms(raw_ms)
        canonical_endpoint: datetime | None = None
        for endpoint in (ws, we):
            delta_ms = round((source_ts - endpoint).total_seconds() * 1000)
            if 0 <= delta_ms <= tolerance_ms:
                canonical_endpoint = endpoint
                break

        if canonical_endpoint is None:
            continue
        if canonical_endpoint == we:
            canonical_hits_for_window.append(canonical_endpoint)
        elif canonical_endpoint == ws:
            hit_open_boundary = True

    if len(canonical_hits_for_window) == 1:
        return _SpecWindowResult(SPEC_NAME, True, "accepted", we)
    if len(canonical_hits_for_window) > 1:
        return _SpecWindowResult(
            SPEC_NAME,
            False,
            "duplicate_canonical_endpoint",
            we,
        )
    if not source_funding_times_ms:
        return _SpecWindowResult(SPEC_NAME, False, "missing_source_row")
    if hit_open_boundary:
        return _SpecWindowResult(
            SPEC_NAME,
            False,
            "canonicalized_to_open_boundary",
            ws,
        )
    return _SpecWindowResult(SPEC_NAME, False, "outside_tolerance")


def _funding_row() -> dict:
    return {
        "funding_id": f"{_SYMBOL}|{_WINDOW_END}",
        "symbol": _SYMBOL,
        "bar_ts": _WINDOW_END,
        "window_start": _WINDOW_START,
        "window_end": _WINDOW_END,
        "rate_available": 1,
    }


def _write_source_csv(csv_dir: Path, funding_times_ms: list[int]) -> Path:
    csv_dir.mkdir(parents=True)
    csv_path = csv_dir / f"{_SYMBOL}_8h_funding.csv"
    lines = ["fundingTime,fundingRate,markPrice"]
    lines.extend(f"{ms},0.0001,150.0" for ms in funding_times_ms)
    csv_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return csv_dir


def _current_coverage_report(tmp_path: Path, funding_times_ms: list[int]):
    csv_dir = _write_source_csv(tmp_path / "csv", funding_times_ms)
    return check_funding_coverage_from_rows([_funding_row()], csv_dir)


# ---------------------------------------------------------------------------
# A. Passing spec/reference tests
# ---------------------------------------------------------------------------


def test_spec_exact_endpoint_is_accepted() -> None:
    result = _spec_normalize_funding_timestamp_v1([_ms_at(_WINDOW_END)])

    assert result.spec_name == SPEC_NAME
    assert result.clean_net_of_carry_allowed is True
    assert result.reason == "accepted"
    assert result.canonical_endpoint == _parse_iso_utc(_WINDOW_END)


def test_spec_accepts_5ms_after_endpoint() -> None:
    result = _spec_normalize_funding_timestamp_v1(
        [_ms_at(_WINDOW_END, offset_ms=5)]
    )

    assert result.clean_net_of_carry_allowed is True
    assert result.reason == "accepted"
    assert result.canonical_endpoint == _parse_iso_utc(_WINDOW_END)


def test_spec_accepts_9ms_after_endpoint() -> None:
    result = _spec_normalize_funding_timestamp_v1(
        [_ms_at(_WINDOW_END, offset_ms=9)]
    )

    assert result.clean_net_of_carry_allowed is True
    assert result.reason == "accepted"
    assert result.canonical_endpoint == _parse_iso_utc(_WINDOW_END)


def test_spec_rejects_11ms_after_endpoint() -> None:
    result = _spec_normalize_funding_timestamp_v1(
        [_ms_at(_WINDOW_END, offset_ms=11)]
    )

    assert result.clean_net_of_carry_allowed is False
    assert result.reason == "outside_tolerance"


def test_spec_does_not_move_inside_window_across_boundary() -> None:
    result = _spec_normalize_funding_timestamp_v1(
        [_ms_at(_WINDOW_START, offset_ms=5)]
    )

    assert result.clean_net_of_carry_allowed is False
    assert result.reason == "canonicalized_to_open_boundary"
    assert result.canonical_endpoint == _parse_iso_utc(_WINDOW_START)


def test_spec_missing_row_is_not_clean() -> None:
    result = _spec_normalize_funding_timestamp_v1([])

    assert result.clean_net_of_carry_allowed is False
    assert result.reason == "missing_source_row"


def test_spec_duplicate_canonical_endpoint_is_ambiguous() -> None:
    result = _spec_normalize_funding_timestamp_v1(
        [
            _ms_at(_WINDOW_END),
            _ms_at(_WINDOW_END, offset_ms=5),
        ]
    )

    assert result.clean_net_of_carry_allowed is False
    assert result.reason == "duplicate_canonical_endpoint"
    assert result.canonical_endpoint == _parse_iso_utc(_WINDOW_END)


# ---------------------------------------------------------------------------
# B. Current production xfail tests
# ---------------------------------------------------------------------------


@pytest.mark.xfail(strict=True, reason=PENDING_NORMALIZATION_REASON)
def test_current_funding_coverage_5ms_endpoint_jitter_xfail(
    tmp_path: Path,
) -> None:
    report = _current_coverage_report(
        tmp_path,
        [_ms_at(_WINDOW_END, offset_ms=5)],
    )

    assert report.overall_decision == COVERAGE_COMPLETE
    assert report.missing_windows == []


@pytest.mark.xfail(strict=True, reason=PENDING_NORMALIZATION_REASON)
def test_current_funding_coverage_9ms_endpoint_jitter_xfail(
    tmp_path: Path,
) -> None:
    report = _current_coverage_report(
        tmp_path,
        [_ms_at(_WINDOW_END, offset_ms=9)],
    )

    assert report.overall_decision == COVERAGE_COMPLETE
    assert report.missing_windows == []


@pytest.mark.xfail(strict=True, reason=PENDING_NORMALIZATION_REASON)
def test_current_funding_coverage_duplicate_canonical_endpoint_xfail(
    tmp_path: Path,
) -> None:
    report = _current_coverage_report(
        tmp_path,
        [
            _ms_at(_WINDOW_END),
            _ms_at(_WINDOW_END, offset_ms=5),
        ],
    )

    assert report.overall_decision != COVERAGE_COMPLETE
