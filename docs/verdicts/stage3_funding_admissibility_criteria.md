# Stage 3 — Funding Data Admissibility Criteria
**Date:** 2026-04-21  
**Purpose:** Pre-declared minimum standards for funding data before it may be used in a net-of-carry reevaluation.  
**Principle:** These criteria are declared BEFORE data is sourced. No post-hoc relaxation.

---

## Mandatory Admissibility Criteria

All criteria below must be satisfied before any funding data enters a Stage 3 net-of-carry rerun.

---

### Criterion 1: Historical Depth

**Requirement:** Data must reach **2021-07-01** for all 7 target symbols (SOL, ADA, DOT, AVAX, LINK, XRP, MATIC).

**Rationale:** Stage 3 backfill requires coverage of 2021-H2 through 2025 to match the walkforward split windows.

**Failure mode:** If any symbol lacks data before 2021-07-01, that symbol is excluded from all splits where data is missing. Exclusion must be documented per-split.

---

### Criterion 2: Symbol Mapping Consistency

**Requirement:** All funding rate records must use canonical exchange symbol names that map consistently to the declared universe symbols.

**Canonical mapping:**
| Canonical Symbol | Binance Perp Symbol |
|-----------------|---------------------|
| SOLUSDT | SOLUSDT |
| ADAUSDT | ADAUSDT |
| DOTUSDT | DOTUSDT |
| AVAXUSDT | AVAXUSDT |
| LINKUSDT | LINKUSDT |
| XRPUSDT | XRPUSDT |
| MATICUSDT | MATICUSDT |

**Rationale:** Mixed symbol naming causes silent wrong-symbol attribution.

**Failure mode:** If inconsistent symbol names are found, the loader must normalize before use. Normalization log must be preserved.

---

### Criterion 3: Timestamp Alignment

**Requirement:** Funding rate timestamps must align with 8h bar boundaries (00:00, 08:00, 16:00 UTC) OR the interpolation method must be explicitly documented and pre-approved.

**Rationale:** The strategy operates on 8h bars. Misaligned funding timestamps create look-ahead or look-bias.

**Failure mode:** If timestamps do not align, a pre-declared interpolation or assignment rule must be applied. No ad-hoc alignment after seeing results.

---

### Criterion 4: Coverage Gaps

**Requirement:** Any quarter with **>20% missing funding bars** for a given symbol is flagged, not silently filled.

**Gap policy options (pre-declare before seeing data):**
- **Option A — Drop symbol for that quarter:** Symbol excluded from that quarter's top-5 universe. Conservative.
- **Option B — Zero fill:** Missing bars treated as zero funding. Optimistic.
- **Option C — Forward-fill with cap:** Forward-fill from last known rate, capped at 3× BTC annual rate. Moderate.

**Rationale:** Funding data gaps are informative. Silent zero-filling or forward-filling obscures data quality.

**Chosen policy:** [To be declared before data is sourced. Do not decide based on how the data looks.]

---

### Criterion 5: Duplicate Rows

**Requirement:** Exact duplicate timestamp+symbol records must be deduplicated. Duplicates must be logged.

**Rationale:** Duplicate rows inflate sample size artificially and distort carry calculations.

**Failure mode:** If >1% of records are duplicates, flag data quality issue. Do not silently deduplicate without logging.

---

### Criterion 6: Outlier Policy

**Requirement:** Extreme funding rates must be handled by a pre-declared policy.

**Trigger:** Annualized funding rate >10,000 bps (10× BTC historical max observed in sample).

**Pre-declared outlier policy options:**
- **Option A — Flag and exclude:** Records >10,000 bps annualized excluded from carry calculation. Document count.
- **Option B — Flag and cap:** Cap at 10,000 bps for carry calculation. Document original max.
- **Option C — Flag and investigate:** Exclude quarter from evaluation pending investigation.

**Chosen policy:** [To be declared before data is sourced. Do not decide based on whether excluding helps results.]

**Rationale:** Some funding spikes are real (liquidations, market dislocations). Others are data errors. Pre-declaration prevents outcome-driven exclusion.

---

### Criterion 7: Rollover / Symbol Continuity

**Requirement:** If a perpetual contract rolls to a new contract during the study window, funding must be continuous across the rollover timestamp with no artificial gap or double-count.

**Rationale:** Binance USDT-M perpetuals have noExpiry. Symbol continuity issues arise if data comes from multiple exchange listings.

**Failure mode:** If discontinuous funding is detected at a known contract change, document and apply a pre-declared continuity correction.

---

### Criterion 8: Critical Regime Windows

**Requirement:** The following time windows must have **complete or documented-partial** coverage:

| Window | Rationale |
|--------|-----------|
| 2021-H2 | Bull→bear transition; funding regime shift |
| 2022 | Crisis period (LUNA collapse, FTX collapse) |
| 2023 | Recovery period |
| 2024–2025 | Current regime |

**Rationale:** Stage 2 identified carry as regime-dependent. Missing crisis windows invalidates stress case evaluation.

**Failure mode:** If any critical window has >30% missing data for any symbol, that window is flagged as unevaluable for that symbol.

---

### Criterion 9: Point-in-Time Integrity (No Lookahead)

**Requirement:** For walkforward splits, funding data used at time T must only include data available at or before time T.

**Rationale:** Falsification contract. Funding data is a market observable at time T, not a derived indicator. Confirm that the data source does not include future data in historical queries.

**Failure mode:** If point-in-time integrity is violated (e.g., provider backfills future data into historical queries), data is inadmissible.

---

### Criterion 10: Reproducibility and Provenance

**Requirement:** Data must have documented provenance: source, fetch date, fetch parameters, and version.

**Rationale:** Qnty is a truth machine. Data provenance must be auditable by a third party.

**Required provenance record:**
```
source: <provider name>
fetch_date: <YYYY-MM-DD>
fetch_parameters: <endpoint, symbols, time range>
version: <data version or snapshot id if available>
```

---

## Admissibility Gate Checklist

Before any Stage 3 net-of-carry rerun, the following must be true:

- [ ] All 7 symbols reach 2021-07-01 (or gap policy applied and documented)
- [ ] Symbol mapping verified consistent
- [ ] Timestamp alignment documented (8h boundaries or interpolation declared)
- [ ] Coverage gaps identified; gap policy applied and documented
- [ ] Duplicate rows deduplicated and logged
- [ ] Outlier policy pre-declared and applied
- [ ] Rollover continuity verified
- [ ] Critical regime windows (2021-H2, 2022, 2023, 2024–2025) assessed
- [ ] No lookahead confirmed (provider query method documented)
- [ ] Provenance record created for each data source

---

## Facts / Assumptions / Speculation

**FACTS:**
- The 7 altcoins' Binance funding data currently ends ~2021-06-16 in the repo
- Stage 2 used hardcoded proxy carry scenarios (S1=548, S2=1500, S3=4928 bps), not real data
- BTC has complete 2021–2026 funding data from pre-existing fixture

**ASSUMPTIONS:**
- A suitable institutional data provider can supply 2021-H2–2025 altcoin funding data — not yet verified
- The gap policy and outlier policy can be pre-declared without seeing the data — yes, this is possible

**SPECULATION:**
- Most institutional providers will have the data — the question is cost and access friction, not availability
- Community archives may partially cover the gap — possible but not reproducible or research-grade
