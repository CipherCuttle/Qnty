# QNTY Clean Net Of Carry Repair Plan

## 1. Purpose

Task: `DOCS_ONLY_CLEAN_NET_OF_CARRY_REPAIR_PLAN`

Define the minimum repair path from the current funding verdict
`CAVEATED_ENGINE_SEMANTICS` toward a future stricter label:
`CLEAN_NET_OF_CARRY`.

This is a docs-only plan. It does not implement code, edit tests, edit
fixtures, run a writer, refresh data, mutate any SQLite DB, mutate
`forward_obs`, or change services/timers.

`EDGE_UNPROVEN` is preserved. `CAVEATED_ENGINE_SEMANTICS` is preserved for the
current live ledgers.

## 2. Context

Current local preflight for this plan:

```txt
branch before plan branch: main
main == origin/main: yes, a86f1c6
tracked tree clean: yes
allowed untracked: .claude/
```

Required prerequisite docs are present on `main`:

```txt
docs/plans/QNTY_POSITION_FILL_EQUIVALENCE_AND_UNREALIZED_ATTRIBUTION_AUDIT.md
docs/plans/QNTY_FUNDING_DETERMINISM_AND_FAIL_CLOSED_AUDIT.md
docs/plans/SHADOW_LANE_BATCH14_MANUAL_PHASE3_RECEIPT.md
```

Recent canonical state:

```txt
EDGE_STATUS: EDGE_UNPROVEN
funding verdict: CAVEATED_ENGINE_SEMANTICS
PR #44 position/fill equivalence audit merged
PR #45 funding determinism audit merged
```

The position/fill audit classifies the current shadow lane as an
accounting/pipeline replication control, not a true randomized null lane
([QNTY_POSITION_FILL_EQUIVALENCE_AND_UNREALIZED_ATTRIBUTION_AUDIT.md:205-232](QNTY_POSITION_FILL_EQUIVALENCE_AND_UNREALIZED_ATTRIBUTION_AUDIT.md)).
It also records identical open symbols at the latest aligned snapshot
([QNTY_POSITION_FILL_EQUIVALENCE_AND_UNREALIZED_ATTRIBUTION_AUDIT.md:277-294](QNTY_POSITION_FILL_EQUIVALENCE_AND_UNREALIZED_ATTRIBUTION_AUDIT.md)),
identical unrealized PnL of `+199.35145548`
([QNTY_POSITION_FILL_EQUIVALENCE_AND_UNREALIZED_ATTRIBUTION_AUDIT.md:393-419](QNTY_POSITION_FILL_EQUIVALENCE_AND_UNREALIZED_ATTRIBUTION_AUDIT.md)),
and a prod-minus-shadow residual that is funding-only
([QNTY_POSITION_FILL_EQUIVALENCE_AND_UNREALIZED_ATTRIBUTION_AUDIT.md:458-496](QNTY_POSITION_FILL_EQUIVALENCE_AND_UNREALIZED_ATTRIBUTION_AUDIT.md)).

The funding determinism audit records that live prod and shadow DBs currently
have zero committed `rate_available=0` rows, while the cumulative evaluation
still cannot be labelled clean because exact-millisecond source coverage misses
two historical SOLUSDT windows per lane
([QNTY_FUNDING_DETERMINISM_AND_FAIL_CLOSED_AUDIT.md:318-405](QNTY_FUNDING_DETERMINISM_AND_FAIL_CLOSED_AUDIT.md)).

## 3. Current blocker

QNTY cannot currently use `CLEAN_NET_OF_CARRY` because the engine, verifier,
and source-funding coverage path do not share one explicit timestamp
normalization contract.

Engine behavior:

- `quantbot/paper/engine.py:90-101` builds a per-symbol funding index by
  serializing funding dataframe `dt` values with `strftime("%Y-%m-%dT%H:%M:%S")`.
  This drops subsecond precision.
- `quantbot/paper/engine.py:107-134` then sums funding events by string key in
  `(start_exclusive, end_inclusive]`.
- `quantbot/paper/engine.py:239-277` accrues funding for held long positions,
  setting `funding_amount = 0.0` when `rate_available` is false.
- `quantbot/paper/engine.py:279-310` adds exit-tail funding over
  `(exit_signal_ts, exit_fill_ts]`.

Verifier/source behavior:

- `quantbot/paper/funding_coverage.py:68-78` parses source CSV `fundingTime` as
  integer milliseconds into UTC datetimes.
