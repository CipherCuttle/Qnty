"""Clean TSMOM strategy for Stage 1 admissibility.

4-point pre-declared grid (frozen, no expansion):
  - return_period: [20, 40]  (8h bars ≈ 6.7 / 13.3 day lookback)
  - threshold:    [0.0, 0.03] (mild filter; 0.0 = pure sign)

Signal: long if rolling return > threshold, flat otherwise.
Per-symbol instance; stateful — maintains price history internally.
"""

from dataclasses import dataclass, field

from quantbot.data.types import Bar
from quantbot.strategy.base import Signal


# ----------------------------------------------------------------------
# Frozen 4-point grid — NOT to be modified
# ----------------------------------------------------------------------
TSMOM_GRID: list[dict] = [
    {"return_period": 20, "threshold": 0.0},
    {"return_period": 20, "threshold": 0.03},
    {"return_period": 40, "threshold": 0.0},
    {"return_period": 40, "threshold": 0.03},
]


@dataclass
class TSMOMStrategy:
    """Time-series momentum strategy.

    Logic:
      1. Maintain rolling window of close prices
      2. Compute log rolling return: log(current_close / close_N_bars_ago)
      3. If return > threshold → long signal
      4. Otherwise → flat (no signal)

    Deterministic: same bar sequence → same signals.
    No external state; all state derived from observed bars.
    """

    return_period: int = 20          # bars lookback
    threshold: float = 0.0            # minimum return to be long
    symbol: str = "UNKNOWN"
    confidence: float = 0.5

    # Internal state
    _prices: list[float] = field(default_factory=list, repr=False)
    _bars_since_signal: int = field(default=0, repr=False)

    def __post_init__(self) -> None:
        if not isinstance(self.return_period, int):
            self.return_period = int(self.return_period)
        if not isinstance(self.threshold, float):
            self.threshold = float(self.threshold)

    def on_bar(self, bar: Bar) -> Signal | None:
        """Evaluate bar and emit long/flat signal.

        Args:
            bar: The OHLCV bar to evaluate.

        Returns:
            Signal with direction='long' if threshold exceeded, else None.
        """
        self._prices.append(bar.close)
        self._bars_since_signal += 1

        if len(self._prices) < self.return_period + 1:
            return None

        # Log return over the lookback window
        current_close = bar.close
        past_close = self._prices[-self.return_period - 1]
        if past_close <= 0:
            return None

        log_return = __import__("math").log(current_close / past_close)

        if log_return > self.threshold:
            self._bars_since_signal = 0
            return Signal(
                timestamp=bar.timestamp,
                symbol=self.symbol,
                direction="long",
                confidence=self.confidence,
            )

        return None

    def reset(self) -> None:
        """Reset internal state for a new walkforward split."""
        self._prices.clear()
        self._bars_since_signal = 0
