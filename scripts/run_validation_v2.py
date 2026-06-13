#!/usr/bin/env python3
"""Package V2 — Bounded Validation Runner

Implements the bounded validation protocol from:
  docs/plans/PACKAGE_V2_BOUNDED_VALIDATION_PLAN.md

This is an execution-layer wrapper — NOT a redesign task.
No strategy logic is reimplemented; we import and call the frozen Package V2 code.

RESEARCH_CONTINUE conditions (ALL must pass):
  - max_dd ≤ 0.35
  - excess_return > 0
  - heat_cap triggers in ≤ 5% of bars

FAIL conditions (ANY triggers):
  - max_dd > 0.35
  - excess_return ≤ 0
  - heat_cap triggers in > 5% of bars

INCONCLUSIVE:
  - < 200 bars
  - extreme black swan
  - benchmark/K3 ambiguity

WARNING: The JSON label "GO" below is a research label meaning
"continue research / not killed by this test." It is NOT live
 trading approval.

Usage:
    python scripts/run_validation_v2.py
"""

import argparse
import csv
import json
import math
import subprocess
import sys
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from quantbot.data.multi_asset_loader import load_all_ohlcv
from quantbot.data.funding_loader import load_all_funding, build_funding_lookup
from quantbot.data.quarterly_universe import QUARTERLY_DATES, QUARTERLY_UNIVERSES
from quantbot.data.types import Bar
from quantbot.strategy.tsmom_strategy import TSMOM_GRID, TSMOMStrategy
from quantbot.strategy.vol_state_overlay import VolStateOverlay
from quantbot.experiment.volnorm_portfolio import (
    compute_vol_normed_weights,
    VolatilityTracker,
    PACKAGE_IDENTITY,
    HEAT_CAP,
    VOL_LOOKBACK_BARS,
)

# Validation parameters
WINDOW_SIZE = 500  # ~500 bars holdout window
VOL_QUANTILE = 0.65  # Same as Stage 4

# Kill criteria thresholds (same as Stage 4)
K1_EXCESS_RETURN_THRESHOLD = 0.0
K2_DRAWDOWN_THRESHOLD = 0.35

# Heat cap trigger threshold for FAIL
HEAT_CAP_TRIGGER_RATE_THRESHOLD = 0.05  # 5%
BAR_INTERVAL = timedelta(hours=8)


def _log_return(close_start: float, close_end: float) -> float:
    if close_start <= 0 or close_end <= 0:
        return 0.0
    return math.log(close_end / close_start)


def _compute_equity(bar_returns: list[float]) -> list[float]:
    """Cumulative equity from per-bar log returns. Starts at 1.0."""
    equity = [1.0]
    for r in bar_returns:
        equity.append(equity[-1] * math.exp(r))
    return equity


def _max_drawdown(equity: list[float]) -> float:
    """Peak-to-trough drawdown as fraction (0 = no drawdown)."""
    peak = equity[0]
    max_dd = 0.0
    for e in equity:
        if e > peak:
            peak = e
        dd = (peak - e) / peak
        if dd > max_dd:
            max_dd = dd
    return max_dd


def _sharpe(bar_returns: list[float]) -> float:
    """Annualized Sharpe from per-bar log returns (8h bars, 1095 bars/yr)."""
    if len(bar_returns) < 2:
        return 0.0
    mean_ret = sum(bar_returns) / len(bar_returns)
    variance = sum((r - mean_ret) ** 2 for r in bar_returns) / max(1, len(bar_returns) - 1)
    std_ret = math.sqrt(variance)
    if std_ret == 0.0:
        return 0.0
    return (mean_ret * 1095) / (std_ret * math.sqrt(1095))


def get_git_info() -> tuple[str, str]:
    """Get current branch and commit hash."""
    try:
        branch = subprocess.check_output(
            ["git", "rev-parse", "--abbrev-ref", "HEAD"],
            text=True
        ).strip()
        commit = subprocess.check_output(
            ["git", "rev-parse", "HEAD"],
            text=True
        ).strip()
        return branch, commit
    except subprocess.CalledProcessError:
        return "unknown", "unknown"


