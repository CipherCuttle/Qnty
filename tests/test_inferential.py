"""Tests for PSR/DSR inferential layer.

Tests the probabilistic and deflated Sharpe ratio computation layer
in quantbot.experiment.result, including:
- PSR (Probabilistic Sharpe Ratio) computation
- DSR (Deflated Sharpe Ratio) computation
- Skewness and kurtosis corrections
- InferentialSummary persistence
- Index reading with inferential data
- Legacy artifact compatibility
"""

from __future__ import annotations

import json
import tempfile
from pathlib import Path

import pytest
from scipy.stats import skew as scipy_skew, kurtosis as scipy_kurtosis

from quantbot.core.determinism import canonical_json_dumps
from quantbot.experiment.index import index_experiment_artifacts, IndexedExperiment
from quantbot.experiment.result import (
    InferentialSummary,
    InferenceSummary,
    ReturnSeries,
    ExperimentResult,
    WalkForwardExperimentResult,
    WalkForwardSplitResult,
    compute_psr,
    compute_dsr,
    compute_inferential_summary,
    _compute_skewness,
    _compute_kurtosis,
    compute_inference_summary,
)
from quantbot.experiment.spec import ExperimentSpec


# =============================================================================
# 1. DETERMINISTIC PSR/DSR CALCULATION
# =============================================================================


class TestPSRDeterministic:
    """Tests for PSR computation with known statistics."""

    def test_psr_zero_sharpe(self):
        """PSR with SR=0 should be exactly 0.5 (no evidence in either direction)."""
        psr = compute_psr(sharpe_like=0.0, track_record_length=252)
        assert 0.49 < psr < 0.51, f"PSR for SR=0 should be ~0.5, got {psr}"

    def test_psr_positive_sharpe(self):
        """PSR with positive SR should be > 0.5."""
        psr = compute_psr(sharpe_like=0.5, track_record_length=252)
        assert psr > 0.5, f"PSR for positive SR should be > 0.5, got {psr}"

    def test_psr_negative_sharpe(self):
        """PSR with negative SR should be < 0.5."""
        psr = compute_psr(sharpe_like=-0.5, track_record_length=252)
        assert psr < 0.5, f"PSR for negative SR should be < 0.5, got {psr}"

    def test_psr_clamped_to_valid_range(self):
        """PSR should always be in [0, 1]."""
        # Very short track with extreme SR
        psr = compute_psr(sharpe_like=10.0, track_record_length=2)
        assert 0.0 <= psr <= 1.0, f"PSR should be clamped to [0,1], got {psr}"

        # Negative extreme
        psr = compute_psr(sharpe_like=-10.0, track_record_length=2)
        assert 0.0 <= psr <= 1.0, f"PSR should be clamped to [0,1], got {psr}"

    def test_psr_nearly_normal_case(self):
        """PSR with near-zero skew/kurt should be close to 0.5 for SR=0."""
        # Without skewness/kurtosis corrections, SR=0 gives PSR=0.5 exactly
        psr = compute_psr(sharpe_like=0.0, track_record_length=252)
        assert 0.49 < psr < 0.51


class TestDSRDeterministic:
    """Tests for DSR computation."""

    def test_dsr_returns_none_when_trial_count_1(self):
        """DSR should return None when trial_count < 2."""
        dsr, note = compute_dsr(sharpe_like=1.0, trial_count=1, track_record_length=100)
        assert dsr is None
        assert "trial_count < 2" in note

    def test_dsr_returns_none_when_track_record_too_short(self):
        """DSR should return None when track_record_length < 3."""
        dsr, note = compute_dsr(sharpe_like=1.0, trial_count=10, track_record_length=2)
        assert dsr is None
        assert "track_record_length" in note

    def test_dsr_with_high_sharpe_exceeds_expected_max(self):
        """High Sharpe that exceeds expected max should yield positive DSR."""
        dsr, note = compute_dsr(sharpe_like=3.0, trial_count=10, track_record_length=252)
        assert dsr is not None
        assert dsr > 0, f"High Sharpe should yield positive DSR, got {dsr}"

    def test_dsr_with_low_sharpe_below_expected_max(self):
        """Low Sharpe that doesn't exceed expected max should yield negative DSR."""
        dsr, note = compute_dsr(sharpe_like=0.1, trial_count=100, track_record_length=252)
        assert dsr is not None
        assert dsr < 0, f"Low Sharpe should yield negative DSR, got {dsr}"


