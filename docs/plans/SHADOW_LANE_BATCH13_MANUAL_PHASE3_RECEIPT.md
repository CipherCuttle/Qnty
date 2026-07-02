# Shadow Lane Batch13 Manual Phase3 Receipt

## 1. Purpose

Record the explicitly authorized one-bar shadow-lane writer run for batch13.
This receipt is an operational paper-diagnostics receipt only. It does not make
an edge claim, does not make a profitability claim, and does not authorize or
perform live trading.

## 2. Authorization Context

- Task: `AUTHORIZE_SHADOW_BATCH13_ONE_BAR_WRITER_ONCE`
- Prior gate verdict: `READ_ONLY_BATCH13_ONE_BAR_AUTHORIZATION_READY`
- Authorized writer scope: exactly one shadow writer invocation for the missing
  shadow bar `2026-07-02T00:00:00`.
- Expected new shadow batch: `13`
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
- UTC time: `2026-07-02T10:21:01Z`
- Sweden time: `2026-07-02T12:21:01+0200`

## 4. Preflight State

Local repo preflight:

- Branch: `main`
- `HEAD`: `732993e253ae959f9f1344fa629f785f74eafd0d`
- `origin/main`: `732993e253ae959f9f1344fa629f785f74eafd0d`
- Tracked and staged diff: none
- Allowed untracked path present: `.claude/`
- PR #40 batch12 receipt merge present at `HEAD`:
  `732993e docs: add shadow lane batch12 manual receipt (#40)`
- Required receipt files present on `main`:
  - `docs/plans/SHADOW_LANE_BATCH11_MANUAL_PHASE3_RECEIPT.md`
  - `docs/plans/QNTY_V1_SHADOW_ASSERTED_IDENTITY_PNL_RECONCILIATION_AFTER_BATCH11.md`
  - `docs/plans/SHADOW_LANE_BATCH12_MANUAL_PHASE3_RECEIPT.md`

VM lane preflight:

- Prod DB: `/srv/qnty/output/paper_pnl_v1/paper_ledger.db`
- Shadow DB: `/srv/qnty/output/paper_pnl_null_shadow_v0/paper_ledger.db`
- Live forward_obs: `/srv/qnty/output/forward_obs_v1`
- Prod watermark: `2026-07-02T00:00:00`
- Forward_obs latest timestamp: `2026-07-02T00:00:00`
- Shadow watermark before writer: `2026-07-01T16:00:00`
- Prod latest batch before writer: `35`
- Shadow latest batch before writer: `12`
- Expected next shadow batch: `13`
- Missing shadow bars from forward_obs after shadow watermark: exactly
  `["2026-07-02T00:00:00"]`
- Prod `PRAGMA integrity_check`: `ok`
- Shadow `PRAGMA integrity_check`: `ok`

## 5. Timer State

No QNTY service was running before the writer.

Writer/data timers were outside the dangerous near-trigger window:

- `qnty-data-refresh.timer`: last `2026-07-02 08:05:21 UTC`, next
  `2026-07-02 16:05:03 UTC`, service `inactive/dead`
- `qnty-shadow-run.timer`: last `2026-07-02 08:11:34 UTC`, next
  `2026-07-02 16:10:47 UTC`, service `inactive/dead`
- `qnty-paper-pnl.timer`: last `2026-07-02 08:20:49 UTC`, next
  `2026-07-02 16:20:46 UTC`, service `inactive/dead`

Read-only/observability timers were recorded but not treated as writer/data
collision risk because no service was active:

- `qnty-watermark-watchdog.timer`: last `2026-07-02 10:01:25 UTC`, next
  `2026-07-02 11:00:31 UTC`, service `inactive/dead`
- `qnty-healthcheck.timer`: last `2026-07-02 08:02:34 UTC`, next
  `2026-07-02 12:00:44 UTC`, service `inactive/dead`
- `qnty-health-receipt.timer`: last `2026-07-02 08:32:01 UTC`, next
  `2026-07-02 16:31:08 UTC`, service `inactive/dead`
- `qnty-daily-summary.timer`: last `2026-07-01 17:00:13 UTC`, next
  `2026-07-02 17:00:00 UTC`, service `inactive/dead`

No QNTY service was running after the writer and after the no-emit verifiers.

## 6. DB Identity Assertion

Shadow DB identity from the DB before writing:

- DB path: `/srv/qnty/output/paper_pnl_null_shadow_v0/paper_ledger.db`
- `lane_id`: `paper_pnl_null_shadow_v0`
- `strategy_id`: `matched_null_shadow_v0`
- Version: `0.0.0-shadow`
- DB `config_hash`: `32c0fbccdf46af8b50ef0e6d2da9a76657038da621ff2be1dba95d82208d5d52`
- DB `config_hash_v2`: `50b1bbeff42d33f4413776ea14cc06281b275b346ab79c279baf959b58ae024c`
- `pre_registration_hash`: `null`
- `forward_start_ts`: `2026-06-24T16:00:00`

Both config hash fields were read from the current shadow DB before writing;
the run did not assume values from old receipts.

## 7. Mutation Guards Before And After

Before writer:

```txt
9ffd1abcbc50257c4d9823c2bb325121da36affe21659aba8b873b526e04172a  /srv/qnty/output/paper_pnl_v1/paper_ledger.db
0b32bf072c2a01a397d7d743f42aece8c5d65b9479491fb74e14f721f28127cc  /srv/qnty/output/paper_pnl_null_shadow_v0/paper_ledger.db
49023abca62ee710aa07eeb4b857fcc86383ce6f538c4c3dc31729151c487beb  /srv/qnty/output/forward_obs_v1 fingerprint
```

After writer, before no-emit verifiers:

```txt
9ffd1abcbc50257c4d9823c2bb325121da36affe21659aba8b873b526e04172a  /srv/qnty/output/paper_pnl_v1/paper_ledger.db
075762a4f79d96b50f6a057f5a858f434d1187e181dbfa6d50f193d44600f5a5  /srv/qnty/output/paper_pnl_null_shadow_v0/paper_ledger.db
49023abca62ee710aa07eeb4b857fcc86383ce6f538c4c3dc31729151c487beb  /srv/qnty/output/forward_obs_v1 fingerprint
```

After no-emit verifiers:

```txt
9ffd1abcbc50257c4d9823c2bb325121da36affe21659aba8b873b526e04172a  /srv/qnty/output/paper_pnl_v1/paper_ledger.db
075762a4f79d96b50f6a057f5a858f434d1187e181dbfa6d50f193d44600f5a5  /srv/qnty/output/paper_pnl_null_shadow_v0/paper_ledger.db
49023abca62ee710aa07eeb4b857fcc86383ce6f538c4c3dc31729151c487beb  /srv/qnty/output/forward_obs_v1 fingerprint
```

Interpretation:

- Prod DB checksum stayed unchanged.
- Live forward_obs fingerprint stayed unchanged.
- Shadow DB checksum changed as expected from the authorized shadow writer.

## 8. Frozen Forward_Obs Snapshot

Frozen snapshot path:

```txt
/tmp/qnty_shadow_batch13_manual_run_v0/forward_obs_v1_frozen
```

The run-specific temp dir `/tmp/qnty_shadow_batch13_manual_run_v0` was removed
and recreated before copying.

Snapshot verification:

- Frozen latest timestamp: `2026-07-02T00:00:00`
- Frozen file count: `9`
- Live absolute mutation guard fingerprint:
  `49023abca62ee710aa07eeb4b857fcc86383ce6f538c4c3dc31729151c487beb`
- Live relative metadata fingerprint:
  `1fd04026364e0fd0ecf9d6b7eb2ad660f36ca5a10d5d187f54761f27a487aa23`
- Frozen relative metadata fingerprint:
  `1fd04026364e0fd0ecf9d6b7eb2ad660f36ca5a10d5d187f54761f27a487aa23`
- Live relative content fingerprint:
  `918758d326512a7cf8b634386566295eb8d8a8e68fa6c7ce4ae2705711189273`
- Frozen relative content fingerprint:
  `918758d326512a7cf8b634386566295eb8d8a8e68fa6c7ce4ae2705711189273`

Live and frozen fingerprints matched at copy time.

## 9. Exact Writer Command

The shadow writer was invoked exactly once:

```bash
cd /srv/qnty/repo

QNTY_PAPER_OUTPUT_DIR=/srv/qnty/output/paper_pnl_null_shadow_v0 \
/srv/qnty/venv/bin/python scripts/qnty-paper-sqlite-accounting.py \
  --db-path /srv/qnty/output/paper_pnl_null_shadow_v0/paper_ledger.db \
  --forward-obs-dir /tmp/qnty_shadow_batch13_manual_run_v0/forward_obs_v1_frozen \
  --data-dir /srv/qnty/repo/data \
  --json
```

