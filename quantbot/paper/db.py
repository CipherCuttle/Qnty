"""SQLite/WAL ledger substrate for paper PnL v1 (Phase 1).

Implements the DB schema, connection helpers, and initialization logic
for the paper ledger. This is the Phase 1 substrate only — the writer
and verifier are implemented in later phases.

Schema version: DB_SCHEMA_VERSION = 1
Engine version: PAPER_ENGINE_VERSION = "0.3.0"
Requires SQLite >= 3.37.0 for STRICT table support.

See docs/ADR/0001-paper-sqlite-ledger.md for the full design.
"""

from __future__ import annotations

import hashlib
import json
import os
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from quantbot.core.determinism import canonical_json_dumps
from quantbot.paper import (
    BASELINE_LABEL,
    PAPER_ENGINE_VERSION as PAPER_MODULE_VERSION,
)
from quantbot.paper.config import config_hash

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

DB_SCHEMA_VERSION = 1
PAPER_ENGINE_VERSION = "0.3.0"

# Minimum SQLite version required for STRICT table support.
_MIN_SQLITE_VERSION = (3, 37, 0)

DEFAULT_DB_PATH = Path(
    os.environ.get(
        "QNTY_PAPER_DB_PATH",
        "/srv/qnty/output/paper_pnl_v1/paper_ledger.db",
    )
)


# ---------------------------------------------------------------------------
# Path helper
# ---------------------------------------------------------------------------

def get_paper_db_path(db_path: str | Path | None = None) -> Path:
    """Return the canonical paper DB path.

    Priority:
    1. explicit *db_path* argument
    2. ``QNTY_PAPER_DB_PATH`` environment variable
    3. ``/srv/qnty/output/paper_pnl_v1/paper_ledger.db``
    """
    if db_path is not None:
        return Path(db_path)
    return DEFAULT_DB_PATH


# ---------------------------------------------------------------------------
# SQLite version gate
# ---------------------------------------------------------------------------

def _sqlite_version_info() -> tuple[int, ...]:
    """Return the runtime SQLite version as a tuple, e.g. (3, 45, 1)."""
    version_str = sqlite3.sqlite_version
    parts = []
    for p in version_str.split("."):
        try:
            parts.append(int(p))
        except ValueError:
            break
    return tuple(parts)


def assert_sqlite_capabilities(conn: sqlite3.Connection) -> None:
    """Raise ``RuntimeError`` if SQLite < 3.37.0 (no STRICT support).

    Must be called **after** opening a connection so the caller can close it
    on failure.
    """
    if _sqlite_version_info() < _MIN_SQLITE_VERSION:
        raise RuntimeError(
            f"SQLite {sqlite3.sqlite_version} detected; "
            f"paper ledger requires >= {'.'.join(map(str, _MIN_SQLITE_VERSION))} "
            f"for STRICT table support."
        )


# ---------------------------------------------------------------------------
# Connection helpers
# ---------------------------------------------------------------------------

def connect_writer(db_path: str | Path, timeout: float = 30.0) -> sqlite3.Connection:
    """Open a read-write writer connection with the required PRAGMAs.

    Sets:
    - ``journal_mode=WAL``
    - ``synchronous=FULL``
    - ``foreign_keys=ON``

    The caller is responsible for closing the connection.
    """
    db_path = Path(db_path)
    db_path.parent.mkdir(parents=True, exist_ok=True)

    conn = sqlite3.connect(str(db_path), timeout=timeout)
    conn.execute("PRAGMA journal_mode=WAL").fetchone()
    conn.execute("PRAGMA synchronous=FULL")
    conn.execute("PRAGMA foreign_keys=ON")
    conn.row_factory = sqlite3.Row
    return conn


def connect_readonly(db_path: str | Path, timeout: float = 30.0) -> sqlite3.Connection:
    """Open a read-only connection using URI ``mode=ro`` + ``query_only=ON``.

    Any write attempt raises ``sqlite3.OperationalError``.
    The caller is responsible for closing the connection.
    """
    db_path = Path(db_path)
    uri = f"file:{db_path}?mode=ro"
    conn = sqlite3.connect(uri, timeout=timeout, uri=True)
    conn.execute("PRAGMA query_only=ON")
    conn.row_factory = sqlite3.Row
    return conn


# ---------------------------------------------------------------------------
# Schema DDL
# ---------------------------------------------------------------------------

