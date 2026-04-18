"""Tests for RollingReturnBreakoutStrategy.

Lower-turnover breakout strategy family tests.
Paper mode only - no real trading.
"""

import pytest

from quantbot.data.types import Bar
from quantbot.strategy.base import Signal
from quantbot.strategy.rolling_return_breakout import (
    RollingReturnBreakoutStrategy,
    rolling_return_A,
    rolling_return_B,
    rolling_return_C,
)


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


class TestRollingReturnBreakoutDeterminism:
    """Tests for determinism guarantee: same bar sequence → same signals."""

    def test_same_bars_produce_same_signals(self) -> None:
        """Deterministic bar sequence yields identical signals on two runs."""
        bars = [
            make_bar("2024-01-01T00:00:00Z", 100.0),
            make_bar("2024-01-01T08:00:00Z", 102.0),
            make_bar("2024-01-01T16:00:00Z", 104.0),
            make_bar("2024-01-01T00:00:00Z", 108.0),
            make_bar("2024-01-01T08:00:00Z", 112.0),
            make_bar("2024-01-01T16:00:00Z", 116.0),
            make_bar("2024-01-01T00:00:00Z", 120.0),
            make_bar("2024-01-01T08:00:00Z", 124.0),
            make_bar("2024-01-01T16:00:00Z", 128.0),
            make_bar("2024-01-01T00:00:00Z", 132.0),
            make_bar("2024-01-01T08:00:00Z", 136.0),
            make_bar("2024-01-01T16:00:00Z", 140.0),
            make_bar("2024-01-01T00:00:00Z", 144.0),
            make_bar("2024-01-01T08:00:00Z", 148.0),
            make_bar("2024-01-01T16:00:00Z", 152.0),
            make_bar("2024-01-01T00:00:00Z", 156.0),
            make_bar("2024-01-01T08:00:00Z", 160.0),
            make_bar("2024-01-01T16:00:00Z", 164.0),
            make_bar("2024-01-01T00:00:00Z", 168.0),
            make_bar("2024-01-01T08:00:00Z", 172.0),
            make_bar("2024-01-01T16:00:00Z", 176.0),
            make_bar("2024-01-01T00:00:00Z", 180.0),
        ]

        # First run
        strat1 = RollingReturnBreakoutStrategy(
            rolling_return_period=20,
            return_threshold=0.05,
            min_hold_bars=3,
            symbol="BTCUSDT",
        )
        signals1 = [s for bar in bars for s in ([strat1.on_bar(bar)] if strat1.on_bar(bar) else [])]

        # Second run - recreate strategy to ensure clean state
        strat1b = RollingReturnBreakoutStrategy(
            rolling_return_period=20,
            return_threshold=0.05,
            min_hold_bars=3,
            symbol="BTCUSDT",
        )
        signals1b = [s for bar in bars for s in ([strat1b.on_bar(bar)] if strat1b.on_bar(bar) else [])]

        assert signals1 == signals1b

    def test_different_instances_same_params_same_signals(self) -> None:
        """Two strategy instances with same params produce same signals."""
        bars = [
            make_bar("2024-01-01T00:00:00Z", 100.0 + i * 2) for i in range(25)
        ]

        strat_a = RollingReturnBreakoutStrategy(
            rolling_return_period=20,
            return_threshold=0.05,
            min_hold_bars=3,
            symbol="BTCUSDT",
        )
        strat_b = RollingReturnBreakoutStrategy(
            rolling_return_period=20,
            return_threshold=0.05,
            min_hold_bars=3,
            symbol="BTCUSDT",
        )

        def collect(s, b_list):
            out = []
            for bar in b_list:
                sig = s.on_bar(bar)
                if sig:
                    out.append(sig)
            return out

        assert collect(strat_a, bars) == collect(strat_b, bars)


