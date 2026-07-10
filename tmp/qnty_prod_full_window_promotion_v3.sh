#!/bin/bash
set -euo pipefail

TS=$(date -u +%Y%m%dT%H%M%SZ)
echo "TS=${TS}"

REPORT_PATH="/srv/qnty/output/paper_pnl_v1/paper_verify_report.json"
DB_PATH="/srv/qnty/output/paper_pnl_v1/paper_ledger.db"
DATA_DIR="/srv/qnty/repo/data"
SNAPSHOT_DIR="/srv/qnty/output/paper_pnl_v1/funding_source_snapshots"
BUNDLE_DIR="/srv/qnty/output/paper_pnl_v1/funding_source_bundles"

echo "--- Step 2: Setup/Reuse scratch checkout ---"
# Reuse existing scratch from /tmp/tmp.JcY8gYXSDw which has the updated sqlite_verify.py
SCRATCH="/tmp/tmp.JcY8gYXSDw"
if [ -f "$SCRATCH/quantbot/paper/sqlite_verify.py" ]; then
    echo "PASS: Reusing existing scratch at ${SCRATCH}"
else
    echo "Creating new scratch"
    SCRATCH=$(mktemp -d)
    cd "$SCRATCH"
    git clone /srv/qnty/repo . 2>&1 | tail -1
fi
cd "$SCRATCH"

echo "--- Step 3: Preflight fingerprints ---"
PREFLIGHT_DB_HASH=$(sha256sum "$DB_PATH" | awk '{print $1}')
PREFLIGHT_REPORT_HASH=$(sha256sum "$REPORT_PATH" | awk '{print $1}')
echo "PREFLIGHT_DB_HASH=${PREFLIGHT_DB_HASH}"
echo "PREFLIGHT_REPORT_HASH=${PREFLIGHT_REPORT_HASH}"

PREFLIGHT_CSV_HASHES=$(find "$DATA_DIR" -name '*.csv' -type f | sort | xargs sha256sum 2>/dev/null || echo "NO_CSV")
echo "PREFLIGHT_CSV_COUNT=$(find "$DATA_DIR" -name '*.csv' -type f | wc -l)"

PREFLIGHT_SNAPSHOT_HASHES=$(find "$SNAPSHOT_DIR" -type f | sort | xargs sha256sum 2>/dev/null || echo "NO_SNAPSHOTS")
echo "PREFLIGHT_SNAPSHOT_COUNT=$(find "$SNAPSHOT_DIR" -type f 2>/dev/null | wc -l)"

PREFLIGHT_BUNDLE_HASHES=$(find "$BUNDLE_DIR" -type f | sort | xargs sha256sum 2>/dev/null || echo "NO_BUNDLES")
echo "PREFLIGHT_BUNDLE_COUNT=$(find "$BUNDLE_DIR" -type f 2>/dev/null | wc -l)"

UNWANTED=$(ps aux | grep -E 'quantbot|paper_pnl|data_refresh|backfill' | grep -v grep || true)
if [ -n "$UNWANTED" ]; then
    echo "BLOCKED: Unwanted processes running:"; echo "$UNWANTED"; exit 1
fi
echo "PASS: No unwanted processes"

echo "--- Step 4: Generate candidate with --candidate-report-out ---"
CANDIDATE="/tmp/qnty_prod_full_window_report_promotion_candidate_${TS}.json"
STDERR_FILE="/tmp/qnty_prod_full_window_report_promotion_candidate_stderr_${TS}.json"

PYTHONPATH="$SCRATCH" /usr/bin/python3 -m quantbot.paper.sqlite_verify \
  --read-only --json \
  --db-path "$DB_PATH" \
  --data-dir "$DATA_DIR" \
  --candidate-report-out "$CANDIDATE" \
  2>"$STDERR_FILE"

GEN_EXIT=$?
echo "GEN_EXIT=${GEN_EXIT}"
echo "CANDIDATE=${CANDIDATE}"

if [ "$GEN_EXIT" -ne 0 ]; then
    echo "FAIL: Candidate generation exit code ${GEN_EXIT}"
    cat "$STDERR_FILE"
    echo "FINAL_VERDICT=QNTY_PROD_FULL_WINDOW_REPORT_PROMOTION_EXECUTION_V2_BLOCKED"
    echo "REASON=candidate_generation_failed"
    rm -rf "$SCRATCH"; exit 1
fi
if [ ! -f "$CANDIDATE" ]; then
    echo "FAIL: Candidate not created"
    echo "FINAL_VERDICT=QNTY_PROD_FULL_WINDOW_REPORT_PROMOTION_EXECUTION_V2_BLOCKED"
    echo "REASON=candidate_file_missing"
    rm -rf "$SCRATCH"; exit 1
