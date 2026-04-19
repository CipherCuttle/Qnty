"""Regime-Filtered Breakout (RFB) strategy for QuantBot.

Adds an explicit regime gate before breakout entry to suppress trading
in choppy/ranging regimes. Subclass of RollingReturnBreakoutStrategy.

Paper mode only - no real trading.
"""

from dataclasses import dataclass, field
from typing import Optional

from quantbot.data.types import Bar
from quantbot.experiment.regime import compute_log_returns, compute_trend_regime
from quantbot.strategy.base import Signal
from .rolling_return_breakout import RollingReturnBreakoutStrategy


@dataclass
class RegimeFilteredBreakoutStrategy(RollingReturnBreakoutStrategy):
    """Rolling return breakout gated by trend regime.

    Logic:
    1. Maintain rolling window of bars (own storage for regime computation)
    2. Compute trend regime per-bar using rolling mean return
    3. If regime not in allowed_trend_regimes → suppress signal
    4. Otherwise, emit signal via parent class logic

    Deterministic: same bar sequence → same signals.
    All state derived from observed bars only.
    """

    trend_window: int = 20
    trend_threshold: float = 0.001
    allowed_trend_regimes: list[str] = field(default_factory=lambda: ["uptrend"])

    # Store bars for regime computation (parent stores floats, we need Bar objects)
    _rfb_bars: list[Bar] = field(default_factory=list, repr=False)

    def on_bar(self, bar: Bar) -> Optional[Signal]:
        """Emit signal based on rolling return breakout, gated by trend regime.

        Args:
            bar: The OHLCV bar to evaluate.

        Returns:
            Signal if regime is allowed and direction changes, else None.
        """
        # Store bar for regime computation
        self._rfb_bars.append(bar)
        # Keep trend_window+1 bars so we get trend_window log returns
        # (log returns count = bars - 1, and regime needs len(log_rets) >= window)
        if len(self._rfb_bars) > self.trend_window + 1:
            self._rfb_bars = self._rfb_bars[-(self.trend_window + 1) :]

        # Gate: check trend regime before breakout logic
        if len(self._rfb_bars) >= self.trend_window:
            log_returns = compute_log_returns(self._rfb_bars)
            regime = compute_trend_regime(
                log_returns,
                window=self.trend_window,
                threshold=self.trend_threshold,
            )
            if regime.label in self.allowed_trend_regimes:
                return super().on_bar(bar)
            # Regime not allowed: suppress signal
            return None

        return super().on_bar(bar)


# Register with experiment runner (lazy import to avoid circular deps)
try:
    from quantbot.experiment.runner import _register_strategy

    _register_strategy(RegimeFilteredBreakoutStrategy)
except ImportError:
    pass
