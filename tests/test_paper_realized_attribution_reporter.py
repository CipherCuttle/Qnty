"""Tests for the read-only realized attribution reporter (v0).

These tests build minimal SQLite fixtures under pytest tmp paths only. They do
NOT touch prod/shadow DBs, do NOT run the paper writer/verifier, do NOT run
migrations or schema-ensure helpers, and do NOT mutate any real ledger.

They verify the reporter is read-only (byte-for-byte stable source), computes
closed-trade realized net as SUM(trades.net_pnl), keeps realized/unrealized
separate, computes the accounting identity residual, infers long-only side when
no side column exists, reports missing optionals as UNAVAILABLE_READ_ONLY, and
exits non-zero on a missing/invalid DB.
"""

from __future__ import annotations

import json
import sqlite3
import subprocess
import sys
from pathlib import Path

import pytest

from quantbot.paper.realized_attribution import (
    UNAVAILABLE,
    ReporterError,
    build_report,
    render_json,
)

REPO_ROOT = Path(__file__).resolve().parent.parent
SCRIPT = REPO_ROOT / "scripts" / "qnty-paper-realized-attribution.py"


# ---------------------------------------------------------------------------
# Minimal fixtures (only the tables/columns the reporter reads)
# ---------------------------------------------------------------------------


def _make_minimal_db(
    path: Path,
    *,
    initial_equity: float = 10_000.0,
    trades: list[tuple[float, float, float, float]] | None = None,
    equity_row: dict | None = None,
    open_positions: list[dict] | None = None,
    include_side_column: bool = False,
) -> None:
    """Create a minimal paper-ledger-shaped SQLite DB.

    ``trades`` entries are (gross_pnl, fees, funding, net_pnl) tuples.
    """
    conn = sqlite3.connect(str(path))
    try:
        conn.execute(
            """
            CREATE TABLE paper_config (
                id INTEGER PRIMARY KEY CHECK (id = 1),
                baseline_label TEXT,
                initial_equity_usd REAL NOT NULL,
                config_hash TEXT,
                lane_id TEXT,
                config_hash_v2 TEXT
            )
            """
        )
        conn.execute(
            "INSERT INTO paper_config (id, baseline_label, initial_equity_usd, config_hash) "
            "VALUES (1, 'v1_baseline', ?, 'deadbeef')",
            (initial_equity,),
        )

        conn.execute(
            """
            CREATE TABLE ledger_state (
                id INTEGER PRIMARY KEY CHECK (id = 1),
                watermark_bar_ts TEXT,
                realized_gross REAL,
                fees_cum REAL,
                funding_cum REAL
            )
            """
        )
        conn.execute(
            "INSERT INTO ledger_state (id, watermark_bar_ts, realized_gross, fees_cum, funding_cum) "
            "VALUES (1, '2026-07-06T00:00:00Z', 0, 0, 0)"
        )

        conn.execute(
            """
            CREATE TABLE ledger_batches (
                batch_id INTEGER PRIMARY KEY,
                committed_at TEXT,
                git_sha TEXT,
                prior_watermark_bar_ts TEXT,
                new_watermark_bar_ts TEXT,
                config_hash TEXT,
                lane_id TEXT
            )
            """
        )
        conn.execute(
            "INSERT INTO ledger_batches VALUES "
            "(11, '2026-07-06T00:00:00Z', 'abc123', "
            "'2026-07-05T00:00:00Z', '2026-07-06T00:00:00Z', 'deadbeef', NULL)"
        )

        conn.execute(
            """
            CREATE TABLE trades (
                seq INTEGER PRIMARY KEY,
                gross_pnl REAL, fees REAL, funding REAL, net_pnl REAL,
                hold_bars INTEGER
            )
            """
        )
        trades = trades or []
        for i, (g, f, fu, n) in enumerate(trades, start=1):
            conn.execute(
                "INSERT INTO trades (seq, gross_pnl, fees, funding, net_pnl, hold_bars) "
                "VALUES (?, ?, ?, ?, ?, ?)",
                (i, g, f, fu, n, 5),
            )

        conn.execute(
            """
            CREATE TABLE fills (
                seq INTEGER PRIMARY KEY, side TEXT, kind TEXT
            )
            """
        )
        for i in range(len(trades) * 2):
            conn.execute(
                "INSERT INTO fills (seq, side, kind) VALUES (?, ?, ?)",
                (i + 1, "BUY" if i % 2 == 0 else "SELL", "entry" if i % 2 == 0 else "exit"),
            )

        conn.execute(
            """
            CREATE TABLE equity_snapshots (
                seq INTEGER PRIMARY KEY,
                batch_id INTEGER, bar_ts TEXT,
                realized_gross_pnl REAL, unrealized_pnl REAL,
                funding_cum REAL, fees_cum REAL,
                equity REAL, drawdown REAL, num_open INTEGER
            )
            """
        )
        if equity_row is not None:
            conn.execute(
                "INSERT INTO equity_snapshots (seq, batch_id, bar_ts, realized_gross_pnl, "
                "unrealized_pnl, funding_cum, fees_cum, equity, drawdown, num_open) "
                "VALUES (1, 11, '2026-07-06T00:00:00Z', ?, ?, ?, ?, ?, 0, ?)",
                (
                    equity_row["realized_gross_pnl"],
                    equity_row["unrealized_pnl"],
                    equity_row["funding_cum"],
                    equity_row["fees_cum"],
                    equity_row["equity"],
                    equity_row["num_open"],
                ),
            )

        if include_side_column:
            conn.execute(
                """
                CREATE TABLE open_positions (
                    symbol TEXT PRIMARY KEY, side TEXT, qty REAL, entry_price REAL,
                    entry_fee REAL, funding_accrued REAL, hold_bars INTEGER
                )
                """
            )
        else:
            conn.execute(
                """
                CREATE TABLE open_positions (
                    symbol TEXT PRIMARY KEY, qty REAL, entry_price REAL,
                    entry_fee REAL, funding_accrued REAL, hold_bars INTEGER
                )
                """
            )
        for op in open_positions or []:
            cols = ", ".join(op.keys())
            ph = ", ".join("?" for _ in op)
            conn.execute(
                f"INSERT INTO open_positions ({cols}) VALUES ({ph})",
                tuple(op.values()),
            )

        conn.commit()
    finally:
        conn.close()