# =============================================================================
# 2. DEGENERATE CASES
# =============================================================================


class TestSkewnessDegenerate:
    """Tests for skewness edge cases."""

    def test_skewness_returns_none_for_empty_series(self):
        """Skewness should return None for empty series."""
        result = _compute_skewness([])
        assert result is None

    def test_skewness_returns_none_for_single_value(self):
        """Skewness should return None for n=1."""
        result = _compute_skewness([1.0])
        assert result is None

    def test_skewness_returns_none_for_two_values(self):
        """Skewness should return None for n=2."""
        result = _compute_skewness([1.0, 2.0])
        assert result is None

    def test_skewness_returns_none_for_zero_variance(self):
        """Skewness should return None when std=0 (all identical values)."""
        result = _compute_skewness([1.0, 1.0, 1.0, 1.0])
        assert result is None

    def test_skewness_positive_for_right_skewed(self):
        """Positive skewness for right-skewed distribution."""
        # Mix of mostly low values with a few high outliers
        returns = [-0.01, -0.01, -0.01, -0.01, -0.01, 0.05]
        result = _compute_skewness(returns)
        assert result is not None
        assert result > 0, "Right-skewed should have positive skewness"

    def test_skewness_negative_for_left_skewed(self):
        """Negative skewness for left-skewed distribution."""
        # Mix of mostly high values with a few low outliers
        returns = [0.01, 0.01, 0.01, 0.01, 0.01, -0.05]
        result = _compute_skewness(returns)
        assert result is not None
        assert result < 0, "Left-skewed should have negative skewness"

    def test_skewness_zero_for_symmetric(self):
        """Near-zero skewness for symmetric distribution."""
        # Approximately symmetric: -3, -1, 1, 3
        returns = [-0.03, -0.01, 0.01, 0.03]
        result = _compute_skewness(returns)
        assert result is not None
        assert -0.1 < result < 0.1, "Symmetric distribution should have near-zero skewness"


class TestKurtosisDegenerate:
    """Tests for kurtosis edge cases."""

    def test_kurtosis_returns_none_for_empty_series(self):
        """Kurtosis should return None for empty series."""
        result = _compute_kurtosis([])
        assert result is None

    def test_kurtosis_returns_none_for_single_value(self):
        """Kurtosis should return None for n=1."""
        result = _compute_kurtosis([1.0])
        assert result is None

    def test_kurtosis_returns_none_for_two_values(self):
        """Kurtosis should return None for n=2."""
        result = _compute_kurtosis([1.0, 2.0])
        assert result is None

    def test_kurtosis_returns_none_for_three_values(self):
        """Kurtosis should return None for n=3."""
        result = _compute_kurtosis([1.0, 2.0, 3.0])
        assert result is None

    def test_kurtosis_returns_none_for_zero_variance(self):
        """Kurtosis should return None when std=0 (all identical values)."""
        result = _compute_kurtosis([1.0, 1.0, 1.0, 1.0])
        assert result is None

    def test_kurtosis_positive_for_fat_tails(self):
        """Positive excess kurtosis for fat-tailed distribution."""
        # Mix of mostly normal values with extreme outliers
        returns = [0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, -0.1, 0.1, -0.2, 0.2]
        result = _compute_kurtosis(returns)
        assert result is not None
        assert result > 0, "Fat-tailed distribution should have positive excess kurtosis"


