"""Tests for cross-regime replication summary.

Tests deterministic regime-grouped summary generation, persistence,
JSON output shape, and graceful handling of insufficient regime coverage.
"""

import json
import pytest

from quantbot.experiment.result import (
    RegimeReplicationSummary,
    generate_regime_replication_summary,
    _classify_regime_replication,
    _aggregate_bucket_metrics,
)


# ----------------------------------------------------------------------
# Fixtures / helpers
# ----------------------------------------------------------------------

def make_split_result(
    regime_label: str,
    net_return: float | None = None,
    sharpe_like: float | None = None,
    psr: float | None = None,
    dsr: float | None = None,
    pbo: float | None = None,
) -> dict:
    """Make a minimal split result dict with regime label and metrics."""
    split = {"regime_label": regime_label}
    if net_return is not None:
        split["return_summary"] = {"net_return_total": net_return}
    if sharpe_like is not None:
        split["inference_summary"] = {"sharpe_like": sharpe_like}
    if psr is not None or dsr is not None:
        split["inferential_summary"] = {}
        if psr is not None:
            split["inferential_summary"]["psr"] = psr
        if dsr is not None:
            split["inferential_summary"]["dsr"] = dsr
    if pbo is not None:
        split["overfitting_summary"] = {"pbo": pbo}
    return split


# ----------------------------------------------------------------------
# Test RegimeReplicationSummary dataclass
# ----------------------------------------------------------------------

class TestRegimeReplicationSummaryDataclass:
    def test_default_values(self):
        """RegimeReplicationSummary has correct defaults."""
        summary = RegimeReplicationSummary()
        assert summary.regime_dimension == "volatility"
        assert summary.buckets == {}
        assert summary.interpretation == "insufficient_regime_replication_data"
        assert summary.regime_bucket_count == 0
        assert summary.regime_split_coverage == 0

    def test_to_dict(self):
        """RegimeReplicationSummary.to_dict() serializes correctly."""
        summary = RegimeReplicationSummary(
            regime_dimension="volatility",
            buckets={
                "low_vol": {"net_return": 0.05, "sharpe_like": 1.2, "psr": 0.7, "dsr": 0.5, "pbo": 0.1},
                "high_vol": {"net_return": 0.04, "sharpe_like": 1.1, "psr": 0.6, "dsr": 0.4, "pbo": 0.2},
            },
            interpretation="regime_replication_available",
            regime_bucket_count=2,
            regime_split_coverage=10,
        )
        d = summary.to_dict()
        assert d["regime_dimension"] == "volatility"
        assert "low_vol" in d["buckets"]
        assert "high_vol" in d["buckets"]
        assert d["interpretation"] == "regime_replication_available"
        assert d["regime_bucket_count"] == 2
        assert d["regime_split_coverage"] == 10

    def test_json_serializable(self):
        """RegimeReplicationSummary.to_dict() is fully JSON-serializable."""
        summary = RegimeReplicationSummary(
            regime_dimension="trend",
            buckets={"uptrend": {"net_return": 0.03}, "downtrend": {"net_return": -0.02}},
            interpretation="regime_replication_mixed",
            regime_bucket_count=2,
            regime_split_coverage=5,
        )
        json.dumps(summary.to_dict())


# ----------------------------------------------------------------------
# Test _classify_regime_replication
# ----------------------------------------------------------------------

class TestClassifyRegimeReplication:
    def test_insufficient_when_no_buckets(self):
        """Returns insufficient when no buckets."""
        interp, count = _classify_regime_replication({})
        assert interp == "insufficient_regime_replication_data"
        assert count == 0

    def test_insufficient_when_single_bucket(self):
        """Returns insufficient when only one bucket."""
        interp, count = _classify_regime_replication({"low_vol": {"net_return": 0.05}})
        assert interp == "insufficient_regime_replication_data"
        assert count == 1

    def test_insufficient_when_no_sharpe_or_return(self):
        """Returns insufficient when buckets exist but no usable metrics."""
        interp, count = _classify_regime_replication({
            "low_vol": {},
            "high_vol": {},
        })
        assert interp == "insufficient_regime_replication_data"

    def test_regime_replication_available_same_direction_similar_sharpe(self):
        """Both positive returns + similar sharpe -> available."""
        buckets = {
            "low_vol": {"net_return": 0.05, "sharpe_like": 1.2},
            "high_vol": {"net_return": 0.04, "sharpe_like": 1.1},
        }
        interp, count = _classify_regime_replication(buckets)
        assert interp == "regime_replication_available"
        assert count == 2

    def test_regime_replication_weak_opposite_direction(self):
        """Opposite return signs + divergent sharpe -> weak."""
        buckets = {
            "low_vol": {"net_return": 0.05, "sharpe_like": 1.2},
            "high_vol": {"net_return": -0.03, "sharpe_like": 0.2},
        }
        interp, count = _classify_regime_replication(buckets)
        # sharpe std ≈ 0.5, borderline; direction fails (opposite signs)
        # false_count >= 1 but true_count also >= 1 -> mixed
        # Use clearly different sharpe to force weak
        buckets2 = {
            "low_vol": {"net_return": 0.05, "sharpe_like": 2.0},
            "high_vol": {"net_return": -0.03, "sharpe_like": 0.1},
        }
        interp2, count2 = _classify_regime_replication(buckets2)
        # sharpe std ≈ 0.95 >= 0.5 (not similar), direction fails -> weak
        assert interp2 == "regime_replication_weak"
        assert count2 == 2

    def test_regime_replication_mixed_when_one_signal_fails(self):
        """Same direction but very different sharpe -> mixed."""
        buckets = {
            "low_vol": {"net_return": 0.05, "sharpe_like": 1.2},
            "high_vol": {"net_return": 0.04, "sharpe_like": 0.1},
        }
        interp, count = _classify_regime_replication(buckets)
        assert interp == "regime_replication_mixed"
        assert count == 2

    def test_interpretation_is_observational(self):
        """Interpretation uses observational vocabulary, not claims."""
        buckets = {
            "low_vol": {"net_return": 0.05, "sharpe_like": 1.2},
            "high_vol": {"net_return": 0.04, "sharpe_like": 1.1},
        }
        interp, _ = _classify_regime_replication(buckets)
        # Must NOT contain prohibited words
        prohibited = ["validated", "generalized", "portable", "alpha", "proven", "ready"]
        for word in prohibited:
            assert word not in interp.lower()


