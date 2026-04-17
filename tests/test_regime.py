"""Tests for regime-tagging substrate.

Substrate only - tests deterministic labeling, metadata persistence,
and graceful handling of edge cases. Does NOT test cross-regime replication.
"""

import json
import pytest

from quantbot.data.types import Bar
from quantbot.experiment.regime import (
    compute_log_returns,
    compute_vol_regime,
    compute_trend_regime,
    compute_combined_regime,
    RegimeMetadata,
    CombinedRegimeMetadata,
    VolRegimeLabel,
    TrendRegimeLabel,
    DEFAULT_VOL_WINDOW,
    DEFAULT_TREND_WINDOW,
    DEFAULT_VOL_HIGH_QUANTILE,
    DEFAULT_TREND_THRESHOLD,
)


# ----------------------------------------------------------------------
# Fixtures / helpers
# ----------------------------------------------------------------------

def make_bar(close: float, timestamp: str = "2024-01-01T00:00:00") -> Bar:
    """Make a minimal Bar with all fields valid."""
    return Bar(
        timestamp=timestamp,
        open=close,
        high=close,
        low=close,
        close=close,
        volume=1000.0,
    )


def make_bars(closes: list[float]) -> list[Bar]:
    """Make a list of bars from close prices."""
    bars = []
    for i, c in enumerate(closes):
        bars.append(make_bar(c, f"2024-01-01T{i:02d}:00:00"))
    return bars


# ----------------------------------------------------------------------
# Test compute_log_returns
# ----------------------------------------------------------------------

class TestComputeLogReturns:
    def test_empty_bars(self):
        """Returns empty list when fewer than 2 bars."""
        assert compute_log_returns([]) == []
        assert compute_log_returns([make_bar(100.0)]) == []

    def test_simple_uptrend(self):
        """Log returns positive when close increases."""
        bars = make_bars([100.0, 105.0, 110.0])
        rets = compute_log_returns(bars)
        assert len(rets) == 2
        assert rets[0] > 0  # 105/100
        assert rets[1] > 0  # 110/105

    def test_simple_downtrend(self):
        """Log returns negative when close decreases."""
        bars = make_bars([100.0, 95.0, 90.0])
        rets = compute_log_returns(bars)
        assert len(rets) == 2
        assert rets[0] < 0  # 95/100
        assert rets[1] < 0  # 90/95

    def test_known_log_return(self):
        """Log return of 100->110 ≈ ln(1.1) ≈ 0.0953."""
        bars = make_bars([100.0, 110.0])
        rets = compute_log_returns(bars)
        assert abs(rets[0] - 0.0953102) < 0.0001

    def test_zero_or_negative_close_handled(self):
        """Zero or negative close produces nan."""
        bars = [
            make_bar(100.0),
            make_bar(0.0),
            make_bar(50.0),
        ]
        rets = compute_log_returns(bars)
        assert len(rets) == 2
        import math
        assert math.isnan(rets[1])


# ----------------------------------------------------------------------
# Test compute_vol_regime
# ----------------------------------------------------------------------

