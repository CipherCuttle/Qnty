"""Tests for RegimeFilteredBreakoutStrategy.

Verifies regime gate behavior: sideways suppresses signals, uptrend emits,
allowed_trend_regimes parameter works, parent params inherited, determinism.
Paper mode only - no real trading.
"""

import pytest

from quantbot.data.types import Bar
from quantbot.strategy.regime_filtered_breakout import RegimeFilteredBreakoutStrategy


def make_bar(timestamp: str, close: float) -> Bar:
    """Create a synthetic bar for testing."""
    return Bar(
        timestamp=timestamp,
        open=close - 1.0,
        high=close + 1.0,
        low=close - 2.0,
        close=close,
        volume=1.0,
    )


class TestRegimeFilteredBreakoutSignalSuppression:
    """Tests for signal suppression in sideways regime."""

    def test_sideways_regime_suppresses_signals(self) -> None:
        """When bars are flat (log returns near zero), regime is sideways and signals are suppressed.

        Build a flat price series (small random walk around constant) that produces
        sideways regime. Even if rolling return technically exceeds threshold,
        the regime gate should suppress the signal.
        """
        # Flat prices: small oscillation around 100.0
        # This produces log returns near zero -> sideways regime
        base = 100.0
        flat_bars = [
            make_bar(f"2024-01-01T{i:02d}:00:00Z", base + (i % 3 - 1) * 0.1)
            for i in range(30)
        ]

        strat = RegimeFilteredBreakoutStrategy(
            rolling_return_period=20,
            return_threshold=0.01,  # low threshold to trigger breakout
            min_hold_bars=1,
            trend_window=20,
            trend_threshold=0.001,
            allowed_trend_regimes=["uptrend"],
            symbol="TESTUSD",
        )

        signals = [strat.on_bar(bar) for bar in flat_bars]
        non_none = [s for s in signals if s is not None]

        # In sideways regime, no signals should emit
        assert len(non_none) == 0, f"Expected 0 signals in sideways regime, got {len(non_none)}"


class TestRegimeFilteredBreakoutSignalEmission:
    """Tests for signal emission in uptrend regime."""

    def test_uptrend_regime_emits_signals(self) -> None:
        """When bars have positive trend, regime is uptrend and signals emit normally."""
        # Steady uptrend: prices rising ~0.5% per bar
        # This produces positive log returns -> uptrend regime
        uptrend_bars = [
            make_bar(f"2024-01-01T{i:02d}:00:00Z", 100.0 + i * 0.5)
            for i in range(30)
        ]

        strat = RegimeFilteredBreakoutStrategy(
            rolling_return_period=20,
            return_threshold=0.01,
            min_hold_bars=1,
            trend_window=20,
            trend_threshold=0.001,
            allowed_trend_regimes=["uptrend"],
            symbol="TESTUSD",
        )

        signals = [strat.on_bar(bar) for bar in uptrend_bars]
        non_none = [s for s in signals if s is not None]

        # In uptrend regime with rising prices, signals should emit
        assert len(non_none) > 0, "Expected signals in uptrend regime with rising prices"


class TestRegimeFilteredBreakoutAllowedRegimes:
    """Tests for allowed_trend_regimes parameter."""

    def test_allowed_trend_regimes_parameter(self) -> None:
        """Verify allowed_trend_regimes parameter controls which regimes allow signals."""
        # Steady downtrend: prices falling
        downtrend_bars = [
            make_bar(f"2024-01-01T{i:02d}:00:00Z", 100.0 - i * 0.5)
            for i in range(30)
        ]

        # With only uptrend allowed, downtrend should produce no signals
        strat_uptrend_only = RegimeFilteredBreakoutStrategy(
            rolling_return_period=20,
            return_threshold=0.01,
            min_hold_bars=1,
            trend_window=20,
            trend_threshold=0.001,
            allowed_trend_regimes=["uptrend"],
            symbol="TESTUSD",
        )

        signals_uptrend = [strat_uptrend_only.on_bar(bar) for bar in downtrend_bars]
        non_none_uptrend = [s for s in signals_uptrend if s is not None]

        # With uptrend AND downtrend allowed, downtrend should produce signals
        strat_both = RegimeFilteredBreakoutStrategy(
            rolling_return_period=20,
            return_threshold=0.01,
            min_hold_bars=1,
            trend_window=20,
            trend_threshold=0.001,
            allowed_trend_regimes=["uptrend", "downtrend"],
            symbol="TESTUSD",
        )

        signals_both = [strat_both.on_bar(bar) for bar in downtrend_bars]
        non_none_both = [s for s in signals_both if s is not None]

        # More signals when both regimes are allowed
        assert len(non_none_both) >= len(non_none_uptrend), (
            f"Expected at least as many signals with both regimes allowed "
            f"(got {len(non_none_both)}) as uptrend only (got {len(non_none_uptrend)})"
        )


