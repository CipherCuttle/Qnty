# QNTY Offline-Edge — Execution Packet Lock Decision Memo

**Status:** DECISION_MEMO (docs-only; no code in this change)
**Context:** post `protocol-holdout-seal-v0`
**Standing guardrails (unchanged):** `EDGE_UNPROVEN`, `BLOCK_LIVE_INTEGRATION`,
enclosing receipt verdict `BLOCKED_BY_VALIDATION_IMPLEMENTATION`.

No result is claimed by this document. It decides only *which single computed
quantity QNTY is allowed to add next*, not that any edge exists.

## PLAN

`protocol-split-leakage-audit-v0` materialized and audited the
`train` / `purge` / `embargo` / `holdout` partitions
(`deterministic_split_audit`). `protocol-holdout-seal-v0` sealed the holdout
partition identified by that audit — a role-relative source-byte-span SHA-256
(`holdout_seal_fingerprint`) plus a `holdout_seal_state`, registered
append-only in the trial registry as `holdout_seal_declaration`.

What exists in the registry today is a **scattered** set of independently
computed and independently registered fingerprints/declarations: the data-cut
fingerprint (`input_manifest_fingerprint` / `data_cut_fingerprint`,
`protocol-integrity-slice-v0`), the split boundary declaration
(`split_boundary_declaration`, `protocol-split-leakage-audit-v0`), and the
holdout seal declaration (`holdout_seal_declaration`,
`protocol-holdout-seal-v0`) — plus the candidate/null family definitions and
code/protocol identity that have never been fingerprinted or registered as a
single unit at all. Nothing yet binds these together as one atomic,
tamper-evident object. That is the open seam this memo closes: any one of
those pieces could drift, be swapped, or be recomputed against a different
counterpart without a single check catching the mismatch, because there is no
computed quantity whose job is to say "these belong together and none of
them has moved."

This memo picks the next computed quantity that (a) sits directly on top of
every fingerprint/declaration already registered by the prior three slices,
(b) is the structural precondition for anything that later needs to reason
about "this trial, exactly as declared, once" (honest trial-count, family
cardinality, eventual holdout-open gating), and (c) adds zero forbidden
surface against `FORBIDDEN_CALCULATION_KEYS` (`return`, `returns`, `pnl`,
`sharpe`, `edge`, `score`, `metric`, `performance`, `drawdown`, `risk`,
`p_value`, `confidence_interval`, `baseline_result`, `benchmark_result`,
`trade(s)`, `signal(s)`, `position(s)`, `portfolio`, and the rest of the
frozen set).

## DECISION OPTIONS

| # | Candidate quantity | Protocol clause | Forbidden-surface risk | Dependency |
|---|---|---|---|---|
| **A** | **Trial registry lock / protocol execution packet fingerprint** — SHA-256 over the identity-bound tuple {candidate family declaration, null family declaration, data-cut fingerprint, split boundary declaration, holdout seal declaration, code commit hash, protocol version}, recorded as a single append-only `execution_packet_declaration` with a `packet_lock_state` (`locked` / `mismatch`) | Preamble to §6–§8 (honest trial-count/cardinality require a fixed, countable unit — the "one trial" this packet defines) | **Low** — a byte/hash-of-hashes fingerprint + boolean, same family as `input_manifest_fingerprint` / `holdout_seal_fingerprint` | Ready now (all required constituent identities are available after the prior slices) |
| B | Holdout-open gate receipt | §3 (opening condition) | Low, but premature: a gate receipt should attest that a *locked* packet's structural preconditions are met — without a locked packet to check against, "gate satisfied" has no fixed referent and the receipt would be checking a moving target | Depends on A |
| C | Honest trial-count / family cardinality computation | §6, §7, §8 | Medium — pulls toward `p_value` / correction math with nothing to correct yet; also structurally undefined without a locked packet establishing what "one trial" is | Depends on A (needs a registered execution packet to count) |
| D | Any return/cost/performance computation | §9, §13 | **Disqualified** — cannot be computed without a return; `net_return_value` etc. are forbidden and gated | N/A |

