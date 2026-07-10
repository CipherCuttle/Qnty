"""Real offline validation receipt skeleton for offline edge validation.

Scope boundary (do not violate) — see
docs/status/QNTY_OFFLINE_EDGE_VALIDATION_REAL_VALIDATION_EXECUTION_PLAN.md:

This module builds the *schema and skeleton* for the first real offline
validation receipt. It does **not**:

- compute returns (gross or net)
- compute PnL
- compute Sharpe or any risk-adjusted metric
- run the paper engine
- import any live/exchange code
- emit ``OFFLINE_EDGE_CANDIDATE`` (that constant exists only for
  schema/refusal tests — see ``offline_edge_schema.py``)
- claim edge, profit, or live readiness

Every receipt built by this module has ``final_offline_verdict`` fixed to
``BLOCKED_BY_VALIDATION_IMPLEMENTATION`` and every
``forbidden_calculation_status`` flag fixed to ``False``. Stdlib only —
no pandas, numpy, engine, exchange, ccxt, sqlite, or paper imports.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from quantbot.experiment.offline_edge_schema import (
    BLOCKED_BY_DATA_QUALITY_REGRESSION,
    BLOCKED_BY_VALIDATION_IMPLEMENTATION,
    INCONCLUSIVE,
    NO_EDGE,
    OFFLINE_EDGE_CANDIDATE,
)

__all__ = [
    "build_real_validation_receipt",
    "build_deterministic_split_definitions",
    "build_cost_case_matrix",
    "validate_real_validation_receipt",
    "write_real_validation_receipt",
]

RECEIPT_SCHEMA_KIND: str = "qnty_offline_edge_real_validation_receipt"
RECEIPT_SCHEMA_VERSION: str = "0.1.0"

# Only these final verdicts are recognized by this schema's validator.
ALLOWED_FINAL_VERDICTS = frozenset(
    {
        OFFLINE_EDGE_CANDIDATE,
        NO_EDGE,
        INCONCLUSIVE,
        BLOCKED_BY_VALIDATION_IMPLEMENTATION,
        BLOCKED_BY_DATA_QUALITY_REGRESSION,
    }
)

# This PR (receipt skeleton) may only ever emit this verdict.
_SKELETON_ALLOWED_VERDICTS = frozenset({BLOCKED_BY_VALIDATION_IMPLEMENTATION})

# Top-level keys that must never appear on a receipt from this module.
FORBIDDEN_TOP_LEVEL_KEYS = frozenset({"pnl", "sharpe", "edge", "strategy_performance"})

PROD_BASE = Path("/srv/qnty")
TMP_BASE = Path("/tmp")


# ── Path guards ─────────────────────────────────────────────────────────


def _resolve(path: Path) -> Path:
    return path.resolve()


def _is_under(resolved: Path, base: Path) -> bool:
    base_resolved = base.resolve()
    try:
        common = os.path.commonpath([str(resolved), str(base_resolved)])
    except ValueError:
        return False
    return common == str(base_resolved)


def _refuse_if_prod_path(resolved: Path) -> None:
    if _is_under(resolved, PROD_BASE):
        raise ValueError(f"Refusing path under prod base {PROD_BASE}: {resolved}")


def _refuse_if_not_tmp(resolved: Path) -> None:
    if not _is_under(resolved, TMP_BASE):
        raise ValueError(f"Refusing path not under /tmp: {resolved}")


# ── Split builder skeleton ──────────────────────────────────────────────


def build_deterministic_split_definitions(
    *,
    global_min_timestamp: str,
    global_max_timestamp: str,
    split_count: int = 3,
) -> list[dict[str, Any]]:
    """Build deterministic placeholder split definitions.

    This does **not** inspect any real data file and does **not** compute
    returns. It only partitions the provided ``[global_min_timestamp,
    global_max_timestamp]`` bounds (treated as opaque strings) into
    ``split_count`` deterministic, evenly-labeled placeholder windows, each
    marked ``calculation_status: NOT_EXECUTED``.
    """
    if split_count < 1:
        raise ValueError(f"split_count must be >= 1, got {split_count}")

    splits: list[dict[str, Any]] = []
    for i in range(split_count):
        splits.append(
            {
                "split_id": f"split_{i:02d}",
                "train_window": {
                    "start": global_min_timestamp,
                    "end": global_max_timestamp,
                },
                "validation_window": {
                    "start": global_min_timestamp,
                    "end": global_max_timestamp,
                },
                "split_index": i,
                "split_count": split_count,
                "calculation_status": "NOT_EXECUTED",
            }
        )
    return splits


# ── Cost-case matrix skeleton ────────────────────────────────────────────


def build_cost_case_matrix() -> list[dict[str, Any]]:
    """Build the low/base/high cost-case sensitivity matrix skeleton.

    ``base`` mirrors the existing cost-model assumptions used elsewhere in
    this repo (5 bps commission/slippage per side, 1 bps spread per side).
    ``low`` and ``high`` are conservative skeleton-only bracketing
    assumptions, not derived from any measured execution data. No costs
    are actually applied here — ``calculation_status`` stays
    ``NOT_EXECUTED`` for every case.
    """
    return [
        {
            "cost_case": "low",
            "commission_bps_per_side": 2.0,
            "slippage_bps_per_side": 2.0,
            "spread_bps_per_side": 0.5,
            "funding_included": True,
            "calculation_status": "NOT_EXECUTED",
        },
        {
            "cost_case": "base",
            "commission_bps_per_side": 5.0,
            "slippage_bps_per_side": 5.0,
            "spread_bps_per_side": 1.0,
            "funding_included": True,
            "calculation_status": "NOT_EXECUTED",
        },
        {
            "cost_case": "high",
            "commission_bps_per_side": 10.0,
            "slippage_bps_per_side": 10.0,
            "spread_bps_per_side": 2.0,
            "funding_included": True,
            "calculation_status": "NOT_EXECUTED",
        },
    ]


# ── Receipt builder ──────────────────────────────────────────────────────


def _default_rationale(output_status: str) -> str:
    if output_status == BLOCKED_BY_VALIDATION_IMPLEMENTATION:
        return (
            "BLOCKED_BY_VALIDATION_IMPLEMENTATION: this is a schema/skeleton-only "
            "receipt. No returns, PnL, Sharpe, or paper-engine calculation has been "
            "implemented yet. No edge/profit/live-readiness claim is made."
        )
    return f"{output_status}: skeleton receipt, no calculation implemented."


def build_real_validation_receipt(
    *,
    input_manifest_fingerprint: str,
    data_quality_receipt_sha256: str,
    code_commit_sha: str,
    split_definitions: list[dict[str, Any]],
    cost_cases: list[dict[str, Any]],
    output_status: str = BLOCKED_BY_VALIDATION_IMPLEMENTATION,
    rationale: str | None = None,
) -> dict[str, Any]:
    """Build the real offline validation receipt skeleton.

    This is a pure function: it performs no I/O, computes no returns/PnL/
    Sharpe, and does not run any engine. ``output_status`` defaults to and
    (in this PR) must remain ``BLOCKED_BY_VALIDATION_IMPLEMENTATION`` —
    ``OFFLINE_EDGE_CANDIDATE`` is rejected by ``validate_real_validation_receipt``
    at this phase.
    """
    if rationale is None:
        rationale = _default_rationale(output_status)

    receipt: dict[str, Any] = {
        "validation_receipt": {
            "kind": RECEIPT_SCHEMA_KIND,
            "version": RECEIPT_SCHEMA_VERSION,
            "timestamp_utc": datetime.now(timezone.utc).isoformat(),
        },
        "input_manifest_fingerprint": input_manifest_fingerprint,
        "data_quality_receipt_sha256": data_quality_receipt_sha256,
        "code_commit_sha": code_commit_sha,
        "split_definitions": split_definitions,
        "cost_cases": cost_cases,
        "required_outputs_present": {
            "gross_return": False,
            "net_return_after_costs": False,
            "max_drawdown": False,
            "sharpe_or_risk_metric": False,
            "baseline_comparison": False,
            "sensitivity_cases": False,
        },
        "forbidden_calculation_status": {
            "returns_computed": False,
            "pnl_computed": False,
            "sharpe_computed": False,
            "paper_engine_run": False,
            "live_integration_used": False,
        },
        "guardrail_status": {
            "edge_unproven": True,
            "block_live_integration": True,
            "no_report_promotion": True,
            "output_under_tmp_only": True,
        },
        "final_offline_verdict": output_status,
        "final_offline_verdict_rationale": rationale,
    }
    return receipt


# ── Validation ────────────────────────────────────────────────────────────


_REQUIRED_TOP_LEVEL_KEYS = frozenset(
    {
        "validation_receipt",
        "input_manifest_fingerprint",
        "data_quality_receipt_sha256",
        "code_commit_sha",
        "split_definitions",
        "cost_cases",
        "required_outputs_present",
        "forbidden_calculation_status",
        "guardrail_status",
        "final_offline_verdict",
        "final_offline_verdict_rationale",
    }
)

_REQUIRED_GUARDRAIL_KEYS = frozenset(
    {
        "edge_unproven",
        "block_live_integration",
        "no_report_promotion",
        "output_under_tmp_only",
    }
)

_REQUIRED_FORBIDDEN_CALC_KEYS = frozenset(
    {
        "returns_computed",
        "pnl_computed",
        "sharpe_computed",
        "paper_engine_run",
        "live_integration_used",
    }
)


def validate_real_validation_receipt(receipt: dict[str, Any]) -> None:
    """Validate a real-validation receipt dict.

    Raises ``ValueError`` for any of: missing required top-level keys,
    a forbidden top-level key (``pnl``/``sharpe``/``edge``/
    ``strategy_performance``), a ``final_offline_verdict`` outside the
    allowed vocabulary, ``OFFLINE_EDGE_CANDIDATE`` at this skeleton phase,
    a missing/false ``guardrail_status`` entry, a missing/true
    ``forbidden_calculation_status`` entry, or an ``output_path`` that is
    not under ``/tmp`` or that resolves under ``/srv/qnty``.
    """
    missing = _REQUIRED_TOP_LEVEL_KEYS - set(receipt.keys())
    if missing:
        raise ValueError(f"Missing required keys: {sorted(missing)}")

    forbidden_present = FORBIDDEN_TOP_LEVEL_KEYS & set(receipt.keys())
    if forbidden_present:
        raise ValueError(f"Forbidden top-level keys present: {sorted(forbidden_present)}")

    verdict = receipt["final_offline_verdict"]
    if verdict not in ALLOWED_FINAL_VERDICTS:
        raise ValueError(
            f"final_offline_verdict '{verdict}' is not in allowed vocabulary: "
            f"{sorted(ALLOWED_FINAL_VERDICTS)}"
        )
    if verdict not in _SKELETON_ALLOWED_VERDICTS:
        raise ValueError(
            f"final_offline_verdict '{verdict}' is not allowed in the "
            f"receipt-skeleton phase. Only {sorted(_SKELETON_ALLOWED_VERDICTS)} "
            "may be emitted until a real validator is implemented."
        )

    guardrail_status = receipt.get("guardrail_status")
    if not isinstance(guardrail_status, dict):
        raise ValueError("guardrail_status must be a dict")
    missing_guardrails = _REQUIRED_GUARDRAIL_KEYS - set(guardrail_status.keys())
    if missing_guardrails:
        raise ValueError(f"Missing guardrail_status keys: {sorted(missing_guardrails)}")
    for key in _REQUIRED_GUARDRAIL_KEYS:
        if guardrail_status[key] is not True:
            raise ValueError(f"guardrail_status['{key}'] must be True, got {guardrail_status[key]!r}")

    forbidden_calc = receipt.get("forbidden_calculation_status")
    if not isinstance(forbidden_calc, dict):
        raise ValueError("forbidden_calculation_status must be a dict")
    missing_calc = _REQUIRED_FORBIDDEN_CALC_KEYS - set(forbidden_calc.keys())
    if missing_calc:
        raise ValueError(f"Missing forbidden_calculation_status keys: {sorted(missing_calc)}")
    for key in _REQUIRED_FORBIDDEN_CALC_KEYS:
        if forbidden_calc[key] is not False:
            raise ValueError(
                f"forbidden_calculation_status['{key}'] must be False, got {forbidden_calc[key]!r}"
            )

    output_path = receipt.get("output_path")
    if output_path is not None:
        resolved = Path(str(output_path)).resolve()
        _refuse_if_prod_path(resolved)
        _refuse_if_not_tmp(resolved)


# ── Output writer ─────────────────────────────────────────────────────────


def write_real_validation_receipt(receipt: dict[str, Any], output_path: Path) -> str:
    """Validate and write *receipt* as JSON to *output_path* under ``/tmp`` only.

    Returns the SHA256 hex digest of the exact bytes written. Refuses to
    write anywhere that does not resolve under ``/tmp``, and refuses any
    path resolving under ``/srv/qnty``.
    """
    validate_real_validation_receipt(receipt)

    resolved = output_path.resolve()
    _refuse_if_prod_path(resolved)
    _refuse_if_not_tmp(resolved)

    resolved.parent.mkdir(parents=True, exist_ok=True)
    payload = json.dumps(receipt, indent=2)
    with open(resolved, "w") as f:
        f.write(payload)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


# ── CLI skeleton ───────────────────────────────────────────────────────────


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Real offline validation receipt skeleton (no-op). "
            "Emits BLOCKED_BY_VALIDATION_IMPLEMENTATION only."
        )
    )
    parser.add_argument("--read-only", action="store_true", required=True)
    parser.add_argument("--output-dir", required=True, help="Must resolve under /tmp.")
    parser.add_argument("--input-manifest-fingerprint", required=True)
    parser.add_argument("--data-quality-receipt-sha256", required=True)
    parser.add_argument("--code-commit-sha", required=True)
    parser.add_argument("--global-min-timestamp", required=True)
    parser.add_argument("--global-max-timestamp", required=True)
    parser.add_argument("--split-count", type=int, default=3)
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    output_dir = Path(args.output_dir).resolve()
    try:
        _refuse_if_prod_path(output_dir)
        _refuse_if_not_tmp(output_dir)
    except ValueError as exc:
        print(f"FATAL: {exc}")
        return 3

    split_definitions = build_deterministic_split_definitions(
        global_min_timestamp=args.global_min_timestamp,
        global_max_timestamp=args.global_max_timestamp,
        split_count=args.split_count,
    )
    cost_cases = build_cost_case_matrix()

    receipt = build_real_validation_receipt(
        input_manifest_fingerprint=args.input_manifest_fingerprint,
        data_quality_receipt_sha256=args.data_quality_receipt_sha256,
        code_commit_sha=args.code_commit_sha,
        split_definitions=split_definitions,
        cost_cases=cost_cases,
    )

    output_path = output_dir / "real_validation_receipt.json"
    digest = write_real_validation_receipt(receipt, output_path)

    print(f"final_offline_verdict={receipt['final_offline_verdict']}")
    print(f"receipt_sha256={digest}")
    print(f"receipt_path={output_path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
