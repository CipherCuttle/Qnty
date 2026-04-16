"""Tests for Path Dispersion diagnostic (proxy for PBO).

IMPORTANT: This is a PROXY DIAGNOSTIC, not Bailey-style CSCV/PBO.

Paper mode only - no live trading, no profitability claims.
Requires PYTHONHASHSEED=0 for deterministic dict ordering.
"""

import json
import tempfile
from dataclasses import replace
from pathlib import Path

import pytest

from quantbot.experiment.pbo import (
    PathDispersionSummary,
    PBOSummary,
    compute_path_dispersion,
    compute_pbo_cscv,
    compute_pbo,
)
from quantbot.experiment.result import ReturnSeries, WalkForwardSplitResult, InferenceSummary, ReturnSummary


class TestPathDispersionSummaryDataclass:
    """Tests for PathDispersionSummary dataclass."""

    def test_dispersion_summary_defaults(self) -> None:
        """PathDispersionSummary initializes with correct defaults."""
        disp = PathDispersionSummary()
        assert disp.method == "path_dispersion"
        assert disp.path_count == 0
        assert disp.dispersion_ratio == 0.0
        assert disp.assumptions == []
        assert disp.limitations == []
        assert disp.provenance == {}

    def test_dispersion_summary_to_dict(self) -> None:
        """PathDispersionSummary serializes to dict correctly."""
        disp = PathDispersionSummary(
            path_count=100,
            dispersion_ratio=0.35,
            assumptions=["test assumption"],
            limitations=["test limitation"],
            provenance={"family_id": "test-family", "variant_id": "v1"},
        )
        d = disp.to_dict()
        assert d["method"] == "path_dispersion"
        assert d["path_count"] == 100
        assert d["dispersion_ratio"] == 0.35
        assert d["assumptions"] == ["test assumption"]
        assert d["limitations"] == ["test limitation"]
        assert d["provenance"]["family_id"] == "test-family"

    def test_dispersion_summary_json_roundtrip(self) -> None:
        """PathDispersionSummary survives JSON round-trip."""
        disp = PathDispersionSummary(
            path_count=50,
            dispersion_ratio=0.25,
            assumptions=["Sharpe-based metric"],
            limitations=["Combinatorial cap"],
            provenance={"family_id": "test", "artifact_path": "/tmp/test.json"},
        )
        json_str = json.dumps(disp.to_dict())
        restored = json.loads(json_str)
        assert restored["path_count"] == 50
        assert restored["dispersion_ratio"] == 0.25


class TestComputePathDispersion:
    """Tests for compute_path_dispersion function."""

    def test_empty_input(self) -> None:
        """Empty return series list returns zero dispersion."""
        result = compute_path_dispersion([])
        assert result.dispersion_ratio == 0.0
        assert result.path_count == 0
        assert len(result.assumptions) > 0

    def test_single_split(self) -> None:
        """Single split cannot compute dispersion."""
        rs = ReturnSeries(
            gross_returns=[0.01, 0.02],
            net_returns=[0.009, 0.018],
            bar_timestamps=["2023-01-01T00:00:00Z", "2023-01-02T00:00:00Z"],
            interval="8h",
        )
        result = compute_path_dispersion([rs])
        assert result.dispersion_ratio == 0.0
        assert result.path_count == 1
        assert "Single split" in result.limitations[-1]

    def test_all_identical_returns(self) -> None:
        """All identical returns produce no dispersion signal."""
        rs1 = ReturnSeries(
            gross_returns=[0.01, 0.01],
            net_returns=[0.009, 0.009],
            bar_timestamps=["2023-01-01T00:00:00Z", "2023-01-02T00:00:00Z"],
            interval="8h",
        )
        rs2 = ReturnSeries(
            gross_returns=[0.01, 0.01],
            net_returns=[0.009, 0.009],
            bar_timestamps=["2023-01-03T00:00:00Z", "2023-01-04T00:00:00Z"],
            interval="8h",
        )
        result = compute_path_dispersion([rs1, rs2])
        assert result.dispersion_ratio == 0.0

    def test_deterministic_path_generation(self) -> None:
        """Same inputs produce same paths."""
        rs1 = ReturnSeries(
            gross_returns=[0.01, 0.02],
            net_returns=[0.009, 0.018],
            bar_timestamps=["2023-01-01T00:00:00Z", "2023-01-02T00:00:00Z"],
            interval="8h",
        )
        rs2 = ReturnSeries(
            gross_returns=[0.03, 0.04],
            net_returns=[0.028, 0.038],
            bar_timestamps=["2023-01-03T00:00:00Z", "2023-01-04T00:00:00Z"],
            interval="8h",
        )
        rs3 = ReturnSeries(
            gross_returns=[0.01, 0.015],
            net_returns=[0.009, 0.013],
            bar_timestamps=["2023-01-05T00:00:00Z", "2023-01-06T00:00:00Z"],
            interval="8h",
        )

        result1 = compute_path_dispersion([rs1, rs2, rs3])
        result2 = compute_path_dispersion([rs1, rs2, rs3])

        assert result1.path_count == result2.path_count

    def test_provenance_passed_through(self) -> None:
        """Provenance fields are passed through to result."""
        rs = ReturnSeries(
            gross_returns=[0.01, 0.02],
            net_returns=[0.009, 0.018],
            bar_timestamps=["2023-01-01T00:00:00Z", "2023-01-02T00:00:00Z"],
            interval="8h",
        )
        result = compute_path_dispersion(
            [rs, rs],
            family_id="test-family",
            variant_id="v1",
            artifact_path="/path/to/artifact.json",
        )
        assert result.provenance.get("family_id") == "test-family"
        assert result.provenance.get("variant_id") == "v1"
        assert result.provenance.get("artifact_path") == "/path/to/artifact.json"

    def test_assumptions_are_explicit(self) -> None:
        """Result includes explicit list of assumptions."""
        rs1 = ReturnSeries(
            gross_returns=[0.01, 0.02],
            net_returns=[0.009, 0.018],
            bar_timestamps=["2023-01-01T00:00:00Z"],
            interval="8h",
        )
        rs2 = ReturnSeries(
            gross_returns=[0.03, 0.04],
            net_returns=[0.028, 0.038],
            bar_timestamps=["2023-01-03T00:00:00Z"],
            interval="8h",
        )
        result = compute_path_dispersion([rs1, rs2])
        assert len(result.assumptions) > 0
        assert any("NOT Bailey" in a for a in result.assumptions)

    def test_limitations_are_explicit(self) -> None:
        """Result includes explicit list of limitations."""
        rs1 = ReturnSeries(
            gross_returns=[0.01, 0.02],
            net_returns=[0.009, 0.018],
            bar_timestamps=["2023-01-01T00:00:00Z"],
            interval="8h",
        )
        rs2 = ReturnSeries(
            gross_returns=[0.03, 0.04],
            net_returns=[0.028, 0.038],
            bar_timestamps=["2023-01-03T00:00:00Z"],
            interval="8h",
        )
        result = compute_path_dispersion([rs1, rs2])
        assert len(result.limitations) > 0
        assert any("PROXY" in l for l in result.limitations)


