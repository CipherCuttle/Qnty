# QNTY Funding Source Snapshot Recommit Plan

## Status Boundary

- `EDGE_UNPROVEN` remains.
- `BLOCK_LIVE_INTEGRATION` remains.
- Full-ledger `CAVEATED_ENGINE_SEMANTICS` remains.
- This is a plan only.
- This plan does not prove edge, profitability, statistical significance,
  shorting readiness, live readiness, or production deployment.
- This plan authorizes no DB mutation, writer run, trader run, live
  integration, deployment, backfill, official report overwrite, or snapshot
  recommit.

## Why This Plan Exists

- **PR #91** (`docs: record VM shadow verifier tmp run receipt`) resolved the
  path-availability artifact: the verifier now runs in-place against the true
  shadow DB path, `source_path_available = true`,
  `resolved_funding_source_dir = /srv/qnty/repo/data`, with no
  `source_path_unavailable` and no top-level `CORRUPT`.
- **PR #92** (`docs: diagnose funding source digest window mismatch`) diagnosed
  the *remaining* full-ledger and batch caveat (`refused_digest_mismatch`) as
  two independent provenance gaps rather than an accounting error:
  - `funding_source_file_digest_mismatch` — the committed snapshot's per-file
    and bundle digests are stale because the source CSVs were refreshed after
    the snapshot was committed (`CURRENT_SOURCE_FILES_CHANGED_AFTER_SNAPSHOT`
    plus `COMMITTED_SNAPSHOT_DIGEST_STALE`).
  - `funding_source_snapshot_window_mismatch` — the committed snapshot is
    batch-scoped and does not span the full-ledger funding window
    (`SNAPSHOT_WINDOW_DOES_NOT_COVER_LEDGER`).
- A fix must be **planned** before it is executed because a careless snapshot
  "recommit" could rewrite committed evidence, mutate the shadow (or prod) DB,
  or overwrite the official report without a clear provenance model — trading
  one silent-drift problem for a worse silent-rewrite problem. The safe path is
  to fix the provenance *model* first, prove it with tests and `/tmp` receipts,
  and only then consider any DB-touching operation under explicit approval.

## Current Facts

- PR #92 merge SHA: `0e6c96ae0d044c17348747dc8cdcf6918a8e7344`.
- Shadow DB path: `/srv/qnty/output/paper_pnl_null_shadow_v0/paper_ledger.db`.
- Official shadow report path:
  `/srv/qnty/output/paper_pnl_null_shadow_v0/paper_verify_report.json`.
- Data dir path: `/srv/qnty/repo/data`.
- Snapshot batch window (committed batch 17 `evaluation_window`):
  `2026-07-03T08:00:00Z -> 2026-07-05T16:00:00Z`.
- Full-ledger funding window (`funding` table
  `MIN(window_start)`/`MAX(window_end)`):
  `2026-06-25T08:00:00Z -> 2026-07-05T16:00:00Z`.
- Digest mismatch labels from PR #92:
  `CURRENT_SOURCE_FILES_CHANGED_AFTER_SNAPSHOT` (primary),
  `COMMITTED_SNAPSHOT_DIGEST_STALE` (corollary),
  reason codes `funding_source_file_digest_mismatch` (full-ledger and batch).
- Window mismatch labels from PR #92:
  full-ledger `SNAPSHOT_WINDOW_DOES_NOT_COVER_LEDGER` (primary),
  batch-scope `WINDOW_OK_BUT_VERIFIER_RULE_STRICT`,
  reason code `funding_source_snapshot_window_mismatch` (full-ledger only).
- Arithmetic / resum OK: `arithmetic_ok = true`, `arithmetic_status = OK`,
  resum `status = ok` (`funding_rows = 59`,
  `funding_amount_sum = 3.44000686`,
  `ledger_state_funding_cum = 3.4400068507041306`, `tolerance_abs = 1e-06`,
  resum `reason_codes = []`).
- Funding coverage complete: `funding_coverage_decision = complete`,
  `funding_source_coverage_verdict = CLEAN_NET_OF_CARRY`,
  snapshot `coverage_decision = complete`, payload `reason_codes = []`.
- Official report promotion is **blocked** (`OFFICIAL_REPORT_PROMOTION_BLOCKED`):
  the `/tmp` verifier output must not be promoted while the caveat stands.

## Problem A — Digest Drift

- The committed funding-source snapshot was **internally consistent** when
  written: recomputing the bundle over the snapshot's stored `source_files`
  reproduces the stored `source_bundle_sha256`
  (`1c5b433eb3adc345…`). This is not a canonicalization defect.
