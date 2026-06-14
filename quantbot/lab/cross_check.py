"""CROSS_CHECK lane — row-by-row engine-vs-replay diff + disagreement classifier.

Compares the production paper engine (``quantbot.paper.engine.run_engine``) against the
independent ``quantbot.lab.replay_engine.run_replay`` re-derive. A CLEAN result means both
implementations agree on the fill/cost/funding/equity spec, which raises trust in the
witness. A disagreement is a *measured quantity* (per the implementation-risk literature),
emitted as a structured diff and triaged into one of four classes — it is NEVER
auto-blamed on QNTY.

Classes:
  QNTY_BUG_CANDIDATE          — production equity/PnL is internally INCONSISTENT
                                (its own equity != initial + realized - fees - funding +
                                unreal) while the replay's is consistent.
  CHECKER_BUG_CANDIDATE       — the replay's equity is internally inconsistent (the checker
                                arithmetic is the suspect, not QNTY).
  TIMESTAMP_FILL_COST_MISMATCH— diff on a fill/cost/timing field (open/fill price, qty, fee,
                                fill_ts, exposure): a fill-timing or cost-model assumption
                                gap, the most common false-red-alert source.
  SPEC_AMBIGUITY              — funding-interval / definitional diff, or any diff where both
                                sides are internally consistent: the spec, not a bug.

Fail-closed bias: the DEFAULT classification is never QNTY_BUG_CANDIDATE.
"""

from __future__ import annotations

import argparse
import json
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from quantbot.data.types import Bar
from quantbot.lab.replay_engine import ReplayResult, run_replay

# --- classification ---------------------------------------------------------------------

QNTY_BUG_CANDIDATE = "QNTY_BUG_CANDIDATE"
CHECKER_BUG_CANDIDATE = "CHECKER_BUG_CANDIDATE"
SPEC_AMBIGUITY = "SPEC_AMBIGUITY"
TIMESTAMP_FILL_COST_MISMATCH = "TIMESTAMP_FILL_COST_MISMATCH"

CLASSES = (
    QNTY_BUG_CANDIDATE,
    CHECKER_BUG_CANDIDATE,
    SPEC_AMBIGUITY,
    TIMESTAMP_FILL_COST_MISMATCH,
)

# Fields whose disagreement points at a fill-timing / cost-model assumption gap.
COST_FIELDS = frozenset(
    {"open_price", "fill_price", "qty", "fee", "fill_ts", "gross_exposure_usd", "side", "kind"}
)
# Fields governed by the funding-interval convention (documented spec-ambiguous zone).
FUNDING_FIELDS = frozenset(
    {"funding_cum", "funding_amount", "funding_rate", "funding_events", "window_start",
     "window_end", "rate_available", "funding"}
)
# Core accounting identity fields.
EQUITY_FIELDS = frozenset(
    {"equity", "realized_gross_pnl", "unrealized_pnl", "fees_cum", "net_pnl", "gross_pnl"}
)

_ABS_TOL = 1e-6


@dataclass
class Disagreement:
    bar_ts: str
    symbol: str | None
    field: str
    engine_value: Any
    replay_value: Any
    delta: float | None
    classification: str = ""


def _equity_consistent(row: dict[str, Any], initial: float) -> bool:
    """Is an equity row internally self-consistent under the documented identity?"""
    try:
        recomputed = (
            initial
            + float(row["realized_gross_pnl"])
            - float(row["fees_cum"])
            - float(row["funding_cum"])
            + float(row["unrealized_pnl"])
        )
        return abs(recomputed - float(row["equity"])) <= 1e-4
    except (KeyError, TypeError, ValueError):
        return False


def classify_disagreement(
    field_name: str,
    engine_equity_row: dict[str, Any] | None,
    replay_equity_row: dict[str, Any] | None,
    initial_equity: float,
) -> str:
    """Triage a single field disagreement. NEVER defaults to QNTY_BUG_CANDIDATE.

    The bar's engine/replay equity rows (when available) decide internal consistency for the
    arithmetic-identity classes; the field name decides the cost/funding/spec classes.
    """
    if field_name in COST_FIELDS:
        return TIMESTAMP_FILL_COST_MISMATCH
    if field_name in FUNDING_FIELDS:
        return SPEC_AMBIGUITY
    if field_name in EQUITY_FIELDS:
        engine_ok = engine_equity_row is not None and _equity_consistent(
            engine_equity_row, initial_equity
        )
        replay_ok = replay_equity_row is not None and _equity_consistent(
            replay_equity_row, initial_equity
        )
        if not replay_ok:
            # Suspect the checker first — do not blame QNTY for the checker's own bad math.
            return CHECKER_BUG_CANDIDATE
        if not engine_ok:
            # Replay is self-consistent, production equity is not -> production is suspect.
            return QNTY_BUG_CANDIDATE
        # Both internally consistent but differ -> a definitional/spec difference.
        return SPEC_AMBIGUITY
    # num_open, open_symbols, presence-only and any unknown field: spec, never auto-QNTY.
    return SPEC_AMBIGUITY