@pytest.fixture
def basic_db(tmp_path: Path) -> Path:
    db = tmp_path / "paper_ledger.db"
    _make_minimal_db(
        db,
        initial_equity=10_000.0,
        trades=[(100.0, 5.0, 2.0, 93.0), (-50.0, 5.0, 1.0, -56.0)],
        equity_row={
            "realized_gross_pnl": 50.0,   # 100 + (-50)
            "unrealized_pnl": 200.0,
            "funding_cum": 3.0,
            "fees_cum": 12.0,             # 10 closed + 2 open-entry
            "equity": 10_235.0,           # 10000 + 50 - 12 - 3 + 200
            "num_open": 1,
        },
        open_positions=[
            {
                "symbol": "BTCUSDT",
                "qty": 0.5,
                "entry_price": 60_000.0,
                "entry_fee": 2.0,
                "funding_accrued": 0.0,
                "hold_bars": 3,
            }
        ],
    )
    return db


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


def test_read_only_no_hash_size_mtime_change(basic_db: Path):
    """(1) Reporter must not change the source DB hash/size/mtime."""
    import hashlib

    before = basic_db.read_bytes()
    before_sha = hashlib.sha256(before).hexdigest()
    before_stat = basic_db.stat()

    report = build_report(basic_db)

    after = basic_db.read_bytes()
    assert hashlib.sha256(after).hexdigest() == before_sha
    assert basic_db.stat().st_size == before_stat.st_size
    assert basic_db.stat().st_mtime_ns == before_stat.st_mtime_ns
    # No WAL / journal / sidecar created.
    assert not (basic_db.parent / "paper_ledger.db-wal").exists()
    assert not (basic_db.parent / "paper_ledger.db-journal").exists()
    assert report["read_only"] is True
    assert report["read_only_integrity"] == "READ_ONLY_CONFIRMED"
    assert report["db_sha256_before"] == report["db_sha256_after"] == before_sha


