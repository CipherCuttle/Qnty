"""Minimal replay runner that iterates bars and emits a deterministic receipt."""

import hashlib
import json
from dataclasses import dataclass, field
from typing import Iterator

from quantbot.data.types import Bar
from quantbot.version import ENGINE_VERSION


@dataclass
class ReplayReceipt:
    """Deterministic summary receipt from a replay run."""

    bar_count: int
    bar_hash: str
    first_timestamp: str
    last_timestamp: str
    total_volume: float
    engine_version: str = ENGINE_VERSION
    input_digest: str = ""
    signal_count: int = 0
    output_digest: str = field(init=False)

    def __post_init__(self) -> None:
        """Compute deterministic output digest from receipt fields (excluding output_digest)."""
        receipt_for_hash = {
            "bar_count": self.bar_count,
            "bar_hash": self.bar_hash,
            "first_timestamp": self.first_timestamp,
            "last_timestamp": self.last_timestamp,
            "total_volume": self.total_volume,
            "engine_version": self.engine_version,
            "input_digest": self.input_digest,
            "signal_count": self.signal_count,
        }
        canonical = json.dumps(receipt_for_hash, separators=(",", ":"), sort_keys=True)
        self.output_digest = hashlib.sha256(canonical.encode()).hexdigest()

    def to_dict(self) -> dict:
        """Serialize receipt to dict."""
        return {
            "bar_count": self.bar_count,
            "bar_hash": self.bar_hash,
            "first_timestamp": self.first_timestamp,
            "last_timestamp": self.last_timestamp,
            "total_volume": self.total_volume,
            "engine_version": self.engine_version,
            "input_digest": self.input_digest,
            "signal_count": self.signal_count,
            "output_digest": self.output_digest,
        }


class ReplayRunner:
    """Iterate bars and emit a deterministic summary receipt.

    No trading, no order placement.
    """

    def __init__(self, bars: list[Bar], strategy=None):
        """Initialize runner with bars and optional strategy.

        Args:
            bars: List of Bars to replay.
            strategy: Optional strategy object implementing on_bar(bar) -> Signal|None.
        """
        self.bars = bars
        self.strategy = strategy

    def iter_bars(self) -> Iterator[Bar]:
        """Iterate bars in order.

        Yields:
            Bar objects sequentially.
        """
        yield from self.bars

    def run(self) -> ReplayReceipt:
        """Run replay and produce deterministic receipt.

        If a strategy is set, it is called on each bar and signals are counted.
        Without a strategy, signal_count is 0.

        Returns:
            ReplayReceipt with bar summary and hash.
        """
        bar_dicts = [bar.to_dict() for bar in self.bars]
        bar_json = json.dumps(bar_dicts, separators=(",", ":"), sort_keys=True)
        bar_hash = hashlib.sha256(bar_json.encode()).hexdigest()
        input_digest = hashlib.sha256(bar_json.encode()).hexdigest()

        total_volume = sum(bar.volume for bar in self.bars)

        signal_count = 0
        if self.strategy is not None:
            for bar in self.bars:
                sig = self.strategy.on_bar(bar)
                if sig is not None:
                    signal_count += 1

        return ReplayReceipt(
            bar_count=len(self.bars),
            bar_hash=bar_hash,
            first_timestamp=self.bars[0].timestamp if self.bars else "",
            last_timestamp=self.bars[-1].timestamp if self.bars else "",
            total_volume=total_volume,
            input_digest=input_digest,
            signal_count=signal_count,
        )