Option A is the only candidate that is strictly-next in dependency order
(consumes the outputs of all three prior slices directly, invents no new
input), is a precondition rather than a peer of B and C (both of which need
"one locked trial" to refer to before they can be computed at all), and is
forbidden-clean. B is real but premature — it would be checking gate
satisfaction against nothing durable. C is out of order for the same reason
as it was in the prior memo, now compounded: there is still no computed
statistic to correct, and additionally no fixed unit of "one trial" to count
honestly against. D remains barred.

## RED TEAM

- **"Locking a packet that includes the candidate/null family definitions is
  where QNTY starts committing to a specific strategy — isn't that
  design/tuning, which §3 says must happen before sealing?"** *Mitigation:*
  the packet lock does not create or modify the candidate/null family
  declarations — it fingerprints declarations that must already exist and be
  registered *before* the holdout was sealed (holdout-seal's own kill
  criteria in `protocol-holdout-seal-v0` require `leakage_audit_passed` on a
  split declared prior to sealing; the candidate/null families are logically
  and temporally upstream of that, per protocol §3's "design, tuning, and
  selection" happening before sealing). The lock is a **retrospective
  attestation that these already-frozen declarations are what they claim to
  be**, not a new act of design. If the candidate/null family declarations do
  not already exist in the registry by the time this quantity runs, the lock
  step must fail closed (Decision 8) rather than backfill them.
- **"A fingerprint of a fingerprint is not a new computed quantity — it's
  just packaging."** Rebuttal: each prior fingerprint (data-cut, split
  boundary, holdout seal) currently answers "has *this one artifact* moved."
  None of them answers "do all of these artifacts, taken together, still
  refer to the same trial." A single artifact drifting silently while the
  others stay registered and green is a case none of the existing per-slice
  checks can catch — e.g. the holdout seal is recomputed and re-registered
  against a *different* split boundary than the one the data-cut fingerprint
  was taken against, with each individual check still passing in isolation.
  Only a hash over the whole tuple detects that kind of cross-artifact
  divergence. This mirrors exactly the rebuttal used for the holdout seal
  itself against "just restates the leakage audit."
- **"`packet_lock_state: locked` is functionally an authorization — it's the
  green light to run a trial."** *Mitigation:* the lock attests that the
  declared inputs are internally consistent and unchanged; it is not an
  authorization gate and must not be treated as one. `paper_trade_authorized`
  and `live_integration_authorized` are computed and gated entirely
  separately and stay `false` regardless of `packet_lock_state`. Decision 7
  bars any field name that could be read as an authorization
  (`*_authorized`, `*_approved`, `*_go`).
- **"Including the code commit hash pulls in implementation details that
  have nothing to do with data/statistics — scope creep."** *Mitigation:*
  the code commit hash is included precisely because it is *not* a
  data/statistics quantity — it is a structural identity field (which build
  computed the other five fingerprints), the same category as
  `protocol_version` already implicit in every prior receipt's schema
  version. Neither field is derived from or informs any value/outcome; both
  are opaque identity tokens, consistent with Decision 2's byte-span-only
  discipline for the holdout seal.
- **"Once locked, any future need to re-run analysis with a fixed bug in
  non-scoring code would look like tampering."** *Mitigation:* identical to
  the holdout-seal precedent — a changed code commit hash changes the packet
  fingerprint and must be treated as a new packet-lock event, registered
  append-only, never overwritten. A mismatch is a kill condition
  (`packet_lock_killed: true`), not silently absorbed, and does not retroactively
  invalidate the still-valid holdout seal or split declarations it references.

## RECOMMENDATION — Option A, specified against the ten decisions

