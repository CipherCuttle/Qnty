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
from quantbot.paper import (
    BASELINE_LABEL,
    PAPER_ENGINE_VERSION,
    SCHEMA_VERSION,
    paper_output_dir,
)

# v1 defaults (see schema doc section 2/3)
DEFAULT_INITIAL_EQUITY_USD = 10_000.0
DEFAULT_NOTIONAL_USD = 1_000.0
DEFAULT_LEVERAGE = 1.0
DEFAULT_FEE_BPS = 5.0  # 0.05% taker per side
DEFAULT_SLIPPAGE_BPS = 5.0  # 5 bps per side
FILL_MODEL = "next_bar_open_pessimistic"
SIGNAL_SOURCE = "observation_log.json:per_bar_obs"

# Freshness-gate defaults (see schema doc section 9 and quantbot/paper/freshness.py).
DEFAULT_BAR_INTERVAL_HOURS = 8  # 8h grid (00/08/16 UTC)
DEFAULT_MAX_BAR_STALENESS_HOURS = 24  # abort if newest observer bar is older than this
DEFAULT_HEARTBEAT_MAX_AGE_HOURS = 24  # abort if bar_decisions heartbeat is older than this


# Minimum schema/engine contract a stored config MUST satisfy to be loaded. An older
# (e.g. engine 0.1.0) config that predates the hardened provenance engine must fail loudly
# and be archived + re-init'd, NOT run under the current engine (Blocker 2 / schema § 4-5).
MIN_SCHEMA_VERSION = SCHEMA_VERSION
EXPECTED_ENGINE_VERSION = PAPER_ENGINE_VERSION
REQUIRED_CONFIG_FIELDS = (
    "schema_version",
    "engine_version",
    "baseline_label",
    "forward_start_ts",
    "initial_equity_usd",
    "notional_usd",
    "fee_model",
    "slippage_model",
    "fill_model",
    "funding_model",
    "signal_source",
    "freshness",
    "config_hash",
)
REQUIRED_FRESHNESS_FIELDS = (
    "bar_interval_hours",
    "max_bar_staleness_hours",
    "heartbeat_max_age_hours",
)

_REINIT_HINT = (
    "Archive/delete the stale paper output dir and re-init a fresh write-once "
    "paper_config.json (with a fresh future forward_start_ts) for this engine version."
)


class ConfigContractError(ValueError):
    """Raised when a stored paper_config.json does not meet the current load contract."""


def config_hash(config: dict[str, Any]) -> str:
    """SHA-256 over canonical JSON of the config (excluding config_hash itself)."""
    payload = {k: v for k, v in config.items() if k != "config_hash"}
    return hashlib.sha256(canonical_json_dumps(payload).encode("utf-8")).hexdigest()


def validate_config_contract(config: dict[str, Any]) -> None:
    """Reject any config that does not meet the current minimum schema/engine contract.

    Old `0.1.0` configs (missing `baseline_label`/`freshness`, wrong engine_version) must
    fail loudly here so they never run under the hardened provenance engine. Raises
    ConfigContractError (a ValueError) on any violation.
    """
    if not isinstance(config, dict):
        raise ConfigContractError(f"paper_config.json is not a JSON object. {_REINIT_HINT}")

    missing = [f for f in REQUIRED_CONFIG_FIELDS if f not in config]
    if missing:
        raise ConfigContractError(
            f"paper_config.json is missing required field(s) {missing} — it predates the "
            f"current paper engine contract (schema {MIN_SCHEMA_VERSION}, engine "
            f"{EXPECTED_ENGINE_VERSION}). {_REINIT_HINT}"
        )

    # Exact schema match: an unknown/future schema_version (e.g. 2) fails closed unless a
    # migration is intentionally implemented for it. paper_pnl_v1 is pinned to one schema
    # (Blocker 4) — a >= comparison would silently accept a future, unvalidated layout.
    schema_v = config.get("schema_version")
    if not isinstance(schema_v, int) or schema_v != SCHEMA_VERSION:
        raise ConfigContractError(
            f"paper_config.json schema_version {schema_v!r} != required exact "
            f"{SCHEMA_VERSION}. An unknown/future schema fails closed (no migration is "
            f"implemented for paper_pnl_v1). {_REINIT_HINT}"
        )

    engine_v = config.get("engine_version")
    if engine_v != EXPECTED_ENGINE_VERSION:
        raise ConfigContractError(
            f"paper_config.json engine_version {engine_v!r} != expected "
            f"{EXPECTED_ENGINE_VERSION}. A config built for a different engine version must "
            f"not run under this engine (contradictory provenance / stale forward_start_ts). "
            f"{_REINIT_HINT}"
        )

    # Exact baseline match: the label is part of the contract, not free text. A wrong label
    # (e.g. "not_the_fixed_baseline") must fail closed so a config that claims a different
    # baseline can never be run under this fixed-notional engine (Blocker 4).
    baseline = config.get("baseline_label")
    if baseline != BASELINE_LABEL:
        raise ConfigContractError(
            f"paper_config.json baseline_label {baseline!r} != required exact "
            f"{BASELINE_LABEL!r}. {_REINIT_HINT}"
        )

    freshness = config.get("freshness")
    if not isinstance(freshness, dict):
        raise ConfigContractError(
            f"paper_config.json freshness must be an object with "
            f"{list(REQUIRED_FRESHNESS_FIELDS)}. {_REINIT_HINT}"
        )
    fresh_missing = [f for f in REQUIRED_FRESHNESS_FIELDS if f not in freshness]
    if fresh_missing:
        raise ConfigContractError(
            f"paper_config.json freshness is missing {fresh_missing}. {_REINIT_HINT}"
        )