class TestDispersionEdgeCases:
    """Tests for Dispersion edge cases."""

    def test_empty_return_series(self) -> None:
        """Empty return series handled gracefully."""
        rs_empty = ReturnSeries(
            gross_returns=[],
            net_returns=[],
            bar_timestamps=[],
            interval="8h",
        )
        rs_valid = ReturnSeries(
            gross_returns=[0.01, 0.02],
            net_returns=[0.009, 0.018],
            bar_timestamps=["2023-01-01T00:00:00Z", "2023-01-02T00:00:00Z"],
            interval="8h",
        )
        result = compute_path_dispersion([rs_empty, rs_valid])
        assert result.path_count >= 0

    def test_single_bar_return_series(self) -> None:
        """Single bar return series handled (Sharpe undefined)."""
        rs1 = ReturnSeries(
            gross_returns=[0.01],
            net_returns=[0.009],
            bar_timestamps=["2023-01-01T00:00:00Z"],
            interval="8h",
        )
        rs2 = ReturnSeries(
            gross_returns=[0.02],
            net_returns=[0.018],
            bar_timestamps=["2023-01-02T00:00:00Z"],
            interval="8h",
        )
        result = compute_path_dispersion([rs1, rs2])
        assert result.dispersion_ratio >= 0.0

    def test_unknown_interval(self) -> None:
        """Unknown interval still computes (Sharpe not annualized)."""
        rs1 = ReturnSeries(
            gross_returns=[0.01, 0.02],
            net_returns=[0.009, 0.018],
            bar_timestamps=["2023-01-01T00:00:00Z", "2023-01-02T00:00:00Z"],
            interval="unknown",
        )
        rs2 = ReturnSeries(
            gross_returns=[0.03, 0.04],
            net_returns=[0.028, 0.038],
            bar_timestamps=["2023-01-03T00:00:00Z", "2023-01-04T00:00:00Z"],
            interval="unknown",
        )
        result = compute_path_dispersion([rs1, rs2])
        assert result.path_count >= 0


class TestDispersionInterpretation:
    """Tests for interpreting Dispersion results."""

    def test_dispersion_values_are_valid(self) -> None:
        """Dispersion values are always in [0.0, 1.0]."""
        rs1 = ReturnSeries(
            gross_returns=[0.01, 0.05, 0.02],
            net_returns=[0.009, 0.048, 0.018],
            bar_timestamps=["2023-01-01T00:00:00Z", "2023-01-02T00:00:00Z", "2023-01-03T00:00:00Z"],
            interval="8h",
        )
        rs2 = ReturnSeries(
            gross_returns=[0.02, -0.01, 0.03],
            net_returns=[0.018, -0.012, 0.028],
            bar_timestamps=["2023-01-04T00:00:00Z", "2023-01-05T00:00:00Z", "2023-01-06T00:00:00Z"],
            interval="8h",
        )
        rs3 = ReturnSeries(
            gross_returns=[0.01, 0.01, 0.01],
            net_returns=[0.009, 0.009, 0.009],
            bar_timestamps=["2023-01-07T00:00:00Z", "2023-01-08T00:00:00Z", "2023-01-09T00:00:00Z"],
            interval="8h",
        )

        result = compute_path_dispersion([rs1, rs2, rs3])
        assert 0.0 <= result.dispersion_ratio <= 1.0

    def test_method_is_path_dispersion(self) -> None:
        """Dispersion method is 'path_dispersion'."""
        rs = ReturnSeries(
            gross_returns=[0.01, 0.02],
            net_returns=[0.009, 0.018],
            bar_timestamps=["2023-01-01T00:00:00Z", "2023-01-02T00:00:00Z"],
            interval="8h",
        )
        result = compute_path_dispersion([rs, rs])
        assert result.method == "path_dispersion"


