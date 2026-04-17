"""Strategy integration tests for QuantBot.

Requires PYTHONHASHSEED=0 for deterministic dict ordering.
"""

import json
import tempfile
from pathlib import Path

import pytest

from quantbot.app.run_replay import run_replay
from quantbot.strategy.ma_deviation import MADeviationStrategy
from quantbot.strategy.noop import NoOpStrategy
from quantbot.strategy.threshold import ThresholdStrategy


FIXTURE_DIR = Path(__file__).parent / "fixtures"
MANIFEST_PATH = FIXTURE_DIR / "sample_manifest.json"
CSV_PATH = FIXTURE_DIR / "sample_bars.csv"


def test_noop_strategy_signal_count_is_zero() -> None:
    """NoOpStrategy never emits signals, so receipt signal_count is 0."""
    with tempfile.TemporaryDirectory() as tmpdir:
        out = Path(tmpdir) / "run"
        run_replay(MANIFEST_PATH, CSV_PATH, out, strategy=NoOpStrategy())

        receipt = json.loads((out / "receipt.json").read_text())
        assert receipt["signal_count"] == 0
        assert receipt["bar_count"] == 8


def test_threshold_strategy_produces_signals() -> None:
    """ThresholdStrategy emits signals when price crosses threshold."""
    with tempfile.TemporaryDirectory() as tmpdir:
        out = Path(tmpdir) / "run"
        # Threshold 103: bar1=101(short), bar4=103(long switch)
        strategy = ThresholdStrategy(threshold=103.0)
        run_replay(MANIFEST_PATH, CSV_PATH, out, strategy=strategy)

        receipt = json.loads((out / "receipt.json").read_text())
        # First bar emits short, bar 4 switches to long = 2 signals
        assert receipt["signal_count"] == 2


def test_strategy_determinism() -> None:
    """Two runs with same strategy produce byte-identical receipts."""
    with tempfile.TemporaryDirectory() as tmpdir:
        out1 = Path(tmpdir) / "run1"
        out2 = Path(tmpdir) / "run2"

        strategy = ThresholdStrategy(threshold=103.0)

        path1 = run_replay(MANIFEST_PATH, CSV_PATH, out1, strategy=strategy)
        path2 = run_replay(MANIFEST_PATH, CSV_PATH, out2, strategy=strategy)

        # Receipts must be byte-identical across runs
        assert path1.read_bytes() == path2.read_bytes()


def test_replay_without_strategy_still_works() -> None:
    """run_replay with strategy=None produces signal_count=0 (backwards compat)."""
    with tempfile.TemporaryDirectory() as tmpdir:
        out = Path(tmpdir) / "run"
        path = run_replay(MANIFEST_PATH, CSV_PATH, out, strategy=None)

        receipt = json.loads(path.read_text())
        assert receipt["signal_count"] == 0
        assert receipt["bar_count"] == 8


class TestMADeviationStrategy:
    """Tests for MADeviationStrategy."""

    def test_ma_deviation_strategy_registered_in_runner(self) -> None:
        """MADeviationStrategy is registered in the experiment runner registry."""
        from quantbot.experiment.runner import _STRATEGY_REGISTRY

        assert "MADeviationStrategy" in _STRATEGY_REGISTRY

    def test_ma_deviation_strategy_produces_signals(self) -> None:
        """MADeviationStrategy emits signals when price deviates from MA."""
        with tempfile.TemporaryDirectory() as tmpdir:
            out = Path(tmpdir) / "run"
            strategy = MADeviationStrategy(ma_period=3, symbol="TESTUSD")
            run_replay(MANIFEST_PATH, CSV_PATH, out, strategy=strategy)

            receipt = json.loads((out / "receipt.json").read_text())
            assert receipt["signal_count"] > 0

    def test_ma_deviation_strategy_accepts_walkforward_internal_params(self) -> None:
        """MADeviationStrategy accepts _split_index, _test_start, _test_end params."""
        strategy = MADeviationStrategy(
            ma_period=3,
            symbol="TESTUSD",
            _split_index=0,
            _test_start=100,
            _test_end=150,
            _train_start=0,
            _train_end=100,
        )
        assert strategy.ma_period == 3
        assert strategy.symbol == "TESTUSD"


class TestWalkforwardManifestIntegrity:
    """Tests for walkforward manifest verification."""

    def test_walkforward_splits_produce_valid_manifests(self) -> None:
        """Walkforward split CSVs have valid SHA256 hashes in their manifests."""
        from quantbot.core.determinism import sha256_file
        from quantbot.experiment.spec import ExperimentSpec
        from quantbot.experiment.walkforward_runner import run_walkforward_experiment

        FIXTURE_DIR = Path(__file__).parent / "fixtures"
        BTCUSDT_MANIFEST_PATH = FIXTURE_DIR / "BTCUSDT_manifest.json"
        BTCUSDT_CSV_PATH = FIXTURE_DIR / "BTCUSDT_8h.csv"

        with tempfile.TemporaryDirectory() as tmpdir:
            out = Path(tmpdir) / "wf_manifest_test"
            spec = ExperimentSpec(
                experiment_name="manifest_integrity_test",
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

            # Check that each split has a valid manifest with matching hash
            for idx, split in enumerate(result.splits[:3]):
                split_dir = out / f"split_{idx:03d}"
                manifest_path = split_dir / "manifest.json"
                csv_path = split_dir / "split_bars.csv"

                assert manifest_path.exists(), f"Split {idx} missing manifest"
                assert csv_path.exists(), f"Split {idx} missing CSV"

                manifest_data = json.loads(manifest_path.read_text())
                csv_hash = sha256_file(csv_path)
                assert manifest_data["split_bars.csv"] == csv_hash

    def test_walkforward_produces_non_empty_outputs(self) -> None:
        """Walkforward run produces non-empty signal outputs for all splits."""
        from quantbot.experiment.spec import ExperimentSpec
        from quantbot.experiment.walkforward_runner import run_walkforward_experiment

        FIXTURE_DIR = Path(__file__).parent / "fixtures"
        BTCUSDT_MANIFEST_PATH = FIXTURE_DIR / "BTCUSDT_manifest.json"
        BTCUSDT_CSV_PATH = FIXTURE_DIR / "BTCUSDT_8h.csv"

        with tempfile.TemporaryDirectory() as tmpdir:
            out = Path(tmpdir) / "wf_nonempty_test"
            spec = ExperimentSpec(
                experiment_name="nonempty_wf_test",
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

            # All splits should have receipts (experiments succeeded)
            assert all(s.receipt_path is not None for s in result.splits)
            # All splits should have non-zero bar counts
            assert all(s.test_bar_count > 0 for s in result.splits)