1. **What gets computed:** a SHA-256 **execution packet fingerprint**
   (`execution_packet_fingerprint`) over the concatenated hex digests of seven
   already-registered identity fields — `candidate_family_declaration_hash`,
   `null_family_declaration_hash`, `data_cut_fingerprint`,
   `split_boundary_declaration_hash` (from A), `holdout_seal_fingerprint`
   (from holdout-seal), and `code_commit_hash` — plus `protocol_version`, and
   a `packet_lock_state` (`locked` on first registration, `mismatch` if a
   later run's recomputed fingerprint diverges from the registered value).
   Nothing else.
2. **What exactly gets locked, and over what:** the lock is over **hashes of
   already-registered declarations**, never over decoded values.
   - *Not the raw candidate/null family definitions inline* — hashing their
     already-registered declaration (not re-deriving or re-evaluating them)
     keeps this a pure identity check, not a re-specification step.
   - *Not a re-fingerprint of the data cut or holdout bytes* — those
     fingerprints already exist from prior slices; this quantity consumes
     them as opaque hex strings, it does not re-hash source bytes.
   - *Not a partial subset* — omitting any one of the seven inputs would leave
     that artifact's drift undetected by this check, defeating the purpose
     (Decision on scope in Red Team, item 2).
   - **SHA-256 over the fixed-order concatenation of the seven constituent
     identity hashes/strings**, reusing the same
     hash-of-hashes technique already implicit in how a data-cut fingerprint
     aggregates role-relative fingerprints in `protocol-integrity-slice-v0`.
3. **Why locking does not mean designing, tuning, or authorizing:** the
   packet lock hashes seven pre-existing identity strings — it never creates,
   selects, or modifies a candidate, a null, a split, or a holdout; it never
   reads a price/value/outcome; and it never sets an authorization flag. A
   SHA-256 digest of hash strings carries no information usable for design,
   tuning, selection, or approval — it can only ever answer "do these seven
   things, together, still match what was registered." This is the same
   principle already applied to `holdout_seal_fingerprint` (Decision 3 of the
   prior memo): hashing is content-blind and write-only.
4. **Why this does not compute returns/PnL/profit/edge/score/performance:**
   the packet lock's only inputs are hex-string fingerprints/hashes already
   computed and registered by prior slices, plus a commit hash and a version
   string; its only output is a 64-hex-character digest and a boolean/enum
   lock state. No price, value, outcome, position, trade, signal, or
   portfolio quantity is read, derived, or compared.
   `FORBIDDEN_CALCULATION_KEYS` is unchanged; the new fields
   (`execution_packet_fingerprint`, `packet_lock_state`, etc.) do not match
   any forbidden key at any depth, mirroring the existing exact-key and
   AST-forbidden-key tests.
5. **Dependency on prior slices:** hard dependency on all three —
   `protocol-integrity-slice-v0` (data-cut fingerprint),
   `protocol-split-leakage-audit-v0` (split boundary declaration, and its
   `leakage_audit_passed == true` / `leakage_audit_killed == false`
   requirement), and `protocol-holdout-seal-v0` (`holdout_seal_state ==
   sealed`, not `mismatch` or `not_sealed`). The packet lock must run only
   when all upstream declarations are present and none of their own kill
   conditions are set. A missing input or an upstream `mismatch`/`killed`
   state must block locking, never be silently skipped over.
6. **Registry declaration required:** append-only; add one new registry
   entry, `execution_packet_declaration`
   (`execution_packet_fingerprint`, `locked_at`, and the seven constituent
   identity hashes/strings it was computed from, recorded verbatim for auditability),
   registered **at first successful lock**, before any subsequent run may
   claim `packet_lock_state: locked`. **No new trial**
   (`honest_trial_count` stays 1) — this quantity defines what "one trial"
   structurally consists of, it does not create additional trials by
   existing.
7. **Allowed receipt field names (structural only):**
   `execution_packet_fingerprint`, `packet_lock_state`
   (`locked` | `mismatch` | `not_locked`), `packet_locked_at`,
   `registry_packet_fingerprint`, `packet_fingerprint_matches_registry`,
   `packet_lock_killed`, `execution_packet_input_count`. **Barred:** anything
   in `FORBIDDEN_CALCULATION_KEYS`; per Red Team item 3, no field implying
   authorization (`*_authorized`, `*_approved`, `*_go`, `*_ready_to_trade`);
   per Decision 2, no field implying a value/outcome was read.
   `computed_input_integrity_result.status` stays `EDGE_UNPROVEN`; verdict
   stays `BLOCKED_BY_VALIDATION_IMPLEMENTATION`.
8. **Kill criteria:** any of the seven required upstream declarations missing
   or unregistered; upstream `leakage_audit_killed == true` or
   `holdout_seal_state != sealed`; lock attempted with no registry
   declaration path available; a re-run's recomputed fingerprint diverges
   from a registry-recorded `execution_packet_fingerprint` for the same seven
   inputs (`packet_lock_killed: true`, `packet_lock_state: mismatch`);
   registry declaration missing any of the seven required constituent hashes;
   any constituent hash recorded in the packet declaration does not match
   the current registry-authoritative value for that artifact (e.g. packet
   references a stale `holdout_seal_fingerprint`). Any → `packet_lock_killed:
   true`, no authorization advance.
9. **Tests required in the implementation PR:** lock computed only when all
   seven upstream inputs are present and upstream kill states are clear
   (any missing/killed upstream → lock step skipped, not silently locked);
   first-lock registry write is append-only and exactly one entry; re-run
   with unchanged seven inputs reproduces the identical fingerprint
   (determinism test); re-run with any single constituent hash changed
   changes the packet fingerprint and kills (`mismatch`); order-independence
   is explicitly *not* claimed — the seven inputs are hashed in one fixed,
   documented order, and a test asserts that order is stable across runs;
   a stale reference test (packet declares a constituent hash that no longer
   matches the current registry value for that artifact) kills; existing
   forbidden-key AST + exact-key-at-any-depth tests stay green with the new
   field names added to the allow-list of structural keys; behavioral test
   asserting the packet-lock computation path never reads a price, value, or
   outcome field from any upstream artifact — only their hash strings;
   `forbidden_calculation_status` all false; both authorizations false;
   verdict unchanged.
10. **Proceed or pause:** **PROCEED** — it is the structural precondition for
    both the previously-deferred Option B (holdout-open gate) and Option C
    (honest trial-count), strictly next in dependency order (consumes all
    three prior slices, invents no new artifact), and forbidden-clean.
    Bounded to the same freeze timebox discipline as the prior slices.

## ACCEPTANCE GATE

Merge the eventual implementation only if **all** hold:

1. Receipt adds only structural/identity names; zero
   `FORBIDDEN_CALCULATION_KEYS` at any depth (existing AST + exact-key tests
   green, extended to cover the new fields); zero authorization-implying
   field names per Decision 7.
2. All kill tests in Decision 9 fail closed, including the stale-reference
   test and the fixed-order determinism test.
3. `forbidden_calculation_status` all false;
   `paper_trade_authorized` / `live_integration_authorized` false; verdict
   `BLOCKED_BY_VALIDATION_IMPLEMENTATION`; guardrails `edge_unproven` /
   `block_live_integration` true; `packet_lock_state` never treated as or
   coupled to either authorization flag.
4. No price/value/outcome field decoded, read, or compared by the packet-lock
   computation (behavioral test present, passing) — only hash/identity
   strings are read.
5. Registry append-only, `honest_trial_count == 1`,
   `execution_packet_declaration` recorded at first successful lock and never
   overwritten in place.
6. The lock step only runs when all three upstream slices' own kill
   conditions are clear (`leakage_audit_passed == true`,
   `leakage_audit_killed == false`, `holdout_seal_state == sealed`); it must
   be structurally impossible to lock a packet referencing a killed or
   unaudited split, or an unsealed/mismatched holdout.
7. Outputs under `/tmp` only; no prod path in receipt; real ledgers untouched.
8. Reproducible example fixture + `emitted_receipt.json` updated; README
   documents the new kill conditions and the locked/mismatch semantics.
9. Delivered as one thin end-to-end slice within the freeze timebox; no new
   alphabet lane introduced.

## VERDICT

**PROCEED** with Option A — the trial registry lock / execution packet
fingerprint — as specified. It is the structural precondition both prior
memos implicitly deferred to (holdout-open gating and honest trial-count both
need a fixed, locked unit of "one trial" to refer to), forbidden-clean when
scoped to hashing already-registered identity fields, strictly
dependency-next on all three merged prior slices, and kill-capable on missing
inputs, upstream kill states, and after-the-fact tampering or drift across
any of the seven bound artifacts. **Pause** only if it cannot be delivered as
one thin slice within the freeze timebox, or if any acceptance-gate item
above cannot be met — in which case the freeze's own fallback (pause or
archive) applies.

This memo adds no code. QNTY remains `EDGE_UNPROVEN` and
`BLOCK_LIVE_INTEGRATION`.
