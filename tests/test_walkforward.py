"""Tests for walk-forward split support."""

from quantbot.data.types import Bar
from quantbot.experiment.result import InferenceSummary, ReturnSummary
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


class TestWalkForwardSplitResultFields:
    """Tests for WalkForwardSplitResult train/test path substrate fields."""

    def test_walkforward_split_result_default_split_role(self):
        """Default split_role is 'test'."""
        from quantbot.experiment.result import WalkForwardSplitResult

        result = WalkForwardSplitResult(
            split_index=0,
            train_bar_count=10,
            test_bar_count=5,
            signal_count=0,
            long_count=0,
            short_count=0,
            flat_count=0,
            receipt_path=None,
            artifact_path=None,
        )
        assert result.split_role == "test"
        assert result.train_inference_summary is None
        assert result.train_return_summary is None

    def test_walkforward_split_result_train_role(self):
        """split_role can be set to 'train'."""
        from quantbot.experiment.result import WalkForwardSplitResult

        result = WalkForwardSplitResult(
            split_index=0,
            train_bar_count=10,
            test_bar_count=5,
            signal_count=0,
            long_count=0,
            short_count=0,
            flat_count=0,
            receipt_path=None,
            artifact_path=None,
            split_role="train",
        )
        assert result.split_role == "train"

    def test_walkforward_split_result_both_role(self):
        """split_role can be set to 'both'."""
        from quantbot.experiment.result import WalkForwardSplitResult

        result = WalkForwardSplitResult(
            split_index=0,
            train_bar_count=10,
            test_bar_count=5,
            signal_count=0,
            long_count=0,
            short_count=0,
            flat_count=0,
            receipt_path=None,
            artifact_path=None,
            split_role="both",
        )
        assert result.split_role == "both"

    def test_walkforward_split_result_train_inference_summary(self):
        """train_inference_summary can be assigned."""
        from quantbot.experiment.result import WalkForwardSplitResult

        inference = InferenceSummary(
            bar_count_for_returns=10,
            mean_return=0.01,
            std_return=0.02,
            gross_return_total=0.1,
            net_return_total=0.08,
            cost_deduction_total=0.02,
            sharpe_like=1.5,
            annualized=False,
            interval="unknown",
            annualization_note="interval unknown",
        )
        result = WalkForwardSplitResult(
            split_index=0,
            train_bar_count=10,
            test_bar_count=5,
            signal_count=0,
            long_count=0,
            short_count=0,
            flat_count=0,
            receipt_path=None,
            artifact_path=None,
            train_inference_summary=inference,
        )
        assert result.train_inference_summary is not None
        assert result.train_inference_summary.sharpe_like == 1.5

    def test_walkforward_split_result_train_return_summary(self):
        """train_return_summary can be assigned."""
        from quantbot.experiment.result import WalkForwardSplitResult

        ret_summary = ReturnSummary(
            gross_return_total=0.10,
            net_return_total=0.08,
            cost_deduction_total=0.02,
            bars_held=10,
            winning_bars=6,
            losing_bars=4,
        )
        result = WalkForwardSplitResult(
            split_index=0,
            train_bar_count=10,
            test_bar_count=5,
            signal_count=0,
            long_count=0,
            short_count=0,
            flat_count=0,
            receipt_path=None,
            artifact_path=None,
            train_return_summary=ret_summary,
        )
        assert result.train_return_summary is not None
        assert result.train_return_summary.gross_return_total == 0.10

    def test_walkforward_split_result_legacy_test_only(self):
        """Ensure existing test-only results work without changes."""
        from quantbot.experiment.result import WalkForwardSplitResult

        result = WalkForwardSplitResult(
            split_index=0,
            train_bar_count=10,
            test_bar_count=100,
            signal_count=50,
            long_count=25,
            short_count=10,
            flat_count=15,
            receipt_path=None,
            artifact_path=None,
            return_summary=ReturnSummary(
                gross_return_total=0.05,
                net_return_total=0.04,
                cost_deduction_total=0.01,
            ),
        )
        assert result.split_role == "test"  # default
        assert result.train_inference_summary is None  # not populated
        assert result.return_summary.gross_return_total == 0.05