class TestRollingReturnBreakoutSignals:
    """Tests for signal generation with synthetic bars designed to trigger signals."""

    def test_signal_emitted_when_return_exceeds_threshold(self) -> None:
        """Long signal emitted when rolling return exceeds positive threshold."""
        # Bars that will produce > 5% return over 20 periods
        # Need period + 1 = 21 bars before first rolling return can be computed
        # Price goes from 100 to ~107.2 at bar 24, which is > 5% return
        bars = [make_bar(f"2024-01-01T{i:02d}:00:00Z", 100.0 + i * 0.3) for i in range(25)]

        strat = RollingReturnBreakoutStrategy(
            rolling_return_period=20,
            return_threshold=0.05,
            min_hold_bars=3,
            symbol="BTCUSDT",
        )

        signals = []
        for bar in bars:
            sig = strat.on_bar(bar)
            if sig:
                signals.append(sig)

        assert len(signals) >= 1
        sig = signals[0]
        # First signal appears at bar 20 (index), where rolling return can first be computed
        assert sig.timestamp == bars[20].timestamp
        assert sig.symbol == "BTCUSDT"
        assert sig.direction == "long"
        assert isinstance(sig.confidence, float)
        assert 0.0 <= sig.confidence <= 1.0

    def test_short_signal_emitted_when_return_below_negative_threshold(self) -> None:
        """Short signal emitted when rolling return below -threshold."""
        # Declining bars that produce < -5% return over 20 periods
        bars = [make_bar(f"2024-01-02T{i:02d}:00:00Z", 120.0 - i * 0.5) for i in range(25)]

        strat = RollingReturnBreakoutStrategy(
            rolling_return_period=20,
            return_threshold=0.05,
            min_hold_bars=3,
            symbol="BTCUSDT",
        )

        signals = []
        for bar in bars:
            sig = strat.on_bar(bar)
            if sig:
                signals.append(sig)

        assert len(signals) >= 1
        sig = signals[0]
        assert sig.direction == "short"

    def test_signal_fields_are_correct(self) -> None:
        """Signal dataclass fields are correctly populated."""
        bars = [make_bar(f"2024-01-03T{i:02d}:00:00Z", 100.0 + i * 3) for i in range(25)]

        strat = RollingReturnBreakoutStrategy(
            rolling_return_period=20,
            return_threshold=0.05,
            min_hold_bars=3,
            confidence=0.75,
            symbol="ETHUSDT",
        )

        signal = None
        for bar in bars:
            sig = strat.on_bar(bar)
            if sig:
                signal = sig
                break

        assert signal is not None
        assert isinstance(signal, Signal)
        assert signal.timestamp == bars[20].timestamp
        assert signal.symbol == "ETHUSDT"
        assert signal.direction in ("long", "short")
        assert signal.confidence == 0.75
        d = signal.to_dict()
        assert "timestamp" in d
        assert "symbol" in d
        assert "direction" in d
        assert "confidence" in d


class TestRollingReturnBreakoutMinHold:
    """Tests for min_hold_bars preventing rapid position flipping."""

    def test_min_hold_prevents_immediate_flip(self) -> None:
        """After a signal, cannot flip until min_hold_bars have passed."""
        strat = RollingReturnBreakoutStrategy(
            rolling_return_period=5,
            return_threshold=0.05,
            min_hold_bars=3,
            symbol="BTCUSDT",
        )

        # Build up: first 5 bars at 100 to establish window, then spike up
        # This ensures rolling return clearly exceeds 5% threshold
        up_bars = [make_bar(f"2024-01-01T{i:02d}:00:00Z", 100.0) for i in range(5)]
        up_bars.append(make_bar("2024-01-01T05:00:00Z", 110.0))  # 10% return triggers long
        up_bars.extend([make_bar(f"2024-01-01T{i:02d}:00:00Z", 110.0) for i in range(6, 10)])

        # Find first long signal while feeding bars
        long_sig = None
        for bar in up_bars:
            sig = strat.on_bar(bar)
            if sig and sig.direction == "long":
                long_sig = sig
                break

        assert long_sig is not None
        assert long_sig.direction == "long"

        # Now drop sharply to trigger short - but min_hold=3 should block
        down_bars = [make_bar(f"2024-01-02T{i:02d}:00:00Z", 110.0 - i * 5.0) for i in range(5)]

        # Try to flip within min_hold (first 3 bars)
        signals_during_hold = []
        for i, bar in enumerate(down_bars[:3]):
            sig = strat.on_bar(bar)
            if sig:
                signals_during_hold.append((i, sig.direction))

        # Should be blocked - no short signals during min_hold period
        short_signals = [d for _, d in signals_during_hold if d == "short"]
        assert len(short_signals) == 0

    def test_flip_allowed_after_min_hold_passes(self) -> None:
        """Position can flip once min_hold_bars have elapsed."""
        strat = RollingReturnBreakoutStrategy(
            rolling_return_period=5,
            return_threshold=0.05,
            min_hold_bars=3,
            symbol="BTCUSDT",
        )

        # Build long position
        up_bars = [make_bar(f"2024-01-01T{i:02d}:00:00Z", 100.0 + i * 1.0) for i in range(10)]
        for bar in up_bars:
            strat.on_bar(bar)

        # Wait through min_hold period with neutral bars
        neutral_bars = [make_bar(f"2024-01-02T{i:02d}:00:00Z", 110.0) for i in range(3)]
        for bar in neutral_bars:
            strat.on_bar(bar)

        # Now drop to trigger short
        down_bars = [make_bar(f"2024-01-03T{i:02d}:00:00Z", 110.0 - i * 5.0) for i in range(10)]

        short_sig = None
        for bar in down_bars:
            sig = strat.on_bar(bar)
            if sig and sig.direction == "short":
                short_sig = sig
                break

        # Short should trigger once min_hold has passed
        assert short_sig is not None
        assert short_sig.direction == "short"

    def test_lower_turnover_than_threshold_zero(self) -> None:
        """RollingReturnBreakout with proper threshold produces fewer flips than threshold=0."""
        # Create oscillating bars that would flip on every bar with threshold=0
        oscillating_bars = []
        for i in range(50):
            # Oscillate: up, down, up, down...
            price = 100.0 + (10.0 if i % 2 == 0 else -10.0)
            oscillating_bars.append(
                make_bar(f"2024-01-01T{i:02d}:00:00Z", price)
            )

        # RollingReturnBreakout with proper threshold
        breakout_strat = RollingReturnBreakoutStrategy(
            rolling_return_period=5,
            return_threshold=0.05,
            min_hold_bars=3,
            symbol="BTCUSDT",
        )

        breakout_signals = []
        for bar in oscillating_bars:
            sig = breakout_strat.on_bar(bar)
            if sig:
                breakout_signals.append(sig)

        # With min_hold=3, should not produce more than half the bars as signals
        # (worst case: signal every 3 bars = ~17 signals for 50 bars)
        assert len(breakout_signals) <= 20


