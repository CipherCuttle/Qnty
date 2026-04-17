"""Tests for the Qnty → Franken promotion contract.

Tests classify_promotion and compute_promotion_summary functions.
Paper mode only - no real trading.
"""

import json
import tempfile
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from quantbot.experiment.calibration import MATERIAL_MISMATCH_THRESHOLD_BPS
from quantbot.experiment.index import (
    IndexedExperiment,
    classify_promotion,
    compute_promotion_summary,
)
from quantbot.experiment.result import PromotionSummary, PromotionVerdict


class TestPaperEligiblePath:
    """Test cases for paper_eligible classification path."""

    def _make_single_experiment_all_gates_pass(self) -> IndexedExperiment:
        """Create a single experiment where ALL hard gates pass and all eligibility fields present."""
        return IndexedExperiment(
            experiment_name="paper-eligible-test",
            strategy_name="ThresholdStrategy",
            fixture_name="BTCUSDT_8h",
            gate_status="PASS",
            split_count=0,
            signal_count=5,  # >= 3 for single
            receipt_digest="abc123",
            artifact_path=Path("/tmp/artifact.json"),
            result_type="single",
            family_id="family-001",
            variant_id="variant-a",
            trial_count=10,
            fee_bps=10.0,
            slippage_bps=3.0,
            inference_summary={
                "bar_count_for_returns": 100,  # > 0 for single
                "mean_return": 0.001,
                "std_return": 0.01,
                "gross_return_total": 0.1,
                "net_return_total": 0.08,
                "cost_deduction_total": 0.02,
                "sharpe_like": 0.8,
                "annualized": True,
                "interval": "8h",
            },
            # No provisional signals
        )

    def test_paper_eligible_classification(self) -> None:
        """All hard gates pass + all eligibility fields + no provisional => paper_eligible."""
        exp = self._make_single_experiment_all_gates_pass()
        verdict = classify_promotion(exp)

        assert verdict.classification == "paper_eligible"
        assert verdict.hard_gate_status == "PASS"
        assert verdict.eligibility_status == "PASS"
        assert verdict.review_signal_flags == []
        assert verdict.provisional_flags == []

    def test_paper_eligible_hard_gate_reasons_empty(self) -> None:
        """paper_eligible has no hard gate failure reasons."""
        exp = self._make_single_experiment_all_gates_pass()
        verdict = classify_promotion(exp)

        assert verdict.hard_gate_status == "PASS"
        assert verdict.hard_gate_reasons == []

    def test_paper_eligible_eligibility_reasons_empty(self) -> None:
        """paper_eligible has no eligibility failure reasons."""
        exp = self._make_single_experiment_all_gates_pass()
        verdict = classify_promotion(exp)

        assert verdict.eligibility_status == "PASS"
        assert verdict.eligibility_reasons == []

    def test_paper_eligible_provenance_populated(self) -> None:
        """paper_eligible verdict has provenance data."""
        exp = self._make_single_experiment_all_gates_pass()
        verdict = classify_promotion(exp)

        assert verdict.provenance["family_id"] == "family-001"
        assert verdict.provenance["variant_id"] == "variant-a"
        assert verdict.provenance["trial_count"] == 10
        assert verdict.provenance["result_type"] == "single"

    def test_paper_eligible_honest_caveats_present(self) -> None:
        """paper_eligible includes honest caveats."""
        exp = self._make_single_experiment_all_gates_pass()
        verdict = classify_promotion(exp)

        assert len(verdict.honest_caveats) > 0
        assert any("PAPER" in c or "paper" in c for c in verdict.honest_caveats)


