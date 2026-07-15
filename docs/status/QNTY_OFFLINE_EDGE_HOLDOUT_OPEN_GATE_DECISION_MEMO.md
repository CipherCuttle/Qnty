# QNTY Offline-Edge — Holdout-Open Gate Decision Memo

**Status:** DECISION_MEMO (docs-only; no code in this change)
**Context:** post `protocol-execution-packet-lock-v0`
**Standing guardrails (unchanged):** `EDGE_UNPROVEN`, `BLOCK_LIVE_INTEGRATION`,
enclosing receipt verdict `BLOCKED_BY_VALIDATION_IMPLEMENTATION`.

No result is claimed by this document. It decides only *which single computed
quantity QNTY is allowed to add next*, not that any edge exists, and not that
holdout data may be opened.

## PLAN

`protocol-execution-packet-lock-v0` bound the seven previously-scattered
identity fields — candidate family declaration, null family declaration,
data-cut fingerprint, split boundary declaration, holdout seal fingerprint,
code commit hash, protocol version — into a single append-only
`execution_packet_declaration`, fingerprinted as
`execution_packet_fingerprint` with a `packet_lock_state`
(`locked` / `mismatch`). That closed the seam where any one constituent
artifact could drift, be swapped, or be recomputed against a mismatched
counterpart without a single check catching it.

What still does not exist anywhere in the registry is any computed answer to
the question **"are all structural prerequisites required before any future
holdout opening actually present, locked, and unkilled, right now?"** Today
that question can only be answered by a human manually re-reading five prior
receipts (`data_cut_fingerprint`, `split_boundary_declaration`,
`holdout_seal_declaration`, `execution_packet_declaration`, and their
respective kill flags) and mentally conjoining them. There is no single
computed quantity whose job is to say "structurally, nothing here blocks a
future holdout open" — nor is there one that says the opposite. This memo
picks the next computed quantity that (a) consumes only fingerprints/states
already registered by the four prior slices plus the packet lock, (b) reads
zero rows of the holdout partition itself, and (c) adds zero forbidden
surface against `FORBIDDEN_CALCULATION_KEYS` (`return`, `returns`, `pnl`,
`sharpe`, `edge`, `score`, `metric`, `performance`, `drawdown`, `risk`,
`p_value`, `confidence_interval`, `baseline_result`, `benchmark_result`,
`trade(s)`, `signal(s)`, `position(s)`, `portfolio`, and the rest of the
frozen set).

**This is explicitly not holdout evaluation.** No holdout row is read. No
return, PnL, profit, edge, score, or performance value is computed. No
paper/live authorization is granted or implied. This is a structural gate
receipt only: a boolean-flavored attestation over the *presence, locked
state, and mutual consistency* of prerequisite declarations already in the
registry.

## DECISION OPTIONS

| # | Candidate quantity | Protocol clause | Forbidden-surface risk | Dependency |
|---|---|---|---|---|
| **A** | **Holdout-open gate receipt** — a structural check over the registry that confirms every prerequisite declaration required before any future holdout open is present, its own kill flag clear, and its fingerprint internally consistent with the locked `execution_packet_declaration`; emits a single `holdout_open_gate_state` (`blocked` / `gate_passed` / `mismatch`). No holdout data opened, no outcome read. | Preamble to §3 (opening condition) | **Low** — reads only existing hex fingerprints/state enums already registered by prior slices; outputs a boolean/enum, same family as `packet_lock_state` | Ready now (execution packet is locked; this is the first quantity that has a fixed, locked referent to check against) |
| B | Honest trial-count / family cardinality computation | §6, §7, §8 | Medium — now better-defined because the execution packet fixes what "one trial" structurally is, but still logically downstream: cardinality counts *how many locked packets exist*, and the gate (A) is what determines whether a given locked packet may ever be checked against a holdout at all. Computing a count before the gate exists would leave "one trial, countable" without an answer to "usable at all." | Depends on A (needs a defined gate concept even to know what "eligible for opening" means before counting eligible trials) |
| C | Pause/archive | N/A | None — always available | N/A |
| D | Any return/cost/performance computation | §9, §13 | **Disqualified** — cannot be computed without a return; `net_return_value` etc. are forbidden and gated; also disqualified independently because it presupposes an open holdout, which nothing has authorized | N/A |

