# Shadow Lane Batch12 Manual Phase3 Receipt

## 1. Purpose

Record the explicitly authorized one-bar shadow-lane writer run for batch12.
This receipt is an operational paper-diagnostics receipt only. It does not make
an edge claim, does not make a profitability claim, and does not authorize or
perform live trading.

## 2. Authorization Context

- Task: `AUTHORIZE_SHADOW_BATCH12_ONE_BAR_WRITER_ONCE`
- Prior gate verdict: `READ_ONLY_BATCH12_ONE_BAR_AUTHORIZATION_READY`
- Authorized writer scope: exactly one shadow writer invocation for the missing
  shadow bar `2026-07-01T16:00:00`.
- Expected new shadow batch: `12`
- Expected committed bar count: `1`
- Expected event count: verify from writer output and DB.
- Preserved edge status: `EDGE_UNPROVEN`
- Preserved funding verdict: `CAVEATED_ENGINE_SEMANTICS`

## 3. Correct VM Target

Used only:

```bash
ssh -i ~/.ssh/hetzner_qnty_key -o IdentitiesOnly=yes viktor@37.27.216.174
```

The forbidden `192.168.1.100` target was not used.

VM identity at preflight:

- Hostname: `ubuntu-4gb-hel1-1-qnty`
- UTC time: `2026-07-02T00:55:22Z`
- Sweden time: `2026-07-02T02:55:22+0200`

## 4. Preflight State

Local repo preflight:

- Branch: `main`
- `HEAD`: `29a23a3191f3448f8fc06383879e87337d31ffa9`
- `origin/main`: `29a23a3191f3448f8fc06383879e87337d31ffa9`
- Tracked and staged diff: none
- Allowed untracked path present: `.claude/`
- PR #38 reconciliation receipt present in history:
  `fd644dc docs: reconcile asserted-identity PnL after shadow batch11 (#38)`
- PR #39 corrected batch11 receipt present at `HEAD`:
  `29a23a3 docs: correct shadow batch11 receipt values (#39)`

VM lane preflight:

- Prod DB: `/srv/qnty/output/paper_pnl_v1/paper_ledger.db`
- Shadow DB: `/srv/qnty/output/paper_pnl_null_shadow_v0/paper_ledger.db`
- Live forward_obs: `/srv/qnty/output/forward_obs_v1`
- Prod watermark: `2026-07-01T16:00:00`
- Forward_obs latest timestamp: `2026-07-01T16:00:00`
- Shadow watermark before writer: `2026-07-01T08:00:00`
- Prod latest batch before writer: `34`
- Shadow latest batch before writer: `11`
- Expected next shadow batch: `12`
- Missing shadow bars from forward_obs after shadow watermark: exactly
  `["2026-07-01T16:00:00"]`
- Prod `PRAGMA integrity_check`: `ok`
- Shadow `PRAGMA integrity_check`: `ok`

## 5. Timer State

No QNTY service was running before the writer.

Writer/data timers were outside the dangerous near-trigger window:

- `qnty-data-refresh.timer`: last `2026-07-02 00:05:34 UTC`, next
  `2026-07-02 08:05:08 UTC`, service `inactive/dead`
- `qnty-shadow-run.timer`: last `2026-07-02 00:11:25 UTC`, next
  `2026-07-02 08:11:26 UTC`, service `inactive/dead`
- `qnty-paper-pnl.timer`: last `2026-07-02 00:22:03 UTC`, next
  `2026-07-02 08:20:47 UTC`, service `inactive/dead`

Read-only/observability timers were recorded but not treated as writer/data
collision risk because no service was active:

- `qnty-watermark-watchdog.timer`: last `2026-07-02 00:01:51 UTC`, next
  `2026-07-02 01:00:11 UTC`, service `inactive/dead`
- `qnty-healthcheck.timer`: last `2026-07-02 00:04:48 UTC`, next
  `2026-07-02 04:04:37 UTC`, service `inactive/dead`
- `qnty-health-receipt.timer`: last `2026-07-02 00:32:34 UTC`, next
  `2026-07-02 08:31:56 UTC`, service `inactive/dead`
- `qnty-daily-summary.timer`: last `2026-07-01 17:00:13 UTC`, next
  `2026-07-02 17:00:00 UTC`, service `inactive/dead`

No QNTY service was running after the writer and after the no-emit verifiers.

## 6. DB Identity Assertion

Shadow DB identity from the DB before writing:

- DB path: `/srv/qnty/output/paper_pnl_null_shadow_v0/paper_ledger.db`
- `lane_id`: `paper_pnl_null_shadow_v0`
- `strategy_id`: `matched_null_shadow_v0`
- Version: `0.0.0-shadow`
- Actual identity `config_hash`: `50b1bbeff42d33f4413776ea14cc06281b275b346ab79c279baf959b58ae024c`
- `config_hash_v2`: `50b1bbeff42d33f4413776ea14cc06281b275b346ab79c279baf959b58ae024c`
- Legacy/batch `config_hash`: `32c0fbccdf46af8b50ef0e6d2da9a76657038da621ff2be1dba95d82208d5d52`
- `forward_start_ts`: `2026-06-24T16:00:00`