class TestPaperReviewRequiredPath:
    """Test cases for paper_review_required classification path."""

    def _make_with_provisional_signal(self, provisional_type: str) -> IndexedExperiment:
        """Create a single experiment with a provisional signal present."""
        exp = IndexedExperiment(
            experiment_name="review-required-test",
            strategy_name="ThresholdStrategy",
            fixture_name="BTCUSDT_8h",
            gate_status="PASS",
            split_count=0,
            signal_count=5,
            receipt_digest="abc123",
            artifact_path=Path("/tmp/artifact.json"),
            result_type="single",
            family_id="family-001",
            variant_id="variant-a",
            trial_count=10,
            fee_bps=10.0,
            slippage_bps=3.0,
            inference_summary={
                "bar_count_for_returns": 100,
                "mean_return": 0.001,
                "std_return": 0.01,
                "gross_return_total": 0.1,
                "net_return_total": 0.08,
                "cost_deduction_total": 0.02,
                "sharpe_like": 0.8,
                "annualized": True,
                "interval": "8h",
            },
        )

        if provisional_type == "pbo":
            exp.overfitting_summary = {
                "pbo": 0.15,
                "path_count": 100,
                "method": "bootstrap",
            }
        elif provisional_type == "dsr_provisional":
            exp.inferential_summary = {
                "psr": 0.7,
                "dsr": 0.6,
                "dsr_provisional": True,
                "dsr_trial_semantics_note": "split_count < 2, using raw trial_count",
                "sharpe_like": 0.8,
                "std_return": 0.01,
            }
        elif provisional_type == "calibration":
            # Calibration requires a mock calibration object
            mock_cal = MagicMock()
            mock_cal.delta_bps = 3.5
            mock_cal.assumed_total_cost_bps = 13.0
            mock_cal.observed_avg_shortfall_bps = 16.5
            mock_cal.record_count = 50
            exp.calibration = mock_cal
        elif provisional_type == "sharpe_like_no_interval":
            exp.inference_summary = {
                "bar_count_for_returns": 100,
                "mean_return": 0.001,
                "std_return": 0.01,
                "gross_return_total": 0.1,
                "net_return_total": 0.08,
                "cost_deduction_total": 0.02,
                "sharpe_like": 0.8,
                "annualized": False,
                "interval": "unknown",
            }

        return exp

    def test_paper_review_required_with_pbo(self) -> None:
        """PBO present => paper_review_required."""
        exp = self._make_with_provisional_signal("pbo")
        verdict = classify_promotion(exp)

        assert verdict.classification == "paper_review_required"
        assert verdict.hard_gate_status == "PASS"
        assert verdict.eligibility_status == "PASS"
        assert "pbo_non_canonical" in verdict.provisional_flags
        # PBO is surfaced in provisional_flags and review_signals, but NOT in review_signal_flags
        # (review_signal_flags only contain actionable thresholds like psr < 0.5, dsr < 0.5, etc.)
        assert "pbo" in verdict.review_signals

    def test_paper_review_required_with_dsr_provisional(self) -> None:
        """DSR provisional flag => paper_review_required."""
        exp = self._make_with_provisional_signal("dsr_provisional")
        verdict = classify_promotion(exp)

        assert verdict.classification == "paper_review_required"
        assert "dsr_trial_semantics_exploration_count" in verdict.provisional_flags
        assert "dsr_provisional_trial_semantics" in verdict.review_signal_flags

    def test_paper_review_required_with_calibration(self) -> None:
        """Calibration present => paper_review_required."""
        exp = self._make_with_provisional_signal("calibration")
        verdict = classify_promotion(exp)

        assert verdict.classification == "paper_review_required"
        assert "calibration_requires_external_franken" in verdict.provisional_flags

    def test_calibration_mild_mismatch_no_material_flag(self) -> None:
        """Mild mismatch (10 bps) does NOT trigger calibration_material_mismatch flag."""
        exp = IndexedExperiment(
            experiment_name="calibration-mild-test",
            strategy_name="ThresholdStrategy",
            fixture_name="BTCUSDT_8h",
            gate_status="PASS",
            split_count=0,
            signal_count=5,
            receipt_digest="abc123",
            artifact_path=Path("/tmp/artifact.json"),
            result_type="single",
            family_id="family-001",
            variant_id="variant-a",
            trial_count=10,
            fee_bps=10.0,
            slippage_bps=3.0,
            inference_summary={
                "bar_count_for_returns": 100,
                "mean_return": 0.001,
                "std_return": 0.01,
                "gross_return_total": 0.1,
                "net_return_total": 0.08,
                "cost_deduction_total": 0.02,
                "sharpe_like": 0.8,
                "annualized": True,
                "interval": "8h",
            },
        )
        mock_cal = MagicMock()
        mock_cal.delta_bps = 10.0  # 5 < |delta| <= 15, so mild_mismatch
        mock_cal.record_count = 100
        exp.calibration = mock_cal

        verdict = classify_promotion(exp)

        assert "calibration_material_mismatch" not in verdict.review_signal_flags

    def test_calibration_material_mismatch_triggers_flag(self) -> None:
        """Material mismatch (20 bps) DOES trigger calibration_material_mismatch flag."""
        exp = IndexedExperiment(
            experiment_name="calibration-material-test",
            strategy_name="ThresholdStrategy",
            fixture_name="BTCUSDT_8h",
            gate_status="PASS",
            split_count=0,
            signal_count=5,
            receipt_digest="abc123",
            artifact_path=Path("/tmp/artifact.json"),
            result_type="single",
            family_id="family-001",
            variant_id="variant-a",
            trial_count=10,
            fee_bps=10.0,
            slippage_bps=3.0,
            inference_summary={
                "bar_count_for_returns": 100,
                "mean_return": 0.001,
                "std_return": 0.01,
                "gross_return_total": 0.1,
                "net_return_total": 0.08,
                "cost_deduction_total": 0.02,
                "sharpe_like": 0.8,
                "annualized": True,
                "interval": "8h",
            },
        )
        mock_cal = MagicMock()
        mock_cal.delta_bps = 20.0  # > 15 bps, so material_mismatch
        mock_cal.record_count = 100
        exp.calibration = mock_cal

        verdict = classify_promotion(exp)

        assert "calibration_material_mismatch" in verdict.review_signal_flags

    def test_calibration_exact_threshold_no_flag(self) -> None:
        """Exact threshold (15 bps) does NOT trigger calibration_material_mismatch flag."""
        exp = IndexedExperiment(
            experiment_name="calibration-exact-test",
            strategy_name="ThresholdStrategy",
            fixture_name="BTCUSDT_8h",
            gate_status="PASS",
            split_count=0,
            signal_count=5,
            receipt_digest="abc123",
            artifact_path=Path("/tmp/artifact.json"),
            result_type="single",
            family_id="family-001",
            variant_id="variant-a",
            trial_count=10,
            fee_bps=10.0,
            slippage_bps=3.0,
            inference_summary={
                "bar_count_for_returns": 100,
                "mean_return": 0.001,
                "std_return": 0.01,
                "gross_return_total": 0.1,
                "net_return_total": 0.08,
                "cost_deduction_total": 0.02,
                "sharpe_like": 0.8,
                "annualized": True,
                "interval": "8h",
            },
        )
        mock_cal = MagicMock()
        mock_cal.delta_bps = MATERIAL_MISMATCH_THRESHOLD_BPS  # exactly 15.0
        mock_cal.record_count = 100
        exp.calibration = mock_cal

        verdict = classify_promotion(exp)

        assert "calibration_material_mismatch" not in verdict.review_signal_flags

    def test_calibration_insufficient_records_no_flag(self) -> None:
        """Insufficient records (record_count < 10) does not trigger material mismatch flag."""
        exp = IndexedExperiment(
            experiment_name="calibration-insufficient-test",
            strategy_name="ThresholdStrategy",
            fixture_name="BTCUSDT_8h",
            gate_status="PASS",
            split_count=0,
            signal_count=5,
            receipt_digest="abc123",
            artifact_path=Path("/tmp/artifact.json"),
            result_type="single",
            family_id="family-001",
            variant_id="variant-a",
            trial_count=10,
            fee_bps=10.0,
            slippage_bps=3.0,
            inference_summary={
                "bar_count_for_returns": 100,
                "mean_return": 0.001,
                "std_return": 0.01,
                "gross_return_total": 0.1,
                "net_return_total": 0.08,
                "cost_deduction_total": 0.02,
                "sharpe_like": 0.8,
                "annualized": True,
                "interval": "8h",
            },
        )
        mock_cal = MagicMock()
        mock_cal.delta_bps = 20.0  # Would be material mismatch with enough records
        mock_cal.record_count = 5  # Below 10 threshold
        exp.calibration = mock_cal

        verdict = classify_promotion(exp)

        assert "calibration_material_mismatch" not in verdict.review_signal_flags

    def test_paper_review_required_with_sharpe_like_no_interval(self) -> None:
        """Sharpe-like without interval => paper_review_required."""
        exp = self._make_with_provisional_signal("sharpe_like_no_interval")
        verdict = classify_promotion(exp)

        assert verdict.classification == "paper_review_required"
        assert "sharpe_like_without_interval" in verdict.provisional_flags


