# Funding-Source Bundle-Mode Official Report Promotion — Rerun After PR #115 Superset Fix

**Task:** `FUNDING_SOURCE_BUNDLE_MODE_OFFICIAL_REPORT_PROMOTION_RERUN_AFTER_SUPERSET_FIX_GIT_OWNED`
**Date (UTC):** 2026-07-08
**Verdict:** `FUNDING_SOURCE_BUNDLE_MODE_OFFICIAL_REPORT_PROMOTION_RERUN_AFTER_SUPERSET_RECORDED_CLEAN`

Guardrails preserved: `EDGE_UNPROVEN`, `BLOCK_LIVE_INTEGRATION`. `CLEAN_NET_OF_CARRY`
means only "not killed by this verifier gate" — not edge/profit/live approval.

---

## PLAN

Re-run the real shadow official report promotion in **bundle mode** after PR #115
merged, expecting the covering-superset window gate to now accept the bundle evaluation
window (2026-06-25 → 2026-07-05) as covering batch 17 (2026-07-03 → 2026-07-05).
Produce a candidate report to `/tmp` first; back up and atomically replace the official
shadow report **only if all acceptance gates pass**; otherwise stop with a blocked
verdict. Reuse the existing immutable full-ledger bundle from the prior attempts.
Read-only on all real DBs/CSVs; docs-only change in git.

---

## CHANGESET

### Scope

| Item | Action |
|------|--------|
| `/srv/qnty/output/paper_pnl_null_shadow_v0/paper_verify_report.json` | Atomically replaced (bundle-mode verification) |
| `/srv/qnty/output/paper_pnl_null_shadow_v0/backups/paper_verify_report_20260708T232217Z_653605a76fdd0b8117c8373c9dadd3fcd41bed147778920c82f29f19f14e0ffd.json` | Backup created |
| `/tmp/qnty-candidate-report.json` | Scratch candidate |
| `/tmp/qnty-candidate-stdout.txt` | Scratch log |
| `/tmp/qnty-gates-result.json` | Scratch gate results |
| `/tmp/qnty-scratch-QJ7weS` | Detached scratch worktree |
| `docs/status/funding_source_bundle_mode_official_report_promotion_rerun_after_superset_2026-07-09.md` | This receipt |

### What Was NOT Touched

- Real shadow DB: not modified
- Source CSVs (10): not modified
- Bundle: not modified
- Sidecar: not modified
- Prod DB: not touched (N/A)
- Writer/trader/live/backfill: not run
- Systemd timers/services: not modified
- `/srv/qnty/repo` main worktree: not modified
- Exchange keys: not accessed
- Live integration: blocked (`BLOCK_LIVE_INTEGRATION` remains)

---

## EXECUTION

### Setup

- **Branch:** `docs/funding-source-bundle-mode-official-report-promotion-rerun-after-superset`
- **PR #115 merge commit:** `45bbb502e30c9c862127018e668396a699041c6a`
- **PR #114 merge commit:** `10e152f0d3a42c948103c10c404ecb12ee3dab16`
- **PR #113 merge commit:** `b44f3def743c9043ab57351e86caf57c52ab39a4`
- **VM:** `viktor@37.27.216.174`
- **Scratch worktree:** `/tmp/qnty-scratch-QJ7weS` at `origin/main` commit `45bbb50`
- **Editable-install workaround:** dropped `__editable__` meta-path finder, prepended scratch worktree to `sys.path`, confirmed `quantbot.__file__` resolves to scratch tree
- **Real shadow DB path:** `/srv/qnty/output/paper_pnl_null_shadow_v0/paper_ledger.db`
- **Official report path:** `/srv/qnty/output/paper_pnl_null_shadow_v0/paper_verify_report.json`

### Preflight Hashes

| Artifact | SHA256 | Expected | Match |
|----------|--------|----------|-------|
| Real shadow DB | `00a4817e1d49aef51398fe0022cc2f3754302bc12f445912d4eb0d0596fc21ce` | `00a4817e...` | ✅ |
| Stale official report | `653605a76fdd0b8117c8373c9dadd3fcd41bed147778920c82f29f19f14e0ffd` | `653605a7...` | ✅ |
| Selected sidecar | `7c5068afef44fc360e88bbde126d892c538973e8f98cbd32dfd0a63ae310ab66` | `7c5068af...` | ✅ |
| Bundle file | `aaa12ea0ab368cd3f34a6c30fcf37c56213cd3e1bd29751e042a7a0dbeb8414b` | `aaa12ea0...` | ✅ |
| Source bundle SHA | `37f6fb596bd44d63dd7e5efee26ca08e50fcc0785561c25cc6ac384fbfd27cf4` | `37f6fb...` | ✅ |
| Snapshot bundle SHA | `8b9d80408b5aae517ba745a5072d9f7d09125572a23ea5e792e2d80e9c099d69` | `8b9d80...` | ✅ |
| Selected batch | 17 | 17 | ✅ |

### Bundle Identity

- `source_bundle_sha256`: `37f6fb596bd44d63dd7e5efee26ca08e50fcc0785561c25cc6ac384fbfd27cf4` ✅
- `snapshot_bundle_sha256`: `8b9d80408b5aae517ba745a5072d9f7d09125572a23ea5e792e2d80e9c099d69` ✅
- Bundle evaluation window: `2026-06-25T08:00:00Z` → `2026-07-05T16:00:00Z`
- Batch 17 window: `2026-07-03T08:00:00` → `2026-07-05T16:00:00`
- Bundle window covers batch 17: ✅ (exact boundary match at end)

