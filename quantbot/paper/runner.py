"""Orchestration for one paper accounting run (idempotent, append-only).

Hardened evidence path (schema doc sections 9-10): before any ledger row is written we run
a hard freshness gate on the observer output and a divergence check against frozen consumed
signal snapshots. A failure of either aborts the run loudly, writes an ABORTED summary /
receipt / provenance entry, and leaves the append-only ledgers and state untouched.
"""

from __future__ import annotations

import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from quantbot.data.multi_asset_loader import load_all_ohlcv, SYMBOLS
from quantbot.data.funding_loader import load_all_funding
from quantbot.data.types import Bar
from quantbot.paper import forward_obs_dir as default_forward_obs_dir
from quantbot.paper import paper_output_dir as default_paper_output_dir
from quantbot.paper.config import load_config
from quantbot.paper.engine import new_state, run_engine
from quantbot.paper import freshness
from quantbot.paper import ledger
from quantbot.paper import provenance
from quantbot.paper import snapshots


def _now_utc_str() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _abort(
    out: Path,
    obs_dir: Path,
    data_dir: Path,
    config: dict[str, Any],
    code: str,
    reason: str,
) -> dict[str, Any]:
    """Persist an ABORTED summary/receipt/provenance entry without touching ledgers."""
    # Loud failure on stderr (journald captures this on the VM).
    print(f"[paper-pnl][ABORT] {code}: {reason}", file=sys.stderr, flush=True)

    summary = provenance.aborted_summary(config, code, reason)
    ledger.write_json(out / "paper_pnl_summary.json", summary)

    prov = provenance.build_provenance(obs_dir, out, data_dir, SYMBOLS, config=config,
                                        aborted=True, abort_code=code, abort_reason=reason)
    ledger.write_json(out / "paper_provenance.json", prov)
    ledger.append_rows(out / "paper_provenance_log.jsonl", [prov])

    receipt = provenance.render_aborted_receipt(summary, code, reason)
    (out / "paper_receipt.md").write_text(receipt, encoding="utf-8")
    return summary


