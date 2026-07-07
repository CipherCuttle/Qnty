# QNTY Funding Source Shadow Official Report Promotion Plan

Plan for a future, explicitly approved promotion of a fresh real shadow-DB
verifier result to the official shadow verifier report path, now that PR #101
proved the real DB-linked full-ledger clean-carry gate is clean.

This document is plan-only. It authorizes no promotion, no DB mutation, no
writer/trader/live/backfill run, and no code/test/schema/verifier/reporter/writer
change.

## 1. Status Boundary

- This is a plan only.
- No official report overwrite occurs in this PR.
- No DB mutation occurs in this PR.
- No writer / trader / live / backfill run occurs in this PR.
- No code / test / schema / verifier / reporter / writer change occurs in this
  PR.
- No prod DB mutation occurs in this PR.
- No edge, profit, live, shorting, or deployment claim is made by this PR.
- `EDGE_UNPROVEN` remains.
- `BLOCK_LIVE_INTEGRATION` remains.
- Real shadow DB full-ledger clean-carry was proven clean by PR #101, using a
  read-only real DB-linked verifier run that returned `CLEAN_NET_OF_CARRY` with
  reason codes `[]`.
- The official report remains stale until a separate, explicitly approved future
  promotion execution replaces it.

## 2. Why This Plan Exists

- PR #99 proved metadata-aligned copied-DB full-ledger clean-carry:
  `CLEAN_NET_OF_CARRY`, reason codes `[]`, target funding-source caveats absent,
  and no real DB mutation.
- PR #100 planned the real shadow DB recommit, including backup, rollback,
  guarded DB update, `/tmp` verifier output, and an explicit boundary that the
  official report must not be overwritten during recommit.
- PR #101 executed the real shadow DB recommit: exactly one `ledger_batches` row
  (batch `17`) had the six `funding_source_snapshot_*` fields set, exactly one
  new funding-source sidecar JSON was written under the shadow lane, and the
  real DB-linked verifier proved full-ledger `CLEAN_NET_OF_CARRY`.
- The official report was deliberately not overwritten by PR #101.
- Therefore official report promotion is now plannable, but still requires a
  separate explicit approval and execution task.

## 3. Target Report And Inputs

- Official shadow verifier report:
  `/srv/qnty/output/paper_pnl_null_shadow_v0/paper_verify_report.json`
- Real shadow DB:
  `/srv/qnty/output/paper_pnl_null_shadow_v0/paper_ledger.db`
- Shadow lane output dir:
  `/srv/qnty/output/paper_pnl_null_shadow_v0`
- Data dir:
  `/srv/qnty/repo/data`
- VM repo:
  `/srv/qnty/repo`
- Future promotion workspace / verifier output path pattern:
  `/tmp/qnty_shadow_report_promotion_<timestamp>/paper_verify_report.candidate.json`
- Future stderr path pattern:
  `/tmp/qnty_shadow_report_promotion_<timestamp>/paper_verify_report.candidate.err`
- Backup dir pattern:
  `/tmp/qnty_shadow_report_promotion_backup_<timestamp>/`
- PR #101 verifier output was written under `/tmp`, not to the official report.
  A future execution must re-run the verifier fresh. Any surviving old `/tmp`
  output may be used only as hash-verified comparison evidence, never as the
  direct promotion source.

## 4. Preconditions For Future Promotion Execution

The future execution must verify and record all of the following before any
promotion write:

- Local `main` includes PR #101 merge SHA
  `23344f8e4ff315712b528780733d8cc6ccc97f68`.
- Real shadow DB exists at
  `/srv/qnty/output/paper_pnl_null_shadow_v0/paper_ledger.db`.
- Official report exists at
  `/srv/qnty/output/paper_pnl_null_shadow_v0/paper_verify_report.json`.