- `quantbot/paper/funding_coverage.py:106-132` and
  `quantbot/paper/funding_coverage.py:363-395` check exact open-closed
  intervals with `ws < ts <= we`.
- `quantbot/paper/sqlite_verify.py:1322-1392` builds a read-only funding
  coverage stamp from the live `funding` table and source CSVs.
- `quantbot/paper/sqlite_verify.py:1521-1531` adds that stamp without changing
  the normal arithmetic status.

The millisecond-boundary mismatch is concrete:

```txt
engine: source timestamps normalized/truncated to whole seconds before interval lookup
verifier/source coverage: source timestamps compared at exact millisecond precision
```

The funding audit found these affected SOLUSDT rows:

```txt
SOLUSDT|2026-06-27T08:00:00|exit
window: (2026-06-27T08:00:00, 2026-06-27T16:00:00]
CSV fundingTime: 2026-06-27T16:00:00.009000Z
exact-ms result: source row is 9 ms after the inclusive endpoint

SOLUSDT|2026-06-30T16:00:00
window: (2026-06-30T08:00:00, 2026-06-30T16:00:00]
CSV fundingTime: 2026-06-30T16:00:00.005000Z
exact-ms result: source row is 5 ms after the inclusive endpoint
```

Source: [QNTY_FUNDING_DETERMINISM_AND_FAIL_CLOSED_AUDIT.md:390-405](QNTY_FUNDING_DETERMINISM_AND_FAIL_CLOSED_AUDIT.md).

The live DB rows are internally available:

```txt
prod rate_available=0 rows: 0
shadow rate_available=0 rows: 0
current open-position DB rate_available=0 rows since entry: 0 for all open symbols
```

Source: [QNTY_FUNDING_DETERMINISM_AND_FAIL_CLOSED_AUDIT.md:318-379](QNTY_FUNDING_DETERMINISM_AND_FAIL_CLOSED_AUDIT.md).

The caveat still stands because `rate_available=0 rows: 0` proves only internal
engine availability under the engine's current normalization. It does not prove
that the verifier can independently reproduce source coverage under exact
millisecond rules, and it does not prove that later source-file mutations cannot
change historical coverage verdicts.

## 4. Desired `CLEAN_NET_OF_CARRY` standard

`CLEAN_NET_OF_CARRY` should mean:

```txt
For the named evaluation window, every funding/carry interval required by every
held position and exit-tail stub is backed by immutable or content-addressed
source funding data; the engine, coverage gate, verifier, and tests use the same
explicit timestamp-normalization rule; the DB funding rows are independently
re-summed to the latest equity_snapshots.funding_cum and ledger_state.funding_cum
within documented precision; the verifier refuses the clean label when any
required funding interval is missing, duplicated beyond the accepted rule,
outside tolerance, source-ambiguous, unavailable, or not reproducible from the
recorded source snapshot.
```

Operationally, the clean label requires all of the following:

1. Source-backed: every required funding interval has accepted source evidence.
2. Deterministic: rerunning the same verifier against the same content-addressed
   source snapshot gives the same verdict.
3. Timestamp-normalized: engine, coverage gate, verifier, and tests share one
   rule for endpoint and millisecond treatment.
4. Independently re-summed: `funding.funding_amount` sums match
   `equity_snapshots.funding_cum` and `ledger_state.funding_cum` within a named
   tolerance.
5. Verifier-enforced: a clean-mode verifier refuses `CLEAN_NET_OF_CARRY` when
   ambiguity exists.
6. Non-retroactive: old live rows are not rewritten to manufacture cleanliness.

## 5. Current code/docs evidence

Current constants already define the label surface in
`quantbot/paper/funding_status.py:22-36`: `CLEAN_NET_OF_CARRY`,
`CAVEATED_ENGINE_SEMANTICS`, `CAVEATED_EX_FUNDING`, `FAIL`, and coverage
decisions.

The older fail-closed gate plan already states that `CLEAN_NET_OF_CARRY` is for
fully covered required funding plus consistent arithmetic, and that it must not
be reachable with any missing required funding interval
([FUNDING_COVERAGE_FAIL_CLOSED_GATE_PLAN.md:88-107](FUNDING_COVERAGE_FAIL_CLOSED_GATE_PLAN.md)).

