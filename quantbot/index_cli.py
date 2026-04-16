"""Index CLI for QuantBot.

qnty-index path [path ...]

Paper mode only - no live trading, no profitability claims.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from quantbot.experiment.index import IndexedExperiment, index_experiment_artifacts


def _format_row(exp: IndexedExperiment) -> str:
    """Format a single indexed experiment as a compact text row."""
    eligible_indicator = "✓" if exp.eligible_for_review else "✗"
    # Format economics summary if present
    econ = exp.economics_summary
    if econ:
        cost_sides = econ.get("cost_side_count", 0) if econ else 0
        entries = econ.get("entry_count", 0) if econ else 0
        exits = econ.get("exit_count", 0) if econ else 0
        flips = econ.get("flip_count", 0) if econ else 0
        econ_str = f"cs={cost_sides} e={entries} x={exits} f={flips}"
    else:
        econ_str = "N/A"
    # Format return summary if present
    ret = exp.return_summary
    if ret:
        gross = ret.get("gross_return_total", 0.0)
        net = ret.get("net_return_total", 0.0)
        cost = ret.get("cost_deduction_total", 0.0)
        ret_str = f"g={gross:.4f} n={net:.4f} c={cost:.4f}"
    else:
        ret_str = "N/A"
    # Format inference summary if present
    inf = exp.inference_summary
    if inf:
        mean = inf.get("mean_return", 0.0)
        std = inf.get("std_return")
        bars = inf.get("bar_count_for_returns", 0)
        interval = inf.get("interval", "unknown")
        sharpe_like = inf.get("sharpe_like")
        if sharpe_like is not None:
            inf_str = f"μ={mean:.6f} σ={std:.6f} n={bars} [{interval}] sharpe={sharpe_like:.4f}*"
        elif std is not None:
            inf_str = f"μ={mean:.6f} σ={std:.6f} n={bars} [{interval}]"
        else:
            inf_str = f"μ={mean:.6f} n={bars} [{interval}]"
    else:
        inf_str = "N/A"
    # Format inferential summary (PSR/DSR) if present
    inf_summary = exp.inferential_summary
    if inf_summary:
        psr = inf_summary.get("psr")
        dsr = inf_summary.get("dsr")
        dsr_provisional = inf_summary.get("dsr_provisional", False)
        if psr is not None and dsr is not None:
            dsr_display = f"{dsr:.4f}(prov)" if dsr_provisional else f"{dsr:.4f}"
            inf_meta_str = f"PSR={psr:.4f} DSR={dsr_display}"
        elif psr is not None:
            inf_meta_str = f"PSR={psr:.4f} DSR=N/A"
        else:
            inf_meta_str = "PSR=N/A DSR=N/A"
    else:
        inf_meta_str = "N/A"
    return (
        f"{exp.experiment_name} | {exp.strategy_name} | {exp.family_id or 'N/A'} | "
        f"{exp.variant_id or 'N/A'} | {exp.trial_count or 0} | "
        f"{exp.gate_status or 'N/A'} | {exp.split_count} | {exp.signal_count} | "
        f"{exp.fee_bps} | {exp.slippage_bps} | {econ_str} | {ret_str} | {inf_str} | "
        f"{inf_meta_str} | {exp.result_type} | {eligible_indicator} | {exp.artifact_path}"
    )


def _format_review_row(exp: IndexedExperiment) -> str:
    """Format a single eligible artifact as a compact review text row."""
    ret = exp.return_summary
    if ret:
        gross = ret.get("gross_return_total", 0.0) if ret else 0.0
        net = ret.get("net_return_total", 0.0) if ret else 0.0
        cost = ret.get("cost_deduction_total", 0.0) if ret else 0.0
        ret_str = f"g={gross:.4f} n={net:.4f} c={cost:.4f}"
    else:
        ret_str = "g=N/A n=N/A c=N/A"
    return (
        f"{exp.experiment_name} | {exp.family_id or 'N/A'} | {exp.variant_id or 'N/A'} | "
        f"{exp.result_type} | {exp.gate_status or 'N/A'} | {exp.trial_count or 0} | "
        f"{exp.fee_bps} | {exp.slippage_bps} | {exp.signal_count} | {exp.split_count} | "
        f"{ret_str} | {exp.artifact_path}"
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="qnty-index",
        description="Index experiment artifacts and produce a normalized summary.",
    )
    parser.add_argument(
        "paths",
        type=Path,
        nargs="+",
        help="Paths to experiment_result.json or walkforward_result.json files, "
             "or directories containing them.",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="Output machine-readable JSON array.",
    )
    parser.add_argument(
        "--by-family",
        action="store_true",
        help="Group artifacts by family_id and emit a compact summary.",
    )
    parser.add_argument(
        "--sort-by",
        choices=["family_id", "eligible_count", "pass_count", "fail_count", "max_trial_count", "artifact_count"],
        default="family_id",
        help="Sort family summaries by this field. Default: family_id.",
    )
    filter_group = parser.add_mutually_exclusive_group()
    filter_group.add_argument(
        "--eligible-only",
        action="store_true",
        help="Show only families with eligible_count > 0.",
    )
    filter_group.add_argument(
        "--ineligible-only",
        action="store_true",
        help="Show only families with eligible_count == 0.",
    )
    parser.add_argument(
        "--limit",
        type=int,
        metavar="N",
        default=None,
        help="Show only top N families after sort and filter.",
    )
    parser.add_argument(
        "--review-summary",
        action="store_true",
        help="Surface a compact review record for eligible artifacts only.",
    )

    try:
        args = parser.parse_args(argv)
    except SystemExit:
        return 1

    # Validate paths exist
    for p in args.paths:
        if not p.exists():
            print(f"Error: Path does not exist: {p}", file=sys.stderr)
            return 1

    # Index artifacts
    try:
        indexed = index_experiment_artifacts(args.paths)
    except (FileNotFoundError, ValueError) as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1

    # Handle empty result
    if not indexed:
        if args.json:
            print("[]")
        else:
            print("No artifacts found.")
        return 0

    # Output
    if args.by_family:
        # Group by family_id
        families: dict[str, list[IndexedExperiment]] = {}
        for exp in indexed:
            fid = exp.family_id or ""
            if fid not in families:
                families[fid] = []
            families[fid].append(exp)

        # Build summary per family
        summaries = []
        for fid, exps in families.items():
            pass_count = sum(1 for e in exps if e.gate_status == "PASS")
            fail_count = sum(1 for e in exps if e.gate_status == "FAIL")
            eligible_count = sum(1 for e in exps if e.eligible_for_review)
            max_trial = max((e.trial_count for e in exps if e.trial_count is not None), default=0)
            summaries.append({
                "family_id": fid,
                "artifact_count": len(exps),
                "max_trial_count": max_trial,
                "pass_count": pass_count,
                "fail_count": fail_count,
                "eligible_count": eligible_count,
            })

        # Sort summaries
        numeric_sort_fields = {"eligible_count", "pass_count", "fail_count", "max_trial_count", "artifact_count"}
        reverse_sort = args.sort_by in numeric_sort_fields
        summaries.sort(key=lambda s: s[args.sort_by], reverse=reverse_sort)

        # Apply filters
        if args.eligible_only:
            summaries = [s for s in summaries if s["eligible_count"] > 0]
        elif args.ineligible_only:
            summaries = [s for s in summaries if s["eligible_count"] == 0]

        # Apply limit
        if args.limit is not None:
            summaries = summaries[:args.limit]

        if args.json:
            print(json.dumps(summaries, indent=2))
        else:
            print(
                "family_id | artifact_count | max_trial_count | pass_count | fail_count | eligible_count"
            )
            for s in summaries:
                print(
                    f"{s['family_id']} | {s['artifact_count']} | "
                    f"{s['max_trial_count']} | {s['pass_count']} | {s['fail_count']} | "
                    f"eligible {s['eligible_count']}/{s['artifact_count']}"
                )
    elif args.review_summary:
        # Filter to eligible artifacts only
        eligible = [e for e in indexed if e.eligible_for_review]

        if args.json:
            records = []
            for e in eligible:
                ret = e.return_summary or {}
                inf = e.inference_summary or {}
                records.append({
                    "experiment_name": e.experiment_name,
                    "family_id": e.family_id,
                    "variant_id": e.variant_id,
                    "result_type": e.result_type,
                    "gate_status": e.gate_status,
                    "trial_count": e.trial_count,
                    "fee_bps": e.fee_bps,
                    "slippage_bps": e.slippage_bps,
                    "signal_count": e.signal_count,
                    "split_count": e.split_count,
                    "gross_return_total": ret.get("gross_return_total"),
                    "net_return_total": ret.get("net_return_total"),
                    "cost_deduction_total": ret.get("cost_deduction_total"),
                    "inference_summary": inf,
                    "inferential_summary": e.inferential_summary,
                    "artifact_path": str(e.artifact_path),
                })
            print(json.dumps({"review_summary": records, "count": len(records)}, indent=2))
        else:
            if not eligible:
                print("No eligible artifacts for review.")
            else:
                print(
                    "experiment_name | family_id | variant_id | result_type | gate_status | "
                    "trial_count | fee_bps | slippage_bps | signal_count | split_count | "
                    "gross_return | net_return | cost_deduction | artifact_path"
                )
                for exp in eligible:
                    ret = exp.return_summary
                    gross = ret.get("gross_return_total", 0.0) if ret else 0.0
                    net = ret.get("net_return_total", 0.0) if ret else 0.0
                    cost = ret.get("cost_deduction_total", 0.0) if ret else 0.0
                    print(
                        f"{exp.experiment_name} | {exp.family_id or 'N/A'} | {exp.variant_id or 'N/A'} | "
                        f"{exp.result_type} | {exp.gate_status or 'N/A'} | {exp.trial_count or 0} | "
                        f"{exp.fee_bps} | {exp.slippage_bps} | {exp.signal_count} | {exp.split_count} | "
                        f"{gross:.4f} | {net:.4f} | {cost:.4f} | {exp.artifact_path}"
                    )
    elif args.json:
        # Machine-readable JSON: list of dicts with new fields
        records = [
            {
                "experiment_name": e.experiment_name,
                "strategy_name": e.strategy_name,
                "fixture_name": e.fixture_name,
                "gate_status": e.gate_status,
                "split_count": e.split_count,
                "signal_count": e.signal_count,
                "receipt_digest": e.receipt_digest,
                "artifact_path": str(e.artifact_path),
                "result_type": e.result_type,
                "family_id": e.family_id,
                "variant_id": e.variant_id,
                "trial_count": e.trial_count,
                "fee_bps": e.fee_bps,
                "slippage_bps": e.slippage_bps,
                "economics_summary": e.economics_summary,
                "return_summary": e.return_summary,
                "inference_summary": e.inference_summary,
                "inferential_summary": e.inferential_summary,
                "eligible_for_review": e.eligible_for_review,
                "ineligibility_reasons": e.ineligibility_reasons,
            }
            for e in indexed
        ]
        print(json.dumps(records, indent=2))
    else:
        # Header
        print(
            "experiment_name | strategy_name | family_id | variant_id | trial_count | "
            "gate_status | split_count | signal_count | fee_bps | slippage_bps | economics | returns | inference | psr_dsr | result_type | eligible | artifact_path"
        )
        # Rows
        for exp in indexed:
            print(_format_row(exp))

    return 0