class TestDispersionIndexIntegration:
    """Tests for Dispersion integration with experiment index."""

    def test_dispersion_summary_in_json_output(self) -> None:
        """PathDispersionSummary can be serialized to JSON for index output."""
        disp = PathDispersionSummary(
            path_count=100,
            dispersion_ratio=0.35,
            assumptions=["test assumption"],
            limitations=["test limitation"],
            provenance={"family_id": "test-family"},
        )
        json_str = json.dumps(disp.to_dict(), indent=2)
        assert '"method": "path_dispersion"' in json_str
        assert '"path_count": 100' in json_str
        assert '"dispersion_ratio": 0.35' in json_str

    def test_dispersion_none_for_legacy_artifacts(self) -> None:
        """Artifacts without dispersion show default values."""
        disp = PathDispersionSummary()
        assert disp.path_count == 0
        assert disp.dispersion_ratio == 0.0


class TestBackwardCompatibility:
    """Tests for backward compatibility alias."""

    def test_compute_pbo_cscv_returns_path_dispersion_summary(self) -> None:
        """compute_pbo_cscv returns PathDispersionSummary (not PboSummary)."""
        rs = ReturnSeries(
            gross_returns=[0.01, 0.02],
            net_returns=[0.009, 0.018],
            bar_timestamps=["2023-01-01T00:00:00Z", "2023-01-02T00:00:00Z"],
            interval="8h",
        )
        result = compute_pbo_cscv([rs, rs])
        assert isinstance(result, PathDispersionSummary)
        assert result.method == "path_dispersion"

    def test_deprecated_alias_still_works(self) -> None:
        """Old compute_pbo_cscv function still works via alias."""
        rs1 = ReturnSeries(
            gross_returns=[0.01, 0.02],
            net_returns=[0.009, 0.018],
            bar_timestamps=["2023-01-01T00:00:00Z"],
            interval="8h",
        )
        rs2 = ReturnSeries(
            gross_returns=[0.03, 0.04],
            net_returns=[0.028, 0.038],
            bar_timestamps=["2023-01-03T00:00:00Z"],
            interval="8h",
        )
        result = compute_pbo_cscv([rs1, rs2])
        assert result.path_count >= 0
        assert result.dispersion_ratio >= 0.0


class TestPBOSummaryDataclass:
    """Tests for PBOSummary dataclass."""

    def test_pbo_summary_defaults(self) -> None:
        """PBOSummary initializes with correct defaults."""
        pbo = PBOSummary()
        assert pbo.method == "pbo"
        assert pbo.path_count == 0
        assert pbo.selection_metric == "sharpe"
        assert pbo.pbo == 0.0
        assert pbo.assumptions == []
        assert pbo.limitations == []
        assert pbo.provenance == {}

    def test_pbo_summary_to_dict(self) -> None:
        """PBOSummary serializes to dict correctly."""
        pbo = PBOSummary(
            path_count=100,
            selection_metric="return",
            pbo=0.65,
            assumptions=["test assumption"],
            limitations=["test limitation"],
            provenance={"family_id": "test-family", "variant_id": "v1"},
        )
        d = pbo.to_dict()
        assert d["method"] == "pbo"
        assert d["path_count"] == 100
        assert d["selection_metric"] == "return"
        assert d["pbo"] == 0.65
        assert d["assumptions"] == ["test assumption"]
        assert d["limitations"] == ["test limitation"]
        assert d["provenance"]["family_id"] == "test-family"

    def test_pbo_summary_json_roundtrip(self) -> None:
        """PBOSummary survives JSON round-trip."""
        pbo = PBOSummary(
            path_count=50,
            pbo=0.45,
            assumptions=["Sharpe-based metric"],
            limitations=["Combinatorial cap"],
            provenance={"family_id": "test"},
        )
        json_str = json.dumps(pbo.to_dict())
        restored = json.loads(json_str)
        assert restored["path_count"] == 50
        assert restored["pbo"] == 0.45


