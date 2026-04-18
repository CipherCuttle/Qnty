# RFB Comparison Sprint Verdict — 2026-04-18

## Verdict: BASELINE WINS — min_hold_bars=8 direction not supported by fresh runs

---

## Source of Truth

Fresh receipts from post-economics-fix runs on branch `qnty/economics-truth-sprint`:

```
# RFB BASELINE (defaults, no special params)
Command: python -m quantbot.walkforward_cli --fixture btcusdt-8h --strategy RegimeFilteredBreakoutStrategy --train-size 300 --test-size 100 --step-size 100 --out /tmp/rfb_baseline --family-id rfb_comparison --variant-id rfb_baseline --fee-bps 10 --slippage-bps 5
Output: /tmp/rfb_baseline/walkforward_result.json

# RFB with min_hold_bars=8
Command: python -m quantbot.walkforward_cli --fixture btcusdt-8h --strategy RegimeFilteredBreakoutStrategy --train-size 300 --test-size 100 --step-size 100 --out /tmp/rfb_minhold8 --family-id rfb_comparison --variant-id rfb_minhold8 --fee-bps 10 --slippage-bps 5 --param min_hold_bars=8
Output: /tmp/rfb_minhold8/walkforward_result.json
```

Both runs use BTCUSDT 8h fixture with 10 bps fee + 5 bps slippage = 15 bps total per side.

---

## Side-by-Side Comparison

### Economics Summary

| Field | BASELINE | min_hold_bars=8 |
|-------|----------|-----------------|
| split_count | 18 | 18 |
| signal_count | 31 | 22 |
| entry_count | 31 | 22 |
| exit_count | 31 | 22 |
| flip_count | 0 | 0 |
| cost_side_count | 62 | 44 |
| assumed_total_cost_bps | 930.0 | 660.0 |

### Return Summary

| Field | BASELINE | min_hold_bars=8 |
|-------|----------|-----------------|
| gross_return_total | +33.74% (0.3374) | +26.06% (0.2606) |
| net_return_total | +24.44% (0.2444) | +19.46% (0.1946) |
| cost_deduction_total | +9.30% (0.0930) | +6.60% (0.0660) |

### Per-Split Signal Counts

| Variant | splits_signal_counts |
|---------|---------------------|
| BASELINE | [1, 0, 1, 0, 1, 4, 3, 2, 2, 2, 0, 1, 2, 2, 1, 4, 1, 4] |
| min_hold_bars=8 | [0, 0, 1, 0, 1, 2, 2, 2, 2, 2, 0, 1, 1, 1, 1, 3, 1, 2] |

### Break-Even Analysis

| Variant | Break-even cost/side |
|---------|---------------------|
| BASELINE | 54.42 bps (exceeds 15 bps applied) |
| min_hold_bars=8 | 59.22 bps (exceeds 15 bps applied) |

---

## Decision

**RETAIN BASELINE. Discard min_hold_bars=8 direction.**

Fresh runs on post-fix codebase show:
- BASELINE net_return = +24.44% (positive after costs)
- min_hold_bars=8 net_return = +19.46% (positive after costs, but lower)

The min_hold_bars=8 variant **reduces signals by 29%** (31→22) and **reduces costs by 29%** (62→44 sides), but also **reduces gross return by 23%** (0.3374→0.2606). The cost savings do not compensate for the return loss.

The direction of `min_hold_bars=8` is NOT supported by these results. BASELINE (min_hold_bars=3 default) wins on both gross and net return.

**Next step:** Explore alternative parameter directions or accept BASELINE as current champion.

---

