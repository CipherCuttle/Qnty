#!/usr/bin/env bash
# qnty-shadow-run.sh - Ops-only: run frozen Package V2 observer on latest 8h bar
# Does NOT place orders. Does NOT require exchange credentials.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_DIR="$(cd "$SCRIPT_DIR/../.." && pwd)"
OUTPUT_DIR="/srv/qnty/output/forward_obs_v1"

echo "[$(date -u '+%Y-%m-%dT%H:%M:%SZ')] qnty-shadow-run: starting"

# Activate venv
source /srv/qnty/venv/bin/activate

cd "$REPO_DIR"

# Ensure output dir exists
mkdir -p "$OUTPUT_DIR"

# Record run timestamp and package identity
RUN_TS=$(date -u '+%Y-%m-%dT%H:%M:%SZ')
COMMIT_SHA=$(git rev-parse HEAD)
echo "{\"run_ts\": \"$RUN_TS\", \"commit_sha\": \"$COMMIT_SHA\", \"phase\": \"forward_observation\"}" \
    > "$OUTPUT_DIR/run_metadata.json"

# Run stage4 volnorm (produces per_split_metrics, kill_criteria)
echo "[$(date -u '+%Y-%m-%dT%H:%M:%SZ')] Running stage4 volnorm..."
python scripts/run_stage4_volnorm.py

# Copy stage4 outputs to forward_obs directory
cp output/stage4_volnorm/per_split_metrics.csv "$OUTPUT_DIR/" 2>/dev/null || true
cp output/stage4_volnorm/kill_criteria.json "$OUTPUT_DIR/" 2>/dev/null || true

# Run validation v2 (produces verdict, observation_log, etc.)
echo "[$(date -u '+%Y-%m-%dT%H:%M:%SZ')] Running validation v2..."
python scripts/run_validation_v2.py

# Copy validation outputs to forward_obs directory
cp output/validation_v2/verdict.json "$OUTPUT_DIR/" 2>/dev/null || true
cp output/validation_v2/observation_log.json "$OUTPUT_DIR/" 2>/dev/null || true
cp output/validation_v2/caveat_note.md "$OUTPUT_DIR/" 2>/dev/null || true
cp output/validation_v2/validation_receipt.md "$OUTPUT_DIR/" 2>/dev/null || true

# Append a bar_decisions record (one per shadow run)
# This is a simple timestamped marker noting a bar was processed
BAR_TS=$(date -u '+%Y-%m-%dT%H:%M:%SZ')
echo "{\"bar_processed_at\": \"$BAR_TS\", \"commit_sha\": \"$COMMIT_SHA\"}" \
    >> "$OUTPUT_DIR/bar_decisions.jsonl"

echo "[$(date -u '+%Y-%m-%dT%H:%M:%SZ')] qnty-shadow-run: complete"