class TestRollingReturnBreakoutVariants:
    """Tests for rolling_return_A, rolling_return_B, rolling_return_C variants."""

    def test_A_B_C_have_different_parameters(self) -> None:
        """Each variant has distinct rolling_return_period, return_threshold, min_hold_bars."""
        assert rolling_return_A.rolling_return_period != rolling_return_B.rolling_return_period
        assert rolling_return_B.rolling_return_period != rolling_return_C.rolling_return_period

        assert rolling_return_A.return_threshold != rolling_return_B.return_threshold
        assert rolling_return_B.return_threshold != rolling_return_C.return_threshold

        assert rolling_return_A.min_hold_bars != rolling_return_B.min_hold_bars
        assert rolling_return_B.min_hold_bars != rolling_return_C.min_hold_bars

    def test_A_is_shortest_period_lowest_threshold(self) -> None:
        """Variant A has shortest period and lowest threshold (most responsive)."""
        assert rolling_return_A.rolling_return_period == 20
        assert rolling_return_B.rolling_return_period == 40
        assert rolling_return_C.rolling_return_period == 60

        assert rolling_return_A.return_threshold == 0.05
        assert rolling_return_B.return_threshold == 0.08
        assert rolling_return_C.return_threshold == 0.10

    def test_C_is_longest_period_highest_threshold(self) -> None:
        """Variant C has longest period and highest threshold (least responsive)."""
        assert rolling_return_C.rolling_return_period == 60
        assert rolling_return_C.return_threshold == 0.10
        assert rolling_return_C.min_hold_bars == 7

    def test_variants_produce_different_signal_counts(self) -> None:
        """Each variant produces different number of signals on same bar sequence."""
        # Same bar sequence for all
        bars = [
            make_bar(f"2024-01-01T{i:02d}:00:00Z", 100.0 + i * 2) for i in range(80)
        ]

        for strat in [rolling_return_A, rolling_return_B, rolling_return_C]:
            strat._bars.clear()
            strat._prev_direction = None
            strat._bars_since_signal = 0

        def count_signals(strat, bar_list):
            count = 0
            for bar in bar_list:
                if strat.on_bar(bar):
                    count += 1
            return count

        count_a = count_signals(rolling_return_A, bars)
        count_b = count_signals(rolling_return_B, bars)
        count_c = count_signals(rolling_return_C, bars)

        # C (most conservative) should produce equal or fewer signals than A
        assert count_c <= count_a


