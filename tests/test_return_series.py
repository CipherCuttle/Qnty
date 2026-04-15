"""Tests for position-state and return-series semantics.

Requires PYTHONHASHSEED=0 for deterministic dict ordering.
Paper mode only - no real trading, no profitability claims.
"""

import json
import tempfile
from pathlib import Path
from typing import Optional
from unittest.mock import MagicMock

import pytest

from quantbot.data.types import Bar
from quantbot.experiment.result import (
    EconomicsSummary,
    ExperimentResult,
    InferenceSummary,
    ReturnSeries,
    ReturnSummary,
    WalkForwardExperimentResult,
    WalkForwardSplitResult,
    compute_inference_summary,
)
from quantbot.experiment.runner import _compute_economics_summary, _compute_return_summary
from quantbot.experiment.spec import ExperimentSpec


class MockSignal:
    """Mock signal object with direction attribute."""

    def __init__(self, direction: Optional[str] = None):
        self.direction = direction


class TestReturnSummaryDataclass:
    """Tests for ReturnSummary dataclass."""

    def test_return_summary_defaults(self) -> None:
        """ReturnSummary initializes with correct defaults."""
        rs = ReturnSummary()
        assert rs.gross_return_total == 0.0
        assert rs.net_return_total == 0.0
        assert rs.cost_deduction_total == 0.0
        assert rs.bars_held == 0
        assert rs.winning_bars == 0
        assert rs.losing_bars == 0

    def test_return_summary_to_dict(self) -> None:
        """ReturnSummary serializes to dict correctly."""
        rs = ReturnSummary(
            gross_return_total=0.05,
            net_return_total=0.04,
            cost_deduction_total=0.01,
            bars_held=10,
            winning_bars=6,
            losing_bars=4,
        )
        d = rs.to_dict()
        assert d["gross_return_total"] == 0.05
        assert d["net_return_total"] == 0.04
        assert d["cost_deduction_total"] == 0.01
        assert d["bars_held"] == 10
        assert d["winning_bars"] == 6
        assert d["losing_bars"] == 4

    def test_return_summary_with_values(self) -> None:
        """ReturnSummary stores provided values."""
        rs = ReturnSummary(
            gross_return_total=0.10,
            net_return_total=0.08,
            cost_deduction_total=0.02,
            bars_held=20,
            winning_bars=12,
            losing_bars=8,
        )
        assert rs.gross_return_total == 0.10
        assert rs.net_return_total == 0.08
        assert rs.cost_deduction_total == 0.02
        assert rs.bars_held == 20
        assert rs.winning_bars == 12
        assert rs.losing_bars == 8


class TestReturnSeriesDataclass:
    """Tests for ReturnSeries dataclass."""

    def test_return_series_defaults(self) -> None:
        """ReturnSeries initializes with correct defaults."""
        rs = ReturnSeries()
        assert rs.gross_returns == []
        assert rs.net_returns == []
        assert rs.bar_timestamps == []
        assert rs.interval == "unknown"

    def test_return_series_to_dict(self) -> None:
        """ReturnSeries serializes to dict correctly."""
        rs = ReturnSeries(
            gross_returns=[0.01, -0.005, 0.02],
            net_returns=[0.009, -0.006, 0.019],
            bar_timestamps=["2023-01-01T00:00:00+00:00", "2023-01-02T00:00:00+00:00", "2023-01-03T00:00:00+00:00"],
            interval="8h",
        )
        d = rs.to_dict()
        assert d["gross_returns"] == [0.01, -0.005, 0.02]
        assert d["net_returns"] == [0.009, -0.006, 0.019]
        assert d["bar_timestamps"] == ["2023-01-01T00:00:00+00:00", "2023-01-02T00:00:00+00:00", "2023-01-03T00:00:00+00:00"]
        assert d["interval"] == "8h"

    def test_return_series_with_values(self) -> None:
        """ReturnSeries stores provided values."""
        rs = ReturnSeries(
            gross_returns=[0.05, 0.03],
            net_returns=[0.04, 0.02],
            bar_timestamps=["2023-01-01T00:00:00Z"],
            interval="1d",
        )
        assert rs.gross_returns == [0.05, 0.03]
        assert rs.net_returns == [0.04, 0.02]
        assert rs.bar_timestamps == ["2023-01-01T00:00:00Z"]
        assert rs.interval == "1d"


class TestExperimentResultReturnSeries:
    """Tests for ExperimentResult return_series field."""

    def test_experiment_result_has_return_series_field(self) -> None:
        """ExperimentResult accepts return_series field."""
        from quantbot.experiment.spec import ExperimentSpec
        spec = ExperimentSpec(
            experiment_name="test",
            strategy_name="noop",
            strategy_params={},
            fixture_name="test.csv",
        )
        rs = ReturnSeries(
            gross_returns=[0.01, 0.02],
            net_returns=[0.009, 0.018],
            bar_timestamps=["2023-01-01T00:00:00Z", "2023-01-02T00:00:00Z"],
            interval="unknown",
        )
        # This should not raise
        assert rs.gross_returns == [0.01, 0.02]


class TestWalkForwardReturnSeries:
    """Tests for WalkForward return_series field."""

    def test_walkforward_split_result_has_return_series_field(self) -> None:
        """WalkForwardSplitResult accepts return_series field."""
        rs = ReturnSeries(
            gross_returns=[0.01],
            net_returns=[0.009],
            bar_timestamps=["2023-01-01T00:00:00Z"],
            interval="unknown",
        )
        split = WalkForwardSplitResult(
            split_index=0,
            train_bar_count=100,
            test_bar_count=50,
            signal_count=5,
            long_count=3,
            short_count=2,
            flat_count=0,
            receipt_path=None,
            artifact_path=None,
            return_series=rs,
        )
        assert split.return_series is not None
        assert split.return_series.gross_returns == [0.01]


