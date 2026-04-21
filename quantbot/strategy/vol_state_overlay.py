"""Vol-state overlay for TSMOM — stratifies signals by vol regime.

Per Component 4 specification:
  - Uses compute_vol_regime from quantbot.experiment.regime
  - window=20, high_quantile=0.65 → two regimes: low_vol, high_vol
  - Stratifies TSMOM signals by regime
  - Does NOT use trend-regime (market-state) — that's Stage 2 candidate

This is a thin wrapper: it reads the current bar index and regime label,
and applies the TSMOM strategy's on_bar, then tags the result with regime.
"""

from dataclasses import dataclass, field
from typing import Optional

from quantbot.data.types import Bar
from quantbot.experiment.regime import (
    compute_vol_regime,
    compute_log_returns,
)
from quantbot.strategy.base import Signal
from quantbot.strategy.tsmom_strategy import TSMOMStrategy


# Overlay parameters — frozen per spec
VOL_WINDOW: int = 20
VOL_HIGH_QUANTILE: float = 0.65


@dataclass
class VolStateOverlay:
    """TSMOM strategy overlaid with vol-regime conditioning.

    On each bar, it:
      1. Maintains a rolling window of bars for regime computation
      2. Computes vol regime (low_vol / high_vol) using rolling stdev quantile
      3. Delegates to the TSMOM strategy
      4. Tags the resulting signal (if any) with the current vol regime

    State is accumulated across bars; reset() clears both the price window
    and the regime computation state.
    """

    tsme: TSMOMStrategy = field(default_factory=TSMOMStrategy)
    vol_window: int = VOL_WINDOW
    vol_high_quantile: float = VOL_HIGH_QUANTILE

    # Internal state
    _bars: list[Bar] = field(default_factory=list, repr=False)
    _current_regime: str = "unknown"

    def on_bar(self, bar: Bar) -> tuple[Signal | None, str]:
        """Process bar and return (signal, regime_label).

        Args:
            bar: The OHLCV bar to evaluate.

        Returns:
            Tuple of (Signal or None, regime_label string).
            Regime is 'low_vol', 'high_vol', or 'unknown'.
        """
        self._bars.append(bar)

        # Compute vol regime from accumulated bars
        self._current_regime = self._compute_regime_label()

        # Delegate to TSMOM strategy
        signal = self.tsme.on_bar(bar)

        return signal, self._current_regime

    def _compute_regime_label(self) -> str:
        """Compute vol regime label from accumulated bars."""
        if len(self._bars) < self.vol_window + 1:
            return "unknown"

        # Use close prices of the last vol_window bars
        log_rets = compute_log_returns(self._bars)

        if len(log_rets) < self.vol_window:
            return "unknown"

        regime_meta = compute_vol_regime(
            log_rets,
            window=self.vol_window,
            high_quantile=self.vol_high_quantile,
            source_start=max(0, len(log_rets) - self.vol_window),
            source_end=len(log_rets),
        )

        return regime_meta.label

    def reset(self) -> None:
        """Clear all internal state for a new walkforward split."""
        self._bars.clear()
        self._current_regime = "unknown"
        self.tsme.reset()

    @property
    def current_regime(self) -> str:
        """Return the most recently computed regime label."""
        return self._current_regime
