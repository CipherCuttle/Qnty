"""CSV loader for OHLCV bar data."""

import csv
from pathlib import Path

from quantbot.data.types import Bar


def load_bars_from_csv(csv_path: Path) -> list[Bar]:
    """Load OHLCV bars from a CSV file deterministically.

    The CSV must have headers: timestamp,open,high,low,close,volume

    Args:
        csv_path: Path to the CSV file.

    Returns:
        List of Bar objects in file order.
    """
    bars = []
    with open(csv_path, newline="", encoding="utf-8") as fh:
        reader = csv.DictReader(fh)
        for row in reader:
            bars.append(Bar.from_csv_row(row))
    return bars
