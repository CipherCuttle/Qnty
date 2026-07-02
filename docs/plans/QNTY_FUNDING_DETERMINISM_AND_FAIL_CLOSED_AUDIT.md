# QNTY Funding Determinism And Fail-Closed Audit

## 1. Purpose

Task: `READ_ONLY_FUNDING_DETERMINISM_AND_FAIL_CLOSED_AUDIT`

Audit whether QNTY funding/carry accounting is deterministic, fail-closed, and
interpretable enough to support future paper economic readouts.

This is paper diagnostics only. It makes no edge claim and no profitability
claim. `EDGE_UNPROVEN` and `CAVEATED_ENGINE_SEMANTICS` are preserved.

## 2. Context

Operator context:

```txt
PR #43: batch14 receipt merged
PR #44: position/fill equivalence audit merged
main: c623f96 or newer
```

The position/fill audit established:

```txt
current shadow lane = accounting/pipeline replication control
not a true randomized null
prod/shadow open positions are identical at latest aligned snapshot
+199.35145548 unrealized PnL is from BTC/ETH/SOL/XRP open positions
0.00061629 prod-minus-shadow residual is funding-only
EDGE_UNPROVEN
CAVEATED_ENGINE_SEMANTICS
```

## 3. Scope And Exclusions

Performed:

```txt
local source/docs audit
local test inventory audit
read-only VM hash guards
immutable read-only SQLite inspection by explicit absolute path
read-only source funding CSV timestamp inspection
docs-only receipt creation
```

Not performed:

```txt
writer invocation
prod writer
shadow writer
data refresh
prod DB mutation
shadow DB mutation
forward_obs mutation
systemd/timer mutation
service stop/start/restart
dependency install
migration or ALTER
WAL checkpoint
code/test/fixture change
.claude/ change
push
```

SQLite ledgers were opened only through:

```txt
file:/srv/qnty/output/paper_pnl_v1/paper_ledger.db?mode=ro&immutable=1
file:/srv/qnty/output/paper_pnl_null_shadow_v0/paper_ledger.db?mode=ro&immutable=1
```

## 4. Local Repo State

Preflight before branch creation:

```txt
branch: main
HEAD: c623f96d04541b126c211d090235f2c5177d50e1
main: c623f96d04541b126c211d090235f2c5177d50e1
origin/main: c623f96d04541b126c211d090235f2c5177d50e1
main == origin/main: yes
HEAD is c623f96 or newer: yes
tracked tree clean: yes
allowed untracked: .claude/qnty_funding_gap_forensic_vm_v0.sh
```

Required files present on main:

```txt
docs/plans/SHADOW_LANE_BATCH14_MANUAL_PHASE3_RECEIPT.md
docs/plans/QNTY_POSITION_FILL_EQUIVALENCE_AND_UNREALIZED_ATTRIBUTION_AUDIT.md
docs/plans/QNTY_V1_SHADOW_ASSERTED_IDENTITY_PNL_RECONCILIATION_AFTER_BATCH11.md
```

Receipt branch:

```txt
docs/funding-determinism-audit
```

## 5. VM State

VM target used:

```bash
ssh -i ~/.ssh/hetzner_qnty_key -o IdentitiesOnly=yes viktor@37.27.216.174
```

Read targets:

```txt
prod DB:   /srv/qnty/output/paper_pnl_v1/paper_ledger.db
shadow DB: /srv/qnty/output/paper_pnl_null_shadow_v0/paper_ledger.db
repo data: /srv/qnty/repo/data
forward_obs: /srv/qnty/output/forward_obs_v1
```

## 6. DB Identity Assertions

Prod:

```txt
DB path: /srv/qnty/output/paper_pnl_v1/paper_ledger.db
query_only: 1
baseline_label: fixed_notional_active_symbols_paper_v1
paper_engine_version: 0.3.0
config_hash: 1d61c1c779107ad194ca12febe620685bbc730edf75a766467fb45c05a74561b
forward_start_ts: 2026-06-20T16:00:00
funding_type: accrual
funding_applied_as: cash_flow
latest watermark: 2026-07-02T08:00:00
batch count: 36
```

Shadow:

