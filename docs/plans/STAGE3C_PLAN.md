# Stage 3C PLAN: Net-of-Carry Reevaluation via Free Binance Paths

**Date:** 2026-04-21  
**Status:** PLAN ONLY — DO NOT EXECUTE  
**Branch:** `qnty/week1-conditioning-reset` (current)

---

## FACTS

### Path Verification
1. **Path A (Primary) — Verified Free:** Binance public S3 archive at `s3-ap-northeast-1.amazonaws.com/data.binance.vision/data/futures/um/monthly/fundingRate/` — fully accessible, no auth, free. Confirmed in [`docs/verdicts/stage3_free_funding_path_verdict.md`](docs/verdicts/stage3_free_funding_path_verdict.md).

2. **Path B (Secondary) — REST pagination:** `GET /fapi/v1/fundingRate` with `startTime` anchor pagination forward through time. The broken backward pagination in [`scripts/fetch_binance_funding.py:55`](scripts/fetch_binance_funding.py:55) was the root cause of the misdiagnosed 9-month retention limit. Forward pagination from a `startTime` anchor resolves this.

3. **Commercial paths:** SUPERSEDED. No vendor outreach. No Kaiko/CoinMetrics/ChainQ.

### Current Funding Data State
4. **BTC funding coverage:** BTCUSDT 8h fixture in [`tests/fixtures/BTCUSDT_8h.csv`](tests/fixtures/BTCUSDT_8h.csv) — 2190 rows, 2023-01-01 to 2024-12-30, zero gaps. OHLCV bars only; funding embedded in the bar data via THT0 shadow adapter mechanism.

5. **Altcoin funding coverage:** Only ~9 months of altcoin (SOL, MATIC, etc.) funding data available via old broken pagination — ends ~2021-06-16. Fails [`stage3_funding_admissibility_criteria.md`](docs/verdicts/stage3_funding_admissibility_criteria.md) Criterion 1 (historical depth to 2021-07-01).

6. **SOL funding interval change:** SOLUSDT switched from 8h funding intervals to 4h intervals at some point. **Exact date and direction not yet verified.** This is a known open item requiring exact verification.

### Listing Dates
7. All 10 symbols listed before 2021. MATICUSDT delisted/migrated 2024-09-11. From [`docs/data/listing_dates.md`](docs/data/listing_dates.md).

### Previous Stage Results
8. **Stage 2 gross:** 55.4% positive net at S2 carry stress. Vol-threshold sensitivity: PASS (100% sign consistency). All 6 combined-regime cells positive. From [`docs/verdicts/stage2_stress_verdict.md`](docs/verdicts/stage2_stress_verdict.md).

9. **Stage 2 proxy-carry:** Carry was treated as a fixed scalar cost (regime-dependent: 4928 bps/yr bull, 766 bps/yr bear, 548 bps/yr current) applied to direction, not actual funding rate data for altcoins.

10. **BTC funding rates:** 2021 bull: 4928 bps/yr (hostile). 2022 bear: 766 bps/yr (not hostile). 2025 current: 548 bps/yr. From [`docs/verdicts/stage0b_funding_diagnostic.md`](docs/verdicts/stage0b_funding_diagnostic.md).

### Repo State
11. **Branch:** `qnty/week1-conditioning-reset` — dirty (`.roo/shadow_context.md` deleted, untracked files present).
12. **No new strategy logic** — Stage 3C is a data swap, not a strategy change.

---

## ASSUMPTIONS

1. **BTC archive parity:** The S3 archive BTCUSDT funding data will match the existing BTCUSDT 8h OHLCV fixture in [`tests/fixtures/BTCUSDT_8h.csv`](tests/fixtures/BTCUSDT_8h.csv) for the overlapping period (2023-01-01 to 2024-12-30). This requires explicit verification before full rerun.

2. **S3 completeness:** The S3 archive contains complete monthly files for all 10 symbols from 2021-07 through 2025-04. This is assumed based on Binance's typical archival completeness but requires explicit existence check per month per symbol.

