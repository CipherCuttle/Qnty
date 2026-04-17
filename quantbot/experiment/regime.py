"""Regime-tagging substrate for QuantBot.

Substrate only - enables cross-regime comparison but does not implement
full cross-regime replication. Regime labels are deterministic and
inspectable with explicit thresholds.

Minimal honest scheme supported by existing bar data:
- volatility regime: low_vol vs high_vol (based on rolling return stdev)
- trend regime: uptrend vs downtrend vs sideways (based on rolling mean return)

Labels are computed per-window using only the bars in that window,
so regime is tied to the walk-forward split being analyzed.
"""

from dataclasses import dataclass
from typing import Literal

import math


# ----------------------------------------------------------------------
# Regime label types
# ----------------------------------------------------------------------

VolRegimeLabel = Literal["low_vol", "high_vol"]
TrendRegimeLabel = Literal["uptrend", "downtrend", "sideways"]


# ----------------------------------------------------------------------
# Regime metadata (persistence layer)
# ----------------------------------------------------------------------

@dataclass
class RegimeMetadata:
    """Metadata describing how a regime label was computed.

    Enables later audit: what rule, what parameters, what thresholds.
    Serializable via to_dict().
    """

    regime_type: str  # e.g. "volatility", "trend", "combined"
    label: str  # the actual regime label value
    rule: str  # human-readable rule name, e.g. "rolling_stdev_quantile"
    parameters: dict[str, object]  # explicit parameters used (window_size, etc.)
    thresholds: dict[str, float]  # explicit threshold values used
    source_start: int  # bar index start of the window this label covers
    source_end: int  # bar index end of the window this label covers

    def to_dict(self) -> dict:
        return {
            "regime_type": self.regime_type,
            "label": self.label,
            "rule": self.rule,
            "parameters": dict(self.parameters),
            "thresholds": dict(self.thresholds),
            "source_start": self.source_start,
            "source_end": self.source_end,
        }


# ----------------------------------------------------------------------
# Rolling helpers (pure, no external state)
# ----------------------------------------------------------------------

def _rolling_stdev(values: list[float], window: int) -> float:
    """Population stdev of the most recent `window` values."""
    if len(values) < window:
        return float("nan")
    recent = values[-window:]
    n = len(recent)
    mean = sum(recent) / n
    variance = sum((x - mean) ** 2 for x in recent) / n
    return math.sqrt(variance)


def _rolling_mean(values: list[float], window: int) -> float:
    """Mean of the most recent `window` values."""
    if len(values) < window:
        return float("nan")
    recent = values[-window:]
    return sum(recent) / len(recent)


def compute_log_returns(bars: list) -> list[float]:
    """Compute log returns from close prices.

    Args:
        bars: List of objects with .close attribute (e.g. Bar dataclass).

    Returns:
        List of log-return floats. Length is len(bars) - 1 (no return for first bar).
    """
    if len(bars) < 2:
        return []
    returns = []
    for i in range(1, len(bars)):
        prev_close = bars[i - 1].close
        curr_close = bars[i].close
        if prev_close <= 0 or curr_close <= 0:
            returns.append(float("nan"))
        else:
            returns.append(math.log(curr_close / prev_close))
    return returns


# ----------------------------------------------------------------------
# Volatility regime
# ----------------------------------------------------------------------

# Default parameters - explicit, not hidden
DEFAULT_VOL_WINDOW: int = 20
DEFAULT_VOL_HIGH_QUANTILE: float = 0.65  # above 65th percentile = high_vol


def compute_vol_regime(
    log_returns: list[float],
    *,
    window: int = DEFAULT_VOL_WINDOW,
    high_quantile: float = DEFAULT_VOL_HIGH_QUANTILE,
    source_start: int = 0,
    source_end: int | None = None,
) -> RegimeMetadata:
    """Classify volatility regime using rolling stdev quantile.

    Args:
        log_returns: Precomputed log returns (from compute_log_returns).
        window: Rolling window size for stdev computation.
        high_quantile: Quantile threshold for high_vol classification.
                      Must be > 0.5. Values above this quantile -> high_vol.
        source_start: Starting bar index for the window this label covers.
        source_end: Ending bar index. Defaults to len(log_returns).

    Returns:
        RegimeMetadata with volatility regime label and computation details.
    """
    if source_end is None:
        source_end = len(log_returns)

    if len(log_returns) < window:
        return RegimeMetadata(
            regime_type="volatility",
            label="unknown",
            rule="rolling_stdev_quantile",
            parameters={"window": window, "high_quantile": high_quantile},
            thresholds={},
            source_start=source_start,
            source_end=source_end,
        )

    # Compute rolling stdevs
    rolling_stddevs: list[float] = []
    for i in range(window, len(log_returns) + 1):
        segment = log_returns[i - window : i]
        std = _rolling_stdev(segment, window)
        rolling_stddevs.append(std)

    if not rolling_stddevs:
        return RegimeMetadata(
            regime_type="volatility",
            label="unknown",
            rule="rolling_stdev_quantile",
            parameters={"window": window, "high_quantile": high_quantile},
            thresholds={},
            source_start=source_start,
            source_end=source_end,
        )

    # Determine threshold
    sorted_vals = sorted(rolling_stddevs)
    q_index = int(len(sorted_vals) * high_quantile)
    q_index = min(q_index, len(sorted_vals) - 1)
    threshold = sorted_vals[q_index]

    # Current regime: last rolling stdev vs threshold
    current_std = rolling_stddevs[-1]
    if math.isnan(current_std):
        label = "unknown"
    elif current_std >= threshold:
        label = "high_vol"
    else:
        label = "low_vol"

    return RegimeMetadata(
        regime_type="volatility",
        label=label,
        rule="rolling_stdev_quantile",
        parameters={"window": window, "high_quantile": high_quantile},
        thresholds={"high_vol_threshold": round(threshold, 6)},
        source_start=source_start,
        source_end=source_end,
    )


