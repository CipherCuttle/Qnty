# QNTY Realized Attribution And Shorting Research Foundation

**Type:** docs-only build plan (no code changes proposed by this document)
**Date:** 2026-07-06
**Strategy label:** `EDGE_UNPROVEN` — no profitability or edge claim is made anywhere in this document.
**Live status:** `BLOCK_LIVE_INTEGRATION` — live trading integration remains blocked.
**Full-ledger accounting label:** `CAVEATED_ENGINE_SEMANTICS` — unchanged by this plan.

---

## Status Boundary

These labels are preserved, not weakened, by everything in this plan:

- `EDGE_UNPROVEN` remains. Nothing here claims, implies, or is designed to
  manufacture an edge claim.
- `BLOCK_LIVE_INTEGRATION` remains. No live exchange integration, no live
  capital, no live-readiness implication. (Note: this label is currently an
  audit-conversation convention; it does not yet appear as a string in the
  tracked repo. The first PR below gives it a canonical repo home so it can be
  cited instead of re-asserted.)
- Full-ledger `CAVEATED_ENGINE_SEMANTICS` remains. The batch-scoped
  clean-carry verifier (PR #77, `docs/plans/QNTY_BATCH_SCOPED_CLEAN_CARRY_VERIFIER_PLAN.md`)
  can stamp the *latest batch* `CLEAN_NET_OF_CARRY`; it explicitly does not and
  must not relabel the full historical ledger.
- Batch-scoped cleanliness is **evidence quality**, not edge. A batch labeled
  `CLEAN_NET_OF_CARRY` means the accounting arithmetic, funding coverage, and
  DB-linked source snapshot for that batch check out. It says nothing about
  whether the strategy makes money.
- The current paper gain is **not** sufficient evidence for shorting, for
  sizing up, or for live trading. It is mostly unrealized long exposure in a
  single window, with negative realized gross PnL (see next section).

---

## Why This Plan Exists

Recent audits (watermark `2026-07-05T16:00:00`; prod batch 46, shadow batch 17,
both latest batches batch-scoped `CLEAN_NET_OF_CARRY`) established the
following facts:

1. **Green equity is mostly unrealized long exposure.** The equity curve is up,
   but the gain lives in `unrealized_pnl` on open long positions, not in
   `realized_gross_pnl` on closed trades.
2. **Realized gross PnL is negative.** The closed-trade record — the only part
   of the ledger that reflects completed round-trips through the fill model,
   fees, and funding — has lost money so far.
3. **There is no canonical artifact stating this.** The facts above live in
   audit conversations and ad-hoc queries. The repo has a verifier
   (`quantbot/paper/sqlite_verify.py`) that proves arithmetic consistency, but
   no spec that defines *realized attribution* as a first-class, receipt-backed
   status: what QNTY has actually earned in realized terms, net of funding and
   fees, over how many closed trades.
4. **Shorting cannot be honestly motivated without that artifact.** A shorting
   hypothesis of the form "harvest positive funding while short in downtrends"
   is a claim about improving *realized, net-of-carry* PnL. If the current
   long-only realized record is undocumented, any short-side motivation is
   built on the unrealized mark — exactly the number Perold (1988) warns is a
   paper return, not a captured one.
5. **The current shadow lane is a replication/identity control, not an alpha
   null.** Prod and shadow behave identically over the overlapping window; the
   shadow proves the plumbing is deterministic and reproducible
   (cf. `docs/plans/QNTY_V1_SHADOW_ASSERTED_IDENTITY_PNL_RECONCILIATION_AFTER_BATCH11.md`),
   but it cannot tell us whether the strategy beats a matched null. A true
   null lane is future work, gated behind the preregistered experiment plan
   (third PR below).
6. **Recent engineering went into evidence plumbing, not the trader.** PRs
   #73–#77 changed the verifier, source-path resolution, and batch-scoped
   clean-carry stamping. Trader/decision/signal logic is unchanged. The
   natural next increment is therefore *more evidence discipline* — a realized
   attribution spec — not new trading behavior.

The correct order is: **document what is real (realized attribution) → state
what is hypothesized (shorting v3) → prereg how it would be tested (forward
experiment plan)**. This document plans exactly those three docs-only steps.

---

## Forensic Repo Map

All paths verified read-only at HEAD `2bd8843`. Nothing below was modified.

### Paper ledger schema (where the numbers live)

- `quantbot/paper/db.py` — canonical SQLite DDL (STRICT tables, append-only
  triggers). Tables: `paper_config`, `ledger_batches`, `ledger_events`,
  `signal_snapshots`, `fills`, `trades`, `funding`, `position_snapshots`,
  `position_snapshot_symbols`, `equity_snapshots`, `ledger_state` (mutable
  singleton), `open_positions` (mutable).
  - `trades` carries per-round-trip `gross_pnl`, `fees`, `funding`, `net_pnl`,
    `hold_bars` — realized attribution per closed trade already exists at row
    level.
  - `equity_snapshots` carries per-bar `realized_gross_pnl`, `unrealized_pnl`,
    `funding_cum`, `fees_cum`, `equity`, `drawdown`, `num_open`.
  - `ledger_state` carries cumulative `realized_gross`, `fees_cum`,
    `funding_cum`, `peak_equity`, `watermark_bar_ts`.
  - `open_positions` carries `entry_price`, `qty`, `entry_fee`,
    `funding_accrued`, `hold_bars` per open symbol.
- `docs/paper_pnl_v1_schema.md` — canonical schema/semantics doc. §3.2 defines
  the equity identity (no double counting); §5a defines the authority model
  (the verifier verifies a frozen snapshot, never live files).

### Writer (where the ledger is produced)

- `quantbot/paper/sqlite_writer.py` — single `BEGIN IMMEDIATE` transaction per
  batch; full replay reconciliation before commit. The accounting identity is
  enforced at `quantbot/paper/sqlite_writer.py:913-919`:

  ```
  equity = initial_equity + realized_gross_pnl - fees_cum - funding_cum + unrealized_pnl
  ```

  with absolute tolerance `1e-6`. Note the sign convention: `funding_cum` and
  `fees_cum` are stored as accumulated *costs* and subtracted.
- `quantbot/paper/engine.py` — deterministic paper engine. **Long-only:** the
  only fill sides are `BUY` (entry) and `SELL` (exit)
  (`quantbot/paper/engine.py:373`, `:428`). There is no short-side code path.
- `scripts/qnty-paper-sqlite-accounting.py` — writer entrypoint. Exit codes:
  0 OK, 2 ABORTED, 3 CONFIG_ERROR, 4 CORRUPT_LEDGER, 5 PRE_START,
  6 LEDGER_BUSY. Its docstring states writer exit codes are runner status
  only; trust comes from the verifier report.
- Supporting modules: `quantbot/paper/ledger.py`, `reconcile.py`,
  `snapshots.py`, `freshness.py`, `runner.py`.

### Verifier (where trust is stamped)

- `quantbot/paper/sqlite_verify.py` — the authority. Absolute tolerance
  `_ABS_TOL = 1e-6` (`:198`). Validates schema presence, config/lane identity,
  event chain, batches, arithmetic, trades, cumulative equity, ledger state,
  open positions, snapshot identity, foreign keys.
  - Funding clean-carry stamping: `CLEAN_NET_OF_CARRY` vs
    `CAVEATED_ENGINE_SEMANTICS`, fail-closed on digest mismatch or missing
    DB-linked snapshot (sha256 file + bundle digests).
  - Deterministic source-path resolution (PR #75) with
    `source_path_unavailable` fail-closed reason.
  - Batch-scoped clean-carry (PR #77): separate report fields
    `funding_clean_carry_batch_decision`, `funding_clean_carry_batch_status`,
    `funding_clean_carry_batch_reason_codes`, `funding_clean_carry_batch` —
    scoped to the latest batch only, never relabeling the full ledger
    (contract in `tests/test_paper_sqlite_verify_batch_scoped_clean_carry.py`).
- `scripts/qnty-paper-sqlite-verify.py` — verifier entrypoint.
- `quantbot/paper/funding_coverage.py`, `funding_source_snapshot.py`,
  `funding_status.py`, `funding_time.py` — funding coverage decision, source
  snapshot digesting, interval math.
- `quantbot/paper/lane_identity.py`, `lane_config_hash.py`, `lane_init.py`,
  `provenance.py`, `config.py` — lane identity model, `config_hash_v2`,
  output-dir/lane resolution (`paper_output_dir()`; env override
  `QNTY_PAPER_OUTPUT_DIR`).
- `quantbot/sidecars/ledger_ro.py` — read-only ledger sidecar (useful pattern
  for the read-only status queries the first PR will specify).

### Status/inspection scripts

- `scripts/paper_verify.py`, `scripts/paper_reconcile.py`,
  `scripts/health_receipt.py` — existing read/report tooling.
- **Absent:** there is no script or doc that prints a *realized attribution*
  summary (realized vs unrealized split, N_closed, funding/fees decomposition).
  That gap is exactly what the first PR specifies (as a spec; any script is a
  later, separate decision).

### Null/experiment infrastructure

- `quantbot/paper/null_comparator.py` — offline matched-null comparison
  fixture (`docs/plans/OFFLINE_MATCHED_NULL_FIXTURE_PHASE2_RECEIPT.md`).
- `quantbot/experiment/pbo.py` — **explicitly a proxy diagnostic, not
  Bailey-style CSCV/PBO** (its own docstring says so). Honest labeling already
  in place; the real CSCV requirement belongs in the preregistered experiment
  plan, not here.
- `quantbot/experiment/gates.py`, `walkforward.py`, `calibration.py` —
  backtest experiment framework (not the paper lane).

### Docs and status language

- `docs/CURRENT_STATE.md` and `docs/verdicts/CURRENT_QNTY_STATE.md` — current
  top-level status ("shadow-only", "live capital: not authorized").
- `docs/plans/` — receipts and plans for the shadow lane (batches 2–14
  receipts), DB-linked snapshots, funding determinism, clean-carry repair,
  batch-scoped clean-carry verifier.
- `docs/experiments/` — evidence packs and receipts carrying `EDGE_UNPROVEN`.
- **Absent:** `docs/status/` does not exist. The first PR creates it. No
  shorting docs exist anywhere in the repo. No preregistered forward
  experiment plan exists (the closest are the walkforward/experiment framework
  docs, which target backtests, not the forward paper lane).

### Tests relevant to this plan's subject matter

- `tests/test_paper_sqlite_verify_batch_scoped_clean_carry.py` (batch-scope contract)
- `tests/test_paper_sqlite_funding_coverage.py`, `tests/test_paper_sqlite_writer_funding_fail_closed_proof.py`
- `tests/test_paper_sqlite.py`, `tests/test_paper_sqlite_verify.py`, `tests/test_paper_sqlite_verify_report.py`
- `tests/test_paper_verify_lane_identity.py`, `tests/test_paper_ledger_batch_lane_stamping.py`

---

## Literature Review

Sources verified by web search on 2026-07-06.

### 1. Statistical edge validation and the insufficiency of tiny samples

Bailey & López de Prado's Probabilistic Sharpe Ratio / **Minimum Track Record
Length** framework ("The Sharpe Ratio Efficient Frontier," *Journal of Risk*
15(2), 2012; exposition in ["Deflating the Sharpe Ratio"](http://boston.qwafafew.org/wp-content/uploads/sites/4/2017/01/Lopez_de_Prado_Sharpe.pdf))
formalizes the minimum number of observations needed before a Sharpe estimate
is statistically distinguishable from zero at a given confidence, accounting
for skew and kurtosis. QNTY's realized record — a small `N_closed` of trades
with negative realized gross PnL — is far below any plausible MinTRL. The
first artifact must therefore *report N_closed explicitly* so that every
future claim can be checked against a sample-size floor rather than against
the visual impression of an equity curve.

### 2. Backtest overfitting, multiple testing, DSR and PBO

- Bailey & López de Prado, ["The Deflated Sharpe Ratio: Correcting for Selection Bias, Backtest Overfitting and Non-Normality"](https://papers.ssrn.com/sol3/papers.cfm?abstract_id=2460551),
  *Journal of Portfolio Management* 40(5), 2014 ([PDF](https://www.davidhbailey.com/dhbpapers/deflated-sharpe.pdf)):
  observed Sharpe ratios must be deflated by the number of trials that
  produced them; a single lane's green curve after many prior strategy
  iterations (QNTY's `docs/verdicts/` history shows many) is inflated by
  selection.
- Bailey, Borwein, López de Prado & Zhu, ["The Probability of Backtest Overfitting"](https://papers.ssrn.com/sol3/papers.cfm?abstract_id=2326253),
  *Journal of Computational Finance* 20(4), 2017 ([PDF](https://www.davidhbailey.com/dhbpapers/backtest-prob.pdf)):
  CSCV estimates the probability that the selected strategy's in-sample rank
  does not survive out-of-sample. Note: `quantbot/experiment/pbo.py` honestly
  documents itself as a proxy, *not* CSCV — so QNTY currently has **no**
  canonical PBO estimate, another reason no edge claim is possible.
- White, "A Reality Check for Data Snooping," *Econometrica* 68(5), 2000, and
  Hansen, "A Test for Superior Predictive Ability," *Journal of Business &
  Economic Statistics* 23(4), 2005 (survey of both in
  [Hybrid test literature](https://arxiv.org/pdf/2008.02318)): when many rules
  are searched, the best one must be tested against the full search universe
  via bootstrap; Hansen's SPA re-centers White's conservative null. The
  preregistered experiment plan (third PR) must count trials for exactly this
  reason — a trial registry is the input a Reality-Check-style correction
  needs.
- López de Prado, *Advances in Financial Machine Learning* (Wiley, 2018),
  ch. 7 ([purged K-fold CV with embargo](https://en.wikipedia.org/wiki/Purged_cross-validation)):
  overlapping/leaking samples inflate performance; forward paper evaluation
  windows must be non-overlapping and embargoed against label leakage.

### 3. Execution realism and implementation shortfall

- Perold, "The Implementation Shortfall: Paper Versus Reality," *Journal of
  Portfolio Management* 14(3), 1988: the gap between paper returns and
  captured returns is the central measurement problem. QNTY's situation is a
  textbook instance — the "gain" is a paper mark on open positions; the
  *realized* record is what implementation has actually captured, and it is
  negative. The realized attribution spec is, in Perold's terms, the document
  that separates paper from reality inside a paper system.
- Almgren & Chriss, "Optimal Execution of Portfolio Transactions," *Journal of
  Risk* 3(2), 2000/2001: execution cost has permanent and temporary impact
  components plus risk; any future short-side design must budget for costs
  beyond the current `next_bar_open_pessimistic` fill model, and the
  cost-stress section of the shorting hypothesis doc must stress fills, not
  just fees.

### 4. Crypto perpetual funding — why shorting is not just negative longing

- He, Manela, Ross & von Wachter, ["Fundamentals of Perpetual Futures"](https://arxiv.org/abs/2212.06888)
  (SSRN 4301150): derives no-arbitrage perp pricing; funding is the mechanism
  tying perp to spot, deviations in crypto are large and time-varying. A short
  position's carry is the *time-varying* funding stream, not a constant.
- Ackerer, Hugonnier & Jermann, ["Perpetual Futures Pricing"](https://www.nber.org/system/files/working_papers/w32936/w32936.pdf)
  (NBER w32936): funding-rate specification drives the perp–spot spread;
  regime changes in funding flip the sign of short carry.
- [Binance funding rate documentation](https://www.binance.com/en/support/faq/detail/360033525031)
  and [funding history API](https://developers.binance.com/docs/derivatives/coin-margined-futures/market-data/rest-api/Get-Funding-Rate-History-of-Perpetual-Futures):
  8h intervals, premium index + clamped interest-rate component; positive
  funding pays shorts, negative funding *charges* shorts. Asymmetries a short
  book faces that a long book does not: unbounded upside loss, forced-buy-in
  dynamics (squeezes), funding sign flips in exactly the downtrends the
  strategy would target, and exchange-specific clamps/caps on funding.
- QNTY-specific: the `funding` table already records signed
  `funding_amount` per held interval for longs; the semantics of that sign
  convention for a hypothetical short must be *defined on paper first* —
  which is precisely the shorting v3 hypothesis doc's job.

### 5. Risk sizing — why `EDGE_UNPROVEN` means zero live allocation

Thorp, ["The Kelly Criterion in Blackjack, Sports Betting, and the Stock Market"](https://gwern.net/doc/statistics/decision/2006-thorp.pdf),
*Handbook of Asset and Liability Management* vol. 1, 2006: Kelly sizing is a
function of edge; with edge unknown or ≤ 0, the growth-optimal allocation is
**zero**, and overbetting relative to true (not estimated) edge produces
ruin-bound dynamics. This is cited strictly as a risk-management bound: an
`EDGE_UNPROVEN` label implies the only defensible live allocation is zero,
which is exactly what `BLOCK_LIVE_INTEGRATION` encodes. It is *not* a sizing
justification for any future allocation.

---

## Five-Methodology Diagnosis

### 1. Statistical edge validation

- **Current diagnosis:** realized sample is tiny and realized gross PnL is
  negative; total equity gain is dominated by an unrealized mark on open
  longs. No Sharpe, PSR, or MinTRL computation on realized returns exists in
  the repo.
- **Required guardrail:** every status artifact must report `N_closed` and
  must state that no statistic computed on fewer trades than a stated MinTRL
  threshold can support an edge claim.
- **First repo artifact needed:** `docs/status/realized_attribution_spec.md`
  (first PR) — defines the realized quantities and requires `N_closed` in
  every output.
- **What would be misleading:** quoting the equity curve or total return
  (unrealized-dominated) as "performance"; computing a Sharpe on marks rather
  than on realized round-trips.

### 2. Backtest / overfitting control

- **Current diagnosis:** many historical strategy iterations exist in
  `docs/verdicts/`; `quantbot/experiment/pbo.py` is a self-declared proxy,
  not CSCV; there is no trial registry, so no DSR-style deflation is possible.
- **Required guardrail:** a trial registry must exist before any forward
  window is scored; the shorting hypothesis must be preregistered *before*
  any short-capable code exists, so the hypothesis can't be tuned to data
  already seen.
- **First repo artifact needed:** the preregistered forward experiment plan
  (third PR) with an explicit trial-count/registry requirement.
- **What would be misleading:** treating the current green window as a
  successful "test" of the strategy; silently iterating hypotheses and
  reporting only the survivor.

### 3. Market microstructure / crypto-perp execution

- **Current diagnosis:** fills are `next_bar_open_pessimistic`
  (`docs/paper_pnl_v1_schema.md` §2); funding accrual uses actual funding rows
  over held intervals; the engine is long-only with no short-side fill,
  margin, or liquidation semantics at all.
- **Required guardrail:** short-side semantics (fill model, funding sign,
  margin/liquidation proxy, squeeze stress) must be specified on paper and
  cost-stressed before any code; funding coverage must remain fail-closed.
- **First repo artifact needed:** the shorting v3 hypothesis doc (second PR)
  with explicit cost-stress and squeeze-risk sections.
- **What would be misleading:** modeling a short as a sign-flipped long —
  ignoring funding sign flips, borrow/margin asymmetry, and unbounded-loss
  geometry.

### 4. Experimental design / null models

- **Current diagnosis:** the shadow lane is an identity/replication control
  (proves determinism and plumbing), not an alpha null; the offline matched
  null exists only as a fixture (`null_comparator.py`). No preregistered
  forward experiment with kill criteria exists.
- **Required guardrail:** any claim of edge must be relative to a matched
  null lane over a preregistered horizon with preregistered kill criteria;
  logic changes reset the window.
- **First repo artifact needed:** the preregistered forward experiment plan
  (third PR).
- **What would be misleading:** citing prod/shadow agreement as evidence of
  edge (it is evidence of *reproducibility*); moving goalposts mid-window.

### 5. Risk management / portfolio construction

- **Current diagnosis:** paper-only, fixed-notional baseline lane; live
  capital not authorized (`docs/CURRENT_STATE.md`); no sizing framework is
  needed yet because no allocation decision is on the table.
- **Required guardrail:** `EDGE_UNPROVEN` ⇒ zero live allocation (Kelly bound
  with unknown/non-positive edge); no leverage discussion until edge is
  established, which is not in scope for any of the three PRs.
- **First repo artifact needed:** the Status Boundary section of the realized
  attribution spec, restating the zero-allocation implication in a canonical
  place.
- **What would be misleading:** any "if it keeps this up, size X would
  yield Y" extrapolation; treating unrealized gains as a risk buffer.

---

## Correct Build Sequence

Exactly three near-term steps, in order. Each is docs-only.

1. **`docs: add realized attribution status spec`** — canonical definitions
   and reporting requirements for realized vs unrealized attribution
   (detailed plan below).
2. **`docs: add shorting v3 research hypothesis`** — preregistered hypothesis
   `short_v3_carry_harvest_downtrend`, paper-only, no code (sketch below).
3. **`docs: add preregistered forward experiment plan`** — frozen-logic
   forward test design with nulls, horizon, and kill criteria (sketch below).

**Later, not now** (explicitly out of the near-term sequence): a read-only
realized-attribution reporting script; a true CSCV/PBO implementation
replacing the proxy in `quantbot/experiment/pbo.py`; a matched alpha-null
lane; any short-capable engine code; any verifier extension. None of these
may begin until the three docs above are merged and reviewed.

---

## First PR Plan: `docs: add realized attribution status spec`

### Files

- **New:** `docs/status/realized_attribution_spec.md` (creates `docs/status/`)
- **Optional, same PR:** `docs/status/realized_attribution_2026-07-05.md` — a
  dated snapshot instance produced by running the spec's read-only queries
  against the prod ledger at watermark `2026-07-05T16:00:00`. Include only if
  the numbers can be captured read-only without running any writer; otherwise
  defer the snapshot to a follow-up and land the spec alone.

### Purpose

Define, once and canonically, what "what has QNTY actually earned" means in
this repo: which SQLite quantities constitute realized attribution, how they
decompose, what identity binds them, and what language any status output must
use — so that every future claim (including the shorting motivation) cites
this spec instead of ad-hoc queries.

### Definitions (each bound to a schema location)

| Term | Canonical source |
|---|---|
| realized gross PnL | `equity_snapshots.realized_gross_pnl` at watermark; cross-check `SUM(trades.gross_pnl)` and `ledger_state.realized_gross` |
| realized net PnL | **derived:** `SUM(trades.net_pnl)` = `SUM(gross_pnl - fees - funding)` over closed trades (per-trade attribution); the spec must note this differs from ledger-level `realized_gross - fees_cum - funding_cum`, because cumulative fees/funding include entry fees and accrual on still-open positions |
| unrealized PnL | `equity_snapshots.unrealized_pnl` at watermark; per-symbol detail in `position_snapshot_symbols.unrealized_gross` |
| funding cumulative | `equity_snapshots.funding_cum` (cost convention: positive = paid); event detail in `funding.funding_amount` |
| fees cumulative | `equity_snapshots.fees_cum`; event detail in `fills`/`trades.fees` |
| total equity | `equity_snapshots.equity` at watermark |
| open positions | `open_positions` rows (symbol, qty, entry, `funding_accrued`, `entry_fee`, `hold_bars`) |
| closed trades | `trades` rows (round-trips with `gross_pnl`, `fees`, `funding`, `net_pnl`, `hold_bars`) |
| N_closed | `COUNT(*)` of `trades` rows (report per lane and per batch range) |

### Required read-only SQL query categories

1. Watermark/identity: latest `equity_snapshots` row; `ledger_state`;
   `paper_config` identity + `config_hash`/`config_hash_v2`; latest
   `ledger_batches` row and its clean-carry stamps.
2. Realized decomposition: `SUM(gross_pnl)`, `SUM(fees)`, `SUM(funding)`,
   `SUM(net_pnl)`, `COUNT(*)`, win/loss counts, `AVG(hold_bars)` from `trades`.
3. Unrealized decomposition: `open_positions` joined to latest
   `position_snapshot_symbols` for per-symbol `unrealized_gross`.
4. Identity check: the accounting identity below recomputed from parts.
5. Cross-lane: the same queries against prod and shadow DBs, resolved per the
   lane-resolution rules below, reported side by side.

All queries must be executable via read-only connection (SQLite URI
`mode=ro`, as in `quantbot/sidecars/ledger_ro.py`). The spec defines the
queries; it does not add a script (that is "later, not now").

### Required accounting identity

The repo's proven identity (enforced with tolerance at
`quantbot/paper/sqlite_writer.py:913-919`, sign conventions per
`docs/paper_pnl_v1_schema.md` §3.2):

```
equity = initial_equity + realized_gross_pnl - fees_cum - funding_cum + unrealized_pnl
```

The spec must state this exact form (funding and fees stored as accumulated
costs and subtracted) and must require every status snapshot to recompute it
from parts and report the residual.

### DB digest requirements

Every dated snapshot must record: the DB file path and `sha256` of the DB
file at read time, the watermark `bar_ts`, latest `batch_id`, `config_hash`
and (if present) `config_hash_v2`, and the latest verifier report's verdict
and clean-carry fields (full-ledger and batch-scoped). A snapshot whose DB
digest cannot be captured is not a valid snapshot.

### Decimal tolerance

Identity residuals must be reported and compared against the verifier's
existing absolute tolerance `1e-6` (`quantbot/paper/sqlite_verify.py:198`).
The spec adopts the verifier's tolerance rather than inventing a new one.

### Lane-resolution requirements

Snapshots must state which lane they read and how it was resolved:
explicit `--db-path` / `QNTY_PAPER_DB_PATH`, or output-dir resolution via
`paper_output_dir()` / `QNTY_PAPER_OUTPUT_DIR`. A snapshot that does not name
its lane and resolution mode is invalid. Prod and shadow must never be
conflated in one table without explicit lane columns.

### Output/verdict language requirements

- Required labels on every snapshot: `EDGE_UNPROVEN`,
  `BLOCK_LIVE_INTEGRATION`, and the full-ledger clean-carry state (currently
  `CAVEATED_ENGINE_SEMANTICS`) plus the batch-scoped state for the latest
  batch.
- Required phrasing: realized and unrealized figures must never be summed
  into a single "profit" headline; "gain" without the qualifier
  "unrealized" is prohibited when referring to open-position marks.
- Forbidden: "edge", "profitable", "works", "ready" as descriptions of the
  strategy; any annualized/extrapolated return.

### Acceptance criteria

1. Spec file exists at `docs/status/realized_attribution_spec.md` with all
   definitions bound to real schema columns (reviewer can check each against
   `quantbot/paper/db.py`).
2. The accounting identity matches the writer's enforced identity exactly.
3. All queries are read-only and lane-explicit.
4. Status Boundary labels present verbatim.
5. `git diff` for the PR touches only the new doc(s) under `docs/status/`.
6. No code, tests, configs, timers, or DBs touched.

### What it proves / does not prove

- **Proves:** that QNTY has a canonical, receipt-backed definition of
  realized vs unrealized attribution, and (if the dated snapshot is included)
  one honest instance of it: realized gross negative, gain concentrated in
  unrealized long exposure, N_closed small.
- **Does not prove:** edge, profitability, statistical significance,
  readiness for shorting, or readiness for live. It is a measurement
  contract, not a result.

### Files that must not be touched

`quantbot/**` (all engine/writer/verifier/strategy code), `scripts/**`,
`tests/**`, `data/**`, any systemd/timer config, any DB under
`/srv/qnty/output`, `forward_obs` artifacts, `.claude/**`,
`docs/paper_pnl_v1_schema.md` (the spec cites it; it does not edit it).

---

## Second PR Sketch: `docs: add shorting v3 research hypothesis`

Proposed file: `docs/research/short_v3_carry_harvest_downtrend.md` (sketch
only; full content is that PR's job).

- **Hypothesis name:** `short_v3_carry_harvest_downtrend`.
- **Statement:** short exposure is permitted *on paper, in a future dedicated
  lane only* when (a) the trend signal is negative, (b) expected funding
  carry to a short is positive (longs paying shorts) over the anticipated
  hold, and (c) risk filters pass (volatility regime, liquidity floor,
  squeeze guard). Shorting is hypothesized to add *realized net-of-carry*
  PnL relative to the long-only baseline — the quantity defined by the first
  PR's spec.
- **Scope locks:** no shorts in current prod or shadow lanes; no code in this
  PR or any near-term PR; the current engine's long-only invariant
  (`BUY` entry / `SELL` exit only) is untouched.
- **Sample-size minimum:** a preregistered minimum `N_closed` of short
  round-trips (justified via MinTRL-style reasoning) before any evaluation
  statement may be made; below it the only permitted label is
  `INSUFFICIENT_SAMPLE`.
- **Null requirements:** evaluation only against (a) a matched no-short null
  and (b) a random-entry short null with identical costs, over identical
  windows.
- **Cost-stress requirements:** results must survive stressed fills (worse
  than `next_bar_open_pessimistic`), stressed fees, and funding-sign-flip
  scenarios; must state the funding sign convention for shorts relative to
  the existing `funding.funding_amount` cost convention.
- **Squeeze-risk guardrails:** explicit worst-case adverse-excursion model
  for unbounded-loss geometry; a max-adverse-move assumption that, if
  exceeded in observation data, invalidates the window.
- **Rejection criteria:** preregistered conditions under which the hypothesis
  is declared dead (e.g., stressed realized net PnL below null after minimum
  sample; funding-carry assumption fails empirically in observed downtrends).
- Preserves all Status Boundary labels; makes no claim that shorting will
  work.

---

## Third PR Sketch: `docs: add preregistered forward experiment plan`

Proposed file: `docs/research/preregistered_forward_experiment_plan.md`
(sketch only).

- **Freeze:** trader/decision/signal logic frozen at a named commit for the
  duration of the window; any change to that logic resets the window to zero.
- **Metrics (preregistered):** realized net PnL per the first PR's spec;
  N_closed; realized-only Sharpe with PSR/MinTRL check; max drawdown;
  funding/fees decomposition. No metric added after the window starts.
- **Horizon:** a fixed calendar horizon *and* a minimum N_closed, both stated
  up front; whichever is later governs.
- **Benchmark/null lanes:** the existing shadow stays as identity control;
  the plan specifies (as future work) a matched alpha-null lane
  (e.g., randomized-entry with identical cost model) building on
  `quantbot/paper/null_comparator.py`.
- **Trial registry:** every evaluated variant/hypothesis is logged with a
  count, so DSR/Reality-Check-style multiplicity corrections are computable;
  unregistered trials disqualify the window.
- **Kill criteria:** preregistered conditions that terminate the experiment
  early (accounting caveat regression, drawdown bound, funding coverage
  failure).
- **Window resets:** logic change, config-hash change, accounting-semantics
  change, or any manual intervention in lane data.
- **No live integration:** the plan's only possible outcomes are
  documentation verdicts; `BLOCK_LIVE_INTEGRATION` is not lifted by any
  outcome of this experiment.

---

## Explicit Non-Goals

- No short-side code (engine, strategy, writer, verifier — nothing).
- No live integration of any kind.
- No leverage, and no leverage discussion beyond the Kelly zero-allocation bound.
- No DB mutation (prod, shadow, `forward_obs`, or any test artifact presented as evidence).
- No snapshot rewriting or retroactive relabeling of ledger history.
- No trader/decision/signal tweaks.
- No strategy promotion (shadow → prod, or any lane → "candidate").
- No edge claim, no profitability claim, no annualized projections.

---

## Open Questions

Questions that block *future implementation* (none block the three docs PRs):

1. **Short funding sign convention:** `funding.funding_amount` is stored as a
   cost to the long. For a future short lane, is the convention "negate the
   amount" or "recompute from signed rate × signed notional"? This must be
   fixed before any short-capable schema is designed.
2. **Short-side schema shape:** would shorts reuse `open_positions` with
   signed `qty` (STRICT table, no sign constraint today) or require a
   `side` column and verifier changes? Determines the size of the eventual
   (far-future) schema PR.
3. **Matched alpha-null lane mechanics:** can `null_comparator.py`'s offline
   fixture be promoted to a persistent null lane without touching the writer,
   or does a null lane require a writer variant (and therefore heavyweight
   review)?
4. **Margin/liquidation proxy:** what liquidation proxy is acceptable in a
   paper model for unbounded-loss shorts (fixed maintenance-margin threshold
   vs exchange-realistic tiered margin), and which exchange's rules anchor it?
5. **MinTRL threshold choice:** which confidence level and benchmark Sharpe
   should parameterize the minimum-sample rule that the shorting hypothesis
   and forward experiment will both cite?

---

*This plan is docs-only. No writer ran, no database was read with write
access, no trader/decision/signal/verifier code was modified. `EDGE_UNPROVEN`,
`BLOCK_LIVE_INTEGRATION`, and full-ledger `CAVEATED_ENGINE_SEMANTICS` are
preserved.*