- The current VM source CSVs changed **after** the snapshot was committed: all
  five funding CSVs (`BNBUSDT`, `BTCUSDT`, `ETHUSDT`, `SOLUSDT`, `XRPUSDT`)
  carry mtimes of `2026-07-07 00:06–00:07 UTC`, roughly 19.5 hours after the
  committed snapshot / shadow DB (`2026-07-06T04:33:09Z`), and every current
  per-file `sha256` differs from the committed stored digest.
- **Why the verifier refuses.** The verifier recomputes the expected digest
  from the *current* source files on disk and compares against the committed
  snapshot's stored `full_file_sha256` values
  (`clean_mode_decision_from_snapshot_v1` in
  `quantbot/paper/funding_source_snapshot.py`, and the DB-linked classifier in
  `quantbot/paper/sqlite_verify.py`). Because the live files drifted, the
  recomputed digest no longer matches the committed digest, so clean-carry is
  refused with `funding_source_file_digest_mismatch`.
- **Why this is a provenance issue, not an arithmetic issue.** PR #91 already
  established `arithmetic_ok = true`, resum `status = ok`, and
  `funding_coverage_decision = complete`. Nothing about the ledger accounting is
  wrong; the committed *evidence* simply went stale because a data-refresh cron
  rewrote the source CSVs after the snapshot was captured. The committed
  snapshot is the source of truth; the live files drifted away from it.

## Problem B — Window Semantics

- The committed snapshot's `evaluation_window` is **batch-17-scoped**
  (`2026-07-03T08:00:00Z -> 2026-07-05T16:00:00Z`), matching
  `snapshot_metadata.batch_start_watermark` / `batch_end_watermark`
  (`prior_watermark_bar_ts` -> `new_watermark_bar_ts`).
- The full-ledger expected window is the entire `funding`-table span
  (`2026-06-25T08:00:00Z -> 2026-07-05T16:00:00Z`).
- **Batch window was OK but full-ledger window was not.** The batch object's
  `evaluation_window` equals the snapshot window exactly, so the batch gate
  raises no window mismatch (its caveat is digest-only). The full-ledger gate,
  however, compares `evaluation_window` against the full funding span by strict
  **equality** (`clean_mode_decision_from_snapshot_v1`,
  `if payload.get("evaluation_window") != expected_window:`). The **end**
  aligns (`2026-07-05T16:00:00Z`), so the snapshot is not stale relative to the
  latest bar; the **start** differs (`2026-07-03T08:00:00Z` vs
  `2026-06-25T08:00:00Z`), so a batch-scoped snapshot can never satisfy the
  full-span equality.
- **Why a simple batch recommit will not clear full-ledger clean-carry.** Even
  a fresh, digest-valid batch-17 snapshot would still carry a batch-scoped
  `evaluation_window`. It would clear the *batch* caveat but leave the
  full-ledger `funding_source_snapshot_window_mismatch` intact, because the
  full-ledger gate structurally expects a snapshot covering the whole funding
  span. The window problem is a semantics/model decision, not a freshness
  problem.

## Candidate Resolution Strategies

### Strategy 1 — Content-Addressed Source Bundle

Store/copy the exact source-CSV bytes (or a normalized source payload) into an
immutable, content-addressed evidence bundle referenced by the snapshot, and
have the verifier validate against the *bundled* bytes rather than the mutable
live CSVs under `/srv/qnty/repo/data`.

- **Pros:** Makes committed evidence immune to post-commit data refreshes — the
  digest can never go stale because the bytes the digest describes are frozen
  alongside the snapshot. Directly addresses Problem A's root cause (source
  files drifting after commit). Content-addressing makes the bundle
  self-verifying and de-duplicable across batches.
- **Cons:** Increases on-disk evidence size (copies of CSV bytes). Requires a
  writer/verifier contract change (where the "source of truth" bytes live) —
  therefore must be specced and tested before implementation. Does **not** by
  itself resolve Problem B (window scope).

### Strategy 2 — Full-Ledger Snapshot

Build a funding-source snapshot whose `evaluation_window` spans the whole
`funding` table (`2026-06-25T08:00:00Z -> 2026-07-05T16:00:00Z`) so the
full-ledger equality gate can be satisfied.

- **Pros:** Directly clears the full-ledger `funding_source_snapshot_window_mismatch`
  under the existing strict-equality rule, with no verifier code change. Matches
  the full-ledger verifier's current expectation exactly.
