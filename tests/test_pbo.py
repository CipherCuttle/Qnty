"""Tests for Path Dispersion diagnostic (proxy for PBO).

IMPORTANT: This is a PROXY DIAGNOSTIC, not Bailey-style CSCV/PBO.

Paper mode only - no live trading, no profitability claims.
Requires PYTHONHASHSEED=0 for deterministic dict ordering.
"""

import json
import tempfile
from pathlib import Path

import pytest

from quantbot.experiment.pbo import PathDispersionSummary, compute_path_dispersion, compute_pbo_cscv
from quantbot.experiment.result import ReturnSeries


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
