"""Tests for quantbot.experiment module.

Requires PYTHONHASHSEED=0 for deterministic dict ordering.
Paper mode only - no real trading.
"""

import json
import tempfile
from pathlib import Path

import pytest

from quantbot.experiment.result import ExperimentResult
from quantbot.experiment.runner import run_experiment
from quantbot.experiment.spec import ExperimentSpec


FIXTURE_DIR = Path(__file__).parent / "fixtures"
BTCUSDT_MANIFEST_PATH = FIXTURE_DIR / "BTCUSDT_manifest.json"
BTCUSDT_CSV_PATH = FIXTURE_DIR / "BTCUSDT_8h.csv"


class TestExperimentSpec:
    """Tests for ExperimentSpec dataclass."""

    def test_spec_to_dict(self) -> None:
        """ExperimentSpec serializes to dict correctly."""
        spec = ExperimentSpec(
            experiment_name="test-exp",
            strategy_name="ThresholdStrategy",
            strategy_params={"threshold": 16500.0, "symbol": "BTCUSDT"},
            fixture_name="BTCUSDT_8h",
            description="Threshold experiment on BTCUSDT 8h",
            notes="Toy strategy - no profitability claims.",
        )
        d = spec.to_dict()
        assert d["experiment_name"] == "test-exp"
        assert d["strategy_name"] == "ThresholdStrategy"
        assert d["strategy_params"]["threshold"] == 16500.0
        assert d["fixture_name"] == "BTCUSDT_8h"


class TestExperimentResult:
    """Tests for ExperimentResult dataclass."""

    def test_result_to_dict(self) -> None:
        """ExperimentResult serializes to dict correctly."""
        spec = ExperimentSpec(
            experiment_name="test-exp",
            strategy_name="ThresholdStrategy",
            strategy_params={"threshold": 16500.0},
            fixture_name="BTCUSDT_8h",
        )
        result = ExperimentResult(
            spec=spec,
            result_path=Path("/tmp/result.json"),
            receipt_path=Path("/tmp/receipt.json"),
            receipt_digest="abc123",
            bar_count=2190,
            signal_count=5,
            first_timestamp="2023-01-01T00:00:00+00:00",
            last_timestamp="2024-12-30T16:00:00+00:00",
            long_count=3,
            short_count=2,
            flat_count=0,
            engine_version="0.1.0",
        )
        d = result.to_dict()
        assert d["bar_count"] == 2190
        assert d["signal_count"] == 5
        assert d["long_count"] == 3
        assert d["short_count"] == 2
        assert d["experiment_name"] == "test-exp"
        assert d["strategy_name"] == "ThresholdStrategy"
        assert d["strategy_params"]["threshold"] == 16500.0
        assert d["fixture_name"] == "BTCUSDT_8h"
        assert d["engine_version"] == "0.1.0"
        assert d["receipt_digest"] == "abc123"


