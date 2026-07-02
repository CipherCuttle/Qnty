"""Spec for shared funding timestamp normalization.

FUNDING_TIMESTAMP_NORMALIZATION_SPEC_V2 pins the intended timestamp contract
implemented by the production coverage/verifier path:

* funding intervals remain open-closed: (window_start, window_end]
* source rows in the same UTC second as window_end canonicalize back to that
  endpoint
* rows outside the same-second endpoint contract, missing rows, and duplicate
  canonical endpoint rows cannot earn clean carry classification
* rows jittered after window_start must not be moved into the next window

The helper tests pin the shared rule; the coverage tests prove the public
``check_funding_coverage_from_rows`` path uses it.
"""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

import pytest

from quantbot.paper.funding_coverage import check_funding_coverage_from_rows
from quantbot.paper.funding_time import (
    ENDPOINT_SAME_SECOND_TOLERANCE_MS,
    FUNDING_TIMESTAMP_NORMALIZATION_SPEC_V2,
    classify_funding_timestamps_for_window,
)
from quantbot.paper.funding_status import COVERAGE_COMPLETE

SPEC_NAME = FUNDING_TIMESTAMP_NORMALIZATION_SPEC_V2

_SYMBOL = "SOLUSDT"
_WINDOW_START = "2026-06-14T16:00:00"
_WINDOW_END = "2026-06-15T00:00:00"
_ENDPOINT_SAME_SECOND_TOLERANCE_MS = ENDPOINT_SAME_SECOND_TOLERANCE_MS


def _parse_iso_utc(raw: str) -> datetime:
    dt = datetime.fromisoformat(raw)
    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def _ms_at(raw: str, *, offset_ms: int = 0) -> int:
    return int(_parse_iso_utc(raw).timestamp() * 1000) + offset_ms


def _dt_from_ms(ms: int) -> datetime:
    return datetime.fromtimestamp(ms / 1000.0, tz=timezone.utc)


def _spec_normalize_funding_timestamp_v2(
    source_funding_times_ms: list[int],
    *,
    window_start: str = _WINDOW_START,
    window_end: str = _WINDOW_END,
):
    return classify_funding_timestamps_for_window(
        [_dt_from_ms(ms) for ms in source_funding_times_ms],
        window_start=_parse_iso_utc(window_start),
        window_end=_parse_iso_utc(window_end),
    )


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
    result = _spec_normalize_funding_timestamp_v2([_ms_at(_WINDOW_END)])

    assert result.spec_name == SPEC_NAME
    assert result.clean_net_of_carry_allowed is True
    assert result.reason == "accepted"
    assert result.canonical_endpoint == _parse_iso_utc(_WINDOW_END)


@pytest.mark.parametrize(
    "offset_ms",
    [5, 9, 28, _ENDPOINT_SAME_SECOND_TOLERANCE_MS],
)
def test_spec_accepts_same_second_endpoint_offsets(offset_ms: int) -> None:
    result = _spec_normalize_funding_timestamp_v2(
        [_ms_at(_WINDOW_END, offset_ms=offset_ms)]
    )

    assert result.clean_net_of_carry_allowed is True
    assert result.reason == "accepted"
    assert result.canonical_endpoint == _parse_iso_utc(_WINDOW_END)


@pytest.mark.parametrize("offset_ms", [1000, 1001])
def test_spec_rejects_next_second_endpoint_offsets(offset_ms: int) -> None:
    result = _spec_normalize_funding_timestamp_v2(
        [_ms_at(_WINDOW_END, offset_ms=offset_ms)]
    )

    assert result.clean_net_of_carry_allowed is False
    assert result.reason == "outside_tolerance"


def test_spec_does_not_move_inside_window_across_boundary() -> None:
    result = _spec_normalize_funding_timestamp_v2(
        [_ms_at(_WINDOW_START, offset_ms=5)]
    )

    assert result.clean_net_of_carry_allowed is False
    assert result.reason == "canonicalized_to_open_boundary"
    assert result.canonical_endpoint == _parse_iso_utc(_WINDOW_START)


def test_spec_missing_row_is_not_clean() -> None:
    result = _spec_normalize_funding_timestamp_v2([])

    assert result.clean_net_of_carry_allowed is False
    assert result.reason == "missing_source_row"


def test_spec_duplicate_canonical_endpoint_is_ambiguous() -> None:
    result = _spec_normalize_funding_timestamp_v2(
        [
            _ms_at(_WINDOW_END),
            _ms_at(_WINDOW_END, offset_ms=999),
        ]
    )

    assert result.clean_net_of_carry_allowed is False
    assert result.reason == "duplicate_canonical_endpoint"
    assert result.canonical_endpoint == _parse_iso_utc(_WINDOW_END)


# ---------------------------------------------------------------------------
# B. Current production coverage tests
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("offset_ms", [0, 5, 9, 28, 999])
def test_current_funding_coverage_accepts_same_second_endpoint_offsets(
    tmp_path: Path,
    offset_ms: int,
) -> None:
    report = _current_coverage_report(
        tmp_path,
        [_ms_at(_WINDOW_END, offset_ms=offset_ms)],
    )

    assert report.overall_decision == COVERAGE_COMPLETE
    assert report.missing_windows == []


@pytest.mark.parametrize("offset_ms", [1000, 1001])
def test_current_funding_coverage_rejects_next_second_endpoint_offsets(
    tmp_path: Path,
    offset_ms: int,
) -> None:
    report = _current_coverage_report(
        tmp_path,
        [_ms_at(_WINDOW_END, offset_ms=offset_ms)],
    )

    assert report.overall_decision != COVERAGE_COMPLETE
    assert report.missing_windows
    assert report.missing_windows[0].source_issue == "outside_tolerance"


def test_current_funding_coverage_rejects_open_boundary_jitter(
    tmp_path: Path,
) -> None:
    report = _current_coverage_report(
        tmp_path,
        [_ms_at(_WINDOW_START, offset_ms=5)],
    )

    assert report.overall_decision != COVERAGE_COMPLETE
    assert report.missing_windows
    assert report.missing_windows[0].source_issue == "canonicalized_to_open_boundary"


def test_current_funding_coverage_rejects_duplicate_canonical_endpoint(
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
    assert report.missing_windows
    assert report.missing_windows[0].source_issue == "duplicate_canonical_endpoint"
