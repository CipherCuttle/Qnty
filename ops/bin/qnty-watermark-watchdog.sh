#!/usr/bin/env bash
# qnty-watermark-watchdog.sh - Ops-only: check the paper ledger watermark is advancing.
# Reads paper_ledger.db (read-only), compares the watermark to the expected 8h-cycle minimum,
# and writes a watchdog receipt under QNTY_RECEIPTS_DIR. Does NOT write to the paper DB. Does
# NOT place orders. Does NOT touch the observer/paper lane. See scripts/watermark_watchdog.py.
#
# Exit codes: 0=OK/DEFERRED/ERROR (informational), 1=STALE (gating).
# Testability: override Python interpreter via QNTY_PAPER_PYTHON (default: python).
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_DIR="$(cd "$SCRIPT_DIR/../.." && pwd)"

QNTY_PAPER_PYTHON="${QNTY_PAPER_PYTHON:-python}"

echo "[$(date -u '+%Y-%m-%dT%H:%M:%SZ')] qnty-watermark-watchdog: starting (read-only)"

# Only activate venv if it exists AND QNTY_PAPER_PYTHON is the default (python).
if [ "$QNTY_PAPER_PYTHON" = "python" ] && [ -f /srv/qnty/venv/bin/activate ]; then
    # shellcheck disable=SC1091
    source /srv/qnty/venv/bin/activate
fi

cd "$REPO_DIR"

# Propagate the watchdog exit code (1 == STALE) so the systemd unit records a failure.
set +e
${QNTY_PAPER_PYTHON} scripts/watermark_watchdog.py "$@"
rc=$?
set -e

echo "[$(date -u '+%Y-%m-%dT%H:%M:%SZ')] qnty-watermark-watchdog: complete (rc=${rc})"
exit "$rc"