The 2026-06-18 funding-gap receipt established the original risk: missing SOL
source rows could be treated as zero by engine semantics while verifier OK still
meant internal consistency only, not clean net-of-carry evidence
([../experiments/QNTY_FUNDING_COVERAGE_GAP_RECEIPT_2026-06-18.md:36-51](../experiments/QNTY_FUNDING_COVERAGE_GAP_RECEIPT_2026-06-18.md),
[../experiments/QNTY_FUNDING_COVERAGE_GAP_RECEIPT_2026-06-18.md:61-83](../experiments/QNTY_FUNDING_COVERAGE_GAP_RECEIPT_2026-06-18.md)).

Current live SQLite writer protection:

- `scripts/qnty-paper-sqlite-accounting.py:99-104` calls
  `run_sqlite_accounting`.
- `quantbot/paper/sqlite_writer.py:982-1005` opens the DB and begins a writer
  transaction.
- `quantbot/paper/sqlite_writer.py:1140-1146` runs the engine in memory before
  DB inserts.
- `quantbot/paper/sqlite_writer.py:1148-1207` rolls back before mutation when
  positive-duration funding rows have `rate_available=False`.
- `quantbot/paper/sqlite_writer.py:1291-1325` starts the first ledger-event
  insert path only after that gate.

Current JSONL runner protection:

- `quantbot/paper/runner.py:368-402` runs a pre-engine fail-closed funding
  coverage gate and aborts with `FUNDING_COVERAGE_MISSING` on missing or partial
  coverage.

Current SQLite verifier behavior:

- `quantbot/paper/sqlite_verify.py:835-850` re-sums funding up to each equity
  snapshot for arithmetic validation.
- `quantbot/paper/sqlite_verify.py:1322-1392` adds the funding coverage stamp.
- `quantbot/paper/sqlite_verify.py:1703-1728` renders funding coverage verdict,
  decision, totals, and missing windows.

Current schema and write surface:

- `quantbot/paper/db.py:287-302` defines the `funding` table fields.
- `quantbot/paper/sqlite_writer.py:313-339` inserts `funding` typed rows with
  `rate_available` serialized as `1` or `0`.

Current tests prove partial pieces:

- `tests/test_funding_coverage.py:103-177` covers complete, missing, partial,
  and source-dropped JSONL coverage cases.
- `tests/test_funding_coverage.py:181-216` verifies missing source coverage does
  not reach `CLEAN_NET_OF_CARRY`.
- `tests/test_paper_sqlite_funding_coverage.py:381-428` covers SQLite complete
  versus missing source verdicts.
- `tests/test_paper_sqlite_funding_coverage.py:435-478` covers partial source
  gaps and confirms the current coverage stamp is additive to arithmetic status.
- `tests/test_paper_sqlite_writer_funding_coverage.py:220-269` proves missing
  required funding aborts and leaves the SQLite ledger unmutated in the writer
  path.
- `tests/test_paper_sqlite_writer_funding_coverage.py:360-397` proves positive
  duration missing rows abort, degenerate rows do not over-fire, and malformed
  missing-funding timestamps fail closed.
- `tests/test_paper_runner_funding_coverage.py:196-309` proves the JSONL runner
  aborts before ledger mutation and before `run_engine` when source funding is
  missing.
- `tests/test_paper_pnl.py:490-534` proves held-interval and exit-tail funding
  behavior in the engine path.

Known gaps from the funding audit remain:

```txt
funding millisecond-boundary normalization: not directly proved
partial source gap abort-before-mutation in live SQLite writer path: not directly proved
prod vs shadow/manual output directory coverage: not directly proved
signed/short funding behavior: not covered; shorts unsupported
```

Source: [QNTY_FUNDING_DETERMINISM_AND_FAIL_CLOSED_AUDIT.md:288-294](QNTY_FUNDING_DETERMINISM_AND_FAIL_CLOSED_AUDIT.md).

## 6. Required repair set

Minimum safe repair set:

1. Add a shared funding timestamp-normalization function.
   The engine, coverage gate, verifier, and tests must call the same function.
   The function must define whether 5-9 ms post-endpoint rows normalize to the
   endpoint, are accepted within tolerance, or remain outside the window. The
   chosen rule must be explicit and tested.

2. Add funding source snapshot/content-addressing.
   The verifier must be able to reproduce a historical verdict from source
   content recorded with the batch or in a content-addressed receipt. Later edits
   to `data/*_funding.csv` must not silently change historical clean/caveated
   classification.

3. Add a clean-mode verifier gate.
   Current verifier status can remain arithmetic `OK`, but `CLEAN_NET_OF_CARRY`
   must require a mode that refuses the clean label when source ambiguity,
   missing rows, duplicate rows, outside-tolerance rows, or unsnapshotted source
   inputs exist.

