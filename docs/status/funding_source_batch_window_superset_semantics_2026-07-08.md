# FUNDING_SOURCE_BATCH_WINDOW_SUPERSET_SEMANTICS_RECORDED

**Date:** 2026-07-08
**Branch:** `feature/funding-source-batch-window-superset-semantics`
**HEAD:** `1a7818b704d23701f9ee6c7b78d2d3369cf2d975`

## Context

PR #113 merged: batch stamp honors `source_mode="bundle"`. PR #114 blocked by `funding_source_batch_window_mismatch`: strict window equality between bundle evaluation window (`2026-06-25 → 2026-07-05`) and batch window (`2026-07-03 → 2026-07-05`) fails because they are not identical, even though the bundle window covers the batch window.

## PLAN

Replace strict window equality with covering-superset semantics:
- snapshot evaluation window start <= expected window start (covers from left)
- snapshot evaluation window end >= expected window end (covers from right)
- fail on missing/unparseable boundaries
- preserve full-ledger gate behavior (already uses full-ledger MIN/MAX window)
- preserve live-current/compatibility

## CHANGESET

### [`quantbot/paper/funding_source_snapshot.py`](quantbot/paper/funding_source_snapshot.py)

**`_window_covers()` helper** (lines 631-644):
A new function returning True when the outer (payload) window's start ≤ inner (expected) window's start and outer end ≥ inner end. Handles None/unparseable via try/except returning False.

**Comparison change** (line 693):
- Before: `if payload.get("evaluation_window") != expected_window:`
- After: `if not _window_covers(payload.get("evaluation_window", {}), expected_window):`

The reason code (`funding_source_snapshot_window_mismatch`) is preserved. The batch stamp in `sqlite_verify.py` still translates it to `funding_source_batch_window_mismatch` as before.

### [`tests/test_paper_sqlite_verify_batch_scoped_clean_carry.py`](tests/test_paper_sqlite_verify_batch_scoped_clean_carry.py)

**Fixed:** `test_batch_scope_refuses_window_mismatch` — changed snapshot window from covering superset (which now passes) to strict subset (starts after, ends before batch window).

**Added (7 new tests):**

| Test | Purpose |
|------|---------|
| `test_batch_scope_accepts_covering_superset_window` | PR #114 regression: bundle window `2026-06-25→2026-07-05` covers batch window `2026-07-03→2026-07-05` → clean |
| `test_batch_scope_accepts_exact_window` | Exact match still works (regression guard) |
| `test_batch_scope_refuses_window_start_after_batch_start` | Snapshot starts after batch start → refused |
| `test_batch_scope_refuses_window_end_before_batch_end` | Snapshot ends before batch end → refused |
| `test_batch_scope_refuses_missing_window_boundaries` | Snapshot has None start → refused |
| `test_full_ledger_clean_carry_unchanged` | Full-ledger gate behavior preserved |
| `test_batch_stamp_live_current_compatible` | Live-current mode remains compatible |

## VERIFY

### Test results

| Test suite | Result |
|-----------|--------|
| Batch-scoped clean-carry (batch tests file) | 24/24 passed |
| Bundle semantics (`test_funding_source_immutable_bundle_semantics.py`) | 11/11 passed |
| Clean-net-of-carry gate (`test_paper_sqlite_verifier_clean_net_of_carry_gate.py`) | 14/14 passed |
| Source snapshot schema (`test_funding_source_snapshot_schema.py`) | 18/18 passed |
| Source path resolution (`test_paper_sqlite_verify_source_path_resolution.py`) | 5/5 passed |
| Read-only CLI contract (`test_paper_sqlite_verify_read_only_cli_contract.py`) | 13/13 passed |
| Broader sweep (11 test files) | 47/48 passed (1 pre-existing unrelated failure) |

**Pre-existing failure:** `test_funding_bearing_db_is_ok` in `test_paper_sqlite_verify.py` — a writer CSV test infrastructure gap where `_run_writer` does not supply the funding source CSV. Unrelated to window semantics change.

### Git diff quality

```
git diff --check          → clean (no whitespace errors)
git diff --stat origin/main →
  quantbot/paper/funding_source_snapshot.py        |  17 +-
  tests/test_paper_sqlite_verify_batch_scoped_clean_carry.py | 232 +-
  docs/status/funding_source_bundle_mode_official_report_promotion_rerun_2026-07-08.md | +184
```

### VM read-only check

Skipped. Local tests (including the PR #114 regression test `test_batch_scope_accepts_covering_superset_window`) directly prove the semantic change resolves the blocker. The VM check would add marginal benefit at SSH/infrastructure risk.

## What was NOT touched

- `quantbot/paper/sqlite_verify.py` — no changes to batch window extraction, full-ledger gate, or reason code translation
- `quantbot/paper/ledger.py` — unchanged
- `quantbot/paper/funding_source_bundle.py` — unchanged
- No DB mutation, no official report write, no source CSV mutation, no deploy, no service mutation
- `EDGE_UNPROVEN` and `BLOCK_LIVE_INTEGRATION` remain in place
- No new bundle resolver or duplicate bundle handling

## Semantic rule

The correct covering-superset rule is:
- source_start <= batch_start AND source_end >= batch_end
- AND rows/digests/snapshot/bundle identity are valid
- AND batch arithmetic is computed/scoped to the batch window

Not "any overlap is fine." Not "use full-ledger funding totals as batch funding totals."

## Next actions

1. Open PR from `feature/funding-source-batch-window-superset-semantics`
2. Verify CI passes
3. If merged, rerun PR #114 promotion (bundle mode batch stamp should now be clean)
4. Update shadow report if/when promotion succeeds