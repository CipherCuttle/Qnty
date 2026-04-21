"""Quarterly point-in-time top-5 universe constructor.

Per the universe definitions in docs/data/universe_definitions.md:
- BTC and ETH are 100% members (always included)
- Remaining 3 slots filled by trailing volume ranking
- MATIC excluded after 2024-09-11
- Uses the hardcoded quarterly membership table from docs (ground truth)
"""

from dataclasses import dataclass
from datetime import datetime
from typing import Final

# Quarterly rebalance dates as (year, month, day)
# Covers 2021-Q1 through 2025-Q4
QUARTERLY_DATES: Final[list[str]] = [
    "2021-01-01",
    "2021-04-01",
    "2021-07-01",
    "2021-10-01",
    "2022-01-01",
    "2022-04-01",
    "2022-07-01",
    "2022-10-01",
    "2023-01-01",
    "2023-04-01",
    "2023-07-01",
    "2023-10-01",
    "2024-01-01",
    "2024-04-01",
    "2024-07-01",
    "2024-10-01",
    "2025-01-01",
    "2025-04-01",
    "2025-07-01",
    "2025-10-01",
]

# Pre-declared universe per quarter from docs/data/universe_definitions.md
# This is the ground-truth point-in-time universe derived from actual volume data
QUARTERLY_UNIVERSES: Final[dict[str, list[str]]] = {
    "2021-01-01": ["BTCUSDT", "ETHUSDT", "XRPUSDT", "LINKUSDT", "DOTUSDT"],
    "2021-04-01": ["BTCUSDT", "ETHUSDT", "BNBUSDT", "ADAUSDT", "XRPUSDT"],
    "2021-07-01": ["BTCUSDT", "ETHUSDT", "BNBUSDT", "XRPUSDT", "MATICUSDT"],
    "2021-10-01": ["BTCUSDT", "ETHUSDT", "SOLUSDT", "ADAUSDT", "XRPUSDT"],
    "2022-01-01": ["BTCUSDT", "ETHUSDT", "MATICUSDT", "SOLUSDT", "AVAXUSDT"],
    "2022-04-01": ["BTCUSDT", "ETHUSDT", "SOLUSDT", "AVAXUSDT", "XRPUSDT"],
    "2022-07-01": ["BTCUSDT", "ETHUSDT", "SOLUSDT", "ADAUSDT", "AVAXUSDT"],
    "2022-10-01": ["BTCUSDT", "ETHUSDT", "XRPUSDT", "SOLUSDT", "ADAUSDT"],
    "2023-01-01": ["BTCUSDT", "ETHUSDT", "BNBUSDT", "XRPUSDT", "SOLUSDT"],
    "2023-04-01": ["BTCUSDT", "ETHUSDT", "XRPUSDT", "MATICUSDT", "SOLUSDT"],
    "2023-07-01": ["BTCUSDT", "ETHUSDT", "XRPUSDT", "BNBUSDT", "SOLUSDT"],
    "2023-10-01": ["BTCUSDT", "ETHUSDT", "SOLUSDT", "XRPUSDT", "LINKUSDT"],
    "2024-01-01": ["BTCUSDT", "ETHUSDT", "SOLUSDT", "AVAXUSDT", "ADAUSDT"],
    "2024-04-01": ["BTCUSDT", "ETHUSDT", "SOLUSDT", "XRPUSDT", "BNBUSDT"],
    "2024-07-01": ["BTCUSDT", "ETHUSDT", "SOLUSDT", "BNBUSDT", "XRPUSDT"],
    "2024-10-01": ["BTCUSDT", "ETHUSDT", "SOLUSDT", "XRPUSDT", "BNBUSDT"],
    "2025-01-01": ["BTCUSDT", "ETHUSDT", "XRPUSDT", "SOLUSDT", "BNBUSDT"],
    "2025-04-01": ["BTCUSDT", "ETHUSDT", "SOLUSDT", "XRPUSDT", "ADAUSDT"],
    "2025-07-01": ["BTCUSDT", "ETHUSDT", "SOLUSDT", "XRPUSDT", "ADAUSDT"],
    "2025-10-01": ["ETHUSDT", "BTCUSDT", "SOLUSDT", "XRPUSDT", "BNBUSDT"],
}

# MATIC last valid date (delisted/migrated by Binance)
MATIC_CUTOFF: Final[str] = "2024-09-11"

# Always-present anchors
ANCHOR_SYMBOLS: Final[list[str]] = ["BTCUSDT", "ETHUSDT"]


@dataclass
class RebalanceEvent:
    """A single quarterly rebalance event."""

    timestamp: str  # ISO date string e.g. "2021-04-01"
    symbols: list[str]  # Top-5 universe at this rebalance

    def is_valid_at(self, timestamp: str) -> bool:
        """Check if this universe is still valid at a given timestamp."""
        return timestamp >= self.timestamp


def get_universe_at_date(date_str: str) -> list[str]:
    """Get the top-5 universe applicable at a given date.

    Args:
        date_str: ISO date string (e.g. "2021-07-15")

    Returns:
        List of 5 symbol strings for the current quarter.
        Returns empty list if date is before first rebalance.
    """
    applicable: list[str] = []

    for qdate in QUARTERLY_DATES:
        if date_str >= qdate:
            applicable = QUARTERLY_UNIVERSES[qdate]
        else:
            break

    # Filter out MATIC after cutoff
    filtered = [s for s in applicable if s != "MATICUSDT" or date_str < MATIC_CUTOFF]

    return filtered[:5]


def get_rebalance_events() -> list[RebalanceEvent]:
    """Return all rebalance events in chronological order."""
    return [
        RebalanceEvent(timestamp=qdate, symbols=QUARTERLY_UNIVERSES[qdate])
        for qdate in QUARTERLY_DATES
    ]


def get_test_quarters(
    start_date: str = "2021-10-01",
    end_date: str = "2025-07-01",
) -> list[tuple[str, str]]:
    """Return (start, end) quarter boundaries for test windows.

    Args:
        start_date: First test quarter start (ISO string)
        end_date: Last test quarter end (ISO string)

    Returns:
        List of (quarter_start, quarter_end) tuples.
    """
    quarter_starts = [d for d in QUARTERLY_DATES if d >= start_date]
    test_quarters: list[tuple[str, str]] = []

    for i, qstart in enumerate(quarter_starts):
        if qstart > end_date:
            break
        # Next quarter start, or cap at end_date
        if i + 1 < len(QUARTERLY_DATES):
            qend = QUARTERLY_DATES[i + 1]
        else:
            qend = end_date

        if qstart < end_date:
            test_quarters.append((qstart, qend))

    return test_quarters


def get_anchor_symbols() -> list[str]:
    """Return the always-present anchor symbols."""
    return list(ANCHOR_SYMBOLS)
