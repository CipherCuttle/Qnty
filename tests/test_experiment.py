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

    def test_spec_trial_family_fields(self) -> None:
        """ExperimentSpec includes family_id, variant_id, trial_count."""
        spec = ExperimentSpec(
            experiment_name="test-exp",
            strategy_name="ThresholdStrategy",
            family_id="my-family",
            variant_id="variant-v1",
            trial_count=5,
        )
        d = spec.to_dict()
        assert d["family_id"] == "my-family"
        assert d["variant_id"] == "variant-v1"
        assert d["trial_count"] == 5

    def test_spec_trial_count_defaults_to_one(self) -> None:
        """ExperimentSpec defaults trial_count to 1."""
        spec = ExperimentSpec(
            experiment_name="test-exp",
            strategy_name="ThresholdStrategy",
        )
        assert spec.trial_count == 1

    def test_spec_rejects_trial_count_zero(self) -> None:
        """ExperimentSpec raises ValueError when trial_count < 1."""
        with pytest.raises(ValueError, match="trial_count must be >= 1"):
            ExperimentSpec(
                experiment_name="test-exp",
                strategy_name="ThresholdStrategy",
                trial_count=0,
            )

    def test_spec_rejects_negative_trial_count(self) -> None:
        """ExperimentSpec raises ValueError for negative trial_count."""
        with pytest.raises(ValueError, match="trial_count must be >= 1"):
            ExperimentSpec(
                experiment_name="test-exp",
                strategy_name="ThresholdStrategy",
                trial_count=-1,
            )
    
        def test_spec_accepts_non_negative_fee_and_slippage(self) -> None:
            """ExperimentSpec accepts non-negative fee_bps and slippage_bps."""
            spec = ExperimentSpec(
                experiment_name="test-exp",
                strategy_name="ThresholdStrategy",
                fee_bps=5.0,
                slippage_bps=2.0,
            )
            assert spec.fee_bps == 5.0
            assert spec.slippage_bps == 2.0
    
        def test_spec_rejects_negative_fee_bps(self) -> None:
            """ExperimentSpec raises ValueError for negative fee_bps."""
            with pytest.raises(ValueError, match="fee_bps must be non-negative"):
                ExperimentSpec(
                    experiment_name="test-exp",
                    strategy_name="ThresholdStrategy",
                    fee_bps=-1.0,
                )
    
        def test_spec_rejects_negative_slippage_bps(self) -> None:
            """ExperimentSpec raises ValueError for negative slippage_bps."""
            with pytest.raises(ValueError, match="slippage_bps must be non-negative"):
                ExperimentSpec(
                    experiment_name="test-exp",
                    strategy_name="ThresholdStrategy",
                    slippage_bps=-1.0,
                )
    
        def test_spec_rejects_negative_both(self) -> None:
            """ExperimentSpec raises ValueError when both fee_bps and slippage_bps are negative."""
            with pytest.raises(ValueError):
                ExperimentSpec(
                    experiment_name="test-exp",
                    strategy_name="ThresholdStrategy",
                    fee_bps=-1.0,
                    slippage_bps=-2.0,
                )