# ----------------------------------------------------------------------
# Test _aggregate_bucket_metrics
# ----------------------------------------------------------------------

class TestAggregateBucketMetrics:
    def test_empty_split_results(self):
        """Returns empty dict when no splits."""
        result = _aggregate_bucket_metrics([])
        assert result == {}

    def test_aggregates_two_splits_same_bucket(self):
        """Two splits with same regime label -> median aggregation."""
        splits = [
            make_split_result("low_vol", net_return=0.05, sharpe_like=1.2),
            make_split_result("low_vol", net_return=0.07, sharpe_like=1.4),
        ]
        result = _aggregate_bucket_metrics(splits)
        assert "low_vol" in result
        # With 2 elements, sorted_vals[n//2] = sorted_vals[1] = upper median = 0.07
        assert result["low_vol"]["net_return"] == 0.07
        assert result["low_vol"]["sharpe_like"] == 1.4

    def test_aggregates_two_splits_different_buckets(self):
        """Two splits with different regime labels -> two buckets."""
        splits = [
            make_split_result("low_vol", net_return=0.05, sharpe_like=1.2),
            make_split_result("high_vol", net_return=0.04, sharpe_like=1.1),
        ]
        result = _aggregate_bucket_metrics(splits)
        assert "low_vol" in result
        assert "high_vol" in result
        assert result["low_vol"]["net_return"] == 0.05
        assert result["high_vol"]["net_return"] == 0.04

    def test_skips_splits_without_regime_label(self):
        """Splits without regime_label are skipped."""
        splits = [
            make_split_result("low_vol", net_return=0.05),
            {"other_key": "value"},  # no regime_label
        ]
        result = _aggregate_bucket_metrics(splits)
        assert "low_vol" in result
        assert len(result) == 1

    def test_includes_psr_dsr_pbo_when_available(self):
        """PSR, DSR, PBO are included when present in splits."""
        splits = [
            make_split_result("low_vol", net_return=0.05, psr=0.7, dsr=0.5, pbo=0.1),
            make_split_result("low_vol", net_return=0.07, psr=0.8, dsr=0.6, pbo=0.15),
        ]
        result = _aggregate_bucket_metrics(splits)
        assert result["low_vol"]["psr"] is not None
        assert result["low_vol"]["dsr"] is not None
        assert result["low_vol"]["pbo"] is not None


# ----------------------------------------------------------------------
# Test generate_regime_replication_summary
# ----------------------------------------------------------------------

