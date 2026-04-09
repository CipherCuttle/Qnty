"""Signal protocol interface for QuantBot.

Protocol only - no implementation.
"""

from typing import Protocol, runtime_checkable


@runtime_checkable
class SignalProtocol(Protocol):
    """Protocol for trading signal generators."""

    def emit(self, symbol: str, direction: str, confidence: float) -> dict:
        """Emit a trading signal.

        Args:
            symbol: Trading pair symbol.
            direction: 'long' or 'short'.
            confidence: Confidence score 0.0-1.0.

        Returns:
            Signal payload dict.
        """
        ...