4. Add independent funding re-sum evidence.
   A clean receipt must independently sum DB `funding.funding_amount` over the
   evaluation window and compare it to latest `equity_snapshots.funding_cum` and
   `ledger_state.funding_cum` within a documented tolerance. The existing
   per-snapshot arithmetic check is necessary but not sufficient as an
   operator-facing clean-carry receipt.

5. Add synthetic millisecond-boundary tests.
   Required cases:

   ```txt
   source row exactly at endpoint
   source row 5 ms after endpoint
   source row 9 ms after endpoint
   source row outside allowed tolerance
   missing row
   duplicate row
   ```

6. Add test-only proof for funding gap abort before DB mutation in the live
   SQLite writer path.
   Existing tests cover missing source rows and positive-duration missing engine
   rows. Add explicit partial-source and clean-mode ambiguity cases.

7. Add prod/shadow/manual path-specific proof.
   Prove the same script/function path protects prod DB, shadow DB, and manual
   frozen-forward-obs `--db-path` invocations. This can be local test proof first;
   VM read-only evidence belongs in a later acceptance receipt.

8. Keep short-funding sign tests out of the first clean-carry repair unless the
   repair attempts to enable shorts. Before shorts are enabled, signed long/short
   funding tests are mandatory.

## 7. Recommended PR sequence

Prefer small PRs in this order:

| Order | Task | Purpose | Files likely touched | Tests likely added | Acceptance gate | Rollback/safety notes | VM access needed |
| ---: | --- | --- | --- | --- | --- | --- | --- |
| 1 | `TEST_ONLY_FUNDING_TIMESTAMP_NORMALIZATION_SPEC` | Pin the intended endpoint and tolerance contract before implementation. | `tests/test_funding_coverage.py`, possibly new `tests/test_funding_timestamp_normalization.py` | Exact endpoint, +5 ms, +9 ms, outside tolerance, missing, duplicate. | Tests fail for the current mismatch or are marked as expected-future only in a docs/test planning PR. | No production code, no DB, no fixtures outside test fixtures. Easy revert. | No |
| 2 | `IMPLEMENT_SHARED_FUNDING_TIMESTAMP_NORMALIZATION` | Move engine/source/verifier timestamp handling onto one helper. | likely `quantbot/paper/funding_coverage.py`, `quantbot/paper/engine.py`, possibly new helper module under `quantbot/paper/` | Existing funding coverage tests plus new boundary tests. | Engine and coverage gate agree on all boundary cases; no current funding tests regress. | Pure code change with synthetic tests first. No writer invocation. | No |
| 3 | `TEST_ONLY_FUNDING_FAIL_CLOSED_SQLITE_WRITER_PROOF` | Prove partial source ambiguity and missing/duplicate boundary cases abort before mutation in SQLite writer tests. | `tests/test_paper_sqlite_writer_funding_coverage.py` | Partial source gap, outside tolerance, duplicate ambiguity, malformed timestamp no mutation. | DB tables remain empty and watermark unadvanced after abort. | Test-only local tmp DBs. No `/srv`. | No |
| 4 | `IMPLEMENT_VERIFIER_CLEAN_NET_OF_CARRY_GATE` | Add explicit clean-mode verifier semantics that refuse clean labels on ambiguity. | `quantbot/paper/sqlite_verify.py`, `quantbot/paper/funding_coverage.py`, CLI/wrapper if a flag is added | Clean accepted only when source-backed/snapshotted/re-summed; ambiguity returns caveated or nonzero clean-mode failure. | `CLEAN_NET_OF_CARRY` unreachable for missing, partial, duplicate, outside-tolerance, or unsnapshotted source evidence. | Additive to normal arithmetic status; do not rewrite existing DB rows. | No for unit tests; later read-only VM receipt optional |
| 5 | `ADD_FUNDING_SOURCE_SNAPSHOT_RECEIPT` | Make source funding evidence immutable or content-addressed for future clean windows. | likely writer/verifier provenance code, docs receipt template, maybe DB metadata or output manifest | Snapshot digest roundtrip; verifier refuses clean when required source snapshot is absent or digest mismatches. | Historical verdict is reproducible from recorded source content/digest, not mutable repo `data/`. | No retroactive mutation. If schema changes are proposed, isolate them in their own PR with migration plan. | No for tests; read-only VM inspection for receipt |
| 6 | `ADD_CLEAN_NET_OF_CARRY_ACCEPTANCE_RECEIPT` | Produce receipt-grade proof after the repairs land. | new docs receipt only, plus read-only command transcript if explicitly authorized | No new tests unless acceptance exposes a gap. | Current or replayed evaluation window either remains caveated with exact reasons or earns clean label through all gates. | Read-only by default. Any replay/writer is separately authorized and still caveated until gates pass. | Read-only VM likely needed |

