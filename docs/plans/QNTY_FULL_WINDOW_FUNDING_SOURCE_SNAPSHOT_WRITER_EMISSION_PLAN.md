# QNTY Full-Window Funding Source Snapshot Writer Emission Plan

## 1. Purpose

Task: `QNTY_FULL_WINDOW_FUNDING_SOURCE_SNAPSHOT_WRITER_EMISSION`

Define and verify the writer-side emission path for explicit `full_window`-scoped
funding-source snapshots and their immutable bundles. This is the runtime side of
PR #120 (which added semantics but emitted no artifacts): a multi-batch ledger
currently cannot reach `CLEAN_NET_OF_CARRY` because there is no full-window
sidecar for the verifier to consume.

This plan documents what has been implemented, what remains to be tested, and the
precise verification contract between the writer emission path and the verifier.

## 2. Context

### PR #120 (merged, `feature/full-window-funding-source-snapshot-semantics`)

PR #120 added code support for:

| Component | File | What changed |
|-----------|------|-------------|
| Snapshot scope discriminator | [`funding_source_snapshot.py:35-36`](../../quantbot/paper/funding_source_snapshot.py) | `SNAPSHOT_SCOPE_BATCH`, `SNAPSHOT_SCOPE_FULL_WINDOW` constants |
| Full-window builder | [`funding_source_snapshot.py:646-696`](../../quantbot/paper/funding_source_snapshot.py) | `build_full_window_funding_source_snapshot_payload_v1()` wrapper |
| Absolute `resolved_funding_source_dir` | [`funding_source_snapshot.py:616-618`](../../quantbot/paper/funding_source_snapshot.py) | `source_path_resolution.resolved_funding_source_dir` in provenance |
| Bundle carry-through | [`funding_source_bundle.py:178-184`](../../quantbot/paper/funding_source_bundle.py) | `snapshot_scope` and `resolved_funding_source_dir` in bundle payload |
| Full-ledger verifier scope requirement | [`sqlite_verify.py:2278-2289`](../../quantbot/paper/sqlite_verify.py) | `_full_ledger_requires_full_window_scope()` returns True when `_committed_batch_count > 1` |
| Full-window snapshot resolution | [`sqlite_verify.py:2482-2537`](../../quantbot/paper/sqlite_verify.py) | `_resolve_full_window_snapshot_for_gate()` resolves by exact batch-bound filename |
| Scope-aware clean-carry gate | [`sqlite_verify.py:2589-2726`](../../quantbot/paper/sqlite_verify.py) | `_build_funding_clean_carry_stamp()` selects full-window sidecar when scope required |
| Scope-aware decision with explicit reason codes | [`funding_source_snapshot.py:763-883`](../../quantbot/paper/funding_source_snapshot.py) | `clean_mode_decision_from_snapshot_v1()` with `expected_snapshot_scope` param |
| Full-window path helpers | [`funding_source_snapshot.py:49-62`](../../quantbot/paper/funding_source_snapshot.py) | `full_window_snapshot_filename()`, `full_window_snapshot_path()` |
| Semantics tests (pure, no emit) | [`test_full_window_funding_source_snapshot_semantics.py`](../../tests/test_full_window_funding_source_snapshot_semantics.py) | 13 tests covering builder, decision, verifier gate, bundle carry-through |

### Current PR #119 blocker

A prod-like lane with multiple committed batches (e.g., lane A after 15+ batches)
cannot reach `CLEAN_NET_OF_CARRY` because:

1. The full-ledger gate (`_full_ledger_requires_full_window_scope`) returns True
   when `_committed_batch_count > 1`
2. The verifier calls `_resolve_full_window_snapshot_for_gate()` which looks for
   `funding_source_full_window_snapshot_v1_batch{target_batch_id}.json`
3. No such file exists → `funding_source_full_window_snapshot_missing` reason code
4. Verdict is `REFUSED_MISSING_SNAPSHOT`

The writer emission path (this task) produces the missing sidecar.

## 3. Current Implementation

The writer emission path is implemented in a **standalone module** — it is NOT
wired into `run_sqlite_accounting`. This is deliberate: the existing per-batch
snapshot writer path is untouched. The full-window emission path is an explicit,
opt-in entry point that reads the target lane DB **read-only** (never mutates it).

### Module: [`funding_source_full_window_emit.py`](../../quantbot/paper/funding_source_full_window_emit.py)

Public entry point:

