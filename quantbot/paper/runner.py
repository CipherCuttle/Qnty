"""Orchestration for one paper accounting run (idempotent, append-only).

Hardened evidence path (schema doc sections 9-10): before any ledger row is written we run
a hard freshness gate on the observer output and a divergence check against frozen consumed
signal snapshots. A failure of either aborts the run loudly, writes an ABORTED summary /
receipt / provenance entry, and leaves the append-only ledgers and state untouched.
"""

from __future__ import annotations

import hashlib
import json
import os
import sys
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from quantbot.data.multi_asset_loader import load_all_ohlcv, SYMBOLS
from quantbot.data.funding_loader import load_all_funding
from quantbot.data.types import Bar
from quantbot.paper import forward_obs_dir as default_forward_obs_dir
from quantbot.paper import paper_output_dir as default_paper_output_dir
from quantbot.paper.config import ConfigContractError, load_config
from quantbot.paper.engine import new_state, run_engine
from quantbot.paper import freshness
from quantbot.paper import ledger
from quantbot.paper.ledger import LedgerCorruptionError
from quantbot.paper import provenance
from quantbot.paper import snapshots
from quantbot.paper.reconcile import check_existing_ledgers, reconcile


def _now_utc_str() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


SUMMARY_FILE = "paper_pnl_summary.json"
STAGED_SUMMARY_GLOB = ".paper_pnl_summary.json.*.preflight_previous"


def _stage_previous_summary(out: Path, run_id: str) -> tuple[Path | None, list[str]]:
    """Move the prior authoritative summary aside without reading it.

    The old summary must still be schema-validated, but no persisted artifact may be read before
    RUNNING is visible. An atomic rename removes any stale OK from the authoritative path without
    parsing it; after RUNNING is written, the health gate validates this staged copy. Any staged
    copies left by an interrupted prior run are also validated by the next run.
    """
    staged = out / f".paper_pnl_summary.json.{run_id}.preflight_previous"
    try:
        os.replace(out / SUMMARY_FILE, staged)
    except FileNotFoundError:
        return None, []
    except OSError as exc:
        return None, [
            f"{SUMMARY_FILE} could not be staged before preflight "
            f"({type(exc).__name__}: {exc}); refusing to leave prior status unverified"
        ]
    return staged, []


def _staged_summaries(out: Path) -> tuple[Path, ...]:
    """Return every prior summary staged by this or an interrupted earlier run."""
    try:
        return tuple(sorted(out.glob(STAGED_SUMMARY_GLOB)))
    except OSError as exc:
        raise LedgerCorruptionError(
            f"could not enumerate staged prior summaries ({type(exc).__name__}: {exc})"
        ) from exc


def _cleanup_staged_summaries(paths: tuple[Path, ...]) -> None:
    """Best-effort cleanup after the prior summaries have been validated and handled."""
    for path in paths:
        try:
            path.unlink(missing_ok=True)
        except OSError:
            # A leftover validated copy is harmless and will be revalidated next run.
            pass


def _write_preflight_marker(
    out: Path, config: dict[str, Any], run_id: str, started_at: str
) -> None:
    """Invalidate any stale `OK` by writing the authoritative RUNNING preflight marker (Blocker 1).

    This is the FIRST summary write of a run, performed BEFORE any abort/corrupt publication can
    fail (i.e. before the `_corrupt`/`_abort`/`_no_eligible_bars` publications and before any
    ledger/snapshot/state mutation or persisted-artifact read). The prior summary is atomically
    staged without parsing first, then validated by the health gate only after this marker is
    visible. If a later gate/publication fails, the visible status stays RUNNING — never the
    superseded OK. Atomic write (temp + os.replace).
    """
    marker = provenance.running_summary(config, run_id, started_at, "", phase="preflight")
    ledger.write_json_atomic(out / SUMMARY_FILE, marker)


