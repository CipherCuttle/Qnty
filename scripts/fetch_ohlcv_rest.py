#!/usr/bin/env python3
"""
Fetch Binance Futures 8h klines via REST API with forward pagination.
Saves to data/{SYMBOL}_8h_ohlcv.csv
"""

import csv
import time
import os
from datetime import datetime, timezone
from pathlib import Path

import requests

# Configuration
SYMBOLS = [
    "BTCUSDT", "ETHUSDT", "BNBUSDT", "SOLUSDT", "ADAUSDT",
    "DOTUSDT", "AVAXUSDT", "LINKUSDT", "MATICUSDT", "XRPUSDT"
]

START_TIME_MS = 1625097600000  # 2021-07-01 00:00:00 UTC


def resolve_end_time_ms() -> int:
    """Resolve the pagination cutoff (epoch ms) for the fetch.

    Reads the ``END_TIME_MS`` environment variable that
    ``ops/bin/qnty-data-refresh.sh`` already exports. When the variable is
    unset/blank, defaults to ``now + 1 day`` so a scheduled refresh always
    paginates through the latest available data.

    A malformed value fails closed (``ValueError``) instead of silently
    falling back. The previous hardcoded cutoff (2026-04-20) acted only as a
    pagination guard and silently truncated fetches when a symbol's full pages
    happened to land past that stale date — never again.
    """
    raw = os.environ.get("END_TIME_MS")
    if raw is None or raw.strip() == "":
        return int(time.time() * 1000) + 86_400_000  # now + 1 day
    try:
        return int(raw)
    except (TypeError, ValueError) as exc:
        raise ValueError(
            f"END_TIME_MS must be integer epoch milliseconds, got {raw!r}"
        ) from exc


END_TIME_MS = resolve_end_time_ms()

API_URL_TEMPLATE = "https://fapi.binance.com/fapi/v1/klines?symbol={SYM}&interval=8h&startTime={TS}&limit=500"
DATA_DIR = Path("data")
FETCH_LOG_PATH = DATA_DIR / "fetch_ohlcv_log_rest.txt"
REQUEST_SLEEP = 0.2  # seconds between requests


def fetch_ohlcv_for_symbol(symbol: str) -> dict:
    """
    Fetch all 8h klines for a symbol using forward pagination.
    Returns dict with keys: records, pages, date_range
    """
    records = []
    current_start = START_TIME_MS
    pages = 0
    first_time = None
    last_time = None

    while current_start < END_TIME_MS:
        url = API_URL_TEMPLATE.format(SYM=symbol, TS=current_start)
        response = requests.get(url, timeout=30)
        response.raise_for_status()
        data = response.json()

        if not data:
            print(f"  {symbol}: No more data at startTime {current_start} — end of history reached")
            break

        # Binance klines response format:
        # [openTime, open, high, low, close, volume, closeTime, ...]
        for kline in data:
            open_time_ms = int(kline[0])
            if first_time is None:
                first_time = open_time_ms
            last_time = open_time_ms

            records.append({
                "timestamp": ms_to_iso(open_time_ms),
                "open": float(kline[1]),
                "high": float(kline[2]),
                "low": float(kline[3]),
                "close": float(kline[4]),
                "volume": float(kline[5]),
            })

        pages += 1
        last_open_time = int(data[-1][0])
        current_start = last_open_time + 1  # move to next page

        print(f"  {symbol}: page {pages}, records {len(records)}, "
              f"last openTime {last_open_time} ({ms_to_iso(last_open_time)})")

        time.sleep(REQUEST_SLEEP)

    return {
        "records": records,
        "pages": pages,
        "date_range": (first_time, last_time) if first_time else (None, None),
    }


def ms_to_iso(ms: int) -> str:
    """Convert millisecond timestamp to ISO 8601 UTC string."""
    if ms is None:
        return "N/A"
    return datetime.fromtimestamp(ms / 1000, tz=timezone.utc).strftime("%Y-%m-%dT%H:%M:%S")


