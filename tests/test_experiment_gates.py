"""Tests for experiment gates (falsification checks)."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

import pytest

from quantbot.experiment.gates import (
    GateVerdict,
    gate_experiment_result,
    gate_walkforward_result,
)
from quantbot.experiment.result import (
    ExperimentResult,
    WalkForwardExperimentResult,
    WalkForwardSplitResult,
)
from quantbot.experiment.spec import ExperimentSpec


# ---------------------------------------------------------------------------
# Minimal mock helpers
# ---------------------------------------------------------------------------

def _make_spec() -> ExperimentSpec:
    """Create a valid ExperimentSpec for mock results."""
    return ExperimentSpec(
        experiment_name="test_experiment",
        strategy_name="noop",
        strategy_params={},
        fixture_name="test_fixture",
    )


@dataclass
class MockExperimentResult:
    """Minimal mock for ExperimentResult (no real spec/path needed)."""
    bar_count: int
    signal_count: int
    spec: ExperimentSpec = field(default_factory=_make_spec)
    receipt_path: Path = field(default_factory=lambda: Path("."))
    result_path: Path = field(default_factory=lambda: Path("."))
    receipt_digest: str = ""
    first_timestamp: str = "2024-01-01T00:00:00"
    last_timestamp: str = "2024-01-02T00:00:00"
    long_count: int = 0
    short_count: int = 0
    flat_count: int = 0
    engine_version: str = ""


@dataclass
class MockWalkForwardSplitResult:
    """Minimal mock for WalkForwardSplitResult."""
    split_index: int
    train_bar_count: int
    test_bar_count: int
    signal_count: int
    long_count: int = 0
    short_count: int = 0
    flat_count: int = 0
    receipt_path: str | None = None
    artifact_path: str | None = None
    first_timestamp: str = ""
    last_timestamp: str = ""


# ---------------------------------------------------------------------------
# ExperimentResult gate tests
# ---------------------------------------------------------------------------

class TestGateExperimentResult:
    """Gate tests for ExperimentResult falsification."""

    def test_signal_count_zero_fails(self) -> None:
        """signal_count == 0 → FAIL."""
        result = MockExperimentResult(bar_count=100, signal_count=0)
        verdict = gate_experiment_result(result)
        assert verdict.status == "FAIL"
        assert any("signal_count is zero" in r for r in verdict.reasons)

    def test_signal_count_below_threshold_fails(self) -> None:
        """signal_count < 3 → FAIL."""
        result = MockExperimentResult(bar_count=100, signal_count=2)
        verdict = gate_experiment_result(result)
        assert verdict.status == "FAIL"
        assert any("below degenerate threshold" in r for r in verdict.reasons)

    def test_bar_count_zero_fails(self) -> None:
        """bar_count == 0 → FAIL."""
        result = MockExperimentResult(bar_count=0, signal_count=10)
        verdict = gate_experiment_result(result)
        assert verdict.status == "FAIL"
        assert any("bar_count is zero" in r for r in verdict.reasons)

    def test_valid_result_passes(self) -> None:
        """bar_count > 0, signal_count >= 3 → PASS."""
        result = MockExperimentResult(bar_count=100, signal_count=5)
        verdict = gate_experiment_result(result)
        assert verdict.status == "PASS"
        assert verdict.reasons == []


# ---------------------------------------------------------------------------
# WalkForwardExperimentResult gate tests
# ---------------------------------------------------------------------------

class TestGateWalkForwardResult:
    """Gate tests for WalkForwardExperimentResult falsification."""

    def test_split_count_zero_fails(self) -> None:
        """split_count == 0 → FAIL."""
        result = WalkForwardExperimentResult(
            experiment_name="wf_test",
            split_count=0,
            splits=[],
            total_bar_count=0,
            total_signal_count=0,
        )
        verdict = gate_walkforward_result(result)
        assert verdict.status == "FAIL"
        assert any("split_count is zero" in r for r in verdict.reasons)

    def test_split_count_below_minimum_fails(self) -> None:
        """split_count < 2 → FAIL."""
        result = WalkForwardExperimentResult(
            experiment_name="wf_test",
            split_count=1,
            splits=[
                MockWalkForwardSplitResult(
                    split_index=0,
                    train_bar_count=50,
                    test_bar_count=50,
                    signal_count=5,
                ),
            ],
            total_bar_count=100,
            total_signal_count=5,
        )
        verdict = gate_walkforward_result(result)
        assert verdict.status == "FAIL"
        assert any("split_count below minimum" in r for r in verdict.reasons)

    def test_total_signal_count_zero_fails(self) -> None:
        """total_signal_count == 0 → FAIL."""
        result = WalkForwardExperimentResult(
            experiment_name="wf_test",
            split_count=2,
            splits=[
                MockWalkForwardSplitResult(
                    split_index=0,
                    train_bar_count=50,
                    test_bar_count=50,
                    signal_count=0,
                ),
                MockWalkForwardSplitResult(
                    split_index=1,
                    train_bar_count=50,
                    test_bar_count=50,
                    signal_count=0,
                ),
            ],
            total_bar_count=100,
            total_signal_count=0,
        )
        verdict = gate_walkforward_result(result)
        assert verdict.status == "FAIL"
        assert any("total_signal_count is zero" in r for r in verdict.reasons)

    def test_total_signal_count_below_aggregate_minimum_fails(self) -> None:
        """total_signal_count < 5 → FAIL."""
        result = WalkForwardExperimentResult(
            experiment_name="wf_test",
            split_count=2,
            splits=[
                MockWalkForwardSplitResult(
                    split_index=0,
                    train_bar_count=50,
                    test_bar_count=50,
                    signal_count=2,
                ),
                MockWalkForwardSplitResult(
                    split_index=1,
                    train_bar_count=50,
                    test_bar_count=50,
                    signal_count=2,
                ),
            ],
            total_bar_count=100,
            total_signal_count=4,
        )
        verdict = gate_walkforward_result(result)
        assert verdict.status == "FAIL"
        assert any("total_signal_count below aggregate minimum" in r for r in verdict.reasons)

    def test_signal_count_sum_mismatch_fails(self) -> None:
        """Splits signal_count sum != total_signal_count → FAIL."""
        result = WalkForwardExperimentResult(
            experiment_name="wf_test",
            split_count=2,
            splits=[
                MockWalkForwardSplitResult(
                    split_index=0,
                    train_bar_count=50,
                    test_bar_count=50,
                    signal_count=3,
                ),
                MockWalkForwardSplitResult(
                    split_index=1,
                    train_bar_count=50,
                    test_bar_count=50,
                    signal_count=4,
                ),
            ],
            total_bar_count=100,
            total_signal_count=5,  # Wrong: should be 7
        )
        verdict = gate_walkforward_result(result)
        assert verdict.status == "FAIL"
        assert any("signal_count mismatch" in r for r in verdict.reasons)

    def test_valid_walkforward_passes(self) -> None:
        """Valid splits with consistent totals → PASS."""
        result = WalkForwardExperimentResult(
            experiment_name="wf_test",
            split_count=2,
            splits=[
                MockWalkForwardSplitResult(
                    split_index=0,
                    train_bar_count=50,
                    test_bar_count=50,
                    signal_count=3,
                ),
                MockWalkForwardSplitResult(
                    split_index=1,
                    train_bar_count=50,
                    test_bar_count=50,
                    signal_count=4,
                ),
            ],
            total_bar_count=100,
            total_signal_count=7,
        )
        verdict = gate_walkforward_result(result)
        assert verdict.status == "PASS"
        assert verdict.reasons == []
