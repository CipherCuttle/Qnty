# QNTY Position Fill Equivalence And Unrealized Attribution Audit

## 1. Purpose

Task: `READ_ONLY_POSITION_FILL_EQUIVALENCE_AND_UNREALIZED_ATTRIBUTION_AUDIT`

Explain why prod and shadow overlap PnL tracks almost identically, attribute the
current large unrealized PnL, and classify the current `paper_pnl_null_shadow_v0`
lane semantics.

This is paper diagnostics only. It makes no edge claim and no profitability
claim. `EDGE_UNPROVEN` and `CAVEATED_ENGINE_SEMANTICS` are preserved.

## 2. Context

Repo state provided by operator:

```txt
latest main after batch14 receipt merge: 9e1575a
PR #43 merged: docs: add shadow lane batch14 manual receipt

prod lane: paper_pnl_v1
shadow lane: paper_pnl_null_shadow_v0

prod watermark:       2026-07-02T08:00:00
forward_obs latest:   2026-07-02T08:00:00
shadow watermark:     2026-07-02T08:00:00

prod batch:           36
shadow batch:         14
```

Prior batch14 receipt recorded the latest overlap delta:

```txt
first shared timestamp: 2026-06-24T16:00:00
latest shared timestamp: 2026-07-02T08:00:00
prod delta:              +176.86587642
shadow delta:            +176.86526013
prod-minus-shadow delta: +0.00061629
```

## 3. Scope And Exclusions

Performed:

```txt
local source/docs audit
read-only VM preflight
immutable read-only SQLite inspection
local OHLCV mark lookup from /srv/qnty/repo/data
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
source/test/fixture change
.claude/ change
push
```

SQLite ledgers were opened only by explicit absolute URI:

```txt
file:/srv/qnty/output/paper_pnl_v1/paper_ledger.db?mode=ro&immutable=1
file:/srv/qnty/output/paper_pnl_null_shadow_v0/paper_ledger.db?mode=ro&immutable=1
```

## 4. Local Repo State

Preflight before branch creation:

```txt
branch: main
HEAD: 9e1575aa1d2171466c16e97cd4aeb633430a95c2
origin/main: 9e1575aa1d2171466c16e97cd4aeb633430a95c2
main == origin/main: yes
HEAD is 9e1575a or newer: yes
tracked worktree diff: none
cached diff: none
allowed untracked: .claude/qnty_funding_gap_forensic_vm_v0.sh
```

Required receipt files were present on main:

```txt
docs/plans/SHADOW_LANE_BATCH11_MANUAL_PHASE3_RECEIPT.md
docs/plans/QNTY_V1_SHADOW_ASSERTED_IDENTITY_PNL_RECONCILIATION_AFTER_BATCH11.md
docs/plans/SHADOW_LANE_BATCH12_MANUAL_PHASE3_RECEIPT.md
docs/plans/SHADOW_LANE_BATCH13_MANUAL_PHASE3_RECEIPT.md
docs/plans/SHADOW_LANE_BATCH14_MANUAL_PHASE3_RECEIPT.md
```

Branch created for this receipt:

```txt
docs/position-fill-equivalence-audit
```

## 5. VM State

VM target used:

```bash
ssh -i ~/.ssh/hetzner_qnty_key -o IdentitiesOnly=yes viktor@37.27.216.174
```

The `192.168.1.100` host was not used.

VM identity and service state:

```txt
HOSTNAME=ubuntu-4gb-hel1-1-qnty
UTC=2026-07-02T18:46:32Z
running qnty services: none
```

Timer state was recorded for awareness only:

```txt
qnty-watermark-watchdog.timer next 2026-07-02 19:00:53 UTC, last 2026-07-02 18:00:34 UTC
qnty-healthcheck.timer        next 2026-07-02 20:02:45 UTC, last 2026-07-02 16:04:28 UTC
qnty-data-refresh.timer       next 2026-07-03 00:05:11 UTC, last 2026-07-02 16:05:08 UTC
qnty-shadow-run.timer         next 2026-07-03 00:11:06 UTC, last 2026-07-02 16:10:57 UTC
qnty-paper-pnl.timer          next 2026-07-03 00:21:23 UTC, last 2026-07-02 16:20:48 UTC
qnty-health-receipt.timer     next 2026-07-03 00:32:56 UTC, last 2026-07-02 16:31:33 UTC
qnty-daily-summary.timer      next 2026-07-03 17:00:00 UTC, last 2026-07-02 17:00:03 UTC
```

Watermarks and integrity:

```txt
prod watermark:       2026-07-02T08:00:00
shadow watermark:     2026-07-02T08:00:00
forward_obs latest:   2026-07-02T08:00:00
forward_obs rows:     500
prod integrity_check: ok
shadow integrity_check: ok
```

## 6. DB Identity Assertions

Prod DB:

```txt
DB path: /srv/qnty/output/paper_pnl_v1/paper_ledger.db
lane_id: absent
strategy_id: absent
version/paper_engine_version: 0.3.0
config_hash: 1d61c1c779107ad194ca12febe620685bbc730edf75a766467fb45c05a74561b
config_hash_v2: absent
forward_start_ts: 2026-06-20T16:00:00
baseline_label: fixed_notional_active_symbols_paper_v1
latest batch: 36
latest equity: 10161.53197739
```

Shadow DB:

```txt
DB path: /srv/qnty/output/paper_pnl_null_shadow_v0/paper_ledger.db
lane_id: paper_pnl_null_shadow_v0
strategy_id: matched_null_shadow_v0
version/strategy_version: 0.0.0-shadow
paper_engine_version: 0.3.0
config_hash: 32c0fbccdf46af8b50ef0e6d2da9a76657038da621ff2be1dba95d82208d5d52
config_hash_v2: 50b1bbeff42d33f4413776ea14cc06281b275b346ab79c279baf959b58ae024c
forward_start_ts: 2026-06-24T16:00:00
baseline_label: fixed_notional_active_symbols_paper_v1
latest batch: 14
latest equity: 10176.86526013
```

No DB identity mismatch was found.

## 7. Source-Code Lane Semantics Audit

The paper engine consumes active symbols directly from each observation:

- `quantbot/paper/engine.py:220` sets `desired = set(obs.get("active_symbols", []))`.
- `quantbot/paper/engine.py:239-354` snapshots equity/positions before T+1 fills.
- `quantbot/paper/engine.py:357-447` applies exits/entries after the snapshot.

The SQLite writer path passes the observation log directly into the engine:

- `scripts/qnty-paper-sqlite-accounting.py:99-104` delegates to `run_sqlite_accounting`.
- `quantbot/paper/sqlite_writer.py:1077` reads `per_bar_obs = obs_log.get("per_bar_obs", [])`.
- `quantbot/paper/sqlite_writer.py:1140-1147` calls `run_engine(engine_config, per_bar_obs, ...)`.

The matched-null selector exists, but is not called by the forward writer path:

- `quantbot/paper/null_comparator.py:37-80` defines `select_null_active`.
- `quantbot/paper/null_comparator.py:51-52` says one seed is only a plumbing/fixture test.
- `rg -n "select_null_active|from quantbot\\.paper\\.null_comparator|import .*null_comparator" quantbot scripts tests docs README.md KNOWN_LIMITATIONS.md DISCLAIMER.md` found imports/calls in `tests/test_paper_matched_null.py` and offline fixture docs, not in `scripts/qnty-paper-sqlite-accounting.py`, `quantbot/paper/sqlite_writer.py`, `quantbot/paper/runner.py`, or `quantbot/paper/engine.py`.

Existing docs already warn against overreading one null fixture:

- `docs/plans/PARALLEL_SHADOW_LANES_PLAN.md:100-121` defines the intended true null as randomized selection/direction and says many seeds are required.
- `docs/plans/OFFLINE_MATCHED_NULL_FIXTURE_PHASE2_RECEIPT.md:12-16` says Phase 2 was a plumbing/fixture step, not a strategy result.
- `docs/plans/OFFLINE_MATCHED_NULL_FIXTURE_PHASE2_RECEIPT.md:23-27` says the production runner/writer/verifier were intentionally not changed.
- `docs/plans/OFFLINE_MATCHED_NULL_FIXTURE_PHASE2_RECEIPT.md:107-109` preserves `EDGE_UNPROVEN` and says the fixture proves only null-selection plumbing.

Boundary docs inspected:

- `README.md:3-8` says QNTY is research preview, shadow-only, and does not prove deployable alpha.
- `KNOWN_LIMITATIONS.md:7-16` says no live trading and forward burn-in is not edge.
- `DISCLAIMER.md:5-13` says no financial advice, no guarantee of profit, and no live-capital authorization.
- `docs/CURRENT_STATE.md:3-11` says shadow-only, not deployment-ready, operational burn-in is machine-health evidence only.
- `docs/PROJECT_BOUNDARIES.md:5-10` frames QNTY as research/falsification/paper replay.
- `quantbot/paper/funding_status.py:22-29` preserves `CAVEATED_ENGINE_SEMANTICS`.

Conclusion:

```txt
select_null_active called by forward writer path: no
engine consumes obs["active_symbols"] directly: yes
current shadow lane randomized by writer path: no
current shadow lane best description: accounting/pipeline replication control
```

## 8. Open Position Comparison

There are two relevant states:

1. Latest equity/position snapshot at `2026-07-02T08:00:00` is pre-fill and has
   4 open symbols.
2. Mutable `open_positions` after processing the `2026-07-02T08:00:00` signal
   has 5 symbols because BNB is entered at T+1 fill timestamp
   `2026-07-02T16:00:00`. That BNB entry is not part of the
   `2026-07-02T08:00:00` equity/unrealized PnL snapshot.

Latest snapshot positions were identical across prod and shadow:

| symbol | side | qty | entry_bar_ts | entry_fill_ts | entry_price | mark close | unrealized PnL |
| --- | --- | ---: | --- | --- | ---: | ---: | ---: |
| BTCUSDT | BUY | 0.0166234836 | 2026-07-02T00:00:00 | 2026-07-02T08:00:00 | 60155.86290000 | 61584.00000000 | 23.74061365 |
| ETHUSDT | BUY | 0.6186749094 | 2026-07-02T00:00:00 | 2026-07-02T08:00:00 | 1616.35777500 | 1696.32000000 | 49.47062231 |
| SOLUSDT | BUY | 13.5286985635 | 2026-06-29T08:00:00 | 2026-06-29T16:00:00 | 73.91694000 | 80.82000000 | 93.38941791 |
| XRPUSDT | BUY | 944.6179471459 | 2026-07-02T00:00:00 | 2026-07-02T08:00:00 | 1.05862905 | 1.09330000 | 32.75080161 |

Mutable post-process `open_positions` state was also identical across prod and
shadow:

```txt
BNBUSDT entry_bar_ts=2026-07-02T08:00:00 entry_fill_ts=2026-07-02T16:00:00 qty=1.7756582101 entry_price=563.17144500
BTCUSDT entry_bar_ts=2026-07-02T00:00:00 entry_fill_ts=2026-07-02T08:00:00 qty=0.0166234836 entry_price=60155.86290000
ETHUSDT entry_bar_ts=2026-07-02T00:00:00 entry_fill_ts=2026-07-02T08:00:00 qty=0.6186749094 entry_price=1616.35777500
SOLUSDT entry_bar_ts=2026-06-29T08:00:00 entry_fill_ts=2026-06-29T16:00:00 qty=13.5286985635 entry_price=73.91694000
XRPUSDT entry_bar_ts=2026-07-02T00:00:00 entry_fill_ts=2026-07-02T08:00:00 qty=944.6179471459 entry_price=1.05862905
```

