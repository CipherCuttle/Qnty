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

### Lane C2 and beyond

Lane C2 or later must decide a non-self-referential commit-containment model.
The approach must resolve ``contract_commit_sha`` without editing the same file
whose bytes define the hash. Possible strategies include:

- A separate commit-metadata sidecar generated post-merge.
- An out-of-band binding mechanism (e.g., CI pipeline stamps the merge SHA).
- Contract instance versioning that externalizes the commit reference.

## Verification

```bash
# Validate JSON
python3 -m json.tool qnty_offline_edge_strategy_rule_contract_v1.json > /dev/null

# Verify SHA-256 sidecar
cd docs/contracts/instances && sha256sum -c qnty_offline_edge_strategy_rule_contract_v1.sha256