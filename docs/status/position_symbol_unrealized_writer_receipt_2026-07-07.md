# QNTY Position Symbol Unrealized Writer Receipt — 2026-07-07

## Status Boundary

- `EDGE_UNPROVEN` remains in force.
- `BLOCK_LIVE_INTEGRATION` remains in force.
- Full-ledger `CAVEATED_ENGINE_SEMANTICS` remains in force.
- This receipt proves **only** post-fix writer behavior in throwaway SQLite DBs.
- This receipt does **not** prove edge, profitability, statistical significance,
  shorting readiness, live readiness, or production deployment.
- This receipt does **not** backfill historical prod/shadow rows.

## Scope

- Date: 2026-07-07.
- PR #87 merge SHA inspected: `c489e6cefc32e17b16100d3d0762cff34193c399`
  (`fix: populate per-symbol unrealized snapshot values`, state `MERGED`,
  merged 2026-07-06T23:05:51Z, base `main`).
- Local repo head at receipt authoring: `c489e6cefc32e17b16100d3d0762cff34193c399`
  (branch created from updated local `main`, itself fast-forwarded to
  `origin/main`).
- Branch name: `docs/position-symbol-unrealized-postfix-receipt`.
- Exact files changed by this receipt PR:
  - `docs/status/position_symbol_unrealized_writer_receipt_2026-07-07.md`
    (this file, added).
- No production code changes are made in this PR. This is a docs/receipt PR only.

`main` was confirmed to already include the fix artifacts before this receipt was
authored:

- `quantbot/paper/sqlite_writer.py`
- `tests/test_position_snapshot_symbol_unrealized_gross.py`

## Method

- Tests run (all via the repo `.venv` interpreter):
  1. `tests/test_position_snapshot_symbol_unrealized_gross.py` — the post-fix
     spec pinning per-symbol `unrealized_gross` semantics.
  2. `tests/test_paper_realized_attribution_reporter.py` — reporter regression.
  3. `tests/test_paper_sqlite_writer.py --collect-only` — writer collection
     sanity.
  4. A nearby writer subset (typed-row insert, equity balance, open-positions
     consistency).
- Tmp DB fixture method: the committed spec module builds each scenario
  end-to-end through the **real** writer (`run_sqlite_accounting`) against a
  throwaway SQLite DB under `tmp_path`. Only `load_config` and the writer clock
  (`_now`) are patched; the genuine OHLCV/funding/observation loaders read
  fixture CSVs written under the temp `data_dir`. `initialize_database` runs
  against the tmp DB only.
- Concrete post-fix numeric values below were extracted with a **read-only**
  helper under `/tmp` (`/tmp/qnty_receipt_evidence.py`) that imports the same
  committed spec fixture helpers, builds the same throwaway DBs under a
  `tempfile.TemporaryDirectory()`, opens each DB via `connect_readonly`, and
  dumps the stored values. The helper is temporary and is not part of this PR's
  changeset.
- Writer was invoked **only** against temporary SQLite DBs (pytest `tmp_path`
  and a `/tmp` temp dir).
- No prod/shadow writer run. No schema migration on any real DB. No deploy.
  No backfill. No dependency installation. No package-manager use.

## Post-Fix Evidence

All values are the **actual** stored figures observed in the throwaway DBs built
by the committed fixtures. Shared config: `notional_usd = 1000.0`,
`fee_bps = 5.0`, `slippage_bps = 5.0`, `initial_equity_usd = 10000.0`.
Per-symbol quantity is sized from notional (`qty ≈ notional / entry_price`).
The mark is the latest committed bar's close. `TOL = 1e-6`.

### Single Moved Long

- Symbol: `BTCUSDT`
- Entry price (stored `entry_price`): `140.07`
- Mark / current close price (latest committed bar): `100.0`
- Qty (stored): `7.1392874991`
- Expected formula: `unrealized = (mark - entry_price) * qty`
- Expected unrealized: `(100.0 - 140.07) * 7.1392874991 = -286.07125009`
- Stored `position_snapshot_symbols.unrealized_gross`: `-286.07125009`
- Ledger-level `equity_snapshots.unrealized_pnl`: `-286.07125009`
- Absolute diff (per-symbol vs ledger): `0.0`
- Verdict: `SINGLE_SYMBOL_UNREALIZED_MATCH`

### Multi-Symbol Open Positions

Two independent open longs on identical rising grids.