_SCHEMA_SQL: str = """
-- 4.1 paper_config — singleton, immutable
CREATE TABLE IF NOT EXISTS paper_config (
    id                          INTEGER PRIMARY KEY CHECK (id = 1),
    db_schema_version          INTEGER NOT NULL,
    paper_contract_version     INTEGER NOT NULL,
    paper_engine_version       TEXT NOT NULL,
    baseline_label             TEXT NOT NULL,
    forward_start_ts            TEXT NOT NULL,
    initial_equity_usd         REAL NOT NULL,
    notional_usd               REAL NOT NULL,
    leverage                   REAL NOT NULL,
    fee_type                   TEXT NOT NULL,
    fee_bps                    REAL NOT NULL,
    slippage_type              TEXT NOT NULL,
    slippage_bps               REAL NOT NULL,
    funding_type               TEXT NOT NULL,
    funding_applied_as         TEXT NOT NULL,
    fill_model                 TEXT NOT NULL,
    signal_source              TEXT NOT NULL,
    freshness_bar_interval_hours      INTEGER NOT NULL,
    freshness_max_bar_staleness_hours REAL NOT NULL,
    freshness_heartbeat_max_age_hours REAL NOT NULL,
    created_at                 TEXT NOT NULL,
    config_hash                TEXT NOT NULL
) STRICT;

-- 4.2 ledger_batches — append-only
CREATE TABLE IF NOT EXISTS ledger_batches (
    batch_id                   INTEGER PRIMARY KEY AUTOINCREMENT,
    created_at                 TEXT NOT NULL,
    started_at                 TEXT,
    committed_at               TEXT,
    git_sha                    TEXT,
    prior_watermark_bar_ts    TEXT,
    new_watermark_bar_ts      TEXT,
    first_event_seq           INTEGER,
    last_event_seq            INTEGER,
    event_count                INTEGER NOT NULL DEFAULT 0,
    committed_bar_count        INTEGER NOT NULL DEFAULT 0,
    paper_engine_version       TEXT NOT NULL,
    config_hash                TEXT NOT NULL
) STRICT;

-- 4.3 ledger_events — global ordered index (append-only)
CREATE TABLE IF NOT EXISTS ledger_events (
    seq                       INTEGER PRIMARY KEY AUTOINCREMENT,
    batch_id                  INTEGER REFERENCES ledger_batches(batch_id),
    event_type                TEXT NOT NULL CHECK (
        event_type IN (
            'signal_snapshot',
            'funding',
            'fill',
            'trade',
            'position_snapshot',
            'equity_snapshot'
        )
    ),
    event_key                 TEXT NOT NULL,
    recorded_at               TEXT NOT NULL,
    bar_ts                    TEXT,
    symbol                    TEXT,
    prev_seq                  INTEGER,
    UNIQUE(event_type, event_key)
) STRICT;

CREATE INDEX IF NOT EXISTS idx_ledger_events_event_type ON ledger_events(event_type);
CREATE INDEX IF NOT EXISTS idx_ledger_events_bar_ts ON ledger_events(bar_ts);
CREATE INDEX IF NOT EXISTS idx_ledger_events_symbol ON ledger_events(symbol);
CREATE INDEX IF NOT EXISTS idx_ledger_events_batch_id ON ledger_events(batch_id);

-- 4.4a signal_snapshots
CREATE TABLE IF NOT EXISTS signal_snapshots (
    seq                       INTEGER PRIMARY KEY REFERENCES ledger_events(seq),
    batch_id                  INTEGER NOT NULL REFERENCES ledger_batches(batch_id),
    snapshot_id               TEXT NOT NULL,
    bar_ts                    TEXT NOT NULL,
    bar_commit_id             TEXT NOT NULL,
    bar_index                 INTEGER,
    active_symbols            TEXT NOT NULL,  -- JSON array
    portfolio_heat            REAL,
    heat_cap_triggered        INTEGER NOT NULL,  -- bool stored as 0/1
    weighted_return           REAL,
    source_observation_digest TEXT NOT NULL,
    source_observation_mtime  TEXT,
    run_ts                    TEXT NOT NULL
) STRICT;

-- 4.4b fills
CREATE TABLE IF NOT EXISTS fills (
    seq                       INTEGER PRIMARY KEY REFERENCES ledger_events(seq),
    batch_id                  INTEGER NOT NULL REFERENCES ledger_batches(batch_id),
    fill_id                   TEXT NOT NULL,
    bar_commit_id             TEXT NOT NULL,
    signal_bar_ts             TEXT NOT NULL,
    fill_ts                   TEXT NOT NULL,
    symbol                    TEXT NOT NULL,
    side                      TEXT NOT NULL CHECK (side IN ('BUY', 'SELL')),
    kind                      TEXT NOT NULL CHECK (kind IN ('entry', 'exit')),
    qty                       REAL NOT NULL,
    open_price                REAL NOT NULL,
    fill_price                REAL NOT NULL,
    slippage_bps              REAL NOT NULL,
    fee                       REAL NOT NULL,
    backfill                  INTEGER NOT NULL DEFAULT 0
) STRICT;

-- 4.4c trades
CREATE TABLE IF NOT EXISTS trades (
    seq                       INTEGER PRIMARY KEY REFERENCES ledger_events(seq),
    batch_id                  INTEGER NOT NULL REFERENCES ledger_batches(batch_id),
    trade_id                  TEXT NOT NULL,
    bar_commit_id             TEXT NOT NULL,
    symbol                    TEXT NOT NULL,
    entry_fill_id             TEXT NOT NULL,
    exit_fill_id              TEXT NOT NULL,
    entry_bar_ts              TEXT NOT NULL,
    exit_bar_ts               TEXT NOT NULL,
    qty                       REAL NOT NULL,
    entry_price               REAL NOT NULL,
    exit_price                REAL NOT NULL,
    gross_pnl                 REAL NOT NULL,
    fees                      REAL NOT NULL,
    funding                   REAL NOT NULL,
    net_pnl                   REAL NOT NULL,
    hold_bars                 INTEGER NOT NULL,
    backfill                  INTEGER NOT NULL DEFAULT 0
) STRICT;

-- 4.4d funding
CREATE TABLE IF NOT EXISTS funding (
    seq                       INTEGER PRIMARY KEY REFERENCES ledger_events(seq),
    batch_id                  INTEGER NOT NULL REFERENCES ledger_batches(batch_id),
    funding_id                TEXT NOT NULL,
    bar_commit_id             TEXT NOT NULL,
    symbol                    TEXT NOT NULL,
    bar_ts                    TEXT NOT NULL,
    window_start              TEXT NOT NULL,
    window_end                TEXT NOT NULL,
    notional_usd              REAL NOT NULL,
    funding_rate              REAL NOT NULL,
    funding_events            INTEGER NOT NULL,
    rate_available            INTEGER NOT NULL,
    funding_amount            REAL NOT NULL
) STRICT;

-- 4.4e position_snapshots
CREATE TABLE IF NOT EXISTS position_snapshots (
    seq                       INTEGER PRIMARY KEY REFERENCES ledger_events(seq),
    batch_id                  INTEGER NOT NULL REFERENCES ledger_batches(batch_id),
    bar_ts                    TEXT NOT NULL,
    bar_commit_id             TEXT NOT NULL,
    open_symbols              TEXT NOT NULL,  -- JSON array
    num_open                  INTEGER NOT NULL
) STRICT;

-- 4.4f position_snapshot_symbols (child table)
CREATE TABLE IF NOT EXISTS position_snapshot_symbols (
    snapshot_seq              INTEGER NOT NULL REFERENCES position_snapshots(seq) ON DELETE CASCADE,
    symbol                    TEXT NOT NULL,
    qty                       REAL NOT NULL,
    entry_price               REAL NOT NULL,
    entry_fill_id             TEXT NOT NULL,
    entry_bar_ts              TEXT NOT NULL,
    unrealized_gross          REAL NOT NULL,
    PRIMARY KEY (snapshot_seq, symbol)
) STRICT;

-- 4.4g equity_snapshots
CREATE TABLE IF NOT EXISTS equity_snapshots (
    seq                       INTEGER PRIMARY KEY REFERENCES ledger_events(seq),
    batch_id                  INTEGER NOT NULL REFERENCES ledger_batches(batch_id),
    bar_ts                    TEXT NOT NULL,
    bar_commit_id             TEXT NOT NULL,
    realized_gross_pnl        REAL NOT NULL,
    unrealized_pnl            REAL NOT NULL,
    funding_cum               REAL NOT NULL,
    fees_cum                  REAL NOT NULL,
    equity                    REAL NOT NULL,
    drawdown                  REAL NOT NULL,
    num_open                  INTEGER NOT NULL
) STRICT;

-- 4.5 ledger_state — mutable singleton cache
CREATE TABLE IF NOT EXISTS ledger_state (
    id                          INTEGER PRIMARY KEY CHECK (id = 1),
    watermark_bar_ts            TEXT,
    realized_gross              REAL NOT NULL DEFAULT 0.0,
    fees_cum                    REAL NOT NULL DEFAULT 0.0,
    funding_cum                 REAL NOT NULL DEFAULT 0.0,
    peak_equity                 REAL NOT NULL DEFAULT 0.0,
    updated_at                  TEXT NOT NULL
) STRICT;

-- 4.5 open_positions — mutable cache
CREATE TABLE IF NOT EXISTS open_positions (
    symbol                    TEXT PRIMARY KEY,
    entry_fill_id             TEXT NOT NULL,
    entry_price               REAL NOT NULL,
    qty                       REAL NOT NULL,
    entry_bar_ts              TEXT NOT NULL,
    entry_fill_ts             TEXT NOT NULL,
    funding_accrued           REAL NOT NULL DEFAULT 0.0,
    hold_bars                 INTEGER NOT NULL DEFAULT 0
) STRICT;
"""


