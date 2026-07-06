# QNTY Realized Attribution Snapshot — 2026-07-06

**Snapshot date:** 2026-07-06
**Run timestamp (UTC):** 2026-07-06T17:24:41Z
**Measurement contract:** `docs/status/realized_attribution_spec.md` (spec version 1.0.0)
**Repo commit at snapshot time:** `cfc8862d75d129f9439912db8bc8f00aa826b453`
**Local branch:** `docs/realized-attribution-snapshot-2026-07-06`
**VM repo head (`/srv/qnty/repo`):** `2bd8843` (`main`)
**Type:** docs-only status receipt. This is **not** an edge claim, **not** a
trading recommendation, **not** a live-readiness artifact, and **not** a
verifier/schema/writer/trader change.

This snapshot reports the observed paper ledger state of the two accessible
long-only V2 lanes (prod and shadow) using read-only evidence, with realized
and unrealized figures kept separate, per the canonical measurement contract.

---

## Status Boundary

- `EDGE_UNPROVEN` remains.
- `BLOCK_LIVE_INTEGRATION` remains.
- Full-ledger `CAVEATED_ENGINE_SEMANTICS` remains for both lanes. The prod
  verifier report explicitly records `funding_clean_carry_decision =
  CAVEATED_ENGINE_SEMANTICS`; the shadow verifier report predates the
  clean-carry fields and is stale, so no upgrade is asserted for it either.
- **No batch-scoped `CLEAN_NET_OF_CARRY` is present on either lane.** The prod
  latest batch (batch 48) is `funding_clean_carry_batch_decision =
  CAVEATED_ENGINE_SEMANTICS` (batch arithmetic re-sum is OK, but the clean
  label is refused for a source-coverage reason). Had a `CLEAN_NET_OF_CARRY`
  stamp been present, it would be evidence/accounting quality for that batch
  only — never trading edge, and never a relabel of the full historical ledger.
- This snapshot does not prove edge, profitability, statistical significance,
  shorting readiness, or live readiness.
- No code, trader, decision, signal, writer, verifier, or schema changes are
  made by this snapshot. No writer ran. No database was mutated.

---

## Scope

- **Dated snapshot date:** 2026-07-06.
- **Lanes inspected:** prod paper lane (`paper_pnl_v1`) and shadow paper lane
  (`paper_pnl_null_shadow_v0`) — both accessible and read.
- **Data source paths:**
  - Prod DB: `/srv/qnty/output/paper_pnl_v1/paper_ledger.db`
  - Shadow DB: `/srv/qnty/output/paper_pnl_null_shadow_v0/paper_ledger.db`
- **Watermarks:**
  - Prod: `2026-07-06T08:00:00`
  - Shadow: `2026-07-05T16:00:00`
- **Local repo branch/head:** `docs/realized-attribution-snapshot-2026-07-06`
  @ `cfc8862`.
- **VM repo head:** `2bd8843` (`/srv/qnty/repo`, on `main`). Both ledgers'
  latest committed batch stamps `git_sha =
  2bd88430fe6b2881aaa2b32947002217d3e02ba5`, i.e. the VM repo head.
- **All reads are read-only.** No writer ran. No DB was mutated (see Source
  Integrity / Mutation Proof).

---

## Method

- **Read-only SQL.** Every query used a read-only SQLite connection opened as
  `sqlite3.connect("file:<path>?mode=ro", uri=True)` with `PRAGMA
  query_only=ON`, matching the spec's sanctioned live-file read pattern
  (`quantbot/paper/db.py:133-139`). `mode=ro` (not `immutable=1`) was chosen
  because the prod lane has an active writer and a present (0-byte) WAL, so
  `immutable=1` would be invalid. The Python interpreter was invoked over SSH
  with the script passed on stdin; **no helper file was written to the repo or
  to the VM**, and no temporary files were created.
- **Query categories** followed the spec's Required Read-Only Query Categories:
  (1) lane identity/config/watermark, (2) latest equity snapshot, (3) realized
  closed-trade decomposition, (4) fees/funding open-vs-closed decomposition,
  (5) open-position per-symbol detail, (6) accounting identity residual,
  (7) verifier / clean-carry status from the report artifact, (8) cross-lane
  side-by-side.