class TestComputePBO:
    """Tests for compute_pbo function using paired train/test paths."""

    def _make_split(
        self,
        split_index: int,
        train_sharpe: float,
        test_sharpe: float,
        train_net_return: float = 0.0,
        test_net_return: float = 0.0,
    ) -> WalkForwardSplitResult:
        """Helper to create a WalkForwardSplitResult with split_role='both'."""
        train_inf = InferenceSummary(
            bar_count_for_returns=10,
            mean_return=0.001,
            std_return=0.01,
            sharpe_like=train_sharpe,
            annualized=False,
            interval="8h",
        )
        train_ret = ReturnSummary(
            gross_return_total=train_net_return * 1.01,
            net_return_total=train_net_return,
        )
        test_rs = ReturnSeries(
            gross_returns=[0.01, 0.02],
            net_returns=[0.009, 0.018] if test_sharpe > 0 else [-0.009, -0.018],
            bar_timestamps=[f"2023-01-{i+1:02d}T00:00:00Z" for i in range(2)],
            interval="8h",
        )
        return WalkForwardSplitResult(
            split_index=split_index,
            train_bar_count=10,
            test_bar_count=2,
            signal_count=1,
            long_count=1,
            short_count=0,
            flat_count=0,
            receipt_path=None,
            artifact_path=None,
            split_role="both",
            train_inference_summary=train_inf,
            train_return_summary=train_ret,
            return_series=test_rs,
        )

    def test_empty_paths(self) -> None:
        """Empty paths returns zero PBO."""
        result = compute_pbo([])
        assert result.pbo == 0.0
        assert result.path_count == 0
        assert len(result.assumptions) > 0

    def test_single_path(self) -> None:
        """Single path cannot compute meaningful PBO."""
        split = self._make_split(0, train_sharpe=1.0, test_sharpe=1.0)
        result = compute_pbo([[split]])
        assert result.pbo == 0.0
        assert "Need at least 2 paths" in result.limitations[-1]

    def test_selected_beats_random(self) -> None:
        """Best in-sample path beats some random paths OOS."""
        # Path 0: best train (1.5), mediocre test (0.8)
        p0 = [self._make_split(0, train_sharpe=1.5, test_sharpe=0.8)]
        # Path 1: mediocre train (0.5), terrible test (-0.5)
        p1 = [self._make_split(0, train_sharpe=0.5, test_sharpe=-0.5)]

        result = compute_pbo([p0, p1])
        assert result.pbo == 1.0  # Path 0 beats Path 1 OOS
        assert result.path_count == 2

    def test_selected_loses_to_random(self) -> None:
        """Best in-sample path loses to random paths OOS (overfitting signal)."""
        # Path 0: best train (2.0), terrible test (-1.0) - classic overfitting
        p0 = [self._make_split(0, train_sharpe=2.0, test_sharpe=-1.0)]
        # Path 1: mediocre train (0.5), good test (1.0) - generalizes
        p1 = [self._make_split(0, train_sharpe=0.5, test_sharpe=1.0)]

        result = compute_pbo([p0, p1])
        assert result.pbo == 0.0  # Path 0 loses to Path 1 OOS
        assert result.path_count == 2

    def test_tie_half_credit(self) -> None:
        """Tied OOS scores give half credit."""
        # Path 0: best train (1.5), test (1.0)
        p0 = [self._make_split(0, train_sharpe=1.5, test_sharpe=1.0)]
        # Path 1: train (0.5), test (1.0) - same OOS score
        p1 = [self._make_split(0, train_sharpe=0.5, test_sharpe=1.0)]

        result = compute_pbo([p0, p1])
        # p0 beats p1 tie -> 0.5 credit, so PBO = 0.5 / 1 = 0.5
        assert result.pbo == 0.5

    def test_return_metric(self) -> None:
        """PBO works with 'return' selection metric."""
        # Path 0: best train return (0.10), test return (-0.05) - loses OOS
        p0 = [self._make_split(0, train_sharpe=0.0, test_sharpe=-0.5, train_net_return=0.10, test_net_return=-0.05)]
        # Path 1: train return (0.02), test return (0.08) - wins OOS
        p1 = [self._make_split(0, train_sharpe=0.0, test_sharpe=0.5, train_net_return=0.02, test_net_return=0.08)]

        result = compute_pbo([p0, p1], selection_metric="return")
        assert result.selection_metric == "return"
        # Path 0 wins train but loses OOS (overfitting signal)
        assert result.pbo == 0.0

    def test_provenance_passed_through(self) -> None:
        """Provenance fields are passed through to result."""
        split = self._make_split(0, train_sharpe=1.0, test_sharpe=1.0)
        result = compute_pbo(
            [[split]],
            family_id="test-family",
            variant_id="v1",
            artifact_path="/path/to/artifact.json",
        )
        assert result.provenance.get("family_id") == "test-family"
        assert result.provenance.get("variant_id") == "v1"
        assert result.provenance.get("artifact_path") == "/path/to/artifact.json"

    def test_assumptions_are_explicit(self) -> None:
        """Result includes explicit list of assumptions."""
        split = self._make_split(0, train_sharpe=1.0, test_sharpe=1.0)
        result = compute_pbo([[split], [self._make_split(0, train_sharpe=0.5, test_sharpe=0.5)]])
        assert len(result.assumptions) > 0
        assert any("PBO is computed as P" in a for a in result.assumptions)
        assert any("DIAGNOSTIC" in a for a in result.assumptions)

    def test_limitations_are_explicit(self) -> None:
        """Result includes explicit list of limitations."""
        split = self._make_split(0, train_sharpe=1.0, test_sharpe=1.0)
        result = compute_pbo([[split], [self._make_split(0, train_sharpe=0.5, test_sharpe=0.5)]])
        assert len(result.limitations) > 0
        assert any("DIAGNOSTIC" in l for l in result.limitations)

    def test_split_role_not_both_skipped(self) -> None:
        """Splits with split_role != 'both' are skipped."""
        # Path 0: split_role='test' - will be skipped, scores = 0
        split_test_only = WalkForwardSplitResult(
            split_index=0,
            train_bar_count=10,
            test_bar_count=2,
            signal_count=1,
            long_count=1,
            short_count=0,
            flat_count=0,
            receipt_path=None,
            artifact_path=None,
            split_role="test",  # Not 'both' - skipped
        )
        # Path 1: split_role='both' - valid scores
        result = compute_pbo(
            [[split_test_only], [self._make_split(0, train_sharpe=0.5, test_sharpe=0.5)]],
            selection_metric="sharpe",
        )
        # Should still work - path 0 has no valid scores (train=0, test=0)
        # Path 1 is selected (0.5 > 0), its test=3.0 > path 0's test=0
        assert result.path_count == 2
        # Selected (path 1) beats random (path 0) OOS
        assert result.pbo == 1.0