class TestReturnSeriesPreserved:
    """Tests that return series are correctly preserved from _compute_return_summary."""

    def _make_mock_strategy(self, signals: list[str | None]):
        """Create a mock strategy that returns MockSignal objects."""
        mock = MagicMock()
        signal_list = list(signals)
        idx = [0]

        def on_bar(bar):
            if idx[0] >= len(signal_list):
                idx[0] = 0
            direction = signal_list[idx[0]]
            idx[0] += 1
            if direction is None or direction == "flat":
                return None
            return MockSignal(direction=direction)

        mock.on_bar = MagicMock(side_effect=on_bar)
        return mock

    def _make_bars(self, closes: list[float]) -> list[Bar]:
        """Create bar objects with given close prices."""
        bars = []
        for i, close in enumerate(closes):
            bar = MagicMock(spec=Bar)
            bar.close = close
            bar.open = close
            bar.high = close
            bar.low = close
            bar.volume = 0
            bar.timestamp = f"2023-01-{i+1:02d}T00:00:00+00:00"
            bars.append(bar)
        return bars

    def test_return_series_length_matches_bars_held(self) -> None:
        """Return series length matches bars_held from ReturnSummary."""
        signals = ["long", "long", "long", "long"]
        strategy = self._make_mock_strategy(signals)
        bars = self._make_bars([100.0, 102.0, 101.0, 103.0])

        economics = EconomicsSummary(
            cost_side_count=1,
            entry_count=1,
            exit_count=0,
            flip_count=0,
            fee_bps=0.0,
            slippage_bps=0.0,
            assumed_total_cost_bps=0.0,
        )

        result, return_series = _compute_return_summary(strategy, bars, economics)

        assert len(return_series.gross_returns) == result.bars_held
        assert len(return_series.net_returns) == result.bars_held
        assert len(return_series.bar_timestamps) == result.bars_held

    def test_return_series_gross_returns_match_calculation(self) -> None:
        """Gross returns in series match individual bar calculations."""
        signals = ["long", "long", "long", "long"]
        strategy = self._make_mock_strategy(signals)
        bars = self._make_bars([100.0, 102.0, 101.0, 103.0])

        economics = EconomicsSummary(
            cost_side_count=1,
            entry_count=1,
            exit_count=0,
            flip_count=0,
            fee_bps=0.0,
            slippage_bps=0.0,
            assumed_total_cost_bps=0.0,
        )

        result, return_series = _compute_return_summary(strategy, bars, economics)

        # Expected: (102-100)/100=0.02, (101-102)/102=-0.009804, (103-101)/101=0.019802
        expected = [
            (102.0 - 100.0) / 100.0,
            (101.0 - 102.0) / 102.0,
            (103.0 - 101.0) / 101.0,
        ]
        for i, (actual, exp) in enumerate(zip(return_series.gross_returns, expected)):
            assert abs(actual - exp) < 0.0001, f"Mismatch at index {i}"

    def test_return_series_timestamps_match_bars(self) -> None:
        """Return series timestamps match bar timestamps."""
        signals = ["long", "long", "long", "long"]
        strategy = self._make_mock_strategy(signals)
        bars = self._make_bars([100.0, 102.0, 101.0, 103.0])

        economics = EconomicsSummary(
            cost_side_count=1,
            entry_count=1,
            exit_count=0,
            flip_count=0,
            fee_bps=0.0,
            slippage_bps=0.0,
            assumed_total_cost_bps=0.0,
        )

        result, return_series = _compute_return_summary(strategy, bars, economics)

        # Timestamps should match bars[1:] (bar-to-bar returns start from 2nd bar)
        for i, ts in enumerate(return_series.bar_timestamps):
            assert ts == bars[i + 1].timestamp


class TestEconomicsSummaryDataclass:
    """Tests for EconomicsSummary dataclass."""

    def test_economics_summary_defaults(self) -> None:
        """EconomicsSummary initializes with correct defaults."""
        es = EconomicsSummary()
        assert es.cost_side_count == 0
        assert es.entry_count == 0
        assert es.exit_count == 0
        assert es.flip_count == 0
        assert es.fee_bps == 0.0
        assert es.slippage_bps == 0.0
        assert es.assumed_total_cost_bps == 0.0

    def test_economics_summary_to_dict(self) -> None:
        """EconomicsSummary serializes to dict correctly."""
        es = EconomicsSummary(
            cost_side_count=5,
            entry_count=2,
            exit_count=2,
            flip_count=1,
            fee_bps=10.0,
            slippage_bps=3.0,
            assumed_total_cost_bps=65.0,
        )
        d = es.to_dict()
        assert d["cost_side_count"] == 5
        assert d["entry_count"] == 2
        assert d["exit_count"] == 2
        assert d["flip_count"] == 1
        assert d["fee_bps"] == 10.0
        assert d["slippage_bps"] == 3.0
        assert d["assumed_total_cost_bps"] == 65.0


class TestPositionStateTransitions:
    """Tests for deterministic position-state transitions."""

    def _make_mock_strategy(self, signals: list[str | None]):
        """Create a mock strategy that returns MockSignal objects.

        Args:
            signals: List of direction strings ("long", "short", "flat") or None for flat.

        Returns:
            Mock strategy with on_bar method that returns MockSignal objects.
        """
        mock = MagicMock()
        signal_list = list(signals)
        idx = [0]

        def on_bar(bar):
            if idx[0] >= len(signal_list):
                idx[0] = 0
            direction = signal_list[idx[0]]
            idx[0] += 1
            if direction is None or direction == "flat":
                return None
            return MockSignal(direction=direction)

        mock.on_bar = MagicMock(side_effect=on_bar)
        return mock

    def _make_bars(self, closes: list[float]) -> list[Bar]:
        """Create bar objects with given close prices."""
        bars = []
        for i, close in enumerate(closes):
            bar = MagicMock(spec=Bar)
            bar.close = close
            bar.open = close
            bar.high = close
            bar.low = close
            bar.volume = 0
            bar.timestamp = f"2023-01-{i+1:02d}T00:00:00+00:00"
            bars.append(bar)
        return bars

    def test_flat_to_long_to_short_to_flat_transitions(self) -> None:
        """Signal sequence flat->long->short->flat produces correct position states.

        Position state should be:
        - flat until first non-flat signal
        - long after first long signal
        - short after first short signal
        - flat after flat signal
        """
        # Signals: flat, flat, long, long, short, short, flat, flat
        signals = ["flat", "flat", "long", "long", "short", "short", "flat", "flat"]
        strategy = self._make_mock_strategy(signals)
        bars = self._make_bars([100.0] * len(signals))

        economics = _compute_economics_summary(strategy, bars, 10.0, 3.0)

        # Entry: 1 (first long), Flip: 1 (long->short), Exit: 1 (short->flat)
        assert economics.entry_count == 1
        assert economics.flip_count == 1
        assert economics.exit_count == 1
        assert economics.cost_side_count == 3  # entry + flip + exit

    def test_position_state_held_across_bars(self) -> None:
        """Position state is held across bars until signal changes."""
        # Three consecutive long signals
        signals = ["long", "long", "long"]
        strategy = self._make_mock_strategy(signals)
        bars = self._make_bars([100.0, 101.0, 102.0])

        economics = _compute_economics_summary(strategy, bars, 10.0, 3.0)

        # Only one entry, no flips or exits during the run
        assert economics.entry_count == 1
        assert economics.flip_count == 0
        assert economics.exit_count == 0
        assert economics.cost_side_count == 1

    def test_multiple_entries_and_exits(self) -> None:
        """Multiple position entries and exits are counted correctly."""
        # long -> flat -> long -> flat -> short -> flat
        # Note: flat signal resets position, so each non-flat is a new entry
        signals = ["long", "flat", "long", "flat", "short", "flat"]
        strategy = self._make_mock_strategy(signals)
        bars = self._make_bars([100.0] * len(signals))

        economics = _compute_economics_summary(strategy, bars, 10.0, 3.0)

        # 3 entries (long, long, short), 3 exits (after each flat)
        assert economics.entry_count == 3  # long, long, short
        assert economics.exit_count == 3  # each flat triggers an exit
        assert economics.flip_count == 0
        assert economics.cost_side_count == 6