- **Verifier fields** were read from each lane's `paper_verify_report.json`
  artifact next to its DB (the verdict lives in the report, not the DB, per
  spec def. #16). No verifier was run by this snapshot; the existing terminal
  reports were read as-is.
- **Mutation proof** used `stat` (size, mtime) and `sha256sum` on both DB files
  before and after all reads (see next section).
- **Fields required by the spec** are all reported below, except the following
  marked `UNAVAILABLE_READ_ONLY`:
  - **Per-symbol unrealized PnL detail (spec category 5 /
    `position_snapshot_symbols.unrealized_gross`):** `UNAVAILABLE_READ_ONLY`.
    In both DBs every `position_snapshot_symbols.unrealized_gross` value is
    stored as `0.0` (prod: 0 of 84 rows nonzero; shadow: 0 of 64 rows nonzero).
    The column is not populated by the writer at mark time, so the spec's
    category-5 cross-check (`SUM(pss.unrealized_gross)` ≈
    `equity_snapshots.unrealized_pnl`) does **not** hold against this column.
    The authoritative unrealized figure is the aggregate
    `equity_snapshots.unrealized_pnl`, which is consistent under the accounting
    identity (residual ≈ 0, below). Recovering a per-symbol unrealized
    breakdown would require recomputing marks from OHLCV, which is out of scope
    for a read-only snapshot.

---

## Source Integrity / Mutation Proof

Captured immediately before the first read and immediately after the last read.

**Prod — `/srv/qnty/output/paper_pnl_v1/paper_ledger.db`**

| | size (bytes) | mtime (epoch) | sha256 |
|---|---|---|---|
| before | 217088 | 1783354846 | `8d21c37406647e2252fd6c7079ac4b55dcfa300b6b94aded9561fc06cc4184d3` |
| after  | 217088 | 1783354846 | `8d21c37406647e2252fd6c7079ac4b55dcfa300b6b94aded9561fc06cc4184d3` |

- **Match status:** identical (size, mtime, sha256 all unchanged).
- **WAL note:** a 0-byte `paper_ledger.db-wal` and a `paper_ledger.db-shm` are
  present (active writer lane); the hash is of the main DB file. Read mode:
  `mode=ro`.

**Shadow — `/srv/qnty/output/paper_pnl_null_shadow_v0/paper_ledger.db`**

| | size (bytes) | mtime (epoch) | sha256 |
|---|---|---|---|
| before | 172032 | 1783312420 | `3cbc6e9c63c74072aa019d6a53b1f5519f369f95cec1f9c21495e307c739a897` |
| after  | 172032 | 1783312420 | `3cbc6e9c63c74072aa019d6a53b1f5519f369f95cec1f9c21495e307c739a897` |

- **Match status:** identical (size, mtime, sha256 all unchanged).
- **WAL note:** no live WAL file present at read time. Read mode: `mode=ro`.

**Verdict: `READ_ONLY_CONFIRMED`** — both DB files are byte-identical before and
after all reads; no mutation occurred.

---

## Lane Summary Table

| Field | Prod (`paper_pnl_v1`) | Shadow (`paper_pnl_null_shadow_v0`) |
|---|---|---|
| DB path | `/srv/qnty/output/paper_pnl_v1/paper_ledger.db` | `/srv/qnty/output/paper_pnl_null_shadow_v0/paper_ledger.db` |
| git SHA (latest batch `git_sha`) | `2bd88430fe6b2881aaa2b32947002217d3e02ba5` | `2bd88430fe6b2881aaa2b32947002217d3e02ba5` |
| `lane_id` | absent / NULL (implicit v1 baseline) | `paper_pnl_null_shadow_v0` |
| `config_hash` | `1d61c1c779107ad194ca12febe620685bbc730edf75a766467fb45c05a74561b` | `32c0fbccdf46af8b50ef0e6d2da9a76657038da621ff2be1dba95d82208d5d52` |
| `config_hash_v2` | absent/NULL (column not present) | `50b1bbeff42d33f4413776ea14cc06281b275b346ab79c279baf959b58ae024c` |
| `strategy_id` / `strategy_version` | absent (v1 baseline) | `matched_null_shadow_v0` / `0.0.0-shadow` |
| Latest committed batch | 48 (of 48; range 1–48) | 17 (of 17; range 1–17) |
| Latest batch window | `2026-07-06T00:00:00` → `2026-07-06T08:00:00` | `2026-07-03T08:00:00` → `2026-07-05T16:00:00` |
| Watermark | `2026-07-06T08:00:00` | `2026-07-05T16:00:00` |
| `forward_start_ts` | `2026-06-20T16:00:00` | `2026-06-24T16:00:00` |
| Verifier `current_verdict` | `OK (simulation)` | `OK (simulation)` — **stale** (verified through watermark `2026-07-01T08:00:00`) |
| Verifier report `verified_at` | `2026-07-06T16:20:46Z` (fresh; report watermark matches DB) | `2026-07-01T18:15:57Z` (stale vs DB watermark) |
| Full-ledger clean-carry | `CAVEATED_ENGINE_SEMANTICS` | `UNAVAILABLE_READ_ONLY` (report predates clean-carry fields) |
| Batch-scoped clean-carry | `CAVEATED_ENGINE_SEMANTICS` (batch 48) | `UNAVAILABLE_READ_ONLY` (report predates batch-scoped fields) |

---

## Realized Attribution Table

All figures as of each lane's watermark. Realized and unrealized are reported
separately and are **never** summed into a single headline.

| Metric | Prod | Shadow |
|---|---|---|
| Initial equity | 10000.00000000 | 10000.00000000 |
| Total equity (mark-to-market) | 10312.77956158 | 10350.80781593 |
| Total equity delta | +312.77956158 | +350.80781593 |
| Realized gross PnL | −36.61557032 | −25.40311929 |
| **Closed-trade realized net PnL (`SUM(trades.net_pnl)`)** | **−43.91342549** | **−28.58037638** |
| Unrealized PnL (`equity_snapshots.unrealized_pnl`) | +362.93382432 | +385.13824051 |
| Fees cumulative | 9.48169221 | 5.48729844 |
| Funding cumulative | 4.05700021 | 3.44000685 |
| Open positions (`num_open`) | 5 | 5 |
| **`N_closed`** | **7** | **3** |
| Fills count | 19 (12 entry / 7 exit) | 11 (8 entry / 3 exit) |
| Accounting identity residual | 0.0 (≤ 1e-6) | 1.82e-12 (≤ 1e-6) |

**Cross-checks (all pass within 1e-6):**

- **Prod realized-gross three-way:** `equity_snapshots.realized_gross_pnl` =
  −36.61557032; `ledger_state.realized_gross` = −36.6155703187; `SUM(trades.gross_pnl)`
  = −36.61557031 — agree.
- **Shadow realized-gross three-way:** `equity_snapshots.realized_gross_pnl` =
  −25.40311929; `ledger_state.realized_gross` = −25.4031192857;
  `SUM(trades.gross_pnl)` = −25.40311928 — agree.
- **Closed-net identity:** `SUM(net_pnl)` = `SUM(gross_pnl) − SUM(fees) −
  SUM(funding)` for both lanes (prod −43.91342549; shadow −28.58037638).
- **Fees decomposition:** prod `fees_cum` 9.48169221 = closed 6.98169222 + open
  entry 2.50000000; shadow 5.48729844 = closed 2.98729844 + open entry
  2.50000000.
- **Funding decomposition:** prod `funding_cum` 4.05700021 = closed 0.31616296
  + open accrual 3.74083724; shadow 3.44000685 = closed 0.18995866 + open
  accrual 3.25004820.

---

## Prod Lane Details

- **Latest batch / window / watermark:** batch 48, window
  `2026-07-06T00:00:00` → `2026-07-06T08:00:00`, watermark
  `2026-07-06T08:00:00`; latest equity snapshot seq 249 at the same bar.
- **Realized / unrealized split:** realized gross PnL is **−36.61557032**
  (negative); the closed-trade realized net PnL is **−43.91342549** after the
  fees and funding charged to closed round-trips. The positive total-equity
  delta of +312.78 is therefore **entirely** attributable to **unrealized
  mark-to-market** on the 5 open long positions (+362.93382432), net of
  still-open-position entry fees and accrued funding. The green equity curve is
  a statement about `equity_snapshots.unrealized_pnl`, not about captured PnL.
- **Closed-trade realized net PnL:** −43.91342549 over `N_closed` = 7 (2 wins,
  5 losses; average hold 2.29 bars).
- **Funding / fees interpretation:** funding cumulative 4.05700021 is a **cost**
  (positive = paid by the long), of which only 0.31616296 belongs to closed
  trades and 3.74083724 is accrued-so-far on still-open positions. Fees
  cumulative 9.48169221 splits 6.98169222 (closed) + 2.50000000 (open-position
  entry fees). This is exactly why the ledger-level net differs from the
  closed-trade realized net and must not be conflated with it.
- **Open positions summary** (long-only engine; the schema has no side column —
  positions are implicitly long):

  | symbol | qty | entry price | entry bar | entry fee | funding accrued | hold bars | per-symbol unrealized |
  |---|---|---|---|---|---|---|---|
  | BNBUSDT | 1.740592184 | 574.517115 | 2026-07-03T16:00:00 | 0.50 | 0.45660148 | 8 | `UNAVAILABLE_READ_ONLY` (stored 0.0) |
  | BTCUSDT | 0.016623484 | 60155.8629 | 2026-07-02T00:00:00 | 0.50 | 1.03496202 | 13 | `UNAVAILABLE_READ_ONLY` (stored 0.0) |
  | ETHUSDT | 0.618674909 | 1616.357775 | 2026-07-02T00:00:00 | 0.50 | 0.92051363 | 13 | `UNAVAILABLE_READ_ONLY` (stored 0.0) |
  | SOLUSDT | 13.528698564 | 73.91694 | 2026-06-29T08:00:00 | 0.50 | 1.06352646 | 21 | `UNAVAILABLE_READ_ONLY` (stored 0.0) |
  | XRPUSDT | 944.617947146 | 1.05862905 | 2026-07-02T00:00:00 | 0.50 | 0.26523364 | 13 | `UNAVAILABLE_READ_ONLY` (stored 0.0) |

  Aggregate unrealized (+362.93382432) is taken from
  `equity_snapshots.unrealized_pnl`; per-symbol decomposition is unavailable
  read-only (see Method).
- **Verifier / evidence status:** `current_verdict = OK (simulation)`,
  `verified_at 2026-07-06T16:20:46Z`, report watermark matches DB watermark
  (fresh). Full-ledger `funding_clean_carry_decision =
  CAVEATED_ENGINE_SEMANTICS` (`status = refused_db_or_lane_mismatch`;
  `reason_codes = [funding_source_snapshot_window_mismatch,
  source_path_unavailable]`). Batch-scoped `funding_clean_carry_batch_decision
  = CAVEATED_ENGINE_SEMANTICS` for target batch 48 (`status =
  refused_source_coverage_issue`; `reason_codes = [source_path_unavailable]`);
  the batch re-sum arithmetic is itself OK (`arithmetic_ok = true`,
  `funding_amount_sum 4.05700022` over 79 funding rows vs `funding_cum
  4.05700021`), but complete arithmetic is necessary-not-sufficient for the
  clean label, which stays caveated.
- **Interpretation:** observed paper ledger state shows negative realized
  closed-trade net PnL with the paper account only above water because of
  unrealized long marks. `EDGE_UNPROVEN`.

---

## Shadow Lane Details

- **Latest batch / window / watermark:** batch 17, window
  `2026-07-03T08:00:00` → `2026-07-05T16:00:00`, watermark
  `2026-07-05T16:00:00`; latest equity snapshot seq 175 at the same bar.
- **Staleness:** the shadow DB has advanced to watermark `2026-07-05T16:00:00`,
  but its `paper_verify_report.json` was last written `2026-07-01T18:15:57Z`
  verifying through watermark `2026-07-01T08:00:00`. The verifier report is
  therefore **stale by roughly four days of bars** relative to the current
  shadow DB, and it predates the clean-carry report fields entirely (no
  `funding_clean_carry*` keys). Shadow clean-carry status is therefore recorded
  as `UNAVAILABLE_READ_ONLY` rather than assumed.
- **Realized / unrealized split:** realized gross PnL −25.40311929; closed-trade
  realized net PnL −28.58037638; unrealized +385.13824051. As with prod, the
  positive equity delta (+350.81) is entirely unrealized mark-to-market on 5
  open long positions.
- **Closed-trade realized net PnL:** −28.58037638 over `N_closed` = 3 (1 win,
  2 losses; average hold 2.0 bars).
- **Funding / fees interpretation:** funding cumulative 3.44000685 (closed
  0.18995866 + open accrual 3.25004820); fees cumulative 5.48729844 (closed
  2.98729844 + open entry 2.50000000). Same cost-to-long convention as prod.
- **Open positions summary** (long-only; implicitly long): identical 5 symbols
  and identical qty/entry-price to the prod open book (BNBUSDT, BTCUSDT,
  ETHUSDT, SOLUSDT, XRPUSDT), with smaller accrued funding and hold bars
  because the shadow window ends two bars earlier and started later. Per-symbol
  unrealized is `UNAVAILABLE_READ_ONLY` (stored 0.0), same as prod.
- **Verifier / evidence status:** `current_verdict = OK (simulation)` but
  **stale** as described; `trusted = true`, `exit_code = 0`, `failure_count =
  0` in the report as written, applicable only through its own (older)
  watermark. Clean-carry fields absent → `UNAVAILABLE_READ_ONLY`.
- **Interpretation:** the shadow lane is an identity/replication control; its
  realized closed-trade net PnL is also negative on a very small `N_closed`.
  `EDGE_UNPROVEN`.

---

## Prod vs Shadow Comparison

- **The shadow lane is an identity/replication control, not an alpha null and
  not a benchmark.** Prod/shadow agreement is evidence of reproducibility,
  never of edge. The shadow is never counted as an alpha null and is not
  modified by this program.
- **Only compatible windows may be compared, and these endpoints are not
  compatible.** Prod watermark is `2026-07-06T08:00:00` (batch 48); shadow
  watermark is `2026-07-05T16:00:00` (batch 17). The lanes also have different
  `forward_start_ts` (prod `2026-06-20T16:00:00`, shadow `2026-06-24T16:00:00`)
  and different config identities (`config_hash` differs; shadow is a distinct
  `lane_id`). **Headline PnL is therefore not compared as if equivalent, and
  the two lanes' figures are never summed or averaged** (per spec query
  category 8).
