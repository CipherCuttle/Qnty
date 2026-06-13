"""Determinism and closed-candle tests for the Package V2 observer."""

from __future__ import annotations

import hashlib
import math
import statistics
from datetime import datetime, timedelta, timezone

import pandas as pd
import pytest

import scripts.run_validation_v2 as validation
from quantbot.core.determinism import canonical_json_dumps
from quantbot.data.types import Bar
from quantbot.experiment.volnorm_portfolio import VolatilityTracker


INCIDENT_FROZEN_DIGEST = "2e9035dfa6a530f71c31b323847107c80a3e2d826e27fbe0c3ef7efcf4833ae0"
INCIDENT_CURRENT_DIGEST = "46640b58f3ee6f95c651f9f9daec757aa5d43a879652d96b19f38dde2e578bfc"
INCIDENT_FROZEN_ROW = {
    "active_symbols": ["ETHUSDT", "BTCUSDT", "SOLUSDT", "XRPUSDT", "BNBUSDT"],
    "bar_index": 5424,
    "heat_cap_triggered": False,
    "portfolio_heat": 0.04136014230186636,
    "timestamp": "2026-06-13T00:00:00",
    "weighted_return": 0.004596412265193691,
}
INCIDENT_CURRENT_ROW = {
    "active_symbols": ["ETHUSDT", "BTCUSDT", "SOLUSDT", "XRPUSDT", "BNBUSDT"],
    "bar_index": 5424,
    "heat_cap_triggered": False,
    "portfolio_heat": 0.04137793252232853,
    "timestamp": "2026-06-13T00:00:00",
    "weighted_return": 0.004596098316676865,
}
SYMBOLS = ["ETHUSDT", "BTCUSDT", "SOLUSDT", "XRPUSDT", "BNBUSDT"]


def _digest(row: dict) -> str:
    return hashlib.sha256(canonical_json_dumps(row).encode("utf-8")).hexdigest()


def _bars(count: int, start: datetime | None = None) -> dict[str, list[Bar]]:
    start = start or datetime(2025, 10, 1, tzinfo=timezone.utc)
    result: dict[str, list[Bar]] = {}
    for symbol_index, symbol in enumerate(SYMBOLS):
        price = 100.0 + symbol_index * 10
        rows = []
        for index in range(count):
            price *= math.exp(0.002 * math.sin((index + symbol_index) / 5) + 0.0002)
            timestamp = (start + timedelta(hours=8 * index)).strftime("%Y-%m-%dT%H:%M:%S")
            rows.append(Bar(timestamp, price, price, price, price, 1000.0))
        result[symbol] = rows
    return result


def _empty_funding() -> pd.DataFrame:
    return pd.DataFrame(columns=["symbol", "dt", "fundingRate", "abs_rate"])


def test_volatility_tracker_depends_only_on_final_bounded_window() -> None:
    final_window = [math.sin(index) / 100 for index in range(90)]
    short_history = VolatilityTracker(lookback=90)
    long_history = VolatilityTracker(lookback=90)

    for value in final_window:
        short_history.update(value)
    for value in [0.9, -0.8, 0.7, -0.6] + final_window:
        long_history.update(value)

    assert short_history._returns == long_history._returns
    assert short_history._mean == long_history._mean
    assert short_history._m2 == long_history._m2
    assert short_history.volatility == long_history.volatility
    assert short_history.volatility == pytest.approx(statistics.stdev(final_window))


