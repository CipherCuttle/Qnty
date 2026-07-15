# QNTY Offline-Edge — Next Computed Quantity Decision Memo

**Status:** DECISION_MEMO (docs-only; no code in this change)
**Context:** post `protocol-integrity-slice-v0`
**Standing guardrails (unchanged):** `EDGE_UNPROVEN`, `BLOCK_LIVE_INTEGRATION`,
enclosing receipt verdict `BLOCKED_BY_VALIDATION_IMPLEMENTATION`.

No result is claimed by this document. It decides only *which single computed
quantity QNTY is allowed to add next*, not that any edge exists.

## PLAN

The protocol freeze mandates exactly one next move: one thin, end-to-end
computed validation that implements the frozen protocol without expanding the
alphabet (see `QNTY_OFFLINE_EDGE_PROTOCOL_FREEZE.md`, "Required next move").

The shipped `protocol-integrity-slice-v0` computes **input integrity** only —
role-relative source-byte fingerprint, append-only registry match, and a
*declaration* check that purge/embargo are integers ≥ 1
(`build_protocol_computed_validation_slice`). It does **not** compute the split
those intervals describe. That is the open seam and the strictly-next atomic
step.

This memo picks the next computed quantity that (a) sits on top of the
already-fingerprinted immutable cut, (b) executes a numbered protocol clause the
slice currently only *declares*, and (c) adds zero forbidden surface against
`FORBIDDEN_CALCULATION_KEYS` (which already bars `return*`, `pnl`, `sharpe`,
`edge`, `score`, `metric`, `performance`, `drawdown`, `risk`, `p_value`,
`confidence_interval`, `baseline_result`, `benchmark_result`).

## DECISION OPTIONS

| # | Candidate quantity | Protocol clause | Forbidden-surface risk | Dependency |
|---|---|---|---|---|
| **A** | **Deterministic split materialization + leakage audit** — partition the fingerprinted rows by source order at a pre-declared boundary, apply purge/embargo, compute integer partition counts and a `leakage_audit` disjointness boolean | §3 future holdout, §4 purge/embargo | **Low** — ordinal row counts + booleans, same family as existing `source_file_count` / `honest_trial_count` | Ready now (cut already fingerprinted) |
| B | **Holdout seal fingerprint** — SHA-256 over the sealed holdout partition, record seal state | §3 | Low, but *requires* the split from A first | Blocked on A |
| C | **Honest trial-count / family cardinality computation** — enumerate the multiple-testing family and correction denominator | §6, §7, §8 | Medium — pulls toward `p_value` / correction math with nothing to correct yet; premature | Needs a computed statistic that does not exist |
| D | **Cost-case / net-return skeleton fill** | §9, §13 | **Disqualified** — cannot be computed without a return; `net_return_value` etc. are forbidden and gated | N/A |

Option A is the only candidate that is strictly-next in dependency order,
protocol-bound, and forbidden-clean. B is A's natural successor. C is out of
order (nothing to correct yet). D is barred by the guardrails.

## RED TEAM

- **"Row counts are a metric — forbidden."** `metric` / `score` are forbidden as
  *key names* and as return-derived statistics. Ordinal partition counts are
  structural provenance already precedented on the receipt (`source_file_count`,
  `honest_trial_count`). *Mitigation:* never name a field `*metric*` / `*score*`
  / `*performance*`; keep names structural (`*_row_count`, `*_disjoint`).
- **"Touching the split touches price → slippery slope to returns."** The
  computation reads only timestamp ordering and row position — never a price /
  value / outcome column. *Mitigation:* behavioral/AST test asserting no
  price/value/outcome column is dereferenced.
- **"Materializing a split is a search knob → inflates the trial family
  (§6/§7)."** Only if the boundary is *tuned*. *Mitigation:* boundary is
  pre-declared, fixed, and registered before execution; any post-registration
  boundary change must kill (a changed split is a new trial under §6).
- **"This is just more schema, not computation."** Rebuttal: the audit produces
  a boolean that *can be false* on real bytes and *can kill* — a genuine
  computed quantity, unlike a static field.
- **"Sealing the holdout = opening it."** Deferred: the seal is Option B, not
  this step, keeping this quantity atomic and the sealed partition untouched.

## RECOMMENDATION — Option A, specified against the ten decisions

1. **What gets computed:** the deterministic
   train / purge / embargo / holdout partition of the already-fingerprinted
   immutable cut, plus a `leakage_audit` result — integer partition counts and a
   disjointness boolean. Nothing else.
2. **Why protocol-bound:** it directly executes §3 (future holdout) and §4
   (purge/embargo), which `v0` only *declares*. It converts a declaration into a
   checked computation.
3. **Why not a forbidden output:** it computes ordinal positions and
   set-disjointness — never a price value, return, PnL, profit, edge, score,
   metric, or outcome comparison. It reads timestamp/row order only.