class TestPSREdgeCases:
    """Tests for PSR edge cases."""

    def test_psr_returns_zero_when_track_record_too_short(self):
        """PSR should return 0.0 when track_record_length < 2."""
        psr = compute_psr(sharpe_like=1.0, track_record_length=1)
        assert psr == 0.0

        psr = compute_psr(sharpe_like=1.0, track_record_length=0)
        assert psr == 0.0

    def test_psr_handles_negative_sharpe(self):
        """PSR should handle negative Sharpe ratios."""
        psr = compute_psr(sharpe_like=-2.0, track_record_length=100)
        assert 0.0 <= psr <= 1.0

    def test_psr_with_skewness_correction(self):
        """PSR with skewness correction should differ from uncorrected."""
        psr_uncorrected = compute_psr(sharpe_like=0.5, track_record_length=100)
        psr_corrected = compute_psr(
            sharpe_like=0.5,
            track_record_length=100,
            skewness=0.5,
            kurtosis=0.0,
        )
        # Skewness correction should change the PSR
        assert psr_corrected != psr_uncorrected

    def test_psr_with_kurtosis_correction(self):
        """PSR with kurtosis correction should differ from uncorrected."""
        psr_uncorrected = compute_psr(sharpe_like=0.5, track_record_length=100)
        psr_corrected = compute_psr(
            sharpe_like=0.5,
            track_record_length=100,
            skewness=None,
            kurtosis=2.0,
        )
        # Kurtosis correction should change the PSR
        assert psr_corrected != psr_uncorrected


# =============================================================================
# 3. ARTIFACT PERSISTENCE
# =============================================================================


class TestInferentialSummaryPersistence:
    """Tests for InferentialSummary serialization."""

    def test_inferential_summary_to_dict(self):
        """Test InferentialSummary.to_dict() produces expected keys."""
        summary = InferentialSummary(
            psr=0.75,
            psr_n=252,
            dsr=0.45,
            dsr_trial_count=10,
            dsr_note="test note",
            sharpe_like=0.5,
            std_return=0.02,
            skewness=0.1,
            kurtosis=0.2,
        )
        d = summary.to_dict()
        assert "psr" in d
        assert "psr_n" in d
        assert "dsr" in d
        assert "dsr_trial_count" in d
        assert "dsr_note" in d
        assert "sharpe_like" in d
        assert "std_return" in d
        assert "skewness" in d
        assert "kurtosis" in d
        assert "assumptions_note" in d

    def test_inferential_summary_round_trip(self):
        """Test inferential_summary survives JSON serialization/deserialization."""
        original = InferentialSummary(
            psr=0.75,
            psr_n=252,
            dsr=0.45,
            dsr_trial_count=10,
            dsr_note="test note",
            sharpe_like=0.5,
            std_return=0.02,
            skewness=0.1,
            kurtosis=0.2,
        )
        json_str = json.dumps(original.to_dict())
        parsed = json.loads(json_str)
        assert parsed["psr"] == 0.75
        assert parsed["dsr"] == 0.45
        assert parsed["dsr_note"] == "test note"


class TestExperimentResultPersistence:
    """Tests for ExperimentResult inferential_summary persistence."""

    def _make_minimal_spec(self) -> ExperimentSpec:
        """Create a minimal ExperimentSpec for testing."""
        return ExperimentSpec(
            experiment_name="test",
            strategy_name="test",
            strategy_params={},
            fixture_name="test",
            family_id="test-family",
            variant_id="test-variant",
            trial_count=5,
        )

    def _make_minimal_result(self) -> ExperimentResult:
        """Create a minimal ExperimentResult with inference_summary."""
        net_returns = [0.01, -0.005, 0.015, 0.01, -0.01] * 50  # 250 bars
        return_series = ReturnSeries(
            gross_returns=net_returns,
            net_returns=net_returns,
            bar_timestamps=[],
            interval="8h",
        )
        # Compute the inference_summary
        inference_summary = compute_inference_summary(return_series)
        return ExperimentResult(
            spec=self._make_minimal_spec(),
            receipt_path=Path("/tmp/receipt.json"),
            result_path=Path("/tmp/result.json"),
            receipt_digest="abc123",
            bar_count=250,
            signal_count=10,
            first_timestamp="2024-01-01T00:00:00Z",
            last_timestamp="2024-01-10T00:00:00Z",
            return_series=return_series,
            inference_summary=inference_summary,
        )

    def test_experiment_result_includes_inferential_summary(self):
        """ExperimentResult.to_dict() should include inferential_summary."""
        result = self._make_minimal_result()
        d = result.to_dict()
        assert "inferential_summary" in d

    def test_experiment_result_inferential_summary_has_psr(self):
        """inferential_summary should have PSR when inference_summary is present."""
        result = self._make_minimal_result()
        d = result.to_dict()
        assert d["inferential_summary"] is not None
        assert "psr" in d["inferential_summary"]
        assert d["inferential_summary"]["psr"] is not None

    def test_experiment_result_inferential_summary_with_trial_count(self):
        """inferential_summary should have DSR when trial_count >= 2."""
        result = self._make_minimal_result()
        # spec.trial_count = 5 >= 2, bar_count = 250 >= 3
        d = result.to_dict()
        assert d["inferential_summary"] is not None
        # DSR should be computed since trial_count >= 2 and bar_count >= 3
        assert d["inferential_summary"]["dsr"] is not None

    def test_experiment_result_json_serialization(self):
        """ExperimentResult.to_json() should produce valid JSON with inferential_summary."""
        result = self._make_minimal_result()
        json_str = result.to_json()
        parsed = json.loads(json_str)
        assert "inferential_summary" in parsed


