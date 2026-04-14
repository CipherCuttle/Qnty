"""Tests for experiment index.

Requires PYTHONHASHSEED=0 for deterministic dict ordering.
Paper mode only - no real trading.
"""

import json
import tempfile
from pathlib import Path

import pytest

from quantbot.experiment.index import (
    EligibilityResult,
    IndexedExperiment,
    evaluate_eligibility,
    index_experiment_artifacts,
)
from quantbot.experiment.spec import ExperimentSpec
from quantbot.experiment.walkforward_runner import run_walkforward_experiment


FIXTURE_DIR = Path(__file__).parent / "fixtures"
BTCUSDT_MANIFEST_PATH = FIXTURE_DIR / "BTCUSDT_manifest.json"
BTCUSDT_CSV_PATH = FIXTURE_DIR / "BTCUSDT_8h.csv"


class TestIndexExperimentArtifacts:
    """Tests for index_experiment_artifacts reading existing artifact files."""

    def test_indexes_single_experiment_result(self) -> None:
        """Can index a single experiment_result.json artifact."""
        with tempfile.TemporaryDirectory() as tmpdir:
            out = Path(tmpdir) / "experiment"
            spec = ExperimentSpec(
                experiment_name="index-single-test",
                strategy_name="ThresholdStrategy",
                strategy_params={"threshold": 16500.0, "symbol": "BTCUSDT"},
                fixture_name="BTCUSDT_8h",
            )
            result = run_walkforward_experiment(
                spec=spec,
                manifest_path=BTCUSDT_MANIFEST_PATH,
                csv_path=BTCUSDT_CSV_PATH,
                output_dir=out,
                train_size=100,
                test_size=50,
                step_size=50,
            )
            # The walkforward result writes walkforward_result.json
            wf_path = out / "walkforward_result.json"
            assert wf_path.exists()

            indexed = index_experiment_artifacts([wf_path])
            assert len(indexed) == 1
            assert indexed[0].experiment_name == "index-single-test"
            assert indexed[0].strategy_name == "ThresholdStrategy"
            assert indexed[0].fixture_name == "BTCUSDT_8h"
            assert indexed[0].result_type == "walkforward"
            assert indexed[0].split_count > 0
            assert indexed[0].signal_count >= 0
            # Verify new trial-family fields are present
            assert indexed[0].family_id is not None
            assert indexed[0].variant_id is not None
            assert indexed[0].trial_count is not None

    def test_indexes_walkforward_result(self) -> None:
        """Can index a walkforward_result.json artifact."""
        with tempfile.TemporaryDirectory() as tmpdir:
            out = Path(tmpdir) / "walkforward"
            spec = ExperimentSpec(
                experiment_name="index-wf-test",
                strategy_name="ThresholdStrategy",
                strategy_params={"threshold": 16500.0, "symbol": "BTCUSDT"},
                fixture_name="BTCUSDT_8h",
            )
            run_walkforward_experiment(
                spec=spec,
                manifest_path=BTCUSDT_MANIFEST_PATH,
                csv_path=BTCUSDT_CSV_PATH,
                output_dir=out,
                train_size=100,
                test_size=50,
                step_size=50,
            )
            wf_path = out / "walkforward_result.json"
            indexed = index_experiment_artifacts([wf_path])
            assert len(indexed) == 1
            assert indexed[0].result_type == "walkforward"
            assert indexed[0].split_count > 0

    def test_indexes_directory_with_artifact(self) -> None:
        """Can index a directory path; finds walkforward_result.json inside."""
        with tempfile.TemporaryDirectory() as tmpdir:
            out = Path(tmpdir) / "experiment_dir"
            spec = ExperimentSpec(
                experiment_name="index-dir-test",
                strategy_name="ThresholdStrategy",
                strategy_params={"threshold": 16500.0, "symbol": "BTCUSDT"},
                fixture_name="BTCUSDT_8h",
            )
            run_walkforward_experiment(
                spec=spec,
                manifest_path=BTCUSDT_MANIFEST_PATH,
                csv_path=BTCUSDT_CSV_PATH,
                output_dir=out,
                train_size=100,
                test_size=50,
                step_size=50,
            )
            indexed = index_experiment_artifacts([out])
            assert len(indexed) == 1
            assert indexed[0].result_type == "walkforward"

    def test_raises_on_nonexistent_path(self) -> None:
        """Raises FileNotFoundError for non-existent paths."""
        with tempfile.TemporaryDirectory() as tmpdir:
            bad_path = Path(tmpdir) / "does_not_exist.json"
            with pytest.raises(FileNotFoundError):
                index_experiment_artifacts([bad_path])

    def test_raises_on_unrecognized_artifact(self) -> None:
        """Raises ValueError for unrecognized artifact filename."""
        with tempfile.TemporaryDirectory() as tmpdir:
            bad_file = Path(tmpdir) / "random_file.json"
            bad_file.write_text("{}", encoding="utf-8")
            with pytest.raises(ValueError, match="Unrecognized experiment artifact"):
                index_experiment_artifacts([bad_file])

    def test_indexes_legacy_artifact_missing_trial_fields(self) -> None:
        """Indexing a legacy artifact without family_id/variant_id/trial_count fields does not break."""
        with tempfile.TemporaryDirectory() as tmpdir:
            # Write a legacy artifact without trial-family fields
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
            }
            legacy_path.write_text(json.dumps(legacy_data), encoding="utf-8")

            indexed = index_experiment_artifacts([legacy_path])
            assert len(indexed) == 1
            assert indexed[0].experiment_name == "legacy-exp"
            # Legacy artifacts map missing fields to None
            assert indexed[0].family_id is None
            assert indexed[0].variant_id is None
            assert indexed[0].trial_count is None

    def test_index_handles_legacy_artifact_missing_cost_fields(self) -> None:
        """Indexing a legacy artifact without fee_bps/slippage_bps defaults to 0.0."""
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
            }
            legacy_path.write_text(json.dumps(legacy_data), encoding="utf-8")

            indexed = index_experiment_artifacts([legacy_path])
            assert len(indexed) == 1
            assert indexed[0].experiment_name == "legacy-exp"
            assert indexed[0].fee_bps == 0.0
            assert indexed[0].slippage_bps == 0.0