class TestPaperIneligibleHardGateFail:
    """Test cases for paper_ineligible due to hard gate failures."""

    def test_bar_count_zero_fails_hard_gate_single(self) -> None:
        """bar_count == 0 fails hard gate for single experiment."""
        exp = IndexedExperiment(
            experiment_name="ineligible-zero-bars",
            strategy_name="ThresholdStrategy",
            fixture_name="BTCUSDT_8h",
            gate_status="PASS",
            split_count=0,
            signal_count=5,
            receipt_digest="abc123",
            artifact_path=Path("/tmp/artifact.json"),
            result_type="single",
            family_id="family-001",
            variant_id="variant-a",
            trial_count=10,
            fee_bps=10.0,
            slippage_bps=3.0,
            inference_summary={
                "bar_count_for_returns": 0,  # Zero bars
                "mean_return": 0.0,
                "std_return": None,
                "gross_return_total": 0.0,
                "net_return_total": 0.0,
                "cost_deduction_total": 0.0,
                "sharpe_like": None,
                "annualized": False,
                "interval": "8h",
            },
        )
        verdict = classify_promotion(exp)

        assert verdict.classification == "paper_ineligible"
        assert verdict.hard_gate_status == "FAIL"
        assert any("bar_count is zero" in r for r in verdict.hard_gate_reasons)

    def test_signal_count_below_threshold_fails_hard_gate_single(self) -> None:
        """signal_count < 3 fails hard gate for single experiment."""
        exp = IndexedExperiment(
            experiment_name="ineligible-low-signals",
            strategy_name="ThresholdStrategy",
            fixture_name="BTCUSDT_8h",
            gate_status="PASS",
            split_count=0,
            signal_count=2,  # < 3
            receipt_digest="abc123",
            artifact_path=Path("/tmp/artifact.json"),
            result_type="single",
            family_id="family-001",
            variant_id="variant-a",
            trial_count=10,
            fee_bps=10.0,
            slippage_bps=3.0,
            inference_summary={
                "bar_count_for_returns": 100,
                "mean_return": 0.001,
                "std_return": 0.01,
                "gross_return_total": 0.1,
                "net_return_total": 0.08,
                "cost_deduction_total": 0.02,
                "sharpe_like": 0.8,
                "annualized": True,
                "interval": "8h",
            },
        )
        verdict = classify_promotion(exp)

        assert verdict.classification == "paper_ineligible"
        assert verdict.hard_gate_status == "FAIL"
        assert any("signal_count" in r and "3" in r for r in verdict.hard_gate_reasons)

    def test_split_count_below_minimum_fails_hard_gate_walkforward(self) -> None:
        """split_count < 2 fails hard gate for walkforward."""
        exp = IndexedExperiment(
            experiment_name="ineligible-low-splits",
            strategy_name="ThresholdStrategy",
            fixture_name="BTCUSDT_8h",
            gate_status="PASS",
            split_count=1,  # < 2
            signal_count=10,
            receipt_digest=None,
            artifact_path=Path("/tmp/artifact.json"),
            result_type="walkforward",
            family_id="family-001",
            variant_id="variant-a",
            trial_count=10,
            fee_bps=10.0,
            slippage_bps=3.0,
        )
        verdict = classify_promotion(exp)

        assert verdict.classification == "paper_ineligible"
        assert verdict.hard_gate_status == "FAIL"
        assert any("split_count" in r and "2" in r for r in verdict.hard_gate_reasons)

    def test_total_signal_count_below_minimum_fails_hard_gate_walkforward(self) -> None:
        """total_signal_count < 5 fails hard gate for walkforward."""
        exp = IndexedExperiment(
            experiment_name="ineligible-low-total-signals",
            strategy_name="ThresholdStrategy",
            fixture_name="BTCUSDT_8h",
            gate_status="PASS",
            split_count=3,  # >= 2
            signal_count=3,  # < 5
            receipt_digest=None,
            artifact_path=Path("/tmp/artifact.json"),
            result_type="walkforward",
            family_id="family-001",
            variant_id="variant-a",
            trial_count=10,
            fee_bps=10.0,
            slippage_bps=3.0,
        )
        verdict = classify_promotion(exp)

        assert verdict.classification == "paper_ineligible"
        assert verdict.hard_gate_status == "FAIL"
        assert any("total_signal_count" in r and "5" in r for r in verdict.hard_gate_reasons)

    def test_gate_status_fail_fails_hard_gate(self) -> None:
        """gate_status != PASS fails hard gate."""
        exp = IndexedExperiment(
            experiment_name="ineligible-gate-fail",
            strategy_name="ThresholdStrategy",
            fixture_name="BTCUSDT_8h",
            gate_status="FAIL",
            split_count=0,
            signal_count=5,
            receipt_digest="abc123",
            artifact_path=Path("/tmp/artifact.json"),
            result_type="single",
            family_id="family-001",
            variant_id="variant-a",
            trial_count=10,
            fee_bps=10.0,
            slippage_bps=3.0,
            inference_summary={
                "bar_count_for_returns": 100,
                "mean_return": 0.001,
                "std_return": 0.01,
                "gross_return_total": 0.1,
                "net_return_total": 0.08,
                "cost_deduction_total": 0.02,
                "sharpe_like": 0.8,
                "annualized": True,
                "interval": "8h",
            },
        )
        verdict = classify_promotion(exp)

        assert verdict.classification == "paper_ineligible"
        assert verdict.hard_gate_status == "FAIL"
        assert any("gate_status" in r for r in verdict.hard_gate_reasons)


