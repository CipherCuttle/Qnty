# H001 scientific-contract consistency — independent-review candidate V001

**Classification:** ADMIN_LANE review preparation. This is **not** the canonical H001 protocol audit transition, independent approval, or authorization to execute. Review target: exact canonical main commit `610f66f6c5660e09a6c0560ae1b4262f0bfd5578` and handoff `v041`.

## Trusted continuity evidence

The existing [GitHub qnty-continuity CI run #39354282715](https://github.com/CipherCuttle/Qnty/actions/runs/39354282715) executed `python -m quantbot.continuity verify` and `show` successfully; emitted `CONTINUITY_VERIFY_OK` with receipt SHA-256 `c90088efd7bc034f52c33c13f9168788e27e34e2fb91b774d8dd576afb0e3c10`; and passed **828/828** continuity tests. That was a **PR checkout** with the same unmodified control state as canonical main, not a local clean-main verifier run. Its context packet confirms the sole next action `AUDIT_H001_SCIENTIFIC_CONTRACT_CONSISTENCY_BEFORE_ACTIVATION`.

## Source-level comparison (18/18 corrected static checks PASS)

Cross-checked effective frozen spec, numeric/RNG activated amendments, `quantbot/experiment/h001_null_calibration_engine.py`, per-run orchestration and fail-closed assurance boundary:

- **Sample:** 9 synthetic series × 2,193 8-hour periods, no real data.
- **Statistic:** HAC Bartlett lag 21; null centering at observed series means; fresh bootstrap HAC standard error; synchronous absolute maximum-t across nine series.
- **Resampling:** stationary block length 63; 10,000 paths per outer replicate; frozen +1 p-value correction, non-strict ties and alpha=0.05.
- **Cases:** closed set of six stationary null DGPs and four stress diagnostics; exactly 2,000 outer-replication indices per case. Diagnostics are not in the six-family formal gate.
- **RNG:** activated direct Philox4x64-10 bootstrap-index key/counter mapping with draw-purpose and attempt addressing and retry cap 8. DGP component streams retain their declared NumPy runtime boundary. Both activated amendments expressly *exclude* scientific execution authority.
- **Gate:** each stationary null DGP requires a one-sided 95% exact Clopper–Pearson upper confidence bound on familywise rejection frequency `<= 0.075` over 2,000 outer replicates. This criterion is not implemented by the pure bootstrap-statistics engine.

One initial automated check incorrectly read `spec_freeze_activation.authority_non_effects`; the actual schema has `authorization_state.execution_authorized=false` plus explicit `non_effects`. After correcting the **checker**, the check passes. There is no repository defect from that mismatch.

## Blockers

1. **Review not independent:** this report is the assistant's static source audit. Independent exact-head adversarial review must inspect the effective amendment hierarchy, KATs and science semantics.
2. **No activation:** `execute_calibration` still unconditionally rejects, and the per-run helper is neither effective nor wired. The v041 safety state retains `EDGE_UNPROVEN`, `BLOCK_LIVE_INTEGRATION`, scientific/paper/live authorization false and decomposition count 0/1.
3. **No runnable calibration pipeline:** DGP generation, 2,000-outer-loop FWER accumulation, exact Clopper–Pearson decision, durable result provenance, and replay/partial-run controls are governed future components; their absence does **not** falsify the reviewed pure core, but forbids any complete calibration inference.
4. **Scale risk:** six mandatory DGPs × 2,000 outer × 10,000 bootstrap = 120 million bootstrap replicates, each involving a shared 2,193-index path and nine series. Runtime/budget feasibility is unqualified. No benchmark or empirical results were generated.

## Required independent reviewer decision

On a **clean pinned checkout**, run continuity `verify` and `show` first. Then (without executing calibration) inspect activated SHA-256 bindings and independent Philox/numerical known-answer fixture derivations, DGP/stress definitions, correct familywise calibration logic, activation non-effects and fail-closed execution boundary. Record evidence-backed **PASS / FAIL / BLOCK**. A PASS approves at most consistency review; it does not create v042, activate orchestration, grant data authority or approve any trade. Any canonical handoff or activation requires its **own** separately reviewed and authorized transition.

**Candidate verdict:** `READY_FOR_INDEPENDENT_REVIEW`. **STOP**. No merge, no protocol mutation, no protected data or calibration execution.
