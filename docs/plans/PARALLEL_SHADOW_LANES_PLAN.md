# Parallel Shadow Lanes Plan

**Status:** DESIGN RECEIPT (docs-only). No code, DB, VM, systemd, or comparator
changes are made by this document. This records the agreed design for adding
*isolated* parallel paper/shadow lanes alongside the frozen production lane.

**Scope guardrails (this phase):**

- Documentation only — no source code changes.
- Production lane `paper_pnl_v1` must remain untouched.
- No DB mutation, no VM access, no systemd/timer changes.
- The null comparator is **not** run; V2 is **not** implemented.
- No live trading, no exchange keys, no real orders.
- **No edge or profitability claim is made or implied.** The strategy edge is
  `EDGE_UNPROVEN`.

---

## 1. Current baseline lane status

- **Lane:** `paper_pnl_v1`.
- **Health:** clean — verifier OK/trusted, funding coverage clean, git
  provenance complete.
- **Sample:** tiny (a handful of closed trades). Any result is statistically
  uninterpretable on its own.
- **Edge:** `EDGE_UNPROVEN`. A green paper result does **not** prove real-money
  profitability or deployment readiness.
- **Constraint:** `paper_pnl_v1` is frozen and **must remain untouched** by all
  future work described here (its output dir, DB, write-once config, verifier
  report, provenance, and systemd unit/timer stay byte-identical).

---

## 2. Architecture finding

**Lane locations are already environment-driven**, so a new lane needs no core
change merely to *locate* its files:

- `QNTY_PAPER_OUTPUT_DIR` — paper ledger output directory.
- `QNTY_PAPER_DB_PATH` — SQLite `paper_ledger.db` path.
- `QNTY_FORWARD_OBS_DIR` — read-only forward observer output directory.

**Gap:** the current DB/config identity does **not** carry first-class,
verifier-enforced fields for multi-lane operation. Identity today is expressed
through `baseline_label` + `config_hash` + `git_sha` + `forward_start_ts`. The
following are **missing** as first-class fields and must be added before lanes
can be told apart safely:

- `lane_id`
- `strategy_id`
- `strategy_version`
- `source_data_digest`

(Note: the live production accounting path is the **SQLite** path —
`paper_ledger.db` via the writer + read-only verifier. The legacy JSONL path is
the reference contract.)

---

## 3. Proposed future lanes

Two new lanes, each fully isolated from the baseline and from each other:

- **`paper_pnl_null_shadow`** — matched deterministic null comparator.
- **`paper_pnl_v2_volnorm_shadow`** — time-series momentum with inverse-vol /
  vol-normalized sizing, per-symbol cap, and portfolio heat cap.

Both are *shadow* lanes: simulation only, consuming the read-only observer
output. Neither places orders or requires exchange credentials.

---

## 4. Lane isolation rules

Each future lane must have its own, with **no shared output state**:

- separate output directory,
- separate DB (`paper_ledger.db`),
- separate write-once config,
- separate verifier report,
- separate provenance,
- eventually a separate systemd unit/timer (added only after offline
  validation; not in early phases).

Additional rules:

- Lane location is set **only** via the per-lane env profile
  (`QNTY_PAPER_OUTPUT_DIR` / `QNTY_PAPER_DB_PATH` / `QNTY_FORWARD_OBS_DIR`); no
  global default is changed.
- `lane_id` equals the output-directory leaf and the config's `lane_id`.
- A new lane must **not** reuse the baseline's `baseline_label`; the baseline
  engine's exact-match config contract must continue to reject any non-baseline
  config (and vice-versa).
- The `paper_config` singleton row and the `ledger_state` watermark are
  per-DB, so two lanes can never share a DB.
- **Baseline `paper_pnl_v1` is never touched.**

---

## 5. Null comparator design

The null is a fair, matched comparator — the only difference from the target
strategy is that signal selection/direction is randomized:

- **same bar clock** (8h grid, 00/08/16 UTC),
- **same universe**,
- **same number of active positions as the target strategy per bar**
  (cardinality-matched),
