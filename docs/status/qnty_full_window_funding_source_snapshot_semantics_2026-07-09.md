# QNTY — Full-window funding-source snapshot semantics (code PR)

Date: 2026-07-09
Branch: `feature/full-window-funding-source-snapshot-semantics`
Task: `QNTY_FULL_WINDOW_FUNDING_SOURCE_SNAPSHOT_SEMANTICS_CODE_PR`
Predecessor: PR #119 (`dd6a8da`) —
`QNTY_PROD_FULL_WINDOW_IMMUTABLE_BUNDLE_BUILD_AND_READONLY_EVAL_BLOCKED`

Scope: **code + tests + this receipt only.** No prod/shadow DB mutation, no
report promotion, no bundle/snapshot built on the VM, no writer/timer/service
run, no deploy, no live integration. `EDGE_UNPROVEN` and
`BLOCK_LIVE_INTEGRATION` remain. This PR does not recommend or enable real
leverage or shorting.

---

## PLAN

PR #119 established the structural blocker: prod `paper_pnl_v1` cannot reach
full-ledger `CLEAN_NET_OF_CARRY`, because

- the full-ledger evaluation window spans every committed batch
  (`2026-06-21 → 2026-07-09` in prod), while
- every committed snapshot is **batch-scoped** (one 8h window), and
- `build_funding_source_bundle_v1` freezes a single snapshot, and
- the full-ledger gate compares the selected snapshot's `evaluation_window`
  against the full funding span, so a batch snapshot yields
  `funding_source_snapshot_window_mismatch` by construction. Bundle mode only
  swaps source-digest expectations; it cannot cure the window mismatch.

Root cause (confirmed by prior root-cause audit and recommit plan):
`ROOT_CAUSE_BATCH_VS_LEDGER_WINDOW_SEMANTICS`. The cure is an **explicit
full-window snapshot artifact** that covers the whole full-ledger span, not a
docs-built bundle over an 8h snapshot.

Design chosen: **explicit `snapshot_scope` discriminator + a full-window
snapshot builder + absolute `resolved_funding_source_dir`, carried through the
existing immutable bundle, and consumed by the full-ledger clean-carry gate via
a backward-compatible scope requirement.** No ambiguous multi-snapshot
discovery: a single full-window snapshot carries the full-ledger window and the
union of all required funding windows.

Key backward-compat decision: the full-ledger gate demands `full_window` scope
**only when the ledger spans more than one committed batch**
(`_full_ledger_requires_full_window_scope`). Single-batch ledgers (all existing
synthetic/test DBs, and any one-batch lane) are unchanged — a covering batch
snapshot may still be CLEAN exactly as before. This is what preserves the
existing full-ledger CLEAN and read-only CLI contract tests verbatim.

---

## CHANGESET

Files changed (vs `origin/main`):

- `quantbot/paper/funding_source_snapshot.py`
  - Added scope discriminator: `SNAPSHOT_SCOPE_BATCH` (default),
    `SNAPSHOT_SCOPE_FULL_WINDOW`, `SNAPSHOT_SCOPES_V1`.
  - Added reason codes `funding_source_full_window_snapshot_missing`,
    `funding_source_snapshot_scope_mismatch` to `REASON_CODES_V1`.
  - `build_funding_source_snapshot_payload_v1`: new `snapshot_scope` (default
    `batch`) and absolute-only `resolved_funding_source_dir` params. Writes
    `snapshot_scope` at payload top-level and in `snapshot_metadata`, and
    `provenance.source_path_resolution.resolved_funding_source_dir`.
  - New `build_full_window_funding_source_snapshot_payload_v1(...)`: thin,
    explicit wrapper that pins `full_window` scope, pins the caller-computed
    full-ledger `evaluation_window`, and requires an absolute source dir.
  - `clean_mode_decision_from_snapshot_v1`: new `expected_snapshot_scope` arg.
    When `full_window` is required: a missing snapshot → the explicit
    `funding_source_full_window_snapshot_missing`; a wrong-scope snapshot →
    `funding_source_snapshot_scope_mismatch`. Unset requirement preserves the
    historical batch behavior byte-for-byte.
- `quantbot/paper/funding_source_bundle.py`
  - Carries `snapshot_scope` (default `batch`) and absolute
    `resolved_funding_source_dir` into `bundle_payload`. These fields do **not**
    participate in `source_bundle_sha256` (which content-addresses only
    `canonical_rows`), so existing bundle identity/filename are unchanged.
- `quantbot/paper/sqlite_verify.py`
  - `_committed_batch_count` + `_full_ledger_requires_full_window_scope`.
  - Full-ledger clean-carry gate passes `expected_snapshot_scope=full_window`
    only for multi-batch ledgers.
  - Status mapping: `funding_source_full_window_snapshot_missing` →
    `refused_missing_snapshot`; `funding_source_snapshot_scope_mismatch` →
    `refused_db_or_lane_mismatch` (same family as window mismatch).
  - Batch-scoped stamp is untouched (keeps batch-scope semantics).
- `tests/test_full_window_funding_source_snapshot_semantics.py` — new, 18 tests.
- `tests/test_funding_source_snapshot_schema.py` — extended the pinned
  `REASON_CODES_V1` golden set with the two new codes.

