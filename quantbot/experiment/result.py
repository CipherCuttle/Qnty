"""Minimal experiment result for QuantBot.

Paper mode only - no real trading, no profitability claims.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING, Any, Optional

from quantbot.core.determinism import canonical_json_dumps
from quantbot.experiment.spec import ExperimentSpec

if TYPE_CHECKING:
    from quantbot.experiment.gates import GateVerdict


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
    result_path: Path
    receipt_digest: str
    bar_count: int
    signal_count: int
    first_timestamp: str
    last_timestamp: str
    long_count: int = 0
    short_count: int = 0
    flat_count: int = 0
    engine_version: str = ""
    gate_verdict: Optional[GateVerdict] = None
    fee_bps: float = 0.0
    slippage_bps: float = 0.0

    def _gate_verdict_to_dict(self) -> dict[str, Any]:
        """Serialize gate_verdict to dict, or None if not set."""
        if self.gate_verdict is None:
            return None
        return {
            "status": self.gate_verdict.status,
            "reasons": self.gate_verdict.reasons,
            "checked": self.gate_verdict.checked,
        }

    def to_dict(self) -> dict[str, Any]:
        """Serialize result to dict."""
        d = {
            "experiment_name": self.spec.experiment_name,
            "strategy_name": self.spec.strategy_name,
            "strategy_params": self.spec.strategy_params,
            "fixture_name": self.spec.fixture_name,
            "family_id": self.spec.family_id,
            "variant_id": self.spec.variant_id,
            "trial_count": self.spec.trial_count,
            "engine_version": self.engine_version,
            "receipt_digest": self.receipt_digest,
            "bar_count": self.bar_count,
            "signal_count": self.signal_count,
            "first_timestamp": self.first_timestamp,
            "last_timestamp": self.last_timestamp,
            "long_count": self.long_count,
            "short_count": self.short_count,
            "flat_count": self.flat_count,
            "gate_verdict": self._gate_verdict_to_dict(),
            "fee_bps": self.fee_bps,
            "slippage_bps": self.slippage_bps,
        }
        return d

    def to_json(self) -> str:
        """Serialize result to deterministic canonical JSON string."""
        return canonical_json_dumps(self.to_dict())

    def write_json(self, path: Path) -> None:
        """Write result as deterministic JSON to disk."""
        path.write_text(self.to_json(), encoding="utf-8")


@dataclass
class WalkForwardSplitResult:
    """Summary of a single walk-forward split's execution."""

    split_index: int
    train_bar_count: int
    test_bar_count: int
    signal_count: int
    long_count: int
    short_count: int
    flat_count: int
    receipt_path: str | None  # None if no receipt written
    artifact_path: str | None
    first_timestamp: str = ""
    last_timestamp: str = ""


@dataclass
class WalkForwardExperimentResult:
    """Summary of a walk-forward experiment across multiple splits."""

    experiment_name: str
    split_count: int
    splits: list[WalkForwardSplitResult]  # per-split summaries
    total_bar_count: int
    total_signal_count: int
    strategy_name: str = ""
    strategy_params: dict = None
    fixture_name: str = ""
    family_id: str = ""
    variant_id: str = ""
    trial_count: int = 1
    engine_version: str = ""
    gate_verdict: Optional[GateVerdict] = None
    fee_bps: float = 0.0
    slippage_bps: float = 0.0

    def __post_init__(self) -> None:
        if self.strategy_params is None:
            self.strategy_params = {}

    def _gate_verdict_to_dict(self) -> dict[str, Any]:
        """Serialize gate_verdict to dict, or None if not set."""
        if self.gate_verdict is None:
            return None
        return {
            "status": self.gate_verdict.status,
            "reasons": self.gate_verdict.reasons,
            "checked": self.gate_verdict.checked,
        }

    def to_dict(self) -> dict[str, Any]:
        """Serialize to deterministic dict for canonical JSON output."""
        # Aggregate signal counts across all splits
        aggregate_signal_count = sum(s.signal_count for s in self.splits)
        aggregate_long_count = sum(s.long_count for s in self.splits)
        aggregate_short_count = sum(s.short_count for s in self.splits)
        aggregate_flat_count = sum(s.flat_count for s in self.splits)

        # Find earliest and latest timestamps across all splits
        first_timestamp = ""
        last_timestamp = ""
        for split in self.splits:
            if split.first_timestamp:
                if not first_timestamp or split.first_timestamp < first_timestamp:
                    first_timestamp = split.first_timestamp
                if not last_timestamp or split.last_timestamp > last_timestamp:
                    last_timestamp = split.last_timestamp

        split_results = [
            {
                "split_index": s.split_index,
                "test_bar_count": s.test_bar_count,
                "train_bar_count": s.train_bar_count,
                "signal_count": s.signal_count,
                "long_count": s.long_count,
                "short_count": s.short_count,
                "flat_count": s.flat_count,
                "first_timestamp": s.first_timestamp,
                "last_timestamp": s.last_timestamp,
            }
            for s in self.splits
        ]

        return {
            "experiment_name": self.experiment_name,
            "strategy_name": self.strategy_name,
            "strategy_params": self.strategy_params,
            "fixture_name": self.fixture_name,
            "family_id": self.family_id,
            "variant_id": self.variant_id,
            "trial_count": self.trial_count,
            "engine_version": self.engine_version,
            "split_count": self.split_count,
            "aggregate_signal_count": aggregate_signal_count,
            "aggregate_long_count": aggregate_long_count,
            "aggregate_short_count": aggregate_short_count,
            "aggregate_flat_count": aggregate_flat_count,
            "first_timestamp": first_timestamp,
            "last_timestamp": last_timestamp,
            "split_results": split_results,
            "gate_verdict": self._gate_verdict_to_dict(),
            "fee_bps": self.fee_bps,
            "slippage_bps": self.slippage_bps,
        }

    def to_json(self) -> str:
        """Serialize to deterministic canonical JSON string."""
        return canonical_json_dumps(self.to_dict())

    def write_json(self, path: Path) -> None:
        """Write result as deterministic JSON to disk."""
        path.write_text(self.to_json(), encoding="utf-8")