- A fresh real shadow DB verifier run still returns:
  - status `OK`;
  - `failure_count` `0`;
  - full-ledger clean-carry `CLEAN_NET_OF_CARRY`;
  - full-ledger reason codes `[]`;
  - target funding-source caveats absent:
    - `funding_source_file_digest_mismatch`;
    - `funding_source_snapshot_window_mismatch`;
    - `funding_source_snapshot_db_mismatch`;
    - `funding_source_snapshot_unreferenced_or_orphaned`.
- Batch clean-carry is either clean or remains `CAVEATED_ENGINE_SEMANTICS` with
  only `funding_source_batch_window_mismatch`.
- No writer / trader / live / backfill process is running.
- Source CSV digests under `/srv/qnty/repo/data` are stable during promotion.
- VM repo `/srv/qnty/repo` is unchanged during promotion.
- Official report before hash / size / mtime are captured.
- DB before hash / size / mtime are captured.
- Shadow output dir before aggregate / listing are captured.
- Disk space is sufficient for backup, temp candidate output, and atomic replace.
- Backup directory is prepared under
  `/tmp/qnty_shadow_report_promotion_backup_<timestamp>/`.

If any precondition fails, stop before promotion.

## 5. Backup / Rollback

Backup requirements before overwrite:

- Copy the current official report to:
  `/tmp/qnty_shadow_report_promotion_backup_<timestamp>/paper_verify_report.json`
- Capture official report before sha256, size, and mtime.
- Optionally capture real shadow DB sha256, size, and mtime in the backup
  metadata, but do not mutate or copy the DB unless explicitly needed for
  metadata retention.
- Verify the backup report sha256 equals the original official report sha256
  before promotion. If it does not match, stop.

Rollback requirements:

- If candidate write, atomic rename, or post-promotion validation fails, restore
  the official report from the verified backup.
- After rollback, verify the restored official report sha256 equals the original
  official report sha256.
- Verify the real shadow DB hash is unchanged from preflight.
- Record the failed promotion and rollback evidence in a receipt.

Atomicity requirement:

- Promotion must write the candidate to a temporary file in the official report
  directory, fsync the file and containing directory if practical, then rename
  the temporary file into place as `paper_verify_report.json`.
- Never stream verifier output directly to the official report path.

## 6. Fresh Verifier Generation

Future execution should:

1. Run the verifier against the real shadow DB read-only:

   ```bash
   quantbot.paper.sqlite_verify --db-path /srv/qnty/output/paper_pnl_null_shadow_v0/paper_ledger.db --read-only --json --data-dir /srv/qnty/repo/data
   ```

2. Write stdout first to:
   `/tmp/qnty_shadow_report_promotion_<timestamp>/paper_verify_report.candidate.json`
3. Write stderr to:
   `/tmp/qnty_shadow_report_promotion_<timestamp>/paper_verify_report.candidate.err`
4. Capture stdout and stderr size and sha256.
5. Verify the DB was not mutated by the verifier by comparing DB before/after
   sha256, size, and mtime.
6. Verify no `paper_ledger.db-wal` or `paper_ledger.db-shm` residue was created
   by the verifier.
7. Validate the candidate JSON parses.
8. Check verifier `status`, `failure_count`, full-ledger clean-carry decision,
   full-ledger reason codes, funding-source status, DB-linked status, source path
   availability, read-only open mode, and mutation fields.

Do not write directly to the official report path.

## 7. Candidate Report Acceptance Criteria

The candidate report can be promoted only if all of the following are true:

- JSON parses.
- `status` is `OK`.
- `failure_count` is `0`.
- Watermark matches the expected latest real shadow DB watermark.
- Full-ledger clean-carry is `CLEAN_NET_OF_CARRY`.
- Full-ledger reason codes are `[]`.
- Target caveats are absent:
  - `funding_source_file_digest_mismatch`;
  - `funding_source_snapshot_window_mismatch`;
  - `funding_source_snapshot_db_mismatch`;
  - `funding_source_snapshot_unreferenced_or_orphaned`.
