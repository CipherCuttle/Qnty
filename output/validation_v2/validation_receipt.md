# Package V2 — Bounded Validation Receipt

## Run Metadata
- **Run timestamp:** 2026-04-23T00:17:14Z
- **Branch:** qnty/tsmom-package-v2-volnorm
- **Commit:** b3310e9857c9dc483e13f1cef8737370a16ff8dd

## Package V2 Identity
- **Package name:** tsmom-package-v2-volnorm
- **Branch:** qnty/tsmom-package-v2-volnorm
- **Sizing method:** volatility-normalized (inverse-vol)
- **Heat cap:** 1.0
- **Vol lookback:** 90 bars
- **Benchmark mode:** gross (no funding adjustment)

## Validation Window Definition
- **Window start bar:** 4771
- **Window end bar:** 5271
- **Window size:** 500 bars
- **Warmup size:** 90 bars
- **Window start timestamp:** 2025-11-07T08:00:00
- **Window end timestamp:** 2026-04-22T16:00:00

## Grid Point Tested
- **Return period:** 20
- **Threshold:** 0.0
- **Universe:** ['ETHUSDT', 'BTCUSDT', 'SOLUSDT', 'XRPUSDT', 'BNBUSDT']

## Mutation Confirmation
No package components were mutated during this validation run:
- Signal family: unchanged (TSMOM multi-asset breakout)
- Thresholds: unchanged (K1/K2/K4 as defined in Stage 4)
- Vol lookback: unchanged (90 bars)
- Heat cap: unchanged (1.0)
- Sizing logic: unchanged (inverse-vol normalized)
- Benchmark semantics: unchanged (gross)
