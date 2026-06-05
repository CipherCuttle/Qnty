#!/usr/bin/env bash
# qnty-paper-pnl-run.sh - Ops-only: run one paper PnL accounting pass + reconcile.
# Strictly additive. Reads forward_obs_v1 read-only; writes only paper_pnl_v1.
# Does NOT place orders. Does NOT touch the observer. Decoupled from qnty-shadow-run.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_DIR="$(cd "$SCRIPT_DIR/../.." && pwd)"
LOCK_FILE="${QNTY_PAPER_LOCK:-/tmp/qnty-paper-pnl.lock}"

# Single-instance guard: skip silently if a run is already in progress.
exec 9>"$LOCK_FILE"
if ! flock -n 9; then
    echo "[$(date -u '+%Y-%m-%dT%H:%M:%SZ')] qnty-paper-pnl: another run holds the lock; skipping"
    exit 0
fi

echo "[$(date -u '+%Y-%m-%dT%H:%M:%SZ')] qnty-paper-pnl: starting (SIMULATION)"

if [ -f /srv/qnty/venv/bin/activate ]; then
    # shellcheck disable=SC1091
    source /srv/qnty/venv/bin/activate
fi

cd "$REPO_DIR"

# Refuse to run until the write-once config exists (operator must init first).
PAPER_DIR="${QNTY_PAPER_OUTPUT_DIR:-/srv/qnty/output/paper_pnl_v1}"
if [ ! -f "$PAPER_DIR/paper_config.json" ]; then
    echo "Missing $PAPER_DIR/paper_config.json. Run qnty-paper-pnl-init.sh first." >&2
    exit 1
fi

python scripts/qnty-paper-accounting.py
python scripts/paper_reconcile.py

echo "[$(date -u '+%Y-%m-%dT%H:%M:%SZ')] qnty-paper-pnl: complete"