def save_to_csv(records: list, symbol: str):
    """Save records to CSV file."""
    output_path = DATA_DIR / f"{symbol}_8h_ohlcv.csv"

    with open(output_path, "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=["timestamp", "open", "high", "low", "close", "volume"])
        writer.writeheader()
        writer.writerows(records)

    return output_path


def main():
    print("=" * 70)
    print("Binance Futures 8h OHLCV REST Fetch")
    print(f"Start: {ms_to_iso(START_TIME_MS)}")
    print(f"End:   {ms_to_iso(END_TIME_MS)}")
    print(f"Symbols: {len(SYMBOLS)}")
    print("=" * 70)

    # Ensure data directory exists
    DATA_DIR.mkdir(exist_ok=True)

    # Open fetch log
    with open(FETCH_LOG_PATH, "w") as log_file:
        log_file.write(f"Binance Futures 8h OHLCV REST Fetch\n")
        log_file.write(f"Started: {datetime.now(timezone.utc).isoformat()}\n")
        log_file.write(f"Start Time: {ms_to_iso(START_TIME_MS)} ({START_TIME_MS})\n")
        log_file.write(f"End Time: {ms_to_iso(END_TIME_MS)} ({END_TIME_MS})\n")
        log_file.write(f"Symbols: {', '.join(SYMBOLS)}\n")
        log_file.write("=" * 70 + "\n\n")

        total_records_all = 0
        all_results = []

        for symbol in SYMBOLS:
            print(f"\nFetching {symbol}...")
            log_file.write(f"\n{symbol}\n")
            log_file.write("-" * 40 + "\n")

            try:
                result = fetch_ohlcv_for_symbol(symbol)
                records = result["records"]
                pages = result["pages"]
                date_range = result["date_range"]

                if not records:
                    raise ValueError(f"No records returned for {symbol}")

                output_path = save_to_csv(records, symbol)
                print(f"  -> Saved {len(records)} records to {output_path}")
                log_file.write(f"Pages: {pages}\n")
                log_file.write(f"Records: {len(records)}\n")
                log_file.write(f"First: {date_range[0]} ({ms_to_iso(date_range[0])})\n")
                log_file.write(f"Last:  {date_range[1]} ({ms_to_iso(date_range[1])})\n")
                log_file.write(f"Output: {output_path}\n")
                total_records_all += len(records)
                all_results.append({
                    "symbol": symbol,
                    "pages": pages,
                    "records": len(records),
                    "first": date_range[0],
                    "last": date_range[1],
                })

            except Exception as e:
                print(f"  -> ERROR: {e}")
                log_file.write(f"ERROR: {e}\n")
                raise  # fail loudly

        # Summary
        print("\n" + "=" * 70)
        print("SUMMARY")
        print("=" * 70)
        log_file.write("\n" + "=" * 70 + "\n")
        log_file.write("SUMMARY\n")
        log_file.write("=" * 70 + "\n")

        for r in all_results:
            print(f"{r['symbol']}: {r['pages']} pages, {r['records']} records, "
                  f"{ms_to_iso(r['first'])} -> {ms_to_iso(r['last'])}")
            log_file.write(f"{r['symbol']}: {r['pages']} pages, {r['records']} records, "
                          f"{ms_to_iso(r['first'])} -> {ms_to_iso(r['last'])}\n")

        print(f"\nTotal records: {total_records_all}")
        print(f"Fetch log: {FETCH_LOG_PATH}")
        print("=" * 70)

        log_file.write(f"\nTotal records: {total_records_all}\n")
        log_file.write(f"Completed: {datetime.now(timezone.utc).isoformat()}\n")

    # Verify files exist
    print("\nVerifying output files:")
    for symbol in SYMBOLS:
        output_path = DATA_DIR / f"{symbol}_8h_ohlcv.csv"
        if output_path.exists():
            size = output_path.stat().st_size
            print(f"  {output_path}: {size} bytes")
        else:
            print(f"  {output_path}: NOT FOUND")


if __name__ == "__main__":
    main()