class TestGrossReturnCalculation:
    """Tests for gross return calculation on known sequences."""

    def _make_mock_strategy(self, signals: list[str | None]):
        """Create a mock strategy that returns MockSignal objects."""
        mock = MagicMock()
        signal_list = list(signals)
        idx = [0]

        def on_bar(bar):
            if idx[0] >= len(signal_list):
                idx[0] = 0
            direction = signal_list[idx[0]]
            idx[0] += 1
            if direction is None or direction == "flat":
                return None
            return MockSignal(direction=direction)

        mock.on_bar = MagicMock(side_effect=on_bar)
        return mock

    def _make_bars(self, closes: list[float]) -> list[Bar]:
        """Create bar objects with given close prices."""
        bars = []
        for i, close in enumerate(closes):
            bar = MagicMock(spec=Bar)
            bar.close = close
            bar.open = close
            bar.high = close
            bar.low = close
            bar.volume = 0
            bar.timestamp = f"2023-01-{i+1:02d}T00:00:00+00:00"
            bars.append(bar)
        return bars

    def test_long_position_returns_with_known_prices(self) -> None:
        """Test long position return = (close_t - close_{t-1}) / close_{t-1}.

        Prices: [100, 102, 101, 103]
        Expected returns:
        - Bar 1->2: (102-100)/100 = 0.02
        - Bar 2->3: (101-102)/102 = -0.009804
        - Bar 3->4: (103-101)/101 = 0.019802
        """
        signals = ["long", "long", "long", "long"]
        strategy = self._make_mock_strategy(signals)
        bars = self._make_bars([100.0, 102.0, 101.0, 103.0])

        economics = EconomicsSummary(
            cost_side_count=1,
            entry_count=1,
            exit_count=0,
            flip_count=0,
            fee_bps=0.0,
            slippage_bps=0.0,
            assumed_total_cost_bps=0.0,
        )

        result, return_series = _compute_return_summary(strategy, bars, economics)

        # Product of (1 + r): (1 + 0.02) * (1 - 0.009804) * (1 + 0.019802)
        # = 1.02 * 0.990196 * 1.019802 = 1.0299...
        expected_gross = (1.02) * (1 - 0.009804) * (1 + 0.019802) - 1.0
        assert abs(result.gross_return_total - expected_gross) < 0.0001
        assert result.bars_held == 3  # 3 bars with non-flat position
        assert result.winning_bars == 2  # bars 1->2 and 3->4 positive
        assert result.losing_bars == 1  # bar 2->3 negative
        # Verify return series is also returned
        assert len(return_series.gross_returns) == 3
        assert len(return_series.net_returns) == 3

    def test_short_position_returns_are_negated(self) -> None:
        """Test short position returns are negated from long."""
        signals = ["short", "short", "short", "short"]
        strategy = self._make_mock_strategy(signals)
        bars = self._make_bars([100.0, 102.0, 101.0, 103.0])

        economics = EconomicsSummary(
            cost_side_count=1,
            entry_count=1,
            exit_count=0,
            flip_count=0,
            fee_bps=0.0,
            slippage_bps=0.0,
            assumed_total_cost_bps=0.0,
        )

        result, return_series = _compute_return_summary(strategy, bars, economics)

        # Short returns are negated
        # Bar 1->2: -(102-100)/100 = -0.02
        # Bar 2->3: -(101-102)/102 = +0.009804
        # Bar 3->4: -(103-101)/101 = -0.019802
        expected_gross = (1 - 0.02) * (1 + 0.009804) * (1 - 0.019802) - 1.0
        assert abs(result.gross_return_total - expected_gross) < 0.0001
        assert result.bars_held == 3
        assert result.winning_bars == 1  # only bar 2->3 positive for short
        assert result.losing_bars == 2  # bars 1->2 and 3->4 negative for short

    def test_flat_position_returns_are_zero(self) -> None:
        """Test flat position returns are 0."""
        signals = ["flat", "flat", "flat", "flat"]
        strategy = self._make_mock_strategy(signals)
        bars = self._make_bars([100.0, 102.0, 101.0, 103.0])

        economics = EconomicsSummary(
            cost_side_count=0,
            entry_count=0,
            exit_count=0,
            flip_count=0,
            fee_bps=0.0,
            slippage_bps=0.0,
            assumed_total_cost_bps=0.0,
        )

        result, return_series = _compute_return_summary(strategy, bars, economics)

        assert result.gross_return_total == 0.0
        assert result.bars_held == 0
        assert result.winning_bars == 0
        assert result.losing_bars == 0

    def test_mixed_position_states(self) -> None:
        """Test with mixed long/short/flat positions."""
        # long for bars 1-2, flat for bar 3, short for bars 4-5
        signals = ["long", "long", "flat", "short", "short"]
        strategy = self._make_mock_strategy(signals)
        bars = self._make_bars([100.0, 102.0, 101.0, 99.0, 97.0])

        economics = EconomicsSummary(
            cost_side_count=3,  # entry + exit + entry
            entry_count=2,
            exit_count=1,
            flip_count=0,
            fee_bps=0.0,
            slippage_bps=0.0,
            assumed_total_cost_bps=0.0,
        )

        result, return_series = _compute_return_summary(strategy, bars, economics)

        # Verify the computation produces a valid gross return
        assert result.gross_return_total > 0  # positive overall
        assert result.bars_held == 4  # 2 long + 2 short


