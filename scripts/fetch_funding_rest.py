#!/usr/bin/env python3
"""
Fetch Binance futures funding rate data via REST API with forward pagination.
Saves to data/{SYMBOL}_8h_funding.csv
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
    pagination guard and silently truncated SOLUSDT funding when a symbol's
    full pages happened to land past that stale date — never again.
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

API_URL_TEMPLATE = "https://fapi.binance.com/fapi/v1/fundingRate?symbol={SYM}&startTime={TS}&limit=500"
DATA_DIR = Path("data")
FETCH_LOG_PATH = DATA_DIR / "fetch_log_rest.txt"
REQUEST_SLEEP = 0.2  # seconds between requests


def fetch_funding_for_symbol(symbol: str) -> dict:
    """
    Fetch all funding records for a symbol using forward pagination.
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
            break

        pages += 1

        for record in data:
            funding_time = int(record["fundingTime"])
            if first_time is None:
                first_time = funding_time
            last_time = funding_time

            mark_price_str = record.get("markPrice", "0")
            mark_price = float(mark_price_str) if mark_price_str else 0.0

            records.append({
                "symbol": symbol,
                "fundingTime": funding_time,
                "fundingRate": float(record["fundingRate"]),
                "markPrice": mark_price,
            })

        # Move to next page: last fundingTime + 1ms
        last_funding_time = int(data[-1]["fundingTime"])
        current_start = last_funding_time + 1

        # Progress print
        print(f"  {symbol}: page {pages}, records {len(records)}, "
              f"last fundingTime {last_funding_time} ({ms_to_date(last_funding_time)})")

        time.sleep(REQUEST_SLEEP)

    return {
        "records": records,
        "pages": pages,
        "date_range": (first_time, last_time) if first_time else (None, None),
    }


def ms_to_date(ms: int) -> str:
    """Convert millisecond timestamp to ISO date string."""
    if ms is None:
        return "N/A"
    return datetime.fromtimestamp(ms / 1000, tz=timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")


def save_to_csv(records: list, symbol: str):
    """Save records to CSV file."""
    output_path = DATA_DIR / f"{symbol}_8h_funding.csv"

    with open(output_path, "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=["symbol", "fundingTime", "fundingRate", "markPrice"])
        writer.writeheader()
        writer.writerows(records)

    return output_path


def main():
    print("=" * 70)
    print("Binance Futures Funding Rate REST Fetch")
    print(f"Start: {ms_to_date(START_TIME_MS)}")
    print(f"End:   {ms_to_date(END_TIME_MS)}")
    print(f"Symbols: {len(SYMBOLS)}")
    print("=" * 70)

    # Ensure data directory exists
    DATA_DIR.mkdir(exist_ok=True)

    # Open fetch log
    with open(FETCH_LOG_PATH, "w") as log_file:
        log_file.write(f"Binance Futures Funding Rate REST Fetch\n")
        log_file.write(f"Started: {datetime.now(timezone.utc).isoformat()}\n")
        log_file.write(f"Start Time: {ms_to_date(START_TIME_MS)} ({START_TIME_MS})\n")
        log_file.write(f"End Time: {ms_to_date(END_TIME_MS)} ({END_TIME_MS})\n")
        log_file.write(f"Symbols: {', '.join(SYMBOLS)}\n")
        log_file.write("=" * 70 + "\n\n")

        total_records_all = 0
        all_results = []

        for symbol in SYMBOLS:
            print(f"\nFetching {symbol}...")
            log_file.write(f"\n{symbol}\n")
            log_file.write("-" * 40 + "\n")

            try:
                result = fetch_funding_for_symbol(symbol)
                records = result["records"]
                pages = result["pages"]
                date_range = result["date_range"]

                if records:
                    output_path = save_to_csv(records, symbol)
                    print(f"  -> Saved {len(records)} records to {output_path}")
                    log_file.write(f"Pages: {pages}\n")
                    log_file.write(f"Records: {len(records)}\n")
                    log_file.write(f"First: {ms_to_date(date_range[0])} ({date_range[0]})\n")
                    log_file.write(f"Last:  {ms_to_date(date_range[1])} ({date_range[1]})\n")
                    log_file.write(f"Output: {output_path}\n")
                    total_records_all += len(records)
                    all_results.append({
                        "symbol": symbol,
                        "pages": pages,
                        "records": len(records),
                        "first": date_range[0],
                        "last": date_range[1],
                    })
                else:
                    print(f"  -> No records returned for {symbol}")
                    log_file.write("No records returned.\n")

            except Exception as e:
                print(f"  -> ERROR: {e}")
                log_file.write(f"ERROR: {e}\n")

        # Summary
        print("\n" + "=" * 70)
        print("SUMMARY")
        print("=" * 70)
        log_file.write("\n" + "=" * 70 + "\n")
        log_file.write("SUMMARY\n")
        log_file.write("=" * 70 + "\n")

        for r in all_results:
            print(f"{r['symbol']}: {r['pages']} pages, {r['records']} records, "
                  f"{ms_to_date(r['first'])} -> {ms_to_date(r['last'])}")
            log_file.write(f"{r['symbol']}: {r['pages']} pages, {r['records']} records, "
                          f"{ms_to_date(r['first'])} -> {ms_to_date(r['last'])}\n")

        print(f"\nTotal records: {total_records_all}")
        print(f"Fetch log: {FETCH_LOG_PATH}")
        print("=" * 70)

        log_file.write(f"\nTotal records: {total_records_all}\n")
        log_file.write(f"Completed: {datetime.now(timezone.utc).isoformat()}\n")

    # Verify files exist
    print("\nVerifying output files:")
    for symbol in SYMBOLS:
        output_path = DATA_DIR / f"{symbol}_8h_funding.csv"
        if output_path.exists():
            size = output_path.stat().st_size
            print(f"  {output_path}: {size} bytes")
        else:
            print(f"  {output_path}: NOT FOUND")


if __name__ == "__main__":
    main()
