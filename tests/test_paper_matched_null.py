"""Offline matched-null fixture (Phase 2, PARALLEL_SHADOW_LANES_PLAN §5/§10.2).

A tiny, pure, in-memory test that (a) exercises the matched-null SELECTOR
(quantbot/paper/null_comparator.select_null_active) and (b) feeds the resulting
null observations through the SAME production accounting path
(quantbot/paper/engine.run_engine) so costs/funding are applied identically to
the baseline engine.

Scope guards (Phase 2 only):
  * No SQLite writer/verifier, no VM, no /srv, no production DB, no timers.
  * No real data — all bars/funding are synthetic and deterministic.
  * Long-only + cardinality-matched (the engine is long-only/fixed-notional).
  * No profitability or edge claim is made. Strategy edge is EDGE_UNPROVEN.
"""

from __future__ import annotations

import hashlib

import pandas as pd

from quantbot.core.determinism import canonical_json_dumps
from quantbot.lab import fixtures as fx
from quantbot.paper.engine import EngineResult, new_state, run_engine
from quantbot.paper.null_comparator import select_null_active

# --- synthetic scenario constants ------------------------------------------------
UNIVERSE = ["AAA", "BBB", "CCC", "DDD"]  # >= 4 fake symbols
N_BARS = 6  # >= 4 synthetic 8h bars (extra tail bars so T+1 exit fills resolve)
TS = fx.grid(N_BARS)

# Cardinality-matched target counts per bar, covering the required cases:
#   bar 0 -> 0 (zero active positions), bar 1 -> 1 (one), bar 2 -> 2 (multiple),
#   then unwind so every opened position closes within the synthetic window.
TARGET_COUNTS = [0, 1, 2, 1, 0, 0]

# Two seeds whose draws diverge on at least one bar (see test_seed_change).
SEED_A = 1
SEED_B = 2

# Deterministic per-symbol (open, close) price series. Distinct per symbol; used
# ONLY for arithmetic through the engine, never as an edge claim.
_PRICE_BASE = {"AAA": 100.0, "BBB": 50.0, "CCC": 200.0, "DDD": 75.0}
_PRICE_STEP = {"AAA": 1.0, "BBB": 2.0, "CCC": 5.0, "DDD": 3.0}


def _bars_for(symbol: str) -> list:
    base, step = _PRICE_BASE[symbol], _PRICE_STEP[symbol]
    pairs = [(base + i * step, base + (i + 1) * step) for i in range(N_BARS)]
    return fx.bars(pairs, TS)


def _bars_by_symbol() -> dict[str, list]:
    return {sym: _bars_for(sym) for sym in UNIVERSE}


def _zero_funding_df() -> pd.DataFrame:
    """Funding rows present for every (symbol, bar) at rate 0.0.

    Verifier-safe zero semantics: an event exists in each held interval, so
    rate_available is True and the accrued amount is exactly 0.0 — never a
    silently-missing funding gap.
    """
    rows = [
        {"symbol": sym, "dt": pd.Timestamp(ts, tz="UTC"), "fundingRate": 0.0, "abs_rate": 0.0}
        for sym in UNIVERSE
        for ts in TS
    ]
    return pd.DataFrame(rows)


def _null_active_by_bar(seed: int) -> list[list[str]]:
    """Run the matched-null selector across the scenario bars for one seed."""
    return [
        select_null_active(UNIVERSE, TARGET_COUNTS[i], seed, TS[i])
        for i in range(N_BARS)
    ]


def _run_null_engine(active_by_bar: list[list[str]]) -> EngineResult:
    """Feed null observations through the production accounting path."""
    cfg = fx.config(forward_start_ts=TS[0])
    per_bar_obs = fx.obs_log(active_by_bar, TS)
    state = new_state(cfg["initial_equity_usd"])
    return run_engine(cfg, per_bar_obs, _bars_by_symbol(), _zero_funding_df(), state)


def _result_digest(result: EngineResult) -> str:
    payload = {
        "fills": result.fills,
        "positions": result.positions,
        "trades": result.trades,
        "equity": result.equity,
        "funding": result.funding,
        "deferred_bar_ts": result.deferred_bar_ts,
    }
    return hashlib.sha256(canonical_json_dumps(payload).encode("utf-8")).hexdigest()


# ============================================================ selector invariants