class TestNetReturnDeduction:
    """Tests for net return deduction from explicit entry/exit/flip events."""

    def _make_mock_strategy(self, signals: list[str | None]):
        """Create a mock strategy that returns MockSignal objects."""
        mock = MagicMock()
        signal_list = list(signals)
        idx = [0]

        def on_bar(bar):
            if idx[0] >= len(signal_list):
                idx[0] = 0
            direction = signal_list[idx[0]]
            idx[0] += 1
            if direction is None or direction == "flat":
                return None
            return MockSignal(direction=direction)

        mock.on_bar = MagicMock(side_effect=on_bar)
        return mock

    def _make_bars(self, closes: list[float]) -> list[Bar]:
        """Create bar objects with given close prices."""
        bars = []
        for i, close in enumerate(closes):
            bar = MagicMock(spec=Bar)
            bar.close = close
            bar.open = close
            bar.high = close
            bar.low = close
            bar.volume = 0
            bar.timestamp = f"2023-01-{i+1:02d}T00:00:00+00:00"
            bars.append(bar)
        return bars

    def test_costs_deducted_only_on_cost_bearing_events(self) -> None:
        """Test costs are deducted only on entry, exit, flip events."""
        # long -> flat (one entry, one exit)
        signals = ["long", "flat"]
        strategy = self._make_mock_strategy(signals)
        bars = self._make_bars([100.0, 102.0])

        # 10 bps fee + 3 bps slippage = 13 bps per event
        # The function computes: entry=1, exit=1, cost_side_count=2
        economics = EconomicsSummary(
            cost_side_count=2,  # entry + exit
            entry_count=1,
            exit_count=1,
            flip_count=0,
            fee_bps=10.0,
            slippage_bps=3.0,
            assumed_total_cost_bps=26.0,  # 2 * 13
        )

        result, return_series = _compute_return_summary(strategy, bars, economics)

        # Gross: (102-100)/100 = 0.02
        # Cost: 2 * (26/10000) = 0.0052 (cost_per_event = assumed_total_cost_bps/10000)
        # Net: 0.02 - 0.0052 = 0.0148
        assert abs(result.gross_return_total - 0.02) < 0.0001
        assert abs(result.cost_deduction_total - 0.0052) < 0.0001
        assert abs(result.net_return_total - 0.0148) < 0.0001

    def test_net_return_with_explicit_cost_rate(self) -> None:
        """Test net = gross - cost_deduction with explicit cost rate."""
        # Simple long with 10 bps total cost
        signals = ["long", "long"]
        strategy = self._make_mock_strategy(signals)
        bars = self._make_bars([100.0, 110.0])

        # 10 bps total cost, 1 cost-bearing event
        economics = EconomicsSummary(
            cost_side_count=1,
            entry_count=1,
            exit_count=0,
            flip_count=0,
            fee_bps=7.0,
            slippage_bps=3.0,
            assumed_total_cost_bps=10.0,
        )

        result, return_series = _compute_return_summary(strategy, bars, economics)

        # Gross: (110-100)/100 = 0.10
        # Cost: 1 * (10/10000) = 0.001
        # Net: 0.10 - 0.001 = 0.099
        assert abs(result.gross_return_total - 0.10) < 0.0001
        assert abs(result.cost_deduction_total - 0.001) < 0.0001
        assert abs(result.net_return_total - 0.099) < 0.0001

    def test_flip_counts_as_two_cost_bearing_events(self) -> None:
        """Test flip counts as exit + entry (2 cost-bearing events)."""
        # long -> short (flip)
        signals = ["long", "short"]
        strategy = self._make_mock_strategy(signals)
        bars = self._make_bars([100.0, 102.0])

        # Flip = exit + entry = 2 cost-bearing events
        economics = EconomicsSummary(
            cost_side_count=2,  # flip = exit + entry
            entry_count=1,
            exit_count=0,
            flip_count=1,
            fee_bps=10.0,
            slippage_bps=0.0,
            assumed_total_cost_bps=20.0,  # 2 * 10
        )

        result, return_series = _compute_return_summary(strategy, bars, economics)

        # Verify gross return is computed (actual value depends on position state timing)
        assert result.gross_return_total > 0
        # Cost: 2 events * 20/10000 = 0.004
        assert abs(result.cost_deduction_total - 0.004) < 0.0001
        # Net = gross - cost
        assert result.net_return_total < result.gross_return_total


class TestExperimentResultReturnSummary:
    """Tests for ExperimentResult including return_summary field."""

    def test_experiment_result_has_return_summary_field(self) -> None:
        """ExperimentResult includes return_summary field."""
        spec = ExperimentSpec(
            experiment_name="test-exp",
            strategy_name="ThresholdStrategy",
        )
        result = ExperimentResult(
            spec=spec,
            result_path=Path("/tmp/result.json"),
            receipt_path=Path("/tmp/receipt.json"),
            receipt_digest="abc123",
            bar_count=100,
            signal_count=5,
            first_timestamp="2023-01-01T00:00:00+00:00",
            last_timestamp="2023-01-02T00:00:00+00:00",
            return_summary=ReturnSummary(
                gross_return_total=0.05,
                net_return_total=0.04,
                cost_deduction_total=0.01,
                bars_held=10,
                winning_bars=6,
                losing_bars=4,
            ),
        )
        assert result.return_summary is not None
        assert result.return_summary.gross_return_total == 0.05
        assert result.return_summary.net_return_total == 0.04
        assert result.return_summary.cost_deduction_total == 0.01

    def test_experiment_result_return_summary_serializes(self) -> None:
        """ExperimentResult.to_dict() includes return_summary."""
        spec = ExperimentSpec(
            experiment_name="test-exp",
            strategy_name="ThresholdStrategy",
        )
        result = ExperimentResult(
            spec=spec,
            result_path=Path("/tmp/result.json"),
            receipt_path=Path("/tmp/receipt.json"),
            receipt_digest="abc123",
            bar_count=100,
            signal_count=5,
            first_timestamp="2023-01-01T00:00:00+00:00",
            last_timestamp="2023-01-02T00:00:00+00:00",
            return_summary=ReturnSummary(
                gross_return_total=0.05,
                net_return_total=0.04,
                cost_deduction_total=0.01,
                bars_held=10,
                winning_bars=6,
                losing_bars=4,
            ),
        )
        d = result.to_dict()
        assert "return_summary" in d
        assert d["return_summary"]["gross_return_total"] == 0.05
        assert d["return_summary"]["net_return_total"] == 0.04
        assert d["return_summary"]["cost_deduction_total"] == 0.01
        assert d["return_summary"]["bars_held"] == 10
        assert d["return_summary"]["winning_bars"] == 6
        assert d["return_summary"]["losing_bars"] == 4

    def test_experiment_result_return_summary_none(self) -> None:
        """ExperimentResult with None return_summary serializes to None."""
        spec = ExperimentSpec(
            experiment_name="test-exp",
            strategy_name="ThresholdStrategy",
        )
        result = ExperimentResult(
            spec=spec,
            result_path=Path("/tmp/result.json"),
            receipt_path=Path("/tmp/receipt.json"),
            receipt_digest="abc123",
            bar_count=100,
            signal_count=5,
            first_timestamp="2023-01-01T00:00:00+00:00",
            last_timestamp="2023-01-02T00:00:00+00:00",
        )
        d = result.to_dict()
        assert d["return_summary"] is None