| Symbol   | Qty          | Entry price | Mark  | Expected unrealized | Stored `unrealized_gross` |
|----------|--------------|-------------|-------|---------------------|---------------------------|
| BTCUSDT  | 7.1392874991 | 140.07      | 100.0 | -286.07125009       | -286.07125009             |
| ETHUSDT  | 7.1392874991 | 140.07      | 100.0 | -286.07125009       | -286.07125009             |

- Per-symbol sum: `-286.07125009 + -286.07125009 = -572.14250018`
- Ledger-level `equity_snapshots.unrealized_pnl`: `-572.14250018`
- Absolute diff (sum vs ledger): `0.0`
- Verdict: `MULTI_SYMBOL_UNREALIZED_SUM_MATCH`

### Flat Control

Mark equals entry fill (long fills at `open * (1 + 5bps)`; close held at that
fill), so a genuine `0.0` unrealized — not a writer that failed to populate.

- Symbol: `BTCUSDT`
- Entry price (stored `entry_price`): `100.05`
- Mark / current close price: `100.05`
- Qty (stored): `9.9950024988`
- Stored `position_snapshot_symbols.unrealized_gross`: `0.0`
- Ledger-level `equity_snapshots.unrealized_pnl`: `0.0`
- Absolute diff: `0.0`
- Verdict: `FLAT_POSITION_ZERO_UNREALIZED_CONFIRMED`

## Test Results

Exact commands and observed results:

- Position symbol unrealized spec:
  `.venv/bin/python -m pytest tests/test_position_snapshot_symbol_unrealized_gross.py`
  → **`4 passed`** (no xfails).
- Reporter regression:
  `.venv/bin/python -m pytest tests/test_paper_realized_attribution_reporter.py`
  → **`16 passed`**.
- Writer collect-only:
  `.venv/bin/python -m pytest tests/test_paper_sqlite_writer.py --collect-only`
  → **`45 tests collected`**, collection succeeds.
- Nearby writer subset:
  `.venv/bin/python -m pytest tests/test_paper_sqlite_writer.py::TestFirstSuccessfulBatch::test_typed_rows_inserted tests/test_paper_sqlite_writer.py::TestEquityArithmetic::test_equity_balance tests/test_paper_sqlite_writer.py::TestStateAndOpenPositions::test_open_positions_consistent`
  → **`3 passed`**.

The full `tests/test_paper_sqlite_writer.py` file was **not** run in full; only
the collection sanity and the named subset above were executed. No unrelated
fixture failures were relied on as proof for this receipt.

## Prod/Shadow Ledger Boundary

- Prod/shadow DBs were **not** mutated.
- No backfill was performed.
- Existing historical rows may still carry
  `position_snapshot_symbols.unrealized_gross = 0.0` — the fix is forward-looking
  for batches written by the fixed writer.
- Future batches generated by the fixed writer should populate the field
  per-symbol as evidenced above.
- Any production deployment, production writer run, or backfill requires a
  separate, explicit task.

Prod/shadow read-only integrity hashes were **not** collected for this receipt;
the VM/prod/shadow DBs were not accessed at all. Accordingly:

- Prod/shadow DBs were not opened.
- Prod/shadow DBs were not mutated.
- No deployment happened.
- No backfill happened.
- Therefore this receipt proves only new writer behavior in throwaway DBs, not
  historical ledger repair.

Verdict: `PROD_SHADOW_NOT_ACCESSED_BY_THIS_RECEIPT`

## Impact On Existing Receipts

- PR #82 manual realized attribution snapshot remains valid.
- PR #84 reporter parity remains valid (reporter regression still `16 passed`).
- PR #85 diagnosis remains valid — it correctly identified the
  `unrealized_gross = 0.0` gap that PR #87 subsequently closed.
- PR #86 xfail spec was satisfied by PR #87; the spec now passes `4 passed` with
  no xfails.
- Existing prod/shadow historical DB rows are not retroactively changed by this
  receipt.
- No edge-status change: `EDGE_UNPROVEN` is preserved.

## Non-Goals

- No code change.
- No test change.
- No schema change.
- No verifier change.
- No reporter change.
- No trader change.
- No DB writes except tmp fixtures.
- No prod/shadow writer run.
- No deployment.
- No backfill.
- No live integration.
- No shorting.
- No trial registry change.
- No null/benchmark lane changes.

## Verdict

`POSITION_SYMBOL_UNREALIZED_POSTFIX_RECEIPT_RECORDED`