class TestPaperIneligibleMissingEligibilityField:
    """Test cases for paper_ineligible due to missing eligibility fields."""

    def test_missing_family_id_fails_eligibility(self) -> None:
        """Missing family_id => paper_ineligible."""
        exp = IndexedExperiment(
            experiment_name="ineligible-no-family",
            strategy_name="ThresholdStrategy",
            fixture_name="BTCUSDT_8h",
            gate_status="PASS",
            split_count=0,
            signal_count=5,
            receipt_digest="abc123",
            artifact_path=Path("/tmp/artifact.json"),
            result_type="single",
            family_id=None,  # Missing
            variant_id="variant-a",
            trial_count=10,
            fee_bps=10.0,
            slippage_bps=3.0,
            inference_summary={
                "bar_count_for_returns": 100,
                "mean_return": 0.001,
                "std_return": 0.01,
                "gross_return_total": 0.1,
                "net_return_total": 0.08,
                "cost_deduction_total": 0.02,
                "sharpe_like": 0.8,
                "annualized": True,
                "interval": "8h",
            },
        )
        verdict = classify_promotion(exp)

        assert verdict.classification == "paper_ineligible"
        assert verdict.eligibility_status == "FAIL"
        assert verdict.hard_gate_status == "PASS"
        assert any("family_id" in r for r in verdict.eligibility_reasons)

    def test_missing_variant_id_fails_eligibility(self) -> None:
        """Missing variant_id => paper_ineligible."""
        exp = IndexedExperiment(
            experiment_name="ineligible-no-variant",
            strategy_name="ThresholdStrategy",
            fixture_name="BTCUSDT_8h",
            gate_status="PASS",
            split_count=0,
            signal_count=5,
            receipt_digest="abc123",
            artifact_path=Path("/tmp/artifact.json"),
            result_type="single",
            family_id="family-001",
            variant_id=None,  # Missing
            trial_count=10,
            fee_bps=10.0,
            slippage_bps=3.0,
            inference_summary={
                "bar_count_for_returns": 100,
                "mean_return": 0.001,
                "std_return": 0.01,
                "gross_return_total": 0.1,
                "net_return_total": 0.08,
                "cost_deduction_total": 0.02,
                "sharpe_like": 0.8,
                "annualized": True,
                "interval": "8h",
            },
        )
        verdict = classify_promotion(exp)

        assert verdict.classification == "paper_ineligible"
        assert verdict.eligibility_status == "FAIL"
        assert any("variant_id" in r for r in verdict.eligibility_reasons)

    def test_missing_trial_count_fails_eligibility(self) -> None:
        """Missing trial_count => paper_ineligible."""
        exp = IndexedExperiment(
            experiment_name="ineligible-no-trial",
            strategy_name="ThresholdStrategy",
            fixture_name="BTCUSDT_8h",
            gate_status="PASS",
            split_count=0,
            signal_count=5,
            receipt_digest="abc123",
            artifact_path=Path("/tmp/artifact.json"),
            result_type="single",
            family_id="family-001",
            variant_id="variant-a",
            trial_count=None,  # Missing
            fee_bps=10.0,
            slippage_bps=3.0,
            inference_summary={
                "bar_count_for_returns": 100,
                "mean_return": 0.001,
                "std_return": 0.01,
                "gross_return_total": 0.1,
                "net_return_total": 0.08,
                "cost_deduction_total": 0.02,
                "sharpe_like": 0.8,
                "annualized": True,
                "interval": "8h",
            },
        )
        verdict = classify_promotion(exp)

        assert verdict.classification == "paper_ineligible"
        assert verdict.eligibility_status == "FAIL"
        assert any("trial_count" in r for r in verdict.eligibility_reasons)

    def test_zero_fee_bps_fails_eligibility(self) -> None:
        """fee_bps == 0 => paper_ineligible."""
        exp = IndexedExperiment(
            experiment_name="ineligible-zero-fee",
            strategy_name="ThresholdStrategy",
            fixture_name="BTCUSDT_8h",
            gate_status="PASS",
            split_count=0,
            signal_count=5,
            receipt_digest="abc123",
            artifact_path=Path("/tmp/artifact.json"),
            result_type="single",
            family_id="family-001",
            variant_id="variant-a",
            trial_count=10,
            fee_bps=0.0,  # Zero
            slippage_bps=3.0,
            inference_summary={
                "bar_count_for_returns": 100,
                "mean_return": 0.001,
                "std_return": 0.01,
                "gross_return_total": 0.1,
                "net_return_total": 0.08,
                "cost_deduction_total": 0.02,
                "sharpe_like": 0.8,
                "annualized": True,
                "interval": "8h",
            },
        )
        verdict = classify_promotion(exp)

        assert verdict.classification == "paper_ineligible"
        assert verdict.eligibility_status == "FAIL"
        assert any("fee_bps" in r for r in verdict.eligibility_reasons)

    def test_zero_slippage_bps_fails_eligibility(self) -> None:
        """slippage_bps == 0 => paper_ineligible."""
        exp = IndexedExperiment(
            experiment_name="ineligible-zero-slip",
            strategy_name="ThresholdStrategy",
            fixture_name="BTCUSDT_8h",
            gate_status="PASS",
            split_count=0,
            signal_count=5,
            receipt_digest="abc123",
            artifact_path=Path("/tmp/artifact.json"),
            result_type="single",
            family_id="family-001",
            variant_id="variant-a",
            trial_count=10,
            fee_bps=10.0,
            slippage_bps=0.0,  # Zero
            inference_summary={
                "bar_count_for_returns": 100,
                "mean_return": 0.001,
                "std_return": 0.01,
                "gross_return_total": 0.1,
                "net_return_total": 0.08,
                "cost_deduction_total": 0.02,
                "sharpe_like": 0.8,
                "annualized": True,
                "interval": "8h",
            },
        )
        verdict = classify_promotion(exp)

        assert verdict.classification == "paper_ineligible"
        assert verdict.eligibility_status == "FAIL"
        assert any("slippage_bps" in r for r in verdict.eligibility_reasons)


