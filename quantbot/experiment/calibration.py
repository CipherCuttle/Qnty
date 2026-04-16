"""Franken reconciliation calibration surface.

Structural and observational only — no auto-calibration policy,
no automatic rewriting of historical artifacts.
"""

from dataclasses import dataclass
from pathlib import Path
from typing import Optional

# Threshold constants for calibration status classification.
# These are inspectable policy knobs — review them alongside any calibration report.
INSUFFICIENT_DATA_MIN_RECORDS: int = 30
MILD_MISMATCH_THRESHOLD_BPS: float = 5.0
MATERIAL_MISMATCH_THRESHOLD_BPS: float = 15.0

from quantbot.experiment.result import EconomicsSummary


@dataclass
class FrankenReconciliationRecord:
    """Single Franken reconciliation output record.

    Represents observed shortfall metrics from a Franken backtest
    reconciliation run. Linkage fields may be None if the source
    artifact did not carry them.
    """

    family_id: Optional[str] = None
    variant_id: Optional[str] = None
    trial_count: Optional[int] = None
    observed_avg_shortfall_bps: float = 0.0
    observed_entry_shortfall_bps: float = 0.0
    observed_exit_shortfall_bps: float = 0.0
    record_count: int = 0
    source_path: Optional[str] = None


@dataclass
class CalibrationComparison:
    """Comparison between Qnty assumed costs and Franken observed costs.

    Attributes:
        assumed_fee_bps: Qnty assumed fee in basis points.
        assumed_slippage_bps: Qnty assumed slippage in basis points.
        assumed_total_cost_bps: Qnty assumed total cost (fee + slippage).
        observed_avg_shortfall_bps: Franken observed average shortfall in bps.
        observed_entry_shortfall_bps: Franken observed entry shortfall in bps.
        observed_exit_shortfall_bps: Franken observed exit shortfall in bps.
        delta_bps: Difference between observed avg shortfall and assumed total cost.
        record_count: Number of Franken records aggregated.
        family_id: Experiment family identifier (may be None).
        variant_id: Experiment variant identifier (may be None).
        trial_count: Experiment trial count (may be None).
        source_path: Provenance path to source artifact (may be None).
    """

    assumed_fee_bps: float = 0.0
    assumed_slippage_bps: float = 0.0
    assumed_total_cost_bps: float = 0.0
    observed_avg_shortfall_bps: float = 0.0
    observed_entry_shortfall_bps: float = 0.0
    observed_exit_shortfall_bps: float = 0.0
    delta_bps: float = 0.0
    record_count: int = 0
    family_id: Optional[str] = None
    variant_id: Optional[str] = None
    trial_count: Optional[int] = None
    source_path: Optional[str] = None


def ingest_franken_reconciliation(path: str | Path) -> FrankenReconciliationRecord:
    """Parse a Franken reconciliation JSON file.

    Args:
        path: Path to the Franken reconciliation JSON file.

    Returns:
        FrankenReconciliationRecord with fields populated from the JSON.
        Missing fields default to None/0 as appropriate.
    """
    import json

    p = Path(path)
    raw = json.loads(p.read_text())

    return FrankenReconciliationRecord(
        family_id=raw.get("family_id"),
        variant_id=raw.get("variant_id"),
        trial_count=raw.get("trial_count"),
        observed_avg_shortfall_bps=raw.get("observed_avg_shortfall_bps", 0.0),
        observed_entry_shortfall_bps=raw.get("observed_entry_shortfall_bps", 0.0),
        observed_exit_shortfall_bps=raw.get("observed_exit_shortfall_bps", 0.0),
        record_count=raw.get("record_count", 0),
        source_path=str(p),
    )


def compare_record(
    record: FrankenReconciliationRecord,
    economics_summary: EconomicsSummary,
) -> CalibrationComparison:
    """Compare a Franken reconciliation record against Qnty EconomicsSummary.

    Args:
        record: Franken reconciliation record with observed shortfall metrics.
        economics_summary: Qnty economics summary with assumed costs.

    Returns:
        CalibrationComparison showing assumed vs observed and delta.
    """
    assumed_total = economics_summary.assumed_total_cost_bps
    delta = record.observed_avg_shortfall_bps - assumed_total

    return CalibrationComparison(
        assumed_fee_bps=economics_summary.fee_bps,
        assumed_slippage_bps=economics_summary.slippage_bps,
        assumed_total_cost_bps=assumed_total,
        observed_avg_shortfall_bps=record.observed_avg_shortfall_bps,
        observed_entry_shortfall_bps=record.observed_entry_shortfall_bps,
        observed_exit_shortfall_bps=record.observed_exit_shortfall_bps,
        delta_bps=delta,
        record_count=record.record_count,
        family_id=record.family_id,
        variant_id=record.variant_id,
        trial_count=record.trial_count,
        source_path=record.source_path,
    )


def compare_reconciliation_dir(
    dir_path: str | Path,
) -> list[CalibrationComparison]:
    """Scan a directory for Franken reconciliation JSON files.

    Args:
        dir_path: Directory containing Franken reconciliation files.

    Returns:
        List of CalibrationComparison objects, one per found file.
    """
    d = Path(dir_path)
    comparisons: list[CalibrationComparison] = []

    # Use the existing receipt artifact discovery pattern if available,
    # otherwise fall back to globbing for *reconciliation*.json files.
    artifact_paths = list(d.glob("*reconciliation*.json"))

    for path in artifact_paths:
        try:
            record = ingest_franken_reconciliation(path)
            # When scanning a directory we don't have EconomicsSummary context,
            # so we construct a minimal comparison that carries the observed data.
            # Delta cannot be computed without assumed costs — set to 0.
            comp = CalibrationComparison(
                observed_avg_shortfall_bps=record.observed_avg_shortfall_bps,
                observed_entry_shortfall_bps=record.observed_entry_shortfall_bps,
                observed_exit_shortfall_bps=record.observed_exit_shortfall_bps,
                delta_bps=0.0,  # assumed_total_cost_bps unknown in this path
                record_count=record.record_count,
                family_id=record.family_id,
                variant_id=record.variant_id,
                trial_count=record.trial_count,
                source_path=record.source_path,
            )
            comparisons.append(comp)
        except Exception:
            # Skip files that fail to parse — structural observability only.
            continue

    return comparisons


def classify_calibration_status(delta_bps: float, record_count: int) -> str:
    """Classify calibration status based on delta magnitude and sample size.

    Policy knobs (inspectable at module level):
        INSUFFICIENT_DATA_MIN_RECORDS  : minimum record count for classification
        MILD_MISMATCH_THRESHOLD_BPS    : |delta| above this → mild mismatch
        MATERIAL_MISMATCH_THRESHOLD_BPS: |delta| above this → material mismatch

    Status values:
        insufficient_data : record_count below threshold
        aligned            : |delta| <= threshold with sufficient records
        mild_mismatch      : threshold < |delta| <= material
        material_mismatch  : |delta| > material threshold

    Returns:
        One of: "insufficient_data", "aligned", "mild_mismatch", "material_mismatch"
    """
    if record_count < INSUFFICIENT_DATA_MIN_RECORDS:
        return "insufficient_data"

    abs_delta = abs(delta_bps)
    if abs_delta <= MILD_MISMATCH_THRESHOLD_BPS:
        return "aligned"
    elif abs_delta <= MATERIAL_MISMATCH_THRESHOLD_BPS:
        return "mild_mismatch"
    else:
        return "material_mismatch"
