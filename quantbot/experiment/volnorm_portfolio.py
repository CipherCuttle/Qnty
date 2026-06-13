"""
Volatility-Normalized Portfolio Engine with Explicit Heat Cap
==============================================================

Package: TSMOM Package V2 — Volatility-Normalized with Heat Cap
Branch: qnty/tsmom-package-v2-volnorm

This module provides a portfolio engine that:
1. Sizes positions by inverse volatility (vol-normalized)
2. Caps aggregate portfolio heat at a configurable maximum
3. Maintains per-bar portfolio equity truth

FROZEN: signal family, thresholds, universe logic, carry semantics.
ONLY CHANGES: position sizing and portfolio heat handling.
"""

from __future__ import annotations

import math


# =============================================================================
# CONFIGURATION — HEAT CAP
# =============================================================================

# Target portfolio heat (annualized volatility units).
# At heat=1.0, the portfolio targets 1.0 unit of risk per unit of equity.
# This cap constrains total risk contribution across all active positions.
HEAT_CAP: float = 1.0

# Rolling window for volatility estimation (in bars).
# 8h bars: 90 bars ≈ 30 days.
VOL_LOOKBACK_BARS: int = 90

# Minimum volatility floor to prevent division by zero.
VOL_FLOOR: float = 1e-6


# =============================================================================
# VOLATILITY TRACKER — PER-SYMBOL ROLLING STD DEV OF LOG RETURNS
# =============================================================================

class VolatilityTracker:
    """
    Tracks rolling volatility (std dev of log returns) for a single symbol.

    Statistics are recomputed from the bounded return buffer after each update.
    This makes volatility depend only on the final rolling window, not on returns
    that were previously observed and later evicted.
    """
    
    def __init__(self, lookback: int = VOL_LOOKBACK_BARS, floor: float = VOL_FLOOR):
        self.lookback = lookback
        self.floor = floor
        self._returns: list[float] = []
        self._mean: float = 0.0
        self._m2: float = 0.0
        self._n: int = 0
    
    def update(self, log_return: float) -> None:
        """Update with a new log return."""
        self._returns.append(log_return)
        if len(self._returns) > self.lookback:
            self._returns.pop(0)

        self._n = len(self._returns)
        self._mean = math.fsum(self._returns) / max(1, self._n)
        self._m2 = math.fsum((value - self._mean) ** 2 for value in self._returns)
    
    @property
    def volatility(self) -> float:
        """Current volatility estimate (sample std dev)."""
        if self._n < 2:
            return self.floor
        variance = self._m2 / (self._n - 1)
        return max(math.sqrt(variance), self.floor)
    
    def reset(self) -> None:
        """Clear all state."""
        self._returns.clear()
        self._mean = 0.0
        self._m2 = 0.0
        self._n = 0


# =============================================================================
# PER-BAR PORTFOLIO WEIGHT COMPUTATION
# =============================================================================

def compute_vol_normed_weights(
    active_symbols: list[str],
    vol_trackers: dict[str, VolatilityTracker],
    heat_cap: float = HEAT_CAP,
) -> dict[str, float]:
    """
    Compute volatility-normalized position weights with heat cap.
    
    Each position gets weight proportional to 1/volatility.
    Total portfolio heat is then scaled to respect heat_cap.
    
    Args:
        active_symbols: List of symbols with active long signals this bar.
        vol_trackers: Dict mapping symbol -> VolatilityTracker with history.
        heat_cap: Maximum aggregate heat (risk) allowed.
    
    Returns:
        Dict mapping symbol -> position weight (scaled to respect heat_cap).
    """
    if not active_symbols:
        return {}
    
    # Step 1: Raw inverse-vol weights
    raw_weights: dict[str, float] = {}
    for symbol in active_symbols:
        tracker = vol_trackers.get(symbol)
        if tracker is None:
            # No history yet — use equal weight
            raw_weights[symbol] = 1.0
        else:
            # Inverse vol weighting
            raw_weights[symbol] = 1.0 / tracker.volatility
    
    # Step 2: Normalize raw weights to sum to 1.0 (for fair comparison)
    total_raw = sum(raw_weights.values())
    if total_raw <= 0:
        # Fallback to equal weight
        eq_w = 1.0 / len(active_symbols)
        return {s: eq_w for s in active_symbols}
    
    norm_weights = {s: w / total_raw for s, w in raw_weights.items()}
    
    # Step 3: Heat cap scaling
    # For equal-risk contribution, we want each position to contribute equally
    # to total portfolio volatility. With inverse-vol weighting, each position's
    # risk contribution = weight * volatility ≈ constant.
    # Heat cap constrains the sum of risk contributions.
    #
    # Effective portfolio heat = sum(weight_i * volatility_i)
    # With inverse-vol weights: weight_i = (1/vol_i) / sum(1/vol_j)
    # So heat = sum((1/vol_i) / sum(1/vol_j) * vol_i) = sum(1) / sum(1/vol_j) = n / sum(1/vol_j)
    #
    # We scale down if heat > heat_cap
    portfolio_heat = sum(norm_weights[s] * vol_trackers[s].volatility 
                         for s in active_symbols 
                         if s in vol_trackers)
    
    if portfolio_heat > heat_cap and portfolio_heat > 0:
        # Scale all weights proportionally to respect heat cap
        scale_factor = heat_cap / portfolio_heat
        return {s: w * scale_factor for s, w in norm_weights.items()}
    
    return norm_weights


# =============================================================================
# PACKAGE IDENTITY — ARTIFACT TRUTH
# =============================================================================

PACKAGE_IDENTITY = {
    "package_name": "tsmom-package-v2-volnorm",
    "package_version": "1.0.0",
    "branch": "qnty/tsmom-package-v2-volnorm",
    "sizing_method": "volatility-normalized (inverse-vol)",
    "position_weighting": "inverse-vol normalized, heat-capped",
    "heat_cap": HEAT_CAP,
    "vol_lookback_bars": VOL_LOOKBACK_BARS,
    "vol_floor": VOL_FLOOR,
    "benchmark_mode": "gross (no funding adjustment)",
    "carry_mode": "net of realistic funding costs",
    "carry_symmetry": "long/short symmetric carry burden",
    "heat_cap_active": True,
}
