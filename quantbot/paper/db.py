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
    config_hash                TEXT NOT NULL,
    -- Additive new-lane identity columns (ADDITIVE_NEW_LANE_DB_SCHEMA_PHASE3_PLAN).
    -- Nullable and unpopulated for the v1 baseline: a NULL lane_id means implicit v1
    -- mode, so old schema-1 rows (which lack these columns entirely) and freshly
    -- created baseline rows behave identically. The writer does NOT populate these
    -- yet; config_hash_from_row does NOT read them. They exist only so a future
    -- new-lane DB can store lane identity without an in-place ALTER.
    lane_id                    TEXT,
    strategy_id                TEXT,
    strategy_version           TEXT,
    config_hash_v2             TEXT,
    pre_registration_hash      TEXT
) STRICT;

-- 4.2 ledger_batches — mutable (updated after commit)
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
    unrealized_gross          REAL NOT NULL DEFAULT 0.0,
    PRIMARY KEY (snapshot_seq, symbol)
) STRICT;

-- 4.5 equity_snapshots
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

-- 4.6 ledger_state (mutable, singleton)
CREATE TABLE IF NOT EXISTS ledger_state (
    id                  INTEGER PRIMARY KEY CHECK (id = 1),
    watermark_bar_ts    TEXT,
    realized_gross       REAL NOT NULL DEFAULT 0.0,
    fees_cum            REAL NOT NULL DEFAULT 0.0,
    funding_cum         REAL NOT NULL DEFAULT 0.0,
    peak_equity         REAL NOT NULL DEFAULT 0.0,
    updated_at          TEXT NOT NULL
) STRICT;

-- 4.7 open_positions (mutable)
-- Carries every field the deterministic engine needs to resume an open
-- position across writer runs (entry_fee / funding_accrued / hold_bars are
-- required by the exit path), so restart is lossless.
CREATE TABLE IF NOT EXISTS open_positions (
    symbol              TEXT PRIMARY KEY,
    entry_fill_id       TEXT NOT NULL,
    entry_price         REAL NOT NULL,
    qty                 REAL NOT NULL,
    entry_bar_ts        TEXT NOT NULL,
    entry_fill_ts       TEXT NOT NULL,
    entry_fee           REAL NOT NULL DEFAULT 0.0,
    funding_accrued     REAL NOT NULL DEFAULT 0.0,
    hold_bars           INTEGER NOT NULL DEFAULT 0
) STRICT;
"""


# ---------------------------------------------------------------------------
# Trigger DDL — append-only enforcement
# ---------------------------------------------------------------------------

# ledger_batches is MUTABLE (updated after commit with committed_at, new_watermark, etc.)
# ledger_state and open_positions are also mutable by design
_APPEND_ONLY_TABLES = [
    "paper_config",
    "ledger_events",
    "signal_snapshots",
    "fills",
    "trades",
    "funding",
    "position_snapshots",
    "position_snapshot_symbols",
    "equity_snapshots",
]

_MUTABLE_TABLES = ["ledger_batches", "ledger_state", "open_positions"]


def _build_trigger_sql() -> str:
    """Generate the append-only trigger DDL.

    Tables in ``_APPEND_ONLY_TABLES`` get BEFORE UPDATE/DELETE triggers
    that raise ABORT.  ``ledger_batches``, ``ledger_state`` and
    ``open_positions`` are intentionally mutable and receive no append-only triggers.
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
    """
    db_path = Path(db_path)
    if db_path.exists():
        raise FileExistsError(
            f"Database {db_path} already exists — refusing to overwrite"
        )

    conn = connect_writer(db_path)
    try:
        # Execute schema DDL
        conn.executescript(_SCHEMA_SQL)

        # Install append-only triggers
        conn.executescript(_TRIGGER_SQL)

        # Insert paper_config row (singleton, id=1)
        now = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
        cfg_hash = config_hash(config)
        conn.execute(
            """
            INSERT INTO paper_config (
                id, db_schema_version, paper_contract_version,
                paper_engine_version, baseline_label,
                forward_start_ts, initial_equity_usd, notional_usd,
                leverage, fee_type, fee_bps,
                slippage_type, slippage_bps,
                funding_type, funding_applied_as,
                fill_model, signal_source,
                freshness_bar_interval_hours,
                freshness_max_bar_staleness_hours,
                freshness_heartbeat_max_age_hours,
                created_at, config_hash
            ) VALUES (1, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                DB_SCHEMA_VERSION,
                config.get("schema_version", DB_SCHEMA_VERSION),
                PAPER_ENGINE_VERSION,
                config.get("baseline_label", "paper_pnl_v1"),
                config["forward_start_ts"],
                float(config.get("initial_equity_usd", 10000.0)),
                float(config.get("notional_usd", 1000.0)),
                float(config.get("leverage", 1.0)),
                config.get("fee_model", {}).get("type", "flat_taker"),
                float(config.get("fee_bps", 5.0)),
                config.get("slippage_model", {}).get("type", "fixed"),
                float(config.get("slippage_bps", 5.0)),
                config.get("funding_model", {}).get("type", "accrual"),
                config.get("funding_model", {}).get("applied_as", "cash_flow"),
                config.get("fill_model", "next_bar_open_pessimistic"),
                config.get("signal_source", "observation_log.json:per_bar_obs"),
                int(config.get("freshness", {}).get("bar_interval_hours", 8)),
                int(config.get("freshness", {}).get("max_bar_staleness_hours", 24)),
                int(config.get("freshness", {}).get("heartbeat_max_age_hours", 24)),
                now,
                cfg_hash,
            ),
        )

        # Insert initial ledger_state row (singleton, id=1)
        initial_equity = float(config.get("initial_equity_usd", 10000.0))
        conn.execute(
            """
            INSERT INTO ledger_state (
                id, watermark_bar_ts, realized_gross, fees_cum,
                funding_cum, peak_equity, updated_at
            ) VALUES (1, NULL, 0.0, 0.0, 0.0, ?, ?)
            """,
            (initial_equity, now),
        )

        conn.commit()
    except Exception:
        conn.rollback()
        conn.close()
        raise

    conn.close()
    return db_path


