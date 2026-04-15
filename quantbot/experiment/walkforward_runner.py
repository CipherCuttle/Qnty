"""Walk-forward experiment runner for QuantBot.

Minimal honest implementation - no optimization, no alpha claims.
"""

import json
from pathlib import Path

from quantbot.data.loaders import load_bars_from_csv
from quantbot.data.types import Bar
from quantbot.experiment.gates import gate_walkforward_result
from quantbot.experiment.result import (
    ExperimentResult,
    WalkForwardExperimentResult,
    WalkForwardSplitResult,
)
from quantbot.experiment.spec import ExperimentSpec
from quantbot.experiment.walkforward import WalkForwardSplit, build_walkforward_splits
from quantbot.experiment.runner import run_experiment
from quantbot.version import ENGINE_VERSION


def _write_split_csv(bars: list[Bar], output_path: Path) -> None:
    """Write a subset of bars to a CSV file.

    Args:
        bars: List of Bar objects to write.
        output_path: Path to write CSV file.
    """
    lines = ["timestamp,open,high,low,close,volume"]
    for bar in bars:
        lines.append(
            f"{bar.timestamp},{bar.open},{bar.high},{bar.low},{bar.close},{bar.volume}"
        )
    output_path.write_text("\n".join(lines), encoding="utf-8")


def run_walkforward_experiment(
    spec: ExperimentSpec,
    manifest_path: Path,
    csv_path: Path,
    output_dir: Path,
    train_size: int,
    test_size: int,
    step_size: int | None = None,
) -> WalkForwardExperimentResult:
    """
    Run experiment across walk-forward splits.

    1. Load bars from csv_path
    2. Build walk-forward splits via build_walkforward_splits()
    3. For each split:
       - Write test window bars to per-split CSV
       - Run experiment via run_experiment() on test window only
       - Collect per-split summary
    4. Return WalkForwardExperimentResult

    Args:
        spec: Base ExperimentSpec to use for each split.
        manifest_path: Path to manifest JSON file.
        csv_path: Path to bars CSV file.
        output_dir: Directory for output files.
        train_size: Number of bars in each training window.
        test_size: Number of bars in each test window.
        step_size: Step to advance between splits. Defaults to test_size.

    Returns:
        WalkForwardExperimentResult with per-split summaries.
    """
    # Step 1: load all bars
    bars = load_bars_from_csv(csv_path)

    # Step 2: build walk-forward splits
    splits = build_walkforward_splits(bars, train_size, test_size, step_size)

    if not splits:
        # No splits possible - return empty result
        return WalkForwardExperimentResult(
            experiment_name=spec.experiment_name,
            split_count=0,
            splits=[],
            total_bar_count=0,
            total_signal_count=0,
        )

    # Step 3: run experiment for each split
    split_results: list[WalkForwardSplitResult] = []
    total_bar_count = 0
    total_signal_count = 0

    # Create parent output directory
    output_dir.mkdir(parents=True, exist_ok=True)

    for idx, wf_split in enumerate(splits):
        # Create output directory for this split
        split_dir = output_dir / f"split_{idx:03d}"
        split_dir.mkdir(parents=True, exist_ok=True)

        # Slice bars to test window only
        test_bars = bars[wf_split.test_start:wf_split.test_end]
        test_bar_count = len(test_bars)

        # Write test bars to per-split CSV
        split_csv_path = split_dir / "split_bars.csv"
        _write_split_csv(test_bars, split_csv_path)

        # Write a minimal manifest for this split
        split_manifest = {
            "version": 1,
            "bars_file": "split_bars.csv",
            "symbol": spec.strategy_params.get("symbol", "UNKNOWN"),
            "interval": "unknown",
        }
        split_manifest_path = split_dir / "manifest.json"
        split_manifest_path.write_text(json.dumps(split_manifest), encoding="utf-8")

        # Build split-specific spec
        # Use variant_id as base for split-specific variant (falls back to experiment_name)
        base_variant = spec.variant_id if spec.variant_id else spec.experiment_name
        split_spec = ExperimentSpec(
            experiment_name=f"{spec.experiment_name}_split_{idx:03d}",
            strategy_name=spec.strategy_name,
            strategy_params={
                **spec.strategy_params,
                "_split_index": idx,
                "_test_start": wf_split.test_start,
                "_test_end": wf_split.test_end,
            },
            fixture_name=spec.fixture_name,
            description=f"{spec.description} [split {idx}]",
            notes=spec.notes,
            family_id=spec.family_id if spec.family_id else spec.experiment_name,
            variant_id=f"{base_variant}_split_{idx:03d}",
            trial_count=spec.trial_count,
        )

        # Run experiment for this split on the sliced bars
        try:
            result = run_experiment(
                spec=split_spec,
                manifest_path=split_manifest_path,
                csv_path=split_csv_path,
                output_dir=split_dir,
            )
            receipt_path_str = str(result.receipt_path)
            artifact_path_str = str(split_dir / "experiment_result.json")
            signal_count = result.signal_count
            long_count = result.long_count
            short_count = result.short_count
            flat_count = result.flat_count
            split_economics = result.economics_summary
            split_returns = result.return_summary
            split_return_series = result.return_series
        except Exception:
            # If experiment fails, record empty results
            receipt_path_str = None
            artifact_path_str = None
            signal_count = 0
            long_count = 0
            short_count = 0
            flat_count = 0
            first_ts = ""
            last_ts = ""
            split_economics = None
            split_returns = None
            split_return_series = None
        else:
            first_ts = result.first_timestamp
            last_ts = result.last_timestamp

        # Collect per-split summary
        split_result = WalkForwardSplitResult(
            split_index=idx,
            train_bar_count=wf_split.train_end - wf_split.train_start,
            test_bar_count=test_bar_count,
            signal_count=signal_count,
            long_count=long_count,
            short_count=short_count,
            flat_count=flat_count,
            receipt_path=receipt_path_str,
            artifact_path=artifact_path_str,
            first_timestamp=first_ts,
            last_timestamp=last_ts,
            economics_summary=split_economics,
            return_summary=split_returns,
            return_series=split_return_series,
        )
        split_results.append(split_result)
        total_bar_count += test_bar_count
        total_signal_count += signal_count

    # Step 4: build result and write JSON artifact
    # Default family_id/variant_id to experiment_name if not set (for backward compat)
    wf_family_id = spec.family_id if spec.family_id else spec.experiment_name
    wf_variant_id = spec.variant_id if spec.variant_id else spec.experiment_name
    wf_result = WalkForwardExperimentResult(
        experiment_name=spec.experiment_name,
        split_count=len(split_results),
        splits=split_results,
        total_bar_count=total_bar_count,
        total_signal_count=total_signal_count,
        strategy_name=spec.strategy_name,
        strategy_params=spec.strategy_params,
        fixture_name=spec.fixture_name,
        family_id=wf_family_id,
        variant_id=wf_variant_id,
        trial_count=spec.trial_count,
        engine_version=ENGINE_VERSION,
        fee_bps=spec.fee_bps,
        slippage_bps=spec.slippage_bps,
    )

    # Aggregate economics from splits
    wf_result.economics_summary = wf_result.aggregate_economics_summary()

    # Aggregate returns from splits
    wf_result.return_summary = wf_result.aggregate_return_summary()

    # Run gate checks and attach verdict
    wf_result.gate_verdict = gate_walkforward_result(wf_result)

    # Write deterministic walkforward_result.json (now includes gate_verdict)
    wf_json_path = output_dir / "walkforward_result.json"
    wf_result.write_json(wf_json_path)

    return wf_result