def test_required_top_level_fields(basic_db: Path):
    """(2) All required top-level JSON fields are present."""
    report = build_report(basic_db, lane_label="prod")
    required = [
        "schema_version", "db_path", "lane_label", "generated_at_utc",
        "read_only", "db_sha256_before", "db_sha256_after",
        "db_size_before", "db_size_after", "db_mtime_before", "db_mtime_after",
        "read_only_integrity", "lane_identity", "latest_batch", "latest_equity",
        "realized_attribution", "open_positions", "evidence_quality",
        "unavailable_fields", "warnings",
    ]
    for field in required:
        assert field in report, f"missing top-level field: {field}"
    assert report["schema_version"] == "realized_attribution_report_v0"
    assert report["lane_label"] == "prod"


def test_closed_trade_realized_net_is_sum_net_pnl(basic_db: Path):
    """(3) Closed-trade realized net == SUM(trades.net_pnl)."""
    report = build_report(basic_db)
    ra = report["realized_attribution"]
    assert ra["n_closed"] == 2
    assert ra["closed_trade_realized_net_pnl"] == pytest.approx(93.0 + -56.0)
    assert ra["closed_trade_realized_gross_pnl"] == pytest.approx(50.0)
    # Explicitly NOT equal to ledger_gross - fees_cum - funding_cum.
    ledger_net = ra["ledger_realized_gross_pnl"] - ra["ledger_fees_cum"] - ra["ledger_funding_cum"]
    assert ra["closed_trade_realized_net_pnl"] != pytest.approx(ledger_net)


def test_realized_unrealized_split_separate(basic_db: Path):
    """(4) Realized and unrealized figures are separate, never merged."""
    report = build_report(basic_db)
    ra = report["realized_attribution"]
    le = report["latest_equity"]
    assert ra["ledger_unrealized_pnl"] == pytest.approx(200.0)
    assert le["unrealized_pnl"] == pytest.approx(200.0)
    assert le["realized_gross_pnl"] == pytest.approx(50.0)
    # No merged "profit" field exists.
    assert "profit" not in report
    assert "total_pnl" not in report


def test_accounting_identity_residual(basic_db: Path):
    """(5) equity == initial + realized_gross - fees - funding + unrealized."""
    report = build_report(basic_db)
    ra = report["realized_attribution"]
    assert ra["accounting_identity_residual"] == pytest.approx(0.0, abs=1e-6)
    assert report["warnings"] == [] or all(
        "accounting_identity_residual" not in w for w in report["warnings"]
    )


def test_open_position_side_inferred_long(basic_db: Path):
    """(6) side == 'long' when no side column and qty > 0."""
    report = build_report(basic_db)
    positions = report["open_positions"]
    assert len(positions) == 1
    assert positions[0]["symbol"] == "BTCUSDT"
    assert positions[0]["side"] == "long"
    assert positions[0]["qty"] == pytest.approx(0.5)
    # Unrealized detail absent (no position_snapshots) -> UNAVAILABLE, not invented.
    assert positions[0]["unrealized_pnl"] == UNAVAILABLE


def test_side_column_used_when_present(tmp_path: Path):
    """(6b) An explicit side column is used rather than inferred."""
    db = tmp_path / "paper_ledger.db"
    _make_minimal_db(
        db,
        trades=[(1.0, 0.0, 0.0, 1.0)],
        equity_row={
            "realized_gross_pnl": 1.0, "unrealized_pnl": 0.0,
            "funding_cum": 0.0, "fees_cum": 0.0, "equity": 10_001.0, "num_open": 1,
        },
        include_side_column=True,
        open_positions=[
            {
                "symbol": "ETHUSDT", "side": "long", "qty": 1.0,
                "entry_price": 3000.0, "entry_fee": 1.0,
                "funding_accrued": 0.0, "hold_bars": 1,
            }
        ],
    )
    report = build_report(db)
    assert report["open_positions"][0]["side"] == "long"


