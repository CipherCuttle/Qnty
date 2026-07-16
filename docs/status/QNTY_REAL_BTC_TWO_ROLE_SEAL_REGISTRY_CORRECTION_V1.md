# Real BTC two-role seal registry correction v1

## Summary

This is a **registry-only, pre-result** correction of the single real-BTC
inventory trial entry. It rebinds the trial's structural holdout chain from the
incomplete legacy **bars-only** seal to the reviewed **bars-plus-funding**
two-role seal established by merged PR #267. No statistic was computed, no
scoring occurred, and no `T` (statistic value) has ever existed for this trial.

The correction is caused by **structural incompleteness**, not by any observed
outcome. The frozen split, candidate, null, statistic, costs, and immutable data
cut are all unchanged.

## Why this correction was needed

- PR #266 registered an incomplete **bars-only** structural chain. Its holdout
  seal hashed only the bars holdout partition and could not bind sparse funding.
- PR #267 added the reviewed **sparse-funding projection** policy
  (`bars_timestamp_partition_projection_v1`), which projects normalized UTC
  funding-event timestamps into the frozen source-ordered bars partition windows
  and seals the two roles together.
- Against the complete bars-plus-funding execution surface, the legacy bars-only
  registry declaration now **fails closed** (`holdout_seal_state = not_sealed`,
  `holdout_seal_killed = true`) with the single reason
  `registry_declaration_missing_required_fields`: the projected invocation
  requires `sealed_roles` and `projection_policy`, which the legacy declaration
  lacks. The computed preview seal itself reproduces exactly as
  `1e05840e…14ef9`; the failure is attributable only to the stale registry
  declaration, not to any data, split, or projection failure.

## Execution / scoring status

- Candidate 1 execution count remained **zero** before this correction and
  remains **zero** after it.
- No `T` (statistic value) existed before this correction, and none is computed
  by it.
- This is a structural pre-execution repair, not edge, profitability, or
  experimental evidence.

## Fingerprint transition

| Role | Old (bars-only) | New (bars + funding) |
| --- | --- | --- |
| Holdout seal | `46cde529296e9bde4a884e3ea51950474ed75667a8b9a46d632581e76cd9a2cf` | `1e05840e3d49ec4d74a76b8477d51a2170086fd93c4eaba38b43c30c03d14ef9` |
| Execution packet | `bc0526ecdbbb1a7c2ff183babd465266f8122efd19ca06ad604b916abca6bdb3` | `b8a60de328193e23128b53f7436b5b992b7f0b2920187ffc274a89b52e868ca2` |
| Structural gate | `6f37e476ff5e69b6bb3531c09ee7e1eec80f6e1fb44be72089879fc4bdf52533` | `6c216226f0438ddd66f38f9d14cb967d736bdfabcc8f353237e2c506c40b760f` |
| Bound implementation commit | `a8c6f48613aee6e596758370c841112011773781` | `e1b493e22403a228e9d3994e7a39a0f02fbb2bcc` |

The execution-packet and structural-gate fingerprints necessarily changed
because both the bound holdout seal and the bound implementation commit changed.

## Bound two-role seal properties

- Projection policy: `bars_timestamp_partition_projection_v1`
- Sealed roles: `bars`, `funding`
- Sealed quarantine row counts: `bars = 8344`, `funding = 1042`
- Funding timestamp column: `fundingTime`
- All `5271` funding events classified exactly once
  (`before_bars = 1`, `train = 4215`, `purge = 1`, `embargo = 12`,
  `quarantine = 1042`, `after_bars = 0`).

## Schema note on history disclosure

The registry schema closes the `holdout_seal_declaration`,
`execution_packet_declaration`, and `holdout_open_gate_declaration` objects to
exactly their permitted fields. It does not permit historical/supersession keys
inside those exact-closed declarations. Prior-state history is therefore
disclosed in this decision memo rather than by adding extra registry keys.

## Unchanged invariants

- Frozen split: boundary index `33735`, purge `8`, embargo `90`, `42169` bars
  rows — unchanged.
- Candidate 1 (`funding_sign_one_interval_carry_v1`), the null, the statistic,
  costs, warmup, and hold period — unchanged.
- Immutable data cut `020eac5e…f55224` and nested first-statistic data binding
  `7c8552f1…f86c6f` — unchanged.
- Partition-use policy remains exactly `quarantine_only`
  (`partition_use_policy_fingerprint = c47d5fff…38ba5`), tail remains
  quarantine-only, `scientific_use_authorized = false`.

## Boundaries and authorizations

- Structural `gate_passed` is **not** scientific authorization. It attests only
  that the structural prerequisites are present, internally consistent, and
  unkilled.
- Future genuine confirmation still requires **unseen post-cutoff data**
  (`future_confirmatory_data_after_utc = 2026-04-23T01:00:00Z`).
- `EDGE_UNPROVEN`.
- `BLOCK_LIVE_INTEGRATION`.
- `paper_trade_authorized = false`, `live_integration_authorized = false`.
- No scientific confirmation is claimed. No paper trading or live integration is
  authorized. No scoring is performed in this correction.
