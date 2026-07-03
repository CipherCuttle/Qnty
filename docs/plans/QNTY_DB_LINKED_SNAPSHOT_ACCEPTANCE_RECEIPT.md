# QNTY DB-Linked Snapshot Acceptance Receipt

## 1. Purpose

Record acceptance of the DB-linked funding source snapshot selector chain for future/tmp SQLite writer-created batches.

## 2. Scope

This receipt covers repository changes through the additive `ledger_batches` snapshot reference columns, writer DB reference storage, post-commit sidecar marker handling, and verifier DB-linked clean-carry selection.

It does not cover a live read-only acceptance audit, prod/shadow DB mutation, `/srv` writer execution, data refresh, VM inspection, edge proof, or profitability proof.

## 3. Current repository state

`main` includes the DB-linked selector chain through:

- PR #60: additive nullable `ledger_batches` funding source snapshot reference columns.
- PR #61: writer storage of funding source snapshot DB references and post-commit committed marker/hash updates.
- PR #62: verifier clean-carry selection from exact `ledger_batches` DB-linked snapshot references.

`EDGE_UNPROVEN` remains preserved.

## 4. Implemented DB-linked selector chain

The DB is now the selector authority for clean-carry funding source snapshot evidence. The sidecar remains the evidence payload. Hashes bind the DB reference to the sidecar and bind the sidecar envelope to its canonical payload.

Old/current live ledgers remain caveated when they lack valid committed DB-linked snapshot references.

## 5. Writer DB reference behavior

For future writer-created batches, the writer emits a pending funding source snapshot sidecar before ledger mutation, stores the pending sidecar reference on the batch inside the ledger transaction, then attempts a committed sidecar rewrite after DB commit.

After the committed sidecar rewrite succeeds, the writer updates `ledger_batches.funding_source_snapshot_sha256` to the committed sidecar file-byte SHA and updates DB write state to `committed`. If that post-commit DB update fails, the batch remains caveated and no clean claim is made.

## 6. Verifier DB-linked selector behavior

The verifier clean-carry path starts from the verifier target committed `ledger_batches` row and uses its snapshot reference fields as the deterministic selector.

It rejects missing or incomplete DB references, missing sidecar files, references outside `<db_path.parent>/funding_source_snapshots/`, path traversal, DB file-byte SHA mismatch, envelope payload digest mismatch, bundle/schema mismatch, DB/lane/window/batch identity mismatch, non-committed DB or sidecar state, duplicate DB references, source coverage issues, arithmetic failures, and independent funding re-sum mismatch.

Directory scan remains diagnostic/provenance context only.

## 7. Clean-carry gate behavior

`STATUS_OK` remains arithmetic/accounting status only. It does not imply `CLEAN_NET_OF_CARRY`.

The system can now prove CLEAN_NET_OF_CARRY for future/tmp writer-created batches when DB-linked committed snapshot references, valid sidecar hashes, complete source coverage, arithmetic OK, and re-sum proof all pass.

Failure in any DB-linked selector, sidecar hash, coverage, arithmetic, or re-sum requirement preserves `CAVEATED_ENGINE_SEMANTICS`.

## 8. Synthetic test evidence

Phase 1 evidence:

- `python -m pytest tests/test_paper_sqlite_ledger_batch_snapshot_reference_schema.py -q` -> passed.
- `python -m pytest tests/test_paper_sqlite_verifier_clean_net_of_carry_gate.py -q` -> passed.
- `python -m pytest tests/test_paper_sqlite_verifier_source_snapshot_read.py -q` -> passed.
- `python -m pytest tests/test_funding_source_snapshot_schema.py -q` -> passed.
- `/tmp/qnty-pr50-pandas-test/bin/python -m pytest tests/test_paper_sqlite_writer_source_snapshot_emission.py -q` -> passed.
- `/tmp/qnty-pr50-pandas-test/bin/python -m pytest tests/test_paper_sqlite_writer_funding_coverage.py -q` -> passed.

Phase 2 evidence:

- `/tmp/qnty-pr50-pandas-test/bin/python -m pytest tests/test_paper_sqlite_writer_snapshot_reference_transaction.py -q` -> passed.
- `/tmp/qnty-pr50-pandas-test/bin/python -m pytest tests/test_paper_sqlite_writer_source_snapshot_emission.py -q` -> passed.
- `/tmp/qnty-pr50-pandas-test/bin/python -m pytest tests/test_paper_sqlite_writer_funding_coverage.py -q` -> passed.
- `/tmp/qnty-pr50-pandas-test/bin/python -m pytest tests/test_paper_sqlite_writer_funding_fail_closed_proof.py -q` -> passed.
- Python verifier/schema/snapshot tests and `py_compile` checks passed.

Phase 3 evidence:

- `python -m pytest tests/test_paper_sqlite_verifier_db_linked_snapshot_selector.py -q` -> passed.
- `python -m pytest tests/test_paper_sqlite_verifier_clean_net_of_carry_gate.py -q` -> passed.
- `python -m pytest tests/test_paper_sqlite_verifier_source_snapshot_read.py -q` -> passed.
- `python -m pytest tests/test_paper_sqlite_ledger_batch_snapshot_reference_schema.py -q` -> passed.
- `python -m pytest tests/test_funding_source_snapshot_schema.py -q` -> passed.
- `/tmp/qnty-pr50-pandas-test/bin/python -m pytest tests/test_paper_sqlite_writer_snapshot_reference_transaction.py tests/test_paper_sqlite_writer_source_snapshot_emission.py -q` -> passed.
- `python -m py_compile quantbot/paper/db.py quantbot/paper/funding_source_snapshot.py quantbot/paper/sqlite_writer.py quantbot/paper/sqlite_verify.py` -> passed.

## 9. Why old/current live ledgers remain caveated

Current/live ledgers are not relabeled because no read-only live acceptance run was performed and historical/current batches lack valid committed DB-linked snapshot references.

Historical rows with NULL snapshot reference fields remain valid historical evidence, but they do not satisfy the DB-linked clean-carry selector.

## 10. Why no live CLEAN_NET_OF_CARRY is claimed

No live `CLEAN_NET_OF_CARRY` is claimed because this sprint used tmp/synthetic tests only and did not run a read-only live acceptance audit.

Current/live ledgers are not `CLEAN_NET_OF_CARRY`.

## 11. Remaining blockers

Remaining blockers for any live clean-carry label are:

- A separately authorized read-only live acceptance audit.
- Live/current batches with valid committed DB-linked snapshot references.
- Verified sidecar file-byte hashes, envelope payload digests, source bundle/schema identity, source coverage, arithmetic OK, and funding re-sum proof for the evaluated live target.

## 12. Next optional read-only live audit

The optional next task is a separate `READ_ONLY_LIVE_SNAPSHOT_STATUS_AUDIT` authorization. That task was explicitly not run in this sprint.

## 13. Safety boundaries

This sprint did not run a prod writer, shadow writer, `/srv` writer, real DB migration, data refresh, VM SSH, live trading action, or exchange-key action.

No profitability or edge claim is made.

`CAVEATED_ENGINE_SEMANTICS` remains preserved for current/live evidence.

## 14. Verdict

The DB-linked selector chain is implemented for future/tmp writer-created batches under the stated synthetic acceptance evidence.

`EDGE_UNPROVEN` remains preserved.

`CAVEATED_ENGINE_SEMANTICS` remains preserved for current/live evidence.

No live `CLEAN_NET_OF_CARRY` relabel is made.