---

## VERIFY

Verification ladder run:

1. Import check — `IMPORT_OK`.
2. Targeted tests (all pass):
   - `tests/test_full_window_funding_source_snapshot_semantics.py` — 18 passed.
   - Sweep of funding snapshot schema, immutable bundle semantics, digest/window
     semantics, clean-net-of-carry gate, batch-scoped clean-carry, read-only CLI
     contract, source-snapshot read, db-linked selector, source-path resolution,
     writer snapshot emission + reference transaction — **154 passed**.
3. Smoke — `./scripts/release_smoke.sh` — 6 passed, `IMPORT_OK`.
4. Full suite — `1437 passed, 32 failed`. The 32 failures are **pre-existing
   and unrelated**: an identical `32 failed, 97 passed` set appears on clean
   `origin/main` for `test_paper_sqlite_verify.py`,
   `test_paper_sqlite_verify_report.py`, `test_paper_sqlite_writer.py` with my
   changes stashed. My change adds **zero** new failures.
5. `git diff --check` — clean. `git diff --stat origin/main` —
   5 files, +585/−3.

New-test coverage maps to the required matrix:

1. Existing batch snapshot fixture still validates + defaults to `batch` scope.
2. Full-window snapshot fixture validates.
3. Full-window snapshot with absolute `resolved_funding_source_dir` validates.
4. Full-window snapshot covers the full-ledger window and passes the gate.
5. 8h batch snapshot refuses the full-ledger window with
   `funding_source_snapshot_window_mismatch` (and explicit scope mismatch).
6. Missing full-window snapshot → `funding_source_full_window_snapshot_missing`.
7. Wrong lane / wrong DB identity refuses (`..._db_mismatch`).
8. Row-subset digest mismatch refuses.
9. Source-file digest mismatch refuses.
10/11. Full-window snapshot → full-window bundle; batch bundle stays `batch`;
    bundle identity hash ignores the new fields.
12. Live-current/default behavior intact (batch stamp untouched; targeted
    batch-scoped + CLI contract suites pass).
13. No copied-DB false positive introduced (source-path resolution suite passes;
    no reason-code string filtering, no binding weakening).
14. PR #119 regression: batch-only cannot full-ledger clean; adding a
    full-window snapshot makes full-ledger clean reachable.
    Plus verifier-trigger tests: single committed batch does **not** require
    full-window scope; multi-batch does.

---

## Compatibility statements

- **Existing shadow bundle-mode behavior unchanged.** Bundle identity is still
  content-addressed over `canonical_rows` only; the added `snapshot_scope` /
  `resolved_funding_source_dir` bundle fields do not change
  `source_bundle_sha256` or the bundle filename. `resolve_funding_source_bundle`
  hash/refusal semantics are untouched. Shadow remains the bundle-mode
  `CLEAN_NET_OF_CARRY` lane via the batch stamp.
- **Existing 8h batch snapshots unchanged.** The builder defaults to
  `snapshot_scope="batch"`; older/unscoped payloads are read as `batch` and are
  never silently reinterpreted as full-window. The batch-scoped clean-carry
  stamp still uses batch-scope semantics.
- **Refusal semantics preserved / strengthened, never weakened.** No reason-code
  string filtering. Row and source-file digest checks unchanged. DB/lane/batch
  binding checks unchanged. The scope discriminator is additive strictness: a
  batch snapshot with an artificially widened window is still refused for a
  full-window gate.
- **No copied-DB false positives.** No change to source-path resolution or
  snapshot-selection binding.

## What was NOT touched

- No writer code that emits snapshots was changed (no new artifact is emitted at
  runtime by this PR).
- No prod/shadow DB, no official report, no source CSV, no VM snapshot/bundle,
  no service/timer/cron/systemd, no `/srv/qnty/repo` main worktree.
- No live/writer/backfill/data-refresh run. No prod report promotion.
- No optional VM read-only sanity check was performed (not needed; PR #119
  already characterized real prod, and this is a pure code/test PR).

## Next recommended task

`QNTY_FULL_WINDOW_FUNDING_SOURCE_SNAPSHOT_WRITER_EMISSION` — teach the
snapshot-writer path to emit a `full_window`-scoped snapshot (and its bundle)
bound to a target lane/DB/latest committed batch over the computed full-ledger
window, plus a narrow verifier selection hook so the full-ledger gate consumes
the full-window snapshot sidecar when present. That is the change that would let
a real (still shadow-first) lane demonstrate full-ledger `CLEAN_NET_OF_CARRY`.
It remains gated by `EDGE_UNPROVEN` / `BLOCK_LIVE_INTEGRATION`.

---

## VERDICT

`QNTY_FULL_WINDOW_FUNDING_SOURCE_SNAPSHOT_SEMANTICS_RECORDED`

Test-backed code support for an explicit full-window funding-source snapshot now
exists: it can cover the full-ledger clean-carry window, is carried through the
immutable bundle without changing bundle identity, and is consumed by the
full-ledger gate for multi-batch ledgers — while every existing batch/shadow
behavior, binding, and digest check is preserved.
