"""Tests for cost-robustness sensitivity scan."""

import pytest
from quantbot.experiment.result import (
    CostRobustnessLevel,
    CostRobustnessSummary,
    COST_STRESS_MULTIPLIERS,
    compute_cost_robustness,
    WalkForwardExperimentResult,
    WalkForwardSplitResult,
    EconomicsSummary,
    ReturnSummary,
    ReturnSeries,
    compute_inference_summary,
)


class TestCostRobustnessConstants:
    """Tests for COST_STRESS_MULTIPLIERS constant."""

    def test_stress_multipliers_are_defined(self):
        """Verify stress multipliers constant is defined."""
        assert COST_STRESS_MULTIPLIERS == (0.5, 1.0, 2.0, 3.0, 5.0)

    def test_stress_multipliers_count(self):
        """Verify we have 5 stress levels."""
        assert len(COST_STRESS_MULTIPLIERS) == 5


class TestCostRobustnessLevel:
    """Tests for CostRobustnessLevel dataclass."""

    def test_to_dict_basic(self):
        """Verify CostRobustnessLevel serializes correctly."""
        level = CostRobustnessLevel(
            stress_multiplier=2.0,
            stressed_total_cost_bps=100.0,
            stressed_net_return_total=0.05,
            stressed_sharpe_like=1.5,
            stressed_dsr=1.2,
            stressed_psr=0.95,
        )
        d = level.to_dict()
        assert d["stress_multiplier"] == 2.0
        assert d["stressed_total_cost_bps"] == 100.0
        assert d["stressed_net_return_total"] == 0.05
        assert d["sharpe_like"] == 1.5
        assert d["dsr"] == 1.2
        assert d["psr"] == 0.95

    def test_to_dict_with_none_sharpe(self):
        """Verify serialization works with None sharpe."""
        level = CostRobustnessLevel(
            stress_multiplier=0.5,
            stressed_total_cost_bps=25.0,
            stressed_net_return_total=0.10,
            stressed_sharpe_like=None,
        )
        d = level.to_dict()
        assert d["stress_multiplier"] == 0.5
        assert d["sharpe_like"] is None
        assert d["dsr"] is None
        assert d["psr"] is None


class TestCostRobustnessSummary:
    """Tests for CostRobustnessSummary dataclass."""

    def test_to_dict_complete(self):
        """Verify full CostRobustnessSummary serializes correctly."""
        level = CostRobustnessLevel(
            stress_multiplier=2.0,
            stressed_total_cost_bps=100.0,
            stressed_net_return_total=0.05,
            stressed_sharpe_like=1.5,
        )
        summary = CostRobustnessSummary(
            baseline_assumed_total_cost_bps=50.0,
            scan_levels=[0.5, 1.0, 2.0, 3.0, 5.0],
            results=[level],
            break_even_cost_multiplier=3.0,
            break_even_cost_bps=150.0,
            first_degraded_inference_multiplier=2.0,
            first_degraded_inference_threshold=1.0,
            franken_comparison_note="Franken observed shortfall is ~2.5x baseline.",
            assumptions_limitations="Some limitations text.",
        )
        d = summary.to_dict()
        assert d["baseline_assumed_total_cost_bps"] == 50.0
        assert len(d["results"]) == 1
        assert d["break_even_cost_multiplier"] == 3.0
        assert d["break_even_cost_bps"] == 150.0
        assert d["first_degraded_inference_multiplier"] == 2.0
        assert d["first_degraded_inference_threshold"] == 1.0
        assert "Franken" in d["franken_comparison_note"]
        assert "limitations" in d["assumptions_limitations"]

    def test_to_dict_minimal(self):
        """Verify minimal CostRobustnessSummary serializes correctly."""
        summary = CostRobustnessSummary(
            baseline_assumed_total_cost_bps=0.0,
            scan_levels=[0.5, 1.0],
            results=[],
            assumptions_limitations="No economics available.",
        )
        d = summary.to_dict()
        assert d["baseline_assumed_total_cost_bps"] == 0.0
        assert len(d["results"]) == 0
        assert d["break_even_cost_multiplier"] is None