Option A is the only candidate that is strictly-next in dependency order: it
is the first quantity whose entire input surface (five prior
declarations plus the packet lock) is now fully populated and locked, and it
is a **structural precondition** to B rather than a peer — B's "honest
trial-count" only has meaning relative to trials that are structurally
eligible for holdout opening, and eligibility is exactly what A defines. C
remains a valid fallback if A cannot be delivered forbidden-clean within the
freeze timebox, per the standing freeze discipline. D remains barred, both
on forbidden-key grounds and because it presupposes an opened holdout that
nothing in this memo or its predecessors authorizes.

## RED TEAM

- **"A gate that says `gate_passed` is functionally the authorization to open
  the holdout — isn't `gate_passed` just `holdout_open_authorized` with a
  different name?"** *Mitigation:* `holdout_open_gate_state` attests only
  that structural prerequisites are present and internally consistent; it
  says nothing about whether opening should happen, when, by whom, or under
  what statistical discipline. It is read-only structural bookkeeping, the
  same category as `packet_lock_state` and `leakage_audit_passed`. Decision 7
  bars any field name that could be read as an authorization
  (`*_authorized`, `*_approved`, `*_go`, `*_ready_to_trade`); the gate's own
  `gate_passed` state must never be treated as, wired to, or substituted for
  `paper_trade_authorized` / `live_integration_authorized`, both of which
  remain independently computed and stay `false` regardless of gate state.
- **"Checking that prerequisites are 'present and locked' requires reading
  the holdout partition to confirm the seal actually covers real data —
  isn't that touching holdout content?"** *Mitigation:* the gate reads only
  the already-registered `holdout_seal_fingerprint` and
  `holdout_seal_state` as opaque hex/enum values (exactly as the execution
  packet lock did) — it never opens the file(s) the seal fingerprints, never
  decodes byte spans, and never reads a row. "Present and locked" is
  answered entirely from registry metadata already computed by
  `protocol-holdout-seal-v0` and `protocol-execution-packet-lock-v0`; this
  quantity adds no new read path into holdout content.
- **"This is just re-deriving `execution_packet_fingerprint` under a new
  name — not a new computed quantity."** Rebuttal: the packet lock answers
  "do these seven identity fields still match what was registered" — a
  pairwise/tuple consistency check with no notion of a *phase gate*. The
  gate receipt answers a categorically different question: "is the system,
  right now, in the specific state where a future holdout open would not be
  structurally premature" — which requires the packet lock to be
  `locked` (not merely present) *and* every one of its constituent kill
  flags to be clear *and* no upstream declaration to have been superseded
  since. This is a new aggregate predicate over states, not a re-fingerprint
  of the same tuple. It mirrors exactly the rebuttal used for the execution
  packet lock itself against "just packaging."
- **"If the gate ever reports `gate_passed`, that becomes de facto pressure
  to actually open the holdout regardless of statistical readiness — this
  memo is manufacturing its own momentum."** *Mitigation:* the gate reports
  only structural completeness, not statistical or design readiness (family
  cardinality, correction discipline, pre-registration completeness — all of
  §6–§8 — remain entirely uncomputed and unaddressed by this quantity).
  `gate_passed` is a necessary-but-not-sufficient signal; nothing in this
  memo or the acceptance gate below claims or implies sufficiency. Any
  future memo proposing to actually open the holdout must independently
  establish and pass its own statistical-readiness gate(s) — this receipt
  does not shortcut, imply, or pre-clear that.
- **"Reason codes on a `blocked` state could leak information about which
  specific prior artifact is broken — is that itself a form of evaluation
  creep, incentivizing patching the registry until the gate flips green?"**
  *Mitigation:* reason codes are restricted to a fixed, closed enum of
  structural conditions (e.g. missing declaration, kill flag set, fingerprint
  mismatch) tied to artifact *names*, never to any value/outcome derived from
  holdout content. This is the same transparency-vs-gaming tradeoff already
  accepted for `packet_lock_killed` and `leakage_audit_killed`; fixing a
  structural registry defect (e.g. re-locking a stale packet) is exactly the
  intended remediation path, not gaming, because it changes no computed
  outcome — only which artifacts are present and consistent.

