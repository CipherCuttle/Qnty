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

## What this PR does NOT do

- The runner does **not** read this contract.
- The receipt does **not** emit it.
- No scoring, strategy implementation, signal calculation, PnL, edge, or live-readiness
  claim is introduced.
- All downstream gates remain `false` / static.
- `final_offline_verdict` remains `BLOCKED_BY_VALIDATION_IMPLEMENTATION`.
- `EDGE_UNPROVEN` and `BLOCK_LIVE_INTEGRATION` remain.

## Lane C and beyond

Lane C will decide the exact runtime binding and validator semantics. This PR is
strictly the artifact commit — the contract exists as frozen bytes, but nothing reads
it yet.

## Verification

```bash
# Validate JSON
python3 -m json.tool qnty_offline_edge_strategy_rule_contract_v1.json > /dev/null

# Verify SHA-256 sidecar
cd docs/contracts/instances && sha256sum -c qnty_offline_edge_strategy_rule_contract_v1.sha256