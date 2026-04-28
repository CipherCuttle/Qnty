#!/usr/bin/env bash
# qnty-daily-summary.sh - Ops-only: generate <operator>-facing daily status summary
# Does NOT place orders. Does NOT require exchange credentials.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_DIR="$(cd "$SCRIPT_DIR/../.." && pwd)"
OUTPUT_DIR="/srv/qnty/output/forward_obs_v1"
DATA_DIR="/srv/qnty/data"

NOW_UTC=$(date -u '+%Y-%m-%dT%H:%M:%SZ')
TODAY=$(date -u '+%Y-%m-%d')

echo "[$NOW_UTC] qnty-daily-summary: starting"

cd "$REPO_DIR"

# Collect metrics
COMMIT_SHA=$(git rev-parse HEAD)
COMMIT_DATE=$(git log -1 --format='%ci' HEAD)

# Count bars processed
BAR_COUNT=0
if [ -f "$OUTPUT_DIR/bar_decisions.jsonl" ]; then
    BAR_COUNT=$(wc -l < "$OUTPUT_DIR/bar_decisions.jsonl" 2>/dev/null || echo 0)
fi

# Get newest bar timestamp
NEWEST_BAR="unknown"
for f in "$DATA_DIR"/*_8h_ohlcv.csv; do
    if [ -f "$f" ]; then
        LAST_TS=$(tail -1 "$f" | cut -d',' -f1)
        if [ -n "$LAST_TS" ] && [ "$LAST_TS" != "timestamp" ]; then
            # Convert ms to readable
            TS_EPOCH=${LAST_TS%000}
            READABLE=$(date -d "@$TS_EPOCH" -u '+%Y-%m-%dT%H:%M:%SZ' 2>/dev/null || echo "$LAST_TS")
            if [ "$READABLE" != "unknown" ]; then
                NEWEST_BAR="$READABLE"
            fi
        fi
    fi
done

# Get last verdict if exists
VERDICT="no-verdict-yet"
if [ -f "$OUTPUT_DIR/verdict.json" ]; then
    VERDICT=$(python3 -c "import json; d=json.load(open('$OUTPUT_DIR/verdict.json')); print(d.get('verdict','unknown'))" 2>/dev/null || echo "unknown")
fi

# Generate summary
SUMMARY_FILE="$OUTPUT_DIR/daily_summary.jsonl"
SUMMARY_ENTRY=$(cat <<EOF
{
  "date": "$TODAY",
  "generated_at": "$NOW_UTC",
  "commit_sha": "$COMMIT_SHA",
  "commit_date": "$COMMIT_DATE",
  "bars_processed": $BAR_COUNT,
  "newest_bar": "$NEWEST_BAR",
  "last_verdict": "$VERDICT"
}
EOF
)

echo "$SUMMARY_ENTRY" >> "$SUMMARY_FILE"

# Write human-readable summary to logs
LOG_FILE="$LOG_DIR/daily_summary_${TODAY}.txt"
mkdir -p "$LOG_DIR"
{
    echo "Qnty 90-Day Observer - Daily Summary"
    echo "===================================="
    echo "Generated: $NOW_UTC"
    echo ""
    echo "Package: Package V2 (volnorm, frozen)"
    echo "Commit: $COMMIT_SHA ($COMMIT_DATE)"
    echo "Phase: forward_observation"
    echo ""
    echo "Bars processed (total): $BAR_COUNT"
    echo "Newest bar available: $NEWEST_BAR"
    echo "Last shadow run verdict: $VERDICT"
    echo ""
    echo "Caveats (unchanged):"
    echo "  - benchmark remains gross"
    echo "  - strategy remains net of realistic funding"
    echo "  - K3 remains unavailable / caveated"
    echo "  - Package V2 is NOT deployment-ready"
    echo ""
    echo "Next authorized action: frozen forward observation"
    echo "Forbidden: any package mutation, K3 impl, overlay/ML/Kelly/RAMOM"
} > "$LOG_FILE"

echo "[$NOW_UTC] qnty-daily-summary: complete"
echo "Summary written to $LOG_FILE"
