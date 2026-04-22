# Stage 1 Verdict — Multi-Asset Liquid Perp TSMOM Admissibility

**Date**: 2026-04-22
**Verdict**: **PASS**

## Summary

- Splits tested: 12
- Grid points tested: 4 (4-point frozen grid × splits)
- Test quarters: 2021-12-28, 2022-03-28, 2022-06-26, 2022-09-24, 2022-12-23, 2023-03-23...
- Low-vol regime pass: True
- High-vol regime pass: True
- Bootstrap centered near zero: False
- Trials adequate (≥5): True

## Reasoning
- Sign consistency: 84% of regime instances beat benchmark
- Bootstrap 95% CI excludes zero in 64% of regime instances (not centered)
- Trial adequacy: adequate

## BTC Funding Sensitivity (secondary context — NOT modeled truth)

| BTC Funding (bps/yr) | Return Delta (per bar) |
|---------------------|------------------------|
| 548 | -0.000050 |
| 1500 | -0.000137 |
| 4928 | -0.000450 |

## Pass/Fail Criteria Reference

**PASS**: TSMOM+vol-overlay shows sign consistency OR rank evidence OR return stability
materially above always-long benchmark, ≥5 trials per regime per split, bootstrap not centered at zero.

**FAIL**: TSMOM indistinguishable from or worse than always-long; no sign consistency;
bootstrap centered near zero; insufficient trials.

**CONTINUE**: Mixed evidence; needs explicit conditions to proceed.

## Raw Results

See `scripts/stage1_results.csv` for per-split, per-regime raw results.