```
emit_full_window_funding_source_snapshot(
    db_path: str | Path,
    *,
    data_dir: str | Path | None = None,
    generated_at_utc: str | None = None,
    qnty_git_commit: str = "",
    writer_or_verifier_command: str | None = None,
) -> FullWindowEmissionResult
```

Returns a `FullWindowEmissionResult` dataclass with:
- `snapshot_path` — path to the written snapshot
- `bundle_path` — path to the written bundle
- `target_batch_id` — latest committed batch ID
- `lane_id` — resolved lane
- `source_bundle_sha256` / `snapshot_sha256` — content digests
- `evaluation_window` — full-ledger span `{start, end}`
- `resolved_funding_source_dir` — absolute resolved path
- `envelope` — the full snapshot envelope (for test assertions)

#### Internal helpers

| Helper | Lines | Purpose |
|--------|-------|---------|
| `_lane_id_from_config()` | [`86-93`](../../quantbot/paper/funding_source_full_window_emit.py) | Read lane_id from `paper_config` (read-only) |
| `_latest_committed_batch()` | [`96-106`](../../quantbot/paper/funding_source_full_window_emit.py) | `SELECT ... FROM ledger_batches WHERE committed_at IS NOT NULL ORDER BY batch_id DESC LIMIT 1` |
| `_full_ledger_windows()` | [`108-136`](../../quantbot/paper/funding_source_full_window_emit.py) | `SELECT DISTINCT symbol, window_start, window_end FROM funding` across ALL committed batches |
| `_full_ledger_evaluation_window()` | [`138-148`](../../quantbot/paper/funding_source_full_window_emit.py) | `SELECT MIN(window_start), MAX(window_end) FROM funding` |
| `_resolve_source_dir()` | [`150-158`](../../quantbot/paper/funding_source_full_window_emit.py) | Resolve `data_dir` or `funding_loader._DATA_DIR` to absolute path |
| `_source_csv_paths()` | [`160-163`](../../quantbot/paper/funding_source_full_window_emit.py) | Derive CSV paths from distinct symbols in required windows |
| `_db_identity_hash()` | [`165-176`](../../quantbot/paper/funding_source_full_window_emit.py) | Deterministic identity binding for snapshot metadata |

#### Error handling

All errors raise `FundingSourceSnapshotEmissionError` (imported from
[`sqlite_writer.py:118`](../../quantbot/paper/sqlite_writer.py)). Refusal cases:

- No committed batch found
- No funding rows in DB
- Coverage decision != `complete`
- Envelope validation failure
- Invalid source bundle digest
- Source files missing/unreadable

### Reused writer primitives

The emit module imports two private helpers from `sqlite_writer.py`:

| Helper | Location | Purpose |
|--------|----------|---------|
| `_read_funding_source_csv_rows()` | [`sqlite_writer.py:1113`](../../quantbot/paper/sqlite_writer.py) | Read CSV rows from resolved source file paths |
| `_write_json_atomic()` | [`sqlite_writer.py:1190`](../../quantbot/paper/sqlite_writer.py) | Atomic JSON write (atomic rename) |

### DB read-only guarantee

The emit module opens the target DB via `connect_readonly()` from
[`db.py:132`](../../quantbot/paper/db.py), which uses URI `mode=ro` plus
`PRAGMA query_only=ON`. This path never:
- Mutates the ledger DB
- Updates `ledger_batches` reference columns
- Runs the trader / live / backfill
- Touches a report

### Selection by exact path

The full-window snapshot filename is bound to the latest committed batch ID:
```
funding_source_full_window_snapshot_v1_batch{N}.json
```

The verifier resolves it by the exact, derivable path
([`sqlite_verify.py:2503`](../../quantbot/paper/sqlite_verify.py)) — never a
fuzzy glob. No ambiguous multi-snapshot discovery.

### Snapshot / Bundle lifecycle

```
1. emit_full_window_funding_source_snapshot() called
2. Open DB read-only
   ├─ Resolve lane_id from paper_config
   ├─ Read latest committed batch (target_batch_id)
   ├─ Read full_ledger_windows (DISTINCT symbol/window_start/window_end from funding)
   └─ Compute full_ledger_evaluation_window (MIN/MAX from funding)
3. Close DB
4. Resolve source directory (absolute path)
5. Read source CSV rows
6. Build full-window payload via build_full_window_funding_source_snapshot_payload_v1()
   ├─ snapshot_scope = full_window
   ├─ evaluation_window = full_ledger window
   ├─ resolved_funding_source_dir = absolute
   ├─ write_state = committed
   ├─ pending_batch_id = None
   ├─ ledger_batch_id = str(target_batch_id)
   └─ batch_identity_matches = True / evaluation_identity_matches = True
7. Build envelope (content-addressed)
8. Validate envelope
9. Write snapshot to funding_source_full_window_snapshot_v1_batch{N}.json
10. Build bundle from envelope
11. Write bundle to funding_source_bundles/funding_source_bundle_v1_{sha}.json
12. Return FullWindowEmissionResult
```

