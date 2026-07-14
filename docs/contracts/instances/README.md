# Strategy Rule Contract Instance — Freeze Packet v1

## Lane B Artifact

This directory contains the frozen declaration-only strategy rule contract instance
for the offline-edge validation ladder.

**Lane B** per the spec (§17): *"Contract instance v1 committed and hashed, still not
read by the runner."*

## Files

| File | Purpose |
|---|---|
| `qnty_offline_edge_strategy_rule_contract_v1.json` | Contract payload (declaration-only) |
| `qnty_offline_edge_strategy_rule_contract_v1.sha256` | SHA-256 sidecar of the exact JSON bytes |

## How the contract is frozen

The contract payload is frozen by **file bytes + sidecar hash**:

1. The JSON file is written with deterministic formatting (`sort_keys=True`, `indent=2`,
   trailing newline).
2. The SHA-256 of the exact file bytes is computed and stored in the `.sha256` sidecar.
3. The JSON `contract_hash` field is set to the literal marker `"FROZEN_IN_SIDECAR"`.
   Embedding the digest of the same JSON bytes would create a self-referential loop;
   the authoritative digest is the `.sha256` sidecar.

### Self-hash limitation

The spec (§5) requires `contract_hash` to be the hash of the contract bytes as
committed in git. This creates a circular dependency: the hash cannot be known until
the file is written, and writing the hash into the file changes the bytes.

**Resolution:** The contract uses a two-part packet:

- `contract_hash` is set to the literal marker `"FROZEN_IN_SIDECAR"` because embedding
  the digest of the same JSON bytes would create a self-referential loop.
- `contract_hash_status = "FROZEN_IN_SIDECAR"` — the authoritative hash lives in the
  sidecar file.
- `contract_hash_scope = "exact committed JSON bytes, excluding sidecar"` — the scope
  is unambiguous.

### Merge-commit limitation

`contract_commit_sha` is set to `"TO_BE_FILLED_AFTER_MERGE"` because the final merge
commit SHA cannot be known before the PR is merged. After merge, this field should be
updated to the actual merge commit SHA that contains these file bytes.

## Input ceiling

`allowed_input_columns` is constrained to the verified runner input ceiling:

| Role | Columns |
|---|---|
| `bars` | `timestamp`, `close` |
| `funding` | `fundingTime`, `fundingRate` |

Unavailable columns are documented in `non_materialized_input_columns` but are
**not** allowed inputs. No strategy implementation reads these columns, no signal
depends on them, and no scoring uses them.

## Output-boundary fields

The contract includes declaration-only output-boundary fields (`output_boundary`,
`forbidden_output_keys`, `receipt_key_naming_constraint`) as required by the spec (§11).

These fields:
- Are **declarative only** — no receipt emits them, no validator enforces them yet.
- `forbidden_output_keys` mirrors the 42-key `FORBIDDEN_CALCULATION_KEYS` scanner
  as string values (not dict keys), which is permitted by the scanner's exact
  dict-key-match rule.
- Lane C will decide the exact runtime binding and validator semantics.

## What this PR does NOT do

- This PR (Lane B) did **not** read the contract.

## Lane C1 — diagnostic loading (merged in ``contract/strategy-rule-contract-loader-c1``)

Lane C1 adds the ability for the runner to **read and hash-check** the frozen contract
packet, emitting a diagnostic-only section into the offline-edge validation receipt.

What Lane C1 does:

- Loads the contract JSON and SHA-256 sidecar at runtime.
- Verifies JSON parseability, sidecar format, and SHA-256 binding.
- Scans all dict keys against the `FORBIDDEN_CALCULATION_KEYS` (42 keys).
- Checks that `allowed_input_columns` matches the verified runner ceiling
  (bars: `timestamp`, `close`; funding: `fundingTime`, `fundingRate`).
- Checks that output-boundary fields (`output_boundary`, `forbidden_output_keys`,
  `receipt_key_naming_constraint`) are present.
- Checks that all downstream dependency booleans are `false`.
- Reports diagnostic statuses including ``contract_runner_read_status``,
  ``contract_commit_sha_binding_status``, ``contract_scoring_ready``,
  ``contract_validation_status``.

What Lane C1 does **not** do:

- No scoring, strategy implementation, signal calculation, PnL, or edge.
- No live-readiness or exchange integration.
- **Does not solve the `contract_commit_sha` self-reference problem.**
  The commit SHA field value remains ``TO_BE_FILLED_AFTER_MERGE``. Editing it
  inside the same JSON file creates a commit self-reference: changing the bytes
  produces a new SHA, which cannot be known pre-merge. The diagnostic reports
  ``contract_commit_sha_binding_status = "UNRESOLVED_SELF_REFERENCE_PLACEHOLDER"``
  and ``contract_commit_sha_bound = false``.
- No gates flip true. ``contract_scoring_ready``, ``contract_instance_readiness``,
  and ``contract_commit_sha_bound`` are all ``false``.
- ``final_offline_verdict`` remains ``BLOCKED_BY_VALIDATION_IMPLEMENTATION``.
- ``EDGE_UNPROVEN`` and ``BLOCK_LIVE_INTEGRATION`` remain.
- ``scoring_authorization`` remains ``false``.

CLI arguments (optional):

- ``--strategy-contract-path`` — path to the frozen contract JSON.
- ``--strategy-contract-sha256-path`` — path to the SHA-256 sidecar.

If both arguments are supplied, the materializer runs and the diagnostic section
appears in the receipt. If either is omitted, the existing ``CONTRACT_NOT_DEFINED``
diagnostic is emitted (unchanged).

### Lane C2 — non-self-referential commit-containment binding (this PR)

Lane C2 adds a **commit-binding sidecar** that proves the frozen contract bytes
existed in a prior git commit, without editing the contract JSON and without
creating a commit-SHA self-reference loop.

**Key design rule:** Do not put the current PR's future merge commit SHA inside
a file that will be part of that same merge commit. That is self-referential
and invalid.

**Solution:** A separate binding sidecar that points to a **prior commit already
on main** that contains the frozen contract JSON bytes.

