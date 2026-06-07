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
from quantbot.paper.reconcile import check_existing_ledgers, reconcile


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


def _corrupt(
    out: Path,
    obs_dir: Path,
    data_dir: Path,
    config: dict[str, Any],
    failures: list[str],
) -> dict[str, Any]:
    """Persist a CORRUPT_LEDGER summary/receipt/provenance; never advance the watermark.

    Called when post-mutation reconcile fails (Blocker 1). The state/watermark is NOT written,
    so the next run reprocesses; the reconcile failures are surfaced loudly here so a partial/
    corrupt ledger can never be silently normalized into OK.
    """
    print(
        f"[paper-pnl][CORRUPT_LEDGER] {len(failures)} reconcile failure(s); watermark NOT "
        f"advanced, no OK published",
        file=sys.stderr,
        flush=True,
    )
    for f in failures:
        print(f"[paper-pnl][CORRUPT_LEDGER]   - {f}", file=sys.stderr, flush=True)

    summary = provenance.corrupt_summary(config, failures)
    ledger.write_json(out / "paper_pnl_summary.json", summary)

    prov = provenance.build_provenance(
        obs_dir, out, data_dir, SYMBOLS, config=config,
        status="CORRUPT_LEDGER", reconcile_failures=failures,
    )
    ledger.write_json(out / "paper_provenance.json", prov)
    ledger.append_rows(out / "paper_provenance_log.jsonl", [prov])

    receipt = provenance.render_corrupt_receipt(summary, failures)
    (out / "paper_receipt.md").write_text(receipt, encoding="utf-8")
    return summary