def test_incident_digest_class_no_longer_changes_after_eviction() -> None:
    """Regression for the production 2e903... -> 46640... divergence."""
    final_window = [math.sin(index / 3) / 100 for index in range(90)]

    class LegacyVolatilityTracker:
        def __init__(self) -> None:
            self.returns: list[float] = []
            self.mean = 0.0
            self.m2 = 0.0

        def update(self, value: float) -> None:
            self.returns.append(value)
            if len(self.returns) > 90:
                self.returns.pop(0)
            n = len(self.returns)
            if n < 2:
                self.mean = sum(self.returns) / max(1, n)
                return
            delta = value - self.mean
            self.mean += delta / n
            self.m2 += delta * (value - self.mean)

        @property
        def volatility(self) -> float:
            return math.sqrt(self.m2 / (len(self.returns) - 1))

    fixed_trackers = []
    legacy_trackers = []
    for prefix in ([], [0.25]):
        tracker = VolatilityTracker(lookback=90)
        legacy = LegacyVolatilityTracker()
        for value in prefix + final_window:
            tracker.update(value)
            legacy.update(value)
        fixed_trackers.append(tracker)
        legacy_trackers.append(legacy)

    fixed_rows = [
        {
            "timestamp": "2026-06-13T00:00:00",
            "active_symbols": ["ETHUSDT", "BTCUSDT"],
            "portfolio_heat": tracker.volatility,
        }
        for tracker in fixed_trackers
    ]
    legacy_rows = [
        {
            "timestamp": "2026-06-13T00:00:00",
            "active_symbols": ["ETHUSDT", "BTCUSDT"],
            "portfolio_heat": tracker.volatility,
        }
        for tracker in legacy_trackers
    ]

    assert _digest(INCIDENT_FROZEN_ROW) == INCIDENT_FROZEN_DIGEST
    assert _digest(INCIDENT_CURRENT_ROW) == INCIDENT_CURRENT_DIGEST
    assert _digest(legacy_rows[0]) != _digest(legacy_rows[1])
    assert _digest(fixed_rows[0]) == _digest(fixed_rows[1])


@pytest.mark.parametrize(
    ("now", "latest_closed"),
    [
        ("2026-06-13T00:15:00+00:00", "2026-06-12T16:00:00"),
        ("2026-06-13T08:15:00+00:00", "2026-06-13T00:00:00"),
        ("2026-06-13T16:15:00+00:00", "2026-06-13T08:00:00"),
    ],
)
def test_filter_closed_bars_excludes_current_open_candle(now: str, latest_closed: str) -> None:
    start = datetime(2026, 6, 12, 16, tzinfo=timezone.utc)
    bars = _bars(4, start=start)

    filtered = validation.filter_closed_bars(bars, datetime.fromisoformat(now))

    assert filtered["BTCUSDT"][-1].timestamp == latest_closed


def test_overlapping_closed_observer_rows_are_byte_identical(monkeypatch) -> None:
    monkeypatch.setattr(validation, "WINDOW_SIZE", 50)
    bars = _bars(90)
    funding = _empty_funding()

    first_last = bars["BTCUSDT"][-2]
    second_last = bars["BTCUSDT"][-1]
    first_now = (
        datetime.fromisoformat(first_last.timestamp).replace(tzinfo=timezone.utc)
        + timedelta(hours=8, minutes=15)
    )
    second_now = (
        datetime.fromisoformat(second_last.timestamp).replace(tzinfo=timezone.utc)
        + timedelta(hours=8, minutes=15)
    )

    first = validation.run_observer_window(
        {symbol: rows[:-1] for symbol, rows in bars.items()},
        funding,
        {},
        now=first_now,
    )
    second = validation.run_observer_window(bars, funding, {}, now=second_now)

    first_by_ts = {row["timestamp"]: row for row in first["per_bar_obs"]}
    second_by_ts = {row["timestamp"]: row for row in second["per_bar_obs"]}
    overlap = sorted(set(first_by_ts) & set(second_by_ts))

    assert len(overlap) == 49
    assert [
        canonical_json_dumps(first_by_ts[timestamp])
        for timestamp in overlap
    ] == [
        canonical_json_dumps(second_by_ts[timestamp])
        for timestamp in overlap
    ]


def test_observer_window_publishes_closed_rows_only(monkeypatch) -> None:
    monkeypatch.setattr(validation, "WINDOW_SIZE", 50)
    bars = _bars(90)
    funding = _empty_funding()
    latest = bars["BTCUSDT"][-1]
    now = datetime.fromisoformat(latest.timestamp).replace(tzinfo=timezone.utc) + timedelta(minutes=15)

    metrics = validation.run_observer_window(bars, funding, {}, now=now)

    assert metrics["per_bar_obs"][-1]["timestamp"] == bars["BTCUSDT"][-2].timestamp
    assert all(row["timestamp"] != latest.timestamp for row in metrics["per_bar_obs"])