def run_once(
    output_dir: Path | None = None,
    forward_obs_dir: Path | None = None,
    data_dir: Path = Path("data"),
    bars_by_symbol: dict[str, list[Bar]] | None = None,
    funding_df: Any | None = None,
    now: datetime | None = None,
) -> dict[str, Any]:
    """Run the paper engine once and persist outputs. Returns the summary dict.

    `now` (UTC) is injectable for deterministic freshness tests; defaults to wall clock.
    """
    out = output_dir or default_paper_output_dir()
    obs_dir = forward_obs_dir or default_forward_obs_dir()
    now = now or datetime.now(timezone.utc)

    config = load_config(out)
    freshness_cfg = config.get("freshness", {})
    forward_start_ts = config["forward_start_ts"]

    # --- inputs (read-only) ---
    obs_path = obs_dir / "observation_log.json"
    # A malformed observation_log.json must NOT raise an uncaught JSONDecodeError before the
    # gate (which would skip the ABORTED artifacts); convert it to a controlled abort.
    try:
        obs_log = ledger.read_json(obs_path, default={})
    except (json.JSONDecodeError, ValueError) as exc:
        return _abort(
            out, obs_dir, data_dir, config,
            "MALFORMED_OBSERVATION_LOG",
            f"observation_log.json is not valid JSON: {exc}",
        )

    # === HARD FRESHNESS GATE (before any ledger write) ===
    fresh = freshness.check_freshness(
        obs_path, obs_log, obs_dir, now, freshness_cfg, forward_start_ts=forward_start_ts
    )
    if fresh.aborted:
        return _abort(out, obs_dir, data_dir, config, fresh.code, fresh.reason)

    per_bar_obs = obs_log.get("per_bar_obs", [])
    forward_obs = [o for o in per_bar_obs if o.get("timestamp", "") >= forward_start_ts]

    # === SIGNAL SNAPSHOT DIVERGENCE GATE ===
    existing_snapshots = snapshots.read_snapshots(out)
    divergence = snapshots.check_divergence(existing_snapshots, forward_obs)
    if divergence:
        return _abort(out, obs_dir, data_dir, config, "SIGNAL_SNAPSHOT_DIVERGENCE", divergence)

    if bars_by_symbol is None:
        bars_by_symbol = load_all_ohlcv()
    if funding_df is None:
        funding_df = load_all_funding()

    # --- state ---
    state_path = out / "paper_position_state.json"
    state = ledger.read_json(state_path, default=None) or new_state(
        float(config["initial_equity_usd"])
    )

    # --- engine ---
    result = run_engine(config, per_bar_obs, bars_by_symbol, funding_df, state)

    # --- persist new rows idempotently (ids dedupe overlap) ---
    # CRASH-SAFE ORDER (Blocker 4): the bar accounting rows (fills/trades/funding/positions/
    # equity) are committed BEFORE the consumed-signal snapshot for that bar, and the state
    # watermark is written LAST as the commit marker. Therefore:
    #   - a committed snapshot for a bar implies its equity/ledger rows are also committed
    #     (no orphan snapshot can report success), and
    #   - a crash before the state write leaves the watermark un-advanced, so the next run
    #     reprocesses the bar and idempotently completes any half-written ledger.
    ledger.append_new(out / "paper_fills.jsonl", result.fills, "fill_id")
    ledger.append_new(out / "paper_trades.jsonl", result.trades, "trade_id")
    ledger.append_new(out / "paper_funding.jsonl", result.funding, "funding_id")
    # positions/equity are per-bar snapshots keyed by bar_ts; the watermark guarantees a
    # bar is snapshotted at most once, so a plain id-keyed append stays idempotent.
    ledger.append_new(out / "paper_positions.jsonl", result.positions, "bar_ts")
    ledger.append_new(out / "paper_equity.jsonl", result.equity, "bar_ts")

    # --- freeze consumed signal snapshots AFTER the bar accounting rows are committed ---
    processed_bar_ts = {e["bar_ts"] for e in result.equity}
    existing_snapshot_ids = {
        s["snapshot_id"] for s in existing_snapshots if "snapshot_id" in s
    }
    source_mtime = obs_path.stat().st_mtime if obs_path.exists() else None
    new_snapshots = snapshots.build_snapshots(
        forward_obs, processed_bar_ts, existing_snapshot_ids, source_mtime, _now_utc_str()
    )
    ledger.append_new(out / snapshots.SNAPSHOT_FILE, new_snapshots, "snapshot_id")

    # state (watermark) LAST — commit marker for the whole bar batch.
    ledger.write_json(state_path, state)

    # --- summary + provenance + receipt over the FULL ledgers ---
    all_trades = ledger.read_jsonl(out / "paper_trades.jsonl")
    all_equity = ledger.read_jsonl(out / "paper_equity.jsonl")
    all_funding = ledger.read_jsonl(out / "paper_funding.jsonl")
    funding_gaps = sum(1 for f in all_funding if not f.get("rate_available", True))

    summary = provenance.compute_summary(
        config,
        all_trades,
        all_equity,
        state["open_positions"],
        state["bars_elapsed"],
        funding_gaps=funding_gaps,
    )
    ledger.write_json(out / "paper_pnl_summary.json", summary)

    prov = provenance.build_provenance(obs_dir, out, data_dir, SYMBOLS, config=config)
    ledger.write_json(out / "paper_provenance.json", prov)
    ledger.append_rows(out / "paper_provenance_log.jsonl", [prov])

    receipt = provenance.render_receipt(
        summary,
        last_trades=all_trades[-5:],
        funding_gaps=funding_gaps,
        deferred_bar_ts=result.deferred_bar_ts,
    )
    (out / "paper_receipt.md").write_text(receipt, encoding="utf-8")

    return summary
