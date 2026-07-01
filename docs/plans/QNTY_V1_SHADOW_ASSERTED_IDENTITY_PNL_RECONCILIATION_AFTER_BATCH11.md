# QNTY v1 — Shadow Asserted-Identity PnL Reconciliation After Batch11

**Verdict:** `RECONCILIATION_COMPLETE_RECEIPT_STALE_DB_AUTHORITATIVE`
**Strategy label:** `EDGE_UNPROVEN` (preserved)
**Funding verdict:** `CAVEATED_ENGINE_SEMANTICS` (preserved, NOT `CLEAN_NET_OF_CARRY`)
**Date:** 2026-07-01
**Mode:** read-only against VM/data; docs-only locally. No writer run. No DB mutated.

---

## 1. Purpose

Reconcile a serious PnL/equity contradiction after shadow **batch11**. A
browser-mode red-team review flagged a possible measurement footgun:

- A latest ad-hoc PnL readout reported shadow equity after batch11 ≈ `10026.2084`.
- The committed batch11 receipt states shadow equity after batch11 ≈ `9980.0415`.
- Both cannot be true.

The red-team hypothesis was that the `10026.2084` readout may have accidentally
read the **prod** (or prod-windowed) DB via the known output-dir footgun
(`QNTY_PAPER_OUTPUT_DIR` unset → defaults to `/srv/qnty/output/paper_pnl_v1`),
rather than the true shadow DB.

This investigation determined which value is authoritative by reading both DBs
**by explicit absolute path, read-only, with asserted lane identity**, using no
QNTY app helpers and no env-var lane resolution.

---

## 2. Context

```txt
EDGE_STATUS: EDGE_UNPROVEN
funding verdict: CAVEATED_ENGINE_SEMANTICS
local main after PR #37: b5277e2
prod lane:   paper_pnl_v1
shadow lane: paper_pnl_null_shadow_v0
prod DB:   /srv/qnty/output/paper_pnl_v1/paper_ledger.db
shadow DB: /srv/qnty/output/paper_pnl_null_shadow_v0/paper_ledger.db
expected aligned watermark after batch11: 2026-07-01T08:00:00
expected prod batches: 33
expected shadow batches: 11
```