- **same fees / slippage / funding / fill model**,
- **same `forward_start_ts`** as the strategy it is paired with,
- selection/direction replaced by a **deterministic seeded PRNG**, with the
  seed and the consumed-input digest folded into each draw so the result is
  reproducible and divergence-checkable.

Sampling discipline:

- **One seed is only a plumbing/fixture test** — it proves the matched-null
  machinery works; it is **not** a comparison result.
- **Many seeds are required** to form an actual null distribution (e.g. a
  percentile of the strategy versus the spread of null draws).
- No profitability claim is made from any single seed or small sample.

---

## 6. V2 pre-registration fields

The following must be pre-registered (frozen) **before V2's first bar**. Exact
values are **not** selected in this docs-only phase; this records the required
field set only:

- lookback(s),
- vol estimator,
- vol window,
- threshold,
- per-symbol cap,
- portfolio heat cap,
- universe,
- rebalance clock,
- costs (fees, slippage, fill model),
- funding treatment,
- exit/hold rules,
- sizing rule (inverse-vol / vol-normalized, with cap application order).

Any change to any field after registration ⇒ a new `strategy_version` and a new
`config_hash` and a fresh lane init — never an in-place edit. No parameter may
be tuned from the current tiny sample.

---

## 7. Mandatory extra guard

Any future schema or config code change (even one intended only for the new
lanes) must **prove the baseline is unaffected** before it is accepted:

- existing `paper_pnl_v1` `config_hash` is **unchanged**,
- existing baseline verifier still **passes** (OK/trusted),
- existing baseline DB identity still **validates**,
- baseline systemd **unit/timer remains untouched**.

A change that cannot demonstrate all four is rejected.

---

## 8. Metrics every future lane must emit

Per batch and cumulative:

- equity,
- net PnL,
- realized / unrealized PnL,
- fees,
- funding,
- drawdown,
- turnover,
- exposure,
- open / closed trades,
- win / loss,
- average hold,
- per-symbol PnL,
- verifier status,
- git provenance,
- funding coverage.

Plus lane-identity stamping on every emission:

- `lane_id`,
- `strategy_id`,
- `strategy_version`,
- `config_hash`,
- `source_data_digest`.

A cross-lane reporter renders these side-by-side but emits **no** profitability
verdict on small samples.

---

## 9. Kill criteria

Any one of the following halts the lane / blocks an OK:

- verifier failure,
- missing / partial funding coverage,
- signal snapshot divergence,
- unprovenanced batch (no resolvable git SHA),
- DB integrity / reconcile failure,
- null comparator unavailable or untrusted (V2 results are uninterpretable
  without it),
- config / pre-registration hash mismatch,
- `source_data_digest` mismatch between paired lanes (inputs diverged),
- any pre-registered parameter changed mid-run,
- **no edge or profit claim is permitted below the pre-registered minimum
  sample size.**

---

## 10. Implementation phases

Minimal-first; each phase is independently reviewable and the early phases
require **zero** writes to any live DB:

1. **Docs-only design receipt** (this document).
2. **Offline null fixture** — pure, no live DB; validates matched-null logic,
   determinism, and metric emission.
3. **Lane config schema** — additive `lane_id` / `strategy_id` /
   `strategy_version` / `source_data_digest` fields and a lane registry;
   baseline config unchanged.
4. **Read-only cross-lane reporter** — reads each lane's artifacts read-only,
   renders side-by-side metrics and strategy-minus-null deltas; no writes.
5. **Offline shadow DB writer** — generalize the writer/engine to a
   non-baseline contract; stand up the new DBs offline and dry-run.
6. **Only later:** per-lane systemd units / timers, live seeds, multi-seed
   fan-out, and the actual comparator run (all out of scope here).

---

*This is a simulation design. Paper PnL is not live trading and does not prove
real-money profitability. The strategy edge remains `EDGE_UNPROVEN`.*