### Candidate Verifier Result

| Field | Value |
|-------|-------|
| `status` | `OK` |
| `failure_count` | `0` |
| `funding_clean_carry.source_resolution_mode` | `bundle` |
| `funding_clean_carry_decision` | `CLEAN_NET_OF_CARRY` |
| `funding_clean_carry.reason_codes` | `[]` |
| Batch 17 stamp — `source_resolution_mode` | `bundle` |
| Batch 17 stamp — `decision` | `CLEAN_NET_OF_CARRY` |
| Batch 17 stamp — `reason_codes` | `[]` |
| Bundle path | `/srv/qnty/output/paper_pnl_null_shadow_v0/funding_source_bundles/funding_source_bundle_v1_37f6fb596bd44d63dd7e5efee26ca08e50fcc0785561c25cc6ac384fbfd27cf4.json` |
| `source_bundle_sha256` | `37f6fb596bd44d63dd7e5efee26ca08e50fcc0785561c25cc6ac384fbfd27cf4` |

### Acceptance Gate Table

| Gate | Result |
|------|--------|
| `verifier_status_OK` | ✅ PASS |
| `failure_count_zero` | ✅ PASS |
| `full_ledger_source_mode_bundle` | ✅ PASS |
| `full_ledger_decision_clean` | ✅ PASS |
| `full_ledger_reasons_empty` | ✅ PASS |
| `batch_stamp_bundle_mode` | ✅ PASS |
| `batch_stamp_decision_clean` | ✅ PASS |
| `no_digest_mismatch` | ✅ PASS |
| `no_window_mismatch` | ✅ PASS |
| `no_row_digest_mismatch` | ✅ PASS |
| `no_path_outside_snapshot_dir` | ✅ PASS |
| `no_snapshot_db_mismatch` | ✅ PASS |
| `report_exposes_bundle_info` | ✅ PASS |

**Overall: ALL GATES PASS**

### Official Report Backup

- **Backup path:** `/srv/qnty/output/paper_pnl_null_shadow_v0/backups/paper_verify_report_20260708T232217Z_653605a76fdd0b8117c8373c9dadd3fcd41bed147778920c82f29f19f14e0ffd.json`
- **Backup SHA:** `653605a76fdd0b8117c8373c9dadd3fcd41bed147778920c82f29f19f14e0ffd` (matches old report)

### Official Report Final Hash

```
9985842ac4488c4109c5d5f4652096c01fcaa9f2d7b2716ec5e464af2c739e91
```

### Post-Run Integrity Hashes

| Artifact | SHA256 | Status |
|----------|--------|--------|
| Real DB | `00a4817e1d49aef51398fe0022cc2f3754302bc12f445912d4eb0d0596fc21ce` | Unchanged |
| Official report | `9985842ac4488c4109c5d5f4652096c01fcaa9f2d7b2716ec5e464af2c739e91` | New |
| Bundle | `aaa12ea0ab368cd3f34a6c30fcf37c56213cd3e1bd29751e042a7a0dbeb8414b` | Unchanged |
| Backup (old report) | `653605a76fdd0b8117c8373c9dadd3fcd41bed147778920c82f29f19f14e0ffd` | Preserved |
| Source CSVs (10) | All unchanged | Unchanged |

---

## VERIFY

### Preflight Integrity

All 7 preflight hashes matched expected values. Selected batch was 17.

### Candidate Verification

The verifier ran with `source_resolution_mode=bundle`, targeting batch 17.
- `status`: `OK`
- `failure_count`: `0`
- `funding_clean_carry_decision`: `CLEAN_NET_OF_CARRY`
- All 13 acceptance gates passed.

### Backup and Atomic Replace

The stale official report (`653605a7...`) was backed up and the new report
(`9985842a...`) was atomically written to the official path.

### Post-Run Integrity

Real DB, bundle, and source CSVs all unchanged. Only the official report changed.

---

## VERDICT

**FUNDING_SOURCE_BUNDLE_MODE_OFFICIAL_REPORT_PROMOTION_RERUN_AFTER_SUPERSET_RECORDED_CLEAN**

All 13 acceptance gates passed. The official shadow report now reflects:

- `source_resolution_mode: "bundle"`
- `funding_clean_carry_decision: "CLEAN_NET_OF_CARRY"`
- Bundle identity: `37f6fb...` (source) / `8b9d80...` (snapshot)
- Batch 17: clean carry, bundle mode, no mismatches

### Recommended Next Action

- Review merged PR #115 output for correctness
- Validate that shadow verifier auto-run picks up the new report on next timer
- After sufficient observation, consider whether `EDGE_UNPROVEN` can be resolved
- Official shadow report now reflects `source_resolution_mode: "bundle"` and `CLEAN_NET_OF_CARRY` at batch 17 scope

### Guardrails

- `EDGE_UNPROVEN` — remains in place
- `BLOCK_LIVE_INTEGRATION` — remains in place
- `CLEAN_NET_OF_CARRY` — verifier-level only, not edge/profit/live approval