4. **Input data:** the **supplied immutable bars/funding cut** — the same cut
   that was byte-fingerprinted by `v0`, resolved from the caller-supplied
   `--bars-dir` / `--funding-dir`. The `docs/examples/protocol-computed-validation`
   tree is a **fixture only** and must not be treated as the fixed or canonical
   input; production/real invocations pass their own immutable cut. Only
   timestamp/row-index ordering is used, never price columns.
5. **Null/benchmark:** **none.** This is structural integrity, not inference. A
   null now risks a forbidden `baseline_result`; `null_family` stays
   declared-only until a return-generating step (which is gated).
6. **Kill criteria:** empty train; empty holdout; empty purge or empty embargo
   band when the declared interval is ≥ 1; overlapping partitions; holdout not
   strictly after train in source order; realized purge/embargo gap < declared
   intervals; boundary index out of range; non-monotonic timestamps within a
   role. Any → `leakage_audit_killed: true`, no authorization advance.
7. **Trial-registry entry:** append-only; add one field to the single existing
   entry — a `split_boundary_declaration` (`boundary_index` + `purge_intervals`
   + `embargo_intervals`), registered **before** execution. **No new trial**
   (`honest_trial_count` stays 1) — same candidate / same data-cut.
8. **Allowed receipt field names (structural only):** `boundary_index`,
   `train_row_count`, `holdout_row_count`, `purged_row_count`,
   `embargoed_row_count`, `holdout_strictly_after_train`, `partitions_disjoint`,
   `realized_purge_gap_intervals`, `realized_embargo_gap_intervals`,
   `leakage_audit_passed`, `leakage_audit_killed`. **Barred:** anything in
   `FORBIDDEN_CALCULATION_KEYS`. `computed_input_integrity_result.status` stays
   `EDGE_UNPROVEN`; verdict stays `BLOCKED_BY_VALIDATION_IMPLEMENTATION`.
9. **Tests that must fail closed:** overlap → kill; holdout-before-train → kill;
   realized gap < declared → kill; empty train/holdout/purge/embargo → kill;
   post-registration boundary change → kill; existing forbidden-key AST +
   exact-key-at-any-depth tests stay green; `forbidden_calculation_status` all
   false; both authorizations false; verdict unchanged; behavioral test that no
   price/value/outcome column is dereferenced.
10. **Proceed or pause:** **PROCEED** — it is the freeze's mandated thin slice,
    strictly next in dependency order, with zero forbidden surface. Bounded to
    the freeze timebox.

## Exact split semantics (normative)

Given source rows in recorded order per role and a declared `boundary_index`,
`purge_intervals`, `embargo_intervals`:

- `boundary_index` is the index of the **first raw holdout row**.
- **train_eligible** = rows *before* `boundary_index`.
- **holdout_eligible** = rows *from* `boundary_index` onward.
- **purged rows** = the final `purge_intervals` rows of `train_eligible`.
- **embargoed rows** = the first `embargo_intervals` rows of `holdout_eligible`.
- **train rows** = `train_eligible` minus purged rows.
- **holdout rows** = `holdout_eligible` minus embargoed rows.

Fixtures (and any real cut) must contain **enough rows for non-empty train,
purge, embargo, and holdout partitions**; otherwise the leakage audit kills.

Split materialization **may** parse timestamps and row order, but **must not**
dereference price, value, or outcome columns. Reading a market value at this
step is a protocol violation, not just a lint failure.

## ACCEPTANCE GATE

Merge the eventual implementation only if **all** hold:

1. Receipt adds only structural/ordinal names; zero `FORBIDDEN_CALCULATION_KEYS`
   at any depth (existing AST + exact-key tests green).
2. All kill tests above fail closed.
3. `forbidden_calculation_status` all false;
   `paper_trade_authorized` / `live_integration_authorized` false; verdict
   `BLOCKED_BY_VALIDATION_IMPLEMENTATION`; guardrails `edge_unproven` /
   `block_live_integration` true.
4. No price/value/outcome column dereferenced (behavioral test present, passing).
5. Registry append-only, `honest_trial_count == 1`, boundary registered before
   execution.
6. Outputs under `/tmp` only; no prod path in receipt; real ledgers untouched.
7. Reproducible example fixture + `emitted_receipt.json` updated; README
   documents the new kill conditions.
8. Delivered as one thin end-to-end slice within the freeze timebox.

## VERDICT

**PROCEED** with Option A — the deterministic-split leakage-audit computed
quantity — as specified. It is protocol-bound (§3, §4), forbidden-clean,
dependency-next, and kill-capable. **Pause** only if it cannot be delivered as
one thin slice within the freeze timebox, or if any acceptance-gate item cannot
be met — in which case the freeze's own fallback (pause or archive) applies. The
holdout seal (Option B) is the designated successor and is explicitly out of
scope here to keep this step atomic.

This memo adds no code. QNTY remains `EDGE_UNPROVEN` and
`BLOCK_LIVE_INTEGRATION`.