# ---------------------------------------------------------------------------
# Trigger DDL — append-only enforcement
# ---------------------------------------------------------------------------

_APPEND_ONLY_TABLES = [
    "paper_config",
    "ledger_batches",
    "ledger_events",
    "signal_snapshots",
    "fills",
    "trades",
    "funding",
    "position_snapshots",
    "position_snapshot_symbols",
    "equity_snapshots",
]

_MUTABLE_TABLES = ["ledger_state", "open_positions"]


def _build_trigger_sql() -> str:
    """Generate the append-only trigger DDL.

    Tables in ``_APPEND_ONLY_TABLES`` get BEFORE UPDATE/DELETE triggers
    that raise ABORT.  ``ledger_state`` and ``open_positions`` are
    intentionally mutable and receive no append-only triggers.
    """
    parts: list[str] = []
    for tbl in _APPEND_ONLY_TABLES:
        for action in ("UPDATE", "DELETE"):
            trigger = f"""
CREATE TRIGGER IF NOT EXISTS trg_{tbl}_deny_{action.lower()}
BEFORE {action} ON {tbl}
BEGIN
    SELECT RAISE(ABORT, 'Table {tbl} is append-only — {action} not permitted');
END;
"""
            parts.append(trigger)
    return "\n".join(parts)


_TRIGGER_SQL = _build_trigger_sql()


