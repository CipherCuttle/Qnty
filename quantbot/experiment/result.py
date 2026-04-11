"""Minimal experiment result for QuantBot.

Paper mode only - no real trading, no profitability claims.
"""

from dataclasses import dataclass
from pathlib import Path
from typing import Any

from quantbot.core.determinism import canonical_json_dumps
from quantbot.experiment.spec import ExperimentSpec


@dataclass
class ExperimentResult:
    """Result of a single deterministic experiment run.

    Combines the experiment spec with execution outcomes.
    Honest summary: what ran, what it saw, what it emitted.

    Attributes:
        spec: The ExperimentSpec describing the experiment setup.
        receipt_path: Path to the produced receipt JSON file.
        receipt_digest: SHA256 digest of the receipt file.
        bar_count: Number of bars processed.
        signal_count: Number of signals emitted.
        first_timestamp: First bar timestamp.
        last_timestamp: Last bar timestamp.
        long_count: Number of long signals (if strategy emits direction).
        short_count: Number of short signals (if strategy emits direction).
        flat_count: Number of flat/neutral transitions (if applicable).
        engine_version: Version string of the QuantBot engine.
    """

    spec: ExperimentSpec
    receipt_path: Path
    receipt_digest: str
    bar_count: int
    signal_count: int
    first_timestamp: str
    last_timestamp: str
    long_count: int = 0
    short_count: int = 0
    flat_count: int = 0
    engine_version: str = ""

    def to_dict(self) -> dict[str, Any]:
        """Serialize result to dict."""
        return {
            "experiment_name": self.spec.experiment_name,
            "strategy_name": self.spec.strategy_name,
            "strategy_params": self.spec.strategy_params,
            "fixture_name": self.spec.fixture_name,
            "engine_version": self.engine_version,
            "receipt_digest": self.receipt_digest,
            "bar_count": self.bar_count,
            "signal_count": self.signal_count,
            "first_timestamp": self.first_timestamp,
            "last_timestamp": self.last_timestamp,
            "long_count": self.long_count,
            "short_count": self.short_count,
            "flat_count": self.flat_count,
        }

    def to_json(self) -> str:
        """Serialize result to deterministic canonical JSON string."""
        return canonical_json_dumps(self.to_dict())

    def write_json(self, path: Path) -> None:
        """Write result as deterministic JSON to disk."""
        path.write_text(self.to_json(), encoding="utf-8")
