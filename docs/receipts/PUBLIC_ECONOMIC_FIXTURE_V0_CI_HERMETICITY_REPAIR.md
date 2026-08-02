# Public economic fixture v0 — CI hermeticity repair receipt

**Task ID:** `REPAIR_PUBLIC_ECONOMIC_FIXTURE_CI_HERMETICITY_V0`
**PR:** `CipherCuttle/Qnty#326`
**Branch:** `feat/public-economic-fixture-v0-integration`
**Worktree:** `/home/swirky/DevHub/worktrees/Qnty-public-economic-fixture-v0`

## Failed workflow and run ID

- Workflow: `qnty-full-suite`
- Run: `https://github.com/CipherCuttle/Qnty/actions/runs/30767520608`
- Job: `full-suite`

## CI failure summary

`10 failed, 7544 passed, 1 skipped in 311.34s`. All ten failures were in
`tests/test_public_funding_economic_fixture_v0.py`:

```
test_source_hash_mutation_rejected[raw-...]
test_source_hash_mutation_rejected[selected_event-...]
test_source_event_mutation_rejected[symbol-ETHUSDT-SYMBOL_MISMATCH]
test_source_event_mutation_rejected[fundingTime-1780272000002-FUNDING_TIME_INVALID]
test_source_event_mutation_rejected[rateType-Special-RATE_TYPE_INVALID]
test_runnable_module_returns_bounded_verdict
test_runnable_module_resolves_real_qntylab_checkout_from_worktree
test_env_root_succeeds
test_explicit_root_overrides_env_root
test_receipt_identity_independent_of_source_root_location
```

## Root cause

The test helper `_source_copy()` called `resolve_source_root()` to locate a
real, locally checked-out `QntyLab` sibling repository and copy evidence
bytes from it:

```
FileNotFoundError: [Errno 2] No such file or directory:
'/home/runner/work/Qnty/QntyLab/docs/forensics/evidence/binance_public_funding_event_v0/BTCUSDT-fundingRate-2026-06.raw.json'
```

A GitHub Actions checkout of `Qnty` alone has no `QntyLab` sibling. This is
not flaky CI — it is a structural non-portability defect in the test suite.

## Hermetic test contract

- **Production source verification** may still consume authenticated
  evidence from an explicit external QntyLab root (`--source-root`,
  `QNTYLAB_ROOT`, or the bounded worktree-aware sibling fallback).
- **QNTY unit/CI tests** now use immutable, hash-pinned, QNTY-local test
  evidence and never require a QntyLab checkout to exist.
- **Local integration smoke** (running the CLI with no override against a
  real local QntyLab checkout) remains possible manually but is not a
  required pytest case.

## Vendored test evidence

Byte-exact copies of the authenticated QntyLab evidence, committed under
`tests/fixtures/public_funding_economic_v0/source_root/`:

```
docs/forensics/PUBLIC_ECONOMIC_FIXTURE_CONTRACT_V0.json
docs/forensics/evidence/binance_public_funding_event_v0/BTCUSDT-fundingRate-2026-06.raw.json
docs/forensics/evidence/binance_public_funding_event_v0/BTCUSDT-fundingRate-2026-06.selected-event.json
docs/forensics/evidence/binance_public_funding_event_v0/BTCUSDT-fundingRate-2026-06.receipt.json
```

Verified hashes (SHA-256), matching the required pinned values exactly:

```
contract JSON:      b6c9ad8f3b21c983952820c6bb05d4ca6e8a8695cc3b5b57db34413e7391b5c3
raw REST response:  01d38d5b8c8581388621015a2bc618673cac1ff51ff88672aea52f9bdb31bafd
selected event:     fcc0682d5a30976d860fbbefaf415b0e0c0d0585835a4a8ef089acd9c5376b59
source receipt:     456e7918e3d9c7caeee67a8bde729867cbe0143f2002e7496ef5234382278c1c
```

A `README.md` in the vendored directory states this is a test-only,
byte-exact fixture and does not create a second research-evidence
authority. No other QntyLab content (repository, unrelated forensic
reports, personal data, market-data archives) was copied.

## Non-portable test replacement

`test_runnable_module_resolves_real_qntylab_checkout_from_worktree` (required
a real second checkout) was replaced with
`test_worktree_fallback_resolver_derives_sibling_qntylab_root`: it builds a
fake `<tmp>/repos/Qnty/.git` + `<tmp>/repos/QntyLab/<pinned evidence>` +
`<tmp>/worktrees/Qnty-feature/` layout, monkeypatches
`_git_common_dir` to return the fake `.git` common dir, and proves
`_default_source_root()` / `resolve_source_root()` derive the sibling
`QntyLab` path and that the fixture verifies end to end against it, with the
absolute temporary path confirmed absent from canonical receipt bytes. A
real local-checkout smoke run remains a documented manual option (see
`_run_cli()` with no override, run manually beside a real QntyLab checkout),
not a required pytest case.

A new direct fixture-integrity test,
`test_fixture_integrity_committed_test_evidence`, proves the four committed
files exist, match the frozen hashes, that the selected event is raw index
0 and field-identical to the raw event, that the source receipt's
`artifact_hashes` bind the raw/selected hashes, and that the contract JSON's
`source_fixture` and `source_event_identity` bind the same selected-event
identity — read directly from the fixture files, independent of the
production verifier.

## Production behavior

