"""Orchestration for one paper accounting run (idempotent, append-only)."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from quantbot.data.multi_asset_loader import load_all_ohlcv, SYMBOLS
from quantbot.data.funding_loader import load_all_funding
from quantbot.data.types import Bar
from quantbot.paper import forward_obs_dir as default_forward_obs_dir
from quantbot.paper import paper_output_dir as default_paper_output_dir
from quantbot.paper.config import load_config
from quantbot.paper.engine import new_state, run_engine
from quantbot.paper import ledger
from quantbot.paper import provenance


def run_once(
    output_dir: Path | None = None,
    forward_obs_dir: Path | None = None,
    data_dir: Path = Path("data"),
    bars_by_symbol: dict[str, list[Bar]] | None = None,
    funding_df: Any | None = None,
) -> dict[str, Any]:
    """Run the paper engine once and persist outputs. Returns the summary dict."""
    out = output_dir or default_paper_output_dir()
    obs_dir = forward_obs_dir or default_forward_obs_dir()

    config = load_config(out)

    # --- inputs (read-only) ---
    obs_log = ledger.read_json(obs_dir / "observation_log.json", default={})
    per_bar_obs = obs_log.get("per_bar_obs", []) if isinstance(obs_log, dict) else []

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
    ledger.append_new(out / "paper_fills.jsonl", result.fills, "fill_id")
    ledger.append_new(out / "paper_trades.jsonl", result.trades, "trade_id")
    ledger.append_new(out / "paper_funding.jsonl", result.funding, "funding_id")
    # positions/equity are per-bar snapshots keyed by bar_ts; the watermark guarantees a
    # bar is snapshotted at most once, so a plain id-keyed append stays idempotent.
    ledger.append_new(out / "paper_positions.jsonl", result.positions, "bar_ts")
    ledger.append_new(out / "paper_equity.jsonl", result.equity, "bar_ts")
    ledger.write_json(state_path, state)

    # --- summary + provenance + receipt over the FULL ledgers ---
    all_trades = ledger.read_jsonl(out / "paper_trades.jsonl")
    all_equity = ledger.read_jsonl(out / "paper_equity.jsonl")
    all_funding = ledger.read_jsonl(out / "paper_funding.jsonl")
    funding_gaps = sum(1 for f in all_funding if not f.get("rate_available", True))

    summary = provenance.compute_summary(
        config, all_trades, all_equity, state["open_positions"], state["bars_elapsed"]
    )
    ledger.write_json(out / "paper_pnl_summary.json", summary)

    prov = provenance.build_provenance(obs_dir, out, data_dir, SYMBOLS)
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