class TestProvisionalDimensionHandling:
    """Test that provisional dimensions are surfaced but NOT used as hard gates."""

    def test_provisional_flags_not_used_as_hard_gates(self) -> None:
        """Provisional dimensions should surface in provisional_flags but NOT fail hard gates."""
        # Create an experiment with all hard gates passing but with provisional signals
        exp = IndexedExperiment(
            experiment_name="provisional-test",
            strategy_name="ThresholdStrategy",
            fixture_name="BTCUSDT_8h",
            gate_status="PASS",
            split_count=0,
            signal_count=5,
            receipt_digest="abc123",
            artifact_path=Path("/tmp/artifact.json"),
            result_type="single",
            family_id="family-001",
            variant_id="variant-a",
            trial_count=10,
            fee_bps=10.0,
            slippage_bps=3.0,
            inference_summary={
                "bar_count_for_returns": 100,
                "mean_return": 0.001,
                "std_return": 0.01,
                "gross_return_total": 0.1,
                "net_return_total": 0.08,
                "cost_deduction_total": 0.02,
                "sharpe_like": 0.8,
                "annualized": True,
                "interval": "8h",
            },
            overfitting_summary={
                "pbo": 0.15,
                "path_count": 100,
                "method": "bootstrap",
            },
        )
        verdict = classify_promotion(exp)

        # Hard gates should still PASS even with provisional signals
        assert verdict.hard_gate_status == "PASS"
        assert verdict.hard_gate_reasons == []

        # But classification should be review_required due to provisional flags
        assert verdict.classification == "paper_review_required"
        assert "pbo_non_canonical" in verdict.provisional_flags

    def test_pbo_is_provisional_not_a_hard_gate(self) -> None:
        """PBO presence does not fail hard gates, only triggers review_required."""
        exp = IndexedExperiment(
            experiment_name="pbo-provisional-test",
            strategy_name="ThresholdStrategy",
            fixture_name="BTCUSDT_8h",
            gate_status="PASS",
            split_count=0,
            signal_count=5,
            receipt_digest="abc123",
            artifact_path=Path("/tmp/artifact.json"),
            result_type="single",
            family_id="family-001",
            variant_id="variant-a",
            trial_count=10,
            fee_bps=10.0,
            slippage_bps=3.0,
            inference_summary={
                "bar_count_for_returns": 100,
                "mean_return": 0.001,
                "std_return": 0.01,
                "gross_return_total": 0.1,
                "net_return_total": 0.08,
                "cost_deduction_total": 0.02,
                "sharpe_like": 0.8,
                "annualized": True,
                "interval": "8h",
            },
            overfitting_summary={
                "pbo": 0.15,
                "path_count": 100,
                "method": "bootstrap",
            },
        )
        verdict = classify_promotion(exp)

        # PBO is surfaced but NOT used as a hard gate
        assert "pbo_non_canonical" in verdict.provisional_flags
        assert verdict.hard_gate_status == "PASS"
        assert verdict.classification == "paper_review_required"


