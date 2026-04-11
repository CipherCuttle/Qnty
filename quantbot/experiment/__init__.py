"""Experiment surface for QuantBot.

Minimal honest experiment path.
Paper mode only - no real trading, no profitability claims.
"""

from quantbot.experiment.spec import ExperimentSpec
from quantbot.experiment.result import ExperimentResult, WalkForwardExperimentResult, WalkForwardSplitResult
from quantbot.experiment.runner import run_experiment
from quantbot.experiment.walkforward import WalkForwardSplit, build_walkforward_splits
from quantbot.experiment.walkforward_runner import run_walkforward_experiment

__all__ = [
    "ExperimentSpec",
    "ExperimentResult",
    "run_experiment",
    "WalkForwardSplit",
    "build_walkforward_splits",
    "WalkForwardExperimentResult",
    "WalkForwardSplitResult",
    "run_walkforward_experiment",
]
