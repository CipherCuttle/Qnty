"""Minimal replay runner that iterates bars and emits a deterministic receipt."""

import hashlib
import json
from dataclasses import dataclass, field
from typing import Iterator

from quantbot.data.types import Bar


@dataclass
class ReplayReceipt:
    """Deterministic summary receipt from a replay run."""

    bar_count: int
    bar_hash: str
    first_timestamp: str
    last_timestamp: str
    total_volume: float
    receipt_hash: str = field(init=False)

    def __post_init__(self) -> None:
        """Compute deterministic receipt hash."""
        canonical = json.dumps(
            {
                "bar_count": self.bar_count,
                "bar_hash": self.bar_hash,
                "first_timestamp": self.first_timestamp,
                "last_timestamp": self.last_timestamp,
                "total_volume": self.total_volume,
            },
            separators=(",", ":"),
            sort_keys=True,
        )
        self.receipt_hash = hashlib.sha256(canonical.encode()).hexdigest()

    def to_dict(self) -> dict:
        """Serialize receipt to dict."""
        return {
            "bar_count": self.bar_count,
            "bar_hash": self.bar_hash,
            "first_timestamp": self.first_timestamp,
            "last_timestamp": self.last_timestamp,
            "total_volume": self.total_volume,
            "receipt_hash": self.receipt_hash,
        }


class ReplayRunner:
    """Iterate bars and emit a deterministic summary receipt.

    No strategy logic, no signals, no trading.
    """

    def __init__(self, bars: list[Bar]):
        """Initialize runner with bars.

        Args:
            bars: List of Bars to replay.
        """
        self.bars = bars

    def iter_bars(self) -> Iterator[Bar]:
        """Iterate bars in order.

        Yields:
            Bar objects sequentially.
        """
        yield from self.bars

    def run(self) -> ReplayReceipt:
        """Run replay and produce deterministic receipt.

        Returns:
            ReplayReceipt with bar summary and hash.
        """
        bar_dicts = [bar.to_dict() for bar in self.bars]
        bar_json = json.dumps(bar_dicts, separators=(",", ":"), sort_keys=True)
        bar_hash = hashlib.sha256(bar_json.encode()).hexdigest()

        total_volume = sum(bar.volume for bar in self.bars)

        return ReplayReceipt(
            bar_count=len(self.bars),
            bar_hash=bar_hash,
            first_timestamp=self.bars[0].timestamp if self.bars else "",
            last_timestamp=self.bars[-1].timestamp if self.bars else "",
            total_volume=total_volume,
        )
