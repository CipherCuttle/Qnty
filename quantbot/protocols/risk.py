"""Risk protocol interface for QuantBot.

Protocol only - no implementation.
"""

from typing import Protocol, runtime_checkable


@runtime_checkable
class RiskProtocol(Protocol):
    """Protocol for risk management components."""

    def check(self, signal: dict, portfolio: dict) -> dict:
        """Evaluate risk for a signal against current portfolio.

        Args:
            signal: Trading signal dict.
            portfolio: Current portfolio state dict.

        Returns:
            Risk check result dict with 'approved' bool and 'reason' str.
        """
        ...
