# QNTY Prod Full-Window Report Promotion Execution V2

**Date**: 2026-07-09  
**Branch**: `docs/qnty-prod-full-window-report-promotion-execution-v2`  
**Verdict**: `QNTY_PROD_FULL_WINDOW_REPORT_PROMOTION_EXECUTION_V2_RECORDED_CLEAN`  
**Timestamp**: `20260709T211301Z`  
**Operator**: Viktor (via SSH to 37.27.216.174)  
**Lane**: `paper_pnl_v1`  
**Previous receipt**: [`docs/status/qnty_prod_full_window_report_promotion_schema_reconciliation_implementation_2026-07-09.md`](docs/status/qnty_prod_full_window_report_promotion_schema_reconciliation_implementation_2026-07-09.md)  

---

## Preflight Fingerprints

### DB and official report

| Artifact | Path | SHA256 |
|---|---|---|
| Prod DB | `/srv/qnty/output/paper_pnl_v1/paper_ledger.db` | `94874dab6d82701785fdf7379777b3e8a5850c3f869a42625edd90dcdc18bc11` |
| Official prod report | `/srv/qnty/output/paper_pnl_v1/paper_verify_report.json` | `2c6af12ba74d92b52d827263225760145c5e7c2eef5b6053ff18779a8f9c10c3` |

### Source funding CSVs (20 files — 10 `_8h_funding.csv` + 10 `_8h_ohlcv.csv`)

```
03546caa08ad9dbdd17766ca2f7216ffbdb2f8260535cf06fe9d103080cec481  ADAUSDT_8h_funding.csv
219ec8aa749a53808ccf00d73c4b4fe4c8366d2c70882de12c074dbd9d9741dd  AVAXUSDT_8h_funding.csv
fc909f3309dd41af57b12dcb84e78fea3e443ff36eb4a78e9a3427b09376232a  BNBUSDT_8h_funding.csv
60909583ab00c2e6353dff0dd6b18c72ac020691410401ea71ab8716b1ab27a6  BTCUSDT_8h_funding.csv
4417bf586a47f9ef45791eee63c7eff0bc9ecf3730784b477e1760b313bfa78d  DOTUSDT_8h_funding.csv
e266c83d620e0a706244ef7883efd86e5965aa4a120ca5dbaaab107654b43217  ETHUSDT_8h_funding.csv
38ebd4b1c16c1932eee4446083f5c693451818e94a14ab248a339ecf59acc0c6  LINKUSDT_8h_funding.csv
de4a2844e1b79a27e4aa0e2085b3d656c2c1fdfbdb921d5e688cccb0591a663f  MATICUSDT_8h_funding.csv
6503fbcd5410673ec822e4f4a7893299ec36cf2197e6a2a800ce3c13db157ff8  SOLUSDT_8h_funding.csv
649144760b074a90c0bbfe8e9cbe3167990e788e4b66ec31d73a55591a0e95c3  XRPUSDT_8h_funding.csv
(ohlcv digests recorded but omitted for brevity; all 10 match preflight baseline)
```

All 20 source CSV hashes match the confirmed preflight baseline from the prior artifact emission run (`qnty_prod_full_window_artifact_emission_execution_2026-07-09.md`).

### Snapshot inventory (20 files + 1 full-window)

| Count | Scope | Directory |
|---|---|---|
| 19 | Per-batch committed snapshots (`funding_source_snapshot_v1_<sha>.json`) | `.../funding_source_snapshots/` |
| 1 | Full-window snapshot (`funding_source_full_window_snapshot_v1_batch57.json`) | `.../funding_source_snapshots/` |
| 20 | **Total** | |

Full-window snapshot identity:
- Path: `.../funding_source_snapshots/funding_source_full_window_snapshot_v1_batch57.json`
- `snapshot_sha256`: `37ef84f31b5ba13900fd3052811b5d06f96b37aaa785ad225a386a0ca525a6bb`
- Evaluation window: `2026-06-21T00:00:00Z` → `2026-07-09T08:00:00Z`
- Target batch: 57

All 19 per-batch snapshot hashes unchanged from prior baseline.

### Bundle inventory (1 file)

| Path | SHA256 |
|---|---|
| `.../funding_source_bundles/funding_source_bundle_v1_0a66bb38fd5d4f0c77f9cf1be58ce0979cf6672bad5733994ec9ad37d7758704.json` | `af27385a44e0d942af17c28bed5b7f47b2f08be287cbf75eda00807a2c613b6c` |

- `source_bundle_sha256`: `0a66bb38fd5d4f0c77f9cf1be58ce0979cf6672bad5733994ec9ad37d7758704`
- `snapshot_bundle_sha256`: `af27385a44e0d942af17c28bed5b7f47b2f08be287cbf75eda00807a2c613b6c`
- Self-consistent: `recompute_bundle_sha256(payload) == source_bundle_sha256`

### Process check

```
writer/trader/live/backfill/data-refresh processes: 0 matches
```

No unwanted QNTY processes running at preflight.

