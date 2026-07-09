"""Tests for the full-window emit CLI entry point.

Adapted to the actual ``emit_full_window_funding_source_snapshot`` function
signature which writes artifacts to ``db_path.parent`` (not a separate output
dir).  The test therefore places the DB inside the output directory so that
``db_path.parent == output_dir``.
"""

from __future__ import annotations

import json
import os
import sqlite3
import subprocess
import sys
from pathlib import Path

import pytest

# Path to the CLI module
CLI_MODULE = "quantbot.paper.funding_source_full_window_emit_cli"

# Shared test constants
_LANE_ID = "paper_pnl_v1"
_SYMBOL = "SOL"
_W1 = ("2026-06-14T16:00:00Z", "2026-06-15T00:00:00Z")
_W2 = ("2026-06-15T00:00:00Z", "2026-06-15T08:00:00Z")
_W3 = ("2026-06-15T08:00:00Z", "2026-06-15T16:00:00Z")


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _ms_at(raw: str, *, offset_ms: int = 0) -> int:
    from datetime import datetime, timezone

    dt = datetime.fromisoformat(raw.replace("Z", "+00:00")).astimezone(timezone.utc)
    return int(dt.timestamp() * 1000) + offset_ms


def _make_csv(path: Path, symbol: str, rows: list[dict]) -> Path:
    """Write a minimal funding CSV file matching the existing test helper."""
    path.parent.mkdir(parents=True, exist_ok=True)
    lines = ["fundingTime,fundingRate,markPrice"]
    for r in rows:
        lines.append(f"{r['fundingTime_ms']},{r.get('fundingRate', '0.0001')},100.0")
    path.write_text("\n".join(lines) + "\n")
    return path


def _make_funding_row(
    window_end: str,
    *,
    symbol: str = _SYMBOL,
    row_index: int = 1,
    funding_rate: str = "0.0001",
) -> dict:
    """Return a funding row with a timestamp just after the window endpoint."""
    return {
        "symbol": symbol,
        "fundingTime_ms": _ms_at(window_end, offset_ms=5),
        "fundingRate": funding_rate,
    }


def _window(symbol: str, start: str, end: str) -> dict:
    return {"symbol": symbol, "window_start": start, "window_end": end}


def _create_csv_files(data_dir: Path) -> dict[str, Path]:
    """Create funding CSV files for the standard three-window ledger."""
    windows = [
        _window(_SYMBOL, _W1[0], _W1[1]),
        _window(_SYMBOL, _W2[0], _W2[1]),
        _window(_SYMBOL, _W3[0], _W3[1]),
    ]
    rows = [_make_funding_row(w["window_end"], symbol=_SYMBOL, row_index=i) for i, w in enumerate(windows, start=1)]
    csv_path = data_dir / f"{_SYMBOL}_8h_funding.csv"
    _make_csv(csv_path, _SYMBOL, rows)
    return {_SYMBOL: csv_path}