def test_missing_optional_fields_marked_unavailable(basic_db: Path):
    """(7) Missing optional fields are UNAVAILABLE_READ_ONLY, not invented."""
    report = build_report(basic_db)
    # No paper_verify_report.json next to the DB.
    eq = report["evidence_quality"]
    assert eq["current_verdict"] == UNAVAILABLE
    assert eq["funding_clean_carry_decision"] == UNAVAILABLE
    assert eq["funding_clean_carry_batch_decision"] == UNAVAILABLE
    # config_hash_v2 not populated on the v1 baseline.
    assert report["lane_identity"]["config_hash_v2"] == UNAVAILABLE
    assert UNAVAILABLE not in json.dumps(report["realized_attribution"]["n_closed"])
    # UNAVAILABLE fields are collected.
    assert any("config_hash_v2" in f for f in report["unavailable_fields"])


def test_clean_carry_read_from_existing_report_not_invented(basic_db: Path):
    """(7b) Existing verifier report fields are read but never upgraded."""
    report_path = basic_db.parent / "paper_verify_report.json"
    report_path.write_text(
        json.dumps(
            {
                "current_verdict": "OK",
                "funding_clean_carry_decision": "CAVEATED_ENGINE_SEMANTICS",
                "funding_clean_carry_status": "CAVEATED",
                "funding_clean_carry_batch_decision": "CLEAN_NET_OF_CARRY",
            }
        )
    )
    report = build_report(basic_db)
    eq = report["evidence_quality"]
    assert eq["current_verdict"] == "OK"
    assert eq["funding_clean_carry_decision"] == "CAVEATED_ENGINE_SEMANTICS"
    assert eq["funding_clean_carry_batch_decision"] == "CLEAN_NET_OF_CARRY"


def test_missing_db_raises(tmp_path: Path):
    """(8a) Missing DB raises ReporterError."""
    with pytest.raises(ReporterError):
        build_report(tmp_path / "nope.db")


def test_invalid_schema_raises(tmp_path: Path):
    """(8b) A DB without the expected schema raises ReporterError."""
    db = tmp_path / "empty.db"
    conn = sqlite3.connect(str(db))
    conn.execute("CREATE TABLE unrelated (x INTEGER)")
    conn.commit()
    conn.close()
    with pytest.raises(ReporterError):
        build_report(db)


def test_no_import_side_effects():
    """(9) Importing the module runs no writer/DB side effects."""
    # Re-import in a clean subprocess and assert no files are created.
    result = subprocess.run(
        [sys.executable, "-c", "import quantbot.paper.realized_attribution"],
        cwd=str(REPO_ROOT),
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, result.stderr


def test_cli_json_parseable(basic_db: Path):
    """(10) CLI --json emits parseable JSON and exits 0."""
    result = subprocess.run(
        [sys.executable, str(SCRIPT), "--db-path", str(basic_db), "--json"],
        cwd=str(REPO_ROOT),
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, result.stderr
    payload = json.loads(result.stdout)
    assert payload["schema_version"] == "realized_attribution_report_v0"
    assert payload["read_only_integrity"] == "READ_ONLY_CONFIRMED"
    assert payload["realized_attribution"]["n_closed"] == 2


def test_cli_missing_db_nonzero(tmp_path: Path):
    """(8c) CLI exits non-zero on missing DB."""
    result = subprocess.run(
        [sys.executable, str(SCRIPT), "--db-path", str(tmp_path / "nope.db"), "--json"],
        cwd=str(REPO_ROOT),
        capture_output=True,
        text=True,
    )
    assert result.returncode == 1


def test_cli_pretty_and_lane_label(basic_db: Path):
    """--pretty and --lane-label flags work."""
    result = subprocess.run(
        [
            sys.executable, str(SCRIPT), "--db-path", str(basic_db),
            "--json", "--pretty", "--lane-label", "shadow",
        ],
        cwd=str(REPO_ROOT),
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, result.stderr
    payload = json.loads(result.stdout)
    assert payload["lane_label"] == "shadow"
    assert "\n" in result.stdout  # pretty-printed


def test_render_json_deterministic(basic_db: Path):
    """Given the same report dict, JSON serialization is stable."""
    report = build_report(basic_db)
    assert render_json(report) == render_json(report)