```txt
DB path: /srv/qnty/output/paper_pnl_null_shadow_v0/paper_ledger.db
query_only: 1
lane_id: paper_pnl_null_shadow_v0
strategy_id: matched_null_shadow_v0
strategy_version: 0.0.0-shadow
paper_engine_version: 0.3.0
config_hash: 32c0fbccdf46af8b50ef0e6d2da9a76657038da621ff2be1dba95d82208d5d52
config_hash_v2: 50b1bbeff42d33f4413776ea14cc06281b275b346ab79c279baf959b58ae024c
forward_start_ts: 2026-06-24T16:00:00
funding_type: accrual
funding_applied_as: cash_flow
latest watermark: 2026-07-02T08:00:00
batch count: 14
```

## 7. Funding Semantics In Code

`quantbot/paper/engine.py:90-134` builds a per-symbol funding index and sums all
funding rows in `(start_exclusive, end_inclusive]`. `rate_available=False` means
no funding event landed in the interval; the engine returns `0.0`, `0` events, and
the missing flag.

`quantbot/paper/engine.py:239-277` accrues funding on held long positions. The
window start is clamped to `entry_fill_ts`; if the effective start is at or after
the bar timestamp, no funding row is emitted. The amount is:

```txt
funding_amount = notional_usd * funding_rate when rate_available
funding_amount = 0.0 when rate_available is false
```

`quantbot/paper/engine.py:279-310` adds an exit-tail funding stub over
`(exit_signal_ts, exit_fill_ts]`.

Long sign semantics:

```txt
positive funding_rate -> positive funding_amount -> subtracted from equity
negative funding_rate -> negative funding_amount -> adds to equity through subtraction
```

This follows `engine.py:256-260` and `engine.py:323-329`. `engine.py:1-6` and
`quantbot/paper/null_comparator.py:8-14` state the current paper engine is
long-only/fixed-notional. Shorts and short funding sign are not supported.

The loader preserves millisecond funding timestamps (`quantbot/data/funding_loader.py:20-34`),
but `engine.build_funding_index` serializes funding `dt` with second precision
(`engine.py:99-101`). The verifier/source coverage path parses exact CSV
milliseconds (`quantbot/paper/funding_coverage.py:68-78`). That mismatch is now
part of what `CAVEATED_ENGINE_SEMANTICS` means for the current live ledgers.

`CAVEATED_ENGINE_SEMANTICS` is defined in `quantbot/paper/funding_status.py:22-29`
with diagnostic label:

```txt
missing_funding_treated_as_zero_like_current_engine_not_net_of_carry_clean
```

The DB stores funding rows with `rate_available`: schema in
`quantbot/paper/db.py:287-302`; SQLite writer insertion in
`quantbot/paper/sqlite_writer.py:313-339`.

## 8. Fail-Closed Gate In Code

There are two runner families:

1. Legacy JSONL runner: `quantbot/paper/runner.py:368-402` runs a pre-batch
   source coverage gate after freshness/divergence and before `run_engine`.
   `COVERAGE_MISSING` or `COVERAGE_PARTIAL` aborts with
   `FUNDING_COVERAGE_MISSING`; exceptions inside the gate also abort.
2. Live SQLite writer path: `scripts/qnty-paper-sqlite-accounting.py:99-104`
   calls `quantbot.paper.sqlite_writer.run_sqlite_accounting`. The SQLite writer
   runs the engine in memory only (`sqlite_writer.py:1140-1146`), then applies a
   post-engine, pre-insert funding gate (`sqlite_writer.py:1148-1207`).

For the SQLite path, a positive-duration funding row with `rate_available=False`
is fail-closed:

```txt
status: STATUS_ABORTED
message code: FUNDING_COVERAGE_MISSING
DB action: rollback and close before _insert_ledger_batch or any typed row insert
```

The gate excludes zero-duration/degenerate exit stubs, and treats unparseable
timestamps on a missing-funding row as fail-closed (`sqlite_writer.py:1183-1191`).
The first insert path starts only after that gate (`sqlite_writer.py:1241-1256`).

Coverage:

```txt
prod writer path: covered if it uses qnty-paper-sqlite-accounting.py/run_sqlite_accounting
shadow writer path: covered if it uses the same script/function with shadow --db-path
manual frozen-forward_obs invocation: covered if it uses the same script/function
direct DB writes or alternate writer code: not covered by this audit
historical committed batches: not retroactively changed by the gate
```

The verifier does not enforce the writer gate as a hard status failure. It adds a
read-only funding coverage stamp (`sqlite_verify.py:1322-1392`) and then preserves
the arithmetic status unless normal verifier failures exist (`sqlite_verify.py:1521-1544`).

## 9. Test Coverage Findings

Found:

```txt
SQLite writer missing funding abort:
  tests/test_paper_sqlite_writer_funding_coverage.py:220-229

SQLite writer abort leaves DB unmutated:
  tests/test_paper_sqlite_writer_funding_coverage.py:258-269

SQLite writer complete funding proceeds:
  tests/test_paper_sqlite_writer_funding_coverage.py:234-252

SQLite writer positive-duration missing row aborts:
  tests/test_paper_sqlite_writer_funding_coverage.py:360-367

SQLite writer malformed timestamp on missing row fails closed:
  tests/test_paper_sqlite_writer_funding_coverage.py:390-397

JSONL runner missing SOL funding aborts before ledger mutation:
  tests/test_paper_runner_funding_coverage.py:196-217

JSONL runner complete funding does not abort:
  tests/test_paper_runner_funding_coverage.py:223-249

JSONL runner abort short-circuits before run_engine:
  tests/test_paper_runner_funding_coverage.py:255-279

Verifier/source coverage clean/missing/partial/caveated tests:
  tests/test_funding_coverage.py:103-177
  tests/test_funding_coverage.py:181-216
  tests/test_paper_sqlite_funding_coverage.py:1-18

Funding row arithmetic tests:
  tests/test_paper_sqlite_writer.py:961-987

Entry/hold/exit-tail funding tests:
  tests/test_paper_pnl.py:490-521

Long-only invariant:
  tests/test_paper_pnl.py:238-244
```

Gaps:

```txt
partial source gap abort-before-mutation in the live SQLite writer path: not directly proved
prod vs shadow/manual output directory coverage: not directly proved
funding millisecond-boundary normalization: not directly proved
signed/short funding behavior: not covered; shorts unsupported
```

No tests were added or changed in this audit.

## 10. Live DB Funding Audit

Funding table schema in both DBs:

```txt
seq INTEGER
batch_id INTEGER NOT NULL
funding_id TEXT NOT NULL
bar_commit_id TEXT NOT NULL
symbol TEXT NOT NULL
bar_ts TEXT NOT NULL
window_start TEXT NOT NULL
window_end TEXT NOT NULL
notional_usd REAL NOT NULL
funding_rate REAL NOT NULL
funding_events INTEGER NOT NULL
rate_available INTEGER NOT NULL
funding_amount REAL NOT NULL
```

Prod funding:

```txt
row_count: 23
rate_available=0 rows: 0
rate_available=1 rows: 23
rate_other rows: 0
min bar_ts: 2026-06-21T08:00:00
max bar_ts: 2026-07-02T08:00:00
min window_start: 2026-06-21T00:00:00
max window_end: 2026-07-02T08:00:00
symbols: BTCUSDT, ETHUSDT, SOLUSDT, XRPUSDT
symbols with rate_available=0 rows: none
funding sum from table: 0.80232194
latest equity funding_cum: 0.80232197
ledger_state funding_cum: 0.8023219655464447
```

Prod per symbol:

```txt
BTCUSDT rows 1, missing 0, sum 0.04188407
ETHUSDT rows 3, missing 0, sum 0.07144939
SOLUSDT rows 17, missing 0, sum 0.70603180
XRPUSDT rows 2, missing 0, sum -0.01704332
```

Shadow funding:

```txt
row_count: 13
rate_available=0 rows: 0
rate_available=1 rows: 13
rate_other rows: 0
min bar_ts: 2026-06-25T08:00:00
max bar_ts: 2026-07-02T08:00:00
min window_start: 2026-06-25T08:00:00
max window_end: 2026-07-02T08:00:00
symbols: SOLUSDT
symbols with rate_available=0 rows: none
funding sum from table: 0.67588401
latest equity funding_cum: 0.67588404
ledger_state funding_cum: 0.6758840359174081
```

