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

## Verification

```bash
# Validate JSON
python3 -m json.tool qnty_offline_edge_strategy_rule_contract_v1.json > /dev/null

# Verify SHA-256 sidecar
cd docs/contracts/instances && sha256sum -c qnty_offline_edge_strategy_rule_contract_v1.sha256