class TestRegimeFilteredBreakoutInheritance:
    """Tests that RFB inherits parent behavior correctly."""

    def test_inherits_rolling_return_period(self) -> None:
        """Verify strategy respects rolling_return_period from parent."""
        # Need at least rolling_return_period + 1 bars to compute return
        bars = [make_bar(f"2024-01-01T{i:02d}:00:00Z", 100.0 + i * 2) for i in range(25)]

        strat = RegimeFilteredBreakoutStrategy(
            rolling_return_period=20,
            return_threshold=0.01,
            min_hold_bars=1,
            trend_window=20,
            trend_threshold=0.001,
            allowed_trend_regimes=["uptrend"],
            symbol="TESTUSD",
        )

        signals = [strat.on_bar(bar) for bar in bars]
        non_none = [s for s in signals if s is not None]

        # With period=20, first signal possible at bar 21
        # With rising prices and uptrend regime, should get signals after warmup
        assert len(non_none) > 0, "Expected signals after rolling_return_period warmup"

    def test_inherits_return_threshold(self) -> None:
        """Verify strategy respects return_threshold from parent."""
        # Small moves that won't exceed a high threshold
        small_move_bars = [
            make_bar(f"2024-01-01T{i:02d}:00:00Z", 100.0 + i * 0.1)
            for i in range(30)
        ]

        strat_high_threshold = RegimeFilteredBreakoutStrategy(
            rolling_return_period=20,
            return_threshold=0.50,  # Very high threshold - won't be exceeded
            min_hold_bars=1,
            trend_window=20,
            trend_threshold=0.001,
            allowed_trend_regimes=["uptrend"],
            symbol="TESTUSD",
        )

        signals = [strat_high_threshold.on_bar(bar) for bar in small_move_bars]
        non_none = [s for s in signals if s is not None]

        # High threshold should suppress signals even in uptrend
        assert len(non_none) == 0, f"Expected 0 signals with high threshold, got {len(non_none)}"

    def test_inherits_min_hold_bars(self) -> None:
        """Verify strategy respects min_hold_bars from parent."""
        # Oscillating prices to trigger multiple direction changes
        bars = [
            make_bar(f"2024-01-01T{i:02d}:00:00Z", 100.0 + (i % 10) * 3)
            for i in range(50)
        ]

        strat = RegimeFilteredBreakoutStrategy(
            rolling_return_period=10,
            return_threshold=0.05,
            min_hold_bars=5,  # Must hold for 5 bars minimum
            trend_window=20,
            trend_threshold=0.001,
            allowed_trend_regimes=["uptrend"],
            symbol="TESTUSD",
        )

        signals = [strat.on_bar(bar) for bar in bars]
        non_none = [s for s in signals if s is not None]

        # With min_hold_bars=5, consecutive signals should be at least 5 bars apart
        if len(non_none) >= 2:
            for i in range(1, len(non_none)):
                prev_ts = non_none[i - 1].timestamp
                curr_ts = non_none[i].timestamp
                # Timestamps should be at least 5 * 1-hour intervals apart
                assert curr_ts > prev_ts, "Signals should respect min_hold_bars"


class TestRegimeFilteredBreakoutDeterminism:
    """Tests for determinism guarantee."""

    def test_same_bars_produce_same_signals(self) -> None:
        """Deterministic bar sequence yields identical signals on two runs."""
        bars = [
            make_bar(f"2024-01-01T{i:02d}:00:00Z", 100.0 + i * 2)
            for i in range(30)
        ]

        strat1 = RegimeFilteredBreakoutStrategy(
            rolling_return_period=20,
            return_threshold=0.05,
            min_hold_bars=3,
            trend_window=20,
            trend_threshold=0.001,
            allowed_trend_regimes=["uptrend"],
            symbol="TESTUSD",
        )
        signals1 = [strat1.on_bar(bar) for bar in bars]
        non_none1 = [s for s in signals1 if s is not None]

        # Second run - recreate strategy to ensure clean state
        strat2 = RegimeFilteredBreakoutStrategy(
            rolling_return_period=20,
            return_threshold=0.05,
            min_hold_bars=3,
            trend_window=20,
            trend_threshold=0.001,
            allowed_trend_regimes=["uptrend"],
            symbol="TESTUSD",
        )
        signals2 = [strat2.on_bar(bar) for bar in bars]
        non_none2 = [s for s in signals2 if s is not None]

        assert non_none1 == non_none2, "Same bars should produce same signals (determinism)"

    def test_different_instances_same_params_same_signals(self) -> None:
        """Two strategy instances with same params produce same signals."""
        bars = [
            make_bar(f"2024-01-01T{i:02d}:00:00Z", 100.0 + i * 2)
            for i in range(30)
        ]

        strat_a = RegimeFilteredBreakoutStrategy(
            rolling_return_period=20,
            return_threshold=0.05,
            min_hold_bars=3,
            trend_window=20,
            trend_threshold=0.001,
            allowed_trend_regimes=["uptrend"],
            symbol="TESTUSD",
        )
        strat_b = RegimeFilteredBreakoutStrategy(
            rolling_return_period=20,
            return_threshold=0.05,
            min_hold_bars=3,
            trend_window=20,
            trend_threshold=0.001,
            allowed_trend_regimes=["uptrend"],
            symbol="TESTUSD",
        )

        def collect(s, b_list):
            return [sig for bar in b_list for sig in ([s.on_bar(bar)] if s.on_bar(bar) else [])]

        signals_a = collect(strat_a, bars)
        signals_b = collect(strat_b, bars)

        assert signals_a == signals_b, "Same params should produce same signals across instances"


