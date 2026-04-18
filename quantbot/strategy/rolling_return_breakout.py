"""Rolling return breakout strategy for QuantBot.

Lower-turnover breakout strategy based on rolling returns.
Paper mode only - no real trading.
"""

from dataclasses import dataclass, field

from quantbot.data.types import Bar
from quantbot.strategy.base import Signal


@dataclass
class RollingReturnBreakoutStrategy:
    """Rolling return breakout with minimum hold period.

    Logic:
    1. Maintain rolling window of close prices
    2. Compute rolling return: (current_close - close_N_bars_ago) / close_N_bars_ago
    3. If return > return_threshold → long
    4. If return < -return_threshold → short
    5. Otherwise → flat (no signal)
    6. Minimum hold: once in position, must hold for min_hold_bars before flipping

    Deterministic: same bar sequence → same signals.
    All state derived from observed bars only.
    No time-based state except what comes from bar sequence.
    """

    rolling_return_period: int = 20
    return_threshold: float = 0.05
    min_hold_bars: int = 3
    confidence: float = 0.5
    symbol: str = "TESTUSD"

    # Internal params injected by walkforward_runner - accepted but ignored
    _split_index: int | None = None
    _test_start: int | None = None
    _test_end: int | None = None

    # Internal state - not constructor params
    _bars: list[float] = field(default_factory=list, repr=False)
    _prev_direction: str | None = field(default=None, repr=False)
    _bars_since_signal: int = field(default=0, repr=False)

    def __post_init__(self) -> None:
        """Coerce parameter types to ensure compatibility with CLI string params."""
        # Coerce rolling_return_period to int
        if not isinstance(self.rolling_return_period, int):
            self.rolling_return_period = int(self.rolling_return_period)
        # Coerce return_threshold to float
        if not isinstance(self.return_threshold, float):
            self.return_threshold = float(self.return_threshold)
        # Coerce min_hold_bars to int
        if not isinstance(self.min_hold_bars, int):
            self.min_hold_bars = int(self.min_hold_bars)

    def on_bar(self, bar: Bar) -> Signal | None:
        """Emit signal based on rolling return breakout.

        Args:
            bar: The OHLCV bar to evaluate.

        Returns:
            Signal if direction changes (with min_hold enforcement), else None.
        """
        self._bars.append(bar.close)
        self._bars_since_signal += 1

        if len(self._bars) < self.rolling_return_period + 1:
            return None

        # Compute rolling return: (current - N_bars_ago) / N_bars_ago
        current_close = bar.close
        past_close = self._bars[-self.rolling_return_period - 1]
        rolling_return = (current_close - past_close) / past_close if past_close != 0 else 0.0

        # Determine direction from rolling return
        if rolling_return > self.return_threshold:
            direction = "long"
        elif rolling_return < -self.return_threshold:
            direction = "short"
        else:
            direction = "flat"

        prev = self._prev_direction

        # First signal - emit if not flat
        if prev is None:
            self._prev_direction = direction
            if direction != "flat":
                self._bars_since_signal = 0
                return Signal(
                    timestamp=bar.timestamp,
                    symbol=self.symbol,
                    direction=direction,
                    confidence=self.confidence,
                )
            return None

        # Direction change detection with min_hold enforcement
        if direction != prev:
            # Only allow flip if min_hold_bars has passed
            if self._bars_since_signal >= self.min_hold_bars:
                self._prev_direction = direction
                self._bars_since_signal = 0
                if direction != "flat":
                    return Signal(
                        timestamp=bar.timestamp,
                        symbol=self.symbol,
                        direction=direction,
                        confidence=self.confidence,
                    )
        elif direction == "flat":
            # Reset prev_direction when returning to flat so next signal is fresh
            self._prev_direction = None
            self._bars_since_signal = 0

        return None


# Variants
rolling_return_A = RollingReturnBreakoutStrategy(
    rolling_return_period=20,
    return_threshold=0.05,
    min_hold_bars=3,
    confidence=0.5,
    symbol="TESTUSD",
)

rolling_return_B = RollingReturnBreakoutStrategy(
    rolling_return_period=40,
    return_threshold=0.08,
    min_hold_bars=5,
    confidence=0.5,
    symbol="TESTUSD",
)

rolling_return_C = RollingReturnBreakoutStrategy(
    rolling_return_period=60,
    return_threshold=0.10,
    min_hold_bars=7,
    confidence=0.5,
    symbol="TESTUSD",
)


# Auto-register with experiment system (imported lazily to avoid circular deps)
def _register() -> None:
    """Register RollingReturnBreakoutStrategy variants with experiment runner registry."""
    try:
        from quantbot.experiment.runner import _register_strategy

        _register_strategy(RollingReturnBreakoutStrategy)
    except ImportError:
        pass


_register()