class TestWalkForwardResultPersistence:
    """Tests for WalkForwardExperimentResult inferential_summary persistence."""

    def _make_minimal_wf_result(self) -> WalkForwardExperimentResult:
        """Create a minimal WalkForwardExperimentResult with aggregate inference_summary."""
        net_returns = [0.01, -0.005, 0.015] * 30  # 90 bars

        # Create two splits
        split1 = WalkForwardSplitResult(
            split_index=0,
            train_bar_count=60,
            test_bar_count=30,
            signal_count=5,
            long_count=3,
            short_count=2,
            flat_count=0,
            receipt_path=None,
            artifact_path=None,
            return_series=ReturnSeries(
                gross_returns=net_returns[:45],
                net_returns=net_returns[:45],
                bar_timestamps=[],
                interval="8h",
            ),
        )
        split2 = WalkForwardSplitResult(
            split_index=1,
            train_bar_count=60,
            test_bar_count=30,
            signal_count=5,
            long_count=3,
            short_count=2,
            flat_count=0,
            receipt_path=None,
            artifact_path=None,
            return_series=ReturnSeries(
                gross_returns=net_returns[45:],
                net_returns=net_returns[45:],
                bar_timestamps=[],
                interval="8h",
            ),
        )

        wf = WalkForwardExperimentResult(
            experiment_name="test-wf",
            split_count=2,
            splits=[split1, split2],
            total_bar_count=90,
            total_signal_count=10,
            strategy_name="test",
            strategy_params={},
            fixture_name="test",
            family_id="test-family",
            variant_id="test-variant",
            trial_count=1,
            fee_bps=10.0,
            slippage_bps=5.0,
        )
        # Compute aggregate inference_summary for the wf result
        wf.inference_summary = wf.aggregate_inference_summary()
        return wf

    def test_walkforward_result_has_inference_summary(self):
        """WalkForwardExperimentResult should have aggregate inference_summary."""
        result = self._make_minimal_wf_result()
        assert result.inference_summary is not None

    def test_walkforward_result_to_dict_includes_inference_summary(self):
        """WalkForwardExperimentResult.to_dict() should include inference_summary."""
        result = self._make_minimal_wf_result()
        d = result.to_dict()
        assert "inference_summary" in d
        assert d["inference_summary"] is not None


# =============================================================================
# 4. INDEX READING
# =============================================================================


