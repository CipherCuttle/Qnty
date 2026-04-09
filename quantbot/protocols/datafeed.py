"""Data feed protocol interface for QuantBot.

Protocol only - no implementation.
"""

from typing import Protocol, runtime_checkable


@runtime_checkable
class DataFeedProtocol(Protocol):
    """Protocol for market data providers."""

    def fetch(self, symbol: str, timeframe: str) -> dict:
        """Fetch market data for a symbol.

        Args:
            symbol: Trading pair symbol.
            timeframe: Timeframe (e.g., '1m', '1h', '1d').

        Returns:
            Market data dict.
        """
        ...
