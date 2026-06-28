# Shadow Lane Batch 5 — Manual Phase 3 Receipt

**Verdict:** `VM_SHADOW_BATCH5_MANUAL_CATCHUP_RECEIPT_READY`
**Strategy label:** `EDGE_UNPROVEN`

---

## 1. Purpose

Manually authorized shadow-lane **batch 5 catch-up** against the existing shadow
ledger. Scope:

- Existing shadow DB reused (no reset, no recreate, no migration).
- **Exactly one** shadow writer invocation.
- Writer fed a **frozen snapshot** of `forward_obs_v1` (copied to `/tmp` run root).
- No production DB mutation; no live `forward_obs_v1` mutation.
- No timers, services, or systemd state touched.
- No live trading, no real orders, no exchange keys.
- Strategy remains `EDGE_UNPROVEN`. All equity/PnL figures are paper diagnostics
  only.

## 2. Authorization Context

The previous batch 5 gate ran late and returned `SHADOW_BATCH5_NOT_READY`: it
expected forward_obs latest `2026-06-27T08:00:00`, but the actual latest had
advanced to `2026-06-28T00:00:00` (forward_obs moved 3 bars ahead of the shadow
watermark). That stale gate was **not RED** — shadow integrity, lane_id, batch
count, verifiers, and safety stats were all clean.

This is a **refreshed authorization** for the catch-up:

| Field | Value |
|---|---|
| Shadow watermark (prior) | `2026-06-27T00:00:00` |
| Forward_obs latest | `2026-06-28T00:00:00` |
| Hours ahead | `24.0` |
| Bars available | 3 (`2026-06-27T08:00:00`, `2026-06-27T16:00:00`, `2026-06-28T00:00:00`) |

## 3. Preflight (read-only except `/tmp` run root)

| Check | Result |
|---|---|
| Local main HEAD | `0d6a8611a02d473ade833d4a50dae3505f79f444` (== origin/main, incl. PR #30) |
| VM repo SHA | `fde43a511ef98d7292a6bd93dd9e198ea92f79fe` (allowed for batch5) |
| Venv Python | `/srv/qnty/venv/bin/python` |
| pandas import | OK (`3.0.2`) |
| Timer window | `timer_window_ok=true` (not within prod timer windows 00:20/08:20/16:20Z) |
| Shadow DB integrity | `ok` |
| Shadow lane_id | `paper_pnl_null_shadow_v0` |
| Prior shadow batches | exactly 4, latest watermark `2026-06-27T00:00:00` |
| Shadow verifier | `status=OK`, failure_count=0 |
| Production verifier | `status=OK`, failure_count=0 |
| Forward_obs preflight | latest `2026-06-28T00:00:00`, on 8h grid, 24.0h ahead, 500 rows |
| Frozen snapshot | `/tmp/qnty_shadow_batch5_manual_run_v0/fwd_obs_snapshot/observation_log.json` (500 rows, last `2026-06-28T00:00:00`) |

**Safety stats before:**
- prod: mtime `1782634836`, size `131072`
- shadow: mtime `1782560427`, size `102400`
- forward_obs: mtime `1782634575`, size `132652`

## 4. Command Shape

One writer invocation:

- `/srv/qnty/venv/bin/python scripts/qnty-paper-sqlite-accounting.py`
- `--db-path` → shadow DB
- `--forward-obs-dir` → frozen snapshot
- `--data-dir /srv/qnty/repo/data`
- `--json`
- env: `QNTY_PAPER_OUTPUT_DIR` (shadow out), `QNTY_PAPER_DB_PATH` (shadow DB),
  `QNTY_FORWARD_OBS_DIR` (frozen snapshot)

Verifier: `qnty-paper-sqlite-verify.py --db-path <shadow> --no-emit --json`
(read-only). DB inspection: read-only `mode=ro` SQLite connection.

## 5. Writer Result

- `writer_exit=0`
- stdout: `{"status_code": 0, "status_message": "Committed batch 5: 3 bars, 13 events"}`
- No rerun performed.

## 6. Verifier Result

- `verify_exit=0`, `status=OK`, `failure_count=0`
- batches=5, equity_rows=11, events=44
- watermark_bar_ts `2026-06-28T00:00:00`
- funding_coverage_verdict `CAVEATED_ENGINE_SEMANTICS`
  (decision `partial`; one missing window `SOLUSDT|2026-06-27T08:00:00|exit`
  treated as zero, matching current engine semantics — diagnostic only, not a
  failure)
- git provenance: all batches provenanced, latest batch git_sha
  `fde43a511ef98d7292a6bd93dd9e198ea92f79fe`

## 7. DB Inspection (read-only after writer)

- paper_config lane_id: `paper_pnl_null_shadow_v0`
  (strategy_id `matched_null_shadow_v0`, version `0.0.0-shadow`)
- ledger_batches count after: **5**

| batch_id | prior_watermark | new_watermark | committed_bar_count | event_count |
|---|---|---|---|---|
| 1 | `null` | `2026-06-25T08:00:00` | 3 | 13 |
| 2 | `2026-06-25T08:00:00` | `2026-06-26T00:00:00` | 2 | 7 |
| 3 | `2026-06-26T00:00:00` | `2026-06-26T08:00:00` | 1 | 3 |
| 4 | `2026-06-26T08:00:00` | `2026-06-27T00:00:00` | 2 | 8 |
| **5** | `2026-06-27T00:00:00` | `2026-06-28T00:00:00` | **3** | **13** |

Key counts after batch5: ledger_batches=5, ledger_events=44,
signal_snapshots=11, equity_snapshots=11, trades=2, open_positions=0,
funding=5, fills=4.

Latest equity snapshot (batch5, `2026-06-28T00:00:00`): equity `9980.04154734`,
num_open=0, unrealized_pnl=0.0 — paper diagnostic only.

## 8. Safety

| Invariant | Status |
|---|---|
| Production DB | unchanged (mtime `1782634836`, size `131072` before == after) |
| Live forward_obs | unchanged (mtime `1782634575`, size `132652` before == after) |
| Shadow DB | changed only by the authorized writer (mtime `1782560427` → `1782651800`, size `102400`) |
| systemd / timers / services | not touched |
| Migrations / ALTER | none |
| Exchange keys / orders | none |
| `.claude/` | unstaged |

## 9. Scope / Exclusions

No live trading. No real orders. No `source_data_digest`. No V2 config path. No
recurring shadow timers. No cross-lane reporter. No edge or profitability claim.

## 10. Interpretation

Batch 5 catch-up demonstrates continued, manually authorized shadow-lane
accounting over 3 closed bars (`2026-06-27T08:00:00`, `2026-06-27T16:00:00`,
`2026-06-28T00:00:00`), advancing the watermark `2026-06-27T00:00:00` →
`2026-06-28T00:00:00`. This proves the writer/verifier pipeline remains
internally consistent on the existing shadow ledger. It does **not** prove
strategy edge. All PnL/equity values are paper diagnostics only.

## 11. Verdict

`VM_SHADOW_BATCH5_MANUAL_CATCHUP_RECEIPT_READY` — `EDGE_UNPROVEN`