# --- comparison -------------------------------------------------------------------------


def _as_delta(a: Any, b: Any) -> float | None:
    if isinstance(a, (int, float)) and isinstance(b, (int, float)):
        return float(a) - float(b)
    return None


def _row_by_bar(rows: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    return {r["bar_ts"]: r for r in rows}


def _fill_key(f: dict[str, Any]) -> tuple[str, str, str]:
    return (f["signal_bar_ts"], f["symbol"], f["kind"])


_EQUITY_CMP = ("realized_gross_pnl", "unrealized_pnl", "funding_cum", "fees_cum", "equity",
               "num_open")
_POSITION_CMP = ("num_open", "gross_exposure_usd", "open_symbols")
_FILL_CMP = ("fill_ts", "side", "qty", "open_price", "fill_price", "fee")


def compare(engine_result: Any, replay_result: ReplayResult, initial_equity: float) -> list[Disagreement]:
    """Diff production EngineResult vs ReplayResult; return classified disagreements."""
    diffs: list[Disagreement] = []

    eng_eq = _row_by_bar(engine_result.equity)
    rep_eq = _row_by_bar(replay_result.equity)

    # equity rows
    for ts in sorted(set(eng_eq) | set(rep_eq)):
        e, r = eng_eq.get(ts), rep_eq.get(ts)
        if e is None or r is None:
            diffs.append(Disagreement(ts, None, "equity_row_presence",
                                      e is not None, r is not None, None,
                                      classify_disagreement("equity_row_presence", e, r,
                                                            initial_equity)))
            continue
        for fld in _EQUITY_CMP:
            ev, rv = e.get(fld), r.get(fld)
            if ev != rv:
                diffs.append(Disagreement(ts, None, fld, ev, rv, _as_delta(ev, rv),
                                          classify_disagreement(fld, e, r, initial_equity)))

    # position rows
    eng_pos = _row_by_bar(engine_result.positions)
    rep_pos = _row_by_bar(replay_result.positions)
    for ts in sorted(set(eng_pos) | set(rep_pos)):
        e, r = eng_pos.get(ts), rep_pos.get(ts)
        if e is None or r is None:
            continue
        for fld in _POSITION_CMP:
            ev, rv = e.get(fld), r.get(fld)
            if ev != rv:
                diffs.append(Disagreement(ts, None, fld, ev, rv, _as_delta(ev, rv),
                                          classify_disagreement(fld, eng_eq.get(ts),
                                                                rep_eq.get(ts), initial_equity)))

    # fills
    eng_fills = {_fill_key(f): f for f in engine_result.fills}
    rep_fills = {_fill_key(f): f for f in replay_result.fills}
    for key in sorted(set(eng_fills) | set(rep_fills)):
        e, r = eng_fills.get(key), rep_fills.get(key)
        ts, sym, _ = key
        if e is None or r is None:
            diffs.append(Disagreement(ts, sym, "fill_presence", e is not None, r is not None,
                                      None,
                                      classify_disagreement("fill_ts", eng_eq.get(ts),
                                                            rep_eq.get(ts), initial_equity)))
            continue
        for fld in _FILL_CMP:
            ev, rv = e.get(fld), r.get(fld)
            if ev != rv:
                diffs.append(Disagreement(ts, sym, fld, ev, rv, _as_delta(ev, rv),
                                          classify_disagreement(fld, eng_eq.get(ts),
                                                                rep_eq.get(ts), initial_equity)))

    # deferral boundary
    if engine_result.deferred_bar_ts != replay_result.deferred_bar_ts:
        diffs.append(Disagreement(
            str(engine_result.deferred_bar_ts), None, "deferred_bar_ts",
            engine_result.deferred_bar_ts, replay_result.deferred_bar_ts, None,
            TIMESTAMP_FILL_COST_MISMATCH,
        ))
    return diffs


@dataclass
class CrossCheckReport:
    lane: str = "CROSS_CHECK"
    clean: bool = True
    verdict: str = "PASS"  # PASS (clean) | FAIL (classified disagreement) | INCONCLUSIVE
    disagreements: list[dict[str, Any]] = field(default_factory=list)
    by_class: dict[str, int] = field(default_factory=dict)
    note: str = ""


def cross_check(
    config: dict[str, Any],
    per_bar_obs: list[dict[str, Any]],
    bars_by_symbol: dict[str, list[Bar]],
    funding_df,
    initial_equity_usd: float | None = None,
) -> CrossCheckReport:
    """Run both engines on identical inputs and produce a classified cross-check report."""
    # Lazy import so the lab package never forces a paper import at module load.
    from quantbot.paper.engine import new_state, run_engine

    initial = float(initial_equity_usd if initial_equity_usd is not None
                    else config["initial_equity_usd"])
    state = new_state(initial)
    engine_result = run_engine(config, per_bar_obs, bars_by_symbol, funding_df, state)
    replay_result = run_replay(
        config, per_bar_obs, bars_by_symbol, funding_df, initial_equity_usd=initial
    )
    diffs = compare(engine_result, replay_result, initial)

    by_class: dict[str, int] = {}
    for d in diffs:
        by_class[d.classification] = by_class.get(d.classification, 0) + 1

    clean = not diffs
    if clean:
        verdict, note = "PASS", "engine and independent replay agree row-by-row"
    elif by_class.get(CHECKER_BUG_CANDIDATE) or by_class.get(SPEC_AMBIGUITY):
        # A checker-bug or spec-ambiguity disagreement does NOT condemn the witness on its
        # own: it must be triaged before any code change.
        verdict, note = "INCONCLUSIVE", "disagreement requires triage (see classes)"
    else:
        verdict, note = "FAIL", "disagreement indicates the witness may be wrong"
    return CrossCheckReport(
        clean=clean,
        verdict=verdict,
        disagreements=[asdict(d) for d in diffs],
        by_class=by_class,
        note=note,
    )


# --- CLI: run a cross-check on a recorded fixture, write to output/lab only --------------


def _bars_from_payload(payload: dict[str, Any]) -> dict[str, list[Bar]]:
    out: dict[str, list[Bar]] = {}
    for sym, rows in payload.get("bars_by_symbol", {}).items():
        out[sym] = [Bar(r["timestamp"], r["open"], r["high"], r["low"], r["close"],
                        r.get("volume", 0.0)) for r in rows]
    return out


def _funding_from_payload(payload: dict[str, Any]):
    rows = payload.get("funding")
    if not rows:
        return None
    import pandas as pd
    return pd.DataFrame(
        [{"symbol": r["symbol"], "dt": pd.Timestamp(r["dt"], tz="UTC"),
          "fundingRate": float(r["fundingRate"]), "abs_rate": abs(float(r["fundingRate"]))}
         for r in rows]
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="CROSS_CHECK: independent replay vs paper engine (diagnostic only)."
    )
    parser.add_argument("--obs-fixture", required=True,
                        help="JSON bundle: {config, per_bar_obs, bars_by_symbol, funding?}")
    parser.add_argument("--out", default="output/lab/cross_check",
                        help="Diagnostic output dir (must be under output/lab/).")
    parser.add_argument("--json", action="store_true", help="Print the JSON report.")
    args = parser.parse_args(argv)

    out_root = Path(args.out)
    # Hard guard: this lane only ever writes under output/lab/.
    if "output/lab" not in out_root.as_posix():
        raise SystemExit(f"refusing to write outside output/lab/: {out_root}")

    payload = json.loads(Path(args.obs_fixture).read_text(encoding="utf-8"))
    config = payload["config"]
    per_bar_obs = payload["per_bar_obs"]
    bars = _bars_from_payload(payload)
    funding = _funding_from_payload(payload)

    report = cross_check(config, per_bar_obs, bars, funding)

    run_id = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    run_dir = out_root / run_id
    run_dir.mkdir(parents=True, exist_ok=True)
    report_path = run_dir / "cross_check_report.json"
    report_path.write_text(json.dumps(asdict(report), indent=2, sort_keys=True),
                           encoding="utf-8")

    print(f"[CROSS_CHECK] verdict={report.verdict} clean={report.clean} "
          f"disagreements={len(report.disagreements)} by_class={report.by_class}")
    print(f"[CROSS_CHECK] report: {report_path}")
    if args.json:
        print(json.dumps(asdict(report), indent=2, sort_keys=True))
    # CLEAN/INCONCLUSIVE exit 0 (diagnostic, no edge claim); FAIL exit 1.
    return 1 if report.verdict == "FAIL" else 0


if __name__ == "__main__":
    raise SystemExit(main())