- **Cons:** Introduces a second snapshot *scope* (full-ledger vs batch) that
  must be built, referenced, and kept fresh; raises the question of when a
  full-ledger snapshot is (re)built and how it stays digest-valid as new batches
  land. Combined with Problem A, a full-ledger snapshot is only useful if its
  source bytes are also frozen (needs Strategy 1) so it does not immediately go
  stale on the next data refresh.

### Strategy 3 — Batch Snapshot Aggregation

Keep batch-scoped snapshots for batch verifier mode, and allow full-ledger
clean-carry only if **all** batch-scoped snapshots covering the full funding
span are present, digest-valid, contiguous (no gaps/overlaps in their
`evaluation_window`s), and internally consistent — i.e., the full-ledger verdict
is composed from a contiguous chain of batch snapshots.

- **Pros:** Reuses the batch snapshots the writer already emits; no separate
  full-ledger snapshot to maintain. Naturally extends as new batches land.
  Preserves batch-scoped semantics as the primitive.
- **Cons:** Requires new verifier semantics (aggregation + contiguity checks)
  and is the most complex to specify and test correctly (gap/overlap/ordering
  edge cases). Must be specced and tested before any operational change. Still
  needs Strategy 1 to keep each batch snapshot's source bytes frozen.

### Strategy 4 — Verifier Semantics Tests First

Before any operational (writer/snapshot/DB) change, add tests/specs that pin the
current and intended semantics:

- stale file digests after a source refresh produce
  `funding_source_file_digest_mismatch` (Problem A, current behavior);
- a batch-scoped snapshot is valid for batch clean-carry but **not** full-ledger
  (Problem B, current behavior — strict-equality window gate);
- a full-ledger-scoped snapshot clears the full-ledger window gate (Strategy 2
  target);
- a contiguous set of batch snapshots *could* clear full-ledger if aggregation
  is chosen (Strategy 3 target, if pursued);
- official report promotion remains blocked while any caveat stands.

- **Pros:** Locks down behavior before changing it, so any later
  writer/verifier change is a deliberate, reviewed semantics change rather than
  an accidental one. Zero DB/VM risk (pure test/spec work). Turns the "which
  strategy" decision into an executable specification.
- **Cons:** Does not itself clear any caveat; it is a prerequisite, not a fix.
  Depends on existing test architecture supporting these cases (see
  `tests/test_paper_sqlite_verify_batch_scoped_clean_carry.py`,
  `tests/test_paper_sqlite_verifier_db_linked_snapshot_selector.py`,
  `tests/test_funding_source_snapshot_schema.py`).

### Strategy 5 — Keep Full-Ledger Caveated

Accept a permanent full-ledger `CAVEATED_ENGINE_SEMANTICS` and treat only the
latest batch-scoped clean-carry as the evidence-quality signal.

- **Pros:** Zero implementation risk; no writer/verifier/DB change. Honest about
  the current provenance model. Batch-scoped clean-carry (once digest-fresh)
  still provides a bounded, verifiable signal.
- **Cons:** Never clears the full-ledger caveat, so full-ledger `CLEAN_NET_OF_CARRY`
  is unreachable by construction. Weakest evidence outcome; likely unacceptable
  as a permanent posture but acceptable as an *interim* posture while Strategies
  1–4 are sequenced.

## Recommended Path

Conservative sequence — provenance model first, tests second, `/tmp` receipts
third, DB-touching operations only under explicit later approval:

1. **`VERIFIER_DIGEST_WINDOW_SEMANTICS_TESTS`**
   - Add tests/specs only (Strategy 4). Pin current digest-drift and
     batch-vs-full-ledger window behavior, and encode the intended target
     behavior for whichever window strategy is chosen (2 or 3).
   - No VM access, no DB mutation, no writer run.
2. **`FUNDING_SOURCE_SNAPSHOT_REBUILD_TMP_RECEIPT`**
   - Rebuild candidate full-ledger and/or batch snapshots to `/tmp` only.
     Compare rebuilt digests/windows against the committed snapshot and against
     the current source files. Confirm the content-addressed bundle approach
     (Strategy 1) reproduces deterministically.
   - No DB writes; no official report overwrite; `/tmp` output stays `/tmp`.
3. **`FUNDING_SOURCE_SNAPSHOT_RECOMMIT_DRY_RUN`**
   - Only if tests (step 1) and the `/tmp` receipt (step 2) are good: plan and
     execute a dry-run commit path against a **copied** DB (never the live
     shadow/prod DB), capturing before/after DB hashes.