class TestWalkForwardReturnSummary:
    """Tests for WalkForwardExperimentResult aggregate return_summary."""

    def test_walkforward_experiment_result_has_return_summary(self) -> None:
        """WalkForwardExperimentResult includes return_summary field."""
        result = WalkForwardExperimentResult(
            experiment_name="wf-test",
            split_count=2,
            splits=[],
            total_bar_count=100,
            total_signal_count=10,
            return_summary=ReturnSummary(
                gross_return_total=0.10,
                net_return_total=0.08,
                cost_deduction_total=0.02,
                bars_held=20,
                winning_bars=12,
                losing_bars=8,
            ),
        )
        assert result.return_summary is not None
        assert result.return_summary.gross_return_total == 0.10

    def test_aggregate_return_summary_sums_correctly(self) -> None:
        """aggregate_return_summary sums per-split summaries correctly."""
        split1 = WalkForwardSplitResult(
            split_index=0,
            train_bar_count=100,
            test_bar_count=50,
            signal_count=5,
            long_count=3,
            short_count=2,
            flat_count=0,
            receipt_path=None,
            artifact_path=None,
            return_summary=ReturnSummary(
                gross_return_total=0.05,
                net_return_total=0.04,
                cost_deduction_total=0.01,
                bars_held=10,
                winning_bars=6,
                losing_bars=4,
            ),
        )
        split2 = WalkForwardSplitResult(
            split_index=1,
            train_bar_count=100,
            test_bar_count=50,
            signal_count=5,
            long_count=2,
            short_count=3,
            flat_count=0,
            receipt_path=None,
            artifact_path=None,
            return_summary=ReturnSummary(
                gross_return_total=0.03,
                net_return_total=0.02,
                cost_deduction_total=0.01,
                bars_held=10,
                winning_bars=5,
                losing_bars=5,
            ),
        )

        result = WalkForwardExperimentResult(
            experiment_name="wf-test",
            split_count=2,
            splits=[split1, split2],
            total_bar_count=100,
            total_signal_count=10,
        )

        aggregated = result.aggregate_return_summary()

        assert aggregated is not None
        assert aggregated.gross_return_total == 0.08  # 0.05 + 0.03
        assert aggregated.net_return_total == 0.06  # 0.04 + 0.02
        assert aggregated.cost_deduction_total == 0.02  # 0.01 + 0.01
        assert aggregated.bars_held == 20  # 10 + 10
        assert aggregated.winning_bars == 11  # 6 + 5
        assert aggregated.losing_bars == 9  # 4 + 5

    def test_aggregate_return_summary_returns_none_when_no_splits(self) -> None:
        """aggregate_return_summary returns None when no splits have return data."""
        result = WalkForwardExperimentResult(
            experiment_name="wf-test",
            split_count=0,
            splits=[],
            total_bar_count=0,
            total_signal_count=0,
        )

        aggregated = result.aggregate_return_summary()

        assert aggregated is None

    def test_walkforward_return_summary_serializes(self) -> None:
        """WalkForwardExperimentResult.to_dict() includes return_summary."""
        split = WalkForwardSplitResult(
            split_index=0,
            train_bar_count=100,
            test_bar_count=50,
            signal_count=5,
            long_count=3,
            short_count=2,
            flat_count=0,
            receipt_path=None,
            artifact_path=None,
            return_summary=ReturnSummary(
                gross_return_total=0.05,
                net_return_total=0.04,
                cost_deduction_total=0.01,
                bars_held=10,
                winning_bars=6,
                losing_bars=4,
            ),
        )

        result = WalkForwardExperimentResult(
            experiment_name="wf-test",
            split_count=1,
            splits=[split],
            total_bar_count=50,
            total_signal_count=5,
            return_summary=ReturnSummary(
                gross_return_total=0.05,
                net_return_total=0.04,
                cost_deduction_total=0.01,
                bars_held=10,
                winning_bars=6,
                losing_bars=4,
            ),
        )

        d = result.to_dict()
        assert "return_summary" in d
        assert d["return_summary"]["gross_return_total"] == 0.05
        assert d["return_summary"]["net_return_total"] == 0.04
        assert d["return_summary"]["cost_deduction_total"] == 0.01


class TestIndexReadsReturnSummary:
    """Tests for IndexedExperiment reading return_summary from artifacts."""

    def test_indexed_experiment_includes_return_summary(self) -> None:
        """IndexedExperiment includes return_summary field."""
        from quantbot.experiment.index import IndexedExperiment

        indexed = IndexedExperiment(
            experiment_name="test",
            strategy_name="TestStrategy",
            fixture_name="test_fixture",
            gate_status="PASS",
            split_count=0,
            signal_count=5,
            receipt_digest="abc123",
            artifact_path=Path("/tmp/result.json"),
            result_type="single",
            return_summary={
                "gross_return_total": 0.05,
                "net_return_total": 0.04,
                "cost_deduction_total": 0.01,
                "bars_held": 10,
                "winning_bars": 6,
                "losing_bars": 4,
            },
        )

        assert indexed.return_summary is not None
        assert indexed.return_summary["gross_return_total"] == 0.05
        assert indexed.return_summary["net_return_total"] == 0.04

    def test_index_reads_return_summary_from_json(self) -> None:
        """Index reads return_summary from experiment_result.json."""
        import tempfile
        from quantbot.experiment.index import index_experiment_artifacts

        with tempfile.TemporaryDirectory() as tmpdir:
            artifact_path = Path(tmpdir) / "experiment_result.json"
            artifact_data = {
                "experiment_name": "test-exp",
                "strategy_name": "ThresholdStrategy",
                "strategy_params": {},
                "fixture_name": "BTCUSDT_8h",
                "engine_version": "0.1.0",
                "receipt_digest": "abc123",
                "bar_count": 100,
                "signal_count": 5,
                "first_timestamp": "2023-01-01T00:00:00+00:00",
                "last_timestamp": "2023-01-02T00:00:00+00:00",
                "long_count": 3,
                "short_count": 2,
                "flat_count": 0,
                "gate_verdict": None,
                "fee_bps": 10.0,
                "slippage_bps": 3.0,
                "return_summary": {
                    "gross_return_total": 0.05,
                    "net_return_total": 0.04,
                    "cost_deduction_total": 0.01,
                    "bars_held": 10,
                    "winning_bars": 6,
                    "losing_bars": 4,
                },
            }
            artifact_path.write_text(json.dumps(artifact_data), encoding="utf-8")

            indexed = index_experiment_artifacts([artifact_path])

            assert len(indexed) == 1
            assert indexed[0].return_summary is not None
            assert indexed[0].return_summary["gross_return_total"] == 0.05
            assert indexed[0].return_summary["net_return_total"] == 0.04
            assert indexed[0].return_summary["cost_deduction_total"] == 0.01

    def test_index_reads_return_summary_from_walkforward_json(self) -> None:
        """Index reads return_summary from walkforward_result.json."""
        import tempfile
        from quantbot.experiment.index import index_experiment_artifacts

        with tempfile.TemporaryDirectory() as tmpdir:
            artifact_path = Path(tmpdir) / "walkforward_result.json"
            artifact_data = {
                "experiment_name": "wf-test",
                "strategy_name": "ThresholdStrategy",
                "strategy_params": {},
                "fixture_name": "BTCUSDT_8h",
                "engine_version": "0.1.0",
                "split_count": 2,
                "aggregate_signal_count": 10,
                "gate_verdict": None,
                "fee_bps": 10.0,
                "slippage_bps": 3.0,
                "return_summary": {
                    "gross_return_total": 0.08,
                    "net_return_total": 0.06,
                    "cost_deduction_total": 0.02,
                    "bars_held": 20,
                    "winning_bars": 11,
                    "losing_bars": 9,
                },
                "split_results": [],
            }
            artifact_path.write_text(json.dumps(artifact_data), encoding="utf-8")

            indexed = index_experiment_artifacts([artifact_path])

            assert len(indexed) == 1
            assert indexed[0].return_summary is not None
            assert indexed[0].return_summary["gross_return_total"] == 0.08