The run recorded the DB-provided identity hash `50b1...024c`; it did not assume
the legacy batch hash `32c0...d5d52`.

## 7. Mutation Guards Before And After

Before writer:

```txt
de5df1193c2094b2bda8fc1509f2c6c71365ef14e9e0aea5e8691fa5c7b6b67f  /srv/qnty/output/paper_pnl_v1/paper_ledger.db
8ed3fd9a2e506a9bafa1bdc17f1cbe31bddd6984c375e34a116efa5b93c9998c  /srv/qnty/output/paper_pnl_null_shadow_v0/paper_ledger.db
624ba43740c340b231700204861af5aab2a22484d14a43b555f2d6bb07473847  /srv/qnty/output/forward_obs_v1 fingerprint
```

After writer:

```txt
de5df1193c2094b2bda8fc1509f2c6c71365ef14e9e0aea5e8691fa5c7b6b67f  /srv/qnty/output/paper_pnl_v1/paper_ledger.db
0b32bf072c2a01a397d7d743f42aece8c5d65b9479491fb74e14f721f28127cc  /srv/qnty/output/paper_pnl_null_shadow_v0/paper_ledger.db
624ba43740c340b231700204861af5aab2a22484d14a43b555f2d6bb07473847  /srv/qnty/output/forward_obs_v1 fingerprint
```

After no-emit verifiers:

```txt
de5df1193c2094b2bda8fc1509f2c6c71365ef14e9e0aea5e8691fa5c7b6b67f  /srv/qnty/output/paper_pnl_v1/paper_ledger.db
0b32bf072c2a01a397d7d743f42aece8c5d65b9479491fb74e14f721f28127cc  /srv/qnty/output/paper_pnl_null_shadow_v0/paper_ledger.db
624ba43740c340b231700204861af5aab2a22484d14a43b555f2d6bb07473847  /srv/qnty/output/forward_obs_v1 fingerprint
```

Interpretation:

- Prod DB checksum stayed unchanged.
- Live forward_obs fingerprint stayed unchanged.
- Shadow DB checksum changed as expected from the authorized shadow writer.

## 8. Frozen Forward_Obs Snapshot

Frozen snapshot path:

```txt
/tmp/qnty_shadow_batch12_manual_run_v0/forward_obs_v1_frozen
```

The run-specific temp dir `/tmp/qnty_shadow_batch12_manual_run_v0` was removed
and recreated before copying.

Snapshot verification:

- Frozen latest timestamp: `2026-07-01T16:00:00`
- Frozen file count: `9`
- Live absolute mutation guard fingerprint:
  `624ba43740c340b231700204861af5aab2a22484d14a43b555f2d6bb07473847`
- Live relative metadata fingerprint:
  `fb6a39e1afc2c11817f18f9d0bab99997bfd72cc8f0b4f4e89557b5d2dfc9950`
- Frozen relative metadata fingerprint:
  `fb6a39e1afc2c11817f18f9d0bab99997bfd72cc8f0b4f4e89557b5d2dfc9950`
- Live relative content fingerprint:
  `f7a6687d612a2c9071e153c468f71bc65ce9a64ca5e44f5c434fff309863df2d`
- Frozen relative content fingerprint:
  `f7a6687d612a2c9071e153c468f71bc65ce9a64ca5e44f5c434fff309863df2d`

Live and frozen fingerprints matched at copy time.

## 9. Exact Writer Command

The shadow writer was invoked exactly once:

```bash
cd /srv/qnty/repo

QNTY_PAPER_OUTPUT_DIR=/srv/qnty/output/paper_pnl_null_shadow_v0 \
/srv/qnty/venv/bin/python scripts/qnty-paper-sqlite-accounting.py \
  --db-path /srv/qnty/output/paper_pnl_null_shadow_v0/paper_ledger.db \
  --forward-obs-dir /tmp/qnty_shadow_batch12_manual_run_v0/forward_obs_v1_frozen \
  --data-dir /srv/qnty/repo/data \
  --json
```

No prod writer, data refresh, timer mutation, service start/stop/restart,
install, migration, `ALTER`, or manual WAL checkpoint was run.

## 10. Writer Output

```json
{
  "status_code": 0,
  "status_message": "Committed batch 12: 1 bars, 4 events"
}
```

Shell exit status:

```txt
WRITER_EXIT_STATUS=0
```

## 11. Batch12 DB Verification

Shadow batch12 verification from the DB:

- Batch exists exactly once: yes
- Latest shadow batch after writer: `12`
- Shadow batch count after writer: `12`
- Batch12 `prior_watermark_bar_ts`: `2026-07-01T08:00:00`
- Batch12 `new_watermark_bar_ts`: `2026-07-01T16:00:00`
- Batch12 `committed_bar_count`: `1`
- Batch12 `event_count`: `4`
- Batch12 `first_event_seq`: `81`
- Batch12 `last_event_seq`: `84`
- Batch12 `git_sha`: `fde43a511ef98d7292a6bd93dd9e198ea92f79fe`
- Batch12 `committed_at`: `2026-07-02T00:56:10Z`
- Shadow DB `PRAGMA integrity_check` after writer: `ok`

