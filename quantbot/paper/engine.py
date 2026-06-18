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
from datetime import datetime, timedelta, timezone
from typing import Any

from quantbot.data.types import Bar
from quantbot.paper.freshness import parse_bar_utc
from quantbot.paper.snapshots import bar_commit_id

_BAR_FMT = "%Y-%m-%dT%H:%M:%S"

# ------------------------------------------------------------------- canonical money


def _round8(x: float) -> float:
    """Round a money value to the persisted 8-dp precision."""
    return round(float(x), 8)


def canonical_net_pnl(gross: float, fees: float, funding: float) -> float:
    """Derive net_pnl from the SAME rounded components that are persisted.

    The ledger stores gross_pnl/fees/funding each rounded to 8 dp. The in-tx
    verifier re-derives net from those stored (rounded) columns and rejects at
    ABS(net - (gross - fees - funding)) > 1e-8. Computing net from the unrounded
    inputs and rounding separately can drift past that gate by ~1e-8. Deriving
    net from the rounded components makes the persisted row self-consistent by
    construction (residual <= 0.5e-8 < 1e-8). net_pnl is a redundant audit column
    -- equity uses the raw accumulators -- so this cannot move any cumulative.
    """
    return _round8(_round8(gross) - _round8(fees) - _round8(funding))


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


def funding_in_interval(
    index: dict[str, list[tuple[str, float]]],
    symbol: str,
    start_exclusive: str,
    end_inclusive: str,
) -> tuple[float, int, bool]:
    """Sum every funding event in (start_exclusive, end_inclusive] for a symbol.

    Returns (total_rate, num_events, rate_available). This accrues ALL actual funding rows
    by their timestamp inside the held interval — it does NOT assume exactly one 8h-aligned
    funding value, and does NOT assume symbols settle only at 00/08/16 (the interval window
    captures sub-grid / multiple events too).

    rate_available=False means no funding event landed in the interval (an expected funding
    row is missing where one was needed). The amount is reported as 0.0 with the gap flag
    set — never silently zeroed without the flag. (See schema doc section 1.3 / 11.)
    """
    series = index.get(symbol)
    if not series:
        return 0.0, 0, False
    keys = [k for k, _ in series]
    lo = bisect.bisect_right(keys, start_exclusive)  # first event strictly after start
    hi = bisect.bisect_right(keys, end_inclusive)  # first event after end (exclusive bound)
    events = series[lo:hi]
    if not events:
        return 0.0, 0, False
    total_rate = sum(rate for _, rate in events)
    return total_rate, len(events), True


