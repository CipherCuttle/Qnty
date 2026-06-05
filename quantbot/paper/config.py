"""Write-once paper config + deterministic config hashing.

See docs/paper_pnl_v1_schema.md section 4 (paper_config.json) and section 5.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path
from typing import Any

from quantbot.core.determinism import canonical_json_dumps
from quantbot.paper import SCHEMA_VERSION, PAPER_ENGINE_VERSION, paper_output_dir

# v1 defaults (see schema doc section 2/3)
DEFAULT_INITIAL_EQUITY_USD = 10_000.0
DEFAULT_NOTIONAL_USD = 1_000.0
DEFAULT_LEVERAGE = 1.0
DEFAULT_FEE_BPS = 5.0  # 0.05% taker per side
DEFAULT_SLIPPAGE_BPS = 5.0  # 5 bps per side
FILL_MODEL = "next_bar_open_pessimistic"
SIGNAL_SOURCE = "observation_log.json:per_bar_obs"


def config_hash(config: dict[str, Any]) -> str:
    """SHA-256 over canonical JSON of the config (excluding config_hash itself)."""
    payload = {k: v for k, v in config.items() if k != "config_hash"}
    return hashlib.sha256(canonical_json_dumps(payload).encode("utf-8")).hexdigest()


def build_config(
    forward_start_ts: str,
    initial_equity_usd: float = DEFAULT_INITIAL_EQUITY_USD,
    notional_usd: float = DEFAULT_NOTIONAL_USD,
    leverage: float = DEFAULT_LEVERAGE,
    fee_bps: float = DEFAULT_FEE_BPS,
    slippage_bps: float = DEFAULT_SLIPPAGE_BPS,
) -> dict[str, Any]:
    """Construct the canonical paper config dict (with config_hash filled in)."""
    config: dict[str, Any] = {
        "schema_version": SCHEMA_VERSION,
        "engine_version": PAPER_ENGINE_VERSION,
        "forward_start_ts": forward_start_ts,
        "initial_equity_usd": float(initial_equity_usd),
        "notional_usd": float(notional_usd),
        "leverage": float(leverage),
        "fee_model": {"type": "flat_taker", "fee_bps": float(fee_bps)},
        "slippage_model": {"type": "fixed", "slippage_bps": float(slippage_bps)},
        "fill_model": FILL_MODEL,
        "funding_model": {"type": "accrual", "applied_as": "cash_flow"},
        "signal_source": SIGNAL_SOURCE,
    }
    config["config_hash"] = config_hash(config)
    return config


def config_path(output_dir: Path | None = None) -> Path:
    return (output_dir or paper_output_dir()) / "paper_config.json"


def load_config(output_dir: Path | None = None) -> dict[str, Any]:
    path = config_path(output_dir)
    with open(path, encoding="utf-8") as fh:
        config = json.load(fh)
    expected = config_hash(config)
    if config.get("config_hash") != expected:
        raise ValueError(
            f"paper_config.json hash mismatch: stored {config.get('config_hash')} "
            f"!= recomputed {expected} (config was mutated)"
        )
    return config


def write_config_once(
    config: dict[str, Any],
    output_dir: Path | None = None,
    force: bool = False,
) -> Path:
    """Write paper_config.json exactly once. Refuse overwrite unless force=True."""
    out = output_dir or paper_output_dir()
    out.mkdir(parents=True, exist_ok=True)
    path = config_path(out)
    if path.exists() and not force:
        raise FileExistsError(
            f"Refusing to overwrite {path}. Config is write-once; set force/FORCE=1 "
            "only after operator review."
        )
    path.write_text(json.dumps(config, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return path


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Initialize write-once paper_config.json")
    parser.add_argument(
        "--forward-start-ts",
        required=True,
        help="Hard UTC bar boundary (e.g. 2026-06-05T00:00:00). No fill before this.",
    )
    parser.add_argument("--initial-equity-usd", type=float, default=DEFAULT_INITIAL_EQUITY_USD)
    parser.add_argument("--notional-usd", type=float, default=DEFAULT_NOTIONAL_USD)
    parser.add_argument("--leverage", type=float, default=DEFAULT_LEVERAGE)
    parser.add_argument("--fee-bps", type=float, default=DEFAULT_FEE_BPS)
    parser.add_argument("--slippage-bps", type=float, default=DEFAULT_SLIPPAGE_BPS)
    parser.add_argument("--output-dir", default=None)
    parser.add_argument("--force", action="store_true")
    args = parser.parse_args(argv)

    out = Path(args.output_dir) if args.output_dir else None
    config = build_config(
        forward_start_ts=args.forward_start_ts,
        initial_equity_usd=args.initial_equity_usd,
        notional_usd=args.notional_usd,
        leverage=args.leverage,
        fee_bps=args.fee_bps,
        slippage_bps=args.slippage_bps,
    )
    path = write_config_once(config, out, force=args.force)
    print(f"Wrote {path}")
    print(f"  forward_start_ts: {config['forward_start_ts']}")
    print(f"  config_hash:      {config['config_hash']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