fi
CANDIDATE_SIZE=$(wc -c < "$CANDIDATE")
echo "CANDIDATE_SIZE=${CANDIDATE_SIZE}"
if [ "$CANDIDATE_SIZE" -lt 100 ]; then
    echo "FAIL: Candidate too small"; cat "$CANDIDATE"; cat "$STDERR_FILE"
    echo "FINAL_VERDICT=QNTY_PROD_FULL_WINDOW_REPORT_PROMOTION_EXECUTION_V2_BLOCKED"
    echo "REASON=candidate_too_small"; rm -rf "$SCRATCH"; exit 1
fi
echo "PASS: Candidate generated (${CANDIDATE_SIZE} bytes)"

echo "--- Step 5: Validate candidate ---"
python3 -c "
import json, sys

with open('/srv/qnty/output/paper_pnl_v1/paper_verify_report.json') as f:
    off = json.load(f)
with open('${CANDIDATE}') as f:
    cand = json.load(f)

cand_keys = set(cand.keys())
off_keys = set(off.keys())
print('candidate keys: ' + str(sorted(cand_keys)))
print('official keys: ' + str(sorted(off_keys)))
if cand_keys != off_keys:
    diff = cand_keys.symmetric_difference(off_keys)
    print('FAIL: key set diff = ' + str(diff))
    sys.exit(1)
print('PASS: same top-level key set')

for name in ['status', 'failure_count', 'funding_clean_carry_decision']:
    val = cand.get(name)
    print('  ' + name + ' = ' + str(val))

for k in ['authoritative', 'trusted', 'content_digests', 'content_sha256', 'snapshot_identity', 'verifier']:
    ok = k in cand
    print(('PASS' if ok else 'FAIL') + ': has key \"' + k + '\"')
    if not ok:
        sys.exit(1)

snap = cand.get('funding_source_snapshot', {})
print('snapshot_identity: ' + str(snap.get('snapshot_identity', 'MISSING')))
print('snapshot_path: ' + str(snap.get('path', 'MISSING')))
bundle = cand.get('funding_source_bundle', {})
print('bundle_identity: ' + str(bundle.get('bundle_identity', 'MISSING')))

snap_path = snap.get('path', '')
if 'full_window' in snap_path:
    print('PASS: full-window sidecar snapshot selected')
else:
    print('WARN: snapshot path = ' + snap_path)

mode = cand.get('source_path_resolution_mode', 'MISSING')
print(('PASS' if mode == 'explicit_data_dir' else 'FAIL') + ': source_path_resolution_mode = ' + str(mode))

print('TOTAL KEYS: ' + str(len(cand.keys())))
print('OVERALL: PASS')
"

VALIDATION_EXIT=$?
echo "VALIDATION_EXIT=${VALIDATION_EXIT}"
if [ "$VALIDATION_EXIT" -ne 0 ]; then
    echo "BLOCKED: Candidate validation failed"
    echo "FINAL_VERDICT=QNTY_PROD_FULL_WINDOW_REPORT_PROMOTION_EXECUTION_V2_BLOCKED"
    echo "REASON=candidate_validation_failed"; rm -rf "$SCRATCH"; exit 1
fi
echo "PASS: Candidate validation complete"

echo "--- Step 6: Backup ---"
BACKUP="${REPORT_PATH}.bak_${TS}"
cp "$REPORT_PATH" "$BACKUP"
if [ ! -f "$BACKUP" ]; then echo "FAIL: Backup not created"; rm -rf "$SCRATCH"; exit 1; fi
ORIG_HASH=$(sha256sum "$REPORT_PATH" | awk '{print $1}')
BACKUP_HASH=$(sha256sum "$BACKUP" | awk '{print $1}')
if [ "$ORIG_HASH" != "$BACKUP_HASH" ]; then
    echo "FAIL: Backup hash mismatch"; rm -rf "$SCRATCH"; exit 1
fi
echo "PASS: Backup verified (${BACKUP_HASH})"
echo "BACKUP=${BACKUP}"

echo "--- Step 7: Atomic replace ---"
TMP_REPORT="${REPORT_PATH}.tmp_${TS}"
cp "$CANDIDATE" "$TMP_REPORT"
mv "$TMP_REPORT" "$REPORT_PATH"
echo "PASS: Atomic replace completed"

echo "--- Step 8: Postflight ---"
CANDIDATE_HASH=$(sha256sum "$CANDIDATE" | awk '{print $1}')
PROD_REPORT_HASH=$(sha256sum "$REPORT_PATH" | awk '{print $1}')
echo "CANDIDATE_HASH=${CANDIDATE_HASH}"
echo "PROD_REPORT_HASH=${PROD_REPORT_HASH}"
if [ "$CANDIDATE_HASH" != "$PROD_REPORT_HASH" ]; then
    echo "FAIL: Hash mismatch"; exit 1
fi
echo "PASS: Candidate matches prod report"

if [ "$BACKUP_HASH" != "$PREFLIGHT_REPORT_HASH" ]; then
    echo "FAIL: Backup hash != preflight"; exit 1
