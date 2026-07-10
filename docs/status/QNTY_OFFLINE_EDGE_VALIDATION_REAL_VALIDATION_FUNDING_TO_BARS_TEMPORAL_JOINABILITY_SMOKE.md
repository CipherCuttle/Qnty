# QNTY Offline Edge Validation — Real-Validation Funding-to-Bars Temporal Joinability Smoke

## Status

`BLOCKED_BY_VALIDATION_IMPLEMENTATION`

## Run ID

`QNTY_OFFLINE_EDGE_VALIDATION_REAL_VALIDATION_FUNDING_TO_BARS_TEMPORAL_JOINABILITY_SMOKE_RECORDED_BLOCKED`

## Dependency

- PR #166
- merge commit `9df8445e90c681b5949622a31805938ac5307ba1`

## Scratch / execution

- Scratch worktree: `/tmp/qnty_scratch_pr166_temporal_joinability_smoke_1783718089`
- Scratch HEAD: `9df8445e90c681b5949622a31805938ac5307ba1`
- `quantbot.__file__` resolved inside scratch.
- Real 20-file CSV corpus from `/home/swirky/DevHub/repos/Qnty/data/*_8h_ohlcv.csv` and `*_8h_funding.csv`.
- Staged through `/tmp`-only symlinks preserving real filenames.
- 10 bars files + 10 funding files.
- Command used both `--bars-dir` and `--funding-dir`.
- `--split-count 3`.
- Exit code `0`.
- stderr: empty / no reported stderr.
- Output directory contained only `real_validation_receipt.json`.

## Receipt

- Path: `/tmp/qnty_temporal_joinability_receipt_1783718251/real_validation_receipt.json`
- SHA-256: `6507b3120adad48d6de28c0418541df1fcbbe57f3da24862061a64d977bd3764`
- Printed and independently calculated hashes matched.
- `code_commit_sha`: `9df8445e90c681b5949622a31805938ac5307ba1`
- Receipt remained under `/tmp` and must not be committed.

## Top-level temporal joinability summary

- `calculation_status`: `FUNDING_TO_BARS_TEMPORAL_JOINABILITY_DIAGNOSTIC_ONLY`
- `timestamp_match_policy`: `EXACT_UTC_TIMESTAMP_ONLY`
- `funding_application_status`: `NOT_EXECUTED`
- `symbol_count`: 10
- `exact_set_match_symbol_count`: 0
- `partial_match_symbol_count`: 10
- `no_exact_match_symbol_count`: 0

## Main finding

No symbol achieved exact timestamp-set match. All 10 symbols were partial matches. Equal row counts did not imply equal timestamps.

## Per-symbol table

| Symbol    | Bars timestamps | Funding timestamps | Exact matched | Bars without funding | Funding without bars | Bars outside overlap | Funding outside overlap | Status                      |
| --------- | --------------: | -----------------: | ------------: | --------------------: | --------------------: | --------------------: | -----------------------: | ---------------------------- |
| ADAUSDT   |            5271 |               5271 |          2909 |                   2362 |                   2362 |                      0 |                        0 | PARTIAL_TIMESTAMP_SET_MATCH  |
| AVAXUSDT  |            5271 |               5271 |          2909 |                   2362 |                   2362 |                      0 |                        0 | PARTIAL_TIMESTAMP_SET_MATCH  |
| BNBUSDT   |            5271 |               5271 |          2909 |                   2362 |                   2362 |                      0 |                        0 | PARTIAL_TIMESTAMP_SET_MATCH  |
| BTCUSDT   |            5271 |               5271 |          2909 |                   2362 |                   2362 |                      0 |                        0 | PARTIAL_TIMESTAMP_SET_MATCH  |
| DOTUSDT   |            5271 |               5271 |          2909 |                   2362 |                   2362 |                      0 |                        0 | PARTIAL_TIMESTAMP_SET_MATCH  |
| ETHUSDT   |            5271 |               5271 |          2909 |                   2362 |                   2362 |                      0 |                        0 | PARTIAL_TIMESTAMP_SET_MATCH  |
| LINKUSDT  |            5271 |               5271 |          2909 |                   2362 |                   2362 |                      0 |                        0 | PARTIAL_TIMESTAMP_SET_MATCH  |
| MATICUSDT |            3506 |               5271 |          1875 |                   1631 |                   3396 |                      0 |                     1765 | PARTIAL_TIMESTAMP_SET_MATCH  |
| SOLUSDT   |            5271 |               5346 |          2909 |                   2362 |                   2437 |                      0 |                        0 | PARTIAL_TIMESTAMP_SET_MATCH  |
| XRPUSDT   |            5271 |               5271 |          2909 |                   2362 |                   2362 |                      0 |                        0 | PARTIAL_TIMESTAMP_SET_MATCH  |