`quantbot/paper/public_funding_economic_fixture.py` was **not modified**.
`resolve_source_root()` already supported explicit `--source-root`,
`QNTYLAB_ROOT`, and a bounded worktree-aware sibling fallback with no
test-only seam needed. In a clean QNTY-only checkout, the default CLI (no
`--source-root`, no `QNTYLAB_ROOT`) truthfully fails with
`SOURCE_FIXTURE_MISSING` — verified in the clean-checkout simulation below.
This is expected and correct: production source verification requires
external evidence, and the test suite does not assert otherwise.

## Identity stability

Unchanged, verified after the repair:

```
receipt ID:               3833f2fb83a0c59031236cf5bb29b2de0ad2122765f03074f219a2c24bf5bd9b
canonical receipt SHA-256: d7a8827d8054ac2a843baf25dcc9dd547f4235ef10571e30d43cb69ef20b294f
```

No change to the economic formula, golden vectors, source hashes, selected
event, non-claims, account-posting status, or research-state policy.

## Changed paths

```
tests/test_public_funding_economic_fixture_v0.py
tests/fixtures/public_funding_economic_v0/source_root/README.md
tests/fixtures/public_funding_economic_v0/source_root/docs/forensics/PUBLIC_ECONOMIC_FIXTURE_CONTRACT_V0.json
tests/fixtures/public_funding_economic_v0/source_root/docs/forensics/evidence/binance_public_funding_event_v0/BTCUSDT-fundingRate-2026-06.raw.json
tests/fixtures/public_funding_economic_v0/source_root/docs/forensics/evidence/binance_public_funding_event_v0/BTCUSDT-fundingRate-2026-06.selected-event.json
tests/fixtures/public_funding_economic_v0/source_root/docs/forensics/evidence/binance_public_funding_event_v0/BTCUSDT-fundingRate-2026-06.receipt.json
docs/receipts/PUBLIC_ECONOMIC_FIXTURE_V0_CI_HERMETICITY_REPAIR.md
```

No changes to `quantbot/paper/engine.py`, database schemas, strategy code,
network code, `input.json`, `expected_receipt.json`, QntyLab, GitHub workflow
files, or candidate/trial/decision state.

## Feature-test results

- Before repair (live CI, run 30767520608): **10 failed, 7544 passed, 1
  skipped**.
- After repair, local run
  (`tests/test_public_funding_economic_fixture_v0.py`, `QNTYLAB_ROOT` and
  `TMPDIR` unset): **62 passed**, 0 failures (61 prior + 1 net: one
  non-portable test replaced by two hermetic tests).
- Audit-hook instrumentation confirmed every file path opened under a name
  containing `QntyLab` during this run was inside pytest's own `tmp_path`
  sandbox, never the real local QntyLab checkout.

## Clean-checkout simulation

Built via `git stash create` (captures the fully staged repair tree as a
dangling commit without touching the branch or working tree) then
`git archive <dangling-commit> | tar -x` into a fresh temporary directory
with no `QntyLab` sibling present:

- `tests/test_public_funding_economic_fixture_v0.py` from the archive:
  **62 passed**, 0 failures, with no sibling QntyLab directory on disk.
- Explicit portable CLI run (`--source-root <temp-copy-of-vendored-fixture>
  --verify`) from the archive: `PUBLIC_ECONOMIC_FIXTURE_V0_VERIFIED`,
  `receipt_id` and `receipt_sha256` matching the frozen identity values
  above.
- Default CLI run (no `--source-root`, no `QNTYLAB_ROOT`) from the archive:
  truthfully rejected with `SOURCE_FIXTURE_MISSING`, confirming production
  behavior is unchanged and the test suite does not assert a clean checkout
  magically contains QntyLab.

## Full offline suite

- Focused regression (9 files: `test_paper_pnl.py`,
  `test_funding_source_snapshot_schema.py`,
  `test_funding_source_digest_window_semantics.py`,
  `test_funding_source_immutable_bundle_semantics.py`,
  `test_paper_sqlite_writer.py`, `test_paper_sqlite_verify.py`,
  `test_paper_sqlite_verify_report.py`, `test_paper_matched_null.py`,
  `test_receipt_schema.py`): **413 passed**, 0 failures — unchanged from the
  prior integration receipt.
- Full offline suite (`QNTYLAB_ROOT` and `TMPDIR` unset, default
  `/tmp`-backed `tmp_path`): **7555 passed, 1 skipped, 0 failed**, exit 0,
  159.70s. Delta vs. the prior integration receipt's 7554 passed: +1 net
  (one non-portable test replaced by two hermetic tests), 0 new failures,
  0 new skips.

## Scope and non-claims

This repair proves the test suite is portable to a bare CI checkout. It
does not change, weaken, or re-verify: the economic formula, the claim
scope, account-posting status, or research-state policy of the underlying
fixture. It does not constitute a new profitability, alpha, or execution
claim.

## Commit

`test(paper): make public funding fixture CI-hermetic`

## Push

`git push origin feat/public-economic-fixture-v0-integration` (no
force-push).

## Final CI result

Recorded after push — see PR #326 status checks for the new head commit.

## Verdict

`PUBLIC_ECONOMIC_FIXTURE_V0_CI_HERMETICITY_REPAIRED`, pending
`QNTY_PR_326_ALL_REQUIRED_CHECKS_PASS` confirmation from the new head
commit's workflow runs.