def _no_eligible_bars(
    out: Path,
    obs_dir: Path,
    data_dir: Path,
    config: dict[str, Any],
    reason: str,
) -> dict[str, Any]:
    """Persist a NO_ELIGIBLE_BARS_YET no-op summary/receipt/provenance (Blocker 3).

    No ledger rows are written and NO position state/watermark is created or mutated. The run
    is clearly labeled so a fresh future-boundary re-init can never be mistaken for a FLAT/zero
    accounting result.
    """
    print(f"[paper-pnl][NO_ELIGIBLE_BARS_YET] {reason}", file=sys.stderr, flush=True)

    summary = provenance.no_eligible_bars_summary(config, reason)
    ledger.write_json(out / "paper_pnl_summary.json", summary)

    prov = provenance.build_provenance(
        obs_dir, out, data_dir, SYMBOLS, config=config, status="NO_ELIGIBLE_BARS_YET",
    )
    ledger.write_json(out / "paper_provenance.json", prov)
    ledger.append_rows(out / "paper_provenance_log.jsonl", [prov])

    receipt = provenance.render_no_eligible_receipt(summary, reason)
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

    # === EXISTING-LEDGER HEALTH GATE (before ANY mutation OR healthy no-op) ===========
    # Blocker 2/3: check the already-persisted ledgers FIRST. A malformed JSONL ledger or a
    # pre-existing reconcile failure (e.g. an orphan fill/snapshot left by a crashed prior run)
    # must fail closed as CORRUPT_LEDGER here — before we write any new snapshot/row, before a
    # NO_ELIGIBLE_BARS_YET no-op, and before the divergence gate — so existing corruption can
    # never be masked as a benign no-op/divergence or silently overwritten with fresh rows.
    existing_failures = check_existing_ledgers(out)
    if existing_failures:
        return _corrupt(out, obs_dir, data_dir, config, existing_failures)

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

    # Controlled no-op (Blocker 3): the file validated clean but no bar has reached
    # forward_start_ts. Write a clearly-labeled NO_ELIGIBLE_BARS_YET status WITHOUT creating
    # or mutating any ledger row or the position state/watermark, then return before the
    # engine runs. This must never be reported as a normal OK accounting run.
    if fresh.code == "NO_ELIGIBLE_BARS_YET":
        return _no_eligible_bars(out, obs_dir, data_dir, config, fresh.reason)

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
    # CRASH-SAFE ORDER (Blocker 1): the immutable consumed-signal snapshot for a bar is
    # frozen FIRST (it carries the bar_commit_id and the full source digest), THEN the bar
    # accounting rows (fills/trades/funding/positions/equity) that must agree with it, and
    # the state watermark is written LAST as the commit marker. Therefore:
    #   - a bar can never have fills/trades/equity without a matching immutable snapshot for
    #     the exact consumed row (snapshot precedes them);
    #   - a crash AFTER the snapshot but BEFORE the accounting rows leaves an orphan snapshot
    #     with no equity, which reconcile fails on loudly (a partial bar never reconciles
    #     clean), and — because the snapshot is already frozen — if the rolling observer then
    #     recomputes that bar, the next run's divergence gate ABORTS instead of continuing;
    #   - a crash before the state write leaves the watermark un-advanced, so the next run
    #     reprocesses the bar and idempotently completes any half-written ledger.
    processed_bar_ts = {e["bar_ts"] for e in result.equity}
    existing_snapshot_ids = {
        s["snapshot_id"] for s in existing_snapshots if "snapshot_id" in s
    }
    source_mtime = obs_path.stat().st_mtime if obs_path.exists() else None
    new_snapshots = snapshots.build_snapshots(
        forward_obs,
        processed_bar_ts,
        existing_snapshot_ids,
        source_mtime,
        _now_utc_str(),
        config["engine_version"],
        config["config_hash"],
    )
    ledger.append_new(out / snapshots.SNAPSHOT_FILE, new_snapshots, "snapshot_id")

    ledger.append_new(out / "paper_fills.jsonl", result.fills, "fill_id")
    ledger.append_new(out / "paper_trades.jsonl", result.trades, "trade_id")
    ledger.append_new(out / "paper_funding.jsonl", result.funding, "funding_id")
    # positions/equity are per-bar snapshots keyed by bar_ts; the watermark guarantees a
    # bar is snapshotted at most once, so a plain id-keyed append stays idempotent.
    ledger.append_new(out / "paper_positions.jsonl", result.positions, "bar_ts")
    ledger.append_new(out / "paper_equity.jsonl", result.equity, "bar_ts")

    # === RECONCILE GATE BEFORE OK (Blocker 1) =========================================
    # The mutations above are on disk (idempotent appends), but a run may only emit OK if the
    # FULL ledger reconciles. Reconcile runs the internal invariants over everything just
    # written PLUS any pre-existing partial/corrupt rows. If it finds any error, fail closed:
    # write a CORRUPT_LEDGER summary/receipt/provenance, do NOT advance the watermark/state
    # (so the next run reprocesses), and return a non-OK status. An OK summary/receipt/
    # provenance is NEVER published ahead of this check, so a partial bar (e.g. an orphan fill
    # from a now-recomputed source row) can no longer slip through as OK.
    recon_failures = reconcile(out)
    if recon_failures:
        return _corrupt(out, obs_dir, data_dir, config, recon_failures)

    # --- summary + provenance + receipt over the FULL ledgers (BEFORE the state write) ---
    # The summary uses the in-memory `state` (open_positions/bars_elapsed); it does not need
    # the state file on disk. We compute and persist the summary/provenance/receipt FIRST so
    # that the state watermark is the very last mutation (Blocker 1, high-level rule 6).
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

    # state (watermark) is the FINAL mutation — the commit marker for the whole bar batch.
    # It is written ONLY after reconcile passed AND the summary/provenance/receipt were all
    # written successfully (Blocker 1). If any of those writes raises, the watermark is NOT
    # advanced, so the next run reprocesses the bar batch and idempotently re-publishes the
    # evidence. (The provenance digest of paper_position_state.json therefore reflects the
    # PRIOR run's state by one run; this is the deliberate cost of making the watermark the
    # strictly-last write, and self-heals on the next successful run.)
    ledger.write_json(state_path, state)

    return summary
