"""Deterministic paper accounting engine (paper_pnl_v1).

Consumes forward observer signals (observation_log.json -> per_bar_obs) and produces
fills, positions, closed trades, equity, and funding cash flows under a
next_bar_open_pessimistic fill model. Long-only, fixed-notional.

See docs/paper_pnl_v1_schema.md for the full contract. Timing/off-by-one and the
equity definition are pinned in section 3.
"""

from __future__ import annotations

import bisect
import hashlib
from dataclasses import dataclass, field
from typing import Any

from quantbot.data.types import Bar

# ----------------------------------------------------------------------------- ids


def fill_id(symbol: str, signal_bar_ts: str, side: str, kind: str) -> str:
    raw = f"{symbol}|{signal_bar_ts}|{side}|{kind}"
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:16]


# --------------------------------------------------------------------------- price


@dataclass
class PriceBook:
    """Per-symbol timestamp -> index, for O(1) close + next-open lookups."""

    bars_by_symbol: dict[str, list[Bar]]
    _index: dict[str, dict[str, int]] = field(default_factory=dict)

    def __post_init__(self) -> None:
        for sym, bars in self.bars_by_symbol.items():
            self._index[sym] = {b.timestamp: i for i, b in enumerate(bars)}

    def close_at(self, symbol: str, ts: str) -> float | None:
        i = self._index.get(symbol, {}).get(ts)
        if i is None:
            return None
        return self.bars_by_symbol[symbol][i].close

    def next_bar(self, symbol: str, ts: str) -> tuple[str, float] | None:
        """Return (next_ts, next_open) for the bar after `ts`, or None if unavailable."""
        i = self._index.get(symbol, {}).get(ts)
        if i is None:
            return None
        bars = self.bars_by_symbol[symbol]
        if i + 1 >= len(bars):
            return None
        nb = bars[i + 1]
        return nb.timestamp, nb.open


# ------------------------------------------------------------------------- funding


def build_funding_index(funding_df) -> dict[str, list[tuple[str, float]]]:
    """Per-symbol sorted list of (iso_ts, rate) from load_all_funding() output.

    iso_ts is naive-UTC "%Y-%m-%dT%H:%M:%S" to match OHLCV bar timestamps.
    """
    index: dict[str, list[tuple[str, float]]] = {}
    if funding_df is None or getattr(funding_df, "empty", True):
        return index
    for _, row in funding_df.iterrows():
        dt = row["dt"]
        iso = dt.strftime("%Y-%m-%dT%H:%M:%S")
        index.setdefault(str(row["symbol"]), []).append((iso, float(row["fundingRate"])))
    for sym in index:
        index[sym].sort(key=lambda x: x[0])
    return index


def funding_at(
    index: dict[str, list[tuple[str, float]]], symbol: str, ts: str
) -> tuple[float, bool]:
    """Most recent funding rate at or before ts. Returns (rate, rate_available).

    rate_available=False means no funding data exists for this symbol up to ts; the
    rate is reported as 0.0 but the flag makes the gap explicit (never silently zeroed).
    """
    series = index.get(symbol)
    if not series:
        return 0.0, False
    keys = [k for k, _ in series]
    pos = bisect.bisect_right(keys, ts) - 1
    if pos < 0:
        return 0.0, False
    return series[pos][1], True


# --------------------------------------------------------------------------- state


def new_state(initial_equity_usd: float) -> dict[str, Any]:
    return {
        "watermark_bar_ts": "",
        "open_positions": {},
        "accumulators": {"realized_gross": 0.0, "fees_cum": 0.0, "funding_cum": 0.0},
        "peak_equity": float(initial_equity_usd),
        "bars_elapsed": 0,
    }


@dataclass
class EngineResult:
    fills: list[dict[str, Any]] = field(default_factory=list)
    positions: list[dict[str, Any]] = field(default_factory=list)
    trades: list[dict[str, Any]] = field(default_factory=list)
    equity: list[dict[str, Any]] = field(default_factory=list)
    funding: list[dict[str, Any]] = field(default_factory=list)
    state: dict[str, Any] = field(default_factory=dict)
    deferred_bar_ts: str | None = None  # first bar whose T+1 open was unavailable


