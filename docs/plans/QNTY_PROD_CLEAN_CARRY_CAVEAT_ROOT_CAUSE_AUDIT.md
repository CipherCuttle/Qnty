# QNTY Prod CLEAN_NET_OF_CARRY Caveat — Root Cause Audit

## 1. Purpose

PR #71 (`STRICT_READ_ONLY_PROD_VERIFIER_AUDIT_CAVEATED`) ran the strict
read-only clean-carry verifier against the prod `paper_pnl_v1` ledger and
found the DB-linked funding source snapshot structurally valid (sidecar
exists, DB SHA matches sidecar bytes, envelope validates, bundle/schema/
write_state committed, funding re-sum OK, DB unchanged before/after) yet the
strict CLI still refused `CLEAN_NET_OF_CARRY` and returned
`CAVEATED_ENGINE_SEMANTICS` with four reason codes plus 36 `missing_source_row`
funding windows. This audit is a read-only, no-write root-cause investigation
into *why* the caveat persists despite the passing manual checks, per the
`A`–`E` hypothesis list in the task brief.

## 2. Scope

Read-only only. No prod writer, no shadow writer, no writer against `/srv`,
no prod/shadow DB mutation, no `forward_obs` mutation, no data refresh, no
migrations, no schema-ensure helpers, no systemd/timer changes, no dependency
installs, no WAL checkpoint. All DB access used an immutable, read-only
SQLite URI (`file:...?mode=ro&immutable=1`) with `PRAGMA query_only=ON`. All
verifier invocations used `--read-only --strict-clean-carry`, and
`db_mutation_performed: false` was confirmed on every run.

## 3. Prior strict verifier result (PR #71)

```txt
STRICT_READ_ONLY_PROD_VERIFIER_AUDIT_CAVEATED

Strict CLI result:
- CAVEATED_ENGINE_SEMANTICS
- funding_source_coverage_not_complete
- funding_source_file_digest_mismatch
- funding_source_row_digest_mismatch
- funding_source_snapshot_window_mismatch
- 36 missing_source_row funding windows across all 5 tracked symbols

Manual checks passed:
- DB-linked sidecar exists
- DB file SHA matches sidecar bytes
- envelope validation passes
- bundle/schema/write_state committed
- funding re-sum OK
- DB unchanged before/after
```

## 4. Read-only commands

VM precheck (`/srv/qnty/repo`, commit `8576d6f`, clean `main` branch):

```bash
ssh -i ~/.ssh/hetzner_qnty_key -o IdentitiesOnly=yes viktor@37.27.216.174
cd /srv/qnty/repo
hostname && date -u
git status --short --branch
git log --oneline -5
/srv/qnty/venv/bin/python -m py_compile quantbot/paper/sqlite_verify.py       # OK
/srv/qnty/venv/bin/python -m py_compile quantbot/paper/funding_source_snapshot.py  # OK
```

Strict CLI, run twice under two different working directories to isolate a
CWD-dependent path effect (both `--read-only --json --strict-clean-carry`,
both confirmed `db_mutation_performed: false`):

```bash
# Run 1: default SSH login cwd (/home/viktor) — reproduces PR #71 caveat
/srv/qnty/venv/bin/python -m quantbot.paper.sqlite_verify \
  --db-path /srv/qnty/output/paper_pnl_v1/paper_ledger.db \
  --read-only --json --strict-clean-carry > /tmp/qnty_prod_strict_verify.json
# exit_code=4

# Run 2: cwd = /srv/qnty/repo
cd /srv/qnty/repo
/srv/qnty/venv/bin/python -m quantbot.paper.sqlite_verify \
  --db-path /srv/qnty/output/paper_pnl_v1/paper_ledger.db \
  --read-only --json --strict-clean-carry > /tmp/qnty_prod_strict_verify_cwdrepo.json
# exit_code=4
```

Read-only DB inspection (immutable URI, `PRAGMA query_only=ON`) covered:
`sqlite_master` table list, `ledger_batches`/`funding`/`ledger_state`/
`equity_snapshots` row counts and columns, the latest `ledger_batches` row's
`funding_source_snapshot_*` reference columns, all 36 `funding` rows ordered
by `seq`, per-symbol funding row counts, the full 36-row funding window span
(`MIN(window_start)`/`MAX(window_end)`), and the latest committed sidecar
JSON payload (`snapshot_payload.evaluation_window`, `required_funding_windows`,
`source_files`, `symbols_covered`, `coverage_decision`, `reason_codes`).