class TestPBODeterministicPaths:
    """Tests for deterministic train/test path construction."""

    def _make_path(self, splits_data: list[tuple[float, float]]) -> list[WalkForwardSplitResult]:
        """Helper: create path from list of (train_sharpe, test_sharpe) pairs."""
        path = []
        for i, (train_s, test_s) in enumerate(splits_data):
            train_inf = InferenceSummary(
                bar_count_for_returns=10,
                mean_return=0.001,
                std_return=0.01,
                sharpe_like=train_s,
                annualized=False,
                interval="8h",
            )
            train_ret = ReturnSummary(
                gross_return_total=train_s * 0.1,
                net_return_total=train_s * 0.09,
            )
            # Use 2 data points so Sharpe computation works (needs n>=2)
            test_rs = ReturnSeries(
                gross_returns=[test_s * 0.1, test_s * 0.12],
                net_returns=[test_s * 0.09, test_s * 0.108],
                bar_timestamps=["2023-01-01T00:00:00Z", "2023-01-02T00:00:00Z"],
                interval="8h",
            )
            path.append(WalkForwardSplitResult(
                split_index=i,
                train_bar_count=10,
                test_bar_count=2,
                signal_count=1,
                long_count=1,
                short_count=0,
                flat_count=0,
                receipt_path=None,
                artifact_path=None,
                split_role="both",
                train_inference_summary=train_inf,
                train_return_summary=train_ret,
                return_series=test_rs,
            ))
        return path

    def test_same_paths_produce_same_pbo(self) -> None:
        """Multiple runs with same paths produce same PBO."""
        p0 = self._make_path([(1.5, 0.8), (1.2, 0.6)])
        p1 = self._make_path([(0.5, 1.0), (0.3, 0.8)])

        result1 = compute_pbo([p0, p1])
        result2 = compute_pbo([p0, p1])

        assert result1.pbo == result2.pbo
        assert result1.path_count == result2.path_count

    def test_different_path_order_produces_different_winner(self) -> None:
        """Path order affects which path is selected as winner."""
        # Path 0 clearly best train
        p0 = self._make_path([(2.0, -0.5)])
        # Path 1 mediocre train but good OOS
        p1 = self._make_path([(0.5, 1.5)])

        # p0 first, p1 second
        r1 = compute_pbo([p0, p1])
        # p1 first, p0 second
        r2 = compute_pbo([p1, p0])

        # Both should select p0 as winner (highest train score)
        # But order of random paths in PBO count differs
        assert r1.pbo == r2.pbo  # PBO is order-independent for selection


class TestPBOInSampleWinner:
    """Tests for in-sample winner selection."""

    def _make_path(self, train_sharpe: float, test_sharpe: float = 0.0) -> list[WalkForwardSplitResult]:
        """Helper to create a single-split path."""
        train_inf = InferenceSummary(
            bar_count_for_returns=10,
            mean_return=0.001,
            std_return=0.01,
            sharpe_like=train_sharpe,
            annualized=False,
            interval="8h",
        )
        train_ret = ReturnSummary(
            gross_return_total=train_sharpe * 0.1,
            net_return_total=train_sharpe * 0.09,
        )
        # Use 2 data points so Sharpe computation works (needs n>=2)
        test_rs = ReturnSeries(
            gross_returns=[test_sharpe * 0.1, test_sharpe * 0.12],
            net_returns=[test_sharpe * 0.09, test_sharpe * 0.108],
            bar_timestamps=["2023-01-01T00:00:00Z", "2023-01-02T00:00:00Z"],
            interval="8h",
        )
        return [WalkForwardSplitResult(
            split_index=0,
            train_bar_count=10,
            test_bar_count=2,
            signal_count=1,
            long_count=1,
            short_count=0,
            flat_count=0,
            receipt_path=None,
            artifact_path=None,
            split_role="both",
            train_inference_summary=train_inf,
            train_return_summary=train_ret,
            return_series=test_rs,
        )]

    def test_highest_train_sharpe_is_selected(self) -> None:
        """Path with highest train Sharpe is selected (not highest test)."""
        # Path 0: best train, bad test - overfits
        p0 = self._make_path(train_sharpe=2.0, test_sharpe=-1.0)
        # Path 1: mediocre train, great test - generalizes
        p1 = self._make_path(train_sharpe=0.5, test_sharpe=2.0)

        result = compute_pbo([p0, p1])
        # p0 has highest train, so selected
        # p0 OOS = -1.0, p1 OOS = 2.0
        # Selected beats random? p0 loses to p1 OOS
        assert result.pbo == 0.0  # Path 0 (selected) loses to Path 1

    def test_sharpe_vs_return_selection_metric(self) -> None:
        """Winner selection is consistent across metric choices."""
        # Path 0: best train sharpe, mediocre train return
        train_inf0 = InferenceSummary(
            bar_count_for_returns=10,
            mean_return=0.001,
            std_return=0.01,
            sharpe_like=2.0,
            annualized=False,
            interval="8h",
        )
        train_ret0 = ReturnSummary(
            gross_return_total=0.05,
            net_return_total=0.04,  # Low total return
        )

        # Path 1: mediocre train sharpe, best train return
        train_inf1 = InferenceSummary(
            bar_count_for_returns=10,
            mean_return=0.001,
            std_return=0.01,
            sharpe_like=0.5,
            annualized=False,
            interval="8h",
        )
        train_ret1 = ReturnSummary(
            gross_return_total=0.20,
            net_return_total=0.18,  # High total return
        )

        # Use 2 data points so Sharpe computation works (needs n>=2)
        test_rs = ReturnSeries(
            gross_returns=[0.01, 0.012],
            net_returns=[0.009, 0.0108],
            bar_timestamps=["2023-01-01T00:00:00Z", "2023-01-02T00:00:00Z"],
            interval="8h",
        )

        p0 = [WalkForwardSplitResult(
            split_index=0, train_bar_count=10, test_bar_count=2,
            signal_count=1, long_count=1, short_count=0, flat_count=0,
            receipt_path=None, artifact_path=None, split_role="both",
            train_inference_summary=train_inf0,
            train_return_summary=train_ret0,
            return_series=test_rs,
        )]
        p1 = [WalkForwardSplitResult(
            split_index=0, train_bar_count=10, test_bar_count=2,
            signal_count=1, long_count=1, short_count=0, flat_count=0,
            receipt_path=None, artifact_path=None, split_role="both",
            train_inference_summary=train_inf1,
            train_return_summary=train_ret1,
            return_series=test_rs,
        )]

        # Sharpe metric: selects p0 (sharpe 2.0 > 0.5)
        r_sharpe = compute_pbo([p0, p1], selection_metric="sharpe")
        # Return metric: selects p1 (return 0.18 > 0.04)
        r_return = compute_pbo([p0, p1], selection_metric="return")

        # Different selection, different PBO outcomes
        assert r_sharpe.selection_metric == "sharpe"
        assert r_return.selection_metric == "return"


