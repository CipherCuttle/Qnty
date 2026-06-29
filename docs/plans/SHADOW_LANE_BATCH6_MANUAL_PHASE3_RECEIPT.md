# Shadow Lane Batch6 Manual Catch-Up — Phase 3 Receipt

**Verdict:** `VM_SHADOW_BATCH6_MANUAL_CATCHUP_RECEIPT_READY`
**Strategy label:** `EDGE_UNPROVEN`
**Funding verdict:** `CAVEATED_ENGINE_SEMANTICS` (NOT `CLEAN_NET_OF_CARRY`)

---

## 1. Purpose

Manually authorized shadow-lane **batch6 catch-up** against the existing shadow
lane database. The run:

- reused the existing shadow DB (no recreate / reset / migration),
- executed **exactly one** shadow writer invocation,
- read forward observations from a **frozen snapshot** of `forward_obs_v1`,
- did **not** mutate the production DB,
- did **not** mutate the live forward observer directory,
- touched **no** systemd timers / services,
- placed **no** live trades and used **no** exchange keys.

Strategy remains `EDGE_UNPROVEN`. All equity / PnL figures are **paper
diagnostics only** and constitute no profitability or edge claim.

---

## 2. Authorization Context

The prior batch6 readiness gate returned `SHADOW_BATCH6_NOT_READY` because it
expected forward_obs latest `2026-06-28T08:00:00`, while the observer had since
advanced to `2026-06-29T00:00:00`. That gate was **stale, not RED** — shadow DB
integrity OK, lane_id correct, exactly 5 batches, no unauthorized batch6,
shadow verifier OK, production verifier OK, prod DB unchanged, shadow DB
unchanged, forward_obs unchanged during the check.

This refreshed authorization is based on:

| Field                  | Value                  |
| ---------------------- | ---------------------- |
| Shadow watermark       | `2026-06-28T00:00:00`  |
| forward_obs latest     | `2026-06-29T00:00:00`  |
| Hours ahead            | `24.0`                 |
| Expected bars to add   | 3                      |

Expected available bars:
- `2026-06-28T08:00:00`
- `2026-06-28T16:00:00`
- `2026-06-29T00:00:00`

---

## 3. Preflight (read-only except `/tmp` snapshot/log dir)

