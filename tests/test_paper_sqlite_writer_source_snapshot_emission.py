"""SQLite writer funding source snapshot sidecar emission tests.

All tests use tmp SQLite DBs, tmp forward observations, and tmp OHLCV/funding
CSVs. They never touch /srv, production DBs, shadow DBs, or forward_obs.

The sidecar emitted in this PR is deliberately pending-only evidence. It is not
clean-carry proof: without a committed batch/evaluation identity in DB schema v1,
future verifier clean-mode must refuse unreferenced or orphaned snapshots.
"""

from __future__ import annotations

import csv
import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from quantbot.paper.config import build_config, write_config_once
from quantbot.paper.db import connect_readonly, initialize_database
from quantbot.paper.funding_source_snapshot import (
    clean_mode_decision_from_snapshot_v1,
    validate_funding_source_snapshot_envelope_v1,
)
from quantbot.paper.sqlite_writer import (
    STATUS_ABORTED,
    STATUS_OK,
    run_sqlite_accounting,
)

SYMBOL = "BTCUSDT"
GRID_START = datetime(2026, 6, 5, 0, 0, 0, tzinfo=timezone.utc)
GRID_TIMES = [GRID_START + timedelta(hours=8 * i) for i in range(6)]
TS = [dt.strftime("%Y-%m-%dT%H:%M:%S") for dt in GRID_TIMES]
FWD_HELD = TS[0]
NOW = GRID_TIMES[-1] + timedelta(minutes=5)
REQUIRED_FUNDING_ENDPOINTS = TS[2:]