class TestIndexedExperiment:
    """Tests for IndexedExperiment summary shape."""

    def test_gate_passed_helper(self) -> None:
        """gate_passed() returns True when status is PASS."""
        indexed = IndexedExperiment(
            experiment_name="test",
            strategy_name="TestStrategy",
            fixture_name="test_fixture",
            gate_status="PASS",
            split_count=0,
            signal_count=5,
            receipt_digest=None,
            artifact_path=Path("."),
            result_type="single",
        )
        assert indexed.gate_passed() is True
        assert indexed.gate_failed() is False

    def test_gate_failed_helper(self) -> None:
        """gate_failed() returns True when status is FAIL."""
        indexed = IndexedExperiment(
            experiment_name="test",
            strategy_name="TestStrategy",
            fixture_name="test_fixture",
            gate_status="FAIL",
            split_count=0,
            signal_count=0,
            receipt_digest=None,
            artifact_path=Path("."),
            result_type="single",
        )
        assert indexed.gate_failed() is True
        assert indexed.gate_passed() is False

    def test_gate_status_none(self) -> None:
        """gate_passed/gate_failed return False when status is None."""
        indexed = IndexedExperiment(
            experiment_name="test",
            strategy_name="TestStrategy",
            fixture_name="test_fixture",
            gate_status=None,
            split_count=0,
            signal_count=5,
            receipt_digest=None,
            artifact_path=Path("."),
            result_type="single",
        )
        assert indexed.gate_passed() is False
        assert indexed.gate_failed() is False

    def test_multiple_artifacts_sortable(self) -> None:
        """Multiple indexed experiments can be sorted by signal_count."""
        with tempfile.TemporaryDirectory() as tmpdir:
            out1 = Path(tmpdir) / "exp1"
            out2 = Path(tmpdir) / "exp2"
            spec1 = ExperimentSpec(
                experiment_name="sort-test-1",
                strategy_name="ThresholdStrategy",
                strategy_params={"threshold": 16500.0, "symbol": "BTCUSDT"},
                fixture_name="BTCUSDT_8h",
            )
            spec2 = ExperimentSpec(
                experiment_name="sort-test-2",
                strategy_name="ThresholdStrategy",
                strategy_params={"threshold": 16500.0, "symbol": "BTCUSDT"},
                fixture_name="BTCUSDT_8h",
            )
            run_walkforward_experiment(
                spec=spec1,
                manifest_path=BTCUSDT_MANIFEST_PATH,
                csv_path=BTCUSDT_CSV_PATH,
                output_dir=out1,
                train_size=100,
                test_size=50,
                step_size=50,
            )
            run_walkforward_experiment(
                spec=spec2,
                manifest_path=BTCUSDT_MANIFEST_PATH,
                csv_path=BTCUSDT_CSV_PATH,
                output_dir=out2,
                train_size=100,
                test_size=50,
                step_size=50,
            )
            indexed = index_experiment_artifacts([out1, out2])
            assert len(indexed) == 2
            # Sort by signal_count (descending)
            sorted_idx = sorted(indexed, key=lambda x: x.signal_count, reverse=True)
            assert sorted_idx[0].signal_count >= sorted_idx[1].signal_count


