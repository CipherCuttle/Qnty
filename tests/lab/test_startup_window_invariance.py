"""T1 (ADVERSARIAL) — VolatilityTracker startup-window path-independence.

Property: a VolatilityTracker's full state and output depend ONLY on the final bounded
`lookback`-bar window, never on the prefix that was observed and later evicted. This extends
the incident-regression class (the production 2e903... -> 46640... digest divergence caused
by an online-Welford eviction bug) into a property test over many deterministic prefixes.

A failure here = a path-dependence regression of the eviction bug class = the witness can be
fooled by run history. STOP and fix the witness.

Diagnostic lane: ADVERSARIAL (FORWARD remains authoritative). No edge claim.
"""

from __future__ import annotations

import math
import statistics

import pytest

from quantbot.experiment.volnorm_portfolio import VolatilityTracker

LOOKBACK = 90


def _final_window(seed: int) -> list[float]:
    """A deterministic 90-value final window (distinct per seed, no RNG)."""
    return [math.sin((i + seed) / 3.0) / 100.0 + math.cos((i * seed + 1) / 7.0) / 200.0
            for i in range(LOOKBACK)]


# Deterministic prefixes of varied length AND content, including the empty prefix and
# adversarial large-magnitude spikes that, under a naive online update, would leave residue
# in mean/m2 after eviction.
_PREFIXES = [
    [],
    [0.25],
    [0.9, -0.8, 0.7, -0.6],
    [10.0, -10.0, 5.0],                       # large spikes (eviction-residue trap)
    [0.0] * 130,                              # longer than lookback, all zeros
    [(-1.0) ** i * (i % 7) for i in range(200)],  # long, alternating, > lookback
    list(_final_window(99)),                  # a full unrelated window as prefix
]


def _drive(prefix: list[float], window: list[float]) -> VolatilityTracker:
    t = VolatilityTracker(lookback=LOOKBACK)
    for v in prefix + window:
        t.update(v)
    return t


@pytest.mark.parametrize("seed", [0, 1, 7, 42])
def test_identical_final_window_yields_identical_state_regardless_of_prefix(seed: int) -> None:
    window = _final_window(seed)
    baseline = _drive([], window)

    for prefix in _PREFIXES:
        t = _drive(prefix, window)
        # Full internal state must be byte-identical, not merely close.
        assert t._returns == baseline._returns, f"buffer diverged for prefix len {len(prefix)}"
        assert t._mean == baseline._mean
        assert t._m2 == baseline._m2
        assert t.volatility == baseline.volatility


@pytest.mark.parametrize("seed", [0, 3, 11])
def test_volatility_matches_independent_stdev_of_final_window(seed: int) -> None:
    window = _final_window(seed)
    for prefix in _PREFIXES:
        t = _drive(prefix, window)
        # Independent re-derivation: sample stdev of EXACTLY the final window.
        assert t.volatility == pytest.approx(statistics.stdev(window))


def test_prefix_longer_than_lookback_fully_evicts() -> None:
    """A prefix longer than lookback must be completely forgotten once the window fills."""
    window = _final_window(5)
    poisoned = _drive([1e6, -1e6] * 100, window)  # extreme prefix, fully evicted
    clean = _drive([], window)
    assert poisoned._returns == clean._returns
    assert poisoned.volatility == clean.volatility
    # The buffer never exceeds the bound.
    assert len(poisoned._returns) == LOOKBACK
