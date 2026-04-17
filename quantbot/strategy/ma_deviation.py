"""MA deviation toy strategy for QuantBot.

Tiny deterministic strategy for tests only.
NOT for production use - no performance claims.
Paper mode only - no real trading.
"""

from quantbot.data.types import Bar
from quantbot.strategy.base import Signal, Strategy


class MADeviationStrategy:
    """Strategy that emits signals based on price deviation from moving average.

    - "long" when close > MA
    - "short" when close < MA
    - neutral otherwise

    Deterministic: same bars always produce same signals.
    Only for testing - no real trading.
    """

    def __init__(
        self,
        ma_period: int = 20,
        symbol: str = "TESTUSD",
        threshold_pct: float = 0.0,
        # Internal params injected by walkforward_runner - accepted but ignored
        _split_index: int | None = None,
        _test_start: int | None = None,
        _test_end: int | None = None,
        _train_start: int | None = None,
        _train_end: int | None = None,
        **kwargs,
    ) -> None:
        """Initialize MA deviation strategy.

        Args:
            ma_period: Number of bars for moving average window.
            symbol: Symbol for emitted signals.
            threshold_pct: Minimum deviation percentage to trigger signal.
        """
        self.ma_period = ma_period
        self.symbol = symbol
        self.threshold_pct = threshold_pct
        self._bars: list[float] = []

    def on_bar(self, bar: Bar) -> Signal | None:
        """Emit signal based on bar close vs moving average.

        Args:
            bar: The OHLCV bar to evaluate.

        Returns:
            Signal if direction changes from previous bar, else None.
        """
        self._bars.append(bar.close)

        if len(self._bars) < self.ma_period:
            return None

        ma = sum(self._bars[-self.ma_period :]) / self.ma_period
        deviation_pct = (bar.close - ma) / ma if ma != 0 else 0.0

        if abs(deviation_pct) < self.threshold_pct:
            direction = "flat"
        else:
            direction = "long" if bar.close > ma else "short"

        prev = getattr(self, "_prev_direction", None)
        self._prev_direction = direction

        if prev is None:
            if direction != "flat":
                return Signal(
                    timestamp=bar.timestamp,
                    symbol=self.symbol,
                    direction=direction,
                    confidence=0.5,
                )
            return None

        if direction != prev:
            if direction != "flat":
                return Signal(
                    timestamp=bar.timestamp,
                    symbol=self.symbol,
                    direction=direction,
                    confidence=0.5,
                )

        return None


# Auto-register with experiment system (imported lazily to avoid circular deps)
def _register() -> None:
    """Register MADeviationStrategy with experiment runner registry."""
    try:
        from quantbot.experiment.runner import _register_strategy

        _register_strategy(MADeviationStrategy)
    except ImportError:
        pass


_register()