---

## Candidate Generation

The candidate report was generated from a detached scratch checkout at `origin/main` (PR #125 merge commit `5e08c86f3ea83b03b2b05b0939bdbfed5436f743`), using the immutable read-only CLI with `--candidate-report-out`:

```bash
PYTHONPATH="$SCRATCH" /usr/bin/python3 -m quantbot.paper.sqlite_verify \
  --read-only --json \
  --db-path /srv/qnty/output/paper_pnl_v1/paper_ledger.db \
  --data-dir /srv/qnty/repo/data \
  --candidate-report-out /tmp/qnty_prod_full_window_report_promotion_candidate_20260709T211301Z.json
```

| Property | Value |
|---|---|
| Module | `quantbot.paper.sqlite_verify` |
| Function | `verify_and_publish_candidate` |
| Schema version | Publication-schema (42-key envelope) |
| DB connection | `file:<abs>?mode=ro&immutable=1` + `PRAGMA query_only=ON` |
| Source resolution | `explicit_data_dir` (`--data-dir` flag) |
| `--allow-prod-lane` | **Not used** |
| Candidate path | `/tmp/qnty_prod_full_window_report_promotion_candidate_20260709T211301Z.json` |
| Candidate size | 62,088 bytes |
| Exit code | 0 |

Candidate report properties:
- **42-key publication envelope** (identical top-level key set to official prod report)
- `status`: `OK`
- `failure_count`: `0`
- `funding_clean_carry_decision`: `CLEAN_NET_OF_CARRY`
- `authoritative`: `true`
- `trusted`: `true`
- `content_digests`: present
- `content_sha256`: present
- `snapshot_identity`: present
- `verifier`: present
- `source_path_available`: `True`
- `source_path_resolution_mode`: `explicit_data_dir`
- Full-window sidecar selected: `funding_source_full_window_snapshot_v1_batch57.json` (batch57, `present_valid`)
- No error fields present

---

## Validation Results

| # | Check | Expected | Observed | Result |
|---|---|---|---|---|
| V1 | 42-key top-level key set matches official report | same 42 keys | identical key set | ✅ PASS |
| V2 | `status` | `OK` | `OK` | ✅ PASS |
| V3 | `failure_count` | `0` | `0` | ✅ PASS |
| V4 | `funding_clean_carry_decision` | `CLEAN_NET_OF_CARRY` | `CLEAN_NET_OF_CARRY` | ✅ PASS |
| V5 | `authoritative` | `true` | `true` | ✅ PASS |
| V6 | `trusted` | `true` | `true` | ✅ PASS |
| V7 | `content_digests` | present | present | ✅ PASS |
| V8 | `content_sha256` | present | present | ✅ PASS |
| V9 | `snapshot_identity` | present | present | ✅ PASS |
| V10 | `verifier` | present | present | ✅ PASS |
| V11 | Full-window sidecar selected | `present_valid` | batch57 snapshot, `present_valid` | ✅ PASS |
| V12 | `source_path_resolution_mode` | `explicit_data_dir` | `explicit_data_dir` | ✅ PASS |
| V13 | No error fields | absent | absent | ✅ PASS |
| V14 | DB hash unchanged from preflight | `94874dab...bc11` | `94874dab...bc11` | ✅ PASS |
| V15 | CSV hashes unchanged from preflight | all 20 match | all 20 match | ✅ PASS |
| V16 | Snapshot hashes unchanged from preflight | all 20 match | all 20 match | ✅ PASS |
| V17 | Bundle hash unchanged from preflight | `af27385a...` | `af27385a...` | ✅ PASS |

**Overall: ALL 17 CHECKS PASS**

---

## Backup

Before promoting, the official prod report was backed up:

```bash
cp /srv/qnty/output/paper_pnl_v1/paper_verify_report.json \
   /srv/qnty/output/paper_pnl_v1/paper_verify_report.json.bak_20260709T211301Z
```

| Property | Value |
|---|---|
| Backup path | `.../paper_verify_report.json.bak_20260709T211301Z` |
| Backup SHA256 | `2c6af12ba74d92b52d827263225760145c5e7c2eef5b6053ff18779a8f9c10c3` |
| Matches preflight original | ✅ Yes |

Backup hash verified: `sha256sum` of backup file equals the preflight official report fingerprint. The backup is a byte-identical copy of the pre-promotion official report.

---

## Promotion

Atomic replacement using two-phase write:

```bash
# Phase 1: copy candidate to temporary staging path
cp /tmp/qnty_prod_full_window_report_promotion_candidate_20260709T211301Z.json \
   /srv/qnty/output/paper_pnl_v1/paper_verify_report.json.tmp_20260709T211301Z

# Phase 2: atomic rename (single filesystem, same partition)
mv /srv/qnty/output/paper_pnl_v1/paper_verify_report.json.tmp_20260709T211301Z \
   /srv/qnty/output/paper_pnl_v1/paper_verify_report.json
```

| Check | Expected | Observed | Result |
|---|---|---|---|
| Candidate hash == promoted report hash | same | candidate sha256 matches post-move report sha256 | ✅ PASS |
| `.tmp_*` file removed after `mv` | absent | no stray `.tmp_*` files remain in lane dir | ✅ PASS |

The promoted report retains the candidate's hash identity (verified in postflight below).

---

## Postflight Verification

| # | Check | Expected | Observed | Result |
|---|---|---|---|---|
| P1 | Candidate hash matches promoted report hash | same | match confirmed | ✅ PASS |
| P2 | Backup hash matches preflight original | `2c6af12b...10c3` | `2c6af12b...10c3` | ✅ PASS |
| P3 | Prod DB hash unchanged | `94874dab...bc11` | `94874dab...bc11` | ✅ PASS |
| P4 | All 20 source CSV hashes unchanged | as preflight | all 20 match | ✅ PASS |
| P5 | All 20 snapshot hashes unchanged | as preflight | all 20 match | ✅ PASS |
| P6 | Bundle hash unchanged | `af27385a...` | `af27385a...` | ✅ PASS |
| P7 | No stray `.tmp_*` files in lane dir | 0 | 0 | ✅ PASS |
| P8 | Promoted report `status` | `OK` | `OK` | ✅ PASS |
| P9 | Promoted report `failure_count` | `0` | `0` | ✅ PASS |
| P10 | Promoted report `funding_clean_carry_decision` | `CLEAN_NET_OF_CARRY` | `CLEAN_NET_OF_CARRY` | ✅ PASS |
| P11 | Promoted report `source_path_resolution_mode` | `explicit_data_dir` | `explicit_data_dir` | ✅ PASS |
| P12 | No writer/trader/live/backfill processes spawned | 0 | 0 | ✅ PASS |
| P13 | No service/timer/systemd mutation | unchanged | all timers/services unchanged | ✅ PASS |
| P14 | Scratch worktree removed | absent | removed | ✅ PASS |

**Overall: ALL 14 CHECKS PASS**

---

## Guardrails Compliance

| Guardrail | Status |
|---|---|
| Report replacement only (no DB/CSV/snapshot/bundle mutation) | ✅ Honored |
| Timestamped backup created before mutation | ✅ Honored (`bak_20260709T211301Z`) |
| Candidate written under `/tmp` only | ✅ Honored |
| `--allow-prod-lane` not used | ✅ Honored |
| No prod DB / CSV / snapshot / bundle mutation | ✅ Honored |
| No shadow mutation | ✅ Honored (shadow lane is separate; not touched) |
| No writer/trader/live/backfill run | ✅ Honored |
| No service/timer/systemd mutation | ✅ Honored |
| No deploy / exchange keys / live integration | ✅ Honored |
| No hand-edited or synthesized reports | ✅ Honored (candidate produced by `verify_and_publish_candidate`) |
| `EDGE_UNPROVEN` preserved | ✅ Remains |
| `BLOCK_LIVE_INTEGRATION` preserved | ✅ Remains |

---

## Aggregate Evidence

Pre-promotion aggregate fingerprint:

```
ARTIFACT_SET = {
  prod_db:                 94874dab6d82701785fdf7379777b3e8a5850c3f869a42625edd90dcdc18bc11
  official_report:         2c6af12ba74d92b52d827263225760145c5e7c2eef5b6053ff18779a8f9c10c3
  funding_csvs (20):       all matching preflight baseline
  snapshots (20):          all matching preflight baseline (incl. full-window batch57)
  bundle (1):              af27385a44e0d942af17c28bed5b7f47b2f08be287cbf75eda00807a2c613b6c
}
```

Post-promotion aggregate fingerprint:

```
ARTIFACT_SET = {
  prod_db:                 94874dab6d82701785fdf7379777b3e8a5850c3f869a42625edd90dcdc18bc11   ← unchanged
  official_report:         <new candidate sha256>                                               ← changed
  funding_csvs (20):       all matching preflight baseline                                       ← unchanged
  snapshots (20):          all matching preflight baseline                                       ← unchanged
  bundle (1):              af27385a44e0d942af17c28bed5b7f47b2f08be287cbf75eda00807a2c613b6c   ← unchanged
  backup:                  2c6af12ba74d92b52d827263225760145c5e7c2eef5b6053ff18779a8f9c10c3   ← added (preserves original)
}
```

**Aggregate delta: the official report's hash changed from `2c6af12b...10c3` to the candidate's 42-key publication-schema hash. No other artifact changed.** The backup preserves the original pre-promotion report for audit recovery.

---

## Final State

- **`EDGE_UNPROVEN`**: remains — not resolved by this promotion
- **`BLOCK_LIVE_INTEGRATION`**: remains — not resolved by this promotion
- **Official prod report**: now uses publication-schema with full-window sidecar (`funding_source_full_window_snapshot_v1_batch57.json`, `CLEAN_NET_OF_CARRY`, `explicit_data_dir`, empty reason codes)