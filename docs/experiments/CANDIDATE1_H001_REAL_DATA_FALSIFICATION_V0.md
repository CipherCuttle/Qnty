# Candidate 1 H001 real-data falsification preregistration

Status: `PREREGISTERED_DESIGN_ONLY`

This document freezes a non-executable experimental design. It does not access,
select, bind, preserve, or execute on real data. It does not authorize a
scientific claim, paper trading, live integration, or capital allocation.
Synthetic exploration is mechanical-only and is not market evidence.

## Scope and scientific boundary

The design tests `candidate1-v1-funding-crowding-reversal-h001`, whose rule kind
is `FUNDING_CROWDING_REVERSAL`. Real-data access, artifact operations, and all
H001 execution remain forbidden until the later custody, implementation,
environment, review, preflight, and governance gates are satisfied.

## Protocol identity

- Schema: `0.1.0`
- Protocol: `real_btc_h001_funding_crowding_reversal_falsification_v0`
- Hypothesis: `candidate1-v1-funding-crowding-reversal-h001`
- Status: `PREREGISTERED_DESIGN_ONLY`
- Data identity: `UNBOUND_DESIGN_ONLY`
- Future artifact identity: `UNASSIGNED_REQUIRES_LATER_GOVERNANCE`
- Execution authorized: `false`
- Real-data access authorized: `false`
- Artifact operations authorized: `false`
- Validation and holdout execution authorized: `false`
- Scientific, paper-trade, and live authorization: `false`
- Primary execution budget/count: `0/0`

This is separate from `real_btc_candidate1_train_mechanism_decomposition_v0`;
that V0 identity is not mutated, recovered, retired, replaced, or reused.

## Hypothesis

Conditional on funding crowding, a confirmed lagged price reversal against the
crowded side may define a mechanically distinct future return process after
registered trading costs and funding cashflows. Positive funding crowding with
a confirmed downward price reversal produces a short signal. Negative funding
crowding with a confirmed upward price reversal produces a long signal.
Funding crowding without price reversal and price reversal without funding
crowding both produce no position. “May define” is the claim under test, not an
accepted finding.

## Primary falsification question

Does any member of the frozen nine-variant H001 family pass the registered
family-wise validation test and then independently confirm positive net returns
on the single untouched final holdout after registered costs?

## Data universe

The universe is Binance USD-M Futures, the BTCUSDT linear USDT-margined
perpetual contract, with 8-hour UTC bars from `2020-01-01T00:00:00Z` through
`2026-06-30T23:59:59Z`. Price and funding come from that same venue and
instrument. Cross-venue mixing is forbidden. A later freezing task may use only
official Binance public historical files or the official Binance public API,
and must record exact source URLs, retrieval timestamps, raw-byte hashes,
parsed-file hashes, and a portable manifest. This design task contacts no such
source.

## Raw schema and integrity

Bars require `open_time_utc`, `close_time_utc`, `open`, `high`, `low`, `close`,
and `volume`. Funding requires `funding_time_utc` and
`funding_rate_decimal`. Values must be finite; timestamps must be UTC, unique,
strictly increasing, and bars must have exact 8-hour cadence. OHLC prices are
positive, `high >= max(open, close, low)`, `low <= min(open, close, high)`, and
volume is non-negative. No duplicate resolution, interpolation, silent row
deletion, flattening, or exclusion of defective intervals is allowed.

## Real-input transformations

For signal construction only, use `100 * natural_log(raw_close)` and
`100 * raw_funding_rate_decimal`. Thus price deadbands 0.5, 1, and 2 represent
approximately 0.5%, 1%, and 2%; funding deadbands 0.05 and 0.1 represent 5 and
10 basis points. Raw BTC-dollar differences are forbidden. Inputs may not be
rescaled after activation counts or returns are viewed. Accounting uses raw
prices and raw decimal funding rates.

## Temporal join contract

For held interval `t`, the decision timestamp is `bar[t].open_time_utc`, entry
is `bar[t].open`, and exit is `bar[t].close`. The signal may use only bar closes
with `close_time_utc <= bar[t].open_time_utc` and the latest funding event with
`funding_time_utc <= bar[t].open_time_utc`. `prior close` is close of `t-1`,
`lookback close` is close of `t-1-lookback`, and prior funding is the latest
eligible event. No nearest-neighbour join or future funding is allowed.