class TestExperimentResult:
    """Tests for ExperimentResult dataclass."""

    def test_result_to_dict(self) -> None:
        """ExperimentResult serializes to dict correctly."""
        spec = ExperimentSpec(
            experiment_name="test-exp",
            strategy_name="ThresholdStrategy",
            strategy_params={"threshold": 16500.0},
            fixture_name="BTCUSDT_8h",
            family_id="family-1",
            variant_id="var-a",
            trial_count=3,
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
        assert d["family_id"] == "family-1"
        assert d["variant_id"] == "var-a"
        assert d["trial_count"] == 3

    def test_experiment_result_contains_cost_fields(self) -> None:
        """ExperimentResult.to_dict() includes fee_bps and slippage_bps."""
        spec = ExperimentSpec(
            experiment_name="test-exp",
            strategy_name="ThresholdStrategy",
            fee_bps=10.0,
            slippage_bps=3.0,
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
            long_count=3,
            short_count=2,
            flat_count=0,
            engine_version="0.1.0",
            fee_bps=10.0,
            slippage_bps=3.0,
        )
        d = result.to_dict()
        assert d["fee_bps"] == 10.0
        assert d["slippage_bps"] == 3.0


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
            # Verify new trial-family fields are present
            assert "family_id" in data
            assert "variant_id" in data
            assert "trial_count" in data
            # Defaults are empty strings for ids, 1 for trial_count (CLI layer fills experiment_name)
            assert data["family_id"] == ""
            assert data["variant_id"] == ""
            assert data["trial_count"] == 1

    def test_run_experiment_with_trial_family_metadata(self) -> None:
        """run_experiment writes explicit family_id, variant_id, trial_count to artifact."""
        with tempfile.TemporaryDirectory() as tmpdir:
            out = Path(tmpdir) / "exp_run"
            spec = ExperimentSpec(
                experiment_name="btc-trial-family",
                strategy_name="ThresholdStrategy",
                strategy_params={"threshold": 16500.0},
                fixture_name="BTCUSDT_8h",
                family_id="threshold-family",
                variant_id="threshold_16500_v7",
                trial_count=4,
            )
            result = run_experiment(
                spec=spec,
                manifest_path=BTCUSDT_MANIFEST_PATH,
                csv_path=BTCUSDT_CSV_PATH,
                output_dir=out,
            )
            artifact_path = out / "experiment_result.json"
            assert artifact_path.exists()
            data = json.loads(artifact_path.read_text())
            assert data["family_id"] == "threshold-family"
            assert data["variant_id"] == "threshold_16500_v7"
            assert data["trial_count"] == 4

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
            assert artifact1 == artifact2

    def test_run_experiment_economics_summary_in_artifact(self) -> None:
        """run_experiment writes economics_summary to experiment_result.json."""
        with tempfile.TemporaryDirectory() as tmpdir:
            out = Path(tmpdir) / "exp_run"
            spec = ExperimentSpec(
                experiment_name="btc-econ-test",
                strategy_name="ThresholdStrategy",
                strategy_params={"threshold": 16500.0, "symbol": "BTCUSDT"},
                fixture_name="BTCUSDT_8h",
                fee_bps=10.0,
                slippage_bps=3.0,
            )
            result = run_experiment(
                spec=spec,
                manifest_path=BTCUSDT_MANIFEST_PATH,
                csv_path=BTCUSDT_CSV_PATH,
                output_dir=out,
            )
            artifact_path = out / "experiment_result.json"
            assert artifact_path.exists()
            data = json.loads(artifact_path.read_text())
            assert "economics_summary" in data
            assert data["economics_summary"] is not None
            # Verify fields are correct types
            es = data["economics_summary"]
            assert isinstance(es["cost_side_count"], int)
            assert isinstance(es["entry_count"], int)
            assert isinstance(es["exit_count"], int)
            assert isinstance(es["flip_count"], int)
            assert isinstance(es["fee_bps"], (int, float))
            assert isinstance(es["slippage_bps"], (int, float))
            assert isinstance(es["assumed_total_cost_bps"], (int, float))


class TestEconomicsSummary:
    """Tests for EconomicsSummary dataclass."""

    def test_economics_summary_to_dict(self) -> None:
        """EconomicsSummary serializes to dict correctly."""
        from quantbot.experiment.result import EconomicsSummary

        summary = EconomicsSummary(
            cost_side_count=5,
            entry_count=2,
            exit_count=2,
            flip_count=1,
            fee_bps=10.0,
            slippage_bps=3.0,
            assumed_total_cost_bps=65.0,
        )
        d = summary.to_dict()
        assert d["cost_side_count"] == 5
        assert d["entry_count"] == 2
        assert d["exit_count"] == 2
        assert d["flip_count"] == 1
        assert d["fee_bps"] == 10.0
        assert d["slippage_bps"] == 3.0
        assert d["assumed_total_cost_bps"] == 65.0

    def test_economics_summary_default_values(self) -> None:
        """EconomicsSummary defaults to zeros."""
        from quantbot.experiment.result import EconomicsSummary

        summary = EconomicsSummary()
        assert summary.cost_side_count == 0
        assert summary.entry_count == 0
        assert summary.exit_count == 0
        assert summary.flip_count == 0
        assert summary.fee_bps == 0.0
        assert summary.slippage_bps == 0.0
        assert summary.assumed_total_cost_bps == 0.0


class TestComputeEconomicsSummary:
    """Tests for _compute_economics_summary event accounting logic."""

    def test_flat_to_long_is_entry(self) -> None:
        """Signal from flat to long counts as entry."""
        from quantbot.experiment.runner import _compute_economics_summary

        class MockSignal:
            def __init__(self, direction):
                self.direction = direction

        class MockStrategy:
            def __init__(self, signals):
                self._signals = signals
                self._idx = 0

            def on_bar(self, bar):
                if self._idx < len(self._signals):
                    sig = self._signals[self._idx]
                    self._idx += 1
                    return sig
                return None

        bars = [{"timestamp": f"2024-01-{i+1:02d}"} for i in range(5)]
        # flat -> long = 1 entry, position stays open (no exit)
        signals = [MockSignal("flat"), MockSignal("long"), MockSignal("long"), MockSignal("long"), MockSignal("long")]
        strategy = MockStrategy(signals)
        result = _compute_economics_summary(strategy, bars, 10.0, 3.0)
        assert result.entry_count == 1
        assert result.exit_count == 0
        assert result.flip_count == 0
        assert result.cost_side_count == 1

    def test_flat_to_short_is_entry(self) -> None:
        """Signal from flat to short counts as entry."""
        from quantbot.experiment.runner import _compute_economics_summary

        class MockSignal:
            def __init__(self, direction):
                self.direction = direction

        class MockStrategy:
            def __init__(self, signals):
                self._signals = signals
                self._idx = 0

            def on_bar(self, bar):
                if self._idx < len(self._signals):
                    sig = self._signals[self._idx]
                    self._idx += 1
                    return sig
                return None

        bars = [{"timestamp": f"2024-01-{i+1:02d}"} for i in range(5)]
        # flat -> short = 1 entry, position stays open
        signals = [MockSignal("flat"), MockSignal("short"), MockSignal("short"), MockSignal("short"), MockSignal("short")]
        strategy = MockStrategy(signals)
        result = _compute_economics_summary(strategy, bars, 10.0, 3.0)
        assert result.entry_count == 1
        assert result.exit_count == 0
        assert result.flip_count == 0
        assert result.cost_side_count == 1

    def test_long_to_flat_is_exit(self) -> None:
        """Signal from long to flat counts as exit."""
        from quantbot.experiment.runner import _compute_economics_summary

        class MockSignal:
            def __init__(self, direction):
                self.direction = direction

        class MockStrategy:
            def __init__(self, signals):
                self._signals = signals
                self._idx = 0

            def on_bar(self, bar):
                if self._idx < len(self._signals):
                    sig = self._signals[self._idx]
                    self._idx += 1
                    return sig
                return None

        bars = [{"timestamp": f"2024-01-{i+1:02d}"} for i in range(5)]
        # long -> flat = 1 entry (first long from flat) + 1 exit (last flat) = 2 cost sides
        signals = [MockSignal("long"), MockSignal("long"), MockSignal("long"), MockSignal("long"), MockSignal("flat")]
        strategy = MockStrategy(signals)
        result = _compute_economics_summary(strategy, bars, 10.0, 3.0)
        assert result.entry_count == 1  # first long from flat
        assert result.exit_count == 1  # flat closes position
        assert result.flip_count == 0
        assert result.cost_side_count == 2

    def test_short_to_flat_is_exit(self) -> None:
        """Signal from short to flat counts as exit."""
        from quantbot.experiment.runner import _compute_economics_summary

        class MockSignal:
            def __init__(self, direction):
                self.direction = direction

        class MockStrategy:
            def __init__(self, signals):
                self._signals = signals
                self._idx = 0

            def on_bar(self, bar):
                if self._idx < len(self._signals):
                    sig = self._signals[self._idx]
                    self._idx += 1
                    return sig
                return None

        bars = [{"timestamp": f"2024-01-{i+1:02d}"} for i in range(5)]
        # short -> flat = 1 entry (first short from flat) + 1 exit (last flat) = 2 cost sides
        signals = [MockSignal("short"), MockSignal("short"), MockSignal("short"), MockSignal("short"), MockSignal("flat")]
        strategy = MockStrategy(signals)
        result = _compute_economics_summary(strategy, bars, 10.0, 3.0)
        assert result.entry_count == 1  # first short from flat
        assert result.exit_count == 1  # flat closes position
        assert result.flip_count == 0
        assert result.cost_side_count == 2

    def test_long_to_short_is_flip(self) -> None:
        """Signal from long to short counts as flip (exit + entry)."""
        from quantbot.experiment.runner import _compute_economics_summary

        class MockSignal:
            def __init__(self, direction):
                self.direction = direction

        class MockStrategy:
            def __init__(self, signals):
                self._signals = signals
                self._idx = 0

            def on_bar(self, bar):
                if self._idx < len(self._signals):
                    sig = self._signals[self._idx]
                    self._idx += 1
                    return sig
                return None

        bars = [{"timestamp": f"2024-01-{i+1:02d}"} for i in range(5)]
        # long -> short = 1 entry (first long) + 1 flip (long->short) = 2 cost sides
        signals = [MockSignal("long"), MockSignal("short"), MockSignal("short"), MockSignal("short"), MockSignal("short")]
        strategy = MockStrategy(signals)
        result = _compute_economics_summary(strategy, bars, 10.0, 3.0)
        assert result.flip_count == 1  # long->short is a flip
        assert result.entry_count == 1  # first long from flat
        assert result.exit_count == 0
        assert result.cost_side_count == 2

    def test_short_to_long_is_flip(self) -> None:
        """Signal from short to long counts as flip (exit + entry)."""
        from quantbot.experiment.runner import _compute_economics_summary

        class MockSignal:
            def __init__(self, direction):
                self.direction = direction

        class MockStrategy:
            def __init__(self, signals):
                self._signals = signals
                self._idx = 0

            def on_bar(self, bar):
                if self._idx < len(self._signals):
                    sig = self._signals[self._idx]
                    self._idx += 1
                    return sig
                return None

        bars = [{"timestamp": f"2024-01-{i+1:02d}"} for i in range(5)]
        # short -> long = 1 entry (first short) + 1 flip (short->long) = 2 cost sides
        signals = [MockSignal("short"), MockSignal("long"), MockSignal("long"), MockSignal("long"), MockSignal("long")]
        strategy = MockStrategy(signals)
        result = _compute_economics_summary(strategy, bars, 10.0, 3.0)
        assert result.flip_count == 1  # short->long is a flip
        assert result.entry_count == 1  # first short from flat
        assert result.exit_count == 0
        assert result.cost_side_count == 2

    def test_cost_side_count_formula(self) -> None:
        """cost_side_count = entry_count + exit_count + flip_count."""
        from quantbot.experiment.runner import _compute_economics_summary

        class MockSignal:
            def __init__(self, direction):
                self.direction = direction

        class MockStrategy:
            def __init__(self, signals):
                self._signals = signals
                self._idx = 0

            def on_bar(self, bar):
                if self._idx < len(self._signals):
                    sig = self._signals[self._idx]
                    self._idx += 1
                    return sig
                return None

        bars = [{"timestamp": f"2024-01-{i+1:02d}"} for i in range(10)]
        # flat -> long (1 entry) -> flat (1 exit) -> short (1 entry) -> flat (1 exit) = 2 entries, 2 exits
        signals = [
            MockSignal("flat"), MockSignal("long"), MockSignal("flat"),
            MockSignal("short"), MockSignal("flat"), None, None, None, None, None
        ]
        strategy = MockStrategy(signals)
        result = _compute_economics_summary(strategy, bars, 10.0, 3.0)
        assert result.entry_count == 2
        assert result.exit_count == 2
        assert result.cost_side_count == result.entry_count + result.exit_count + result.flip_count

    def test_assumed_total_cost_bps_formula(self) -> None:
        """assumed_total_cost_bps = cost_side_count * (fee_bps + slippage_bps)."""
        from quantbot.experiment.runner import _compute_economics_summary

        class MockSignal:
            def __init__(self, direction):
                self.direction = direction

        class MockStrategy:
            def __init__(self, signals):
                self._signals = signals
                self._idx = 0

            def on_bar(self, bar):
                if self._idx < len(self._signals):
                    sig = self._signals[self._idx]
                    self._idx += 1
                    return sig
                return None

        bars = [{"timestamp": f"2024-01-{i+1:02d}"} for i in range(5)]
        signals = [MockSignal("flat"), MockSignal("long"), None, None, None]
        strategy = MockStrategy(signals)
        fee_bps = 10.0
        slippage_bps = 3.0
        result = _compute_economics_summary(strategy, bars, fee_bps, slippage_bps)
        expected_cost = result.cost_side_count * (fee_bps + slippage_bps)
        assert result.assumed_total_cost_bps == expected_cost
        assert result.fee_bps == fee_bps
        assert result.slippage_bps == slippage_bps