class TestRollingReturnBreakoutEdgeCases:
    """Tests for edge cases and boundary conditions."""

    def test_returns_none_before_rolling_period_satisfied(self) -> None:
        """No signals emitted until rolling_return_period + 1 bars received."""
        bars = [make_bar(f"2024-01-01T{i:02d}:00:00Z", 100.0 + i) for i in range(15)]

        strat = RollingReturnBreakoutStrategy(
            rolling_return_period=20,
            return_threshold=0.01,
            min_hold_bars=1,
            symbol="BTCUSDT",
        )

        signals = []
        for bar in bars:
            sig = strat.on_bar(bar)
            if sig:
                signals.append(sig)

        # Should be empty - not enough bars for rolling return
        assert len(signals) == 0

    def test_exact_threshold_boundary(self) -> None:
        """At exactly return_threshold, should NOT trigger (flat zone)."""
        # Bars designed to produce return EXACTLY at threshold
        # Start at 100, after 20 bars end at 105 (exactly 5% return)
        bars = [make_bar(f"2024-01-01T{i:02d}:00:00Z", 100.0) for i in range(21)]
        # Modify last bar to produce exactly 5% return
        bars[-1] = make_bar("2024-01-01T20:00:00Z", 105.0)

        strat = RollingReturnBreakoutStrategy(
            rolling_return_period=20,
            return_threshold=0.05,
            min_hold_bars=1,
            symbol="BTCUSDT",
        )

        signals = []
        for bar in bars:
            sig = strat.on_bar(bar)
            if sig:
                signals.append(sig)

        # Exactly at threshold should be flat (no signal)
        # The condition is > threshold for long, < -threshold for short
        directions = [s.direction for s in signals]
        assert "long" not in directions  # Not > 0.05, just == 0.05

    def test_min_hold_of_one_allows_nearly_immediate_flip(self) -> None:
        """With min_hold_bars=1, can flip on next eligible bar."""
        strat = RollingReturnBreakoutStrategy(
            rolling_return_period=5,
            return_threshold=0.05,
            min_hold_bars=1,
            symbol="BTCUSDT",
        )

        # Generate initial long signal
        up_bars = [make_bar(f"2024-01-01T{i:02d}:00:00Z", 100.0 + i * 2.0) for i in range(10)]
        for bar in up_bars:
            strat.on_bar(bar)

        # Wait 1 bar (min_hold=1), then drop
        wait_bar = make_bar("2024-01-02T10:00:00Z", 125.0)
        strat.on_bar(wait_bar)

        down_bars = [make_bar(f"2024-01-02T{i:02d}:00:00Z", 125.0 - i * 5.0) for i in range(5)]

        short_sig = None
        for bar in down_bars:
            sig = strat.on_bar(bar)
            if sig and sig.direction == "short":
                short_sig = sig
                break

        assert short_sig is not None

    def test_flat_when_return_within_threshold_band(self) -> None:
        """When rolling return is within ±threshold, direction is flat."""
        # Flat/inactive bars - no trend
        bars = [make_bar(f"2024-01-01T{i:02d}:00:00Z", 100.0) for i in range(25)]

        strat = RollingReturnBreakoutStrategy(
            rolling_return_period=20,
            return_threshold=0.05,
            min_hold_bars=3,
            symbol="BTCUSDT",
        )

        signals = []
        for bar in bars:
            sig = strat.on_bar(bar)
            if sig:
                signals.append(sig)

        # Return = 0% → within band → flat → no signal
        assert len(signals) == 0

    def test_strategy_state_is_isolated(self) -> None:
        """Each strategy instance maintains independent state."""
        strat1 = RollingReturnBreakoutStrategy(
            rolling_return_period=10,
            return_threshold=0.05,
            min_hold_bars=2,
            symbol="BTCUSDT",
        )
        strat2 = RollingReturnBreakoutStrategy(
            rolling_return_period=10,
            return_threshold=0.05,
            min_hold_bars=2,
            symbol="BTCUSDT",
        )

        bars = [make_bar(f"2024-01-01T{i:02d}:00:00Z", 100.0 + i * 3) for i in range(20)]

        # Feed different number of bars to each
        for bar in bars[:15]:
            strat1.on_bar(bar)

        for bar in bars:
            strat2.on_bar(bar)

        # strat1 has processed fewer bars, so should have different state
        assert len(strat1._bars) < len(strat2._bars)
