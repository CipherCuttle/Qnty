# QNTY Realized Attribution Status Spec

**Spec version:** 1.0.0
**Date:** 2026-07-06
**Type:** measurement contract (docs-only; defines language and queries, produces no numbers)
**Plan of record:** `docs/plans/QNTY_REALIZED_ATTRIBUTION_AND_SHORTING_RESEARCH_FOUNDATION.md` (first PR)

---

## Status Boundary

- `EDGE_UNPROVEN` remains. Nothing in this spec claims, implies, or is designed
  to manufacture an edge claim.
- `BLOCK_LIVE_INTEGRATION` remains. No live exchange integration, no live
  capital, no live-readiness implication. This document is the canonical repo
  home for that label: it may now be cited as
  `docs/status/realized_attribution_spec.md` § Status Boundary instead of being
  re-asserted per audit conversation.
- Full-ledger `CAVEATED_ENGINE_SEMANTICS` remains unless an explicit verifier
  report (`paper_verify_report.json`, produced by
  `quantbot/paper/sqlite_verify.py`) says otherwise via its
  `funding_clean_carry_decision` field.
- A batch-scoped `CLEAN_NET_OF_CARRY` stamp
  (`funding_clean_carry_batch_decision`, PR #77), when present, is
  **evidence/accounting quality for the latest batch only** — it is not
  trading edge, and it never relabels the full historical ledger.
- This document defines **measurement language only**. It does not prove edge,
  profitability, live readiness, shorting readiness, or statistical
  significance.

---

## Purpose

QNTY needs a canonical answer to the question *"what has actually been
earned?"* Today the honest answer has three parts, and none of them has a
first-class repo artifact:

1. **Total equity can be dominated by unrealized open-position marks.** The
   equity curve being green tells you about `equity_snapshots.unrealized_pnl`,
   not about captured PnL. In Perold's (1988) terms, the unrealized mark is a
   paper return, not a captured one — even inside a paper system, the
   realized/unrealized split is the line between measurement and impression.
2. **Realized and unrealized attribution must be separated, with funding and
   fees explicit.** The ledger already stores everything needed
   (`trades`, `equity_snapshots`, `funding`, `fills`, `open_positions`), but
   no doc defines which columns constitute "realized attribution" and how they
   decompose.
3. **`N_closed` must be explicit in every status output.** A realized figure
   without its sample size invites statistical claims that a small `N_closed`
   cannot support (Bailey & López de Prado's minimum track record length
   argument). Every snapshot must report `N_closed` so every future claim can
   be checked against a sample-size floor.

Future shorting research (`docs: add shorting v3 research hypothesis`, the
second PR in the plan of record) must motivate itself against **realized,
net-of-carry attribution as defined here** — not against total equity, not
against ad-hoc SQL, not against the visual impression of a curve.

---

## Definitions

Every definition below is bound to the canonical SQLite schema in
`quantbot/paper/db.py` (STRICT tables, append-only triggers) and the semantics
doc `docs/paper_pnl_v1_schema.md`. No column named here is invented; a
reviewer can check each against the DDL.

| # | Term | Definition | Canonical source | Cross-check | Caveat |
|---|------|-----------|------------------|-------------|--------|
| 1 | **initial equity** | Starting capital of the lane. | `paper_config.initial_equity_usd` (`quantbot/paper/db.py:159`) | `sqlite_verify.py` reads the same column (`quantbot/paper/sqlite_verify.py:905`) | Singleton row (`id = 1`); write-once by trigger. |
| 2 | **total equity** | Mark-to-market account value at the watermark bar. | `equity_snapshots.equity` at the latest `bar_ts` (`quantbot/paper/db.py:344`) | Recompute via the accounting identity (below) | Includes unrealized marks; never quote as "profit". |
| 3 | **realized gross PnL** | Cumulative price PnL of **closed round-trips only**, before fees and funding. | `equity_snapshots.realized_gross_pnl` at watermark | `SUM(trades.gross_pnl)` over all `trades` rows; `ledger_state.realized_gross` (`quantbot/paper/db.py:362`) | All three must agree within tolerance; disagreement is a ledger fault, not a reporting choice. |
| 4 | **closed-trade realized net PnL** | What closed round-trips actually netted after their own fees and funding. | `SUM(trades.net_pnl)` (`quantbot/paper/db.py:299`) | `SUM(trades.gross_pnl - trades.fees - trades.funding)` — must equal `SUM(net_pnl)` within tolerance | See the realized-net distinction below; **not** the same number as `realized_gross - fees_cum - funding_cum`. |
| 5 | **unrealized PnL** | Mark-to-market gross PnL on currently open positions. | `equity_snapshots.unrealized_pnl` at watermark | Per-symbol detail: `position_snapshot_symbols.unrealized_gross` for the latest snapshot (`quantbot/paper/db.py:339`) | Gross of the exit fee and of future funding; it is a mark, not a capture. |
| 6 | **funding cumulative** | Accumulated funding **cost** across the whole lane history (closed trades + accrual-so-far on open positions). | `equity_snapshots.funding_cum` at watermark; `ledger_state.funding_cum` | Event detail: `funding.funding_amount` rows (`quantbot/paper/db.py:318`) | Cost convention: positive = paid by the (long) position. "Long pays when the rate is positive" (`docs/paper_pnl_v1_schema.md:691`). |
| 7 | **fees cumulative** | Accumulated fee **cost**: entry+exit fees of closed trades plus entry fees of still-open positions (`docs/paper_pnl_v1_schema.md` §3.2). | `equity_snapshots.fees_cum` at watermark; `ledger_state.fees_cum` | Event detail: `fills.fee` per fill; `trades.fees` per closed round-trip; `open_positions.entry_fee` for open entries | Includes open-position entry fees — this is why ledger-level nets differ from closed-trade nets. |
| 8 | **open positions** | Currently held (long-only) positions. | `open_positions` rows: `symbol`, `qty`, `entry_price`, `entry_fee`, `funding_accrued`, `hold_bars` (`quantbot/paper/db.py:373-382`) | Latest `position_snapshots` row + `position_snapshot_symbols` children | Mutable table by design; the engine is long-only (`quantbot/paper/engine.py:373`, `:428` — only `BUY` entry / `SELL` exit exist). |
| 9 | **closed trades** | Completed round-trips through the fill model. | `trades` rows: `gross_pnl`, `fees`, `funding`, `net_pnl`, `hold_bars`, `entry_bar_ts`, `exit_bar_ts` (`quantbot/paper/db.py:283`) | Each links `entry_fill_id`/`exit_fill_id` back to `fills` | Append-only; the only rows in the ledger that reflect completed capture. |
| 10 | **fills** | Individual executions under the `next_bar_open_pessimistic` fill model. | `fills` rows: `side` (`BUY`/`SELL`), `kind` (`entry`/`exit`), `qty`, `fill_price`, `slippage_bps`, `fee` (`quantbot/paper/db.py:264`) | `paper_config.fill_model` names the model | Paper fills; no market impact model beyond configured slippage. |
| 11 | **`N_closed`** | `COUNT(*)` of `trades` rows for the lane (and, where relevant, per batch range via `trades.batch_id`). | `trades` table | — | **Required in every status output.** No statistic computed on realized returns may be quoted without its `N_closed`. |
| 12 | **watermark** | The last bar the ledger has committed through. | `ledger_state.watermark_bar_ts` (`quantbot/paper/db.py:361`) | `ledger_batches.new_watermark_bar_ts` of the latest committed batch; latest `equity_snapshots.bar_ts` | All snapshot figures are "as of watermark". |
| 13 | **batch id** | Identifier of one writer commit (one `BEGIN IMMEDIATE` transaction). | `ledger_batches.batch_id` (`quantbot/paper/db.py:189`) | `ledger_events.batch_id` on every event row | Batch-scoped clean-carry stamps attach to exactly one `batch_id`. |
| 14 | **lane identity** | Which ledger (prod, shadow, future lanes) a number came from. | `paper_config.lane_id` (nullable; NULL = implicit v1 baseline), `ledger_batches.lane_id` per-batch stamp; resolution modules `quantbot/paper/lane_identity.py`, `lane_config_hash.py` | Output-dir/db-path resolution (see Read-Only IO Requirements) | A number without a lane label is invalid under this spec. |
| 15 | **config hash / config hash v2** | Digest of the lane's configuration identity. | `paper_config.config_hash` (required); `paper_config.config_hash_v2` (nullable, additive new-lane column) | `ledger_batches.config_hash` stamped per batch | `config_hash_v2` may be NULL on the v1 baseline; report it as absent, do not fabricate. |
| 16 | **verifier decision fields** | The authoritative trust verdict for a frozen DB snapshot. | `paper_verify_report.json` written by `quantbot/paper/sqlite_verify.py`: `current_verdict` (`OK` / `CORRUPT`, constants at `sqlite_verify.py:111-113`) | Human receipt `paper_verify_receipt.md`; append-only `paper_verify_log.jsonl` (non-gating) | The verdict lives in the report **artifact**, not in the DB (authority model: `docs/paper_pnl_v1_schema.md` §5a). |
| 17 | **full-ledger funding clean-carry fields** | Whole-history carry-accounting cleanliness. | Report fields `funding_clean_carry_decision`, `funding_clean_carry_status`, `funding_clean_carry_reason_codes` (`quantbot/paper/sqlite_verify.py:2556-2558`) | Values: `CLEAN_NET_OF_CARRY` / `CAVEATED_ENGINE_SEMANTICS`; fail-closed on digest mismatch or missing DB-linked snapshot | Currently `CAVEATED_ENGINE_SEMANTICS`; this spec does not change that. |
| 18 | **batch-scoped funding clean-carry fields** | Latest-batch-only carry cleanliness (PR #77). | Report fields `funding_clean_carry_batch_decision`, `funding_clean_carry_batch_status`, `funding_clean_carry_batch_reason_codes`, `funding_clean_carry_batch` (`quantbot/paper/sqlite_verify.py:2585-2588`) | Contract test: `tests/test_paper_sqlite_verify_batch_scoped_clean_carry.py` | Scoped to the latest batch only; never relabels the full ledger; accounting quality, not edge. |

### The realized-net distinction (normative)

Two quantities both sound like "realized net PnL" and **must never be
conflated**:

- **Closed-trade realized net PnL** = `SUM(trades.net_pnl)`
  = `SUM(trades.gross_pnl - trades.fees - trades.funding)`.
  This is per-round-trip attribution: only the fees and funding actually
  charged to closed trades.
- **Ledger-level net** = `realized_gross - fees_cum - funding_cum` (from
  `equity_snapshots` or `ledger_state`).
  Per `docs/paper_pnl_v1_schema.md` §3.2, `fees_cum` includes the **entry fees
  of still-open positions** and `funding_cum` includes **funding accrued so
  far on still-open positions** (mirrored per-position in
  `open_positions.entry_fee` and `open_positions.funding_accrued`).

The ledger-level net therefore mixes open-position costs into a "realized"
arithmetic and must **not** be casually called "closed-trade realized net"
unless the decomposition queries below have verified the difference and the
open-position cost components are reported alongside it. Snapshots must report
the closed-trade figure as the headline realized-net number and may report the
ledger-level net only with its open-cost components broken out.

---

## Accounting Identity

The repo's proven identity, enforced by the writer's replay reconciliation at
`quantbot/paper/sqlite_writer.py:913-919` and re-verified per batch by
`quantbot/paper/sqlite_verify.py` (equity balance arithmetic, e.g. `:941`),
with semantics defined in `docs/paper_pnl_v1_schema.md` §3.2:

```
equity = initial_equity + realized_gross_pnl - fees_cum - funding_cum + unrealized_pnl
```

- **Sign convention, fees:** `fees_cum` is an accumulated **cost** (positive =
  paid) and is **subtracted**.
- **Sign convention, funding:** `funding_cum` is an accumulated **cost**
  (positive = paid by the long; "long pays when the rate is positive",
  `docs/paper_pnl_v1_schema.md:691`) and is **subtracted**. Event-level
  `funding.funding_amount = notional_at_mark * funding_rate` carries the same
  convention.
- **Tolerance:** absolute `1e-6`, matching both the writer's enforcement
  (`sqlite_writer.py:913-919`) and the verifier's `_ABS_TOL = 1e-6`
  (`quantbot/paper/sqlite_verify.py:198`). This spec **adopts** the verifier's
  tolerance; it does not invent a new one. (The verifier's `_TIGHT_TOL = 1e-8`
  applies to drawdown arithmetic, not to this identity.)
- **Residual requirement:** every dated snapshot must recompute the identity
  from its parts and report the residual
  `equity − (initial_equity + realized_gross_pnl − fees_cum − funding_cum + unrealized_pnl)`.
  A residual with `abs(residual) > 1e-6` invalidates the snapshot (it
  indicates a ledger fault, and the correct response is a verifier run, not a
  status report).

---

## Required Read-Only Query Categories

This section specifies queries; it does not add a script (a reporting script
is explicitly "later, not now" in the plan of record). Templates below are
SQLite-compatible, read-only, deterministic, watermark-scoped where
applicable, and independent of any writer execution. `?` placeholders are
standard SQLite parameters.

### 1. Lane identity / config / watermark

```sql
SELECT id, db_schema_version, paper_contract_version, paper_engine_version,
       baseline_label, forward_start_ts, initial_equity_usd,
       fill_model, signal_source, config_hash,
       lane_id, strategy_id, strategy_version, config_hash_v2
FROM paper_config WHERE id = 1;

SELECT watermark_bar_ts, realized_gross, fees_cum, funding_cum,
       peak_equity, updated_at
FROM ledger_state WHERE id = 1;

SELECT batch_id, committed_at, new_watermark_bar_ts, event_count,
       committed_bar_count, config_hash, lane_id,
       funding_source_snapshot_path, funding_source_snapshot_sha256,
       funding_source_snapshot_bundle_sha256,
       funding_source_snapshot_write_state
FROM ledger_batches
WHERE committed_at IS NOT NULL
ORDER BY batch_id DESC LIMIT 1;
```

### 2. Latest equity snapshot

```sql
SELECT seq, batch_id, bar_ts, realized_gross_pnl, unrealized_pnl,
       funding_cum, fees_cum, equity, drawdown, num_open
FROM equity_snapshots
ORDER BY seq DESC LIMIT 1;
```

### 3. Realized closed-trade decomposition

```sql
SELECT COUNT(*)                                   AS n_closed,
       SUM(gross_pnl)                             AS realized_gross_sum,
       SUM(fees)                                  AS closed_fees_sum,
       SUM(funding)                               AS closed_funding_sum,
       SUM(net_pnl)                               AS closed_net_sum,
       SUM(CASE WHEN net_pnl > 0 THEN 1 ELSE 0 END) AS n_wins,
       SUM(CASE WHEN net_pnl <= 0 THEN 1 ELSE 0 END) AS n_losses,
       AVG(hold_bars)                             AS avg_hold_bars
FROM trades;
```

Consistency requirements: `realized_gross_sum` must match
`equity_snapshots.realized_gross_pnl` and `ledger_state.realized_gross` within
`1e-6`; `closed_net_sum` must equal
`SUM(gross_pnl) - SUM(fees) - SUM(funding)` within `1e-6`.

### 4. Fees/funding decomposition (open vs closed)

```sql
-- Costs attributable to closed trades (already in category 3):
SELECT SUM(fees) AS closed_fees, SUM(funding) AS closed_funding FROM trades;

-- Costs carried by still-open positions:
SELECT COUNT(*)            AS n_open,
       SUM(entry_fee)      AS open_entry_fees,
       SUM(funding_accrued) AS open_funding_accrued
FROM open_positions;
```

Consistency requirements (from `docs/paper_pnl_v1_schema.md` §3.2):
`fees_cum ≈ closed_fees + open_entry_fees` and
`funding_cum ≈ closed_funding + open_funding_accrued`, each within `1e-6`.
These two checks are what license (or forbid) any ledger-level net claim.

### 5. Open-position / unrealized per-symbol detail

```sql
SELECT op.symbol, op.qty, op.entry_price, op.entry_bar_ts,
       op.entry_fee, op.funding_accrued, op.hold_bars,
       pss.unrealized_gross
FROM open_positions op
LEFT JOIN position_snapshot_symbols pss
  ON pss.symbol = op.symbol
 AND pss.snapshot_seq = (SELECT seq FROM position_snapshots
                         ORDER BY seq DESC LIMIT 1)
ORDER BY op.symbol;
```

`SUM(pss.unrealized_gross)` must match the latest
`equity_snapshots.unrealized_pnl` within `1e-6`.

### 6. Accounting identity residual

```sql
SELECT eq.equity
       - ((SELECT initial_equity_usd FROM paper_config WHERE id = 1)
          + eq.realized_gross_pnl - eq.fees_cum - eq.funding_cum
          + eq.unrealized_pnl)     AS identity_residual
FROM equity_snapshots eq
ORDER BY eq.seq DESC LIMIT 1;
```

`abs(identity_residual)` must be `<= 1e-6` (see Accounting Identity).

### 7. Latest verifier / clean-carry status

The verifier verdict and clean-carry decisions are **not stored in the DB**.
They live in the verifier's report artifact `paper_verify_report.json`
(authoritative latest terminal report, written next to the DB;
`quantbot/paper/sqlite_verify.py:193-195`, authority model in
`docs/paper_pnl_v1_schema.md` §5a). A snapshot must therefore **cite the
report artifact**: its path, its `current_verdict`, its
`funding_clean_carry_decision` / `_status` / `_reason_codes` (full-ledger),
and its `funding_clean_carry_batch_decision` / `_status` / `_reason_codes`
plus the stamped batch id (batch-scoped). The DB itself carries only the
DB-linked funding-source snapshot references on `ledger_batches` (category 1),
which the snapshot must also record.

### 8. Cross-lane comparison (prod vs shadow)

Cross-lane reporting must run the same categories 1–7 against each lane's DB
**separately**, resolved per the Read-Only IO Requirements below, and present
results side by side with an explicit lane column on every row. Prod and
shadow figures must never be summed, averaged, or presented in one column.
The shadow lane is an identity/replication control
(`docs/plans/QNTY_V1_SHADOW_ASSERTED_IDENTITY_PNL_RECONCILIATION_AFTER_BATCH11.md`);
prod/shadow agreement is evidence of **reproducibility**, never of edge.

---

## Read-Only IO Requirements

- **Connection mode:** use SQLite read-only URI mode. The repo provides two
  sanctioned patterns:
  - live-file reads: `file:<path>?mode=ro` + `PRAGMA query_only=ON`
    (`quantbot.paper.db.connect_readonly`, `quantbot/paper/db.py:133-139`),
    snapshot-pinned via `BEGIN` + first read as in
    `quantbot/sidecars/ledger_ro.py` (`open_ro`);
  - frozen-copy reads: `file:<path>?mode=ro&immutable=1` + `PRAGMA
    query_only=ON` as the verifier does for frozen snapshots
    (`quantbot/paper/sqlite_verify.py:3351`). `immutable=1` is only valid on a
    file no writer can touch.
- **No writer** runs to produce a snapshot. Writer exit codes are runner
  status only; trust comes from the verifier report.
- **No migrations, no schema-ensure helpers** — a snapshot never creates or
  alters tables.
- **No WAL-mutating operations** — no checkpoints, no `wal_checkpoint`
  pragmas, no journal-mode changes.
- **No DB mutation of any kind, no snapshot rewriting** — dated snapshots are
  append-only artifacts; a wrong snapshot is superseded by a new dated
  snapshot, never edited in place.
- **Every snapshot must record:** DB path, lane and how it was resolved
  (explicit `--db-path` / `QNTY_PAPER_DB_PATH` per
  `quantbot/paper/db.py:45,69`, or output-dir resolution via
  `paper_output_dir()` / `QNTY_PAPER_OUTPUT_DIR`,
  `quantbot/paper/__init__.py:38-43`), read mode used (`mode=ro` vs
  `mode=ro&immutable=1`), DB file sha256 at read time, watermark `bar_ts`,
  latest `batch_id`, and the spec version of this document. A snapshot missing
  any of these is not a valid snapshot.
  - *WAL caveat:* physical file hashes are noisy under WAL churn
    (`quantbot/sidecars/ledger_ro.py` header). The sha256 must be taken of the
    main DB file at read time with WAL presence noted; a snapshot may
    additionally record the sidecar's logical `head_fingerprint` for a
    churn-stable identity.

---

## Required Snapshot Fields

A future dated snapshot (e.g. `docs/status/realized_attribution_YYYY-MM-DD.md`)
must contain **all** of the following:

**Provenance**

- spec version (of this document)
- run timestamp (UTC)
- repo commit (`git rev-parse HEAD` at snapshot time)
- DB path
- DB sha256 (with WAL-presence note; optional logical `head_fingerprint`)
- lane + resolution mode (see Read-Only IO Requirements)
- read mode (`mode=ro` vs `mode=ro&immutable=1`)
- `config_hash`; `config_hash_v2` if present (report "absent/NULL" otherwise)
- watermark (`ledger_state.watermark_bar_ts`)
- latest committed `batch_id`

**Verifier citation**

- verifier report artifact path and its `current_verdict`
- full-ledger clean-carry: `funding_clean_carry_decision`, `_status`,
  `_reason_codes`
- batch-scoped clean-carry: `funding_clean_carry_batch_decision`, `_status`,
  `_reason_codes`, and the batch id it stamps

**Attribution figures** (all from the query categories above)

- initial equity
- total equity
- realized gross PnL (with its three-way cross-check result)
- closed-trade realized net PnL (`SUM(trades.net_pnl)`)
- unrealized PnL (with per-symbol detail or a pointer to it)
- funding cumulative (with closed vs open-accrual decomposition)
- fees cumulative (with closed vs open-entry decomposition)
- open positions count (`num_open` / `COUNT(open_positions)`)
- closed trades count — **`N_closed`**
- accounting identity residual (must be `<= 1e-6` in absolute value)

**Required labels, verbatim**

- `EDGE_UNPROVEN`
- `BLOCK_LIVE_INTEGRATION`
- `CAVEATED_ENGINE_SEMANTICS` (full-ledger, if still applicable per the cited
  verifier report), plus the batch-scoped clean-carry state for the latest
  batch

---

## Required Language

**Safe phrasing** (use these exact terms):

- "realized gross PnL"
- "closed-trade realized net PnL"
- "unrealized PnL"
- "current mark-to-market"
- "batch-scoped accounting cleanliness"
- "EDGE_UNPROVEN"

**Forbidden unless separately proven** (none are provable from attribution
snapshots alone):

- "edge"
- "profitable strategy"
- "works"
- "ready"
- "live-ready"
- "shorting-ready"
- "alpha proven"
- any annualized or extrapolated projection from the current sample
- treating unrealized PnL as captured profit

**Composition rules:**

- Realized and unrealized figures must never be summed into a single "profit"
  headline.
- The word "gain" without the qualifier "unrealized" is prohibited when
  referring to open-position marks.
- No statistic on realized returns may be quoted without its `N_closed`.

---

## Relationship To Shorting Research

- This spec must exist **before** `docs: add shorting v3 research hypothesis`
  (the second PR in the plan of record). The shorting hypothesis is a claim
  about improving *realized, net-of-carry* PnL — a quantity that is undefined
  until this spec defines it.
- Shorting research must cite realized attribution as defined here — never
  total equity alone, which is currently dominated by unrealized long marks.
- Shorting **code** remains out of scope entirely: the engine's long-only
  invariant (`BUY` entry / `SELL` exit only, `quantbot/paper/engine.py:373`,
  `:428`) is untouched by this spec and by the shorting hypothesis doc.
- The current prod and shadow long-only lanes must not be modified; any future
  short experiment would run in a dedicated future lane.
- A future short hypothesis must define its own realized net-of-carry metrics
  **in terms of this spec's definitions**, including an explicit statement of
  the funding sign convention for shorts relative to the existing
  `funding.funding_amount` cost-to-long convention (Open Question 1 in the
  plan of record).

---

## Acceptance Criteria For This PR

1. `docs/status/realized_attribution_spec.md` exists (this file; it creates
   `docs/status/`).
2. All definitions are bound to actual repo schema/code paths
   (`quantbot/paper/db.py` DDL, `docs/paper_pnl_v1_schema.md`,
   `quantbot/paper/sqlite_writer.py`, `quantbot/paper/sqlite_verify.py`).
3. The accounting identity matches the writer's enforced identity
   (`quantbot/paper/sqlite_writer.py:913-919`) and the verifier's tolerance
   (`_ABS_TOL = 1e-6`) exactly.
4. All query templates/categories are read-only and lane-explicit.
5. Status Boundary labels are present verbatim.
6. The doc explicitly states what it proves and does not prove (next two
   sections).
7. No code, tests, configs, DBs, writers, verifiers, or trader/decision/signal
   files touched — the PR diff contains only this file.
8. `git diff --check` passes.

---

## What This Spec Proves

- A **measurement contract** now exists: canonical, schema-bound definitions
  of realized vs unrealized attribution, funding, fees, open/closed positions,
  and `N_closed`.
- Future dated attribution snapshots have a canonical field schema, query set,
  tolerance, and language to conform to.
- It does **not** itself prove the current numbers. The known facts as of the
  plan of record (realized gross PnL negative; gain concentrated in unrealized
  long exposure; `N_closed` small) become receipt-backed only when a dated
  snapshot conforming to this spec is later produced.

---

## What This Spec Does Not Prove

- **No edge.** `EDGE_UNPROVEN` stands.
- **No profitability.** Negative realized gross PnL is the current known
  state; nothing here changes or launders it.
- **No statistical significance.** `N_closed` is far below any plausible
  minimum track record length.
- **No shorting readiness.** Shorting remains an unpreregistered hypothesis.
- **No live readiness.** `BLOCK_LIVE_INTEGRATION` stands.
- **No full-ledger clean status upgrade.** Full-ledger
  `CAVEATED_ENGINE_SEMANTICS` stands; only the verifier can ever change it.
- **No strategy promotion.** No lane changes status because this spec exists.

---

## Non-Goals

- No code.
- No scripts (the read-only reporting script is a later, separate decision).
- No JSONL registry, and no trial registry (that belongs to the preregistered
  forward experiment plan, the third PR).
- No shorting docs yet (second PR).
- No preregistered forward experiment plan yet (third PR).
- No verifier changes.
- No DB reads with write access, ever, for any snapshot.
- No live integration.
- No leverage, and no leverage discussion beyond the Kelly zero-allocation
  bound already stated in the plan of record.

---

## Open Questions

None of these block this docs PR.

1. **Reporter shape:** should the future implementation be a standalone
   read-only script under `scripts/`, or a verifier-adjacent reporter that
   reuses `quantbot/sidecars/ledger_ro.py`'s snapshot-pinned connection and
   logical fingerprinting?
2. **Snapshot home:** should dated attribution snapshots live in
   `docs/status/` next to this spec (e.g.
   `realized_attribution_YYYY-MM-DD.md`), or under `docs/verdicts/` with the
   other dated status artifacts?
3. **Trial registry format:** should the future trial registry (third PR's
   concern) use append-only JSONL, and if so should snapshots reference
   registry entries?
4. **DB path handling:** for cross-lane snapshots, should prod/shadow DB paths
   be pinned in the snapshot header explicitly, resolved via
   `QNTY_PAPER_OUTPUT_DIR` per lane, or both (explicit path + resolution mode
   recorded, as this spec currently requires)?
5. **Prereg integration:** how should conforming snapshots be referenced by
   the preregistered forward experiment plan — as scheduled evaluation
   artifacts at preregistered checkpoints, or produced ad hoc and merely
   required to conform?

---

*This spec is docs-only. No writer ran, no database was opened, no
trader/decision/signal/verifier code was modified. `EDGE_UNPROVEN`,
`BLOCK_LIVE_INTEGRATION`, and full-ledger `CAVEATED_ENGINE_SEMANTICS` are
preserved.*
