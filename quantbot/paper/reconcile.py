"""Reconciliation invariants for the paper_pnl_v1 ledger.

Pure checks over the persisted ledgers. Returns a list of failure strings; empty == pass.
See docs/paper_pnl_v1_schema.md sections 3, 5, 6.
"""

from __future__ import annotations

import hashlib
import json
from collections import Counter
from pathlib import Path
from typing import Any

from quantbot.core.determinism import sha256_file
from quantbot.paper.config import ConfigContractError, load_config
from quantbot.paper.freshness import parse_bar_utc
from quantbot.paper import ledger
from quantbot.paper.ledger import LedgerCorruptionError

EPS = 1e-6
# Re-derivation tolerances (Blocker 4). Every value below is recomputed from the persisted
# ledgers and compared to the stored value. The stored numbers are rounded (fill_price/8,
# qty/10, fee/funding/equity/8, drawdown/8), so recomputing from the already-rounded inputs
# accumulates a few ulp of slack; these tolerances sit comfortably above that while still
# catching a fabricated fee / gross / funding / drawdown / exposure (the Codex blocker).
REDERIVE_EPS = 1e-4
# drawdown is a ratio in [0, 1]; its inputs (equity) are rounded to 8 decimals so the recompute
# is tight.
DRAWDOWN_EPS = 1e-6
# gross_exposure is bounded, not pinned: marks (close prices) are NOT available to the read-only
# reconcile, so exposure is tied to the equity row's unrealized_pnl plus the open book's entry
# notionals (exposure - unrealized == Σ entry_notional over the *markable* open positions, which
# is between 0 and Σ over the *whole* open book). This catches an arbitrarily fabricated exposure
# without re-deriving marks (documented limitation: a genuine missing mark only shrinks the sum,
# so the bound never false-positives).
EXPOSURE_EPS = 1e-2
# Tolerance for tying the state accumulators to the SUM of the rounded ledger rows. Each ledger
# value is rounded to 8 decimals, so a long run accumulates a few * n * 5e-9 of slack; 1e-4 is
# comfortably above that while still catching a tampered accumulator.
STATE_ACC_EPS = 1e-4
# Tolerance for tying an open position's entry_price/qty back to the committed fill row. The
# state stores the UNROUNDED engine values; the fill ledger stores round(fill_price, 8) /
# round(qty, 10). 1e-6 is far above that rounding slack while still catching a doubled qty or a
# tampered entry_price (Blocker 3).
OPEN_POS_EPS = 1e-6

# state.accumulators key -> the committed ledger it must equal the SUM of (Blocker: state must
# tie to the ledgers, not be normalized into OK from a shape-valid-but-inconsistent value).
_STATE_ACC_TO_LEDGER = {
    "realized_gross": ("paper_trades.jsonl", "gross_pnl"),
    "fees_cum": ("paper_fills.jsonl", "fee"),
    "funding_cum": ("paper_funding.jsonl", "funding_amount"),
}

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