class TestRunExperiment:
    """End-to-end tests for run_experiment on BTCUSDT 8h fixture."""

    def test_run_experiment_produces_result(self) -> None:
        """run_experiment on BTCUSDT 8h produces ExperimentResult."""
        with tempfile.TemporaryDirectory() as tmpdir:
            out = Path(tmpdir) / "exp_run"
            spec = ExperimentSpec(
                experiment_name="btc-threshold-16500",
                strategy_name="ThresholdStrategy",
                strategy_params={"threshold": 16500.0, "symbol": "BTCUSDT"},
                fixture_name="BTCUSDT_8h",
                description="Threshold 16500 on BTCUSDT 8h",
                notes="Toy strategy - no profitability claims.",
            )
            result = run_experiment(
                spec=spec,
                manifest_path=BTCUSDT_MANIFEST_PATH,
                csv_path=BTCUSDT_CSV_PATH,
                output_dir=out,
            )
            assert isinstance(result, ExperimentResult)
            assert result.spec.experiment_name == "btc-threshold-16500"
            assert result.bar_count == 2190
            assert result.signal_count >= 0
            assert result.receipt_path.exists()
            assert len(result.receipt_digest) == 64

    def test_run_experiment_receipt_json_valid(self) -> None:
        """Receipt JSON written by run_experiment is valid and well-formed."""
        with tempfile.TemporaryDirectory() as tmpdir:
            out = Path(tmpdir) / "exp_run"
            spec = ExperimentSpec(
                experiment_name="btc-threshold-test",
                strategy_name="ThresholdStrategy",
                strategy_params={"threshold": 16500.0},
                fixture_name="BTCUSDT_8h",
            )
            result = run_experiment(
                spec=spec,
                manifest_path=BTCUSDT_MANIFEST_PATH,
                csv_path=BTCUSDT_CSV_PATH,
                output_dir=out,
            )
            receipt_data = json.loads(result.receipt_path.read_text())
            assert receipt_data["bar_count"] == 2190
            assert receipt_data["signal_count"] >= 0
            assert receipt_data["first_timestamp"] == "2023-01-01 00:00:00+00:00"
            assert receipt_data["last_timestamp"] == "2024-12-30 16:00:00+00:00"

    def test_run_experiment_deterministic(self) -> None:
        """Two identical experiment runs produce same receipt digest."""
        with tempfile.TemporaryDirectory() as tmpdir:
            out1 = Path(tmpdir) / "run1"
            out2 = Path(tmpdir) / "run2"
            spec = ExperimentSpec(
                experiment_name="btc-threshold-det",
                strategy_name="ThresholdStrategy",
                strategy_params={"threshold": 16500.0},
                fixture_name="BTCUSDT_8h",
            )
            result1 = run_experiment(
                spec=spec,
                manifest_path=BTCUSDT_MANIFEST_PATH,
                csv_path=BTCUSDT_CSV_PATH,
                output_dir=out1,
            )
            result2 = run_experiment(
                spec=spec,
                manifest_path=BTCUSDT_MANIFEST_PATH,
                csv_path=BTCUSDT_CSV_PATH,
                output_dir=out2,
            )
            # Receipts must be byte-identical
            assert result1.receipt_path.read_bytes() == result2.receipt_path.read_bytes()
            assert result1.receipt_digest == result2.receipt_digest

    def test_run_experiment_signal_counts(self) -> None:
        """run_experiment reports long/short/flat signal counts."""
        with tempfile.TemporaryDirectory() as tmpdir:
            out = Path(tmpdir) / "exp_run"
            spec = ExperimentSpec(
                experiment_name="btc-signal-counts",
                strategy_name="ThresholdStrategy",
                strategy_params={"threshold": 16500.0},
                fixture_name="BTCUSDT_8h",
            )
            result = run_experiment(
                spec=spec,
                manifest_path=BTCUSDT_MANIFEST_PATH,
                csv_path=BTCUSDT_CSV_PATH,
                output_dir=out,
            )
            # long + short + flat should equal signal_count
            total = result.long_count + result.short_count + result.flat_count
            assert total == result.signal_count
            # All counts should be non-negative
            assert result.long_count >= 0
            assert result.short_count >= 0
            assert result.flat_count >= 0

    def test_run_experiment_produces_result_artifact(self) -> None:
        """run_experiment writes experiment_result.json with correct fields."""
        with tempfile.TemporaryDirectory() as tmpdir:
            out = Path(tmpdir) / "exp_run"
            spec = ExperimentSpec(
                experiment_name="btc-result-artifact",
                strategy_name="ThresholdStrategy",
                strategy_params={"threshold": 16500.0},
                fixture_name="BTCUSDT_8h",
            )
            result = run_experiment(
                spec=spec,
                manifest_path=BTCUSDT_MANIFEST_PATH,
                csv_path=BTCUSDT_CSV_PATH,
                output_dir=out,
            )
            artifact_path = out / "experiment_result.json"
            assert artifact_path.exists(), "experiment_result.json not found"

            data = json.loads(artifact_path.read_text())
            assert data["experiment_name"] == "btc-result-artifact"
            assert data["strategy_name"] == "ThresholdStrategy"
            assert data["strategy_params"]["threshold"] == 16500.0
            assert data["fixture_name"] == "BTCUSDT_8h"
            assert data["engine_version"] == "0.1.0"
            assert data["receipt_digest"] == result.receipt_digest
            assert data["bar_count"] == 2190
            assert data["signal_count"] >= 0
            assert data["first_timestamp"] == "2023-01-01 00:00:00+00:00"
            assert data["last_timestamp"] == "2024-12-30 16:00:00+00:00"
            assert "long_count" in data
            assert "short_count" in data
            assert "flat_count" in data
            assert "gate_verdict" in data
            assert "receipt_path" not in data

    def test_run_experiment_result_artifact_deterministic(self) -> None:
        """Two identical experiment runs produce byte-identical experiment_result.json."""
        with tempfile.TemporaryDirectory() as tmpdir:
            out1 = Path(tmpdir) / "run1"
            out2 = Path(tmpdir) / "run2"
            spec = ExperimentSpec(
                experiment_name="btc-deterministic-artifact",
                strategy_name="ThresholdStrategy",
                strategy_params={"threshold": 16500.0},
                fixture_name="BTCUSDT_8h",
            )
            run_experiment(
                spec=spec,
                manifest_path=BTCUSDT_MANIFEST_PATH,
                csv_path=BTCUSDT_CSV_PATH,
                output_dir=out1,
            )
            run_experiment(
                spec=spec,
                manifest_path=BTCUSDT_MANIFEST_PATH,
                csv_path=BTCUSDT_CSV_PATH,
                output_dir=out2,
            )
            artifact1 = (out1 / "experiment_result.json").read_bytes()
            artifact2 = (out2 / "experiment_result.json").read_bytes()
            assert artifact1 == artifact2, "experiment_result.json not byte-identical across runs"
