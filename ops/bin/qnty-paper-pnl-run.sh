#!/usr/bin/env bash
# qnty-paper-pnl-run.sh - Ops-only: run one paper PnL accounting pass, then the AUTHORITATIVE
# read-only verifier. SQLite ledger path (Phase 4). Reads forward_obs_v1 read-only; writes only
# paper_ledger.db. Does NOT place orders. Does NOT touch the observer. Decoupled from qnty-shadow-run.
#
# Flow (ADR 0001 / Phase 4): (1) SQLite accounting writer, then (2) SQLite read-only verifier.
# The single authoritative paper status is the verifier exit code. See docs/ADR/0001-paper-sqlite-ledger.md.
#
# Precondition: QNTY_PAPER_DB_PATH must point to an existing paper_ledger.db.
# If DB is missing, fails cleanly with guidance to run qnty-paper-sqlite-init.py.
#
# Testability: override accounting/verify commands via QNTY_PAPER_ACCT_CMD / QNTY_PAPER_VERIFY_CMD.
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

# Precondition: SQLite DB must exist.
DB_PATH="${QNTY_PAPER_DB_PATH:-/srv/qnty/output/paper_pnl_v1/paper_ledger.db}"
if [ ! -f "$DB_PATH" ]; then
    echo "Missing SQLite DB at $DB_PATH" >&2
    echo "Run: python scripts/qnty-paper-sqlite-init.py --forward-start-ts <future UTC 8h boundary>" >&2
    exit 1
fi

# (1) SQLite accounting writer.
#     Exit codes: 0=OK, 2=ABORTED, 3=CONFIG_ERROR, 4=CORRUPT_LEDGER, 5=PRE_START, 6=LEDGER_BUSY
#     If accounting fails (rc!=0 and rc!=5), do NOT run verifier (prevents certifying stale DB).
ACCT_CMD="${QNTY_PAPER_ACCT_CMD:-python scripts/qnty-paper-sqlite-accounting.py}"
set +e
$ACCT_CMD
acct_rc=$?
set -e
echo "[$(date -u '+%Y-%m-%dT%H:%M:%SZ')] qnty-paper-pnl: accounting exit=${acct_rc}"

case "$acct_rc" in
    0|5)
        # OK or PRE_START: proceed to verifier.
        ;;
    2)
        # ABORTED: failure, not healthy no-op. Do NOT run verifier.
        echo "[$(date -u '+%Y-%m-%dT%H:%M:%SZ')] qnty-paper-pnl: accounting ABORTED (rc=2) — not proceeding to verifier" >&2
        exit 2
        ;;
    3)
        # CONFIG_ERROR: do NOT run verifier.
        echo "[$(date -u '+%Y-%m-%dT%H:%M:%SZ')] qnty-paper-pnl: accounting CONFIG_ERROR (rc=3) — not proceeding to verifier" >&2
        exit 3
        ;;
    4)
        # CORRUPT_LEDGER: do NOT run verifier.
        echo "[$(date -u '+%Y-%m-%dT%H:%M:%SZ')] qnty-paper-pnl: accounting CORRUPT_LEDGER (rc=4) — not proceeding to verifier" >&2
        exit 4
        ;;
    6)
        # LEDGER_BUSY: do NOT run verifier.
        echo "[$(date -u '+%Y-%m-%dT%H:%M:%SZ')] qnty-paper-pnl: accounting LEDGER_BUSY (rc=6) — not proceeding to verifier" >&2
        exit 6
        ;;
    *)
        # Unexpected nonzero: do NOT run verifier.
        echo "[$(date -u '+%Y-%m-%dT%H:%M:%SZ')] qnty-paper-pnl: accounting unexpected rc=${acct_rc} — not proceeding to verifier" >&2
        exit "$acct_rc"
        ;;
esac

# (2) SQLite read-only verifier.
#     Exit codes: 0=OK, 3=CONFIG_ERROR, 4=CORRUPT, 5=PRE_START
VERIFY_CMD="${QNTY_PAPER_VERIFY_CMD:-python scripts/qnty-paper-sqlite-verify.py}"
set +e
$VERIFY_CMD
verify_rc=$?
set -e
echo "[$(date -u '+%Y-%m-%dT%H:%M:%SZ')] qnty-paper-pnl: verifier exit=${verify_rc}"

# Wrapper exit code matrix:
#   acct 0 + verify 0   => exit 0
#   acct 5 + verify 5   => exit 0
#   acct 0 + verify 5   => exit 4
#   acct 5 + verify 0   => exit 4
#   acct 0 + verify 3   => exit 3
#   acct 0 + verify 4   => exit 4
#   acct 5 + verify 3   => exit 3
#   acct 5 + verify 4   => exit 4
case "$acct_rc:$verify_rc" in
    0:0|5:5)
        echo "[$(date -u '+%Y-%m-%dT%H:%M:%SZ')] qnty-paper-pnl: VERIFIED OK (authoritative; SIMULATION)"
        exit 0
        ;;
    0:5|5:0)
        echo "[$(date -u '+%Y-%m-%dT%H:%M:%SZ')] qnty-paper-pnl: accounting/verifier status mismatch (acct=${acct_rc}, verify=${verify_rc})" >&2
        exit 4
        ;;
    0:3|5:3)
        echo "[$(date -u '+%Y-%m-%dT%H:%M:%SZ')] qnty-paper-pnl: verifier CONFIG_ERROR (rc=3)" >&2
        exit 3
        ;;
    0:4|5:4)
        echo "[$(date -u '+%Y-%m-%dT%H:%M:%SZ')] qnty-paper-pnl: verifier CORRUPT (rc=4)" >&2
        exit 4
        ;;
    *)
        # Unexpected combination: exit with verifier rc if nonzero, else 4.
        if [ "$verify_rc" -ne 0 ]; then
            exit "$verify_rc"
        fi
        exit 4
        ;;
esac