# ---------------------------------------------------------------------------
# Database initialisation
# ---------------------------------------------------------------------------

def initialize_database(db_path: str | Path, config: dict[str, Any]) -> Path:
    """Create a fresh paper ledger DB and insert the singleton config row.

    Refuses if *db_path* already exists.  On success returns the resolved
    ``Path`` to the database file.

    The *config* dict must contain (at minimum) the fields produced by
    :func:`quantbot.paper.config.build_config`.
    """
    db_path = Path(db_path)
    if db_path.exists():
        raise FileExistsError(
            f"Refusing to initialise: {db_path} already exists."
        )

    conn = connect_writer(db_path)
    try:
        assert_sqlite_capabilities(conn)

        # Create schema + triggers
        conn.executescript(_SCHEMA_SQL)
        conn.executescript(_TRIGGER_SQL)

        # Insert singleton config (id=1)
        now = datetime.now(timezone.utc).isoformat()
        fee_model = config.get("fee_model", {})
        slippage_model = config.get("slippage_model", {})
        funding_model = config.get("funding_model", {})
        freshness = config.get("freshness", {})

        conn.execute(
            """
            INSERT INTO paper_config (
                id,
                db_schema_version,
                paper_contract_version,
                paper_engine_version,
                baseline_label,
                forward_start_ts,
                initial_equity_usd,
                notional_usd,
                leverage,
                fee_type,
                fee_bps,
                slippage_type,
                slippage_bps,
                funding_type,
                funding_applied_as,
                fill_model,
                signal_source,
                freshness_bar_interval_hours,
                freshness_max_bar_staleness_hours,
                freshness_heartbeat_max_age_hours,
                created_at,
                config_hash
            ) VALUES (1, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                DB_SCHEMA_VERSION,
                config.get("schema_version", 1),
                PAPER_ENGINE_VERSION,
                config.get("baseline_label", BASELINE_LABEL),
                config["forward_start_ts"],
                config["initial_equity_usd"],
                config["notional_usd"],
                config["leverage"],
                fee_model.get("type", "flat_taker"),
                fee_model.get("fee_bps", 5.0),
                slippage_model.get("type", "fixed"),
                slippage_model.get("slippage_bps", 5.0),
                funding_model.get("type", "accrual"),
                funding_model.get("applied_as", "cash_flow"),
                config.get("fill_model", "next_bar_open_pessimistic"),
                config.get("signal_source", "observation_log.json:per_bar_obs"),
                freshness.get("bar_interval_hours", 8),
                freshness.get("max_bar_staleness_hours", 24.0),
                freshness.get("heartbeat_max_age_hours", 24.0),
                now,
                config.get("config_hash", ""),
            ),
        )

        # Insert initial ledger_state row
        conn.execute(
            """
            INSERT INTO ledger_state (id, updated_at)
            VALUES (1, ?)
            """,
            (now,),
        )

        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()

    return db_path


# ---------------------------------------------------------------------------
# Identity / capability validation
# ---------------------------------------------------------------------------

def validate_database_identity(conn: sqlite3.Connection) -> dict[str, Any]:
    """Read + return the singleton config row, raising on any contract violation.

    Validates:
    - exactly one config row (id=1)
    - ``db_schema_version`` matches ``DB_SCHEMA_VERSION``
    - ``paper_engine_version`` matches ``PAPER_ENGINE_VERSION``
    - ``baseline_label`` matches ``BASELINE_LABEL``
    - ``config_hash`` is correct (excludes itself, stable)

    Returns the config row as a dict on success.
    """
    row = conn.execute(
        "SELECT * FROM paper_config WHERE id = 1"
    ).fetchone()

    if row is None:
        raise ValueError("paper_config row (id=1) not found — corrupted or uninitialised DB.")

    cfg = dict(row)

    if cfg["db_schema_version"] != DB_SCHEMA_VERSION:
        raise ValueError(
            f"DB schema version mismatch: stored {cfg['db_schema_version']} "
            f"!= required {DB_SCHEMA_VERSION}"
        )

    if cfg["paper_engine_version"] != PAPER_ENGINE_VERSION:
        raise ValueError(
            f"Paper engine version mismatch: stored {cfg['paper_engine_version']} "
            f"!= required {PAPER_ENGINE_VERSION}"
        )

    if cfg["baseline_label"] != BASELINE_LABEL:
        raise ValueError(
            f"Baseline label mismatch: stored {cfg['baseline_label']!r} "
            f"!= required {BASELINE_LABEL!r}"
        )

    # Recompute config_hash over all fields except config_hash itself
    stored_hash = cfg.pop("config_hash")
    recomputed = config_hash_from_row(cfg)
    if stored_hash != recomputed:
        raise ValueError(
            f"config_hash mismatch: stored {stored_hash} != recomputed {recomputed}"
        )

    # Restore for caller
    cfg["config_hash"] = stored_hash
    return cfg


def config_hash_from_row(config_row: dict[str, Any]) -> str:
    """Deterministic SHA-256 over the config row, excluding ``config_hash``.

    The row dict may contain SQLite column names — we serialise only the
    canonical subset that matches the JSON config contract.
    """
    canonical = {
        "schema_version": config_row.get("paper_contract_version", 1),
        "engine_version": config_row["paper_engine_version"],
        "baseline_label": config_row["baseline_label"],
        "forward_start_ts": config_row["forward_start_ts"],
        "initial_equity_usd": config_row["initial_equity_usd"],
        "notional_usd": config_row["notional_usd"],
        "leverage": config_row["leverage"],
        "fee_model": {
            "type": config_row["fee_type"],
            "fee_bps": config_row["fee_bps"],
        },
        "slippage_model": {
            "type": config_row["slippage_type"],
            "slippage_bps": config_row["slippage_bps"],
        },
        "funding_model": {
            "type": config_row["funding_type"],
            "applied_as": config_row["funding_applied_as"],
        },
        "fill_model": config_row["fill_model"],
        "signal_source": config_row["signal_source"],
        "freshness": {
            "bar_interval_hours": config_row["freshness_bar_interval_hours"],
            "max_bar_staleness_hours": config_row["freshness_max_bar_staleness_hours"],
            "heartbeat_max_age_hours": config_row["freshness_heartbeat_max_age_hours"],
        },
    }
    return hashlib.sha256(canonical_json_dumps(canonical).encode("utf-8")).hexdigest()


# ---------------------------------------------------------------------------
# Legacy artifact detection
# ---------------------------------------------------------------------------

def _legacy_artifact_paths(output_dir: Path) -> list[Path]:
    """Return a list of legacy paper artifacts present in *output_dir*."""
    patterns = [
        "paper_config.json",
        "paper_fills.jsonl",
        "paper_trades.jsonl",
        "paper_funding.jsonl",
        "paper_positions.jsonl",
        "paper_equity.jsonl",
        "paper_signal_snapshots.jsonl",
        "paper_position_state.json",
        "paper_pnl_summary.json",
        "paper_provenance.json",
        "paper_verify_report.json",
    ]
    found: list[Path] = []
    for p in patterns:
        path = output_dir / p
        if path.exists():
            found.append(path)
    return found
