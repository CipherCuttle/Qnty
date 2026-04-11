"""Walk-forward split support for QuantBot experiments.

Minimal honest implementation - no purge/embargo, no optimization.
"""

from dataclasses import dataclass

from quantbot.data.types import Bar


@dataclass
class WalkForwardSplit:
    """Train/test split indices for walk-forward analysis.

    Attributes:
        train_start: Starting index (inclusive) of training window.
        train_end: Ending index (exclusive) of training window.
        test_start: Starting index (inclusive) of test window.
        test_end: Ending index (exclusive) of test window.
    """

    train_start: int
    train_end: int
    test_start: int
    test_end: int


def build_walkforward_splits(
    bars: list[Bar],
    train_size: int,
    test_size: int,
    step_size: int | None = None,
) -> list[WalkForwardSplit]:
    """Build walk-forward split windows over a bar series.

    Bars are assumed to be pre-sorted by timestamp ascending.

    Args:
        bars: List of Bar objects in chronological order.
        train_size: Number of bars in each training window.
        test_size: Number of bars in each test window.
        step_size: Step to advance between splits. Defaults to test_size.

    Returns:
        List of WalkForwardSplit objects. Empty if insufficient data.
    """
    if step_size is None:
        step_size = test_size

    if len(bars) < train_size + test_size:
        return []

    splits: list[WalkForwardSplit] = []
    position = 0

    while position + train_size + test_size <= len(bars):
        splits.append(
            WalkForwardSplit(
                train_start=position,
                train_end=position + train_size,
                test_start=position + train_size,
                test_end=position + train_size + test_size,
            )
        )
        position += step_size

    return splits