class TestEvaluateEligibility:
    """Tests for evaluate_eligibility() eligibility checks."""

    def _base_artifact(self) -> dict:
        """Return a fully valid artifact dict."""
        return {
            "family_id": "test-family",
            "variant_id": "v1",
            "trial_count": 100,
            "fee_bps": 10,
            "slippage_bps": 5,
            "gate_verdict": {"status": "PASS"},
        }

    def test_eligible_with_all_required_fields(self) -> None:
        """All required fields + gate PASS => eligible_for_review=True, no reasons."""
        artifact = self._base_artifact()
        result = evaluate_eligibility(artifact)
        assert isinstance(result, EligibilityResult)
        assert result.eligible_for_review is True
        assert result.ineligibility_reasons == []

    def test_missing_family_id(self) -> None:
        """Empty family_id => ineligible with 'missing family_id' reason."""
        artifact = self._base_artifact()
        artifact["family_id"] = ""
        result = evaluate_eligibility(artifact)
        assert result.eligible_for_review is False
        assert "missing family_id" in result.ineligibility_reasons

    def test_absent_family_id(self) -> None:
        """Absent family_id key => ineligible with 'missing family_id' reason."""
        artifact = self._base_artifact()
        del artifact["family_id"]
        result = evaluate_eligibility(artifact)
        assert result.eligible_for_review is False
        assert "missing family_id" in result.ineligibility_reasons

    def test_missing_variant_id(self) -> None:
        """Empty variant_id => ineligible with 'missing variant_id' reason."""
        artifact = self._base_artifact()
        artifact["variant_id"] = ""
        result = evaluate_eligibility(artifact)
        assert result.eligible_for_review is False
        assert "missing variant_id" in result.ineligibility_reasons

    def test_absent_variant_id(self) -> None:
        """Absent variant_id key => ineligible with 'missing variant_id' reason."""
        artifact = self._base_artifact()
        del artifact["variant_id"]
        result = evaluate_eligibility(artifact)
        assert result.eligible_for_review is False
        assert "missing variant_id" in result.ineligibility_reasons

    def test_missing_trial_count(self) -> None:
        """trial_count=None => ineligible with 'missing trial_count' reason."""
        artifact = self._base_artifact()
        artifact["trial_count"] = None
        result = evaluate_eligibility(artifact)
        assert result.eligible_for_review is False
        assert "missing trial_count" in result.ineligibility_reasons

    def test_absent_trial_count(self) -> None:
        """Absent trial_count key => ineligible with 'missing trial_count' reason."""
        artifact = self._base_artifact()
        del artifact["trial_count"]
        result = evaluate_eligibility(artifact)
        assert result.eligible_for_review is False
        assert "missing trial_count" in result.ineligibility_reasons

    def test_missing_fee_bps(self) -> None:
        """fee_bps=None => ineligible with 'missing cost assumptions' reason."""
        artifact = self._base_artifact()
        artifact["fee_bps"] = None
        result = evaluate_eligibility(artifact)
        assert result.eligible_for_review is False
        assert any("missing cost assumptions" in r for r in result.ineligibility_reasons)

    def test_missing_slippage_bps(self) -> None:
        """slippage_bps=None => ineligible with 'missing cost assumptions' reason."""
        artifact = self._base_artifact()
        artifact["slippage_bps"] = None
        result = evaluate_eligibility(artifact)
        assert result.eligible_for_review is False
        assert any("missing cost assumptions" in r for r in result.ineligibility_reasons)

    def test_missing_both_cost_fields(self) -> None:
        """Both fee_bps and slippage_bps None => single 'missing cost assumptions' reason."""
        artifact = self._base_artifact()
        artifact["fee_bps"] = None
        artifact["slippage_bps"] = None
        result = evaluate_eligibility(artifact)
        assert result.eligible_for_review is False
        cost_reasons = [r for r in result.ineligibility_reasons if "missing cost assumptions" in r]
        assert len(cost_reasons) == 1

    def test_gate_fail(self) -> None:
        """gate_status='FAIL' => ineligible with 'gate_status != PASS' reason."""
        artifact = self._base_artifact()
        artifact["gate_verdict"] = {"status": "FAIL"}
        result = evaluate_eligibility(artifact)
        assert result.eligible_for_review is False
        assert any("gate_status != PASS" in r for r in result.ineligibility_reasons)

    def test_gate_missing(self) -> None:
        """Absent gate_verdict => ineligible with 'gate_status != PASS' reason."""
        artifact = self._base_artifact()
        del artifact["gate_verdict"]
        result = evaluate_eligibility(artifact)
        assert result.eligible_for_review is False
        assert any("gate_status != PASS" in r for r in result.ineligibility_reasons)

    def test_multiple_failures_accumulate(self) -> None:
        """Multiple missing fields accumulate all reasons."""
        artifact = {
            "family_id": "",
            "variant_id": "",
            "trial_count": None,
            "fee_bps": None,
            "slippage_bps": None,
            "gate_verdict": {"status": "FAIL"},
        }
        result = evaluate_eligibility(artifact)
        assert result.eligible_for_review is False
        assert "missing family_id" in result.ineligibility_reasons
        assert "missing variant_id" in result.ineligibility_reasons
        assert "missing trial_count" in result.ineligibility_reasons
        assert any("missing cost assumptions" in r for r in result.ineligibility_reasons)