Code inspection (read-only, no edits): `quantbot/paper/sqlite_verify.py`
(`_resolve_funding_csv_dir`, `_build_funding_coverage_stamp`,
`_snapshot_source_file_path`, `_read_snapshot_source_rows`,
`_snapshot_source_digest_expectations`, `_funding_evaluation_window`,
`_build_funding_clean_carry_stamp`) and `quantbot/paper/funding_source_snapshot.py`
(`_evaluation_window`, `build_funding_source_snapshot_payload_v1`,
`clean_mode_decision_from_snapshot_v1`).

## 5. Latest prod batch reference

```txt
batch_id: 39
created_at: 2026-07-03T16:21:35Z
prior_watermark_bar_ts: 2026-07-03T00:00:00
new_watermark_bar_ts:   2026-07-03T08:00:00
funding_source_snapshot_write_state: committed
funding_source_snapshot_created_at:  2026-07-03T16:21:35Z
funding_source_snapshot_bundle_sha256: 05db004f...dfae3ea
```

Batches 28–38 (the 11 batches immediately prior) all have `funding_source_
snapshot_write_state = NULL` (no DB-linked snapshot reference) — only the
newest batch (39) carries one. This is expected under an incremental,
per-batch writer model, not evidence of a writer defect.

## 6. Snapshot payload/window findings

The committed sidecar (`funding_source_snapshot_v1_05db004f...json`,
`schema_version FUNDING_SOURCE_SNAPSHOT_SCHEMA_V1`, `write_state: committed`,
`coverage_decision: complete`, `reason_codes: []`) declares:

```txt
evaluation_window: { start: 2026-07-03T00:00:00Z, end: 2026-07-03T08:00:00Z }
required_funding_windows: 4 entries (BTCUSDT, ETHUSDT, SOLUSDT, XRPUSDT
                           @ 2026-07-03T00:00–08:00), each with a matched
                           accepted_source_row and source_issue: null
symbols_covered: [BTCUSDT, ETHUSDT, SOLUSDT, XRPUSDT]   (BNBUSDT excluded —
                           no funding row fell in this window for BNBUSDT)
```

The full `funding` table's window span (`MIN(window_start)`/`MAX(window_end)`
across all 36 rows) is `2026-06-21T00:00:00` → `2026-07-03T08:00:00` — i.e.
the entire ledger's funding history since inception, roughly 12 days / 39
batches, versus the sidecar's single 8-hour batch-39 window. The writer's
`_evaluation_window()` (funding_source_snapshot.py:461) derives the window
strictly from the `required_windows` passed in by the caller for that one
batch — it is designed as a per-batch, incremental snapshot, not a
full-ledger snapshot.

## 7. Funding table/window findings

`funding` has 36 rows total (`BNBUSDT`: 1, `BTCUSDT`: 4, `ETHUSDT`: 6,
`SOLUSDT`: 20, `XRPUSDT`: 5), spanning `2026-06-21T08:00:00` through
`2026-07-03T08:00:00`. Re-running the strict CLI with `cwd=/srv/qnty/repo`
(Run 2) instead of the default SSH login directory (Run 1) changed the
`funding_coverage` result from `decision: missing` / 36 `missing_source_row`
entries (including the four most-recent rows that the sidecar itself already
marks `accepted_source_row` with `source_issue: null`) to `decision: complete`
/ 0 missing rows. Both runs are read-only and neither mutated the DB.

