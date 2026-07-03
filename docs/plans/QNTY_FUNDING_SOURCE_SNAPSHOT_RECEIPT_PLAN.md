# QNTY Funding Source Snapshot Receipt Plan

## 1. Purpose

Task: `DOCS_ONLY_FUNDING_SOURCE_SNAPSHOT_RECEIPT_PLAN`

Create a docs-only implementation plan for funding source snapshot/content
addressing, so future funding/carry verdicts can be reproduced from recorded
source evidence instead of mutable repo `data/` CSV state.

This plan does not implement code, edit tests, edit fixtures, run any writer,
refresh data, mutate any SQLite DB, mutate `forward_obs`, change
systemd/timers, install dependencies, run migrations, touch `.claude/`, or
authorize live execution.

Current interpretation remains:

```txt
EDGE_STATUS: EDGE_UNPROVEN
funding verdict: CAVEATED_ENGINE_SEMANTICS
not CLEAN_NET_OF_CARRY
```

## 2. Context

Local preflight before creating this docs branch:

```txt
branch before plan branch: main
HEAD: d960e9234608822dc9210e5b75f1f018973ec7ef
origin/main: d960e9234608822dc9210e5b75f1f018973ec7ef
main == origin/main: yes
HEAD is d960e92 or newer: yes
tracked tree clean: yes
allowed untracked: .claude/
```

Required files present on `main`:

```txt
docs/plans/QNTY_CLEAN_NET_OF_CARRY_REPAIR_PLAN.md
quantbot/paper/funding_time.py
quantbot/paper/funding_coverage.py
quantbot/paper/sqlite_writer.py
tests/test_funding_timestamp_normalization_spec.py
tests/test_paper_sqlite_writer_funding_fail_closed_proof.py
```

This follows the merged repair chain:

```txt
PR #46 clean-net-of-carry repair plan merged
PR #47 funding timestamp normalization spec merged
PR #48 shared funding timestamp normalization merged
PR #49 sqlite writer funding fail-closed proof merged
PR #50 sqlite writer funding source ambiguity fail-closed merged
main: d960e92
```

Current capabilities:

```txt
shared funding timestamp normalization
same-second endpoint canonicalization
writer fail-closed behavior for missing/outside/duplicate source coverage
```

Remaining missing capability:

```txt
immutable funding source snapshots
source row/content-addressing
clean-mode verifier tied to a source snapshot digest
independent receipt proving source data used for a given evaluation window is reproducible
CLEAN_NET_OF_CARRY
```

## 3. Current Remaining Caveat

Timestamp normalization and writer fail-closed behavior reduce ambiguity, but
they do not make historical funding evidence reproducible.

The remaining caveat is:

```txt
repo/source CSVs are mutable over time
verifier may read current data/ state, not the exact source rows used during a historical writer run
rate_available=1 inside DB proves the engine had a funding row, not that source evidence is immutable/replayable
clean-carry needs a digestable source evidence bundle
```

The current verifier fallback to `<db_dir>/data` or repo `data/` is useful for
diagnostics, but it is not sufficient for a historical clean-carry receipt.
Future clean-mode verification must bind the DB/evaluation window to a recorded
funding source snapshot.

## 4. Desired Snapshot/Receipt Artifact

The snapshot should be an operator-readable and machine-checkable JSON artifact
that records source funding evidence, normalized row decisions, and provenance.
It should support both strict future verification and caveated historical
diagnostics.

Required minimum contents:

```txt
schema_version
generated_at_utc
evaluation_window_start
evaluation_window_end
lane_id
output_dir
db_path_reference
db_identity_hash_before
batch_start_watermark
batch_end_watermark
ledger_batch_id if available after commit, otherwise pending_batch_id
normalization_spec_version
funding source files used
full source file SHA-256
canonical accepted/rejected row-subset SHA-256
symbols covered
required funding windows
accepted source row per required window
canonical endpoint per accepted row
raw fundingTime ms
normalized/canonical timestamp
funding rate
duplicate rows if any
missing rows if any
outside same-second rows if any
final coverage decision
reason codes
source_bundle_sha256
```

