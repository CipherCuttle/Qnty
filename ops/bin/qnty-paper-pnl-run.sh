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

# (1) Paper accounting runner. Its paper_pnl_summary.json status is the runner's in-process
#     status only and is NOT authoritative — but its EXIT CODE gates whether we even try to
#     certify. Accounting exit-code matrix (see docs/paper_pnl_v1_schema.md § 5 / CLAUDE.md):
#       0 = OK or healthy NO_ELIGIBLE_BARS_YET no-op
#       2 = ABORTED (freshness/divergence gate; ledgers unchanged)
#       3 = CONFIG_ERROR (stale/missing/malformed paper_config.json — no writes)
#       4 = CORRUPT_LEDGER (a persisted ledger failed closed)
#     A CONFIG_ERROR or CORRUPT_LEDGER means we must NOT proceed to certify stale old ledgers as
#     trusted — fail the unit immediately.
set +e
python scripts/qnty-paper-accounting.py
acct_rc=$?
set -e
echo "[$(date -u '+%Y-%m-%dT%H:%M:%SZ')] qnty-paper-pnl: accounting runner exit=${acct_rc} (runner status, NOT authoritative)"

case "$acct_rc" in
    0)
        : # OK or healthy NO_ELIGIBLE_BARS_YET — proceed to the verifier.
        ;;
    2)
        # ABORTED (freshness/divergence). The existing ledgers were not mutated; this is normal
        # during pre-start (observer not yet fresh/past forward_start_ts). Tolerated and logged;
        # proceed to the verifier, which certifies whatever already-committed ledgers exist.
        echo "[$(date -u '+%Y-%m-%dT%H:%M:%SZ')] qnty-paper-pnl: accounting ABORTED (rc=2; freshness/divergence) — tolerated, ledgers unchanged; proceeding to verifier" >&2
        ;;
    3|4)
        # CONFIG_ERROR / CORRUPT_LEDGER: the accounting layer itself failed closed. Do NOT run the
        # verifier against stale/corrupt ledgers (it must not certify them). Fail the unit now.
        echo "[$(date -u '+%Y-%m-%dT%H:%M:%SZ')] qnty-paper-pnl: accounting FAILED CLOSED (rc=${acct_rc}; CONFIG_ERROR/CORRUPT_LEDGER) — refusing to certify; inspect paper_pnl_summary.json" >&2
        exit "$acct_rc"
        ;;
    *)
        echo "[$(date -u '+%Y-%m-%dT%H:%M:%SZ')] qnty-paper-pnl: accounting returned unexpected rc=${acct_rc} — failing closed" >&2
        exit "$acct_rc"
        ;;
esac

# (2) AUTHORITATIVE verifier. The latest paper_verify_report.json is the single source of truth;
#     trust is preserved separately in paper_verify_trusted_ok.json (advanced ONLY on OK).
#     Exit codes: 0=OK, 3=CONFIG_ERROR, 4=CORRUPT, 5=INCOMPLETE/RUNNING_STALE/NEEDS_BOOTSTRAP.
#     NOTE: the first trusted baseline must be established once by an operator with
#     `python scripts/paper_verify.py --bootstrap` after reviewing the first committed bars; the
#     timer never auto-bootstraps (it would otherwise blindly trust whatever ledgers it found).
set +e
python scripts/paper_verify.py
verify_rc=$?
set -e

case "$verify_rc" in
    0)
        echo "[$(date -u '+%Y-%m-%dT%H:%M:%SZ')] qnty-paper-pnl: VERIFIED OK (authoritative; SIMULATION)"
        ;;
    5)
        # INCOMPLETE / RUNNING_STALE / NEEDS_BOOTSTRAP: nothing certifiable yet. Tolerated during
        # pre-start (no eligible bars) or while awaiting an operator --bootstrap. Logged loudly;
        # the unit does not fail so the timer keeps observing.
        echo "[$(date -u '+%Y-%m-%dT%H:%M:%SZ')] qnty-paper-pnl: NOT YET CERTIFIABLE (verify rc=5; INCOMPLETE/RUNNING_STALE/NEEDS_BOOTSTRAP) — inspect paper_verify_report.json" >&2
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
