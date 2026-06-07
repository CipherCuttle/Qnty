"""Reconciliation invariants for the paper_pnl_v1 ledger.

Pure checks over the persisted ledgers. Returns a list of failure strings; empty == pass.
See docs/paper_pnl_v1_schema.md sections 3, 5, 6.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from quantbot.paper.config import load_config
from quantbot.paper import ledger
from quantbot.paper.ledger import LedgerCorruptionError

EPS = 1e-6

# Per-artifact shape contract for every append-only JSONL ledger (Blocker 2). Each row must be
# an object (read_jsonl) and pass a DEEP type check against this spec — required fields present,
# finite numbers where numbers are needed (no bool/NaN/inf/str), finite >= 0 where non-negative,
# non-empty strings where strings are needed, lists-of-strings where lists are needed, real
# bools, and enumerated side/kind values — otherwise the row is malformed/partial and fails
# closed as CORRUPT_LEDGER instead of KeyError'ing/TypeError'ing in the checks below or in the
# summary/receipt. The fields mirror exactly what the engine emits (quantbot/paper/engine.py)
# and what reconcile / the summary / the receipt index without `.get`. bar_commit_id
# well-formedness (16-hex) is left to the structural pass so it reports a per-row message; only
# its presence is required here (so empty/malformed ids surface there, not as a generic read
# error — see tests for the empty/`not-16-hex` cases). Spec keys: required / numeric / nonneg /
# strings / str_lists / bools / enums (see ledger.read_jsonl_validated).
LEDGER_JSONL_SCHEMAS: dict[str, dict[str, Any]] = {
    "paper_fills.jsonl": {
        "required": (
            "fill_id", "bar_commit_id", "signal_bar_ts", "fill_ts", "symbol",
            "side", "kind", "qty", "open_price", "fill_price", "slippage_bps", "fee", "backfill",
        ),
        "positive": ("qty", "open_price", "fill_price"),
        "nonneg": ("slippage_bps", "fee"),
        "strings": ("fill_id", "symbol"),
        "timestamps": ("signal_bar_ts", "fill_ts"),
        "bools": ("backfill",),
        "enums": {"side": frozenset({"BUY", "SELL"}), "kind": frozenset({"entry", "exit"})},
    },
    "paper_trades.jsonl": {
        "required": (
            "trade_id", "bar_commit_id", "symbol", "entry_fill_id", "exit_fill_id",
            "entry_bar_ts", "exit_bar_ts", "qty", "entry_price", "exit_price",
            "gross_pnl", "fees", "funding", "net_pnl", "hold_bars", "backfill",
        ),
        "positive": ("qty", "entry_price", "exit_price"),
        "numeric": ("gross_pnl", "funding", "net_pnl"),
        "nonneg": ("fees",),
        "nonneg_ints": ("hold_bars",),
        "strings": (
            "trade_id", "symbol", "entry_fill_id", "exit_fill_id",
        ),
        "timestamps": ("entry_bar_ts", "exit_bar_ts"),
        "bools": ("backfill",),
    },
    "paper_funding.jsonl": {
        "required": (
            "funding_id", "bar_ts", "bar_commit_id", "symbol", "window_start",
            "window_end", "notional_usd", "funding_rate", "funding_events",
            "rate_available", "funding_amount",
        ),
        "positive": ("notional_usd",),
        "numeric": ("funding_rate", "funding_amount"),
        "nonneg_ints": ("funding_events",),
        "strings": ("funding_id", "symbol"),
        "timestamps": ("bar_ts", "window_start", "window_end"),
        "bools": ("rate_available",),
    },
    "paper_positions.jsonl": {
        "required": ("bar_ts", "bar_commit_id", "open_symbols", "num_open", "gross_exposure_usd"),
        "nonneg": ("gross_exposure_usd",),
        "nonneg_ints": ("num_open",),
        "strings": (),
        "timestamps": ("bar_ts",),
        "str_lists": ("open_symbols",),
    },
    "paper_equity.jsonl": {
        "required": (
            "bar_ts", "bar_commit_id", "realized_gross_pnl", "unrealized_pnl",
            "funding_cum", "fees_cum", "equity", "drawdown", "num_open",
        ),
        "numeric": (
            "realized_gross_pnl", "unrealized_pnl", "funding_cum", "fees_cum",
            "equity",
        ),
        "nonneg": ("drawdown",),
        "nonneg_ints": ("num_open",),
        "strings": (),
        "timestamps": ("bar_ts",),
    },
    "paper_signal_snapshots.jsonl": {
        "required": (
            "snapshot_id", "bar_ts", "bar_commit_id", "bar_index", "active_symbols",
            "portfolio_heat", "heat_cap_triggered", "weighted_return",
            "source_observation_digest", "source_observation_mtime", "run_ts", "backfill",
        ),
        "numeric": (
            "portfolio_heat", "weighted_return", "source_observation_mtime",
        ),
        "nonneg_ints": ("bar_index",),
        "strings": ("snapshot_id", "source_observation_digest"),
        "timestamps": ("bar_ts", "run_ts"),
        "str_lists": ("active_symbols",),
        "bools": ("heat_cap_triggered", "backfill"),
    },
}

# Every append-only JSONL ledger that must be readable before a run may proceed (Blocker 2/3).
LEDGER_JSONL_FILES = tuple(LEDGER_JSONL_SCHEMAS)


def _read_ledger_validated(output_dir: Path, fname: str) -> list[dict[str, Any]]:
    """Read one JSONL ledger with parse + deep shape validation (fails closed, Blocker 2)."""
    return ledger.read_jsonl_validated(
        output_dir / fname,
        name=fname,
        spec=LEDGER_JSONL_SCHEMAS[fname],
    )

# bar_commit_id = sha256(...)[:16] (see quantbot/paper/snapshots.py) -> 16 lowercase hex
# chars. A missing/null/empty/malformed id must never be accepted (Blocker 2).
_HEXDIGITS = set("0123456789abcdef")


def _valid_commit_id(v: Any) -> bool:
    """True iff v is a well-formed 16-char lowercase-hex bar_commit_id.

    Rejects missing (None), empty, non-string, and malformed values so reconcile can never
    let a `None == None` comparison pass as agreement between artifacts (Blocker 2).
    """
    return isinstance(v, str) and len(v) == 16 and all(c in _HEXDIGITS for c in v)


def _dup_ids(rows: list[dict[str, Any]], key: str) -> list[str]:
    seen: set[str] = set()
    dups: list[str] = []
    for r in rows:
        v = str(r.get(key))
        if v in seen:
            dups.append(v)
        seen.add(v)
    return dups


def check_existing_ledgers(
    output_dir: Path, *, prior_summary_paths: tuple[Path, ...] = ()
) -> list[str]:
    """Fail-closed integrity + reconcile over the ALREADY-PERSISTED ledgers (Blocker 2/3).

    Run BEFORE any new ledger/snapshot/state mutation and before any healthy no-op
    (NO_ELIGIBLE_BARS_YET) or benign abort (e.g. signal-snapshot divergence) can be returned.
    A malformed JSONL ledger or any pre-existing reconcile failure (e.g. an orphan fill from a
    crashed prior run) is surfaced here so it can never be masked as a benign no-op/divergence
    or silently overwritten with fresh rows.

    Returns failure strings; empty == the existing ledgers are clean. Never raises on corrupt
    JSONL — a parse failure is captured as a failure string.
    """
    failures: list[str] = []
    # 1. Parse + shape integrity first: an unreadable/wrong-shape artifact can't be reconciled.
    #    Every JSONL row must be an object AND carry its required fields with finite numerics;
    #    the summary and position-state files must be objects of the right shape. Invalid UTF-8 /
    #    JSON / a non-object row, a structurally malformed/partial row (e.g. `{}`), a `{}`/partial
    #    summary or state all fail closed here (Blocker 2). If ANY artifact is corrupt we stop
    #    (do not attempt structural reconcile over partial reads).
    for fname in LEDGER_JSONL_FILES:
        try:
            _read_ledger_validated(output_dir, fname)
        except (LedgerCorruptionError, OSError) as exc:
            failures.append(str(exc))
    # The runner atomically stages the prior summary before publishing RUNNING, then passes the
    # staged path(s) here. This preserves status-shape validation without reading the old summary
    # before the authoritative preflight marker is visible.
    summary_paths = prior_summary_paths or (output_dir / "paper_pnl_summary.json",)
    for summary_path in summary_paths:
        try:
            ledger.read_summary_obj(summary_path)
        except (LedgerCorruptionError, OSError) as exc:
            failures.append(str(exc))
    # State: absent -> None (first run); present-but-`{}`/partial -> corrupt (never silently
    # reinitialized).
    try:
        ledger.read_state_obj(output_dir / "paper_position_state.json")
    except (LedgerCorruptionError, OSError) as exc:
        failures.append(str(exc))
    if failures:
        return failures
    # 2. Structural reconcile over the existing rows (all artifacts parsed cleanly above).
    failures.extend(reconcile(output_dir))
    return failures


def reconcile(output_dir: Path) -> list[str]:
    failures: list[str] = []
    config = load_config(output_dir)
    forward_start_ts = config["forward_start_ts"]
    initial_equity = float(config["initial_equity_usd"])

    # Reads fail CLOSED: any corrupt artifact (bad UTF-8/JSON, non-object row, malformed
    # summary) is returned as a single failure string rather than raised, so the runner's
    # post-mutation reconcile gate converts it to CORRUPT_LEDGER (exit 4) without a traceback
    # (Blocker 2). reconcile() therefore NEVER raises on corruption.
    try:
        fills = _read_ledger_validated(output_dir, "paper_fills.jsonl")
        trades = _read_ledger_validated(output_dir, "paper_trades.jsonl")
        equity = _read_ledger_validated(output_dir, "paper_equity.jsonl")
        funding = _read_ledger_validated(output_dir, "paper_funding.jsonl")
        positions = _read_ledger_validated(output_dir, "paper_positions.jsonl")
        snaps = _read_ledger_validated(output_dir, "paper_signal_snapshots.jsonl")
        summary = ledger.read_summary_obj(output_dir / "paper_pnl_summary.json")
    except (LedgerCorruptionError, OSError) as exc:
        return [str(exc)]

    # --- uniqueness / append-only ---
    for rows, key, name in [
        (fills, "fill_id", "fills"),
        (trades, "trade_id", "trades"),
        (funding, "funding_id", "funding"),
        (equity, "bar_ts", "equity"),
        (positions, "bar_ts", "positions"),
        (snaps, "snapshot_id", "snapshots"),
    ]:
        dups = _dup_ids(rows, key)
        if dups:
            failures.append(f"{name}: duplicate {key} values {dups[:5]}")

    # --- one frozen snapshot per consumed (equity) bar; never more than one per bar_ts ---
    snap_dup_ts = _dup_ids(snaps, "bar_ts")
    if snap_dup_ts:
        failures.append(f"snapshots: duplicate bar_ts values {snap_dup_ts[:5]}")
    snap_ts = {s.get("bar_ts") for s in snaps}
    equity_ts = {e["bar_ts"] for e in equity}
    for e in equity:
        if e["bar_ts"] not in snap_ts:
            failures.append(f"equity bar {e['bar_ts']} has no consumed-signal snapshot")
    # Orphan-snapshot guard (Blocker 4): a committed snapshot must have its bar accounting
    # (equity) row too. The crash-safe write order is snapshot-FIRST, then the bar accounting
    # rows, then the state watermark LAST; a clean run therefore always lands the equity row
    # for every snapshot. If an orphan snapshot exists, a crash/corruption left a snapshot
    # without its ledger — fail loudly instead of reporting success. (No PENDING marker is
    # written in v1; any orphan is a hard failure.)
    for s in snaps:
        if s.get("bar_ts") not in equity_ts:
            failures.append(
                f"snapshot {s.get('snapshot_id')} bar {s.get('bar_ts')} has no equity row "
                f"(orphan snapshot — crash/corruption between snapshot and equity writes)"
            )

    # --- per-bar atomic commit (Blocker 1 + Blocker 2) ---------------------------------
    # The snapshot is frozen FIRST and is the immutable source-of-truth for a bar. Every
    # accounting row (fills/trades/funding/positions/equity) for a processed bar must:
    #   (a) carry a WELL-FORMED bar_commit_id (mandatory — never null/empty/malformed), AND
    #   (b) have a matching frozen snapshot for that exact bar_ts, AND
    #   (c) carry the SAME bar_commit_id as that snapshot.
    # bar_commit_id is mandatory on every participating row, including the snapshot itself: a
    # `None == None` comparison must never pass as agreement (Blocker 2). A partial bar —
    # fills/equity written by a crash before the snapshot, rows left over from a now-recomputed
    # source row, or artifacts with the id stripped out — fails loudly here instead of
    # reconciling clean against changed/absent source evidence.
    for s in snaps:
        if not _valid_commit_id(s.get("bar_commit_id")):
            failures.append(
                f"snapshot {s.get('snapshot_id')} bar {s.get('bar_ts')} has missing/malformed "
                f"bar_commit_id {s.get('bar_commit_id')!r} (mandatory on every committed bar)"
            )
    commit_by_bar = {s.get("bar_ts"): s.get("bar_commit_id") for s in snaps}
    for rows, bar_key, id_key, name in [
        (fills, "signal_bar_ts", "fill_id", "fill"),
        (trades, "exit_bar_ts", "trade_id", "trade"),
        (funding, "bar_ts", "funding_id", "funding"),
        (positions, "bar_ts", "bar_ts", "positions"),
        (equity, "bar_ts", "bar_ts", "equity"),
    ]:
        for r in rows:
            bt = r.get(bar_key)
            rid = r.get(id_key)
            got = r.get("bar_commit_id")
            if not _valid_commit_id(got):
                failures.append(
                    f"{name} {rid} bar {bt} has missing/malformed bar_commit_id {got!r} "
                    f"(mandatory on every accounting row of a committed bar)"
                )
            if bt not in commit_by_bar:
                failures.append(
                    f"{name} {rid} bar {bt} has no consumed-signal snapshot "
                    f"(orphan/partial bar — accounting row without a frozen source snapshot)"
                )
                continue
            expected = commit_by_bar.get(bt)
            # If either side is missing/malformed it was already flagged above; do NOT fall
            # through to a `None == None`/garbage equality that would mask the corruption.
            if not _valid_commit_id(got) or not _valid_commit_id(expected):
                continue
            if got != expected:
                failures.append(
                    f"{name} {rid} bar {bt} bar_commit_id {got} != snapshot {expected} "
                    f"(rows for a processed bar disagree — partial/stale commit)"
                )

    # --- backfill policy: no forward fill before forward_start_ts ---
    for f in fills:
        if f.get("backfill") is not False:
            failures.append(f"fill {f.get('fill_id')} not marked backfill=false")
        if f.get("fill_ts", "") < forward_start_ts:
            failures.append(
                f"fill {f.get('fill_id')} fill_ts {f.get('fill_ts')} < forward_start_ts"
            )

    # --- fill shape ---
    fill_ids = {f["fill_id"] for f in fills}
    fill_price_by_id = {f["fill_id"]: f.get("fill_price") for f in fills}
    for f in fills:
        side, kind = f.get("side"), f.get("kind")
        if (kind == "entry" and side != "BUY") or (kind == "exit" and side != "SELL"):
            failures.append(f"fill {f['fill_id']} side/kind mismatch: {side}/{kind}")
        if f.get("qty", 0) <= 0:
            failures.append(f"fill {f['fill_id']} non-positive qty")

    # --- trade internal consistency ---
    for t in trades:
        expect_net = t["gross_pnl"] - t["fees"] - t["funding"]
        if abs(expect_net - t["net_pnl"]) > EPS:
            failures.append(
                f"trade {t['trade_id']} net_pnl {t['net_pnl']} != gross-fees-funding {expect_net}"
            )
        if t.get("hold_bars", 0) < 1:
            failures.append(f"trade {t['trade_id']} hold_bars < 1")
        for ref in ("entry_fill_id", "exit_fill_id"):
            if t.get(ref) not in fill_ids:
                failures.append(f"trade {t['trade_id']} dangling {ref}={t.get(ref)}")
        # trade entry/exit prices must equal the referenced fills' fill_price
        for ref, price_field in (("entry_fill_id", "entry_price"), ("exit_fill_id", "exit_price")):
            ref_price = fill_price_by_id.get(t.get(ref))
            if ref_price is not None and abs(ref_price - t.get(price_field, 0.0)) > EPS:
                failures.append(
                    f"trade {t['trade_id']} {price_field} {t.get(price_field)} != "
                    f"{ref} fill_price {ref_price}"
                )

    # --- equity internal consistency (section 3.2) ---
    prev_fees = None
    for e in equity:
        recomputed = (
            initial_equity
            + e["realized_gross_pnl"]
            - e["fees_cum"]
            - e["funding_cum"]
            + e["unrealized_pnl"]
        )
        if abs(recomputed - e["equity"]) > 1e-4:
            failures.append(
                f"equity {e['bar_ts']} mismatch: stored {e['equity']} vs recomputed {recomputed}"
            )
        if not (0.0 - EPS <= e["drawdown"] <= 1.0 + EPS):
            failures.append(f"equity {e['bar_ts']} drawdown out of range: {e['drawdown']}")
        if prev_fees is not None and e["fees_cum"] + EPS < prev_fees:
            failures.append(f"equity {e['bar_ts']} fees_cum decreased")
        prev_fees = e["fees_cum"]

    # --- funding ledger ties to last equity funding_cum ---
    if equity:
        funding_total = sum(f.get("funding_amount", 0.0) for f in funding)
        if abs(funding_total - equity[-1]["funding_cum"]) > 1e-4:
            failures.append(
                f"funding sum {funding_total} != last equity funding_cum {equity[-1]['funding_cum']}"
            )

    # --- summary: winrate null iff no closed trades ---
    if summary:
        closed = summary.get("closed_trades", 0)
        wr = summary.get("winrate", None)
        if closed == 0 and wr is not None:
            failures.append("summary winrate must be null when closed_trades == 0")
        if closed > 0 and wr is None:
            failures.append("summary winrate must be set when closed_trades > 0")

    return failures