- **What is observable as a reproducibility signal (not edge):** the two lanes
  currently hold the **same 5 open symbols with identical qty and entry
  price**. The differences that exist — realized gross (−36.62 vs −25.40),
  `N_closed` (7 vs 3), fills (19 vs 11), funding/fees cumulative, and accrued
  funding per position — are attributable to the **different history length,
  window endpoints, forward-start dates, and number of closed round-trips**,
  not to any edge difference. No directional or alpha conclusion is drawn from
  the comparison.

---

## Interpretation

- **Realized closed-trade performance is the primary evidence.** For both lanes
  the closed-trade realized net PnL is negative (prod −43.91342549; shadow
  −28.58037638).
- **Unrealized marks are secondary and reversible.** The entire positive
  total-equity delta on both lanes is unrealized mark-to-market on open long
  positions; it is a mark, not a capture, and can reverse before it is
  realized.
- **Current evidence does not establish edge.** `EDGE_UNPROVEN`.
- **Small `N_closed` prevents statistical interpretation.** With `N_closed` = 7
  (prod) and 3 (shadow), no Sharpe/Sortino/PSR/DSR-style statistic is
  interpretable; these samples are far below any plausible minimum track record
  length.
- **No annualized or extrapolated projection** is made from these samples.
- **No live implication.** `BLOCK_LIVE_INTEGRATION` stands.
- **No shorting implication.** The engine remains long-only; shorting remains an
  untested, preregistered hypothesis.