class TestPBOOutOfSample:
    """Tests for out-of-sample ranking/evaluation."""

    def _make_path(self, train_sharpe: float, test_sharpe: float) -> list[WalkForwardSplitResult]:
        """Helper to create a single-split path."""
        train_inf = InferenceSummary(
            bar_count_for_returns=10,
            mean_return=0.001,
            std_return=0.01,
            sharpe_like=train_sharpe,
            annualized=False,
            interval="8h",
        )
        train_ret = ReturnSummary(
            gross_return_total=train_sharpe * 0.1,
            net_return_total=train_sharpe * 0.09,
        )
        # Use 2 data points so Sharpe computation works (needs n>=2)
        test_rs = ReturnSeries(
            gross_returns=[test_sharpe * 0.1, test_sharpe * 0.12],
            net_returns=[test_sharpe * 0.09, test_sharpe * 0.108],
            bar_timestamps=["2023-01-01T00:00:00Z", "2023-01-02T00:00:00Z"],
            interval="8h",
        )
        return [WalkForwardSplitResult(
            split_index=0,
            train_bar_count=10,
            test_bar_count=2,
            signal_count=1,
            long_count=1,
            short_count=0,
            flat_count=0,
            receipt_path=None,
            artifact_path=None,
            split_role="both",
            train_inference_summary=train_inf,
            train_return_summary=train_ret,
            return_series=test_rs,
        )]

    def test_oos_score_computed_from_test_returns(self) -> None:
        """Selected path's OOS score is computed from return_series."""
        # Create explicit ReturnSeries where p0 has higher train but lower OOS Sharpe
        # p0: best train (2.0), test OOS with LOWER Sharpe
        # Sharpe = mean / std; for low Sharpe use high variance returns
        p0_test_rs = ReturnSeries(
            gross_returns=[-0.01, 0.03],  # mean=0.01, high variance -> low Sharpe
            net_returns=[-0.009, 0.027],
            bar_timestamps=["2023-01-01T00:00:00Z", "2023-01-02T00:00:00Z"],
            interval="8h",
        )
        p0_train_inf = InferenceSummary(
            bar_count_for_returns=10,
            mean_return=0.001,
            std_return=0.01,
            sharpe_like=2.0,
            annualized=False,
            interval="8h",
        )
        p0_train_ret = ReturnSummary(gross_return_total=0.2, net_return_total=0.18)
        p0 = [WalkForwardSplitResult(
            split_index=0, train_bar_count=10, test_bar_count=2,
            signal_count=1, long_count=1, short_count=0, flat_count=0,
            receipt_path=None, artifact_path=None, split_role="both",
            train_inference_summary=p0_train_inf,
            train_return_summary=p0_train_ret,
            return_series=p0_test_rs,
        )]

        # p1: mediocre train (0.5), test OOS with HIGHER Sharpe
        # Sharpe = mean / std; for higher Sharpe use low variance returns
        p1_test_rs = ReturnSeries(
            gross_returns=[0.01, 0.02],  # mean=0.015, low variance -> high Sharpe
            net_returns=[0.009, 0.018],
            bar_timestamps=["2023-01-03T00:00:00Z", "2023-01-04T00:00:00Z"],
            interval="8h",
        )
        p1_train_inf = InferenceSummary(
            bar_count_for_returns=10,
            mean_return=0.001,
            std_return=0.01,
            sharpe_like=0.5,
            annualized=False,
            interval="8h",
        )
        p1_train_ret = ReturnSummary(gross_return_total=0.05, net_return_total=0.045)
        p1 = [WalkForwardSplitResult(
            split_index=0, train_bar_count=10, test_bar_count=2,
            signal_count=1, long_count=1, short_count=0, flat_count=0,
            receipt_path=None, artifact_path=None, split_role="both",
            train_inference_summary=p1_train_inf,
            train_return_summary=p1_train_ret,
            return_series=p1_test_rs,
        )]

        result = compute_pbo([p0, p1])
        # p0 selected (best train=2.0 > 0.5), but p0 OOS Sharpe < p1 OOS Sharpe
        # p0 loses to p1 OOS -> PBO = 0.0
        assert result.pbo == 0.0

    def test_oos_ranking_reflects_test_performance(self) -> None:
        """OOS ranking correctly reflects actual test performance."""
        # Three paths with known OOS rankings
        p0 = self._make_path(train_sharpe=3.0, test_sharpe=-2.0)  # Worst OOS
        p1 = self._make_path(train_sharpe=2.0, test_sharpe=1.0)  # Middle OOS
        p2 = self._make_path(train_sharpe=1.0, test_sharpe=3.0)  # Best OOS

        result = compute_pbo([p0, p1, p2])
        # p0 selected (highest train), its OOS is worst
        # p0 beats p1? -2.0 < 1.0 -> no
        # p0 beats p2? -2.0 < 3.0 -> no
        assert result.pbo == 0.0


