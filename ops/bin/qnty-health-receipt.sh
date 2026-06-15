#!/usr/bin/env bash
# qnty-health-receipt.sh - Ops-only: emit a READ-ONLY paper health receipt.
# Reads paper_verify_report.json + paper_ledger.db (read-only) and writes a health receipt
# under QNTY_RECEIPTS_DIR. Does NOT write to the paper DB. Does NOT place orders. Does NOT
# touch the observer/paper lane. See scripts/health_receipt.py.
#
# Testability: override Python interpreter via QNTY_PAPER_PYTHON (default: python).
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_DIR="$(cd "$SCRIPT_DIR/../.." && pwd)"

QNTY_PAPER_PYTHON="${QNTY_PAPER_PYTHON:-python}"

echo "[$(date -u '+%Y-%m-%dT%H:%M:%SZ')] qnty-health-receipt: starting (read-only)"

# Only activate venv if it exists AND QNTY_PAPER_PYTHON is the default (python).
if [ "$QNTY_PAPER_PYTHON" = "python" ] && [ -f /srv/qnty/venv/bin/activate ]; then
    # shellcheck disable=SC1091
    source /srv/qnty/venv/bin/activate
fi

cd "$REPO_DIR"

# Health is informational and always exits 0 (OK/WARN/DEFERRED/ERROR captured in the receipt).
${QNTY_PAPER_PYTHON} scripts/health_receipt.py "$@"

echo "[$(date -u '+%Y-%m-%dT%H:%M:%SZ')] qnty-health-receipt: complete"