## Range notes

- Most non-divergent symbols cover `2021-07-01` through `2026-04-22 16:00` on both sides.
- MATIC bars end at `2024-09-11 08:00`; funding continues through `2026-04-22 16:00`.
- SOL has 75 more funding timestamps than bar timestamps.

## Per-split findings

For the 8 non-divergent symbols:

- `split_00` train: `EMPTY_BOTH`, bars/funding `0/0`.
- `split_00` validation: bars/funding `1757/1757`, exact `568`, `PARTIAL_TIMESTAMP_SET_MATCH`.
- `split_01` train: bars/funding `1757/1757`, exact `568`, `PARTIAL_TIMESTAMP_SET_MATCH`.
- `split_01` validation: bars/funding `1757/1757`, exact `1313`, `PARTIAL_TIMESTAMP_SET_MATCH`.
- `split_02` train: bars/funding `3514/3514`, exact `1881`, `PARTIAL_TIMESTAMP_SET_MATCH`.
- `split_02` validation: bars/funding `1757/1757`, exact `1028`, `PARTIAL_TIMESTAMP_SET_MATCH`.

MATIC-specific:

- Structurally divergent.
- `split_02` validation has bars `0` / funding `1757`.
- Status there: `NO_EXACT_TIMESTAMP_MATCH`.
- `split_01` validation has bars `1749` / funding `1757`.
- Confirms the previous MATIC split divergence with more detail.

SOL-specific:

- Structurally divergent.
- Funding has 75 more rows than bars.
- Surplus is concentrated in early-window split areas, especially `split_00` / `split_01` train and `split_00` validation.
- Confirms previous SOL 75-row surplus with more detail.

## Guardrails

- Final verdict remained `BLOCKED_BY_VALIDATION_IMPLEMENTATION`.
- All six `required_outputs_present` values were false.
- All five `forbidden_calculation_status` values were false.
- All four `guardrail_status` values were true.
- No PnL, Sharpe, edge, strategy-performance, risk, trade, signal, position, or portfolio calculation keys.
- No exact generic `return` or `returns` keys.
- No `funding_adjusted_return`.
- No `net_return_value`.
- No `price_change`.
- No `OFFLINE_EDGE_CANDIDATE`.
- No `EDGE_CANDIDATE`.
- No DB, paper-engine, live integration, exchange keys, report promotion, data-refresh, service, timer, or systemd activity.
- All 20 pre/post source SHA-256 hashes matched.
- Source repo git status was clean.
- Scratch worktree git status was clean.
- Output directory contained only the JSON receipt.
- Scratch worktree was removed after run.
- Stale `/srv/qnty/repo` was not used as source of truth.

## Interpretation

The smoke proves the temporal joinability diagnostic executes against the real 20-file corpus and correctly emits exact UTC timestamp-set evidence. It also proves that direct exact-timestamp funding-to-bars joining is not currently valid for any of the 10 symbols.

This does not prove no edge, no profitability, or no future strategy validity. It blocks funding-adjusted bars until timestamp convention / offset / cadence diagnostics explain the mismatch.

- `EDGE_UNPROVEN` remains.
- `BLOCK_LIVE_INTEGRATION` remains.
- Do not claim exact temporal alignment.
- Do not claim funding-adjusted returns.
- Do not claim strategy validity.
- Do not claim edge.
- Do not claim profitability.
- Do not claim live readiness.
