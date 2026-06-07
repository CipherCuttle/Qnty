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
from quantbot.paper import BASELINE_LABEL, BASELINE_NOT_REPRODUCED, PAPER_ENGINE_VERSION

DISCLAIMER = (
    "SIMULATION ONLY. These are paper fills on a frozen research observer. This is NOT "
    "live trading, NOT realized money, and a positive paper result does NOT prove "
    "real-money profitability or deployment readiness. This is the "
    f"'{BASELINE_LABEL}' baseline, NOT faithful Package V2 vol-normalized PnL: "
    f"{BASELINE_NOT_REPRODUCED}"
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
    funding_gaps: int = 0,
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
        "status": "OK",
        "baseline_label": config.get("baseline_label", BASELINE_LABEL),
        "baseline_note": BASELINE_NOT_REPRODUCED,
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
        # Funding-gap exposure must be visible in the summary, not only the receipt (Blocker 6).
        "funding_gap": funding_gaps > 0,
        "funding_gap_count": int(funding_gaps),
        "current_verdict": verdict,
        "disclaimer": DISCLAIMER,
    }


def aborted_summary(config: dict[str, Any], code: str, reason: str) -> dict[str, Any]:
    """Summary written when a run aborts at the freshness/divergence gate.

    Marked ABORTED so no downstream reader mistakes a stale/aborted run for a FLAT result.
    """
    return {
        "schema_version": config["schema_version"],
        "status": "ABORTED",
        "baseline_label": config.get("baseline_label", BASELINE_LABEL),
        "abort_code": code,
        "abort_reason": reason,
        "forward_start_ts": config["forward_start_ts"],
        "aborted_at": _now_utc(),
        "current_verdict": f"ABORTED — {code} (no ledger rows written this run)",
        "disclaimer": DISCLAIMER,
    }


def corrupt_summary(config: dict[str, Any], failures: list[str]) -> dict[str, Any]:
    """Summary written when post-mutation reconcile fails (Blocker 1).

    Marked CORRUPT_LEDGER so no reader mistakes a partial/corrupt ledger for an OK or FLAT
    result. The watermark/state is NOT advanced when this is written; the reconcile failures
    are surfaced here (and in the receipt/provenance) so the corruption is never silent.
    """
    return {
        "schema_version": config["schema_version"],
        "status": "CORRUPT_LEDGER",
        "baseline_label": config.get("baseline_label", BASELINE_LABEL),
        "forward_start_ts": config["forward_start_ts"],
        "detected_at": _now_utc(),
        "reconcile_failures": list(failures),
        "reconcile_failure_count": len(failures),
        "current_verdict": (
            f"CORRUPT_LEDGER — {len(failures)} reconcile failure(s); watermark NOT advanced, "
            f"no OK published"
        ),
        "disclaimer": DISCLAIMER,
    }


def no_eligible_bars_summary(config: dict[str, Any], reason: str) -> dict[str, Any]:
    """Summary for a controlled NO_ELIGIBLE_BARS_YET no-op run (Blocker 3).

    The observer output validated clean but no bar has reached forward_start_ts. This is NOT
    an OK accounting run: no ledger rows were written and no position state/watermark was
    created or mutated. Clearly labeled so a fresh future-boundary re-init can never be
    mistaken for a FLAT/zero result.
    """
    return {
        "schema_version": config["schema_version"],
        "status": "NO_ELIGIBLE_BARS_YET",
        "baseline_label": config.get("baseline_label", BASELINE_LABEL),
        "forward_start_ts": config["forward_start_ts"],
        "checked_at": _now_utc(),
        "bars_elapsed": 0,
        "reason": reason,
        "current_verdict": (
            "NO_ELIGIBLE_BARS_YET — no bar has reached forward_start_ts; no ledger rows "
            "written and no state/watermark created"
        ),
        "disclaimer": DISCLAIMER,
    }


def _digest(path: Path) -> str:
    return sha256_file(path) if path.exists() else "absent"


