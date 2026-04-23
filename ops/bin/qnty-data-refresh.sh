#!/usr/bin/env bash
# qnty-data-refresh.sh - Ops-only: fetch OHLCV and funding data from Binance public API
# Does NOT place orders. Does NOT require exchange credentials.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_DIR="$(cd "$SCRIPT_DIR/../.." && pwd)"
DATA_DIR="/srv/qnty/data"

echo "[$(date -u '+%Y-%m-%dT%H:%M:%SZ')] qnty-data-refresh: starting"

# Activate venv
source /srv/qnty/venv/bin/activate

cd "$REPO_DIR"

# Determine the END_TIME to fetch.
# Use TODAY's date + 1 day as END_TIME_MS to capture all available data.
# The fetch scripts write Unix-ms timestamps.
TODAY_EPOCH_MS=$(date -d "$(date -u +%Y-%m-%d) +1 day" +%s000)
export END_TIME_MS="${END_TIME_MS:-$TODAY_EPOCH_MS}"

echo "[$(date -u '+%Y-%m-%dT%H:%M:%SZ')] Fetching OHLCV (END_TIME_MS=$END_TIME_MS)..."
python scripts/fetch_ohlcv_rest.py

echo "[$(date -u '+%Y-%m-%dT%H:%M:%SZ')] Fetching funding rates..."
python scripts/fetch_funding_rest.py

echo "[$(date -u '+%Y-%m-%dT%H:%M:%SZ')] qnty-data-refresh: complete"