---

## What This Snapshot Proves

- The dated ledger state of both accessible lanes was read read-only on
  2026-07-06.
- The realized vs unrealized split is recorded, with realized closed-trade net
  PnL as the headline realized figure and unrealized mark-to-market reported
  separately.
- Evidence-quality labels (verifier verdicts, full-ledger and batch-scoped
  clean-carry states, staleness of the shadow report) are recorded.
- Source-integrity / mutation proof is recorded and confirms both DBs were
  unchanged by the reads (`READ_ONLY_CONFIRMED`).

---

## What This Snapshot Does Not Prove

- **No edge.** `EDGE_UNPROVEN`.
- **No profitability** beyond the observed paper/accounting values themselves;
  realized closed-trade net PnL is negative on both lanes.
- **No statistical significance.** `N_closed` is far below any plausible minimum
  track record length.
- **No live readiness.** `BLOCK_LIVE_INTEGRATION` stands.
- **No shorting readiness.**
- **No full-ledger clean-status upgrade.** Full-ledger
  `CAVEATED_ENGINE_SEMANTICS` stands; only an explicit read-only verifier report
  can ever change it, and none does here.
- **No authorization** to change code, create lanes, or trade.

---

## Non-Goals

- No code.
- No scripts.
- No DB writes.
- No writer run.
- No trader / decision / signal change.
- No verifier change (no verifier was run; existing reports were read as-is).
- No schema change.
- No null model.
- No benchmark run.
- No trial registry.
- No JSONL implementation.
- No live integration.
- No leverage.

