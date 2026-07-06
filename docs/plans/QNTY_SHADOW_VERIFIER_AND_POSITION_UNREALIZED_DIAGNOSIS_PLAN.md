# QNTY Shadow Verifier And Position Unrealized Diagnosis Plan

**Plan version:** 1.0.0
**Date:** 2026-07-06
**Type:** diagnosis / remediation plan (docs-only; implements no code, no test,
no schema, no writer/verifier change, no DB mutation)
**Measurement contract:** `docs/status/realized_attribution_spec.md` (spec
version 1.0.0)
**Receipts diagnosed:**
`docs/status/realized_attribution_2026-07-06.md`,
`docs/status/realized_attribution_reporter_parity_2026-07-06.md`
**Governance:** `docs/research/preregistered_forward_experiment_plan.md`

---

## Status Boundary

- `EDGE_UNPROVEN` remains. Nothing here claims, implies, or is designed to
  manufacture an edge claim for any lane or variant.
- `BLOCK_LIVE_INTEGRATION` remains. No live exchange integration, no live
  capital, no live-readiness implication.
- Full-ledger `CAVEATED_ENGINE_SEMANTICS` remains for both lanes. Only an
  explicit verifier report can ever change that label; this document does not
  and cannot.
- **This document diagnoses evidence-quality gaps only.** It records read-only
  evidence, classifies two issues, and proposes a conservative future PR
  sequence. It is not a fix, not code, not a verifier/writer/schema change.
- This document **does not prove** edge, profitability, statistical
  significance, shorting readiness, or live readiness.
- This document **authorizes no** DB mutation, writer run, verifier semantics
  change, schema change, or trading-behavior change.

---

## Scope

- **Date:** 2026-07-06.
- **Issues investigated:**
  1. **Stale shadow verifier report** — the shadow lane's
     `paper_verify_report.json` predates both the current shadow ledger
     watermark and the PR #77 clean-carry verifier fields, so its clean-carry
     evidence is missing.
  2. **Per-symbol unrealized stored as `0.0`** —
     `position_snapshot_symbols.unrealized_gross` is `0.0` for every row on both
     lanes, so per-symbol unrealized attribution is substantively unavailable
     read-only, even though ledger-level `equity_snapshots.unrealized_pnl` is
     nonzero and identity-consistent.
- **Docs inspected:** `docs/status/realized_attribution_2026-07-06.md`,
  `docs/status/realized_attribution_reporter_parity_2026-07-06.md`,
  `docs/status/realized_attribution_spec.md`,
  `docs/research/preregistered_forward_experiment_plan.md`,
  `docs/paper_pnl_v1_schema.md`.
- **Code inspected read-only:** `quantbot/paper/realized_attribution.py`
  (reporter), `quantbot/paper/sqlite_writer.py` (writer),
  `quantbot/paper/db.py` (schema), `quantbot/paper/sqlite_verify.py` (verifier —
  not run).
- **DB paths inspected read-only:**
  - Prod: `/srv/qnty/output/paper_pnl_v1/paper_ledger.db`
  - Shadow: `/srv/qnty/output/paper_pnl_null_shadow_v0/paper_ledger.db`
- **Verifier report artifacts inspected read-only:**
  - Prod: `/srv/qnty/output/paper_pnl_v1/paper_verify_report.json`
  - Shadow: `/srv/qnty/output/paper_pnl_null_shadow_v0/paper_verify_report.json`
