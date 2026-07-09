"""Fixture-only cost-model helpers for offline edge validation.

PR C — deterministic, pure cost-model math on fixture assumptions only.
Stdlib only (no third-party imports).  **No** engine, exchange, DB, paper,
or file-write imports.

Scope boundary (do not violate):
- These functions convert a *notional* and *bps assumptions* into per-side and
  round-trip cost placeholders.  They are pure arithmetic.
- They do **not** compute strategy performance, do **not** apply costs to any
  trade or ledger, do **not** call the paper engine, and do **not** replay real
  funding.  ``calculate_fixture_funding_cost`` multiplies a *fixture* funding
  rate by a notional — it is not a funding replay.
- Producing a cost number here is NOT an edge/profit/live-readiness claim.
  EDGE_UNPROVEN / BLOCK_LIVE_INTEGRATION remain in force.
"""

from __future__ import annotations

# Bump when the cost-model math or its assumptions change shape.
COST_MODEL_VERSION: str = "1.0"

# One basis point = 1e-4 of notional.
_BPS_DENOMINATOR: float = 10_000.0


# ── Validation helpers ─────────────────────────────────────────────────────


def _validate_notional(notional: float) -> None:
    """Reject negative notional.  Zero is allowed (yields zero cost)."""
    if notional < 0:
        raise ValueError(f"notional must be >= 0, got {notional}")


def _validate_bps(bps: float, name: str) -> None:
    """Reject negative bps for commission/slippage/spread assumptions.

    Funding rate is intentionally *not* routed through this check because a
    negative funding rate is economically meaningful (funding received).
    """
    if bps < 0:
        raise ValueError(f"{name} must be >= 0, got {bps}")


# ── Per-side cost helpers ──────────────────────────────────────────────────


def calculate_commission_cost(notional: float, commission_bps_per_side: float) -> float:
    """Per-side commission cost = notional * commission_bps_per_side / 10_000."""
    _validate_notional(notional)
    _validate_bps(commission_bps_per_side, "commission_bps_per_side")
    return notional * commission_bps_per_side / _BPS_DENOMINATOR


def calculate_slippage_cost(notional: float, slippage_bps_per_side: float) -> float:
    """Per-side slippage cost = notional * slippage_bps_per_side / 10_000."""
    _validate_notional(notional)
    _validate_bps(slippage_bps_per_side, "slippage_bps_per_side")
    return notional * slippage_bps_per_side / _BPS_DENOMINATOR


def calculate_spread_cost(notional: float, spread_bps_per_side: float) -> float:
    """Per-side spread cost = notional * spread_bps_per_side / 10_000."""
    _validate_notional(notional)
    _validate_bps(spread_bps_per_side, "spread_bps_per_side")
    return notional * spread_bps_per_side / _BPS_DENOMINATOR


# ── Round-trip aggregation ─────────────────────────────────────────────────


def calculate_round_trip_cost(
    notional: float,
    commission_bps_per_side: float,
    slippage_bps_per_side: float,
    spread_bps_per_side: float,
) -> dict:
    """Aggregate per-side costs into a round-trip (entry + exit) cost breakdown.

    A round trip crosses the book twice, so each per-side component is counted
    for both the entry and the exit side (i.e. multiplied by 2).

    Returns a dict with the notional, each round-trip component, the total
    round-trip cost, the total round-trip cost in bps, and the cost-model
    version.  This is fixture math only — not a strategy PnL.
    """
    commission_per_side = calculate_commission_cost(notional, commission_bps_per_side)
    slippage_per_side = calculate_slippage_cost(notional, slippage_bps_per_side)
    spread_per_side = calculate_spread_cost(notional, spread_bps_per_side)

    commission_round_trip = commission_per_side * 2.0
    slippage_round_trip = slippage_per_side * 2.0
    spread_round_trip = spread_per_side * 2.0
    total_cost = commission_round_trip + slippage_round_trip + spread_round_trip
    total_round_trip_bps = (
        commission_bps_per_side + slippage_bps_per_side + spread_bps_per_side
    ) * 2.0

    return {
        "notional": notional,
        "commission_cost": commission_round_trip,
        "slippage_cost": slippage_round_trip,
        "spread_cost": spread_round_trip,
        "total_cost": total_cost,
        "total_round_trip_bps": total_round_trip_bps,
        "cost_model_version": COST_MODEL_VERSION,
    }


# ── Optional fixture funding placeholder ───────────────────────────────────


def calculate_fixture_funding_cost(notional: float, funding_rate: float) -> float:
    """Fixture funding-cost placeholder = notional * funding_rate.

    ``funding_rate`` may be negative (funding received) as well as positive
    (funding paid), so it is deliberately not rejected for being negative.

    This is a placeholder over a *single fixture rate*; it is not a replay of
    real or prod funding history.
    """
    _validate_notional(notional)
    return notional * funding_rate
