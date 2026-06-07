#!/usr/bin/env bash
# qnty-paper-pnl-run.sh - Ops-only: run one paper PnL accounting pass, then the AUTHORITATIVE
# read-only verifier. Strictly additive. Reads forward_obs_v1 read-only; writes only paper_pnl_v1.
# Does NOT place orders. Does NOT touch the observer. Decoupled from qnty-shadow-run.
#
# Flow (see docs/paper_pnl_v1_schema.md § 5a): (1) paper accounting runner, then (2) paper
# verifier. The runner's paper_pnl_summary.json is a CONVENIENCE status only; the single
# authoritative paper status is paper_verify_report.json. Operators MUST inspect
# paper_verify_report.json (NOT paper_pnl_summary.json) to decide whether a run is trusted.
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

# (1) Paper accounting runner. Its own exit code / paper_pnl_summary.json status is the runner's
#     in-process status only and is NOT authoritative. An ABORTED/no-op run is normal during
#     pre-start (observer not yet past forward_start_ts), so do not fail the unit on it here —
#     the verifier below is the gate.
set +e
python scripts/qnty-paper-accounting.py
acct_rc=$?
set -e
echo "[$(date -u '+%Y-%m-%dT%H:%M:%SZ')] qnty-paper-pnl: accounting runner exit=${acct_rc} (runner status, NOT authoritative)"

# (2) AUTHORITATIVE verifier. paper_verify_report.json is the single source of truth.
#     Exit codes: 0=OK, 3=CONFIG_ERROR, 4=CORRUPT, 5=INCOMPLETE/RUNNING_STALE.
set +e
python scripts/paper_verify.py
verify_rc=$?
set -e

case "$verify_rc" in
    0)
        echo "[$(date -u '+%Y-%m-%dT%H:%M:%SZ')] qnty-paper-pnl: VERIFIED OK (authoritative; SIMULATION)"
        ;;
    5)
        # INCOMPLETE / RUNNING_STALE: nothing certifiable yet. Tolerated during pre-start (no
        # eligible bars). Logged loudly; the unit does not fail so the timer keeps observing.
        echo "[$(date -u '+%Y-%m-%dT%H:%M:%SZ')] qnty-paper-pnl: NOT YET CERTIFIABLE (verify rc=5; INCOMPLETE/RUNNING_STALE) — inspect paper_verify_report.json" >&2
        ;;
    *)
        # CONFIG_ERROR (3), CORRUPT (4), or any unexpected code: the run is NOT trusted. Fail the
        # unit so systemd marks it failed and alerting fires. Operators inspect
        # paper_verify_report.json (NOT paper_pnl_summary.json).
        echo "[$(date -u '+%Y-%m-%dT%H:%M:%SZ')] qnty-paper-pnl: VERIFIER FAILED (rc=${verify_rc}) — paper run NOT trusted; inspect paper_verify_report.json" >&2
        exit "$verify_rc"
        ;;
esac

echo "[$(date -u '+%Y-%m-%dT%H:%M:%SZ')] qnty-paper-pnl: complete"
