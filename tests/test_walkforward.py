"""Tests for walk-forward split support."""

from quantbot.data.types import Bar
from quantbot.experiment.walkforward import WalkForwardSplit, build_walkforward_splits


def _make_bars(n: int) -> list[Bar]:
    """Create n synthetic bars."""
    return [
        Bar(
            timestamp=f"2024-01-{i+1:02d}T00:00:00",
            open=float(i),
            high=float(i + 1),
            low=float(i - 1),
            close=float(i),
            volume=1.0,
        )
        for i in range(n)
    ]


class TestSplitBoundaries:
    """Verify split boundaries are correct."""

    def test_single_split(self):
        """train_end and test_start are adjacent with no gap."""
        bars = _make_bars(15)
        splits = build_walkforward_splits(bars, train_size=10, test_size=5)

        assert len(splits) == 1
        s = splits[0]
        assert s.train_start == 0
        assert s.train_end == 10
        assert s.test_start == 10
        assert s.test_end == 15

    def test_three_splits_with_default_step(self):
        """Default step_size=test_size gives overlapping train windows."""
        bars = _make_bars(20)
        splits = build_walkforward_splits(bars, train_size=10, test_size=5)

        assert len(splits) == 2

        s0 = splits[0]
        assert s0.train_start == 0
        assert s0.train_end == 10
        assert s0.test_start == 10
        assert s0.test_end == 15

        s1 = splits[1]
        assert s1.train_start == 5
        assert s1.train_end == 15
        assert s1.test_start == 15
        assert s1.test_end == 20

    def test_train_end_equals_test_start(self):
        """Training window ends exactly where test window begins."""
        bars = _make_bars(15)
        splits = build_walkforward_splits(bars, train_size=7, test_size=3)
        s = splits[0]
        assert s.train_end == s.test_start


class TestNoOverlap:
    """Verify test windows do not overlap across splits."""

    def test_consecutive_test_windows_dont_overlap(self):
        """Test windows are disjoint when step_size == test_size."""
        bars = _make_bars(30)
        splits = build_walkforward_splits(bars, train_size=10, test_size=5)

        for i in range(len(splits) - 1):
            assert splits[i].test_end <= splits[i + 1].test_start


class TestDeterminism:
    """Repeated runs produce identical splits."""

    def test_idempotent(self):
        """Calling twice returns same result."""
        bars = _make_bars(25)
        first = build_walkforward_splits(bars, train_size=8, test_size=4, step_size=4)
        second = build_walkforward_splits(bars, train_size=8, test_size=4, step_size=4)
        assert first == second


class TestEdgeCases:
    """Edge cases should fail or return empty clearly."""

    def test_insufficient_data_returns_empty(self):
        """Not enough bars for one full split."""
        bars = _make_bars(5)
        result = build_walkforward_splits(bars, train_size=10, test_size=5)
        assert result == []

    def test_exactly_enough_data(self):
        """Exactly train_size + test_size bars yields one split."""
        bars = _make_bars(15)
        splits = build_walkforward_splits(bars, train_size=10, test_size=5)
        assert len(splits) == 1

    def test_step_larger_than_test_advances_faster(self):
        """step_size > test_size skips bars between test windows."""
        bars = _make_bars(30)
        splits = build_walkforward_splits(bars, train_size=10, test_size=5, step_size=10)

        assert len(splits) == 2

        assert splits[0].test_start == 10
        assert splits[0].test_end == 15

        assert splits[1].train_start == 10
        assert splits[1].test_start == 20
        assert splits[1].test_end == 25

    def test_no_partial_split_at_end(self):
        """Final window that doesn't fit completely is discarded."""
        bars = _make_bars(23)
        splits = build_walkforward_splits(bars, train_size=10, test_size=5, step_size=5)

        last = splits[-1]
        assert last.test_end <= len(bars)
