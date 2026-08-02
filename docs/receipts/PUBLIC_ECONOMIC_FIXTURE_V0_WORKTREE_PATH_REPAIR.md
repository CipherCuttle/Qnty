# Public economic fixture v0 — worktree-safe source resolution repair

**Task ID:** `REPAIR_WORKTREE_SAFE_QNTYLAB_SOURCE_RESOLUTION_V0`
**Integration branch:** `feat/public-economic-fixture-v0-integration`
**Worktree:** `/home/swirky/DevHub/worktrees/Qnty-public-economic-fixture-v0`
**Starting HEAD:** `252b46397236abf43499b89acdb12dfb13d1af6a`

## Root cause

`quantbot/paper/public_funding_economic_fixture.py` located the sibling
`QntyLab` evidence checkout via:

```python
Path(__file__).resolve().parents[3] / "QntyLab"
```

This assumes the module always lives at a fixed depth under a directory whose
sibling is `QntyLab` (true only for `/home/swirky/DevHub/repos/Qnty`). Run
from a linked worktree (`/home/swirky/DevHub/worktrees/Qnty-public-economic-fixture-v0`),
`parents[3]` resolves to `.../worktrees` instead of `.../repos`, so the
sibling checkout was never found.

Failing derived path (before repair):
`/home/swirky/DevHub/worktrees/QntyLab/docs/forensics/evidence/binance_public_funding_event_v0/BTCUSDT-fundingRate-2026-06.raw.json`
→ `SOURCE_FIXTURE_MISSING`.

## Existing-convention check

Searched `docs/artifacts/` (`README.md`, `candidate1-real-input-v0.json`,
`stores.json`) and the repo for a reusable artifact-root/source-root
resolver. Classification: **ABSENT** — no general-purpose external-source
root resolver exists to reuse for this domain. One existing mechanism was
found and **REUSED**: the fixture module already exposed an explicit
`--source-root` CLI flag / `source_root` keyword argument on
`parse_fixture` / `verify_source_artifacts`. That flag already satisfies
tier 1 of the required precedence (explicit override), so no duplicate
`--qntylab-root` flag was added — extending the existing flag's backing
resolver was preferred over building a second CLI surface for the same
concept.

## Source-resolution contract (implemented in `resolve_source_root`)

1. Explicit argument — `--source-root` / `source_root=` kwarg (existing,
   reused). Invalid explicit path → `QNTYLAB_ROOT_INVALID`, no fallthrough.
2. `QNTYLAB_ROOT` environment variable. Invalid value → `QNTYLAB_ROOT_INVALID`,
   no fallthrough.
3. Existing canonical artifact-record resolver — **NOT_APPLICABLE** (absent).
4. Git-worktree-aware fallback: `git rev-parse --git-common-dir` run as a
   bounded subprocess (5s timeout, `check=False`, no traceback on failure)
   from the module's own directory; the *original* checkout's repo root is
   `git_common_dir.parent` (when it ends in `.git`), and the candidate is
   that root's parent joined with `QntyLab`. This resolves correctly both
   for the main checkout and for any linked worktree.
5. Ordinary sibling-checkout fallback relative to this repo's own root
   (`Path(__file__).resolve().parents[1].parent / "QntyLab"`), used only
   when Git is unavailable.

If both fallback candidates (4) and (5) exist as directories and differ,
resolution fails with `QNTYLAB_ROOT_AMBIGUOUS` rather than silently picking
one. No recursive filesystem or home-directory scanning is performed.

Evidence validation (SHA-256 hashes, selected-event identity, receipt
linkage, Decimal arithmetic, verification metadata) is unchanged — only
*how the root is located* changed.

## Explicit / environment / worktree-fallback verification

- Explicit `--source-root` (hermetic temp copy): CLI returns
  `PUBLIC_ECONOMIC_FIXTURE_V0_VERIFIED`, byte-identical across two runs.
- `QNTYLAB_ROOT` env var (hermetic temp copy): `parse_fixture` +
  `reconstruct_transfer` succeed, receipt ID unchanged.
- Explicit root overrides an invalid `QNTYLAB_ROOT` env value (no
  fallthrough attempted, override proven).