# ----------------------------------------------------------------------
# Trend regime
# ----------------------------------------------------------------------

DEFAULT_TREND_WINDOW: int = 20
# Uptrend: mean return > threshold
# Downtrend: mean return < -threshold
# Sideways: |mean return| <= threshold
DEFAULT_TREND_THRESHOLD: float = 0.001  # ~0.1% per bar


def compute_trend_regime(
    log_returns: list[float],
    *,
    window: int = DEFAULT_TREND_WINDOW,
    threshold: float = DEFAULT_TREND_THRESHOLD,
    source_start: int = 0,
    source_end: int | None = None,
) -> RegimeMetadata:
    """Classify trend regime using rolling mean return.

    Args:
        log_returns: Precomputed log returns.
        window: Rolling window size for mean computation.
        threshold: Absolute return threshold for up/down classification.
                  Mean > threshold -> uptrend
                  Mean < -threshold -> downtrend
                  Otherwise -> sideways
        source_start: Starting bar index.
        source_end: Ending bar index.

    Returns:
        RegimeMetadata with trend regime label and computation details.
    """
    if source_end is None:
        source_end = len(log_returns)

    if len(log_returns) < window:
        return RegimeMetadata(
            regime_type="trend",
            label="unknown",
            rule="rolling_mean_return",
            parameters={"window": window, "threshold": threshold},
            thresholds={"uptrend_threshold": threshold, "downtrend_threshold": -threshold},
            source_start=source_start,
            source_end=source_end,
        )

    # Rolling mean of last window
    recent = log_returns[-window:]
    mean_return = _rolling_mean(recent, window)

    if math.isnan(mean_return):
        label = "unknown"
    elif mean_return > threshold:
        label = "uptrend"
    elif mean_return < -threshold:
        label = "downtrend"
    else:
        label = "sideways"

    return RegimeMetadata(
        regime_type="trend",
        label=label,
        rule="rolling_mean_return",
        parameters={"window": window, "threshold": threshold},
        thresholds={"uptrend_threshold": threshold, "downtrend_threshold": -threshold, "sideways_max_abs": threshold},
        source_start=source_start,
        source_end=source_end,
    )


# ----------------------------------------------------------------------
# Combined regime (substrate for later cross-regime replication)
# ----------------------------------------------------------------------

@dataclass
class CombinedRegimeMetadata:
    """Combined regime labels (volatility + trend) for a window.

    This is the substrate layer - it does not claim cross-regime replication
    is valid. It simply makes regime labels available for later comparison.
    """

    vol_regime: RegimeMetadata
    trend_regime: RegimeMetadata

    @property
    def vol_label(self) -> str:
        return self.vol_regime.label

    @property
    def trend_label(self) -> str:
        return self.trend_regime.label

    def to_dict(self) -> dict:
        return {
            "vol_regime": self.vol_regime.to_dict(),
            "trend_regime": self.trend_regime.to_dict(),
        }


def compute_combined_regime(
    bars: list,
    *,
    vol_window: int = DEFAULT_VOL_WINDOW,
    vol_high_quantile: float = DEFAULT_VOL_HIGH_QUANTILE,
    trend_window: int = DEFAULT_TREND_WINDOW,
    trend_threshold: float = DEFAULT_TREND_THRESHOLD,
) -> CombinedRegimeMetadata:
    """Compute both volatility and trend regime labels for a bar window.

    This is the primary entry point for regime-tagging a walk-forward split.

    Args:
        bars: List of Bar objects.
        vol_window: Window for volatility regime computation.
        vol_high_quantile: Quantile threshold for high_vol.
        trend_window: Window for trend regime computation.
        trend_threshold: Return threshold for trend direction.

    Returns:
        CombinedRegimeMetadata with both regime labels and metadata.
    """
    log_returns = compute_log_returns(bars)

    vol_regime = compute_vol_regime(
        log_returns,
        window=vol_window,
        high_quantile=vol_high_quantile,
        source_start=0,
        source_end=len(bars),
    )

    trend_regime = compute_trend_regime(
        log_returns,
        window=trend_window,
        threshold=trend_threshold,
        source_start=0,
        source_end=len(bars),
    )

    return CombinedRegimeMetadata(vol_regime=vol_regime, trend_regime=trend_regime)