# QNTY Fast Truth Lab — v0 (implementation-truth only)

> **Scope contract.** This lab raises trust in the *implementation* of the paper witness.
> It does **not** test, measure, or imply any **strategy edge / profitability**. Nothing here
> is live-trading approval. PASS means "the witness is harder to fool," never "the strategy
> works."

QNTY runs in clean forward **Paper PnL observation mode**. The read-only verifier re-derives
invariants **from the SQLite DB, not from source OHLCV** (`VERIFIER_DISCLAIMER`,
`quantbot/paper/sqlite_verify.py`). So a bug in the paper engine gets baked into the ledger
and then *re-validated cleanly* by the verifier. Closing that blind spot is this lab's job:
re-derive marks / unrealized PnL / fees / funding / exposure / equity **independently from
source inputs** and compare to the engine, plus targeted adversarial falsifiers around the
known off-by-one / path-dependence / open-candle hazards.

The lab is **additive and import-only**. It never touches systemd, the live paper DB, or
`/srv/qnty/output`. Every artifact it writes lands under `output/lab/` (gitignored).

## Lanes

| Lane | Authority | Meaning |
|---|---|---|
| `FORWARD` | **authoritative** | the production paper engine / ledger (NOT in `quantbot/lab/`) |
| `REPLAY` | diagnostic | independent zero-dep re-derive (`quantbot/lab/replay_engine.py`) |
| `ADVERSARIAL` | diagnostic | property/falsifier tests (`tests/lab/test_*`) |
| `CROSS_CHECK` | diagnostic | engine-vs-replay row diff + classifier (`quantbot/lab/cross_check.py`) |

The diagnostic lanes can only **raise** witness trust or **halt** on a real defect. They make
no edge claim either way.

## Verdict semantics

- **PASS** — falsifiers pass and cross-check is CLEAN ⇒ witness harder to fool.
- **FAIL** — a falsifier fails or a disagreement indicates the witness is wrong ⇒ stop & fix.
- **INCONCLUSIVE** — a disagreement needs triage (checker bug / spec ambiguity) ⇒ no edge claim.

## Falsifiers (ranked by bug-killing power)

- **T4 — Independent replay / CROSS_CHECK** (`tests/lab/test_replay_cross_check.py`).
  Re-derives the ledger from `per_bar_obs` + OHLCV + funding and diffs it row-by-row against
  `quantbot.paper.engine.run_engine`. Directly attacks the verifier's DB-only blind spot.
- **T1 — Startup-window invariance** (`tests/lab/test_startup_window_invariance.py`).
  Property: `VolatilityTracker` state/output depends only on the final bounded window, never on
  an evicted prefix. Kills regressions of the production `2e903… → 46640…` eviction bug class.
- **T2 — Open-candle rejection** (`tests/lab/test_open_candle_rejection.py`).
  A not-yet-closed 8h candle must be excluded by `filter_closed_bars`, never published by the
  observer, and never decided on by any lab/paper flow (it may only be a T+1 fill source).
- **T3 — `forward_start_ts` boundary** (`tests/lab/test_forward_start_boundary.py`).
  The boundary bar (naive **and** trailing-`Z` forms) commits exactly once — never skipped,
  never duplicated — and reruns are idempotent.
- **T5 — Disagreement classifier** (in `test_replay_cross_check.py`).
  A cross-check disagreement is a *measured quantity*, triaged into one of four classes and
  **never auto-blamed on QNTY**.

## Disagreement classes (T5)

| Class | When |
|---|---|
| `TIMESTAMP_FILL_COST_MISMATCH` | diff on a fill/cost/timing field (open/fill price, qty, fee, fill_ts, exposure) |
| `SPEC_AMBIGUITY` | funding-interval / definitional diff, or both sides internally self-consistent but differing |
| `CHECKER_BUG_CANDIDATE` | the **replay's** equity is internally inconsistent (the checker's own math is suspect) |
| `QNTY_BUG_CANDIDATE` | the **production** equity is internally inconsistent while the replay's is consistent |

The internal-consistency test is the documented identity
`equity == initial + realized_gross − fees − funding + unrealized`. The default class is
**never** `QNTY_BUG_CANDIDATE`: a red alert must be triaged, not auto-blamed.

## Re-derived spec (must match the production contract)

- `active_symbols` at bar `T` = desired long set; entries/exits vs the open book.
- Fill at **T+1 open** (pessimistic); **all-or-nothing** deferral if any acted-on symbol lacks a T+1 open.
- entry fill `= open·(1+slip)`, exit fill `= open·(1−slip)`; `qty = notional / entry_fill_price`.
- `fee = fill_price · qty · fee_rate`.
- funding accrued over the **actual held interval** (entry fill → exit fill), summing every event in `(start_exclusive, end_inclusive]`; long pays when `rate > 0`.
- unrealized marked at bar-`T` close; `gross_exposure = Σ qty·close`.
- `equity = initial + realized_gross − fees_cum − funding_cum + unrealized`.

## Run instructions

Pre-flight (read-only FORWARD baseline — **no mutation**):

```bash
python scripts/qnty-paper-sqlite-verify.py --db-path "$QNTY_PAPER_DB_PATH" --no-emit --json
```

Falsifiers, priority order, **stop on first failure**:

```bash
pytest tests/lab/test_startup_window_invariance.py -x -q   # T1
pytest tests/lab/test_open_candle_rejection.py     -x -q   # T2
pytest tests/lab/test_forward_start_boundary.py    -x -q   # T3
pytest tests/lab/test_replay_cross_check.py        -x -q   # T4 + T5
```

Cross-check on a recorded observer bundle (writes only under `output/lab/`):

```bash
python -m quantbot.lab.cross_check \
  --obs-fixture tests/lab/fixtures/recorded_obs.json \
  --out output/lab/cross_check --json
```

Regression guard (full suite stays green):

```bash
pytest -q
```

## Hard constraints (non-negotiable)

No live trading; no exchange keys; no VM/systemd/DB mutation; no writes into
`/srv/qnty/output/paper_pnl_v1`; never reset the clean DB; never delete archived contaminated
output; no new heavy dependency (no vectorbt); additive files only (no edits under
`quantbot/paper/`, `ops/`, `/srv/`); never call anything profitable; **stop on first failure**.
DSR/PBO/MinTRL forward edge inference is explicitly **deferred** — strategy-edge, not witness
trust.