- Funding snapshot status is `present_valid`.
- DB-linked is `true`.
- Source path available is `true`.
- Verifier opened the DB read-only / immutable.
- `db_mutation_performed` is `false`.
- Official report has not changed since the preflight hash was captured.
- Source CSV digests are stable during the run.
- VM repo `/srv/qnty/repo` is unchanged during the run.

Batch clean-carry may remain `CAVEATED_ENGINE_SEMANTICS` only if the sole reason
is `funding_source_batch_window_mismatch`.

Any other caveat stops promotion.

## 8. Promotion Execution Outline

Future execution sequence:

1. Run preflight checks and create verified backups.
2. Generate candidate verifier JSON to `/tmp`.
3. Validate candidate acceptance criteria.
4. Compare the current official report hash to the preflight official report
   hash; it must still match.
5. Write the candidate to a temporary file in the official report directory:
   `paper_verify_report.json.tmp.<timestamp>`.
6. Fsync the temporary file and containing directory if practical.
7. Atomically rename the temporary file to:
   `paper_verify_report.json`.
8. Compute official report after hash / size / mtime.
9. Verify official report after hash equals candidate report hash.
10. Verify real DB hash is unchanged.
11. Verify VM repo `/srv/qnty/repo` is unchanged.
12. Verify output dir changes are exactly official report replacement and temp
    file cleanup.
13. Record the execution receipt.

## 9. Stop Conditions

Stop without promotion if any of the following occur:

- PR #101 SHA `23344f8e4ff315712b528780733d8cc6ccc97f68` is not present on
  local `main`.
- The real DB verifier does not return the expected clean full-ledger result.
- Official report before hash changes during the run.
- Source CSV digests change mid-run.
- DB hash changes unexpectedly.
- VM repo `/srv/qnty/repo` changes.
- A writer / trader / live / backfill process is running.
- Candidate JSON is invalid.
- Unexpected caveats are present.
- Batch has any caveat beyond `funding_source_batch_window_mismatch`.
- Backup cannot be created or hash-verified.
- Atomic write / rename cannot be performed safely.
- Official report after hash does not equal candidate hash.

If a failure occurs after a temp file is written but before validation completes,
remove only the temp file and restore the official report from backup if it was
replaced.

## 10. Expected Future Execution Receipt

Future execution should create:
`docs/status/funding_source_shadow_official_report_promotion_2026-07-07.md`

It must record:

- report before / after hash, size, and mtime;
- candidate report path and sha256;
- exact verifier command;
- exact promotion command;
- DB before / after hash proving DB unchanged;
- official report before / after proving intended replacement;
- output dir before / after;
- source digests before / after;
- clean-carry decisions and reasons;
- target caveats absent;
- no writer / trader / live / backfill process;
- `EDGE_UNPROVEN` remains;
- `BLOCK_LIVE_INTEGRATION` remains.

## 11. Expected Future PR Sequence

1. `FUNDING_SOURCE_SHADOW_OFFICIAL_REPORT_PROMOTION_EXECUTION_GIT_OWNED`
   - re-run the verifier fresh;
   - promote the official report atomically;
   - record the execution receipt.
2. `QNTY_POST_FUNDING_SOURCE_REPAIR_STATUS_ROLLUP_GIT_OWNED`
   - optional docs/status rollup of final current state.
3. Then begin paper-only experiment planning:
   - `QNTY_PAPER_EXPERIMENT_VARIANT_REGISTRY_PLAN_GIT_OWNED`
   - `QNTY_SHORTING_HYPOTHESIS_SCOPING_PLAN_GIT_OWNED`

## 12. Non-Goals

- No official report promotion in this PR.
- No DB mutation.
- No writer / trader / live / backfill.
- No code / test / schema / verifier / reporter / writer changes.
- No prod DB mutation.
- No edge / profit / live / shorting / deployment claim.
- No shorting / trial registry / null lane / benchmark lane change.
