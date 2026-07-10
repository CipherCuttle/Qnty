"""CLI stub for offline edge validation — skeleton mode only.

PR A — safe skeleton.  No exchange, engine, DB, or paper imports.
Stdlib + schema only.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

from quantbot.experiment.offline_edge_input_manifest import (
    build_input_manifest_summary,
    discover_input_files,
)
from quantbot.experiment.offline_edge_cost_model import COST_MODEL_VERSION
from quantbot.experiment.offline_edge_volnorm import (
    reconstruct_fixture_volnorm_weights,
)
from quantbot.experiment.offline_edge_walkforward import (
    run_fixture_walkforward,
)
from quantbot.experiment.offline_edge_schema import (
    CostModelAssumptions,
    FIXTURE_VOLNORM_STAGE_ID,
    FIXTURE_VOLNORM_STAGE_NAME,
    FIXTURE_WALKFORWARD_STAGE_ID,
    FIXTURE_WALKFORWARD_STAGE_NAME,
    PLACEHOLDER_SKELETON_NO_OP,
    ReceiptMetadata,
    SKELETON_ONLY,
    StageMetrics,
    ValidationReceipt,
)

# ── Constants ─────────────────────────────────────────────────────────────

PROD_PATH_PREFIX = "/srv/qnty"
PROD_PAPER_PNL_V1_PATH = "/srv/qnty/output/paper_pnl_v1"
OFFICIAL_REPORT_PATTERNS = ("paper_verify_report.json", "official_report")
ALLOWED_OUTPUT_PREFIXES = ("/tmp",)


# ── Helpers ────────────────────────────────────────────────────────────────


def _resolve_abs(path_str: str) -> str:
    """Resolve a path string to an absolute, real (no symlinks) path."""
    return os.path.realpath(os.path.abspath(os.path.expanduser(path_str)))


def _is_under_dir(path: str, parent: str) -> bool:
    """Return True if resolved path is strictly under parent directory.

    Uses os.path.commonpath to prevent prefix-bypass attacks like
    /tmp_evil, /tmp123, or /tmp-not-actually-tmp from matching /tmp.

    Examples
    --------
    >>> _is_under_dir("/tmp/qnty-output", "/tmp")
    True
    >>> _is_under_dir("/tmp_evil", "/tmp")
    False
    """
    return os.path.commonpath([path, parent]) == parent


# ── Argument Parser ───────────────────────────────────────────────────────


def build_parser() -> argparse.ArgumentParser:
    """Build the argument parser for the offline edge validation CLI."""
    parser = argparse.ArgumentParser(
        description="Offline edge validation runner (skeleton mode — no-op)."
    )

    parser.add_argument(
        "--read-only",
        action="store_true",
        required=True,
        help="Read-only mode: no mutations to input data or production paths.",
    )
    parser.add_argument(
        "--output-dir",
        required=True,
        help="Directory to write validation_receipt.json (must be under /tmp)",
    )
    parser.add_argument(
        "--bars-dir",
        required=False,
        default=None,
        help="Directory containing bar/candle CSV files",
    )
    parser.add_argument(
        "--funding-dir",
        required=False,
        default=None,
        help="Directory containing funding rate CSV files",
    )
    parser.add_argument(
        "--manifest-dir",
        required=False,
        default=None,
        help="Directory containing manifest JSON files",
    )
    parser.add_argument(
        "--volnorm-bars",
        required=False,
        default=None,
        help=(
            "Fixture bars CSV for deterministic fixture-only volnorm "
            "reconstruction (no PnL, no trades, SKELETON_ONLY only)"
        ),
    )
    parser.add_argument(
        "--walkforward-bars",
        required=False,
        default=None,
        help=(
            "Fixture bars CSV for deterministic fixture-only walk-forward "
            "replay scaffolding (no PnL, no trades, no real funding replay, "
            "SKELETON_ONLY only)"
        ),
    )
    return parser


# ── Prod-path Guard ──────────────────────────────────────────────────────


def refuse_prod_path(path_str: str, output_path: bool = False) -> None:
    """Refuse if path is a production path or (if output_path) not in allowed prefixes.

    All paths are resolved to absolute, real paths before checking.
    output_path=True also checks the positive allowlist (must be under /tmp).

    Parameters
    ----------
    path_str : str
        The path to check.
    output_path : bool
        If True, also enforce the positive allowlist (ALLOWED_OUTPUT_PREFIXES).

    Exits
    -----
    sys.exit(3)
        If the resolved path is not allowed.
    """
    resolved = _resolve_abs(path_str)

    # Positive allowlist for output dirs
    if output_path:
        if not any(_is_under_dir(resolved, prefix) for prefix in ALLOWED_OUTPUT_PREFIXES):
            print(f"FATAL: Output directory must be under {ALLOWED_OUTPUT_PREFIXES}, got: {resolved}")
            sys.exit(3)

    # Negative prod-path refusals (applies to all paths)
    if resolved.startswith(PROD_PATH_PREFIX):
        print(f"Refusing prod path: {resolved}")
        sys.exit(3)

    for pattern in OFFICIAL_REPORT_PATTERNS:
        if pattern in resolved:
            print(f"Refusing official report path: {resolved}")
            sys.exit(3)


# ── Main ─────────────────────────────────────────────────────────────────


def main() -> None:
    """Parse args, guard prod paths, write skeleton receipt, exit 0."""
    parser = build_parser()
    args = parser.parse_args()

    # Guard production paths
    refuse_prod_path(args.output_dir, output_path=True)
    if args.bars_dir is not None:
        refuse_prod_path(args.bars_dir)
    if args.funding_dir is not None:
        refuse_prod_path(args.funding_dir)
    if args.manifest_dir is not None:
        refuse_prod_path(args.manifest_dir)
    if args.volnorm_bars is not None:
        refuse_prod_path(args.volnorm_bars)
    if args.walkforward_bars is not None:
        refuse_prod_path(args.walkforward_bars)

    # Collect input paths for manifest fingerprinting
    input_dirs: list[Path] = []
    if args.bars_dir is not None:
        input_dirs.append(Path(args.bars_dir))
    if args.funding_dir is not None:
        input_dirs.append(Path(args.funding_dir))
    if args.manifest_dir is not None:
        input_dirs.append(Path(args.manifest_dir))

    # Compute fingerprint if any input directories are provided
    has_input = len(input_dirs) > 0
    input_manifest_summary: dict | None = None
    if has_input:
        discovered = discover_input_files(input_dirs)
        input_manifest_summary = build_input_manifest_summary(discovered)
        fingerprint = input_manifest_summary["fingerprint"]
    else:
        fingerprint = PLACEHOLDER_SKELETON_NO_OP

    # Fixture-only volnorm reconstruction (PR D).  Deterministic weight rebuild
    # from tiny fixture bar data only.  This computes NO strategy PnL, generates
    # NO trades, replays NO funding, and keeps the verdict SKELETON_ONLY.
    volnorm_fixture_summary: dict | None = None
    per_stage_metrics: dict[str, StageMetrics] = {}
    if args.volnorm_bars is not None:
        volnorm_fixture_summary = reconstruct_fixture_volnorm_weights(
            Path(args.volnorm_bars)
        )
        per_stage_metrics[FIXTURE_VOLNORM_STAGE_ID] = StageMetrics(
            stage_id=FIXTURE_VOLNORM_STAGE_ID,
            stage_name=FIXTURE_VOLNORM_STAGE_NAME,
            status=SKELETON_ONLY,
            summary=(
                "fixture-only volnorm reconstruction: "
                f"weight={volnorm_fixture_summary['inverse_vol_weight']:.6g}, "
                f"realized_volatility="
                f"{volnorm_fixture_summary['realized_volatility']:.6g} "
                "(no PnL, no trades, not full V2)"
            ),
        )

    # Fixture-only walk-forward replay (PR E).  Deterministic tiny fixture splits
    # over fixture bars; reconstructs a fixture volnorm weight per split, applies
    # fixture cost assumptions, and emits a toy replay summary.  This computes NO
    # strategy PnL, generates NO trades, replays NO real funding, creates NO Lane
    # B, and keeps the verdict SKELETON_ONLY.
    walkforward_fixture_summary: dict | None = None
    if args.walkforward_bars is not None:
        walkforward_fixture_summary = run_fixture_walkforward(
            Path(args.walkforward_bars)
        )
        per_stage_metrics[FIXTURE_WALKFORWARD_STAGE_ID] = StageMetrics(
            stage_id=FIXTURE_WALKFORWARD_STAGE_ID,
            stage_name=FIXTURE_WALKFORWARD_STAGE_NAME,
            status=SKELETON_ONLY,
            summary=(
                "fixture-only walk-forward replay: "
                f"split_count={walkforward_fixture_summary['split_count']}, "
                "fixture_counterfactual_return_total="
                f"{walkforward_fixture_summary['fixture_counterfactual_return_total']:.6g} "
                "(no PnL, no trades, no real funding replay, not full walk-forward)"
            ),
        )

    # Build skeleton receipt
    receipt_kwargs: dict = ValidationReceipt(
        validation_receipt=ReceiptMetadata(
            tool_name="offline_edge_validation",
            tool_version="0.1.0",
            timestamp_utc=datetime.now(timezone.utc).isoformat(),
            pipeline_description="skeleton",
        ),
        input_manifest_fingerprint=fingerprint,
        cost_model_assumptions=CostModelAssumptions(
            slippage_bps_per_side=5.0,
            commission_bps_per_side=5.0,
            heat_cap=1.0,
            vol_lookback_bars=90,
            vol_floor=1e-6,
            # PR C — fixture-only cost-model placeholders. These are assumptions
            # only: the CLI does NOT apply them to any trade or compute PnL.
            cost_model_version=COST_MODEL_VERSION,
            spread_bps_per_side=1.0,
            funding_cost_placeholder=0.0,
        ),
        per_stage_metrics=per_stage_metrics,
        final_verdict=SKELETON_ONLY,
    )
    receipt: ValidationReceipt = dict(receipt_kwargs)  # type: ignore[arg-type]
    if input_manifest_summary is not None:
        receipt["input_manifest_summary"] = input_manifest_summary
    if volnorm_fixture_summary is not None:
        receipt["volnorm_fixture_summary"] = volnorm_fixture_summary
    if walkforward_fixture_summary is not None:
        receipt["walkforward_fixture_summary"] = walkforward_fixture_summary

    # Ensure output directory exists
    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    # Write receipt
    receipt_path = output_dir / "validation_receipt.json"
    with open(receipt_path, "w") as f:
        json.dump(receipt, f, indent=2)

    # Summary to stdout
    print(f"Validation receipt written to {receipt_path}")
    print(f"Final verdict: {receipt['final_verdict']}")
    if has_input:
        print(f"Input manifest fingerprint: {fingerprint}")
    else:
        print("Input manifest: PLACEHOLDER_SKELETON_NO_OP (no input dirs)")
    if volnorm_fixture_summary is not None:
        print(
            "Volnorm fixture reconstruction: "
            f"weight={volnorm_fixture_summary['inverse_vol_weight']:.6g}, "
            f"realized_volatility="
            f"{volnorm_fixture_summary['realized_volatility']:.6g} "
            "(fixture-only, no PnL)"
        )
    if walkforward_fixture_summary is not None:
        print(
            "Walk-forward fixture replay: "
            f"split_count={walkforward_fixture_summary['split_count']}, "
            "fixture_counterfactual_return_total="
            f"{walkforward_fixture_summary['fixture_counterfactual_return_total']:.6g} "
            "(fixture-only, no PnL, no real funding replay)"
        )
    print("Mode: read-only skeleton (no-op)")


if __name__ == "__main__":
    main()