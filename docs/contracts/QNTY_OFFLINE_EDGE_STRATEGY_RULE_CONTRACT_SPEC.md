# QNTY_OFFLINE_EDGE_STRATEGY_RULE_CONTRACT_SPEC

## 1. Status

- **Spec type:** contract-form specification
- **Contract instance:** `NOT_DEFINED`
- `contract_status` remains `CONTRACT_NOT_DEFINED`
- `scoring_authorized` remains `false`
- `final_offline_verdict` remains `BLOCKED_BY_VALIDATION_IMPLEMENTATION`
- `EDGE_UNPROVEN` remains
- `BLOCK_LIVE_INTEGRATION` remains

This document defines **no strategy** and authorizes **no scoring**. It describes the
*form* a strategy rule contract must take. It is not a contract instance, and nothing
in it may be read as a strategy, a signal, a parameter choice, or a permission to score.

Base of record: `c1251f5ba9ca0a2386b2a5eaf4b805d8d5f33b15` (`origin/main` after PR #207).
All code facts below were read from that commit.

---

## 2. Purpose

The strategy rule contract is the **root contract that makes any future score
interpretable**. Without it, a number produced by a scorer has no meaning: there is
nothing that says which inputs were legal, what instant the decision was taken, how far
back features could look, how far forward a label could reach, or how many free
parameters were burned to obtain it. A score without those constraints is not a weak
result — it is an *uninterpretable* one.

The contract therefore defines **admissibility before any score exists**. It fixes what
would count as a legal strategy evaluation, and it does so *in advance*, so that the
constraints cannot be reverse-fitted to a result that has already been seen.

It is a **constitution for future strategy evaluation, not an entry/exit
implementation.** It says what a strategy *may* do and what it may *never* do. It does
not say what the strategy *is*. A constitution that is written after the verdict is not
a constitution.

---

## 3. Existing receipt field vocabulary

The canonical runner (`quantbot/experiment/offline_edge_real_validation.py`,
`_build_strategy_rule_contract_diagnostics`) **already emits** a
`strategy_rule_contract_diagnostics` section. This spec **extends those names**. It does
not replace them.

Fields already emitted today, which must be preserved:

```
contract_version
calculation_status
contract_status
scoring_authorized
scoring_blocked_reason

allowed_input_roles
allowed_input_columns
forbidden_input_roles
forbidden_input_columns
forbidden_future_columns

decision_time_convention
decision_time_column
decision_time_offset

feature_lookback
feature_lookback_bars
label_horizon
label_horizon_bars
holding_period
holding_period_bars

side_semantics
side_source
notional_semantics
notional_source
notional_currency

cost_dependency
funding_dependency

scoring_prerequisites_present
```

Every one of these is currently `None`, `NOT_DEFINED`, or `False`. The section is a
**diagnostic of absence**, not a definition of presence.

**Do not rename these to parallel vocabulary** such as `signal_inputs_allowed` or
`timestamp_policy`. A parallel name does not add a field; it forks the schema. Two names
for one concept means two things to keep in sync, two things to test, and eventually two
answers to the same question. **That is schema drift, and it is the failure mode this
spec exists to prevent.**

`scoring_prerequisites_present` is a nested map whose six keys are today all `False`:
`decision_time_convention`, `feature_lookback`, `label_horizon`, `holding_period`,
`funding_interval_exposure`, `cost_event_timing`.

---

## 4. Verified runner input ceiling

The canonical runner materializes **only**:

**bars**
- `timestamp`
- `close`

**funding**
- `fundingTime`
- `fundingRate`

Therefore the **honest `allowed_input_columns` ceiling today** is exactly:

```
timestamp
close
fundingTime
fundingRate
```

**A future contract must not name columns the harness does not materialize.** A contract
that references `open`, `high`, `low`, `volume`, order-book depth, trade prints, or any
other field is not describing this harness. It is describing an imagined one. Naming a
column the runner cannot supply is not an ambitious contract; it is a false one, and it
is a kill criterion (§16).

The ceiling may rise **only** by a separate, single-purpose PR that actually widens what
the runner materializes. The contract follows the harness. The harness does not follow
the contract.

---

## 5. Required contract identity and freeze fields

A future contract instance must carry:

```
contract_id
contract_version
contract_status
contract_hash
contract_source_path
contract_frozen
contract_frozen_at_utc
contract_commit_sha
```

**Why freeze and hash matter:** a trial manifest cannot bind to an *immutable* strategy
rule contract unless the contract is frozen, committed, and hash-addressed. If the
contract can be edited after a score is seen, then the constraints are not constraints —
they are a narrative fitted to the outcome. Hash-addressing is what makes "we
pre-committed to this" a checkable claim instead of an assertion.

`contract_hash` must be the hash of the **contract bytes as committed in git**, and
`contract_commit_sha` must be a commit that **contains those bytes**. Either one alone
is insufficient: a hash with no commit proves nothing about *when*, and a commit with no
hash proves nothing about *what*.

---

## 6. Required strategy declaration fields

Declaration-only fields:

```
strategy_family
strategy_candidate_id
hypothesis_id
decision_cadence
symbol_universe_policy
symbol_universe_frozen
```

**Hard boundary.** These fields **declare** the strategy family and universe policy.
They do **not** implement entry rules, exit rules, signals, trades, positions, orders,
fills, execution, or sizing. Declaring "this is a funding-carry family, on an 8h cadence,
over a frozen symbol universe" is metadata. It is not a strategy, and it computes
nothing.

`strategy_candidate_id` and `hypothesis_id` already appear in the trial-manifest
diagnostics vocabulary; they are reused here deliberately so that a contract and a trial
manifest can be cross-checked for agreement rather than each carrying a private name.

`symbol_universe_frozen` must be `true` before scoring is conceivable: a universe chosen
after seeing which symbols worked is survivorship selection wearing a contract's clothes.

---

## 7. Required input and data-source fields

Reuse the existing names:

```
allowed_input_roles
allowed_input_columns
forbidden_input_roles
forbidden_input_columns
forbidden_future_columns
```

Add:

```
allowed_data_sources
forbidden_data_sources
```

**Allowed data sources** are CSV replay inputs declared by the validation lane — nothing
else.

**Forbidden data sources** include the paper ledger, live exchange data, output
directories, generated receipts, report outputs, and **any data source not explicitly
declared**. The default is denial: a source that is not on the allow-list is forbidden,
whether or not anyone remembered to enumerate it. An allow-list that fails open is not
an allow-list.

---

## 8. Required time and causality fields

Reuse the existing names:

```
decision_time_convention
decision_time_column
decision_time_offset
feature_lookback
feature_lookback_bars
label_horizon
label_horizon_bars
holding_period
holding_period_bars
```

Add:

```
warmup_bars
funding_interval_exposure_policy
```

**The causal rule:**

> **No input observable after `decision_time` may enter the decision.**

This is the single rule the whole ladder rests on. Every look-ahead bug that has ever
manufactured a fake edge is a violation of exactly this sentence. `feature_lookback` and
`warmup_bars` bound what may be read *backwards*; `label_horizon` and `holding_period`
bound what is being predicted *forwards*; `decision_time_offset` fixes the boundary
between them. `funding_interval_exposure_policy` exists because funding accrues over an
interval, and an interval that straddles `decision_time` is precisely where future
information leaks in while looking innocent.

---

## 9. Complexity and search budget

Add:

```
complexity_budget:
  free_parameter_count
  declared_parameter_names
  max_free_parameters

parameter_policy
hyperparameter_search_policy
trial_count_policy
```

**At contract-spec stage, `hyperparameter_search_policy` must be `NO_SEARCH`.**

The contract may define **how a search would be declared later**. It must not **perform**
a search, and it must not **authorize** one.

**Why the complexity budget is mandatory:** later multiple-testing and Deflated-Sharpe
style controls can only be honest if the model's degrees of freedom and the size of the
search space are known *and were declared in advance*. A trial count reconstructed after
the fact is a guess, and a guess always flatters the researcher — the trials that were
abandoned are exactly the ones nobody writes down. `free_parameter_count` must agree with
`declared_parameter_names` (§16); a budget that does not tie out to a name list is a
budget that can absorb any number of quiet extra knobs.

---

## 10. Semantics

Reuse the existing names:

```
side_semantics
side_source
notional_semantics
notional_source
notional_currency
cost_dependency
funding_dependency
```

These are **semantic declarations only**. They state what a side *would mean* and what a
notional *would be denominated in*. They do **not** authorize trades, positions, orders,
fills, execution, PnL, risk, equity, or benchmark comparison. Declaring that notional
would be quoted in USDT is a statement about units. It is not a position.

`cost_dependency` and `funding_dependency` are `NOT_DEFINED` today and remain so.

---

## 11. Output boundary

Add:

```
output_boundary
forbidden_output_keys
receipt_key_naming_constraint
scoring_authorization
```

**The contract may define admissibility only.** It may **not** emit values used as
performance, edge, profitability, returns, PnL, equity, risk, drawdown, Sharpe,
benchmark, or live-readiness outputs.

`forbidden_output_keys` **must mirror the forbidden calculation-key scanner**
(`FORBIDDEN_CALCULATION_KEYS`, `_assert_no_forbidden_calculation_keys`). "Mirror" means
*mirror the code as it actually is* — not an aspirational list. Below is the scanner's
**actual enforced set**, which is what `forbidden_output_keys` must reflect today.

The previously reserved names have now been **appended** to the scanner by a single-purpose
append-only PR. The enforced set moved from **22 keys to 42 keys**. No key was removed or
renamed; the scanner is strictly stronger.

**Enforced today — exact dict-key match, at any nesting depth (42 keys):**

```
pnl                 sharpe              edge                strategy_performance
return              returns             gross_observational_return
gross_return_value  net_return_value    cost_adjusted_return
funding_adjusted_return                 price_change
trade               trades              signal              signals
position            positions           portfolio
live_ready          deploy_ready        profitable
drawdown            risk                baseline_result     benchmark_result
OFFLINE_EDGE_CANDIDATE                  EDGE_CANDIDATE
p_value             confidence_interval score
metric              performance         profit
order               orders              fill                fills
execution           executions          equity              equity_curve
```

`OFFLINE_EDGE_CANDIDATE` and `EDGE_CANDIDATE` are forbidden **dict keys** only. This is
defense-in-depth against verdict-named maps (e.g. a `{"OFFLINE_EDGE_CANDIDATE": {...}}`
block smuggled into a receipt). It is **not** verdict enforcement: verdict control remains
owned by `ALLOWED_FINAL_VERDICTS` / `_SKELETON_ALLOWED_VERDICTS` and the verdict
validators, which are untouched.

Additionally, `FORBIDDEN_TOP_LEVEL_KEYS` (`pnl`, `sharpe`, `edge`,
`strategy_performance`) are rejected at the receipt root.

**Matching is exact dict-key equality only** — no substring, prefix, regex, or
case-insensitive matching. Sibling names that merely *contain* a forbidden name are
accepted by design and remain valid contract field names (e.g. `max_drawdown`,
`drawdown_policy`, `order_timing_policy`, `fill_policy`, `equity_curve_policy`,
`risk_measure_policy`, `sharpe_or_risk_metric`).

**One narrow exemption exists in code:** the key `gross_observational_return` is permitted
**only** under the receipt path prefix `$.gross_observational_returns`. Everywhere else it
is forbidden. **This exemption is unchanged by the append** — its behavior is byte-for-byte
the same, and it remains key-scoped, not section-wide (a `pnl` key nested inside
`gross_observational_returns` is still rejected). A contract field must not rely on or
widen this exemption.

**Known gap, deliberately deferred:** the exemption is implemented with a `startswith`
path check, so a sibling section whose path merely *begins with* the exempt prefix could
inherit the exemption. Tightening this prefix-hole is **intentionally out of scope here**
and is deferred to a separate single-purpose PR, so that this change stays purely
append-only and no existing semantics shift underneath it.

**Reserved names — none outstanding:**

The reserved block is retained as the designated home for any *future* semantically
forbidden name that is not yet enforced. **After this append, no additional reserved names
are listed** — the reserved set is empty, and the spec's output boundary and the scanner's
enforced set are in agreement.

```
(none)
```

Any future name added here must be recorded as reserved **until** a single-purpose PR
appends it to the scanner. Stating that a name is enforced when it is not would itself be
a false receipt claim. Widening the scanner is **append-only** work for a separate PR.

**`receipt_key_naming_constraint`:** contract field names must **survive recursive
exact-key scanning**. The scanner is **append-only and must never be weakened to
accommodate a contract.** If a contract field name collides with a forbidden key,
**rename the contract field** — never the scanner. The scanner is the control; the
contract is the thing being controlled. Loosening the control to fit the controlled
object inverts the entire safety argument.

`scoring_authorization` remains `false`.

---

## 12. Dependency relations

Explicit false relations:

```
trial_manifest_dependency_satisfied            = false
oos_seal_dependency_satisfied                  = false
null_benchmark_dependency_satisfied            = false
multiple_testing_dependency_satisfied          = false
split_scoring_safe_dependency_satisfied        = false
trade_position_simulation_dependency_satisfied = false
net_pnl_equity_risk_dependency_satisfied       = false
live_integration_authorized                    = false
```

**These must remain `false` until each downstream gate is separately defined and
verified.** Each `false` is a specific, named thing that does not exist yet. Flipping one
to `true` is a claim that a particular gate was built and checked — it is never a
formality, and never a side effect of unrelated work.

---

## 13. Split and leakage relation

**Split policy and leakage controls are owned by `split_leakage_audit_diagnostics`.**

Current known state, read from the base commit:

- `purge_gap_seconds = 0`
- `embargo_gap_seconds = 0`
- `split_scoring_safe = false`

There is **no purge and no embargo today.** The splits are adjacent, and `split_scoring_safe`
is computed as a conjunction that includes an OOS seal, a trial manifest, and a frozen
symbol universe — none of which exist. It is `false` by construction, not by accident.

The strategy rule contract **may reference split safety**, but it must **not redefine
split policy** and must **not create a parallel leakage-control vocabulary.** One owner
per concept. A contract that carries its own private notion of "safe splits" would let a
future scorer satisfy the contract while violating the audit.

---

## 14. Static gate warning

**The downstream gates are currently static absence records. They do not read the strategy
rule contract.** They are hardcoded `False` values that describe a world in which nothing
has been built yet — which is the true world.

Making gates **derive** readiness from a real, validated contract is a **separate,
single-purpose future PR** (§17, lane D).

> **A gate flipping `true` without a real frozen contract is an attack, not progress.**

The danger is precise: because the gates are static, a one-character edit can make every
readiness flag report `true` while nothing whatsoever has been validated. That edit would
look like progress in a diff and would be catastrophic in meaning. Any PR that turns a
gate `true` must show the contract it read, the hash it bound to, and the validator that
accepted it.

---

## 15. Test-surface warning

`TestStrategyRuleContractDiagnostics` (in
`tests/experiment/test_offline_edge_real_validation.py`) currently **pins the absence
state**. As of the base commit it holds **38 test methods and 42 assert statements**.
(The working figure of "38" refers to the test methods; the assert-statement count is 42.
Both are recorded here so that a future PR reconciles against the real numbers.)

Emitting a **real** strategy rule contract into the receipt would require a **separate,
single-purpose PR** that **re-specifies** those tests — because they currently assert, by
design, that every contract field is `None` / `NOT_DEFINED` / `False`.

**Those tests must not be weakened, skipped, `xfail`ed, or deleted.** They are the tripwire
that makes the absence claim checkable. A PR that makes them pass by removing them has
removed the only evidence that the absence was ever real. Re-specification means replacing
"assert absent" with an equally strict "assert exactly this frozen, hashed, validated
contract" — never with silence.

---

## 16. Contract kill criteria

A contract instance is **void** — and any score derived from it is void — if any of the
following hold. These are stated so that a contract can be *killed by evidence* rather
than defended by argument.

- Contract references any input column the runner does not materialize (§4).
- Contract field name collides with the forbidden exact-key scanner (§11).
- Contract edited after its freeze timestamp.
- Contract hash does not match the bytes in git.
- `contract_commit_sha` does not contain the contract bytes.
- `free_parameter_count` disagrees with `declared_parameter_names`.
- Trial manifest references a different contract hash.
- `decision_time` policy allows future information (§8).
- A forbidden data source is used (§7).
- A live / paper / exchange path is used.
- The output boundary emits scoring / performance / edge-like values (§11).

---

## 17. Lane sequence

Expected future lane sequence. Each lane is a **separate, single-purpose PR**.

| Lane | Work | Gate state |
|---|---|---|
| **A** | Docs-only strategy rule contract spec — **this PR** | absence unchanged |
| **B** | Contract instance v1 committed and hashed, **still not read by the runner** | absence unchanged |
| **C** | Loader + validator + receipt binding, **with test re-specification** (§15) | contract becomes readable |
| **D** | Gate de-staticization — downstream gates **derive** readiness from validated contract state (§14) | gates become real |
| **E** | Trial manifest binds to `contract_hash` | manifest gate |
| **F** | OOS seal | seal gate |
| **G** | Null benchmark contract | benchmark gate |
| **H** | Multiple-testing control | multiplicity gate |
| **I** | Trade / position simulation contract | simulation gate |
| **J** | Net PnL / equity / risk contract | PnL gate |
| **K** | **Final verdict advancement logic — only after all upstream gates are real and verified** | verdict may move |

Lane K is last for a reason. A verdict produced before lanes B–J are real would be a
verdict about nothing.

---

## 18. Hard boundaries

- **No** strategy implementation.
- **No** signal calculation.
- **No** trade / position / order / fill / execution logic.
- **No** returns, PnL, equity, drawdown, risk, Sharpe, benchmark, or edge computation.
- **No** final scoring.
- **No** `final_offline_verdict` advancement.
- **No** report promotion.
- **No** live / paper integration expansion.
- **No** exchange keys.
- **No** data refresh.
- **No** source CSV mutation.
- **No** generated receipts.
- **No** runtime imports from `quantbot/strategy/**`, `runner.py`, `walkforward_runner.py`,
  `pbo.py`, `quantbot/paper/**`, `quantbot/execution/**`, or `quantbot/exchange/**`.

---

## Closing

`EDGE_UNPROVEN` remains.
`BLOCK_LIVE_INTEGRATION` remains.
`final_offline_verdict` remains `BLOCKED_BY_VALIDATION_IMPLEMENTATION`.
`contract_status` remains `CONTRACT_NOT_DEFINED`.
`scoring_authorized` remains `false`.

**This spec proves no edge, no profitability, no OOS safety, and no live readiness.**
It defines a form. A form is not a result.
