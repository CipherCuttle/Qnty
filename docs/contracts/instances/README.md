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