class TestJsonOutputShape:
    """Test that PromotionVerdict and PromotionSummary produce valid JSON-serializable output."""

    def test_promotion_verdict_to_dict_is_json_serializable(self) -> None:
        """PromotionVerdict.to_dict() produces valid JSON-serializable output."""
        exp = IndexedExperiment(
            experiment_name="json-test",
            strategy_name="ThresholdStrategy",
            fixture_name="BTCUSDT_8h",
            gate_status="PASS",
            split_count=0,
            signal_count=5,
            receipt_digest="abc123",
            artifact_path=Path("/tmp/artifact.json"),
            result_type="single",
            family_id="family-001",
            variant_id="variant-a",
            trial_count=10,
            fee_bps=10.0,
            slippage_bps=3.0,
            inference_summary={
                "bar_count_for_returns": 100,
                "mean_return": 0.001,
                "std_return": 0.01,
                "gross_return_total": 0.1,
                "net_return_total": 0.08,
                "cost_deduction_total": 0.02,
                "sharpe_like": 0.8,
                "annualized": True,
                "interval": "8h",
            },
        )
        verdict = classify_promotion(exp)
        verdict_dict = verdict.to_dict()

        # Should not raise
        json_str = json.dumps(verdict_dict)
        assert json_str is not None

        # Should have all required fields
        assert "classification" in verdict_dict
        assert "hard_gate_status" in verdict_dict
        assert "hard_gate_reasons" in verdict_dict
        assert "eligibility_status" in verdict_dict
        assert "eligibility_reasons" in verdict_dict
        assert "review_signals" in verdict_dict
        assert "review_signal_flags" in verdict_dict
        assert "provisional_flags" in verdict_dict
        assert "provenance" in verdict_dict
        assert "honest_caveats" in verdict_dict

    def test_promotion_summary_to_dict_is_json_serializable(self) -> None:
        """PromotionSummary.to_dict() produces valid JSON-serializable output."""
        exp = IndexedExperiment(
            experiment_name="summary-json-test",
            strategy_name="ThresholdStrategy",
            fixture_name="BTCUSDT_8h",
            gate_status="PASS",
            split_count=0,
            signal_count=5,
            receipt_digest="abc123",
            artifact_path=Path("/tmp/artifact.json"),
            result_type="single",
            family_id="family-001",
            variant_id="variant-a",
            trial_count=10,
            fee_bps=10.0,
            slippage_bps=3.0,
            inference_summary={
                "bar_count_for_returns": 100,
                "mean_return": 0.001,
                "std_return": 0.01,
                "gross_return_total": 0.1,
                "net_return_total": 0.08,
                "cost_deduction_total": 0.02,
                "sharpe_like": 0.8,
                "annualized": True,
                "interval": "8h",
            },
        )
        summary = compute_promotion_summary(exp)
        summary_dict = summary.to_dict()

        # Should not raise
        json_str = json.dumps(summary_dict)
        assert json_str is not None

        # Should have all required fields
        assert "contract_version" in summary_dict
        assert "generated_at" in summary_dict
        assert "artifact_path" in summary_dict
        assert "experiment_name" in summary_dict
        assert "family_id" in summary_dict
        assert "variant_id" in summary_dict
        assert "result_type" in summary_dict
        assert "verdict" in summary_dict

    def test_classify_promotion_returns_promotion_verdict(self) -> None:
        """classify_promotion returns a PromotionVerdict with all required fields."""
        exp = IndexedExperiment(
            experiment_name="type-test",
            strategy_name="ThresholdStrategy",
            fixture_name="BTCUSDT_8h",
            gate_status="PASS",
            split_count=0,
            signal_count=5,
            receipt_digest="abc123",
            artifact_path=Path("/tmp/artifact.json"),
            result_type="single",
            family_id="family-001",
            variant_id="variant-a",
            trial_count=10,
            fee_bps=10.0,
            slippage_bps=3.0,
            inference_summary={
                "bar_count_for_returns": 100,
                "mean_return": 0.001,
                "std_return": 0.01,
                "gross_return_total": 0.1,
                "net_return_total": 0.08,
                "cost_deduction_total": 0.02,
                "sharpe_like": 0.8,
                "annualized": True,
                "interval": "8h",
            },
        )
        verdict = classify_promotion(exp)

        assert isinstance(verdict, PromotionVerdict)
        # Check Literal types
        assert verdict.classification in ("paper_eligible", "paper_review_required", "paper_ineligible")
        assert verdict.hard_gate_status in ("PASS", "FAIL")
        assert verdict.eligibility_status in ("PASS", "FAIL")