# ---------------------------------------------------------------------------
# DB identity validation
# ---------------------------------------------------------------------------

def validate_database_identity(conn: sqlite3.Connection) -> dict[str, Any]:
    """Read and validate the paper_config row.

    Returns the config dict on success; raises ``ValueError`` if the
    stored config does not satisfy the current engine contract.
    """
    row = conn.execute("SELECT * FROM paper_config WHERE id = 1").fetchone()
    if row is None:
        raise ValueError("paper_config row (id=1) not found")

    config = dict(row)

    # Validate engine version matches
    if config["paper_engine_version"] != PAPER_ENGINE_VERSION:
        raise ValueError(
            f"paper_engine_version mismatch: "
            f"stored={config['paper_engine_version']!r}, "
            f"expected={PAPER_ENGINE_VERSION!r}"
        )

    return config



def config_hash_from_row(row: sqlite3.Row) -> str:
    """Recompute config_hash from a paper_config row (excluding config_hash itself)."""
    # Reconstruct nested config structure to match build_config() output
    d = dict(row)
    d.pop("config_hash", None)
    # Schema identity for the v1 accounting hash is the PAPER CONTRACT version, NOT
    # the storage db_schema_version (ADDITIVE_NEW_LANE_DB_SCHEMA_PHASE3_PLAN §3). This
    # decouples the frozen v1 accounting hash from a future storage-schema bump (e.g.
    # db_schema_version 1 -> 2 for new-lane DBs): as long as paper_contract_version
    # stays 1, the recomputed hash is unchanged. Fall back to db_schema_version only
    # for legacy/synthetic rows that predate the paper_contract_version column, so the
    # existing golden hash is preserved byte-for-byte.
    schema_identity = d.get("paper_contract_version")
    if schema_identity is None:
        schema_identity = d.get("db_schema_version")
    # Rebuild nested structure
    config = {
        "schema_version": schema_identity,
        "engine_version": d.get("paper_engine_version"),
        "baseline_label": d.get("baseline_label"),
        "forward_start_ts": d.get("forward_start_ts"),
        "initial_equity_usd": d.get("initial_equity_usd"),
        "notional_usd": d.get("notional_usd"),
        "leverage": d.get("leverage"),
        "fee_model": {"type": d.get("fee_type"), "fee_bps": d.get("fee_bps")},
        "slippage_model": {"type": d.get("slippage_type"), "slippage_bps": d.get("slippage_bps")},
        "funding_model": {"type": d.get("funding_type"), "applied_as": d.get("funding_applied_as")},
        "fill_model": d.get("fill_model"),
        "signal_source": d.get("signal_source"),
        "freshness": {
            "bar_interval_hours": d.get("freshness_bar_interval_hours"),
            "max_bar_staleness_hours": d.get("freshness_max_bar_staleness_hours"),
            "heartbeat_max_age_hours": d.get("freshness_heartbeat_max_age_hours"),
        },
    }
    return config_hash(config)

# ---------------------------------------------------------------------------
# Legacy artifact detection
# ---------------------------------------------------------------------------

def _legacy_artifact_paths(output_dir: Path) -> list[Path]:
    """Return a list of legacy JSONL/JSON files in *output_dir*."""
    patterns = [
        "paper_config.json",
        "paper_fills.jsonl",
        "paper_trades.jsonl",
        "paper_funding.jsonl",
        "paper_positions.jsonl",
        "paper_equity.jsonl",
        "paper_pnl_summary.json",
        "paper_position_state.json",
    ]
    found = []
    for p in patterns:
        fp = output_dir / p
        if fp.exists():
            found.append(fp)
    return found
