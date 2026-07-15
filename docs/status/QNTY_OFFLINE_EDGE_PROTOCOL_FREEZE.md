# QNTY Offline-Edge Protocol Freeze

**Status:** FROZEN_GOVERNANCE_PROTOCOL
**Scope:** required protocol before the first computed validation result

The alphabet ladder is frozen at `ladder-final`. This is not a schema lane, a
diagnostic scaffold, or evidence of validity. QNTY remains `EDGE_UNPROVEN` and
`BLOCK_LIVE_INTEGRATION`.

## Non-negotiable protocol

1. **Exploratory versus confirmatory.** Exploratory work may generate ideas but
   may not support a claim. Confirmatory work uses this frozen protocol and may
   not change its rules after results are seen.
2. **Immutable data cut.** Before a confirmatory run, record the data cut,
   source locations, timestamp convention, code commit, and a reproducible
   SHA-256 manifest fingerprint. Any input change creates a new cut.
3. **Future holdout.** Reserve an untouched future period before model choice.
   It is sealed from design, tuning, and selection; it is opened once, only
   after the candidate and protocol are locked.
4. **Purge and embargo.** Define the split boundary, purge interval, and
   embargo interval before execution. Purging removes overlap/leakage; embargo
   prevents post-boundary information contamination. Neither is optional.
5. **Trial registry.** Register every candidate before confirmatory execution:
   identifier, hypothesis, rule version, data cut, split, parameters, owner,
   timestamp, and disposition. The registry is append-only.
6. **One trial.** A trial is one distinct candidate-rule/parameter/data-cut/
   split combination evaluated for selection or inference. Renaming, rerunning,
   reseeding, changing a filter, or changing a measurement convention does not
   make the attempt disappear.
7. **Historical variants.** Count every earlier variant, abandoned branch,
   failed run, manual selection, and materially equivalent formulation in the
   same testing family unless a pre-registered rationale proves independence.
8. **Multiple testing.** Pre-specify the family and correction method. No
   confirmatory claim is allowed without applying the correction to the honest
   trial count.
9. **Deflated/probabilistic metrics.** Pre-specify and report an appropriate
   deflated or probabilistic assessment that accounts for selection and
   uncertainty. A raw point estimate is not enough.
10. **Complexity accounting.** Record parameter count, discrete choices,
    search ranges, feature/rule choices, model complexity, and total search
    space. Unrecorded search is counted conservatively, not ignored.
11. **Deviation log.** Log every deviation before continuing: what changed,
    why, who approved it, affected trials, and whether the run is exploratory
    only. A post-result protocol edit invalidates confirmatory status.
12. **Kill criteria.** Lock objective stop conditions before the run, including
    data-integrity failure, leakage, registry incompleteness, failed controls,
    invalid correction/deflation, and pre-specified candidate failure. A kill
    ends the confirmatory attempt; it is not tuned around.
13. **Paper-trade gate.** Paper trading requires a completed confirmatory
    validation with immutable provenance, sealed-holdout treatment, honest
    trial accounting, correction, deflated/probabilistic assessment,
    complexity accounting, and no unresolved kill criterion.
14. **Live-trade gate.** Live trading requires the paper-trade gate plus a
    separately approved paper-trading operating period, explicit risk and
    operational controls, and a written authorization. It is blocked now.

## Required next move

There will be no more schema-only lanes before the first computed validation
slice. The next implementation after this freeze must be one thin,
end-to-end computed validation that implements this protocol without expanding
the alphabet. If that computed validation cannot be produced within the agreed
timebox, QNTY should be paused or archived.

No result is claimed by this document. Until that validation exists and clears
the gates above, QNTY remains `EDGE_UNPROVEN` and `BLOCK_LIVE_INTEGRATION`.