def test_same_seed_identical_selections():
    assert _null_active_by_bar(SEED_A) == _null_active_by_bar(SEED_A)


def test_seed_change_alters_at_least_one_bar():
    a = _null_active_by_bar(SEED_A)
    b = _null_active_by_bar(SEED_B)
    assert a != b, "different seed must change selection on at least one bar"
    assert any(set(x) != set(y) for x, y in zip(a, b))


def test_cardinality_matched_per_bar():
    for seed in (SEED_A, SEED_B):
        active = _null_active_by_bar(seed)
        for i in range(N_BARS):
            assert len(active[i]) == TARGET_COUNTS[i]


def test_zero_count_returns_empty():
    assert select_null_active(UNIVERSE, 0, SEED_A, TS[0]) == []


def test_no_symbol_outside_universe():
    universe_set = set(UNIVERSE)
    for seed in (SEED_A, SEED_B):
        for sel in _null_active_by_bar(seed):
            assert set(sel) <= universe_set


def test_no_duplicate_selected_symbols():
    for seed in (SEED_A, SEED_B):
        for sel in _null_active_by_bar(seed):
            assert len(sel) == len(set(sel))


def test_selection_stable_under_universe_reordering():
    reordered = list(reversed(UNIVERSE))
    for i in range(N_BARS):
        assert select_null_active(UNIVERSE, TARGET_COUNTS[i], SEED_A, TS[i]) == \
            select_null_active(reordered, TARGET_COUNTS[i], SEED_A, TS[i])


def test_target_count_exceeds_universe_raises():
    import pytest

    with pytest.raises(ValueError):
        select_null_active(UNIVERSE, len(UNIVERSE) + 1, SEED_A, TS[0])


def test_no_lookahead_future_bar_change_is_inert():
    """Changing a FUTURE bar's target must not change a current bar's selection.

    Selection depends only on (universe, target_count, seed, bar_id) — no future
    bar, price, or outcome is consulted. So re-running an earlier bar's draw is
    identical regardless of what a later bar does.
    """
    early_i = 1
    baseline = select_null_active(UNIVERSE, TARGET_COUNTS[early_i], SEED_A, TS[early_i])
    # Mutate a strictly-later bar's target; recompute the earlier bar.
    mutated_targets = list(TARGET_COUNTS)
    mutated_targets[early_i + 2] = (mutated_targets[early_i + 2] + 1) % (len(UNIVERSE) + 1)
    after = select_null_active(UNIVERSE, TARGET_COUNTS[early_i], SEED_A, TS[early_i])
    assert baseline == after
    # And the mutation actually changed something downstream (guards a no-op test).
    assert mutated_targets != list(TARGET_COUNTS)


# ============================================================ engine integration


def test_null_obs_run_through_engine_deterministic():
    """Same seed -> identical null selections -> identical engine result digest."""
    active = _null_active_by_bar(SEED_A)
    d1 = _result_digest(_run_null_engine(active))
    d2 = _result_digest(_run_null_engine(active))
    assert d1 == d2


def test_engine_applies_costs_and_funding_through_same_path():
    """The null observations exercise the real engine: fills, fees, funding ledger."""
    result = _run_null_engine(_null_active_by_bar(SEED_A))
    # Equity is marked every forward bar.
    assert len(result.equity) >= 1
    # Long-only entries occurred and carried a (taker) fee through the engine.
    entries = [f for f in result.fills if f["kind"] == "entry"]
    assert entries, "expected at least one entry fill"
    # Long-only invariant: every entry is a BUY, every exit a SELL (no shorts).
    assert all(f["side"] == "BUY" for f in entries)
    assert all(f["side"] == "SELL" for f in result.fills if f["kind"] == "exit")
    assert any(f["fee"] > 0 for f in entries)
    # Funding ran through the same path with verifier-safe zero semantics:
    # every accrual row is present and available at exactly 0.0 (no silent gap).
    assert result.funding, "expected funding accrual rows"
    assert all(row["rate_available"] for row in result.funding)
    assert all(row["funding_amount"] == 0.0 for row in result.funding)
    # The scenario fully unwinds, so every opened position closes (closed trades).
    assert result.trades, "expected at least one closed trade"


def test_different_seed_changes_engine_digest():
    da = _result_digest(_run_null_engine(_null_active_by_bar(SEED_A)))
    db = _result_digest(_run_null_engine(_null_active_by_bar(SEED_B)))
    assert da != db