For each variant, `price_delta = price_signal_value[t-1] -
price_signal_value[t-1-lookback]`. If warm-up is insufficient, position is 0.
Otherwise, prior funding above its deadband and price delta below its deadband
produce `-1`; prior funding below the negative deadband and price delta above
the deadband produce `+1`; all other cases are 0. Equality remains flat.
Funding used for the signal is not a cashflow for the newly entered position.
Held-interval funding includes events satisfying
`bar[t].open_time_utc < funding_time_utc <= bar[t].close_time_utc`. Funding may
not be forward-filled beyond 12 hours. Any evaluable interval without an
eligible prior funding event within 12 hours, or any missing 8-hour bar, fails
the data-integrity gate.

## Frozen H001 variant family

All nine are one disclosed family; no synthetic result selects or prioritizes a
variant. The candidate trial count is 9.

| variant | lookback | price deadband | funding deadband |
|---|---:|---:|---:|
| `h001-l1-pdb0-fdb0` | 1 | 0 | 0 |
| `h001-l1-pdb0p5-fdb0p05` | 1 | 0.5 | 0.05 |
| `h001-l1-pdb1-fdb0p1` | 1 | 1 | 0.1 |
| `h001-l2-pdb0-fdb0` | 2 | 0 | 0 |
| `h001-l2-pdb1-fdb0p05` | 2 | 1 | 0.05 |
| `h001-l2-pdb2-fdb0p1` | 2 | 2 | 0.1 |
| `h001-l4-pdb0-fdb0` | 4 | 0 | 0 |
| `h001-l4-pdb1-fdb0p05` | 4 | 1 | 0.05 |
| `h001-l4-pdb2-fdb0p1` | 4 | 2 | 0.1 |

## Controls

The controls are `ALWAYS_FLAT`, `ALWAYS_LONG`, `ALWAYS_SHORT`,
`FUNDING_SIGN_FADE`, `LAGGED_RETURN_SIGN`, and `LAGGED_RETURN_FADE`. They are
benchmarks and mechanism decompositions and cannot become the selected H001
survivor.

## Chronological split design

- Development: 2020-01-01 through 2022-12-31 UTC. It is limited to schema,
  timestamp, joinability, cost-document, implementation, and regime-threshold
  work. No H001 returns, performance, ranking, activation ranking, charts, or
  primary statistics may be computed or used for selection.
- Validation: 2023-01-01 through 2024-12-31 UTC. All nine variants and six
  controls may be evaluated exactly once.
- Final untouched holdout: 2025-01-01 through 2026-06-30 UTC. It remains sealed
  unless validation passes, then only the single selected H001 variant is
  evaluated exactly once. Up to four preceding bars and the latest eligible
  preceding funding event from the prior region may warm up the holdout; warmup
  observations are excluded from split statistics. No random splits or
  outcome-informed boundary changes are allowed.

## Return accounting and cost model

Positions are `-1`, `0`, and `+1`; leverage is forbidden and normalized
notional is 1. For each interval:

```text
gross_price_return = position * ((close / open) - 1)
funding_return = -position * sum(eligible held funding rates)
turnover = abs(position - prior_position)
net_return = gross_price_return + funding_return
             - turnover * (frozen_taker_fee + 0.0002)
```

A direct reversal has turnover 2. There is no compounding in the primary
statistic. Terminal liquidation charges `abs(final_position) *
(frozen_taker_fee + 0.0002)`. At later data freezing, retrieve and hash the
official Binance USD-M VIP-0 taker fee; freeze the fee as
`max(official_documented_VIP0_taker_fee, 0.0005)`. Maker fees and favorable
tiers are forbidden. Cost stress is 1.0x base, 1.5x stress-1, and 2.0x stress-2;
funding cashflows are not stress-multiplied. Primary testing uses base cost and
stress-1 survival is required.

## Primary statistic and diagnostics

The sole primary statistic is mean net return per all evaluated 8-hour
intervals. Flat intervals remain in the denominator. Secondary diagnostics are
active intervals, entries, long/short intervals, exposure, turnover, gross
price, funding, trading cost, cumulative net return
`product(1 + net_return) - 1`, and maximum drawdown. Controls, gross/net,
funding/price, long/short, half-year stability, drawdown, turnover, exposure,
stress-2, and development-derived volatility/funding regimes are secondary;
regime thresholds use development data only and cannot rescue primary failure.

## Validation test and selection

Use one synchronous stationary-bootstrap maximum-t family test across the nine
variants, preserving cross-variant dependence. Center each series under the
zero-mean null. Use 10,000 replicates, expected block length 63 intervals,
Newey-West HAC lag 21, one-sided alternative mean net return > 0, family-wise
alpha 0.05, and p-value `(1 + exceedance_count) / (1 + 10000)`. The seed is the
integer represented by the first 16 hex characters of
`SHA256(protocol_id + ":validation:max-t:v0")`. Record Python version,
dependency-lock identity, seed, repetitions, block length, HAC lag, and result
byte hashes.

