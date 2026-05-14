#!/usr/bin/env bash
# qnty-write-provenance-receipt.sh - Record VM observer provenance receipt.
# Writes only /srv/qnty/state provenance files. Does NOT restart services.
set -euo pipefail

ROOT_DIR="${QNTY_ROOT_DIR:-/srv/qnty}"
REPO_DIR="${QNTY_REPO_DIR:-$ROOT_DIR/repo}"
STATE_DIR="${QNTY_STATE_DIR:-$ROOT_DIR/state}"
OUTPUT_DIR="${QNTY_OUTPUT_DIR:-$ROOT_DIR/output/forward_obs_v1}"
FORCE="${FORCE:-0}"

DEPLOY_SHA_PATH="$STATE_DIR/deploy_sha"
AUTHORIZED_SHA_PATH="$STATE_DIR/authorized_sha"
START_DATE_PATH="$STATE_DIR/90d_start_date"
RECEIPT_PATH="$STATE_DIR/protocol_receipt.md"

TIMERS=(
    qnty-data-refresh.timer
    qnty-shadow-run.timer
    qnty-healthcheck.timer
    qnty-daily-summary.timer
)

SERVICES=(
    qnty-data-refresh.service
    qnty-shadow-run.service
    qnty-healthcheck.service
    qnty-daily-summary.service
)

refuse_overwrite() {
    local path="$1"
    if [ -e "$path" ] && [ "$FORCE" != "1" ]; then
        echo "Refusing to overwrite $path. Set FORCE=1 only after operator review." >&2
        exit 1
    fi
}

if [ ! -d "$REPO_DIR/.git" ]; then
    echo "Missing git repo at $REPO_DIR" >&2
    exit 1
fi

mkdir -p "$STATE_DIR"

for path in "$DEPLOY_SHA_PATH" "$AUTHORIZED_SHA_PATH" "$START_DATE_PATH" "$RECEIPT_PATH"; do
    refuse_overwrite "$path"
done

cd "$REPO_DIR"

COMMIT_SHA="$(git rev-parse HEAD)"
NOW_UTC="$(date -u '+%Y-%m-%dT%H:%M:%SZ')"
START_DATE="${START_DATE:-$(date -u '+%Y-%m-%d')}"
HOST="$(hostname)"
HEALTH_RESULT="$(systemctl show qnty-healthcheck.service -p Result --value 2>/dev/null || echo unknown)"
HEALTH_STATUS="$(systemctl show qnty-healthcheck.service -p ExecMainStatus --value 2>/dev/null || echo unknown)"
LATEST_HEALTH_LINE="$(
    journalctl -t qnty-healthcheck --no-pager -n 80 2>/dev/null \
        | grep -E 'qnty-healthcheck: (PASS|FAIL)' \
        | tail -1 || true
)"
LATEST_OUTPUT="$(
    find "$OUTPUT_DIR" -maxdepth 1 -type f -printf '%TY-%Tm-%TdT%TH:%TM:%TSZ %p\n' 2>/dev/null \
        | sort \
        | tail -1 || true
)"

printf '%s\n' "$COMMIT_SHA" > "$DEPLOY_SHA_PATH"
printf '%s\n' "${AUTHORIZED_SHA:-$COMMIT_SHA}" > "$AUTHORIZED_SHA_PATH"
printf '%s\n' "$START_DATE" > "$START_DATE_PATH"

{
    echo "# Qnty VM Observer Protocol Receipt"
    echo ""
    echo "- Generated at UTC: $NOW_UTC"
    echo "- Host: $HOST"
    echo "- Repo: $REPO_DIR"
    echo "- Commit SHA: $COMMIT_SHA"
    echo "- Authorized SHA: ${AUTHORIZED_SHA:-$COMMIT_SHA}"
    echo "- 90-day start date: $START_DATE"
    echo "- Latest healthcheck result: Result=$HEALTH_RESULT ExecMainStatus=$HEALTH_STATUS"
    if [ -n "$LATEST_HEALTH_LINE" ]; then
        echo "- Latest healthcheck line: $LATEST_HEALTH_LINE"
    fi
    if [ -n "$LATEST_OUTPUT" ]; then
        echo "- Latest output: $LATEST_OUTPUT"
    fi
    echo ""
    echo "## Qnty Units"
    for unit in "${SERVICES[@]}" "${TIMERS[@]}"; do
        echo "- $unit"
    done
    echo ""
    echo "## Unit File Hashes"
    for unit in "${SERVICES[@]}" "${TIMERS[@]}"; do
        fragment="$(systemctl show "$unit" -p FragmentPath --value 2>/dev/null || true)"
        if [ -n "$fragment" ] && [ -f "$fragment" ]; then
            sha="$(sha256sum "$fragment" | awk '{print $1}')"
            echo "- $unit: $sha  $fragment"
        else
            echo "- $unit: missing FragmentPath"
        fi
    done
    echo ""
    echo "## Interpretation Guardrail"
    echo ""
    echo "A qnty verdict of GO/PASSED means the observer's configured kill criteria"
    echo "were not triggered for this research run. It does not prove real-money"
    echo "profitability, deployment readiness, or live-trading approval."
} > "$RECEIPT_PATH"

echo "Wrote:"
echo "  $DEPLOY_SHA_PATH"
echo "  $AUTHORIZED_SHA_PATH"
echo "  $START_DATE_PATH"
echo "  $RECEIPT_PATH"
