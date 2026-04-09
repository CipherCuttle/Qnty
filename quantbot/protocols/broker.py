"""Broker protocol interface for QuantBot.

Protocol only - no implementation.
"""

from typing import Protocol, runtime_checkable


@runtime_checkable
class BrokerProtocol(Protocol):
    """Protocol for order execution brokers."""

    def submit(self, symbol: str, direction: str, quantity: float) -> dict:
        """Submit an order.

        Args:
            symbol: Trading pair symbol.
            direction: 'long' or 'short'.
            quantity: Order quantity.

        Returns:
            Order response dict.
        """
        ...

    def cancel(self, order_id: str) -> dict:
        """Cancel an order.

        Args:
            order_id: Order identifier.

        Returns:
            Cancellation response dict.
        """
        ...