- Default resolution (no explicit arg, no env var) from this worktree:
  worktree-aware Git-common-dir fallback finds the real
  `/home/swirky/DevHub/repos/QntyLab` checkout and CLI verify succeeds.

## Hermetic test strategy

`tests/test_public_funding_economic_fixture_v0.py` no longer hardcodes
`/home/swirky/DevHub/repos/QntyLab`. A `_real_qntylab_root()` helper calls
the production `resolve_source_root()` instead, so the module-level
constant that previously hardcoded the absolute path is gone. New/adjusted
tests cover:

- `test_runnable_module_returns_bounded_verdict` — now hermetic via an
  explicit `--source-root` temp copy (no absolute-path dependence).
- `test_runnable_module_resolves_real_qntylab_checkout_from_worktree` — the
  required integration-level proof that the real local QntyLab checkout is
  found by default resolution from this isolated worktree.
- `test_env_root_succeeds`, `test_explicit_root_overrides_env_root`
- `test_invalid_explicit_root_fails`, `test_invalid_env_root_fails_without_fallthrough`
- `test_ambiguous_fallback_candidates_rejected` (monkeypatched candidates)
- `test_layout_sibling_fallback_used_when_worktree_candidate_absent`
- `test_receipt_identity_independent_of_source_root_location` — proves two
  different filesystem locations with identical evidence yield identical
  receipt bytes/IDs, and that the temp path string never appears in
  canonical receipt bytes.

## Changed paths

- `quantbot/paper/public_funding_economic_fixture.py`
- `tests/test_public_funding_economic_fixture_v0.py`
- `docs/receipts/PUBLIC_ECONOMIC_FIXTURE_V0_WORKTREE_PATH_REPAIR.md` (this file)

No changes to `tests/fixtures/public_funding_economic_v0/{input,expected_receipt}.json`,
`quantbot/paper/engine.py`, SQLite schemas, strategy code, network code, QntyLab
files, or candidate/trial/decision state.

## Identity stability

- Receipt ID: `3833f2fb83a0c59031236cf5bb29b2de0ad2122765f03074f219a2c24bf5bd9b` (unchanged)
- Canonical receipt SHA-256: `d7a8827d8054ac2a843baf25dcc9dd547f4235ef10571e30d43cb69ef20b294f` (unchanged)
- The absolute QntyLab root is not, and was never, a load-bearing identity
  field — confirmed structurally (never read into the receipt/identity
  payload) and by test (`test_receipt_identity_independent_of_source_root_location`).

## Test results

- Feature suite: `tests/test_public_funding_economic_fixture_v0.py` → **61 passed**
  (53 original + 8 new resolver tests).
- CLI verify: `PUBLIC_ECONOMIC_FIXTURE_V0_VERIFIED`, byte-identical across two
  consecutive runs, via the worktree-aware default fallback.
- Self-hash control (`test_no_new_self_hash_source_binding_in_repo`): 1 passed.
- Focused regression (9 files): **413 passed**.
- Full offline suite: **7554 passed, 1 skipped, 0 failed**, exit 0, 128.27s.
  (Baseline was 7493 passed/1 skipped/0 failed; delta is exactly +8 new
  resolver tests + the 1 previously-failing test now passing.)

## Scope and non-claims

This repair does not claim: real account posting, real position, real
trade, profitability, alpha, strategy validity, or production readiness.
It changes only how the QntyLab evidence root is located; source-hash,
event-identity, and receipt-linkage verification are unchanged and were
not weakened.

## Remaining minor findings (not repaired in this task)

- Unexpected non-forbidden fixture fields remain accepted.
- The batch verifier and broad reason enum may be reduced later.

## Verdict

`PUBLIC_ECONOMIC_FIXTURE_V0_WORKTREE_PATH_REPAIRED`

## Next action

Create the repair commit, then the integration receipt
(`docs/receipts/PUBLIC_ECONOMIC_FIXTURE_V0_INTEGRATION.md`), and report
`READY_FOR_QNTYLAB_RESEARCH_DIRECTION_DECISION`.
