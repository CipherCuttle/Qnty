"""Threshold toy strategy for QuantBot.

Tiny deterministic strategy for tests only.
NOT for production use - no performance claims.
Paper mode only - no real trading.
"""

from quantbot.data.types import Bar
from quantbot.strategy.base import Signal, Strategy


class ThresholdStrategy:
    """Toy strategy that emits signals based on price vs threshold.

    - "long" when close >= threshold
    - "short" when close < threshold

    Deterministic: same bars always produce same signals.
    Only for testing - no real trading.
    """

    def __init__(self, threshold: float, symbol: str = "TESTUSD") -> None:
        """Initialize threshold strategy.

        Args:
            threshold: Price threshold for signal generation.
            symbol: Symbol for emitted signals.
        """
        self.threshold = threshold
        self.symbol = symbol

    def on_bar(self, bar: Bar) -> Signal | None:
        """Emit signal based on bar close vs threshold.

        Args:
            bar: The OHLCV bar to evaluate.

        Returns:
            Signal if direction changes from previous bar, else None.
        """
        direction = "long" if bar.close >= self.threshold else "short"

        # Emit only when direction changes (tracked via instance state)
        # For first bar, record state and emit first direction
        prev = getattr(self, "_prev_direction", None)
        self._prev_direction = direction

        if prev is None:
            # First bar: emit based on current direction
            return Signal(
                timestamp=bar.timestamp,
                symbol=self.symbol,
                direction=direction,
                confidence=0.5,
            )

        if direction != prev:
            return Signal(
                timestamp=bar.timestamp,
                symbol=self.symbol,
                direction=direction,
                confidence=0.5,
            )

        return None


# Auto-register with experiment system (imported lazily to avoid circular deps)
def _register() -> None:
    """Register ThresholdStrategy with experiment runner registry."""
    try:
        from quantbot.experiment.runner import _register_strategy
        _register_strategy(ThresholdStrategy)
    except ImportError:
        pass


_register()
