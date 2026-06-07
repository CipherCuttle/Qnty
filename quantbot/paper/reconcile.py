"""Reconciliation invariants for the paper_pnl_v1 ledger.

Pure checks over the persisted ledgers. Returns a list of failure strings; empty == pass.
See docs/paper_pnl_v1_schema.md sections 3, 5, 6.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from quantbot.paper.config import load_config
from quantbot.paper import ledger

EPS = 1e-6

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


def reconcile(output_dir: Path) -> list[str]:
    failures: list[str] = []
    config = load_config(output_dir)
    forward_start_ts = config["forward_start_ts"]
    initial_equity = float(config["initial_equity_usd"])

    fills = ledger.read_jsonl(output_dir / "paper_fills.jsonl")
    trades = ledger.read_jsonl(output_dir / "paper_trades.jsonl")
    equity = ledger.read_jsonl(output_dir / "paper_equity.jsonl")
    funding = ledger.read_jsonl(output_dir / "paper_funding.jsonl")
    positions = ledger.read_jsonl(output_dir / "paper_positions.jsonl")
    snaps = ledger.read_jsonl(output_dir / "paper_signal_snapshots.jsonl")
    summary = ledger.read_json(output_dir / "paper_pnl_summary.json", default={})

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