def run_engine(
    config: dict[str, Any],
    per_bar_obs: list[dict[str, Any]],
    bars_by_symbol: dict[str, list[Bar]],
    funding_df,
    state: dict[str, Any],
) -> EngineResult:
    """Process forward observation bars beyond the watermark. Append-only semantics.

    Returns NEW rows produced this run plus the updated state. The caller persists them
    idempotently (ids dedupe any overlap).
    """
    forward_start_ts = config["forward_start_ts"]
    notional = float(config["notional_usd"])
    initial_equity = float(config["initial_equity_usd"])
    fee_rate = float(config["fee_model"]["fee_bps"]) / 10_000.0
    slip = float(config["slippage_model"]["slippage_bps"]) / 10_000.0

    prices = PriceBook(bars_by_symbol)
    funding_index = build_funding_index(funding_df)

    acc = state["accumulators"]
    open_positions: dict[str, dict[str, Any]] = state["open_positions"]
    watermark = state.get("watermark_bar_ts", "") or ""
    peak_equity = float(state.get("peak_equity", initial_equity))

    result = EngineResult(state=state)

    forward = sorted(
        (o for o in per_bar_obs if o["timestamp"] >= forward_start_ts),
        key=lambda o: o["timestamp"],
    )

    for obs in forward:
        ts = obs["timestamp"]
        if ts <= watermark:
            continue  # already processed in a prior run

        desired = set(obs.get("active_symbols", []))
        current = set(open_positions)
        entries = sorted(desired - current)
        exits = sorted(current - desired)

        # Resolve T+1 open for every acted-on symbol. If any is missing, defer the
        # WHOLE bar (all-or-nothing) and stop: leaves ledgers contiguous; retry later.
        nxt: dict[str, tuple[str, float]] = {}
        deferred = False
        for sym in entries + exits:
            nb = prices.next_bar(sym, ts)
            if nb is None:
                deferred = True
                break
            nxt[sym] = nb
        if deferred:
            result.deferred_bar_ts = ts
            break

        # --- 1. snapshot bar `ts` on the PRE-FILL book (funding + marks + equity) ---
        for sym in sorted(open_positions):
            pos = open_positions[sym]
            close_ts = prices.close_at(sym, ts)
            mark = close_ts if close_ts is not None else pos["entry_price"]
            notional_at = pos["qty"] * mark
            rate, available = funding_at(funding_index, sym, ts)
            amount = notional_at * rate if available else 0.0  # long pays when rate>0
            pos["funding_accrued"] += amount
            pos["hold_bars"] += 1
            acc["funding_cum"] += amount
            result.funding.append(
                {
                    "funding_id": f"{sym}|{ts}",
                    "symbol": sym,
                    "bar_ts": ts,
                    "notional_usd": round(notional_at, 8),
                    "funding_rate": rate,
                    "rate_available": available,
                    "funding_amount": round(amount, 8),
                }
            )

        unreal = 0.0
        gross_exposure = 0.0
        for sym, pos in open_positions.items():
            close_ts = prices.close_at(sym, ts)
            if close_ts is None:
                continue
            unreal += (close_ts - pos["entry_price"]) * pos["qty"]
            gross_exposure += pos["qty"] * close_ts

        realized_gross = acc["realized_gross"]
        equity = (
            initial_equity
            + realized_gross
            - acc["fees_cum"]
            - acc["funding_cum"]
            + unreal
        )
        peak_equity = max(peak_equity, equity)
        drawdown = (peak_equity - equity) / peak_equity if peak_equity > 0 else 0.0

        result.equity.append(
            {
                "bar_ts": ts,
                "realized_pnl": round(realized_gross, 8),
                "unrealized_pnl": round(unreal, 8),
                "funding_cum": round(acc["funding_cum"], 8),
                "fees_cum": round(acc["fees_cum"], 8),
                "equity": round(equity, 8),
                "drawdown": round(drawdown, 8),
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
        state["bars_elapsed"] += 1

        # --- 2. apply fills (execute at T+1 open) ---
        for sym in exits:
            next_ts, open_price = nxt[sym]
            fill_price = open_price * (1.0 - slip)
            pos = open_positions.pop(sym)
            qty = pos["qty"]
            fee = fill_price * qty * fee_rate
            acc["fees_cum"] += fee
            fid = fill_id(sym, ts, "SELL", "exit")
            result.fills.append(
                {
                    "fill_id": fid,
                    "signal_bar_ts": ts,
                    "fill_ts": next_ts,
                    "symbol": sym,
                    "side": "SELL",
                    "kind": "exit",
                    "qty": round(qty, 10),
                    "open_price": round(open_price, 8),
                    "fill_price": round(fill_price, 8),
                    "slippage_bps": float(config["slippage_model"]["slippage_bps"]),
                    "fee": round(fee, 8),
                    "backfill": False,
                }
            )
            gross = (fill_price - pos["entry_price"]) * qty
            acc["realized_gross"] += gross
            fees = pos["entry_fee"] + fee
            funding = pos["funding_accrued"]
            net = gross - fees - funding
            result.trades.append(
                {
                    "trade_id": fid,
                    "symbol": sym,
                    "entry_fill_id": pos["entry_fill_id"],
                    "exit_fill_id": fid,
                    "entry_bar_ts": pos["entry_bar_ts"],
                    "exit_bar_ts": ts,
                    "qty": round(qty, 10),
                    "entry_price": round(pos["entry_price"], 8),
                    "exit_price": round(fill_price, 8),
                    "gross_pnl": round(gross, 8),
                    "fees": round(fees, 8),
                    "funding": round(funding, 8),
                    "net_pnl": round(net, 8),
                    "hold_bars": pos["hold_bars"],
                    "backfill": False,
                }
            )

        for sym in entries:
            next_ts, open_price = nxt[sym]
            fill_price = open_price * (1.0 + slip)
            qty = notional / fill_price
            fee = fill_price * qty * fee_rate
            acc["fees_cum"] += fee
            fid = fill_id(sym, ts, "BUY", "entry")
            result.fills.append(
                {
                    "fill_id": fid,
                    "signal_bar_ts": ts,
                    "fill_ts": next_ts,
                    "symbol": sym,
                    "side": "BUY",
                    "kind": "entry",
                    "qty": round(qty, 10),
                    "open_price": round(open_price, 8),
                    "fill_price": round(fill_price, 8),
                    "slippage_bps": float(config["slippage_model"]["slippage_bps"]),
                    "fee": round(fee, 8),
                    "backfill": False,
                }
            )
            open_positions[sym] = {
                "entry_fill_id": fid,
                "entry_price": fill_price,
                "qty": qty,
                "entry_bar_ts": ts,
                "funding_accrued": 0.0,
                "entry_fee": fee,
                "hold_bars": 0,
            }

        watermark = ts

    state["watermark_bar_ts"] = watermark
    state["peak_equity"] = peak_equity
    return result