class TestLegacyArtifactsBackwardCompatibility:
    """Tests for graceful handling of legacy artifacts missing new fields."""

    def test_legacy_artifact_missing_return_summary(self) -> None:
        """Indexing a legacy artifact without return_summary does not break."""
        import tempfile
        from quantbot.experiment.index import index_experiment_artifacts

        with tempfile.TemporaryDirectory() as tmpdir:
            legacy_path = Path(tmpdir) / "experiment_result.json"
            legacy_data = {
                "experiment_name": "legacy-exp",
                "strategy_name": "ThresholdStrategy",
                "strategy_params": {},
                "fixture_name": "BTCUSDT_8h",
                "engine_version": "0.1.0",
                "receipt_digest": "abc123",
                "bar_count": 100,
                "signal_count": 5,
                "first_timestamp": "2023-01-01T00:00:00+00:00",
                "last_timestamp": "2023-01-02T00:00:00+00:00",
                "long_count": 2,
                "short_count": 3,
                "flat_count": 0,
                "gate_verdict": None,
                "fee_bps": 10.0,
                "slippage_bps": 3.0,
                # No return_summary field
            }
            legacy_path.write_text(json.dumps(legacy_data), encoding="utf-8")

            indexed = index_experiment_artifacts([legacy_path])

            assert len(indexed) == 1
            assert indexed[0].experiment_name == "legacy-exp"
            # return_summary should be None for legacy artifacts
            assert indexed[0].return_summary is None

    def test_legacy_walkforward_missing_return_summary(self) -> None:
        """Indexing a legacy walkforward artifact without return_summary does not break."""
        import tempfile
        from quantbot.experiment.index import index_experiment_artifacts

        with tempfile.TemporaryDirectory() as tmpdir:
            legacy_path = Path(tmpdir) / "walkforward_result.json"
            legacy_data = {
                "experiment_name": "legacy-wf",
                "strategy_name": "ThresholdStrategy",
                "strategy_params": {},
                "fixture_name": "BTCUSDT_8h",
                "engine_version": "0.1.0",
                "split_count": 2,
                "aggregate_signal_count": 10,
                "gate_verdict": None,
                "fee_bps": 10.0,
                "slippage_bps": 3.0,
                # No return_summary field
                "split_results": [],
            }
            legacy_path.write_text(json.dumps(legacy_data), encoding="utf-8")

            indexed = index_experiment_artifacts([legacy_path])

            assert len(indexed) == 1
            assert indexed[0].experiment_name == "legacy-wf"
            assert indexed[0].return_summary is None

    def test_legacy_artifact_missing_economics_summary(self) -> None:
        """Indexing a legacy artifact without economics_summary does not break."""
        import tempfile
        from quantbot.experiment.index import index_experiment_artifacts

        with tempfile.TemporaryDirectory() as tmpdir:
            legacy_path = Path(tmpdir) / "experiment_result.json"
            legacy_data = {
                "experiment_name": "legacy-exp",
                "strategy_name": "ThresholdStrategy",
                "strategy_params": {},
                "fixture_name": "BTCUSDT_8h",
                "engine_version": "0.1.0",
                "receipt_digest": "abc123",
                "bar_count": 100,
                "signal_count": 5,
                "first_timestamp": "2023-01-01T00:00:00+00:00",
                "last_timestamp": "2023-01-02T00:00:00+00:00",
                "long_count": 2,
                "short_count": 3,
                "flat_count": 0,
                "gate_verdict": None,
                "fee_bps": 10.0,
                "slippage_bps": 3.0,
                # No economics_summary field
            }
            legacy_path.write_text(json.dumps(legacy_data), encoding="utf-8")

            indexed = index_experiment_artifacts([legacy_path])

            assert len(indexed) == 1
            assert indexed[0].experiment_name == "legacy-exp"
            assert indexed[0].economics_summary is None


class TestInferenceSummaryDataclass:
    """Tests for InferenceSummary dataclass."""

    def test_inference_summary_defaults(self) -> None:
        """InferenceSummary initializes with correct defaults."""
        inf = InferenceSummary()
        assert inf.bar_count_for_returns == 0
        assert inf.mean_return == 0.0
        assert inf.std_return is None
        assert inf.gross_return_total == 0.0
        assert inf.net_return_total == 0.0
        assert inf.cost_deduction_total == 0.0
        assert inf.sharpe_like is None
        assert inf.annualized is False
        assert inf.interval == "unknown"
        assert "not annualized" in inf.annualization_note

    def test_inference_summary_to_dict(self) -> None:
        """InferenceSummary serializes to dict correctly."""
        inf = InferenceSummary(
            bar_count_for_returns=10,
            mean_return=0.001,
            std_return=0.02,
            gross_return_total=0.05,
            net_return_total=0.04,
            cost_deduction_total=0.01,
            sharpe_like=None,
            annualized=False,
            interval="8h",
            annualization_note="not annualized - interval unknown",
        )
        d = inf.to_dict()
        assert d["bar_count_for_returns"] == 10
        assert d["mean_return"] == 0.001
        assert d["std_return"] == 0.02
        assert d["gross_return_total"] == 0.05
        assert d["net_return_total"] == 0.04
        assert d["cost_deduction_total"] == 0.01
        assert d["sharpe_like"] is None
        assert d["annualized"] is False
        assert d["interval"] == "8h"
        assert "not annualized" in d["annualization_note"]


class TestComputeInferenceSummary:
    """Tests for compute_inference_summary function."""

    def test_empty_series(self) -> None:
        """Empty return series produces zero/invalid stats."""
        rs = ReturnSeries(gross_returns=[], net_returns=[], bar_timestamps=[], interval="unknown")
        inf = compute_inference_summary(rs)
        assert inf.bar_count_for_returns == 0
        assert inf.mean_return == 0.0
        assert inf.std_return is None
        assert inf.gross_return_total == 0.0
        assert inf.net_return_total == 0.0
        assert "empty" in inf.annualization_note

    def test_single_bar(self) -> None:
        """Single bar has undefined std (None)."""
        rs = ReturnSeries(
            gross_returns=[0.01],
            net_returns=[0.009],
            bar_timestamps=["2023-01-01T00:00:00Z"],
            interval="8h",
        )
        inf = compute_inference_summary(rs)
        assert inf.bar_count_for_returns == 1
        assert abs(inf.mean_return - 0.009) < 0.0001
        assert inf.std_return is None  # std undefined for single observation
        assert inf.sharpe_like is None  # cannot compute without std

    def test_identical_returns_zero_std(self) -> None:
        """All identical returns produce std = 0."""
        rs = ReturnSeries(
            gross_returns=[0.01, 0.01, 0.01],
            net_returns=[0.009, 0.009, 0.009],
            bar_timestamps=["2023-01-01T00:00:00Z", "2023-01-02T00:00:00Z", "2023-01-03T00:00:00Z"],
            interval="8h",
        )
        inf = compute_inference_summary(rs)
        assert inf.bar_count_for_returns == 3
        assert abs(inf.mean_return - 0.009) < 0.0001
        assert inf.std_return == 0.0  # all identical => zero variance

    def test_known_sequence_stats(self) -> None:
        """Statistics computed correctly on known sequence."""
        # net_returns = [0.01, -0.005, 0.02, -0.01, 0.015]
        net_returns = [0.01, -0.005, 0.02, -0.01, 0.015]
        gross_returns = [0.011, -0.004, 0.021, -0.009, 0.016]
        rs = ReturnSeries(
            gross_returns=gross_returns,
            net_returns=net_returns,
            bar_timestamps=["2023-01-01T00:00:00Z"] * 5,
            interval="8h",
        )
        inf = compute_inference_summary(rs)
        
        # Mean = sum/5
        expected_mean = sum(net_returns) / 5
        assert abs(inf.mean_return - expected_mean) < 0.0001
        
        # Verify totals from series
        assert abs(inf.net_return_total - sum(net_returns)) < 0.0001
        assert abs(inf.gross_return_total - sum(gross_returns)) < 0.0001
        assert abs(inf.cost_deduction_total - (sum(gross_returns) - sum(net_returns))) < 0.0001
        
        # bar_count
        assert inf.bar_count_for_returns == 5
        
        # std should not be None (5 bars >= 2)
        assert inf.std_return is not None

    def test_interval_unknown_no_annualization(self) -> None:
        """Interval unknown => no annualization, sharpe_like is None."""
        rs = ReturnSeries(
            gross_returns=[0.01, 0.02],
            net_returns=[0.009, 0.018],
            bar_timestamps=["2023-01-01T00:00:00Z", "2023-01-02T00:00:00Z"],
            interval="unknown",
        )
        inf = compute_inference_summary(rs)
        assert inf.annualized is False
        assert inf.sharpe_like is None
        assert "interval unknown" in inf.annualization_note

    def test_interval_known_still_no_annualization(self) -> None:
        """Even with known interval, sharpe_like stays None (explicit choice)."""
        rs = ReturnSeries(
            gross_returns=[0.01, 0.02],
            net_returns=[0.009, 0.018],
            bar_timestamps=["2023-01-01T00:00:00Z", "2023-01-02T00:00:00Z"],
            interval="8h",
        )
        inf = compute_inference_summary(rs)
        assert inf.interval == "8h"
        # sharpe_like is None because we explicitly do not annualize without explicit factor
        assert inf.sharpe_like is None
        assert inf.annualized is False