No prod writer, data refresh, timer mutation, service start/stop/restart,
install, migration, `ALTER`, or manual WAL checkpoint was run.

## 10. Writer Output

```json
{
  "status_code": 0,
  "status_message": "Committed batch 13: 1 bars, 7 events"
}
```

Shell exit status:

```txt
WRITER_STATUS=0
```

## 11. Batch13 DB Verification

Shadow batch13 verification from the DB:

- Batch exists exactly once: yes
- Latest shadow batch after writer: `13`
- Shadow batch count after writer: `13`
- Batch13 `prior_watermark_bar_ts`: `2026-07-01T16:00:00`
- Batch13 `new_watermark_bar_ts`: `2026-07-02T00:00:00`
- Batch13 `committed_bar_count`: `1`
- Batch13 `event_count`: `7`
- Batch13 `first_event_seq`: `85`
- Batch13 `last_event_seq`: `91`
- Batch13 `git_sha`: `fde43a511ef98d7292a6bd93dd9e198ea92f79fe`
- Batch13 `committed_at`: `2026-07-02T10:21:52Z`
- Shadow DB `PRAGMA integrity_check` after writer: `ok`

Latest shadow equity snapshot after writer:

- `bar_ts`: `2026-07-02T00:00:00`
- `batch_id`: `13`
- `seq`: `91`
- `equity`: `10033.54916805`

## 12. Latest Shadow PnL After Batch13

Paper diagnostics only:

- Initial equity: `10000.0`
- Latest shadow equity: `10033.54916805`
- Paper PnL absolute vs initial: `33.54916805`
- Paper PnL percent vs initial: `0.335491680500%`
- Realized gross PnL: `-17.81922092`
- Unrealized PnL: `54.56205303`
- Funding cumulative: `0.70257367`
- Fees cumulative: `2.49109039`
- Open positions count: `1`
- Latest snapshot `num_open`: `1`

This is not an edge claim and not a profitability claim.

## 13. Prod Unchanged Verification

Prod DB checksum before and after:

```txt
9ffd1abcbc50257c4d9823c2bb325121da36affe21659aba8b873b526e04172a
```

Prod state after writer:

- Latest prod batch: `35`
- Prod batch count: `35`
- Prod watermark: `2026-07-02T00:00:00`
- Latest prod equity: `10018.21588531`
- Prod `PRAGMA integrity_check`: `ok`

## 14. Live Forward_Obs Unchanged Verification

Live forward_obs fingerprint before and after:

```txt
49023abca62ee710aa07eeb4b857fcc86383ce6f538c4c3dc31729151c487beb
```

Live forward_obs after writer:

- Latest timestamp: `2026-07-02T00:00:00`
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
- Batches: `13`
- Events: `91`
- Equity rows: `23`
- Watermark: `2026-07-02T00:00:00`
- `report_path`: `null`
- Funding coverage verdict: `CAVEATED_ENGINE_SEMANTICS`

Prod verifier:

- Exit: `0`
- Status: `OK`
- Failure count: `0`
- `query_only`: `1`
- Batches: `35`
- Events: `149`
- Equity rows: `35`
- Watermark: `2026-07-02T00:00:00`
- `report_path`: `null`
- Funding coverage verdict: `CAVEATED_ENGINE_SEMANTICS`

## 16. Overlap Comparison

Recomputed from asserted-identity `equity_snapshots` only. Paper diagnostics
only; this is not edge evidence.

- First shared timestamp: `2026-06-24T16:00:00`
- Latest shared timestamp: `2026-07-02T00:00:00`
- Latest shared includes `2026-07-02T00:00:00`: yes
- Prod start equity: `9984.66610097`
- Prod end equity: `10018.21588531`
- Prod delta equity: `33.54978434`
- Shadow start equity: `10000.0`
- Shadow end equity: `10033.54916805`
- Shadow delta equity: `33.54916805`
- Prod-minus-shadow delta equity: `0.00061629`

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

- One explicit shadow writer invocation for batch13.
- Read-only preflight and postflight checks.
- Frozen forward_obs copy under `/tmp/qnty_shadow_batch13_manual_run_v0`.
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

`SHADOW_BATCH13_ONE_BAR_COMMITTED_RECEIPT_READY_FOR_PR`
