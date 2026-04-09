"""Strategy layer for QuantBot.

Paper mode only - no real trading.
"""

from quantbot.strategy.base import Signal, Strategy
from quantbot.strategy.noop import NoOpStrategy
from quantbot.strategy.threshold import ThresholdStrategy

__all__ = ["Strategy", "Signal", "NoOpStrategy", "ThresholdStrategy"]