The artifact must record both:

```txt
1. full source file SHA-256
2. canonical accepted/rejected row-subset SHA-256
```

Full-file hashes detect any source CSV mutation. They are intentionally strict
and may be brittle when source CSVs are appended after the evaluation window.
Canonical row-subset hashes preserve reproducibility for the exact funding
windows being evaluated. Strict clean-mode can require both; archived historical
receipts may allow row-subset-only only when explicitly documented.

## 5. Recommended Artifact Location

Options:

| Option | Description | Strength | Weakness |
| --- | --- | --- | --- |
| 1 | Inside paper output dir next to DB | Closest to the evaluated ledger and manual `--db-path` runs | Needs orphan handling when DB commit fails |
| 2 | Per-batch receipt directory | Clear grouping for operator receipts | Adds another path convention before DB linkage exists |
| 3 | Committed docs receipt only | Easy to review | Not enough for machine replay; docs can drift from artifacts |
| 4 | DB metadata table | Strong DB linkage | Requires schema/migration decisions too early |
| 5 | Hybrid output artifact plus docs summary | Machine-checkable artifact with operator-facing summary | Requires sidecar atomicity and orphan policy |

Recommended v1 strategy: hybrid output artifact plus docs receipt summary.

Future snapshots should live under the evaluated DB directory:

```txt
<db_dir>/funding_source_snapshots/funding_source_snapshot_v1_<snapshot_sha256>.json
```

A docs receipt should record:

```txt
snapshot path
snapshot_sha256
source_bundle_sha256
evaluation window
lane/output/db references
final coverage decision
clean-mode refusal reasons if any
```

Docs receipts summarize evidence; they do not replace the source snapshot.

## 6. DB/Schema Strategy

Prefer no DB migration for the first version.

The v1 implementation should use:

```txt
standalone JSON snapshot artifact
snapshot SHA recorded in docs receipt
optional batch/window identifiers inside the snapshot payload
no ALTER
no migration
no retroactive DB row mutation
```

DB metadata can be revisited later only if standalone artifacts are not enough.
Possible later additions:

```txt
ledger_batches metadata field, if a schema extension is explicitly authorized
new source_snapshot table, only if sidecar linkage proves insufficient
```

Until then, clean-mode verifier logic should treat an unreferenced or orphaned
sidecar as insufficient for `CLEAN_NET_OF_CARRY`.

## 7. Writer Integration Plan

The writer should build a snapshot for the evaluated source coverage decision,
including clean, caveated, or refused reasons.

The writer should only proceed to durable ledger mutation when required funding
coverage passes the writer's fail-closed gate.

Recommended sequencing:

```txt
1. acquire writer lock and read DB identity/state
2. load observation, OHLCV, and funding source data
3. run in-memory engine
4. derive engine-required funding windows
5. evaluate source coverage using shared timestamp normalization
6. build funding source snapshot payload for the evaluated decision
7. write snapshot sidecar atomically
8. proceed to durable DB inserts only if required coverage passed
9. commit DB transaction
```

Atomic sidecar rules:

```txt
write snapshot to temp file
fsync temp file if practical
atomic rename to final path
only then proceed to durable DB inserts
```

Failure rules:

```txt
snapshot creation/write failure aborts before durable DB mutation
missing required funding coverage aborts before durable DB mutation
source duplicate/outside/missing ambiguity aborts before durable DB mutation
manual explicit --db-path runs use the same snapshot logic
snapshot location derives from db_path.parent
```

If DB commit later fails, the already-written snapshot is orphaned. An orphaned
snapshot must be ignored unless a later receipt or batch identity explicitly
ties it to a committed evaluation window.

Payload linkage fields should include:

```txt
db_path_reference
db_identity_hash_before
batch_start_watermark
batch_end_watermark
ledger_batch_id if available after commit, otherwise pending_batch_id
```

## 8. Verifier Integration Plan

The verifier should keep normal arithmetic `OK` separate from clean-carry
classification.

Normal verification may remain additive and diagnostic. Clean-mode verification
must be stricter:

```txt
require snapshot presence
recompute snapshot/payload digests
recompute full-file and row-subset digests where available
check DB/window/lane linkage
refuse CLEAN_NET_OF_CARRY when the snapshot is missing, mismatched, orphaned, ambiguous, or not tied to the evaluated DB/window
emit structured reason codes
preserve CAVEATED_ENGINE_SEMANTICS when arithmetic is OK but clean evidence is incomplete
```

The verifier may continue to report arithmetic status as `OK` for an internally
consistent DB. It must not collapse arithmetic `OK` into clean funding/carry
evidence when snapshot proof is absent or mismatched.

## 9. Snapshot Schema Draft

Use an envelope to avoid self-hash ambiguity:

```json
{
  "snapshot_payload": {
    "schema_version": "funding_source_snapshot_v1",
    "generated_at_utc": "YYYY-MM-DDTHH:MM:SSZ",
    "evaluation_window": {
      "start": "YYYY-MM-DDTHH:MM:SSZ",
      "end": "YYYY-MM-DDTHH:MM:SSZ"
    },
    "db_reference": {
      "db_path_reference": "<path-or-sanitized-path>",
      "db_identity_hash_before": "<sha256-or-config-hash>",
      "batch_start_watermark": "<timestamp-or-null>",
      "batch_end_watermark": "<timestamp-or-null>",
      "pending_batch_id": "<stable pending id>",
      "ledger_batch_id": null
    },
    "lane": {
      "lane_id": "<lane-id-or-null>",
      "output_dir": "<path-or-sanitized-path>"
    },
    "normalization_spec_version": "FUNDING_TIMESTAMP_NORMALIZATION_SPEC_V2",
    "source_files": [
      {
        "symbol": "SOLUSDT",
        "path": "data/SOLUSDT_8h_funding.csv",
        "full_file_sha256": "<sha256>",
        "canonical_row_subset_sha256": "<sha256>"
      }
    ],
    "required_windows": [
      {
        "symbol": "SOLUSDT",
        "window_start": "YYYY-MM-DDTHH:MM:SS",
        "window_end": "YYYY-MM-DDTHH:MM:SS",
        "accepted_source_row": {
          "raw_fundingTime_ms": 0,
          "canonical_endpoint": "YYYY-MM-DDTHH:MM:SSZ",
          "normalized_timestamp": "YYYY-MM-DDTHH:MM:SSZ",
          "funding_rate": 0.0,
          "row_sha256": "<sha256>"
        },
        "duplicate_rows": [],
        "missing_rows": [],
        "outside_same_second_rows": [],
        "coverage_decision": "accepted",
        "reason_codes": []
      }
    ],
    "final_coverage_decision": "complete|partial|missing|refused|not_required",
    "reason_codes": [],
    "source_bundle_sha256": "<sha256>",
    "provenance": {
      "entity_inputs": [
        {
          "source_csv_path": "data/SOLUSDT_8h_funding.csv",
          "source_csv_sha256": "<sha256>",
          "canonical_row_subset_sha256": "<sha256>"
        }
      ],
      "activity": {
        "writer_or_verifier_command": "<sanitized command>",
        "qnty_git_commit": "<40-hex-sha>",
        "normalization_spec_version": "FUNDING_TIMESTAMP_NORMALIZATION_SPEC_V2",
        "generated_at_utc": "YYYY-MM-DDTHH:MM:SSZ"
      },
      "agent": {
        "qnty_paper_writer_or_verifier_version": "<version>",
        "lane_id": "<lane-id-or-null>",
        "machine_user_label": "<optional sanitized label>"
      }
    }
  },
  "snapshot_sha256": "<sha256>"
}
```