Latest aligned snapshot in both lanes:

```txt
bar_ts: 2026-07-02T08:00:00
snapshot open symbols: BTCUSDT, ETHUSDT, SOLUSDT, XRPUSDT
current open_positions after batch: BNBUSDT, BTCUSDT, ETHUSDT, SOLUSDT, XRPUSDT
current open-position DB rate_available=0 rows since entry: 0 for all open symbols
SOLUSDT funding rows since entry_fill_ts 2026-06-29T16:00:00: 8 available, 0 missing
new BTC/ETH/XRP/BNB positions have no committed required funding rows yet after entry
```

Committed `rate_available=0` rows:

```txt
prod: none
shadow: none
```

Source coverage recheck against `/srv/qnty/repo/data`:

```txt
prod affected batches: 21, 31
shadow affected batches: 5, 10
affected symbol: SOLUSDT
affected rows per lane: 2
```

Affected rows:

```txt
SOLUSDT|2026-06-27T08:00:00|exit
window: (2026-06-27T08:00:00, 2026-06-27T16:00:00]
CSV fundingTime: 2026-06-27T16:00:00.009000Z
result: source row is 9 ms after the inclusive endpoint, so exact-ms source coverage misses it

SOLUSDT|2026-06-30T16:00:00
window: (2026-06-30T08:00:00, 2026-06-30T16:00:00]
CSV fundingTime: 2026-06-30T16:00:00.005000Z
result: source row is 5 ms after the inclusive endpoint, so exact-ms source coverage misses it
```

This explains why `rate_available=0` is zero while the current funding verdict
still cannot become `CLEAN_NET_OF_CARRY`.

## 11. Historical Batch Coverage Audit

Funding gate implementation commit:

```txt
2484e047aa34f58ea29326c37daf6e35806f1517
2026-06-19 02:43:25 +0200
Add SQLite writer funding fail-closed gate
```

Live DB batch provenance:

```txt
prod batches 1-14: git_sha e784a8c8d992919e12983573a2d12bce35004493
prod batches 15-36: git_sha fde43a511ef98d7292a6bd93dd9e198ea92f79fe
shadow batches 1-14: git_sha fde43a511ef98d7292a6bd93dd9e198ea92f79fe
```

Local ancestry check:

```txt
2484e04 is ancestor of e784a8c8d992919e12983573a2d12bce35004493: yes
2484e04 is ancestor of fde43a511ef98d7292a6bd93dd9e198ea92f79fe: yes
```

Therefore, in the current live SQLite ledgers:

```txt
committed prod batches before fail-closed gate existed: none found
committed shadow batches before fail-closed gate existed: none found
committed prod batches after gate existed: 1-36
committed shadow batches after gate existed: 1-14
committed batches with rate_available=0 rows: none
committed batches affected by exact-ms source coverage caveat:
  prod: 21, 31
  shadow: 5, 10
```

The older 2026-06-18 funding-gap docs remain historically relevant, but this
audit did not find `rate_available=0` rows in the current live SQLite DBs.

The current cumulative live evaluation window cannot be labelled
`CLEAN_NET_OF_CARRY` because the verifier/source recheck has exact-millisecond
coverage misses and the funding source is not snapshotted with the batch in a
way that proves deterministic re-sum independent of later source-file state and
timestamp normalization rules.

## 12. Synthetic Fail-Closed Proof Status

Existing synthetic proof:

```txt
funding gap -> SQLite writer aborts before DB mutation:
  tests/test_paper_sqlite_writer_funding_coverage.py:258-269

positive-duration missing row -> abort + no mutation:
  tests/test_paper_sqlite_writer_funding_coverage.py:360-367

malformed missing-funding timestamp -> abort + no mutation:
  tests/test_paper_sqlite_writer_funding_coverage.py:390-397
```

Future test-only task still recommended:

```txt
TEST_ONLY_FUNDING_FAIL_CLOSED_PROOF
```

Scope for that future task:

```txt
prove partial source gap aborts before mutation in the live SQLite writer path
prove prod/shadow/manual --db-path invocations use the same fail-closed gate
pin millisecond-boundary funding source behavior
pin verifier red/caveat semantics for clean-window claims
```

No future test was implemented in this audit.

## 13. CLEAN_NET_OF_CARRY Requirements

Required before replacing `CAVEATED_ENGINE_SEMANTICS` with
`CLEAN_NET_OF_CARRY`:

```txt
1. All writer paths that can commit a paper batch must use the fail-closed gate.
2. Missing required funding must abort before ledger mutation.
3. Partial source coverage must abort before ledger mutation or be explicitly non-evidentiary.
4. Gate exception paths must abort before ledger mutation.
5. The verifier must refuse clean-window labels when source funding is missing or ambiguous.
6. Funding source data used for a batch must be snapshotted or otherwise content-addressed.
7. Funding timestamp cadence/normalization must be defined, including millisecond offsets.
8. Engine funding timestamp normalization and verifier source coverage must use the same rule.
9. Funding table sums must independently match equity/ledger_state funding_cum within documented precision.
10. Entry/hold/exit-tail windows must remain tested.
11. Long sign behavior must remain tested.
12. Short funding sign tests must exist before shorts are enabled.
13. A receipt-grade proof must show no missing/unavailable funding rows in the evaluation window.
14. A receipt-grade proof must show no source recheck gaps in the evaluation window.
```

## 14. Implications For Current PnL Interpretation

`EDGE_UNPROVEN` is preserved.

Current funding/carry arithmetic is internally consistent under existing engine
semantics:

```txt
prod latest equity funding_cum: 0.80232197
prod funding table sum: 0.80232194
shadow latest equity funding_cum: 0.67588404
shadow funding table sum: 0.67588401
```

The current live DBs have no committed `rate_available=0` rows, and the latest
open-position funding rows since entry have no DB missing flags. However, the
cumulative live evaluation remains `CAVEATED_ENGINE_SEMANTICS` because two
historical SOLUSDT windows per lane fail exact-millisecond source coverage
recheck.

This audit supports paper diagnostics only. It does not show alpha, edge,
deployability, or real-money profitability.

## 15. Implications For Exit-Policy Lab

Take-profit or exit-policy implementation is not justified by this audit.

Allowed:

```txt
docs-only exit-policy lab planning
read-only audit/design of funding-clean evaluation requirements
explicitly authorized paper replay only under CAVEATED_ENGINE_SEMANTICS unless CLEAN_NET_OF_CARRY gates are proven
```

Blocked by this audit:

```txt
claiming clean net-of-carry economics
using current live cumulative PnL as clean carry-adjusted evidence
strategy mutation based on this funding audit
live or production trading implication
```

## 16. Implications For Shorting

Shorting remains blocked.

The current paper engine is long-only/fixed-notional. Direction randomization and
shorts are explicitly out of scope until the engine supports shorts
(`quantbot/paper/null_comparator.py:8-14`). This audit did not add short support,
short funding sign semantics, or short funding tests.

## 17. Mutation Guards

Before VM reads:

```txt
prod DB sha256:   06ea139db69aca17b72fb7e667962212bcbffc616a8f69c71d7da14943c3a14e
shadow DB sha256: 2ee2ba884278dffd08f6145e80d3b852c4e42fa8a49400291aa8868437c97f47
forward_obs hash: a8b8a761953a49c93e54bd5b0d7fe10944a1ef534a62f9e0e75b601c8807f521
```

After VM reads:

```txt
prod DB sha256:   06ea139db69aca17b72fb7e667962212bcbffc616a8f69c71d7da14943c3a14e
shadow DB sha256: 2ee2ba884278dffd08f6145e80d3b852c4e42fa8a49400291aa8868437c97f47
forward_obs hash: a8b8a761953a49c93e54bd5b0d7fe10944a1ef534a62f9e0e75b601c8807f521
```

Result:

```txt
prod DB unchanged: yes
shadow DB unchanged: yes
forward_obs unchanged: yes
```

## 18. Verdict

```txt
FUNDING_AUDIT_COMPLETE_CAVEAT_STANDS_GATE_PRESENT
```
