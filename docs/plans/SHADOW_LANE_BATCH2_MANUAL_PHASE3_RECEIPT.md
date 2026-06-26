# Shadow Lane Batch 2 — Manual Phase 3 Receipt

Docs-only receipt for a manually authorized shadow-lane batch 2.

## 1. Purpose

- Docs-only receipt for the manually authorized shadow lane batch 2.
- The existing shadow lane database was reused; no lane init was rerun.
- Exactly one batch2 writer invocation was performed.
- A frozen forward-obs snapshot was used as the writer source (not the live observer directory).
- No production DB mutation.
- No forward_obs mutation.
- No timers/services were touched.
- No live trading / no orders.
- `EDGE_UNPROVEN`.

## 2. Authorization context

Prior both-lane read-only status check returned:

- `PROD_LANE: GREEN`
- `SHADOW_LANE: READY_FOR_BATCH2_AUTH`
- `FORWARD_OBS: FRESH`
- `NEXT_ACTION: AUTHORIZE_BATCH2_MANUAL`

State immediately before batch 2:

- Shadow watermark before batch2: `2026-06-25T08:00:00`
- Forward obs latest before batch2: `2026-06-26T00:00:00`
- Forward obs was 16h ahead of the shadow watermark and on the 8h grid.

## 3. Preflight

- Local main SHA: `ebf3827` (`HEAD == origin/main`, working tree clean, only `.claude/` untracked).
- VM repo SHA: `fde43a5` (`fde43a511ef98d7292a6bd93dd9e198ea92f79fe`) — code-equivalent for lane behavior; later local commits are docs-only receipts.
- venv Python: `/srv/qnty/venv/bin/python`.
- pandas import OK: `3.0.2`.
- Timer window OK (`timer_window_ok=true`; not within the prod timer guard windows at 00:20 / 08:20 / 16:20 UTC). Preflight host time `2026-06-26T10:05:03Z`.
- Production DB before stat: mtime `1782462056`, size `110592`.
- Shadow DB before stat: mtime `1782408501`, size `102400`.
- Forward obs before stat (`observation_log.json`): mtime `1782461734`, size `132948`.
- Shadow DB integrity: `ok`.
- lane_id correct: `paper_config.lane_id = paper_pnl_null_shadow_v0`; exactly 1 batch before batch2, batch 1 lane_id correct, watermark `2026-06-25T08:00:00`.
- Verifier OK before writer: exit 0, status `OK`, failure_count 0, `CLEAN_NET_OF_CARRY`.
- Snapshot path: `/tmp/qnty_shadow_batch2_manual_run_v0/fwd_obs_snapshot` (500 obs rows, last ts `2026-06-26T00:00:00`).

## 4. Command shape

One writer command, using `/srv/qnty/venv/bin/python`:

- script: `scripts/qnty-paper-sqlite-accounting.py`
- `--db-path` pointed to the shadow DB: `/srv/qnty/output/paper_pnl_null_shadow_v0/paper_ledger.db`
- `--forward-obs-dir` pointed to the frozen snapshot `/tmp/qnty_shadow_batch2_manual_run_v0/fwd_obs_snapshot` (not live `forward_obs_v1`)
- `--data-dir /srv/qnty/repo/data`
- `--json`
- environment: `QNTY_PAPER_OUTPUT_DIR`, `QNTY_PAPER_DB_PATH`, `QNTY_FORWARD_OBS_DIR` all scoped to the shadow lane / frozen snapshot.

Verifier command: `scripts/qnty-paper-sqlite-verify.py --db-path <shadow DB> --no-emit --json`.

DB inspection: read-only (`mode=ro`).

## 5. Writer result

- Writer exit code: `0`.
- Writer stdout summary: `Committed batch 2: 2 bars, 7 events` (`status_code: 0`).
- No rerun.

## 6. Verifier result

- Verifier exit code: `0`.
- Verifier status: `OK`.
- Failure count: `0`.
- Funding / net-of-carry verdict: `CLEAN_NET_OF_CARRY` (funding coverage `complete`, SOLUSDT complete).
- Reported watermark: `2026-06-26T00:00:00`, batches `2`, events `20`, equity rows `5`.

## 7. DB inspection (after writer, read-only)

- `paper_config.lane_id`: `paper_pnl_null_shadow_v0` (strategy_id `matched_null_shadow_v0`, strategy_version `0.0.0-shadow`).
- Ledger batch count after: `2`.
- Batch 1: prior watermark `null` → new watermark `2026-06-25T08:00:00`, committed_bar_count `3`, event_count `13`, lane_id `paper_pnl_null_shadow_v0`, git_sha `fde43a5`.
- Batch 2: prior watermark `2026-06-25T08:00:00` → new watermark `2026-06-26T00:00:00`, committed_bar_count `2`, event_count `7`, lane_id `paper_pnl_null_shadow_v0`, git_sha `fde43a5`, created_at `2026-06-26T10:05:56Z`.

Counts after batch 2:

| table | count |
| --- | --- |
| ledger_batches | 2 |
| ledger_events | 20 |
| signal_snapshots | 5 |
| equity_snapshots | 5 |
| trades | 1 |
| open_positions | 1 |
| funding | 1 |
| fills | 3 |

Paper diagnostics only (not edge): latest equity snapshot at bar `2026-06-26T00:00:00` is `9953.1577499` with realized_gross_pnl `-45.91133828`, funding_cum `-0.04613251`, fees_cum `0.97704433`, num_open `0`. The single recorded trade is SOLUSDT entry `2026-06-25T00:00:00` / exit `2026-06-25T08:00:00`, net_pnl `-46.8422501`. These are paper simulation figures only.

## 8. Safety

- Production DB before/after stat unchanged: before `1782462056 110592`, after `1782462056 110592`.
- Forward_obs before/after stat unchanged: before `1782461734 132948`, after `1782461734 132948`.
- Shadow DB changed only because the authorized batch2 writer ran: mtime `1782408501` → `1782468357` (size `102400` unchanged).
- No write into `paper_pnl_v1`.
- No write into live `forward_obs_v1` (frozen snapshot used as source).
- No systemd / timer / service changes.
- No migration / ALTER.
- No exchange keys / orders.
- `.claude/` unstaged.

## 9. Scope / exclusions

- No live trading.
- No real orders.
- No `source_data_digest`.
- No V2.
- No recurring shadow timers.
- No cross-lane reporter.
- No edge / profitability claim.

## 10. Interpretation

- Batch 2 demonstrates continued manual shadow-lane accounting / plumbing over the next closed bars (`2026-06-25T16:00:00` and `2026-06-26T00:00:00`).
- This does not prove strategy edge.
- All PnL / equity is paper diagnostic only.
- `EDGE_UNPROVEN`.

## 11. Verdict

- `VM_SHADOW_BATCH2_MANUAL_RECEIPT_READY`
- `EDGE_UNPROVEN`
