# Stage 3 — Free Funding Path Method
**Date:** 2026-04-21  
**Scope:** Acquisition method for historical Binance USD-M perpetual funding rates, 2021-07-01 through 2025-04-20

---

## Source Hierarchy

| Priority | Source | Path/Method | Access | Auth |
|----------|--------|-------------|--------|------|
| **Primary** | Binance S3 Archive | `s3://data.binance.vision/data/futures/um/monthly/fundingRate/{SYMBOL}/{SYMBOL}-fundingRate-{YYYY-MM}.zip` | Free | None |
| **Secondary** | REST API pagination | `GET /fapi/v1/fundingRate?symbol={SYM}&startTime={TS}&limit=1000` | Free | None |

---

## Primary Path — S3 Archive Download

### URL Pattern
```
https://s3-ap-northeast-1.amazonaws.com/data.binance.vision/
  data/futures/um/monthly/fundingRate/{SYMBOL}/{SYMBOL}-fundingRate-{YYYY-MM}.zip
```

**Important:** Do NOT use `https://data.binance.vision/` for file downloads — CloudFront returns 404. Use the S3 direct URL.

### Download Command (curl/wget)
```bash
# Example: BTCUSDT 2021-07
curl -o BTCUSDT-fundingRate-2021-07.zip \
  "https://s3-ap-northeast-1.amazonaws.com/data.binance.vision/data/futures/um/monthly/fundingRate/BTCUSDT/BTCUSDT-fundingRate-2021-07.zip"

# With checksum verification
curl -o BTCUSDT-fundingRate-2021-07.zip.CHECKSUM \
  "https://s3-ap-northeast-1.amazonaws.com/data.binance.vision/data/futures/um/monthly/fundingRate/BTCUSDT/BTCUSDT-fundingRate-2021-07.zip.CHECKSUM"
```

### Schema
Each zip contains one CSV with three columns:
```
calc_time,funding_interval_hours,last_funding_rate
1625097600000,8,0.00010000
```

- `calc_time`: Unix timestamp in milliseconds (UTC)
- `funding_interval_hours`: Integer (currently 8; note: SOL was 4h before ~mid-2022)
- `last_funding_rate`: Decimal rate (e.g., `0.00010000` = 0.01% per period)

### Checksum Verification
Every zip has a corresponding `.CHECKSUM` file using CRC64NVME.
```python
import zipfile, hashlib

def verify_checksum(zip_path: str, checksum_path: str) -> bool:
    with open(checksum_path) as f:
        expected = f.read().split()[0]
    with zipfile.ZipFile(zip_path) as z:
        actual = z.checksum
    return actual == expected
```

---

## Secondary Path — REST Pagination (Gap-fill / Recency Patch)

### Endpoint
```
GET https://fapi.binance.com/fapi/v1/fundingRate
```

### Parameters
| Param | Description |
|-------|-------------|
| `symbol` | Perpetual symbol, e.g., `BTCUSDT` |
| `startTime` | Start timestamp in ms (inclusive) |
| `endTime` | End timestamp in ms (exclusive, optional) |
| `limit` | Max records per call (max: 1000) |

### Key Finding
`startTime` filter IS respected by the API. The prior script's backward pagination approach was unnecessary complexity — the correct approach is forward pagination from a `startTime` anchor.

### Correct Pagination Logic
```python
def fetch_funding_forward(symbol: str, start_time_ms: int, end_time_ms: int, limit: int = 1000) -> list[dict]:
    """
    Fetch funding history forward using startTime anchor.
    Binance returns limit records starting from startTime (inclusive).
    Page by advancing startTime to last record's fundingTime + 1ms.
    """
    all_rows = []
    current_start = start_time_ms
    
    while True:
        url = f"https://fapi.binance.com/fapi/v1/fundingRate?symbol={symbol}&startTime={current_start}&limit={limit}"
        rows = requests.get(url).json()
        if not rows:
            break
        all_rows.extend(rows)
        # Advance: next page starts after last record
        current_start = rows[-1]['fundingTime'] + 1
        if rows[-1]['fundingTime'] >= end_time_ms:
            break
        time.sleep(1.1)  # Rate limit compliance
    
    return all_rows
```

