#!/usr/bin/env bash
# qnty-verify-vm-provenance.sh - Read-only VM provenance verifier.
# Does NOT restart services. Does NOT write files. Does NOT require secrets.
set -euo pipefail

ROOT_DIR="${QNTY_ROOT_DIR:-/srv/qnty}"
REPO_DIR="${QNTY_REPO_DIR:-$ROOT_DIR/repo}"
STATE_DIR="${QNTY_STATE_DIR:-$ROOT_DIR/state}"
OUTPUT_DIR="${QNTY_OUTPUT_DIR:-$ROOT_DIR/output/forward_obs_v1}"

TIMERS=(
    qnty-data-refresh.timer
    qnty-shadow-run.timer
    qnty-healthcheck.timer
    qnty-daily-summary.timer
)

FAIL=0

ok() {
    echo "[OK] $*"
}

fail() {
    echo "[FAIL] $*"
    FAIL=1
}

info() {
    echo "[INFO] $*"
}

read_file_trimmed() {
    local path="$1"
    if [ -f "$path" ]; then
        tr -d '[:space:]' < "$path"
    fi
}

echo "qnty VM provenance verifier"
echo "host=$(hostname)"
echo "checked_at=$(date -u '+%Y-%m-%dT%H:%M:%SZ')"
echo "repo=$REPO_DIR"

if [ ! -d "$REPO_DIR/.git" ]; then
    fail "git repo not found at $REPO_DIR"
else
    cd "$REPO_DIR"

    HEAD_SHA="$(git rev-parse HEAD 2>/dev/null || true)"
    if [ -n "$HEAD_SHA" ]; then
        ok "git HEAD $HEAD_SHA"
    else
        fail "could not read git HEAD"
    fi

    NON_RUNTIME_STATUS="$(
        git status --short --untracked-files=no -- . ':!data/**' ':!output/**' ':!experiment_results/**' 2>/dev/null || true
    )"
    NON_RUNTIME_UNTRACKED="$(
        git ls-files --others --exclude-standard -- . ':!data/**' ':!output/**' ':!experiment_results/**' 2>/dev/null || true
    )"

    if [ -z "$NON_RUNTIME_STATUS" ] && [ -z "$NON_RUNTIME_UNTRACKED" ]; then
        ok "git worktree has no non-runtime drift"
    else
        fail "git worktree has non-runtime drift"
        if [ -n "$NON_RUNTIME_STATUS" ]; then
            echo "$NON_RUNTIME_STATUS"
        fi
        if [ -n "$NON_RUNTIME_UNTRACKED" ]; then
            echo "$NON_RUNTIME_UNTRACKED"
        fi
    fi
fi

for timer in "${TIMERS[@]}"; do
    state="$(systemctl is-active "$timer" 2>/dev/null || true)"
    if [ "$state" = "active" ]; then
        ok "$timer active"
    else
        fail "$timer state: ${state:-not-found}"
    fi
done

HEALTH_RESULT="$(systemctl show qnty-healthcheck.service -p Result --value 2>/dev/null || true)"
HEALTH_STATUS="$(systemctl show qnty-healthcheck.service -p ExecMainStatus --value 2>/dev/null || true)"
LATEST_HEALTH_LINE="$(
    journalctl -t qnty-healthcheck --no-pager -n 80 2>/dev/null \
        | grep -E 'qnty-healthcheck: (PASS|FAIL)' \
        | tail -1 || true
)"

if [ "$HEALTH_RESULT" = "success" ] && [ "$HEALTH_STATUS" = "0" ] && [[ "$LATEST_HEALTH_LINE" == *"PASS"* ]]; then
    ok "latest healthcheck PASS"
    info "$LATEST_HEALTH_LINE"
else
    fail "latest healthcheck not proven PASS (Result=${HEALTH_RESULT:-unknown}, ExecMainStatus=${HEALTH_STATUS:-unknown})"
    if [ -n "$LATEST_HEALTH_LINE" ]; then
        info "$LATEST_HEALTH_LINE"
    fi
fi

LATEST_OUTPUT="$(
    find "$OUTPUT_DIR" -maxdepth 1 -type f -printf '%TY-%Tm-%TdT%TH:%TM:%TSZ %p\n' 2>/dev/null \
        | sort \
        | tail -1 || true
)"
if [ -n "$LATEST_OUTPUT" ]; then
    ok "latest output exists: $LATEST_OUTPUT"
else
    fail "no output files found under $OUTPUT_DIR"
fi

DEPLOY_SHA_PATH="$STATE_DIR/deploy_sha"
AUTHORIZED_SHA_PATH="$STATE_DIR/authorized_sha"
START_DATE_PATH="$STATE_DIR/90d_start_date"

DEPLOY_SHA=""
AUTHORIZED_SHA=""

if [ -f "$DEPLOY_SHA_PATH" ]; then
    DEPLOY_SHA="$(read_file_trimmed "$DEPLOY_SHA_PATH")"
    ok "deploy_sha present: $DEPLOY_SHA"
else
    fail "missing $DEPLOY_SHA_PATH"
fi

if [ -f "$AUTHORIZED_SHA_PATH" ]; then
    AUTHORIZED_SHA="$(read_file_trimmed "$AUTHORIZED_SHA_PATH")"
    ok "authorized_sha present: $AUTHORIZED_SHA"
else
    fail "missing $AUTHORIZED_SHA_PATH"
fi

if [ -f "$START_DATE_PATH" ]; then
    ok "90d_start_date present: $(read_file_trimmed "$START_DATE_PATH")"
else
    fail "missing $START_DATE_PATH"
fi

if [ -n "${HEAD_SHA:-}" ] && [ -n "$DEPLOY_SHA" ]; then
    if [ "$HEAD_SHA" = "$DEPLOY_SHA" ]; then
        ok "git HEAD matches deploy_sha"
    else
        fail "git HEAD ($HEAD_SHA) does not match deploy_sha ($DEPLOY_SHA)"
    fi
fi

if [ -n "$DEPLOY_SHA" ] && [ -n "$AUTHORIZED_SHA" ]; then
    if [ "$DEPLOY_SHA" = "$AUTHORIZED_SHA" ]; then
        ok "deploy_sha matches authorized_sha"
    else
        fail "deploy_sha ($DEPLOY_SHA) does not match authorized_sha ($AUTHORIZED_SHA)"
    fi
fi

if [ "$FAIL" -eq 0 ]; then
    echo "VERDICT: PASS"
else
    echo "VERDICT: FAIL"
fi

exit "$FAIL"