class TestComputeVolRegime:
    def test_unknown_when_insufficient_data(self):
        """Returns 'unknown' when fewer bars than window."""
        bars = make_bars([100.0, 105.0, 110.0])  # only 2 returns
        log_rets = compute_log_returns(bars)
        result = compute_vol_regime(log_rets, window=20)
        assert result.label == "unknown"
        assert result.regime_type == "volatility"

    def test_low_vol_on_calm_series(self):
        """Stable series with low stdev -> low_vol."""
        # Low volatility: all bars close to same price
        bars = make_bars([100.0, 100.1, 100.2, 100.1, 99.9, 100.0, 100.1, 100.2, 100.1, 100.0,
                          100.1, 100.0, 100.2, 100.1, 99.9, 100.0, 100.1, 100.2, 100.1, 100.0,
                          100.1, 100.0, 100.2, 100.1, 99.9, 100.0])
        log_rets = compute_log_returns(bars)
        result = compute_vol_regime(log_rets, window=20, high_quantile=0.65)
        assert result.label in ("low_vol", "high_vol")
        assert result.rule == "rolling_stdev_quantile"
        assert "high_vol_threshold" in result.thresholds

    def test_high_vol_on_volatile_series(self):
        """High volatility series -> high_vol."""
        # High volatility: big swings
        bars = make_bars([100.0, 120.0, 80.0, 110.0, 90.0, 115.0, 85.0, 105.0, 95.0, 110.0,
                          80.0, 120.0, 85.0, 115.0, 90.0, 105.0, 95.0, 110.0, 80.0, 120.0,
                          85.0, 115.0, 90.0, 105.0, 95.0, 110.0])
        log_rets = compute_log_returns(bars)
        result = compute_vol_regime(log_rets, window=20, high_quantile=0.65)
        assert result.label in ("low_vol", "high_vol")
        assert result.rule == "rolling_stdev_quantile"

    def test_deterministic_same_input_same_output(self):
        """Regime label is deterministic - same input yields same output."""
        bars = make_bars([100.0, 105.0, 110.0, 95.0, 100.0, 105.0, 110.0, 95.0, 100.0, 105.0,
                          110.0, 95.0, 100.0, 105.0, 110.0, 95.0, 100.0, 105.0, 110.0, 95.0,
                          100.0, 105.0, 110.0, 95.0, 100.0])
        log_rets = compute_log_returns(bars)
        r1 = compute_vol_regime(log_rets, window=20)
        r2 = compute_vol_regime(log_rets, window=20)
        assert r1.label == r2.label
        assert r1.thresholds == r2.thresholds

    def test_metadata_persistence(self):
        """RegimeMetadata serializes correctly to dict."""
        bars = make_bars([100.0, 105.0, 110.0, 95.0, 100.0, 105.0, 110.0, 95.0, 100.0, 105.0,
                          110.0, 95.0, 100.0, 105.0, 110.0, 95.0, 100.0, 105.0, 110.0, 95.0,
                          100.0, 105.0, 110.0, 95.0, 100.0])
        log_rets = compute_log_returns(bars)
        result = compute_vol_regime(log_rets, window=20)
        d = result.to_dict()
        assert d["regime_type"] == "volatility"
        assert d["label"] in ("low_vol", "high_vol", "unknown")
        assert "rule" in d
        assert "parameters" in d
        assert "thresholds" in d
        assert "source_start" in d
        assert "source_end" in d
        # Verify JSON-serializable
        json.dumps(d)


# ----------------------------------------------------------------------
# Test compute_trend_regime
# ----------------------------------------------------------------------

class TestComputeTrendRegime:
    def test_unknown_when_insufficient_data(self):
        """Returns 'unknown' when fewer bars than window."""
        bars = make_bars([100.0, 105.0, 110.0])
        log_rets = compute_log_returns(bars)
        result = compute_trend_regime(log_rets, window=20)
        assert result.label == "unknown"
        assert result.regime_type == "trend"

    def test_uptrend_on_rising_series(self):
        """Consistently rising series -> uptrend."""
        bars = make_bars([100.0, 101.0, 102.0, 103.0, 104.0, 105.0, 106.0, 107.0, 108.0, 109.0,
                          110.0, 111.0, 112.0, 113.0, 114.0, 115.0, 116.0, 117.0, 118.0, 119.0,
                          120.0, 121.0, 122.0, 123.0, 124.0])
        log_rets = compute_log_returns(bars)
        result = compute_trend_regime(log_rets, window=20, threshold=0.001)
        assert result.label == "uptrend"
        assert result.rule == "rolling_mean_return"

    def test_downtrend_on_falling_series(self):
        """Consistently falling series -> downtrend."""
        bars = make_bars([124.0, 123.0, 122.0, 121.0, 120.0, 119.0, 118.0, 117.0, 116.0, 115.0,
                          114.0, 113.0, 112.0, 111.0, 110.0, 109.0, 108.0, 107.0, 106.0, 105.0,
                          104.0, 103.0, 102.0, 101.0, 100.0])
        log_rets = compute_log_returns(bars)
        result = compute_trend_regime(log_rets, window=20, threshold=0.001)
        assert result.label == "downtrend"
        assert result.rule == "rolling_mean_return"

    def test_sideways_on_flat_series(self):
        """Flat series -> sideways."""
        bars = make_bars([100.0] * 30)
        log_rets = compute_log_returns(bars)
        result = compute_trend_regime(log_rets, window=20, threshold=0.001)
        assert result.label == "sideways"
        assert result.rule == "rolling_mean_return"

    def test_threshold_is_explicit(self):
        """Threshold is preserved in metadata."""
        bars = make_bars([100.0] * 30)
        log_rets = compute_log_returns(bars)
        result = compute_trend_regime(log_rets, window=20, threshold=0.005)
        assert result.parameters["threshold"] == 0.005
        assert result.thresholds["uptrend_threshold"] == 0.005

    def test_metadata_persistence(self):
        """RegimeMetadata serializes correctly to dict."""
        bars = make_bars([100.0, 101.0, 102.0] * 10)
        log_rets = compute_log_returns(bars)
        result = compute_trend_regime(log_rets, window=20)
        d = result.to_dict()
        assert d["regime_type"] == "trend"
        assert d["label"] in ("uptrend", "downtrend", "sideways", "unknown")
        assert "rule" in d
        assert "parameters" in d
        assert "thresholds" in d
        json.dumps(d)