Do not combine clean-carry repair with strategy changes.

## 8. Acceptance gates

`CLEAN_NET_OF_CARRY` is not available until all gates pass:

1. Shared timestamp normalization exists and is used by engine, coverage gate,
   verifier, and tests.
2. Boundary tests cover exact endpoint, +5 ms, +9 ms, outside tolerance, missing,
   and duplicate rows.
3. Writer fail-closed tests prove missing, partial, malformed, and ambiguous
   funding conditions abort before SQLite mutation.
4. JSONL runner and SQLite writer continue to abort before ledger mutation on
   missing required source funding.
5. Verifier clean mode refuses the clean label when source evidence is missing,
   partial, duplicate, outside tolerance, unsnapshotted, or digest-mismatched.
6. Source funding evidence is content-addressed or snapshotted with the batch or
   with a receipt-grade manifest.
7. Independent DB re-sum matches `equity_snapshots.funding_cum` and
   `ledger_state.funding_cum` within documented precision.
8. Prod, shadow, and manual `--db-path` invocation paths are proven to use the
   same gate.
9. Existing labels remain unchanged for current evidence unless a future
   receipt proves a new window clean:

   ```txt
   EDGE_UNPROVEN
   CAVEATED_ENGINE_SEMANTICS
   ```

## 9. Tests required

Required tests:

```txt
test_funding_timestamp_normalization_exact_endpoint
test_funding_timestamp_normalization_accepts_or_rejects_5ms_by_spec
test_funding_timestamp_normalization_accepts_or_rejects_9ms_by_spec
test_funding_timestamp_normalization_rejects_outside_tolerance
test_funding_timestamp_normalization_missing_row_caveated
test_funding_timestamp_normalization_duplicate_row_caveated
test_sqlite_writer_partial_source_gap_aborts_before_mutation
test_sqlite_writer_duplicate_source_row_aborts_before_mutation
test_sqlite_writer_outside_tolerance_aborts_before_mutation
test_sqlite_verifier_clean_mode_requires_snapshot_digest
test_sqlite_verifier_clean_mode_refuses_ambiguous_source
test_sqlite_verifier_independent_funding_resum_matches_equity_and_state
test_prod_shadow_manual_cli_paths_share_run_sqlite_accounting_gate
```

Existing tests that must continue passing:

```txt
tests/test_funding_coverage.py
tests/test_paper_sqlite_funding_coverage.py
tests/test_paper_sqlite_writer_funding_coverage.py
tests/test_paper_runner_funding_coverage.py
tests/test_paper_pnl.py funding audit block
tests/test_paper_matched_null.py
```

## 10. Verifier changes required

The verifier should keep the current arithmetic status model, but add a stricter
clean-carry decision path.

Required verifier behavior:

1. Preserve normal `STATUS_OK` arithmetic semantics for internally consistent
   DBs.
2. Add a clean-mode or clean-label gate that refuses `CLEAN_NET_OF_CARRY` unless
   source coverage, timestamp normalization, source snapshot, duplicate policy,
   and independent re-sum all pass.
3. Emit structured reasons when clean is refused:

   ```txt
   funding_source_missing
   funding_source_partial
   funding_source_duplicate_ambiguous
   funding_timestamp_outside_tolerance
   funding_source_snapshot_missing
   funding_source_digest_mismatch
   funding_resum_mismatch
   ```

4. Keep `CAVEATED_ENGINE_SEMANTICS` for internally consistent but non-clean
   engine/source conditions.
5. Do not convert old rows to clean by assertion. Clean labels require evidence.

## 11. Funding source/snapshot requirements

Future clean windows need source evidence that is stable after the batch is
created.

Minimum acceptable snapshot/content-addressing requirements:

1. Record the exact funding source files or rows used for the evaluation window.
2. Record SHA-256 digests for each source file or canonical row subset.
3. Record the normalization rule version.
4. Record per-symbol required windows and source rows accepted for each window.
5. Record duplicate handling: none found, or duplicates found and clean refused.
6. Make the verifier read the recorded snapshot/digest in clean mode.
7. Refuse `CLEAN_NET_OF_CARRY` if the digest is absent, mismatched, or points only
   to mutable live `data/` state.

