# QNTY Offline-Edge — Holdout Seal Fingerprint Decision Memo

**Status:** DECISION_MEMO (docs-only; no code in this change)
**Context:** post `protocol-split-leakage-audit-v0`
**Standing guardrails (unchanged):** `EDGE_UNPROVEN`, `BLOCK_LIVE_INTEGRATION`,
enclosing receipt verdict `BLOCKED_BY_VALIDATION_IMPLEMENTATION`.

No result is claimed by this document. It decides only *which single computed
quantity QNTY is allowed to add next*, not that any edge exists.

## PLAN

`QNTY_OFFLINE_EDGE_NEXT_COMPUTED_QUANTITY_DECISION_MEMO.md` named Option B —
holdout seal fingerprint — as Option A's designated successor and explicitly
scoped it out of `protocol-split-leakage-audit-v0` "to keep this step atomic."
`protocol-split-leakage-audit-v0` shipped Option A: it materializes
`train` / `purge` / `embargo` / `holdout` row partitions from the
already-fingerprinted immutable cut and audits them for disjointness,
ordering, and gap sufficiency (`deterministic_split_audit`,
`leakage_audit_passed` / `leakage_audit_killed`). It does **not** seal the
holdout partition it identifies — the holdout rows remain exactly as
accessible after the audit as before it. That is the open seam this memo
closes.

