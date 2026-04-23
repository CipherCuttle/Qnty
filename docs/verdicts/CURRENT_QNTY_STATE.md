# QNTY Current State

**Date:** 2026-04-23
**Branch:** `main`
**After:** PR #6 merged

---

## What Failed

- Equal-weight multi-asset TSMOM package: FAILED Stage 4 kill criteria

## What Is Canonical

- Forensic baseline repaired and preserved on `main`
- Package V2 (vol-normalized, heat-capped, net-of-carry) is the current canonical lead candidate
- Bounded validation produced positive continuation evidence (K1, K2, K4 passed)
- `data/` contains raw OHLCV + funding data for 10 symbols (untracked, local runtime use)

## What Remains Caveated

- Benchmark mode is **gross** (no funding adjustment)
- Strategy figures are **net of realistic funding costs**
- K3 (funding drag ratio) remains **unavailable** — funding data insufficient for full cross-symbol burden
- Package V2 is **not deployment-ready**

## Next Phase

- Frozen forward / shadow observation only
- No redesign currently authorized
- No new validation runs without explicit authorization