class TestComputeCostRobustness:
    """Tests for compute_cost_robustness function."""

    def _make_wf_result(self, gross_return: float, cost_deduction: float, bars_held: int) -> WalkForwardExperimentResult:
        """Create a minimal WalkForwardExperimentResult for testing."""
        split = WalkForwardSplitResult(
            split_index=0,
            train_bar_count=100,
            test_bar_count=50,
            signal_count=10,
            long_count=5,
            short_count=3,
            flat_count=2,
            receipt_path=None,
            artifact_path=None,
            economics_summary=EconomicsSummary(
                cost_side_count=8,
                entry_count=5,
                exit_count=3,
                flip_count=0,
                fee_bps=5.0,
                slippage_bps=5.0,
                assumed_total_cost_bps=80.0,  # 8 * (5 + 5)
            ),
            return_summary=ReturnSummary(
                gross_return_total=gross_return,
                net_return_total=gross_return - cost_deduction,
                cost_deduction_total=cost_deduction,
                bars_held=bars_held,
                winning_bars=6,
                losing_bars=4,
            ),
            return_series=ReturnSeries(
                gross_returns=[gross_return / bars_held] * bars_held,
                net_returns=[(gross_return - cost_deduction) / bars_held] * bars_held,
                bar_timestamps=[],
                interval="8h",
            ),
        )
        return WalkForwardExperimentResult(
            experiment_name="test",
            split_count=1,
            splits=[split],
            total_bar_count=50,
            total_signal_count=10,
            strategy_name="test_strategy",
            trial_count=1,
            fee_bps=5.0,
            slippage_bps=5.0,
        )

    def test_no_economics_returns_empty_result(self):
        """Verify handling when no economics summary is available."""
        split = WalkForwardSplitResult(
            split_index=0,
            train_bar_count=100,
            test_bar_count=50,
            signal_count=10,
            long_count=5,
            short_count=3,
            flat_count=2,
            receipt_path=None,
            artifact_path=None,
        )
        wf_result = WalkForwardExperimentResult(
            experiment_name="test",
            split_count=1,
            splits=[split],
            total_bar_count=50,
            total_signal_count=10,
        )
        summary = compute_cost_robustness(wf_result)
        assert len(summary.results) == 0
        assert "Cannot compute" in summary.assumptions_limitations

    def test_stress_levels_count(self):
        """Verify all stress levels are computed."""
        wf_result = self._make_wf_result(
            gross_return=0.15,
            cost_deduction=0.01,
            bars_held=100,
        )
        summary = compute_cost_robustness(wf_result)
        assert len(summary.results) == len(COST_STRESS_MULTIPLIERS)

    def test_baseline_cost_extracted(self):
        """Verify baseline cost is extracted correctly."""
        wf_result = self._make_wf_result(
            gross_return=0.15,
            cost_deduction=0.008,
            bars_held=100,
        )
        summary = compute_cost_robustness(wf_result)
        # baseline assumed_total_cost_bps should be 8 * (5 + 5) = 80 bps
        assert summary.baseline_assumed_total_cost_bps == 80.0

    def test_break_even_detected(self):
        """Verify break-even multiplier is detected when net return goes negative."""
        wf_result = self._make_wf_result(
            gross_return=0.10,  # 10% gross return
            cost_deduction=0.08,  # 8% cost deduction
            bars_held=100,
        )
        summary = compute_cost_robustness(wf_result)
        # Net return at baseline = 0.10 - 0.08 = 0.02 (positive)
        # At 2x cost: net = 0.10 - 0.16 = -0.06 (negative)
        # At 1x cost: net = 0.10 - 0.08 = 0.02 (positive)
        # So break_even should be between 1.0 and 2.0
        assert summary.break_even_cost_multiplier is not None
        assert 1.0 < summary.break_even_cost_multiplier <= 2.0

    def test_no_break_even_when_profitable_at_max(self):
        """Verify no break-even when profitable even at max stress."""
        wf_result = self._make_wf_result(
            gross_return=1.0,  # 100% gross return
            cost_deduction=0.05,  # 5% cost
            bars_held=100,
        )
        summary = compute_cost_robustness(wf_result)
        # Even at 5x stress: net = 1.0 - 0.25 = 0.75 (still positive)
        assert summary.break_even_cost_multiplier is None

    def test_stressed_sharpe_computed(self):
        """Verify stressed Sharpe-like is computed when returns have variance."""
        # Create non-uniform returns to ensure std > 0
        per_bar_gross = [0.003, 0.001, 0.002, 0.0015, 0.0025] * 20  # 100 bars with variance
        net_return_total = 0.15 - 0.01  # 14%
        cost_per_bar = 0.01 / 100  # 0.0001 per bar
        per_bar_net = [g - cost_per_bar for g in per_bar_gross]
        
        split = WalkForwardSplitResult(
            split_index=0,
            train_bar_count=100,
            test_bar_count=50,
            signal_count=10,
            long_count=5,
            short_count=3,
            flat_count=2,
            receipt_path=None,
            artifact_path=None,
            economics_summary=EconomicsSummary(
                cost_side_count=8,
                entry_count=5,
                exit_count=3,
                flip_count=0,
                fee_bps=5.0,
                slippage_bps=5.0,
                assumed_total_cost_bps=80.0,
            ),
            return_summary=ReturnSummary(
                gross_return_total=sum(per_bar_gross),
                net_return_total=sum(per_bar_net),
                cost_deduction_total=0.01,
                bars_held=100,
                winning_bars=60,
                losing_bars=40,
            ),
            return_series=ReturnSeries(
                gross_returns=per_bar_gross,
                net_returns=per_bar_net,
                bar_timestamps=[],
                interval="8h",
            ),
        )
        wf_result = WalkForwardExperimentResult(
            experiment_name="test",
            split_count=1,
            splits=[split],
            total_bar_count=50,
            total_signal_count=10,
            strategy_name="test_strategy",
            trial_count=1,
            fee_bps=5.0,
            slippage_bps=5.0,
        )
        summary = compute_cost_robustness(wf_result)
        # Should have some stressed_sharpe_like values
        sharpes = [r.stressed_sharpe_like for r in summary.results if r.stressed_sharpe_like is not None]
        assert len(sharpes) > 0, "Expected some non-None sharpe-like values"

    def test_inference_threshold_detection(self):
        """Verify first degraded inference multiplier is detected."""
        # Create non-uniform returns to ensure std > 0
        per_bar_gross = [0.003, 0.001, 0.002, 0.0015, 0.0025] * 20  # 100 bars with variance
        net_return_total = 0.15 - 0.01  # 14%
        cost_per_bar = 0.01 / 100  # 0.0001 per bar
        per_bar_net = [g - cost_per_bar for g in per_bar_gross]
        
        split = WalkForwardSplitResult(
            split_index=0,
            train_bar_count=100,
            test_bar_count=50,
            signal_count=10,
            long_count=5,
            short_count=3,
            flat_count=2,
            receipt_path=None,
            artifact_path=None,
            economics_summary=EconomicsSummary(
                cost_side_count=8,
                entry_count=5,
                exit_count=3,
                flip_count=0,
                fee_bps=5.0,
                slippage_bps=5.0,
                assumed_total_cost_bps=80.0,
            ),
            return_summary=ReturnSummary(
                gross_return_total=sum(per_bar_gross),
                net_return_total=sum(per_bar_net),
                cost_deduction_total=0.01,
                bars_held=100,
                winning_bars=60,
                losing_bars=40,
            ),
            return_series=ReturnSeries(
                gross_returns=per_bar_gross,
                net_returns=per_bar_net,
                bar_timestamps=[],
                interval="8h",
            ),
        )
        wf_result = WalkForwardExperimentResult(
            experiment_name="test",
            split_count=1,
            splits=[split],
            total_bar_count=50,
            total_signal_count=10,
            strategy_name="test_strategy",
            trial_count=1,
            fee_bps=5.0,
            slippage_bps=5.0,
        )
        # Set a threshold that should be exceeded at some stress level
        # Sharpe at 1x stress is ~89, at 5x stress is ~70, so use 75
        summary = compute_cost_robustness(wf_result, inference_threshold=75.0)
        # The stressed sharpe should be lower than baseline
        # At high enough stress, it should degrade
        assert summary.first_degraded_inference_multiplier is not None
        assert summary.first_degraded_inference_threshold == 75.0

    def test_franken_note_added(self):
        """Verify Franken observational note is added when record provided."""
        from dataclasses import replace
        from quantbot.experiment.calibration import FrankenReconciliationRecord

        wf_result = self._make_wf_result(
            gross_return=0.15,
            cost_deduction=0.01,
            bars_held=100,
        )
        franken_record = FrankenReconciliationRecord(
            family_id="test",
            observed_avg_shortfall_bps=100.0,  # 100 bps observed shortfall
        )
        summary = compute_cost_robustness(wf_result, franken_record=franken_record)
        assert summary.franken_comparison_note is not None
        assert "Franken" in summary.franken_comparison_note
        assert "100" in summary.franken_comparison_note

    def test_assumptions_not_empty(self):
        """Verify assumptions/limitations string is not empty."""
        wf_result = self._make_wf_result(
            gross_return=0.15,
            cost_deduction=0.01,
            bars_held=100,
        )
        summary = compute_cost_robustness(wf_result)
        assert len(summary.assumptions_limitations) > 0