### When to Use REST vs. Archive
- **Archive (Primary):** All historical data from 2021-07 onward. Use for full backfill.
- **REST (Secondary):** Use for gap-filling if any archive months are missing, or for recency extension beyond archive's last month.

---

## Symbol Coverage Map

| Symbol | Archive Start | Archive End | REST Earliest | Notes |
|--------|--------------|-------------|---------------|-------|
| BTCUSDT | 2020-01 ✅ | 2026-03 ✅ | 2019-09 ✅ | Full history |
| ETHUSDT | ⚠️ unverified | ⚠️ unverified | ⚠️ unverified | To verify |
| BNBUSDT | ⚠️ unverified | ⚠️ unverified | ⚠️ unverified | To verify |
| SOLUSDT | 2020-09 ⚠️ | ⚠️ unverified | 2020-09 ⚠️ | Pre-launch data? Verify listing |
| ADAUSDT | ⚠️ unverified | ⚠️ unverified | ⚠️ unverified | To verify |
| DOTUSDT | ⚠️ unverified | ⚠️ unverified | ⚠️ unverified | To verify |
| AVAXUSDT | ⚠️ unverified | ⚠️ unverified | ⚠️ unverified | To verify |
| LINKUSDT | ⚠️ unverified | ⚠️ unverified | ⚠️ unverified | To verify |
| XRPUSDT | ⚠️ unverified | ⚠️ unverified | ⚠️ unverified | To verify |
| MATICUSDT | 2020-10 ⚠️ | ⚠️ unverified | ⚠️ unverified | Pre-launch data? Verify listing |

---

## Required Pre-Stage-3C Verification Checklist

Before proceeding to net-of-carry reevaluation:

- [ ] **BTCUSDT archive vs. repo fixture parity check** — 5-row spot compare of archive file against existing `data/btcusdt_funding_8h_raw.csv`
- [ ] **SOLUSDT listing date confirmed** — check `docs/data/listing_dates.md` to determine if pre-2021 archive data should be excluded
- [ ] **MATICUSDT listing date confirmed** — same
- [ ] **All 10 symbols: verify 2021-07 through 2025-04 completeness** — full month-by-month existence check
- [ ] **Row count sanity check per month** — confirm each month has ~93 rows (31 days × 3 daily fundings), accounting for month length
- [ ] **SOL interval change documented** — if SOL was 4h before mid-2022, document this as a carry model caveat
- [ ] **Point-in-time integrity test** — compare archive data against API data for a known past date; if different, archive is backfilled and not admissible
- [ ] **Checksum verification** — run CRC64 check on every downloaded zip
- [ ] **Provenance record created** — source, fetch date, method, version per symbol

---

## Known Caveats

### SOL Funding Interval Change
SOL perp funding changed from 4-hour to 8-hour intervals. If using SOL pre- and post-change in the same carry calculation, normalize intervals to 8h equivalents before comparison.

### Archive Last-Modified vs. Point-in-Time
Archive files have `Last-Modified` timestamps in 2023-2025. This means the archive was written well after the funding events occurred. The data may reflect a corrected/revised view rather than point-in-time snapshots. **Critical: must verify against API for a past date before accepting archive as research-grade.**

### SOL/MATIC Pre-Launch Data
Archive shows SOL and MATIC funding rate data from 2020-09 and 2020-10 respectively — before their known Binance perp listing dates. This data may be from testnet, a different contract, or data artifacts. **Do not use pre-listing archive data without verifying it represents actual mainnet funding.**

---

## Non-Goals (Not in Scope)

- Commercial outreach is superseded by this finding
- No Stage 3C rerun yet — only acquisition method specified here
- No parameter changes
- No strategy changes