This memo picks the next computed quantity that (a) sits directly on top of
the already-materialized and leakage-audited holdout partition, (b) executes
protocol §3 ("sealed from design, tuning, and selection; opened once, only
after the candidate and protocol are locked") which no shipped slice yet
implements, and (c) adds zero forbidden surface against
`FORBIDDEN_CALCULATION_KEYS` (`return`, `returns`, `pnl`, `sharpe`, `edge`,
`score`, `metric`, `performance`, `drawdown`, `risk`, `p_value`,
`confidence_interval`, `baseline_result`, `benchmark_result`, `trade(s)`,
`signal(s)`, `position(s)`, `portfolio`, and the rest of the frozen set).

## DECISION OPTIONS

| # | Candidate quantity | Protocol clause | Forbidden-surface risk | Dependency |
|---|---|---|---|---|
| **B** | **Holdout seal fingerprint** — SHA-256 over the holdout partition identified by `deterministic_split_audit`, recorded as a seal state (`sealed` / `unsealed`) with a registry-bound seal declaration | §3 (future holdout) | **Low** — a byte-fingerprint + boolean, same family as `input_manifest_fingerprint` / `actual_sha256` / `leakage_audit_passed` | Ready now (split materialized and leakage-audited by A) |
| C | Honest trial-count / family cardinality computation | §6, §7, §8 | Medium — pulls toward `p_value` / correction math with nothing to correct yet; premature | Needs a computed statistic that does not exist |
| D | Cost-case / net-return skeleton fill | §9, §13 | **Disqualified** — cannot be computed without a return; `net_return_value` etc. are forbidden and gated | N/A |
| E | Re-seal / re-fingerprint on registry change | §5, §11 | Low, but this is a variant of B, not an independent next step; folding it into B's kill criteria is sufficient | Subset of B |

Option B is the only candidate that is strictly-next in dependency order
(directly consumes A's output), protocol-bound (§3 is otherwise unimplemented),
and forbidden-clean. C is out of order — no computed result exists yet to
correct. D remains barred. E is not a separate quantity; its concern is
folded into B's kill criteria below.

## RED TEAM

- **"A fingerprint over row content is close enough to touching values —
  slippery slope to returns."** *Mitigation:* the seal fingerprint hashes
  **source bytes at fixed row/column boundaries already established by A**
  (the same file-region hashing already used for
  `input_manifest_fingerprint` / `data_cut_fingerprint`), not decoded prices.
  It never parses, compares, or aggregates a price/value/outcome column; it
  treats the holdout partition as an opaque byte span. Decision 2 below fixes
  this as normative.
- **"Sealing the holdout is the first step of evaluating it — this is where
  QNTY starts looking at the answer."** This is the central objection and is
  addressed directly in Decision 3: a seal fingerprint is a **write-once
  attestation that the holdout was not touched**, computed without decoding,
  comparing, or aggregating any value inside it. Producing a hash of a byte
  region is not equivalent to reading, scoring, or evaluating that region —
  the same distinction already relied on for `actual_sha256` over the whole
  cut in `v0`, which nobody has read as "QNTY evaluated the data."
- **"A `sealed` boolean is a metric."** `metric` / `score` are forbidden as
  key names and as return-derived statistics. `holdout_sealed` is a
  structural attestation state, precedented by `leakage_audit_passed` and
  `matches_expected`. *Mitigation:* never name a field `*metric*` / `*score*`
  / `*performance*`; keep names structural (`*_sealed`, `*_fingerprint`,
  `*_mismatch`).
- **"Once sealed, re-running the audit to fix a bug looks like re-opening the
  holdout — this could quietly rotate what 'sealed' means."** *Mitigation:*
  the seal is over the **exact holdout row/column byte span**, identity-bound
  to the registered `split_boundary_declaration` from A. Any re-materialization
  of the split (changed boundary, changed purge/embargo, changed source cut)
  produces a different fingerprint and must be treated as a new seal event,
  registered append-only — never silently overwritten. A seal-fingerprint
  mismatch against the registry is a kill condition, not a warning.
- **"This just restates the leakage audit with an extra hash — not a genuine
  new computed quantity."** Rebuttal: the leakage audit answers "is this
  partition structurally sound." The seal answers a different, temporally
  extended question — "has this exact partition been read, altered, or
  re-cut since it was declared sealed" — which only a persisted fingerprint
  comparison across runs can answer. It is a new computed quantity because it
  can fail (kill) on a case the leakage audit cannot detect: an untouched-looking
  but silently mutated holdout file.

## RECOMMENDATION — Option B, specified against the ten decisions

1. **What gets computed:** a SHA-256 **seal fingerprint** over the exact
   holdout row/column byte span identified by `deterministic_split_audit`
   (the `holdout_row_count` rows from `boundary_index` onward, minus the
   embargoed rows, per role), plus a `holdout_seal_state` — `sealed` on first
   registration, `mismatch` if a later run's recomputed fingerprint diverges
   from the registered value. Nothing else.
2. **What exactly is sealed, and over what:** the seal is over **role-relative
   source byte spans**, not row identities, not timestamps, and not decoded
   values.
   - *Not row identities alone* — an identity-only seal (e.g. hashing row
     indices) would not detect the holdout file being edited in place while
     row counts stay constant.
   - *Not timestamps alone* — timestamps are already covered by the leakage
     audit's monotonicity check (A); re-hashing them adds no new guarantee
     and risks conflating "ordered" with "sealed."
   - *Not source bytes globally* — hashing the whole file (already done by
     `input_manifest_fingerprint` in `v0`) does not distinguish "the holdout
     portion is untouched" from "the train portion changed but holdout
     didn't," which is the specific guarantee §3 requires.
   - **Role-relative source byte span, per role (`bars`, `funding`), computed
     as the SHA-256 of the exact byte ranges backing the holdout rows as
     resolved by the already-shipped role-relative fingerprinting path used
     for `aggregate_role_fingerprint` in `v0`/`protocol-integrity-slice-v0`.**
     This is the only option that (a) is bound to the concrete artifact
     (bytes), (b) is scoped to exactly the holdout partition (not the whole
     cut), and (c) reuses an already-audited fingerprinting mechanism rather
     than inventing a new one.
     If non-bars roles are sealed, their holdout byte spans must be resolved by
     the same timestamp convention and alignment policy declared for the supplied
     immutable cut; if a role cannot be deterministically aligned to the
     bars-derived holdout partition, the seal step must fail closed rather than
     guessing.
3. **Why sealing does not mean evaluating:** the seal fingerprint is computed
   by hashing an opaque byte span — it never decodes a column, never compares
   a value against another value, never aggregates across rows, and never
   produces or consumes a price/value/outcome. Hashing is a write-only,
   content-blind operation; the holdout is never opened, read as data, or
   scored. Protocol §3's guarantee ("sealed from design, tuning, and
   selection; opened once, only after the candidate and protocol are locked")
   is about *decision-relevant reading*, not about a boundary crossing a
   byte-count. A SHA-256 digest carries no information usable for design,
   tuning, or selection — it cannot be inverted into a value that could
   inform a choice. This is the same principle already applied to the full
   cut in `v0` (`actual_sha256` fingerprints the entire cut without that
   fingerprinting constituting "evaluation" of the cut).
4. **Why this does not compute returns/PnL/profit/edge/score/performance:**
   the seal fingerprint's only inputs are raw source bytes and row/column
   boundary indices already established by A; its only output is a 64-hex-
   character digest and a boolean/enum seal state. No price, value, outcome,
   position, trade, signal, or portfolio quantity is read, derived, or
   compared. `FORBIDDEN_CALCULATION_KEYS` is unchanged by this quantity —
   its fields (`holdout_seal_fingerprint`, `holdout_seal_state`, etc.) do not
   match any forbidden key at any depth, mirroring the existing exact-key and
   AST-forbidden-key tests that already pass for `v0`.
5. **Dependency on `protocol-split-leakage-audit-v0`:** hard dependency, not
   soft precedent. The seal fingerprint cannot exist without A's
   `deterministic_split_audit` output: it needs A's `boundary_index`,
   `holdout_row_count`, and the registered `split_boundary_declaration` to
   know *which* bytes constitute the holdout, and it must run only when A's
   `leakage_audit_passed == true` and `leakage_audit_killed == false` — a
   killed or unaudited split must never be sealed. If A's boundary or
   purge/embargo declaration changes, the seal is invalidated and must be
   recomputed and re-registered, never silently reused.
6. **Registry declaration required:** append-only; add one field to the
   existing trial-registry entry — a `holdout_seal_declaration`
   (`holdout_seal_fingerprint`, `sealed_at_boundary_index`, matching A's
   `split_boundary_index` / `purge_intervals` / `embargo_intervals`),
   registered **at first successful seal**, before any subsequent run may
   claim `holdout_seal_state: sealed`. **No new trial**
   (`honest_trial_count` stays 1) — same candidate / same data-cut / same
   split. A registry entry with a `holdout_seal_declaration` already present
   makes every later run's fingerprint recomputation-and-compare
   authoritative; a run computing a first-time seal without one entering the
   registry has produced nothing durable.
7. **Allowed receipt field names (structural only):** `holdout_seal_fingerprint`,
   `holdout_seal_state` (`sealed` | `mismatch` | `not_sealed`),
   `sealed_role_count`, `sealed_row_count`, `sealed_at_boundary_index`,
   `registry_seal_fingerprint`, `seal_fingerprint_matches_registry`,
   `holdout_seal_killed`. **Barred:** anything in `FORBIDDEN_CALCULATION_KEYS`
   and, per Decision 2, no field may imply a value/outcome was read
   (e.g. no `holdout_value_*`, no `holdout_result_*`).
   `computed_input_integrity_result.status` stays `EDGE_UNPROVEN`; verdict
   stays `BLOCKED_BY_VALIDATION_IMPLEMENTATION`.
8. **Kill criteria:** upstream `deterministic_split_audit` not present or
   `leakage_audit_killed == true`; holdout byte span cannot be resolved
   (missing/unreadable role source); seal attempted with no registry
   declaration path available; a re-run's recomputed fingerprint diverges
   from a registry-recorded `holdout_seal_fingerprint` for the same
   registered boundary/purge/embargo (`holdout_seal_killed: true`,
   `holdout_seal_state: mismatch`); registry declaration missing required
   fields; boundary/purge/embargo used for sealing does not match A's
   registered `split_boundary_declaration`. Any → `holdout_seal_killed: true`,
   no authorization advance.
9. **Tests required in the implementation PR:** seal computed only when
   upstream leakage audit passed (absent/killed upstream → seal step
   skipped, not silently sealed); first-seal registry write is append-only
   and exactly one entry; re-run with unchanged holdout bytes reproduces the
   identical fingerprint (determinism test); re-run with any single byte
   changed inside the holdout span changes the fingerprint and kills
   (`mismatch`) while a byte changed **outside** the holdout span (e.g. in
   train or purge) does not affect the seal fingerprint (scope-isolation
   test); boundary/purge/embargo mismatch against A's declaration kills;
   missing registry declaration on a claimed `sealed` state kills; existing
   forbidden-key AST + exact-key-at-any-depth tests stay green with the new
   field names added to the allow-list of structural keys; behavioral test
   asserting the seal computation path never decodes/parses a price, value,
   or outcome column (only reads raw bytes for hashing); `forbidden_calculation_status`
   all false; both authorizations false; verdict unchanged.
10. **Proceed or pause:** **PROCEED** — it is A's explicitly designated
    successor, strictly next in dependency order, protocol-bound to an
    otherwise-unimplemented clause (§3), and forbidden-clean when scoped to
    role-relative source byte spans per Decision 2. Bounded to the same
    freeze timebox discipline as A.

## ACCEPTANCE GATE

Merge the eventual implementation only if **all** hold:

1. Receipt adds only structural/attestation names; zero
   `FORBIDDEN_CALCULATION_KEYS` at any depth (existing AST + exact-key tests
   green, extended to cover the new fields).
2. All kill tests in Decision 9 fail closed, including the scope-isolation
   test (out-of-holdout byte changes do not affect the seal) and the
   determinism test (unchanged bytes reproduce identical fingerprint).
3. `forbidden_calculation_status` all false;
   `paper_trade_authorized` / `live_integration_authorized` false; verdict
   `BLOCKED_BY_VALIDATION_IMPLEMENTATION`; guardrails `edge_unproven` /
   `block_live_integration` true.
4. No price/value/outcome column decoded or compared by the seal computation
   (behavioral test present, passing) — only raw bytes are hashed.
5. Registry append-only, `honest_trial_count == 1`, `holdout_seal_declaration`
   recorded at first successful seal and never overwritten in place.
6. The seal step only runs on a split that already has
   `leakage_audit_passed == true` and `leakage_audit_killed == false` from A;
   it must be structurally impossible to seal an unaudited or killed split.
7. Outputs under `/tmp` only; no prod path in receipt; real ledgers untouched.
8. Reproducible example fixture + `emitted_receipt.json` updated; README
   documents the new kill conditions and the seal/mismatch semantics.
9. Delivered as one thin end-to-end slice within the freeze timebox; no new
   alphabet lane introduced.

## VERDICT

**PROCEED** with Option B — the holdout seal fingerprint — as specified. It is
protocol-bound (§3), forbidden-clean when scoped to role-relative source byte
spans over exactly the holdout partition, strictly dependency-next on the
merged `protocol-split-leakage-audit-v0`, and kill-capable on both structural
failure and after-the-fact tampering. **Pause** only if it cannot be delivered
as one thin slice within the freeze timebox, or if any acceptance-gate item
above cannot be met — in which case the freeze's own fallback (pause or
archive) applies.

This memo adds no code. QNTY remains `EDGE_UNPROVEN` and
`BLOCK_LIVE_INTEGRATION`.