def build_provenance(
    forward_obs_dir: Path,
    paper_dir: Path,
    data_dir: Path,
    symbols: list[str],
    config: dict[str, Any] | None = None,
    aborted: bool = False,
    abort_code: str | None = None,
    abort_reason: str | None = None,
    status: str | None = None,
    reconcile_failures: list[str] | None = None,
    output_digest_overrides: dict[str, str] | None = None,
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
        "paper_signal_snapshots.jsonl",
        "paper_position_state.json",
        "paper_pnl_summary.json",
    ]
    outputs = {name: _digest(paper_dir / name) for name in output_files}
    # The OK summary is published LAST (Blocker 1), so on a successful run it is not yet on disk
    # when provenance is built. The caller passes the digest of the exact in-memory summary
    # bytes here so provenance pins the NEW summary, not the stale prior file.
    if output_digest_overrides:
        outputs.update(output_digest_overrides)

    record: dict[str, Any] = {
        "run_ts": _now_utc(),
        "engine_version": PAPER_ENGINE_VERSION,
        # baseline_label must appear in every provenance artifact (Blocker 6 / schema § 8).
        "baseline_label": (config or {}).get("baseline_label", BASELINE_LABEL),
        "git_sha": git_sha(),
        "status": status or ("ABORTED" if aborted else "OK"),
        "input_digests": inputs,
        "output_digests": outputs,
    }
    if aborted:
        record["abort_code"] = abort_code
        record["abort_reason"] = abort_reason
    if reconcile_failures is not None:
        record["reconcile_failures"] = list(reconcile_failures)
        record["reconcile_failure_count"] = len(reconcile_failures)
    return record


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
        f"- Baseline: `{summary.get('baseline_label', BASELINE_LABEL)}` "
        "(fixed-notional active-symbol baseline — NOT V2 volnorm live/PnL approval)",
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


def render_aborted_receipt(summary: dict[str, Any], code: str, reason: str) -> str:
    """Loud receipt for an aborted run: no ledger rows were written this pass."""
    return "\n".join(
        [
            "# Paper PnL v1 — Receipt (ABORTED)",
            "",
            f"> **{summary['disclaimer']}**",
            "",
            f"## 🛑 RUN ABORTED — {code}",
            "",
            f"- Aborted (UTC): {summary.get('aborted_at', _now_utc())}",
            f"- Reason: {reason}",
            f"- forward_start_ts: {summary['forward_start_ts']}",
            "- No fills/trades/equity/positions/funding/snapshot rows were written this run.",
            "- The observer output was stale, missing, malformed, or diverged from a frozen "
            "snapshot. This was NOT treated as a FLAT result.",
            "",
        ]
    )


def render_corrupt_receipt(summary: dict[str, Any], failures: list[str]) -> str:
    """Loud receipt for a CORRUPT_LEDGER run: reconcile failed, watermark NOT advanced."""
    lines = [
        "# Paper PnL v1 — Receipt (CORRUPT_LEDGER)",
        "",
        f"> **{summary['disclaimer']}**",
        "",
        "## 🛑 RUN FAILED CLOSED — CORRUPT_LEDGER",
        "",
        f"- Detected (UTC): {summary.get('detected_at', _now_utc())}",
        f"- forward_start_ts: {summary['forward_start_ts']}",
        f"- Reconcile failures: {summary.get('reconcile_failure_count', len(failures))}",
        "- The position state/watermark was NOT advanced and NO OK summary was published.",
        "- Existing partial/corrupt ledger rows were NOT silently normalized into an OK or "
        "FLAT result.",
        "",
        "### Reconcile failures",
    ]
    for f in failures:
        lines.append(f"- {f}")
    lines.append("")
    return "\n".join(lines)


def render_no_eligible_receipt(summary: dict[str, Any], reason: str) -> str:
    """Receipt for a controlled NO_ELIGIBLE_BARS_YET no-op: nothing written, nothing mutated."""
    return "\n".join(
        [
            "# Paper PnL v1 — Receipt (NO_ELIGIBLE_BARS_YET)",
            "",
            f"> **{summary['disclaimer']}**",
            "",
            "## ⏳ NO ELIGIBLE BARS YET — controlled no-op",
            "",
            f"- Checked (UTC): {summary.get('checked_at', _now_utc())}",
            f"- forward_start_ts: {summary['forward_start_ts']}",
            f"- {reason}",
            "- No fills/trades/equity/positions/funding/snapshot rows were written, and the "
            "position state/watermark was NOT created or mutated.",
            "- This is NOT a FLAT/zero accounting result; no bar has reached forward_start_ts "
            "yet.",
            "",
        ]
    )