---

## Reproduction Notes

All reads are read-only; no file is written to the repo or the VM.

1. **VM head + before-mutation proof:**
   `git -C /srv/qnty/repo rev-parse --short HEAD`;
   `stat -c "%n %s %Y" <prod.db> <shadow.db>`;
   `sha256sum <prod.db> <shadow.db>`.
2. **Read-only connection:** `sqlite3.connect("file:<db>?mode=ro", uri=True)`
   then `PRAGMA query_only=ON` (spec live-file pattern, `quantbot/paper/db.py`).
   Do not use `immutable=1` on the prod lane (active writer / present WAL).
3. **Query categories (per `docs/status/realized_attribution_spec.md`):**
   - cat 1: `paper_config` (id=1), `ledger_state` (id=1), latest committed
     `ledger_batches` row.
   - cat 2: latest `equity_snapshots` by `seq`.
   - cat 3: aggregate over `trades` (`COUNT(*)`, `SUM(gross_pnl/fees/funding/
     net_pnl)`, win/loss, `AVG(hold_bars)`).
   - cat 4: aggregate over `open_positions` (`COUNT(*)`, `SUM(entry_fee)`,
     `SUM(funding_accrued)`).
   - cat 5: `open_positions` LEFT JOIN `position_snapshot_symbols` at the latest
     `position_snapshots.seq` (note: `unrealized_gross` is stored 0.0 — per
     Method).
   - cat 6: accounting-identity residual on the latest `equity_snapshots` row.
   - cat 7: read `paper_verify_report.json` next to each DB for
     `current_verdict` and `funding_clean_carry*` fields.
   - cat 8: run cats 1–7 per lane, present side by side, never summed.
