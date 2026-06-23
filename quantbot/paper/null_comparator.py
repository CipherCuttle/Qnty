"""Offline matched-null selector (Phase 2, docs ref: PARALLEL_SHADOW_LANES_PLAN §5).

A *pure*, deterministic, seeded selector that replaces signal SELECTION with a
matched random draw while preserving everything else the production engine
already controls (same bar clock, same universe, same fees/slippage/funding/fill
model — all enforced downstream by ``run_engine``).

Scope (Phase 2 only):
  * Long-only and cardinality-matched. The production engine
    (``quantbot/paper/engine.py::run_engine``) is long-only and fixed-notional,
    and selection enters solely through ``obs.active_symbols``. So the null only
    needs to pick *which* symbols are active per bar, matched in count to the
    target strategy. Direction randomization (shorts) is intentionally OUT of
    scope until the engine supports shorts.

This module is import-only: no I/O, no DB, no network, no clock, no prices.
It makes NO profitability or edge claim. The strategy edge is EDGE_UNPROVEN.
"""

from __future__ import annotations

import hashlib


def _rank_key(seed: int, bar_id: str, symbol: str) -> str:
    """Deterministic per-(seed, bar, symbol) ordering key.

    Folding the seed and the bar id into each symbol's draw makes the selection
    reproducible for a fixed ``(seed, bar_id)`` and divergence-checkable. It uses
    only the inputs themselves — never a price, return, PnL, or any future bar —
    so there is no lookahead.
    """
    raw = f"{seed}|{bar_id}|{symbol}"
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def select_null_active(
    universe: list[str],
    target_count: int,
    seed: int,
    bar_id: str,
) -> list[str]:
    """Pick ``target_count`` active symbols for one bar via a matched seeded draw.

    Args:
        universe: candidate symbols for the bar. De-duplicated and sorted before
            drawing, so the result is independent of input ordering.
        target_count: number of symbols the paired target strategy holds this bar
            (cardinality match). 0 returns an empty list. Must not exceed the
            number of distinct symbols in ``universe``.
        seed: PRNG seed for this null draw. A single seed is only a plumbing/
            fixture test, not a comparison result; a real null needs many seeds.
        bar_id: stable identifier for the bar (e.g. its on-grid timestamp). Folded
            into each draw so selections differ across bars under the same seed.

    Returns:
        A sorted list of distinct symbols, all drawn from ``universe``, of length
        exactly ``target_count``.

    Properties (verified in tests/test_paper_matched_null.py):
        deterministic for a fixed (universe, target_count, seed, bar_id);
        cardinality-matched; no duplicates; no symbol outside the universe;
        stable under reordering of ``universe``; no lookahead (no prices, PnL,
        outcomes, or future bars consulted). Pure — no I/O, DB, or network.
    """
    if not isinstance(target_count, int) or isinstance(target_count, bool):
        raise TypeError(f"target_count must be an int (got {target_count!r})")
    if target_count < 0:
        raise ValueError(f"target_count must be >= 0 (got {target_count})")

    candidates = sorted(set(universe))
    if target_count > len(candidates):
        raise ValueError(
            f"target_count {target_count} exceeds universe size {len(candidates)}"
        )
    if target_count == 0:
        return []

    ranked = sorted(candidates, key=lambda sym: _rank_key(seed, bar_id, sym))
    return sorted(ranked[:target_count])