Known output-dir footgun (confirmed in source, read-only):
[`quantbot/paper/__init__.py:43`](../../quantbot/paper/__init__.py#L43)

```python
return Path(os.environ.get("QNTY_PAPER_OUTPUT_DIR", "/srv/qnty/output/paper_pnl_v1"))
```

Any reader that resolves `paper_output_dir()` with `QNTY_PAPER_OUTPUT_DIR` unset
silently reads the **prod** lane. This receipt therefore opened DBs only by
explicit absolute path.

---

## 3. The Contradiction

| Source                                   | Shadow equity after batch11 |
| ---------------------------------------- | --------------------------- |
| Ad-hoc PnL readout                       | `10026.2084`                |
| Committed batch11 receipt (§7 narrative) | `9980.0415`                 |

**Resolution (spoiler):** the **ad-hoc readout was correct** — `10026.2084` is
the genuine shadow-DB latest equity snapshot. The **committed receipt's §7
"Latest equity snapshot" line is stale/wrong** (a copy-paste from the
batch5–7 flat-position era). The live DB is authoritative and its lane identity
is unambiguous.

---

## 4. What Was Inspected

- Local repo preflight (branch/sync/tree state, stale-branch check, receipt presence).
- Committed receipts: `SHADOW_LANE_BATCH10_MANUAL_PHASE3_RECEIPT.md`,
  `SHADOW_LANE_BATCH11_MANUAL_PHASE3_RECEIPT.md` (plus figure grep across all receipts).
- Live prod DB and shadow DB via explicit absolute paths, SQLite read-only URI
  `file:<path>?mode=ro&immutable=1`, stdlib `sqlite3` only (no QNTY helpers).
- `paper_config`, `ledger_state`, `ledger_batches`, `equity_snapshots` (full series).
- Figure hunts for `10026.2084`, `9980.0415`, `9991.5443` across both DBs and the repo.
- Reader-contamination source audit (`paper_output_dir()` and callers).
- Before/after mutation-guard checksums on both DBs and forward_obs.

---

## 5. Local Repo State

- Branch at start: `main`; `HEAD == origin/main == b5277e2` (`b5277e2ed4a11b0004ef054a9484d7a6c72fca12`).
- Working tree clean except harmless untracked `.claude/`. No tracked/staged diff.
- PR #37 receipt present on main: `docs/plans/SHADOW_LANE_BATCH11_MANUAL_PHASE3_RECEIPT.md`. ✔
- Wrong-VM stale branch check: a **remote** branch `origin/docs/shadow-batch11-receipt`
  exists; **no local branch** of that name exists. Reported, not deleted, not pushed.
- `QNTY_PAPER_OUTPUT_DIR` in local shell: **unset**.
- This receipt authored on PR branch `docs/asserted-identity-pnl-reconciliation-batch11`
  (not committed to main).

---

## 6. Receipt Value Extraction

**Batch11 receipt** (`SHADOW_LANE_BATCH11_MANUAL_PHASE3_RECEIPT.md`, §7 lines 200–203):

> Latest equity snapshot (`bar_ts=2026-07-01T08:00:00`, batch 11): equity
> `9980.04154734`, realized_gross_pnl `-17.81922092`, fees_cum `1.99109039`,
> funding_cum `0.14814135`, num_open `0`, unrealized_pnl `0.0` — flat over the new bar.

Batch-table facts in the same receipt are correct and DB-consistent: batch11
`committed_bar_count=1`, `event_count=4`, watermark `2026-07-01T00:00:00 →
2026-07-01T08:00:00`, `git_sha=fde43a51…`, `config_hash=32c0fbcc…`.

**Batch10 receipt** (`SHADOW_LANE_BATCH10_MANUAL_PHASE3_RECEIPT.md`, §6 lines 191–194):

> Latest equity snapshot (`bar_ts=2026-07-01T00:00:00`, batch 10): equity
> `9991.5443494`, unrealized_pnl `12.35251351`, num_open `1`.

Answers to the required questions:

1. Does batch11 receipt state a shadow latest equity? **Yes.**
2. Exact value stated? **`9980.04154734`.**
3. Does it state `9980.0415` or similar? **Yes** (`9980.04154734`).
4. Does it state `10026.2084` or similar? **No.** `10026.2084` appears nowhere in any receipt.
5. Does batch10 receipt state `9991.5443`? **Yes** (`9991.5443494`).
6. Are receipt values latest-state values, or another metric? The batch11 §7
   line is *labelled* a latest-state snapshot but is a **stale copy-paste** of the
   batch5–7-era flat snapshot (`9980.04154734`, num_open 0, unrealized 0.0). Its
   companion cumulative counts are likewise stale (e.g. it lists `fees_cum
   1.99109039`, `equity_snapshots 22`, `funding 10`, which are pre-batch11
   values). The receipt's **batch table** is correct; only its §7 latest-snapshot
   narrative + cumulative-count block are stale.

---

## 7. Asserted DB Identity — PROD

- **DB_PATH:** `/srv/qnty/output/paper_pnl_v1/paper_ledger.db`
- **SHA-256:** `f8b03faa26ef9f35e28bd61ab1bc95c3e015f23af478e01ff477bde5c4f953c9`
  (matches the batch11 receipt's recorded prod checksum → prod unchanged).
- **integrity_check:** `ok`
- **paper_config:** `forward_start_ts=2026-06-20T16:00:00`, `initial_equity_usd=10000.0`,
  `config_hash=1d61c1c779107ad194ca12febe620685bbc730edf75a766467fb45c05a74561b`.
  (This schema has **no** `lane_id` column — it is the older v1 prod config.)
- **ledger_batches:** count `33`; max `batch_id=33`; watermark `2026-07-01T08:00:00`.
- **ledger_state:** `watermark_bar_ts=2026-07-01T08:00:00`, `realized_gross=-29.03167196`,
  `fees_cum=6.48548416`, `funding_cum=0.72900285`, `peak_equity=10010.87510985`.
- **Latest equity_snapshot** (seq 138, batch 33, `bar_ts=2026-07-01T08:00:00`):
  `equity=10010.87510985`, `unrealized_pnl=47.12126882`, `num_open=1`.

Prod lane identity is clearly `paper_pnl_v1` (33 batches, forward_start 2026-06-20T16:00).

---

## 8. Asserted DB Identity — SHADOW

- **DB_PATH:** `/srv/qnty/output/paper_pnl_null_shadow_v0/paper_ledger.db`
- **SHA-256:** `8ed3fd9a2e506a9bafa1bdc17f1cbe31bddd6984c375e34a116efa5b93c9998c`
- **integrity_check:** `ok`
- **paper_config (lane identity fields present):**
  - `lane_id=paper_pnl_null_shadow_v0`
  - `strategy_id=matched_null_shadow_v0`
  - `strategy_version=0.0.0-shadow`
  - `config_hash=32c0fbccdf46af8b50ef0e6d2da9a76657038da621ff2be1dba95d82208d5d52`
    (matches the batch11 receipt's stated shadow config hash)
  - `forward_start_ts=2026-06-24T16:00:00`
  - `initial_equity_usd=10000.0`
- **ledger_batches:** count `11`; max `batch_id=11`; watermark `2026-07-01T08:00:00`;
  batch11 `git_sha=fde43a51…`, `committed_bar_count=1`, `event_count=4`,
  `committed_at=2026-07-01T18:15:43Z` — matches the receipt's batch table exactly.
- **ledger_state:** `watermark_bar_ts=2026-07-01T08:00:00`, `realized_gross=-17.81922092`,
  `fees_cum=2.49109039`, `funding_cum=0.60256492`, `peak_equity=10026.20839258`.

Shadow lane identity is clearly `paper_pnl_null_shadow_v0` (distinct config_hash,
distinct forward_start, `lane_id` present). **The two DBs are unambiguously
different lanes.**

---

## 9. Latest Equity/PnL From Live DBs

Asserted-identity latest `equity_snapshots` row per lane
(`bar_ts=2026-07-01T08:00:00`, the aligned watermark):

| Field              | PROD (`paper_pnl_v1`) | SHADOW (`paper_pnl_null_shadow_v0`) |
| ------------------ | --------------------- | ----------------------------------- |
| seq                | 138                   | 80                                  |
| batch_id           | 33                    | 11                                  |
| bar_ts             | 2026-07-01T08:00:00   | 2026-07-01T08:00:00                 |
| **equity**         | **10010.87510985**    | **10026.20839258**                  |
| realized_gross_pnl | -29.03167196          | -17.81922092                        |
| unrealized_pnl     | 47.12126882           | 47.12126882                         |
| funding_cum        | 0.72900285            | 0.60256492                          |
| fees_cum           | 6.48548416            | 2.49109039                          |
| num_open           | 1                     | 1                                   |
| drawdown           | 0.0                   | 0.0                                 |

**Shadow batch11 latest equity is `10026.20839258` with an OPEN position
(`num_open=1`, `unrealized_pnl=47.12126882`)** — NOT the flat `9980.04154734`
the receipt narrative claims.

The receipt's stated `9980.04154734 / num_open 0 / unrealized 0.0` matches **no
batch11 row**; it matches shadow's earlier flat-position bars
(2026-06-27T16:00 … 2026-06-29T08:00) — see §11.

---

## 10. Was `10026.2084` Found, and Where?

| Location                              | Found? | Detail                                              |
| ------------------------------------- | ------ | --------------------------------------------------- |
| 1. shadow DB **latest** equity snap   | **YES** | seq 80, batch 11, 2026-07-01T08:00:00 → `10026.20839258` (also = shadow `peak_equity`) |
| 2. prod DB latest equity snap         | No     | prod latest = `10010.87510985`                      |
| 3. shadow DB any equity snap          | Yes    | only the latest (batch11)                           |
| 4. prod DB any equity snap            | No     | not present anywhere in prod series                 |
| 5. batch11 receipt                    | No     |                                                     |
| 6. batch10 receipt                    | No     |                                                     |
| 7. computed window delta from prod    | No     | it is an absolute equity level, not a delta         |
| 8. nowhere                            | n/a    |                                                     |

**Conclusion:** `10026.2084` is exactly and only the **true shadow-DB latest
equity**. It is **not** a prod value and **not** a window delta. The ad-hoc
readout that produced it read the correct shadow lane.

---

## 11. Was `9980.0415` Found, and Where?

| Location                              | Found? | Detail                                                                 |
| ------------------------------------- | ------ | ---------------------------------------------------------------------- |
| 1. shadow DB latest equity snap       | No     | shadow latest = `10026.20839258`                                       |
| 2. prod DB latest equity snap         | No     |                                                                        |
| 3. shadow DB **any** equity snap      | **YES** | `9980.04154734` at bars 2026-06-27T16:00 → 2026-06-29T08:00 (6 rows, flat) |
| 4. prod DB any equity snap            | No     | (prod has a distinct `9980.61938769`, not `9980.0415`)                 |
| 5. batch11 receipt                    | **YES** | stated (incorrectly) as the batch11 "latest" snapshot                  |
| 6. batch10 receipt                    | No     | batch10 receipt states `9991.5443494`                                  |
| 7. nowhere                            | n/a    |                                                                        |

The same `9980.04154734` value also appears verbatim in the batch5/6/7 receipts —
confirming the batch11 receipt's §7 line was copied from that earlier flat era
and never refreshed to the real batch11 numbers.

---

## 12. Corrected Overlap-Window Comparison

Overlap computed **only** from stored `equity_snapshots` on both lanes, using the
first and last timestamps present in **both** series. No missing marks inferred.
No helper path resolution.

- First timestamp present in both series: `2026-06-24T16:00:00` (shadow's first bar).
- Latest shared timestamp: `2026-07-01T08:00:00`.

| Field                       | Value                        |
| --------------------------- | ---------------------------- |
| overlap_start               | `2026-06-24T16:00:00`        |
| overlap_end                 | `2026-07-01T08:00:00`        |
| prod start equity           | `9984.66610097`              |
| prod end equity             | `10010.87510985`             |
| **prod Δequity**            | **`+26.20900888`**           |
| shadow start equity         | `10000.0` (flat, num_open 0) |
| shadow end equity           | `10026.20839258`             |
| **shadow Δequity**          | **`+26.20839258`**           |
| **prod-minus-shadow Δequity** | **`+0.0006163`**           |
| overlap includes 2026-07-01T08:00:00 | **Yes**             |

Over the shared window prod and shadow gained **essentially the same amount**
(`+26.209`, differing by `6.2e-4`), consistent with a `matched_null_shadow_v0`
lane that mirrors prod's mark-to-market on a different absolute base and later
start. The prior "prod ≈ shadow overlap" characterization is therefore **not
contradicted** by asserted-identity data — the overlap deltas genuinely agree.
(Absolute levels differ only because the lanes have different `forward_start_ts`
and different realized/fee/funding histories.)

---

## 13. Reader Contamination Audit

Source scan (read-only, no code changed) for output-dir resolution:

- `paper_output_dir()` at [`quantbot/paper/__init__.py:43`](../../quantbot/paper/__init__.py#L43)
  defaults to `/srv/qnty/output/paper_pnl_v1` (prod) when `QNTY_PAPER_OUTPUT_DIR`
  is unset — the confirmed footgun.
- Env/default-dependent callers that could read prod when shadow was intended:
  `scripts/paper_reconcile.py`, `scripts/paper_verify.py`,
  `scripts/qnty-paper-accounting.py`, `quantbot/paper/lane_init.py`,
  `quantbot/paper/config.py`, and the `quantbot/paper/*` engine/runner modules.
  The read-only sidecar `quantbot/sidecars/ledger_ro.py` opens whatever path it is
  handed (`connect_readonly`), so it is only as safe as its caller's path.

**Did the prior `10026.2084` readout use explicit paths, app helpers, or env-dependent resolution?**
The exact invocation is not recoverable from here, but its **result content decides
it**: `10026.2084` equals the shadow-DB latest equity and equals **no** prod value
(prod latest = `10010.875`). A prod-contaminated read would have returned
`10010.875`, not `10026.208`. Therefore the readout **read the correct shadow
lane and was NOT prod-contaminated** — whether it used an explicit `--db-path`,
`QNTY_PAPER_OUTPUT_DIR=…null_shadow_v0`, or an explicit reader. Classification:
**explicit/correct shadow read (env-var lane resolution ruled out as the source of
error, since the answer matches shadow, not the prod default).**

No reader-contamination event is confirmed. The footgun exists in source but did
**not** cause the `10026.2084` figure.

---

## 14. Mutation Guard Checksums

Identical before and after all reads (reads used `mode=ro&immutable=1`; no writer,
no checkpoint, no ALTER, no migration):

| Target                         | Before                                                             | After                                                             | Match |
| ------------------------------ | ----------------------------------------------------------------- | ----------------------------------------------------------------- | ----- |
| prod DB                        | `f8b03faa26ef9f35e28bd61ab1bc95c3e015f23af478e01ff477bde5c4f953c9` | `f8b03faa26ef9f35e28bd61ab1bc95c3e015f23af478e01ff477bde5c4f953c9` | ✔     |
| shadow DB                      | `8ed3fd9a2e506a9bafa1bdc17f1cbe31bddd6984c375e34a116efa5b93c9998c` | `8ed3fd9a2e506a9bafa1bdc17f1cbe31bddd6984c375e34a116efa5b93c9998c` | ✔     |
| forward_obs_v1 (aggregate)     | `9dd2e7e979f52e81f5e1f3b235e6cc6fa29c3c69bfa918e25e6396f52b3de253` | `9dd2e7e979f52e81f5e1f3b235e6cc6fa29c3c69bfa918e25e6396f52b3de253` | ✔     |

---

## 15. Interpretation

- **The live shadow DB is authoritative.** Its lane identity is unambiguous
  (`lane_id=paper_pnl_null_shadow_v0`, `config_hash=32c0fbcc…`,
  `forward_start_ts=2026-06-24T16:00:00`, 11 batches, watermark
  `2026-07-01T08:00:00`), and it is a clearly distinct file/lane from prod.
- **The `10026.2084` ad-hoc readout was correct** and read the true shadow lane.
  It is the genuine shadow batch11 latest equity (open position, unrealized
  `+47.12`). **No retraction of that readout is warranted; it is affirmed.**
- **The browser-mode red-team concern is resolved but inverted:** the value at
  risk was not the readout — it was the **committed receipt**. The batch11
  receipt's §7 "Latest equity snapshot" narrative (`9980.04154734`, num_open 0,
  unrealized 0.0) and its cumulative-count block are a **stale copy-paste from the
  batch5–7 flat era** and do not describe the actual batch11 state. The receipt's
  batch table, watermark, counts-of-batches, git_sha and config_hash remain
  correct.
- **No reader contamination occurred.** The output-dir footgun exists in source
  (`paper_output_dir()` defaults to prod) but did not produce the `10026.2084`
  figure — that figure matches shadow, not the prod default (`10010.875`).
- **Overlap agreement stands:** prod and shadow Δequity over the shared window
  agree to `6.2e-4`, consistent with a matched null shadow. The prior
  "prod ≈ shadow overlap" statement is **not** retracted.
- **No edge, no profitability claim.** All equity/PnL values are paper diagnostics
  only. `EDGE_UNPROVEN` preserved. `CAVEATED_ENGINE_SEMANTICS` preserved.

Recommended follow-up (docs-only, not performed here): correct §7 of
`SHADOW_LANE_BATCH11_MANUAL_PHASE3_RECEIPT.md` to the true batch11 snapshot
(`equity 10026.20839258`, `unrealized_pnl 47.12126882`, `num_open 1`,
`fees_cum 2.49109039`, `funding_cum 0.60256492`) and refresh its cumulative
counts, in a separate PR.

---

## 16. Scope / Exclusions

- Read-only against VM/data; docs-only locally. No writer (prod or shadow) run.
- No prod DB, shadow DB, or live forward_obs mutation (checksums identical, §14).
- No systemd/timer/service changes. No installs, migrations, `ALTER`, or WAL checkpoint.
- No QNTY app helpers that resolve `paper_output_dir()` / `QNTY_PAPER_OUTPUT_DIR`
  were used for reading; DBs opened only by explicit absolute path with
  `file:<path>?mode=ro&immutable=1`.
- No source, test, fixture, or strategy-parameter changes.
- No live trading, no exchange keys, no FrankenTrader wiring.
- No profitability or edge claim.

---

## 17. Verdict

`RECONCILIATION_COMPLETE_RECEIPT_STALE_DB_AUTHORITATIVE`
`EDGE_UNPROVEN`
`CAVEATED_ENGINE_SEMANTICS`