Latest shadow equity snapshot after writer:

- `bar_ts`: `2026-07-01T16:00:00`
- `batch_id`: `12`
- `seq`: `84`
- `bar_commit_id`: `402491cfaaed99cf`

## 12. Latest Shadow PnL After Batch12

Paper diagnostics only:

- Initial equity: `10000.0`
- Latest shadow equity: `10026.40724116`
- Paper PnL absolute vs initial: `26.407241159999103`
- Paper PnL percent vs initial: `0.264072411599991%`
- Realized gross PnL: `-17.81922092`
- Unrealized PnL: `47.39184279`
- Funding cumulative: `0.67429032`
- Fees cumulative: `2.49109039`
- Open positions count: `1`
- Latest snapshot `num_open`: `1`

This is not an edge claim and not a profitability claim.

## 13. Prod Unchanged Verification

Prod DB checksum before and after:

```txt
de5df1193c2094b2bda8fc1509f2c6c71365ef14e9e0aea5e8691fa5c7b6b67f
```

Prod state after writer:

- Latest prod batch: `34`
- Prod batch count: `34`
- Prod watermark: `2026-07-01T16:00:00`
- Latest prod equity: `10011.07395842`
- Prod `PRAGMA integrity_check`: `ok`

## 14. Live Forward_Obs Unchanged Verification

Live forward_obs fingerprint before and after:

```txt
624ba43740c340b231700204861af5aab2a22484d14a43b555f2d6bb07473847
```

Live forward_obs after writer:

- Latest timestamp: `2026-07-01T16:00:00`
- File count: `9`

## 15. Verifier Results

No-emit verifier command shape:

```bash
/srv/qnty/venv/bin/python scripts/qnty-paper-sqlite-verify.py \
  --db-path <db> \
  --no-emit \
  --json
```

Shadow verifier:

- Exit: `0`
- Status: `OK`
- Failure count: `0`
- `query_only`: `1`
- Batches: `12`
- Events: `84`
- Equity rows: `22`
- Watermark: `2026-07-01T16:00:00`
- `report_path`: `null`
- Funding coverage verdict: `CAVEATED_ENGINE_SEMANTICS`

Prod verifier:

- Exit: `0`
- Status: `OK`
- Failure count: `0`
- `query_only`: `1`
- Batches: `34`
- Events: `142`
- Equity rows: `34`
- Watermark: `2026-07-01T16:00:00`
- `report_path`: `null`
- Funding coverage verdict: `CAVEATED_ENGINE_SEMANTICS`

## 16. Overlap Comparison

Recomputed from asserted-identity `equity_snapshots` only. Paper diagnostics
only; this is not edge evidence.

- First shared timestamp: `2026-06-24T16:00:00`
- Latest shared timestamp: `2026-07-01T16:00:00`
- Latest shared includes `2026-07-01T16:00:00`: yes
- Prod start equity: `9984.66610097`
- Prod end equity: `10011.07395842`
- Prod delta equity: `26.407857449999938`
- Shadow start equity: `10000.0`
- Shadow end equity: `10026.40724116`
- Shadow delta equity: `26.407241159999103`
- Prod-minus-shadow delta equity: `0.0006162900008348515`

## 17. Funding Caveat

The no-emit verifiers returned:

- Funding coverage verdict: `CAVEATED_ENGINE_SEMANTICS`
- Diagnostic label:
  `missing_funding_treated_as_zero_like_current_engine_not_net_of_carry_clean`

Shadow missing funding windows reported by verifier:

- `SOLUSDT|2026-06-27T08:00:00|exit`
- `SOLUSDT|2026-06-30T16:00:00`

Prod reported the same SOLUSDT caveat windows plus complete coverage for the
other reported symbols.

## 18. EDGE Status

`EDGE_UNPROVEN`

This receipt does not validate or invalidate strategy edge.

## 19. Scope And Exclusions

Performed:

- One explicit shadow writer invocation for batch12.
- Read-only preflight and postflight checks.
- Frozen forward_obs copy under `/tmp/qnty_shadow_batch12_manual_run_v0`.
- No-emit read-only verifiers for shadow and prod.
- Local docs-only receipt creation.

Excluded:

- No prod writer.
- No data refresh.
- No second shadow writer invocation.
- No rerun.
- No mutation of live forward_obs.
- No mutation of prod DB.
- No timer changes.
- No service start, stop, or restart.
- No dependency install.
- No DB migration or `ALTER`.
- No manual WAL checkpoint.
- No live trading authorization or action.

## 20. Verdict

`SHADOW_BATCH12_ONE_BAR_COMMITTED_RECEIPT_READY_FOR_PR`