class TestCostRobustnessWalkForwardResult:
    """Tests for robustness_summary field in WalkForwardExperimentResult."""

    def test_robustness_summary_field_exists(self):
        """Verify robustness_summary field exists in WalkForwardExperimentResult."""
        wf_result = WalkForwardExperimentResult(
            experiment_name="test",
            split_count=1,
            splits=[],
            total_bar_count=50,
            total_signal_count=10,
        )
        assert hasattr(wf_result, "robustness_summary")

    def test_robustness_summary_serialized(self):
        """Verify robustness_summary is included in to_dict output."""
        split = WalkForwardSplitResult(
            split_index=0,
            train_bar_count=100,
            test_bar_count=50,
            signal_count=10,
            long_count=5,
            short_count=3,
            flat_count=2,
            receipt_path=None,
            artifact_path=None,
            economics_summary=EconomicsSummary(
                cost_side_count=8,
                entry_count=5,
                exit_count=3,
                flip_count=0,
                fee_bps=5.0,
                slippage_bps=5.0,
                assumed_total_cost_bps=80.0,
            ),
            return_summary=ReturnSummary(
                gross_return_total=0.10,
                net_return_total=0.08,
                cost_deduction_total=0.02,
                bars_held=100,
                winning_bars=6,
                losing_bars=4,
            ),
        )
        wf_result = WalkForwardExperimentResult(
            experiment_name="test",
            split_count=1,
            splits=[split],
            total_bar_count=50,
            total_signal_count=10,
            robustness_summary=CostRobustnessSummary(
                baseline_assumed_total_cost_bps=80.0,
                scan_levels=[0.5, 1.0, 2.0],
                results=[],
                assumptions_limitations="Test.",
            ),
        )
        d = wf_result.to_dict()
        assert "robustness_summary" in d
        assert d["robustness_summary"]["baseline_assumed_total_cost_bps"] == 80.0