def _init_db(
    path: Path,
    *,
    lane_id: str = _LANE_ID,
) -> Path:
    """Create a minimal lane DB with one committed batch and funding rows.

    Mirrors the pattern from ``test_funding_source_full_window_emit.py``.
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(path))
    conn.row_factory = sqlite3.Row
    try:
        conn.execute(
            "CREATE TABLE paper_config (id INTEGER PRIMARY KEY, lane_id TEXT)"
        )
        conn.execute(
            "INSERT INTO paper_config (id, lane_id) VALUES (1, ?)", (lane_id,)
        )
        conn.execute(
            "CREATE TABLE ledger_batches ("
            "batch_id INTEGER PRIMARY KEY, "
            "committed_at TEXT, "
            "prior_watermark_bar_ts TEXT, "
            "new_watermark_bar_ts TEXT"
            ")"
        )
        conn.execute(
            "INSERT INTO ledger_batches (batch_id, committed_at, "
            "prior_watermark_bar_ts, new_watermark_bar_ts) "
            "VALUES (1, '2026-06-15T01:00:00Z', "
            "'2026-06-14T08:00:00Z', '2026-06-15T01:00:00Z')"
        )
        conn.execute(
            "CREATE TABLE funding ("
            "symbol TEXT, window_start TEXT, window_end TEXT, "
            "funding_amount REAL"
            ")"
        )
        windows = [
            _window(_SYMBOL, _W1[0], _W1[1]),
            _window(_SYMBOL, _W2[0], _W2[1]),
            _window(_SYMBOL, _W3[0], _W3[1]),
        ]
        for fw in windows:
            conn.execute(
                "INSERT INTO funding (symbol, window_start, window_end) "
                "VALUES (?, ?, ?)",
                (fw["symbol"], fw["window_start"], fw["window_end"]),
            )
        conn.commit()
    finally:
        conn.close()
    return path


def _run_cli(argv: list[str]) -> subprocess.CompletedProcess:
    """Run the CLI as a subprocess via python -m."""
    cmd = [sys.executable, "-m", CLI_MODULE] + argv
    return subprocess.run(cmd, capture_output=True, text=True)


# ---------------------------------------------------------------------------
# Test classes
# ---------------------------------------------------------------------------


class TestCliHelp:
    def test_help_succeeds(self) -> None:
        result = _run_cli(["--help"])
        assert result.returncode == 0
        assert "usage:" in result.stdout.lower() or "usage:" in result.stderr.lower()


class TestCliMissingRequired:
    def test_missing_db(self, tmp_path: Path) -> None:
        result = _run_cli(
            [
                "--funding-source-dir",
                str(tmp_path),
                "--output-dir",
                str(tmp_path),
            ]
        )
        assert result.returncode != 0

    def test_missing_funding_source_dir(self, tmp_path: Path) -> None:
        db = tmp_path / "test.db"
        db.touch()
        result = _run_cli(
            [
                "--db",
                str(db),
                "--output-dir",
                str(tmp_path),
            ]
        )
        assert result.returncode != 0

    def test_missing_output_dir(self, tmp_path: Path) -> None:
        db = tmp_path / "test.db"
        db.touch()
        result = _run_cli(
            [
                "--db",
                str(db),
                "--funding-source-dir",
                str(tmp_path),
            ]
        )
        assert result.returncode != 0


class TestCliDryRun:
    def test_dry_run_succeeds(self, tmp_path: Path) -> None:
        db = tmp_path / "test.db"
        db.touch()
        result = _run_cli(
            [
                "--db",
                str(db),
                "--funding-source-dir",
                str(tmp_path),
                "--output-dir",
                str(tmp_path),
                "--dry-run",
            ]
        )
        assert result.returncode == 0
        output = json.loads(result.stdout)
        assert output["status"] == "DRY_RUN"
        assert "db" in output
        assert "funding_source_dir" in output
        assert "output_dir" in output


class TestCliEmitToTemp:
    """Integration test: emit full-window snapshot+bundle to temp output dir.

    Places the DB *inside* the output dir so that the underlying function
    (which writes to ``db_path.parent``) produces artifacts in the expected
    location.
    """

    def test_emit_full_window_to_temp(self, tmp_path: Path) -> None:
        """CLI emits full-window snapshot + bundle to temp output dir."""
        # 1. Create funding CSV
        csv_dir = tmp_path / "funding_csv"
        csv_dir.mkdir(parents=True, exist_ok=True)
        _create_csv_files(csv_dir)

        # 2. Create DB inside output dir so db_path.parent == output_dir
        output_dir = tmp_path / "output"
        output_dir.mkdir(parents=True, exist_ok=True)
        db_path = output_dir / "test.db"
        _init_db(db_path)

        # 3. Run CLI
        result = _run_cli(
            [
                "--db",
                str(db_path),
                "--funding-source-dir",
                str(csv_dir),
                "--output-dir",
                str(output_dir),
            ]
        )
        assert result.returncode == 0, f"CLI failed: stderr={result.stderr}"

        # 4. Verify JSON summary
        summary = json.loads(result.stdout)
        assert summary["status"] == "OK"
        assert "snapshot_path" in summary
        assert "snapshot_sha256" in summary
        assert "bundle_path" in summary
        assert "bundle_sha256" in summary
        assert "target_batch_id" in summary
        assert "evaluation_window" in summary
        assert "resolved_funding_source_dir" in summary

        # 5. Verify files exist on disk
        assert os.path.isfile(
            summary["snapshot_path"]
        ), f"Snapshot not found at {summary['snapshot_path']}"
        assert os.path.isfile(
            summary["bundle_path"]
        ), f"Bundle not found at {summary['bundle_path']}"

        # 6. Verify files are within output dir (db_path.parent == output_dir)
        snapshot_path = Path(summary["snapshot_path"])
        bundle_path = Path(summary["bundle_path"])
        assert str(snapshot_path).startswith(str(output_dir)), (
            f"Snapshot outside output dir: {snapshot_path}"
        )
        assert str(bundle_path).startswith(str(output_dir)), (
            f"Bundle outside output dir: {bundle_path}"
        )

    def test_emit_refuses_missing_funding_dir(self, tmp_path: Path) -> None:
        """CLI refuses non-existent funding source dir."""
        db = tmp_path / "test.db"
        db.touch()
        missing_dir = tmp_path / "does_not_exist"
        result = _run_cli(
            [
                "--db",
                str(db),
                "--funding-source-dir",
                str(missing_dir),
                "--output-dir",
                str(tmp_path),
            ]
        )
        assert result.returncode != 0
        assert "ERROR" in result.stderr or "ERROR" in result.stdout

    def test_emit_refuses_missing_db(self, tmp_path: Path) -> None:
        """CLI refuses non-existent DB path."""
        missing_db = tmp_path / "does_not_exist.db"
        result = _run_cli(
            [
                "--db",
                str(missing_db),
                "--funding-source-dir",
                str(tmp_path),
                "--output-dir",
                str(tmp_path),
            ]
        )
        assert result.returncode != 0
        assert "ERROR" in result.stderr or "ERROR" in result.stdout

    def test_emit_does_not_touch_report_path(self, tmp_path: Path) -> None:
        """CLI does not touch paper_verify_report.json."""
        # Create a dummy report to verify it's not touched
        report_path = tmp_path / "paper_verify_report.json"
        report_path.write_text('{"original": true}')
        report_mtime = os.path.getmtime(str(report_path))

        # Create funding CSV
        csv_dir = tmp_path / "funding_csv"
        csv_dir.mkdir(parents=True, exist_ok=True)
        _create_csv_files(csv_dir)

        # Create DB inside output dir
        output_dir = tmp_path / "output"
        output_dir.mkdir(parents=True, exist_ok=True)
        db_path = output_dir / "test.db"
        _init_db(db_path)

        result = _run_cli(
            [
                "--db",
                str(db_path),
                "--funding-source-dir",
                str(csv_dir),
                "--output-dir",
                str(output_dir),
            ]
        )
        assert result.returncode == 0, f"CLI failed: {result.stderr}"

        # Verify report is untouched
        assert os.path.getmtime(str(report_path)) == report_mtime
        assert report_path.read_text() == '{"original": true}'