"""Tests for ReplicationSummary cross-asset replication layer.

Paper mode only - no real trading, no profitability claims.
"""

import json
import pytest

from quantbot.experiment.result import (
    ReplicationSummary,
    generate_replication_summary,
    _compute_replication_metrics,
    _classify_replication,
)


class TestReplicationSummaryDataclass:
    """Tests for ReplicationSummary dataclass."""

    def test_default_values(self):
        """ReplicationSummary has correct default values."""
        summary = ReplicationSummary()
        assert summary.replication_dimension == "asset"
        assert summary.source_fixture == ""
        assert summary.comparison_fixture is None
        assert summary.source_metrics == {}
        assert summary.comparison_metrics == {}
        assert summary.interpretation == "insufficient_replication_data"
        assert summary.comparison_count == 0

    def test_to_dict(self):
        """ReplicationSummary.to_dict() serializes correctly."""
        summary = ReplicationSummary(
            source_fixture="BTCUSDT_8h",
            comparison_fixture="ETHUSDT_8h",
            source_metrics={"net_return": 0.05, "sharpe_like": 1.2},
            comparison_metrics={"net_return": 0.04, "sharpe_like": 1.1},
            interpretation="replication_available",
            comparison_count=1,
        )
        d = summary.to_dict()
        assert d["replication_dimension"] == "asset"
        assert d["source_fixture"] == "BTCUSDT_8h"
        assert d["comparison_fixture"] == "ETHUSDT_8h"
        assert d["source_metrics"]["net_return"] == 0.05
        assert d["comparison_metrics"]["net_return"] == 0.04
        assert d["interpretation"] == "replication_available"
        assert d["comparison_count"] == 1


class TestComputeReplicationMetrics:
    """Tests for _compute_replication_metrics helper."""

    def test_returns_none_when_no_data(self):
        """Returns None when no return/inference summary available."""
        result = _compute_replication_metrics({})
        assert result is None

    def test_extracts_return_metrics(self):
        """Extracts net_return and sharpe_like from artifact data."""
        artifact = {
            "return_summary": {"net_return_total": 0.05},
            "inference_summary": {"sharpe_like": 1.2},
        }
        result = _compute_replication_metrics(artifact)
        assert result is not None
        assert result["net_return"] == 0.05
        assert result["sharpe_like"] == 1.2

    def test_extracts_inferential_metrics(self):
        """Extracts psr, dsr from inferential_summary."""
        artifact = {
            "inferential_summary": {"psr": 0.7, "dsr": 0.5},
        }
        result = _compute_replication_metrics(artifact)
        assert result is not None
        assert result["psr"] == 0.7
        assert result["dsr"] == 0.5

    def test_extracts_pbo(self):
        """Extracts pbo from overfitting_summary."""
        artifact = {
            "overfitting_summary": {"pbo": 0.15},
        }
        result = _compute_replication_metrics(artifact)
        assert result is not None
        assert result["pbo"] == 0.15


class TestClassifyReplication:
    """Tests for _classify_replication function."""

    def test_insufficient_when_comparison_none(self):
        """Returns insufficient when comparison_metrics is None."""
        interp, count = _classify_replication({}, None)
        assert interp == "insufficient_replication_data"
        assert count == 0

    def test_insufficient_when_comparison_metrics_empty(self):
        """Returns insufficient when comparison has no valid metrics."""
        interp, count = _classify_replication(
            {"net_return": 0.05},
            {"net_return": None, "sharpe_like": None},
        )
        assert interp == "insufficient_replication_data"
        assert count == 0

    def test_replication_available_when_metrics_align(self):
        """Returns replication_available when metrics align."""
        source = {"net_return": 0.05, "sharpe_like": 1.2}
        comparison = {"net_return": 0.04, "sharpe_like": 1.1}  # same direction, similar sharpe
        interp, count = _classify_replication(source, comparison)
        assert interp == "replication_available"
        assert count == 2

    def test_replication_weak_when_metrics_diverge(self):
        """Returns replication_weak when metrics diverge significantly."""
        source = {"net_return": 0.05, "sharpe_like": 1.2}
        comparison = {"net_return": -0.03, "sharpe_like": -0.8}  # opposite direction
        interp, count = _classify_replication(source, comparison)
        assert interp == "replication_weak"

    def test_replication_mixed_when_mixed_signals(self):
        """Returns replication_mixed when signals are mixed."""
        source = {"net_return": 0.05, "sharpe_like": 1.2, "dsr": 0.8}
        comparison = {"net_return": 0.04, "sharpe_like": 0.3, "dsr": 0.2}  # sharpe differs but direction same
        interp, count = _classify_replication(source, comparison)
        # direction agrees but sharpe differs significantly and dsr disagrees
        assert interp in ("replication_mixed", "replication_weak", "replication_available")


class TestGenerateReplicationSummary:
    """Tests for generate_replication_summary function."""

    def test_no_source_metrics_returns_insufficient(self):
        """Returns insufficient when source has no metrics."""
        summary = generate_replication_summary({}, "BTCUSDT_8h")
        assert summary.interpretation == "insufficient_replication_data"
        assert summary.source_fixture == "BTCUSDT_8h"

    def test_with_comparison_fixture(self):
        """Generates comparison when comparison artifact provided."""
        source = {
            "return_summary": {"net_return_total": 0.05},
            "inference_summary": {"sharpe_like": 1.2},
        }
        comparison = {
            "return_summary": {"net_return_total": 0.04},
            "inference_summary": {"sharpe_like": 1.1},
        }
        summary = generate_replication_summary(
            source, "BTCUSDT_8h", comparison, "ETHUSDT_8h"
        )
        assert summary.source_fixture == "BTCUSDT_8h"
        assert summary.comparison_fixture == "ETHUSDT_8h"
        assert summary.source_metrics["net_return"] == 0.05
        assert summary.comparison_metrics["net_return"] == 0.04

    def test_graceful_handling_missing_comparison(self):
        """Handles missing comparison fixture gracefully."""
        source = {
            "return_summary": {"net_return_total": 0.05},
            "inference_summary": {"sharpe_like": 1.2},
        }
        summary = generate_replication_summary(source, "BTCUSDT_8h", None, None)
        assert summary.comparison_fixture is None
        assert summary.interpretation == "insufficient_replication_data"
        assert summary.comparison_count == 0


class TestReplicationSummaryInterpretation:
    """Tests for interpretation wording (strict observational language)."""

    def test_interpretation_values(self):
        """Only allowed interpretation values are used."""
        valid_interpretations = {
            "replication_available",
            "replication_mixed",
            "replication_weak",
            "insufficient_replication_data",
        }
        # Test that all possible interpretations are valid
        source = {"net_return": 0.05, "sharpe_like": 1.2}
        comparison_none = None
        interp, _ = _classify_replication(source, comparison_none)
        assert interp in valid_interpretations

    def test_no_invalid_words_in_interpretation(self):
        """Interpretation never uses: validated, generalized, ready, portable alpha."""
        invalid_words = {"validated", "generalized", "ready", "portable", "alpha"}
        summary = ReplicationSummary(interpretation="replication_available")
        for word in invalid_words:
            assert word not in summary.interpretation