@pytest.fixture(autouse=True)
def _freeze_writer_now(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("quantbot.paper.sqlite_writer._now", lambda: NOW)


def _ms_at(ts: str, *, offset_ms: int = 0) -> int:
    dt = datetime.fromisoformat(ts).replace(tzinfo=timezone.utc)
    return int(dt.timestamp() * 1000) + offset_ms


def _config() -> dict:
    return build_config(
        forward_start_ts=FWD_HELD,
        initial_equity_usd=10000.0,
        notional_usd=1000.0,
        fee_bps=5.0,
        slippage_bps=5.0,
        max_bar_staleness_hours=72.0,
    )


def _init_test_db(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    *,
    db_path: Path | None = None,
    config_dir: Path | None = None,
) -> Path:
    output_dir = config_dir or (tmp_path / "paper")
    output_dir.mkdir(parents=True, exist_ok=True)
    monkeypatch.setenv("QNTY_PAPER_OUTPUT_DIR", str(output_dir))

    config = _config()
    write_config_once(config, output_dir=output_dir)
    final_db_path = db_path or (output_dir / "paper_ledger.db")
    initialize_database(final_db_path, config)
    return final_db_path


def _write_observation_log(tmp_path: Path) -> Path:
    obs_dir = tmp_path / "forward_obs_v1"
    obs_dir.mkdir(parents=True, exist_ok=True)
    per_bar_obs = [
        {
            "timestamp": ts,
            "bar_index": i,
            "active_symbols": [SYMBOL],
            "portfolio_heat": 0.0,
            "heat_cap_triggered": False,
            "weighted_return": 0.0,
        }
        for i, ts in enumerate(TS)
    ]
    (obs_dir / "observation_log.json").write_text(
        json.dumps({"per_bar_obs": per_bar_obs}, indent=2),
        encoding="utf-8",
    )
    return obs_dir


def _write_ohlcv_csv(data_dir: Path) -> None:
    data_dir.mkdir(parents=True, exist_ok=True)
    csv_path = data_dir / f"{SYMBOL}_8h_ohlcv.csv"
    with csv_path.open("w", newline="", encoding="utf-8") as fh:
        writer = csv.writer(fh)
        writer.writerow(["timestamp", "open", "high", "low", "close", "volume"])
        for i, ts in enumerate(TS):
            open_price = 100.0 + (i * 10.0)
            close_price = open_price + 5.0
            writer.writerow(
                [
                    ts,
                    open_price,
                    max(open_price, close_price),
                    min(open_price, close_price),
                    close_price,
                    1.0,
                ]
            )


def _write_funding_csv(data_dir: Path, funding_times_ms: list[int]) -> None:
    data_dir.mkdir(parents=True, exist_ok=True)
    csv_path = data_dir / f"{SYMBOL}_8h_funding.csv"
    with csv_path.open("w", newline="", encoding="utf-8") as fh:
        writer = csv.writer(fh)
        writer.writerow(["fundingTime", "fundingRate", "markPrice"])
        for ms in funding_times_ms:
            writer.writerow([ms, "0.0001", "100.0"])


def _funding_times_with_endpoint_offset(offset_ms: int = 5) -> list[int]:
    return [_ms_at(ts, offset_ms=offset_ms) for ts in REQUIRED_FUNDING_ENDPOINTS]


def _funding_times_with_duplicate_canonical_endpoints() -> list[int]:
    rows: list[int] = []
    for ts in REQUIRED_FUNDING_ENDPOINTS:
        rows.append(_ms_at(ts))
        rows.append(_ms_at(ts, offset_ms=5))
    return rows


def _run_writer(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    *,
    funding_times_ms: list[int] | None = None,
    db_path: Path | None = None,
    config_dir: Path | None = None,
) -> tuple[int, str, Path]:
    final_db_path = _init_test_db(
        tmp_path,
        monkeypatch,
        db_path=db_path,
        config_dir=config_dir,
    )
    obs_dir = _write_observation_log(tmp_path)
    data_dir = tmp_path / "data"
    _write_ohlcv_csv(data_dir)
    if funding_times_ms is not None:
        _write_funding_csv(data_dir, funding_times_ms)

    status, msg = run_sqlite_accounting(
        db_path=final_db_path,
        forward_obs_dir=obs_dir,
        data_dir=data_dir,
    )
    return status, msg, final_db_path


def _snapshot_dir(db_path: Path) -> Path:
    return db_path.parent / "funding_source_snapshots"


def _snapshot_files(db_path: Path) -> list[Path]:
    path = _snapshot_dir(db_path)
    if not path.exists():
        return []
    return sorted(path.glob("funding_source_snapshot_v1_*.json"))


def _load_single_snapshot(db_path: Path) -> dict:
    files = _snapshot_files(db_path)
    assert len(files) == 1, f"expected exactly one snapshot, got {files}"
    return json.loads(files[0].read_text(encoding="utf-8"))


def _assert_no_durable_mutation(db_path: Path) -> None:
    conn = connect_readonly(db_path)
    try:
        for table in (
            "ledger_batches",
            "ledger_events",
            "signal_snapshots",
            "funding",
            "fills",
            "trades",
            "position_snapshots",
            "equity_snapshots",
            "open_positions",
        ):
            count = conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
            assert count == 0, f"{table} must stay empty after abort, got {count}"

        state = conn.execute(
            """
            SELECT watermark_bar_ts, realized_gross, fees_cum, funding_cum
            FROM ledger_state
            WHERE id = 1
            """
        ).fetchone()
        assert state["watermark_bar_ts"] is None
        assert state["realized_gross"] == 0.0
        assert state["fees_cum"] == 0.0
        assert state["funding_cum"] == 0.0
    finally:
        conn.close()


def test_happy_path_emits_pending_snapshot_sidecar_with_valid_envelope(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    status, msg, db_path = _run_writer(
        tmp_path,
        monkeypatch,
        funding_times_ms=_funding_times_with_endpoint_offset(),
    )

    assert status == STATUS_OK, f"expected OK, got {status}: {msg}"
    envelope = _load_single_snapshot(db_path)
    assert validate_funding_source_snapshot_envelope_v1(envelope) == []

    payload = envelope["snapshot_payload"]
    snapshot_file = _snapshot_files(db_path)[0]
    assert payload["source_bundle_sha256"] in snapshot_file.name
    assert payload["write_state"] == "pending"
    assert payload["coverage_decision"] == "complete"
    assert payload["reason_codes"] == []
    assert payload["lane"]["lane_id"] == "paper_pnl_v1"
    assert payload["lane"]["output_dir"] == str(db_path.parent)
    assert payload["evaluation_window"] == {
        "start": "2026-06-05T08:00:00Z",
        "end": "2026-06-06T16:00:00Z",
    }
    assert payload["normalization_spec_version"] == (
        "FUNDING_TIMESTAMP_NORMALIZATION_SPEC_V2"
    )
    assert payload["symbols_covered"] == [SYMBOL]
    assert len(payload["required_funding_windows"]) == len(REQUIRED_FUNDING_ENDPOINTS)
    assert payload["source_files"][0]["path"] == str(
        tmp_path / "data" / f"{SYMBOL}_8h_funding.csv"
    )
    assert {
        "writer_or_verifier_command",
        "qnty_git_commit",
        "normalization_spec_version",
        "generated_at_utc",
    } <= set(payload["provenance"]["activity"])

    metadata = payload["snapshot_metadata"]
    assert metadata["db_path_reference"] == str(db_path)
    assert metadata["batch_start_watermark"] is None
    assert metadata["batch_end_watermark"] == TS[-1]
    assert metadata["pending_batch_id"].startswith("pending-")
    assert metadata["ledger_batch_id"] is None

    clean_decision = clean_mode_decision_from_snapshot_v1(envelope)
    assert clean_decision["clean_net_of_carry_allowed"] is False
    assert clean_decision["reason_codes"] == [
        "funding_source_snapshot_unreferenced_or_orphaned"
    ]


def test_explicit_db_path_controls_snapshot_directory_not_output_env(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    explicit_db_path = tmp_path / "manual-db-root" / "manual_paper_ledger.db"
    env_output_dir = tmp_path / "env-output-dir"

    status, msg, db_path = _run_writer(
        tmp_path,
        monkeypatch,
        funding_times_ms=_funding_times_with_endpoint_offset(),
        db_path=explicit_db_path,
        config_dir=env_output_dir,
    )

    assert status == STATUS_OK, f"expected OK, got {status}: {msg}"
    assert db_path == explicit_db_path
    assert len(_snapshot_files(explicit_db_path)) == 1
    assert not (env_output_dir / "funding_source_snapshots").exists()


def test_snapshot_builder_failure_aborts_before_durable_db_mutation(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def _raise(*args, **kwargs):
        raise RuntimeError("forced builder failure")

    monkeypatch.setattr(
        "quantbot.paper.sqlite_writer.build_funding_source_snapshot_payload_v1",
        _raise,
    )

    status, msg, db_path = _run_writer(
        tmp_path,
        monkeypatch,
        funding_times_ms=_funding_times_with_endpoint_offset(),
    )

    assert status == STATUS_ABORTED, f"expected ABORTED, got {status}: {msg}"
    assert "FUNDING_SOURCE_SNAPSHOT_EMISSION_FAILED" in msg, msg
    assert "forced builder failure" in msg, msg
    _assert_no_durable_mutation(db_path)
    assert _snapshot_files(db_path) == []


def test_atomic_snapshot_rename_failure_leaves_db_and_final_json_unchanged(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def _raise_replace(src, dst):
        raise OSError("forced rename failure")

    monkeypatch.setattr("quantbot.paper.sqlite_writer.os.replace", _raise_replace)

    status, msg, db_path = _run_writer(
        tmp_path,
        monkeypatch,
        funding_times_ms=_funding_times_with_endpoint_offset(),
    )

    assert status == STATUS_ABORTED, f"expected ABORTED, got {status}: {msg}"
    assert "FUNDING_SOURCE_SNAPSHOT_EMISSION_FAILED" in msg, msg
    assert "forced rename failure" in msg, msg
    _assert_no_durable_mutation(db_path)
    assert _snapshot_files(db_path) == []
    assert list(_snapshot_dir(db_path).glob("*.tmp")) == []


@pytest.mark.parametrize(
    ("case_name", "funding_times_ms", "expected_msg"),
    [
        ("missing", None, "FUNDING_COVERAGE_MISSING"),
        (
            "outside_tolerance",
            _funding_times_with_endpoint_offset(1000),
            "FUNDING_COVERAGE_MISSING",
        ),
        (
            "duplicate_endpoint",
            _funding_times_with_duplicate_canonical_endpoints(),
            "duplicate_canonical_endpoint",
        ),
    ],
)
def test_no_snapshot_emitted_for_aborted_funding_coverage_runs(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    case_name: str,
    funding_times_ms: list[int] | None,
    expected_msg: str,
) -> None:
    status, msg, db_path = _run_writer(
        tmp_path,
        monkeypatch,
        funding_times_ms=funding_times_ms,
    )

    assert status == STATUS_ABORTED, (
        f"{case_name}: expected ABORTED, got {status}: {msg}"
    )
    assert expected_msg in msg, msg
    _assert_no_durable_mutation(db_path)
    assert _snapshot_files(db_path) == []
