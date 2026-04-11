"""Experiment surface for QuantBot.

Minimal honest experiment path.
Paper mode only - no real trading, no profitability claims.
"""

from quantbot.experiment.spec import ExperimentSpec
from quantbot.experiment.result import ExperimentResult
from quantbot.experiment.runner import run_experiment

__all__ = [
    "ExperimentSpec",
    "ExperimentResult",
    "run_experiment",
]
