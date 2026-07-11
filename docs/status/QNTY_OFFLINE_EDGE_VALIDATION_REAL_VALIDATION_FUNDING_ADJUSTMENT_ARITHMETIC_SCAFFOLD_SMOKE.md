# QNTY_OFFLINE_EDGE_VALIDATION_REAL_VALIDATION_FUNDING_ADJUSTMENT_ARITHMETIC_SCAFFOLD_SMOKE

**Status**: `BLOCKED_BY_VALIDATION_IMPLEMENTATION`

**Run ID**: `QNTY_OFFLINE_EDGE_VALIDATION_REAL_VALIDATION_FUNDING_ADJUSTMENT_ARITHMETIC_SCAFFOLD_SMOKE_RECORDED_BLOCKED`

---

## Dependency

- PR #179
- Merge commit: `0675026181b117e37977c84701170c6fa2ef74ea`

---

## Execution

- Receipt: `/tmp/20260711_232335_output/real_validation_receipt.json`
- SHA-256: `cc4faaa65f3e84ab257991335f181601df3ec16e61cbefda6de17a3db0bea898`
- Exit status: `0`
- stderr: empty
- Final verdict: `BLOCKED_BY_VALIDATION_IMPLEMENTATION`
- Output directory contained exactly one JSON receipt
- 10 bars + 10 funding files staged via `/tmp` symlinks preserving filenames
- All 20 source CSV pre/post hashes matched
- Scratch worktree clean and removed after verification
- Source repo unchanged except pre-existing untracked `plans/`
- No stale `/srv/qnty/repo`

---

## Arithmetic Scaffold Summary

| Field                                 | Value                                                    |
| ------------------------------------- | -------------------------------------------------------- |
| calculation status                    | `FUNDING_ADJUSTMENT_ARITHMETIC_SCAFFOLD_DIAGNOSTIC_ONLY` |
| funding adjustment application status | `FIXTURE_ONLY_NOT_APPLIED_TO_STRATEGY`                   |
| strategy application status           | `NOT_EXECUTED`                                           |
| pnl application status                | `NOT_EXECUTED`                                           |
| requires policy contract diagnostics  | `true`                                                   |
| policy contract section required      | `funding_adjustment_policy_contract_diagnostics`         |
| funding rate unit                     | `decimal_rate_not_percent`                               |
| annualization status                  | `NOT_ANNUALIZED`                                         |
| compounding status                    | `NOT_COMPOUNDED`                                         |
| side source                           | `EXPLICIT_FIXTURE_ONLY`                                  |
| notional source                       | `EXPLICIT_FIXTURE_ONLY`                                  |
| strategy rule source                  | `NOT_EXECUTED`                                           |
| fixture cases                         | 6                                                        |
| passed fixture cases                  | 6                                                        |
| failed fixture cases                  | 0                                                        |

---

## Fixture Cases

| Case                            | Side    | Funding rate | Notional | Expected cashflow | Actual cashflow | Status |
| ------------------------------- | ------- | -----------: | -------: | ----------------: | --------------: | ------ |
| `case_1_long_positive_funding`  | `LONG`  |       `0.01` |    `100` |            `-1.0` |         `-1.00` | `PASS` |
| `case_2_long_negative_funding`  | `LONG`  |      `-0.01` |    `100` |             `1.0` |          `1.00` | `PASS` |
| `case_3_short_positive_funding` | `SHORT` |       `0.01` |    `100` |             `1.0` |          `1.00` | `PASS` |
| `case_4_short_negative_funding` | `SHORT` |      `-0.01` |    `100` |            `-1.0` |         `-1.00` | `PASS` |
| `case_5_long_zero_funding`      | `LONG`  |        `0.0` |    `100` |             `0.0` |           `0.0` | `PASS` |
| `case_6_short_zero_funding`     | `SHORT` |        `0.0` |    `100` |             `0.0` |           `0.0` | `PASS` |

### Fixture Case Properties (all cases)

- `fixture_status = PASS`
- `formula = LONG_NEGATES_FUNDING_RATE_SHORT_PRESERVES_FUNDING_RATE_TIMES_NOTIONAL`
- `application_scope = EXPLICIT_FIXTURE_ONLY_NOT_STRATEGY`
- Cashflow values emitted as strings
- No `symbol` key
- No `timestamp` key
- No OHLCV fields
- No strategy fields
- No real-data row identifiers

---

## Interpretation

This smoke proves only that the arithmetic fixture scaffold is emitted during the real-data CLI path and that its six hardcoded fixture cases pass. It does **not** prove real funding adjustment has been applied.

### Explicitly Unproven / Blocked

| Item | Status |
|------|--------|
| `EDGE_UNPROVEN` | Remains |
| `BLOCK_LIVE_INTEGRATION` | Remains |
| Final verdict | `BLOCKED_BY_VALIDATION_IMPLEMENTATION` |
| Funding adjustment application | `FIXTURE_ONLY_NOT_APPLIED_TO_STRATEGY` |
| Strategy application | `NOT_EXECUTED` |
| PnL application | `NOT_EXECUTED` |
| Real-data funding adjustment values | Not produced |
| Row-level adjustment values for real symbols | Not produced |
| Funding-adjusted bars | Not produced |
| Full joined dataset | Not produced |
| OHLCV values | Not emitted |
| Symbol-level arithmetic outputs | Not emitted |
| Timestamp-level arithmetic outputs | Not emitted |
| Strategy rules | Not executed |
| Strategy application | Not occurred |
| Side inference | Not occurred |
| Notional inference | Not occurred |
| Position inference | Not occurred |
| Bar return calculation | Not occurred |
| Funding-adjusted return calculation | Not occurred |
| Net return calculation | Not occurred |
| Price change calculation | Not occurred |
| Carry calculation | Not occurred |
| PnL | Not computed |
| Sharpe | Not computed |
| Drawdown | Not computed |
| Risk metrics | Not computed |
| Edge candidates | Not produced |
| Trades, positions, signals, or portfolio logic | Not executed |
| Live readiness | Not implied |

---

## Guardrails

| Guardrail | Status |
|-----------|--------|
| Final verdict remained `BLOCKED_BY_VALIDATION_IMPLEMENTATION` | Passed |
| All `required_outputs_present` values were `false` | Passed |
| All `forbidden_calculation_status` values were `false` | Passed |
| All `guardrail_status` values were `true` | Passed |
| No `OFFLINE_EDGE_CANDIDATE` | Confirmed |
| No `EDGE_CANDIDATE` | Confirmed |
| No `funding_adjusted_return` | Confirmed |
| No `net_return_value` | Confirmed |
| No `price_change` | Confirmed |
| No DB, paper-engine, or live integration activity | Confirmed |
| No exchange keys accessed | Confirmed |
| No report promotion | Confirmed |
| No data-refresh, service, timer, or systemd activity | Confirmed |
| All 20 pre/post source SHA-256 hashes matched | Confirmed |
| Output directory contained only the JSON receipt | Confirmed |
| Stale `/srv/qnty/repo` was not used | Confirmed |

---

## Receipt Audit Trail

- Receipt path: `/tmp/20260711_232335_output/real_validation_receipt.json`
- Receipt SHA-256: `cc4faaa65f3e84ab257991335f181601df3ec16e61cbefda6de17a3db0bea898`
- All fields verified before document creation
