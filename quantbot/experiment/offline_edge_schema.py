"""Schema TypedDicts and verdict constants for offline edge validation receipts.

PR A — safe skeleton only. No exchange, engine, or DB imports.
Stdlib only (typing, dataclasses, datetime).
"""

from __future__ import annotations

from typing import TypedDict


# ── Verdict Constants ──────────────────────────────────────────────────
# Allowed in skeleton mode (PR A)
SKELETON_ONLY: str = "SKELETON_ONLY"
INCONCLUSIVE: str = "INCONCLUSIVE"

# Placeholder fingerprint for when no input directories are provided
PLACEHOLDER_SKELETON_NO_OP: str = "PLACEHOLDER_SKELETON_NO_OP"

# PR D — fixture-only volnorm reconstruction stage identity.  This is a
# SKELETON_ONLY stage: it reconstructs a deterministic weight from fixture bars
# and does NOT compute strategy PnL or emit an edge verdict.
FIXTURE_VOLNORM_STAGE_ID: str = "A"
FIXTURE_VOLNORM_STAGE_NAME: str = "fixture_volnorm_reconstruction"

# Forbidden future verdicts — named here for refusal tests only
EDGE_CANDIDATE: str = "EDGE_CANDIDATE"
NO_EDGE: str = "NO_EDGE"
NEEDS_MORE_DATA: str = "NEEDS_MORE_DATA"
BLOCKED_BY_DATA_QUALITY: str = "BLOCKED_BY_DATA_QUALITY"


# ── TypedDicts ─────────────────────────────────────────────────────────

class ReceiptMetadata(TypedDict):
    """Metadata describing the tool and pipeline that produced a receipt."""

    tool_name: str
    tool_version: str
    timestamp_utc: str
    pipeline_description: str


class CostModelAssumptions(TypedDict, total=False):
    """Deterministic cost-model assumptions used during validation.

    The original PR-A keys (slippage/commission/heat_cap/vol_*) remain for
    backwards compatibility.  PR C adds fixture-only cost-model fields
    (``cost_model_version``, ``spread_bps_per_side``, ``funding_cost_placeholder``).
    ``total=False`` keeps every key optional so existing receipts stay valid.
    """

    slippage_bps_per_side: float
    commission_bps_per_side: float
    heat_cap: float
    vol_lookback_bars: int
    vol_floor: float
    # PR C — fixture-only cost-model additions.
    cost_model_version: str
    spread_bps_per_side: float
    funding_cost_placeholder: float


class StageMetrics(TypedDict):
    """Per-stage outcome for one stage (A-F) of the validation pipeline."""

    stage_id: str
    stage_name: str
    status: str  # PASS | FAIL | SKIP | SKELETON_ONLY
    summary: str


class ValidationReceipt(TypedDict):
    """Top-level receipt produced by the offline edge validation pipeline."""

    validation_receipt: ReceiptMetadata
    input_manifest_fingerprint: str  # SHA256
    cost_model_assumptions: CostModelAssumptions
    per_stage_metrics: dict[str, StageMetrics]
    final_verdict: str


# ── Helper Functions ───────────────────────────────────────────────────

def validate_skeleton_verdict(verdict: str) -> str:
    """Validate that *verdict* is SKELETON_ONLY or INCONCLUSIVE.

    Raises
    ------
    ValueError
        If *verdict* is ``EDGE_CANDIDATE`` or any other disallowed value.

    Returns
    -------
    str
        The verdict string if valid.
    """
    allowed = {SKELETON_ONLY, INCONCLUSIVE}
    if verdict not in allowed:
        raise ValueError(
            f"Verdict '{verdict}' is not allowed in skeleton mode. "
            f"Allowed: {allowed}"
        )
    return verdict