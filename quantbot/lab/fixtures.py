"""Synthetic, deterministic fixture builders for the Fast Truth Lab.

All builders are pure and produce in-memory objects only — no disk, no /srv, no DB. They
mirror the observer/paper contracts (8h grid, naive-UTC timestamps, full per_bar_obs rows)
so the lab can drive both the production engine and the independent replay from identical
inputs.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any, Iterable

import pandas as pd

from quantbot.data.types import Bar
from quantbot.paper.config import build_config

BAR_FMT = "%Y-%m-%dT%H:%M:%S"
BAR_INTERVAL = timedelta(hours=8)


def grid(n: int, start: str = "2026-06-05T00:00:00") -> list[str]:
    """`n` consecutive on-grid 8h naive-UTC timestamps from `start` (inclusive)."""
    t0 = datetime.strptime(start, BAR_FMT).replace(tzinfo=timezone.utc)
    return [(t0 + i * BAR_INTERVAL).strftime(BAR_FMT) for i in range(n)]


def bars(prices: Iterable[tuple[float, float]], timestamps: list[str]) -> list[Bar]:
    """Build a bar list from (open, close) pairs aligned to `timestamps`."""
    out: list[Bar] = []
    for ts, (o, c) in zip(timestamps, prices):
        out.append(Bar(timestamp=ts, open=float(o), high=max(o, c), low=min(o, c),
                       close=float(c), volume=1.0))
    return out


def rising_bars(timestamps: list[str], start_price: float = 100.0,
                step: float = 10.0) -> list[Bar]:
    """A monotonically rising (open, close) series — deterministic, profitable-looking but
    used ONLY for arithmetic equivalence, never as an edge claim."""
    out: list[Bar] = []
    price = start_price
    for ts in timestamps:
        o = price
        c = price + step
        out.append(Bar(timestamp=ts, open=o, high=max(o, c), low=min(o, c), close=c,
                       volume=1.0))
        price = c
    return out


def obs_row(ts: str, active: Iterable[str] = (), bar_index: int = 0,
            **extra: Any) -> dict[str, Any]:
    """A full per_bar_obs row carrying the complete observer contract."""
    row = {
        "timestamp": ts,
        "bar_index": bar_index,
        "active_symbols": list(active),
        "portfolio_heat": 0.0,
        "heat_cap_triggered": False,
        "weighted_return": 0.0,
    }
    row.update(extra)
    return row


def obs_log(active_by_bar: list[Iterable[str]], timestamps: list[str]) -> list[dict[str, Any]]:
    """Per-bar observation rows from a list of active_symbols aligned to `timestamps`."""
    return [obs_row(ts, active, i) for i, (ts, active) in enumerate(zip(timestamps, active_by_bar))]


def funding_df(symbol: str, pairs: list[tuple[str, float]]):
    """A funding DataFrame in load_all_funding() shape from (iso_ts, rate) pairs."""
    return pd.DataFrame(
        [{"symbol": symbol, "dt": pd.Timestamp(ts, tz="UTC"), "fundingRate": float(rate),
          "abs_rate": abs(float(rate))} for ts, rate in pairs]
    )


def empty_funding_df():
    return pd.DataFrame(columns=["symbol", "dt", "fundingRate", "abs_rate"])


def config(forward_start_ts: str, **kwargs: Any) -> dict[str, Any]:
    """Canonical paper config (write-once contract) for driving run_engine/run_replay."""
    return build_config(forward_start_ts=forward_start_ts, **kwargs)


def round_trip_scenario(symbol: str = "AAA") -> dict[str, Any]:
    """A complete entry->hold->exit scenario with funding, ready for a cross-check.

    Returns a dict with config, per_bar_obs, bars_by_symbol, funding_df, initial_equity.
    """
    ts = grid(6)
    price_bars = rising_bars(ts)
    active = [[], [symbol], [symbol], [symbol], [], []]
    fund = funding_df(symbol, [(t, 0.0001) for t in ts])
    cfg = config(forward_start_ts=ts[0])
    return {
        "config": cfg,
        "per_bar_obs": obs_log(active, ts),
        "bars_by_symbol": {symbol: price_bars},
        "funding_df": fund,
        "initial_equity_usd": cfg["initial_equity_usd"],
        "timestamps": ts,
        "symbol": symbol,
    }


def to_payload(scenario: dict[str, Any]) -> dict[str, Any]:
    """Serialize a scenario into the JSON bundle the cross_check CLI consumes."""
    fund = scenario.get("funding_df")
    funding_rows = None
    if fund is not None and not getattr(fund, "empty", True):
        funding_rows = [
            {"symbol": str(r["symbol"]),
             "dt": pd.Timestamp(r["dt"]).strftime("%Y-%m-%dT%H:%M:%S"),
             "fundingRate": float(r["fundingRate"])}
            for _, r in fund.iterrows()
        ]
    return {
        "config": scenario["config"],
        "per_bar_obs": scenario["per_bar_obs"],
        "bars_by_symbol": {
            sym: [b.to_dict() for b in blist]
            for sym, blist in scenario["bars_by_symbol"].items()
        },
        "funding": funding_rows,
    }
