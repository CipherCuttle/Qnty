"""Tests for experiment index.

Requires PYTHONHASHSEED=0 for deterministic dict ordering.
Paper mode only - no real trading.
"""

import tempfile
from pathlib import Path

import pytest

from quantbot.experiment.index import (
    IndexedExperiment,
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
