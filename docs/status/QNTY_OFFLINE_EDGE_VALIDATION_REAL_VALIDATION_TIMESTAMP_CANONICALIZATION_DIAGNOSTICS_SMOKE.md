# QNTY Offline Edge Validation Real Validation Timestamp Canonicalization Diagnostics Smoke

## Status

`BLOCKED_BY_VALIDATION_IMPLEMENTATION`

Run ID: `QNTY_OFFLINE_EDGE_VALIDATION_REAL_VALIDATION_TIMESTAMP_CANONICALIZATION_DIAGNOSTICS_SMOKE_RECORDED_BLOCKED`

## Dependency

- PR #171
- Merge commit: `96e183c2d02aee3cc33c583c1bbb325e2afd0942`

## Precondition cleanup

- Initial source status was `?? plans/`.
- `plans/` was preserved intact at `/tmp/qnty_preserved_user_plans_1783728183/plans`.
- Source status was clean before smoke execution.
- `plans/` was restored only after clean-smoke postflight was recorded.
- Final source status returned to the original expected state, `?? plans/`.

## Scratch and execution

- Scratch worktree: `/tmp/qnty_scratch_pr171_timestamp_canonicalization_smoke_clean_1783728201`
- Scratch HEAD: `96e183c2d02aee3cc33c583c1bbb325e2afd0942`
- `quantbot.__file__` resolved inside the scratch worktree.
- The real 20-file CSV corpus came from `/home/swirky/DevHub/repos/Qnty/data/*_8h_ohlcv.csv` and `/home/swirky/DevHub/repos/Qnty/data/*_8h_funding.csv`.
- The corpus was staged through `/tmp`-only symlinks that preserved the real filenames: 10 bars files and 10 funding files.
- The command used both `--bars-dir` and `--funding-dir`, with `--split-count 3`.
- Exit code was `0`; stderr was empty.
- The output directory contained only `real_validation_receipt.json`.
- Pre/post SHA-256 values matched for all 20 source CSVs.
- The scratch worktree was clean and removed after verification.
- The stale `/srv/qnty/repo` checkout was not used.

## Receipt

- Path: `/tmp/qnty_timestamp_canonicalization_receipt_clean_1783728201/real_validation_receipt.json`
- SHA-256: `e02b0e18a9af8078e0bbcb05ffcca89073616a2db65b8aabff34ec5b4bd838f7`
- Printed and independently calculated hashes matched.
- `code_commit_sha`: `96e183c2d02aee3cc33c583c1bbb325e2afd0942`
- The receipt remained under `/tmp` and is not committed.

The receipt contained all four diagnostic sections:

- `funding_to_bars_alignment_diagnostics`
- `funding_to_bars_temporal_joinability_diagnostics`
- `funding_to_bars_timestamp_convention_diagnostics`
- `funding_to_bars_timestamp_canonicalization_diagnostics`

## Top-level canonicalization summary

- `calculation_status`: `FUNDING_TO_BARS_TIMESTAMP_CANONICALIZATION_DIAGNOSTIC_ONLY`
- `canonicalization_policy`: `DIAGNOSTIC_WHOLE_SECOND_UTC_ONLY`
- `funding_application_status`: `NOT_EXECUTED`
- Symbol count: 10.
- All symbols contained subsecond funding jitter.
- Maximum observed jitter: 47,000 microseconds.
- All policies produced zero canonicalized timestamp collisions.
- All collision-example lists were empty.

## Main finding

For the eight non-divergent symbols—ADA, AVAX, BNB, BTC, DOT, ETH, LINK, and XRP—both `floor_to_second` and `round_half_away_from_zero` produced exact canonical timestamp-set matches across the full symbol range and in every non-empty split window, with zero collisions and zero ambiguity.

This finding does not approve funding application.

