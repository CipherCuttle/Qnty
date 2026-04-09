"""Strategy contract for QuantBot.

Minimal typed interface for signal-generating strategies.
Paper mode only - no real trading.
"""

from dataclasses import dataclass
from typing import Protocol, runtime_checkable

from quantbot.data.types import Bar


@dataclass
class Signal:
    """Trading signal produced by a strategy.

    Attributes:
        timestamp: ISO timestamp of the bar that generated this signal.
        symbol: Trading pair symbol (e.g. "BTCUSDT").
        direction: "long" or "short".
        confidence: Confidence score 0.0–1.0.
    """

    timestamp: str
    symbol: str
    direction: str
    confidence: float

    def to_dict(self) -> dict:
        """Serialize signal to dict."""
        return {
            "timestamp": self.timestamp,
            "symbol": self.symbol,
            "direction": self.direction,
            "confidence": self.confidence,
        }


@runtime_checkable
class Strategy(Protocol):
    """Protocol for signal-generating strategies.

    A strategy receives bars sequentially and may emit signals.
    No execution, no order placement, no risk management.
    """

    def on_bar(self, bar: Bar) -> Signal | None:
        """Process a single bar and optionally emit a signal.

        Args:
            bar: The OHLCV bar to process.

        Returns:
            A Signal if the strategy generates one, otherwise None.
        """
        ...
