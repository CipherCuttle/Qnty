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
    """

    experiment_name: str
    strategy_name: str
    strategy_params: dict[str, Any] = field(default_factory=dict)
    fixture_name: str = ""
    description: str = ""
    notes: str = ""

    def to_dict(self) -> dict[str, Any]:
        """Serialize spec to dict."""
        return {
            "experiment_name": self.experiment_name,
            "strategy_name": self.strategy_name,
            "strategy_params": self.strategy_params,
            "fixture_name": self.fixture_name,
            "description": self.description,
            "notes": self.notes,
        }