def _invalidate_stale_ok_on_config_error(out: Path, run_id: str, started_at: str) -> None:
    """Supersede any stale `OK` when the config itself cannot be loaded (Blocker 1).

    The invalid config defines the output contract, so no valid summary can be built and the CLI
    exits 3 writing nothing for a first-run config error. But if a summary already exists (e.g. a
    previous `OK`), it MUST NOT remain visible after the config later goes missing/malformed.
    Only overwrite an EXISTING summary — never create one in a fresh dir — so the exit-3
    "no writes" contract is preserved for first-run config errors.
    """
    summary_path = out / SUMMARY_FILE
    if not summary_path.exists():
        return
    ledger.write_json_atomic(
        summary_path, provenance.config_error_preflight_marker(run_id, started_at)
    )


def _sha256_hex(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _terminal_digests(summary_bytes: bytes, receipt_bytes: bytes) -> dict[str, str]:
    """Provenance output-digest overrides for a terminal (non-OK) publication (Blocker 1).

    The terminal summary + receipt are published AFTER provenance is generated, so provenance
    must pin the digests of their exact in-memory bytes rather than the preceding RUNNING marker
    / stale receipt on disk. The state is NOT written on a terminal run, so its on-disk digest is
    already the correct final value and is not overridden here.
    """
    return {
        "paper_pnl_summary.json": _sha256_hex(summary_bytes),
        "paper_receipt.md": _sha256_hex(receipt_bytes),
    }


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

    # Build the terminal summary + receipt in memory FIRST, then pin THEIR digests into
    # provenance (Blocker 1). Digesting from disk would record the preceding RUNNING preflight
    # marker, not this ABORTED summary. Publish provenance + receipt, then the summary LAST.
    summary = provenance.aborted_summary(config, code, reason)
    receipt = provenance.render_aborted_receipt(summary, code, reason)
    summary_bytes = ledger.json_bytes(summary)
    receipt_bytes = receipt.encode("utf-8")
    prov = provenance.build_provenance(
        obs_dir, out, data_dir, SYMBOLS, config=config,
        aborted=True, abort_code=code, abort_reason=reason,
        output_digest_overrides=_terminal_digests(summary_bytes, receipt_bytes),
    )
    # Atomic writes so a crash mid-publish never leaves a half-written ABORTED artifact.
    ledger.write_json_atomic(out / "paper_provenance.json", prov)
    ledger.append_rows(out / "paper_provenance_log.jsonl", [prov])
    ledger.write_bytes_atomic(out / "paper_receipt.md", receipt_bytes)
    ledger.write_bytes_atomic(out / "paper_pnl_summary.json", summary_bytes)
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

    # In-memory summary + receipt first, then pin their digests into provenance (Blocker 1):
    # provenance must digest this CORRUPT_LEDGER terminal summary, not the preceding RUNNING marker.
    summary = provenance.corrupt_summary(config, failures)
    receipt = provenance.render_corrupt_receipt(summary, failures)
    summary_bytes = ledger.json_bytes(summary)
    receipt_bytes = receipt.encode("utf-8")
    prov = provenance.build_provenance(
        obs_dir, out, data_dir, SYMBOLS, config=config,
        status="CORRUPT_LEDGER", reconcile_failures=failures,
        output_digest_overrides=_terminal_digests(summary_bytes, receipt_bytes),
    )
    ledger.write_json_atomic(out / "paper_provenance.json", prov)
    ledger.append_rows(out / "paper_provenance_log.jsonl", [prov])
    ledger.write_bytes_atomic(out / "paper_receipt.md", receipt_bytes)
    ledger.write_bytes_atomic(out / "paper_pnl_summary.json", summary_bytes)
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

    # In-memory summary + receipt first, then pin their digests into provenance (Blocker 1).
    summary = provenance.no_eligible_bars_summary(config, reason)
    receipt = provenance.render_no_eligible_receipt(summary, reason)
    summary_bytes = ledger.json_bytes(summary)
    receipt_bytes = receipt.encode("utf-8")
    prov = provenance.build_provenance(
        obs_dir, out, data_dir, SYMBOLS, config=config, status="NO_ELIGIBLE_BARS_YET",
        output_digest_overrides=_terminal_digests(summary_bytes, receipt_bytes),
    )
    ledger.write_json_atomic(out / "paper_provenance.json", prov)
    ledger.append_rows(out / "paper_provenance_log.jsonl", [prov])
    ledger.write_bytes_atomic(out / "paper_receipt.md", receipt_bytes)
    ledger.write_bytes_atomic(out / "paper_pnl_summary.json", summary_bytes)
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

    run_id = uuid.uuid4().hex
    started_at = _now_utc_str()

    # === CONFIG (fail closed; never leave a stale OK visible) =========================
    # The config defines the output contract, so a missing/malformed config cannot build a valid
    # summary and the CLI exits 3 (CONFIG_ERROR) writing nothing for a FIRST-run config error.
    # But a previously-visible `OK` summary must NOT survive a now-broken config (Blocker 1), so
    # before re-raising we supersede an EXISTING summary with a minimal RUNNING preflight marker.
    try:
        config = load_config(out)
    except ConfigContractError:
        _invalidate_stale_ok_on_config_error(out, run_id, started_at)
        raise
    freshness_cfg = config.get("freshness", {})
    forward_start_ts = config["forward_start_ts"]

    # Atomically move the old summary aside WITHOUT reading it, then publish RUNNING before
    # any persisted-artifact read. The staged prior summary remains available for the health
    # gate's status-specific schema validation after stale OK has already been superseded.
    _, stage_failures = _stage_previous_summary(out, run_id)
    _write_preflight_marker(out, config, run_id, started_at)

    # === EXISTING-LEDGER HEALTH GATE (before ANY ledger mutation OR healthy no-op) =====
    # Blocker 2/3: check the already-persisted ledgers FIRST. A malformed JSONL ledger or a
    # pre-existing reconcile failure (e.g. an orphan fill/snapshot left by a crashed prior run)
    # must fail closed as CORRUPT_LEDGER here — before we write any new snapshot/row, before a
    # NO_ELIGIBLE_BARS_YET no-op, and before the divergence gate — so existing corruption can
    # never be masked as a benign no-op/divergence or silently overwritten with fresh rows.
    # These are pure READS of the existing artifacts. The prior summary is read from its staged
    # path so malformed/partial status evidence is still caught without ever reading it before
    # the authoritative RUNNING marker.
    try:
        staged_summaries = _staged_summaries(out)
        existing_failures = stage_failures + check_existing_ledgers(
            out, prior_summary_paths=staged_summaries
        )
    except (LedgerCorruptionError, OSError) as exc:
        staged_summaries = ()
        existing_failures = stage_failures + [str(exc)]

    if existing_failures:
        summary = _corrupt(out, obs_dir, data_dir, config, existing_failures)
        _cleanup_staged_summaries(staged_summaries)
        return summary
    _cleanup_staged_summaries(staged_summaries)

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
    # The existing-ledger health gate above already validated paper_position_state.json's
    # parse AND shape (fail-closed CORRUPT_LEDGER on a `{}`/partial/corrupt state), so this read
    # cannot traceback or silently reinitialize a malformed state. read_state_obj returns None
    # ONLY when the file is genuinely absent (first run); a present-but-empty `{}` would have
    # already failed the health gate (Blocker 2).
    state_path = out / "paper_position_state.json"
    state = ledger.read_state_obj(state_path) or new_state(
        float(config["initial_equity_usd"])
    )

    # --- engine ---
    # The authoritative RUNNING marker was already written in preflight (Blocker 1), before the
    # health/freshness/divergence gates — so the visible status has been RUNNING (never the stale
    # OK) since the start of this run. The mutations below proceed under that marker; only the
    # final `OK` summary (written last, as the commit marker) flips the visible status back to
    # OK, and only after the watermark + the full evidence bundle are already on disk.
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

    # === OK EVIDENCE PUBLICATION PROTOCOL (Blocker 1) =================================
    # A run may NEVER leave a final `status: OK` summary unless the WHOLE OK evidence bundle
    # (provenance + receipt + state/watermark + summary) was published successfully. Chosen
    # invariant (documented in schema doc § 5): paper_pnl_summary.json is the authoritative
    # current status, and the FINAL `OK` summary write is the single commit marker. Sequence:
    #   1. Build the entire bundle IN MEMORY first. If any content generation raises, nothing
    #      new is published; the on-disk status is still RUNNING (set above) — never a false OK.
    #   2. Serialize the summary to its exact on-disk bytes and pin THAT digest into provenance,
    #      so provenance reflects the new summary even though the summary is written last.
    #   3. Publish provenance + receipt, THEN write the state/watermark, THEN the `OK` summary
    #      LAST. Writing state BEFORE the final OK summary closes the Codex blocker where a
    #      state-write failure left an already-OK summary: now if the state write fails, the
    #      visible status is still RUNNING. If the very last OK-summary write fails, the state
    #      may be advanced but the visible status is RUNNING (not OK); the next run finds no new
    #      bars to process, re-runs the publication, and self-heals to OK. In every failure case
    #      the visible authoritative status is RUNNING/ABORTED/CORRUPT_LEDGER — never stale OK.
    # --- 1. build the whole bundle in memory (no writes yet) ---
    # The post-reconcile re-reads can themselves fail closed (PermissionError / other OSError /
    # bad UTF-8 / non-object row) — read_jsonl normalizes those to LedgerCorruptionError. That
    # must NOT propagate as a traceback after RUNNING was written (Blocker 4): convert it to a
    # CORRUPT_LEDGER publication (CLI exit 4). The state/watermark is not written below, so the
    # visible status becomes CORRUPT_LEDGER (never OK) and the next run reprocesses idempotently.
    try:
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
        receipt = provenance.render_receipt(
            summary,
            last_trades=all_trades[-5:],
            funding_gaps=funding_gaps,
            deferred_bar_ts=result.deferred_bar_ts,
        )
        # 2. exact on-disk bytes + digests for the artifacts published AFTER provenance, so
        # provenance pins the NEW summary AND the NEW state (written last / second-to-last) and
        # the receipt — never the stale prior files / "absent" state on a first run (Blocker 1).
        summary_bytes = ledger.json_bytes(summary)
        receipt_bytes = receipt.encode("utf-8")
        state_bytes = ledger.json_bytes(state)
        prov = provenance.build_provenance(
            obs_dir, out, data_dir, SYMBOLS, config=config,
            output_digest_overrides={
                "paper_pnl_summary.json": _sha256_hex(summary_bytes),
                "paper_position_state.json": _sha256_hex(state_bytes),
                "paper_receipt.md": _sha256_hex(receipt_bytes),
            },
        )
    except (LedgerCorruptionError, OSError) as exc:
        return _corrupt(
            out, obs_dir, data_dir, config,
            [f"persisted-artifact read failed while building the OK evidence bundle "
             f"({type(exc).__name__}: {exc})"],
        )

    # --- 3. publish: provenance + receipt, then state, then the OK summary LAST ---
    # The receipt/state are written from the EXACT bytes whose digests were pinned in provenance
    # above (write_text_atomic / write_json_atomic emit byte-identical content to receipt_bytes /
    # state_bytes), so provenance stays a faithful manifest of the committed files.
    ledger.write_json_atomic(out / "paper_provenance.json", prov)
    ledger.append_rows(out / "paper_provenance_log.jsonl", [prov])
    ledger.write_text_atomic(out / "paper_receipt.md", receipt)
    # state (watermark) is written BEFORE the final OK summary so a state-write failure leaves
    # the visible status at RUNNING (not OK). The OK summary is the single commit marker.
    ledger.write_json_atomic(state_path, state)
    # The OK summary is the LAST evidence write — an atomic rename, so the final summary path is
    # only ever observed as fully-old (RUNNING) or the complete OK commit, never half-written.
    # It supersedes the RUNNING marker only now that state + provenance + receipt are on disk.
    ledger.write_bytes_atomic(out / "paper_pnl_summary.json", summary_bytes)

    return summary