4. **`FUNDING_SOURCE_SNAPSHOT_RECOMMIT_REAL_DB`**
   - Only after explicit approval and only with DB hash before/after, a DB
     backup, and a defined rollback. This is the sole step that may touch a real
     DB, and it is gated behind all prior steps.
5. Official report promotion remains **blocked** until a fresh verifier run
   returns clean/correct digest and window fields and is separately reviewed.
   `/tmp` verifier output is never promoted to the official report by this
   sequence.

The window-strategy decision (Strategy 2 full-ledger snapshot vs Strategy 3
batch aggregation) should be **made in step 1 as an executable spec**, combined
with Strategy 1 (content-addressed bundle) to fix Problem A regardless of which
window strategy wins. Strategy 5 (keep caveated) is the acceptable interim
posture until step 4 completes.

## Non-Negotiable Safety Gates

- No production/shadow DB mutation without an explicit, separate later task.
- No writer run against a real DB until a dry-run against a **copied** DB proves
  the behavior.
- No official report overwrite; `OFFICIAL_REPORT_PROMOTION_BLOCKED` stays in
  force until a fresh clean verifier run is separately reviewed.
- No live/trader/decision/signal/strategy changes.
- DB hash before/after is mandatory for any future real DB operation.
- Report hash before/after is mandatory for any operation near the official
  report.
- The source-bundle digest must be deterministic (reproduced identically from
  the same bytes, using the existing `canonical_json` / `build_source_file_digest`
  canonicalization).
- Window semantics must be tested before being changed (batch-scoped vs
  full-ledger equality vs aggregation).
- Full-ledger vs batch semantics must be made explicit in code/spec, not left
  implicit.
- All receipts must preserve `EDGE_UNPROVEN`, `BLOCK_LIVE_INTEGRATION`, and
  full-ledger `CAVEATED_ENGINE_SEMANTICS` caveats.

## Proposed Next Task

Exactly one next task:

**`VERIFIER_DIGEST_WINDOW_SEMANTICS_TESTS_GIT_OWNED`**

Purpose: add tests/specs for the digest-drift and batch-vs-full-ledger window
semantics **before** any operational snapshot rebuild or recommit.

Constraints for that task: code/test-only if the existing test architecture
supports the required cases (build on
`tests/test_paper_sqlite_verify_batch_scoped_clean_carry.py`,
`tests/test_paper_sqlite_verifier_db_linked_snapshot_selector.py`,
`tests/test_funding_source_snapshot_schema.py`), or docs+tests if additional
spec scaffolding is needed. It must not touch DBs, must not run the
writer/trader, and must not access or modify the VM, `/srv/qnty/repo`, or
`/srv/qnty/output`.

## What This Plan Proves

- It defines a safe, staged sequence for resolving funding-source provenance
  issues (tests → `/tmp` receipt → copied-DB dry run → real-DB recommit under
  approval).
- It separates digest drift (Problem A) from window semantics (Problem B) and
  ties each to a concrete strategy.
- It prevents premature report promotion or DB mutation by gating every
  DB-touching step behind tests and `/tmp` evidence.

## What This Plan Does Not Prove

- no edge
- no profitability
- no clean full-ledger guarantee
- no DB repair
- no official report promotion
- no deployment
- no live readiness

## Non-Goals

- no code change
- no test change
- no schema change
- no verifier code change
- no reporter change
- no writer change
- no trader change
- no strategy change
- no DB writes
- no prod/shadow writer run
- no deployment
- no backfill
- no official report overwrite
- no live integration
- no shorting
- no trial registry
- no null/benchmark lane changes

## Verdict

`FUNDING_SOURCE_SNAPSHOT_RECOMMIT_PLAN_RECORDED`

This plan records a conservative, docs-only sequence for resolving the
funding-source snapshot digest/window provenance issue diagnosed in PR #92. It
separates digest drift (`CURRENT_SOURCE_FILES_CHANGED_AFTER_SNAPSHOT`) from
full-ledger window semantics (`SNAPSHOT_WINDOW_DOES_NOT_COVER_LEDGER`), compares
five candidate strategies, and recommends verifier digest/window semantics tests
first, then a `/tmp` rebuild receipt, then a copied-DB dry run, then a real-DB
recommit only under explicit later approval. No DB mutation, writer run, official
report promotion, or backfill is authorized. `EDGE_UNPROVEN`,
`BLOCK_LIVE_INTEGRATION`, and full-ledger `CAVEATED_ENGINE_SEMANTICS` remain.