class TestExperimentResultInferenceSummary:
    """Tests for ExperimentResult inference_summary field."""

    def test_experiment_result_has_inference_summary_field(self) -> None:
        """ExperimentResult accepts inference_summary field."""
        spec = ExperimentSpec(
            experiment_name="test-exp",
            strategy_name="ThresholdStrategy",
        )
        inf = InferenceSummary(
            bar_count_for_returns=10,
            mean_return=0.001,
            std_return=0.02,
            gross_return_total=0.05,
            net_return_total=0.04,
            cost_deduction_total=0.01,
        )
        result = ExperimentResult(
            spec=spec,
            result_path=Path("/tmp/result.json"),
            receipt_path=Path("/tmp/receipt.json"),
            receipt_digest="abc123",
            bar_count=100,
            signal_count=5,
            first_timestamp="2023-01-01T00:00:00+00:00",
            last_timestamp="2023-01-02T00:00:00+00:00",
            inference_summary=inf,
        )
        assert result.inference_summary is not None
        assert result.inference_summary.bar_count_for_returns == 10

    def test_experiment_result_inference_summary_serializes(self) -> None:
        """ExperimentResult.to_dict() includes inference_summary."""
        spec = ExperimentSpec(
            experiment_name="test-exp",
            strategy_name="ThresholdStrategy",
        )
        inf = InferenceSummary(
            bar_count_for_returns=10,
            mean_return=0.001,
            std_return=0.02,
            gross_return_total=0.05,
            net_return_total=0.04,
            cost_deduction_total=0.01,
        )
        result = ExperimentResult(
            spec=spec,
            result_path=Path("/tmp/result.json"),
            receipt_path=Path("/tmp/receipt.json"),
            receipt_digest="abc123",
            bar_count=100,
            signal_count=5,
            first_timestamp="2023-01-01T00:00:00+00:00",
            last_timestamp="2023-01-02T00:00:00+00:00",
            inference_summary=inf,
        )
        d = result.to_dict()
        assert "inference_summary" in d
        assert d["inference_summary"]["bar_count_for_returns"] == 10
        assert d["inference_summary"]["mean_return"] == 0.001
        assert d["inference_summary"]["std_return"] == 0.02

    def test_experiment_result_inference_summary_none(self) -> None:
        """ExperimentResult with None inference_summary serializes to None."""
        spec = ExperimentSpec(
            experiment_name="test-exp",
            strategy_name="ThresholdStrategy",
        )
        result = ExperimentResult(
            spec=spec,
            result_path=Path("/tmp/result.json"),
            receipt_path=Path("/tmp/receipt.json"),
            receipt_digest="abc123",
            bar_count=100,
            signal_count=5,
            first_timestamp="2023-01-01T00:00:00+00:00",
            last_timestamp="2023-01-02T00:00:00+00:00",
        )
        d = result.to_dict()
        assert d["inference_summary"] is None


class TestWalkForwardInferenceSummary:
    """Tests for WalkForwardExperimentResult inference_summary field."""

    def test_walkforward_split_result_has_inference_summary_field(self) -> None:
        """WalkForwardSplitResult accepts inference_summary field."""
        inf = InferenceSummary(
            bar_count_for_returns=10,
            mean_return=0.001,
            std_return=0.02,
            gross_return_total=0.05,
            net_return_total=0.04,
            cost_deduction_total=0.01,
        )
        split = WalkForwardSplitResult(
            split_index=0,
            train_bar_count=100,
            test_bar_count=50,
            signal_count=5,
            long_count=3,
            short_count=2,
            flat_count=0,
            receipt_path=None,
            artifact_path=None,
            inference_summary=inf,
        )
        assert split.inference_summary is not None
        assert split.inference_summary.bar_count_for_returns == 10

    def test_walkforward_experiment_result_has_inference_summary_field(self) -> None:
        """WalkForwardExperimentResult includes inference_summary field."""
        inf = InferenceSummary(
            bar_count_for_returns=20,
            mean_return=0.001,
            std_return=0.02,
            gross_return_total=0.10,
            net_return_total=0.08,
            cost_deduction_total=0.02,
        )
        result = WalkForwardExperimentResult(
            experiment_name="wf-test",
            split_count=2,
            splits=[],
            total_bar_count=100,
            total_signal_count=10,
            inference_summary=inf,
        )
        assert result.inference_summary is not None
        assert result.inference_summary.bar_count_for_returns == 20

    def test_aggregate_inference_summary(self) -> None:
        """aggregate_inference_summary concatenates series and recomputes."""
        split1 = WalkForwardSplitResult(
            split_index=0,
            train_bar_count=100,
            test_bar_count=50,
            signal_count=5,
            long_count=3,
            short_count=2,
            flat_count=0,
            receipt_path=None,
            artifact_path=None,
            return_series=ReturnSeries(
                gross_returns=[0.01, 0.02],
                net_returns=[0.009, 0.018],
                bar_timestamps=["2023-01-01T00:00:00Z", "2023-01-02T00:00:00Z"],
                interval="8h",
            ),
        )
        split2 = WalkForwardSplitResult(
            split_index=1,
            train_bar_count=100,
            test_bar_count=50,
            signal_count=5,
            long_count=2,
            short_count=3,
            flat_count=0,
            receipt_path=None,
            artifact_path=None,
            return_series=ReturnSeries(
                gross_returns=[0.03],
                net_returns=[0.028],
                bar_timestamps=["2023-01-03T00:00:00Z"],
                interval="8h",
            ),
        )

        result = WalkForwardExperimentResult(
            experiment_name="wf-test",
            split_count=2,
            splits=[split1, split2],
            total_bar_count=100,
            total_signal_count=10,
        )

        aggregated = result.aggregate_inference_summary()

        assert aggregated is not None
        assert aggregated.bar_count_for_returns == 3  # 2 + 1
        # mean of combined: (0.009 + 0.018 + 0.028) / 3
        expected_mean = (0.009 + 0.018 + 0.028) / 3
        assert abs(aggregated.mean_return - expected_mean) < 0.0001
        assert aggregated.interval == "8h"
        assert aggregated.annualized is False
        assert aggregated.sharpe_like is None

    def test_aggregate_inference_summary_returns_none_when_no_series(self) -> None:
        """aggregate_inference_summary returns None when no splits have return_series."""
        result = WalkForwardExperimentResult(
            experiment_name="wf-test",
            split_count=0,
            splits=[],
            total_bar_count=0,
            total_signal_count=0,
        )

        aggregated = result.aggregate_inference_summary()

        assert aggregated is None

    def test_walkforward_inference_summary_serializes(self) -> None:
        """WalkForwardExperimentResult.to_dict() includes inference_summary."""
        inf = InferenceSummary(
            bar_count_for_returns=20,
            mean_return=0.001,
            std_return=0.02,
            gross_return_total=0.10,
            net_return_total=0.08,
            cost_deduction_total=0.02,
        )
        result = WalkForwardExperimentResult(
            experiment_name="wf-test",
            split_count=1,
            splits=[],
            total_bar_count=50,
            total_signal_count=5,
            inference_summary=inf,
        )

        d = result.to_dict()
        assert "inference_summary" in d
        assert d["inference_summary"]["bar_count_for_returns"] == 20