def read_ledger_validated(output_dir: Path, fname: str) -> list[dict[str, Any]]:
    """Public deep-validating JSONL reader for the runner's bundle build (Blocker 2).

    The OK summary/provenance/receipt builders must NEVER consume an unvalidated ledger row: a
    plain ``read_jsonl`` would let a structurally-malformed row (e.g. ``[{}]`` injected after the
    post-mutation reconcile) through, then KeyError deep in ``compute_summary`` AFTER ``RUNNING``
    was written — a traceback with the status stuck at RUNNING. Routing every final bundle read
    through the same per-artifact schema as the health/reconcile gates turns that into a
    fail-closed ``LedgerCorruptionError`` the runner converts to CORRUPT_LEDGER (exit 4).
    """
    return _read_ledger_validated(output_dir, fname)

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
    # before the authoritative preflight marker is visible. The prior committed status also tells
    # us whether the state must be STRICTLY tied to the ledgers: only after an `OK` commit is the
    # state guaranteed in lockstep with the ledgers. A non-OK prior (RUNNING/CORRUPT/ABORTED, or
    # an absent summary) means a run may have failed mid-commit after appending equity but before
    # writing the state/watermark, so the state is legitimately allowed to LAG the ledgers and is
    # repaired by the next reprocess — it must not be flagged as corrupt for lagging.
    prior_committed_ok = False
    ok_summary_path: Path | None = None
    summary_paths = prior_summary_paths or (output_dir / "paper_pnl_summary.json",)
    for summary_path in summary_paths:
        try:
            prior = ledger.read_summary_obj(summary_path)
            if prior.get("status") == "OK":
                prior_committed_ok = True
                ok_summary_path = summary_path
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
    # 3. Tie the position state to the committed ledgers. A shape-valid state whose watermark/
    #    accumulators/open_positions disagree with the committed equity/trades/fills/funding must
    #    fail closed as CORRUPT_LEDGER, never be normalized into OK (Blocker: state vs ledgers).
    failures.extend(
        reconcile_state_against_ledgers(output_dir, require_committed=prior_committed_ok)
    )
    # 4. Provenance is authoritative for a prior OK commit (Blocker 4, Option A). The docs say
    #    paper_provenance.json manifests EVERY output, so it is part of the OK commit proof: when
    #    the prior summary committed OK its provenance must parse, be shaped OK, and pin digests
    #    that still match the committed summary/state. A falsified state digest or an invalid
    #    provenance JSON therefore fails closed as CORRUPT_LEDGER instead of being silently
    #    overwritten by the next run. (When the prior summary is non-OK the provenance is just a
    #    regenerated record of an incomplete run, so it is NOT gated — see the schema doc § 4/5.)
    if prior_committed_ok:
        failures.extend(_check_provenance_committed(output_dir, ok_summary_path))
    return failures


def _check_provenance_committed(
    output_dir: Path, ok_summary_path: Path | None
) -> list[str]:
    """Gate paper_provenance.json when the prior summary committed OK (Blocker 4, Option A).

    The schema doc declares provenance a manifest of EVERY output and part of the OK commit
    proof. So once a run has committed OK, its provenance must:
      - parse and be a JSON object (else CORRUPT_LEDGER — an invalid provenance JSON fails closed);
      - carry ``status == OK`` and an ``output_digests`` object;
      - pin digests that STILL match the committed summary + position state on disk — a falsified
        state digest (or a state mutated out from under it) is therefore caught here instead of
        being silently overwritten by the next run.

    The summary is digested from ``ok_summary_path`` because the runner has already atomically
    staged the prior summary aside (renamed, byte-identical) before publishing the RUNNING
    marker, so ``paper_pnl_summary.json`` itself is the fresh RUNNING marker at this point. The
    position state is NOT staged, so it is digested in place.
    """
    name = "paper_provenance.json"
    path = output_dir / name
    try:
        prov = ledger.read_json_obj(path, default=None)
    except (LedgerCorruptionError, OSError) as exc:
        return [str(exc)]
    if prov is None:
        return [
            f"{name} is absent but the prior summary committed OK "
            f"(provenance manifests every output and is part of the OK commit proof)"
        ]
    failures: list[str] = []
    if prov.get("status") != "OK":
        failures.append(
            f"{name} status {prov.get('status')!r} != OK though the prior summary committed OK"
        )
    digests = prov.get("output_digests")
    if not isinstance(digests, dict):
        return failures + [
            f"{name} output_digests is missing or not an object; corrupt provenance manifest"
        ]
    committed = {
        "paper_pnl_summary.json": ok_summary_path,
        "paper_position_state.json": output_dir / "paper_position_state.json",
    }
    for key, fpath in committed.items():
        if fpath is None:
            continue
        pinned = digests.get(key)
        try:
            actual = sha256_file(fpath)
        except FileNotFoundError:
            actual = "absent"
        except OSError as exc:
            failures.append(
                f"{name}: cannot digest committed {key} ({type(exc).__name__}: {exc})"
            )
            continue
        if pinned != actual:
            failures.append(
                f"{name} output digest for {key} ({pinned}) != the committed artifact digest "
                f"({actual}); falsified/stale provenance — the OK commit proof no longer holds"
            )
    return failures


def _ledger_sum(rows: list[dict[str, Any]], field: str) -> float:
    return sum(float(r.get(field, 0.0)) for r in rows)


