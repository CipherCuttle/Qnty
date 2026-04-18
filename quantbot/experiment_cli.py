"""Minimal experiment CLI for QuantBot.

qnty-experiment --fixture btcusdt-8h --strategy ThresholdStrategy \
    --param threshold=16500.0 --out /tmp/exp

Paper mode only - no real trading, no profitability claims.
"""

import argparse
import sys
from pathlib import Path

# Import strategies to register them in the experiment registry
import quantbot.strategy.threshold  # noqa: F401
import quantbot.strategy.rolling_return_breakout  # noqa: F401

from quantbot.experiment import ExperimentSpec, run_experiment
from quantbot.version import ENGINE_VERSION


# Fixture alias → (manifest_path, csv_path, interval)
_FIXTURE_MAP: dict[str, tuple[Path, Path, str]] = {
    "btcusdt-8h": (
        Path(__file__).parent.parent / "tests" / "fixtures" / "BTCUSDT_manifest.json",
        Path(__file__).parent.parent / "tests" / "fixtures" / "BTCUSDT_8h.csv",
        "8h",
    ),
}


def _parse_param(value: str) -> tuple[str, float | str]:
    """Parse a key=value param into (key, parsed_value).

    Attempts to parse as float first, then falls back to str.
    """
    if "=" not in value:
        raise ValueError(f"Invalid param format '{value}', expected key=value")
    key, raw_val = value.split("=", 1)
    key = key.strip()
    raw_val = raw_val.strip()
    try:
        return key, float(raw_val)
    except ValueError:
        return key, raw_val


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="qnty-experiment",
        description="Run a deterministic experiment and produce a receipt.",
    )
    parser.add_argument(
        "--version", action="version", version=f"%(prog)s {ENGINE_VERSION}"
    )
    parser.add_argument(
        "--fixture",
        required=True,
        help="Fixture name (e.g. btcusdt-8h)",
    )
    parser.add_argument(
        "--strategy",
        required=True,
        help="Strategy name (e.g. ThresholdStrategy)",
    )
    parser.add_argument(
        "--param",
        action="append",
        default=[],
        dest="params",
        metavar="KEY=VALUE",
        help="Strategy parameter (repeatable, e.g. --param threshold=16500.0)",
    )
    parser.add_argument(
        "--out",
        required=True,
        type=Path,
        help="Output directory for experiment artifacts",
    )
    parser.add_argument(
        "--experiment-name",
        default=None,
        help="Experiment name (default: {strategy}_{fixture})",
    )
    parser.add_argument(
        "--family-id",
        default=None,
        help="Trial family identifier (default: experiment_name)",
    )
    parser.add_argument(
        "--variant-id",
        default=None,
        help="Variant identifier within the family (default: experiment_name)",
    )
    parser.add_argument(
        "--trial-count",
        type=int,
        default=None,
        help="Cumulative trial count for this family at creation time (default: 1)",
    )
    parser.add_argument(
        "--fee-bps",
        type=float,
        default=0.0,
        help="Assumed fee in basis points (default: 0.0)",
    )
    parser.add_argument(
        "--slippage-bps",
        type=float,
        default=0.0,
        help="Assumed slippage in basis points (default: 0.0)",
    )

    try:
        args = parser.parse_args(argv)
    except SystemExit:
        return 1

    # Resolve fixture
    if args.fixture not in _FIXTURE_MAP:
        print(
            f"Error: Unknown fixture '{args.fixture}'. "
            f"Available: {list(_FIXTURE_MAP.keys())}",
            file=sys.stderr,
        )
        return 1
    manifest_path, csv_path, fixture_interval = _FIXTURE_MAP[args.fixture]

    # Validate fixture files exist
    if not manifest_path.exists():
        print(f"Error: Manifest not found: {manifest_path}", file=sys.stderr)
        return 1
    if not csv_path.exists():
        print(f"Error: CSV not found: {csv_path}", file=sys.stderr)
        return 1

    # Parse strategy params
    strategy_params: dict[str, float | str] = {}
    for p in args.params:
        try:
            k, v = _parse_param(p)
        except ValueError as exc:
            print(f"Error: {exc}", file=sys.stderr)
            return 1
        strategy_params[k] = v

    # Build experiment name
    experiment_name = args.experiment_name or f"{args.strategy}_{args.fixture}"

    # Trial-family metadata: defaults to experiment_name for ids, 1 for trial_count
    family_id = args.family_id if args.family_id is not None else experiment_name
    variant_id = args.variant_id if args.variant_id is not None else experiment_name
    trial_count = args.trial_count if args.trial_count is not None else 1

    # Build spec
    spec = ExperimentSpec(
        experiment_name=experiment_name,
        strategy_name=args.strategy,
        strategy_params=strategy_params,
        fixture_name=args.fixture,
        description="",
        notes="Paper mode - no profitability claims.",
        family_id=family_id,
        variant_id=variant_id,
        trial_count=trial_count,
        fee_bps=args.fee_bps,
        slippage_bps=args.slippage_bps,
    )

    # Run experiment
    try:
        result = run_experiment(
            spec=spec,
            manifest_path=manifest_path,
            csv_path=csv_path,
            output_dir=args.out,
            interval=fixture_interval,
        )
    except ValueError as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1
    except AssertionError as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1

    # Print result summary
    print(f"experiment: {result.spec.experiment_name}")
    print(f"receipt: {result.receipt_path}")
    print(f"result: {result.result_path}")
    print(f"bars: {result.bar_count}  signals: {result.signal_count}")
    print(f"long: {result.long_count}  short: {result.short_count}  flat: {result.flat_count}")
    print(f"digest: {result.receipt_digest}")
    print(f"family: {result.spec.family_id}  variant: {result.spec.variant_id}  trials: {result.spec.trial_count}")
    # Print gate verdict
    verdict = result.gate_verdict
    if verdict.status == "PASS":
        print("gate: PASS")
    else:
        reasons_str = ", ".join(verdict.reasons) if verdict.reasons else "unknown"
        print(f"gate: FAIL reasons=[{reasons_str}]")

    return 0


if __name__ == "__main__":
    sys.exit(main())
