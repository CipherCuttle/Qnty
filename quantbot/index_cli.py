"""Index CLI for QuantBot.

qnty-index path [path ...]

Paper mode only - no live trading, no profitability claims.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from quantbot.experiment.calibration import CalibrationComparison, classify_calibration_status
from quantbot.experiment.index import IndexedExperiment, index_experiment_artifacts
from quantbot.experiment.pbo import classify_pbo_status, pbo_status_label
from quantbot.experiment.result import generate_replication_summary, ReplicationSummary


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
    # Format calibration if present
    cal = exp.calibration
    if cal is not None:
        status = classify_calibration_status(cal.delta_bps, cal.record_count)
        cal_str = f"calibration: assumed={cal.assumed_total_cost_bps:.1f} observed={cal.observed_avg_shortfall_bps:.1f} delta=+{cal.delta_bps:.1f} n={cal.record_count} [{status}]"
    else:
        cal_str = ""
    # Format PBO overfitting summary if present
    pbo_str = ""
    of_summary = exp.overfitting_summary
    if of_summary is not None:
        pbo_val = of_summary.get("pbo")
        path_cnt = of_summary.get("path_count")
        pbo_stat = classify_pbo_status(pbo_val, path_cnt)
        pbo_str = f"pbo: method={of_summary.get('method', 'N/A')} paths={path_cnt if path_cnt is not None else '?'} pbo={pbo_val if pbo_val is not None else '?'} [{pbo_stat}]"
    # Format promotion classification if present
    promo_str = ""
    if exp.promotion_classification is not None:
        pc = exp.promotion_classification
        promo_str = f"promotion: [{pc.get('classification', 'N/A')}] hard_gate={pc.get('hard_gate_status', 'N/A')}"
    row = (
        f"{exp.experiment_name} | {exp.family_id or 'N/A'} | {exp.variant_id or 'N/A'} | "
        f"{exp.result_type} | {exp.gate_status or 'N/A'} | {exp.trial_count or 0} | "
        f"{exp.fee_bps} | {exp.slippage_bps} | {exp.signal_count} | {exp.split_count} | "
        f"{ret_str}"
    )
    if cal_str:
        row += f" | {cal_str}"
    if pbo_str:
        row += f" | {pbo_str}"
    if promo_str:
        row += f" | {promo_str}"
    row += f" | {exp.artifact_path}"
    return row


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
    parser.add_argument(
        "--calibration-dir",
        type=Path,
        default=None,
        help="Path to Franken reconciliation files directory.",
    )
    parser.add_argument(
        "--overfitting",
        action="store_true",
        help="Include path dispersion diagnostic summaries in JSON output.",
    )
    parser.add_argument(
        "--replication",
        nargs=2,
        metavar=("SOURCE_FIXTURE", "COMPARISON_FIXTURE"),
        help="Generate replication summary comparing two fixtures. "
             "Outputs JSON with replication comparison metrics and interpretation.",
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
        indexed = index_experiment_artifacts(args.paths, calibration_dir=args.calibration_dir)
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
            # Aggregate calibration stats
            with_calibration = [e for e in exps if e.calibration is not None]
            if with_calibration:
                avg_delta_bps = sum(e.calibration.delta_bps for e in with_calibration) / len(with_calibration)
                # Count status categories
                aligned_count = sum(1 for e in with_calibration if classify_calibration_status(e.calibration.delta_bps, e.calibration.record_count) == "aligned")
                mild_mismatch_count = sum(1 for e in with_calibration if classify_calibration_status(e.calibration.delta_bps, e.calibration.record_count) == "mild_mismatch")
                material_mismatch_count = sum(1 for e in with_calibration if classify_calibration_status(e.calibration.delta_bps, e.calibration.record_count) == "material_mismatch")
                insufficient_data_count = sum(1 for e in with_calibration if classify_calibration_status(e.calibration.delta_bps, e.calibration.record_count) == "insufficient_data")
                # Determine dominant status
                status_counts = {
                    "aligned": aligned_count,
                    "mild_mismatch": mild_mismatch_count,
                    "material_mismatch": material_mismatch_count,
                    "insufficient_data": insufficient_data_count,
                }
                dominant_status = max(status_counts, key=status_counts.get) if any(v > 0 for v in status_counts.values()) else None
            else:
                avg_delta_bps = None
                aligned_count = mild_mismatch_count = material_mismatch_count = insufficient_data_count = 0
                dominant_status = None
            summary = {
                "family_id": fid,
                "artifact_count": len(exps),
                "max_trial_count": max_trial,
                "pass_count": pass_count,
                "fail_count": fail_count,
                "eligible_count": eligible_count,
                "calibration_count": len(with_calibration),
            }
            if avg_delta_bps is not None:
                summary["avg_delta_bps"] = round(avg_delta_bps, 4)
            if with_calibration:
                summary["aligned_count"] = aligned_count
                summary["mild_mismatch_count"] = mild_mismatch_count
                summary["material_mismatch_count"] = material_mismatch_count
                summary["insufficient_data_count"] = insufficient_data_count
                summary["calibration_status"] = dominant_status
            # Aggregate PBO stats
            with_pbo = [e for e in exps if e.overfitting_summary is not None]
            if with_pbo:
                pbo_values = [e.overfitting_summary.get("pbo") for e in with_pbo if e.overfitting_summary.get("pbo") is not None]
                if pbo_values:
                    avg_pbo = sum(pbo_values) / len(pbo_values)
                    summary["avg_pbo"] = round(avg_pbo, 4)
                summary["pbo_count"] = len(with_pbo)
                # Count status categories
                pbo_statuses = [classify_pbo_status(e.overfitting_summary.get("pbo"), e.overfitting_summary.get("path_count")) for e in with_pbo]
                for status_val in ["insufficient_data", "low_overfit_risk", "elevated_overfit_risk", "high_overfit_risk"]:
                    cnt = pbo_statuses.count(status_val)
                    if cnt > 0:
                        summary[f"pbo_{status_val}_count"] = cnt
                # Worst status (highest risk)
                risk_order = ["high_overfit_risk", "elevated_overfit_risk", "low_overfit_risk", "insufficient_data"]
                for worst in risk_order:
                    if worst in pbo_statuses:
                        summary["worst_pbo_status"] = worst
                        break
            summaries.append(summary)

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
                record = {
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
                    "robustness_summary": e.robustness_summary,
                    "artifact_path": str(e.artifact_path),
                }
                if e.calibration is not None:
                    status = classify_calibration_status(e.calibration.delta_bps, e.calibration.record_count)
                    record["calibration"] = {
                        "assumed_total_cost_bps": e.calibration.assumed_total_cost_bps,
                        "observed_avg_shortfall_bps": e.calibration.observed_avg_shortfall_bps,
                        "delta_bps": e.calibration.delta_bps,
                        "record_count": e.calibration.record_count,
                        "calibration_status": status,
                    }
                if e.overfitting_summary is not None:
                    pbo_val = e.overfitting_summary.get("pbo")
                    path_cnt = e.overfitting_summary.get("path_count")
                    record["pbo"] = {
                        "method": e.overfitting_summary.get("method"),
                        "path_count": path_cnt,
                        "pbo": pbo_val,
                        "pbo_status": classify_pbo_status(pbo_val, path_cnt),
                    }
                records.append(record)
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
                    cal = exp.calibration
                    if cal is not None:
                        status = classify_calibration_status(cal.delta_bps, cal.record_count)
                        cal_line = f"calibration: assumed={cal.assumed_total_cost_bps:.1f} observed={cal.observed_avg_shortfall_bps:.1f} delta=+{cal.delta_bps:.1f} n={cal.record_count} [{status}]"
                    else:
                        cal_line = ""
                    of_summary = exp.overfitting_summary
                    if of_summary is not None:
                        pbo_val = of_summary.get("pbo")
                        path_cnt = of_summary.get("path_count")
                        pbo_stat = classify_pbo_status(pbo_val, path_cnt)
                        pbo_line = f"pbo: method={of_summary.get('method', 'N/A')} paths={path_cnt if path_cnt is not None else '?'} pbo={pbo_val if pbo_val is not None else '?'} [{pbo_stat}]"
                    else:
                        pbo_line = ""
                    print(
                        f"{exp.experiment_name} | {exp.family_id or 'N/A'} | {exp.variant_id or 'N/A'} | "
                        f"{exp.result_type} | {exp.gate_status or 'N/A'} | {exp.trial_count or 0} | "
                        f"{exp.fee_bps} | {exp.slippage_bps} | {exp.signal_count} | {exp.split_count} | "
                        f"{gross:.4f} | {net:.4f} | {cost:.4f}"
                    )
                    line_parts = []
                    if cal_line:
                        line_parts.append(cal_line)
                    if pbo_line:
                        line_parts.append(pbo_line)
                    line_parts.append(str(exp.artifact_path))
                    print(f"  {' | '.join(line_parts)}")
    elif args.replication:
        # Generate replication summary for two fixtures
        source_fixture, comparison_fixture = args.replication

        # Find artifacts matching the source and comparison fixtures
        source_exp = None
        comparison_exp = None
        for exp in indexed:
            if exp.fixture_name == source_fixture:
                if source_exp is None:
                    source_exp = exp
            if exp.fixture_name == comparison_fixture:
                if comparison_exp is None:
                    comparison_exp = exp

        if source_exp is None:
            print(f"Error: No artifact found for source fixture: {source_fixture}", file=sys.stderr)
            return 1

        # Load the raw artifact data
        import json as _json
        try:
            with open(source_exp.artifact_path, "r", encoding="utf-8") as f:
                source_data = _json.load(f)
        except Exception as exc:
            print(f"Error: Failed to load source artifact: {exc}", file=sys.stderr)
            return 1

        comparison_data = None
        if comparison_exp is not None:
            try:
                with open(comparison_exp.artifact_path, "r", encoding="utf-8") as f:
                    comparison_data = _json.load(f)
            except Exception as exc:
                print(f"Warning: Failed to load comparison artifact: {exc}", file=sys.stderr)
                comparison_data = None

        summary = generate_replication_summary(
            source_artifact_data=source_data,
            source_fixture=source_fixture,
            comparison_artifact_data=comparison_data,
            comparison_fixture=comparison_fixture if comparison_data is not None else None,
        )
        print(_json.dumps(summary.to_dict(), indent=2))
        return 0
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
                "promotion_classification": e.promotion_classification,
                **({"overfitting_summary": e.overfitting_summary} if args.overfitting else {}),
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