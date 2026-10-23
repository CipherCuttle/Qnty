# H001 — directional scientific-contract reconciliation: amendment proposal V1

**Status:** `DRAFT_PROPOSAL_NON_EFFECTIVE` — for separate independent scientific adjudication.  
**Lane:** `ADMIN_LANE` document-only planning; this document is NOT an amendment under `docs/control/amendments/`, NOT a protocol transition, and NOT execution authority.  
**Prepared:** 2026-10-23 UTC. **Repo:** `CipherCuttle/Qnty`.  
**Canonical reference base:** `main` `610f66f6c5660e09a6c0560ae1b4262f0bfd5578`.  
**Related non-effective code candidate:** [PR #337](https://github.com/CipherCuttle/Qnty/pull/337), pinned HEAD `ca8c1465979411435c9c29166a041f03272287c1`.  
**Source inconsistency:** independently reported scientific FAIL for PR #336 HEAD `5af1160e6fdb27fb7332adaacab35d7eef890ebe`; its owner's local reviewer artifacts are **not** incorporated into this branch.

> **Authority boundary:** Keep `EDGE_UNPROVEN`, `BLOCK_LIVE_INTEGRATION`, execution budget/count 0/0 for H001, real-data prohibition, no calibration, no paper/live activity. No merger, activation, control-pointer/handoff mutation, numerical-convention replacement, scientific result, or protected data access is authorized by this text. A subsequent **separately authorized `PROTOCOL_LANE`** amendment is required. Do not call this document a review approval.

## 1. Decision required

The preregistered H001 validation alternative is **one-sided mean net return > 0**. Its frozen scientific intention is to identify a positive net-return candidate among nine synchronized candidate variants with familywise adjustment, then test one selected candidate on an untouched final holdout.

An **activated** numerical-conventions amendment instead selects `TWO-SIDED-MAXT-PLUS-ONE-NONSTRICT` and explicitly rejects signed one-sided max-t on the stated (incorrect for the registered alternative) rationale that the null is two-sided. The existing `quantbot/experiment/h001_null_calibration_engine.py` correspondingly uses absolute values and `absmax`.

This is not merely test coverage or documentation wording: two-sided rejection may be driven by a large **negative** observed t-statistic. A scientifically defensible, *pre-result* directional reconciliation must be approved before H001 calibration or future real-data testing. **The pre-existing protocol and all results (if any) must remain attributable to their actual historical definitions.** If any protected/validation results were already exposed, use the preregistration's **new protocol/hypothesis**, not retroactive amendment, route.

### Reference anchors to verify against committed bytes, not chat text

| Role | Existing immutable/current path |
|---|---|
| Original registered test, economic eligibility and amendment policy | `docs/experiments/candidate1_h001_real_data_falsification_v0.json` |
| Frozen synthetic-null calibration target / six DGPs / threshold | `docs/assurance/h001_synthetic_null_calibration_spec_freeze_candidate_v001.json` |
| Existing activated two-sided semantics | `docs/control/amendments/candidate1_h001_synthetic_null_calibration_numerical_conventions_amendment_activation_v001.json` |
| Original numerical candidate and known-answer conventions | `docs/control/amendments/candidate1_h001_synthetic_null_calibration_numerical_conventions_amendment_candidate_v001.json` |
| Existing, hash-bound computational core | `quantbot/experiment/h001_null_calibration_engine.py` |
| Canonical authority/pointer | `docs/agent/START_HERE.md`, `docs/control/active_task.json`, latest immutable handoff `handoff_v041.json` |
| Isolated correction prototype, **not** effective engine | PR #337 at `ca8c1465979411435c9c29166a041f03272287c1` |

The original preregistration permits a **material change before validation result exposure** only by append-only amendment, independent review and new hashes. It disallows retroactive changes after exposure; then a new hypothesis/protocol must retain the earlier result. The available control record says `AUDIT_H001_SCIENTIFIC_CONTRACT_CONSISTENCY_BEFORE_ACTIVATION` is the current next action; this proposal does not advance that pointer.

## 2. Proposed directional scientific rule — NOT YET SELECTED OR EFFECTIVE

**Registered hypothesis:** for each of nine variants, test the *upper-tail/positive* mean net-return alternative. Distinguish the one-sided composite null `mean <= 0` from its mean-zero boundary used to form the centered bootstrap; a strong claim for the composite null requires independent scientific justification.

**Candidate algorithm to independently adjudicate:**

1. Preserve exactly nine registered series, 2,193 observations per series in synthetic calibration, the original statistic `t_i = mean_i / HAC_SE_i`, Newey–West/Bartlett convention and HAC lag **21**. Treat nonfinite or degenerate inputs with controlled fail-closed behavior; no unreviewed changes to HAC arithmetic.
2. For each of **B = 10,000** *completed* inner bootstrap replications, build **one shared synchronous stationary-bootstrap index path** over the nine series, with expected block length **63**, using the existing registered Philox/draw-coordinate contract. Per-series bootstrap numerator is `mean_i_star - mean_i`; independently recompute each resampled HAC standard error and retain its **signed** studentized `t_star_i,b`.
3. Let `M_star_b = max_{j=0..8}(t_star_j,b)` with **no absolute value**; for each observed signed `t_i`, count `c_i = sum_{b=1..B} 1[M_star_b >= t_i]`. Exact ties count as exceedances.
4. Return `p_i = (1+c_i)/(1+B)` as an **exact rational**, with statistical `reject_i = (p_i <= 0.05)`. No additional sign guard inside the p-value or reject rule. The familywise event is `any_i(reject_i)`. Raw adjusted statistical rejection is not a claim of positive economic performance.
5. Keep **economic/strategy eligibility as a distinct decision** requiring, among all frozen gates, `mean_base_cost_net_return > 0`, `mean_stress_1_net_return > 0`, sufficient activity/entries, limits on concentration, positive base means in registered years, and adjusted p-value <= 0.05. The PR #337 `positive_net_means_gate` implements only the **two mean conditions**, not the complete eligibility predicate. A low raw p-value paired with a negative base mean is **ineligible**.
6. Preserve registered family size, resampling synchronization, seeds, lengths, tie handling, alpha, candidate selection order, holdout isolation and one-shot final confirmation. The holdout's registered one-sided single-series test must undergo **separate algorithmic consistency review** before any wiring; this proposal does not silently replace its implementation.

**Adversarial sign counterexample:** for an observed `t_i=-2` and 19 toy bootstrap maxima `-3`, `p_i=1/20=0.05` with statistical `reject_i=true`, yet a negative observed *base-cost mean* must fail economic eligibility. This separates mathematical test output from claims of a profitable strategy. An independent reviewer must adjudicate whether the proposed plain upper-tail rule has valid coverage under the composite null, not treat this contrived construction as an actual market result.

**Directionality counterexample for original bug:** with observed `t_i=-2` and positive bootstrap maxima `0.5`, an absolute two-sided scheme can count large negative excursions as significant while the proposed upper-tail rule does not. Determine the correct rejection region from the preregistered hypothesis, not from the historical implementation.

## 3. Scope of error-control claims — explicit independent decision

The frozen synthetic test names **six mandatory stationary all-zero-mean DGPs**, 2,000 outer replications per DGP, and one-sided exact 95% Clopper–Pearson upper bound <= **0.075** on measured FWER events per DGP, with diagnostic stress cases excluded from formal pass/fail. At 2,000 outer replications the registered acceptance count is **<= 130** FWER events per DGP; **131 fails**. These are **pre-execution criteria**, not observed outcomes.

- The six cases probe the **complete/global null** (all nine means zero) for the registered DGPs. Such a result can substantiate *weak/global-null* FWER behavior for those cases if executed correctly. **It cannot by itself establish strong FWER control across arbitrary mixtures of true/false nulls**, nor generalize to nonstationary live markets.
- A separate qualified statistician must determine whether the signed, studentized synchronized-max bootstrap supports the intended one-sided nine-hypothesis test, which assumptions justify weak vs strong control, and whether subset pivotality or other arguments apply. Otherwise **scope the scientific claim down**, rather than silently adding new DGPs, adjusting alpha, changing the test or tuning using results.
- No calibration run is authorized. Do not conflate a future calibration PASS with positive expected return, tradability, approved real-data access, or live capital authority.

## 4. Required implementation hardening (future, separately authorized)

**Exact-B provenance (Medium):** `counts` plus an integer `B` is insufficient to prove all required bootstrap replications finished. Before any effective integration, use a fail-closed completed-replication accumulator or a rigorously bound orchestrator that records/validates: nine fixed observed statistics, exact registered coordinate/domain, ordered replication indices **0..9999**, exactly **10,000 completed replications at distinct registered replication coordinates, each using one synchronized path shared across the nine series**, no skipped/duplicated replication coordinates (identical realized index paths at different coordinates are valid and must both count), input/source hashes, fixed parameters and deterministic replay checks. Abort on missing, extra, duplicate, nonfinite, mixed-seed or mismatched coordinates. Only a **sealed completed run** may finalize `(1+c)/(B+1)`; do not allow caller-selected B in a governed production path.

**Input/RNG boundary (Medium):** the candidate PR's `guarded_raw_word` is **only a wrapper**. An authorized revision must enforce concrete `BootstrapCoordinate` type and closed DGP/case registry at the *effective engine entry point*, and valid draw-purpose/position/retry domains (`INITIAL_INDEX` at index 0; `RESTART_DECISION` and `RESTART_INDEX` for indices 1..2192; retries in 0..7). Preserve all **valid** Philox known-answer outputs and fixed draw-order semantics, including the restart-index logical allocation convention. Reject arbitrary duck-typed payload-supplying objects, bool-as-int fields, malformed counts, NaN/Inf observed thresholds, and negative/over-range counts.

**Numerical degeneracy rationale (Low):** prior 'constant resamples have probability zero' reasoning is incorrect with discrete bootstrap draws. An append-only explanatory correction must preserve the existing fail-closed zero-SE/nonfinite policy. Do not alter historical numerical-conventions bytes.

## 5. Acceptance gates — exact stop/go checks

| Gate | Required evidence and verdict |
|---|---|
| G0: Authority | Verify canonical `continuity verify` and `show` in a qualified checkout before any `PROTOCOL_LANE` mutation. A new explicitly authorized and independently reviewed governance transition must first permit an append-only amendment candidate. Otherwise **STOP: NON_EFFECTIVE PROPOSAL ONLY**. |
| G1: Source provenance | Rehash existing preregistration, effective numerical amendment, RNG contract, engine, exact PR #337 head and handoff. Record exact actual SHA-256 of source **bytes** from checkout; never invent hashes or reuse a Git blob SHA-1 as SHA-256. Original frozen files byte-identical. |
| G2: Independent statistical decision | Qualified reviewer (not author of PR #337/proposal) independently derives upper-tail vs absolute familywise test, bootstrap centering/studentization, composite-null hypothesis and claim scope, and explicitly decides any previously result-determinative ambiguity. **Written PASS or FAIL**, with referenced equations and synthetic counterexamples. |
| G3: Exact directionality checks | Nine-vector signed maxima; negative/zero/positive observed t; two-sided/one-sided distinction; full and partial ties; **(1+c)/(B+1)** integer threshold equality; no hidden t>0 statistical rejection rule; economic means tested separately; all registered eligibility conditions retained. |
| G4: Complete-run and RNG invariants | Exact 10,000 completed replications before finalized p-value; no caller-supplied shortcut. Reject B-1, B+1, duplicate/missing replication coordinates (but permit identical realized paths), corrupt counts, incorrect path sharing, unknown coordinate IDs, prohibited purpose/position, NaN/Inf, non-whole and negative counters. All historical valid Philox KAT vectors remain identical. |
| G5: Code & governance transition | Only **after** independent authorization: additive superseding amendment explicitly references prior effective two-sided semantics, gives new document/code SHA-256 and binding/provenance changes via governed append-only handoff. Never edit/remove old amendments or old handoff receipts. Verify both old and new named rule explicitly in history. |
| G6: Tests and CI | Focused synthetic regressions and independent numerical reference PASS, full canonical continuity tests and artifact checks PASS; full suite PASS **or** runner-capacity failure separately documented as **UNVERIFIED** (not green). Do not weaken test rules, change pytest tmp root, or rerun indefinitely to manufacture green. |
| G7: Future calibration only | Separate authorization must explicitly enable synthetic calibration after previous gates. Only then may six-DGP, 2,000x10,000 calibration with the frozen Clopper–Pearson threshold be performed; retain all failed results, fixed seeds and hashes, no outcome-driven tuning. Real-data/trading gates remain independently blocked. |

**Stop conditions:** any canonical source conflict, lack of independent reviewer, lack of approved append-only route, unresolved directional validity, incomplete B proof, hash drift, rejected KAT, prohibited data access, attempted merge or activation => **STOP and report**. No release/deploy/merge is implied by PASS of a proposal review.

## 6. Reviewer handoff / decision form (not a completed review)

**Requested reviewer:** qualified, independent of this proposal and PR #337 authorship; **NOT ASSIGNED**. No synthetic result or source status can substitute for identity and a recorded independent review.

The reviewer must record: (a) their independence and exact reviewed HEAD(s); (b) which one-sided statistical hypotheses and null boundary are justified; (c) whether signed upper-tail max-t has valid weak/global-null or strong/partial-null FWER claim under the existing six-DGP calibration; (d) whether `p<=alpha` is the complete statistical decision, with profitability gates distinct; (e) completeness and Philox/coordinate invariants; (f) each unresolved issue with severity; and (g) an explicit **APPROVE_PROPOSAL_FOR_GOVERNANCE_DESIGN / REQUEST_CHANGES / BLOCKED** verdict. Review approval **does not** activate a scientific protocol.

**Current verdict:** `READY_FOR_INDEPENDENT_REVIEW` as a **document-only, non-effective proposal**. **Not** `PASS_SCIENTIFIC`, **not** an effective amendment, **not** permission to merge PR #337, and **not** a license to trade.

**Non-effects:** `EDGE_UNPROVEN` · `BLOCK_LIVE_INTEGRATION` · `CALIBRATION_NOT_AUTHORIZED` · `NO_REAL_DATA_ACCESS` · `NO_MERGE`.
