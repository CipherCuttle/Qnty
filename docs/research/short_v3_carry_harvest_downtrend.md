# short_v3_carry_harvest_downtrend Research Hypothesis

**Hypothesis name:** `short_v3_carry_harvest_downtrend`
**Version:** 1.0.0
**Date:** 2026-07-06
**Type:** preregistered research hypothesis (docs-only; design, no code, no
data run, no numbers)
**Plan of record:**
`docs/plans/QNTY_REALIZED_ATTRIBUTION_AND_SHORTING_RESEARCH_FOUNDATION.md`
(this is the second PR of that plan's three-PR sequence)
**Measurement contract:** `docs/status/realized_attribution_spec.md`
(spec version 1.0.0)

---

## Status Boundary

- `EDGE_UNPROVEN` remains. Nothing in this document claims, implies, or is
  designed to manufacture an edge claim — for the existing long-only lanes or
  for any hypothetical short-side variant.
- `BLOCK_LIVE_INTEGRATION` remains. No live exchange integration, no live
  capital, no live-readiness implication, per the canonical statement in
  `docs/status/realized_attribution_spec.md` § Status Boundary.
- Full-ledger `CAVEATED_ENGINE_SEMANTICS` remains. Only a verifier report
  (`paper_verify_report.json`, `quantbot/paper/sqlite_verify.py`) can ever
  change that label; this document does not and cannot.
- This document is a **hypothesis / preregistration draft only**. It defines
  what would have to be tested, how, and against which nulls — before any
  test exists.
- This document does **not implement shorting**. The paper engine's long-only
  invariant (`quantbot/paper/engine.py` — only `BUY` entry / `SELL` exit
  fills exist, cited by the attribution spec at `engine.py:373`, `:428`) is
  untouched.
- This document does **not authorize shorting** in prod, in shadow, in any
  paper lane, or live. Creating any short-capable lane requires the promotion
  gates below to pass first, and separate review.
- This document does **not prove** edge, profitability, shorting readiness,
  live readiness, or statistical significance. It is a plan for how such
  claims could one day be tested and rejected — nothing more.

---

## Dependency On Realized Attribution Spec

This hypothesis is downstream of, and expressly bound to, the canonical
measurement contract `docs/status/realized_attribution_spec.md`. That
dependency is load-bearing, not decorative:

- **Shorting must be evaluated on closed-trade realized net PnL** —
  `SUM(trades.net_pnl)` per the spec's definition #4 — never on total equity
  alone. Total equity is mark-to-market and **may be dominated by unrealized
  open-position marks** (spec definition #2 and #5); the current lane's gain
  is exactly that. A short-side claim measured against total equity would be
  measuring an impression, not a capture (Perold 1988).
- **`N_closed` must be reported** with every figure — for shorts,
  `N_closed_short` (defined below) — per the spec's definition #11. No
  statistic on realized short returns may be quoted without it.
- **Funding and fees must be explicit**, with the closed vs open
  decomposition of the spec's query categories 3 and 4. For a carry-harvest
  hypothesis this is doubly non-negotiable: funding *is* the hypothesized
  carry, so burying it in a net number would hide the thing being tested.
- **Any future shorting result must conform to the realized attribution
  spec**: its required snapshot fields, its `1e-6` tolerance, its read-only
  IO requirements, its required and forbidden language. A short-side result
  that does not conform is not a result; it is an anecdote.

The plan of record ordered these PRs deliberately: the quantity this
hypothesis targets — *realized, net-of-carry PnL* — was undefined until the
attribution spec defined it.

---

## Hypothesis Summary

- **Name:** `short_v3_carry_harvest_downtrend`
- **One-sentence thesis:** In replay first, and only in a future dedicated
  paper lane if replay gates pass, conditional short exposure — taken only
  when the trend signal is negative, expected funding carry to the short is
  non-hostile, and volatility/liquidity/squeeze filters pass — is
  hypothesized to add closed-trade realized net-of-carry PnL relative to the
  long-only V2 baseline, net of fees, slippage, and funding, and relative to
  the mandatory nulls.

**What it is:**

- A preregistered, falsifiable research hypothesis about *realized,
  net-of-carry* attribution, stated before any short-capable code exists, so
  it cannot have been tuned to data already seen (the preregistration
  discipline of the plan of record's Five-Methodology Diagnosis §2).
- A design document for eligibility rules, nulls, metrics, gates, and kill
  criteria that any future evaluation must implement as specified — or
  register a deviation before running.

**What it is not:**

- Not an edge claim, a strategy, a signal change, or code.
- Not a proposal to modify the current prod or shadow lanes in any way.
- Not a backtest result, and not a promise that a backtest will be run.
- Not a sizing or leverage framework: the only sizing statement this
  document makes is the Kelly zero-allocation bound — with edge unknown or
  non-positive, the growth-optimal live allocation is zero (Thorp 2006),
  which is what `EDGE_UNPROVEN` + `BLOCK_LIVE_INTEGRATION` already encode.

**Why it exists:**

- The known state of the long-only record (per the plan of record): realized
  gross PnL is negative, the equity gain is concentrated in unrealized long
  marks, and `N_closed` is small. The evidence pack
  (`docs/experiments/QNTY_STRATEGY_VALIDITY_EVIDENCE_PACK_2026-06-18.md`)
  diagnosed the forward loss as directional: long-only momentum into a
  non-trending/down tape. The obvious *question* — not answer — is whether
  the short side of the same time-series-momentum family (Moskowitz, Ooi &
  Pedersen 2012) has anything to contribute once carry and short-specific
  risk are priced in.
- Crypto perpetuals add a carry dimension absent in spot: when funding is
  positive, longs pay shorts (Binance funding mechanics; He, Manela, Ross &
  von Wachter 2022). A short taken in a downtrend *may* collect that carry —
  or may face funding that has flipped negative in exactly the downtrend
  being targeted (Ackerer, Hugonnier & Jermann 2024). Whether the carry
  survives conditioning, costs, and squeezes is precisely what is unknown.

**Why it might fail:**

- Funding may flip against shorts in the very regimes the trend filter
  selects — downtrends are when shorts crowd in and funding often goes
  negative, charging shorts instead of paying them.
- The short side of TSMOM in crypto may be weaker than the long side after
  costs; conditioning on three filters may leave too few qualifying events
  (`INSUFFICIENT_SAMPLE`).
- Squeeze dynamics can concentrate losses in a few convex adverse moves that
  overwhelm many small carry gains — negative skew by construction.
- Costs: fees on both legs, pessimistic fills, and stressed funding may
  consume the entire hypothesized effect (Almgren & Chriss 2000; Perold
  1988).
- Any apparent replay success may be one lucky crash regime, or backtest
  overfitting outright (Bailey, Borwein, López de Prado & Zhu 2017).

---

## Proposed Short Eligibility Rules

Design only, not code. Where a number appears it is either borrowed verbatim
from frozen V2 logic (and cited) or explicitly marked
**`PLACEHOLDER — to be preregistered`** before any evaluation runs. A
placeholder is not a tuned value; choosing it after seeing results is a kill
criterion.

1. **Universe.** Same quarterly point-in-time top-5 universe as the long-only
   baseline (`quantbot/data/quarterly_universe.py`; BTC and ETH always
   present). No symbol may be short-eligible that is not in the current
   long-only universe. The known staleness of the universe table past
   2025-10-01 (evidence pack footgun F8) must be resolved before any replay
   window is scored — an out-of-date universe invalidates the window.
2. **Negative trend/momentum condition.** Short eligibility requires a
   negative time-series-momentum signal from the same family as the frozen V2
   TSMOM logic (`quantbot/strategy/tsmom_strategy.py`: rolling log return
   over `return_period ∈ {20, 40}` 8h bars, threshold `∈ {0.0, 0.03}`, long
   iff return > threshold). The proposed short condition is the mirrored
   form: rolling log return `< −threshold` over the same frozen lookbacks.
   Whether the mirror uses the identical grid or a preregistered subset is
   **`PLACEHOLDER — to be preregistered`**; no new lookbacks may be
   introduced.
3. **Funding/carry filter.** A short may only be opened when expected funding
   carry to the short over the anticipated hold is positive or not hostile:
   trailing realized funding (from the same funding data the engine already
   consumes) must not be charging shorts beyond a preregistered tolerance.
   Exact window and tolerance: **`PLACEHOLDER — to be preregistered`**.
4. **Volatility/heat filter.** Short entries are conditioned on the same
   vol-regime machinery as V2 (`quantbot/strategy/vol_state_overlay.py`:
   rolling stdev window 20, high quantile 0.65, regimes `low_vol` /
   `high_vol`). Which regime(s) permit short entry is
   **`PLACEHOLDER — to be preregistered`** — plausibly blocking entries in
   extreme-vol states where squeeze risk is highest.
5. **Liquidity filter.** Short-eligible symbols must satisfy a minimum
   liquidity floor (e.g. trailing volume rank within the top-5 universe).
   Exact floor: **`PLACEHOLDER — to be preregistered`**.
6. **Squeeze-risk block.** No short entry when squeeze precursors are
   present — e.g. sharp short-horizon upside reversal against the downtrend,
   or funding so deeply negative that it signals crowded shorts. Exact
   precursor definitions: **`PLACEHOLDER — to be preregistered`**, and they
   must be fixed *before* any backtest results are seen (see Squeeze And
   Short-Side Risk).
7. **No adds to losing shorts.** A short position that is underwater may
   never be increased. No averaging into a rising market against a short,
   ever. This rule is unconditional and has no placeholder.
8. **Max hold / exit condition.** Every short has a preregistered maximum
   hold in bars; reaching it forces an exit regardless of PnL. Exact value:
   **`PLACEHOLDER — to be preregistered`** (anchored to the V2 lookback
   scale, not tuned to results).
9. **Signal flip exit.** If the trend signal ceases to be negative (per rule
   2), the short exits at the next fill opportunity.
10. **Funding flip exit.** If realized funding flips hostile to the short
    beyond the rule-3 tolerance for a preregistered number of consecutive
    funding events, the short exits. Exact count:
    **`PLACEHOLDER — to be preregistered`**.
11. **Forced risk exit.** A per-position maximum adverse excursion cap; being
    breached forces an exit and counts as a squeeze event in the metrics.
    Exact cap: **`PLACEHOLDER — to be preregistered`**.
12. **No leverage.** Fixed notional per symbol, 1×, exactly as the long-only
    baseline ($1,000/symbol fixed-notional accounting). Nothing in this
    hypothesis introduces leverage, margin optimization, or position
    pyramiding.
13. **No prod/shadow changes.** These rules describe a hypothetical future
    *replay* evaluation and, only after gates pass, a hypothetical
    *dedicated* paper short lane. The current prod and shadow lanes are not
    modified by this document or by any evaluation of this hypothesis.

---

## Funding And Carry Semantics

This section exists because the plan of record's Open Question 1 requires
the short funding convention to be *defined on paper before* any
short-capable schema or code is designed.

- **Exchange semantics govern, not folklore.** On Binance perpetuals,
  positive funding means long positions pay and short positions receive;
  negative funding means shorts pay
  ([Binance funding rate introduction](https://www.binance.com/en/support/faq/detail/360033525031)).
  But "positive funding pays shorts" is an exchange-specific convention with
  exchange-specific clamps, premium-index construction, and interest-rate
  components — any future implementation must follow the documented
  semantics of the venue whose funding data is consumed, not a generic rule
  of thumb.
- **QNTY's stored convention is cost-to-long.** The ledger stores
  `funding.funding_amount = notional_at_mark * funding_rate` with the
  convention "long pays when the rate is positive"
  (`docs/paper_pnl_v1_schema.md:691`; accrual at
  `quantbot/paper/engine.py:256`; spec definition #6:
  positive = cost paid by the long). Every existing funding row in the
  ledger is a *long-side* cost number.
- **The short-side convention is an open design decision.** A future
  short-capable implementation must choose, explicitly and before coding,
  whether short funding is (a) the sign-flipped long amount, or (b)
  recomputed from signed notional × funding rate — and must prove the two
  agree (or document where they do not, e.g. under exchange clamps). This is
  Open Question 1 of the plan of record, restated here as a hard
  precondition; it is *not resolved by this document*.
- **Funding intervals are per-symbol/exchange facts, not constants.**
  Binance's standard interval is 8 hours, but intervals can differ by symbol
  and can change; the funding-info endpoints exist precisely because the
  schedule is data, not a constant
  ([funding rate history API](https://developers.binance.com/docs/derivatives/usds-margined-futures/market-data/rest-api/Get-Funding-Rate-History)).
  Any replay must consume actual funding event timestamps, as the current
  engine already does over held intervals, never a hardcoded "3 per day".
- **Funding is part of realized net attribution, not a side note.** For this
  hypothesis, funding is the *treatment variable*: "carry harvest" means the
  funding column of `trades` (or its future short-lane equivalent) is
  hypothesized to be a positive contributor. Every reported short result
  must show funding contribution per trade separately (see Required
  Metrics), under the attribution spec's decomposition rules. A net number
  that hides funding cannot test a carry hypothesis.

---

## Squeeze And Short-Side Risk

Shorting perpetuals is **not simply "negative longing"**, and any model that
treats it as a sign flip is wrong in ways that flatter the hypothesis:

- **Loss geometry is asymmetric.** A long's worst case is bounded at −100%
  of notional; a short's adverse side is unbounded in price terms. Upside
  moves against a short compound against the position (the short's notional
  exposure grows as price rises), creating convex loss paths and — on a real
  venue — margin-call/liquidation dynamics. The current paper engine has no
  margin or liquidation semantics at all (plan of record, Five-Methodology
  Diagnosis §3); a future evaluation must therefore include an explicit
  liquidation *proxy*, whose design is an open question below.
- **Squeezes produce the worst fills at the worst times.** Short squeezes
  are forced-buy-in cascades: exactly when a stop or risk exit triggers,
  liquidity on the offer side thins and execution costs spike. Assuming the
  standard `next_bar_open_pessimistic` fill (5 bps slippage, 5 bps taker fee
  per side, `docs/paper_pnl_v1_schema.md` §2) is *optimistic* for a
  squeezed exit; the cost-stress requirements below exist for this reason
  (Almgren & Chriss 2000 — cost has permanent and temporary impact
  components that grow with urgency; a squeeze is maximal urgency).
- **Funding and squeezes correlate.** Crowded shorts in a downtrend push
  funding negative (shorts pay), and the same crowding is squeeze fuel. The
  hypothesis's two pillars — carry and downtrend — can therefore fail
  jointly, not independently.
- **Risk filters must be preregistered before results are seen.** Every
  squeeze filter, adverse-excursion cap, and forced-exit rule in this
  document must have its final numeric form registered *before* any replay
  results are examined. Filters chosen after seeing which crashes hurt are
  overfitting with extra steps (Bailey & López de Prado 2014).
- **No adding to losing shorts.** Restated from the eligibility rules
  because it is the single most important short-side risk discipline.
- **No leverage.** 1× fixed notional only.
- **No live capital.** `BLOCK_LIVE_INTEGRATION` applies to every branch of
  this research program, unconditionally.

---

## Five-Methodology Review

### 1. Statistical edge validation

- **Diagnosis:** the realized long-only record is tiny and gross-negative;
  no PSR/MinTRL computation exists in the repo. A short-side variant starts
  with `N_closed_short = 0` and, because entries are triply conditioned
  (trend × funding × risk filters), qualifying events will accrue slowly.
- **Requirement:** a preregistered minimum `N_closed_short` derived by
  MinTRL-style reasoning (Bailey & López de Prado 2012: the track record
  length needed to reject Sharpe ≤ benchmark at a stated confidence, given
  skew and kurtosis) must be fixed before evaluation. Below it, the only
  permitted verdict is `INSUFFICIENT_SAMPLE`. Any Sharpe-like statistic
  reported must be deflated for the number of trials (Bailey & López de
  Prado 2014).
- **Metric:** `N_closed_short`; closed-trade realized net PnL;
  realized-only Sharpe with PSR and MinTRL check; the trial count feeding
  the deflation.
- **Failure mode:** quoting a raw Sharpe on a handful of conditioned short
  trades; computing statistics on marks instead of closed round-trips;
  ignoring the negative skew that squeeze losses impose on the return
  distribution (non-normality is exactly what PSR/DSR correct for).
- **Sources:** Bailey & López de Prado,
  ["The Sharpe Ratio Efficient Frontier"](https://papers.ssrn.com/sol3/papers.cfm?abstract_id=1821643)
  (PSR/MinTRL); Bailey & López de Prado,
  ["The Deflated Sharpe Ratio"](https://papers.ssrn.com/sol3/papers.cfm?abstract_id=2460551),
  *Journal of Portfolio Management* 40(5), 2014.

### 2. Backtest / overfitting control

- **Diagnosis:** the repo has a history of strategy iterations
  (`docs/verdicts/`), a self-declared PBO *proxy* rather than true CSCV
  (`quantbot/experiment/pbo.py`), and no trial registry yet (that is the
  third PR's job). The short hypothesis is being preregistered precisely so
  it exists before any short-capable code or data run.
- **Requirement:** every evaluated variant of this hypothesis — every
  placeholder resolution, every filter combination — must be counted as a
  trial and logged in the future trial registry; the family-wise selection
  effect must be controlled by CSCV/PBO estimation and/or
  Reality-Check/SPA-style tests against the null of no superior predictive
  ability. Unregistered trials disqualify the window. No retuning after
  seeing holdout or forward results.
- **Metric:** number of registered trials; PBO estimate; Reality Check /
  SPA p-value against the benchmark set; DSR using the registered trial
  count.
- **Failure mode:** running the mirrored-TSMOM grid, the funding-filter
  grid, and the vol-filter grid silently and reporting the surviving
  combination; declaring the hypothesis "confirmed" because one
  configuration cleared the nulls when dozens were tried.
- **Sources:** Bailey, Borwein, López de Prado & Zhu,
  ["The Probability of Backtest Overfitting"](https://papers.ssrn.com/sol3/papers.cfm?abstract_id=2326253),
  *Journal of Computational Finance* 20(4), 2017 (CSCV); White,
  ["A Reality Check for Data Snooping"](https://ideas.repec.org/p/wyi/wpaper/002018.html)
  (*Econometrica* 68(5), 2000); Hansen, "A Test for Superior Predictive
  Ability," *Journal of Business & Economic Statistics* 23, 2005.

### 3. Market microstructure / crypto-perp execution realism

- **Diagnosis:** the paper stack models fills as `next_bar_open_pessimistic`
  with 5 bps slippage and 5 bps flat taker fees per side
  (`docs/paper_pnl_v1_schema.md` §2), and has no short-side fill, margin, or
  liquidation semantics. That model was built for unhurried long/flat
  rotation; it does not represent squeezed short exits.
- **Requirement:** short-side results must survive stressed execution:
  fills strictly worse than the baseline model, stressed fees, and
  funding-sign-flip scenarios (plan of record, Second PR Sketch,
  cost-stress requirements). The stress magnitudes are
  **`PLACEHOLDER — to be preregistered`**. Implementation shortfall — the
  gap between the paper decision price and what execution would capture —
  must be treated as the central measurement problem, not a rounding error.
- **Metric:** cost-stressed closed-trade realized net PnL; fee/slippage
  contribution per trade; sensitivity of the headline result to the stress
  grid.
- **Failure mode:** a result that is positive at 5 bps slippage and dead at
  a stressed level; modeling a squeezed exit at the same cost as a calm
  entry; ignoring that funding flips and fill degradation arrive together.
- **Sources:** Perold, "The Implementation Shortfall: Paper Versus Reality,"
  *Journal of Portfolio Management* 14(3), 1988; Almgren & Chriss, "Optimal
  Execution of Portfolio Transactions," *Journal of Risk* 3(2), 2000; He,
  Manela, Ross & von Wachter,
  ["Fundamentals of Perpetual Futures"](https://arxiv.org/abs/2212.06888)
  (perp–spot deviations are large and time-varying).

### 4. Experimental design / null models

- **Diagnosis:** the existing shadow lane proves determinism and plumbing
  (identity/replication control) — it is **not** an alpha null and must not
  be repurposed as one. The offline matched-null selector
  (`quantbot/paper/null_comparator.py`) is long-only and cardinality-matched
  by design; direction randomization is explicitly out of its scope until
  shorts exist.
- **Requirement:** the mandatory null and benchmark set below must be
  designed and preregistered before any replay scoring; a short result is
  interpretable only as a *percentile against its nulls* over identical
  windows with identical cost models. Time-series evaluation must use
  purged/embargoed splits or an equivalent leakage control wherever
  train/selection and evaluation data could overlap through the lookback or
  hold windows.
- **Metric:** null percentile of closed-trade realized net PnL;
  regime-split performance (bull/bear/chop); leakage audit result for the
  split design.
- **Failure mode:** citing prod/shadow agreement as evidence for the
  hypothesis (it is evidence of reproducibility); evaluating shorts against
  zero instead of against random-entry shorts with identical costs; leaking
  the holdout through overlapping lookback windows.
- **Sources:** López de Prado, *Advances in Financial Machine Learning*,
  Wiley, 2018, ch. 7 (purged k-fold cross-validation and embargo); White
  (2000) and Hansen (2005), above, for testing against a benchmark family;
  Moskowitz, Ooi & Pedersen,
  ["Time Series Momentum"](https://papers.ssrn.com/sol3/papers.cfm?abstract_id=2089463),
  *Journal of Financial Economics* 104(2), 2012 (the long–short TSMOM
  literature this hypothesis borrows its family from — and whose regime
  dependence motivates the regime-split requirement).

### 5. Risk management / portfolio construction

- **Diagnosis:** the current system is paper-only, fixed-notional, 1×,
  long-only. No allocation decision exists or is proposed. Short-side risk
  adds unbounded-loss geometry and squeeze convexity that the long book
  never faced.
- **Requirement:** `EDGE_UNPROVEN` ⇒ zero live allocation. Kelly reasoning
  is cited here strictly as a *bound*: with edge unknown or ≤ 0 the
  growth-optimal allocation is zero, and overbetting relative to true edge
  produces ruin-bound dynamics (Thorp 2006). No leverage discussion beyond
  this bound is permitted in this research program. Short-side evaluation
  must additionally cap per-position adverse excursion and forbid adds to
  losing shorts, unconditionally.
- **Metric:** max adverse excursion per trade; worst single short event; max
  drawdown of the hypothetical short book; concentration of PnL by regime
  and by event.
- **Failure mode:** "if replay works, size up" reasoning; treating
  unrealized marks as a risk buffer; letting one lucky crash regime carry
  the whole result and calling the tail risk "managed".
- **Sources:** Thorp,
  ["The Kelly Criterion in Blackjack, Sports Betting, and the Stock Market"](https://gwern.net/doc/statistics/decision/2006-thorp.pdf),
  *Handbook of Asset and Liability Management* vol. 1, 2006; Ackerer,
  Hugonnier & Jermann,
  ["Perpetual Futures Pricing"](https://www.nber.org/system/files/working_papers/w32936/w32936.pdf)
  (NBER w32936: funding-regime changes flip the sign of short carry — the
  carry leg is itself a risk factor, not a coupon).

---

## Null And Benchmark Requirements

No shorting result can be interpreted without null comparison. The following
nulls and benchmarks are **mandatory** for any future evaluation, all run
over identical windows, identical universe, and identical cost/funding
models as the short variant being tested:

1. **Current long-only V2 baseline** — the incumbent. The hypothesis claims
   *additivity* to this baseline's closed-trade realized net PnL; the
   baseline is therefore the primary comparator.
2. **Cash/flat baseline** — zero exposure, zero PnL, zero cost. Any strategy
   that cannot beat doing nothing after costs is dead on arrival.
3. **Buy-and-hold / passive exposure benchmark** — the quarterly top-5
   equal-weight long book with no signal (the Stage-4 benchmark design,
   `docs/plans/STAGE4_PLAN.md`), carry included.
4. **Random-short-entry null** — shorts entered at random times with the
   same holding-time distribution, same universe, same costs and funding.
   Tests whether the *conditioning* (trend/funding/risk filters) adds
   anything beyond "being short sometimes."
5. **Exposure-matched long/short random null** — random direction and timing
   matched to the candidate's gross exposure profile, extending the
   cardinality-matched design of `quantbot/paper/null_comparator.py` (whose
   direction randomization is currently, deliberately, out of scope). Tests
   whether the result is distinguishable from coin-flip direction at equal
   exposure.
6. **Regime-split benchmark** — all of the above split by preregistered
   bull / bear / chop regime definitions (definition method is an open
   question below). A short result that exists only inside one crash regime
   is a regime bet, not a strategy.
7. **The current shadow lane remains an identity/replication control** — it
   is *never* to be counted as an alpha null, cited as a benchmark, or
   modified for this program.

---

## Replay-First Evaluation Plan

- **First evaluation is replay only.** Any initial test of this hypothesis
  runs offline against historical bars and funding events — in the spirit of
  the existing independent replay lane (`quantbot/lab/replay_engine.py`),
  which re-derives accounting from OHLCV + funding without touching the
  production engine. No writer runs, no DB is mutated, no lane is created.
- **No prod/shadow lane changes**, at any point, for any outcome.
- **No paper short lane until replay gates pass** (see Promotion Gates). The
  lane, if ever created, is a *new, dedicated* lane with its own
  `lane_id`/config identity per the attribution spec's lane-identity rules —
  never a modification of an existing lane.
- **All trials must be counted.** Every configuration evaluated under this
  hypothesis must eventually be recorded in the future trial registry /
  preregistered forward experiment plan (the third PR). Trials run before
  the registry exists must be reconstructible and declared; silent trials
  disqualify the affected windows.
- **No retuning after seeing holdout.** Placeholders are resolved and
  registered first; then data is scored. A resolved placeholder that moves
  after results are seen kills the window (see Kill Criteria).
- **Leakage control.** Where any selection/fitting step exists, use purged
  and embargoed time-series splits or an equivalent control sized to the
  lookback and hold windows (López de Prado 2018, ch. 7), so that no
  training/selection window overlaps evaluation labels.
- **`INSUFFICIENT_SAMPLE` is a first-class outcome.** If the triply
  conditioned entry rules produce fewer qualifying short events than the
  preregistered minimum `N_closed_short`, the only permitted report is
  `INSUFFICIENT_SAMPLE` — not a p-value, not a suggestive chart, not an
  extension of the window until significance appears.

---

## Required Metrics

Every future evaluation report for this hypothesis must include **all** of
the following, computed under the realized attribution spec's definitions
and tolerances, with realized and unrealized never summed into one headline:

- **`N_closed_short`** — count of closed short round-trips (the short-lane
  analogue of the spec's `N_closed`; reported alongside the overall
  `N_closed` of any combined book).
- **Closed-trade realized net PnL** — `SUM(net_pnl)` over closed short
  round-trips (headline realized figure).
- **Realized gross PnL** — price-only PnL of closed shorts, before fees and
  funding.
- **Fees** — total and per-trade, closed-trade decomposition.
- **Funding** — total and per-trade, under the explicitly stated short-side
  sign convention (see Funding And Carry Semantics).
- **Unrealized PnL, clearly separated** — mark-to-market on any open
  hypothetical shorts, never mixed into realized figures, labeled
  "unrealized" wherever it appears.
- **Max adverse excursion** — per trade and worst-case, in return and
  notional terms.
- **Max favorable excursion** — per trade, to expose exits that give back
  captured moves.
- **Worst single short event** — the single worst trade, reported
  individually with its regime and funding context.
- **Max drawdown** — of the hypothetical short book's realized equity path.
- **Funding contribution per trade** — the carry actually collected or paid,
  the treatment variable of this hypothesis.
- **Fee/slippage contribution per trade** — execution cost decomposition.
- **Null percentile** — the candidate's closed-trade realized net PnL as a
  percentile of each mandatory null's distribution.
- **Regime-split performance** — all headline metrics split by the
  preregistered bull/bear/chop definitions.
- **Cost-stressed performance** — all headline metrics under the
  preregistered fill/fee/funding stress grid.

---

## Promotion Gates

### Gate 0: Idea → Replay Candidate

Passes when — and only when — all of:

- this hypothesis document exists and is merged (this PR);
- the realized attribution spec exists (done: PR #78);
- all `PLACEHOLDER — to be preregistered` values are resolved and registered
  (in the trial registry / prereg plan of the third PR) *before* scoring;
- the mandatory nulls are designed and their generation method registered;
- the minimum `N_closed_short` and the evaluation windows are preregistered.

### Gate 1: Replay Candidate → Separate Paper Short Lane

A dedicated paper short lane may be *proposed* (not auto-created; separate
review required) only if replay shows **all** of:

- enough qualifying short events: `N_closed_short` ≥ the preregistered
  minimum (otherwise `INSUFFICIENT_SAMPLE`, full stop);
- closed-trade realized net PnL after all costs (fees, slippage, funding) is
  positive;
- the result survives the preregistered cost/funding stress grid;
- the result beats **every** mandatory null at the preregistered percentile;
- PnL is not concentrated in a single crash regime (regime-split
  requirement);
- no known leakage: the purge/embargo audit passes;
- no threshold was retuned after results were seen (registry-verifiable).

### Gate 2: Paper Short Lane → Dry-Live Discussion

A *discussion* of dry-live process (still no live integration) may open only
if the dedicated paper lane shows **all** of:

- the lane has run for its preregistered horizon (calendar *and* minimum
  `N_closed_short`, whichever is later, per the third PR's design);
- enough closed short trades under the same minimum-sample rule;
- positive closed-trade realized net PnL after all costs;
- beats the mandatory nulls over the forward window;
- max drawdown within the preregistered cap;
- verifier and accounting cleanliness preserved for the lane (verifier
  verdict `OK`; no clean-carry regression introduced by the lane);
- **no live integration** — this gate's output is a document, nothing else.

### Gate 3: Dry-Live → Real Capital

**Out of scope and blocked.** `BLOCK_LIVE_INTEGRATION` stands. No outcome of
this research program — no gate, no result, no committee of results — lifts
it. Lifting it is a separate, future, explicit decision that this document
neither schedules nor influences.

---

## Kill Criteria

The hypothesis is declared **dead** (and its death recorded, not quietly
shelved) if any of the following occurs:

1. **Below-null after minimum sample:** closed-trade realized net PnL at or
   below the random-short-entry null's median once `N_closed_short` has
   reached the preregistered minimum.
2. **Catastrophic squeeze behavior:** any single short event, or the tail of
   the adverse-excursion distribution, exceeds the preregistered worst-case
   adverse-move assumption — the window is invalidated and the risk model,
   not the threshold, must be re-examined from scratch.
3. **One lucky crash:** removing the single best regime window (per the
   preregistered regime split) flips the result from pass to fail.
4. **Funding filter fails empirically:** observed funding in qualifying
   downtrends is systematically hostile to shorts (the carry-harvest premise
   is false in the data).
5. **Cost stress kills the result:** the preregistered fill/fee/funding
   stress grid takes stressed realized net PnL below the null.
6. **Insufficient sample after the preregistered window:** the evaluation
   window closes with `N_closed_short` below minimum → `INSUFFICIENT_SAMPLE`
   is recorded; extending the window to chase significance is prohibited and
   itself kills the hypothesis.
7. **Evidence contamination:** any leakage, look-ahead, or
   holdout-peek discovered after the fact.
8. **Any manual DB or snapshot edit** touching evaluation evidence — the
   attribution spec's append-only discipline applies; edited evidence is
   dead evidence.
9. **Any prod/shadow logic contamination:** if pursuing this hypothesis is
   found to have modified prod or shadow lane logic, config, or data in any
   way, the hypothesis program halts pending audit.
10. **Any unregistered trial** run after the trial registry exists.

---

## What This Document Proves

- A **preregistered hypothesis document exists**: the short-side thesis, its
  eligibility rules, its nulls, its metrics, its gates, and its kill
  criteria were written down *before* any short-capable code, lane, or
  backtest result existed.
- QNTY has a **defined shorting research thesis to evaluate later**, bound to
  the realized attribution measurement contract, with `INSUFFICIENT_SAMPLE`
  and death-by-null as first-class outcomes.
- **Nothing about edge or profitability.** Existence of a plan is not
  evidence that the plan will pass its own gates.

---

## What This Document Does Not Prove

- **No edge.** `EDGE_UNPROVEN` stands, for the long book and for any
  hypothetical short book.
- **No profitability.** The known long-only state (negative realized gross
  PnL, unrealized-dominated equity) is unchanged; the short side has zero
  evidence of any kind.
- **No statistical significance.** `N_closed_short` is zero; nothing has
  been measured.
- **No shorting readiness.** No short-capable engine, schema, fill model,
  funding convention, or liquidation proxy exists.
- **No live readiness.** `BLOCK_LIVE_INTEGRATION` stands.
- **No prod/shadow change.** Both lanes are exactly as they were; the shadow
  lane remains an identity/replication control.
- **No full-ledger status upgrade.** Full-ledger `CAVEATED_ENGINE_SEMANTICS`
  stands; only the verifier can ever change it.
- **No authorization to code shorting.** Writing short-capable code requires
  Gate 0 completion (placeholder registration, null design, third-PR prereg
  plan) *and* separate review — this document authorizes none of it.

---

## Non-Goals

- No code.
- No scripts.
- No DB reads or writes of any kind for this PR.
- No writer, verifier, or trader/decision/signal changes.
- No short lane (paper or otherwise).
- No trial registry implementation (third PR defines it; later work builds
  it).
- No live integration.
- No leverage, and no leverage discussion beyond the Kelly zero-allocation
  bound.
- No dated performance snapshot (that is the attribution spec's future
  artifact, produced separately).
- No parameter tuning — every unresolved number in this document is a
  registered placeholder, not a chosen value.

---

## Open Questions

None of these block this docs PR.

1. **Exact numeric thresholds:** final values for every
   `PLACEHOLDER — to be preregistered` (funding-filter window/tolerance,
   vol-regime permission set, liquidity floor, squeeze precursors, max hold,
   funding-flip count, adverse-excursion cap, stress grid magnitudes,
   minimum `N_closed_short`, null percentile) — to be fixed in the trial
   registry / prereg plan before any scoring.
2. **Short funding convention:** sign-flip the stored cost-to-long
   `funding_amount`, or recompute from signed notional × rate? (Plan of
   record Open Question 1; must be settled before any short-capable schema
   design.)
3. **Liquidation proxy:** what margin/liquidation approximation is
   acceptable in a paper model for unbounded-loss shorts — fixed
   maintenance-margin threshold or exchange-realistic tiered margin — and
   which venue's rules anchor it? (Plan of record Open Question 4.)
4. **Random-short-entry null design:** how to draw entry times and match
   holding-time distributions without leaking the candidate's information;
   whether the exposure-matched long/short null extends
   `null_comparator.py`'s seeded design or needs a new mechanism.
5. **Regime definitions:** how bull/bear/chop are defined (trend-sign,
   drawdown-state, vol-regime composite, or external reference series) and
   over what window, fixed before any regime-split scoring.
6. **Future schema shape:** would a future short-capable lane reuse
   `open_positions` with signed `qty` or add a `side` column, and what
   verifier changes follow? (Plan of record Open Question 2; far-future.)

---

## References

1. Bailey & López de Prado, ["The Sharpe Ratio Efficient Frontier"](https://papers.ssrn.com/sol3/papers.cfm?abstract_id=1821643),
   *Journal of Risk* 15(2), 2012 — Probabilistic Sharpe Ratio and Minimum
   Track Record Length.
2. Bailey & López de Prado, ["The Deflated Sharpe Ratio: Correcting for Selection Bias, Backtest Overfitting and Non-Normality"](https://papers.ssrn.com/sol3/papers.cfm?abstract_id=2460551),
   *Journal of Portfolio Management* 40(5), 2014.
3. Bailey, Borwein, López de Prado & Zhu, ["The Probability of Backtest Overfitting"](https://papers.ssrn.com/sol3/papers.cfm?abstract_id=2326253),
   *Journal of Computational Finance* 20(4), 2017 — CSCV.
4. White, "A Reality Check for Data Snooping," *Econometrica* 68(5), 2000.
5. Hansen, "A Test for Superior Predictive Ability," *Journal of Business &
   Economic Statistics* 23, 2005.
6. López de Prado, *Advances in Financial Machine Learning*, Wiley, 2018 —
   ch. 7, purged k-fold cross-validation with embargo.
7. Moskowitz, Ooi & Pedersen, ["Time Series Momentum"](https://papers.ssrn.com/sol3/papers.cfm?abstract_id=2089463),
   *Journal of Financial Economics* 104(2), 2012, pp. 228–250.
8. Perold, "The Implementation Shortfall: Paper Versus Reality," *Journal of
   Portfolio Management* 14(3), 1988.
9. Almgren & Chriss, "Optimal Execution of Portfolio Transactions,"
   *Journal of Risk* 3(2), 2000.
10. He, Manela, Ross & von Wachter, ["Fundamentals of Perpetual Futures"](https://arxiv.org/abs/2212.06888),
    arXiv:2212.06888 / SSRN 4301150.
11. Ackerer, Hugonnier & Jermann, ["Perpetual Futures Pricing"](https://www.nber.org/system/files/working_papers/w32936/w32936.pdf),
    NBER Working Paper w32936.
12. [Binance: Introduction to Binance Futures Funding Rates](https://www.binance.com/en/support/faq/detail/360033525031)
    and [USDⓈ-M funding rate history API](https://developers.binance.com/docs/derivatives/usds-margined-futures/market-data/rest-api/Get-Funding-Rate-History)
    — positive funding: longs pay shorts; per-symbol funding intervals.
13. Thorp, ["The Kelly Criterion in Blackjack, Sports Betting, and the Stock Market"](https://gwern.net/doc/statistics/decision/2006-thorp.pdf),
    *Handbook of Asset and Liability Management* vol. 1, 2006 — cited
    strictly as the zero-allocation bound under unknown/non-positive edge,
    never as a size-up argument.

---

*This document is docs-only. No writer ran, no database was opened, no
trader/decision/signal/verifier code was modified, no short-capable code
exists or is authorized by this document. `EDGE_UNPROVEN`,
`BLOCK_LIVE_INTEGRATION`, and full-ledger `CAVEATED_ENGINE_SEMANTICS` are
preserved.*