def _open_symbols_from_fills(fills: list[dict[str, Any]]) -> set[str]:
    """Reconstruct the open-position book from the committed fills ledger.

    Long-only, no flips: a symbol is open iff it has more entry fills than exit fills. This is
    independent of the per-bar positions snapshot's pre-fill off-by-one (schema § 3.1), so it
    matches the engine's POST-fill book that the persisted state records.
    """
    entries = Counter(f.get("symbol") for f in fills if f.get("kind") == "entry")
    exits = Counter(f.get("symbol") for f in fills if f.get("kind") == "exit")
    return {sym for sym in entries if entries[sym] > exits[sym]}


def _ledger_open_positions(
    fills: list[dict[str, Any]],
    funding: list[dict[str, Any]],
    equity: list[dict[str, Any]],
) -> dict[str, dict[str, Any]]:
    """Reconstruct each open position's full detail from the committed ledgers (Blocker 3).

    Long-only, no flips: the live open position for a symbol is its LAST (unmatched) entry fill.
    Funding accrued = Σ funding_amount for the symbol on bars strictly after its entry bar (the
    entry bar itself accrues nothing — the held sub-interval is zero, schema § 3.1/11; any
    earlier closed position of the same symbol exited before this entry, so its funding rows are
    all at earlier bars). hold_bars = the number of committed equity bars strictly after the
    entry bar (each such bar incremented hold_bars once on the pre-fill book).
    """
    open_syms = _open_symbols_from_fills(fills)
    equity_ts = [e["bar_ts"] for e in equity]
    out: dict[str, dict[str, Any]] = {}
    for sym in open_syms:
        entries = [
            f for f in fills if f.get("symbol") == sym and f.get("kind") == "entry"
        ]
        if not entries:  # defensive: open_syms guarantees at least one, but never index []
            continue
        last_entry = entries[-1]  # append-only chronological order -> the unmatched open entry
        entry_bar_ts = last_entry.get("signal_bar_ts")
        funding_accrued = sum(
            f.get("funding_amount", 0.0)
            for f in funding
            if f.get("symbol") == sym and f.get("bar_ts", "") > entry_bar_ts
        )
        hold_bars = sum(1 for ts in equity_ts if ts > entry_bar_ts)
        out[sym] = {
            "entry_fill_id": last_entry.get("fill_id"),
            "entry_price": last_entry.get("fill_price"),
            "entry_bar_ts": entry_bar_ts,
            "entry_fill_ts": last_entry.get("fill_ts"),
            "qty": last_entry.get("qty"),
            "funding_accrued": funding_accrued,
            "hold_bars": hold_bars,
        }
    return out


def _check_open_position_detail(
    name: str, sym: str, state_pos: dict[str, Any], ledger_pos: dict[str, Any]
) -> list[str]:
    """Tie one state open position to its ledger-derived detail (Blocker 3).

    Codex showed the old check only compared the open-SYMBOL set, so doubling an open qty (or
    tampering entry_fill_id/entry_price/funding_accrued) still returned OK. Every stored field
    of the open position is now tied to the committed fills/funding/equity.
    """
    failures: list[str] = []
    # exact identity / timestamp fields
    for fld in ("entry_fill_id", "entry_bar_ts", "entry_fill_ts"):
        if str(state_pos.get(fld)) != str(ledger_pos.get(fld)):
            failures.append(
                f"{name} open_positions[{sym!r}] {fld} {state_pos.get(fld)!r} != "
                f"ledger-derived {ledger_pos.get(fld)!r}"
            )
    # hold_bars is an exact integer count
    if state_pos.get("hold_bars") != ledger_pos.get("hold_bars"):
        failures.append(
            f"{name} open_positions[{sym!r}] hold_bars {state_pos.get('hold_bars')!r} != "
            f"ledger-derived {ledger_pos.get('hold_bars')}"
        )
    # finite numeric fields within rounding tolerance
    for fld, eps in (
        ("entry_price", OPEN_POS_EPS),
        ("qty", OPEN_POS_EPS),
        ("funding_accrued", STATE_ACC_EPS),
    ):
        got = state_pos.get(fld)
        want = ledger_pos.get(fld)
        if (
            not isinstance(got, (int, float))
            or isinstance(got, bool)
            or not isinstance(want, (int, float))
            or abs(float(got) - float(want)) > eps
        ):
            failures.append(
                f"{name} open_positions[{sym!r}] {fld} {got!r} != ledger-derived {want} "
                f"(within {eps})"
            )
    return failures


