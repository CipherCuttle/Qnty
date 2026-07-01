# Shadow Lane Batch11 Manual One-Bar Commit — Phase 3 Receipt

**Verdict:** `SHADOW_BATCH11_ONE_BAR_COMMITTED_RECEIPT_READY_FOR_PR`
**Strategy label:** `EDGE_UNPROVEN`
**Funding verdict:** `CAVEATED_ENGINE_SEMANTICS` (NOT `CLEAN_NET_OF_CARRY`)
**Date:** 2026-07-01
**Author:** Manual batch11 writer operator

---

## 1. Purpose

Manually authorized shadow-lane **batch11 one-bar commit** against the existing
shadow lane database. The run:

- reused the existing shadow DB (no recreate / reset / migration),
- executed **exactly one** shadow writer invocation,
- read forward observations from a **frozen `/tmp` snapshot** of `forward_obs_v1`,
- did **not** mutate the production DB,
- did **not** mutate the live forward observer directory,
- touched **no** systemd timers / services,
- placed **no** live trades and used **no** exchange keys.

Strategy remains `EDGE_UNPROVEN`. All equity / PnL figures are **paper
diagnostics only** and constitute no profitability or edge claim.

---

## 2. Prior Wrong-VM Blocked Attempt Notice

The previous Zoocode batch11 writer attempt used the **wrong VM**
(`192.168.1.100`). That attempt:

- created a bad local blocked receipt branch,
- never ran a writer against the correct shadow DB,
- was **discarded** and **not pushed or merged** into any remote branch.

No writer invocation, no snapshot, and no receipt from that attempt reached the
correct VM or the shadow ledger. This receipt documents the **correct-VM
replacement** run only.

**Correct VM target:**

```txt
ssh -i ~/.ssh/hetzner_qnty_key -o IdentitiesOnly=yes viktor@37.27.216.174
```

---

## 3. Authorization Context

The both-lane read-only check showed the shadow watermark was **exactly one 8h
bar** behind forward_obs, making this a one-bar commit authorization:

| Field                          | Value                     |
| ------------------------------ | ------------------------- |
| Shadow watermark (prior)       | `2026-07-01T00:00:00`     |
| forward_obs latest             | `2026-07-01T08:00:00`     |
| Prod watermark (situational)   | `2026-07-01T08:00:00`     |
| Gap                            | 8h = one 8h bar           |
| Expected batch_id              | 11                        |
| Expected committed_bar_count   | 1                         |
| Available bar                  | `2026-07-01T08:00:00`     |
| EDGE_STATUS                    | `EDGE_UNPROVEN`           |
| Funding verdict                | `CAVEATED_ENGINE_SEMANTICS`|

Production lane remained at watermark `2026-07-01T08:00:00` (27+ batches) —
observed read-only as a safety stat only, not modified.

**Authorization token:** `AUTHORIZE_SHADOW_BATCH11_ONE_BAR_WRITER_ONCE_CORRECT_VM`

**Readiness check result:** `READ_ONLY_STATUS_PNL_COMPLETE__SHADOW_READY_FOR_SEPARATE_ONE_BAR_AUTHORIZATION`

---

## 4. Preflight & Command Shape

**Local main SHA:** `1ad25c8` (HEAD == origin/main, clean, synced).
**VM repo SHA:** `fde43a511ef98d7292a6bd93dd9e198ea92f79fe` (allowed for batch11).
**VM venv Python:** `/srv/qnty/venv/bin/python`.
**Timer window:** clear — VM UTC time synced; timer window free of prod timer
clusters (00:20 / 08:20 / 16:20Z). No writer services actively running.

**Safety checksums before:**

| Target                | Checksum / Fingerprint                                       |
| --------------------- | ------------------------------------------------------------ |
| prod DB               | `f8b03faa26ef9f35e28bd61ab1bc95c3e015f23af478e01ff477bde5c4f953c9` |
| live forward_obs      | `3e54430bc9f6a3719d335135789ca97a581d118d77aeeab766471c397227225e` |