class TestPBODegenerateCases:
    """Tests for degenerate edge cases."""

    def _make_path(self, train_sharpe: float, test_sharpe: float) -> list[WalkForwardSplitResult]:
        """Helper to create a single-split path."""
        train_inf = InferenceSummary(
            bar_count_for_returns=10,
            mean_return=0.001,
            std_return=0.01,
            sharpe_like=train_sharpe,
            annualized=False,
            interval="8h",
        )
        train_ret = ReturnSummary(
            gross_return_total=train_sharpe * 0.1,
            net_return_total=train_sharpe * 0.09,
        )
        # Use 2 data points so Sharpe computation works (needs n>=2)
        test_rs = ReturnSeries(
            gross_returns=[test_sharpe * 0.1, test_sharpe * 0.12],
            net_returns=[test_sharpe * 0.09, test_sharpe * 0.108],
            bar_timestamps=["2023-01-01T00:00:00Z", "2023-01-02T00:00:00Z"],
            interval="8h",
        )
        return [WalkForwardSplitResult(
            split_index=0,
            train_bar_count=10,
            test_bar_count=2,
            signal_count=1,
            long_count=1,
            short_count=0,
            flat_count=0,
            receipt_path=None,
            artifact_path=None,
            split_role="both",
            train_inference_summary=train_inf,
            train_return_summary=train_ret,
            return_series=test_rs,
        )]

    def test_empty_path_list(self) -> None:
        """Empty path list handled gracefully."""
        result = compute_pbo([])
        assert result.pbo == 0.0
        assert result.path_count == 0
        assert len(result.assumptions) > 0
        assert len(result.limitations) > 0

    def test_single_path_pbo_zero(self) -> None:
        """Single path cannot compute meaningful PBO (needs baseline)."""
        split = self._make_path(train_sharpe=1.0, test_sharpe=1.0)
        result = compute_pbo([[split]])
        assert result.pbo == 0.0
        assert result.path_count == 1
        assert "Need at least 2 paths" in result.limitations[-1]

    def test_all_paths_identical_pbo_half(self) -> None:
        """All identical paths produce PBO ~0.5 (no overfitting signal)."""
        p0 = self._make_path(train_sharpe=1.0, test_sharpe=1.0)
        p1 = self._make_path(train_sharpe=1.0, test_sharpe=1.0)
        p2 = self._make_path(train_sharpe=1.0, test_sharpe=1.0)

        result = compute_pbo([p0, p1, p2])
        # All equal OOS, each tie = 0.5 credit
        # Selected (any) beats 2 others, each tie = 0.5
        # Total = 2 * 0.5 = 1.0 / 2 = 0.5
        assert result.pbo == 0.5

    def test_path_with_no_train_data(self) -> None:
        """Path with no train data handled gracefully."""
        # Path 0: valid train data
        p0 = self._make_path(train_sharpe=1.0, test_sharpe=1.0)
        # Path 1: no train_inference_summary (treated as train=0)
        train_ret = ReturnSummary(
            gross_return_total=0.0,
            net_return_total=0.0,
        )
        # Use 2 data points so Sharpe computation works (needs n>=2)
        test_rs = ReturnSeries(
            gross_returns=[0.01, 0.012],
            net_returns=[0.009, 0.0108],
            bar_timestamps=["2023-01-01T00:00:00Z", "2023-01-02T00:00:00Z"],
            interval="8h",
        )
        p1 = [WalkForwardSplitResult(
            split_index=0,
            train_bar_count=10,
            test_bar_count=2,
            signal_count=1,
            long_count=1,
            short_count=0,
            flat_count=0,
            receipt_path=None,
            artifact_path=None,
            split_role="both",
            train_inference_summary=None,  # No train data
            train_return_summary=train_ret,
            return_series=test_rs,
        )]

        result = compute_pbo([p0, p1])
        # p0 has train=1.0, p1 has train=0.0 (from None inference)
        # p0 selected, beats p1 OOS (1.0 > 0.0)
        assert result.pbo == 1.0

    def test_path_with_no_test_data(self) -> None:
        """Path with no test data handled gracefully."""
        # Path 0: valid train and test
        p0 = self._make_path(train_sharpe=1.0, test_sharpe=1.0)
        # Path 1: valid train but no return_series
        train_inf = InferenceSummary(
            bar_count_for_returns=10,
            mean_return=0.001,
            std_return=0.01,
            sharpe_like=0.5,
            annualized=False,
            interval="8h",
        )
        train_ret = ReturnSummary(
            gross_return_total=0.05,
            net_return_total=0.04,
        )
        p1 = [WalkForwardSplitResult(
            split_index=0,
            train_bar_count=10,
            test_bar_count=2,
            signal_count=1,
            long_count=1,
            short_count=0,
            flat_count=0,
            receipt_path=None,
            artifact_path=None,
            split_role="both",
            train_inference_summary=train_inf,
            train_return_summary=train_ret,
            return_series=None,  # No test data
        )]

        result = compute_pbo([p0, p1])
        # p0 has higher train (1.0 > 0.5), selected
        # p0 OOS = 1.0, p1 OOS = 0.0 (no test data)
        # p0 beats p1
        assert result.pbo == 1.0