4. **After-mutation proof:** repeat `stat` + `sha256sum`; confirm byte-identity.

---

## Open Questions

None of these block this snapshot.

- Whether to automate this snapshot later (standalone read-only script vs a
  verifier-adjacent reporter reusing `quantbot/sidecars/ledger_ro.py`).
- Whether future dated snapshots belong in `docs/status/` next to the spec or
  under `docs/verdicts/` with other dated status artifacts.
- Whether an append-only trial registry should link snapshot IDs.
- The exact MinTRL-derived minimum `N_closed` (and `N_closed_short`) to
  preregister before any scoring.
- The exact benchmark/null generation methods (all future work; none run here).
- Whether the shadow lane's verifier report should be refreshed so its
  clean-carry fields and watermark are current (a separate, verifier-only,
  read-only action — not part of this docs snapshot).
- Whether the writer should populate `position_snapshot_symbols.unrealized_gross`
  so per-symbol unrealized detail becomes available read-only (currently stored
  0.0; a writer/schema concern, out of scope here).

---

## Verdict

`REALIZED_ATTRIBUTION_SNAPSHOT_RECORDED_EDGE_UNPROVEN`

---

*This snapshot is docs-only. No writer ran, no database was mutated (both DBs
byte-identical before and after reads: `READ_ONLY_CONFIRMED`), no
trader/decision/signal/verifier/schema/writer code was modified, no test
changed. `EDGE_UNPROVEN`, `BLOCK_LIVE_INTEGRATION`, and full-ledger
`CAVEATED_ENGINE_SEMANTICS` are preserved. This document authorizes no code, no
lane, no registry, and no live integration.*