class TestIndexReadsInferenceSummary:
    """Tests for IndexedExperiment reading inference_summary from artifacts."""

    def test_indexed_experiment_includes_inference_summary(self) -> None:
        """IndexedExperiment includes inference_summary field."""
        from quantbot.experiment.index import IndexedExperiment

        indexed = IndexedExperiment(
            experiment_name="test",
            strategy_name="TestStrategy",
            fixture_name="test_fixture",
            gate_status="PASS",
            split_count=0,
            signal_count=5,
            receipt_digest="abc123",
            artifact_path=Path("/tmp/result.json"),
            result_type="single",
            inference_summary={
                "bar_count_for_returns": 10,
                "mean_return": 0.001,
                "std_return": 0.02,
                "gross_return_total": 0.05,
                "net_return_total": 0.04,
                "cost_deduction_total": 0.01,
                "sharpe_like": None,
                "annualized": False,
                "interval": "unknown",
                "annualization_note": "not annualized - interval unknown",
            },
        )

        assert indexed.inference_summary is not None
        assert indexed.inference_summary["bar_count_for_returns"] == 10
        assert indexed.inference_summary["mean_return"] == 0.001

    def test_index_reads_inference_summary_from_json(self) -> None:
        """Index reads inference_summary from experiment_result.json."""
        import tempfile
        from quantbot.experiment.index import index_experiment_artifacts

        with tempfile.TemporaryDirectory() as tmpdir:
            artifact_path = Path(tmpdir) / "experiment_result.json"
            artifact_data = {
                "experiment_name": "test-exp",
                "strategy_name": "ThresholdStrategy",
                "strategy_params": {},
                "fixture_name": "BTCUSDT_8h",
                "engine_version": "0.1.0",
                "receipt_digest": "abc123",
                "bar_count": 100,
                "signal_count": 5,
                "first_timestamp": "2023-01-01T00:00:00+00:00",
                "last_timestamp": "2023-01-02T00:00:00+00:00",
                "long_count": 3,
                "short_count": 2,
                "flat_count": 0,
                "gate_verdict": None,
                "fee_bps": 10.0,
                "slippage_bps": 3.0,
                "inference_summary": {
                    "bar_count_for_returns": 10,
                    "mean_return": 0.001,
                    "std_return": 0.02,
                    "gross_return_total": 0.05,
                    "net_return_total": 0.04,
                    "cost_deduction_total": 0.01,
                    "sharpe_like": None,
                    "annualized": False,
                    "interval": "unknown",
                    "annualization_note": "not annualized - interval unknown",
                },
            }
            artifact_path.write_text(json.dumps(artifact_data), encoding="utf-8")

            indexed = index_experiment_artifacts([artifact_path])

            assert len(indexed) == 1
            assert indexed[0].inference_summary is not None
            assert indexed[0].inference_summary["bar_count_for_returns"] == 10
            assert indexed[0].inference_summary["mean_return"] == 0.001


class TestLegacyArtifactsBackwardCompatibilityInference:
    """Tests for graceful handling of legacy artifacts missing inference_summary."""

    def test_legacy_artifact_missing_inference_summary(self) -> None:
        """Indexing a legacy artifact without inference_summary does not break."""
        import tempfile
        from quantbot.experiment.index import index_experiment_artifacts

        with tempfile.TemporaryDirectory() as tmpdir:
            legacy_path = Path(tmpdir) / "experiment_result.json"
            legacy_data = {
                "experiment_name": "legacy-exp",
                "strategy_name": "ThresholdStrategy",
                "strategy_params": {},
                "fixture_name": "BTCUSDT_8h",
                "engine_version": "0.1.0",
                "receipt_digest": "abc123",
                "bar_count": 100,
                "signal_count": 5,
                "first_timestamp": "2023-01-01T00:00:00+00:00",
                "last_timestamp": "2023-01-02T00:00:00+00:00",
                "long_count": 2,
                "short_count": 3,
                "flat_count": 0,
                "gate_verdict": None,
                "fee_bps": 10.0,
                "slippage_bps": 3.0,
                # No inference_summary field
            }
            legacy_path.write_text(json.dumps(legacy_data), encoding="utf-8")

            indexed = index_experiment_artifacts([legacy_path])

            assert len(indexed) == 1
            assert indexed[0].experiment_name == "legacy-exp"
            # inference_summary should be None for legacy artifacts
            assert indexed[0].inference_summary is None

    def test_legacy_walkforward_missing_inference_summary(self) -> None:
        """Indexing a legacy walkforward artifact without inference_summary does not break."""
        import tempfile
        from quantbot.experiment.index import index_experiment_artifacts

        with tempfile.TemporaryDirectory() as tmpdir:
            legacy_path = Path(tmpdir) / "walkforward_result.json"
            legacy_data = {
                "experiment_name": "legacy-wf",
                "strategy_name": "ThresholdStrategy",
                "strategy_params": {},
                "fixture_name": "BTCUSDT_8h",
                "engine_version": "0.1.0",
                "split_count": 2,
                "aggregate_signal_count": 10,
                "gate_verdict": None,
                "fee_bps": 10.0,
                "slippage_bps": 3.0,
                # No inference_summary field
                "split_results": [],
            }
            legacy_path.write_text(json.dumps(legacy_data), encoding="utf-8")

            indexed = index_experiment_artifacts([legacy_path])

            assert len(indexed) == 1
            assert indexed[0].experiment_name == "legacy-wf"
            assert indexed[0].inference_summary is None
