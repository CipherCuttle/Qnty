"""Smoke tests for ReplayRunner determinism."""

from pathlib import Path

from quantbot.data.loaders import load_bars_from_csv
from quantbot.replay.runner import ReplayRunner, ReplayReceipt


FIXTURE_DIR = Path(__file__).parent / "fixtures"


def test_replay_runner_produces_deterministic_receipt():
    """Verify replay produces identical receipt on every run."""
    csv_path = FIXTURE_DIR / "sample_bars.csv"
    bars = load_bars_from_csv(csv_path)

    runner = ReplayRunner(bars)
    receipt1 = runner.run()
    receipt2 = runner.run()

    # Output digest must be identical across runs
    assert receipt1.output_digest == receipt2.output_digest
    assert receipt1.bar_hash == receipt2.bar_hash
    assert receipt1.bar_count == receipt2.bar_count


def test_replay_receipt_has_expected_fields():
    """Verify receipt contains all expected fields."""
    csv_path = FIXTURE_DIR / "sample_bars.csv"
    bars = load_bars_from_csv(csv_path)

    runner = ReplayRunner(bars)
    receipt = runner.run()

    assert isinstance(receipt, ReplayReceipt)
    assert receipt.bar_count == 8
    assert receipt.first_timestamp == "2024-01-02T09:00:00"
    assert receipt.last_timestamp == "2024-01-02T16:00:00"
    assert receipt.total_volume == 14000.0  # Sum of all volumes
    assert receipt.engine_version == "0.1.0"
    assert len(receipt.bar_hash) == 64  # SHA-256 hex
    assert len(receipt.output_digest) == 64  # SHA-256 hex


def test_replay_receipt_to_dict():
    """Verify receipt serializes correctly."""
    csv_path = FIXTURE_DIR / "sample_bars.csv"
    bars = load_bars_from_csv(csv_path)

    runner = ReplayRunner(bars)
    receipt = runner.run()

    d = receipt.to_dict()
    assert "bar_count" in d
    assert "bar_hash" in d
    assert "output_digest" in d
    assert "first_timestamp" in d
    assert "last_timestamp" in d
    assert "total_volume" in d


def test_iter_bars_yields_all_bars():
    """Verify iterator yields all bars in order."""
    csv_path = FIXTURE_DIR / "sample_bars.csv"
    bars = load_bars_from_csv(csv_path)

    runner = ReplayRunner(bars)
    iterated = list(runner.iter_bars())

    assert len(iterated) == len(bars)
    for i, (expected, actual) in enumerate(zip(bars, iterated)):
        assert expected.timestamp == actual.timestamp
