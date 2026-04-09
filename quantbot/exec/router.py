"""Minimal routing stub for QuantBot.

Paper mode only - no real trading.
"""

from typing import Any


def route_signal(signal: dict) -> dict:
    """Route a signal to appropriate handlers.

    Args:
        signal: Signal dict with 'symbol', 'direction', 'confidence'.

    Returns:
        Routing decision dict.
    """
    return {
        "symbol": signal.get("symbol"),
        "direction": signal.get("direction"),
        "routed": True,
    }