**Prior containing commit:** ``f6e2c27ccc9271ca3587895fddd165f76eda784d``
(PR #211 merge commit that introduced the contract packet).

**New file:**

| File | Purpose |
|---|---|
| ``qnty_offline_edge_strategy_rule_contract_v1.commit_binding.json`` | Non-self-referential prior-commit containment binding |

**What the binding sidecar contains:**

- ``contract_containing_commit_sha`` — the prior main merge commit SHA
- ``contract_sha256`` — the expected SHA-256 digest of the contract bytes
- ``contract_id`` — must match the contract JSON's ``contract_id``
- ``contract_source_path`` — repo-relative path to the contract JSON
- Metadata fields documenting the binding model and self-reference avoidance

**What the loader verifies (when ``--strategy-contract-commit-binding-path`` is supplied):**

1. Loads and parses the commit-binding JSON.
2. Verifies all required binding fields exist.
3. Scans binding sidecar dict keys against the 42-key ``FORBIDDEN_CALCULATION_KEYS`` scanner.
4. Verifies ``contract_id`` matches the contract JSON.
5. Verifies ``contract_source_path`` matches the expected repo-relative path.
6. Verifies ``contract_sha256`` equals the computed SHA-256 of the current contract JSON bytes.
7. Verifies ``contract_sha256`` equals the ``.sha256`` sidecar digest.
8. Verifies ``contract_containing_commit_sha`` is exactly 40 hex characters.
9. Uses ``git show <commit_sha>:<path>`` to read the blob at the prior commit.
10. Hashes the blob and compares to ``contract_sha256``.

**Diagnostic statuses when binding succeeds:**

- ``contract_commit_sha_bound = true``
- ``contract_commit_sha_binding_status = "BOUND_BY_PRIOR_COMMIT_CONTAINMENT_SIDECAR"``
- ``contract_commit_binding_read = true``
- ``contract_commit_binding_model = "sidecar_points_to_prior_commit_containing_exact_contract_bytes"``
- ``contract_containing_commit_sha = "f6e2c27ccc9271ca3587895fddd165f76eda784d"``
- ``contract_containing_commit_path_verified = true``
- ``contract_containing_commit_digest_matches = true``
- ``contract_instance_readiness = false``
- ``contract_scoring_ready = false``
- ``contract_validation_status = "COMMIT_BOUND_DIAGNOSTIC_ONLY_NOT_SCORING_READY"``

**Critical:** Even when commit binding succeeds, scoring readiness remains
``false``. This PR only solves containment. It does not solve trial manifest,
OOS seal, null benchmark, multiple testing, simulation, net PnL, or final
verdict advancement.

**CLI argument (optional):**

- ``--strategy-contract-commit-binding-path`` — path to the commit-binding sidecar JSON.

**Rules:**

- No contract args: previous absence behavior unchanged.
- Contract + sha256 args only: C1 behavior unchanged; commit binding unresolved/false.
- Contract + sha256 + commit binding args: C2 containment validation runs; commit
  binding may become ``true``, but scoring readiness remains ``false``.

**What Lane C2 does NOT do:**

- No scoring, strategy implementation, signal calculation, PnL, or edge.
- No live-readiness or exchange integration.
- Does not edit the contract JSON or its SHA-256 sidecar.
- Does not flip ``scoring_authorization``, ``contract_scoring_ready``, or
  ``contract_instance_readiness`` to ``true``.
- ``final_offline_verdict`` remains ``BLOCKED_BY_VALIDATION_IMPLEMENTATION``.
- ``EDGE_UNPROVEN`` and ``BLOCK_LIVE_INTEGRATION`` remain.

### Lane C3 and beyond

Lane C3 or later can use this binding to move from "commit placeholder unresolved"
to "commit-bound diagnostic-only," but all upstream gates still remain false.
Future lanes must still solve trial manifest, OOS seal, null benchmark, multiple
testing control, trade/position simulation, net PnL/equity/risk contract, and
final verdict advancement.

### Lane D1 — contract-packet gate projection (this PR)

Lane D1 adds a **derived contract-packet gate** that compresses the C2 diagnostic
evidence into a single gate object. This is a pure diagnostic projection — it never
reads files, calls git, or mutates the diagnostics.

**What Lane D1 does:**

- Adds a pure helper ``_derive_strategy_rule_contract_packet_gate(diagnostics)``
  that derives the gate from the existing strategy-rule contract diagnostics.
- The gate is automatically added inside ``strategy_rule_contract_diagnostics``
  at build time (no separate integration step).
- The gate can pass only when C2 commit binding verifies — all of:

  * ``contract_packet_read`` is ``True``
  * ``sidecar_digest_matches_json_bytes`` is ``True``
  * ``forbidden_dict_key_scan_passed`` is ``True``
  * ``input_ceiling_check_passed`` is ``True``
  * ``output_boundary_fields_present`` is ``True``
  * ``downstream_dependency_booleans_all_false`` is ``True``
  * ``contract_commit_sha_bound`` is ``True``
  * ``contract_commit_sha_binding_status`` is ``"BOUND_BY_PRIOR_COMMIT_CONTAINMENT_SIDECAR"``
  * ``contract_containing_commit_digest_matches`` is ``True``
  * ``scoring_authorization`` is ``False``
  * ``live_integration_authorized`` is ``False``
  * ``contract_instance_readiness`` is ``False``
  * ``contract_scoring_ready`` is ``False``

**Gate shape when passed:**

```json
"contract_packet_gate": {
  "gate_kind": "strategy_rule_contract_packet_gate",
  "gate_scope": "CONTRACT_PACKET_EXISTENCE_HASH_AND_COMMIT_BINDING_ONLY",
  "gate_status": "CONTRACT_PACKET_COMMIT_BOUND_DIAGNOSTIC_ONLY",
  "gate_passed": true,
  "gate_scoring_authorization": false,
  "gate_live_authorization": false,
  "gate_final_verdict_authorization": false,
  "gate_downstream_unlocks": [],
  "evidence": { ... },
  "blocked_reason": null
}
```

**What Lane D1 does NOT do:**

- No scoring, strategy implementation, signal calculation, PnL, or edge.
- No live-readiness or exchange integration.
- ``gate_scoring_authorization``, ``gate_live_authorization``, and
  ``gate_final_verdict_authorization`` are always ``false``.
- ``gate_downstream_unlocks`` is always an empty list.
- Does not flip ``contract_instance_readiness`` or ``contract_scoring_ready``.
- ``final_offline_verdict`` remains ``BLOCKED_BY_VALIDATION_IMPLEMENTATION``.
- ``EDGE_UNPROVEN`` and ``BLOCK_LIVE_INTEGRATION`` remain.
- Trial manifest, OOS seal, null benchmark, multiple testing, simulation,
  net PnL/equity/risk gates remain false.

## Verification

```bash
# Validate JSON
python3 -m json.tool qnty_offline_edge_strategy_rule_contract_v1.json > /dev/null

# Verify SHA-256 sidecar
cd docs/contracts/instances && sha256sum -c qnty_offline_edge_strategy_rule_contract_v1.sha256

## Lane E1 — Trial Manifest Pre-Registration Packet

This directory also contains the frozen trial manifest pre-registration packet
for the offline-edge validation ladder.

**Lane E1** per the spec: *"Trial manifest pre-registers candidate/trial count,
binds to contract digest and contract packet gate, no hyperparameter search,
one authorized trial declaration, diagnostic-only."*

### Files

| File | Purpose |
|---|---|
| `qnty_offline_edge_trial_manifest_v1.json` | Trial manifest payload (pre-registration only) |
| `qnty_offline_edge_trial_manifest_v1.sha256` | SHA-256 sidecar of the exact JSON bytes |

### What Lane E1 does

- Pre-registers a single no-search trial declaration (`funding_carry_v1_declaration_only`).
- Binds to the frozen strategy contract digest and requires the contract packet gate.
- Declares `authorized_trial_count = 1`, `trial_count_frozen = true`,
  `hyperparameter_search_policy = "NO_SEARCH"`, `free_parameter_count = 0`.
- All authorization booleans are `false`:
  `trial_execution_authorized`, `scoring_authorization`,
  `live_integration_authorized`, `paper_integration_authorized`,
  `final_verdict_authorization`.
- All downstream dependency booleans are `false`:
  `oos_seal_dependency_satisfied`, `null_benchmark_dependency_satisfied`,
  `multiple_testing_dependency_satisfied`,
  `trade_position_simulation_dependency_satisfied`,
  `net_pnl_equity_risk_dependency_satisfied`.

### What Lane E1 does NOT do

- No scoring, PnL, outcomes, strategy execution, signal generation,
  live/paper/exchange integration, or verdict advancement.
- `trial_manifest_readiness` remains `false`.
- `trial_scoring_ready` remains `false`.
- `EDGE_UNPROVEN`, `BLOCK_LIVE_INTEGRATION`, and
  `BLOCKED_BY_VALIDATION_IMPLEMENTATION` remain.
- OOS/null/multiple-testing/simulation/net-PnL gates remain false.

### Lane F1 — OOS Seal Pre-Scoring Declaration Packet

This directory also contains the frozen OOS seal pre-scoring declaration packet
for the offline-edge validation ladder.

**Lane F1** per the spec: *"OOS seal pre-scoring declaration packet that
declares the out-of-sample boundary and split-lock policy before any scoring
exists."*

#### Files

| File | Purpose |
|---|---|
| `qnty_offline_edge_oos_seal_v1.json` | OOS seal payload (pre-scoring declaration only) |
| `qnty_offline_edge_oos_seal_v1.sha256` | SHA-256 sidecar of the exact JSON bytes |

#### What Lane F1 does

- Freezes the OOS boundary policy: `USE_EXISTING_DETERMINISTIC_SPLIT_DEFINITIONS_WITH_FINAL_SPLIT_HELD_OUT`.
- Freezes the split-lock policy: `FINAL_CHRONOLOGICAL_SPLIT_IS_OOS`, no split mutation.
- Binds to the frozen trial manifest digest (`bound_trial_manifest_sha256`).
- Binds to the frozen strategy contract digest (`bound_contract_sha256`).
- Requires the trial manifest gate to pass (gate status `TRIAL_MANIFEST_PREREGISTERED_DIAGNOSTIC_ONLY`).
- All authorization booleans are `false`:
  `oos_scoring_authorized`, `trial_execution_authorized`,
  `scoring_authorization`, `live_integration_authorized`,
  `paper_integration_authorized`, `final_verdict_authorization`,
  `split_mutation_authorized`.
- All downstream dependency booleans are `false`:
  `null_benchmark_dependency_satisfied`, `multiple_testing_dependency_satisfied`,
  `trade_position_simulation_dependency_satisfied`,
  `net_pnl_equity_risk_dependency_satisfied`.

#### What Lane F1 does NOT do

- No scoring, PnL, outcomes, strategy execution, signal generation,
  live/paper/exchange integration, or verdict advancement.
- `oos_seal_readiness` remains `false`.
- `oos_scoring_authorized` remains `false`.
- `EDGE_UNPROVEN`, `BLOCK_LIVE_INTEGRATION`, and
  `BLOCKED_BY_VALIDATION_IMPLEMENTATION` remain.
- Null/multiple-testing/simulation/net-PnL gates remain false.
- Does not edit the contract JSON, contract SHA-256 sidecar, contract
  commit-binding sidecar, trial manifest JSON, or trial manifest SHA-256 sidecar.
---

### Lane G1 — Null Benchmark Pre-Scoring Declaration Packet

**Status:** frozen, diagnostic-only, pre-scoring.
**Verdict impact:** none — `final_offline_verdict` stays
`BLOCKED_BY_VALIDATION_IMPLEMENTATION`.

**Lane G1** pre-registers the null/reference policy *before* any scoring,
outcome math, or candidate evaluation exists. It proves that the strategy
contract, trial manifest, and OOS seal are all pre-registered and
diagnostic-bound, and that a null reference policy is declared and hash-bound
before anything can be compared against it.

#### Files

| File | Purpose |
|---|---|
| `qnty_offline_edge_null_benchmark_v1.json` | Null benchmark payload (pre-scoring declaration only) |
| `qnty_offline_edge_null_benchmark_v1.sha256` | SHA-256 sidecar of the exact JSON bytes |

#### What Lane G1 does

- Freezes the null reference policy: `PREDECLARE_NO_SKILL_REFERENCE_FAMILY_ONLY`.
- Freezes the null reference family: `NO_SKILL_TIME_ORDER_PRESERVING_REFERENCE`.
- Freezes the reference selection and the reference count (exactly `1`), so the
  null cannot be shopped for after outcomes exist.
- Binds to the frozen strategy contract digest (`bound_contract_sha256`).
- Binds to the frozen trial manifest digest (`bound_trial_manifest_sha256`).
- Binds to the frozen OOS seal digest (`bound_oos_seal_sha256`).
- Requires the OOS seal gate to pass (gate status
  `OOS_SEAL_PREREGISTERED_DIAGNOSTIC_ONLY`). A missing or failed OOS seal gate
  fails closed: the null benchmark gate can never pass without it
  (`BLOCKED_BY_OOS_SEAL_GATE`).
- Emits the diagnostic-only `null_benchmark_preregistration_gate`
  (scope `NULL_REFERENCE_POLICY_AND_OOS_SEAL_BINDING_ONLY`, downstream unlocks
  empty).
- All authorization booleans are `false`:
  `null_generation_authorized`, `candidate_comparison_authorized`,
  `trial_execution_authorized`, `oos_scoring_authorized`,
  `scoring_authorization`, `live_integration_authorized`,
  `paper_integration_authorized`, `final_verdict_authorization`.
- All downstream dependency booleans are `false`:
  `multiple_testing_dependency_satisfied`,
  `trade_position_simulation_dependency_satisfied`,
  `net_pnl_equity_risk_dependency_satisfied`.

#### What Lane G1 does NOT do

- Does **not** compute the null benchmark — no null reference values are
  generated in this lane (`null_generation_authorized` remains `false`).
- Does **not** compare a candidate against a null
  (`candidate_comparison_authorized` remains `false`).
- No scoring, PnL, returns, Sharpe, edge, outcomes, strategy execution, signal
  generation, live/paper/exchange integration, or verdict advancement.
- `null_benchmark_readiness` remains `false`. Even when the packet validates and
  the gate passes, this is pre-scoring declaration evidence only.
- `EDGE_UNPROVEN`, `BLOCK_LIVE_INTEGRATION`, and
  `BLOCKED_BY_VALIDATION_IMPLEMENTATION` remain.
- Multiple-testing / simulation / net-PnL gates remain false.
- Does not edit the contract JSON, contract SHA-256 sidecar, contract
  commit-binding sidecar, trial manifest JSON/sidecar, or OOS seal JSON/sidecar.

#### Verification

```bash
python3 -m json.tool docs/contracts/instances/qnty_offline_edge_null_benchmark_v1.json >/dev/null
cd docs/contracts/instances && sha256sum -c qnty_offline_edge_null_benchmark_v1.sha256
```

### Lane H1 — Multiple-Testing Control Pre-Registration Packet

**Status:** frozen, diagnostic-only, pre-scoring.
**Verdict impact:** none — `final_offline_verdict` stays
`BLOCKED_BY_VALIDATION_IMPLEMENTATION`.

**Lane H1** pre-registers the test family and multiplicity policy *before* any
scoring, null generation, candidate comparison, or outcome math exists. It
proves that the strategy contract, trial manifest, OOS seal, and null benchmark
declaration are all pre-registered and diagnostic-bound, and that a
multiple-testing control policy is declared and hash-bound before any
statistical evaluation exists.

Declaring the family *before* any statistic exists is the point: it is what
stops a later "we only ever ran one test" claim from being unfalsifiable.

#### Files

| File | Purpose |
|---|---|
| `qnty_offline_edge_multiple_testing_control_v1.json` | Multiple-testing control payload (pre-scoring declaration only) |
| `qnty_offline_edge_multiple_testing_control_v1.sha256` | SHA-256 sidecar of the exact JSON bytes |

#### What Lane H1 does

- Freezes the test-family policy:
  `SINGLE_PRE_REGISTERED_TRIAL_AND_SINGLE_NULL_REFERENCE_ONLY`.
- Freezes the search-procedure policy: `NO_SEARCH_NO_POST_HOC_SELECTION`.
- Freezes the multiplicity-control policy:
  `NO_ADJUSTMENT_DECLARED_FOR_SINGLE_TRIAL_SINGLE_NULL_REFERENCE_PRE_SCORING`.
  This declares *why* no adjustment is required (family size 1 × 1), not that
  adjustment is waived for a larger family.
- Freezes the statistical-evaluation policy:
  `NO_STATISTICAL_VALUES_COMPUTED_IN_THIS_LANE`.
- Freezes the candidate declaration count and the null reference declaration
  count at exactly `1` each, so the family cannot be silently widened after
  outcomes exist.
- Binds to the frozen strategy contract digest (`bound_contract_sha256`).
- Binds to the frozen trial manifest digest (`bound_trial_manifest_sha256`).
- Binds to the frozen OOS seal digest (`bound_oos_seal_sha256`).
- Binds to the frozen null benchmark digest (`bound_null_benchmark_sha256`).
- Requires the null benchmark gate to pass (gate status
  `NULL_BENCHMARK_PREREGISTERED_DIAGNOSTIC_ONLY`). A missing or failed null
  benchmark gate fails closed: the multiple-testing control gate can never pass
  without it (`BLOCKED_BY_NULL_BENCHMARK_GATE`). Because the null benchmark gate
  itself requires the OOS seal gate, the whole B→H1 chain is transitively
  enforced.
- Emits the diagnostic-only `multiple_testing_control_preregistration_gate`
  (scope `TEST_FAMILY_AND_NULL_BENCHMARK_BINDING_ONLY`, downstream unlocks
  empty).
- All authorization booleans are `false`:
  `statistical_value_generation_authorized`, `candidate_comparison_authorized`,
  `null_generation_authorized`, `trial_execution_authorized`,
  `oos_scoring_authorized`, `scoring_authorization`,
  `live_integration_authorized`, `paper_integration_authorized`,
  `final_verdict_authorization`.
- All downstream dependency booleans are `false`:
  `trade_position_simulation_dependency_satisfied`,
  `net_pnl_equity_risk_dependency_satisfied`.

#### What Lane H1 does NOT do

- Does **not** compute any statistical value — no p-values, no confidence
  intervals, no corrections, no multiplicity math
  (`statistical_value_generation_authorized` remains `false`).
- Does **not** generate a null reference (`null_generation_authorized` remains
  `false`) or compare a candidate against a null
  (`candidate_comparison_authorized` remains `false`).
- No scoring, PnL, returns, Sharpe, edge, outcomes, strategy execution, signal
  generation, live/paper/exchange integration, or verdict advancement.
- `multiple_testing_control_readiness` remains `false`. Even when the packet
  validates and the gate passes, this is pre-scoring declaration evidence only.
- `EDGE_UNPROVEN`, `BLOCK_LIVE_INTEGRATION`, and
  `BLOCKED_BY_VALIDATION_IMPLEMENTATION` remain.
- Simulation / net-PnL gates remain false.
- Does not edit the contract JSON, contract SHA-256 sidecar, contract
  commit-binding sidecar, trial manifest JSON/sidecar, OOS seal JSON/sidecar, or
  null benchmark JSON/sidecar.

#### Verification

```bash
python3 -m json.tool docs/contracts/instances/qnty_offline_edge_multiple_testing_control_v1.json >/dev/null
cd docs/contracts/instances && sha256sum -c qnty_offline_edge_multiple_testing_control_v1.sha256
```

### Lane I1 — Simulation Policy Pre-Registration Packet

**Files added:**

| File | Purpose |
|---|---|
| `qnty_offline_edge_simulation_policy_v1.json` | Frozen simulation policy pre-scoring declaration packet |
| `qnty_offline_edge_simulation_policy_v1.sha256` | SHA-256 sidecar of the exact JSON bytes |

**Lane I1** pre-registers the future hypothetical path-construction policy *before* any
simulated events, returns, PnL, orders, fills, positions, or execution logic exists.

The simulation policy packet:

- Binds to the strategy rule contract, trial manifest, OOS seal, null benchmark, and
  multiple-testing control digests.
- Requires the multiple-testing control gate to pass.
- Declares frozen simulation policy strings:
  - `simulation_family_policy` = `PREDECLARE_HYPOTHETICAL_PATH_CONSTRUCTION_POLICY_ONLY`
  - `simulation_timing_policy` = `NO_INTRABAR_ASSUMPTIONS_BEYOND_FROZEN_CONTRACT_DECISION_TIME`
  - `simulation_cost_policy` = `NO_COST_VALUES_COMPUTED_IN_THIS_LANE`
  - `simulation_funding_policy` = `NO_FUNDING_VALUES_COMPUTED_IN_THIS_LANE`
  - `simulation_quantity_policy` = `NO_QUANTITY_OR_NOTIONAL_VALUES_COMPUTED_IN_THIS_LANE`
  - `simulation_output_policy` = `NO_EVENTS_OR_ECONOMIC_VALUES_EMITTED_IN_THIS_LANE`
- Freezes all policy booleans to `True` and all authorization booleans to `False`.

**CLI arguments (optional):**

- `--simulation-policy-path` — path to the frozen simulation policy JSON.
- `--simulation-policy-sha256-path` — path to the SHA-256 sidecar.

If both are supplied (along with all upstream diagnostic arguments), the materializer
runs and the simulation policy pre-registration gate may pass. If either is omitted,
the existing absence diagnostic is emitted (unchanged).

**What Lane I1 does:**

- Adds a frozen simulation policy pre-registration packet.
- Packet binds to contract, trial manifest, OOS seal, null benchmark, and
  multiple-testing control digests.
- Gate requires multiple-testing control gate.
- Diagnostic-only: no simulated events, orders, fills, positions, executions,
  PnL, returns, Sharpe, edge, outcomes, strategy execution, signal generation,
  live/paper/exchange integration, or verdict advancement.
- `simulation_policy_readiness` remains `false`. Even when the packet validates
  and the gate passes, this is pre-scoring declaration evidence only.

**What Lane I1 does NOT do:**

- No simulated events (`simulated_event_generation_authorized` remains `false`).
- No economic values (`economic_value_generation_authorized` remains `false`).
- No scoring, PnL, returns, Sharpe, edge, outcomes, strategy execution, signal
  generation, live/paper/exchange integration, or verdict advancement.
- `simulation_policy_readiness` remains `false`.
- `EDGE_UNPROVEN`, `BLOCK_LIVE_INTEGRATION`, and
  `BLOCKED_BY_VALIDATION_IMPLEMENTATION` remain.
- Net-PnL/equity-risk gate remains false.
- Does not edit any upstream JSON or sidecar (contract, trial manifest, OOS seal,
  null benchmark, multiple-testing control).

#### Verification

```bash
python3 -m json.tool docs/contracts/instances/qnty_offline_edge_simulation_policy_v1.json >/dev/null
cd docs/contracts/instances && sha256sum -c qnty_offline_edge_simulation_policy_v1.sha256
```

### Lane J1 — Economic Accounting Policy Pre-registration Packet

**Lane J1** per the spec: *"Economic accounting policy pre-registration declared
and hash-bound before any economic value, PnL, return, equity curve, risk,
drawdown, cost-adjusted value, funding-adjusted value, orders, fills, positions,
executions, or scoring exists."*

#### Files

| File | Purpose |
|---|---|
| `qnty_offline_edge_economic_accounting_policy_v1.json` | Economic accounting policy payload (declaration-only) |
| `qnty_offline_edge_economic_accounting_policy_v1.sha256` | SHA-256 sidecar of the exact JSON bytes |

#### What it does

- Freezes the future economic accounting policy boundary before economic values exist.
- Binds to the frozen strategy contract, trial manifest, OOS seal, null benchmark,
  multiple-testing control, and simulation policy digests.
- Requires the simulation policy gate to have passed.
- Declares that no economic values, PnL, returns, equity curves, risk metrics,
  drawdown, cost values, funding values, aggregate series, capital paths,
  dispersion summaries, or accounting outputs are computed in this lane.
- All authorization booleans are `false`: no scoring, no economic value generation,
  no simulation, no statistical values, no candidate comparison, no null generation,
  no live/paper integration, no final verdict.

#### What it does NOT do

- Does **not** compute any economic values.
- Does **not** create PnL, returns, Sharpe, equity curve, risk metrics, drawdown,
  orders, fills, positions, executions, costs, funding values, or final verdict.
- Does **not** authorize scoring.
- Does **not** advance `final_offline_verdict`.
- Does not edit any upstream JSON or sidecar (contract, trial manifest, OOS seal,
  null benchmark, multiple-testing control, simulation policy).

#### Verification

```bash
python3 -m json.tool docs/contracts/instances/qnty_offline_edge_economic_accounting_policy_v1.json >/dev/null
cd docs/contracts/instances && sha256sum -c qnty_offline_edge_economic_accounting_policy_v1.sha256
```

### Lane K1 — Prerequisite Closure Matrix / Implementation Readiness Lock

**Lane K1 is not a scoring lane.** It adds no new frozen packet or sidecar. It
is a **derived, diagnostic-only projection** over the seven pre-registration
gates built by Lanes B through J1 — a pure function of the diagnostics those
lanes already produce, with no file reads, no hashing, no git calls, and no
economic/statistical computation.

It answers exactly one question:

> Are all pre-registration gates present and passing, as a chain? Yes or no.

It does **not** answer, and cannot answer:

> Does that authorize scoring, simulation, economic values, statistics, live
> integration, or final verdict advancement? **No — never.**

#### What Lane K1 does

- Adds `_build_prerequisite_closure_diagnostics(...)` — a pure builder that
  collects the seven required gates:
  `contract_packet_gate`, `trial_manifest_preregistration_gate`,
  `oos_seal_preregistration_gate`, `null_benchmark_preregistration_gate`,
  `multiple_testing_control_preregistration_gate`,
  `simulation_policy_preregistration_gate`, and
  `economic_accounting_policy_preregistration_gate` (read from the top-level
  key on `net_pnl_equity_risk_contract_diagnostics` when present, falling
  back to the nested `economic_accounting_policy_diagnostics` key from Lane
  J1's absence-shape path).
- Adds `_derive_prerequisite_closure_gate(...)` — a pure gate projection that
  fails closed, in priority order: any authorization field unexpectedly
  `true` -> `BLOCKED_BY_UNEXPECTED_AUTHORIZATION`; a required gate missing ->
  `BLOCKED_BY_MISSING_PREREGISTRATION_GATE`; a required gate present but not
  passed -> `BLOCKED_BY_FAILED_PREREGISTRATION_GATE`; otherwise
  `PREREGISTRATION_CHAIN_CLOSED_DIAGNOSTIC_ONLY` with `gate_passed = true`.
- Wires both into `build_real_validation_receipt(...)` under
  `prerequisite_closure_diagnostics` and into `main()`'s build order (after
  the net-PnL/equity-risk contract diagnostics, before the final verdict
  logic diagnostics).

Even when all seven gates pass and `closure_all_required_gates_passed` is
`true`, every authorization field remains `false`:
`closure_scoring_authorization`, `closure_live_authorization`,
`closure_final_verdict_authorization`, `implementation_authorized`,
`simulation_authorized`, `economic_value_generation_authorized`,
`statistical_value_generation_authorized`, `candidate_comparison_authorized`,
`null_generation_authorized`, `final_verdict_advancement_authorized`, and
`gate_downstream_unlocks` is always `[]`. `final_offline_verdict_remains` is
always `BLOCKED_BY_VALIDATION_IMPLEMENTATION`.

#### What Lane K1 does NOT do

- No scoring, strategy implementation, signal calculation, simulated events,
  orders, fills, positions, executions, PnL, returns, Sharpe, edge, equity
  curve, risk metrics, drawdown, economic values, p-values, confidence
  intervals, null benchmark computation, candidate-vs-null comparison, or
  multiple-testing math.
- No live/paper/exchange integration.
- Does not advance `final_offline_verdict`; it remains
  `BLOCKED_BY_VALIDATION_IMPLEMENTATION`.
- Does not change `FORBIDDEN_CALCULATION_KEYS` or `ALLOWED_FINAL_VERDICTS`.
- Does not edit any frozen upstream JSON or sidecar (contract, trial
  manifest, OOS seal, null benchmark, multiple-testing control, simulation
  policy, economic accounting policy).
- `EDGE_UNPROVEN` and `BLOCK_LIVE_INTEGRATION` remain.

**Next after K1** can be implementation planning — but not in this PR.

#### Verification

```bash
.venv/bin/python -m pytest tests/experiment/test_offline_edge_real_validation.py -k PrerequisiteClosureK1 -q
```

### Lane L1 — Implementation Boundary Plan / Runner Contract Shell

**Lane L1 is not implementation.** It adds no new frozen packet or sidecar. It
is a **derived, diagnostic-only projection** over the Lane K1 prerequisite
closure gate and the contract-packet / trial-manifest gates it depends on —
a pure function of diagnostics already produced upstream, with no file
reads, no hashing, no git calls, and no decision/simulated-event/economic/
statistical computation.

It answers exactly one question:

> Given the preregistration chain is closed, what is the implementation
> boundary for a future runner?

It does **not** implement the runner, materialize rule outputs, or compute
decisions, signals, simulated events, economic values, or statistics — and it
does **not** authorize scoring.

#### What Lane L1 does

- Adds `_build_implementation_boundary_diagnostics(...)` — a pure builder
  that reads the K1 `prerequisite_closure_gate`, the strategy contract's
  `contract_packet_gate`, and the trial manifest's
  `trial_manifest_preregistration_gate`, and declares the future runner's
  allowed input roles/columns (`bars`/`funding`, `timestamp`/`close`,
  `fundingTime`/`fundingRate`) and forbidden output/materialization policies.
- Adds `_derive_implementation_boundary_gate(...)` — a pure gate projection
  that fails closed, in priority order: any authorization field unexpectedly
  `true` -> `BLOCKED_BY_UNEXPECTED_AUTHORIZATION`; the prerequisite closure
  gate missing or not passed -> `BLOCKED_BY_PREREQUISITE_CLOSURE_GATE`; the
  contract-packet or trial-manifest gate missing or not passed ->
  `BLOCKED_BY_REQUIRED_UPSTREAM_GATE`; otherwise
  `IMPLEMENTATION_BOUNDARY_DECLARED_DIAGNOSTIC_ONLY` with `gate_passed = true`.
- Wires both into `build_real_validation_receipt(...)` under
  `implementation_boundary_diagnostics` and into `main()`'s build order
  (after the prerequisite closure diagnostics, before the final verdict
  logic diagnostics).

Even when the gate passes, every authorization field remains `false`:
`implementation_authorized`, `rule_materialization_authorized`,
`decision_row_generation_authorized`, `simulated_event_generation_authorized`,
`economic_value_generation_authorized`, `statistical_value_generation_authorized`,
`candidate_comparison_authorized`, `null_generation_authorized`,
`scoring_authorization`, `live_integration_authorized`,
`paper_integration_authorized`, `final_verdict_authorization`, and
`gate_downstream_unlocks` is always `[]`. `final_offline_verdict_remains` is
always `BLOCKED_BY_VALIDATION_IMPLEMENTATION`.

#### What Lane L1 does NOT do

- Does not implement a runner, materialize rule outputs, or compute
  decisions, signals, simulated events, orders, fills, positions,
  executions, PnL, returns, Sharpe, edge, equity curve, risk metrics,
  drawdown, economic values, p-values, confidence intervals, null benchmark
  computation, candidate-vs-null comparison, or multiple-testing math.
- No live/paper/exchange integration.
- Does not authorize scoring/implementation/simulation/economic/statistical
  values or final verdict advancement.
- Does not advance `final_offline_verdict`; it remains
  `BLOCKED_BY_VALIDATION_IMPLEMENTATION`.
- Does not change `FORBIDDEN_CALCULATION_KEYS` or `ALLOWED_FINAL_VERDICTS`.
- Does not edit any frozen upstream JSON or sidecar.
- `EDGE_UNPROVEN` and `BLOCK_LIVE_INTEGRATION` remain.

#### Verification

```bash
.venv/bin/python -m pytest tests/experiment/test_offline_edge_real_validation.py -k ImplementationBoundaryL1 -q
```

### Lane M1 — No-Output Runner Invocation Scaffold

**Lane M1 is not implementation.** It adds no new frozen packet or sidecar. It
is a **derived, diagnostic-only projection** over the Lane L1 implementation
boundary gate and the contract-packet / trial-manifest gates it depends on —
a pure function of diagnostics already produced upstream, with no file
reads, no hashing, no git calls, and no decision/simulated-event/economic/
statistical computation.

It answers exactly one question:

> Can the receipt represent a future runner invocation in a bounded,
> fail-closed way?

It does **not** implement the runner, materialize rule outputs, or compute
decisions, signals, simulated events, economic values, or statistics — and it
does **not** authorize scoring, live/paper integration, or final verdict
advancement.

#### What Lane M1 does

- Adds `_build_no_output_runner_invocation_diagnostics(...)` — a pure builder
  that reads the L1 `implementation_boundary_gate`, the strategy contract's
  `contract_packet_gate`, and the trial manifest's
  `trial_manifest_preregistration_gate`, and records a diagnostic-only
  invocation record: `future_runner_invocation_declared = true`,
  `future_runner_implementation_status = NO_OUTPUT_RUNNER_NOT_IMPLEMENTED`,
  `future_runner_invocation_mode = DIAGNOSTIC_RECORD_ONLY`, and reiterates
  the frozen output (`NO_OUTPUT_ROWS_EMITTED_IN_THIS_LANE`) and
  materialization (`NO_RULE_MATERIALIZATION_IN_THIS_LANE`) policies.
- Adds `_derive_no_output_runner_invocation_gate(...)` — a pure gate
  projection that fails closed, in priority order: any authorization field
  unexpectedly `true` -> `BLOCKED_BY_UNEXPECTED_AUTHORIZATION`; the
  implementation boundary gate missing or not passed ->
  `BLOCKED_BY_IMPLEMENTATION_BOUNDARY_GATE`; the contract-packet or
  trial-manifest gate missing or not passed ->
  `BLOCKED_BY_REQUIRED_UPSTREAM_GATE`; invocation-declaration,
  implementation-status, or output/materialization policy evidence
  missing/empty/mutated -> `BLOCKED_BY_INCOMPLETE_RUNNER_INVOCATION_EVIDENCE`;
  otherwise `NO_OUTPUT_RUNNER_INVOCATION_DECLARED_DIAGNOSTIC_ONLY` with
  `gate_passed = true`.
- Wires both into `build_real_validation_receipt(...)` under
  `no_output_runner_invocation_diagnostics` and into `main()`'s build order
  (after the implementation boundary diagnostics, before the final verdict
  logic diagnostics).

Even when the gate passes, every authorization field remains `false`:
`runner_invocation_readiness`, `implementation_authorized`,
`runner_implementation_authorized`, `rule_materialization_authorized`,
`decision_row_generation_authorized`, `simulated_event_generation_authorized`,
`economic_value_generation_authorized`, `statistical_value_generation_authorized`,
`candidate_comparison_authorized`, `null_generation_authorized`,
`scoring_authorization`, `live_integration_authorized`,
`paper_integration_authorized`, `final_verdict_authorization`, and
`gate_downstream_unlocks` is always `[]`. `final_offline_verdict_remains` is
always `BLOCKED_BY_VALIDATION_IMPLEMENTATION`.

#### What Lane M1 does NOT do

- Does not implement a runner or invoke one — it declares only a diagnostic
  invocation record.
- Does not materialize rule outputs, or compute decisions, signals,
  simulated events, orders, fills, positions, executions, PnL, returns,
  Sharpe, edge, equity curve, risk metrics, drawdown, economic values,
  p-values, confidence intervals, null benchmark computation,
  candidate-vs-null comparison, or multiple-testing math.
- No live/paper/exchange integration.
- Does not authorize scoring/implementation/simulation/economic/statistical
  values or final verdict advancement.
- Does not advance `final_offline_verdict`; it remains
  `BLOCKED_BY_VALIDATION_IMPLEMENTATION`.
- Does not change `FORBIDDEN_CALCULATION_KEYS` or `ALLOWED_FINAL_VERDICTS`.
- Does not edit any frozen upstream JSON or sidecar.
- `EDGE_UNPROVEN` and `BLOCK_LIVE_INTEGRATION` remain.

#### Verification

```bash
.venv/bin/python -m pytest tests/experiment/test_offline_edge_real_validation.py -k NoOutputRunnerInvocationM1 -q
```

### Lane N1 — Allowed Runner Input Projection Diagnostics

**Lane N1 is not implementation.** It adds no new frozen packet or sidecar. It
is a **derived, diagnostic-only projection** over the Lane M1 no-output runner
invocation gate, the Lane L1 implementation boundary gate, and the
contract-packet / trial-manifest gates they depend on.

It answers exactly one question:

> Can the receipt represent the future runner input projection using only the
> frozen allowed input roles and columns?

N1 declares a metadata-only future runner input projection: allowed input
roles `bars` and `funding`; allowed bar columns `close` and `timestamp`;
allowed funding columns `fundingRate` and `fundingTime`; excluded bar columns
`open`, `high`, `low`, and `volume`; and excluded funding column `markPrice`.

It emits no row values and no rule outputs. It does not implement the runner,
materialize rules, compute decisions, signals, simulated events, economic
values, statistics, or final verdict, and it does not authorize scoring,
live/paper integration, or final verdict advancement.

Even when the N1 gate passes, `gate_downstream_unlocks` is always `[]`, every
authorization remains `false`, `EDGE_UNPROVEN` and `BLOCK_LIVE_INTEGRATION`
remain, and `final_offline_verdict` remains
`BLOCKED_BY_VALIDATION_IMPLEMENTATION`.

#### Verification

```bash
.venv/bin/python -m pytest tests/experiment/test_offline_edge_real_validation.py -k AllowedRunnerInputProjectionN1 -q
```

### Lane O1 — Projected Input Shape Inventory Diagnostics

**Lane O1 is not implementation.** It adds no new frozen packet or sidecar. It
is a **derived, diagnostic-only projection** over the Lane N1 allowed runner
input projection, the Lane M1 no-output runner invocation gate, and the Lane
L1 implementation boundary gate.

It answers exactly one question:

> Can the receipt describe the shape of allowed projected runner inputs without
> exposing row values or producing rule outputs?

O1 declares a metadata-only projected input shape inventory for roles `bars`
and `funding`, allowed bar columns `close` and `timestamp`, allowed funding
columns `fundingRate` and `fundingTime`, excluded bar columns `open`, `high`,
`low`, and `volume`, and excluded funding column `markPrice`.

It emits no row values, no projected input row values, and no rule outputs. It
does not implement the runner, materialize rules, compute decisions, signals,
simulated events, economic values, statistics, or final verdict, and it does
not authorize scoring, live/paper integration, or final verdict advancement.

Even when the O1 gate passes, `gate_downstream_unlocks` is always `[]`, every
authorization remains `false`, `EDGE_UNPROVEN` and `BLOCK_LIVE_INTEGRATION`
remain, and `final_offline_verdict` remains
`BLOCKED_BY_VALIDATION_IMPLEMENTATION`.

#### Verification

```bash
.venv/bin/python -m pytest tests/experiment/test_offline_edge_real_validation.py -k ProjectedInputShapeInventoryO1 -q
```

### Lane P1 — Projected Input Row-Count / Column-Presence Diagnostics

**Lane P1 is not implementation.** It adds no new frozen packet or sidecar. It
is a **derived, diagnostic-only projection** over the Lane O1 projected input
shape inventory, the Lane N1 allowed runner input projection, the Lane M1
no-output runner invocation gate, and the Lane L1 implementation boundary gate.

It answers exactly one question:

> Can the receipt verify projected input availability and allowed-column
> presence by role/symbol/split using only counts and column names?

P1 declares a metadata-only projected input row-count and column-presence
summary for roles `bars` and `funding`, allowed bar columns `close` and
`timestamp`, allowed funding columns `fundingRate` and `fundingTime`, excluded
bar columns `open`, `high`, `low`, and `volume`, and excluded funding column
`markPrice`. It depends on the O1 projected input shape inventory gate.

It emits no row values, no projected input row values, no timestamp values, no
price values, no funding values, and no rule outputs. It does not implement
the runner, materialize rules, compute decisions, signals, simulated events,
economic values, statistics, or final verdict, and it does not authorize
scoring, live/paper integration, or final verdict advancement.

Even when the P1 gate passes, `gate_downstream_unlocks` is always `[]`, every
authorization remains `false`, `EDGE_UNPROVEN` and `BLOCK_LIVE_INTEGRATION`
remain, and `final_offline_verdict` remains
`BLOCKED_BY_VALIDATION_IMPLEMENTATION`.

#### Verification

```bash
.venv/bin/python -m pytest tests/experiment/test_offline_edge_real_validation.py -k ProjectedInputRowCountP1 -q
```
