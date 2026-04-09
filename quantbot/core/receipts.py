"""Minimal receipt stubs for QuantBot.

Paper mode only - no real trading.
"""

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any


@dataclass
class TrialReceipt:
    """Minimal trial execution receipt."""

    trial_id: str
    timestamp: str = field(default_factory=lambda: datetime.utcnow().isoformat())
    status: str = "pending"
    metrics: dict[str, Any] = field(default_factory=dict)
    artifacts: dict[str, str] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        """Serialize receipt to dict."""
        return {
            "trial_id": self.trial_id,
            "timestamp": self.timestamp,
            "status": self.status,
            "metrics": self.metrics,
            "artifacts": self.artifacts,
        }