- **Local repo head:** `3fc6ef6` (`main` fast-forwarded to `origin/main` after
  PR #84 merged; this diagnosis branch cut from it).
- **VM repo head (`/srv/qnty/repo`):** `2bd88430fe6b2881aaa2b32947002217d3e02ba5`
  — inspected read-only, **not modified, not pulled, not updated**.
- **No writer ran. No verifier ran. No DB was mutated** (see Source Integrity /
  Mutation Proof).

---

## Method

- **Read-only repo inspection.** Reporter, writer, schema, and verifier modules
  were read locally at `main` head `3fc6ef6`. `unrealized_gross` assignments
  were traced through the writer with `grep`.
- **Read-only SQLite inspection.** Both live ledgers were opened on the VM as
  `file:<path>?mode=ro` with `PRAGMA query_only=ON`. Only `SELECT`/`COUNT`/
  `MIN`/`MAX`/`SUM` were issued. No `INSERT`/`UPDATE`/`DELETE`/`PRAGMA`-write.
- **Verifier report inspection.** The prod and shadow `paper_verify_report.json`
  artifacts were read as JSON on the VM (`json.load`, no write). The verifier
  itself was **not** executed; no report was regenerated in place or anywhere.
- **`/tmp` commands used:** none were required. All reads were direct read-only
  `SELECT`s and `json.load`s over SSH; no temporary copies or scripts were
  persisted to the repo or output tree.
- **Source integrity / mutation proof method:** `stat -c "%n size=%s mtime=%Y"`
  plus `sha256sum` on both DB files immediately before the first read and
  immediately after the last read, compared for byte identity (see below).

---

## Source Integrity / Mutation Proof

Captured on the VM immediately before the first read and immediately after the
last read.

**Prod — `/srv/qnty/output/paper_pnl_v1/paper_ledger.db`**

| | size (bytes) | mtime (epoch) | sha256 |
|---|---|---|---|
| before | 217088 | 1783354846 | `8d21c37406647e2252fd6c7079ac4b55dcfa300b6b94aded9561fc06cc4184d3` |
| after  | 217088 | 1783354846 | `8d21c37406647e2252fd6c7079ac4b55dcfa300b6b94aded9561fc06cc4184d3` |

**Shadow — `/srv/qnty/output/paper_pnl_null_shadow_v0/paper_ledger.db`**

| | size (bytes) | mtime (epoch) | sha256 |
|---|---|---|---|
| before | 172032 | 1783312420 | `3cbc6e9c63c74072aa019d6a53b1f5519f369f95cec1f9c21495e307c739a897` |
| after  | 172032 | 1783312420 | `3cbc6e9c63c74072aa019d6a53b1f5519f369f95cec1f9c21495e307c739a897` |

Both DB files are byte-identical before and after all reads (size, mtime, and
sha256 unchanged on both lanes). Both hashes also equal those recorded in
`docs/status/realized_attribution_2026-07-06.md` and the parity receipt — the
ledgers have not advanced since those receipts, so this diagnosis reads the same
bytes.

**Verdict: `READ_ONLY_CONFIRMED`.**

---

## Finding 1 — Shadow Verifier Report Staleness

**Report paths (VM):**

- Prod: `/srv/qnty/output/paper_pnl_v1/paper_verify_report.json`
- Shadow: `/srv/qnty/output/paper_pnl_null_shadow_v0/paper_verify_report.json`

**Freshness / watermark evidence:**

| | Prod report | Shadow report |
|---|---|---|
| File mtime (epoch) | 1783354846 (2026-07-06 16:20 UTC) | 1782929757 (2026-07-01 18:15 UTC) |
| File size (bytes) | 36859 | 3531 |
| `current_verdict` | `OK (simulation)` | `OK (simulation)` |
| Report `watermark_bar_ts` (verified-through) | matches prod DB | `2026-07-01T08:00:00` |
| Corresponding DB watermark (latest committed bar) | `2026-07-06T08:00:00` (batch 48) | `2026-07-05T16:00:00` (batch 17) |
| DB file mtime (epoch) | 1783354846 | 1783312420 (2026-07-05 04:33 UTC) |

- **Prod report is fresh.** Its file mtime equals the prod DB mtime
  (`1783354846`), it verifies through the current prod watermark, and it
  contains the full clean-carry field set.
- **Shadow report is stale.** It verifies only through `2026-07-01T08:00:00`
  while the shadow ledger has advanced to `2026-07-05T16:00:00` — a
  **~4 day 8 hour verified-through gap** — and its file mtime predates the
  shadow DB mtime by ~4.4 days. **The shadow DB watermark is newer than the
  shadow report watermark.**

**Clean-carry field presence:**

- **Prod report contains all eight clean-carry keys:** `funding_clean_carry`,
  `funding_clean_carry_decision` (`= CAVEATED_ENGINE_SEMANTICS`),
  `funding_clean_carry_status` (`refused_db_or_lane_mismatch`),
  `funding_clean_carry_reason_codes`, `funding_clean_carry_batch`,
  `funding_clean_carry_batch_decision` (`= CAVEATED_ENGINE_SEMANTICS`),
  `funding_clean_carry_batch_status` (`refused_source_coverage_issue`),
  `funding_clean_carry_batch_reason_codes`.
- **Shadow report contains none of them.** Its top-level keys carry no
  `clean_carry` field at all — it **predates the PR #77 clean-carry verifier
  fields**.

**Does the stale report explain `UNAVAILABLE_READ_ONLY`?** Yes. The reporter
reads clean-carry/verdict fields from the existing `paper_verify_report.json`
next to the DB only, never running the verifier
(`quantbot/paper/realized_attribution.py:327-357`, `_evidence_quality`). Because
the shadow report has no clean-carry keys, the reporter correctly emits
`UNAVAILABLE_READ_ONLY` for all seven `evidence_quality.funding_clean_carry_*`
fields on the shadow lane — exactly the "8 unavailable fields" recorded in the
parity receipt. This is faithful read-only behavior, not a reporter defect: the
report simply lacks the fields.

**Classification:** `REPORT_STALENESS_GAP` (primary), with
`EVIDENCE_PRESENTATION_GAP` as the downstream effect (the reporter cannot
present clean-carry evidence that the report never carried). **Not** a writer,
accounting, or reporter bug: the accounting identity holds and the reporter is
faithful.

**Risk:** Low-to-moderate evidence-quality risk. The shadow lane's clean-carry
status is simply *unknown from the artifact*, not wrong. No edge, accounting, or
live-status implication. The remedy is regenerating the shadow report from a
current verifier version — a read-only, no-DB-mutation operation whose output
should land in `/tmp` or a fresh artifact under review, not in place, per this
task's constraints.

**Recommended next PR:** PR A (freshness/field-presence test/spec), then PR B
(a read-only verifier report refresh path), below.

---

## Finding 2 — Per-Symbol Unrealized Values

**Table / schema facts:**

- `position_snapshot_symbols` is a child of `position_snapshots`, defined in
  `quantbot/paper/db.py:332-343` with column
  `unrealized_gross REAL NOT NULL DEFAULT 0.0`.
- The reporter reads latest-snapshot per-symbol unrealized from this table
  (`quantbot/paper/realized_attribution.py:283-295`) and attaches it to each
  open position as `unrealized_pnl`.

**Row counts and aggregates (read-only):**

| | Prod (`paper_pnl_v1`) | Shadow (`paper_pnl_null_shadow_v0`) |
|---|---|---|
| `position_snapshot_symbols` rows | 84 | 64 |
| rows with `unrealized_gross = 0.0` | 84 | 64 |
| rows with `unrealized_gross <> 0.0` | 0 | 0 |
| `MIN` / `MAX` / `SUM(unrealized_gross)` | 0.0 / 0.0 / 0.0 | 0.0 / 0.0 / 0.0 |
| latest snapshot per-symbol unrealized (5 open positions) | all `0.0` | all `0.0` |

The latest snapshot rows carry **real** `qty` and `entry_price` per symbol
(BNBUSDT, BTCUSDT, ETHUSDT, SOLUSDT, XRPUSDT on both lanes, matching
`open_positions`), but `unrealized_gross = 0.0` for every one.

**Comparison to ledger-level unrealized:**

- Latest `equity_snapshots.unrealized_pnl`: **prod `+362.93382432`** (at
  `2026-07-06T08:00:00`), **shadow `+385.13824051`** (at `2026-07-05T16:00:00`)
  — both nonzero.
- These aggregates are identity-consistent (accounting identity residual
  `0.0` prod, `1.82e-12` shadow, both `<= 1e-6`; per the parity receipt).
- So the ledger-level unrealized figure is real and correct; only the
  **per-symbol breakdown** is absent (a column of zeros).

**Writer / reporter / schema code facts:**

- The writer initializes every open position with `"unrealized_gross": 0.0`
  (`quantbot/paper/sqlite_writer.py:695` at entry; `:1869` at restart seeding)
  and **never updates it thereafter**. The snapshot writer persists
  `pos.get("unrealized_gross", 0.0)`
  (`quantbot/paper/sqlite_writer.py:508`), which is therefore always `0.0`.
- **`unrealized_gross` is never assigned a nonzero value anywhere in the
  repository** (verified by grep across `quantbot/`). The per-bar mark that
  feeds `equity_snapshots.unrealized_pnl` is computed and stored at the ledger
  level, but is **not** decomposed back onto the per-symbol child rows.
- The reporter faithfully reads the stored value: when a snapshot exists it
  reports the per-symbol `unrealized_pnl` as the stored `0.0`; it emits
  `UNAVAILABLE_READ_ONLY` only when no snapshot table/row exists
  (`quantbot/paper/realized_attribution.py:320`). Either way, per-symbol
  unrealized attribution is **substantively unavailable**: a hard `0.0` is not a
  mark.

**Likely cause candidates:**

1. **Schema placeholder never populated (most likely).** The column exists with
   `DEFAULT 0.0` and the writer never computes a per-symbol mark to fill it. The
   ledger-level unrealized is computed independently, so the identity still
   holds.
2. **Writer omission** — the per-symbol mark-to-market that would populate
   `unrealized_gross` was never wired into the writer path.
3. **Reporter limitation** — ruled out: the reporter reads the column
   faithfully; the zeros are in the source table, not introduced by the
   reporter.
4. **Stale/unused table** — partially: the table *is* written (real qty /
   entry_price), only the `unrealized_gross` column is a constant `0.0`.
5. **Expected semantics with a different source table** — possible: per-symbol
   unrealized may be intended to be derived on read from `open_positions`
   (qty, entry_price) against a current mark, rather than stored. This is an
   open question, not a settled fact.

**Classification:** `SCHEMA_CONTRACT_GAP` (primary — a column exists in the
contract but is never meaningfully populated), with `WRITER_BUG_SUSPECTED`
secondary (the writer never computes/persists the per-symbol mark) and
`UNKNOWN_NEEDS_TEST` on the intended semantics (stored vs derived-on-read).
Explicitly **not** an `ACCOUNTING_SEMANTICS_GAP`: the ledger-level unrealized
aggregate is nonzero and identity-consistent, so no accounting figure is wrong —
only the per-symbol decomposition is missing.

**Risk:** Low accounting risk (identity holds; headline realized/unrealized
figures are unaffected), moderate evidence-completeness risk (per-symbol
unrealized attribution is unavailable for any future per-symbol analysis).

**Recommended next PR:** PR C (a test/spec pinning the *intended* semantics of
`unrealized_gross`), and only then PR D (a writer or reporter change) **iff** the
test proves the expected semantics. No fix is authorized here.

---

## Impact On Existing Receipts

- **`docs/status/realized_attribution_2026-07-06.md`** — remains valid. It
  already recorded the shadow clean-carry fields as `UNAVAILABLE_READ_ONLY` and
  the per-symbol unrealized as `0.0`; this diagnosis confirms *why* (stale
  report; unpopulated column), and confirms the ledgers are byte-identical to
  that snapshot.
- **`docs/status/realized_attribution_reporter_parity_2026-07-06.md`** — remains
  valid. Its field-for-field prod/shadow parity, its `READ_ONLY_CONFIRMED`
  integrity, and its Open Questions (which already flagged both issues) are all
  corroborated. No parity result changes.
- **What remains unavailable:** (a) the shadow lane's clean-carry status, until
  its verifier report is refreshed; (b) any per-symbol unrealized breakdown, on
  both lanes, until the `unrealized_gross` semantics are resolved.
- **Why this does not change edge status:** both gaps are evidence-presentation
  / evidence-freshness gaps. The primary evidence — closed-trade realized net
  PnL (`SUM(trades.net_pnl)`, negative on both lanes) and `N_closed` (7 prod,
  3 shadow) — is unchanged, as is the ledger-level unrealized aggregate and the
  accounting identity. `EDGE_UNPROVEN`, `BLOCK_LIVE_INTEGRATION`, and
  full-ledger `CAVEATED_ENGINE_SEMANTICS` are untouched.

---

## Proposed Future PR Sequence

Conservative and ordered: tests/specs precede any implementation, and no
implementation is authorized by this document. Each PR is a separate future
proposal under separate review.

### PR A — Shadow verifier freshness / clean-carry field-presence test

- **Scope:** a test (or status-doc spec) asserting that a lane's
  `paper_verify_report.json`, when present, is fresh relative to the lane
  watermark and carries the clean-carry field set; flags a stale/legacy report
  rather than silently degrading.
- **Allowed files:** `tests/**` (new test), optionally a `docs/status/**` spec
  note. Read-only fixtures only.
- **Forbidden:** any writer/verifier/schema change; any DB mutation; running the
  verifier against a prod/shadow DB; regenerating any report in place.
- **Acceptance tests:** a stale/legacy report (no clean-carry keys, or watermark
  behind the DB) is detected as stale; a fresh, complete report passes.
- **Stop conditions:** if implementing the check requires running the verifier
  or touching a live DB, stop and re-scope.

### PR B — Read-only shadow verifier report refresh (only if PR A justifies it)

- **Scope:** a **no-write, read-only** path to regenerate a shadow verifier
  report to `/tmp` or a fresh reviewed artifact — never in place over
  `/srv/qnty/output`.
- **Allowed files:** verifier invocation glue and docs only; output to `/tmp` or
  a new artifact under review.
- **Forbidden:** in-place overwrite of any official report; any DB mutation; any
  verifier *semantics* change; writer changes.
- **Acceptance tests:** report generated read-only; source DB byte-identical
  before/after (`READ_ONLY_CONFIRMED`); clean-carry fields present in the fresh
  report.
- **Stop conditions:** if the verifier cannot run without mutating the DB or
  writing in place, stop and re-scope as a verifier design question.

### PR C — Per-symbol `unrealized_gross` semantics test/spec

- **Scope:** a test/spec pinning the *intended* meaning of
  `position_snapshot_symbols.unrealized_gross` (stored per-symbol mark vs
  derived-on-read from `open_positions`), and asserting the ledger-level
  identity is preserved either way.
- **Allowed files:** `tests/**`, `docs/**` (spec).
- **Forbidden:** writer/reporter/schema change; DB mutation.
- **Acceptance tests:** the intended semantics are encoded as an executable
  expectation the current state either meets or is documented as violating.
- **Stop conditions:** if the intended semantics cannot be determined from spec
  + code, stop at `UNKNOWN_NEEDS_TEST` and record the ambiguity, do not guess.

### PR D — Writer or reporter fix (only if PR C proves expected semantics)

- **Scope:** the minimal change that makes per-symbol unrealized available —
  either the writer computes/persists the per-symbol mark, or the reporter
  derives it read-only from `open_positions` + current mark.
- **Allowed files:** exactly one of `quantbot/paper/sqlite_writer.py` **or**
  `quantbot/paper/realized_attribution.py`, plus its tests.
- **Forbidden:** schema-breaking change; trader/decision/signal/strategy change;
  DB backfill/mutation of historical rows; live integration.
- **Acceptance tests:** PR C's semantics test passes; the accounting identity
  (`<= 1e-6`) is preserved; per-symbol unrealized sums are consistent with
  `equity_snapshots.unrealized_pnl`.
- **Stop conditions:** if the fix requires mutating historical ledger rows or a
  schema migration, stop and re-scope.

### PR E — New dated snapshot after fixes (only if C/D land)

- **Scope:** a fresh dated realized-attribution snapshot reflecting refreshed
  shadow clean-carry evidence and available per-symbol unrealized.
- **Allowed files:** `docs/status/**` (a new dated snapshot; existing dated
  snapshots are superseded, never edited in place).
- **Forbidden:** editing prior dated snapshots; any DB mutation.
- **Acceptance tests:** snapshot is read-only, `READ_ONLY_CONFIRMED`, and
  internally consistent under the spec.
- **Stop conditions:** none beyond the standard read-only constraints.

---

## Non-Goals

- No code changes.
- No tests in this PR.
- No schema change.
- No verifier change (the verifier was not run).
- No writer change (no writer ran).
- No DB writes.
- No report regeneration in place (or anywhere).
- No null model.
- No benchmark lane.
- No trial registry.
- No shorting.
- No live integration.
- No leverage.

---

## Open Questions

None of these block this docs PR.

1. **Exact intended semantics of
   `position_snapshot_symbols.unrealized_gross`** — is it meant to store a
   per-symbol mark-to-market (writer must populate it) or to be derived on read
   from `open_positions` (column may be vestigial)?
2. **Whether the verifier should have a no-write JSON-to-stdout mode** — so a
   fresh shadow report can be produced read-only without overwriting the
   in-place artifact.
3. **Where fresh verifier reports should live** — regenerated next to the DB
   (in place, currently forbidden here), in `/tmp`, or as a new reviewed
   artifact under `docs/`.
4. **Whether shadow verifier freshness should be checked by CI / status docs** —
   a standing check that flags a report whose watermark lags its lane's DB or
   whose clean-carry fields are absent.
5. **Whether the reporter should consume the verifier directly or only existing
   reports** — the reporter currently reads existing reports only; a
   direct-consume mode would need read-only guarantees.

---

## Verdict

`SHADOW_VERIFIER_UNREALIZED_DIAGNOSIS_RECORDED`

---

*This plan is docs-only. No writer ran, no verifier ran, no database was mutated
(both DBs byte-identical before and after all reads: `READ_ONLY_CONFIRMED`), no
trader/decision/signal/verifier/schema/writer/reporter code was modified, no
test changed, no report was regenerated in place. Prod and shadow ledgers and
their verifier reports were accessed read-only. The VM repo was inspected
read-only and not updated. Existing realized-attribution receipts remain valid.
`EDGE_UNPROVEN`, `BLOCK_LIVE_INTEGRATION`, and full-ledger
`CAVEATED_ENGINE_SEMANTICS` are preserved. This document authorizes no code, no
lane, no registry, no report regeneration, and no live integration.*
