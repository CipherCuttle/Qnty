"""Offline tests for the bounded BTCUSDT 1h acquisition helper."""

import hashlib
import importlib.util
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

import pytest


REPO_ROOT = Path(__file__).resolve().parents[1]
SCRIPT_PATH = REPO_ROOT / "scripts" / "fetch_first_statistic_btcusdt_1h.py"


def _load_module():
    spec = importlib.util.spec_from_file_location("bounded_btcusdt_1h", SCRIPT_PATH)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


@pytest.fixture
def helper():
    return _load_module()


class FakeResponse:
    def __init__(self, payload):
        self.payload = payload

    def raise_for_status(self):
        return None

    def json(self):
        return self.payload


def _kline(helper, open_time_ms, *, close_time_ms=None):
    return [
        open_time_ms,
        "100.0",
        "101.0",
        "99.0",
        "100.5",
        "12.0",
        close_time_ms if close_time_ms is not None else open_time_ms + helper.HOUR_MS - 1,
        "0",
        "0",
        "0",
        "0",
        "0",
    ]


def _small_window(monkeypatch, helper, count=3):
    first = 1_704_067_200_000  # 2024-01-01T00:00:00Z
    last = first + (count - 1) * helper.HOUR_MS
    monkeypatch.setattr(helper, "FIRST_OPEN_TIME_MS", first)
    monkeypatch.setattr(helper, "LAST_OPEN_TIME_MS", last)
    monkeypatch.setattr(helper, "LAST_CLOSE_BOUNDARY_MS", last + helper.HOUR_MS)
    return first, last


def test_frozen_window_constants_match_protocol_contract(helper):
    assert helper._utc_iso(helper.FIRST_OPEN_TIME_MS) == "2021-07-01T00:00:00Z"
    assert helper._utc_iso(helper.LAST_OPEN_TIME_MS) == "2026-04-23T00:00:00Z"
    assert helper._utc_iso(helper.LAST_CLOSE_BOUNDARY_MS) == "2026-04-23T01:00:00Z"
    assert helper.LAST_CLOSE_BOUNDARY_MS == helper.LAST_OPEN_TIME_MS + helper.HOUR_MS


def test_paginates_with_frozen_params_and_writes_close_boundaries(helper, monkeypatch, tmp_path):
    first, last = _small_window(monkeypatch, helper, count=3)
    pages = [[_kline(helper, first), _kline(helper, first + helper.HOUR_MS)], [_kline(helper, last)]]
    calls = []

    def fake_get(url, *, params, timeout):
        calls.append((url, params, timeout))
        return FakeResponse(pages.pop(0))

    fixed_now = lambda: datetime(2026, 7, 16, tzinfo=timezone.utc)
    output, receipt_path = helper.download(tmp_path / "BTCUSDT_1h_ohlcv.csv", http_get=fake_get, now=fixed_now)

    assert [call[1]["startTime"] for call in calls] == [first, first + 2 * helper.HOUR_MS]
    assert all(call[0] == helper.ENDPOINT and call[1]["symbol"] == "BTCUSDT" for call in calls)
    assert all(call[1]["interval"] == "1h" and call[1]["endTime"] == last + helper.HOUR_MS for call in calls)
    rows = output.read_text().splitlines()
    assert rows[1].startswith("2024-01-01T01:00:00Z,")
    assert "2024-01-01T00:00:00Z," not in rows[1]
    receipt = json.loads(receipt_path.read_text())
    assert receipt["timestamp_convention"] == helper.TIMESTAMP_CONVENTION
    assert receipt["first_close_boundary_utc"] == "2024-01-01T01:00:00Z"
    assert receipt["last_close_boundary_utc"] == "2024-01-01T03:00:00Z"


def test_rejects_page_boundary_duplicate(helper, monkeypatch):
    first, _ = _small_window(monkeypatch, helper, count=3)
    pages = [[_kline(helper, first), _kline(helper, first + helper.HOUR_MS)], [_kline(helper, first + helper.HOUR_MS)]]
    with pytest.raises(helper.AcquisitionError, match="page boundary|duplicate"):
        helper._fetch_klines(lambda *args, **kwargs: FakeResponse(pages.pop(0)))


@pytest.mark.parametrize(
    ("rows", "message"),
    [
        (lambda h, f: [_kline(h, f), _kline(h, f + 2 * h.HOUR_MS), _kline(h, f + 3 * h.HOUR_MS)], "missing hour"),
        (lambda h, f: [_kline(h, f), _kline(h, f), _kline(h, f + h.HOUR_MS)], "duplicate|non-monotonic"),
        (lambda h, f: [_kline(h, f), ["bad"], _kline(h, f + 2 * h.HOUR_MS)], "malformed kline"),
    ],
)
def test_rejects_malformed_or_non_hourly_pages(helper, monkeypatch, rows, message):
    first, _ = _small_window(monkeypatch, helper, count=3)
    with pytest.raises(helper.AcquisitionError, match=message):
        helper._fetch_klines(lambda *args, **kwargs: FakeResponse(rows(helper, first)))


def test_rejects_wrong_close_time_invariant(helper, monkeypatch):
    first, last = _small_window(monkeypatch, helper, count=3)
    rows = [_kline(helper, first), _kline(helper, first + helper.HOUR_MS, close_time_ms=first + helper.HOUR_MS), _kline(helper, last)]
    with pytest.raises(helper.AcquisitionError, match="closeTime invariant"):
        helper._fetch_klines(lambda *args, **kwargs: FakeResponse(rows))


def test_rejects_raw_open_time_timestamp_semantics(helper, monkeypatch):
    first, last = _small_window(monkeypatch, helper, count=2)
    valid = [helper._normalize_kline(_kline(helper, first)), helper._normalize_kline(_kline(helper, last))]
    invalid = [valid[0], helper.Kline(**{**valid[1].__dict__, "timestamp_ms": last})]
    with pytest.raises(helper.AcquisitionError, match="raw openTime timestamp semantics"):
        helper._validate_klines(invalid)


def test_rejects_partial_frozen_bounds(helper, monkeypatch):
    first, _ = _small_window(monkeypatch, helper, count=3)
    with pytest.raises(helper.AcquisitionError, match="partial coverage"):
        helper._fetch_klines(lambda *args, **kwargs: FakeResponse([_kline(helper, first), _kline(helper, first + helper.HOUR_MS)]))


def test_non_overwrite_rejects_before_network(helper, monkeypatch, tmp_path):
    first, _ = _small_window(monkeypatch, helper, count=1)
    output = tmp_path / "BTCUSDT_1h_ohlcv.csv"
    output.write_text("already here")
    called = False

    def fake_get(*args, **kwargs):
        nonlocal called
        called = True
        return FakeResponse([_kline(helper, first)])

    with pytest.raises(helper.AcquisitionError, match="overwrite"):
        helper.download(output, http_get=fake_get)
    assert not called


def test_csv_hash_is_stable_and_receipt_binds_it(helper, monkeypatch, tmp_path):
    first, last = _small_window(monkeypatch, helper, count=2)
    rows = [_kline(helper, first), _kline(helper, last)]
    fixed_now = lambda: datetime(2026, 7, 16, tzinfo=timezone.utc)
    output, receipt_path = helper.download(
        tmp_path / "BTCUSDT_1h_ohlcv.csv",
        http_get=lambda *args, **kwargs: FakeResponse(rows),
        now=fixed_now,
    )
    assert hashlib.sha256(output.read_bytes()).hexdigest() == json.loads(receipt_path.read_text())["csv_sha256"]
    assert output.read_bytes() == helper._csv_bytes([helper._normalize_kline(row) for row in rows])
