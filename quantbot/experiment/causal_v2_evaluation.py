"""Source-connected synthetic-only causal evaluation adapter for Qnty Package V2.

This is NOT Qnty's original evaluator, an approved scientific run, or a
production-execution engine. It imports hash-verified original Qnty signal and volatility code, but no market
client, ledger, RPC, wallet, or network library. Frozen candidate signal
and inverse-vol concepts follow the publicly inspected source at commit
610f66f6c5660e09a6c0560ae1b4262f0bfd5578.

Key fix: a close-t decision enters at open t+1. A point-in-time trace records
per-symbol weights before future data arrives. Accounting uses simple-dollar
portfolio PnL, realistic explicit price-slippage and fee cash movements, and
signed per-bar funding with missing-coverage refusal.

Do not use this prototype for real-market inference or automated trading.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from math import isfinite, log, sqrt
from typing import Literal

from quantbot.data.types import Bar as QntyBar
from quantbot.strategy.tsmom_strategy import TSMOMStrategy
from quantbot.experiment.volnorm_portfolio import (
    VolatilityTracker, compute_vol_normed_weights,
    VOL_LOOKBACK_BARS as SOURCE_VOL_LOOKBACK, VOL_FLOOR as SOURCE_VOL_FLOOR,
    HEAT_CAP as SOURCE_HEAT_CAP,
)

PINNED_SOURCE_SHA = "610f66f6c5660e09a6c0560ae1b4262f0bfd5578"
SIGNAL_RETURN_PERIOD = 20
SIGNAL_THRESHOLD = 0.0
VOL_LOOKBACK_BARS = 90
VOL_FLOOR = 1e-6
HEAT_CAP = 1.0

@dataclass(frozen=True)
class Bar:
    timestamp: str  # synthetic 8h bar OPEN in UTC
    open: float
    close: float

@dataclass(frozen=True)
class Config:
    fee_bps_per_side: float = 5.0
    slippage_bps_per_side: float = 5.0
    spread_bps_per_side: float = 0.0  # extra half-spread, 0 if included in slippage
    initial_equity: float = 10_000.0
    require_funding: bool = True
    cash_reserve_fraction: float = 0.0  # optional simulation buffer; NOT frozen V2 logic

@dataclass(frozen=True)
class Decision:
    timestamp: str  # known at bar close, executed no earlier than next open
    target_weights: dict[str, float]
    volatility_by_symbol: dict[str, float]

@dataclass(frozen=True)
class Fill:
    decision_timestamp: str
    fill_timestamp: str
    symbol: str
    side: Literal["BUY", "SELL"]
    quantity: float
    executed_price: float
    fee: float

@dataclass(frozen=True)
class Snapshot:
    timestamp: str
    equity: float
    cash: float
    gross_exposure: float
    funding_cashflow: float
    fees_cumulative: float

@dataclass
class Result:
    snapshots: list[Snapshot]
    decisions: list[Decision]
    fills: list[Fill]
    final_cash: float
    final_quantities: dict[str, float]
    mode: str

    def summary(self) -> dict:
        eqs = [s.equity for s in self.snapshots]
        peak = eqs[0]
        drawdown = 0.0
        for eq in eqs:
            peak = max(peak, eq)
            drawdown = max(drawdown, 1.0 - eq / peak)
        return {"mode": self.mode, "bars": len(eqs), "decisions": len(self.decisions),
                "fills": len(self.fills), "final_equity": eqs[-1],
                "simple_return": eqs[-1] / eqs[0] - 1.0, "max_drawdown": drawdown,
                "total_fees": self.snapshots[-1].fees_cumulative}


def _std_last90(values: list[float]) -> float:
    xs = values[-VOL_LOOKBACK_BARS:]
    if len(xs) < 2:
        return VOL_FLOOR
    mean = sum(xs) / len(xs)
    var = sum((x - mean)**2 for x in xs) / (len(xs) - 1)
    return max(sqrt(var), VOL_FLOOR)


def _target_weights(active: list[str], volatility: dict[str, float]) -> dict[str, float]:
    if not active:
        return {}
    unscaled = {s: 1.0 / volatility[s] for s in active}
    total = sum(unscaled.values())
    result = {s: unscaled[s] / total for s in active}
    heat = sum(result[s] * volatility[s] for s in active)
    if heat > HEAT_CAP:
        factor = HEAT_CAP / heat
        result = {s: w * factor for s, w in result.items()}
    return result


def _stamp(value: str) -> datetime:
    t = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if t.tzinfo is None:
        raise ValueError("A timestamp must include UTC offset")
    return t.astimezone(timezone.utc)


def _validate(bars: dict[str, list[Bar]], config: Config) -> tuple[list[str], int]:
    if not bars:
        raise ValueError("Missing symbols")
    if config.initial_equity <= 0 or not isfinite(config.initial_equity):
        raise ValueError("Invalid initial capital")
    for v in (config.fee_bps_per_side, config.slippage_bps_per_side, config.spread_bps_per_side):
        if not 0 <= v < 10000 or not isfinite(v):
            raise ValueError("Invalid cost assumption")
    if not (0.0 <= config.cash_reserve_fraction < 1.0):
        raise ValueError("Invalid cash reserve")
    symbols = sorted(bars)
    n = len(bars[symbols[0]])
    if n < SIGNAL_RETURN_PERIOD + 2:
        raise ValueError("Need warmup and a post-signal fill bar")
    time_grid = [x.timestamp for x in bars[symbols[0]]]
    instants = [_stamp(t) for t in time_grid]
    if len(set(instants)) != n:
        raise ValueError("Duplicate bar timestamp")
    if any(y-x != timedelta(hours=8) for x,y in zip(instants,instants[1:])):
        raise ValueError("Bars must be contiguous 8h candles")
    for sym in symbols:
        rows = bars[sym]
        if len(rows) != n or [b.timestamp for b in rows] != time_grid:
            raise ValueError("Symbols must be strictly timestamp-aligned")
        for b in rows:
            if min(b.open,b.close) <= 0 or not isfinite(b.open) or not isfinite(b.close):
                raise ValueError("Invalid prices")
    return symbols, n


def evaluate(
    bars: dict[str, list[Bar]],
    funding: dict[tuple[str, str], float],
    *,
    config: Config = Config(),
    mode: Literal["v2", "equal_weight_buy_hold", "cash"] = "v2",
) -> Result:
    """Deterministic, 1x, long-only synthetic portfolio account.

    Funding map uses (symbol, bar timestamp) keys; if any long exposure exists
    at bar close, a rate (including explicit 0) must be present. Positive
    funding: long pays; negative funding: long receives. Funding is applied to
    close notional as a synthetic simplification. No gaps or backfills.
    """
    symbols, n = _validate(bars, config)
    if mode not in ("v2", "equal_weight_buy_hold", "cash"):
        raise ValueError("Unsupported mode")
    quantities = {sym: 0.0 for sym in symbols}
    cash = config.initial_equity
    fees = 0.0
    prev_closes: dict[str, float] = {}
    close_history: dict[str, list[float]] = {sym: [] for sym in symbols}
    log_history: dict[str, list[float]] = {sym: [] for sym in symbols}
    strategies = {s: TSMOMStrategy(return_period=SIGNAL_RETURN_PERIOD, threshold=SIGNAL_THRESHOLD, symbol=s) for s in symbols}
    trackers = {s: VolatilityTracker(lookback=SOURCE_VOL_LOOKBACK, floor=SOURCE_VOL_FLOOR) for s in symbols}
    assert SOURCE_VOL_LOOKBACK == VOL_LOOKBACK_BARS and SOURCE_VOL_FLOOR == VOL_FLOOR and SOURCE_HEAT_CAP == HEAT_CAP
    decisions: list[Decision] = []
    fills: list[Fill] = []
    snapshots: list[Snapshot] = []
    pending: Decision | None = None
    cost_fee = config.fee_bps_per_side/10000
    cost_slip = (config.slippage_bps_per_side+config.spread_bps_per_side)/10000
    if cost_slip >= 1.0:
        raise ValueError("Invalid execution price penalty")

    for i in range(n):
        at_open = {sym: bars[sym][i].open for sym in symbols}
        stamp = bars[symbols[0]][i].timestamp
        eq_at_open = cash + sum(quantities[s]*at_open[s] for s in symbols)
        if eq_at_open <= 0:
            raise ValueError("Equity exhausted")

        if pending is not None:
            # Execute last CLOSE's desired portfolio at this bar's OPEN.
            # First sell, then buy. Do not allow leverage to fund fees.
            desired_value = {s: eq_at_open*(1-config.cash_reserve_fraction)*pending.target_weights.get(s,0.0) for s in symbols}
            for sym in symbols:
                delta_value = quantities[sym]*at_open[sym] - desired_value[sym]
                if delta_value <= 1e-9:
                    continue
                qty = min(quantities[sym], delta_value/at_open[sym])
                execution_price = at_open[sym]*(1-cost_slip)
                fee = qty*execution_price*cost_fee
                cash += qty*execution_price-fee
                quantities[sym] -= qty
                fees += fee
                fills.append(Fill(pending.timestamp,stamp,sym,"SELL",qty,execution_price,fee))

            wanted = {s:max(0.0,(desired_value[s]-quantities[s]*at_open[s])/at_open[s]) for s in symbols}
            total_buy_cost = sum(q*at_open[s]*(1+cost_slip)*(1+cost_fee) for s,q in wanted.items())
            scale = min(1.0, max(0.0,cash/total_buy_cost)) if total_buy_cost else 0.0
            for sym in symbols:
                qty = wanted[sym]*scale
                if qty <= 1e-12:
                    continue
                execution_price = at_open[sym]*(1+cost_slip)
                fee = qty*execution_price*cost_fee
                cash -= qty*execution_price+fee
                quantities[sym] += qty
                fees += fee
                fills.append(Fill(pending.timestamp,stamp,sym,"BUY",qty,execution_price,fee))
            if cash < -1e-6:
                raise AssertionError("Unexpected borrowing")
            cash = max(0.0,cash)
            pending = None

        mark = {sym:bars[sym][i].close for sym in symbols}
        funding_cashflow = 0.0
        for sym in symbols:
            qty = quantities[sym]
            if qty <= 1e-12:
                continue
            key = (sym,stamp)
            if config.require_funding and key not in funding:
                raise ValueError(f"Missing funding coverage for {sym} {stamp}")
            rate = funding.get(key,0.0)
            if not isfinite(rate):
                raise ValueError("Nonfinite funding rate")
            flow = -qty*mark[sym]*rate
            funding_cashflow += flow
        cash += funding_cashflow
        equity = cash + sum(quantities[s]*mark[s] for s in symbols)
        exposure = sum(quantities[s]*mark[s] for s in symbols)/equity
        if exposure > 1.0+1e-5: # positive funding could slightly increase this; flag rather than silently use leverage
            raise ValueError("Exposure > 1x; financing/risk control required")
        snapshots.append(Snapshot(stamp,equity,cash,exposure,funding_cashflow,fees))

        # Update only after current interval is over. These inputs may affect
        # NEXT open, never current bar's just-marked returns.
        for sym in symbols:
            if sym in prev_closes:
                log_history[sym].append(log(mark[sym]/prev_closes[sym]))
            close_history[sym].append(mark[sym])
            prev_closes[sym] = mark[sym]

        # Exactly Qnty's original pinned signal generation and weight function.
        # Evaluate at CLOSE t, execute no earlier than OPEN t+1.
        source_signals = {}
        for sym in symbols:
            src = QntyBar(stamp, bars[sym][i].open, max(bars[sym][i].open, mark[sym]),
                          min(bars[sym][i].open, mark[sym]), mark[sym], 1.0)
            source_signals[sym] = strategies[sym].on_bar(src)
            if log_history[sym]:
                trackers[sym].update(log_history[sym][-1])

        if mode == "cash":
            continue
        if mode == "equal_weight_buy_hold":
            if i == SIGNAL_RETURN_PERIOD:
                pending = Decision(stamp,{s:1.0/len(symbols) for s in symbols},{})
                decisions.append(pending)
            # After one entry, leave quantities untouched for the duration.
            continue

        if i >= SIGNAL_RETURN_PERIOD:
            active = [sym for sym in symbols if source_signals[sym] is not None and source_signals[sym].direction == "long"]
            volatility = {sym:trackers[sym].volatility for sym in symbols}
            target = compute_vol_normed_weights(active, trackers, SOURCE_HEAT_CAP)
            pending = Decision(stamp,target,volatility)
            decisions.append(pending)
    return Result(snapshots,decisions,fills,cash,quantities,mode)