def _strict_state_invariants(
    state: dict[str, Any],
    equity: list[dict[str, Any]],
    trades: list[dict[str, Any]],
    fills: list[dict[str, Any]],
    funding: list[dict[str, Any]],
    name: str,
    initial_equity: float,
) -> list[str]:
    """Full at-rest lockstep checks (prior committed OK / OK commit imminent)."""
    failures: list[str] = []
    watermark = state.get("watermark_bar_ts", "")
    latest_equity_ts = max((e["bar_ts"] for e in equity), default=None)
    acc = state.get("accumulators", {})
    open_positions = state.get("open_positions", {})
    bars_elapsed = state.get("bars_elapsed", 0)
    peak_equity = state.get("peak_equity")

    if not equity:
        if watermark != "":
            failures.append(f"{name} OK state has watermark {watermark!r} but no equity rows")
        if bars_elapsed != 0:
            failures.append(f"{name} OK state bars_elapsed {bars_elapsed} != 0 with no equity")
        if open_positions:
            failures.append(
                f"{name} OK state has open_positions {sorted(open_positions)} but no equity rows"
            )
        if (
            not isinstance(peak_equity, (int, float))
            or isinstance(peak_equity, bool)
            or abs(float(peak_equity) - initial_equity) > STATE_ACC_EPS
        ):
            failures.append(
                f"{name} OK state peak_equity {peak_equity!r} != initial_equity {initial_equity} "
                f"with no equity rows"
            )
        return failures

    if watermark != latest_equity_ts:
        failures.append(
            f"{name} watermark_bar_ts {watermark!r} != latest committed equity bar_ts "
            f"{latest_equity_ts!r} (an OK state's watermark must equal the latest equity bar)"
        )
    if bars_elapsed != len(equity):
        failures.append(
            f"{name} bars_elapsed {bars_elapsed} != committed equity row count {len(equity)}"
        )

    ledger_sums = {
        "realized_gross": _ledger_sum(trades, "gross_pnl"),
        "fees_cum": _ledger_sum(fills, "fee"),
        "funding_cum": _ledger_sum(funding, "funding_amount"),
    }
    for key, expected in ledger_sums.items():
        got = acc.get(key)
        if not isinstance(got, (int, float)) or isinstance(got, bool) or (
            abs(float(got) - expected) > STATE_ACC_EPS
        ):
            failures.append(
                f"{name} accumulator {key}={got!r} != committed ledger sum {expected} "
                f"({_STATE_ACC_TO_LEDGER[key][0]}.{_STATE_ACC_TO_LEDGER[key][1]})"
            )

    # peak_equity must equal the running max equity over the committed ledger (Blocker 3): a
    # peak inflated ~$1M too high (or deflated too low) used to pass because only the open-symbol
    # set was checked. peak starts at initial_equity, so the expected peak includes it.
    expected_peak = max([initial_equity] + [e["equity"] for e in equity])
    if (
        not isinstance(peak_equity, (int, float))
        or isinstance(peak_equity, bool)
        or abs(float(peak_equity) - expected_peak) > STATE_ACC_EPS
    ):
        failures.append(
            f"{name} peak_equity {peak_equity!r} != max equity over the committed ledger "
            f"{expected_peak} (within {STATE_ACC_EPS})"
        )

    open_from_fills = _open_symbols_from_fills(fills)
    if set(open_positions) != open_from_fills:
        failures.append(
            f"{name} open_positions {sorted(open_positions)} != open book reconstructed from "
            f"committed fills {sorted(open_from_fills)}"
        )
    # Per-open-position detail (qty / entry_fill_id / entry_price / entry_bar_ts / entry_fill_ts
    # / funding_accrued / hold_bars) for every symbol open in BOTH the state and the ledger book.
    ledger_open = _ledger_open_positions(fills, funding, equity)
    for sym in sorted(set(open_positions) & set(ledger_open)):
        sp = open_positions.get(sym)
        if isinstance(sp, dict):
            failures.extend(
                _check_open_position_detail(name, sym, sp, ledger_open[sym])
            )

    return failures