class TestIndexReading:
    """Tests for index_experiment_artifacts with inferential_summary."""

    def _create_minimal_artifact(
        self, artifact_path: Path, trial_count: int = 5, has_inferential: bool = True
    ) -> None:
        """Create a minimal experiment artifact for testing."""
        artifact_path.parent.mkdir(parents=True, exist_ok=True)

        # Build the artifact data
        net_returns = [0.01, -0.005, 0.015, 0.01, -0.01] * 50
        data = {
            "experiment_name": "test",
            "strategy_name": "test",
            "strategy_params": {},
            "fixture_name": "test",
            "family_id": "test-family",
            "variant_id": "test-variant",
            "trial_count": trial_count,
            "engine_version": "0.1.0",
            "receipt_digest": "abc123",
            "bar_count": 250,
            "signal_count": 10,
            "first_timestamp": "2024-01-01T00:00:00Z",
            "last_timestamp": "2024-01-10T00:00:00Z",
            "long_count": 5,
            "short_count": 3,
            "flat_count": 2,
            "gate_verdict": {"status": "PASS", "reasons": [], "checked": []},
            "fee_bps": 10.0,
            "slippage_bps": 5.0,
            "return_series": {
                "gross_returns": net_returns,
                "net_returns": net_returns,
                "bar_timestamps": [],
                "interval": "8h",
            },
        }

        # Compute what the inferential_summary would look like
        if has_inferential:
            rs = ReturnSeries(
                gross_returns=net_returns,
                net_returns=net_returns,
                bar_timestamps=[],
                interval="8h",
            )
            inference_summary = compute_inference_summary(rs)
            inferential = compute_inferential_summary(inference_summary, trial_count)
            data["inferential_summary"] = inferential.to_dict()

        artifact_path.write_text(canonical_json_dumps(data), encoding="utf-8")

    def test_index_reads_inferential_summary(self, tmp_path: Path):
        """index_experiment_artifacts should populate inferential_summary."""
        artifact_path = tmp_path / "experiment" / "experiment_result.json"
        self._create_minimal_artifact(artifact_path, has_inferential=True)
        results = index_experiment_artifacts([artifact_path])
        assert len(results) == 1, f"Expected 1 result, got {len(results)}"
        indexed = results[0]
        assert indexed.inferential_summary is not None
        assert "psr" in indexed.inferential_summary

    def test_index_json_output_contains_inferential(self, tmp_path: Path):
        """Indexed artifact JSON output should include inferential_summary fields."""
        artifact_path = tmp_path / "experiment" / "experiment_result.json"
        self._create_minimal_artifact(artifact_path, has_inferential=True)
        results = index_experiment_artifacts([artifact_path])
        assert len(results) == 1
        indexed = results[0]
        d = indexed.__dict__
        assert d.get("inferential_summary") is not None


# =============================================================================
# 5. LEGACY ARTIFACT COMPATIBILITY
# =============================================================================


class TestLegacyCompatibility:
    """Tests for backward compatibility with artifacts lacking inferential_summary."""

    def test_artifact_without_inferential_loads_without_error(self, tmp_path: Path):
        """Artifacts without inferential_summary should load without error."""
        artifact_path = tmp_path / "legacy_experiment" / "experiment_result.json"

        # Create an artifact WITHOUT inferential_summary (old format)
        net_returns = [0.01, -0.005, 0.015] * 30
        data = {
            "experiment_name": "legacy-test",
            "strategy_name": "test",
            "strategy_params": {},
            "fixture_name": "test",
            "family_id": "test-family",
            "variant_id": "test-variant",
            "trial_count": 5,
            "engine_version": "0.1.0",
            "receipt_digest": "abc123",
            "bar_count": 90,
            "signal_count": 5,
            "first_timestamp": "2024-01-01T00:00:00Z",
            "last_timestamp": "2024-01-04T00:00:00Z",
            "long_count": 2,
            "short_count": 2,
            "flat_count": 1,
            "gate_verdict": {"status": "PASS", "reasons": [], "checked": []},
            "fee_bps": 10.0,
            "slippage_bps": 5.0,
            "return_series": {
                "gross_returns": net_returns,
                "net_returns": net_returns,
                "bar_timestamps": [],
                "interval": "8h",
            },
            # NOTE: No inferential_summary field - this is a legacy artifact
        }

        artifact_path.parent.mkdir(parents=True, exist_ok=True)
        artifact_path.write_text(canonical_json_dumps(data), encoding="utf-8")

        # Should not raise
        results = index_experiment_artifacts([artifact_path])
        assert len(results) == 1, f"Expected 1 result, got {len(results)}"
        indexed = results[0]
        # inferential_summary should be None (not present in old artifact)
        assert indexed.inferential_summary is None

    def test_artifact_with_null_inferential_loads_without_error(self, tmp_path: Path):
        """Artifacts with null inferential_summary should load without error."""
        artifact_path = tmp_path / "null_inferential_experiment" / "experiment_result.json"

        net_returns = [0.01, -0.005, 0.015] * 30
        data = {
            "experiment_name": "null-inf-test",
            "strategy_name": "test",
            "strategy_params": {},
            "fixture_name": "test",
            "family_id": "test-family",
            "variant_id": "test-variant",
            "trial_count": 5,
            "engine_version": "0.1.0",
            "receipt_digest": "abc123",
            "bar_count": 90,
            "signal_count": 5,
            "first_timestamp": "2024-01-01T00:00:00Z",
            "last_timestamp": "2024-01-04T00:00:00Z",
            "long_count": 2,
            "short_count": 2,
            "flat_count": 1,
            "gate_verdict": {"status": "PASS", "reasons": [], "checked": []},
            "fee_bps": 10.0,
            "slippage_bps": 5.0,
            "return_series": {
                "gross_returns": net_returns,
                "net_returns": net_returns,
                "bar_timestamps": [],
                "interval": "8h",
            },
            "inferential_summary": None,  # Explicitly null
        }

        artifact_path.parent.mkdir(parents=True, exist_ok=True)
        artifact_path.write_text(canonical_json_dumps(data), encoding="utf-8")

        # Should not raise
        results = index_experiment_artifacts([artifact_path])
        assert len(results) == 1, f"Expected 1 result, got {len(results)}"


