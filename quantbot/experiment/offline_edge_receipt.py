"""Fixture-only offline edge validation receipt assembler (PR F).

Stdlib-only receipt builder.  No engine, exchange, DB, or paper imports.
Combines existing skeleton pieces into one deterministic fixture-only
validation receipt.
"""

from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from quantbot.experiment.offline_edge_schema import (
    INCONCLUSIVE,
    ReceiptMetadata,
    SKELETON_ONLY,
    validate_skeleton_verdict,
)


def build_guardrail_status() -> dict[str, bool]:
    """Return deterministic guardrail status dict.

    All five guardrails are locked to True in skeleton mode:
    no edge claim, no live integration, fixture-only, long-only/1x only,
    and clean-net-of-carry is explicitly NOT an edge verdict.
    """
    return {
        "edge_unproven": True,
        "block_live_integration": True,
        "clean_net_of_carry_is_not_edge": True,
        "long_only_1x_only": True,
        "fixture_only": True,
    }


def build_fixture_validation_receipt(
    *,
    input_manifest_fingerprint: str,
    input_manifest_summary: dict | None = None,
    cost_model_assumptions: dict | None = None,
    per_stage_metrics: list[dict] | None = None,
    volnorm_fixture_summary: dict | None = None,
    walkforward_fixture_summary: dict | None = None,
    final_verdict: str = SKELETON_ONLY,
    final_verdict_rationale: str | None = None,
) -> dict[str, Any]:
    """Assemble the full fixture validation receipt dict.

    Parameters
    ----------
    input_manifest_fingerprint : str
        SHA256 fingerprint of the input manifest.
    input_manifest_summary : dict or None
        Optional summary of input files discovered.
    cost_model_assumptions : dict or None
        Optional cost-model assumptions dict.
    per_stage_metrics : list[dict] or None
        Optional list of per-stage metric dicts.
    volnorm_fixture_summary : dict or None
        Optional volnorm fixture reconstruction summary.
    walkforward_fixture_summary : dict or None
        Optional walkforward fixture replay summary.
    final_verdict : str
        Verdict string (SKELETON_ONLY or INCONCLUSIVE).
    final_verdict_rationale : str or None
        Optional rationale; auto-generated if None.

    Returns
    -------
    dict
        The full fixture validation receipt.
    """
    # Validate the verdict first
    validate_skeleton_verdict(final_verdict)

    # Generate default rationale if none provided
    if final_verdict_rationale is None:
        if final_verdict == SKELETON_ONLY:
            final_verdict_rationale = (
                "SKELETON_ONLY: fixture-only validation complete. No edge claim made. "
                "No live integration. No strategy PnL."
            )
        else:
            final_verdict_rationale = (
                "INCONCLUSIVE: fixture-only validation incomplete or ambiguous."
            )

    receipt: dict[str, Any] = {
        "validation_receipt": ReceiptMetadata(
            tool_name="qnty_offline_edge_validation",
            tool_version="0.1.0",
            timestamp_utc=datetime.now(timezone.utc).isoformat(),
            pipeline_description=(
                "fixture-only offline edge validation receipt (skeleton)"
            ),
        ),
        "input_manifest_fingerprint": input_manifest_fingerprint,
        "input_manifest_summary": input_manifest_summary,
        "cost_model_assumptions": cost_model_assumptions,
        "per_stage_metrics": per_stage_metrics or [],
        "volnorm_fixture_summary": volnorm_fixture_summary,
        "walkforward_fixture_summary": walkforward_fixture_summary,
        "guardrail_status": build_guardrail_status(),
        "final_verdict": final_verdict,
        "final_verdict_rationale": final_verdict_rationale,
    }

    return receipt


def validate_fixture_receipt(receipt: dict) -> None:
    """Validate a fixture receipt dict has all required keys and values.

    Parameters
    ----------
    receipt : dict
        The receipt dict to validate.

    Raises
    ------
    ValueError
        If any required key is missing or has an invalid value.
    """
    required_keys = [
        "validation_receipt",
        "input_manifest_fingerprint",
        "input_manifest_summary",
        "cost_model_assumptions",
        "per_stage_metrics",
        "volnorm_fixture_summary",
        "walkforward_fixture_summary",
        "guardrail_status",
        "final_verdict",
        "final_verdict_rationale",
    ]

    for key in required_keys:
        if key not in receipt:
            raise ValueError(f"Missing required receipt key: {key}")

    guardrail_keys = [
        "edge_unproven",
        "block_live_integration",
        "clean_net_of_carry_is_not_edge",
        "long_only_1x_only",
        "fixture_only",
    ]

    guardrail_status = receipt["guardrail_status"]
    for gk in guardrail_keys:
        if gk not in guardrail_status:
            raise ValueError(f"Missing required guardrail_status key: {gk}")
        if not isinstance(guardrail_status[gk], bool):
            raise ValueError(
                f"Guardrail key '{gk}' must be bool, got {type(guardrail_status[gk]).__name__}"
            )

    verdict = receipt["final_verdict"]
    if verdict not in (SKELETON_ONLY, INCONCLUSIVE):
        raise ValueError(
            f"Invalid final_verdict: '{verdict}'. Must be SKELETON_ONLY or INCONCLUSIVE."
        )


def write_receipt_json(receipt: dict, output_path: Path) -> None:
    """Write receipt dict to a JSON file at output_path.

    Validates receipt structure before writing. Refuses prod paths.

    Parameters
    ----------
    receipt : dict
        The receipt dict to write.
    output_path : Path
        Path to write the JSON file to.

    Raises
    ------
    ValueError
        If the receipt fails validation or *output_path* is under ``/srv/qnty``.
    """
    validate_fixture_receipt(receipt)

    resolved = output_path.resolve()

    # Robust prod-path guard: use commonpath boundary comparison
    # (same pattern as CLI's _is_under_dir)
    PROD_BASE = Path("/srv/qnty").resolve()
    try:
        common = os.path.commonpath([str(resolved), str(PROD_BASE)])
    except ValueError:
        # commonpath raises ValueError if paths are on different drives;
        # treat as not matching (safe default)
        common = ""
    if common == str(PROD_BASE):
        raise ValueError(f"Refusing to write to prod path: {output_path}")

    resolved.parent.mkdir(parents=True, exist_ok=True)
    with open(resolved, "w") as f:
        json.dump(receipt, f, indent=2)