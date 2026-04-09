"""Strategy integration tests for QuantBot.

Requires PYTHONHASHSEED=0 for deterministic dict ordering.
"""

import json
import tempfile
from pathlib import Path

import pytest

from quantbot.app.run_replay import run_replay
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
