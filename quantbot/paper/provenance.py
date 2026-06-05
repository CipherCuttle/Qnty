"""Summary stats, provenance digests, and human receipt for paper_pnl_v1.

The simulation disclaimer is loud and mandatory: paper PnL is not live trading and does
not prove real-money profitability (mirrors the guardrail language in
ops/bin/qnty-write-provenance-receipt.sh).
"""

from __future__ import annotations

import subprocess
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from quantbot.core.determinism import sha256_file
from quantbot.paper import PAPER_ENGINE_VERSION

DISCLAIMER = (
    "SIMULATION ONLY. These are paper fills on a frozen research observer. This is NOT "
    "live trading, NOT realized money, and a positive paper result does NOT prove "
    "real-money profitability or deployment readiness."
)


def _now_utc() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def git_sha() -> str:
    try:
        return subprocess.check_output(["git", "rev-parse", "HEAD"], text=True).strip()
    except Exception:
        return "unknown"


def compute_summary(
    config: dict[str, Any],
    trades: list[dict[str, Any]],
    equity: list[dict[str, Any]],
    open_positions: dict[str, Any],
    bars_elapsed: int,
) -> dict[str, Any]:
    """Aggregate stats over ALL forward ledger rows. winrate is null until closed trades."""
    closed = len(trades)
    nets = [t["net_pnl"] for t in trades]
    wins = [n for n in nets if n > 0]
    losses = [n for n in nets if n < 0]

    winrate = (len(wins) / closed) if closed > 0 else None
    realized_net = round(sum(nets), 8) if closed > 0 else 0.0

    gross_win = sum(wins)
    gross_loss = abs(sum(losses))
    profit_factor = round(gross_win / gross_loss, 6) if gross_loss > 0 else None
    expectancy = round(sum(nets) / closed, 8) if closed > 0 else None

    initial_equity = float(config["initial_equity_usd"])
    last_equity = equity[-1]["equity"] if equity else initial_equity
    total_pnl = round(last_equity - initial_equity, 8)
    max_drawdown = round(max((e["drawdown"] for e in equity), default=0.0), 8)

    if closed == 0:
        verdict = "INCONCLUSIVE — no closed paper trades yet"
    elif bars_elapsed < 90:
        verdict = f"INCONCLUSIVE — insufficient forward bars ({bars_elapsed} < 90)"
    else:
        verdict = "MEASURED (simulation) — sufficient forward sample"

    return {
        "schema_version": config["schema_version"],
        "forward_start_ts": config["forward_start_ts"],
        "bars_elapsed": bars_elapsed,
        "closed_trades": closed,
        "winrate": winrate,
        "realized_net_pnl": realized_net,
        "total_pnl": total_pnl,
        "max_drawdown": max_drawdown,
        "profit_factor": profit_factor,
        "expectancy": expectancy,
        "open_positions": sorted(open_positions),
        "num_open": len(open_positions),
        "current_verdict": verdict,
        "disclaimer": DISCLAIMER,
    }


def _digest(path: Path) -> str:
    return sha256_file(path) if path.exists() else "absent"


def build_provenance(
    forward_obs_dir: Path,
    paper_dir: Path,
    data_dir: Path,
    symbols: list[str],
) -> dict[str, Any]:
    inputs = {
        "bar_decisions.jsonl": _digest(forward_obs_dir / "bar_decisions.jsonl"),
        "observation_log.json": _digest(forward_obs_dir / "observation_log.json"),
    }
    for sym in symbols:
        inputs[f"{sym}_8h_ohlcv.csv"] = _digest(data_dir / f"{sym}_8h_ohlcv.csv")
        inputs[f"{sym}_8h_funding.csv"] = _digest(data_dir / f"{sym}_8h_funding.csv")

    output_files = [
        "paper_config.json",
        "paper_fills.jsonl",
        "paper_positions.jsonl",
        "paper_trades.jsonl",
        "paper_equity.jsonl",
        "paper_funding.jsonl",
        "paper_position_state.json",
        "paper_pnl_summary.json",
    ]
    outputs = {name: _digest(paper_dir / name) for name in output_files}

    return {
        "run_ts": _now_utc(),
        "engine_version": PAPER_ENGINE_VERSION,
        "git_sha": git_sha(),
        "input_digests": inputs,
        "output_digests": outputs,
    }


def render_receipt(
    summary: dict[str, Any],
    last_trades: list[dict[str, Any]],
    funding_gaps: int,
    deferred_bar_ts: str | None,
) -> str:
    wr = summary["winrate"]
    wr_str = f"{wr:.1%}" if wr is not None else "null (no closed trades)"
    lines = [
        "# Paper PnL v1 — Receipt",
        "",
        f"> **{summary['disclaimer']}**",
        "",
        f"- Generated (UTC): {_now_utc()}",
        f"- forward_start_ts: {summary['forward_start_ts']}",
        f"- Bars elapsed (forward): {summary['bars_elapsed']}",
        f"- Open positions: {summary['num_open']} {summary['open_positions']}",
        f"- Closed trades: {summary['closed_trades']}",
        f"- Winrate: {wr_str}",
        f"- Realized net PnL: {summary['realized_net_pnl']}",
        f"- Total PnL (incl. unrealized): {summary['total_pnl']}",
        f"- Max drawdown: {summary['max_drawdown']}",
        f"- Profit factor: {summary['profit_factor']}",
        f"- Expectancy: {summary['expectancy']}",
        f"- Current verdict: {summary['current_verdict']}",
        "",
        "## Last closed trades",
    ]
    if last_trades:
        lines.append("| symbol | entry_bar_ts | exit_bar_ts | net_pnl | hold_bars |")
        lines.append("| --- | --- | --- | --- | --- |")
        for t in last_trades:
            lines.append(
                f"| {t['symbol']} | {t['entry_bar_ts']} | {t['exit_bar_ts']} "
                f"| {t['net_pnl']} | {t['hold_bars']} |"
            )
    else:
        lines.append("_None yet._")

    lines += ["", "## Red flags"]
    flags = []
    if funding_gaps > 0:
        flags.append(f"{funding_gaps} funding accrual(s) had no rate available (flagged, not zeroed silently).")
    if deferred_bar_ts:
        flags.append(f"Latest bar {deferred_bar_ts} deferred — T+1 open not yet available (expected for the newest bar).")
    if summary["closed_trades"] == 0:
        flags.append("No closed trades yet; performance metrics are not meaningful.")
    if not flags:
        flags.append("None.")
    for f in flags:
        lines.append(f"- {f}")
    lines.append("")
    return "\n".join(lines)