| Symbol | Bars/Funding | Floor matched | Round matched | Ceil matched | Collisions | Ambiguity |
| ------ | -----------: | ------------: | ------------: | -----------: | ---------: | --------: |
| ADA    |    5271/5271 |    5271 exact |    5271 exact | 2909 partial |          0 |         0 |
| AVAX   |    5271/5271 |    5271 exact |    5271 exact | 2909 partial |          0 |         0 |
| BNB    |    5271/5271 |    5271 exact |    5271 exact | 2909 partial |          0 |         0 |
| BTC    |    5271/5271 |    5271 exact |    5271 exact | 2909 partial |          0 |         0 |
| DOT    |    5271/5271 |    5271 exact |    5271 exact | 2909 partial |          0 |         0 |
| ETH    |    5271/5271 |    5271 exact |    5271 exact | 2909 partial |          0 |         0 |
| LINK   |    5271/5271 |    5271 exact |    5271 exact | 2909 partial |          0 |         0 |
| MATIC  |    3506/5271 |  3506 partial |  3506 partial | 1875 partial |          0 |         0 |
| SOL    |    5271/5346 |  5271 partial |  5271 partial | 2909 partial |          0 |   26/26/8 |
| XRP    |    5271/5271 |    5271 exact |    5271 exact | 2909 partial |          0 |         0 |

## Best-policy summary

- For every symbol, `floor_to_second` was selected deterministically by exact matched count, tied with `round_half_away_from_zero`.
- Each non-divergent symbol had 5,271 matched timestamps.
- MATIC had 3,506 matched timestamps.
- SOL had 5,271 matched timestamps.
- The lowest collision count was zero for all three policies and all symbols.
- This diagnostic tie does not approve canonicalization or funding application.

## Per-split summary

For ADA, AVAX, BNB, BTC, DOT, ETH, LINK, and XRP:

- Floor and round were exact in every non-empty train/validation partition.
- Ceil was partial wherever data was present.
- `split_00/train` was empty by construction.
- No split window had collisions or ambiguity.

For MATIC:

- `split_01/validation`: floor/round `1749/1757`, with 8 extra funding timestamps.
- `split_02/train`: floor/round `3506/3514`, with 8 extra funding timestamps.
- `split_02/validation`: no bars against 1,757 funding timestamps.
- There were no collisions or ambiguity.
- MATIC remains blocked by truncated bar history/range mismatch; 1,765 funding timestamps lie outside the bars range.
- Floor, round, and ceil retain `BARS_END_BEFORE_FUNDING`.

For SOL:

- Floor/round aligned all 5,271 bar timestamps but left 75 extra funding timestamps unmatched.
- `split_00/validation` and corresponding later train windows retained 75 extra funding timestamps and 26 floor/round ambiguities.
- Later validation partitions matched exactly under floor/round.
- Ceil remained partial.
- There were no collisions.
- SOL remains blocked by 75 extra funding rows and ambiguity.

## Interpretation

The clean smoke proves the canonicalization diagnostics execute on the real 20-file corpus and show that whole-second UTC floor/round canonicalization is sufficient for exact timestamp-set matching for the eight non-divergent symbols, with no collisions and no ambiguity. It also shows MATIC and SOL remain structurally blocked.

This supports a future funding-application readiness gate, but does not approve timestamp canonicalization for application, funding application, funding-adjusted bars, strategy validity, edge, profitability, or live readiness.

- `EDGE_UNPROVEN` remains.
- `BLOCK_LIVE_INTEGRATION` remains.
- Funding application remains blocked.
- Timestamp canonicalization is not approved for application.
- No funding-adjusted bars were produced.
- No joined row-level dataset was produced.
- No strategy, trade, position, PnL, Sharpe, risk, portfolio, return, or edge metric was computed.
- No live readiness is implied.

## Guardrails

- The final verdict remained `BLOCKED_BY_VALIDATION_IMPLEMENTATION`.
- All six `required_outputs_present` values were false.
- All five `forbidden_calculation_status` values were false.
- All four `guardrail_status` values were true.
- There were no PnL, Sharpe, edge, strategy-performance, risk, trade, signal, position, or portfolio calculation keys.
- There were no exact generic `return` or `returns` keys.
- There was no `funding_adjusted_return`, `net_return_value`, or `price_change`.
- There was no `OFFLINE_EDGE_CANDIDATE` or `EDGE_CANDIDATE`.
- There was no DB, paper-engine, live integration, exchange-key, report-promotion, data-refresh, service, timer, or systemd activity.
- All 20 pre/post source SHA-256 hashes matched.
- Source-repo git status was clean during postflight before `plans/` was restored.
- The scratch worktree was clean before removal.
- The output directory contained only the JSON receipt.
- The stale `/srv/qnty/repo` checkout was not used as the source of truth.
