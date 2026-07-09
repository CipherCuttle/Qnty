# QNTY_PROD_FULL_WINDOW_SNAPSHOT_BUNDLE_TMP_DRY_RUN

**Date:** 2026-07-09
**Run timestamp:** 2026-07-09T13:34:47Z
**Branch:** `docs/qnty-prod-full-window-snapshot-bundle-tmp-dry-run`
**HEAD:** `c8e26e2979ea85abcbb8cfb6c3641ff29d1c0441`
**VM:** `37.27.216.174` (`ubuntu-4gb-hel1-1-qnty`)

## Guardrails

| Guardrail | Status |
|-----------|--------|
| No prod DB mutation | ✅ UNCHANGED (`4b947feb...`) |
| No official report overwrite | ✅ UNCHANGED (`5bd406d6...`) |
| No source CSV mutation | ✅ All 10 CSV hashes UNCHANGED |
| No prod snapshot write | ✅ Prod snapshots dir UNCHANGED (18 files) |
| No prod bundle write | ✅ Prod bundles dir MISSING (unchanged) |
| No service/timer/cron mutation | ✅ No QNTY services running |
| No writer/trader/live/backfill run | ✅ No QNTY processes |
| `/srv/qnty/repo` main worktree not modified | ✅ Scratch worktree in /tmp, cleaned up |
| All artifacts under `/tmp` | ✅ `/tmp/qnty_prod_full_window_dry_run_20260709T133447/` |
| `EDGE_UNPROVEN` | ✅ Remains |
| `BLOCK_LIVE_INTEGRATION` | ✅ Remains |

## Preflight (Before)

| Artifact | SHA256 |
|----------|--------|
| Prod DB (`/srv/.../paper_ledger.db`) | `4b947febc8373ca065f9fdd5b8705dd311a1e2feba73e71cb714e6e73e432773` |
| Prod report (`/srv/.../paper_verify_report.json`) | `5bd406d6f4b2f8fa8c71d5f91c9e2865e997bcf917ddb9e359fecc7df9071d00` |
| Source CSVs (10 symbols) | All captured, unchanged throughout |
| Prod snapshots dir | 18 existing batch-scoped snapshots |
| Prod bundles dir | MISSING (expected — never created) |
| Running services | None |

## Emission: Full-Window Snapshot + Bundle

**Entry point:** Python API call to `emit_full_window_funding_source_snapshot()` via wrapper script

| Field | Value |
|-------|-------|
| **Snapshot path** | `/tmp/.../output/funding_source_snapshots/funding_source_full_window_snapshot_v1_batch56.json` |
| **Snapshot file hash** | `1e5961204504724af4d4edaa7c339bc2f59db90d55a4fd696de2c3635b90144d` |
| **Snapshot envelope hash** | `cf5609a7fa7fe9beb61a847725533414a5d75ad8068be965dde1d709bd4ba1d7` |
| **Snapshot size** | 93,191 bytes |
| **Snapshot scope** | `full_window` |
| **Snapshot write state** | `committed` |
| **Bundle path** | `/tmp/.../output/funding_source_bundles/funding_source_bundle_v1_65c6f0e3153ff1f174b894e73d713cd35b2e8c929b97b52e8a456250a8929c3a.json` |
| **Bundle file hash** | `85f8c5a74eccea1b9c405ef43d477152b8b2ed71337487b71fda50c6cd88cd79` |
| **Bundle size** | 80,536 bytes |
| **Target batch ID** | 56 |
| **Lane ID** | `paper_pnl_v1` |
| **Evaluation window** | `2026-06-21T00:00:00` → `2026-07-09T00:00:00` |
| **Source bundle SHA256** | `02d4e6a88b546d29f26ee9e1b2527b974e3658b412e08f4b4108636d0fcfbc8e` |
| **Coverage decision** | `complete` |
| **Reason codes** | `[]` (empty) |
| **Git commit** | `6c8799e6836f5cc0386394d71d4fceec70c9c1c1` |

## Verifier: Clean-Carry Evaluation

**Entry point:** `python -m quantbot.paper.sqlite_verify --read-only --json`

| Field | Value |
|-------|-------|
| **`funding_clean_carry_decision`** | **`CLEAN_NET_OF_CARRY`** |
| **`funding_clean_carry_reason_codes`** | **`[]`** (empty) |
| **`funding_clean_carry_status`** | `clean_net_of_carry` |
| **`funding_source_snapshot_window_mismatch`** | **GONE** |
| **`source_path_unavailable`** | **GONE** (`source_path_available: true`) |
| **`full_window_snapshot_selected_path`** | `/tmp/.../funding_source_full_window_snapshot_v1_batch56.json` |
| **`funding_coverage_decision`** | `complete` |
| **Latest batch** | 56 |
| **Batches** | 56 |
| **Events** | 314 |
| **Failure count** | 0 |
| **Resum check** | OK (tolerance 1e-06) |

### Batch-scoped note

The batch-scoped verifier shows `CAVEATED_ENGINE_SEMANTICS` with reason code `funding_source_snapshot_path_outside_snapshot_dir`. This is expected: the DB's batch-snapshot reference field points to the prod path, not the /tmp path. This resolves automatically when the full-window sidecar is placed in the correct prod location.

## Verdict

```
QNTY_PROD_FULL_WINDOW_SNAPSHOT_BUNDLE_TMP_DRY_RUN_RECORDED_CLEAN
```

### Key findings

1. **`funding_source_snapshot_window_mismatch` is GONE** — the full-window snapshot scope matches the full-ledger window, so the window-mismatch reason code no longer fires.
2. **`source_path_unavailable` is GONE** — the full-window emission captures source file availability at emit time, resolving the previous `source_path_unavailable` that affected batch-scoped snapshots.
3. **`CLEAN_NET_OF_CARRY` is reached** — the full-window snapshot + bundle path produces a clean verifier candidate ready for prod promotion.
4. **All artifacts are /tmp-only** — no prod lane was touched.
5. **No services, no deploy, no live integration** — `EDGE_UNPROVEN` and `BLOCK_LIVE_INTEGRATION` remain.

## Next Logical Step

The emit module needs a CLI entry point (`--emit-full-window` flag or standalone script) so it can be run against prod without writing a wrapper. After that, the /tmp candidate can be promoted to a prod lane artifact through the standard official report promotion workflow.