"""Tests for CSV loader determinism."""

import hashlib
import json
from pathlib import Path

from quantbot.data.loaders import load_bars_from_csv
from quantbot.data.types import Bar


FIXTURE_DIR = Path(__file__).parent / "fixtures"


def test_csv_loader_produces_deterministic_bar_list():
    """Verify CSV loads into identical Bar list on every run."""
    csv_path = FIXTURE_DIR / "sample_bars.csv"

    # Load twice
    bars1 = load_bars_from_csv(csv_path)
    bars2 = load_bars_from_csv(csv_path)

    # Must be identical
    assert len(bars1) == len(bars2)
    for b1, b2 in zip(bars1, bars2):
        assert b1.timestamp == b2.timestamp
        assert b1.open == b2.open
        assert b1.high == b2.high
        assert b1.low == b2.low
        assert b1.close == b2.close
        assert b1.volume == b2.volume


def test_csv_loader_bar_hash_is_deterministic():
    """Verify bar list serialization is deterministic (hash stable across runs)."""
    csv_path = FIXTURE_DIR / "sample_bars.csv"
    bars = load_bars_from_csv(csv_path)

    # Serialize to canonical JSON
    bar_dicts = [bar.to_dict() for bar in bars]
    canonical = json.dumps(bar_dicts, separators=(",", ":"), sort_keys=True)
    bar_hash = hashlib.sha256(canonical.encode()).hexdigest()

    # Expected hash computed from fixture CSV (canonical JSON serialization)
    expected_hash = "96481cbfe8d93f5e467499c9d9d60a9ca8c62e895042c101660dea5e78cc8908"
    assert bar_hash == expected_hash, f"Expected {expected_hash}, got {bar_hash}"


def test_bar_count_and_first_last():
    """Verify fixture has expected bar count and timestamps."""
    csv_path = FIXTURE_DIR / "sample_bars.csv"
    bars = load_bars_from_csv(csv_path)

    assert len(bars) == 8
    assert bars[0].timestamp == "2024-01-02T09:00:00"
    assert bars[-1].timestamp == "2024-01-02T16:00:00"


def test_bar_types():
    """Verify Bar fields have correct types."""
    csv_path = FIXTURE_DIR / "sample_bars.csv"
    bars = load_bars_from_csv(csv_path)

    for bar in bars:
        assert isinstance(bar, Bar)
        assert isinstance(bar.timestamp, str)
        assert isinstance(bar.open, float)
        assert isinstance(bar.high, float)
        assert isinstance(bar.low, float)
        assert isinstance(bar.close, float)
        assert isinstance(bar.volume, float)