- **Local main SHA:** `1597c3a9c480d585c42f60144058724d3c26b83e`
  (HEAD == origin/main; latest main includes PR #31 batch5 receipt)
- **VM repo SHA:** `fde43a511ef98d7292a6bd93dd9e198ea92f79fe` (allowed for batch6)
- **VM venv Python:** `/srv/qnty/venv/bin/python`
- **pandas import:** OK (`3.0.2`)
- **Timer window:** `timer_window_ok=true` (UTC `2026-06-29T10:05:14Z`, clear of
  prod timers 00:20 / 08:20 / 16:20Z)

**Safety stats before** (`mtime size`):

| Target                          | mtime        | size     |
| ------------------------------- | ------------ | -------- |
| prod DB                         | `1782721232` | `139264` |
| shadow DB                       | `1782651800` | `102400` |
| forward_obs observation_log.json| `1782720910` | `132516` |

**Shadow DB preflight:** integrity `ok`; `lane_id=paper_pnl_null_shadow_v0`;
exactly **5** prior batches all with correct lane_id; latest watermark
`2026-06-28T00:00:00`.

**Shadow verifier preflight:** status `OK`, exit 0, failure_count 0, 5 batches,
watermark `2026-06-28T00:00:00`, funding verdict `CAVEATED_ENGINE_SEMANTICS`.

**Production verifier preflight:** status `OK`, exit 0, failure_count 0, 26
batches, watermark `2026-06-29T00:00:00`, funding verdict
`CAVEATED_ENGINE_SEMANTICS`. (Read-only safety stat only; prod not modified.)

**Forward obs preflight:** latest `2026-06-29T00:00:00`, 500 rows, on 8h grid,
ahead of shadow, `hours_ahead=24.0`, age `10.088h` from bar open.

**Known funding caveat:** one missing window
`SOLUSDT|2026-06-27T08:00:00|exit` treated as zero by current engine semantics.
Known, not RED by itself.

**Frozen snapshot path:**
`/tmp/qnty_shadow_batch6_manual_run_v0/fwd_obs_snapshot/observation_log.json`
(500 rows, last ts `2026-06-29T00:00:00`, created `2026-06-29T10:05:15Z`).

---

## 4. Command Shape

One writer invocation:

- interpreter `/srv/qnty/venv/bin/python`
- script `scripts/qnty-paper-sqlite-accounting.py`
- `--db-path` → shadow DB
- `--forward-obs-dir` → frozen snapshot (not live forward_obs)
- `--data-dir /srv/qnty/repo/data`
- `--json`

Verifier run read-only with `--no-emit --json`. DB inspection done over a
read-only SQLite connection (`mode=ro`).

---

## 5. Writer Result

- **Exit code:** `0`
- **stdout summary:** `Committed batch 6: 3 bars, 9 events`
- No rerun performed.

---

## 6. Verifier Result (after writer)

- **Exit code:** `0`
- **Status:** `OK`
- **failure_count:** `0`
- **Batches:** `6`
- **Watermark:** `2026-06-29T00:00:00`
- **Funding verdict:** `CAVEATED_ENGINE_SEMANTICS` (preserved)
- **Funding diagnostic label:**
  `missing_funding_treated_as_zero_like_current_engine_not_net_of_carry_clean`
- Missing window still: `SOLUSDT|2026-06-27T08:00:00|exit`
- git provenance: latest batch git_sha
  `fde43a511ef98d7292a6bd93dd9e198ea92f79fe`, no unprovenanced batches.

---

## 7. DB Inspection (after writer, read-only)

- **paper_config.lane_id:** `paper_pnl_null_shadow_v0`
  (`strategy_id=matched_null_shadow_v0`, `strategy_version=0.0.0-shadow`)
- **Batch count after:** `6`

| batch | prior watermark        | new watermark          | committed_bars | events |
| ----- | ---------------------- | ---------------------- | -------------- | ------ |
| 1     | `null`                 | `2026-06-25T08:00:00`  | 3              | 13     |
| 2     | `2026-06-25T08:00:00`  | `2026-06-26T00:00:00`  | 2              | 7      |
| 3     | `2026-06-26T00:00:00`  | `2026-06-26T08:00:00`  | 1              | 3      |
| 4     | `2026-06-26T08:00:00`  | `2026-06-27T00:00:00`  | 2              | 8      |
| 5     | `2026-06-27T00:00:00`  | `2026-06-28T00:00:00`  | 3              | 13     |
| **6** | `2026-06-28T00:00:00`  | `2026-06-29T00:00:00`  | **3**          | **9**  |

**Batch6:** `committed_bar_count=3`, `event_count=9`,
`git_sha=fde43a511ef98d7292a6bd93dd9e198ea92f79fe`.

**Key counts after:**

| table             | count |
| ----------------- | ----- |
| ledger_batches    | 6     |
| ledger_events     | 53    |
| signal_snapshots  | 14    |
| equity_snapshots  | 14    |
| trades            | 2     |
| open_positions    | 0     |
| funding           | 5     |
| fills             | 4     |

Latest equity snapshot (`2026-06-29T00:00:00`, batch 6): equity
`9980.04154734`, realized_gross_pnl `-17.81922092`, fees_cum `1.99109039`,
funding_cum `0.14814135`, num_open `0`, unrealized_pnl `0.0` — paper
diagnostics only.

---

## 8. Safety

- **Production DB unchanged:** before/after `1782721232 139264` ==
  `1782721232 139264`.
- **Live forward_obs unchanged:** before/after `1782720910 132516` ==
  `1782720910 132516`.
- **Shadow DB changed only by the authorized writer:** `102400` → `110592`
  bytes (mtime `1782651800` → `1782727554`).
- No systemd / timer / service changes.
- No migration, no `ALTER`.
- No exchange keys, no orders.
- No package installs, no lane init, no VM git pull before run.
- `.claude/` left untracked / unstaged.

---

## 9. Scope / Exclusions

- No live trading, no real orders.
- No `source_data_digest`.
- No V2 engine work.
- No recurring shadow timers introduced.
- No cross-lane reporter.
- No edge / profitability claim.

---

## 10. Interpretation

The batch6 catch-up demonstrates continued **manual shadow-lane accounting**
over 3 additional closed bars (`2026-06-28T08:00:00`, `2026-06-28T16:00:00`,
`2026-06-29T00:00:00`), with internal accounting consistency intact and full
git provenance. It does **not** prove strategy edge. The funding verdict
remains `CAVEATED_ENGINE_SEMANTICS`, so this run is **not**
`CLEAN_NET_OF_CARRY`. All PnL / equity values are paper diagnostics only.

---

## 11. Verdict

`VM_SHADOW_BATCH6_MANUAL_CATCHUP_RECEIPT_READY`
`EDGE_UNPROVEN`
