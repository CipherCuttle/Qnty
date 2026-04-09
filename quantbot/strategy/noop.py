"""No-op strategy for QuantBot.

Default strategy that never emits signals.
Paper mode only - no real trading.
"""

from quantbot.data.types import Bar
from quantbot.strategy.base import Strategy


class NoOpStrategy:
    """Strategy that processes bars but emits no signals.

    Used as the default safe strategy for replay runs.
    """

    def on_bar(self, bar: Bar) -> None:
        """Process a bar; always returns None (no signal).

        Args:
            bar: The OHLCV bar to process.

        Returns:
            None - never emits a signal.
        """
        return None