3. **SOL interval change date:** The SOL funding interval changed from 8h to 4h at a specific date in 2023 or 2024. The direction is known (8h → 4h). The exact date is not yet verified.

4. **Altcoin data for 2021-07 onward:** All 10 symbols have funding rate data starting 2021-07-01 from the S3 archive. The "9-month retention" diagnosis was wrong — the issue was broken pagination, not API limits.

5. **No regime shift in archive policy:** Binance has not changed S3 archive availability or format during the 2021-2025 period.

5. **Gap policy (CORRECTED):** If funding data is missing for a symbol-quarter where the strategy holds a position, the entire position-quarter is marked **INVALID/AMBIGUOUS** — not silently treated as zero-cost. This prevents the misleading reduction of costs from missing data. Affected quarters are flagged in the coverage matrix and excluded from both the numerator and denominator of carry-adjusted performance metrics. If a quarter has partial funding data, it is split: valid intervals count normally; gaps are flagged and the quarter is flagged AMBIGUOUS.

7. **Outlier policy:** Funding rates exceeding ±5% per interval (annualized > 36500%) will be flagged as outliers. These will be included in the dataset but logged explicitly. No automatic exclusion — the outlier log is the receipt.

---

## SPECULATION

1. **SOL interval change impact on carry:** If SOL switched from 8h to 4h, the number of funding events per year doubled. This changes the compounding of carry costs. Stage 3C should compute carry as: `Σ(interval_fraction × funding_rate)` per year, not assume fixed 8h intervals for all symbols across all time.

2. **Stage 3C verdict direction:** It is plausible that proxy-carry Stage 2 overstated costs for altcoins (if true average funding was lower than the conservative scalar used) or understated costs (if altcoins had higher-than-average funding in the periods the strategy was active). The direction is unknown without running the data.

3. **BTC parity confidence:** BTC is expected to match with high confidence since both sources are Binance. Low risk of discrepancy.

---

## PLAN

### Phase 1: Acquisition

#### 1.1 S3 Archive Bulk Fetch (Primary)
For each of the 10 symbols and each month from 2021-07 through 2025-04:

```
URL pattern: https://s3-ap-northeast-1.amazonaws.com/data.binance.vision/data/futures/um/monthly/fundingRate/{SYMBOLUSDT}-fundingRate-{YYYY-MM}.zip
```

Download and unzip to `data/funding/{SYMBOL}/{YYYY-MM}.csv`.

#### 1.2 REST Patch for Gaps (Secondary, Trailing-Edge Only)
If S3 returns 404 for any month in the range 2025-01 through 2025-04 (trailing edge), use REST `GET /fapi/v1/fundingRate` with `startTime` anchor pagination to fill the gap only. **Do not use REST as primary source.** Strictly gap-fill only.

#### 1.3 SOL Interval Verification
Before carry computation, determine exact date of SOL 8h→4h transition:
- Inspect SOLUSDT S3 archive monthly files for row frequency change
- Target: month-by-month count of SOLUSDT funding records — if any month has ~2× the expected records (expected = hours_in_month / funding_interval_hours), that marks the transition month
- Record: `{symbol: SOLUSDT, old_interval: 8h, new_interval: 4h, transition_date: YYYY-MM-DD}`

### Phase 2: Verification

#### 2.1 Month-by-Month Existence Check
For all 10 symbols × (2021-07 through 2025-04 = 46 months), confirm:
- File exists in S3 (HTTP 200)
- File is non-empty (>0 bytes)
- Row count is non-zero

Produce a verification matrix: `docs/verdicts/stage3c_funding_coverage_matrix.md` with one row per (symbol, month, status) where status ∈ {OK, MISSING, EMPTY}.

#### 2.2 BTC Archive Parity Check
Extract BTCUSDT funding rates for 2023-01-01 to 2024-12-30 from S3 archive. Compare against:
(a) data/btcusdt_funding_8h_raw.csv
(b) Stage 0 BTC funding diagnostic outputs (from docs/verdicts/stage0b_funding_diagnostic.md)

