"""Experiment surface for QuantBot.

Minimal honest experiment path.
Paper mode only - no real trading, no profitability claims.
"""

from quantbot.experiment.spec import ExperimentSpec
from quantbot.experiment.result import (
    ExperimentResult,
    InferenceSummary,
    WalkForwardExperimentResult,
    WalkForwardSplitResult,
    compute_inference_summary,
    CostRobustnessSummary,
    CostRobustnessLevel,
    COST_STRESS_MULTIPLIERS,
    compute_cost_robustness,
    RegimeReplicationSummary,
    generate_regime_replication_summary,
)
from quantbot.experiment.runner import run_experiment
from quantbot.experiment.walkforward import WalkForwardSplit, build_walkforward_splits
from quantbot.experiment.walkforward_runner import run_walkforward_experiment
from quantbot.experiment.gates import GateVerdict, gate_experiment_result, gate_walkforward_result
from quantbot.experiment.index import IndexedExperiment, index_experiment_artifacts
from quantbot.experiment.calibration import (
    FrankenReconciliationRecord,
    CalibrationComparison,
    ingest_franken_reconciliation,
    compare_record,
    compare_reconciliation_dir,
)
from quantbot.experiment.regime import (
    RegimeMetadata,
    CombinedRegimeMetadata,
    compute_combined_regime,
    compute_vol_regime,
    compute_trend_regime,
    compute_log_returns,
    VolRegimeLabel,
    TrendRegimeLabel,
    DEFAULT_VOL_WINDOW,
    DEFAULT_TREND_WINDOW,
    DEFAULT_VOL_HIGH_QUANTILE,
    DEFAULT_TREND_THRESHOLD,
)

__all__ = [
    "ExperimentSpec",
    "ExperimentResult",
    "run_experiment",
    "WalkForwardSplit",
    "build_walkforward_splits",
    "WalkForwardExperimentResult",
    "WalkForwardSplitResult",
    "run_walkforward_experiment",
    "GateVerdict",
    "gate_experiment_result",
    "gate_walkforward_result",
    "IndexedExperiment",
    "index_experiment_artifacts",
    "InferenceSummary",
    "compute_inference_summary",
    "FrankenReconciliationRecord",
    "CalibrationComparison",
    "ingest_franken_reconciliation",
    "compare_record",
    "compare_reconciliation_dir",
    "CostRobustnessSummary",
    "CostRobustnessLevel",
    "COST_STRESS_MULTIPLIERS",
    "compute_cost_robustness",
    # Regime-tagging substrate
    "RegimeMetadata",
    "CombinedRegimeMetadata",
    "compute_combined_regime",
    "compute_vol_regime",
    "compute_trend_regime",
    "compute_log_returns",
    "VolRegimeLabel",
    "TrendRegimeLabel",
    "DEFAULT_VOL_WINDOW",
    "DEFAULT_TREND_WINDOW",
    "DEFAULT_VOL_HIGH_QUANTILE",
    "DEFAULT_TREND_THRESHOLD",
    # Cross-regime replication
    "RegimeReplicationSummary",
    "generate_regime_replication_summary",
]