Open position verdict:

```txt
OPEN_POSITIONS_IDENTICAL
```

## 9. Position Snapshot Comparison

Latest prod position snapshot:

```txt
bar_ts: 2026-07-02T08:00:00
batch_id: 36
seq: 153
open_symbols: ["BTCUSDT", "ETHUSDT", "SOLUSDT", "XRPUSDT"]
num_open: 4
```

Latest shadow position snapshot:

```txt
bar_ts: 2026-07-02T08:00:00
batch_id: 14
seq: 95
open_symbols: ["BTCUSDT", "ETHUSDT", "SOLUSDT", "XRPUSDT"]
num_open: 4
```

`position_snapshot_symbols` matched on symbols, quantities, entry prices,
entry fill IDs, entry bar timestamps, entry fill timestamps, and sides. The
SQLite schema does not store per-symbol market value/exposure in
`position_snapshot_symbols` (`quantbot/paper/db.py:314-324`), and the verifier
explicitly does not rederive child `unrealized_gross` from OHLCV marks
(`quantbot/paper/sqlite_verify.py:1169-1171`). Therefore per-symbol market
values and unrealized attribution below are derived from local OHLCV close marks
and the engine formula, not from `position_snapshot_symbols.unrealized_gross`.

## 10. Fill/Trade Comparison

Shared overlap window:

```txt
2026-06-24T16:00:00 through 2026-07-02T08:00:00
```

Fills with `signal_bar_ts` inside the overlap were identical:

```txt
prod fill count: 9
shadow fill count: 9
fills identical: yes
symbols traded: SOLUSDT, ETHUSDT, BTCUSDT, XRPUSDT, BNBUSDT
```

Fills with `fill_ts` inside the overlap were also identical:

```txt
prod fill count: 8
shadow fill count: 8
fills identical: yes
```

The ninth signal-window fill is BNB from the `2026-07-02T08:00:00` signal with
T+1 fill timestamp `2026-07-02T16:00:00`; it is post-snapshot for the latest
equity row.

Trades in the overlap had the same count, symbols, quantities, entry/exit
prices, realized gross PnL, and fees. One SOL trade differed only in funding and
therefore net PnL:

| field | prod | shadow |
| --- | ---: | ---: |
| symbol | SOLUSDT | SOLUSDT |
| entry_bar_ts | 2026-06-26T00:00:00 | 2026-06-26T00:00:00 |
| exit_bar_ts | 2026-06-27T08:00:00 | 2026-06-27T08:00:00 |
| gross_pnl | 28.09211736 | 28.09211736 |
| fees | 1.01404606 | 1.01404606 |
| funding | 0.19365757 | 0.19427386 |
| net_pnl | 26.88441373 | 26.88379744 |

Fill/trade verdict:

```txt
FILLS_IDENTICAL_OVERLAP
```

Qualification: trade rows are not byte-identical because one funding/net-PnL
value differs by `0.00061629`; fills and gross realized state are identical.

## 11. Signal Snapshot Comparison

Signal snapshots over the shared overlap:

```txt
prod bars: 24
shadow bars: 24
shared bars: 24
active symbol set differences: 0
source observation digest differences: 0
portfolio_heat / weighted_return differences: 0
```

First shared signal snapshot:

```txt
bar_ts: 2026-06-24T16:00:00
active_symbols: []
source_observation_digest: 321705103f3d900283228f9ecda2af5cba83ed9e0a29222b2249e2fce87b6477
```

Latest shared signal snapshot:

```txt
bar_ts: 2026-07-02T08:00:00
active_symbols: ["BNBUSDT", "BTCUSDT", "ETHUSDT", "SOLUSDT", "XRPUSDT"]
source_observation_digest: 4b2636628cc4c6b7d50137f6c5eb9a2a5ca6c94bc083d40a86768fde062f320b
```

