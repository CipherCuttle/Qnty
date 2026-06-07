"""Write-once paper config + deterministic config hashing.

See docs/paper_pnl_v1_schema.md section 4 (paper_config.json) and section 5.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
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
    "leverage",
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

# Exact allowed values for the enumerated accounting-contract fields (Blocker 3). A config that
# claims a different fill/signal/funding/fee/slippage model must fail closed — it would silently
# change how PnL is computed if accepted.
EXPECTED_FILL_MODEL = FILL_MODEL
EXPECTED_SIGNAL_SOURCE = SIGNAL_SOURCE
EXPECTED_FEE_MODEL_TYPE = "flat_taker"
EXPECTED_SLIPPAGE_MODEL_TYPE = "fixed"
EXPECTED_FUNDING_MODEL = {"type": "accrual", "applied_as": "cash_flow"}

_REINIT_HINT = (
    "Archive/delete the stale paper output dir and re-init a fresh write-once "
    "paper_config.json (with a fresh future forward_start_ts) for this engine version."
)


class ConfigContractError(ValueError):
    """Raised when a stored paper_config.json does not meet the current load contract."""


def _is_positive_number(v: Any) -> bool:
    """True iff v is a FINITE int/float (not bool) strictly greater than 0.

    Non-finite values (inf/-inf/NaN) are rejected (Blocker 4): JSON's default decoder accepts
    `Infinity`/`NaN` tokens, and `inf > 0` is True, so without an explicit isfinite check a
    `bar_interval_hours: Infinity` would pass and later traceback (e.g. timedelta(hours=inf)).
    """
    return (
        isinstance(v, (int, float))
        and not isinstance(v, bool)
        and math.isfinite(v)
        and v > 0
    )


def _is_nonneg_number(v: Any) -> bool:
    """True iff v is a FINITE int/float (not bool) >= 0 (inf/-inf/NaN rejected — Blocker 4)."""
    return (
        isinstance(v, (int, float))
        and not isinstance(v, bool)
        and math.isfinite(v)
        and v >= 0
    )


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
    # bool is rejected explicitly: it is a subclass of int and `True == 1`, so a correctly
    # hashed `schema_version: true` would otherwise pass `isinstance(int)` AND `!= 1` (Blocker 3).
    schema_v = config.get("schema_version")
    if isinstance(schema_v, bool) or not isinstance(schema_v, int) or schema_v != SCHEMA_VERSION:
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

    # Type/range-check every freshness numeric (Blocker 4). A string/null/negative/zero value
    # here would otherwise pass the presence check and then traceback later in the freshness
    # gate (e.g. int("bad") / timedelta(hours="bad")). Fail closed in the config contract so
    # the CLI reports a clean stale-config abort (exit 3) with re-init guidance, not a crash.
    # bool is rejected explicitly (it is a subclass of int).
    for fld in REQUIRED_FRESHNESS_FIELDS:
        val = freshness.get(fld)
        if not _is_positive_number(val):
            raise ConfigContractError(
                f"paper_config.json freshness.{fld} must be a number > 0 "
                f"(got {val!r} of type {type(val).__name__}). {_REINIT_HINT}"
            )
    # Optional clock-skew tolerance, if present, must be a non-negative number (>= 0 valid).
    if "max_future_skew_hours" in freshness:
        skew = freshness.get("max_future_skew_hours")
        if not _is_nonneg_number(skew):
            raise ConfigContractError(
                f"paper_config.json freshness.max_future_skew_hours must be a number >= 0 "
                f"(got {skew!r} of type {type(skew).__name__}). {_REINIT_HINT}"
            )

    # --- accounting-value contract (Blocker 3) ----------------------------------------
    # Every value the engine multiplies/divides/compares must be deeply type/range-checked
    # here. A correctly-hashed config with `initial_equity_usd: NaN`, `notional_usd: "bad"`,
    # `leverage: false`, or `fee_bps: NaN` would otherwise pass and either write NaN PnL/state
    # or traceback deep in the engine. Fail closed as ConfigContractError (CLI exit 3) — no
    # NaN/inf/string/bool/null/off-grid value is ever accepted.
    for fld in ("initial_equity_usd", "notional_usd", "leverage"):
        val = config.get(fld)
        if not _is_positive_number(val):
            raise ConfigContractError(
                f"paper_config.json {fld} must be a finite number > 0 "
                f"(got {val!r} of type {type(val).__name__}; NaN/inf/string/bool/null "
                f"rejected). {_REINIT_HINT}"
            )

    # fee_model / slippage_model: exact `type` + a finite non-negative bps (0 is valid).
    fee_model = config.get("fee_model")
    if not isinstance(fee_model, dict) or fee_model.get("type") != EXPECTED_FEE_MODEL_TYPE:
        raise ConfigContractError(
            f"paper_config.json fee_model must be an object with type "
            f"{EXPECTED_FEE_MODEL_TYPE!r} (got {fee_model!r}). {_REINIT_HINT}"
        )
    if not _is_nonneg_number(fee_model.get("fee_bps")):
        raise ConfigContractError(
            f"paper_config.json fee_model.fee_bps must be a finite number >= 0 "
            f"(got {fee_model.get('fee_bps')!r}; NaN/inf/string/bool/null rejected). "
            f"{_REINIT_HINT}"
        )
    slippage_model = config.get("slippage_model")
    if (
        not isinstance(slippage_model, dict)
        or slippage_model.get("type") != EXPECTED_SLIPPAGE_MODEL_TYPE
    ):
        raise ConfigContractError(
            f"paper_config.json slippage_model must be an object with type "
            f"{EXPECTED_SLIPPAGE_MODEL_TYPE!r} (got {slippage_model!r}). {_REINIT_HINT}"
        )
    if not _is_nonneg_number(slippage_model.get("slippage_bps")):
        raise ConfigContractError(
            f"paper_config.json slippage_model.slippage_bps must be a finite number >= 0 "
            f"(got {slippage_model.get('slippage_bps')!r}; NaN/inf/string/bool/null "
            f"rejected). {_REINIT_HINT}"
        )

    # fill_model / signal_source: exact enumerated values.
    if config.get("fill_model") != EXPECTED_FILL_MODEL:
        raise ConfigContractError(
            f"paper_config.json fill_model {config.get('fill_model')!r} != required exact "
            f"{EXPECTED_FILL_MODEL!r}. {_REINIT_HINT}"
        )
    if config.get("signal_source") != EXPECTED_SIGNAL_SOURCE:
        raise ConfigContractError(
            f"paper_config.json signal_source {config.get('signal_source')!r} != required "
            f"exact {EXPECTED_SIGNAL_SOURCE!r}. {_REINIT_HINT}"
        )

    # funding_model: exact allowed object.
    if config.get("funding_model") != EXPECTED_FUNDING_MODEL:
        raise ConfigContractError(
            f"paper_config.json funding_model {config.get('funding_model')!r} != required "
            f"exact {EXPECTED_FUNDING_MODEL!r}. {_REINIT_HINT}"
        )

    # forward_start_ts: a parseable ISO bar timestamp ON the configured grid (Blocker 3). A
    # numeric (`123`), unparseable, or off-grid value would otherwise traceback in the freshness
    # gate or silently shift the no-fill boundary. The grid uses the config's own
    # bar_interval_hours (validated finite > 0 above).
    fwd = config.get("forward_start_ts")
    if not isinstance(fwd, str):
        raise ConfigContractError(
            f"paper_config.json forward_start_ts must be an ISO timestamp string "
            f"(got {fwd!r} of type {type(fwd).__name__}). {_REINIT_HINT}"
        )
    # Lazy import: freshness has no dependency on config, so this cannot cycle.
    from quantbot.paper import freshness as _freshness

    try:
        fwd_dt = _freshness._parse_bar(fwd)
    except (TypeError, ValueError):
        raise ConfigContractError(
            f"paper_config.json forward_start_ts {fwd!r} is not a parseable bar timestamp "
            f"(expected e.g. 2026-06-05T00:00:00). {_REINIT_HINT}"
        )
    if not _freshness._on_grid(fwd_dt, int(freshness["bar_interval_hours"])):
        raise ConfigContractError(
            f"paper_config.json forward_start_ts {fwd!r} is not on the "
            f"{freshness['bar_interval_hours']}h boundary grid (00/08/16 UTC). {_REINIT_HINT}"
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
    """Load + fully validate the write-once paper config, failing CLOSED on every fault.

    Every failure mode raises ConfigContractError (a ValueError) so the CLI can catch a single
    type and exit cleanly (exit 3) with archive/re-init guidance and NO traceback (Blocker 3/4):
    a MISSING config file, an invalid-UTF-8 file, a malformed JSON file, a contract violation
    (missing fields / wrong schema-engine-baseline / non-finite or out-of-range numbers), and a
    config_hash mismatch all fail closed. FileNotFoundError / UnicodeDecodeError / JSONDecodeError
    are each normalized to ConfigContractError so the CLI never tracebacks / exits 1.
    """
    path = config_path(output_dir)
    try:
        raw = path.read_bytes()
    except FileNotFoundError as exc:
        raise ConfigContractError(
            f"paper_config.json not found at {path}. Run "
            f"`python -m quantbot.paper.config --forward-start-ts <FUTURE_UTC_8H_BOUNDARY>` "
            f"to initialize a fresh write-once config. {_REINIT_HINT}"
        ) from exc
    try:
        text = raw.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise ConfigContractError(
            f"paper_config.json is not valid UTF-8: {exc}. {_REINIT_HINT}"
        ) from exc
    try:
        config = json.loads(text)
    except json.JSONDecodeError as exc:
        raise ConfigContractError(
            f"paper_config.json is not valid JSON: {exc}. {_REINIT_HINT}"
        ) from exc
    # Contract gate first: an old/incompatible config must fail loudly with a re-init hint
    # before we trust any of its fields.
    validate_config_contract(config)
    expected = config_hash(config)
    if config.get("config_hash") != expected:
        raise ConfigContractError(
            f"paper_config.json hash mismatch: stored {config.get('config_hash')} "
            f"!= recomputed {expected} (config was mutated). {_REINIT_HINT}"
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