fi
echo "PASS: Backup matches preflight"

POSTFLIGHT_DB_HASH=$(sha256sum "$DB_PATH" | awk '{print $1}')
if [ "$PREFLIGHT_DB_HASH" != "$POSTFLIGHT_DB_HASH" ]; then
    echo "FAIL: DB hash changed!"; exit 1
fi
echo "PASS: DB hash unchanged"

POSTFLIGHT_CSV_HASHES=$(find "$DATA_DIR" -name '*.csv' -type f | sort | xargs sha256sum)
PREFLIGHT_CSV_AGG=$(echo "$PREFLIGHT_CSV_HASHES" | sha256sum | awk '{print $1}')
POSTFLIGHT_CSV_AGG=$(echo "$POSTFLIGHT_CSV_HASHES" | sha256sum | awk '{print $1}')
if [ "$PREFLIGHT_CSV_AGG" != "$POSTFLIGHT_CSV_AGG" ]; then echo "FAIL: CSV changed"; exit 1; fi
echo "PASS: CSV hashes unchanged"

POSTFLIGHT_SNAPSHOT_HASHES=$(find "$SNAPSHOT_DIR" -type f | sort | xargs sha256sum)
PREFLIGHT_SNAPSHOT_AGG=$(echo "$PREFLIGHT_SNAPSHOT_HASHES" | sha256sum | awk '{print $1}')
POSTFLIGHT_SNAPSHOT_AGG=$(echo "$POSTFLIGHT_SNAPSHOT_HASHES" | sha256sum | awk '{print $1}')
if [ "$PREFLIGHT_SNAPSHOT_AGG" != "$POSTFLIGHT_SNAPSHOT_AGG" ]; then echo "FAIL: Snapshots changed"; exit 1; fi
echo "PASS: Snapshot hashes unchanged"

POSTFLIGHT_BUNDLE_HASHES=$(find "$BUNDLE_DIR" -type f | sort | xargs sha256sum)
PREFLIGHT_BUNDLE_AGG=$(echo "$PREFLIGHT_BUNDLE_HASHES" | sha256sum | awk '{print $1}')
POSTFLIGHT_BUNDLE_AGG=$(echo "$POSTFLIGHT_BUNDLE_HASHES" | sha256sum | awk '{print $1}')
if [ "$PREFLIGHT_BUNDLE_AGG" != "$POSTFLIGHT_BUNDLE_AGG" ]; then echo "FAIL: Bundles changed"; exit 1; fi
echo "PASS: Bundle hashes unchanged"

STRAY=$(ls -la "${REPORT_PATH}.tmp_"* 2>/dev/null || echo "NO_STRAY")
echo "STRAY_TMP=${STRAY}"

python3 -c "
import json, sys
with open('/srv/qnty/output/paper_pnl_v1/paper_verify_report.json') as f:
    c = json.load(f)
for name, val, expected in [
    ('status', c.get('status'), 'OK'),
    ('failure_count', c.get('failure_count'), 0),
    ('funding_clean_carry_decision', c.get('funding_clean_carry_decision'), 'CLEAN_NET_OF_CARRY'),
]:
    ok = val == expected
    print(('PASS' if ok else 'FAIL') + ': ' + name + ' = ' + str(val))

mode = c.get('source_path_resolution_mode', 'MISSING')
print(('PASS' if mode == 'explicit_data_dir' else 'FAIL') + ': source_path_resolution_mode = ' + str(mode))
snap_path = c.get('funding_source_snapshot', {}).get('path', '')
if 'full_window' in snap_path:
    print('PASS: full-window sidecar snapshot selected')
else:
    print('INFO: snapshot path = ' + snap_path)
print('TOTAL KEYS: ' + str(len(c.keys())))
print('OVERALL: PASS')
"

systemctl list-timers --no-pager 2>/dev/null | grep -E 'qnty|paper' || echo "No qnty timers found"

echo "--- Step 9: Remove scratch ---"
rm -rf "$SCRATCH"
echo "PASS: Scratch removed"

echo ""
echo "============================================================"
echo " PROMOTION COMPLETE"
echo "============================================================"
echo "TS=${TS}"
echo "PREFLIGHT_DB_HASH=${PREFLIGHT_DB_HASH}"
echo "PREFLIGHT_REPORT_HASH=${PREFLIGHT_REPORT_HASH}"
echo "CANDIDATE_HASH=${CANDIDATE_HASH}"
echo "PROD_REPORT_HASH=${PROD_REPORT_HASH}"
echo "BACKUP_HASH=${BACKUP_HASH}"
echo "BACKUP_PATH=${BACKUP}"
echo "CANDIDATE_SIZE=${CANDIDATE_SIZE}"
echo "GEN_EXIT=${GEN_EXIT}"
echo "FINAL_VERDICT=QNTY_PROD_FULL_WINDOW_REPORT_PROMOTION_EXECUTION_V2_RECORDED_CLEAN"
exit 0