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

    def test_walkforward_result_includes_gate_verdict(self) -> None:
        """walkforward_result.json includes gate_verdict field."""
        import json

        with tempfile.TemporaryDirectory() as tmpdir:
            out = Path(tmpdir) / "wf_experiment"
            spec = ExperimentSpec(
                experiment_name="btc-wf-gate",
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
            wf_json_path = out / "walkforward_result.json"
            data = json.loads(wf_json_path.read_text())
            assert "gate_verdict" in data
            assert data["gate_verdict"] is not None
            assert "status" in data["gate_verdict"]
            assert "reasons" in data["gate_verdict"]
            assert "checked" in data["gate_verdict"]


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

    def test_walkforward_result_contains_cost_fields(self) -> None:
        """WalkForwardExperimentResult.to_dict() includes fee_bps and slippage_bps."""
        result = WalkForwardExperimentResult(
            experiment_name="wf-cost-test",
            split_count=1,
            splits=[],
            total_bar_count=100,
            total_signal_count=5,
            fee_bps=10.0,
            slippage_bps=3.0,
        )
        d = result.to_dict()
        assert d["fee_bps"] == 10.0
        assert d["slippage_bps"] == 3.0


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

    def test_walkforward_result_economics_summary_in_artifact(self) -> None:
        """run_walkforward_experiment writes economics_summary to walkforward_result.json."""
        with tempfile.TemporaryDirectory() as tmpdir:
            out = Path(tmpdir) / "wf_econ"
            spec = ExperimentSpec(
                experiment_name="wf-econ-test",
                strategy_name="ThresholdStrategy",
                strategy_params={"threshold": 16500.0, "symbol": "BTCUSDT"},
                fixture_name="BTCUSDT_8h",
                fee_bps=10.0,
                slippage_bps=3.0,
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
            artifact_path = out / "walkforward_result.json"
            assert artifact_path.exists()
            import json
            data = json.loads(artifact_path.read_text())
            assert "economics_summary" in data
            # economics_summary may be None if no splits had economics data
            if data["economics_summary"] is not None:
                es = data["economics_summary"]
                assert isinstance(es["cost_side_count"], int)
                assert isinstance(es["entry_count"], int)
                assert isinstance(es["exit_count"], int)
                assert isinstance(es["flip_count"], int)

    def test_walkforward_split_result_economics_summary_field_exists(self) -> None:
        """WalkForwardSplitResult has economics_summary field."""
        from quantbot.experiment.result import EconomicsSummary, WalkForwardSplitResult

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
            economics_summary=EconomicsSummary(
                cost_side_count=2,
                entry_count=1,
                exit_count=1,
                flip_count=0,
                fee_bps=10.0,
                slippage_bps=3.0,
                assumed_total_cost_bps=26.0,
            ),
        )
        assert split.economics_summary is not None
        assert split.economics_summary.cost_side_count == 2
        assert split.economics_summary.entry_count == 1
        assert split.economics_summary.exit_count == 1


class TestAggregateEconomicsSummary:
    """Tests for WalkForwardExperimentResult.aggregate_economics_summary."""

    def test_aggregate_economics_sums_counts(self) -> None:
        """aggregate_economics_summary sums entry_count, exit_count, flip_count across splits."""
        from quantbot.experiment.result import EconomicsSummary, WalkForwardExperimentResult, WalkForwardSplitResult

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
            economics_summary=EconomicsSummary(
                cost_side_count=3,
                entry_count=1,
                exit_count=1,
                flip_count=1,
                fee_bps=10.0,
                slippage_bps=3.0,
                assumed_total_cost_bps=39.0,
            ),
        )
        split2 = WalkForwardSplitResult(
            split_index=1,
            train_bar_count=100,
            test_bar_count=50,
            signal_count=3,
            long_count=2,
            short_count=1,
            flat_count=0,
            receipt_path=None,
            artifact_path=None,
            economics_summary=EconomicsSummary(
                cost_side_count=2,
                entry_count=1,
                exit_count=1,
                flip_count=0,
                fee_bps=10.0,
                slippage_bps=3.0,
                assumed_total_cost_bps=26.0,
            ),
        )
        wf_result = WalkForwardExperimentResult(
            experiment_name="test-agg",
            split_count=2,
            splits=[split1, split2],
            total_bar_count=100,
            total_signal_count=8,
        )
        aggregated = wf_result.aggregate_economics_summary()
        assert aggregated is not None
        assert aggregated.cost_side_count == 5  # 3 + 2
        assert aggregated.entry_count == 2  # 1 + 1
        assert aggregated.exit_count == 2  # 1 + 1
        assert aggregated.flip_count == 1  # 1 + 0

    def test_aggregate_recomputes_assumed_total_cost(self) -> None:
        """aggregate_economics_summary recomputes assumed_total_cost from summed values."""
        from quantbot.experiment.result import EconomicsSummary, WalkForwardExperimentResult, WalkForwardSplitResult

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
            economics_summary=EconomicsSummary(
                cost_side_count=3,
                entry_count=1,
                exit_count=1,
                flip_count=1,
                fee_bps=10.0,
                slippage_bps=3.0,
                assumed_total_cost_bps=39.0,  # 3 * 13
            ),
        )
        split2 = WalkForwardSplitResult(
            split_index=1,
            train_bar_count=100,
            test_bar_count=50,
            signal_count=3,
            long_count=2,
            short_count=1,
            flat_count=0,
            receipt_path=None,
            artifact_path=None,
            economics_summary=EconomicsSummary(
                cost_side_count=2,
                entry_count=1,
                exit_count=1,
                flip_count=0,
                fee_bps=10.0,
                slippage_bps=3.0,
                assumed_total_cost_bps=26.0,  # 2 * 13
            ),
        )
        wf_result = WalkForwardExperimentResult(
            experiment_name="test-agg-cost",
            split_count=2,
            splits=[split1, split2],
            total_bar_count=100,
            total_signal_count=8,
        )
        aggregated = wf_result.aggregate_economics_summary()
        assert aggregated is not None
        # cost_side_count = 3 + 2 = 5, fee + slippage = 10 + 3 = 13
        # assumed_total = 5 * 13 = 65
        assert aggregated.assumed_total_cost_bps == 65.0

    def test_aggregate_returns_none_when_no_splits_have_economics(self) -> None:
        """aggregate_economics_summary returns None if no splits have economics data."""
        from quantbot.experiment.result import WalkForwardExperimentResult, WalkForwardSplitResult

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
            economics_summary=None,
        )
        wf_result = WalkForwardExperimentResult(
            experiment_name="test-no-econ",
            split_count=1,
            splits=[split1],
            total_bar_count=50,
            total_signal_count=5,
        )
        aggregated = wf_result.aggregate_economics_summary()
        assert aggregated is None