The OHLCV fixture (tests/fixtures/BTCUSDT_8h.csv) is NOT the primary parity reference for funding. The funding parity check must use the dedicated funding data source (btcusdt_funding_8h_raw.csv) and Stage 0 diagnostic figures (4928 bps/yr bull, 766 bps/yr bear, 548 bps/yr current). Must achieve parity or identify discrepancy before proceeding to Phase 3.

#### 2.3 Schema Validation
For each downloaded file, verify columns:
- `timestamp` (ms or ISO8601)
- `symbol`
- `fundingRate` (decimal)
- `fundingDate` or `fundingTime`

Row count sanity: funding_rate_count should equal (hours_in_month / funding_interval_hours) modulo reasonable tolerance for month boundaries.

#### 2.4 SOL Interval Transition Documentation
Document exact transition date and verify row count jump is consistent (approximately 2× after transition). Store in `docs/verdicts/stage3c_sol_interval_transition.md`.

#### 2.5 Predeclared Gap Policy Confirmation
Confirm gap policy: any month/symbol with MISSING status → exclude that symbol-month from carry calculation, log in coverage matrix. No interpolation, no proxy.

#### 2.6 Predeclared Outlier Policy Confirmation
Confirm outlier policy: flag any `|fundingRate| > 0.05` (5% per interval). Log to `data/funding/outlier_log.csv`. Include flagged rows in dataset but make them visually distinct in all analysis.

### Phase 3: Rerun

#### 3.1 Scope (Identical to Stage 2)
- **Same branch:** `qnty/week1-conditioning-reset`
- **Same frequency:** 8h
- **Same universe:** quarterly top-5 point-in-time from [`quantbot/data/quarterly_universe.py`](quantbot/data/quarterly_universe.py)
- **Same 4-point frozen grid:** no new parameter search
- **Same vol-state overlay:** [`quantbot/strategy/vol_state_overlay.py`](quantbot/strategy/vol_state_overlay.py)
- **No new branch logic**
- **No parameter expansion**

#### 3.2 Data Swap Only
Replace proxy-carry (fixed scalar per regime) with real net-of-carry:
- For each position entry, compute `carry_cost = Σ(intervals_in_position × fundingRate_at_interval)`
- Use actual funding rate time series for the symbol's interval (8h pre-SOL-transition, 4h post-SOL-transition)
- Apply to both entry and exit legs proportionally

#### 3.3 Output Comparison Table
Generate explicit three-way comparison:

| Metric | Gross Stage 2 | Proxy-Carry Stage 2 | Real-Carry Stage 3C |
|--------|---------------|---------------------|----------------------|
| Annualized return | X% | X% | X% |
| Sharpe ratio | X | X | X |
| Max drawdown | X% | X% | X% |
| Positive months | X% | X% | X% |
| Regime breakdown | table | table | table |

### Phase 4: Verdict

Produce `docs/verdicts/stage3c_net_of_carry_verdict.md` with:
- Three-way comparison table
- Whether real-carry changes the Stage 2 "CONTINUE" verdict
- Explicit statement of what the proxy carry was hiding or revealing
- If CONTINUE: next action
- If STOP: kill criteria met

---

## OPEN ITEMS (must resolve before Phase 3 execution)

1. **SOL transition exact date** — verify from S3 archive row counts
2. **BTC parity check** — must pass before full rerun
3. **Coverage matrix** — all 10 symbols × 46 months must be documented
4. **Outlier threshold** — ±5% per interval is the proposed threshold; confirm or adjust with rationale
5. **Gap policy update** — Missing funding for held position → INVALID/AMBIGUOUS, not silent exclusion. Splits for partial quarters.

---

## CONSTRAINTS

- **Do not execute Phase 3 until all Phase 2 verification items are complete and logged**
- **Do not change strategy logic** — data swap only
- **Do not add new parameters or branches**
- **Commercial outreach is explicitly prohibited** — free paths only
- **Forward-paper work is explicitly prohibited**
- **Vendor outreach is explicitly prohibited**

---

*This plan was produced after hygiene fix (`.roo/shadow_context.md` deleted) and review of all Stage 3 related verdicts. Plan-only status: do not execute without user authorization.*