class TestWalkforwardVsSingleDistinction:
    """Test that single experiment and walkforward use different hard gate thresholds."""

    def test_single_experiment_signal_count_threshold(self) -> None:
        """Single experiment: signal_count >= 3 required."""
        # signal_count = 3 should pass
        exp_pass = IndexedExperiment(
            experiment_name="single-signal-test",
            strategy_name="ThresholdStrategy",
            fixture_name="BTCUSDT_8h",
            gate_status="PASS",
            split_count=0,
            signal_count=3,  # Exactly at threshold
            receipt_digest="abc123",
            artifact_path=Path("/tmp/artifact.json"),
            result_type="single",
            family_id="family-001",
            variant_id="variant-a",
            trial_count=10,
            fee_bps=10.0,
            slippage_bps=3.0,
            inference_summary={
                "bar_count_for_returns": 100,
                "mean_return": 0.001,
                "std_return": 0.01,
                "gross_return_total": 0.1,
                "net_return_total": 0.08,
                "cost_deduction_total": 0.02,
                "sharpe_like": 0.8,
                "annualized": True,
                "interval": "8h",
            },
        )
        verdict_pass = classify_promotion(exp_pass)
        assert verdict_pass.hard_gate_status == "PASS", "signal_count=3 should pass for single"

        # signal_count = 2 should fail
        exp_fail = IndexedExperiment(
            experiment_name="single-signal-test",
            strategy_name="ThresholdStrategy",
            fixture_name="BTCUSDT_8h",
            gate_status="PASS",
            split_count=0,
            signal_count=2,  # Below threshold
            receipt_digest="abc123",
            artifact_path=Path("/tmp/artifact.json"),
            result_type="single",
            family_id="family-001",
            variant_id="variant-a",
            trial_count=10,
            fee_bps=10.0,
            slippage_bps=3.0,
            inference_summary={
                "bar_count_for_returns": 100,
                "mean_return": 0.001,
                "std_return": 0.01,
                "gross_return_total": 0.1,
                "net_return_total": 0.08,
                "cost_deduction_total": 0.02,
                "sharpe_like": 0.8,
                "annualized": True,
                "interval": "8h",
            },
        )
        verdict_fail = classify_promotion(exp_fail)
        assert verdict_fail.hard_gate_status == "FAIL", "signal_count=2 should fail for single"
        assert any("signal_count" in r for r in verdict_fail.hard_gate_reasons)

    def test_walkforward_split_count_threshold(self) -> None:
        """Walkforward: split_count >= 2 required."""
        # split_count = 2 should pass
        exp_pass = IndexedExperiment(
            experiment_name="wf-split-test",
            strategy_name="ThresholdStrategy",
            fixture_name="BTCUSDT_8h",
            gate_status="PASS",
            split_count=2,  # Exactly at threshold
            signal_count=10,
            receipt_digest=None,
            artifact_path=Path("/tmp/artifact.json"),
            result_type="walkforward",
            family_id="family-001",
            variant_id="variant-a",
            trial_count=10,
            fee_bps=10.0,
            slippage_bps=3.0,
        )
        verdict_pass = classify_promotion(exp_pass)
        assert verdict_pass.hard_gate_status == "PASS", "split_count=2 should pass for walkforward"

        # split_count = 1 should fail
        exp_fail = IndexedExperiment(
            experiment_name="wf-split-test",
            strategy_name="ThresholdStrategy",
            fixture_name="BTCUSDT_8h",
            gate_status="PASS",
            split_count=1,  # Below threshold
            signal_count=10,
            receipt_digest=None,
            artifact_path=Path("/tmp/artifact.json"),
            result_type="walkforward",
            family_id="family-001",
            variant_id="variant-a",
            trial_count=10,
            fee_bps=10.0,
            slippage_bps=3.0,
        )
        verdict_fail = classify_promotion(exp_fail)
        assert verdict_fail.hard_gate_status == "FAIL", "split_count=1 should fail for walkforward"

    def test_walkforward_total_signal_count_threshold(self) -> None:
        """Walkforward: total_signal_count >= 5 required."""
        # signal_count = 5 should pass
        exp_pass = IndexedExperiment(
            experiment_name="wf-signal-test",
            strategy_name="ThresholdStrategy",
            fixture_name="BTCUSDT_8h",
            gate_status="PASS",
            split_count=3,
            signal_count=5,  # Exactly at threshold
            receipt_digest=None,
            artifact_path=Path("/tmp/artifact.json"),
            result_type="walkforward",
            family_id="family-001",
            variant_id="variant-a",
            trial_count=10,
            fee_bps=10.0,
            slippage_bps=3.0,
        )
        verdict_pass = classify_promotion(exp_pass)
        assert verdict_pass.hard_gate_status == "PASS", "signal_count=5 should pass for walkforward"

        # signal_count = 4 should fail
        exp_fail = IndexedExperiment(
            experiment_name="wf-signal-test",
            strategy_name="ThresholdStrategy",
            fixture_name="BTCUSDT_8h",
            gate_status="PASS",
            split_count=3,
            signal_count=4,  # Below threshold
            receipt_digest=None,
            artifact_path=Path("/tmp/artifact.json"),
            result_type="walkforward",
            family_id="family-001",
            variant_id="variant-a",
            trial_count=10,
            fee_bps=10.0,
            slippage_bps=3.0,
        )
        verdict_fail = classify_promotion(exp_fail)
        assert verdict_fail.hard_gate_status == "FAIL", "signal_count=4 should fail for walkforward"

    def test_single_experiment_uses_bar_count_not_split_count(self) -> None:
        """Single experiment uses bar_count, not split_count."""
        # A single experiment with split_count=0 but bar_count > 0 should pass
        exp = IndexedExperiment(
            experiment_name="single-bar-test",
            strategy_name="ThresholdStrategy",
            fixture_name="BTCUSDT_8h",
            gate_status="PASS",
            split_count=0,  # Single experiment
            signal_count=5,
            receipt_digest="abc123",
            artifact_path=Path("/tmp/artifact.json"),
            result_type="single",
            family_id="family-001",
            variant_id="variant-a",
            trial_count=10,
            fee_bps=10.0,
            slippage_bps=3.0,
            inference_summary={
                "bar_count_for_returns": 100,  # > 0
                "mean_return": 0.001,
                "std_return": 0.01,
                "gross_return_total": 0.1,
                "net_return_total": 0.08,
                "cost_deduction_total": 0.02,
                "sharpe_like": 0.8,
                "annualized": True,
                "interval": "8h",
            },
        )
        verdict = classify_promotion(exp)

        # Should pass even though split_count=0
        assert verdict.hard_gate_status == "PASS"
        # Should not mention split_count in reasons
        assert not any("split_count" in r for r in verdict.hard_gate_reasons)

    def test_walkforward_does_not_use_single_hard_gates(self) -> None:
        """Walkforward does not use bar_count threshold from single experiment."""
        # A walkforward with bar_count=0 but split_count >= 2 should pass
        exp = IndexedExperiment(
            experiment_name="wf-no-bar-test",
            strategy_name="ThresholdStrategy",
            fixture_name="BTCUSDT_8h",
            gate_status="PASS",
            split_count=3,  # Walkforward
            signal_count=10,
            receipt_digest=None,
            artifact_path=Path("/tmp/artifact.json"),
            result_type="walkforward",
            family_id="family-001",
            variant_id="variant-a",
            trial_count=10,
            fee_bps=10.0,
            slippage_bps=3.0,
            # No inference_summary means bar_count would be 0
            inference_summary=None,
        )
        verdict = classify_promotion(exp)

        # Should pass based on split_count >= 2 and signal_count >= 5
        assert verdict.hard_gate_status == "PASS"
        # Should not mention bar_count in reasons
        assert not any("bar_count" in r for r in verdict.hard_gate_reasons)


