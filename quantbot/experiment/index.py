"""Minimal experiment index for reading and comparing existing artifacts.

Paper mode only - no live trading, no profitability claims.
Reads existing experiment_result.json or walkforward_result.json files
and produces a stable normalized summary suitable for sorting/comparison.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Literal, Optional

from quantbot.experiment.result import PromotionSummary, PromotionVerdict


@dataclass
class EligibilityResult:
    """Result of eligibility evaluation for research review.

    Attributes:
        eligible_for_review: True if the artifact meets all eligibility criteria.
        ineligibility_reasons: List of reasons why the artifact is not eligible.
    """

    eligible_for_review: bool
    ineligibility_reasons: list[str]


@dataclass
class IndexedExperiment:
    """Normalized summary of an experiment artifact.

    Provides a stable shape for sorting and comparing experiment runs
    regardless of whether the source is a single experiment or walk-forward.

    Attributes:
        experiment_name: Name of the experiment.
        strategy_name: Name of the strategy used.
        fixture_name: Name of the data fixture used.
        gate_status: Gate verdict status ("PASS", "FAIL") or None if no gate run.
        split_count: Number of splits (0 for single experiment, >0 for walk-forward).
        signal_count: Total signals (aggregate for walk-forward).
        receipt_digest: SHA256 digest of the receipt, or None if not present.
        artifact_path: Path to the source artifact file.
        result_type: "single" for experiment_result.json, "walkforward" for walkforward_result.json.
        family_id: Trial family identifier, or None if not present in artifact.
        variant_id: Variant identifier, or None if not present in artifact.
        trial_count: Cumulative trial count, or None if not present in artifact.
        fee_bps: Trading fee in basis points.
        slippage_bps: Slippage assumption in basis points.
        eligible_for_review: True if artifact meets eligibility criteria for research review.
        ineligibility_reasons: List of reasons for ineligibility (empty if eligible).
    """

    experiment_name: str
    strategy_name: str
    fixture_name: str
    gate_status: Optional[str]
    split_count: int
    signal_count: int
    receipt_digest: Optional[str]
    artifact_path: Path
    result_type: Literal["single", "walkforward"]
    family_id: Optional[str] = None
    variant_id: Optional[str] = None
    trial_count: Optional[int] = None
    fee_bps: float = 0.0
    slippage_bps: float = 0.0
    economics_summary: Optional[dict[str, Any]] = None
    return_summary: Optional[dict[str, Any]] = None
    inference_summary: Optional[dict[str, Any]] = None
    inferential_summary: Optional[dict[str, Any]] = None
    eligible_for_review: bool = False
    ineligibility_reasons: list[str] = None
    calibration: "CalibrationComparison | None" = field(default=None)
    overfitting_summary: Optional[dict[str, Any]] = None
    robustness_summary: Optional[dict[str, Any]] = None
    promotion_classification: Optional[dict[str, Any]] = None

    def __post_init__(self) -> None:
        if self.ineligibility_reasons is None:
            self.ineligibility_reasons = []

    def gate_passed(self) -> bool:
        """Return True if gate status is PASS."""
        return self.gate_status == "PASS"

    def gate_failed(self) -> bool:
        """Return True if gate status is FAIL."""
        return self.gate_status == "FAIL"


def _load_experiment_result(path: Path) -> dict:
    """Load and parse an experiment_result.json file."""
    with path.open("r", encoding="utf-8") as f:
        return json.load(f)


def _load_walkforward_result(path: Path) -> dict:
    """Load and parse a walkforward_result.json file."""
    with path.open("r", encoding="utf-8") as f:
        return json.load(f)


def _extract_gate_status(data: dict) -> Optional[str]:
    """Extract gate status from artifact data dict."""
    gate = data.get("gate_verdict")
    if gate is None:
        return None
    return gate.get("status")


def evaluate_eligibility(artifact_data: dict[str, Any]) -> EligibilityResult:
    """Evaluate whether an artifact is eligible for research review.

    Checks for required fields: family_id, variant_id, trial_count, cost assumptions,
    and a passing gate status.

    Args:
        artifact_data: The parsed artifact JSON data.

    Returns:
        EligibilityResult with eligible status and list of ineligibility reasons.
    """
    reasons: list[str] = []

    # Check family_id
    family_id = artifact_data.get("family_id") or artifact_data.get("spec", {}).get("family_id")
    if not family_id:
        reasons.append("missing family_id")

    # Check variant_id
    variant_id = artifact_data.get("variant_id") or artifact_data.get("spec", {}).get("variant_id")
    if not variant_id:
        reasons.append("missing variant_id")

    # Check trial_count
    trial_count = artifact_data.get("trial_count")
    if trial_count is None:
        reasons.append("missing trial_count")

    # Check cost assumptions (fee_bps and slippage_bps)
    fee_bps = artifact_data.get("fee_bps")
    slippage_bps = artifact_data.get("slippage_bps")
    if fee_bps is None or slippage_bps is None:
        reasons.append("missing cost assumptions (fee_bps or slippage_bps)")

    # Check gate_status
    gate_status = artifact_data.get("gate_verdict", {}).get("status") if isinstance(artifact_data.get("gate_verdict"), dict) else None
    if gate_status != "PASS":
        reasons.append(f"gate_status != PASS (got: {gate_status})")

    return EligibilityResult(
        eligible_for_review=len(reasons) == 0,
        ineligibility_reasons=reasons
    )


def _evaluate_hard_gates(exp: IndexedExperiment) -> tuple[Literal["PASS", "FAIL"], list[str]]:
    """Evaluate hard gate criteria for promotion eligibility.

    Hard gates (all must pass):
        - bar_count > 0 (single) / split_count >= 2 (walkforward)
        - signal_count >= 3 (single) / total_signal_count >= 5 (walkforward)
        - gate_status == PASS

    Returns:
        Tuple of (gate_status, list of failure reasons)
    """
    reasons: list[str] = []

    if exp.result_type == "single":
        # Single experiment: bar_count > 0, signal_count >= 3
        bar_count = exp.inference_summary.get("bar_count_for_returns", 0) if exp.inference_summary else 0
        signal_count = exp.signal_count

        if bar_count == 0:
            reasons.append("bar_count is zero")
        if signal_count < 3:
            reasons.append(f"signal_count {signal_count} < 3 (degenerate threshold)")
    else:
        # Walkforward: split_count >= 2, total_signal_count >= 5
        split_count = exp.split_count
        signal_count = exp.signal_count  # aggregate_signal_count for walkforward

        if split_count < 2:
            reasons.append(f"split_count {split_count} < 2 (minimum viable)")
        if signal_count < 5:
            reasons.append(f"total_signal_count {signal_count} < 5 (aggregate minimum)")

    # Gate status must be PASS
    if exp.gate_status != "PASS":
        reasons.append(f"gate_status is {exp.gate_status}, expected PASS")

    status: Literal["PASS", "FAIL"] = "FAIL" if reasons else "PASS"
    return status, reasons


def _evaluate_eligibility_fields(exp: IndexedExperiment) -> tuple[Literal["PASS", "FAIL"], list[str]]:
    """Evaluate presence of required eligibility fields.

    Required fields:
        - family_id
        - variant_id
        - trial_count
        - fee_bps
        - slippage_bps

    Returns:
        Tuple of (eligibility_status, list of missing field reasons)
    """
    reasons: list[str] = []

    if not exp.family_id:
        reasons.append("missing family_id")
    if not exp.variant_id:
        reasons.append("missing variant_id")
    if exp.trial_count is None:
        reasons.append("missing trial_count")
    if exp.fee_bps is None or exp.fee_bps == 0.0:
        reasons.append("missing or zero fee_bps")
    if exp.slippage_bps is None or exp.slippage_bps == 0.0:
        reasons.append("missing or zero slippage_bps")

    status: Literal["PASS", "FAIL"] = "FAIL" if reasons else "PASS"
    return status, reasons


def _collect_review_signals(exp: IndexedExperiment) -> tuple[dict[str, Any], list[str], list[str]]:
    """Collect soft review signals for observability.

    These signals are OBSERVATIONAL only and do NOT gate promotion.

    Returns:
        Tuple of (review_signals dict, provisional_flags list, review_signal_flags list)
    """
    signals: dict[str, Any] = {}
    provisional_flags: list[str] = []
    review_signal_flags: list[str] = []

    # Economics
    if exp.economics_summary:
        signals["economics"] = {
            "fee_bps": exp.economics_summary.get("fee_bps"),
            "slippage_bps": exp.economics_summary.get("slippage_bps"),
            "assumed_total_cost_bps": exp.economics_summary.get("assumed_total_cost_bps"),
            "cost_side_count": exp.economics_summary.get("cost_side_count"),
        }

    # Returns
    if exp.return_summary:
        signals["returns"] = {
            "gross_return_total": exp.return_summary.get("gross_return_total"),
            "net_return_total": exp.return_summary.get("net_return_total"),
        }

    # Inferential signals (PSR, DSR, skewness, kurtosis)
    if exp.inferential_summary:
        inf = exp.inferential_summary
        signals["inferential"] = {
            "psr": inf.get("psr"),
            "dsr": inf.get("dsr"),
            "dsr_provisional": inf.get("dsr_provisional", False),
            "dsr_trial_semantics_note": inf.get("dsr_trial_semantics_note", ""),
            "sharpe_like": inf.get("sharpe_like"),
            "skewness": inf.get("skewness"),
            "kurtosis": inf.get("kurtosis"),
        }
        # PSR assumes i.i.d. normality - mark as provisional if PSR is present
        if inf.get("psr") is not None:
            provisional_flags.append("psr_assumes_iid")
        # DSR trial semantics are exploration count, not independent trials
        if inf.get("dsr") is not None and inf.get("dsr_provisional"):
            provisional_flags.append("dsr_trial_semantics_exploration_count")

    # Cost robustness
    if exp.robustness_summary:
        break_even = exp.robustness_summary.get("break_even_cost_multiplier")
        if break_even is not None:
            signals["cost_robustness"] = {
                "break_even_cost_multiplier": break_even,
            }

    # PBO (provisional - non-canonical path-dispersion proxy)
    if exp.overfitting_summary:
        pbo = exp.overfitting_summary.get("pbo")
        if pbo is not None:
            signals["pbo"] = {
                "pbo": pbo,
                "path_count": exp.overfitting_summary.get("path_count"),
                "method": exp.overfitting_summary.get("method"),
            }
            provisional_flags.append("pbo_non_canonical")

    # Calibration delta_bps (requires external Franken data)
    if exp.calibration is not None:
        signals["calibration"] = {
            "delta_bps": exp.calibration.delta_bps,
            "assumed_total_cost_bps": exp.calibration.assumed_total_cost_bps,
            "observed_avg_shortfall_bps": exp.calibration.observed_avg_shortfall_bps,
            "record_count": exp.calibration.record_count,
        }
        provisional_flags.append("calibration_requires_external_franken")

    # Sharpe-like without interval (annualization issue)
    if exp.inference_summary:
        sharpe_like = exp.inference_summary.get("sharpe_like")
        interval = exp.inference_summary.get("interval", "unknown")
        if sharpe_like is not None and interval == "unknown":
            provisional_flags.append("sharpe_like_without_interval")

    # Review signal flags: detect signals that warrant review
    # (these are observational flags, not hard gates)
    if exp.inferential_summary:
        psr = exp.inferential_summary.get("psr")
        dsr = exp.inferential_summary.get("dsr")
        dsr_prov = exp.inferential_summary.get("dsr_provisional", False)
        if psr is not None and psr < 0.5:
            review_signal_flags.append("psr_below_0.5")
        if dsr is not None and dsr < 0.5:
            review_signal_flags.append("dsr_below_0.5")
        if dsr_prov:
            review_signal_flags.append("dsr_provisional_trial_semantics")

    if exp.robustness_summary:
        break_even = exp.robustness_summary.get("break_even_cost_multiplier")
        if break_even is not None and break_even < 1.0:
            review_signal_flags.append("break_even_below_1.0")

    if exp.calibration is not None:
        delta = exp.calibration.delta_bps
        record_count = exp.calibration.record_count
        if record_count >= 10 and abs(delta) > 5.0:
            review_signal_flags.append("calibration_material_mismatch")

    return signals, provisional_flags, review_signal_flags


def classify_promotion(exp: IndexedExperiment) -> PromotionVerdict:
    """Classify a shortlisted candidate for Qnty → Franken promotion.

    PAPER/SHADOW CONTRACT ONLY - NOT for live trading.

    Hard gates (all must pass):
        - bar_count > 0 (single) / split_count >= 2 (walkforward)
        - signal_count >= 3 (single) / total_signal_count >= 5 (walkforward)
        - gate_status == PASS

    Soft review signals are OBSERVATIONAL only.

    Provisional dimensions (surfaced but NOT used as gates):
        - pbo (non-canonical path-dispersion proxy)
        - dsr_trial_semantics (exploration count, not independent trials)
        - calibration_delta_bps (requires external Franken data)
        - psr assumes i.i.d. (may not hold)
        - sharpe_like without interval (annualization issue)

    Classification Logic:
        - paper_eligible: ALL hard gates PASS AND ALL eligibility fields present AND no provisional issues
        - paper_review_required: ALL hard gates PASS AND ALL eligibility fields present BUT has provisional signals
        - paper_ineligible: ANY hard gate FAIL OR any eligibility field missing
    """
    # Evaluate hard gates
    hard_gate_status, hard_gate_reasons = _evaluate_hard_gates(exp)

    # Evaluate eligibility fields
    eligibility_status, eligibility_reasons = _evaluate_eligibility_fields(exp)

    # Collect review signals
    review_signals, provisional_flags, review_signal_flags = _collect_review_signals(exp)

    # Honest caveats
    honest_caveats = [
        "PAPER/SHADOW CONTRACT ONLY - NOT for live trading.",
        "Hard gates evaluate structural criteria only, not profitability.",
        "Soft review signals are OBSERVATIONAL - they do NOT constitute proof of edge.",
        "PSR assumes i.i.d. returns - this assumption may not hold in practice.",
        "DSR trial semantics reflect exploration count, not independent trials.",
        "PBO is a non-canonical path-dispersion proxy - not a standard metric.",
        "calibration_delta_bps requires external Franken data not available here.",
        "Sharpe-like without known interval cannot be annualized.",
        "This contract cannot claim alpha, profitability, or readiness for live trading.",
    ]

    # Provenance
    provenance = {
        "artifact_path": str(exp.artifact_path),
        "family_id": exp.family_id,
        "variant_id": exp.variant_id,
        "trial_count": exp.trial_count,
        "result_type": exp.result_type,
    }

    # Classification logic
    if hard_gate_status == "FAIL" or eligibility_status == "FAIL":
        classification: Literal["paper_eligible", "paper_review_required", "paper_ineligible"] = "paper_ineligible"
    elif len(provisional_flags) > 0:
        classification = "paper_review_required"
    else:
        classification = "paper_eligible"

    return PromotionVerdict(
        classification=classification,
        hard_gate_status=hard_gate_status,
        hard_gate_reasons=hard_gate_reasons,
        eligibility_status=eligibility_status,
        eligibility_reasons=eligibility_reasons,
        review_signals=review_signals,
        review_signal_flags=review_signal_flags,
        provisional_flags=provisional_flags,
        provenance=provenance,
        honest_caveats=honest_caveats,
    )


def compute_promotion_summary(exp: IndexedExperiment) -> PromotionSummary:
    """Compute a full promotion summary for an indexed experiment.

    PAPER/SHADOW CONTRACT ONLY - NOT for live trading.
    """
    verdict = classify_promotion(exp)
    generated_at = datetime.now(timezone.utc).isoformat()

    return PromotionSummary(
        contract_version="1.0.0",
        generated_at=generated_at,
        artifact_path=str(exp.artifact_path),
        experiment_name=exp.experiment_name,
        family_id=exp.family_id,
        variant_id=exp.variant_id,
        result_type=exp.result_type,
        verdict=verdict,
    )


def _find_calibration_for_artifact(
    artifact: IndexedExperiment,
    calibration_dir: Path | None,
) -> "CalibrationComparison | None":
    """Find a calibration comparison for an artifact by matching family_id, variant_id, trial_count.

    Args:
        artifact: The indexed experiment to find calibration for.
        calibration_dir: Directory containing Franken reconciliation files, or None.

    Returns:
        CalibrationComparison if found, None otherwise.
    """
    if calibration_dir is None or not calibration_dir.exists():
        return None

    from quantbot.experiment.calibration import compare_reconciliation_dir

    try:
        comparisons = compare_reconciliation_dir(calibration_dir)
    except Exception:
        return None

    for comp in comparisons:
        if (
            comp.family_id == artifact.family_id
            and comp.variant_id == artifact.variant_id
            and comp.trial_count == artifact.trial_count
        ):
            # Compute assumed_total_cost_bps and delta_bps from artifact fee/slippage
            assumed_total = artifact.fee_bps + artifact.slippage_bps
            comp.assumed_fee_bps = artifact.fee_bps
            comp.assumed_slippage_bps = artifact.slippage_bps
            comp.assumed_total_cost_bps = assumed_total
            comp.delta_bps = comp.observed_avg_shortfall_bps - assumed_total
            return comp

    return None


def index_experiment_artifacts(
    paths: list[Path],
    calibration_dir: Path | None = None,
) -> list[IndexedExperiment]:
    """Read experiment artifact files and produce normalized summaries.

    Accepts paths to either experiment_result.json or walkforward_result.json
    files (or directories containing them). Produces a stable normalized summary
    for each artifact that can be sorted and compared.

    Args:
        paths: List of paths to artifact JSON files or directories.
               If a directory is given, looks for experiment_result.json
               or walkforward_result.json inside it.

    Returns:
        List of IndexedExperiment summaries, one per valid artifact found.

    Raises:
        FileNotFoundError: If a specified path does not exist.
        ValueError: If a file is not a recognized experiment artifact.
    """
    results: list[IndexedExperiment] = []

    for path in paths:
        if not path.exists():
            raise FileNotFoundError(f"Path does not exist: {path}")

        # If directory, look for artifact files inside
        if path.is_dir():
            if (path / "experiment_result.json").exists():
                artifact_path = path / "experiment_result.json"
            elif (path / "walkforward_result.json").exists():
                artifact_path = path / "walkforward_result.json"
            else:
                continue  # Skip directories without artifacts
        else:
            artifact_path = path

        filename = artifact_path.name

        if filename == "experiment_result.json":
            data = _load_experiment_result(artifact_path)
            eligibility = evaluate_eligibility(data)
            indexed = IndexedExperiment(
                experiment_name=data.get("experiment_name", ""),
                strategy_name=data.get("strategy_name", ""),
                fixture_name=data.get("fixture_name", ""),
                gate_status=_extract_gate_status(data),
                split_count=0,
                signal_count=data.get("signal_count", 0),
                receipt_digest=data.get("receipt_digest"),
                artifact_path=artifact_path,
                result_type="single",
                family_id=data.get("family_id"),
                variant_id=data.get("variant_id"),
                trial_count=data.get("trial_count"),
                fee_bps=data.get("fee_bps", 0.0),
                slippage_bps=data.get("slippage_bps", 0.0),
                economics_summary=data.get("economics_summary"),
                return_summary=data.get("return_summary"),
                inference_summary=data.get("inference_summary"),
                inferential_summary=data.get("inferential_summary"),
                eligible_for_review=eligibility.eligible_for_review,
                ineligibility_reasons=eligibility.ineligibility_reasons,
                overfitting_summary=data.get("overfitting_summary"),
            )
            indexed.calibration = _find_calibration_for_artifact(indexed, calibration_dir)
            # Compute promotion classification
            verdict = classify_promotion(indexed)
            indexed.promotion_classification = verdict.to_dict()
            results.append(indexed)

        elif filename == "walkforward_result.json":
            data = _load_walkforward_result(artifact_path)
            eligibility = evaluate_eligibility(data)
            indexed = IndexedExperiment(
                experiment_name=data.get("experiment_name", ""),
                strategy_name=data.get("strategy_name", ""),
                fixture_name=data.get("fixture_name", ""),
                gate_status=_extract_gate_status(data),
                split_count=data.get("split_count", 0),
                signal_count=data.get("aggregate_signal_count", 0),
                receipt_digest=None,  # Walk-forward results don't expose a single receipt digest
                artifact_path=artifact_path,
                result_type="walkforward",
                family_id=data.get("family_id"),
                variant_id=data.get("variant_id"),
                trial_count=data.get("trial_count"),
                fee_bps=data.get("fee_bps", 0.0),
                slippage_bps=data.get("slippage_bps", 0.0),
                economics_summary=data.get("economics_summary"),
                return_summary=data.get("return_summary"),
                inference_summary=data.get("inference_summary"),
                inferential_summary=data.get("inferential_summary"),
                eligible_for_review=eligibility.eligible_for_review,
                ineligibility_reasons=eligibility.ineligibility_reasons,
                overfitting_summary=data.get("overfitting_summary"),
                robustness_summary=data.get("robustness_summary"),
            )
            indexed.calibration = _find_calibration_for_artifact(indexed, calibration_dir)
            # Compute promotion classification
            verdict = classify_promotion(indexed)
            indexed.promotion_classification = verdict.to_dict()
            results.append(indexed)

        else:
            raise ValueError(
                f"Unrecognized experiment artifact: {artifact_path}. "
                "Expected experiment_result.json or walkforward_result.json."
            )

    return results
