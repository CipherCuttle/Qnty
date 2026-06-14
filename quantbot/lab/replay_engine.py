"""Independent zero-dependency (numpy/pandas) re-derive of the paper witness.

This is the CROSS_CHECK / REPLAY lane's independent re-implementation of the
fixed-notional long/flat paper accounting. It deliberately does NOT import
``quantbot.paper.engine`` — it re-derives marks, unrealized PnL, fees, funding, exposure
and equity straight from ``per_bar_obs`` + OHLCV + funding so that a bug baked into the
production engine (and therefore into the DB the read-only verifier trusts) is exposed as
a disagreement rather than silently re-validated.

It is intentionally "boring": the same documented spec
(docs/paper_pnl_v1_schema.md sections 3/11), a separate code path, separate data
structures (pandas funding index, plain-dict bar book). Per the implementation-risk
literature, the independent engine must follow the SAME fill/cost/funding spec — a CLEAN
result means both implementations agree on the spec, a disagreement is a *measured
quantity* to be triaged (see cross_check.classify_disagreement), never auto-blamed on QNTY.

Spec re-derived here (must match the production contract exactly):
  * active_symbols at bar T = desired long set; entries/exits resolved against open book
  * fill at T+1 open (pessimistic); all-or-nothing deferral if any T+1 open missing
  * entry fill price = open * (1 + slip);   exit fill price = open * (1 - slip)
  * qty = notional / entry_fill_price (long-only, fixed-notional)
  * fee = fill_price * qty * fee_rate
  * funding accrued over the ACTUAL held interval (entry fill -> exit fill), summing every
    event in (start_exclusive, end_inclusive]; long pays when rate > 0
  * unrealized PnL marked at bar-T close; gross_exposure = sum(qty * close)
  * equity = initial + realized_gross - fees_cum - funding_cum + unrealized
"""

from __future__ import annotations

import bisect
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Any

import pandas as pd

from quantbot.data.types import Bar

_BAR_FMT = "%Y-%m-%dT%H:%M:%S"


# --------------------------------------------------------------------------- timestamps


