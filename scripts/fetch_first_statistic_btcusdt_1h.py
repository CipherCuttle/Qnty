#!/usr/bin/env python3
"""Fetch the frozen BTCUSDT 1h source cut for first_computed_statistic_v0.

This is deliberately a single-purpose, non-overwriting acquisition helper.  It
does not run validation or scoring; it only writes a fully validated raw OHLCV
cut and a provenance receipt when explicitly invoked.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import os
import tempfile
from dataclasses import dataclass
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Callable, Sequence

import requests


SOURCE = "Binance USDⓈ-M Futures public REST"
ENDPOINT = "https://fapi.binance.com/fapi/v1/klines"
SYMBOL = "BTCUSDT"
MARKET_TYPE = "USDⓈ-M perpetual futures"
INTERVAL = "1h"
HOUR_MS = 3_600_000
FIRST_OPEN_TIME_MS = 1_625_097_600_000  # 2021-07-01T00:00:00Z
LAST_OPEN_TIME_MS = 1_776_902_400_000  # 2026-04-23T00:00:00Z
LAST_CLOSE_BOUNDARY_MS = 1_776_906_000_000  # 2026-04-23T01:00:00Z
TIMESTAMP_CONVENTION = "binance_open_time_plus_one_hour_exact_utc_close_boundary"
DEFAULT_OUTPUT_PATH = Path("data/first_computed_statistic_v0/BTCUSDT_1h_ohlcv.csv")


class AcquisitionError(RuntimeError):
    """Raised when the frozen acquisition contract cannot be proven."""


@dataclass(frozen=True)
class Kline:
    open_time_ms: int
    close_time_ms: int
    timestamp_ms: int
    open: str
    high: str
    low: str
    close: str
    volume: str


def _utc_iso(timestamp_ms: int) -> str:
    return datetime.fromtimestamp(timestamp_ms / 1000, tz=timezone.utc).strftime(
        "%Y-%m-%dT%H:%M:%SZ"
    )


def _parse_int(value: object, field: str) -> int:
    if isinstance(value, bool):
        raise AcquisitionError(f"malformed kline {field}: boolean is not an integer")
    try:
        parsed = int(value)
    except (TypeError, ValueError) as exc:
        raise AcquisitionError(f"malformed kline {field}: {value!r}") from exc
    if str(parsed) != str(value) and not isinstance(value, int):
        raise AcquisitionError(f"malformed kline {field}: {value!r}")
    return parsed


def _parse_decimal(value: object, field: str) -> str:
    if not isinstance(value, str) or not value:
        raise AcquisitionError(f"malformed kline {field}: {value!r}")
    try:
        parsed = Decimal(value)
    except InvalidOperation as exc:
        raise AcquisitionError(f"malformed kline {field}: {value!r}") from exc
    if not parsed.is_finite():
        raise AcquisitionError(f"malformed kline {field}: {value!r}")
    return value


def _normalize_kline(raw: object) -> Kline:
    if not isinstance(raw, list) or len(raw) < 7:
        raise AcquisitionError("malformed kline: expected Binance kline list with seven fields")

    open_time_ms = _parse_int(raw[0], "openTime")
    close_time_ms = _parse_int(raw[6], "closeTime")
    expected_boundary = open_time_ms + HOUR_MS
    if close_time_ms + 1 != expected_boundary:
        raise AcquisitionError(
            "Binance closeTime invariant failed: closeTime + 1 must equal openTime + 3600000"
        )
    return Kline(
        open_time_ms=open_time_ms,
        close_time_ms=close_time_ms,
        timestamp_ms=expected_boundary,
        open=_parse_decimal(raw[1], "open"),
        high=_parse_decimal(raw[2], "high"),
        low=_parse_decimal(raw[3], "low"),
        close=_parse_decimal(raw[4], "close"),
        volume=_parse_decimal(raw[5], "volume"),
    )


def _validate_klines(klines: Sequence[Kline]) -> None:
    expected_count = (LAST_OPEN_TIME_MS - FIRST_OPEN_TIME_MS) // HOUR_MS + 1
    if len(klines) != expected_count:
        raise AcquisitionError(
            f"partial coverage: expected {expected_count} klines, received {len(klines)}"
        )
    if not klines:
        raise AcquisitionError("partial coverage: no klines received")
    if klines[0].open_time_ms != FIRST_OPEN_TIME_MS:
        raise AcquisitionError("first openTime does not match frozen bound")
    if klines[-1].open_time_ms != LAST_OPEN_TIME_MS:
        raise AcquisitionError("last openTime does not match frozen bound")

    for kline in klines:
        if not FIRST_OPEN_TIME_MS <= kline.open_time_ms <= LAST_OPEN_TIME_MS:
            raise AcquisitionError("openTime is outside frozen inclusive bounds")
        if kline.timestamp_ms != kline.open_time_ms + HOUR_MS:
            raise AcquisitionError("raw openTime timestamp semantics are forbidden")
        if kline.close_time_ms + 1 != kline.timestamp_ms:
            raise AcquisitionError("Binance closeTime invariant failed after normalization")
    for previous, current in zip(klines, klines[1:]):
        open_delta = current.open_time_ms - previous.open_time_ms
        timestamp_delta = current.timestamp_ms - previous.timestamp_ms
        if open_delta <= 0:
            raise AcquisitionError("duplicate or non-monotonic openTime")
        if open_delta != HOUR_MS:
            raise AcquisitionError("missing hour or unexpected openTime cadence")
        if timestamp_delta <= 0:
            raise AcquisitionError("duplicate or non-monotonic emitted timestamp")
        if timestamp_delta != HOUR_MS:
            raise AcquisitionError("missing hour or unexpected emitted timestamp cadence")


def _fetch_klines(http_get: Callable[..., object]) -> list[Kline]:
    """Fetch all pages using only the frozen source, symbol, interval, and bounds."""
    klines: list[Kline] = []
    next_open_time_ms = FIRST_OPEN_TIME_MS
    while next_open_time_ms <= LAST_OPEN_TIME_MS:
        response = http_get(
            ENDPOINT,
            params={
                "symbol": SYMBOL,
                "interval": INTERVAL,
                "startTime": next_open_time_ms,
                "endTime": LAST_CLOSE_BOUNDARY_MS,
                "limit": 1000,
            },
            timeout=30,
        )
        response.raise_for_status()
        payload = response.json()
        if not isinstance(payload, list) or not payload:
            raise AcquisitionError("partial coverage: Binance returned an empty or malformed page")

        page = [_normalize_kline(raw) for raw in payload]
        if page[0].open_time_ms != next_open_time_ms:
            raise AcquisitionError("partial coverage: unexpected page boundary, duplicate, or partial Binance response")
        for previous, current in zip(page, page[1:]):
            if current.open_time_ms - previous.open_time_ms != HOUR_MS:
                raise AcquisitionError("duplicate, non-monotonic, or missing hour within Binance page")
        if page[-1].open_time_ms > LAST_OPEN_TIME_MS:
            raise AcquisitionError("Binance returned an openTime outside frozen inclusive bounds")
        klines.extend(page)
        next_open_time_ms = page[-1].open_time_ms + HOUR_MS

    _validate_klines(klines)
    return klines


def _csv_bytes(klines: Sequence[Kline]) -> bytes:
    lines = ["timestamp,open,high,low,close,volume\n"]
    lines.extend(
        f"{_utc_iso(k.timestamp_ms)},{k.open},{k.high},{k.low},{k.close},{k.volume}\n"
        for k in klines
    )
    return "".join(lines).encode("utf-8")


def _write_atomic_pair(output_path: Path, csv_bytes: bytes, receipt: dict[str, object]) -> Path:
    receipt_path = output_path.with_suffix(".receipt.json")
    if output_path.exists() or receipt_path.exists():
        raise AcquisitionError("refusing to overwrite existing output or provenance receipt")
    output_path.parent.mkdir(parents=True, exist_ok=True)
    csv_temp: Path | None = None
    receipt_temp: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(dir=output_path.parent, delete=False) as handle:
            csv_temp = Path(handle.name)
            handle.write(csv_bytes)
            handle.flush()
            os.fsync(handle.fileno())
        receipt_bytes = (json.dumps(receipt, indent=2, sort_keys=True) + "\n").encode("utf-8")
        with tempfile.NamedTemporaryFile(dir=output_path.parent, delete=False) as handle:
            receipt_temp = Path(handle.name)
            handle.write(receipt_bytes)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(csv_temp, output_path)
        os.replace(receipt_temp, receipt_path)
    except Exception:
        for temporary in (csv_temp, receipt_temp):
            if temporary is not None:
                temporary.unlink(missing_ok=True)
        raise
    return receipt_path


def download(
    output_path: Path = DEFAULT_OUTPUT_PATH,
    *,
    http_get: Callable[..., object] = requests.get,
    now: Callable[[], datetime] = lambda: datetime.now(timezone.utc),
) -> tuple[Path, Path]:
    """Acquire, validate, and atomically persist the frozen one-hour BTCUSDT cut."""
    output_path = Path(output_path)
    receipt_path = output_path.with_suffix(".receipt.json")
    if output_path.exists() or receipt_path.exists():
        raise AcquisitionError("refusing to overwrite existing output or provenance receipt")
    fetch_started_at = now().astimezone(timezone.utc)
    klines = _fetch_klines(http_get)
    csv_bytes = _csv_bytes(klines)
    receipt = {
        "source": SOURCE,
        "endpoint": ENDPOINT,
        "symbol": SYMBOL,
        "market_type": MARKET_TYPE,
        "interval": INTERVAL,
        "requested_first_open_time_utc": _utc_iso(FIRST_OPEN_TIME_MS),
        "requested_last_open_time_utc": _utc_iso(LAST_OPEN_TIME_MS),
        "timestamp_convention": TIMESTAMP_CONVENTION,
        "row_count": len(klines),
        "first_open_time_utc": _utc_iso(klines[0].open_time_ms),
        "last_open_time_utc": _utc_iso(klines[-1].open_time_ms),
        "first_close_boundary_utc": _utc_iso(klines[0].timestamp_ms),
        "last_close_boundary_utc": _utc_iso(klines[-1].timestamp_ms),
        "csv_sha256": hashlib.sha256(csv_bytes).hexdigest(),
        "fetch_started_at_utc": fetch_started_at.strftime("%Y-%m-%dT%H:%M:%SZ"),
        "fetch_completed_at_utc": now().astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
    }
    written_receipt = _write_atomic_pair(output_path, csv_bytes, receipt)
    return output_path, written_receipt


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-path", type=Path, default=DEFAULT_OUTPUT_PATH)
    args = parser.parse_args()
    output_path, receipt_path = download(args.output_path)
    print(f"wrote {output_path}")
    print(f"wrote {receipt_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
