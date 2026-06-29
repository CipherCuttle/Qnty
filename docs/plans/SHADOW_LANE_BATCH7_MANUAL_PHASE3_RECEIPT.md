# Shadow Lane Batch7 Manual One-Bar Catch-Up — Phase 3 Receipt

**Verdict:** `VM_SHADOW_BATCH7_MANUAL_ONE_BAR_RECEIPT_READY`
**Strategy label:** `EDGE_UNPROVEN`
**Funding verdict:** `CAVEATED_ENGINE_SEMANTICS` (NOT `CLEAN_NET_OF_CARRY`)

---

## 1. Purpose

Manually authorized shadow-lane **batch7 one-bar catch-up** against the existing
shadow lane database. The run:

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

The both-lane read-only check showed forward_obs latest exactly **one 8h bar**
ahead of the shadow watermark, so this is a one-bar catch-up:

| Field                  | Value                  |
| ---------------------- | ---------------------- |
| Shadow watermark       | `2026-06-29T00:00:00`  |
| forward_obs latest     | `2026-06-29T08:00:00`  |
| Hours ahead            | `8.0`                  |
| Expected bars to add   | 1                      |

Expected available bar:
- `2026-06-29T08:00:00`

Production lane stays level with forward_obs (watermark `2026-06-29T08:00:00`,
27 batches) — observed read-only as a safety stat only, not modified.

---

## 3. Preflight (read-only except `/tmp` snapshot/log dir)

- **Local main SHA:** `ea3270021823398294f189246f1274a1dfe3bdf0`
  (HEAD == origin/main; latest main includes PR #32 batch6 receipt)
- **VM repo SHA:** `fde43a511ef98d7292a6bd93dd9e198ea92f79fe` (allowed for batch7)
- **VM venv Python:** `/srv/qnty/venv/bin/python`
- **pandas import:** OK (`3.0.2`)
- **Timer window:** `timer_window_ok=true` (UTC `2026-06-29T20:52:17Z`, clear of
  prod timers 00:20 / 08:20 / 16:20Z)

**Safety stats before** (`mtime size`):

| Target                          | mtime        | size     |
| ------------------------------- | ------------ | -------- |
| prod DB                         | `1782750043` | `139264` |
| shadow DB                       | `1782727554` | `110592` |
| forward_obs observation_log.json| `1782749766` | `132457` |

**Shadow DB preflight:** integrity `ok`; `lane_id=paper_pnl_null_shadow_v0`;
exactly **6** prior batches all with correct lane_id; latest watermark
`2026-06-29T00:00:00`.

**Shadow verifier preflight:** status `OK`, exit 0, failure_count 0, 6 batches,
watermark `2026-06-29T00:00:00`, funding verdict `CAVEATED_ENGINE_SEMANTICS`.

**Production verifier preflight:** status `OK`, exit 0, failure_count 0, 27
batches, watermark `2026-06-29T08:00:00`, funding verdict
`CAVEATED_ENGINE_SEMANTICS`. (Read-only safety stat only; prod not modified.)

**Forward obs preflight:** latest `2026-06-29T08:00:00`, 500 rows, on 8h grid,
ahead of shadow, `hours_ahead=8.0`, age `12.872h` from bar open.

**Known funding caveat:** one missing window
`SOLUSDT|2026-06-27T08:00:00|exit` treated as zero by current engine semantics.
Known, not RED by itself.

**Frozen snapshot path:**
`/tmp/qnty_shadow_batch7_manual_run_v0/fwd_obs_snapshot/observation_log.json`
(500 rows, last ts `2026-06-29T08:00:00`, created `2026-06-29T20:52:17Z`).

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
- **stdout summary:** `Committed batch 7: 1 bars, 4 events`
- No rerun performed.

---

## 6. Verifier Result (after writer)

- **Exit code:** `0`
- **Status:** `OK`
- **failure_count:** `0`
- **Batches:** `7`
- **Watermark:** `2026-06-29T08:00:00`
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
- **Batch count after:** `7`

| batch | prior watermark        | new watermark          | committed_bars | events |
| ----- | ---------------------- | ---------------------- | -------------- | ------ |
| 1     | `null`                 | `2026-06-25T08:00:00`  | 3              | 13     |
| 2     | `2026-06-25T08:00:00`  | `2026-06-26T00:00:00`  | 2              | 7      |
| 3     | `2026-06-26T00:00:00`  | `2026-06-26T08:00:00`  | 1              | 3      |
| 4     | `2026-06-26T08:00:00`  | `2026-06-27T00:00:00`  | 2              | 8      |
| 5     | `2026-06-27T00:00:00`  | `2026-06-28T00:00:00`  | 3              | 13     |
| 6     | `2026-06-28T00:00:00`  | `2026-06-29T00:00:00`  | 3              | 9      |
| **7** | `2026-06-29T00:00:00`  | `2026-06-29T08:00:00`  | **1**          | **4**  |

**Batch7:** `committed_bar_count=1`, `event_count=4`,
`git_sha=fde43a511ef98d7292a6bd93dd9e198ea92f79fe`,
`created_at=2026-06-29T20:53:02Z`.

**Key counts after:**

| table             | count |
| ----------------- | ----- |
| ledger_batches    | 7     |
| ledger_events     | 57    |
| signal_snapshots  | 15    |
| equity_snapshots  | 15    |
| trades            | 2     |
| open_positions    | 1     |
| funding           | 5     |
| fills             | 5     |

Latest equity snapshot (`2026-06-29T08:00:00`, batch 7): equity
`9980.04154734`, realized_gross_pnl `-17.81922092`, fees_cum `1.99109039`,
funding_cum `0.14814135`, num_open `0`, unrealized_pnl `0.0` — flat over the new
bar, paper diagnostics only.

---

## 8. Safety

- **Production DB unchanged:** before/after `1782750043 139264` ==
  `1782750043 139264`.
- **Live forward_obs unchanged:** before/after `1782749766 132457` ==
  `1782749766 132457`.
- **Shadow DB changed only by the authorized writer:** size `110592` → `110592`
  bytes (mtime `1782727554` → `1782766383`).
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

The batch7 one-bar catch-up demonstrates continued **manual shadow-lane
accounting** over one additional closed bar (`2026-06-29T08:00:00`), bringing the
shadow watermark level with both production and forward_obs, with internal
accounting consistency intact and full git provenance. It does **not** prove
strategy edge. The funding verdict remains `CAVEATED_ENGINE_SEMANTICS`, so this
run is **not** `CLEAN_NET_OF_CARRY`. All PnL / equity values are paper
diagnostics only.

---

## 11. Verdict

`VM_SHADOW_BATCH7_MANUAL_ONE_BAR_RECEIPT_READY`
`EDGE_UNPROVEN`
