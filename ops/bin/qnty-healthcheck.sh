#!/usr/bin/env bash
# qnty-healthcheck.sh - Ops-only: check data freshness, disk, service liveness
# Does NOT place orders. Does NOT require exchange credentials.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_DIR="$(cd "$SCRIPT_DIR/../.." && pwd)"
DATA_DIR="/srv/qnty/data"
OUTPUT_DIR="/srv/qnty/output/forward_obs_v1"
LOG_DIR="/srv/qnty/logs"
KNOWN_STALE_OHLCV_FILES="${KNOWN_STALE_OHLCV_FILES:-MATICUSDT_8h_ohlcv.csv}"

HEALTH=0
NOW_UTC=$(date -u '+%Y-%m-%dT%H:%M:%SZ')
echo "[$NOW_UTC] qnty-healthcheck: starting"

is_known_stale_ohlcv_file() {
    local basename="$1"
    case " $KNOWN_STALE_OHLCV_FILES " in
        *" $basename "*) return 0 ;;
        *) return 1 ;;
    esac
}

timestamp_to_epoch_seconds() {
    local raw_ts="$1"

    if [[ "$raw_ts" =~ ^[0-9]+$ ]]; then
        if [ "$raw_ts" -gt 10000000000 ]; then
            echo $(( raw_ts / 1000 ))
        else
            echo "$raw_ts"
        fi
        return 0
    fi

    date -u -d "$raw_ts" +%s 2>/dev/null || echo 0
}

# 1. Check data freshness - newest bar should be within last 9 hours
for f in "$DATA_DIR"/*_8h_ohlcv.csv; do
    if [ -f "$f" ]; then
        BASENAME="$(basename "$f")"
        if is_known_stale_ohlcv_file "$BASENAME"; then
            echo "[INFO] Skipping freshness check for $BASENAME (known stale/delisted symbol; configured via KNOWN_STALE_OHLCV_FILES)"
            continue
        fi

        LAST_LINE=$(tail -1 "$f")
        LAST_TS=$(echo "$LAST_LINE" | cut -d',' -f1)
        if [ -n "$LAST_TS" ]; then
            LAST_EPOCH="$(timestamp_to_epoch_seconds "$LAST_TS")"
            if [ -z "$LAST_EPOCH" ] || [ "$LAST_EPOCH" -eq 0 ] 2>/dev/null; then
                echo "[WARN] Could not parse timestamp from $f: $LAST_TS"
                continue
            fi
            NOW_EPOCH=$(date -u +%s)
            AGE_HOURS=$(( (NOW_EPOCH - LAST_EPOCH) / 3600 ))
            if [ "$AGE_HOURS" -gt 9 ]; then
                echo "[FAIL] $f is stale: ${AGE_HOURS}h old (expected <=9h)"
                HEALTH=1
            fi
        fi
    fi
done

# 2. Check disk usage
DISK_PCT=$(df -h /srv/qnty | tail -1 | awk '{print $5}' | sed 's/%//')
if [ "${DISK_PCT:-0}" -gt 80 ]; then
    echo "[FAIL] Disk usage at ${DISK_PCT}% (threshold 80%)"
    HEALTH=1
else
    echo "[OK] Disk usage at ${DISK_PCT}%"
fi

# 3. Check systemd service states
for svc in qnty-data-refresh qnty-shadow-run qnty-healthcheck qnty-daily-summary; do
    for unit in "$svc.service" "$svc.timer"; do
        STATE=$(systemctl is-active "$unit" 2>/dev/null || echo "not-found")
        if [ "$STATE" != "active" ]; then
            echo "[WARN] $unit state: $STATE"
        fi
    done
done

# 4. Check last shadow run output exists
if [ -f "$OUTPUT_DIR/bar_decisions.jsonl" ]; then
    LAST_RUN=$(tail -1 "$OUTPUT_DIR/bar_decisions.jsonl" | python3 -c "import sys,json; print(json.load(sys.stdin).get('bar_processed_at','unknown'))" 2>/dev/null || echo "unknown")
    echo "[OK] Last shadow run: $LAST_RUN"
else
    echo "[WARN] No bar_decisions.jsonl found"
fi

if [ $HEALTH -eq 0 ]; then
    echo "[$NOW_UTC] qnty-healthcheck: PASS"
else
    echo "[$NOW_UTC] qnty-healthcheck: FAIL"
fi

exit $HEALTH