Answer:

```txt
prod and shadow active symbols per bar: identical
bars where active symbol sets differ: none
shadow consumes same active symbols as prod: yes
```

## 12. Unrealized PnL Attribution

Latest unrealized PnL at `2026-07-02T08:00:00`:

```txt
prod unrealized_pnl:   +199.35145548
shadow unrealized_pnl: +199.35145548
derived from OHLCV marks: +199.35145548
```

Attribution by symbol:

| symbol | qty | entry price | mark close | pct move | unrealized PnL | share |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| SOLUSDT | 13.5286985635 | 73.91694000 | 80.82000000 | +9.33894179% | +93.38941791 | 46.84661955% |
| ETHUSDT | 0.6186749094 | 1616.35777500 | 1696.32000000 | +4.94706223% | +49.47062231 | 24.81578185% |
| XRPUSDT | 944.6179471459 | 1.05862905 | 1.09330000 | +3.27508016% | +32.75080161 | 16.42867444% |
| BTCUSDT | 0.0166234836 | 60155.86290000 | 61584.00000000 | +2.37406137% | +23.74061365 | 11.90892416% |

Mark sources:

```txt
/srv/qnty/repo/data/SOLUSDT_8h_ohlcv.csv close@2026-07-02T08:00:00
/srv/qnty/repo/data/ETHUSDT_8h_ohlcv.csv close@2026-07-02T08:00:00
/srv/qnty/repo/data/XRPUSDT_8h_ohlcv.csv close@2026-07-02T08:00:00
/srv/qnty/repo/data/BTCUSDT_8h_ohlcv.csv close@2026-07-02T08:00:00
```

Prod and shadow have the same per-symbol contribution.

Unrealized attribution verdict:

```txt
UNREALIZED_ATTRIBUTION_COMPLETE
```

## 13. Market Movement Sanity Check

The open long symbols rallied materially from entry to the
`2026-07-02T08:00:00` close mark:

```txt
SOLUSDT: +9.33894179%
ETHUSDT: +4.94706223%
XRPUSDT: +3.27508016%
BTCUSDT: +2.37406137%
```

The current `+199.35145548` unrealized PnL is fully explained by those local
OHLCV price moves and the identical long quantities. This is shared basket/market
exposure under identical consumed signals and fills. It is not evidence of edge
and not a profitability claim.

## 14. Residual `0.00061629` Decomposition

Equity snapshot start/end:

| field | prod | shadow |
| --- | ---: | ---: |
| start equity | 9984.66610097 | 10000.00000000 |
| end equity | 10161.53197739 | 10176.86526013 |
| delta equity | +176.86587642 | +176.86526013 |
| prod-minus-shadow delta | +0.00061629 | |

Component deltas over the overlap:

| component | prod delta | shadow delta | prod minus shadow |
| --- | ---: | ---: | ---: |
| realized gross PnL | -17.81922093 | -17.81922092 | -0.00000001 |
| fees cumulative | +3.99109039 | +3.99109039 | approximately 0 |
| funding cumulative | +0.67526775 | +0.67588404 | -0.00061629 |
| unrealized PnL | +199.35145548 | +199.35145548 | 0 |
| equity delta | +176.86587642 | +176.86526013 | +0.00061629 |

The residual is funding-only, not position/fill/mark drift.

Row-level source:

```txt
Affected trade: SOLUSDT entry 2026-06-26T00:00:00 exit 2026-06-27T08:00:00

prod funding:   0.19365757
shadow funding: 0.19427386
difference:    -0.00061629 prod-minus-shadow
```

The underlying funding rows are identical except for the exit-tail funding
notional on `SOLUSDT|2026-06-27T08:00:00|exit`:

```txt
prod exit-tail notional:   1027.61737593
shadow exit-tail notional:  995.68536343
funding_rate:              -0.00001930
funding_amount prod:       -0.01983302
funding_amount shadow:     -0.01921673
```

