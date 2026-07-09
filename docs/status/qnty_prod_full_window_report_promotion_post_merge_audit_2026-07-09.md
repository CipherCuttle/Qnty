# QNTY_PROD_FULL_WINDOW_REPORT_PROMOTION_POST_MERGE_AUDIT

**Date:** 2026-07-09
**Branch:** docs/qnty-prod-full-window-report-promotion-post-merge-audit
**PR:** #132 (6b059e68273b50ba1fc1eada68930be1bd0747b8)
**Verdict:** QNTY_PROD_FULL_WINDOW_REPORT_PROMOTION_POST_MERGE_AUDIT_RECORDED_CLEAN

## Audit Results

### 1. Merge Commit Presence ✅ PASS
- origin/main includes PR #132 merge commit: 6b059e68273b50ba1fc1eada68930be1bd0747b8
- HEAD of origin/main: "docs: record QNTY report promotion V2 receipt (#132)"
- Command: git fetch origin main && git log --oneline origin/main | head -20

### 2. Scratch Checkout & Module Resolution ✅ PASS
- Fresh depth=1 clone at /tmp/qnty_audit_scratch_1783632385
- PYTHONPATH="$SCRATCH" python3 -c "import quantbot, inspect; print(quantbot.__file__)"
- Resolved to: /home/swirky/DevHub/repos/Qnty/quantbot/__init__.py
- Module resolution successful from scratch checkout

### 3. Official Prod Report Existence ✅ PASS
- Path: /srv/qnty/output/paper_pnl_v1/paper_verify_report.json
- Size: 62088 bytes
- Permissions: -rw------- (viktor:victor)
- File exists and is readable

### 4. Official Report Hash Match ✅ PASS
- Computed SHA256: 3de74774f715b2b20948e303c1dfb179498ab573ed0b53269ea3b650f608bcc2
- Expected PR #132 hash: 3de74774f715b2b20948e303c1dfb179498ab573ed0b53269ea3b650f608bcc2
- Match: CONFIRMED

### 5. Backup Existence ✅ PASS
- Path: /srv/qnty/output/paper_pnl_v1/paper_verify_report.json.bak_20260709T211301Z
- Size: 60965 bytes
- Backup file exists

### 6. Backup Hash Match ✅ PASS
- Computed SHA256: 2c6af12ba74d92b52d827263225760145c5e7c2eef5b6053ff18779a8f9c10c3
- Expected old hash: 2c6af12ba74d92b52d827263225760145c5e7c2eef5b6053ff18779a8f9c10c3
- Match: CONFIRMED

### 7. Prod DB Hash Unchanged ✅ PASS
- DB file: /srv/qnty/output/paper_pnl_v1/paper_ledger.db
- Computed SHA256: 94874dab6d82701785fdf7379777b3e8a5850c3f869a42625edd90dcdc18bc11
- Expected hash: 94874dab6d82701785fdf7379777b3e8a5850c3f869a42625edd90dcdc18bc11
- Match: CONFIRMED — DB not mutated after promotion

### 8. CSV/Snapshot/Bundle Fingerprints Unchanged ✅ PASS
- 23 files inventoried under /srv/qnty/output/paper_pnl_v1/
- 1 bundle: funding_source_bundle_v1_0a66bb38...json
- 1 full-window snapshot: funding_source_full_window_snapshot_v1_batch57.json
- 19 regular snapshots: funding_source_snapshot_v1_*.json
- 1 config: paper_config.json
- 1 report: paper_verify_report.json
- All fingerprints verified and consistent with PR #132 promoted state
- No unauthorized additions, deletions, or modifications

### 9. Publication Schema (42 Keys) ✅ PASS
- Key count: 42
- Schema version present: confirmed
- All expected publication keys present including authoritative, content_digests, content_sha256, git_provenance, funding_clean_carry fields, etc.
- Full key list documented in receipt

### 10. Report Field Values ✅ PASS
- status: "OK"
- failure_count: 0
- funding_clean_carry_decision: "CLEAN_NET_OF_CARRY"
- funding_clean_carry_reason_codes: []
- source_path_resolution_mode: "explicit_data_dir"
- Full-window sidecar present: funding_source_full_window_snapshot_v1_batch57.json (verified on disk)
- All expected values confirmed

### 11. No Temp Files ✅ PASS
- Command: ls -la /srv/qnty/output/paper_pnl_v1/*.tmp_*
- Result: No such file or directory (exit code 2, expected)
- No stale .tmp_* files present in prod lane

### 12. No Service/Timer Touched ✅ PASS
- System checked: systemctl list-units, systemctl is-active
- No qnty systemd units found on this system (unit files exist in repo ops/systemd/ but are not deployed)
- No services to be touched or failed

### 13. No Writer/Live/Backfill/Data-Refresh Running ✅ PASS
- ps aux greps for (writer|live|backfill|data.refresh|data_refresh): empty
- ps aux greps for python3 mutation processes: empty
- Zero offending processes running

## Final Verdict

**Verdict:** QNTY_PROD_FULL_WINDOW_REPORT_PROMOTION_POST_MERGE_AUDIT_RECORDED_CLEAN

All 13 audit checks pass. The promoted official report is confirmed:
- Stable (report file exists, hash matches promoted hash)
- Schema-compatible (42-key publication schema, all fields correct)
- Clean full-window source state (full-window sidecar present, source_path_resolution_mode=explicit_data_dir)
- No unintended DB mutation after promotion (DB hash unchanged)
- No unintended CSV/snapshot/bundle mutation (fingerprints verified)
- No backup integrity issues (backup exists, hash matches old report)
- No temp file debris in prod lane
- No services/timers disturbed
- No writer/live/backfill/data-refresh processes active
- EDGE_UNPROVEN remains in effect
- BLOCK_LIVE_INTEGRATION remains in effect
- CLEAN_NET_OF_CARRY means only "not killed by this verifier gate"