def build_config(
    forward_start_ts: str,
    initial_equity_usd: float = DEFAULT_INITIAL_EQUITY_USD,
    notional_usd: float = DEFAULT_NOTIONAL_USD,
    leverage: float = DEFAULT_LEVERAGE,
    fee_bps: float = DEFAULT_FEE_BPS,
    slippage_bps: float = DEFAULT_SLIPPAGE_BPS,
    bar_interval_hours: int = DEFAULT_BAR_INTERVAL_HOURS,
    max_bar_staleness_hours: float = DEFAULT_MAX_BAR_STALENESS_HOURS,
    heartbeat_max_age_hours: float = DEFAULT_HEARTBEAT_MAX_AGE_HOURS,
) -> dict[str, Any]:
    """Construct the canonical paper config dict (with config_hash filled in)."""
    config: dict[str, Any] = {
        "schema_version": SCHEMA_VERSION,
        "engine_version": PAPER_ENGINE_VERSION,
        # This is a fixed-notional active-symbol baseline, NOT V2 volnorm PnL (section 8).
        "baseline_label": BASELINE_LABEL,
        "forward_start_ts": forward_start_ts,
        "initial_equity_usd": float(initial_equity_usd),
        "notional_usd": float(notional_usd),
        "leverage": float(leverage),
        "fee_model": {"type": "flat_taker", "fee_bps": float(fee_bps)},
        "slippage_model": {"type": "fixed", "slippage_bps": float(slippage_bps)},
        "fill_model": FILL_MODEL,
        "funding_model": {"type": "accrual", "applied_as": "cash_flow"},
        "signal_source": SIGNAL_SOURCE,
        # Hard pre-run freshness gate (section 9). Stale/missing/malformed observer output
        # aborts the run before any ledger row is written.
        "freshness": {
            "bar_interval_hours": int(bar_interval_hours),
            "max_bar_staleness_hours": float(max_bar_staleness_hours),
            "heartbeat_max_age_hours": float(heartbeat_max_age_hours),
        },
    }
    config["config_hash"] = config_hash(config)
    return config


def config_path(output_dir: Path | None = None) -> Path:
    return (output_dir or paper_output_dir()) / "paper_config.json"


def load_config(output_dir: Path | None = None) -> dict[str, Any]:
    path = config_path(output_dir)
    with open(path, encoding="utf-8") as fh:
        config = json.load(fh)
    # Contract gate first: an old/incompatible config must fail loudly with a re-init hint
    # before we trust any of its fields.
    validate_config_contract(config)
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
    parser.add_argument("--bar-interval-hours", type=int, default=DEFAULT_BAR_INTERVAL_HOURS)
    parser.add_argument(
        "--max-bar-staleness-hours", type=float, default=DEFAULT_MAX_BAR_STALENESS_HOURS
    )
    parser.add_argument(
        "--heartbeat-max-age-hours", type=float, default=DEFAULT_HEARTBEAT_MAX_AGE_HOURS
    )
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
        bar_interval_hours=args.bar_interval_hours,
        max_bar_staleness_hours=args.max_bar_staleness_hours,
        heartbeat_max_age_hours=args.heartbeat_max_age_hours,
    )
    path = write_config_once(config, out, force=args.force)
    print(f"Wrote {path}")
    print(f"  forward_start_ts: {config['forward_start_ts']}")
    print(f"  config_hash:      {config['config_hash']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