### Verifier selection flow

```
_build_funding_clean_carry_stamp()
├─ _full_ledger_requires_full_window_scope(conn)
│  └─ returns True when _committed_batch_count > 1
├─ if full_window_required:
│  ├─ _funding_clean_carry_target_batch(conn)
│  └─ _resolve_full_window_snapshot_for_gate(db_path, cfg, target_batch_id)
│     ├─ Exact path: funding_source_full_window_snapshot_v1_batch{target_batch_id}.json
│     ├─ If missing → funding_source_full_window_snapshot_missing
│     ├─ If wrong scope → funding_source_snapshot_scope_mismatch
│     └─ If wrong lane/DB/batch → binding reasons
├─ clean_mode_decision_from_snapshot_v1() with expected_snapshot_scope=SNAPSHOT_SCOPE_FULL_WINDOW
│  └─ Validates: window, scope, lane, DB identity, batch binding, source digests, row digests
└─ Returns clean verdict or refusal with explicit reason codes
```

## 4. File Manifest

### Source (all exist)

| File | Status | Lines | Notes |
|------|--------|-------|-------|
| [`quantbot/paper/funding_source_full_window_emit.py`](../../quantbot/paper/funding_source_full_window_emit.py) | **EXISTS** | 309 | Complete emit module |
| [`quantbot/paper/funding_source_snapshot.py`](../../quantbot/paper/funding_source_snapshot.py) | EXISTS (PR #120) | 907 | Builder, helpers, decision |
| [`quantbot/paper/funding_source_bundle.py`](../../quantbot/paper/funding_source_bundle.py) | EXISTS | 337 | Bundle builder with scope/dir carry-through |
| [`quantbot/paper/sqlite_verify.py`](../../quantbot/paper/sqlite_verify.py) | EXISTS (PR #120) | 3776 | Full-window gate, resolution, clean-carry stamp |
| [`quantbot/paper/sqlite_writer.py`](../../quantbot/paper/sqlite_writer.py) | EXISTS (unchanged) | 2098 | Batch emission (reused primitives) |
| [`quantbot/paper/db.py`](../../quantbot/paper/db.py) | EXISTS | 753 | `connect_readonly()` |

### Exports

The public API for this task is:

```python
from quantbot.paper.funding_source_full_window_emit import (
    emit_full_window_funding_source_snapshot,
    FullWindowEmissionResult,
)
```

The module's `__all__` ([line 302](../../quantbot/paper/funding_source_full_window_emit.py))
exports these plus `full_window_snapshot_filename` and `full_window_snapshot_path`
(re-exported from `funding_source_snapshot.py`).

## 5. Test Plan

### Gap: No existing tests for the emit module

The existing test file
[`test_full_window_funding_source_snapshot_semantics.cs`](../../tests/test_full_window_funding_source_snapshot_semantics.py)
tests the *pure* builder/decision/verifier gate — it never calls
`emit_full_window_funding_source_snapshot()` and never writes artifacts to disk.

**A new test file is needed:**
`tests/test_funding_source_full_window_emit.py`

### Test matrix

#### Phase 1: Unit tests for emit helpers

| # | Test | What it verifies | Method |
|----|------|------------------|--------|
| 1 | `_lane_id_from_config` reads lane from `paper_config` | Helper correctly resolves lane identity | Create in-memory DB with `paper_config` table, call helper |
| 2 | `_lane_id_from_config` defaults to `paper_pnl_v1` | Graceful default when no lane_id column | Create minimal DB without lane_id column |
| 3 | `_latest_committed_batch` returns correct batch | Queries the latest committed batch | Insert 3 committed + 1 pending, verify last committed returned |
| 4 | `_latest_committed_batch` returns None when empty | Graceful when DB has no batches | Empty `ledger_batches` table → None |
| 5 | `_full_ledger_windows` returns distinct windows | Aggregates all committed funding rows | Insert funding rows across multiple symbols/windows, verify |
| 6 | `_full_ledger_evaluation_window` computes MIN/MAX | Computes correct full-ledger span | Funding rows with different start/end, verify span |
| 7 | `_resolve_source_dir` resolves to absolute | Correctly resolves relative to absolute | Patch `_funding_loader._DATA_DIR`, verify result |
| 8 | `_source_csv_paths` derives correct paths | Maps symbols to CSV filenames | 2 symbols → 2 paths under source_dir |
| 9 | `_db_identity_hash` produces deterministic hash | Identity binding is reproducible | Same inputs → same hash; different inputs → different hash |

#### Phase 2: Integration tests for `emit_full_window_funding_source_snapshot`

| # | Test | What it verifies | Setup |
|----|------|------------------|-------|
| 10 | Emits snapshot file at correct path | File written to `full_window_snapshot_path()` | Create real DB with 2 committed batches, funding rows, call emit, assert file exists |
| 11 | Emits bundle file at correct path | Bundle written to `bundle_path()` in `funding_source_bundles/` | Same setup, assert bundle file exists |
| 12 | Snapshot has `snapshot_scope = "full_window"` | Scope discriminator is correct | Read envelope, assert payload.snapshot_scope |
| 13 | Snapshot has absolute `resolved_funding_source_dir` | Provenance is absolute | Read envelope, assert provenance.source_path_resolution.resolved_funding_source_dir is absolute |
| 14 | Evaluation window covers MIN/MAX from funding table | Full-ledger span is correct | 2 funding rows with different windows, verify evaluation_window equals MIN(start)-MAX(end) |
| 15 | Bundle builds from envelope correctly | Bundle payload is valid, scope carried through | Read bundle, assert bundle_payload.snapshot_scope, assert bundle_window_reasons == [] |
| 16 | Emit raises when no committed batch exists | Fail closed on empty ledger | Empty DB, call emit, expect `FundingSourceSnapshotEmissionError` |
| 17 | Emit raises when no funding rows | Fail closed on empty funding table | DB with committed batch but no funding, call emit, expect error |
| 18 | Emit raises when source CSV missing | Fail closed on missing source file | DB with funding rows, non-existent source CSV path, expect error |
| 19 | Emit raises when coverage is not complete | Fail closed on incomplete rows | DB with funding rows, source CSV with partial data, expect error |

#### Phase 3: Verifier integration tests

| # | Test | What it verifies | Setup |
|----|------|------------------|-------|
| 20 | Verifier selects full-window sidecar after emit | `_resolve_full_window_snapshot_for_gate` returns envelope | Create DB, run emit, run verifier, assert full_window_snapshot_selected_path is set |
| 21 | Full-ledger clean-carry passes with full-window sidecar | Multi-batch ledger reaches clean verdict | Emit + verify, assert `clean_net_of_carry_allowed: True` |
| 22 | Multi-batch ledger without sidecar still refuses | Missing sidecar → `funding_source_full_window_snapshot_missing` | Multi-batch DB without emit, verify, assert refusal |
| 23 | Single-batch ledger unchanged without full-window scope | Single batch → no scope requirement | Single-batch DB, verify, assert `full_window_scope_required` is NOT set |
| 24 | Verifier refuses wrong lane DB binding | Lane mismatch caught | Emit with lane X, verify with lane Y, assert `funding_source_snapshot_db_mismatch` |
| 25 | Verifier refuses wrong batch binding | Batch ID mismatch caught | Emit for batch N, tamper target, assert mismatch |
| 26 | Verifier refuses tampered snapshot | Digest mismatch caught | Emit, modify snapshot file, verify refuses |
| 27 | Bundle mode works with full-window bundle | Bundle mode selects full-window bundle | Emit with bundle mode, verify picks correct bundle |

#### Phase 4: Regression tests

| # | Test | What it verifies | 
|----|------|------------------|
| 28 | Existing batch snapshot emission test passes | `test_paper_sqlite_writer_source_snapshot_emission.py` still passes |
| 29 | Existing bundle mode tests pass | `test_funding_source_immutable_bundle_semantics.py` still passes |
| 30 | Existing full-window semantics tests pass | `test_full_window_funding_source_snapshot_semantics.py` still passes |
| 31 | Existing verifier batch-scoped clean-carry tests pass | `test_paper_sqlite_verify_batch_scoped_clean_carry.py` still passes |
| 32 | Existing verifier source path resolution tests pass | `test_paper_sqlite_verify_source_path_resolution.py` still passes |
| 33 | Existing read-only CLI contract tests pass | `test_paper_sqlite_verify_read_only_cli_contract.py` still passes |

### Test fixture strategy

For Phase 2 integration tests, create a real SQLite DB with:

```sql
-- ledger_batches: 2 committed batches (batch-1, batch-2)
CREATE TABLE ledger_batches (
    batch_id INTEGER PRIMARY KEY,
    committed_at TEXT
);
INSERT INTO ledger_batches VALUES (1, '2026-07-01T00:00:00Z');
INSERT INTO ledger_batches VALUES (2, '2026-07-02T00:00:00Z');

-- paper_config: lane identity
CREATE TABLE paper_config (
    id INTEGER PRIMARY KEY,
    lane_id TEXT
);
INSERT INTO paper_config VALUES (1, 'paper_pnl_v1');

-- funding: rows spanning batch-1 and batch-2
CREATE TABLE funding (
    symbol TEXT,
    window_start TEXT,
    window_end TEXT,
    funding_rate REAL
);
INSERT INTO funding VALUES ('SOL', '2026-06-30T16:00:00Z', '2026-07-01T00:00:00Z', 0.0001);
INSERT INTO funding VALUES ('SOL', '2026-07-01T00:00:00Z', '2026-07-01T08:00:00Z', 0.0001);
```

Plus a real (or temp-copied) `SOL_8h_funding.csv` fixture in a temp data dir.

Alternatively, write the test to use `tmp_path` and create minimal CSVs with the
exact rows the snapshot builder expects.

## 6. Risks and Mitigations

| Risk | Impact | Mitigation |
|------|--------|------------|
| Emit module depends on private writer helpers (`_read_funding_source_csv_rows`, `_write_json_atomic`) | Writer refactors could break emit | Keep import surface minimal; if the writer moves, update the import path in `funding_source_full_window_emit.py:57-61` |
| Emit module imports `FundingSourceSnapshotEmissionError` from writer | Coupled error hierarchy | Shared exception class is intentional: same error semantics as batch emission |
| No CLI entry point wired yet | Cannot run emit from command line | Out of scope for this task; a future PR can add a `--emit-full-window` flag to `qnty-paper-sqlite-accounting` or a standalone script |
| Test fixture DB needs `PRAGMA query_only=ON` compatible schema | Test failures if DB has unexpected constraints | Design test fixtures with minimal schemas matching emit module expectations |
| Source CSV files need to exist at test time | Test flakiness | Use `tmp_path` with `tmp_path / "data"` dir and write minimal CSVs with correct headers |

## 7. Rollback Plan

Since the emit module is **not wired into `run_sqlite_accounting`** and does not
mutate the DB, rollback is straightforward:

- **Remove emitted sidecar files**: `rm funding_source_full_window_snapshot_v1_batch{N}.json`
  and `rm funding_source_bundles/funding_source_bundle_v1_{sha}.json`
- **Revert code**: `git checkout -- quantbot/paper/funding_source_full_window_emit.py`
- **Remove test file**: `rm tests/test_funding_source_full_window_emit.py`

The emit module is an opt-in sidecar writer. No existing behavior depends on it.

## 8. Blockers and Dependencies

| Blocker | Status |
|---------|--------|
| PR #120 merged (semantics foundation) | ✅ Done |
| `funding_source_full_window_emit.py` implemented | ✅ Done |
| `connect_readonly()` available in `db.py` | ✅ Done (PR #120) |
| Full-window builder in `funding_source_snapshot.py` | ✅ Done (PR #120) |
| Verifier full-window gate in `sqlite_verify.py` | ✅ Done (PR #120) |
| Bundle carry-through in `funding_source_bundle.py` | ✅ Done (PR #120) |
| **Tests for emit module** | **⏳ Not done** |
| CLI entry point for emit | ❌ Out of scope |

## 9. Implementation Plan — JSON Steps

```json
{
  "name": "QNTY Full-Window Funding Source Snapshot Writer Emission",
  "steps": [
    {
      "id": "step-1",
      "description": "Create test file tests/test_funding_source_full_window_emit.py with Phase 1-2 tests (emit helpers, integration)",
      "inputs": [
        "quantbot/paper/funding_source_full_window_emit.cs",
        "quantbot/paper/sqlite_writer.cs",
        "tests/test_full_window_funding_source_snapshot_semantics.cs"
      ],
      "allowed_tools": [
        "read_file",
        "write_to_file",
        "search_files",
        "run_slash_command",
        "execute_command"
      ],
      "verify_cmd": "python -m pytest tests/test_funding_source_full_window_emit.py -v --tb=short 2>&1",
      "done_definition": "All Phase 1-2 tests pass (emit helpers + integration)"
    },
    {
      "id": "step-2",
      "description": "Add Phase 3 tests to the same test file (verifier integration after emit)",
      "inputs": [
        "tests/test_funding_source_full_window_emit.py",
        "quantbot/paper/sqlite_verify.cs"
      ],
      "allowed_tools": [
        "read_file",
        "write_to_file",
        "search_files",
        "run_slash_command",
        "execute_command"
      ],
      "verify_cmd": "python -m pytest tests/test_funding_source_full_window_emit.py -v --tb=short 2>&1",
      "done_definition": "All Phase 1-3 tests pass (emit + verifier integration)"
    },
    {
      "id": "step-3",
      "description": "Run the full regression suite to confirm no regressions",
      "inputs": [
        "tests/test_paper_sqlite_writer_source_snapshot_emission.cs",
        "tests/test_full_window_funding_source_snapshot_semantics.cs",
        "tests/test_paper_sqlite_verify_batch_scoped_clean_carry.cs",
        "tests/test_paper_sqlite_verify_source_path_resolution.cs",
        "tests/test_paper_sqlite_verify_read_only_cli_contract.cs",
        "tests/test_funding_source_immutable_bundle_semantics.cs"
      ],
      "allowed_tools": [
        "read_file",
        "write_to_file",
        "execute_command"
      ],
      "verify_cmd": "python -m pytest tests/ -v --tb=short -x --timeout=120 2>&1 | tail -40",
      "done_definition": "Full suite passes with no regressions; new emit tests all pass"
    },
    {
      "id": "step-4",
      "description": "Verify type-checking and lint pass cleanly",
      "inputs": [
        "quantbot/paper/funding_source_full_window_emit.cs",
        "tests/test_funding_source_full_window_emit.cs"
      ],
      "allowed_tools": [
        "execute_command"
      ],
      "verify_cmd": "python -m pyright quantbot/paper/funding_source_full_window_emit.py tests/test_funding_source_full_window_emit.py 2>&1",
      "done_definition": "No type errors; flake8/pylint clean on new files"
    }
  ],
  "risks": [
    {
      "risk": "Emit module depends on private writer helpers that may change",
      "mitigation": "Import surface is explicit and minimal; any writer refactor must update the import in funding_source_full_window_emit.py:57-61"
    },
    {
      "risk": "Test fixtures require real CSV files with specific content",
      "mitigation": "Use tmp_path with write_to_file to create minimal CSVs matching expected row format"
    },
    {
      "risk": "Verifier integration tests need coordination between emit + verify in same test",
      "mitigation": "Call emit_full_window_funding_source_snapshot() then directly invoke verifier functions in a single test; avoid forking subprocesses"
    }
  ],
  "rollback_plan": "git checkout -- quantbot/paper/funding_source_full_window_emit.py && rm -f tests/test_funding_source_full_window_emit.py",
  "checkpoint_usage": "Save checkpoint after Phase 1 passes, after Phase 2 passes, and after full regression passes"
}
```

## 10. Verdict

**READY FOR IMPLEMENTATION** — with the following true state:

**IMPLEMENTED (no code changes needed):**
- [`funding_source_full_window_emit.py`](../../quantbot/paper/funding_source_full_window_emit.py) — 309 lines, complete
- Verifier wiring in [`sqlite_verify.py`](../../quantbot/paper/sqlite_verify.py) — already selects full-window sidecar
- Snapshot builder in [`funding_source_snapshot.py`](../../quantbot/paper/funding_source_snapshot.py) — full-window builder and decision logic
- Bundle carry-through in [`funding_source_bundle.py`](../../quantbot/paper/funding_source_bundle.py) — scope and dir fields

**NEEDS IMPLEMENTATION (test gap):**
- [`tests/test_funding_source_full_window_emit.py`](../../tests/test_funding_source_full_window_emit.py) — does NOT exist yet
- Required: 27+ tests across 4 phases (unit helpers, integration, verifier integration, regression)

**OUT OF SCOPE (future PRs):**
- CLI entry point (`--emit-full-window` flag or standalone script)
- Wired into `run_sqlite_accounting()`
- Production deployment / timer change