Cause: `_resolve_funding_csv_dir(db_path)` (sqlite_verify.py:1391) checks
`db_path.parent / "data"` (`/srv/qnty/output/paper_pnl_v1/data`, which does
not exist), then falls back to the **CWD-relative** path `Path("data")`.
`_snapshot_source_file_path` (sqlite_verify.py:2092) has the same fallback
shape. Since the real CSVs live only at `/srv/qnty/repo/data/*.csv`
(confirmed: `BTCUSDT_8h_funding.csv` has 5488 rows, matching the sidecar's
`source_csv_row_index: 5486`), both helpers silently resolve to a
nonexistent path whenever the verifier is invoked from any directory other
than the repo root — which is exactly how the CLI command in the task brief
(and in PR #71) was written, with no `cd /srv/qnty/repo` before it. This is
a real, reproducible verifier defect (CWD-dependent path resolution with a
silent wrong-answer fallback, not a fail-loud error) and it fully explains
three of the four original reason codes: `funding_source_coverage_not_
complete`, `funding_source_file_digest_mismatch`, `funding_source_row_digest_
mismatch`. It is a secondary/contributing bug, not the structural blocker —
see §9.

## 8. Digest/coverage reason-code analysis

With the CWD effect isolated (Run 2, `cwd=/srv/qnty/repo`):

```txt
funding_coverage.decision:               complete   (was: missing)
funding_source_coverage_not_complete:     gone
funding_source_file_digest_mismatch:      gone
funding_source_row_digest_mismatch:       gone
funding_source_snapshot_window_mismatch:  STILL PRESENT (sole remaining reason)
funding_clean_carry_decision:            CAVEATED_ENGINE_SEMANTICS (unchanged)
```

The one surviving reason code traces to `_build_funding_clean_carry_stamp`
(sqlite_verify.py:2254) → `clean_mode_decision_from_snapshot_v1` (funding_
source_snapshot.py:632), which compares the sidecar's declared
`evaluation_window` against `expected_evaluation_window =
_funding_evaluation_window(conn)` (sqlite_verify.py:2083) —
`MIN(window_start)`/`MAX(window_end)` over the **entire** `funding` table
(full ledger history, 2026-06-21 → 2026-07-03), not the latest batch. Since
the writer only ever emits a batch-scoped window (§6), and the verifier's
strict gate expects a full-ledger-scoped window, an exact match is
structurally impossible under the current writer's incremental-snapshot
design — regardless of how many further batches accumulate DB-linked
snapshots, unless every prior batch also gets (and keeps) one and the
verifier's comparison is redefined to reason over that union rather than a
single evaluation_window equality check.

## 9. Root-cause classification

```txt
ROOT_CAUSE_BATCH_VS_LEDGER_WINDOW_SEMANTICS
```

The strict clean-carry gate's `funding_source_snapshot_window_mismatch` check
compares a per-batch-scoped writer snapshot against a full-ledger-scoped
verifier expectation; these two semantics disagree by construction, so the
caveat persists even when the DB-linked snapshot is structurally valid and
its own declared window is 100% covered. This survives with the CWD path
defect (§7) fixed, confirming it is the true structural blocker rather than
a corollary of the path bug. The CWD-dependent path-resolution defect in
`_resolve_funding_csv_dir`/`_snapshot_source_file_path` is a real, separate,
secondary bug (silent wrong-answer fallback instead of resolving to the repo
root or failing loud) that inflated the original caveat with three spurious
reason codes and 36 false `missing_source_row` findings; it should be fixed
independently of the window-semantics question, but does not by itself
explain why the caveat would still occur under correct invocation.

## 10. Recommended next implementation

```txt
PLAN_BATCH_SCOPED_CLEAN_CARRY_VERIFIER
```

Per the task's conservatism instruction: root cause B (batch/window
semantics mismatch — structurally analogous to a full-ledger coverage-scope
gap) calls for a docs-only plan first, not a code change. A follow-up plan
should scope how the strict gate should reason about clean-carry when
DB-linked snapshots are incremental/per-batch: e.g. compare each batch's
snapshot window against that batch's own watermark range (already available
as `prior_watermark_bar_ts`/`new_watermark_bar_ts` on `ledger_batches`)
rather than the full-ledger `MIN`/`MAX`, and separately decide whether older,
un-snapshotted batches should be treated as an explicit backfill gap
(`funding_source_coverage_not_complete`, honestly labeled) versus folded into
a redefined per-batch gate. The CWD-dependent path defect in §7 should also
be tracked as a separate, smaller fix (resolve relative to repo root / `git
rev-parse --show-toplevel` or fail loudly instead of silently falling back
to a CWD-relative path) — but that is independent of, and does not block,
the batch-scoped verifier planning work.

## 11. What was not done

No prod writer, shadow writer, or any writer against `/srv` was run. No
prod or shadow DB was mutated (`db_mutation_performed: false` confirmed on
every verifier invocation). No `forward_obs` mutation. No data refresh, no
migrations, no schema-ensure helpers. No systemd/timer changes. No
dependency installs. No WAL checkpoint. No code in `quantbot/paper/
sqlite_verify.py` or `quantbot/paper/funding_source_snapshot.py` was
modified — only read via `Read`/`grep`/`py_compile`. All SQLite access used
`file:...?mode=ro&immutable=1` with `PRAGMA query_only=ON`.

## 12. Interpretation

No edge claim. No profitability claim. `EDGE_UNPROVEN` remains preserved.
Prod/current remains `CAVEATED_ENGINE_SEMANTICS`. No `CLEAN_NET_OF_CARRY`
relabel is made by this audit. No writer, migration, schema ensure, refresh,
timer change, `forward_obs` mutation, or DB mutation was performed.

## 13. Verdict

```txt
PROD_CLEAN_CARRY_CAVEAT_ROOT_CAUSE_AUDIT_COMPLETE
```