**Shadow lane config:**
`/srv/qnty/output/paper_pnl_null_shadow_v0/paper_config.json` present
(`config_hash=32c0fbccdf46af8b50ef0e6d2da9a76657038da621ff2be1dba95d82208d5d52`,
matches DB).

**Required env var:**
`QNTY_PAPER_OUTPUT_DIR=/srv/qnty/output/paper_pnl_null_shadow_v0`
(without it the writer resolves `paper_config.json` from the production dir and
aborts with `CONFIG_ERROR`; the four CLI flags do not select the lane).

**Frozen forward_obs snapshot path:**
`/tmp/qnty_shadow_batch11_manual_run_v0/forward_obs_v1_frozen`
— copied from `/srv/qnty/output/forward_obs_v1`, byte-identical to live,
`observation_log.json` 500 rows, latest bar `2026-07-01T08:00:00`.

**Exact writer command shape (one invocation, run from `/srv/qnty/repo`):**

```bash
QNTY_PAPER_OUTPUT_DIR=/srv/qnty/output/paper_pnl_null_shadow_v0 \
/srv/qnty/venv/bin/python scripts/qnty-paper-sqlite-accounting.py \
  --db-path /srv/qnty/output/paper_pnl_null_shadow_v0/paper_ledger.db \
  --forward-obs-dir /tmp/qnty_shadow_batch11_manual_run_v0/forward_obs_v1_frozen \
  --data-dir /srv/qnty/repo/data \
  --json
```

Verifier run read-only with `--no-emit --json`. DB inspection over a read-only
SQLite connection (`mode=ro`).

---

## 5. Writer Result

- **Exit code:** `0`
- **stdout:** `{"status_code": 0, "status_message": "Committed batch 11: 1 bars, 4 events"}`
- No rerun performed (single invocation only).

Interpretation:

```txt
lane: paper_pnl_null_shadow_v0
batch_id: 11
committed_bar_count: 1
event_count: 4
prior_watermark_bar_ts: 2026-07-01T00:00:00
new_watermark_bar_ts: 2026-07-01T08:00:00
config_hash: 32c0fbccdf46af8b50ef0e6d2da9a76657038da621ff2be1dba95d82208d5d52
git_sha: fde43a511ef98d7292a6bd93dd9e198ea92f79fe
```

This matches the expected one-bar, 4-event commit. The shadow watermark advanced
from `2026-07-01T00:00:00` to `2026-07-01T08:00:00`.

---

## 6. Verifier Result (after writer)

- **Exit code:** `0` — **Status:** `OK` — **failures:** `[]` — **trusted:** `true`
- **Batches:** `11`
- **Watermark:** `2026-07-01T08:00:00`
- **Funding verdict:** `CAVEATED_ENGINE_SEMANTICS` (preserved)
- git provenance: latest batch git_sha `fde43a511ef98d7292a6bd93dd9e198ea92f79fe`,
  no unprovenanced batches.

Known missing funding windows (unchanged from prior batches) remain diagnosed as
`missing_funding_treated_as_zero_like_current_engine_not_net_of_carry_clean` —
not a verifier failure, not `CLEAN_NET_OF_CARRY`.

---

## 7. DB Inspection (after writer, read-only)

- **paper_config.lane_id:** `paper_pnl_null_shadow_v0`
  (`strategy_id=matched_null_shadow_v0`, `strategy_version=0.0.0-shadow`)
- **Batch count after:** `11`; **batch_id=11 occurs exactly once**; max batch_id `11`.
- **integrity_check:** `ok`; single distinct `lane_id`.
- No batch with watermark `> 2026-07-01T08:00:00`.

