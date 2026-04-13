"""Minimal experiment specification for QuantBot.

Paper mode only - no real trading, no profitability claims.
"""

from dataclasses import dataclass, field
from typing import Any


@dataclass
class ExperimentSpec:
    """Minimal spec for a single deterministic experiment.

    Describes: what strategy was run, with what parameters,
    on what data, producing what receipt.

    Attributes:
        experiment_name: Human-readable experiment identifier.
        strategy_name: Name of the strategy class or function used.
        strategy_params: Dict of strategy constructor/config parameters.
        fixture_name: Name of the data fixture used (e.g. "BTCUSDT_8h").
        description: Optional one-line description.
        notes: Optional free-text notes (no profitability claims).
        family_id: Hypothesis/search family identifier. Defaults to experiment_name.
        variant_id: Exact tested variant inside the family. Defaults to experiment_name.
        trial_count: Cumulative tries consumed for this family at creation time. Default 1.
    """

    experiment_name: str
    strategy_name: str
    strategy_params: dict[str, Any] = field(default_factory=dict)
    fixture_name: str = ""
    description: str = ""
    notes: str = ""
    family_id: str = ""
    variant_id: str = ""
    trial_count: int = 1
    fee_bps: float = 0.0
    slippage_bps: float = 0.0

    def __post_init__(self) -> None:
        if self.trial_count < 1:
            raise ValueError(f"trial_count must be >= 1, got {self.trial_count}")
        if self.fee_bps < 0:
            raise ValueError("fee_bps must be non-negative")
        if self.slippage_bps < 0:
            raise ValueError("slippage_bps must be non-negative")

    def to_dict(self) -> dict[str, Any]:
        """Serialize spec to dict."""
        return {
            "experiment_name": self.experiment_name,
            "strategy_name": self.strategy_name,
            "strategy_params": self.strategy_params,
            "fixture_name": self.fixture_name,
            "description": self.description,
            "notes": self.notes,
            "family_id": self.family_id,
            "variant_id": self.variant_id,
            "trial_count": self.trial_count,
            "fee_bps": self.fee_bps,
            "slippage_bps": self.slippage_bps,
        }
