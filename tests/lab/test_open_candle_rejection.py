"""T2 (ADVERSARIAL) — the not-yet-closed (open) candle must never be decided on.

An 8h candle is "closed" only once its full interval has elapsed (`bar_open + 8h <= now`).
The still-open candle at `now-ε` must:
  1. be excluded by `filter_closed_bars`;
  2. never appear in `run_observer_window` output; and
  3. never be consumed as a DECISION bar by any lab/paper flow (it may only ever serve as
     a T+1 fill price for an earlier, already-closed decision bar).

A failure = the witness acts on a candle whose bar is not yet real = look-ahead. STOP.

Diagnostic lane: ADVERSARIAL. No edge claim.
"""

from __future__ import annotations

import math
from datetime import datetime, timedelta, timezone

import pandas as pd
import pytest

import scripts.run_validation_v2 as validation
from quantbot.data.types import Bar
from quantbot.lab.replay_engine import run_replay
from quantbot.paper.config import build_config

SYMBOLS = ["ETHUSDT", "BTCUSDT", "SOLUSDT", "XRPUSDT", "BNBUSDT"]
BAR_INTERVAL = timedelta(hours=8)


def _bars(count: int, start: datetime) -> dict[str, list[Bar]]:
    out: dict[str, list[Bar]] = {}
    for s_idx, symbol in enumerate(SYMBOLS):
        price = 100.0 + s_idx * 10
        rows = []
        for i in range(count):
            price *= math.exp(0.002 * math.sin((i + s_idx) / 5) + 0.0002)
            ts = (start + timedelta(hours=8 * i)).strftime("%Y-%m-%dT%H:%M:%S")
            rows.append(Bar(ts, price, price * 1.001, price * 0.999, price, 1000.0))
        out[symbol] = rows
    return out


def _empty_funding():
    return pd.DataFrame(columns=["symbol", "dt", "fundingRate", "abs_rate"])


@pytest.mark.parametrize("eps_minutes", [1, 15, 60, 479])
def test_filter_closed_bars_excludes_the_open_candle(eps_minutes: int) -> None:
    start = datetime(2026, 6, 1, tzinfo=timezone.utc)
    bars = _bars(40, start)
    open_bar_open = datetime.fromisoformat(bars["BTCUSDT"][-1].timestamp).replace(
        tzinfo=timezone.utc
    )
    # now is strictly inside the last candle's interval -> that candle is still OPEN.
    now = open_bar_open + timedelta(minutes=eps_minutes)
    assert now < open_bar_open + BAR_INTERVAL  # sanity: candle not yet closed

    filtered = validation.filter_closed_bars(bars, now)
    open_ts = bars["BTCUSDT"][-1].timestamp
    for symbol in SYMBOLS:
        assert all(b.timestamp != open_ts for b in filtered[symbol]), (
            f"{symbol}: open candle {open_ts} leaked through filter_closed_bars"
        )
        # The newest surviving bar is the prior (closed) candle.
        assert filtered[symbol][-1].timestamp == bars[symbol][-2].timestamp


def test_open_candle_exactly_at_boundary_is_still_open() -> None:
    """`bar_open + 8h == now` is the close instant: closed iff `+8h <= now` (inclusive)."""
    start = datetime(2026, 6, 1, tzinfo=timezone.utc)
    bars = _bars(10, start)
    last_open = datetime.fromisoformat(bars["BTCUSDT"][-1].timestamp).replace(
        tzinfo=timezone.utc
    )
    just_before = last_open + BAR_INTERVAL - timedelta(seconds=1)
    exactly_at = last_open + BAR_INTERVAL

    open_ts = bars["BTCUSDT"][-1].timestamp
    before = validation.filter_closed_bars(bars, just_before)
    at = validation.filter_closed_bars(bars, exactly_at)
    assert all(b.timestamp != open_ts for b in before["BTCUSDT"])  # 1s before close: open
    assert at["BTCUSDT"][-1].timestamp == open_ts  # exactly at close: now closed


def test_observer_window_never_publishes_the_open_candle(monkeypatch) -> None:
    monkeypatch.setattr(validation, "WINDOW_SIZE", 50)
    start = datetime(2026, 6, 1, tzinfo=timezone.utc)
    bars = _bars(90, start)
    open_ts = bars["BTCUSDT"][-1].timestamp
    now = datetime.fromisoformat(open_ts).replace(tzinfo=timezone.utc) + timedelta(minutes=15)

    metrics = validation.run_observer_window(bars, _empty_funding(), {}, now=now)

    published = [r["timestamp"] for r in metrics["per_bar_obs"]]
    assert open_ts not in published
    assert metrics["per_bar_obs"][-1]["timestamp"] == bars["BTCUSDT"][-2].timestamp


def test_no_lab_paper_flow_decides_on_an_open_candle(monkeypatch) -> None:
    """End-to-end: observer publishes closed-only obs; the replay decides only on those.

    The open candle's price still exists in `bars_by_symbol` (it can legitimately be a T+1
    fill source), but its timestamp must never be a decision bar (equity bar_ts) nor a
    signal_bar_ts in any fill.
    """
    monkeypatch.setattr(validation, "WINDOW_SIZE", 50)
    start = datetime(2026, 6, 1, tzinfo=timezone.utc)
    bars = _bars(90, start)
    open_ts = bars["BTCUSDT"][-1].timestamp
    now = datetime.fromisoformat(open_ts).replace(tzinfo=timezone.utc) + timedelta(minutes=15)

    metrics = validation.run_observer_window(bars, _empty_funding(), {}, now=now)
    per_bar_obs = metrics["per_bar_obs"]
    first_ts = per_bar_obs[0]["timestamp"]

    cfg = build_config(forward_start_ts=first_ts)
    result = run_replay(cfg, per_bar_obs, bars, None)

    decided = {e["bar_ts"] for e in result.equity}
    signalled = {f["signal_bar_ts"] for f in result.fills}
    assert open_ts not in decided, "replay decided on a still-open candle"
    assert open_ts not in signalled, "replay signalled on a still-open candle"
