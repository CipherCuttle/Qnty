"""Falsification gates for experiment results.

Paper-mode only: no PnL, no Sharpe, no alpha claims.
Output is small, deterministic.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Literal

from quantbot.experiment.result import (
    ExperimentResult,
    WalkForwardExperimentResult,
)


@dataclass
class GateVerdict:
    """Result of a gate check.

    Attributes:
        status: PASS or FAIL.
        reasons: List of human-readable failure reasons (empty if PASS).
        checked: Dict of intermediate values used for debugging/audit.
    """

    status: Literal["PASS", "FAIL"]
    reasons: list[str] = field(default_factory=list)
    checked: dict[str, Any] = field(default_factory=dict)


def gate_experiment_result(result: ExperimentResult) -> GateVerdict:
    """Check a single ExperimentResult against kill criteria.

    Kill criteria:
    - signal_count == 0 → FAIL
    - signal_count < 3 → FAIL (degenerate threshold)
    - bar_count == 0 → FAIL
    """
    reasons: list[str] = []
    checked: dict[str, Any] = {
        "bar_count": result.bar_count,
        "signal_count": result.signal_count,
    }

    if result.bar_count == 0:
        reasons.append("bar_count is zero")

    if result.signal_count == 0:
        reasons.append("signal_count is zero")

    if result.signal_count < 3:
        reasons.append("signal_count below degenerate threshold (3)")

    status: Literal["PASS", "FAIL"] = "FAIL" if reasons else "PASS"
    return GateVerdict(status=status, reasons=reasons, checked=checked)


def gate_walkforward_result(result: WalkForwardExperimentResult) -> GateVerdict:
    """Check a WalkForwardExperimentResult against kill criteria.

    Kill criteria:
    - split_count == 0 → FAIL
    - split_count < 2 → FAIL (minimum viable splits)
    - total_signal_count == 0 → FAIL
    - total_signal_count < 5 → FAIL (aggregate minimum)
    - If splits exist, sum(signal_count over splits) must == total_signal_count
    """
    reasons: list[str] = []
    checked: dict[str, Any] = {
        "split_count": result.split_count,
        "total_signal_count": result.total_signal_count,
    }

    if result.split_count == 0:
        reasons.append("split_count is zero")

    if result.split_count < 2:
        reasons.append("split_count below minimum viable (2)")

    if result.total_signal_count == 0:
        reasons.append("total_signal_count is zero")

    if result.total_signal_count < 5:
        reasons.append("total_signal_count below aggregate minimum (5)")

    if result.splits:
        computed_total = sum(s.signal_count for s in result.splits)
        checked["computed_total_signal_count"] = computed_total
        checked["splits_signal_counts"] = [s.signal_count for s in result.splits]
        if computed_total != result.total_signal_count:
            reasons.append(
                f"signal_count mismatch: total_signal_count={result.total_signal_count} "
                f"but sum of splits={computed_total}"
            )

    status: Literal["PASS", "FAIL"] = "FAIL" if reasons else "PASS"
    return GateVerdict(status=status, reasons=reasons, checked=checked)