The current verifier fallback to source CSVs under `<db_dir>/data` or repo
`data` (`quantbot/paper/sqlite_verify.py:1325-1336`) is useful for diagnostics,
but it is not by itself a historical clean-label source of truth.

## 12. Implications for exit-policy lab

Recommended classification:

```txt
EXIT_POLICY_DOCS_PLAN_ALLOWED
EXIT_POLICY_REPLAY_BLOCKED_UNTIL_CARRY_REPAIR
EXIT_POLICY_IMPLEMENTATION_BLOCKED
```

Meaning:

- Docs-only exit-policy hypothesis planning is allowed.
- Replay that would be interpreted as clean economic evidence is blocked until
  clean-carry repair exists and passes.
- Implementation of take-profit/exit-policy behavior is blocked because the
  current funding verdict remains `CAVEATED_ENGINE_SEMANTICS` and strategy
  mutation based on this audit is explicitly not justified
  ([QNTY_FUNDING_DETERMINISM_AND_FAIL_CLOSED_AUDIT.md:536-550](QNTY_FUNDING_DETERMINISM_AND_FAIL_CLOSED_AUDIT.md)).

`qnty_exit_policy_lab_v0` may define hypotheses, metrics, and required receipt
formats. It must not run a replay for interpretation, implement take-profit, or
claim improved economics until clean-carry gates pass.

## 13. Implications for shorting

Recommended classification:

```txt
SHORTING_BLOCKED_UNTIL_SIGNED_POSITION_AND_FUNDING_SIGN_TESTS
```

The current engine is explicitly long-only/fixed-notional
(`quantbot/paper/engine.py:1-6`). The null selector is also long-only and says
direction randomization/shorts are out of scope until the engine supports shorts
(`quantbot/paper/null_comparator.py:8-14`).

Before shorting:

1. Add signed position representation tests.
2. Add long and short funding sign tests.
3. Add short entry/exit fill tests.
4. Add verifier arithmetic tests proving short funding signs flow through
   `funding_amount`, trade `funding`, net PnL, equity, and `funding_cum`.
5. Only then consider direction-randomized null lanes.

## 14. Implications for real randomized null lane

Clean carry repair should precede interpretation of a real multi-seed randomized
null lane. Planning can happen earlier.

Classification:

```txt
REAL_NULL_LANE_DOCS_PLAN_ALLOWED_BEFORE_CARRY_REPAIR
REAL_NULL_LANE_OFFLINE_PLUMBING_ALLOWED_WITH_CAVEATED_OUTPUTS
REAL_NULL_LANE_ECONOMIC_INTERPRETATION_BLOCKED_UNTIL_CLEAN_CARRY
```

Precise answers:

- Can a real null lane be planned before clean carry? Yes. Docs-only design can
  define seeds, universe, matching rules, receipt shape, and acceptance gates.
- Can it be implemented before clean carry? Only as offline/test/plumbing work
  that preserves `EDGE_UNPROVEN` and `CAVEATED_ENGINE_SEMANTICS`, and only if it
  does not run writers or generate interpreted economic claims.
- Can it be interpreted before clean carry? No. Null-lane comparisons that
  include funding/carry cannot be interpreted as clean net-of-carry evidence
  until the clean-carry gates pass.

The existing matched-null fixture proves selector plumbing only. It is
synthetic, long-only, and not wired into the forward writer path
([QNTY_POSITION_FILL_EQUIVALENCE_AND_UNREALIZED_ATTRIBUTION_AUDIT.md:500-524](QNTY_POSITION_FILL_EQUIVALENCE_AND_UNREALIZED_ATTRIBUTION_AUDIT.md);
`tests/test_paper_matched_null.py:1-14`, `tests/test_paper_matched_null.py:181-197`).

## 15. What not to do

Do not:

- implement take-profit before carry semantics are clean enough for evaluation;
- implement shorting before signed position and funding sign tests exist;
- run live execution;
- run prod writer;
- run shadow writer;
- run data refresh;
- mutate prod DB, shadow DB, or `forward_obs`;
- stop/start/restart services or change timers;
- implement FrankenTrader;
- make an edge claim;
- make a profitability claim;
- relabel current live evidence from `CAVEATED_ENGINE_SEMANTICS` to
  `CLEAN_NET_OF_CARRY` without the required repairs and receipt-grade proof.

## 16. Verdict

```txt
CLEAN_NET_OF_CARRY_REPAIR_PLAN_READY_FOR_PR
```