## RECOMMENDATION — Option A, specified against the ten decisions

1. **What gets computed:** a single structural receipt with
   `holdout_open_gate_state` (`blocked` | `gate_passed` | `mismatch`),
   computed by checking, in registry order: (a) `execution_packet_declaration`
   exists and `packet_lock_state == locked`; (b) `holdout_seal_declaration`
   exists and `holdout_seal_state == sealed`; (c) `split_boundary_declaration`
   exists and `leakage_audit_passed == true`, `leakage_audit_killed ==
   false`; (d) `data_cut_fingerprint` / `input_manifest_fingerprint` exist and
   registered; (e) every constituent hash recorded inside
   `execution_packet_declaration` matches the *current* registry-authoritative
   value for that artifact (no stale reference). All true → `gate_passed`.
   Any missing/false → `blocked`. Any constituent hash mismatch detected
   independently of the packet lock's own mismatch state → `mismatch`. In
   every case (`gate_passed`, `blocked`, or `mismatch`), the gate also
   computes a single `holdout_open_gate_fingerprint`: a SHA-256 digest over
   the fixed-order, length-prefixed concatenation of exactly ten structural
   inputs — `execution_packet_fingerprint`, `packet_lock_state`,
   `holdout_seal_fingerprint`, `holdout_seal_state`, the split boundary
   declaration identity (`boundary_index` / `purge_intervals` /
   `embargo_intervals`, or `split_boundary_declaration_hash` if already
   available in the registry), `leakage_audit_passed`,
   `leakage_audit_killed`, `data_cut_fingerprint` /
   `input_manifest_fingerprint`, `protocol_version`, and the closed
   `holdout_open_gate_reason_codes` set (sorted, joined) produced by this
   same evaluation. Each field is encoded as a 4-byte big-endian length
   prefix followed by its UTF-8 bytes, in that fixed order, before hashing —
   identical length-prefix framing to how each constituent identity string
   is bound in `execution_packet_fingerprint`, chosen to make field
   boundaries unambiguous under concatenation. Nothing else is computed.
2. **Why this is strictly next after execution packet lock:** the packet lock
   is the first quantity in the chain whose own state (`locked`) gives this
   gate a fixed, non-moving referent to check completeness against. Before
   the packet was locked, "are prerequisites present" had no single anchor —
   five independently-registered declarations with no guarantee they refer
   to the same trial. Now that anchor exists, checking "is everything this
   anchor claims to bind actually still true and registered" is the natural,
   dependency-ordered next predicate — a read-only aggregation over states
   the last five slices already produced, inventing no new artifact.
3. **What inputs it may read:** only registry-resident fingerprints, hashes,
   and state/kill enums already produced by `protocol-integrity-slice-v0`,
   `protocol-split-leakage-audit-v0`, `protocol-holdout-seal-v0`, and
   `protocol-execution-packet-lock-v0` — i.e.
   `data_cut_fingerprint`/`input_manifest_fingerprint`,
   `split_boundary_declaration` (+ `leakage_audit_passed`,
   `leakage_audit_killed`), `holdout_seal_declaration` (+
   `holdout_seal_fingerprint`, `holdout_seal_state`),
   `execution_packet_declaration` (+ `execution_packet_fingerprint`,
   `packet_lock_state`, `packet_lock_killed`), and `protocol_version`. All
   read as opaque hex strings or closed-enum values.
