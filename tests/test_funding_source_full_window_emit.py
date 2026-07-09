"""Full-window funding source snapshot writer emission path tests.

Tests the emit module at ``quantbot/paper/funding_source_full_window_emit.py``
across four phases:

- Phase 1: Unit tests for internal helper functions (tests 1-9)
- Phase 2: Integration tests for ``emit_full_window_funding_source_snapshot()`` (tests 10-19)
- Phase 3: Verifier integration tests (tests 20-27)
- Phase 4: Regression tests (tests 28-33)
"""

from __future__ import annotations

import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import pytest

from quantbot.paper.db import connect_readonly
from quantbot.paper.funding_source_bundle import (
    bundle_window_reasons,
    resolve_funding_source_bundle,
)
from quantbot.paper.funding_source_full_window_emit import (
    FullWindowEmissionResult,
    _db_identity_hash,
    _full_ledger_evaluation_window,
    _full_ledger_windows,
    _lane_id_from_config,
    _latest_committed_batch,
    _resolve_source_dir,
    _source_csv_paths,
    emit_full_window_funding_source_snapshot,
)
from quantbot.paper.funding_source_snapshot import (
    SNAPSHOT_SCOPE_FULL_WINDOW,
    full_window_snapshot_path,
)
from quantbot.paper.sqlite_verify import (
    FundingSourcePathResolution,
    SOURCE_MODE_BUNDLE,
    SOURCE_MODE_LIVE_CURRENT,
    _build_funding_clean_carry_stamp,
    _full_ledger_requires_full_window_scope,
    _resolve_full_window_snapshot_for_gate,
)
from quantbot.paper.sqlite_writer import FundingSourceSnapshotEmissionError

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

_LANE_ID = "paper_pnl_v1"
_OTHER_LANE = "paper_pnl_null_shadow_v0"
_SYMBOL = "SOL"
_SYMBOLS = [_SYMBOL, "BTC"]

# Three consecutive 8h windows
_W1 = ("2026-06-14T16:00:00Z", "2026-06-15T00:00:00Z")
_W2 = ("2026-06-15T00:00:00Z", "2026-06-15T08:00:00Z")
_W3 = ("2026-06-15T08:00:00Z", "2026-06-15T16:00:00Z")
_FULL_LEDGER_WINDOW = {"start": _W1[0], "end": _W3[1]}


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _ms_at(raw: str, *, offset_ms: int = 0) -> int:
    dt = datetime.fromisoformat(raw.replace("Z", "+00:00")).astimezone(timezone.utc)
    return int(dt.timestamp() * 1000) + offset_ms


def _make_csv(path: Path, symbol: str, rows: list[dict]) -> Path:
    """Write a minimal funding CSV file."""
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
) -> dict[str, Any]:
    """Return a funding row with a timestamp just after the window endpoint."""
    return {
        "symbol": symbol,
        "fundingTime_ms": _ms_at(window_end, offset_ms=5),
        "fundingRate": funding_rate,
    }


def _window(symbol: str, start: str, end: str) -> dict[str, Any]:
    return {"symbol": symbol, "window_start": start, "window_end": end}


def _default_funding_windows() -> list[dict[str, Any]]:
    """Return three windows across the full-ledger span for a single symbol."""
    return [
        _window(_SYMBOL, _W1[0], _W1[1]),
        _window(_SYMBOL, _W2[0], _W2[1]),
        _window(_SYMBOL, _W3[0], _W3[1]),
    ]


def _csv_rows_for_windows(
    windows: list[dict[str, Any]],
) -> dict[str, list[dict]]:
    """Build CSV row data that covers every funding window (accepted endpoints)."""
    by_symbol: dict[str, list[dict]] = {}
    for i, w in enumerate(windows, start=1):
        sym = w["symbol"]
        rows = by_symbol.setdefault(sym, [])
        row = _make_funding_row(w["window_end"], symbol=sym, row_index=i)
        rows.append(row)
    return by_symbol


def _create_csv_files(
    data_dir: Path,
    windows: list[dict[str, Any]],
) -> dict[str, Path]:
    """Create CSV files for all windows and return a mapping of symbol->path."""
    rows_by_symbol = _csv_rows_for_windows(windows)
    paths: dict[str, Path] = {}
    for sym, csv_rows in rows_by_symbol.items():
        csv_path = data_dir / f"{sym}_8h_funding.csv"
        _make_csv(csv_path, sym, csv_rows)
        paths[sym] = csv_path
    return paths


