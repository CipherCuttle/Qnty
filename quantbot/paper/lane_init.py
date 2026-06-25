"""Temp-safe new-lane initialization (LANE_CONFIG_WRAPPER_PHASE3_PLAN, minimal slice).

A small, fail-closed helper that materializes a NEW accounting lane on disk:

  * writes the unchanged v1 ``paper_config.json`` (byte-compatible with the baseline,
    via :func:`write_config_once`) plus two additive sidecar files —
    ``lane_identity.json`` and ``lane_config_v2.json`` — that hold lane identity and the
    ``config_hash_v2`` commitment without ever mutating the write-once v1 config;
  * initializes the lane SQLite DB through the existing
    :func:`initialize_lane_database` (which refuses the baseline DB path);
  * verifies the resulting DB read-only before reporting success.

It deliberately does NOT run the writer, does NOT start any cycle, and does NOT touch
systemd/timers/network. ``pre_registration_hash`` is written as ``null`` only
(generation is a later, separate slice). This is SIMULATION-support tooling: it makes
NO profitability or edge claim; the strategy edge remains EDGE_UNPROVEN.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from quantbot.core.determinism import canonical_json_dumps
from quantbot.paper import paper_output_dir
from quantbot.paper.config import build_config, config_hash, config_path, write_config_once
from quantbot.paper.db import (
    DEFAULT_DB_PATH,
    connect_readonly,
    initialize_lane_database,
    validate_database_identity,
)
from quantbot.paper.lane_config_hash import config_hash_v2
from quantbot.paper.lane_identity import LaneIdentity
from quantbot.paper.sqlite_verify import STATUS_OK, STATUS_PRE_START, verify_database

LANE_IDENTITY_FILENAME = "lane_identity.json"
LANE_CONFIG_V2_FILENAME = "lane_config_v2.json"

# A freshly initialized lane DB has no committed batches yet, so the read-only verifier
# returns PRE_START (or OK). Anything else means the DB is not cleanly initialized.
_OK_VERIFY_STATUSES = (STATUS_OK, STATUS_PRE_START)


@dataclass(frozen=True)
class LaneInitResult:
    """Structured result of a successful lane initialization (paths + hashes)."""

    output_dir: Path
    db_path: Path
    paper_config_path: Path
    lane_identity_path: Path
    lane_config_v2_path: Path
    accounting_config_hash_v1: str
    config_hash_v2: str
    verify_status: str


def _refuse_baseline_paths(output_dir: Path, db_path: Path) -> None:
    """Fail closed if the lane would collide with the production baseline.

    The baseline output dir / DB path are read from the same env-aware helpers the rest
    of the package uses, so this honors QNTY_PAPER_OUTPUT_DIR / QNTY_PAPER_DB_PATH.
    """
    baseline_out = paper_output_dir().resolve()
    baseline_db = Path(DEFAULT_DB_PATH).resolve()
    out_res = output_dir.resolve()
    db_res = db_path.resolve()

    if out_res == baseline_out:
        raise ValueError(
            f"Refusing lane init: output_dir {output_dir} resolves to the production "
            "baseline output dir; a new lane must use a separate directory."
        )
    if db_res == baseline_db:
        raise ValueError(
            f"Refusing lane init: db_path {db_path} resolves to the production baseline "
            "DB path; a new lane must use a separate database file."
        )
    if baseline_out == db_res or baseline_out in db_res.parents:
        raise ValueError(
            f"Refusing lane init: db_path {db_path} is inside the production baseline "
            f"output dir {baseline_out}; a new lane must live outside it."
        )


def _refuse_existing_targets(
    output_dir: Path, db_path: Path, sidecars: tuple[Path, ...]
) -> None:
    """Fail closed if any target already exists (this is fresh-init only)."""
    if output_dir.exists() and any(output_dir.iterdir()):
        raise FileExistsError(
            f"Refusing lane init: output_dir {output_dir} exists and is non-empty; "
            "lane init requires an absent or empty directory."
        )
    if db_path.exists():
        raise FileExistsError(
            f"Refusing lane init: db_path {db_path} already exists — refusing to overwrite."
        )
    for p in sidecars:
        if p.exists():
            raise FileExistsError(
                f"Refusing lane init: {p} already exists — refusing to overwrite."
            )


def init_lane(
    *,
    output_dir: str | Path,
    db_path: str | Path,
    lane_id: str,
    strategy_id: str,
    strategy_version: str,
    forward_start_ts: str,
    initial_equity_usd: float | None = None,
    notional_usd: float | None = None,
    leverage: float | None = None,
    fee_bps: float | None = None,
    slippage_bps: float | None = None,
    bar_interval_hours: int | None = None,
    max_bar_staleness_hours: float | None = None,
    heartbeat_max_age_hours: float | None = None,
) -> LaneInitResult:
    """Initialize a new-lane output dir + DB, fail-closed. Never runs the writer.

    Order of operations is gate-first: baseline-collision and identity validation happen
    before anything is written, then existence gates, then the file writes + DB init, and
    finally a read-only verification of the resulting DB.
    """
    output_dir = Path(output_dir)
    db_path = Path(db_path)

    paper_config_target = config_path(output_dir)
    lane_identity_target = output_dir / LANE_IDENTITY_FILENAME
    lane_config_v2_target = output_dir / LANE_CONFIG_V2_FILENAME
    sidecars = (paper_config_target, lane_identity_target, lane_config_v2_target)

    # 1. Baseline-collision gates (before any FS mutation).
    _refuse_baseline_paths(output_dir, db_path)

    # 2. Identity validation (pure; rejects invalid + baseline-impersonating ids).
    identity = LaneIdentity(
        lane_id=lane_id,
        strategy_id=strategy_id,
        strategy_version=strategy_version,
    )

    # 3. Build the v1 accounting config (only pass overrides that were supplied so the
    #    existing build_config defaults stay authoritative).
    overrides = {
        "initial_equity_usd": initial_equity_usd,
        "notional_usd": notional_usd,
        "leverage": leverage,
        "fee_bps": fee_bps,
        "slippage_bps": slippage_bps,
        "bar_interval_hours": bar_interval_hours,
        "max_bar_staleness_hours": max_bar_staleness_hours,
        "heartbeat_max_age_hours": heartbeat_max_age_hours,
    }
    config = build_config(
        forward_start_ts=forward_start_ts,
        **{k: v for k, v in overrides.items() if v is not None},
    )
    accounting_config_hash_v1 = config_hash(config)
    cfg_hash_v2 = config_hash_v2(accounting_config_hash_v1, identity)

    # 4. Existence gates (fresh-init only).
    _refuse_existing_targets(output_dir, db_path, sidecars)

    # 5. Write the v1 config (write-once) + the two additive sidecars.
    write_config_once(config, output_dir)
    lane_identity_target.write_text(
        canonical_json_dumps(
            {
                "lane_id": identity.lane_id,
                "strategy_id": identity.strategy_id,
                "strategy_version": identity.strategy_version,
            }
        )
        + "\n",
        encoding="utf-8",
    )
    lane_config_v2_target.write_text(
        canonical_json_dumps(
            {
                "accounting_config_hash_v1": accounting_config_hash_v1,
                "config_hash_v2": cfg_hash_v2,
                "pre_registration_hash": None,
            }
        )
        + "\n",
        encoding="utf-8",
    )

    # 6. Initialize the lane DB (refuses the baseline DB path + existing file).
    initialize_lane_database(
        db_path, config, identity, baseline_db_path=DEFAULT_DB_PATH
    )

    # 7. Read-only verification: stored identity must match, v2 must recompute, and the
    #    full verifier must pass (PRE_START for a freshly initialized, batch-less DB).
    conn = connect_readonly(db_path)
    try:
        row = validate_database_identity(conn)
    finally:
        conn.close()
    if row.get("lane_id") != identity.lane_id:
        raise ValueError(
            f"Post-init lane_id mismatch: stored {row.get('lane_id')!r} != "
            f"{identity.lane_id!r}"
        )
    if row.get("config_hash") != accounting_config_hash_v1:
        raise ValueError("Post-init v1 config_hash mismatch")
    if row.get("config_hash_v2") != cfg_hash_v2:
        raise ValueError(
            f"Post-init config_hash_v2 mismatch: stored {row.get('config_hash_v2')!r} "
            f"!= recomputed {cfg_hash_v2!r}"
        )

    result = verify_database(db_path)
    if result.status not in _OK_VERIFY_STATUSES:
        raise ValueError(
            f"Post-init verification failed (status={result.status}): {result.failures}"
        )

    return LaneInitResult(
        output_dir=output_dir,
        db_path=db_path,
        paper_config_path=paper_config_target,
        lane_identity_path=lane_identity_target,
        lane_config_v2_path=lane_config_v2_target,
        accounting_config_hash_v1=accounting_config_hash_v1,
        config_hash_v2=cfg_hash_v2,
        verify_status=result.status,
    )