class TestIndexedExperimentEconomicsSummary:
    """Tests for IndexedExperiment.economics_summary field."""

    def test_indexed_experiment_reads_economics_summary_from_single_artifact(self) -> None:
        """Indexing an artifact with economics_summary populates IndexedExperiment.economics_summary."""
        with tempfile.TemporaryDirectory() as tmpdir:
            artifact_path = Path(tmpdir) / "experiment_result.json"
            artifact_data = {
                "experiment_name": "single-econ-test",
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
                "gate_verdict": {"status": "PASS", "reasons": [], "checked": True},
                "fee_bps": 10.0,
                "slippage_bps": 3.0,
                "economics_summary": {
                    "cost_side_count": 5,
                    "entry_count": 2,
                    "exit_count": 2,
                    "flip_count": 1,
                    "fee_bps": 10.0,
                    "slippage_bps": 3.0,
                    "assumed_total_cost_bps": 65.0,
                },
            }
            artifact_path.write_text(json.dumps(artifact_data), encoding="utf-8")
            indexed = index_experiment_artifacts([artifact_path])
            assert len(indexed) == 1
            assert indexed[0].economics_summary is not None
            es = indexed[0].economics_summary
            assert es["cost_side_count"] == 5
            assert es["entry_count"] == 2
            assert es["exit_count"] == 2
            assert es["flip_count"] == 1

    def test_indexed_experiment_economics_summary_missing_from_legacy_artifact(self) -> None:
        """Legacy artifact without economics_summary does not break indexing."""
        with tempfile.TemporaryDirectory() as tmpdir:
            legacy_path = Path(tmpdir) / "experiment_result.json"
            legacy_data = {
                "experiment_name": "legacy-no-econ",
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
                # Note: no economics_summary field
            }
            legacy_path.write_text(json.dumps(legacy_data), encoding="utf-8")
            indexed = index_experiment_artifacts([legacy_path])
            assert len(indexed) == 1
            assert indexed[0].experiment_name == "legacy-no-econ"
            # economics_summary should be None for legacy artifact
            assert indexed[0].economics_summary is None
            # gate_status should be None since gate_verdict was None
            assert indexed[0].gate_status is None
