"""Typed data structures for QuantBot."""

from dataclasses import dataclass
from datetime import datetime


@dataclass
class Bar:
    """OHLCV bar structure.

    Attributes:
        timestamp: ISO format timestamp string.
        open: Opening price.
        high: Highest price.
        low: Lowest price.
        close: Closing price.
        volume: Trading volume.
    """

    timestamp: str
    open: float
    high: float
    low: float
    close: float
    volume: float

    @classmethod
    def from_csv_row(cls, row: dict[str, str]) -> "Bar":
        """Parse a Bar from a CSV row dict.

        Args:
            row: Dictionary with keys: timestamp, open, high, low, close, volume.

        Returns:
            Bar instance.
        """
        return cls(
            timestamp=row["timestamp"],
            open=float(row["open"]),
            high=float(row["high"]),
            low=float(row["low"]),
            close=float(row["close"]),
            volume=float(row["volume"]),
        )

    def to_dict(self) -> dict:
        """Serialize Bar to dictionary."""
        return {
            "timestamp": self.timestamp,
            "open": self.open,
            "high": self.high,
            "low": self.low,
            "close": self.close,
            "volume": self.volume,
        }