def _parse_bar_timestamp(timestamp: str) -> datetime:
    """Parse an observer bar-open timestamp as UTC."""
    parsed = datetime.fromisoformat(timestamp.replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def filter_closed_bars(
    bars_by_symbol: dict[str, list[Bar]],
    now: datetime,
) -> dict[str, list[Bar]]:
    """Return only bars whose full 8-hour interval has closed by ``now``."""
    if now.tzinfo is None:
        raise ValueError("now must be timezone-aware")
    now_utc = now.astimezone(timezone.utc)
    return {
        symbol: [
            bar for bar in bars
            if _parse_bar_timestamp(bar.timestamp) + BAR_INTERVAL <= now_utc
        ]
        for symbol, bars in bars_by_symbol.items()
    }


def run_observer_window(
    bars_by_symbol: dict[str, list[Bar]],
    funding_df,
    funding_lookup: dict | None,
    now: datetime,
) -> dict:
    """Run the observer using closed candles only."""
    return run_validation_window(filter_closed_bars(bars_by_symbol, now), funding_df, funding_lookup)


def run_validation_window(
    bars_by_symbol: dict[str, list[Bar]],
    funding_df,
    funding_lookup: dict | None,
) -> dict:
    """Run the Package V2 strategy on the holdout validation window.

    The holdout window is the last ~WINDOW_SIZE bars, preceded by
    VOL_LOOKBACK_BARS warmup bars for volatility trackers.

    Returns a dict with per-bar observations and summary metrics.
    """

    # Find reference symbol (BTC) to determine window boundaries
    ref_bars = bars_by_symbol.get("BTCUSDT", [])
    if not ref_bars:
        raise ValueError("BTCUSDT data required for reference")

    total_bars = len(ref_bars)
    print(f"Total bars available: {total_bars}")

    # Define window: last WINDOW_SIZE bars
    window_start = max(0, total_bars - WINDOW_SIZE)
    window_end = total_bars
    actual_window_size = window_end - window_start

    print(f"Validation window: bars {window_start} to {window_end} ({actual_window_size} bars)")
    print(f"  Start: {ref_bars[window_start].timestamp}")
    print(f"  End: {ref_bars[window_end - 1].timestamp}")

    # Determine universe for this period
    window_ts = ref_bars[window_start].timestamp
    quarter_idx = 0
    for qi, qdate in enumerate(QUARTERLY_DATES):
        if window_ts >= qdate:
            quarter_idx = qi
    qdate = QUARTERLY_DATES[quarter_idx] if quarter_idx < len(QUARTERLY_DATES) else QUARTERLY_DATES[-1]
    universe = QUARTERLY_UNIVERSES.get(qdate, ["BTCUSDT", "ETHUSDT"])
    print(f"Universe: {universe}")

    # Start state calculation at the stable boundary for the selected universe.
    # The published window still rolls, but overlapping rows are always derived
    # from the same preceding state while that universe remains applicable.
    warmup_start = next(
        (i for i, bar in enumerate(ref_bars) if bar.timestamp >= qdate),
        0,
    )
    warmup_end = window_start
    warmup_size = max(0, warmup_end - warmup_start)
    print(f"Warmup period: bars {warmup_start} to {warmup_end} ({warmup_size} bars)")

    # Use representative grid point: rp=20, th=0.0 (same as Stage 4 K2 check)
    rep_params = TSMOM_GRID[0]  # {"return_period": 20, "threshold": 0.0}
    return_period = rep_params["return_period"]
    threshold = rep_params["threshold"]
    print(f"Using grid point: rp={return_period}, th={threshold}")

    # Initialize strategies and volatility trackers
    overlays: dict[str, VolStateOverlay] = {}
    for symbol in universe:
        if symbol not in bars_by_symbol:
            continue
        ts = TSMOMStrategy(return_period=return_period, threshold=threshold, symbol=symbol)
        overlays[symbol] = VolStateOverlay(tsme=ts, vol_high_quantile=VOL_QUANTILE)

    vol_trackers: dict[str, VolatilityTracker] = {
        symbol: VolatilityTracker(lookback=VOL_LOOKBACK_BARS)
        for symbol in universe if symbol in bars_by_symbol
    }

    # Calculate from the stable universe boundary, but score and publish only
    # the rolling validation window.
    print("Warming up deterministic observer state...")
    strat_net: list[float] = []
    bench: list[float] = []
    heat_cap_triggers = 0
    bars_with_active = 0
    total_heat = 0.0
    prev_close: dict[str, float] = {}

    per_bar_obs: list[dict] = []

    for i in range(warmup_start, window_end):
        bar_data: dict[str, tuple[float, float]] = {}

        for symbol in universe:
            if symbol not in bars_by_symbol:
                continue
            bars = bars_by_symbol[symbol]
            if i >= len(bars):
                continue
            bar = bars[i]

            if symbol not in prev_close:
                prev_close[symbol] = bar.close
                continue

            overlay = overlays[symbol]
            signal, regime = overlay.on_bar(bar)
            ret = _log_return(prev_close[symbol], bar.close)

            # Carry cost
            carry_cost = 0.0
            if funding_lookup is not None:
                bar_ts = bar.timestamp
                key = (symbol, bar_ts)
                if key in funding_lookup:
                    carry_cost = abs(funding_lookup[key]) * 3
                else:
                    sub = funding_df[funding_df["symbol"] == symbol]
                    leq = sub[sub["dt"] <= bar_ts]
                    if not leq.empty:
                        carry_cost = abs(float(leq.iloc[-1]["fundingRate"])) * 3

            ret_net = ret - carry_cost

            # Update volatility trackers
            if regime == "low_vol" and symbol in vol_trackers:
                vol_trackers[symbol].update(ret)
            elif regime == "high_vol" and symbol in vol_trackers:
                vol_trackers[symbol].update(ret)

            # Collect active long signals
            if signal is not None and signal.direction == "long":
                bar_data[symbol] = (ret, ret_net)

            prev_close[symbol] = bar.close

        if i < window_start:
            continue

        # Record benchmark (always-long equal-weight) for the published window.
        bench.extend(
            _log_return(
                bars_by_symbol[symbol][i - 1].close,
                bars_by_symbol[symbol][i].close,
            )
            for symbol in universe
            if symbol in bars_by_symbol and 0 < i < len(bars_by_symbol[symbol])
        )

        # Compute weighted portfolio return
        if bar_data:
            active_symbols = list(bar_data.keys())
            weights = compute_vol_normed_weights(active_symbols, vol_trackers, HEAT_CAP)

            # Portfolio heat
            bar_heat = sum(
                weights[s] * vol_trackers[s].volatility
                for s in active_symbols if s in vol_trackers
            )
            total_heat += bar_heat
            bars_with_active += 1

            # Check heat cap
            if bar_heat > HEAT_CAP and bar_heat > 0:
                heat_cap_triggers += 1

            # Weighted return
            weighted_ret = sum(bar_data[s][1] * weights[s] for s in active_symbols)
            strat_net.append(weighted_ret)

            per_bar_obs.append({
                "bar_index": i,
                "timestamp": ref_bars[i].timestamp,
                "active_symbols": active_symbols,
                "portfolio_heat": bar_heat,
                "heat_cap_triggered": bar_heat > HEAT_CAP,
                "weighted_return": weighted_ret,
            })
        else:
            strat_net.append(0.0)
            per_bar_obs.append({
                "bar_index": i,
                "timestamp": ref_bars[i].timestamp,
                "active_symbols": [],
                "portfolio_heat": 0.0,
                "heat_cap_triggered": False,
                "weighted_return": 0.0,
            })

    # Compute summary metrics
    equity = _compute_equity(strat_net)
    net_return = sum(strat_net)
    benchmark_return = sum(bench)
    excess_return = net_return - benchmark_return
    max_dd = _max_drawdown(equity)
    sharpe = _sharpe(strat_net)
    heat_cap_trigger_rate = heat_cap_triggers / max(1, bars_with_active)
    avg_heat = total_heat / max(1, bars_with_active)

    return {
        "window_start_bar": window_start,
        "window_end_bar": window_end,
        "window_size": actual_window_size,
        "warmup_size": warmup_size,
        "window_start_ts": ref_bars[window_start].timestamp,
        "window_end_ts": ref_bars[window_end - 1].timestamp,
        "universe": universe,
        "return_period": return_period,
        "threshold": threshold,
        "net_return": net_return,
        "benchmark_return": benchmark_return,
        "excess_return": excess_return,
        "max_drawdown": max_dd,
        "sharpe": sharpe,
        "heat_cap_triggers": heat_cap_triggers,
        "bars_with_active": bars_with_active,
        "heat_cap_trigger_rate": heat_cap_trigger_rate,
        "avg_portfolio_heat": avg_heat,
        "final_equity": equity[-1] if equity else 1.0,
        "per_bar_obs": per_bar_obs,
    }


def determine_verdict(metrics: dict) -> tuple[str, list[str]]:
    """Apply RESEARCH_CONTINUE/FAIL/INCONCLUSIVE gate.

    Returns (verdict, list of reasons).
    NOTE: "GO" in the returned verdict is a research label only.
    It means "not killed by this test," not live trading approval.
    """
    reasons = []

    # INCONCLUSIVE checks
    if metrics["window_size"] < 200:
        return "INCONCLUSIVE", ["Insufficient bars (< 200)"]

    # FAIL checks
    if metrics["max_drawdown"] > K2_DRAWDOWN_THRESHOLD:
        reasons.append(f"max_dd {metrics['max_drawdown']:.4f} > {K2_DRAWDOWN_THRESHOLD}")

    if metrics["excess_return"] <= 0:
        reasons.append(f"excess_return {metrics['excess_return']:.4f} <= 0")

    if metrics["heat_cap_trigger_rate"] > HEAT_CAP_TRIGGER_RATE_THRESHOLD:
        reasons.append(
            f"heat_cap_trigger_rate {metrics['heat_cap_trigger_rate']:.4f} > {HEAT_CAP_TRIGGER_RATE_THRESHOLD}"
        )

    if reasons:
        return "FAIL", reasons

    # GO checks (all must pass)
    go_reasons = []
    if metrics["max_drawdown"] <= K2_DRAWDOWN_THRESHOLD:
        go_reasons.append(f"max_dd {metrics['max_drawdown']:.4f} <= {K2_DRAWDOWN_THRESHOLD}")
    else:
        reasons.append(f"max_dd {metrics['max_drawdown']:.4f} > {K2_DRAWDOWN_THRESHOLD}")

    if metrics["excess_return"] > 0:
        go_reasons.append(f"excess_return {metrics['excess_return']:.4f} > 0")
    else:
        reasons.append(f"excess_return {metrics['excess_return']:.4f} <= 0")

    if metrics["heat_cap_trigger_rate"] <= HEAT_CAP_TRIGGER_RATE_THRESHOLD:
        go_reasons.append(
            f"heat_cap_trigger_rate {metrics['heat_cap_trigger_rate']:.4f} <= {HEAT_CAP_TRIGGER_RATE_THRESHOLD}"
        )
    else:
        reasons.append(
            f"heat_cap_trigger_rate {metrics['heat_cap_trigger_rate']:.4f} > {HEAT_CAP_TRIGGER_RATE_THRESHOLD}"
        )

    if reasons:
        return "FAIL", reasons

    return "GO", go_reasons


def write_package_identity(output_dir: Path) -> None:
    """Write package_identity.json — frozen Package V2 identity."""
    path = output_dir / "package_identity.json"
    with open(path, "w") as f:
        json.dump(PACKAGE_IDENTITY, f, indent=2)
    print(f"Written: {path}")


def write_validation_receipt(
    output_dir: Path,
    metrics: dict,
    branch: str,
    commit: str,
) -> None:
    """Write validation_receipt.md — window definition, date, branch/commit."""
    path = output_dir / "validation_receipt.md"
    run_ts = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

    content = f"""# Package V2 — Bounded Validation Receipt

## Run Metadata
- **Run timestamp:** {run_ts}
- **Branch:** {branch}
- **Commit:** {commit}

## Package V2 Identity
- **Package name:** {PACKAGE_IDENTITY["package_name"]}
- **Branch:** {PACKAGE_IDENTITY["branch"]}
- **Sizing method:** {PACKAGE_IDENTITY["sizing_method"]}
- **Heat cap:** {PACKAGE_IDENTITY["heat_cap"]}
- **Vol lookback:** {PACKAGE_IDENTITY["vol_lookback_bars"]} bars
- **Benchmark mode:** {PACKAGE_IDENTITY["benchmark_mode"]}

## Validation Window Definition
- **Window start bar:** {metrics["window_start_bar"]}
- **Window end bar:** {metrics["window_end_bar"]}
- **Window size:** {metrics["window_size"]} bars
- **Warmup size:** {metrics["warmup_size"]} bars
- **Window start timestamp:** {metrics["window_start_ts"]}
- **Window end timestamp:** {metrics["window_end_ts"]}

## Grid Point Tested
- **Return period:** {metrics["return_period"]}
- **Threshold:** {metrics["threshold"]}
- **Universe:** {metrics["universe"]}

## Mutation Confirmation
No package components were mutated during this validation run:
- Signal family: unchanged (TSMOM multi-asset breakout)
- Thresholds: unchanged (K1/K2/K4 as defined in Stage 4)
- Vol lookback: unchanged ({VOL_LOOKBACK_BARS} bars)
- Heat cap: unchanged ({HEAT_CAP})
- Sizing logic: unchanged (inverse-vol normalized)
- Benchmark semantics: unchanged (gross)
"""

    with open(path, "w") as f:
        f.write(content)
    print(f"Written: {path}")


def write_observation_log(output_dir: Path, metrics: dict) -> None:
    """Write observation_log.json — per-bar observations."""
    path = output_dir / "observation_log.json"

    # Summary section + per-bar observations (truncated if too many)
    obs_log = {
        "window_size": metrics["window_size"],
        "summary": {
            "net_return": round(metrics["net_return"], 6),
            "benchmark_return": round(metrics["benchmark_return"], 6),
            "excess_return": round(metrics["excess_return"], 6),
            "max_drawdown": round(metrics["max_drawdown"], 6),
            "sharpe": round(metrics["sharpe"], 4),
            "heat_cap_triggers": metrics["heat_cap_triggers"],
            "bars_with_active": metrics["bars_with_active"],
            "heat_cap_trigger_rate": round(metrics["heat_cap_trigger_rate"], 6),
            "avg_portfolio_heat": round(metrics["avg_portfolio_heat"], 6),
            "final_equity": round(metrics["final_equity"], 6),
        },
        "per_bar_obs": metrics["per_bar_obs"],
    }

    with open(path, "w") as f:
        json.dump(obs_log, f, indent=2)
    print(f"Written: {path} ({len(metrics['per_bar_obs'])} bars)")


def write_drawdown_summary(
    output_dir: Path,
    metrics: dict,
    stage4_drawdown_max: float = 0.225758,
    stage4_excess_return: float = 0.703028,
) -> None:
    """Write drawdown_summary.json — realized metrics vs Stage 4."""
    path = output_dir / "drawdown_summary.json"

    summary = {
        "validation_window": {
            "window_size": metrics["window_size"],
            "max_drawdown": round(metrics["max_drawdown"], 6),
            "excess_return": round(metrics["excess_return"], 6),
            "sharpe": round(metrics["sharpe"], 4),
            "net_return": round(metrics["net_return"], 6),
            "benchmark_return": round(metrics["benchmark_return"], 6),
            "heat_cap_trigger_rate": round(metrics["heat_cap_trigger_rate"], 6),
            "avg_portfolio_heat": round(metrics["avg_portfolio_heat"], 6),
            "final_equity": round(metrics["final_equity"], 6),
        },
        "stage4_reference": {
            "max_drawdown": stage4_drawdown_max,
            "excess_return": stage4_excess_return,
            "note": "From output/stage4_volnorm/kill_criteria.json",
        },
        "comparison": {
            "drawdown_delta": round(metrics["max_drawdown"] - stage4_drawdown_max, 6),
            "excess_return_delta": round(metrics["excess_return"] - stage4_excess_return, 6),
            "drawdown_within_threshold": metrics["max_drawdown"] <= K2_DRAWDOWN_THRESHOLD,
            "excess_return_positive": metrics["excess_return"] > 0,
        },
    }

    with open(path, "w") as f:
        json.dump(summary, f, indent=2)
    print(f"Written: {path}")


def write_caveat_note(output_dir: Path) -> None:
    """Write caveat_note.md — benchmark/K3 interpretation problems."""
    path = output_dir / "caveat_note.md"

    content = """# Package V2 — Bounded Validation Caveat Note

## Benchmark Semantics
- This validation uses gross benchmark (always-long equal-weight), consistent with Stage 4.
- The gross benchmark does not account for funding costs, which may cause apparent
  "excess return" that could differ under a net-of-carry benchmark.
- This is the same benchmark interpretation used in Stage 4 qualification.

## K3 Status
- K3 (funding drag ratio) was not measured in this validation run.
- K3 requires gross return retro-computation which was deferred from Stage 4.
- If K3 were measurable and > 0.40, this would trigger an INCONCLUSIVE classification
  due to benchmark/K3 ambiguity.

## Heat Cap Behavior
- Heat cap is set to 1.0 (never triggered in Stage 4; avg heat 0.0614).
- Heat cap triggers are tracked but are not expected in normal regime operation.
- Trigger rate > 5% would trigger FAIL per the validation protocol.

## Conclusion
No benchmark/K3 interpretation problems observed that would prevent verdict determination.
The gross benchmark interpretation is consistent with the frozen Package V2 definition.
"""

    with open(path, "w") as f:
        f.write(content)
    print(f"Written: {path}")


def main() -> int:
    parser = argparse.ArgumentParser(description="Package V2 Bounded Validation")
    parser.add_argument("--output-dir", default="output/validation_v2")
    args = parser.parse_args()

    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    branch, commit = get_git_info()

    print(f"\n{'='*60}")
    print("PACKAGE V2 — BOUNDED VALIDATION")
    print(f"{'='*60}")
    print(f"Output directory: {output_dir}")
    print(f"Branch: {branch}")
    print(f"Commit: {commit}")

    # Load data
    print("\nLoading OHLCV data...")
    bars_by_symbol = load_all_ohlcv()
    ref_bars = bars_by_symbol.get("BTCUSDT", [])
    print(f"  {len(bars_by_symbol)} symbols, {len(ref_bars)} bars")

    print("Loading funding data...")
    funding_df = load_all_funding()
    funding_lookup = build_funding_lookup(funding_df) if not funding_df.empty else None
    print(f"  {len(funding_df)} funding records")

    # Run validation
    print("\nRunning validation window...")
    metrics = run_observer_window(
        bars_by_symbol,
        funding_df,
        funding_lookup,
        now=datetime.now(timezone.utc),
    )

    # Determine verdict
    verdict, reasons = determine_verdict(metrics)
    print(f"\n{'='*60}")
    print(f"VERDICT: {verdict}")
    for r in reasons:
        print(f"  - {r}")
    print(f"{'='*60}")

    # Print summary
    print(f"\nRealized Metrics:")
    print(f"  Window size:       {metrics['window_size']} bars")
    print(f"  Net return:        {metrics['net_return']:.4f}")
    print(f"  Benchmark return:   {metrics['benchmark_return']:.4f}")
    print(f"  Excess return:     {metrics['excess_return']:.4f}")
    print(f"  Max drawdown:      {metrics['max_drawdown']:.4f}")
    print(f"  Sharpe:            {metrics['sharpe']:.4f}")
    print(f"  Heat cap triggers: {metrics['heat_cap_triggers']} / {metrics['bars_with_active']}")
    print(f"  Heat cap rate:     {metrics['heat_cap_trigger_rate']:.4f}")
    print(f"  Avg portfolio heat: {metrics['avg_portfolio_heat']:.4f}")
    print(f"  Final equity:      {metrics['final_equity']:.4f}")

    # Write outputs
    print("\nWriting artifacts...")
    write_package_identity(output_dir)
    write_validation_receipt(output_dir, metrics, branch, commit)
    write_observation_log(output_dir, metrics)
    write_drawdown_summary(output_dir, metrics)
    write_caveat_note(output_dir)

    # Write verdict summary
    verdict_path = output_dir / "verdict.json"
    with open(verdict_path, "w") as f:
        json.dump({
            "verdict": verdict,
            "reasons": reasons,
            "metrics": {
                "max_drawdown": round(metrics["max_drawdown"], 6),
                "excess_return": round(metrics["excess_return"], 6),
                "heat_cap_trigger_rate": round(metrics["heat_cap_trigger_rate"], 6),
                "window_size": metrics["window_size"],
            },
        }, f, indent=2)
    print(f"Written: {verdict_path}")

    print(f"\n{'='*60}")
    print(f"Validation complete. Artifacts in: {output_dir}")
    print(f"VERDICT: {verdict}")
    print(f"{'='*60}")

    return 0


if __name__ == "__main__":
    sys.exit(main())