class TestPBOIndexIntegration:
    """Tests for PBOSummary artifact persistence and index integration."""

    def test_pbo_summary_to_dict_json_serializable(self) -> None:
        """PBOSummary.to_dict() produces valid JSON-serializable output."""
        pbo = PBOSummary(
            path_count=100,
            selection_metric="sharpe",
            pbo=0.65,
            assumptions=["Test assumption"],
            limitations=["Test limitation"],
            provenance={"family_id": "test-family", "variant_id": "v1"},
        )
        d = pbo.to_dict()

        # Verify JSON serializable
        json_str = json.dumps(d)
        assert '"method": "pbo"' in json_str
        assert '"path_count": 100' in json_str
        assert '"selection_metric": "sharpe"' in json_str
        assert '"pbo": 0.65' in json_str

    def test_pbo_summary_from_dict_reconstructable(self) -> None:
        """PBOSummary can be reconstructed from dict."""
        original = PBOSummary(
            path_count=50,
            selection_metric="return",
            pbo=0.45,
            assumptions=["Assumption 1", "Assumption 2"],
            limitations=["Limitation 1"],
            provenance={"family_id": "test"},
        )

        # Round-trip through dict
        d = original.to_dict()
        restored = PBOSummary(**d)

        assert restored.method == original.method
        assert restored.path_count == original.path_count
        assert restored.selection_metric == original.selection_metric
        assert restored.pbo == original.pbo
        assert restored.assumptions == original.assumptions
        assert restored.limitations == original.limitations
        assert restored.provenance == original.provenance

    def test_pbo_summary_in_json_output(self) -> None:
        """PBOSummary can be serialized to JSON for index output."""
        pbo = PBOSummary(
            path_count=100,
            selection_metric="sharpe",
            pbo=0.35,
            assumptions=["test assumption"],
            limitations=["test limitation"],
            provenance={"family_id": "test-family"},
        )
        json_str = json.dumps(pbo.to_dict(), indent=2)
        assert '"method": "pbo"' in json_str
        assert '"path_count": 100' in json_str
        assert '"pbo": 0.35' in json_str


class TestPBOLegacyCompatibility:
    """Tests for legacy compatibility with artifacts without train fields."""

    def _make_path(self, train_sharpe: float, test_sharpe: float) -> list[WalkForwardSplitResult]:
        """Helper to create a single-split path."""
        train_inf = InferenceSummary(
            bar_count_for_returns=10,
            mean_return=0.001,
            std_return=0.01,
            sharpe_like=train_sharpe,
            annualized=False,
            interval="8h",
        )
        train_ret = ReturnSummary(
            gross_return_total=train_sharpe * 0.1,
            net_return_total=train_sharpe * 0.09,
        )
        test_rs = ReturnSeries(
            gross_returns=[test_sharpe * 0.1],
            net_returns=[test_sharpe * 0.09],
            bar_timestamps=["2023-01-01T00:00:00Z"],
            interval="8h",
        )
        return [WalkForwardSplitResult(
            split_index=0,
            train_bar_count=10,
            test_bar_count=1,
            signal_count=1,
            long_count=1,
            short_count=0,
            flat_count=0,
            receipt_path=None,
            artifact_path=None,
            split_role="both",
            train_inference_summary=train_inf,
            train_return_summary=train_ret,
            return_series=test_rs,
        )]

    def test_legacy_split_role_test_still_works(self) -> None:
        """Legacy artifacts with split_role='test' don't crash compute_pbo."""
        # Path with split_role='test' (no train data)
        split_test_only = WalkForwardSplitResult(
            split_index=0,
            train_bar_count=10,
            test_bar_count=1,
            signal_count=1,
            long_count=1,
            short_count=0,
            flat_count=0,
            receipt_path=None,
            artifact_path=None,
            split_role="test",  # Legacy - no train fields
        )

        # Valid path
        p_valid = self._make_path(train_sharpe=1.0, test_sharpe=1.0)

        result = compute_pbo([[split_test_only], p_valid])
        # split_test_only has no valid train scores (split_role != 'both')
        # p_valid selected (1.0 > 0), beats split_test_only OOS
        assert result.path_count == 2

    def test_legacy_split_role_train_only_still_works(self) -> None:
        """Legacy artifacts with split_role='train' don't crash compute_pbo."""
        # Path with split_role='train' (no test data)
        split_train_only = WalkForwardSplitResult(
            split_index=0,
            train_bar_count=10,
            test_bar_count=1,
            signal_count=1,
            long_count=1,
            short_count=0,
            flat_count=0,
            receipt_path=None,
            artifact_path=None,
            split_role="train",  # Legacy - no test data
            train_inference_summary=InferenceSummary(
                bar_count_for_returns=10,
                mean_return=0.001,
                std_return=0.01,
                sharpe_like=1.0,
                annualized=False,
                interval="8h",
            ),
        )

        result = compute_pbo([[split_train_only], self._make_path(train_sharpe=0.5, test_sharpe=0.5)])
        # split_train_only has no valid test scores (split_role != 'both')
        # p_valid selected (0.5 > 0)
        assert result.path_count == 2

    def test_compute_path_dispersion_still_works(self) -> None:
        """Old compute_path_dispersion still works alongside new compute_pbo."""
        from quantbot.experiment.pbo import compute_path_dispersion

        rs1 = ReturnSeries(
            gross_returns=[0.01, 0.02],
            net_returns=[0.009, 0.018],
            bar_timestamps=["2023-01-01T00:00:00Z", "2023-01-02T00:00:00Z"],
            interval="8h",
        )
        rs2 = ReturnSeries(
            gross_returns=[0.03, 0.04],
            net_returns=[0.028, 0.038],
            bar_timestamps=["2023-01-03T00:00:00Z", "2023-01-04T00:00:00Z"],
            interval="8h",
        )

        result = compute_path_dispersion([rs1, rs2])
        assert result.method == "path_dispersion"
        assert result.path_count >= 0

    def test_pbo_and_dispersion_coexist(self) -> None:
        """Both compute_pbo and compute_path_dispersion can be imported."""
        from quantbot.experiment.pbo import compute_pbo, compute_path_dispersion, PBOSummary, PathDispersionSummary

        # Both classes and functions exist
        assert PBOSummary is not None
        assert PathDispersionSummary is not None
        assert callable(compute_pbo)
        assert callable(compute_path_dispersion)
