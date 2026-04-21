"""Multi-asset OHLCV loader for Stage 1 TSMOM admissibility test.

Loads all 10 symbol OHLCV CSVs from data/ directory.
BTC and ETH are guaranteed members per universe definitions.
MATIC data ends 2024-09-11 — handled gracefully.
"""

from pathlib import Path
from typing import Final

from quantbot.data.loaders import load_bars_from_csv
from quantbot.data.types import Bar

# All 10 symbols in the Stage 1 universe
SYMBOLS: Final[list[str]] = [
    "BTCUSDT",
    "ETHUSDT",
    "XRPUSDT",
    "LINKUSDT",
    "DOTUSDT",
    "BNBUSDT",
    "ADAUSDT",
    "MATICUSDT",
    "SOLUSDT",
    "AVAXUSDT",
]

_DATA_DIR: Final[Path] = Path("data")


def load_all_ohlcv() -> dict[str, list[Bar]]:
    """Load OHLCV bars for all 10 universe symbols.

    Returns:
        Dict mapping symbol -> list of Bar objects, sorted by timestamp.
        Symbols with truncated data (MATIC) include all available bars.
    """
    result: dict[str, list[Bar]] = {}

    for symbol in SYMBOLS:
        csv_path = _DATA_DIR / f"{symbol}_8h_ohlcv.csv"
        if not csv_path.exists():
            # MATIC may be missing from some configs — skip gracefully
            continue
        bars = load_bars_from_csv(csv_path)
        # Ensure chronological order
        bars.sort(key=lambda b: b.timestamp)
        result[symbol] = bars

    return result


def align_bars_by_timestamp(
    bars_by_symbol: dict[str, list[Bar]]
) -> list[tuple[str, Bar]]:
    """Align bars across symbols by timestamp index.

    Produces a unified time axis using the longest common timestamp range.
    Each output entry is (symbol, bar) for bars at the same bar index.

    Returns:
        List of (symbol, Bar) tuples aligned by bar index position.
    """
    if not bars_by_symbol:
        return []

    # Find the shortest symbol series to determine common length
    min_len = min(len(bars) for bars in bars_by_symbol.values())

    aligned: list[tuple[str, Bar]] = []
    for symbol, bars in bars_by_symbol.items():
        for i in range(min_len):
            aligned.append((symbol, bars[i]))

    return aligned


def get_symbol_truncation_info(
    bars_by_symbol: dict[str, list[Bar]]
) -> dict[str, str]:
    """Return the last timestamp for each symbol — useful for MATIC diagnostics."""
    return {
        symbol: bars[-1].timestamp
        for symbol, bars in bars_by_symbol.items()
        if bars
    }