Hash rule:

```txt
snapshot_sha256 = sha256(canonical_json(snapshot_payload))
```

`snapshot_sha256` is computed over canonical JSON excluding the
`snapshot_sha256` field itself.

Canonical row ordering:

```txt
symbol
window_end
fundingTime_ms
source CSV path
source row index
```

## 10. Reason Codes

Required reason codes:

```txt
funding_source_snapshot_missing
funding_source_snapshot_digest_mismatch
funding_source_snapshot_schema_unsupported
funding_source_snapshot_window_mismatch
funding_source_snapshot_db_mismatch
funding_source_snapshot_unreferenced_or_orphaned
funding_source_file_digest_mismatch
funding_source_row_digest_mismatch
funding_source_missing
funding_source_partial
funding_source_duplicate_ambiguous
funding_timestamp_outside_tolerance
funding_timestamp_open_boundary
funding_resum_mismatch
```

Verifier reports should surface these as structured fields, not only prose.

## 11. Tests Required

Future implementation PRs need tests for:

```txt
snapshot JSON schema validates
PROV fields are present
snapshot self-hash envelope is deterministic
stable canonical row ordering
file SHA determinism
row-subset SHA determinism
digest mismatch refusal
snapshot missing refusal for clean-mode
orphaned/unreferenced snapshot refusal for clean-mode
mutable source CSV changed after run -> strict clean-mode refusal
duplicate canonical endpoint -> snapshot caveated/refused
outside same-second row -> snapshot caveated/refused
writer records evaluated coverage decision, including refused/caveated reasons
writer proceeds to durable ledger mutation only after fail-closed coverage passes
writer aborts before DB mutation when snapshot creation/write fails
atomic temp-write/rename behavior
manual explicit db_path path uses same snapshot logic
```

Existing funding timestamp and writer fail-closed tests must continue to pass.
The tests should remain local and synthetic unless a later receipt explicitly
authorizes read-only VM evidence collection.

## 12. Recommended PR Sequence

| Order | PR | Purpose | Files likely touched | Tests likely added | Acceptance gate | Rollback/safety notes | VM needed |
| ---: | --- | --- | --- | --- | --- | --- | --- |
| 1 | `TEST_ONLY_FUNDING_SOURCE_SNAPSHOT_SCHEMA` | Pin snapshot schema, PROV fields, canonical ordering, envelope hashing, digest policy, and orphan refusal semantics before implementation. | new tests under `tests/` only | schema validation, PROV presence, self-hash envelope, row ordering, digest determinism, orphan refusal | Tests define the contract without production code changes. | Test-only. No DB, writer, fixtures, `/srv`, or VM. | No |
| 2 | `IMPLEMENT_FUNDING_SOURCE_SNAPSHOT_BUILDER` | Add a pure builder for evaluated funding windows and source rows. | likely new helper under `quantbot/paper/`, maybe funding coverage adapter | full-file SHA, row-subset SHA, source decision payload, reason-code payload | Builder output is deterministic from synthetic rows and source files. | Pure local helper. No writer invocation. Easy revert. | No |
| 3 | `IMPLEMENT_WRITER_SOURCE_SNAPSHOT_EMISSION` | Emit atomic sidecar before durable DB inserts and abort on snapshot failure. | `quantbot/paper/sqlite_writer.py`, maybe CLI wiring | atomic temp/rename, snapshot failure abort, manual `--db-path` path behavior | Writer records evaluated coverage decision and mutates DB only after fail-closed source coverage passes. | Local tmp DB tests only. No `/srv`. | No |
| 4 | `IMPLEMENT_SQLITE_VERIFIER_SOURCE_SNAPSHOT_READ` | Read explicit snapshot artifacts, recompute digests, and detect orphan/unreferenced artifacts. | `quantbot/paper/sqlite_verify.py`, snapshot helper | missing snapshot, digest mismatch, DB/window mismatch, orphan refusal | Normal arithmetic status remains separate; clean-mode has structured refusal reasons. | Additive verifier path. No DB migration. | No |
| 5 | `IMPLEMENT_VERIFIER_CLEAN_NET_OF_CARRY_GATE` | Refuse clean-mode without complete snapshot proof while preserving arithmetic `OK`. | verifier status/report path, CLI flag if needed | missing/mismatched/orphaned/source-ambiguous clean-mode refusal, independent funding re-sum mismatch | `CLEAN_NET_OF_CARRY` unreachable without snapshot proof and arithmetic/re-sum agreement. | Does not rewrite existing DB rows. | No for unit tests |
| 6 | `ADD_FUNDING_SOURCE_SNAPSHOT_ACCEPTANCE_RECEIPT` | Publish receipt-grade source snapshot evidence after implementation lands. | new docs receipt only | none unless receipt exposes a gap | Receipt states clean/caveated/refused with snapshot digest evidence. | Read-only by default. No writer unless separately authorized. | Read-only only if explicitly authorized |

