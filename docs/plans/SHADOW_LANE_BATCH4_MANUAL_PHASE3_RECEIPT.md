# Shadow Lane Batch 4 — Manual Phase 3 Receipt

Status: `VM_SHADOW_BATCH4_MANUAL_RECEIPT_READY`
Strategy label: `EDGE_UNPROVEN`

## 1. Purpose

Docs-only receipt for a single, manually authorized shadow-lane batch 4.

- Existing shadow DB reused; no lane init rerun.
- Exactly one batch4 writer invocation.
- Frozen forward-obs snapshot used as the writer input (not the live directory).
- No production DB mutation.
- No live `forward_obs_v1` mutation.
- No timer/service changes.
- No live-trading actions, no real-money orders.
- Strategy remains `EDGE_UNPROVEN`.

## 2. Authorization context

- Prior read-only gate returned: `SHADOW_BATCH4_GATE: READY_FOR_SEPARATE_AUTHORIZATION`.
- Shadow watermark before batch4: `2026-06-26T08:00:00`.
- Forward obs latest before batch4: `2026-06-27T00:00:00`.
- Forward obs was 16.0h ahead of the shadow watermark and on the 8h grid.

## 3. Preflight (read-only except snapshot/log dir)

- Local main SHA: `0eb96e8b662357c8ae25d91f6c40f846a23abc32` (`== origin/main`).
- VM repo SHA: `fde43a511ef98d7292a6bd93dd9e198ea92f79fe` (accepted; later commits are docs-only receipts).
- VM Python: `/srv/qnty/venv/bin/python`.
- pandas import OK: `3.0.2`.
- Timer window: `timer_window_ok=true` (not within prod timer guard window).
- Production DB before stat: `mtime=1782548429 size=118784`.
- Shadow DB before stat: `mtime=1782502566 size=102400`.
- Forward obs before stat: `mtime=1782548174 size=132848`.
- Shadow DB integrity: `ok`.
- lane_id: `paper_pnl_null_shadow_v0` (correct).
- Exactly 3 existing authorized shadow batches before run.
- Shadow verifier before writer: exit 0 / `OK` / failure_count 0.
- Production verifier before writer: exit 0 / `OK` / failure_count 0.
- Frozen snapshot path: `/tmp/qnty_shadow_batch4_manual_run_v0/fwd_obs_snapshot`
  (500 obs rows, last ts `2026-06-27T00:00:00`).

## 4. Command shape

One writer command:

- `/srv/qnty/venv/bin/python scripts/qnty-paper-sqlite-accounting.py`
- `--db-path` → shadow DB (`paper_pnl_null_shadow_v0/paper_ledger.db`).
- `--forward-obs-dir` → frozen snapshot dir (NOT the live forward-obs directory).
- `--data-dir /srv/qnty/repo/data`.
- `--json`.

Verifier command:

- `/srv/qnty/venv/bin/python scripts/qnty-paper-sqlite-verify.py --db-path <shadow DB> --no-emit --json`.

DB inspection: read-only sqlite connection (`mode=ro`).

## 5. Writer result

- Writer exit code: `0`.
- Writer stdout: `{"status_code": 0, "status_message": "Committed batch 4: 2 bars, 8 events"}`.
- No rerun performed.

## 6. Verifier result

- Verifier exit code: `0`.
- Verifier status: `OK`.
- Failure count: `0`.
- Funding / net-of-carry verdict: `CLEAN_NET_OF_CARRY` (funding coverage `complete`).

## 7. DB inspection (read-only, after writer)

- `paper_config.lane_id`: `paper_pnl_null_shadow_v0`.
- Ledger batch count after: `4`.

Batch watermark details (all `lane_id = paper_pnl_null_shadow_v0`, git_sha `fde43a5…`):

| batch_id | prior_watermark      | new_watermark        | committed_bars | events |
|----------|----------------------|----------------------|----------------|--------|
| 1        | (null)               | 2026-06-25T08:00:00  | 3              | 13     |
| 2        | 2026-06-25T08:00:00  | 2026-06-26T00:00:00  | 2              | 7      |
| 3        | 2026-06-26T00:00:00  | 2026-06-26T08:00:00  | 1              | 3      |
| 4        | 2026-06-26T08:00:00  | 2026-06-27T00:00:00  | 2              | 8      |

- Batch 4 committed_bar_count: `2` (bars `2026-06-26T16:00:00`, `2026-06-27T00:00:00`).
- Batch 4 event_count: `8`.
- Batch 4 created_at / started_at: `2026-06-27T11:40:25Z`.

Table counts after batch4:

- ledger_batches: `4`
- ledger_events: `31`
- signal_snapshots: `8`
- equity_snapshots: `8`
- trades: `1`
- open_positions: `1`
- funding: `3`
- fills: `3`

Paper diagnostics only (latest equity snapshot, bar `2026-06-27T00:00:00`):
equity `9973.61167504`, realized_gross_pnl `-45.91133828`, unrealized_pnl `21.11793976`,
fees_cum `1.47704433`, funding_cum `0.1178821`, num_open `1`. Treat all figures as paper diagnostics.

## 8. Safety

- Production DB before/after stat unchanged: `1782548429 118784` → `1782548429 118784`.
- Live forward_obs before/after stat unchanged: `1782548174 132848` → `1782548174 132848`.
- Shadow DB changed only because the authorized batch4 writer ran:
  `mtime 1782502566 → 1782560427` (size `102400` unchanged).
- No write into the production lane output dir.
- No write into the live forward-obs directory.
- No systemd / timer / service changes.
- No migration / ALTER.
- No exchange API keys, no order placement.
- `.claude/` left unstaged.

## 9. Scope / exclusions

- No live-trading actions.
- No real-money orders.
- No source_data_digest work.
- No V2 work.
- No recurring shadow timers added.
- No cross-lane reporter.
- No edge / profitability claim.

## 10. Interpretation

- Batch 4 demonstrates continued manual shadow-lane accounting/plumbing over the next closed bars.
- This does NOT demonstrate strategy edge.
- All PnL / equity figures are paper diagnostics only.
- Strategy remains `EDGE_UNPROVEN`.

## 11. Verdict

- `VM_SHADOW_BATCH4_MANUAL_RECEIPT_READY`
- `EDGE_UNPROVEN`