def _interval_start(ts: str, interval_hours: int) -> str:
    """Exclusive start of the funding window ending at bar `ts` (ts - interval_hours)."""
    dt = datetime.strptime(ts.rstrip("Z"), _BAR_FMT).replace(tzinfo=timezone.utc)
    start = dt - timedelta(hours=interval_hours)
    return start.strftime(_BAR_FMT)


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
    interval_hours = int(config.get("freshness", {}).get("bar_interval_hours", 8))
    engine_version = config["engine_version"]
    cfg_hash = config["config_hash"]

    prices = PriceBook(bars_by_symbol)
    funding_index = build_funding_index(funding_df)

    acc = state["accumulators"]
    open_positions: dict[str, dict[str, Any]] = state["open_positions"]
    watermark = state.get("watermark_bar_ts", "") or ""
    peak_equity = float(state.get("peak_equity", initial_equity))

    result = EngineResult(state=state)

    # Eligibility is a parsed-instant comparison, never a raw string compare: a naive
    # observer timestamp ('...T00:00:00') sorts lexicographically BEFORE the trailing-Z
    # config boundary ('...T00:00:00Z'), which would silently drop the bar exactly at
    # forward_start_ts. Parse both into tz-aware UTC datetimes (fails closed on malformed).
    forward_start_dt = parse_bar_utc(forward_start_ts)
    forward = sorted(
        (o for o in per_bar_obs if parse_bar_utc(o["timestamp"]) >= forward_start_dt),
        key=lambda o: parse_bar_utc(o["timestamp"]),
    )

    for obs in forward:
        ts = obs["timestamp"]
        if ts <= watermark:
            continue  # already processed in a prior run

        # Bar-level commit identity (Blocker 1): every artifact this bar produces carries it,
        # and it must equal the frozen snapshot's bar_commit_id (built from the same full
        # source row). Reconcile rejects any bar whose rows disagree, so a partial/stale
        # bar can never reconcile clean.
        commit_id = bar_commit_id(obs, ts, engine_version, cfg_hash)

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
        # Funding is accrued over the ACTUAL position holding interval, from entry fill
        # timestamp to exit fill / current mark timestamp — never before the position
        # exists, and through the T+1 exit fill (Blocker 1 / schema doc section 11).
        window_start = _interval_start(ts, interval_hours)
        for sym in sorted(open_positions):
            pos = open_positions[sym]
            pos["hold_bars"] += 1
            close_ts = prices.close_at(sym, ts)
            mark = close_ts if close_ts is not None else pos["entry_price"]
            notional_at = pos["qty"] * mark
            # Clamp the window start to the entry FILL timestamp: the position is filled
            # at T+1 open, so no funding event before that fill may be charged. On the bar
            # the position is first filled the held interval is zero -> nothing to accrue.
            eff_start = max(window_start, pos["entry_fill_ts"])
            if eff_start >= ts:
                continue
            # Accrue EVERY funding event in (eff_start, ts]; long pays when rate>0.
            rate, num_events, available = funding_in_interval(
                funding_index, sym, eff_start, ts
            )
            amount = notional_at * rate if available else 0.0
            pos["funding_accrued"] += amount
            acc["funding_cum"] += amount
            result.funding.append(
                {
                    "funding_id": f"{sym}|{ts}",
                    "symbol": sym,
                    "bar_ts": ts,
                    "bar_commit_id": commit_id,
                    "window_start": eff_start,
                    "window_end": ts,
                    "notional_usd": round(notional_at, 8),
                    "funding_rate": round(rate, 12),
                    "funding_events": num_events,
                    "rate_available": available,
                    "funding_amount": round(amount, 8),
                }
            )

        # Exit-tail funding stub: a position exiting at this bar is still held until its
        # T+1 exit FILL, so funding events in (exit_signal_ts, exit_fill_ts] must still be
        # charged. Accrued here (before the equity snapshot) so the bar-`ts` equity
        # funding_cum stays exactly tied to the funding ledger sum (Blocker 1).
        for sym in exits:
            pos = open_positions[sym]
            next_ts, _ = nxt[sym]
            stub_mark_close = prices.close_at(sym, next_ts)
            # v1 mark approximation: stub notional uses the exit-fill bar mark if available,
            # else the entry price (documented in schema doc section 11).
            stub_mark = stub_mark_close if stub_mark_close is not None else pos["entry_price"]
            stub_notional = pos["qty"] * stub_mark
            s_rate, s_events, s_available = funding_in_interval(
                funding_index, sym, ts, next_ts
            )
            s_amount = stub_notional * s_rate if s_available else 0.0
            pos["funding_accrued"] += s_amount
            acc["funding_cum"] += s_amount
            result.funding.append(
                {
                    "funding_id": f"{sym}|{ts}|exit",
                    "symbol": sym,
                    "bar_ts": ts,
                    "bar_commit_id": commit_id,
                    "window_start": ts,
                    "window_end": next_ts,
                    "notional_usd": round(stub_notional, 8),
                    "funding_rate": round(s_rate, 12),
                    "funding_events": s_events,
                    "rate_available": s_available,
                    "funding_amount": round(s_amount, 8),
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
                "bar_commit_id": commit_id,
                "realized_gross_pnl": round(realized_gross, 8),
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
                "bar_commit_id": commit_id,
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
                    "bar_commit_id": commit_id,
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
            # Persist net derived from the same rounded components we store, so the
            # row is self-consistent with the in-tx verifier (see canonical_net_pnl).
            gross_r = _round8(gross)
            fees_r = _round8(fees)
            funding_r = _round8(funding)
            net_r = canonical_net_pnl(gross, fees, funding)
            result.trades.append(
                {
                    "trade_id": fid,
                    "bar_commit_id": commit_id,
                    "symbol": sym,
                    "entry_fill_id": pos["entry_fill_id"],
                    "exit_fill_id": fid,
                    "entry_bar_ts": pos["entry_bar_ts"],
                    "exit_bar_ts": ts,
                    "qty": round(qty, 10),
                    "entry_price": round(pos["entry_price"], 8),
                    "exit_price": round(fill_price, 8),
                    "gross_pnl": gross_r,
                    "fees": fees_r,
                    "funding": funding_r,
                    "net_pnl": net_r,
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
                    "bar_commit_id": commit_id,
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
                "entry_fill_ts": next_ts,  # actual fill timestamp (T+1 open) for funding
                "funding_accrued": 0.0,
                "entry_fee": fee,
                "hold_bars": 0,
            }

        watermark = ts

    state["watermark_bar_ts"] = watermark
    state["peak_equity"] = peak_equity
    return result