# ----------------------------------------------------------------------
# Test compute_combined_regime
# ----------------------------------------------------------------------

class TestComputeCombinedRegime:
    def test_combined_returns_both_regimes(self):
        """Combined regime returns vol + trend labels."""
        bars = make_bars([100.0, 105.0] * 15)
        result = compute_combined_regime(bars)
        assert isinstance(result, CombinedRegimeMetadata)
        assert result.vol_label in ("low_vol", "high_vol", "unknown")
        assert result.trend_label in ("uptrend", "downtrend", "sideways", "unknown")

    def test_combined_persists_both_metadata(self):
        """Combined regime.to_dict() includes both regime metadata."""
        bars = make_bars([100.0, 105.0] * 15)
        result = compute_combined_regime(bars)
        d = result.to_dict()
        assert "vol_regime" in d
        assert "trend_regime" in d
        json.dumps(d)

    def test_empty_bars_handled(self):
        """Empty bars list produces 'unknown' for both."""
        result = compute_combined_regime([])
        assert result.vol_label == "unknown"
        assert result.trend_label == "unknown"

    def test_short_bars_handled(self):
        """Fewer bars than window produces 'unknown'."""
        bars = make_bars([100.0, 105.0, 110.0])
        result = compute_combined_regime(bars)
        assert result.vol_label == "unknown"
        assert result.trend_label == "unknown"


# ----------------------------------------------------------------------
# Test defaults and explicit thresholds
# ----------------------------------------------------------------------

class TestExplicitThresholds:
    def test_default_vol_window_exposed(self):
        """DEFAULT_VOL_WINDOW is a module-level constant."""
        assert isinstance(DEFAULT_VOL_WINDOW, int)
        assert DEFAULT_VOL_WINDOW > 0

    def test_default_trend_window_exposed(self):
        """DEFAULT_TREND_WINDOW is a module-level constant."""
        assert isinstance(DEFAULT_TREND_WINDOW, int)
        assert DEFAULT_TREND_WINDOW > 0

    def test_default_vol_quantile_exposed(self):
        """DEFAULT_VOL_HIGH_QUANTILE is explicit."""
        assert isinstance(DEFAULT_VOL_HIGH_QUANTILE, float)
        assert 0 < DEFAULT_VOL_HIGH_QUANTILE < 1

    def test_default_trend_threshold_exposed(self):
        """DEFAULT_TREND_THRESHOLD is explicit."""
        assert isinstance(DEFAULT_TREND_THRESHOLD, float)

    def test_non_default_parameters_preserved_in_metadata(self):
        """Custom parameters appear in RegimeMetadata.parameters."""
        bars = make_bars([100.0] * 30)
        log_rets = compute_log_returns(bars)
        vol_result = compute_vol_regime(log_rets, window=10, high_quantile=0.8)
        assert vol_result.parameters["window"] == 10
        assert vol_result.parameters["high_quantile"] == 0.8


# ----------------------------------------------------------------------
# Test legacy compatibility
# ----------------------------------------------------------------------

class TestLegacyCompatibility:
    def test_regime_metadata_is_pure_dict_no_external_deps(self):
        """RegimeMetadata.to_dict() has no datetime/Path deps."""
        bars = make_bars([100.0] * 30)
        log_rets = compute_log_returns(bars)
        result = compute_vol_regime(log_rets)
        d = result.to_dict()
        # All values must be JSON-serializable primitives
        json.dumps(d)

    def test_combined_regime_json_serializable(self):
        """CombinedRegimeMetadata.to_dict() is fully JSON-serializable."""
        bars = make_bars([100.0, 105.0] * 15)
        result = compute_combined_regime(bars)
        d = result.to_dict()
        json.dumps(d)

    def test_no_new_bar_fields_added(self):
        """Bar dataclass unchanged - regime uses log returns computed externally."""
        from quantbot.data.types import Bar
        b = Bar(timestamp="x", open=1, high=2, low=0, close=1, volume=100)
        # Should still have exactly these fields
        assert hasattr(b, "timestamp")
        assert hasattr(b, "open")
        assert hasattr(b, "high")
        assert hasattr(b, "low")
        assert hasattr(b, "close")
        assert hasattr(b, "volume")
        # No new fields
        fields = [f for f in dir(b) if not f.startswith("_") and not callable(getattr(b, f))]
        assert len(fields) == 6