4. **What it must not read:** any row, byte span, or decoded content of the
   holdout, train, purge, or embargo partitions; any price, value, outcome,
   position, trade, signal, or portfolio quantity; any candidate/null family
   *definition content* (only their already-registered hash, per the packet
   lock's own Decision 2 discipline); any return/PnL/profit/edge/score/
   performance/metric/p-value/confidence-interval value, none of which exist
   upstream of this quantity in the first place.
5. **Allowed receipt field names (structural only):**
   `holdout_open_gate_state` (`blocked` | `gate_passed` | `mismatch`),
   `holdout_open_gate_killed`, `holdout_open_gate_reason_codes` (closed enum
   of structural conditions, e.g. `packet_not_locked`,
   `holdout_not_sealed`, `leakage_audit_not_passed`,
   `stale_constituent_reference`, `declaration_missing`,
   `gate_fingerprint_missing`),
   `structural_prerequisite_count`, `holdout_open_gate_fingerprint`,
   `registry_gate_fingerprint`, `gate_fingerprint_matches_registry`.
   `registry_gate_fingerprint` is the `holdout_open_gate_fingerprint` value
   as read back from the registered `holdout_open_gate_declaration` (never
   recomputed); `gate_fingerprint_matches_registry` is the boolean result of
   comparing a freshly recomputed `holdout_open_gate_fingerprint` against
   `registry_gate_fingerprint` for the same ten inputs. **Barred:** anything
   in `FORBIDDEN_CALCULATION_KEYS`; per Red Team item 1, no field implying
   authorization (`*_authorized`, `*_approved`, `*_go`, `*_ready_to_trade`,
   no paper/live enablement language of any form).
   `computed_input_integrity_result.status` stays `EDGE_UNPROVEN`; verdict
   stays `BLOCKED_BY_VALIDATION_IMPLEMENTATION`.
6. **Required registry declaration:** append-only; add one new registry
   entry, `holdout_open_gate_declaration`
   (`holdout_open_gate_fingerprint`, `holdout_open_gate_state`,
   `gate_checked_at`, `structural_prerequisite_count`, and the closed
   `holdout_open_gate_reason_codes` set that produced the state, recorded
   verbatim for auditability), registered on every gate evaluation. **No new
   trial** (`honest_trial_count` stays 1) — this quantity checks the existing
   locked packet's structural surroundings, it does not create, count, or
   open any trial.
7. **Kill criteria:** any of the four upstream declarations missing or
   unregistered; `packet_lock_state != locked`; `holdout_seal_state !=
   sealed`; `leakage_audit_passed == false` or `leakage_audit_killed ==
   true`; `packet_lock_killed == true`; any constituent hash recorded in
   `execution_packet_declaration` no longer matching the current
   registry-authoritative value for that artifact (stale reference,
   independent re-detection); gate evaluation attempted with no registry
   declaration path available; the registered `holdout_open_gate_declaration`
   is missing or incomplete, or is missing `holdout_open_gate_fingerprint`
   specifically. Any → `holdout_open_gate_killed: true`,
   `holdout_open_gate_state` set to `blocked` or `mismatch` as applicable, no
   authorization advance, no holdout access.
8. **Tests required for the implementation PR:** gate evaluates to
   `gate_passed` only when all four upstream declarations are present and
   every one of their own kill flags is clear (constructive test); any single
   missing declaration flips the gate to `blocked` (four variants, one per
   declaration); any single upstream kill flag set flips the gate to
   `blocked`; a constituent-hash staleness case (an artifact re-registered
   with a new fingerprint after the packet lock referenced the old one)
   flips the gate to `mismatch`, independent of and in addition to the
   packet lock's own `packet_lock_state`; determinism test — repeated
   evaluation against an unchanged registry reproduces an identical
   `holdout_open_gate_state` and `holdout_open_gate_fingerprint`, and
   `gate_fingerprint_matches_registry` reports true; order-independence is
   explicitly *not* claimed — the ten inputs are length-prefixed and hashed
   in one fixed, documented order, and a test asserts that order is stable
   across runs; a missing-fingerprint case (registered
   `holdout_open_gate_declaration` lacks `holdout_open_gate_fingerprint`)
   kills; append-only test — each evaluation writes a new
   `holdout_open_gate_declaration` entry, never overwrites a prior one;
   existing forbidden-key AST + exact-key tests stay green with the new
   field names added to the allow-list of structural keys; behavioral test
   asserting the gate computation path
   never opens, reads, or decodes any holdout/train/purge/embargo partition
   file or row; `forbidden_calculation_status` all false; both
   `paper_trade_authorized` / `live_integration_authorized` remain false and
   untouched by gate state; verdict unchanged.
9. **How this preserves standing guardrails:** the gate is read-only
   registry aggregation over already-frozen fingerprints/enums; it computes
   no return/PnL/profit/edge/score/performance value and reads no holdout
   content, so `EDGE_UNPROVEN` is untouched. It opens no exchange connector
   and grants no capital-deployment path, so `BLOCK_LIVE_INTEGRATION` is
   untouched. It does not implement or complete holdout evaluation, honest
   trial-count, or family cardinality — all of which remain uncomputed — so
   `BLOCKED_BY_VALIDATION_IMPLEMENTATION` remains the correct enclosing
   verdict regardless of whether `holdout_open_gate_state` reports
   `gate_passed` or `blocked`.
10. **Proceed or pause:** **PROCEED** — it is the first quantity in the
    chain with a fully populated, locked input surface, is a structural
    precondition to the deferred Option B (honest trial-count/family
    cardinality), and is forbidden-clean by construction (reads only
    hex/enum registry state, never holdout content). Bounded to the same
    freeze-timebox discipline as all four prior slices; **pause/archive**
    (Option C) applies if it cannot be delivered as one thin slice within
    that timebox or if any acceptance-gate item below cannot be met.

## ACCEPTANCE GATE

Merge the eventual implementation only if **all** hold:

1. Receipt adds only structural/identity names; zero
   `FORBIDDEN_CALCULATION_KEYS` at any depth (existing AST + exact-key tests
   green, extended to cover the new fields); zero authorization-implying
   field names per Recommendation item 5 / Red Team item 1.
2. All kill tests in Recommendation item 8 fail closed, including the
   staleness-re-detection test and the append-only/determinism tests.
3. `forbidden_calculation_status` all false;
   `paper_trade_authorized` / `live_integration_authorized` false and
   provably untouched by `holdout_open_gate_state`; verdict
   `BLOCKED_BY_VALIDATION_IMPLEMENTATION`; guardrails `edge_unproven` /
   `block_live_integration` true.
4. No holdout/train/purge/embargo partition file, row, or byte span is
   opened, read, or decoded by the gate computation (behavioral test
   present, passing) — only registry-resident hash/enum values are read.
5. Registry append-only; `honest_trial_count == 1`;
   `holdout_open_gate_declaration` recorded on every evaluation and never
   overwritten in place.
6. The gate can only report `gate_passed` when `packet_lock_state ==
   locked`, `holdout_seal_state == sealed`, `leakage_audit_passed == true`,
   `leakage_audit_killed == false`, and every constituent hash inside
   `execution_packet_declaration` matches current registry-authoritative
   values; it must be structurally impossible to report `gate_passed` while
   any one of those conditions is false.
7. `holdout_open_gate_state` is documented, in code comments and README, as
   necessary-but-not-sufficient for any future holdout open; no downstream
   code path may treat `gate_passed` as authorization, readiness, or a
   go/no-go trading signal.
8. Outputs under `/tmp` only; no prod path in receipt; real ledgers
   untouched.
9. Reproducible example fixture + `emitted_receipt.json` updated; README
   documents the new reason-code enum and the blocked/gate_passed/mismatch
   semantics.
10. Delivered as one thin end-to-end slice within the freeze timebox; no new
    alphabet lane introduced.

## VERDICT

**PROCEED** with Option A — the holdout-open gate receipt — as specified. It
is the first computed quantity in this chain with a fully populated, locked
input surface (four prior slices plus the execution packet lock), is a
structural precondition to the still-deferred Option B (honest trial-count /
family cardinality), reads zero holdout content, and is forbidden-clean by
construction. It is not holdout evaluation, not a returns/PnL/profit/edge/
score/performance computation, and not a paper/live authorization — it is a
read-only structural attestation over registry state that a future holdout
open is not, right now, blocked by a missing, unlocked, unsealed, unaudited,
or stale prerequisite. **Pause/archive** (Option C) applies only if it cannot
be delivered as one thin slice within the freeze timebox, or if any
acceptance-gate item above cannot be met.

This memo adds no code. QNTY remains `EDGE_UNPROVEN` and
`BLOCK_LIVE_INTEGRATION`; the enclosing verdict remains
`BLOCKED_BY_VALIDATION_IMPLEMENTATION`.