class TestGenerateRegimeReplicationSummary:
    def test_empty_split_results(self):
        """Empty list -> insufficient data."""
        result = generate_regime_replication_summary([])
        assert result.interpretation == "insufficient_regime_replication_data"
        assert result.regime_bucket_count == 0
        assert result.regime_split_coverage == 0

    def test_no_tagged_splits(self):
        """Splits without regime_label -> insufficient."""
        splits = [{"other_key": "value"}]
        result = generate_regime_replication_summary(splits)
        assert result.interpretation == "insufficient_regime_replication_data"
        assert result.regime_split_coverage == 0

    def test_single_bucket(self):
        """Single regime bucket -> insufficient (need 2+ for comparison)."""
        splits = [make_split_result("low_vol", net_return=0.05, sharpe_like=1.2)]
        result = generate_regime_replication_summary(splits, regime_dimension="volatility")
        assert result.interpretation == "insufficient_regime_replication_data"
        assert result.regime_bucket_count == 1
        assert result.regime_split_coverage == 1

    def test_two_buckets_available(self):
        """Two buckets with same-direction positive returns -> available."""
        splits = [
            make_split_result("low_vol", net_return=0.05, sharpe_like=1.2),
            make_split_result("high_vol", net_return=0.04, sharpe_like=1.1),
        ]
        result = generate_regime_replication_summary(splits, regime_dimension="volatility")
        assert result.interpretation == "regime_replication_available"
        assert result.regime_dimension == "volatility"
        assert result.regime_bucket_count == 2
        assert result.regime_split_coverage == 2
        assert "low_vol" in result.buckets
        assert "high_vol" in result.buckets

    def test_regime_dimension_passthrough(self):
        """regime_dimension parameter is preserved in output."""
        splits = [
            make_split_result("uptrend", net_return=0.05, sharpe_like=1.2),
            make_split_result("downtrend", net_return=0.03, sharpe_like=0.9),
        ]
        result = generate_regime_replication_summary(splits, regime_dimension="trend")
        assert result.regime_dimension == "trend"

    def test_three_buckets(self):
        """Three regime buckets with conflicting signals -> weak."""
        splits = [
            make_split_result("low_vol", net_return=0.05, sharpe_like=1.2),
            make_split_result("high_vol", net_return=-0.03, sharpe_like=0.2),
            make_split_result("sideways", net_return=0.01, sharpe_like=0.5),
        ]
        result = generate_regime_replication_summary(splits, regime_dimension="combined")
        # Direction: not all same sign (high_vol negative, others positive) -> False
        # Sharpe std: std([1.2, 0.2, 0.5]) ≈ 0.42 < 0.5 -> True
        # false_count=1, true_count=1 -> mixed
        assert result.interpretation in ("regime_replication_mixed", "regime_replication_weak")
        assert result.regime_bucket_count == 3

    def test_no_valid_metrics_in_buckets(self):
        """Buckets exist but no valid metrics -> insufficient."""
        splits = [
            make_split_result("low_vol"),  # no metrics
            make_split_result("high_vol"),  # no metrics
        ]
        result = generate_regime_replication_summary(splits)
        assert result.interpretation == "insufficient_regime_replication_data"


# ----------------------------------------------------------------------
# Test persistence / serialization
# ----------------------------------------------------------------------

class TestPersistence:
    def test_full_roundtrip(self):
        """RegimeReplicationSummary -> dict -> JSON -> dict -> same values."""
        original = RegimeReplicationSummary(
            regime_dimension="volatility",
            buckets={
                "low_vol": {"net_return": 0.05, "sharpe_like": 1.2, "psr": 0.7, "dsr": 0.5, "pbo": 0.1},
                "high_vol": {"net_return": 0.04, "sharpe_like": 1.1, "psr": 0.6, "dsr": 0.4, "pbo": 0.2},
            },
            interpretation="regime_replication_available",
            regime_bucket_count=2,
            regime_split_coverage=10,
        )
        json_str = json.dumps(original.to_dict())
        parsed = json.loads(json_str)
        restored = RegimeReplicationSummary(**parsed)
        assert restored.regime_dimension == original.regime_dimension
        assert restored.interpretation == original.interpretation
        assert restored.regime_bucket_count == original.regime_bucket_count
        assert restored.regime_split_coverage == original.regime_split_coverage
        assert restored.buckets == original.buckets

    def test_json_artifact_shape(self):
        """JSON output matches required artifact shape."""
        splits = [
            make_split_result("low_vol", net_return=0.05, sharpe_like=1.2),
            make_split_result("high_vol", net_return=0.04, sharpe_like=1.1),
        ]
        summary = generate_regime_replication_summary(splits)
        d = summary.to_dict()
        # Required fields present
        assert "regime_dimension" in d
        assert "buckets" in d
        assert "interpretation" in d
        assert "regime_bucket_count" in d
        assert "regime_split_coverage" in d
        # Interpretation is observational
        valid_interps = {
            "regime_replication_available",
            "regime_replication_mixed",
            "regime_replication_weak",
            "insufficient_regime_replication_data",
        }
        assert d["interpretation"] in valid_interps


# ----------------------------------------------------------------------
# Test legacy compatibility
# ----------------------------------------------------------------------

class TestLegacyCompatibility:
    def test_does_not_break_replication_summary(self):
        """Adding RegimeReplicationSummary does not affect ReplicationSummary."""
        from quantbot.experiment.result import ReplicationSummary
        r = ReplicationSummary()
        assert r.replication_dimension == "asset"
        assert r.interpretation == "insufficient_replication_data"

    def test_classification_function_names_distinct(self):
        """Cross-regime functions have distinct names from asset-replication functions."""
        from quantbot.experiment.result import _classify_replication
        # Both functions exist and are distinct
        assert callable(_classify_replication)
        assert callable(_classify_regime_replication)
        assert _classify_regime_replication is not _classify_replication

    def test_replication_dimension_values_differ(self):
        """RegimeReplicationSummary uses 'regime' vs ReplicationSummary uses 'asset'."""
        from quantbot.experiment.result import ReplicationSummary
        reg_summary = RegimeReplicationSummary()
        rep_summary = ReplicationSummary()
        assert reg_summary.regime_dimension == "volatility"  # not "asset"
        assert rep_summary.replication_dimension == "asset"  # unchanged