# =============================================================================
# 6. COMPUTE INFENENTIAL SUMMARY INTEGRATION
# =============================================================================


class TestComputeInferentialSummary:
    """Integration tests for compute_inferential_summary."""

    def _make_inference_summary(
        self, sharpe_like: float, std: float, bar_count: int
    ) -> InferenceSummary:
        """Create a minimal InferenceSummary for testing."""
        return InferenceSummary(
            bar_count_for_returns=bar_count,
            mean_return=0.001,
            std_return=std,
            gross_return_total=0.1,
            net_return_total=0.09,
            cost_deduction_total=0.01,
            sharpe_like=sharpe_like,
            annualized=True,
            interval="8h",
            annualization_note="annualized using 1095 bars/year",
        )

    def test_compute_inferential_summary_returns_psr(self):
        """compute_inferential_summary should return PSR when inputs valid."""
        inf_summary = self._make_inference_summary(
            sharpe_like=0.5, std=0.02, bar_count=100
        )
        result = compute_inferential_summary(inf_summary, trial_count=None)
        assert result.psr is not None
        assert 0.0 <= result.psr <= 1.0

    def test_compute_inferential_summary_returns_none_psr_when_n_too_small(self):
        """PSR should be None when bar_count < 2."""
        inf_summary = self._make_inference_summary(
            sharpe_like=0.5, std=0.02, bar_count=1
        )
        result = compute_inferential_summary(inf_summary, trial_count=None)
        assert result.psr is None

    def test_compute_inferential_summary_returns_dsr_when_trial_count_sufficient(self):
        """DSR should be computed when trial_count >= 2."""
        inf_summary = self._make_inference_summary(
            sharpe_like=0.5, std=0.02, bar_count=100
        )
        result = compute_inferential_summary(inf_summary, trial_count=10)
        assert result.dsr is not None
        assert result.dsr_trial_count == 10

    def test_compute_inferential_summary_returns_none_dsr_when_trial_count_1(self):
        """DSR should be None when trial_count < 2."""
        inf_summary = self._make_inference_summary(
            sharpe_like=0.5, std=0.02, bar_count=100
        )
        result = compute_inferential_summary(inf_summary, trial_count=1)
        assert result.dsr is None
        assert result.dsr_trial_count is None

    def test_compute_inferential_summary_preserves_sharpe_like(self):
        """inferential_summary should preserve sharpe_like from inference_summary."""
        inf_summary = self._make_inference_summary(
            sharpe_like=0.75, std=0.02, bar_count=100
        )
        result = compute_inferential_summary(inf_summary, trial_count=None)
        assert result.sharpe_like == 0.75

    def test_compute_inferential_summary_preserves_std(self):
        """inferential_summary should preserve std_return from inference_summary."""
        inf_summary = self._make_inference_summary(
            sharpe_like=0.75, std=0.025, bar_count=100
        )
        result = compute_inferential_summary(inf_summary, trial_count=None)
        assert result.std_return == 0.025