A variant is validation-eligible only when adjusted p <= 0.05; base and stress-1
mean net return are positive; active intervals >= 100; entries >= 20; base mean
net return is positive in both 2023 and 2024; and no month contributes over 50%
of total positive validation net contribution. If none qualifies, classify
`H001_FAILED_VALIDATION` and keep holdout sealed. If several qualify, choose the
highest validation mean base-cost net return, then lower turnover, lower
lookback, higher price deadband, higher funding deadband, and lexicographically
smaller variant ID. Preserve all nine results and adjusted p-values.

## Holdout test and confirmation

Evaluate only the selected variant using a single-series stationary-bootstrap
t-test: 10,000 replicates, expected block length 63, HAC lag 21, one-sided mean
net return > 0, alpha 0.05. Seed it with the integer represented by the first
16 hex characters of `SHA256(protocol_id + ":holdout:selected:v0")`.

Confirmation requires p <= 0.05, positive base and stress-1 mean net return,
at least 50 active intervals, at least 10 entries, positive base mean net return
in at least two of 2025-H1, 2025-H2, and 2026-H1, and no half-year contributing
over 60% of total positive holdout net contribution. Do not test another variant
after holdout failure and do not reopen validation selection.

## Classifications

- `H001_FAILED_VALIDATION`: validation integrity passes but no variant meets all
  validation gates.
- `H001_FAILED_HOLDOUT`: one variant is selected but fails any holdout gate.
- `H001_INCONCLUSIVE_DATA`: data-integrity or temporal-join failure.
- `H001_INCONCLUSIVE_ACTIVITY`: insufficient eligible history or required
  activity despite correct execution.
- `H001_INCONCLUSIVE_CUSTODY`: fee documentation or two-copy custody failure.
- `H001_INCONCLUSIVE_IMPLEMENTATION`: artifact or environment binding failure.
- `H001_SURVIVED_PREREGISTERED_REAL_FALSIFICATION_V0`: only when one selected
  variant passes every validation and holdout gate. Survival does not prove edge
  or authorize paper/live trading or capital allocation.

## Trial accounting

Nine synthetic variants were previously explored mechanically; nine real
validation candidate tests are disclosed; at most one validation-selected
holdout candidate test is allowed; six controls are disclosed. Later
authorization permits exactly one validation execution and, conditionally,
exactly one holdout execution. Current authorized executions are 0. Any
validation or holdout statistic computation consumes its execution even if the
result is inconvenient or not retained. Byte-identical replay is allowed only
when no result was exposed and a deterministic infrastructure failure is proven
by retained logs; otherwise a new protocol version and permanent amendment
history are required.

## Custody, stop conditions, and future execution sequence

Before execution, two independent qualified durable stores must be configured;
raw files must be stored, independently restored, and rehashed in both; a
portable canonical manifest must match raw and parsed hashes and this design;
joinability must pass without strategy computation; cost documentation,
implementation commit, dependency environment, and bootstrap implementation
must be frozen and reviewed; and a final no-computation preflight plus later
governance authorization must pass. No canonical path may be under `/tmp`,
`/srv/qnty`, or the Git repository. This design creates no artifact identity or
data file.

Stop before performance computation on manifest/raw/parsed hash mismatch,
fewer than two verified copies, wrong venue/contract/date/columns, duplicate or
non-monotonic timestamps, cadence gaps, funding staleness over 12 hours,
ambiguous timestamps, noncanonical timezone, unavailable fee documentation,
implementation/environment/seed/trial-accounting mismatch, or absent
authorization.

The future sequence is: independent design review; separately authorize and
freeze custody; restore and verify both copies; freeze fee, implementation, and
environment bindings; run no-computation preflight; obtain explicit validation
authorization; execute validation once; classify or select; if eligible,
obtain the conditional holdout authorization; unseal and execute the selected
holdout once; classify; publish retained results and hashes. No step grants
scientific, paper, or live authorization.

## Amendment policy and prohibited interpretations

Before any validation result exists, material changes require an append-only
amendment, independent review, and new hashes. After any validation result is
exposed, material amendment is forbidden; a changed rule, variant, split, cost,
statistic, null, threshold, or selection rule is a new hypothesis/protocol that
retains this protocol's result.

Synthetic success is not market evidence; validation success alone is not
confirmation; an uncorrected attractive variant is not evidence; secondary
diagnostics cannot overturn primary failure; inconclusive is not positive;
holdout failure cannot be repaired by testing another variant; and survival is
not proof of stable edge or authorization to trade.