| batch  | prior watermark        | new watermark          | committed_bars | events |
| ------ | ---------------------- | ---------------------- | -------------- | ------ |
| 1      | `null`                 | `2026-06-25T08:00:00`  | 3              | 13     |
| 2      | `2026-06-25T08:00:00`  | `2026-06-26T00:00:00`  | 2              | 7      |
| 3      | `2026-06-26T00:00:00`  | `2026-06-26T08:00:00`  | 1              | 3      |
| 4      | `2026-06-26T08:00:00`  | `2026-06-27T00:00:00`  | 2              | 8      |
| 5      | `2026-06-27T00:00:00`  | `2026-06-28T00:00:00`  | 3              | 13     |
| 6      | `2026-06-28T00:00:00`  | `2026-06-29T00:00:00`  | 3              | 9      |
| 7      | `2026-06-29T00:00:00`  | `2026-06-29T08:00:00`  | 1              | 4      |
| 8      | `2026-06-29T08:00:00`  | `2026-06-30T00:00:00`  | 2              | 7      |
| 9      | `2026-06-30T00:00:00`  | `2026-06-30T08:00:00`  | 1              | 4      |
| 10     | `2026-06-30T08:00:00`  | `2026-07-01T00:00:00`  | 2              | 8      |
| **11** | `2026-07-01T00:00:00`  | `2026-07-01T08:00:00`  | **1**          | **4**  |

**Batch11:** `committed_bar_count=1`, `event_count=4`,
`lane_id=paper_pnl_null_shadow_v0`,
`git_sha=fde43a511ef98d7292a6bd93dd9e198ea92f79fe`.

**Cumulative counts after batch 11:**

| table             | count |
| ----------------- | ----- |
| ledger_batches    | 11    |
| ledger_events     | 80    |
| signal_snapshots  | 22    |
| equity_snapshots  | 22    |
| trades            | 2     |
| open_positions    | 1     |
| funding           | 10    |
| fills             | 5     |

Latest equity snapshot (`bar_ts=2026-07-01T08:00:00`, batch 11): equity
`9980.04154734`, realized_gross_pnl `-17.81922092`, fees_cum `1.99109039`,
funding_cum `0.14814135`, num_open `0`, unrealized_pnl `0.0` — flat over the new
bar, **paper diagnostics only**.

---

## 8. Safety

- **Production DB unchanged:** before/after checksum
  `f8b03faa26ef9f35e28bd61ab1bc95c3e015f23af478e01ff477bde5c4f953c9` (identical).
- **Live forward_obs unchanged:** before/after fingerprint
  `3e54430bc9f6a3719d335135789ca97a581d118d77aeeab766471c397227225e` (identical).
  Frozen `/tmp` snapshot used as the writer's only input.
- **Shadow DB changed only by the authorized writer:** watermark advanced to
  `2026-07-01T08:00:00`.
- No systemd / timer / service changes.
- No migration, no `ALTER`, no DB reset, no deleted outputs.
- No package installs, no lane init, no VM git pull before run.
- No exchange keys, no orders.
- `.claude/` left untouched / untracked.

---

## 9. Scope / Exclusions

- No live trading, no real orders, no exchange keys.
- No profitability or edge claim. Strategy remains `EDGE_UNPROVEN`.
- Funding verdict remains `CAVEATED_ENGINE_SEMANTICS` (not `CLEAN_NET_OF_CARRY`).
- No strategy parameter changes. No V2 engine work. No recurring shadow timers.

---

## 10. Interpretation

The batch11 one-bar commit demonstrates continued **manual shadow-lane
accounting** over one additional closed bar (`2026-07-01T08:00:00`), bringing the
shadow watermark level with forward_obs and prod (`2026-07-01T08:00:00`), with
internal accounting consistency intact and full git provenance. It does **not**
prove strategy edge. The funding verdict remains `CAVEATED_ENGINE_SEMANTICS`, so
this run is **not** `CLEAN_NET_OF_CARRY`. All PnL / equity values are paper
diagnostics only.

---

## 11. Verdict

`SHADOW_BATCH11_ONE_BAR_COMMITTED_RECEIPT_READY_FOR_PR`
`EDGE_UNPROVEN`