Keep these PRs separate from strategy changes, take-profit work, shorting, or
live execution work.

## 13. Acceptance Gates

No future implementation can claim clean funding/carry until all of these pass:

```txt
shared timestamp normalization remains in use
writer fail-closed behavior still aborts before DB mutation on missing/outside/duplicate required source coverage
snapshot JSON schema validates
PROV fields are present
snapshot self-hash envelope is deterministic
full source file SHA determinism holds
row-subset SHA determinism holds
canonical row ordering is stable
atomic temp-write/rename behavior is tested
orphaned snapshot is ignored/refused
digest mismatch refuses clean-mode
missing snapshot refuses clean-mode
mutated source CSV after run refuses strict clean-mode
duplicate canonical endpoint refuses/caveats
outside same-second row refuses/caveats
writer records evaluated coverage decision
writer proceeds to durable ledger mutation only after fail-closed coverage passes
snapshot failure aborts before DB mutation
manual explicit --db-path uses same snapshot logic
normal arithmetic OK remains separate from clean-carry decision
independent funding re-sum evidence agrees with DB cumulative funding fields
```

Until a future receipt proves those gates, the operative labels remain:

```txt
EDGE_UNPROVEN
CAVEATED_ENGINE_SEMANTICS
not CLEAN_NET_OF_CARRY
```

## 14. Rollback/Safety Notes

This docs-only plan can be reverted by removing this one file.

Future implementation safety rules:

```txt
no retroactive mutation of existing DB rows
no DB migration in v1
no ALTER in v1
no source data refresh as part of snapshot implementation
no prod/shadow writer run without explicit separate authorization
no VM write action
no service/timer mutation
orphaned snapshots are ignored unless explicitly tied to a committed batch/window
```

If a snapshot sidecar exists but cannot be tied to a committed batch/evaluation
window, the verifier must emit
`funding_source_snapshot_unreferenced_or_orphaned` and refuse clean-mode.

## 15. What Not To Do

Explicitly blocked:

```txt
no retroactive mutation of existing DB rows
no relabeling current ledgers as CLEAN_NET_OF_CARRY
no take-profit implementation
no shorting
no live execution
no FrankenTrader
no edge claim
no profitability claim
```

Also blocked:

```txt
do not treat writer OK as authoritative clean funding/carry evidence
do not treat mutable repo data/ as historical source truth
do not use docs-only summaries as a substitute for machine-checkable source snapshots
do not combine source snapshotting with strategy or execution changes
```

## 16. Verdict

```txt
FUNDING_SOURCE_SNAPSHOT_PLAN_READY_FOR_PR_WITH_PROVENANCE_AND_ATOMICITY_AMENDMENTS
```
