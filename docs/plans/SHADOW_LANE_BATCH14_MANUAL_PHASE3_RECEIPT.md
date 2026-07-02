# Shadow Lane Batch14 Manual Phase3 Receipt

## 1. Purpose

Record the explicitly authorized one-bar manual shadow-lane writer run for batch14.

This receipt is paper diagnostics only. It makes no edge claim and no live-trading claim.

## 2. Authorization Context

Task: `AUTHORIZE_SHADOW_BATCH14_ONE_BAR_WRITER_ONCE`

The prior read-only gate classified the lane state as:

```txt
SHADOW_READY_FOR_BATCH14_ONE_BAR_AUTHORIZATION
```

Known pre-authorization state:

```txt
EDGE_STATUS: EDGE_UNPROVEN
funding verdict: CAVEATED_ENGINE_SEMANTICS

prod watermark:       2026-07-02T08:00:00
forward_obs latest:   2026-07-02T08:00:00
shadow watermark:     2026-07-02T00:00:00

prod latest batch:    36
shadow latest batch:  13
missing shadow bar:   exactly 2026-07-02T08:00:00
expected shadow batch: 14
```

The authorization allowed exactly one shadow writer invocation. No rerun was allowed on failure.

## 3. Correct VM Target

Used:

```bash
ssh -i ~/.ssh/hetzner_qnty_key -o IdentitiesOnly=yes viktor@37.27.216.174
```

VM identity:

```txt
HOSTNAME=ubuntu-4gb-hel1-1-qnty
UTC=2026-07-02T17:08:33Z
SWEDEN=2026-07-02T19:08:33+0200
```

The `192.168.1.100` host was not used.

## 4. Preflight State

Local repository preflight before VM mutation:

```txt
branch: main
main == origin/main: yes, 0 0 ahead/behind
tracked diff: none
staged diff: none
allowed untracked: .claude/
latest main commit: 9ecb666 docs: add shadow lane batch13 manual receipt (#41)
```

Required receipt files on `main`:

```txt
docs/plans/SHADOW_LANE_BATCH13_MANUAL_PHASE3_RECEIPT.md PRESENT
docs/plans/SHADOW_LANE_BATCH11_MANUAL_PHASE3_RECEIPT.md PRESENT
docs/plans/QNTY_V1_SHADOW_ASSERTED_IDENTITY_PNL_RECONCILIATION_AFTER_BATCH11.md PRESENT
docs/plans/SHADOW_LANE_BATCH12_MANUAL_PHASE3_RECEIPT.md PRESENT
```

VM preflight:

```txt
prod DB:    /srv/qnty/output/paper_pnl_v1/paper_ledger.db
shadow DB:  /srv/qnty/output/paper_pnl_null_shadow_v0/paper_ledger.db
forward_obs: /srv/qnty/output/forward_obs_v1

prod watermark expected: true
forward_obs latest expected: true
shadow watermark expected: true
shadow latest batch expected: true
expected next shadow batch: 14
missing bar count: 1
```

DB integrity preflight:

```txt
prod PRAGMA integrity_check: ok
shadow PRAGMA integrity_check: ok
```

## 5. Timer State

No QNTY service was running before the writer.

Relevant timer state before the writer:

```txt
qnty-watermark-watchdog.timer next 2026-07-02 18:00:34 UTC, last 2026-07-02 17:00:19 UTC
qnty-healthcheck.timer        next 2026-07-02 20:02:45 UTC, last 2026-07-02 16:04:28 UTC
qnty-data-refresh.timer       next 2026-07-03 00:05:11 UTC, last 2026-07-02 16:05:08 UTC
qnty-shadow-run.timer         next 2026-07-03 00:11:06 UTC, last 2026-07-02 16:10:57 UTC
qnty-paper-pnl.timer          next 2026-07-03 00:21:23 UTC, last 2026-07-02 16:20:48 UTC
qnty-health-receipt.timer     next 2026-07-03 00:32:56 UTC, last 2026-07-02 16:31:33 UTC
qnty-daily-summary.timer      next 2026-07-03 17:00:00 UTC, last 2026-07-02 17:00:03 UTC
```

No timer or service was changed.

## 6. DB Identity Assertion

Shadow DB identity was read from the DB before writing:

```txt
DB path: /srv/qnty/output/paper_pnl_null_shadow_v0/paper_ledger.db
lane_id: paper_pnl_null_shadow_v0
strategy_id: matched_null_shadow_v0
version/strategy_version: 0.0.0-shadow
paper_engine_version: 0.3.0
config_hash: 32c0fbccdf46af8b50ef0e6d2da9a76657038da621ff2be1dba95d82208d5d52
config_hash_v2: 50b1bbeff42d33f4413776ea14cc06281b275b346ab79c279baf959b58ae024c
forward_start_ts: 2026-06-24T16:00:00
```

The config hashes above are actual DB values from this run, not copied from older receipts.

## 7. Mutation Guards

Before writer:

```txt
prod DB sha256:   06ea139db69aca17b72fb7e667962212bcbffc616a8f69c71d7da14943c3a14e
shadow DB sha256: 075762a4f79d96b50f6a057f5a858f434d1187e181dbfa6d50f193d44600f5a5
forward_obs hash: a8b8a761953a49c93e54bd5b0d7fe10944a1ef534a62f9e0e75b601c8807f521
```

After writer:

```txt
prod DB sha256:   06ea139db69aca17b72fb7e667962212bcbffc616a8f69c71d7da14943c3a14e
shadow DB sha256: 2ee2ba884278dffd08f6145e80d3b852c4e42fa8a49400291aa8868437c97f47
forward_obs hash: a8b8a761953a49c93e54bd5b0d7fe10944a1ef534a62f9e0e75b601c8807f521
```

Expected mutation scope:

```txt
prod DB unchanged: yes
live forward_obs unchanged: yes
shadow DB changed: yes, expected writer target
```

## 8. Frozen Forward Obs Snapshot

Run-specific temporary directory:

```txt
/tmp/qnty_shadow_batch14_manual_run_v0/forward_obs_v1_frozen
```

The run-specific temp directory was removed before creation, then recreated for this run only.

Snapshot evidence:

```txt
LIVE_ABS_FINGERPRINT=a8b8a761953a49c93e54bd5b0d7fe10944a1ef534a62f9e0e75b601c8807f521
LIVE_REL_FINGERPRINT=fb4d393050117820dcd4808725fab182ed8afa559df0a8c69a64cac3decf6527
FROZEN_REL_FINGERPRINT=fb4d393050117820dcd4808725fab182ed8afa559df0a8c69a64cac3decf6527
FROZEN_FILE_COUNT=9
FROZEN_OBS_COUNT=500
FROZEN_LATEST_TS=2026-07-02T08:00:00
```

Live and frozen relative fingerprints matched at copy time.

## 9. Exact Writer Command

Exactly one writer invocation was run:

```bash
cd /srv/qnty/repo

QNTY_PAPER_OUTPUT_DIR=/srv/qnty/output/paper_pnl_null_shadow_v0 \
/srv/qnty/venv/bin/python scripts/qnty-paper-sqlite-accounting.py \
  --db-path /srv/qnty/output/paper_pnl_null_shadow_v0/paper_ledger.db \
  --forward-obs-dir /tmp/qnty_shadow_batch14_manual_run_v0/forward_obs_v1_frozen \
  --data-dir /srv/qnty/repo/data \
  --json
```

No prod writer, data refresh, service restart, timer mutation, dependency install, migration, or WAL checkpoint was run.

## 10. Writer Output

```json
{
  "status_code": 0,
  "status_message": "Committed batch 14: 1 bars, 5 events"
}
```

## 11. Batch14 DB Verification

Shadow DB post-write:

```txt
latest batch: 14
batch14 count: 1
batch count: 14
PRAGMA integrity_check: ok
```

Batch14 row:

```txt
batch_id: 14
created_at: 2026-07-02T17:09:13Z
started_at: 2026-07-02T17:09:13Z
committed_at: 2026-07-02T17:09:13Z
git_sha: fde43a511ef98d7292a6bd93dd9e198ea92f79fe
prior_watermark_bar_ts: 2026-07-02T00:00:00
new_watermark_bar_ts: 2026-07-02T08:00:00
first_event_seq: 92
last_event_seq: 96
event_count: 5
committed_bar_count: 1
paper_engine_version: 0.3.0
config_hash: 32c0fbccdf46af8b50ef0e6d2da9a76657038da621ff2be1dba95d82208d5d52
lane_id: paper_pnl_null_shadow_v0
```

Latest shadow equity snapshot:

```txt
bar_ts: 2026-07-02T08:00:00
seq: 96
equity: 10176.86526013
realized_gross_pnl: -17.81922092
unrealized_pnl: 199.35145548
funding_cum: 0.67588404
fees_cum: 3.99109039
num_open: 4
```

## 12. Latest Shadow PnL After Batch14

Paper diagnostics only:

```txt
initial equity: 10000.0
latest shadow equity: 10176.86526013
paper PnL absolute vs initial: 176.86526013
paper PnL percent vs initial: 1.7686526013%
realized gross PnL: -17.81922092
unrealized PnL: 199.35145548
funding cumulative: 0.67588404
fees cumulative: 3.99109039
open positions: 4
```

## 13. Prod Unchanged Verification

Prod DB checksum remained unchanged:

```txt
06ea139db69aca17b72fb7e667962212bcbffc616a8f69c71d7da14943c3a14e
```

Prod lane post-write:

```txt
latest batch: 36
watermark: 2026-07-02T08:00:00
latest equity: 10161.53197739
PRAGMA integrity_check: ok
```

## 14. Live Forward Obs Unchanged Verification

Live `forward_obs_v1` hash remained unchanged:

```txt
a8b8a761953a49c93e54bd5b0d7fe10944a1ef534a62f9e0e75b601c8807f521
```

Live `forward_obs_v1` still reported:

```txt
observation count: 500
latest timestamp: 2026-07-02T08:00:00
```

## 15. Verifier Results

Shadow verifier:

```txt
status: OK
exit_code: 0
failure_count: 0
query_only: 1
db_path: /srv/qnty/output/paper_pnl_null_shadow_v0/paper_ledger.db
batches: 14
equity_rows: 24
events: 96
watermark_bar_ts: 2026-07-02T08:00:00
funding_coverage_verdict: CAVEATED_ENGINE_SEMANTICS
latest_batch_id: 14
latest_batch_git_sha: fde43a511ef98d7292a6bd93dd9e198ea92f79fe
```

Prod verifier:

```txt
status: OK
exit_code: 0
failure_count: 0
query_only: 1
db_path: /srv/qnty/output/paper_pnl_v1/paper_ledger.db
batches: 36
equity_rows: 36
events: 154
watermark_bar_ts: 2026-07-02T08:00:00
funding_coverage_verdict: CAVEATED_ENGINE_SEMANTICS
latest_batch_id: 36
latest_batch_git_sha: fde43a511ef98d7292a6bd93dd9e198ea92f79fe
```

Both verifier reports include this disclaimer:

```txt
Verifier v1 validates SQLite ledger integrity and internal accounting consistency. It does not independently rederive OHLCV marks/unrealized PnL/exposure from source price data.
```

## 16. Overlap Comparison

Recomputed from asserted-identity `equity_snapshots` only.

Paper diagnostics only; this is not edge evidence.

```txt
first shared timestamp: 2026-06-24T16:00:00
latest shared timestamp: 2026-07-02T08:00:00
latest shared includes 2026-07-02T08:00:00: true

prod start equity: 9984.66610097
prod end equity: 10161.53197739
prod delta equity: 176.86587642

shadow start equity: 10000.0
shadow end equity: 10176.86526013
shadow delta equity: 176.86526013

prod-minus-shadow delta equity: 0.00061629
```

## 17. Funding Caveat

Funding verdict remains:

```txt
CAVEATED_ENGINE_SEMANTICS
```

Verifier diagnostic label:

```txt
missing_funding_treated_as_zero_like_current_engine_not_net_of_carry_clean
```

This receipt preserves that caveat and does not claim funding-clean economics.

## 18. EDGE Status

```txt
EDGE_STATUS: EDGE_UNPROVEN
```

No edge claim is made.

## 19. Scope And Exclusions

Performed:

```txt
one shadow writer invocation against /srv/qnty/output/paper_pnl_null_shadow_v0/paper_ledger.db
one run-specific frozen forward_obs copy under /tmp/qnty_shadow_batch14_manual_run_v0
read-only post-write verification
```

Not performed:

```txt
prod writer
data refresh
live forward_obs mutation
prod DB mutation
timer changes
service start/stop/restart
dependency install
DB migration or ALTER
WAL checkpoint
push
live trading authorization or action
```

## 20. Verdict

```txt
SHADOW_BATCH14_ONE_BAR_COMMITTED_RECEIPT_READY_FOR_PR
```