def _emit(
    db_path: Path,
    data_dir: Path,
    **overrides: Any,
) -> FullWindowEmissionResult:
    """Convenience wrapper around ``emit_full_window_funding_source_snapshot``."""
    return emit_full_window_funding_source_snapshot(
        db_path,
        data_dir=str(data_dir),
        qnty_git_commit="41bbc86246489c393c53c46349b8e8f5d5967522",
        **overrides,
    )


def _init_db(
    path: Path,
    *,
    lane_id: str = _LANE_ID,
    committed_batches: int = 2,
    funding_windows: list[dict[str, Any]] | None = None,
) -> Path:
    """Create a minimal lane DB for emit / verifier tests.

    Creates ``paper_config``, ``ledger_batches``, and optionally ``funding``
    tables with the given parameters. All batches use sequential ids starting
    at 1.
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
        for i in range(1, committed_batches + 1):
            conn.execute(
                "INSERT INTO ledger_batches (batch_id, committed_at, "
                "prior_watermark_bar_ts, new_watermark_bar_ts) "
                "VALUES (?, ?, ?, ?)",
                (
                    i,
                    f"2026-06-15T0{i}:00:00Z",
                    "2026-06-14T08:00:00Z",
                    f"2026-06-15T0{i}:00:00Z",
                ),
            )
        conn.execute(
            "CREATE TABLE funding ("
            "symbol TEXT, window_start TEXT, window_end TEXT, "
            "funding_amount REAL"
            ")"
        )
        if funding_windows:
            for fw in funding_windows:
                conn.execute(
                    "INSERT INTO funding (symbol, window_start, window_end) "
                    "VALUES (?, ?, ?)",
                    (fw["symbol"], fw["window_start"], fw["window_end"]),
                )
        conn.commit()
    finally:
        conn.close()
    return path


# ===================================================================
# Phase 1: Unit tests for emit helpers (tests 1-9)
# ===================================================================


class TestLaneIdFromConfig:
    """``_lane_id_from_config`` unit tests."""

    def test_lane_id_from_config_reads_lane(self, tmp_path: Path) -> None:
        """Create DB with ``lane_id`` column, assert it returns the lane."""
        db = tmp_path / "test.db"
        db.parent.mkdir(parents=True, exist_ok=True)
        conn = sqlite3.connect(str(db))
        conn.row_factory = sqlite3.Row
        try:
            conn.execute(
                "CREATE TABLE paper_config (id INTEGER PRIMARY KEY, lane_id TEXT)"
            )
            conn.execute(
                "INSERT INTO paper_config (id, lane_id) VALUES (1, ?)", (_LANE_ID,)
            )
            conn.commit()
            assert _lane_id_from_config(conn) == _LANE_ID
        finally:
            conn.close()

    def test_lane_id_from_config_defaults(self, tmp_path: Path) -> None:
        """Create DB without ``lane_id`` column, assert default."""
        db = tmp_path / "test.db"
        db.parent.mkdir(parents=True, exist_ok=True)
        conn = sqlite3.connect(str(db))
        conn.row_factory = sqlite3.Row
        try:
            conn.execute(
                "CREATE TABLE paper_config (id INTEGER PRIMARY KEY)"
            )
            conn.execute("INSERT INTO paper_config (id) VALUES (1)")
            conn.commit()
            assert _lane_id_from_config(conn) == "paper_pnl_v1"
        finally:
            conn.close()


class TestLatestCommittedBatch:
    """``_latest_committed_batch`` unit tests."""

    def test_latest_committed_batch_returns_correct(self, tmp_path: Path) -> None:
        """Insert 3 committed + 1 pending, assert latest batch returned."""
        db = tmp_path / "test.db"
        db.parent.mkdir(parents=True, exist_ok=True)
        conn = sqlite3.connect(str(db))
        conn.row_factory = sqlite3.Row
        try:
            conn.execute(
                "CREATE TABLE ledger_batches ("
                "batch_id INTEGER PRIMARY KEY, "
                "committed_at TEXT, "
                "prior_watermark_bar_ts TEXT, "
                "new_watermark_bar_ts TEXT"
                ")"
            )
            for i in range(1, 4):
                conn.execute(
                    "INSERT INTO ledger_batches (batch_id, committed_at, "
                    "prior_watermark_bar_ts, new_watermark_bar_ts) "
                    "VALUES (?, ?, ?, ?)",
                    (i, f"2026-06-15T0{i}:00:00Z", "2026-06-14T08:00:00Z",
                     f"2026-06-15T0{i}:00:00Z"),
                )
            # Pending batch (not committed)
            conn.execute(
                "INSERT INTO ledger_batches (batch_id, committed_at, "
                "prior_watermark_bar_ts, new_watermark_bar_ts) "
                "VALUES (?, NULL, ?, ?)",
                (4, "2026-06-14T08:00:00Z", "2026-06-15T04:00:00Z"),
            )
            conn.commit()
            batch = _latest_committed_batch(conn)
            assert batch is not None
            assert int(batch["batch_id"]) == 3
        finally:
            conn.close()

    def test_latest_committed_batch_returns_none_when_empty(
        self, tmp_path: Path,
    ) -> None:
        """No batches, assert None."""
        db = tmp_path / "test.db"
        db.parent.mkdir(parents=True, exist_ok=True)
        conn = sqlite3.connect(str(db))
        conn.row_factory = sqlite3.Row
        try:
            conn.execute(
                "CREATE TABLE ledger_batches ("
                "batch_id INTEGER PRIMARY KEY, "
                "committed_at TEXT, "
                "prior_watermark_bar_ts TEXT, "
                "new_watermark_bar_ts TEXT"
                ")"
            )
            conn.commit()
            assert _latest_committed_batch(conn) is None
        finally:
            conn.close()


class TestFullLedgerWindows:
    """``_full_ledger_windows`` unit tests."""

    def test_full_ledger_windows_returns_distinct(self, tmp_path: Path) -> None:
        """Insert funding rows across symbols/windows, assert distinct windows."""
        db = tmp_path / "test.db"
        db.parent.mkdir(parents=True, exist_ok=True)
        conn = sqlite3.connect(str(db))
        conn.row_factory = sqlite3.Row
        try:
            conn.execute(
                "CREATE TABLE funding ("
                "symbol TEXT, window_start TEXT, window_end TEXT"
                ")"
            )
            # Two symbols, two windows each
            for sym in (_SYMBOL, "ETH"):
                conn.execute(
                    "INSERT INTO funding (symbol, window_start, window_end) "
                    "VALUES (?, ?, ?)", (sym, _W1[0], _W1[1])
                )
                conn.execute(
                    "INSERT INTO funding (symbol, window_start, window_end) "
                    "VALUES (?, ?, ?)", (sym, _W2[0], _W2[1])
                )
            conn.commit()
            windows = _full_ledger_windows(conn)
            assert len(windows) == 4
            symbols = {w["symbol"] for w in windows}
            assert symbols == {_SYMBOL, "ETH"}
        finally:
            conn.close()

    def test_full_ledger_evaluation_window_span(self, tmp_path: Path) -> None:
        """Multiple windows with different start/end, assert MIN/MAX computed."""
        db = tmp_path / "test.db"
        db.parent.mkdir(parents=True, exist_ok=True)
        conn = sqlite3.connect(str(db))
        conn.row_factory = sqlite3.Row
        try:
            conn.execute(
                "CREATE TABLE funding ("
                "symbol TEXT, window_start TEXT, window_end TEXT"
                ")"
            )
            for w in (_W1, _W2, _W3):
                conn.execute(
                    "INSERT INTO funding (symbol, window_start, window_end) "
                    "VALUES (?, ?, ?)", (_SYMBOL, w[0], w[1])
                )
            conn.commit()
            ew = _full_ledger_evaluation_window(conn)
            assert ew == _FULL_LEDGER_WINDOW
        finally:
            conn.close()


class TestResolveSourceDir:
    """``_resolve_source_dir`` unit tests."""

    def test_resolve_source_dir_resolves_absolute(
        self, tmp_path: Path,
    ) -> None:
        """Pass an explicit ``data_dir``, assert resolved path is absolute.
        We pass an explicit Path to avoid importing ``_funding_loader``
        (which depends on unavailable pandas)."""
        data_dir = tmp_path / "data"
        data_dir.mkdir(parents=True)
        resolved = _resolve_source_dir(data_dir)
        assert resolved.is_absolute()
        assert str(resolved) == str(data_dir.resolve())


class TestSourceCsvPaths:
    """``_source_csv_paths`` unit tests."""

    def test_source_csv_paths_derives_paths(self, tmp_path: Path) -> None:
        """2 symbols, assert 2 paths under source_dir."""
        windows = [
            _window("SOL", _W1[0], _W1[1]),
            _window("BTC", _W2[0], _W2[1]),
        ]
        source_dir = tmp_path / "data"
        source_dir.mkdir(parents=True)
        paths = _source_csv_paths(windows, source_dir)
        assert len(paths) == 2
        assert paths[0].name == "BTC_8h_funding.csv"
        assert paths[1].name == "SOL_8h_funding.csv"
        assert all(p.parent == source_dir for p in paths)
        assert all(p.is_absolute() for p in paths)


class TestDbIdentityHash:
    """``_db_identity_hash`` unit tests."""

    def test_db_identity_hash_deterministic(self, tmp_path: Path) -> None:
        """Same inputs -> same hash; different inputs -> different hash."""
        db_path = tmp_path / "lane" / "paper_ledger.db"
        db_path.parent.mkdir(parents=True, exist_ok=True)
        ew = _FULL_LEDGER_WINDOW
        h1 = _db_identity_hash(
            db_path=db_path, lane_id=_LANE_ID,
            target_batch_id=2, evaluation_window=ew,
        )
        h2 = _db_identity_hash(
            db_path=db_path, lane_id=_LANE_ID,
            target_batch_id=2, evaluation_window=ew,
        )
        assert h1 == h2
        assert len(h1) == 64

        # Different batch id -> different hash
        h3 = _db_identity_hash(
            db_path=db_path, lane_id=_LANE_ID,
            target_batch_id=3, evaluation_window=ew,
        )
        assert h3 != h1


# ===================================================================
# Phase 2: Integration tests for ``emit_full_window_funding_source_snapshot()``
# (tests 10-19)
# ===================================================================


class TestEmitIntegration:
    """Integration tests for the full emit path."""

    def test_emit_creates_snapshot_file(
        self, tmp_path: Path,
    ) -> None:
        """Call emit, assert snapshot file exists at ``full_window_snapshot_path()``."""
        db = _init_db(
            tmp_path / "lane" / "paper_ledger.db",
            funding_windows=_default_funding_windows(),
        )
        data_dir = tmp_path / "data"
        _create_csv_files(data_dir, _default_funding_windows())
        result = _emit(db, data_dir)
        assert result.snapshot_path.is_file()
        expected = full_window_snapshot_path(db.parent, 2)
        assert result.snapshot_path == expected

    def test_emit_creates_bundle_file(
        self, tmp_path: Path,
    ) -> None:
        """Call emit, assert bundle file exists in ``funding_source_bundles/``."""
        db = _init_db(
            tmp_path / "lane" / "paper_ledger.db",
            funding_windows=_default_funding_windows(),
        )
        data_dir = tmp_path / "data"
        _create_csv_files(data_dir, _default_funding_windows())
        result = _emit(db, data_dir)
        assert result.bundle_path.is_file()
        assert result.bundle_path.parent.name == "funding_source_bundles"
        assert result.bundle_path.suffix == ".json"

    def test_emit_snapshot_has_full_window_scope(
        self, tmp_path: Path,
    ) -> None:
        """Read envelope, assert ``snapshot_scope == 'full_window'``."""
        db = _init_db(
            tmp_path / "lane" / "paper_ledger.db",
            funding_windows=_default_funding_windows(),
        )
        data_dir = tmp_path / "data"
        _create_csv_files(data_dir, _default_funding_windows())
        result = _emit(db, data_dir)
        payload = result.envelope.get("snapshot_payload", {})
        assert payload.get("snapshot_scope") == SNAPSHOT_SCOPE_FULL_WINDOW

    def test_emit_snapshot_has_absolute_resolved_dir(
        self, tmp_path: Path,
    ) -> None:
        """Read envelope, assert ``resolved_funding_source_dir`` is absolute."""
        db = _init_db(
            tmp_path / "lane" / "paper_ledger.db",
            funding_windows=_default_funding_windows(),
        )
        data_dir = tmp_path / "data"
        _create_csv_files(data_dir, _default_funding_windows())
        result = _emit(db, data_dir)
        assert Path(result.resolved_funding_source_dir).is_absolute()

    def test_emit_evaluation_window_covers_all_funding(
        self, tmp_path: Path,
    ) -> None:
        """Assert ``evaluation_window`` equals MIN(start)-MAX(end) from funding."""
        db = _init_db(
            tmp_path / "lane" / "paper_ledger.db",
            funding_windows=_default_funding_windows(),
        )
        data_dir = tmp_path / "data"
        _create_csv_files(data_dir, _default_funding_windows())
        result = _emit(db, data_dir)
        assert result.evaluation_window == _FULL_LEDGER_WINDOW

    def test_emit_bundle_is_valid(
        self, tmp_path: Path,
    ) -> None:
        """Read bundle, assert ``snapshot_scope`` carried through,
        ``bundle_window_reasons`` empty."""
        db = _init_db(
            tmp_path / "lane" / "paper_ledger.db",
            funding_windows=_default_funding_windows(),
        )
        data_dir = tmp_path / "data"
        _create_csv_files(data_dir, _default_funding_windows())
        result = _emit(db, data_dir)
        bundle_data = json.loads(result.bundle_path.read_text(encoding="utf-8"))
        bp = bundle_data["bundle_payload"]
        assert bp["snapshot_scope"] == SNAPSHOT_SCOPE_FULL_WINDOW
        assert bundle_window_reasons(bp) == []

    def test_emit_raises_no_committed_batch(
        self, tmp_path: Path,
    ) -> None:
        """Empty DB (no ledger_batches table at all) -> error."""
        db = tmp_path / "lane" / "paper_ledger.db"
        db.parent.mkdir(parents=True)
        # Create DB with only paper_config
        conn = sqlite3.connect(str(db))
        conn.row_factory = sqlite3.Row
        try:
            conn.execute(
                "CREATE TABLE paper_config (id INTEGER PRIMARY KEY, lane_id TEXT)"
            )
            conn.execute(
                "INSERT INTO paper_config (id, lane_id) VALUES (1, ?)", (_LANE_ID,)
            )
            # Create an empty ledger_batches table so the query doesn't crash
            conn.execute(
                "CREATE TABLE ledger_batches ("
                "batch_id INTEGER PRIMARY KEY, "
                "committed_at TEXT, "
                "prior_watermark_bar_ts TEXT, "
                "new_watermark_bar_ts TEXT"
                ")"
            )
            conn.commit()
        finally:
            conn.close()
        data_dir = tmp_path / "data"
        with pytest.raises(FundingSourceSnapshotEmissionError, match="committed ledger batch"):
            _emit(db, data_dir)

    def test_emit_raises_no_funding_rows(
        self, tmp_path: Path,
    ) -> None:
        """DB with committed batch but no funding rows -> error."""
        db = _init_db(
            tmp_path / "lane" / "paper_ledger.db",
            committed_batches=1,
            funding_windows=None,
        )
        data_dir = tmp_path / "data"
        with pytest.raises(
            FundingSourceSnapshotEmissionError,
            match="funding row",
        ):
            _emit(db, data_dir)

    def test_emit_raises_missing_source_csv(
        self, tmp_path: Path,
    ) -> None:
        """DB with funding rows but CSV file does not exist -> error."""
        db = _init_db(
            tmp_path / "lane" / "paper_ledger.db",
            funding_windows=_default_funding_windows(),
        )
        data_dir = tmp_path / "data"
        # Don't create any CSV files - the emit function will fail when
        # _read_funding_source_csv_rows tries to open the non-existent paths.
        with pytest.raises((FundingSourceSnapshotEmissionError, OSError, FileNotFoundError)):
            _emit(db, data_dir)

    def test_emit_raises_incomplete_coverage(
        self, tmp_path: Path,
    ) -> None:
        """DB with funding rows, CSV with partial data -> coverage failure."""
        db = _init_db(
            tmp_path / "lane" / "paper_ledger.db",
            funding_windows=_default_funding_windows(),
        )
        data_dir = tmp_path / "data"
        # Create CSV with rows that don't match the required windows
        # (fundingTime_ms values far outside the window range)
        data_dir.mkdir(parents=True, exist_ok=True)
        csv_path = data_dir / f"{_SYMBOL}_8h_funding.csv"
        _make_csv(csv_path, _SYMBOL, [
            {"fundingTime_ms": _ms_at("2026-01-01T00:00:00Z"), "fundingRate": "0.0001"},
        ])
        with pytest.raises(FundingSourceSnapshotEmissionError, match="coverage is not complete"):
            _emit(db, data_dir)


# ===================================================================
# Phase 3: Verifier integration tests (tests 20-27)
# ===================================================================


class TestVerifierIntegration:
    """Verifier integration tests for the full-window sidecar."""

    def test_verifier_selects_full_window_sidecar_after_emit(
        self, tmp_path: Path,
    ) -> None:
        """Emit, then call ``_resolve_full_window_snapshot_for_gate()``,
        assert envelope returned."""
        db = _init_db(
            tmp_path / "lane" / "paper_ledger.db",
            funding_windows=_default_funding_windows(),
        )
        data_dir = tmp_path / "data"
        _create_csv_files(data_dir, _default_funding_windows())
        result = _emit(db, data_dir)

        cfg = {"lane_id": _LANE_ID}
        envelope, sel_path, reasons = _resolve_full_window_snapshot_for_gate(
            db, cfg, result.target_batch_id,
        )
        assert envelope is not None, f"expected envelope, got reasons={reasons}"
        assert sel_path is not None
        assert reasons == []

    def test_full_ledger_clean_carry_passes_with_sidecar(
        self, tmp_path: Path,
    ) -> None:
        """Emit, then verify ``clean_mode_decision_from_snapshot_v1`` passes
        for the resolved full-window snapshot with the expected parameters.
        This exercises the verifier's sidecar selection + clean-carry gate
        without requiring a full production DB schema for the resum check."""
        db = _init_db(
            tmp_path / "lane" / "paper_ledger.db",
            funding_windows=_default_funding_windows(),
        )
        data_dir = tmp_path / "data"
        _create_csv_files(data_dir, _default_funding_windows())
        result = _emit(db, data_dir)

        cfg = {"lane_id": _LANE_ID}
        envelope, sel_path, reasons = _resolve_full_window_snapshot_for_gate(
            db, cfg, result.target_batch_id,
        )
        assert envelope is not None, f"expected envelope, got reasons={reasons}"

        # Extract the digests from the snapshot payload to pass to the
        # clean-mode decision function.
        payload = envelope.get("snapshot_payload", {})
        source_files = payload.get("source_files", [])
        file_sha_by_path: dict[str, str] = {
            str(item["path"]): str(item["full_file_sha256"])
            for item in source_files
        }
        row_sha_by_path: dict[str, str] = {
            str(item["path"]): str(item["canonical_row_subset_sha256"])
            for item in source_files
        }

        from quantbot.paper.funding_source_snapshot import (
            clean_mode_decision_from_snapshot_v1,
        )

        decision = clean_mode_decision_from_snapshot_v1(
            envelope,
            expected_evaluation_window=result.evaluation_window,
            expected_lane_id=_LANE_ID,
            expected_db_identity_hash_before=payload.get("db_identity_hash_before"),
            expected_source_file_sha256_by_path=file_sha_by_path,
            expected_row_subset_sha256_by_path=row_sha_by_path,
            expected_snapshot_scope=SNAPSHOT_SCOPE_FULL_WINDOW,
        )
        assert decision.get("clean_net_of_carry_allowed") is True, (
            f"expected clean_net_of_carry, got decision={decision}"
        )
        assert decision.get("reason_codes") == [], (
            f"unexpected reasons: {decision.get('reason_codes')}"
        )

    def test_multi_batch_ledger_without_sidecar_refuses(
        self, tmp_path: Path,
    ) -> None:
        """Multi-batch DB without emit, verify, assert
        ``funding_source_full_window_snapshot_missing``."""
        db = _init_db(
            tmp_path / "lane" / "paper_ledger.db",
            funding_windows=_default_funding_windows(),
        )
        cfg = {"lane_id": _LANE_ID}
        # No emit — no full-window sidecar file.
        envelope, sel_path, reasons = _resolve_full_window_snapshot_for_gate(
            db, cfg, target_batch_id=2,
        )
        assert envelope is None
        assert "funding_source_full_window_snapshot_missing" in reasons

    def test_single_batch_ledger_no_full_window_scope(self, tmp_path: Path) -> None:
        """Single-batch DB, assert ``_full_ledger_requires_full_window_scope()``
        returns False."""
        db = _init_db(
            tmp_path / "lane" / "paper_ledger.db",
            committed_batches=1,
            funding_windows=None,
        )
        conn = connect_readonly(db)
        try:
            assert _full_ledger_requires_full_window_scope(conn) is False
        finally:
            conn.close()

    def test_verifier_refuses_wrong_lane_binding(
        self, tmp_path: Path,
    ) -> None:
        """Emit with lane X, verify with lane Y, assert
        ``funding_source_snapshot_db_mismatch``."""
        db = _init_db(
            tmp_path / "lane" / "paper_ledger.db",
            lane_id=_LANE_ID,
            funding_windows=_default_funding_windows(),
        )
        data_dir = tmp_path / "data"
        _create_csv_files(data_dir, _default_funding_windows())
        result = _emit(db, data_dir)

        # Verify with a different lane id
        cfg = {"lane_id": _OTHER_LANE}
        envelope, sel_path, reasons = _resolve_full_window_snapshot_for_gate(
            db, cfg, result.target_batch_id,
        )
        assert envelope is None
        assert "funding_source_snapshot_db_mismatch" in reasons

    def test_verifier_refuses_tampered_snapshot(
        self, tmp_path: Path,
    ) -> None:
        """Emit, tamper snapshot file, verify refuses."""
        db = _init_db(
            tmp_path / "lane" / "paper_ledger.db",
            funding_windows=_default_funding_windows(),
        )
        data_dir = tmp_path / "data"
        _create_csv_files(data_dir, _default_funding_windows())
        result = _emit(db, data_dir)

        # Tamper the snapshot by corrupting a critical payload field
        raw = json.loads(result.snapshot_path.read_text(encoding="utf-8"))
        payload = raw.get("snapshot_payload", {})
        prov = payload.get("provenance", {})
        prov["source_path_resolution"] = {}
        raw["snapshot_payload"]["provenance"] = prov
        result.snapshot_path.write_text(
            json.dumps(raw, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )

        cfg = {"lane_id": _LANE_ID}
        envelope, sel_path, reasons = _resolve_full_window_snapshot_for_gate(
            db, cfg, result.target_batch_id,
        )
        assert envelope is None
        # Tampered snapshot fails envelope validation -> some validation reason code
        assert len(reasons) > 0

    def test_verifier_refuses_tampered_bundle(
        self, tmp_path: Path,
    ) -> None:
        """Emit, tamper bundle file, verify refuses in bundle mode.

        We test this via ``resolve_funding_source_bundle`` with a tampered
        bundle file so the bundle resolution fails.
        """
        db = _init_db(
            tmp_path / "lane" / "paper_ledger.db",
            funding_windows=_default_funding_windows(),
        )
        data_dir = tmp_path / "data"
        _create_csv_files(data_dir, _default_funding_windows())
        result = _emit(db, data_dir)

        # Tamper the bundle by changing a canonical row value
        raw = json.loads(result.bundle_path.read_text(encoding="utf-8"))
        bp = raw.get("bundle_payload", {})
        rows = bp.get("canonical_rows", [])
        if rows:
            rows[0]["funding_rate"] = "0.9999"
        raw["bundle_payload"]["canonical_rows"] = rows
        result.bundle_path.write_text(
            json.dumps(raw, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )

        # In bundle mode the verifier resolves the bundle from disk.
        # A tampered bundle fails its self-integrity hash recompute.
        bundle_dir = db.parent / "funding_source_bundles"
        bundle_payload, reasons, identity = resolve_funding_source_bundle(
            bundle_dir,
            expected_snapshot_bundle_sha256=result.source_bundle_sha256,
        )
        # Canonical rows changed -> hash mismatch (bundle_payload is still
        # returned by resolve_funding_source_bundle; the failure is in reasons).
        assert bundle_payload is not None
        assert "funding_source_bundle_hash_mismatch" in reasons, (
            f"expected hash_mismatch, got reasons={reasons}"
        )

    def test_bundle_mode_works_with_full_window_bundle(
        self, tmp_path: Path,
    ) -> None:
        """Emit, resolve bundle via ``resolve_funding_source_bundle``, passes."""
        db = _init_db(
            tmp_path / "lane" / "paper_ledger.db",
            funding_windows=_default_funding_windows(),
        )
        data_dir = tmp_path / "data"
        _create_csv_files(data_dir, _default_funding_windows())
        result = _emit(db, data_dir)

        bundle_dir = db.parent / "funding_source_bundles"
        bundle_payload, reasons, identity = resolve_funding_source_bundle(
            bundle_dir,
            expected_snapshot_bundle_sha256=result.source_bundle_sha256,
        )
        assert bundle_payload is not None, f"expected bundle, got reasons={reasons}"
        assert reasons == [], f"unexpected reasons: {reasons}"
        assert bundle_payload.get("snapshot_scope") == SNAPSHOT_SCOPE_FULL_WINDOW
        assert identity.get("source_resolution_mode") == "bundle"


# ===================================================================
# Phase 3b: Additional verifier edge cases
# ===================================================================


class TestVerifierEdgeCases:
    """Additional verifier edge cases for full-window sidecar."""

    def test_verifier_refuses_tampered_snapshot_corrupt_json(
        self, tmp_path: Path,
    ) -> None:
        """Emit, corrupt snapshot JSON, verify returns payload_invalid."""
        db = _init_db(
            tmp_path / "lane" / "paper_ledger.db",
            funding_windows=_default_funding_windows(),
        )
        data_dir = tmp_path / "data"
        _create_csv_files(data_dir, _default_funding_windows())
        result = _emit(db, data_dir)

        # Replace with garbage
        result.snapshot_path.write_text("{{{garbage}}}", encoding="utf-8")

        cfg = {"lane_id": _LANE_ID}
        envelope, sel_path, reasons = _resolve_full_window_snapshot_for_gate(
            db, cfg, result.target_batch_id,
        )
        assert envelope is None
        # Corrupt JSON -> envelope validation fails
        assert len(reasons) >= 1


# ===================================================================
# Phase 4: Regression tests (tests 28-33)
# ===================================================================


class TestRegression:
    """Regression tests that import and run existing test module key tests
    to confirm nothing broke."""

    # --- Test 28: Existing batch snapshot emission test ---

    def test_regression_batch_snapshot_emission(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """Run the core batch snapshot emission happy path from the existing
        ``test_paper_sqlite_writer_source_snapshot_emission`` module."""
        from tests.test_paper_sqlite_writer_source_snapshot_emission import (
            NOW,
            _funding_times_with_endpoint_offset,
            _run_writer,
            _load_single_snapshot,
            test_happy_path_emits_committed_snapshot_sidecar_with_valid_db_reference,
        )
        monkeypatch.setattr("quantbot.paper.sqlite_writer._now", lambda: NOW)
        test_happy_path_emits_committed_snapshot_sidecar_with_valid_db_reference(
            tmp_path, monkeypatch,
        )

    # --- Test 29: Existing bundle mode semantics test ---

    def test_regression_bundle_mode_semantics(self) -> None:
        """Run the bundle identity hash test from the existing
        ``test_full_window_funding_source_snapshot_semantics`` module."""
        from tests.test_full_window_funding_source_snapshot_semantics import (
            test_bundle_identity_hash_ignores_new_fields,
        )
        test_bundle_identity_hash_ignores_new_fields()

    # --- Test 30: Existing full-window semantics test ---

    def test_regression_full_window_semantics(self) -> None:
        """Run the full-window snapshot validates test from the existing
        ``test_full_window_funding_source_snapshot_semantics`` module."""
        from tests.test_full_window_funding_source_snapshot_semantics import (
            test_full_window_snapshot_validates_with_absolute_resolved_dir,
        )
        test_full_window_snapshot_validates_with_absolute_resolved_dir()

    # --- Test 31: Existing verifier batch-scoped clean-carry test ---

    def test_regression_verifier_batch_scoped_clean_carry(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """Run the batch-scoped clean-carry test from the existing
        ``test_paper_sqlite_verify_batch_scoped_clean_carry`` module."""
        from tests.test_paper_sqlite_verify_batch_scoped_clean_carry import (
            test_batch_scope_accepts_exact_window,
        )
        test_batch_scope_accepts_exact_window(tmp_path)

    # --- Test 32: Existing source path resolution test ---

    def test_regression_source_path_resolution(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """Run the explicit db_path controls snapshot directory test from the
        existing batch snapshot emission module."""
        from tests.test_paper_sqlite_writer_source_snapshot_emission import (
            NOW,
            _funding_times_with_endpoint_offset,
            _run_writer,
            test_explicit_db_path_controls_snapshot_directory_not_output_env,
        )
        monkeypatch.setattr("quantbot.paper.sqlite_writer._now", lambda: NOW)
        test_explicit_db_path_controls_snapshot_directory_not_output_env(
            tmp_path, monkeypatch,
        )

    # --- Test 33: Existing read-only CLI contract test ---

    def test_regression_readonly_cli_contract(
        self, tmp_path: Path,
    ) -> None:
        """Re-run the verifier's read-only CLI contract by calling the core
        ``verify_database`` function directly with a minimal DB that has only
        the required tables (empty, pre-start state). The verifier must return
        PRE_START and never write to the DB or the filesystem.
        """
        from tests.test_paper_sqlite_verify import (
            _init_db,
            TestPreStart,
            verify_database,
            STATUS_PRE_START,
        )
        db_path = _init_db(tmp_path)
        result = verify_database(db_path)
        assert result.status == STATUS_PRE_START
        assert result.failures == []