Most likely explanation: the prod and shadow batches processed this historical
exit-tail funding stub at different wall-clock times (`prod batch 21` committed
`2026-06-27T16:21:18Z`; `shadow batch 5` committed `2026-06-28T13:03:18Z`), and
the engine uses the T+1 exit-fill bar close as the exit-tail funding notional
when available (`quantbot/paper/engine.py:279-310`). The current local
`SOLUSDT_8h_ohlcv.csv` row for `2026-06-27T16:00:00` closes at `70.47`, matching
the shadow notional basis. The prod ledger appears to preserve the mark available
at prod run time. This is a small engine/source-data timing artifact inside the
existing funding semantics, not edge evidence.

## 15. Whether Current Shadow Is True Null Or Replication Control

The current shadow lane is not a true randomized null distribution.

Classification:

```txt
true randomized null: no
matched-null implementation: identity-labeled, but selector not wired into forward writer path
accounting/pipeline replication control: yes
something else: asserted-identity shadow lane consuming identical active_symbols
```

Reason:

```txt
signal snapshots are identical across 24 shared bars
fills are identical across the overlap
open positions are identical
unrealized attribution is identical
forward writer does not call select_null_active
```

Future docs should stop describing the current `paper_pnl_null_shadow_v0` lane as
a true null/control for edge. It should be described as an accounting/pipeline
replication control unless and until the randomized selector is wired into the
forward writer path and evaluated over many seeds.

## 16. Implications For Edge Interpretation

`EDGE_UNPROVEN` is preserved.

This audit explains the near-identical overlap PnL as same consumed signals, same
fills, same positions, same marks, and one tiny funding residual. It does not
show alpha, edge, deployability, or real-money profitability.

`CAVEATED_ENGINE_SEMANTICS` is preserved. The residual itself is a reminder that
current funding/mark semantics are not a clean net-of-carry economic proof.

## 17. Implications For Exit-Policy Lab

Take-profit / exit-policy planning is appropriate only as docs-only measurement
design at this stage. Implementation is premature from this audit alone because
the current gain is shared long exposure under a replication-control lane, not a
validated edge result.

Reasonable docs-only next work:

```txt
define exit-policy hypotheses
define attribution metrics
define comparison design against a real randomized null distribution
define funding-clean evaluation requirements
```

Not justified by this audit:

```txt
strategy mutation
writer changes
take-profit implementation
live or paper deployment claim
```

## 18. Implications For Shorting

Shorting remains blocked.

`quantbot/paper/null_comparator.py:8-14` states that the current engine is
long-only/fixed-notional and that direction randomization/shorts are out of
scope until the engine supports shorts. This audit did not change engine
capability, strategy direction, or any shorting support.

## 19. Mutation Guards

Before read-only VM inspection:

```txt
prod DB sha256:   06ea139db69aca17b72fb7e667962212bcbffc616a8f69c71d7da14943c3a14e
shadow DB sha256: 2ee2ba884278dffd08f6145e80d3b852c4e42fa8a49400291aa8868437c97f47
forward_obs hash: a8b8a761953a49c93e54bd5b0d7fe10944a1ef534a62f9e0e75b601c8807f521
```

After read-only VM inspection:

```txt
prod DB sha256:   06ea139db69aca17b72fb7e667962212bcbffc616a8f69c71d7da14943c3a14e
shadow DB sha256: 2ee2ba884278dffd08f6145e80d3b852c4e42fa8a49400291aa8868437c97f47
forward_obs hash: a8b8a761953a49c93e54bd5b0d7fe10944a1ef534a62f9e0e75b601c8807f521
```

Mutation guard result:

```txt
prod DB unchanged: yes
shadow DB unchanged: yes
forward_obs unchanged: yes
```

## 20. Verdict

```txt
POSITION_FILL_AUDIT_COMPLETE_REPLICATION_CONTROL_CONFIRMED
```