def parse_instant(ts: str) -> datetime:
    """Independent naive/Z -> tz-aware UTC parse (mirrors the observer convention).

    Reimplemented here on purpose: the production ``parse_bar_utc`` is part of the witness
    under test (it was the just-fixed naive-vs-Z bug). A regression there must surface as a
    cross-check disagreement, so the replay lane parses timestamps with its own code.
    """
    if not isinstance(ts, str):
        raise TypeError(f"timestamp must be a str, got {type(ts).__name__}")
    parsed = datetime.fromisoformat(ts.replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def _interval_start(ts: str, interval_hours: int) -> str:
    dt = parse_instant(ts) - timedelta(hours=interval_hours)
    return dt.strftime(_BAR_FMT)


# --------------------------------------------------------------------------- price book


class _BarBook:
    """Per-symbol close + next-open lookups, built from plain dicts (independent path)."""

    def __init__(self, bars_by_symbol: dict[str, list[Bar]]):
        self._bars = bars_by_symbol
        self._idx: dict[str, dict[str, int]] = {
            sym: {b.timestamp: i for i, b in enumerate(bars)}
            for sym, bars in bars_by_symbol.items()
        }

    def close_at(self, symbol: str, ts: str) -> float | None:
        i = self._idx.get(symbol, {}).get(ts)
        if i is None:
            return None
        return self._bars[symbol][i].close

    def next_open(self, symbol: str, ts: str) -> tuple[str, float] | None:
        i = self._idx.get(symbol, {}).get(ts)
        if i is None:
            return None
        bars = self._bars[symbol]
        if i + 1 >= len(bars):
            return None
        nb = bars[i + 1]
        return nb.timestamp, nb.open


# ----------------------------------------------------------------------------- funding


def _funding_index(funding_df) -> dict[str, list[tuple[str, float]]]:
    """Per-symbol sorted (iso_ts, rate) list, built via pandas (independent of engine)."""
    index: dict[str, list[tuple[str, float]]] = {}
    if funding_df is None or getattr(funding_df, "empty", True):
        return index
    df = funding_df.copy()
    df["_iso"] = pd.to_datetime(df["dt"], utc=True).dt.strftime(_BAR_FMT)
    for symbol, grp in df.groupby("symbol"):
        rows = sorted(
            ((str(iso), float(rate)) for iso, rate in zip(grp["_iso"], grp["fundingRate"])),
            key=lambda x: x[0],
        )
        index[str(symbol)] = rows
    return index


def _funding_in_interval(
    index: dict[str, list[tuple[str, float]]],
    symbol: str,
    start_exclusive: str,
    end_inclusive: str,
) -> tuple[float, int, bool]:
    """Sum every funding event in (start_exclusive, end_inclusive]; (rate, n, available)."""
    series = index.get(symbol)
    if not series:
        return 0.0, 0, False
    keys = [k for k, _ in series]
    lo = bisect.bisect_right(keys, start_exclusive)
    hi = bisect.bisect_right(keys, end_inclusive)
    events = series[lo:hi]
    if not events:
        return 0.0, 0, False
    return sum(r for _, r in events), len(events), True


# ------------------------------------------------------------------------------- result


@dataclass
class ReplayResult:
    fills: list[dict[str, Any]] = field(default_factory=list)
    positions: list[dict[str, Any]] = field(default_factory=list)
    trades: list[dict[str, Any]] = field(default_factory=list)
    equity: list[dict[str, Any]] = field(default_factory=list)
    funding: list[dict[str, Any]] = field(default_factory=list)
    deferred_bar_ts: str | None = None


def run_replay(
    config: dict[str, Any],
    per_bar_obs: list[dict[str, Any]],
    bars_by_symbol: dict[str, list[Bar]],
    funding_df,
    initial_equity_usd: float | None = None,
    watermark_bar_ts: str = "",
) -> ReplayResult:
    """Re-derive the paper ledger independently. Same spec, separate implementation.

    Returns per-bar equity/positions and per-fill rows in the SAME shape/rounding as the
    production engine so cross_check can diff them row-by-row.
    """
    forward_start = config["forward_start_ts"]
    notional = float(config["notional_usd"])
    initial = float(initial_equity_usd if initial_equity_usd is not None
                    else config["initial_equity_usd"])
    fee_rate = float(config["fee_model"]["fee_bps"]) / 10_000.0
    slip = float(config["slippage_model"]["slippage_bps"]) / 10_000.0
    interval_hours = int(config.get("freshness", {}).get("bar_interval_hours", 8))

    book = _BarBook(bars_by_symbol)
    fidx = _funding_index(funding_df)

    forward_start_dt = parse_instant(forward_start)
    forward = sorted(
        (o for o in per_bar_obs if parse_instant(o["timestamp"]) >= forward_start_dt),
        key=lambda o: parse_instant(o["timestamp"]),
    )

    open_positions: dict[str, dict[str, Any]] = {}
    realized_gross = 0.0
    fees_cum = 0.0
    funding_cum = 0.0
    watermark = watermark_bar_ts or ""

    result = ReplayResult()

    for obs in forward:
        ts = obs["timestamp"]
        if ts <= watermark:
            continue

        desired = set(obs.get("active_symbols", []) or [])
        current = set(open_positions)
        entries = sorted(desired - current)
        exits = sorted(current - desired)

        # All-or-nothing T+1 open resolution; defer the whole bar if any is missing.
        nxt: dict[str, tuple[str, float]] = {}
        deferred = False
        for sym in entries + exits:
            nb = book.next_open(sym, ts)
            if nb is None:
                deferred = True
                break
            nxt[sym] = nb
        if deferred:
            result.deferred_bar_ts = ts
            break

        # --- funding on the held book, then exit-tail stub, BEFORE the equity snapshot ---
        window_start = _interval_start(ts, interval_hours)
        for sym in sorted(open_positions):
            pos = open_positions[sym]
            pos["hold_bars"] += 1
            close_ts = book.close_at(sym, ts)
            mark = close_ts if close_ts is not None else pos["entry_price"]
            notional_at = pos["qty"] * mark
            eff_start = max(window_start, pos["entry_fill_ts"])
            if eff_start >= ts:
                continue
            rate, n_ev, avail = _funding_in_interval(fidx, sym, eff_start, ts)
            amount = notional_at * rate if avail else 0.0
            pos["funding_accrued"] += amount
            funding_cum += amount
            result.funding.append(
                {
                    "funding_id": f"{sym}|{ts}",
                    "symbol": sym,
                    "bar_ts": ts,
                    "window_start": eff_start,
                    "window_end": ts,
                    "notional_usd": round(notional_at, 8),
                    "funding_rate": round(rate, 12),
                    "funding_events": n_ev,
                    "rate_available": avail,
                    "funding_amount": round(amount, 8),
                }
            )

        for sym in exits:
            pos = open_positions[sym]
            next_ts, _ = nxt[sym]
            stub_close = book.close_at(sym, next_ts)
            stub_mark = stub_close if stub_close is not None else pos["entry_price"]
            stub_notional = pos["qty"] * stub_mark
            s_rate, s_ev, s_avail = _funding_in_interval(fidx, sym, ts, next_ts)
            s_amount = stub_notional * s_rate if s_avail else 0.0
            pos["funding_accrued"] += s_amount
            funding_cum += s_amount
            result.funding.append(
                {
                    "funding_id": f"{sym}|{ts}|exit",
                    "symbol": sym,
                    "bar_ts": ts,
                    "window_start": ts,
                    "window_end": next_ts,
                    "notional_usd": round(stub_notional, 8),
                    "funding_rate": round(s_rate, 12),
                    "funding_events": s_ev,
                    "rate_available": s_avail,
                    "funding_amount": round(s_amount, 8),
                }
            )

        # --- marks / exposure / equity on the PRE-FILL book ---
        unreal = 0.0
        gross_exposure = 0.0
        for sym, pos in open_positions.items():
            close_ts = book.close_at(sym, ts)
            if close_ts is None:
                continue
            unreal += (close_ts - pos["entry_price"]) * pos["qty"]
            gross_exposure += pos["qty"] * close_ts

        equity = initial + realized_gross - fees_cum - funding_cum + unreal

        result.equity.append(
            {
                "bar_ts": ts,
                "realized_gross_pnl": round(realized_gross, 8),
                "unrealized_pnl": round(unreal, 8),
                "funding_cum": round(funding_cum, 8),
                "fees_cum": round(fees_cum, 8),
                "equity": round(equity, 8),
                "num_open": len(open_positions),
            }
        )
        result.positions.append(
            {
                "bar_ts": ts,
                "open_symbols": sorted(open_positions),
                "num_open": len(open_positions),
                "gross_exposure_usd": round(gross_exposure, 8),
            }
        )

        # --- fills: exits first (free the book), then entries ---
        for sym in exits:
            next_ts, open_price = nxt[sym]
            fill_price = open_price * (1.0 - slip)
            pos = open_positions.pop(sym)
            qty = pos["qty"]
            fee = fill_price * qty * fee_rate
            fees_cum += fee
            result.fills.append(
                {
                    "signal_bar_ts": ts,
                    "fill_ts": next_ts,
                    "symbol": sym,
                    "side": "SELL",
                    "kind": "exit",
                    "qty": round(qty, 10),
                    "open_price": round(open_price, 8),
                    "fill_price": round(fill_price, 8),
                    "fee": round(fee, 8),
                }
            )
            gross = (fill_price - pos["entry_price"]) * qty
            realized_gross += gross
            result.trades.append(
                {
                    "symbol": sym,
                    "entry_bar_ts": pos["entry_bar_ts"],
                    "exit_bar_ts": ts,
                    "qty": round(qty, 10),
                    "entry_price": round(pos["entry_price"], 8),
                    "exit_price": round(fill_price, 8),
                    "gross_pnl": round(gross, 8),
                    "fees": round(pos["entry_fee"] + fee, 8),
                    "funding": round(pos["funding_accrued"], 8),
                    "net_pnl": round(gross - (pos["entry_fee"] + fee) - pos["funding_accrued"], 8),
                    "hold_bars": pos["hold_bars"],
                }
            )

        for sym in entries:
            next_ts, open_price = nxt[sym]
            fill_price = open_price * (1.0 + slip)
            qty = notional / fill_price
            fee = fill_price * qty * fee_rate
            fees_cum += fee
            result.fills.append(
                {
                    "signal_bar_ts": ts,
                    "fill_ts": next_ts,
                    "symbol": sym,
                    "side": "BUY",
                    "kind": "entry",
                    "qty": round(qty, 10),
                    "open_price": round(open_price, 8),
                    "fill_price": round(fill_price, 8),
                    "fee": round(fee, 8),
                }
            )
            open_positions[sym] = {
                "entry_price": fill_price,
                "qty": qty,
                "entry_bar_ts": ts,
                "entry_fill_ts": next_ts,
                "funding_accrued": 0.0,
                "entry_fee": fee,
                "hold_bars": 0,
            }

        watermark = ts

    return result
