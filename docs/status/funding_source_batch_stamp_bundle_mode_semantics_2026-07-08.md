# Funding-source batch-stamp bundle-mode semantics (2026-07-08)

**Task:** `FUNDING_SOURCE_BATCH_STAMP_BUNDLE_MODE_SEMANTICS_GIT_OWNED`
**Branch:** `feature/funding-source-batch-stamp-bundle-mode`
**Status boundary:** `EDGE_UNPROVEN` remains. `BLOCK_LIVE_INTEGRATION` remains.
`CLEAN_NET_OF_CARRY` means only "not killed by this verifier gate" — not edge,
profit, or live-capital approval.

## PLAN

The full-ledger clean-carry gate (`_build_funding_clean_carry_stamp`) already
honors `source_mode`: in `bundle` mode it resolves funding-source digest
expectations from the pinned immutable bundle
(`_bundle_source_digest_expectations`) instead of the mutable live `data/*.csv`.
The additive **batch-scoped** stamp (`_build_funding_clean_carry_batch_stamp`)
did **not** accept `source_mode` and always used
`_snapshot_source_digest_expectations` (live-current). Result: under
`source_mode="bundle"` the full-ledger gate reached `CLEAN_NET_OF_CARRY` while
the batch stamp still reported `CAVEATED_ENGINE_SEMANTICS /
refused_digest_mismatch` from `funding_source_file_digest_mismatch` against
drifted live CSVs (the PR #111 promotion blocker; see
[[batch-clean-carry-stamp-live-current-only]]).

Fix: thread `source_mode` through the batch-stamp path and, in `bundle` mode,
resolve digest expectations from the bundle — mirroring the full-ledger gate
exactly. The fix is **semantic**: the batch stamp uses the same source-evidence
mode as the requested verifier mode. No reason codes are string-filtered and no
digest mismatch is merely ignored; the live-current path is byte-for-byte
unchanged and remains the default.

## CHANGESET

`quantbot/paper/sqlite_verify.py`
- `_build_funding_clean_carry_batch_stamp(...)`: added
  `source_mode: str = SOURCE_MODE_LIVE_CURRENT` keyword param + docstring note;
  added `resolution_fields = {"source_resolution_mode": source_mode}`.
- Step 5d now branches on `source_mode`: `SOURCE_MODE_BUNDLE` ->
  `_bundle_source_digest_expectations(...)` (bundle reason codes + bundle
  identity recorded); else ->
  `_snapshot_source_digest_expectations(...)` (live CSV digests recorded), same
  as the full-ledger gate.
- Both `batch_report` return paths merge `resolution_fields` (so the batch
  detail sub-dict now carries `source_resolution_mode` and, in bundle mode,
  bundle identity; in live mode, `live_source_digests`).
- `_verify_connection(...)` now passes `source_mode=source_mode` into
  `_build_funding_clean_carry_batch_stamp(...)`.

`tests/test_paper_sqlite_verify_batch_scoped_clean_carry.py`
- Added a bundle-mode section (imports `_build_planned_bundle`,
  `_drift_live_sol_funding_rate` from the immutable-bundle suite):
  1. `test_batch_stamp_live_current_still_detects_live_csv_drift`
  2. `test_batch_stamp_bundle_mode_survives_live_csv_drift`
  3. `test_batch_stamp_bundle_mode_refuses_missing_bundle`
  4. `test_batch_stamp_bundle_mode_refuses_corrupt_bundle`
  5. `test_batch_stamp_bundle_mode_refuses_hash_mismatch`
  6. `test_batch_stamp_default_mode_is_live_current_and_labeled`
  7. `test_bundle_mode_does_not_weaken_full_ledger_gate`

`git diff --stat origin/main`: 2 files changed, 198 insertions(+), 11 deletions(-).

## VERIFY

Rungs run (venv):
1. Import check: `IMPORT_OK`.
2. Scoped tests:
   - `test_paper_sqlite_verify_batch_scoped_clean_carry.py` +
     `test_funding_source_immutable_bundle_semantics.py`: **28 passed**.
   - `test_paper_sqlite_verifier_clean_net_of_carry_gate.py`: **14 passed**.
   - `test_paper_sqlite_verify_report.py`,
     `..._source_path_resolution.py`, `..._read_only_cli_contract.py`,
     `test_funding_source_digest_window_semantics.py`,
     `test_paper_sqlite_funding_coverage.py`: **40 passed, 3 failed**.
3. `git diff --check`: clean.

Proven by the new tests: (1) live-current batch stamp still flips on live CSV
drift; (2) bundle-mode batch stamp survives live CSV drift with a valid bundle
(`CLEAN_NET_OF_CARRY`, bundle identity recorded, no live digests); (3) bundle
mode refuses on missing/corrupt/hash-mismatch bundle (`REFUSED_BUNDLE`); (4)
full-ledger gate semantics unchanged under bundle mode; (5) default stays
live-current and labels the resolution mode.

**Pre-existing failures (NOT caused by this change):** the writer-emission
tests in `test_paper_sqlite_verify.py` (23 fail / 48 pass) and the 3 in
`test_paper_sqlite_verify_report.py` fail identically on a clean `origin/main`
tree (`git stash` reproduced 23 failed / 48 passed). They abort in the *writer*
with `FUNDING_SOURCE_SNAPSHOT_EMISSION_FAILED: ... data/AAAUSDT_8h_funding.csv:
No such file` (a CWD-relative `data/` dependency) and never reach the read-only
verifier code this change touches.

**VM read-only check:** NOT performed (optional). Local tests conclusively
exercise the semantic change against tmp DBs/CSVs/bundles; the VM check would
only re-demonstrate it against the real shadow DB read-only. Left for an
explicit follow-up if Viktor wants the live-shadow receipt.

## What was NOT touched
No real/prod/shadow DB mutation. No official report overwrite. No source CSV
mutation. No service/timer/cron/systemd change. No writer/trader/backfill/
data-refresh run. No deploy, no exchange keys, no live integration, no report
promotion, no source-freeze. `/srv/qnty/repo` main worktree untouched.
Application behavior outside the batch-stamp source-mode threading is unchanged;
the live-current default path is preserved exactly.

## VERDICT

`FUNDING_SOURCE_BATCH_STAMP_BUNDLE_MODE_SEMANTICS_RECORDED`

**Next action:** open the PR for
`feature/funding-source-batch-stamp-bundle-mode` (docs + minimal verifier code +
tests) once Viktor confirms. The bundle-mode batch stamp is now internally
consistent with the full-ledger gate, which unblocks a future
bundle-mode official-report promotion attempt for the shadow lane (still gated
by `EDGE_UNPROVEN` / `BLOCK_LIVE_INTEGRATION`).
