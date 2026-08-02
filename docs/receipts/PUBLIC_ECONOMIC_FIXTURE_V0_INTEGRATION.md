# Public economic fixture v0 — dedicated-branch integration receipt

**Task ID:** `PREPARE_DEDICATED_INTEGRATION_BRANCH_AND_CHERRY_PICK_V0`
(plus follow-on `REPAIR_WORKTREE_SAFE_QNTYLAB_SOURCE_RESOLUTION_V0`)

**Dedicated branch:** `feat/public-economic-fixture-v0-integration`
**Worktree:** `/home/swirky/DevHub/worktrees/Qnty-public-economic-fixture-v0`
**Target base branch:** `main`
**Target base commit:** `5cf88b93467e18be31158a58d0fc9fdee9a6b492`

## Commits

- Implementation (cherry-picked): `6d3d33e` — feat(paper): add public funding economic fixture
  (from `432d5326a7e0d63c704b170cf663d74929257df5`)
- Repair (cherry-picked): `252b463` — fix(paper): harden public funding fixture verification
  (from `45bda3eb037d34d324433c5da867d466386c00ba`)
- Worktree-path repair (this task): `b9a3722` — fix(paper): make funding fixture source resolution worktree-safe

## Baseline control-test / full-suite result

- Control test (`test_no_new_self_hash_source_binding_in_repo`) at base commit: **1 passed**.
- Full offline suite at base commit: **7493 passed, 1 skipped, 0 failed**, exit 0, 132.77s.

## Post-cherry-pick result (before worktree-path repair)

- Control test: **1 passed** — classification `BOTH_PASS`.
- Feature suite: 52 passed, 1 failed (`test_runnable_module_returns_bounded_verdict`,
  `SOURCE_FIXTURE_MISSING`, caused by a fixed-parent-depth path assumption that
  breaks under this dedicated worktree — see
  `docs/receipts/PUBLIC_ECONOMIC_FIXTURE_V0_WORKTREE_PATH_REPAIR.md`).
- Full offline suite: 7545 passed, 1 skipped, **1 failed** — one new failure,
  same test above. Verdict at that point: `BLOCKED_BY_FEATURE_TEST_FAILURE`.

## Post-repair result (final)

- Control test: **1 passed** — classification `BOTH_PASS`.
- Feature suite: **61 passed** (53 original + 8 new resolver tests).
- CLI verify (default worktree-aware fallback): `PUBLIC_ECONOMIC_FIXTURE_V0_VERIFIED`,
  byte-identical across two consecutive runs.
- Focused regression (9 files): **413 passed**.
- Full offline suite: **7554 passed, 1 skipped, 0 failed**, exit 0, 128.27s.
  Delta vs. base: +61 tests net (+8 new resolver tests, +1 previously-failing
  test now passing, +52 unaffected feature tests already counted at
  post-cherry-pick), 0 new failures, 0 new skips.

## Control-test differential classification

`BOTH_PASS` at every stage (base, post-cherry-pick, post-repair).

## Identity stability

- Receipt ID: `3833f2fb83a0c59031236cf5bb29b2de0ad2122765f03074f219a2c24bf5bd9b`
- Canonical receipt SHA-256: `d7a8827d8054ac2a843baf25dcc9dd547f4235ef10571e30d43cb69ef20b294f`
- Unchanged across implementation, repair, and worktree-path-repair commits.

## Scope verification

Changed paths across all three commits, confirmed via
`git diff --name-only 5cf88b9..HEAD`:

```
docs/receipts/PUBLIC_ECONOMIC_FIXTURE_V0_IMPLEMENTATION.md
docs/receipts/PUBLIC_ECONOMIC_FIXTURE_V0_REPAIR.md
docs/receipts/PUBLIC_ECONOMIC_FIXTURE_V0_WORKTREE_PATH_REPAIR.md
docs/receipts/PUBLIC_ECONOMIC_FIXTURE_V0_INTEGRATION.md
quantbot/paper/public_funding_economic_fixture.py
tests/fixtures/public_funding_economic_v0/expected_receipt.json
tests/fixtures/public_funding_economic_v0/input.json
tests/test_public_funding_economic_fixture_v0.py
```

No changes to `quantbot/paper/engine.py`, database schemas, strategy code,
network acquisition, or candidate/trial/decision registries.

## Concurrent-work isolation

- All commands this session ran with cwd inside
  `/home/swirky/DevHub/worktrees/Qnty-public-economic-fixture-v0`.
- The original worktree (`/home/swirky/DevHub/repos/Qnty`) was never used as
  a working directory, never staged, never modified by this session.
- No worktree-management operation (`add`/`remove`/`prune`/`unlock`) was
  performed.
- No branch used by another worktree was checked out here.
- No push occurred.

## Known non-blocking findings

- Unexpected non-forbidden fixture fields remain accepted.
- The batch verifier and broad reason enum may be reduced later.

(Not repaired in this task, per scope.)

## Integration verdict

`PUBLIC_ECONOMIC_FIXTURE_V0_INTEGRATED_ON_DEDICATED_BRANCH`

## Next action

`READY_FOR_QNTYLAB_RESEARCH_DIRECTION_DECISION`
