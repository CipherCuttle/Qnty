"""Tests for walk-forward experiment runner.

Requires PYTHONHASHSEED=0 for deterministic dict ordering.
Paper mode only - no real trading.
"""

import tempfile
from pathlib import Path

import pytest

from quantbot.experiment.result import WalkForwardExperimentResult, WalkForwardSplitResult
from quantbot.experiment.spec import ExperimentSpec
from quantbot.experiment.walkforward_runner import run_walkforward_experiment


FIXTURE_DIR = Path(__file__).parent / "fixtures"
BTCUSDT_MANIFEST_PATH = FIXTURE_DIR / "BTCUSDT_manifest.json"
BTCUSDT_CSV_PATH = FIXTURE_DIR / "BTCUSDT_8h.csv"


class TestRunWalkForwardExperiment:
    """End-to-end tests for run_walkforward_experiment on BTCUSDT 8h fixture."""

    def test_returns_valid_walkforward_experiment_result(self) -> None:
        """run_walkforward_experiment returns WalkForwardExperimentResult."""
        with tempfile.TemporaryDirectory() as tmpdir:
            out = Path(tmpdir) / "wf_experiment"
            spec = ExperimentSpec(
                experiment_name="btc-wf-test",
                strategy_name="ThresholdStrategy",
                strategy_params={"threshold": 16500.0, "symbol": "BTCUSDT"},
                fixture_name="BTCUSDT_8h",
                description="Walk-forward test on BTCUSDT 8h",
                notes="Toy strategy - no profitability claims.",
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
            assert isinstance(result, WalkForwardExperimentResult)
            assert result.experiment_name == "btc-wf-test"

    def test_split_count_is_correct(self) -> None:
        """split_count matches number of splits produced."""
        with tempfile.TemporaryDirectory() as tmpdir:
            out = Path(tmpdir) / "wf_experiment"
            spec = ExperimentSpec(
                experiment_name="btc-wf-count",
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
            # BTCUSDT_8h has 2190 bars
            # With train=100, test=50, step=50: (2190 - 100) // 50 = 41 splits
            assert result.split_count == len(result.splits)
            assert result.split_count > 0

    def test_total_bar_count_equals_sum_of_test_bar_counts(self) -> None:
        """total_bar_count equals sum of per-split test_bar_count."""
        with tempfile.TemporaryDirectory() as tmpdir:
            out = Path(tmpdir) / "wf_experiment"
            spec = ExperimentSpec(
                experiment_name="btc-wf-bars",
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
            sum_of_test_bars = sum(s.test_bar_count for s in result.splits)
            assert result.total_bar_count == sum_of_test_bars

    def test_determinism_receipt_digests_identical(self) -> None:
        """Two identical runs produce identical receipt digests."""
        with tempfile.TemporaryDirectory() as tmpdir:
            out1 = Path(tmpdir) / "run1"
            out2 = Path(tmpdir) / "run2"
            spec = ExperimentSpec(
                experiment_name="btc-wf-det",
                strategy_name="ThresholdStrategy",
                strategy_params={"threshold": 16500.0, "symbol": "BTCUSDT"},
                fixture_name="BTCUSDT_8h",
            )
            result1 = run_walkforward_experiment(
                spec=spec,
                manifest_path=BTCUSDT_MANIFEST_PATH,
                csv_path=BTCUSDT_CSV_PATH,
                output_dir=out1,
                train_size=100,
                test_size=50,
                step_size=50,
            )
            result2 = run_walkforward_experiment(
                spec=spec,
                manifest_path=BTCUSDT_MANIFEST_PATH,
                csv_path=BTCUSDT_CSV_PATH,
                output_dir=out2,
                train_size=100,
                test_size=50,
                step_size=50,
            )
            # Compare receipt digests from each split
            for split1, split2 in zip(result1.splits, result2.splits):
                if split1.receipt_path and split2.receipt_path:
                    digest1 = Path(split1.receipt_path).read_text()
                    digest2 = Path(split2.receipt_path).read_text()
                    assert digest1 == digest2

    def test_walkforward_result_json_byte_identical(self) -> None:
        """walkforward_result.json is byte-identical across two runs."""
        with tempfile.TemporaryDirectory() as tmpdir:
            out1 = Path(tmpdir) / "run1"
            out2 = Path(tmpdir) / "run2"
            spec = ExperimentSpec(
                experiment_name="btc-wf-json-det",
                strategy_name="ThresholdStrategy",
                strategy_params={"threshold": 16500.0, "symbol": "BTCUSDT"},
                fixture_name="BTCUSDT_8h",
            )
            run_walkforward_experiment(
                spec=spec,
                manifest_path=BTCUSDT_MANIFEST_PATH,
                csv_path=BTCUSDT_CSV_PATH,
                output_dir=out1,
                train_size=100,
                test_size=50,
                step_size=50,
            )
            run_walkforward_experiment(
                spec=spec,
                manifest_path=BTCUSDT_MANIFEST_PATH,
                csv_path=BTCUSDT_CSV_PATH,
                output_dir=out2,
                train_size=100,
                test_size=50,
                step_size=50,
            )

            json1_path = out1 / "walkforward_result.json"
            json2_path = out2 / "walkforward_result.json"

            assert json1_path.exists(), "walkforward_result.json not written"
            assert json2_path.exists(), "walkforward_result.json not written"

            json1_bytes = json1_path.read_bytes()
            json2_bytes = json2_path.read_bytes()
            assert json1_bytes == json2_bytes, (
                "walkforward_result.json differs between runs"
            )

            # Also verify receipts are identical
            for idx in range(41):
                receipt1 = out1 / f"split_{idx:03d}" / "receipt.json"
                receipt2 = out2 / f"split_{idx:03d}" / "receipt.json"
                if receipt1.exists() and receipt2.exists():
                    assert receipt1.read_bytes() == receipt2.read_bytes()

    def test_split_directories_named_deterministically(self) -> None:
        """Split directories are named split_000, split_001, etc."""
        with tempfile.TemporaryDirectory() as tmpdir:
            out = Path(tmpdir) / "wf_experiment"
            spec = ExperimentSpec(
                experiment_name="btc-wf-names",
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
            for idx, split_result in enumerate(result.splits):
                assert split_result.split_index == idx
                expected_dir = out / f"split_{idx:03d}"
                assert expected_dir.exists()


class TestWalkForwardExperimentResult:
    """Tests for WalkForwardExperimentResult dataclass."""

    def test_empty_result(self) -> None:
        """Empty result has correct structure."""
        result = WalkForwardExperimentResult(
            experiment_name="empty-test",
            split_count=0,
            splits=[],
            total_bar_count=0,
            total_signal_count=0,
        )
        assert result.split_count == 0
        assert result.total_bar_count == 0
        assert result.total_signal_count == 0
        assert result.splits == []


class TestWalkForwardSplitResult:
    """Tests for WalkForwardSplitResult dataclass."""

    def test_split_result_structure(self) -> None:
        """Split result has correct structure."""
        split = WalkForwardSplitResult(
            split_index=0,
            train_bar_count=100,
            test_bar_count=50,
            signal_count=5,
            long_count=3,
            short_count=2,
            flat_count=0,
            receipt_path="/path/to/receipt.json",
            artifact_path="/path/to/artifact.json",
        )
        assert split.split_index == 0
        assert split.train_bar_count == 100
        assert split.test_bar_count == 50
        assert split.signal_count == 5
        assert split.long_count == 3
        assert split.short_count == 2
        assert split.flat_count == 0
        assert split.receipt_path == "/path/to/receipt.json"
        assert split.artifact_path == "/path/to/artifact.json"