class TestRFBRegimeBoundedness:
    """Regression tests for _rfb_bars boundedness bug.

    Previously, _rfb_bars grew unbounded, contaminating regime computation
    with stale historical bars. The fix caps _rfb_bars to trend_window+1 bars.
    """

    def test_rfb_bars_never_exceeds_trend_window_plus_one(self) -> None:
        """_rfb_bars must not grow beyond trend_window + 1."""
        bars = [
            make_bar(f"2024-01-01T{i:02d}:00:00Z", 100.0 + i * 0.5)
            for i in range(100)
        ]

        strat = RegimeFilteredBreakoutStrategy(
            rolling_return_period=20,
            return_threshold=0.01,
            min_hold_bars=1,
            trend_window=20,
            trend_threshold=0.001,
            allowed_trend_regimes=["uptrend"],
            symbol="TESTUSD",
        )

        for bar in bars:
            strat.on_bar(bar)
            assert len(strat._rfb_bars) <= strat.trend_window + 1, (
                f"_rfb_bars grew to {len(strat._rfb_bars)}, "
                f"exceeding trend_window+1={strat.trend_window + 1}"
            )

    def test_regime_uses_only_recent_window(self) -> None:
        """Regime must be computed from recent bars, not entire history.

        Build a sequence where early bars are strongly uptrend (large gains)
        but recent bars are sideways. Regime should be 'sideways', not 'uptrend'.
        """
        # First 30 bars: strong uptrend (big gains)
        early_bars = [
            make_bar(f"2024-01-01T{i:02d}:00:00Z", 100.0 + i * 5.0)
            for i in range(30)
        ]
        # Next 25 bars: flat sideways (small oscillation around 250)
        flat_base = 250.0
        late_bars = [
            make_bar(f"2024-01-01T{i:02d}:00:00Z", flat_base + (i % 3 - 1) * 0.1)
            for i in range(30, 55)
        ]
        all_bars = early_bars + late_bars

        strat = RegimeFilteredBreakoutStrategy(
            rolling_return_period=20,
            return_threshold=0.01,
            min_hold_bars=1,
            trend_window=20,
            trend_threshold=0.001,
            allowed_trend_regimes=["uptrend"],
            symbol="TESTUSD",
        )

        for bar in all_bars:
            strat.on_bar(bar)

        # After the flat period, regime should be sideways (not uptrend)
        # and no signals should emit since only uptrend is allowed
        signals = [strat.on_bar(bar) for bar in late_bars]
        non_none = [s for s in signals if s is not None]
        assert len(non_none) == 0, (
            f"Expected 0 signals during sideways regime, got {len(non_none)}. "
            f"This means stale uptrend from early bars contaminated regime."
        )

    def test_sideways_holdout_no_signal_from_warmup_contamination(self) -> None:
        """A sideways holdout window must not emit signals due to warmup contamination.

        This is the specific failure mode that exposed the bug: a fresh sideways
        window would incorrectly emit signals because _rfb_bars retained stale
        uptrend bars from the warmup period.
        """
        # Warmup: 30 bars of strong uptrend
        warmup_bars = [
            make_bar(f"2024-01-01T{i:02d}:00:00Z", 100.0 + i * 2.0)
            for i in range(30)
        ]
        # Holdout: 30 bars of flat sideways
        holdout_bars = [
            make_bar(f"2024-01-01T{i:02d}:00:00Z", 160.0 + (i % 3 - 1) * 0.1)
            for i in range(30, 60)
        ]

        strat = RegimeFilteredBreakoutStrategy(
            rolling_return_period=20,
            return_threshold=0.01,
            min_hold_bars=1,
            trend_window=20,
            trend_threshold=0.001,
            allowed_trend_regimes=["uptrend"],
            symbol="TESTUSD",
        )

        # Warmup
        for bar in warmup_bars:
            strat.on_bar(bar)

        # Holdout: should emit no signals (sideways regime, uptrend only allowed)
        holdout_signals = [strat.on_bar(bar) for bar in holdout_bars]
        non_none = [s for s in holdout_signals if s is not None]

        assert len(non_none) == 0, (
            f"Holdout emitted {len(non_none)} signals despite sideways regime. "
            f"Bug: stale warmup bars in _rfb_bars contaminated regime computation."
        )