def _reconcile_state_dict_against_ledgers(
    state: dict[str, Any] | None,
    equity: list[dict[str, Any]],
    trades: list[dict[str, Any]],
    fills: list[dict[str, Any]],
    funding: list[dict[str, Any]],
    *,
    name: str,
    require_committed: bool,
    initial_equity: float,
) -> list[str]:
    """Core state-vs-ledger reconciliation over an in-memory state + already-read ledgers.

    Shared by the disk-reading pre-run health gate (``reconcile_state_against_ledgers``) and the
    final integrity gate, which validates the EXACT in-memory state it is about to commit against
    the final persisted ledgers (so there is no read-after-gate window).
    """
    if state is None:
        # No committed state. After an OK commit a state file always exists; its absence with
        # committed equity rows is corruption — but a mid-commit failure (non-OK prior) may
        # legitimately have appended equity before the first state write, so allow it then.
        if require_committed and equity:
            return [
                f"{name} is absent but paper_equity.jsonl has {len(equity)} committed row(s) "
                f"(an OK run must leave a position state tying to the ledgers)"
            ]
        return []

    failures: list[str] = []
    watermark = state.get("watermark_bar_ts", "")
    latest_equity_ts = max((e["bar_ts"] for e in equity), default=None)

    # --- always-true invariants ---
    if not equity:
        if watermark != "":
            failures.append(
                f"{name} watermark_bar_ts {watermark!r} is set but no equity rows are "
                f"committed (the engine never advances the watermark without an equity row)"
            )
    elif watermark != "" and watermark > latest_equity_ts:
        failures.append(
            f"{name} watermark_bar_ts {watermark!r} is after the latest committed equity bar "
            f"{latest_equity_ts!r} (a future/ahead watermark is never valid)"
        )

    if not require_committed:
        return failures

    failures.extend(
        _strict_state_invariants(
            state, equity, trades, fills, funding, name, initial_equity
        )
    )
    return failures


