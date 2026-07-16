# QNTY — Real BTC Candidate 1 Train Mechanism Decomposition (v0)

**Protocol:** `real_btc_candidate1_train_mechanism_decomposition_v0`
**Status:** preregistered, **not executed**. Diagnostic re-analysis of already-spent
train-smoke data. **Not** confirmation, paper, or live authorization.

Standing status: `EDGE_UNPROVEN`, `BLOCK_LIVE_INTEGRATION`. Scientific authorization
= false. Paper authorization = false. Live authorization = false.

## Bound source (frozen, unchanged)

- Source classification: `CANDIDATE_1_TRAIN_SMOKE_SURVIVED`
- Source repo head: `407996932afbed9f8d1aaa8fc4c05871c6712c39`
- Bound implementation: `e1b493e22403a228e9d3994e7a39a0f02fbb2bcc`
- Archived receipt SHA-256: `7abb521eba06ebd515f6ad1519fab92df1368d342355a744ec415d6d220b9be5`
- Source statistic `T` = `0.0007358157493656125`
- Scored slots: `4203`; invalid slots: `14`
- Statistic reason code: `holdout_remained_sealed_non_holdout_scored`

The archived artifacts, the receipt, the persistent once-only marker, the data, the
scorer, and the quarantine are unchanged by this protocol.

## Why this decomposition exists

1. **Candidate 1 survived only a relative train smoke.** The only claim earned is
   `T > 0` on the frozen non-quarantine train slots — i.e. candidate net minus null net
   is positive in-sample. Nothing more.

2. **The observed `T` does not identify the mechanism.** A positive `T` could come from
   price direction, from a funding/carry transfer, or from both. The single scalar
   cannot separate these sources.

3. **Common fixed costs cancel.** Because `T` is candidate-minus-null and both legs pay
   the same fixed cost on the same active/flat mask, the fixed cost drops out of the
   difference. Therefore the *absolute* economics of Candidate 1 (does it make money net
   of real costs at all?) remain unknown from `T` alone.

4. **A hostile review proposed funding persistence as the likely mechanism** — i.e. that
   the apparent effect is a funding-sign carry artifact rather than directional edge.
   That explanation is plausible but **untested**. This protocol is designed to measure
   it, not to assume it.

5. **No guessed t-statistic is accepted.** No `t`, `p`, confidence interval, or bootstrap
   is part of this protocol.

6. **No arbitrary funding-contribution percentage is accepted.** In particular, no "70%
   funding contribution" or any other percentage threshold is adopted.

7. **This is diagnostic re-analysis of spent train data**, decomposing the already-
   computed `T` into component means. It is not a new trial, not confirmation, and does
   not open the quarantine.

8. **The quarantine remains sealed and forbidden.** Two-role seal
   `1e05840e3d49ec4d74a76b8477d51a2170086fd93c4eaba38b43c30c03d14ef9` stays sealed. No
   quarantine value is accessed or decoded.

9. **Candidate 1 cannot be modified or rerun.** No re-scoring, no `--first-computed-statistic`,
   no recomputation of `T`, candidate returns, or null returns as part of *this* PR.

## What the decomposition will (later) compute

The future executor reuses the **exact** source slot universe — the same 4203 scored
slots, 14 invalid slots, entry/exit timestamps, candidate activity mask, candidate
sides, null sides, funding window, cost accounting, warmup, split, purge, embargo, and
hold period. No slot may be added, removed, or reclassified. It must reconstruct the
original `T = 0.0007358157493656125` from component means (`mean(relative_net_i)`), or
classify `DECOMPOSITION_BLOCKED_OR_INVALID`.

Per-slot definitions, the frozen primary/secondary output schema, the identical-cost
contract (relative cost difference expected zero but **verified, not assumed**), the
activity-matched always-long / always-short regime diagnostics, and the forbidden-output
list are all pinned in
`docs/registries/real_btc_candidate1_train_mechanism_decomposition_registry.json`.

Outcome classifications are frozen there as well:

- `CANDIDATE_1_ABSOLUTE_NET_NONPOSITIVE` — `mean_candidate_net <= 0`: not economically
  viable under frozen absolute accounting; diagnostic baseline only; no rescue.
- `CANDIDATE_1_ABSOLUTE_NET_POSITIVE_RELATIVE_PRICE_NONPOSITIVE` — net `> 0` but
  `mean_relative_price_component <= 0`: any positive economics are not from a directional
  price advantage; investigate funding/carry as measurement; do not claim price alpha.
- `CANDIDATE_1_ABSOLUTE_NET_AND_RELATIVE_PRICE_POSITIVE` — net `> 0` and relative price
  `> 0`: eligible for a **separately** preregistered prospective test; still no edge,
  paper, or live claim.

No percentage-contribution threshold. No significance inference.

## Execution gating

The decomposition will be executed **once only**, after all of:

1. this preregistration PR merges;
2. a separate implementation PR is reviewed and merged;
3. an implementation fingerprint / commit is bound to the registry entry;
4. a final no-computation preflight passes.

The registry entry is append-only with `decomposition_execution_budget = 1` and
`decomposition_execution_count = 0`.

## Next durable fallback

After the decomposition, the next durable fallback is a **minimal funding/basis mechanism
and cost observatory** — measuring the carry/basis structure and realistic costs directly
— rather than any retuning or rescue of Candidate 1.