class TestComputePromotionSummary:
    """Test compute_promotion_summary function."""

    def test_compute_promotion_summary_returns_promotion_summary(self) -> None:
        """compute_promotion_summary returns a PromotionSummary instance."""
        exp = IndexedExperiment(
            experiment_name="summary-test",
            strategy_name="ThresholdStrategy",
            fixture_name="BTCUSDT_8h",
            gate_status="PASS",
            split_count=0,
            signal_count=5,
            receipt_digest="abc123",
            artifact_path=Path("/tmp/artifact.json"),
            result_type="single",
            family_id="family-001",
            variant_id="variant-a",
            trial_count=10,
            fee_bps=10.0,
            slippage_bps=3.0,
            inference_summary={
                "bar_count_for_returns": 100,
                "mean_return": 0.001,
                "std_return": 0.01,
                "gross_return_total": 0.1,
                "net_return_total": 0.08,
                "cost_deduction_total": 0.02,
                "sharpe_like": 0.8,
                "annualized": True,
                "interval": "8h",
            },
        )
        summary = compute_promotion_summary(exp)

        assert isinstance(summary, PromotionSummary)
        assert summary.experiment_name == "summary-test"
        assert summary.family_id == "family-001"
        assert summary.variant_id == "variant-a"
        assert summary.result_type == "single"
        assert summary.verdict is not None

    def test_compute_promotion_summary_includes_generated_at(self) -> None:
        """compute_promotion_summary includes ISO timestamp."""
        exp = IndexedExperiment(
            experiment_name="timestamp-test",
            strategy_name="ThresholdStrategy",
            fixture_name="BTCUSDT_8h",
            gate_status="PASS",
            split_count=0,
            signal_count=5,
            receipt_digest="abc123",
            artifact_path=Path("/tmp/artifact.json"),
            result_type="single",
            family_id="family-001",
            variant_id="variant-a",
            trial_count=10,
            fee_bps=10.0,
            slippage_bps=3.0,
            inference_summary={
                "bar_count_for_returns": 100,
                "mean_return": 0.001,
                "std_return": 0.01,
                "gross_return_total": 0.1,
                "net_return_total": 0.08,
                "cost_deduction_total": 0.02,
                "sharpe_like": 0.8,
                "annualized": True,
                "interval": "8h",
            },
        )
        summary = compute_promotion_summary(exp)

        assert summary.generated_at != ""
        # Should be ISO format
        assert "T" in summary.generated_at or "-" in summary.generated_at

    def test_compute_promotion_summary_verdict_matches_classify(self) -> None:
        """compute_promotion_summary verdict matches classify_promotion output."""
        exp = IndexedExperiment(
            experiment_name="consistent-test",
            strategy_name="ThresholdStrategy",
            fixture_name="BTCUSDT_8h",
            gate_status="PASS",
            split_count=0,
            signal_count=5,
            receipt_digest="abc123",
            artifact_path=Path("/tmp/artifact.json"),
            result_type="single",
            family_id="family-001",
            variant_id="variant-a",
            trial_count=10,
            fee_bps=10.0,
            slippage_bps=3.0,
            inference_summary={
                "bar_count_for_returns": 100,
                "mean_return": 0.001,
                "std_return": 0.01,
                "gross_return_total": 0.1,
                "net_return_total": 0.08,
                "cost_deduction_total": 0.02,
                "sharpe_like": 0.8,
                "annualized": True,
                "interval": "8h",
            },
        )
        verdict = classify_promotion(exp)
        summary = compute_promotion_summary(exp)

        assert summary.verdict.classification == verdict.classification
        assert summary.verdict.hard_gate_status == verdict.hard_gate_status
        assert summary.verdict.eligibility_status == verdict.eligibility_status