def reconcile_state_against_ledgers(
    output_dir: Path, *, require_committed: bool
) -> list[str]:
    """Tie paper_position_state.json to the committed ledgers (fail-closed; never raises).

    ``require_committed`` is True only when the prior visible summary was ``OK`` — i.e. the last
    run committed cleanly, so the state MUST be in exact lockstep with the ledgers. When False
    (a mid-commit failure / first run) the state is allowed to LAG the ledgers (equity may be
    ahead of the watermark, to be repaired by the next reprocess); only the always-true
    invariants are enforced so a legitimate recovery state is not mis-flagged as corrupt.

    Always enforced (a committed watermark always has its equity row on disk, written before the
    state):
      - the watermark is never STRICTLY AFTER the latest committed equity bar (catches a
        future/ahead watermark such as 2030 even if the summary was also tampered to non-OK);
      - a non-empty watermark requires at least one committed equity row.

    Enforced only when ``require_committed`` (the state is at rest after an OK commit):
      - watermark == latest committed equity bar_ts (not earlier, not later);
      - bars_elapsed == committed equity row count;
      - accumulators (realized_gross/fees_cum/funding_cum) == the SUM of the committed
        trades/fills/funding rows;
      - peak_equity == the running max equity over the committed equity ledger (Blocker 3);
      - open_positions == the book reconstructed from the committed fills, AND each open
        position's qty/entry_fill_id/entry_price/entry_bar_ts/entry_fill_ts/funding_accrued/
        hold_bars ties to the ledger-derived detail (Blocker 3);
      - with no committed equity, the state is pristine (engine.new_state).
    """
    name = "paper_position_state.json"
    trades: list[dict[str, Any]] = []
    fills: list[dict[str, Any]] = []
    funding: list[dict[str, Any]] = []
    initial_equity = 0.0
    try:
        state = ledger.read_state_obj(output_dir / name)
        equity = _read_ledger_validated(output_dir, "paper_equity.jsonl")
        if require_committed:
            trades = _read_ledger_validated(output_dir, "paper_trades.jsonl")
            fills = _read_ledger_validated(output_dir, "paper_fills.jsonl")
            funding = _read_ledger_validated(output_dir, "paper_funding.jsonl")
            initial_equity = float(load_config(output_dir)["initial_equity_usd"])
    except (LedgerCorruptionError, OSError, ConfigContractError) as exc:
        return [str(exc)]
    return _reconcile_state_dict_against_ledgers(
        state,
        equity,
        trades,
        fills,
        funding,
        name=name,
        require_committed=require_committed,
        initial_equity=initial_equity,
    )


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
    # Compare parsed instants, not raw strings: fill_ts (T+1 open) is naive while
    # forward_start_ts carries a trailing Z, so a lexicographic compare misrepresents the
    # boundary. A missing/unparseable fill_ts fails closed (treated as before the boundary).
    forward_start_dt = parse_bar_utc(forward_start_ts)
    for f in fills:
        if f.get("backfill") is not False:
            failures.append(f"fill {f.get('fill_id')} not marked backfill=false")
        fill_ts = f.get("fill_ts")
        try:
            before_boundary = fill_ts is None or parse_bar_utc(fill_ts) < forward_start_dt
        except (TypeError, ValueError):
            before_boundary = True  # unparseable fill_ts -> fail closed
        if before_boundary:
            failures.append(
                f"fill {f.get('fill_id')} fill_ts {f.get('fill_ts')} < forward_start_ts"
            )

    # --- fill shape + fee re-derivation (Blocker 4) ---
    # fee = fill_price * qty * fee_bps / 10_000 (engine.run_engine). A fabricated fee that does
    # not equal this product fails closed instead of being accepted because it is merely >= 0.
    fee_bps = float(config["fee_model"]["fee_bps"])
    fill_ids = {f["fill_id"] for f in fills}
    fill_price_by_id = {f["fill_id"]: f.get("fill_price") for f in fills}
    for f in fills:
        side, kind = f.get("side"), f.get("kind")
        if (kind == "entry" and side != "BUY") or (kind == "exit" and side != "SELL"):
            failures.append(f"fill {f['fill_id']} side/kind mismatch: {side}/{kind}")
        if f.get("qty", 0) <= 0:
            failures.append(f"fill {f['fill_id']} non-positive qty")
        expected_fee = f["fill_price"] * f["qty"] * fee_bps / 10_000.0
        if abs(expected_fee - f["fee"]) > REDERIVE_EPS:
            failures.append(
                f"fill {f['fill_id']} fee {f['fee']} != fill_price*qty*fee_bps/1e4 "
                f"{expected_fee} (fabricated/incorrect fee)"
            )

    # --- trade internal consistency ---
    for t in trades:
        # gross re-derivation (Blocker 4): long-only, gross = (exit_price - entry_price) * qty.
        # A fabricated gross_pnl with a matching net_pnl used to pass (only net = gross-fees-
        # funding was checked); re-derive gross from the trade's own prices/qty.
        expect_gross = (t["exit_price"] - t["entry_price"]) * t["qty"]
        if abs(expect_gross - t["gross_pnl"]) > REDERIVE_EPS:
            failures.append(
                f"trade {t['trade_id']} gross_pnl {t['gross_pnl']} != "
                f"(exit_price-entry_price)*qty {expect_gross} (fabricated/incorrect gross)"
            )
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

    # --- equity internal consistency (section 3.2) + drawdown re-derivation (Blocker 4) ---
    # drawdown = (peak - equity) / peak with peak the running max equity (seeded at
    # initial_equity). The equity rows are append-only chronological, so the peak is recomputed
    # in order; a fabricated drawdown that is merely in-range [0,1] now fails closed.
    prev_fees = None
    peak_equity = initial_equity
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
        peak_equity = max(peak_equity, e["equity"])
        expect_dd = (peak_equity - e["equity"]) / peak_equity if peak_equity > 0 else 0.0
        if abs(expect_dd - e["drawdown"]) > DRAWDOWN_EPS:
            failures.append(
                f"equity {e['bar_ts']} drawdown {e['drawdown']} != (peak-equity)/peak "
                f"{expect_dd} (peak {peak_equity}; fabricated/incorrect drawdown)"
            )
        if prev_fees is not None and e["fees_cum"] + EPS < prev_fees:
            failures.append(f"equity {e['bar_ts']} fees_cum decreased")
        prev_fees = e["fees_cum"]

    # --- funding amount re-derivation (Blocker 4) ---
    # funding_amount = notional_usd * funding_rate when a rate is available, else exactly 0.0
    # (engine.run_engine). A fabricated funding_amount / funding_rate pair that does not satisfy
    # this product fails closed instead of being accepted as a finite number.
    for f in funding:
        if f["rate_available"]:
            expected_amount = f["notional_usd"] * f["funding_rate"]
        else:
            expected_amount = 0.0
        if abs(expected_amount - f["funding_amount"]) > REDERIVE_EPS:
            failures.append(
                f"funding {f['funding_id']} funding_amount {f['funding_amount']} != "
                f"notional_usd*funding_rate {expected_amount} "
                f"(rate_available={f['rate_available']}; fabricated/incorrect funding)"
            )

    # --- funding ledger ties to last equity funding_cum ---
    if equity:
        funding_total = sum(f.get("funding_amount", 0.0) for f in funding)
        if abs(funding_total - equity[-1]["funding_cum"]) > 1e-4:
            failures.append(
                f"funding sum {funding_total} != last equity funding_cum {equity[-1]['funding_cum']}"
            )

    # --- positions: open-book + gross_exposure re-derivation (Blocker 4) ---------------
    # The per-bar positions snapshot is taken on the PRE-FILL book (schema § 3.1): a symbol is
    # open at bar `ts` iff it has more entry fills than exit fills with signal_bar_ts STRICTLY
    # before ts. open_symbols/num_open are re-derived exactly from the fills (mark-independent).
    # gross_exposure is bounded, not pinned (marks are unavailable to the read-only reconcile):
    #   exposure - unrealized_pnl(same bar) == Σ entry_notional over the *markable* open book,
    # which lies in [0, Σ entry_notional over the *whole* open book]. A fabricated exposure that
    # leaves this band fails closed; a genuine missing mark only shrinks the sum (no false fail).
    equity_by_ts = {e["bar_ts"]: e for e in equity}
    for p in positions:
        ts = p["bar_ts"]
        entries_before: Counter = Counter()
        exits_before: Counter = Counter()
        last_entry_fill: dict[str, dict[str, Any]] = {}
        for fl in fills:
            if fl["signal_bar_ts"] < ts:
                if fl["kind"] == "entry":
                    entries_before[fl["symbol"]] += 1
                    last_entry_fill[fl["symbol"]] = fl
                elif fl["kind"] == "exit":
                    exits_before[fl["symbol"]] += 1
        open_book = sorted(
            s for s in entries_before if entries_before[s] > exits_before[s]
        )
        if p["open_symbols"] != open_book:
            failures.append(
                f"positions {ts} open_symbols {p['open_symbols']} != pre-fill book "
                f"reconstructed from fills {open_book}"
            )
        if p["num_open"] != len(open_book):
            failures.append(
                f"positions {ts} num_open {p['num_open']} != open book size {len(open_book)}"
            )
        e = equity_by_ts.get(ts)
        if e is None:
            continue  # missing equity row flagged by the snapshot/orphan checks above
        max_notional = sum(
            last_entry_fill[s]["fill_price"] * last_entry_fill[s]["qty"] for s in open_book
        )
        diff = p["gross_exposure_usd"] - e["unrealized_pnl"]
        if diff < -EXPOSURE_EPS or diff > max_notional + EXPOSURE_EPS:
            failures.append(
                f"positions {ts} gross_exposure_usd {p['gross_exposure_usd']} inconsistent with "
                f"unrealized_pnl {e['unrealized_pnl']} + open-book entry notionals "
                f"(must be in [unrealized, unrealized+{max_notional}]; fabricated/incorrect "
                f"exposure)"
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


def _check_ok_commit_semantics(
    output_dir: Path,
    summary_bytes: bytes,
    state_bytes: bytes,
    receipt_bytes: bytes,
) -> list[str]:
    """Validate the OK commit bundle ties together immediately before the OK summary write.

    The OK summary is the single commit marker (schema § 5). Before it is written, the bundle it
    commits must be internally consistent: the summary about to be written is a valid OK summary,
    and the provenance ALREADY on disk pins the EXACT summary/state/receipt bytes about to be
    committed (with the receipt already on disk equal to those bytes). This closes the window
    where a provenance/receipt that no longer matches the committed summary/state could still be
    published as part of an OK.
    """
    failures: list[str] = []
    try:
        summary_obj = json.loads(summary_bytes.decode("utf-8"))
        ledger.validate_summary_shape(summary_obj)
    except (UnicodeDecodeError, ValueError, LedgerCorruptionError) as exc:
        return [f"final OK summary failed shape validation before commit ({exc})"]
    if summary_obj.get("status") != "OK":
        failures.append(
            f"final summary status {summary_obj.get('status')!r} is not OK at commit time"
        )

    name = "paper_provenance.json"
    try:
        prov = ledger.read_json_obj(output_dir / name, default=None)
    except (LedgerCorruptionError, OSError) as exc:
        return failures + [f"{name} unreadable at final commit ({type(exc).__name__}: {exc})"]
    if not isinstance(prov, dict):
        return failures + [f"{name} is missing at final commit (an OK requires a provenance manifest)"]
    digests = prov.get("output_digests")
    if not isinstance(digests, dict):
        return failures + [f"{name} output_digests missing/not an object at final commit"]

    expected = {
        "paper_pnl_summary.json": hashlib.sha256(summary_bytes).hexdigest(),
        "paper_position_state.json": hashlib.sha256(state_bytes).hexdigest(),
        "paper_receipt.md": hashlib.sha256(receipt_bytes).hexdigest(),
    }
    for key, want in expected.items():
        if digests.get(key) != want:
            failures.append(
                f"{name} output digest for {key} ({digests.get(key)}) != the bundle bytes "
                f"about to be committed ({want}) — provenance does not manifest this OK"
            )
    try:
        on_disk_receipt = (output_dir / "paper_receipt.md").read_bytes()
    except OSError as exc:
        return failures + [
            f"paper_receipt.md unreadable at final commit ({type(exc).__name__}: {exc})"
        ]
    if on_disk_receipt != receipt_bytes:
        failures.append(
            "paper_receipt.md on disk != the receipt bytes provenance pinned (commit mismatch)"
        )
    return failures


def final_integrity_gate(
    output_dir: Path,
    *,
    state: dict[str, Any],
    initial_equity: float,
    summary_bytes: bytes,
    state_bytes: bytes,
    receipt_bytes: bytes,
) -> list[str]:
    """Re-validate ALL committed evidence immediately before the final OK summary write (Blocker 1).

    "Reconcile then publish OK" left a TOCTOU gap: Codex passed reconcile, mutated a trade's
    net_pnl, and the runner still published OK while an immediate re-reconcile reported the
    inconsistency. This gate runs as the LAST step before the OK commit and re-derives the
    verdict from the FINAL persisted artifacts so an OK is impossible unless they STILL pass:

      1. deep parse + shape validation of every persisted JSONL ledger (fail closed);
      2. structural reconcile over the final persisted ledgers (net_pnl/fees/equity/funding/
         commit-id invariants);
      3. the in-memory position state about to be committed tied STRICTLY to those ledgers
         (watermark/bars_elapsed/accumulators/peak_equity/open-position detail — Blocker 3);
      4. provenance/summary/receipt commit semantics (the bundle ties together — Blocker 4).

    The runner publishes provenance + receipt BEFORE calling this gate, and only the state +
    OK-summary writes happen AFTER it (writes of pre-validated in-memory bytes — there is no
    read of a mutable artifact after the gate). Any failure aborts the OK and is published as
    CORRUPT_LEDGER (exit 4); the state/watermark is NOT advanced.
    """
    try:
        fills = _read_ledger_validated(output_dir, "paper_fills.jsonl")
        trades = _read_ledger_validated(output_dir, "paper_trades.jsonl")
        equity = _read_ledger_validated(output_dir, "paper_equity.jsonl")
        funding = _read_ledger_validated(output_dir, "paper_funding.jsonl")
        _read_ledger_validated(output_dir, "paper_positions.jsonl")
        _read_ledger_validated(output_dir, "paper_signal_snapshots.jsonl")
    except (LedgerCorruptionError, OSError) as exc:
        return [str(exc)]

    failures: list[str] = []
    failures.extend(reconcile(output_dir))
    failures.extend(
        _reconcile_state_dict_against_ledgers(
            state,
            equity,
            trades,
            fills,
            funding,
            name="paper_position_state.json",
            require_committed=True,
            initial_equity=initial_equity,
        )
    )
    failures.extend(
        _check_ok_commit_semantics(output_dir, summary_bytes, state_bytes, receipt_bytes)
    )
    return failures
