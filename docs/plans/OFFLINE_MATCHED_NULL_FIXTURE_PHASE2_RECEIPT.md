# Offline Matched-Null Fixture — Phase 2 Receipt

Docs-only receipt for the Phase 2 work landed in commit
`ec7309b test: add offline matched null fixture`.

Reference plan: `PARALLEL_SHADOW_LANES_PLAN` §5 / §10.2.

---

## 1. Purpose

Phase 2 implemented **only** the offline matched-null fixture and its pure
selector. It is a **plumbing / fixture step, not a strategy result.** It wires a
deterministic, seeded, cardinality-matched random selector into the existing
paper accounting path so a future null comparison can be built on top of it. It
makes **no profitability or edge claim**.

## 2. Files added

- `quantbot/paper/null_comparator.py`
- `tests/test_paper_matched_null.py`

## 3. Files intentionally NOT changed

- `quantbot/lab/fixtures.py` (reused as-is; not modified)
- production runner / writer / verifier
- strategy modules
- systemd / ops files
- VM files
- production `paper_pnl_v1`

## 4. Selector design (`select_null_active`)

- Pure function: `select_null_active(universe, target_count, seed, bar_id)`.
- Hash-based deterministic ranking (SHA-256 over `"{seed}|{bar_id}|{symbol}"`).
- Stable under universe input ordering (`sorted(set(universe))` before drawing).
- Cardinality-matched: returns exactly `target_count` symbols.
- No duplicates (drawn from a de-duplicated candidate set).
- No out-of-universe symbols.
- `target_count == 0` returns an empty list.
- `target_count > universe size` raises `ValueError`.
- No I/O (no DB, no network, no clock, no file access — import-only).
- No prices, no PnL, no future bars, no outcomes consulted (no lookahead).
- Long-only, because the current production engine is long-only / fixed-notional
  and selection enters solely through `obs.active_symbols`. Direction
  randomization (shorts) is intentionally out of scope until the engine supports
  shorts.

## 5. Fixture design (`tests/test_paper_matched_null.py`)

- 4 fake symbols: `AAA` / `BBB` / `CCC` / `DDD`.
- Synthetic 8h bars on `fx.grid(N_BARS)` (`N_BARS = 6`; extra tail bars so T+1
  exit fills resolve within the window).
- Per-bar target active counts cover zero / one / multiple positions:
  `TARGET_COUNTS = [0, 1, 2, 1, 0, 0]`, unwinding so every opened position closes
  within the synthetic window.
- Zero-rate funding (`fundingRate = 0.0` for every `(symbol, bar)`): a funding
  event exists in each held interval, so `rate_available` is True and the accrued
  amount is exactly `0.0` — verifier-safe semantics, never a silently-missing gap.
- Null observations are fed through the existing `run_engine`
  (`quantbot/paper/engine.py`) so costs / fees / funding are applied through the
  same accounting path as the baseline engine.

## 6. Verified invariants

- Same seed gives identical selections.
- Same seed gives identical engine result digest.
- Different seed changes selection (and changes the engine digest).
- Cardinality match holds per bar.
- Zero target count produces zero selected symbols.
- Selected symbols are inside the universe.
- No duplicates.
- Future-bar perturbation does not affect current-bar selection (no lookahead).
- Engine applies costs / funding through the same path (entries are BUY fills
  carrying a taker fee; exits are SELL fills; funding rows present and available).
- No production paths referenced.
- No SQLite opened.
- No VM / systemd commands.

## 7. Verification results

- Focused matched-null test passed.
- Paper / SQLite regression set passed.
- Full suite via `.venv/bin/python -m pytest -q` passed: **1166 passed**.
- `git diff --check` clean.
- Forbidden-claims grep clean (no live-trading / profit / edge claims).
- Forbidden-infra grep clean (no production / VM path references).
- Note: bare `.venv/bin/pytest -q` has a pre-existing collection issue confirmed
  on clean `HEAD`, so the canonical full-suite command for this repo is
  `.venv/bin/python -m pytest -q`.

## 8. Scope exclusions

- No VM.
- No DB.
- No `/srv/qnty`.
- No systemd / timers / services.
- No production `paper_pnl_v1`.
- No V2.
- No lane config schema.
- No cross-lane reporter.
- No live trading / exchange keys / real orders.
- No profitability or edge claim.

## 9. Current verdict

`EDGE_UNPROVEN`

This fixture proves only null-selection **plumbing**, not strategy quality.

## 10. Next recommended phase

- Phase 3 should be **plan-only** lane config schema / lane identity design.
- No implementation until the plan is approved.
