# H001 signed directional repair — NON-EFFECTIVE review-only candidate

**Date:** 2026-10-23 UTC  
**Lane:** ADMIN_LANE / isolated synthetic-only implementation / **NOT** PROTOCOL_LANE authority  
**Base:** Qnty `main` `610f66f6c5660e09a6c0560ae1b4262f0bfd5578`  
**Independent FAIL evidence:** PR #336 HEAD `5af1160e6fdb27fb7332adaacab35d7eef890ebe` (review performed locally and reported by owner; full local evidence was not supplied to this session).

## Defect and proposed repair

H001 preregisters **one-sided positive** mean net returns (`docs/experiments/candidate1_h001_real_data_falsification_v0.json`, `validation_test.alternative`, `holdout_test.alternative`). The activated numerical amendment and existing engine instead select **two-sided absolute max-t**. The registered test is not changed by this branch.

This candidate implements independent, non-effective helpers in `quantbot/experiment/h001_signed_max_t_repair_candidate.py`:

- Use the **signed maximum**, `max_j t_star[j]`, from the shared synchronous stationary bootstrap path (not `max_j abs(t_star[j])`).
- Compare each **signed** observed `t[i]` with bootstrap maximum using a non-strict `>=` (ties count), and retain `(1+count)/(B+1)` exact rational p-values and `alpha=0.05` integer comparison.
- Statistical rejection is **only** the signed upper-tail adjusted p-value threshold. There is **no additional sign guard**. A deliberately pathological negative observed statistic may have a small adjusted p-value; that is not evidence of positive economic returns.
- The independent partial `positive_net_means_gate(base_cost_net_mean, stress_1_net_mean)` checks the original two strictly positive net-mean conditions. It is **not** the complete registered eligibility test; entries, exposure and concentration constraints, annual consistency and other gates remain separately required. This function never rewrites statistical significance.
- Strict shape, finite-float, nonnegative bounded count and fixed registry-coordinate/draw-purpose validation, with controlled exceptions. The coordinate wrapper preserves raw Philox words **only for valid existing coordinates**; it does not modify the canonical engine's public raw-word entry point.

The module does **not** perform calibration or resampling, open protected data, substitute a research trial, or make the existing engine correct by delegation. It is an isolated, unit-testable **implementation candidate**, not an activated fix.

## Tests / verification

`tests/experiment/test_h001_signed_max_t_repair_candidate.py` covers synthetic examples for negative observed t with unusually small raw p-value, independent positive-net-mean economic screening, positive means, ties, malformed observed t/NaN/Inf, invalid economic means, invalid counter types/ranges, invalid vector length, update overflow, and closed RNG-purpose coordinate handling using fake engine types. It does not claim to independently rederive Philox KATs, global FWER, or full production compatibility.

Command: `python -m pytest -q tests/experiment/test_h001_signed_max_t_repair_candidate.py`.

**Baseline result:** 14 passed on the initial candidate; verification for this updated revision must be run separately. Previous exact-HEAD continuity/artifact workflows passed; previous full suite failed due to disk quota. Neither result applies automatically to a new commit.

## Authority and remaining work

1. Preserve untouched `docs/control/active_task.json`, all immutable handoff receipts, all activated/frozen amendments and original H001 preregistration, and the SHA-bound canonical `quantbot/experiment/h001_null_calibration_engine.py`.
2. Independent reviewer must adjudicate signed max-t versus the frozen positive-mean alternative and confirm that pure statistical p-value decisions are separated from preregistered economic strategy eligibility. This is not a new effective convention.
3. A **separate append-only scientific/governance amendment** and a separately authorized `PROTOCOL_LANE` transition will be needed before altering the activated two-sided choice, binding new code hashes or integrating any of this into the existing engine. This branch does not create or activate such an amendment.
4. Fix the existing engine helper and RNG public-boundary bugs only in that authorized transition, then rerun exact Philox and numerical KATs, regressions, continuity and independent hostile re-review; update provenance through the authorized mechanism rather than rewriting hashes or bypassing tests.
5. Review LOW degeneracy rationale separately: discrete bootstrap re-samples may have nonzero probability of constant paths; zero-SE failure should stay fail-closed. Historical numerical documents remain immutable.

**Verdict:** `READY_FOR_REVIEW`, *non-effective coding candidate only*. Historical scientific review `FAIL` remains in force. `EDGE_UNPROVEN / BLOCK_LIVE_INTEGRATION / CALIBRATION_NOT_AUTHORIZED / NO_MERGE`.

## Focused revision after hostile review (2026-10-23)

Previous hostile review: https://github.com/CipherCuttle/Qnty/pull/337#pullrequestreview-5626849151. This ADMIN_LANE revision eliminates the review's HIGH ambiguity by removing the extra t>0 rejection restriction. For the synthetic counterexample observed t=-2 with 19 bootstrap maxima=-3, the raw upper-tail p-value is exactly 1/20 and raw statistical reject is true; negative base-cost mean separately fails the economic mean gate. No production claim can be inferred from raw statistical rejection. Other outstanding MEDIUM issues are still unresolved: no completed-B-draw provenance, and the baseline raw Philox entry point is not hardened by a wrapper. Formal protocol-bound amendment/independent acceptance still required. No changed frozen artifacts or authorization state.
