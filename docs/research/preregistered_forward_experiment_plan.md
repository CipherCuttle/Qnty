# QNTY Preregistered Forward Experiment Plan

**Plan version:** 1.0.0
**Date:** 2026-07-06
**Type:** preregistration / governance document (docs-only; defines rules and
gates, implements no runner, registry, lane, or code)
**Plan of record:**
`docs/plans/QNTY_REALIZED_ATTRIBUTION_AND_SHORTING_RESEARCH_FOUNDATION.md`
(this is the third PR of that plan's three-PR sequence)
**Measurement contract:** `docs/status/realized_attribution_spec.md`
(spec version 1.0.0)
**Short-side hypothesis:** `docs/research/short_v3_carry_harvest_downtrend.md`
(version 1.0.0)

---

## Status Boundary

- `EDGE_UNPROVEN` remains. Nothing in this document claims, implies, or is
  designed to manufacture an edge claim — for the existing long-only lanes,
  for any hypothetical short-side variant, or for any future experiment this
  plan governs.
- `BLOCK_LIVE_INTEGRATION` remains. No live exchange integration, no live
  capital, no live-readiness implication, per the canonical statement in
  `docs/status/realized_attribution_spec.md` § Status Boundary.
- Full-ledger `CAVEATED_ENGINE_SEMANTICS` remains. Only a verifier report
  (`paper_verify_report.json`, produced by `quantbot/paper/sqlite_verify.py`)
  can ever change that label; this document does not and cannot.
- Latest batch-scoped `CLEAN_NET_OF_CARRY`, when present
  (`funding_clean_carry_batch_decision`, PR #77;
  `quantbot/paper/sqlite_verify.py:2585-2588`), is **evidence/accounting
  quality for the latest batch only** — it is not trading edge, and it never
  relabels the full historical ledger.
- **This document is a preregistration plan only.** It defines the rules,
  metrics, nulls, gates, and kill criteria that any future forward experiment
  in this research program must obey before it may be scored or believed.
- This document **does not implement** any experiment runner, trial registry,
  append-only JSONL ledger, null lane, benchmark lane, short lane, attribution
  reporter, shorting code, live integration, or leverage. Every such artifact
  named below is future work, described as a requirement, not built here.
- This document **does not prove** edge, profitability, statistical
  significance, shorting readiness, or live readiness. It is a rulebook for how
  such claims could one day be tested — and, far more often, rejected.

---

## Dependencies

This plan is the governance layer on top of two documents it does not repeat:

- **`docs/status/realized_attribution_spec.md`** — the **measurement
  contract**. It defines every realized/unrealized quantity, funding and fee
  decomposition, `N_closed`, the `1e-6` accounting-identity tolerance, the
  read-only IO requirements, and the required/forbidden language. Every metric
  in this plan is defined *there*, not re-defined here.
- **`docs/research/short_v3_carry_harvest_downtrend.md`** — the **short-side
  hypothesis**. It defines the `short_v3_carry_harvest_downtrend` thesis,
  its eligibility rules, its mandatory nulls, its `N_closed_short` sample
  requirement, and its promotion gates. This plan governs *when and how* that
  hypothesis (and any future hypothesis) may be evaluated; it does not restate
  its content.
- **`docs/plans/QNTY_REALIZED_ATTRIBUTION_AND_SHORTING_RESEARCH_FOUNDATION.md`**
  — the **plan of record**. It sequenced the three PRs (spec → hypothesis →
  this plan) and sketched this document's required shape in its "Third PR
  Sketch" section. This plan is the realization of that sketch.

Load-bearing consequences of the dependency ordering:

- The realized attribution spec defines the **measurement contract** — the
  language a result must be reported in.
- The shorting v3 doc defines the **short-side hypothesis** — the first
  concrete future experiment this plan governs, but not the only one.
- This doc defines the **forward experiment governance layer** — freeze rules,
  trial counting, nulls, promotion gates, and kill criteria that sit above
  both.
- **None of these three documents authorizes code or live trading.** They are
  a measurement contract, a hypothesis, and a rulebook. Together they raise the
  bar for belief; they do not lower the bar for action.

---

## Purpose

This plan exists to make the QNTY research program falsifiable in advance
rather than negotiable after the fact. Concretely, it exists to:

- **Prevent moving goalposts.** Metrics, horizons, nulls, and kill criteria are
  fixed before scoring, not chosen after seeing which cut looks best. This is
  the preregistration discipline the plan of record's Five-Methodology
  Diagnosis demands, and the input that any Reality-Check / SPA-style
  multiplicity correction (White 2000; Hansen 2005) or Deflated Sharpe Ratio
  (Bailey & López de Prado 2014) requires to mean anything.
- **Prevent green unrealized PnL from becoming an edge claim.** The current
  paper gain is concentrated in unrealized long marks; realized gross PnL is
  negative (plan of record; realized attribution spec § What This Spec Proves).
  An equity curve going up is a statement about
  `equity_snapshots.unrealized_pnl`, not about captured PnL (Perold 1988). This
  plan forbids reading a mark as a capture.
- **Freeze the current forward window.** Define what "the current forward
  observation" *is*, so that its outcome cannot be improved retroactively by
  changing the logic that produced it.
- **Define how future variants are registered** — what a trial is, and that
  every trial must be counted before scoring.
- **Define what resets an experiment window** — which changes void
  comparability and restart the clock.
- **Define mandatory nulls and benchmarks before belief** — no result is
  interpretable except as a percentile against preregistered nulls.
- **Define promotion gates and kill criteria** — the only paths by which an
  observation may become a stronger experiment, and the many ways any
  experiment dies.

---

## Distinctions This Plan Keeps Separate

The plan of record warned that these are routinely conflated; keeping them
apart is the whole point of this document. Each is defined once, here, and used
consistently below:

| Concept | What it is | What it is **not** |
|---|---|---|
| **Current forward observation** | The existing prod paper long-only V2 lane, observed as-is under the attribution spec. | A promotion candidate; an edge; a tuned experiment. |
| **Future shorting research** | The `short_v3_carry_harvest_downtrend` hypothesis, replay-first, no lane yet. | Authorized code; a paper short lane; a live path. |
| **Replay evaluation** | Offline scoring against historical bars + funding (`quantbot/lab/replay_engine.py` in spirit). | Live-grade evidence; a paper lane; a writer run. |
| **Paper lanes** | Writer-produced SQLite ledgers with a `lane_id`/config identity. | Real capital; proof of edge; interchangeable with each other. |
| **Shadow identity control** | The current shadow lane, which proves determinism/replication. | An alpha null; a benchmark; something to modify. |
| **True alpha nulls** | Randomized-entry / exposure-matched comparators built for this program. | The shadow lane; anything that yet exists. |
| **Realized attribution** | `SUM(trades.net_pnl)` and its decomposition, per the spec. | Total equity; unrealized marks; ledger-level net without open-cost breakout. |
| **Statistical sufficiency** | Whether `N_closed` clears a preregistered floor. | An assumption; something achievable by extending the window until significance appears. |
| **Trial counting** | Recording every evaluated variant so multiplicity can be corrected. | Optional bookkeeping; something that can be reconstructed after the fact for free. |
| **Live trading** | Real exchange integration and real capital. | Anything this program produces; anything this plan lifts the block on. |

---

## Experiment Families

Three families are defined. **None is implemented by this PR.** Each entry
describes governance status only.

### A. Current Long-Only V2 Forward Observation

- **Scope:** the existing prod paper lane running the current long-only V2
  strategy, plus the current shadow lane as its identity/replication control.
- **No trader/decision/signal changes.** The engine's long-only invariant
  (`quantbot/paper/engine.py` — only `BUY` entry / `SELL` exit fills exist,
  cited by the attribution spec at `engine.py:373`, `:428`) is untouched.
- **Measured using the realized attribution spec** — its required snapshot
  fields, `N_closed`, `1e-6` tolerance, read-only IO, and required/forbidden
  language. No new metric, no new lane, no new code.
- **The current shadow remains an identity control**
  (`docs/plans/QNTY_V1_SHADOW_ASSERTED_IDENTITY_PNL_RECONCILIATION_AFTER_BATCH11.md`):
  prod/shadow agreement is evidence of reproducibility, never of edge, and the
  shadow is never counted as an alpha null.
- **Purpose: observe, not promote.** Family A exists to freeze and honestly
  report the current state — realized gross negative, gain concentrated in
  unrealized long marks, `N_closed` small — not to advance it toward "candidate."

### B. Future Short V3 Replay Research

- **Governed by** `docs/research/short_v3_carry_harvest_downtrend.md`. That
  document owns the hypothesis, eligibility rules, nulls, and gates; this plan
  owns the freeze/trial/window governance around it.
- **Replay first.** The first evaluation of the hypothesis, if ever run, is
  offline replay against historical bars and funding — no writer, no DB
  mutation, no lane creation.
- **No paper short lane until replay gates pass** (short-side doc, Gate 1).
  Any such lane would be a *new, dedicated* lane with its own `lane_id`/config
  identity, proposed under separate review — never a modification of prod or
  shadow.
- **No prod/shadow changes**, at any point, for any outcome.

### C. Future Benchmark / Null Research

A family of comparators, **all future work**, that any edge claim must be
scored against:

- **buy-and-hold / passive top-universe benchmark** (the Stage-4 benchmark
  design, `docs/plans/STAGE4_PLAN.md`; universe via
  `quantbot/data/quarterly_universe.py`), carry included;
- **cash/flat baseline** — zero exposure, zero PnL, zero cost;
- **random-entry null** — random entries, matched holding-time distribution,
  identical universe and costs;
- **random-short-entry null** — the short analogue, matched holding-time and
  costs;
- **exposure-matched long/short null** — random direction and timing at equal
  gross exposure, extending the cardinality-matched design of
  `quantbot/paper/null_comparator.py` (whose direction randomization is
  currently, deliberately, out of scope);
- **regime-split benchmark** — all of the above split by preregistered
  bull/bear/chop regimes.
- **The current shadow lane is not an alpha null.** It is an identity control
  and stays one.

**Do not implement any of these.** They are named so future work has a fixed
target, and so no result may claim significance without them.

---

## Frozen Logic Rule

A forward experiment's outcome is only meaningful if the logic that produced it
did not change mid-flight. This section defines what "the logic" is and what a
change to it does.

**Principle.** Any change to a **trader/decision/signal-affecting** path resets
the affected forward experiment window to zero. Docs-only changes do not.
Accounting/verifier changes do not prove edge, but may reset *evidence
semantics* if they change interpretation. Lane identity / config-hash changes
reset comparability.

**Reset rules (governance/doc only):**

- **Trading-logic change → window reset.** Any change to a path that can alter
  entries, exits, sizing, universe selection, or fills resets the relevant
  forward experiment window. The prior window's data becomes historical record,
  not continued evidence.
- **Docs-only change → no reset.** Editing documentation (including this file)
  does not touch the trading window.
- **Verifier/accounting change → possible evidence-semantics reset, never an
  edge upgrade.** A change to `quantbot/paper/sqlite_verify.py` or the
  accounting identity may change how a result is *interpreted* (e.g. the
  clean-carry label), which can reset evidence semantics; it can never by
  itself prove edge or lift `CAVEATED_ENGINE_SEMANTICS` in the promotion sense.
- **Config-hash / lane-identity change → comparability reset.** A change to
  `paper_config.config_hash` / `config_hash_v2`
  (`quantbot/paper/lane_config_hash.py`) or `lane_id`
  (`quantbot/paper/lane_identity.py`) means two windows are no longer the same
  experiment and may not be compared as if they were.

**Proposed initial list of frozen path patterns** (governance/doc only — **not
a CI rule, not enforced by code in this PR**; validating these in CI is an open
question below). Derived from repo inspection:

- `quantbot/strategy/**` — the strategy family (`base.py`, `tsmom_strategy.py`,
  `rolling_return_breakout.py`, `regime_filtered_breakout.py`, `ma_deviation.py`,
  `threshold.py`, `vol_state_overlay.py`, `noop.py`).
- Trader/decision/signal modules discovered by inspection: the strategy
  interface (`quantbot/strategy/base.py`) and the run/decision path
  (`quantbot/app/run_replay.py`) that turns signals into orders.
- Paper engine fill/position logic where it affects fills or PnL:
  `quantbot/paper/engine.py` (the long-only fill model), and the writer
  reconciliation it feeds (`quantbot/paper/sqlite_writer.py`).
- Config files that affect decisions, universe, or the cost model — including
  the universe path (`quantbot/data/quarterly_universe.py`,
  `quantbot/data/multi_asset_loader.py`) and any slippage/fee parameters of the
  fill model (`docs/paper_pnl_v1_schema.md` §2).
- Data-generation paths that affect signal inputs (the OHLCV/funding inputs the
  strategy consumes).

This list is a **proposal for the freeze declaration a future window would
name**, not an assertion that these files are frozen now. A concrete forward
window must pin an exact commit and the exact path set it considers frozen.

---

## Metrics

**All metrics are defined by `docs/status/realized_attribution_spec.md`.** This
plan adds no new metric definition; it lists which metrics a conforming forward
report must carry, and forbids some framings. Realized and unrealized figures
are **never** summed into one headline (spec § Required Language).

**Required (all per the spec's definitions and `1e-6` tolerance):**

- `N_closed` (spec def. #11) — and, for short experiments, `N_closed_short`
  (short-side doc) — **required on every figure**.
- closed-trade realized net PnL (`SUM(trades.net_pnl)`, spec def. #4) — the
  headline realized figure.
- realized gross PnL (spec def. #3) with its three-way cross-check.
- unrealized PnL (spec def. #5), **separately labeled**, never mixed into
  realized figures.
- fees cumulative (spec def. #7) with closed-vs-open decomposition (spec query
  category 4).
- funding cumulative (spec def. #6) with closed-vs-open decomposition.
- open positions count (`num_open` / `COUNT(open_positions)`, spec def. #8).
- max drawdown (of the realized equity path).
- realized-only drawdown, where available (drawdown of the closed-trade
  realized path, distinct from mark-inclusive drawdown).
- cost-stressed result (headline metrics recomputed under the preregistered
  cost/funding stress grid; see Cost And Execution Stress Rules).
- benchmark/null percentile (the result as a percentile of each mandatory
  null's distribution).
- regime-split performance (headline metrics split by preregistered
  bull/bear/chop).
- accounting identity residual (spec § Accounting Identity; must be `<= 1e-6`).
- verifier status (`current_verdict` from the cited `paper_verify_report.json`,
  spec query category 7).
- full-ledger clean-carry state (`funding_clean_carry_decision` / `_status` /
  `_reason_codes`).
- batch-scoped clean-carry state (`funding_clean_carry_batch_decision` /
  `_status` / `_reason_codes` and the stamped batch id).

**Forbidden:**

- annualized or extrapolated projections from the current small sample.
- a "profit" headline that mixes realized and unrealized PnL.
- edge / profitability / live-readiness / shorting-readiness language (spec §
  Required Language).

---

## Statistical Sufficiency Rules

- **A minimum `N_closed` is conceptually required before any interpretation.**
  The floor is derived by minimum-track-record-length reasoning (Bailey &
  López de Prado 2012: the record length needed to reject Sharpe ≤ benchmark at
  a stated confidence, given skew and kurtosis). Below the floor, the only
  permitted status is `INSUFFICIENT_SAMPLE` (or `INSUFFICIENT_DATA` where the
  shortfall is data coverage, not closed trades).
- **Sharpe / Sortino / PSR / DSR cannot be interpreted on tiny samples.** A raw
  Sharpe on a handful of trades is an anecdote. PSR/DSR exist precisely to
  correct for short samples and non-normality; they do not manufacture
  significance where the sample cannot support it.
- **DSR requires a trial count.** The Deflated Sharpe Ratio deflates for the
  number of trials tried (Bailey & López de Prado 2014); without the trial
  registry (below), no honest DSR is computable.
- **PBO/CSCV requires a registered strategy family and multiple paths** (Bailey,
  Borwein, López de Prado & Zhu 2017). The repo's current `pbo.py` is a
  self-declared PBO *proxy*, not true CSCV
  (`quantbot/experiment/pbo.py`); a real estimate needs the registered family
  this plan requires.
- **Realized closed trades are primary; marks are secondary.** Every sufficiency
  test is computed on `SUM(trades.net_pnl)` and `N_closed`, never on
  mark-to-market equity.

**Numeric thresholds are not fixed here.** Any specific number is
`PLACEHOLDER — to be preregistered before scoring`. This document deliberately
does not invent a final minimum `N_closed`, a final horizon, or a final
confidence level; those are registered before a window is scored, not chosen
after.

---

## Trial Definition And Registry Requirements

This section **defines, and does not implement,** trial-registry requirements.
No JSONL IO, no registry file, no id-keyed append logic is created by this PR.

**A trial is any evaluation of** any of the following (the list is inclusive,
not exhaustive):

- a strategy variant;
- a parameter set;
- a threshold set;
- a null design;
- a regime-split definition;
- a cost-stress grid;
- a data window;
- a universe rule;
- a shorting-eligibility rule;
- a benchmark comparison.

**Requirements:**

- **Every trial must eventually be logged before scoring is believed.** A
  result whose trials were not counted cannot be corrected for multiplicity and
  therefore cannot support an inference.
- **An unregistered trial invalidates the affected inference.** Silent trials
  disqualify the window they touch (short-side doc, Kill Criteria; plan of
  record: "unregistered trials disqualify the window").
- **Append-only JSONL may be a future implementation option** — the plan of
  record and the attribution spec's Open Questions both float it — **but this
  PR does not implement it.**
- **Idempotent, id-keyed appends may be a future design requirement** (so a
  re-run does not double-count a trial) **but this PR does not implement them.**

The storage format, location, and schema of the registry are open questions
below, not decisions made here.

---

## Null And Benchmark Requirements

The following comparisons are **mandatory future work** for any edge claim,
each run over identical windows, identical universe, and identical cost/funding
models as the candidate being tested (short-side doc, Null And Benchmark
Requirements):

- **current long-only V2 baseline** — the incumbent; additivity is claimed
  relative to *its* closed-trade realized net PnL.
- **cash/flat baseline** — zero exposure; anything that cannot beat doing
  nothing after costs is dead on arrival.
- **buy-and-hold / passive top-universe benchmark** — the Stage-4 design
  (`docs/plans/STAGE4_PLAN.md`), carry included.
- **random-entry null** — tests whether the *conditioning* adds anything beyond
  "being in the market sometimes."
- **random-short-entry null** — the short analogue.
- **exposure-matched long/short random null** — tests whether the result is
  distinguishable from coin-flip direction at equal gross exposure.
- **cost-stressed fill/funding null** — the same comparators under the
  preregistered stress grid.
- **regime split: bull / bear / chop** — every comparison split by
  preregistered regime definitions.
- **the current shadow lane is an identity control only** — never an alpha null,
  never a benchmark, never modified for this program.

**No experiment in this program can support an edge claim without null /
benchmark comparison.** A result is interpretable only as a *percentile against
its preregistered nulls*, over identical windows and cost models. A number
compared only against zero, or against a mark-inclusive equity curve, is not a
result.

---

## Replay Before Paper Rule

- **New strategy variants go replay first.** Offline scoring against historical
  bars and funding (`quantbot/lab/replay_engine.py` in spirit — it re-derives
  accounting from OHLCV + funding without touching the production engine)
  precedes any paper lane.
- **Shorting V3 goes replay first** (short-side doc, Replay-First Evaluation
  Plan; Gate 1).
- **Replay results are research-grade, not live-grade.** A replay pass is
  evidence that a hypothesis is worth a paper lane, never evidence of live
  readiness.
- **A paper lane may only be *proposed* after replay gates pass** — and
  proposal is not creation.
- **Paper lane creation is a separate future PR/task**, under separate review.
  This document neither creates nor authorizes one.
- **The current prod/shadow lanes are not modified**, at any point, for any
  outcome.

---

## Forward Paper Rules

For any future forward paper lane (**none is created here**):

- **Must have a lane identity** — `lane_id` and `config_hash` (and
  `config_hash_v2` where applicable), resolved per the attribution spec's
  lane-identity rules (`quantbot/paper/lane_identity.py`,
  `quantbot/paper/lane_config_hash.py`). A number without a lane label is
  invalid (spec def. #14).
- **Must start from a declared watermark** (`ledger_state.watermark_bar_ts`,
  spec def. #12), recorded at window open.
- **Must have preregistered metrics** — the Metrics list above, fixed before
  the window starts. No metric added mid-window.
- **Must have a preregistered horizon** — a calendar duration *and* a minimum
  `N_closed`, both stated up front (see Window And Horizon Rules).
- **Must have preregistered kill criteria** (see Kill Criteria).
- **Must be read using the realized attribution spec** — its required snapshot
  fields, tolerance, read-only IO, and language.
- **Must have verifier status reported** — the cited `paper_verify_report.json`
  `current_verdict` and clean-carry fields.
- **Cannot be compared against another lane** unless watermark, window, cost
  model, and universe compatibility are explicit. Prod and shadow figures are
  never summed or averaged (spec query category 8).

---

## Window And Horizon Rules

A forward window is defined by, and only by, a preregistered declaration of:

- **start watermark** — the `ledger_state.watermark_bar_ts` at which the window
  opens.
- **end condition** — the calendar end *and* the minimum-`N_closed` end.
- **minimum calendar duration** — `PLACEHOLDER — to be preregistered`.
- **minimum `N_closed`** — `PLACEHOLDER — to be preregistered`.
- **whichever is later governs** — the window is not complete until *both* the
  calendar horizon has elapsed *and* the minimum `N_closed` is reached (plan of
  record, Third PR Sketch).

**What resets the window** (clock back to zero): any trading-logic change
(Frozen Logic Rule), a config-hash or lane-identity change, or an
accounting-semantics change that alters interpretation.

**What voids the window** (data no longer admissible as evidence): a manual DB
edit, a snapshot rewrite, an unregistered trial affecting the window, a
verifier/accounting regression, or discovered lookahead/leakage (see Kill
Criteria).

**No final dates are invented here.** The repo docs do not fix a window date,
so every date and duration above is a placeholder to be registered before a
window is scored.

---

## Cost And Execution Stress Rules

No result may be promoted if it dies under preregistered cost stress.
Implementation shortfall — the gap between the paper decision price and what
execution would actually capture — is treated as a central measurement problem,
not a rounding error (Perold 1988; Almgren & Chriss 2000). Future requirements:

- **1× baseline costs** — the current model: `next_bar_open_pessimistic` fills,
  5 bps slippage, 5 bps flat taker fee per side (`docs/paper_pnl_v1_schema.md`
  §2).
- **2× / 3× fees and slippage** — `PLACEHOLDER — to be preregistered`.
- **mark-to-exit haircut** — a penalty on exit marks to model adverse fills —
  `PLACEHOLDER — to be preregistered`.
- **funding sign / interval stress** — funding perturbed in sign and settlement
  interval, because for a carry hypothesis funding *is* the treatment variable
  (short-side doc, Funding And Carry Semantics).
- **adverse-exit stress for shorts** — a squeezed short exit must not be modeled
  at the cost of a calm entry; short-side results must survive fills strictly
  worse than baseline (short-side doc, Methodology 3).
- **Promotion rule:** a result that is positive at 1× and dead under the
  preregistered stress grid is **not promoted**.

---

## Promotion Gates

Strict, ordered gates. Passing a gate produces at most a *document or a
proposal for separate review* — never automatic creation of a lane, and never
live integration. These gates are the governance wrapper around the
hypothesis-specific gates in the short-side doc.

### Gate A — Observation → Stronger Paper Experiment

An observation (Family A) may be proposed for a stronger, preregistered paper
experiment only when **all** of:

- realized attribution snapshots exist, conforming to the spec;
- verifier status is preserved (verdict `OK`; no clean-carry regression);
- the benchmark/null designs for the proposed experiment are registered;
- the trial-registry requirements are defined and the proposed trials counted;
- there are no frozen-logic violations in the observation window.

### Gate B — Replay Candidate → Separate Paper Lane

A dedicated paper lane may be *proposed* (not auto-created; separate review) for
a replay candidate only if replay shows **all** of (mirrors short-side Gate 1):

- enough replay events: `N_closed` (or `N_closed_short`) ≥ the preregistered
  minimum, else `INSUFFICIENT_SAMPLE`;
- closed-trade realized net PnL positive after all costs (fees, slippage,
  funding);
- the result beats **every** mandatory null at the preregistered percentile;
- the result survives the preregistered cost/funding stress grid;
- PnL is not concentrated in a single regime;
- no known leakage (purge/embargo audit passes, López de Prado 2018 ch. 7);
- no threshold retuned after results were seen (registry-verifiable).

### Gate C — Paper Lane → Dry-Live Discussion

A *discussion* of dry-live process (still no live integration) may open only if
the dedicated paper lane shows **all** of (mirrors short-side Gate 2):

- the preregistered horizon is complete (calendar *and* minimum `N_closed`,
  whichever is later);
- enough closed trades under the same minimum-sample rule;
- positive closed-trade realized net PnL after all costs;
- beats the mandatory nulls over the forward window;
- max drawdown within the preregistered cap;
- verifier and accounting cleanliness preserved (verdict `OK`; no clean-carry
  regression introduced by the lane);
- no logic contamination (Frozen Logic Rule respected across the window);
- **still no live integration** — this gate's output is a document.

### Gate D — Dry-Live → Real Capital

**Out of scope and blocked by `BLOCK_LIVE_INTEGRATION`.** No outcome of this
program — no gate, no result, no accumulation of results — lifts it. Lifting it
is a separate, future, explicit decision this document neither schedules nor
influences.

---

## Kill Criteria

Any experiment window in this program is declared **dead** (and its death
recorded, not quietly shelved) if any of the following occurs:

- **realized net below null after minimum sample** — closed-trade realized net
  PnL at or below a mandatory null once `N_closed` clears the preregistered
  floor;
- **insufficient sample after the preregistered horizon** — the horizon
  completes without reaching the minimum `N_closed`: verdict
  `INSUFFICIENT_SAMPLE`, not a window extension;
- **cost stress kills the result** — positive at 1×, dead under the
  preregistered stress grid;
- **performance concentrated in one lucky regime** — the result exists only
  inside a single bull/bear/chop regime;
- **drawdown breach** — max drawdown exceeds the preregistered cap;
- **verifier / accounting regression** — `current_verdict` degrades, or the
  accounting identity residual exceeds `1e-6`;
- **full-ledger caveat worsening** — a change that worsens the full-ledger
  `CAVEATED_ENGINE_SEMANTICS` state;
- **source-data / universe staleness** affecting the inference;
- **any lookahead / leakage** discovered in the split or lookback design;
- **manual DB edit** to any lane presented as evidence;
- **snapshot rewrite** — a dated snapshot edited in place rather than superseded
  by a new dated snapshot;
- **unregistered trial** touching the window;
- **frozen logic changed mid-window** — any trader/decision/signal-affecting
  path altered inside the window;
- **prod/shadow contaminated by a research branch** — the production or shadow
  lanes modified for, or by, this program.

---

## What This Document Proves

- A **governance / preregistration plan now exists**: the QNTY research program
  has a written rulebook for freeze, trial counting, nulls, promotion gates, and
  kill criteria, fixed before the experiments it governs are scored.
- Future experiments therefore have a fixed target to conform to, and a fixed
  set of ways to be rejected.
- **Nothing about edge, profitability, or significance.** A rulebook is not a
  result.

---

## What This Document Does Not Prove

- **No edge.** `EDGE_UNPROVEN` stands.
- **No profitability.** Realized gross PnL is negative in the current known
  state; nothing here changes or launders it.
- **No statistical significance.** `N_closed` is far below any plausible minimum
  track record length.
- **No shorting readiness.** Shorting remains a preregistered, untested
  hypothesis.
- **No live readiness.** `BLOCK_LIVE_INTEGRATION` stands.
- **No full-ledger clean status upgrade.** Full-ledger
  `CAVEATED_ENGINE_SEMANTICS` stands; only the verifier can ever change it.
- **No authorization to code shorting.**
- **No authorization to create null lanes.**
- **No authorization to create a trial registry.**

---

## Non-Goals

- No code.
- No scripts.
- No DB reads or writes.
- No writer / verifier / trader changes.
- No short lane.
- No null lane.
- No benchmark lane.
- No trial-registry implementation.
- No JSONL IO.
- No live integration.
- No leverage (and no leverage discussion beyond the Kelly zero-allocation
  bound: with edge unknown or ≤ 0, the growth-optimal live allocation is zero —
  Thorp 2006).
- No dated performance snapshot.
- No parameter tuning.

---

## Open Questions

None of these block this docs PR.

1. **Exact minimum `N_closed`** (and `N_closed_short`) — the MinTRL-derived
   floor(s) to preregister before any scoring.
2. **Exact calendar horizon** — the fixed duration to pair with the
   minimum-`N_closed` rule.
3. **Exact regime definitions** — how bull / bear / chop are defined and dated.
4. **Exact null generation method** — the randomization procedures for
   random-entry, random-short-entry, and exposure-matched nulls, and their seeds.
5. **Exact cost-stress grid** — the specific fee/slippage multipliers, exit
   haircut, and funding sign/interval perturbations.
6. **Trial registry storage format** — append-only JSONL vs another store; and
   whether snapshots should reference registry entries (attribution spec Open
   Question 3).
7. **Whether id-keyed idempotent JSONL appends are the right implementation** —
   or whether a different structure better guarantees no double-counting.
8. **Where future forward snapshots live** — `docs/status/` next to the spec, or
   `docs/verdicts/` with the other dated status artifacts (attribution spec Open
   Question 2 and 5).
9. **How to validate the frozen-path rules in CI later** — whether the frozen
   path patterns above can be enforced as a check that flags a window reset when
   a trading-logic path changes.

---

## References

**Repo documents**

- `docs/status/realized_attribution_spec.md` — realized attribution measurement
  contract (spec version 1.0.0).
- `docs/research/short_v3_carry_harvest_downtrend.md` — short-side hypothesis
  (version 1.0.0).
- `docs/plans/QNTY_REALIZED_ATTRIBUTION_AND_SHORTING_RESEARCH_FOUNDATION.md` —
  plan of record.
- `docs/plans/STAGE4_PLAN.md` — passive/benchmark design referenced by Family C.
- `docs/plans/QNTY_V1_SHADOW_ASSERTED_IDENTITY_PNL_RECONCILIATION_AFTER_BATCH11.md`
  — shadow lane as identity/replication control.
- `docs/paper_pnl_v1_schema.md` — paper ledger semantics, fill/cost model.

**Literature**

- Bailey, D. H. & López de Prado, M. (2012). "The Sharpe Ratio Efficient
  Frontier" (Probabilistic Sharpe Ratio and Minimum Track Record Length).
  https://papers.ssrn.com/sol3/papers.cfm?abstract_id=1821643
- Bailey, D. H. & López de Prado, M. (2014). "The Deflated Sharpe Ratio:
  Correcting for Selection Bias, Backtest Overfitting and Non-Normality,"
  *Journal of Portfolio Management* 40(5).
  https://papers.ssrn.com/sol3/papers.cfm?abstract_id=2460551
- Bailey, D. H., Borwein, J., López de Prado, M. & Zhu, Q. J. (2017). "The
  Probability of Backtest Overfitting," *Journal of Computational Finance*
  20(4) (CSCV). https://papers.ssrn.com/sol3/papers.cfm?abstract_id=2326253
- White, H. (2000). "A Reality Check for Data Snooping," *Econometrica* 68(5).
  https://ideas.repec.org/p/wyi/wpaper/002018.html
- Hansen, P. R. (2005). "A Test for Superior Predictive Ability," *Journal of
  Business & Economic Statistics* 23.
- López de Prado, M. (2018). *Advances in Financial Machine Learning*, Wiley,
  ch. 7 (purged k-fold cross-validation and embargo).
- Perold, A. F. (1988). "The Implementation Shortfall: Paper Versus Reality,"
  *Journal of Portfolio Management* 14(3).
- Almgren, R. & Chriss, N. (2000). "Optimal Execution of Portfolio
  Transactions," *Journal of Risk* 3(2).
- Moskowitz, T., Ooi, Y. H. & Pedersen, L. H. (2012). "Time Series Momentum,"
  *Journal of Financial Economics* 104(2).
  https://papers.ssrn.com/sol3/papers.cfm?abstract_id=2089463
- He, S., Manela, A., Ross, O. & von Wachter, V. (2022). "Fundamentals of
  Perpetual Futures." https://arxiv.org/abs/2212.06888
- Ackerer, D., Hugonnier, J. & Jermann, U. (2024). "Perpetual Futures Pricing,"
  NBER Working Paper w32936.
  https://www.nber.org/system/files/working_papers/w32936/w32936.pdf
- Thorp, E. O. (2006). "The Kelly Criterion in Blackjack, Sports Betting, and
  the Stock Market," *Handbook of Asset and Liability Management* vol. 1 (cited
  strictly as the zero-allocation risk bound, not as a size-up argument).
  https://gwern.net/doc/statistics/decision/2006-thorp.pdf

**Exchange documentation (funding mechanics)**

- Binance. "Introduction to Binance Futures Funding Rates" — funding is a
  periodic payment between longs and shorts; **when the funding rate is
  positive, longs pay shorts; when negative, shorts pay longs**. This is the
  sign convention any short-carry evaluation must state explicitly relative to
  the repo's cost-to-long convention (`funding.funding_amount`; attribution
  spec def. #6). https://www.binance.com/en/support/faq/detail/360033525031
- Binance API. "Get Funding Rate History of Perpetual Futures" — the funding
  rate history endpoint any replay of funding carry would source from.
  https://developers.binance.com/docs/derivatives/coin-margined-futures/market-data/rest-api/Get-Funding-Rate-History-of-Perpetual-Futures

---

*This plan is docs-only. No writer ran, no database was opened, no
trader/decision/signal/verifier code was modified, no test changed, no schema
changed. `EDGE_UNPROVEN`, `BLOCK_LIVE_INTEGRATION`, and full-ledger
`CAVEATED_ENGINE_SEMANTICS` are preserved. This document authorizes no code, no
lane, no registry, and no live integration.*
