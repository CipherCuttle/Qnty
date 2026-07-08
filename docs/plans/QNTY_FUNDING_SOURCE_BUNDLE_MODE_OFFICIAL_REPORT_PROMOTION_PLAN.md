# QNTY Funding Source Bundle Mode Official Report Promotion Plan

**Plan ID:** `FUNDING_SOURCE_BUNDLE_MODE_OFFICIAL_REPORT_PROMOTION_PLAN_GIT_OWNED`

**Status:** Plan only — no code, test, config, DB, report, service, timer, or deployment changes. No mutation of real DB, source CSVs, or official report. No writers, traders, backfills, or live runs.

**Author:** System orchestrator (PR #107 + #108 + #109 post-merge)

**Created:** 2026-07-08

## 1. Preconditions

All of the following must be true before promotion execution begins:

| # | Precondition | Evidence |
|---|-------------|----------|
| 1 | PR #107 merged (`funding_source_immutable_bundle_semantics`) | `origin/main` includes the commit |
| 2 | PR #108 merged (copied-DB immutable bundle dry run receipt) | `origin/main` includes the commit |
| 3 | PR #109 merged (metadata-aligned bundle copied-DB dry run receipt) | `origin/main` includes commit `5ca4a86` |
| 4 | Copied metadata-aligned bundle dry run reached `CLEAN_NET_OF_CARRY` | [`docs/status/funding_source_metadata_aligned_bundle_copied_db_dry_run_2026-07-08.md`](docs/status/funding_source_metadata_aligned_bundle_copied_db_dry_run_2026-07-08.md) |
| 5 | Real DB snapshot digest known (before any promotion mutation) | record via `sha256sum` |
| 6 | Real counterparty CSVs known (digest + path) | record via `sha256sum` |
| 7 | Current official shadow verifier report path and hash known | record via `sha256sum` |
| 8 | Bundle mode verifier available (`source_mode="bundle"`) | confirmed by PR #107 + #109 |
| 9 | Current branch is NOT main — promotion uses a dedicated execution branch | branch name recorded |
| 10 | Sufficient disk space for backup + candidate report + working bundle | verify via `df -h` |

## 2. Real-Lane Promotion Strategy

1. **Do not patch the real DB** unless separately authorized by a scoped execution plan. This plan only authorizes **verification** against the real DB, not mutation.
2. **Inspect real-lane snapshot identity** — verify that the real-lane snapshot DB already has identity consistent with the real lane (not a copied/diverged lane). This is a read-only check.
3. **Build/write immutable bundle under real shadow lane** only if separately authorized by a follow-up execution task. Bundle building requires careful path selection and must write to a temporary location first.
4. **Run fresh verifier** in `source_mode="bundle"` against the real shadow DB. Produce a candidate report.
5. **Candidate report must be written to `/tmp` first.** Never write directly to the official report path.
6. **Official report replacement only after all candidate acceptance gates pass.**

## 3. Candidate Acceptance Gates

The candidate report must satisfy ALL of the following before any promotion action:

| # | Gate | Check |
|---|------|-------|
| 1 | `VerifyResult.status = OK` | JSON field `.status` |
| 2 | `failure_count = 0` | JSON field `.failure_count` |
| 3 | `source_resolution_mode = "bundle"` | JSON field `.source_resolution_mode` |
| 4 | Full-ledger `funding_clean_carry_status = "clean_net_of_carry"` | JSON field `.funding_clean_carry_status` |
| 5 | `funding_clean_carry_decision = "CLEAN_NET_OF_CARRY"` | JSON field `.funding_clean_carry_decision` |
| 6 | `reason_codes = []` | JSON field `.reason_codes` |
| 7 | No `funding_source_file_digest_mismatch` anywhere in report | search report for this string |
| 8 | No snapshot path/lane/DB identity mismatch | verify snapshot identity fields match real lane |
| 9 | Report exposes bundle path, bundle hash, and source identity | JSON fields `.bundle_path`, `.bundle_hash`, `.source_identity` |
| 10 | Real DB unchanged after verifier run | compare pre/post `sha256sum` of real DB |
| 11 | Source CSVs unchanged after verifier run | compare pre/post `sha256sum` of source CSVs |
| 12 | Official report NOT touched during verification | verify mtime/hash unchanged |
| 13 | Verifier ran in read-only mode | confirm `source_mode="bundle"` with no write flags |
| 14 | No unexpected files created outside /tmp and verified artifact paths | `find` check for new files |

## 4. Backup / Restore

1. **Before any replacement**, back up the current official report:
   ```bash
   cp <official_report_path> <official_report_path>.backup.<TIMESTAMP>
   sha256sum <official_report_path>.backup.<TIMESTAMP>
   ```
2. Record backup hash and path in execution receipt.
3. **Replacement must be atomic**: use `cp` then `mv` to the target, or equivalent atomic write.
4. After replacement, record post-replacement official report hash:
   ```bash
   sha256sum <official_report_path>
   ```
5. **Rollback path**: If promoted report fails post-promotion validation, restore from backup:
   ```bash
   cp <official_report_path>.backup.<TIMESTAMP> <official_report_path>
   ```
6. Post-rollback hash must match pre-promotion hash.

## 5. Stop Conditions

Execution MUST stop immediately if ANY of the following occur:

1. Any real DB mutation is required unexpectedly (outside the explicit read-only scope).
2. The verifier refuses to run, produces caveats, or returns a non-OK status.
3. Bundle write would touch an unexpected path (e.g., not under a designated temp or shadow directory).
4. The candidate report differs from expectation for unexplained reasons.
5. Any service, timer, cron, systemd, or daemon mutation is required.
6. Any attempt to weaken `EDGE_UNPROVEN` or `BLOCK_LIVE_INTEGRATION` is made.
7. Source CSVs must be modified or frozen without separate prior authorization.
8. The real DB identity check fails (lane/DB mismatch suggests the wrong DB).
9. Disk space is insufficient for backup + candidate.
10. Pre/post hashes of any protected artifact diverge unexpectedly.
11. Network/VM/hardware anomalies during execution.
12. The execution branch is not clean (uncommitted changes).
13. Any step would require exchange keys, API tokens, or live market access.
14. Any step would require modifying the immutable bundle building code.

## 6. Verification Commands

All commands must be run and their output recorded in the execution receipt.

### Pre-execution state

```bash
# Git state
cd /home/swirky/DevHub/repos/Qnty
git log --oneline -5
git branch --show-current
git status --short

# Real DB hash
sha256sum <real_db_path>

# Source CSV hashes
sha256sum <source_csv_path_1>
sha256sum <source_csv_path_2>

# Current official report hash
sha256sum <official_report_path>

# Disk space
df -h <data_mount_point>

# VM runtime
python3 --version
pip3 show quantbot 2>/dev/null | head -5
```

### Candidate verifier command

```bash
cd /home/swirky/DevHub/repos/Qnty
python -m scripts.qnty-paper-sqlite-verify \
    --db <real_shadow_db_path> \
    --source-mode bundle \
    --report-out /tmp/candidate_official_report_<TIMESTAMP>.json
```

### Post-execution verification

```bash
# Candidate report hash
sha256sum /tmp/candidate_official_report_<TIMESTAMP>.json

# Official report backup hash
sha256sum <official_report_path>.backup.<TIMESTAMP>

# Official report final hash (after promotion)
sha256sum <official_report_path>

# Verify no real DB mutation
sha256sum <real_db_path>   # must match pre-execution

# Verify no source CSV mutation
sha256sum <source_csv_path_1>   # must match pre-execution
sha256sum <source_csv_path_2>   # must match pre-execution

# Verify no unexpected file changes
git status --short   # should show only the promoted report file

# Candidate acceptance gates script
python -c "
import json
with open('/tmp/candidate_official_report_<TIMESTAMP>.json') as f:
    r = json.load(f)
assert r['status'] == 'OK', f'status={r[\"status\"]}'
assert r['failure_count'] == 0, f'failure_count={r[\"failure_count\"]}'
assert r['source_resolution_mode'] == 'bundle', f'mode={r[\"source_resolution_mode\"]}'
assert r['funding_clean_carry_status'] == 'clean_net_of_carry'
assert r['funding_clean_carry_decision'] == 'CLEAN_NET_OF_CARRY'
assert r['reason_codes'] == []
print('ALL CANDIDATE ACCEPTANCE GATES PASSED')
"
```

## 7. Verdict Options

On completion, record one of the following verdicts:

### `FUNDING_SOURCE_BUNDLE_MODE_OFFICIAL_REPORT_PROMOTION_PLAN_RECORDED`

Recorded when the plan is written to the repo and pushed, passing docs-only verification. No execution performed — this is a plan only.

### `FUNDING_SOURCE_BUNDLE_MODE_OFFICIAL_REPORT_PROMOTION_PLAN_BLOCKED`

Recorded if the plan cannot be written due to a discovered blocker (e.g., missing precondition, conflicting plan, process violation).

## 8. Non-Goals

This plan explicitly does NOT authorize:

- Any mutation of the real DB, source CSVs, or official report
- Any code, test, config, or deployment changes
- Any service, timer, cron, systemd, or daemon modifications
- Any writer, trader, backfill, or live runs
- Any source-freeze or source modification
- Any weakening of `EDGE_UNPROVEN` or `BLOCK_LIVE_INTEGRATION`
- Any exchange API access or live integration
- Any production deployment
- Any backfill, recompute, or data migration
- Any changes to the immutable bundle building infrastructure

## 9. References

- [PR #107 — Immutable funding-source bundle semantics](https://github.com/CipherCuttle/Qnty/pull/107)
- [PR #108 — Copied-DB immutable bundle dry run](https://github.com/CipherCuttle/Qnty/pull/108)
- [PR #109 — Metadata-aligned bundle copied-DB dry run](https://github.com/CipherCuttle/Qnty/pull/109)
- [Metadata-aligned bundle dry run status](docs/status/funding_source_metadata_aligned_bundle_copied_db_dry_run_2026-07-08.md)
- [Immutable bundle semantics spec](docs/specs/funding_source_immutable_bundle_semantics_v0.md)
- [Prior shadow official report promotion plan](docs/plans/QNTY_FUNDING_SOURCE_SHADOW_OFFICIAL_REPORT_PROMOTION_PLAN.md)