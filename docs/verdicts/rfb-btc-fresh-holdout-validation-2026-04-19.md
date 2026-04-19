# RFB BTC Fresh Holdout Validation — 2026-04-19

## Source Truth
- branch: qnty/rfb-regime-bugfix
- HEAD: 7dfb557
- status: clean, pushed

## Holdout Fixture
- source: Binance public klines API
- file: tests/fixtures/BTCUSDT_8h_holdout.csv
- rows: 1000
- first_bar: 2024-12-31 00:00:00+00:00
- last_bar: 2025-11-29 00:00:00+00:00
- checksum: 96fc9f917545b8b69b8b607314ac7ed1321fe0eabb09ee4318539f722154661e
- schema: timestamp,open,high,low,close,volume,quote_volume,trades

## Holdout Results (RFB BASELINE, unchanged code)

### rolling_window=10, threshold=5
- signal_count: 33
- entry_count: 33
- exit_count: 33
- flip_count: 0
- cost_side_count: 66
- gross_return_total: 0.873984
- net_return_total: 0.834384
- sharpe_like: 3.5737
- RESULT: POSITIVE

### rolling_window=20, threshold=10
- signal_count: 16
- entry_count: 16
- exit_count: 16
- flip_count: 0
- cost_side_count: 32
- gross_return_total: 0.124804
- net_return_total: 0.105604
- sharpe_like: 1.0696
- RESULT: POSITIVE

## Honest Assessment

1. Does unchanged RFB BASELINE survive genuinely fresh BTC holdout data?
   **ANSWER: YES.** Both parameter configurations produce positive net returns after costs. The smaller-window configuration (rw=10, t=5) shows stronger performance (net: 0.834, sharpe: 3.57) than the larger-window configuration (rw=20, t=10, net: 0.106, sharpe: 1.07). No parameter changes were made between canonical and this run.

2. Does the new holdout strengthen or weaken the BTC-only thesis?
   **ANSWER: STRENGTHENS.** The fresh fixture (Dec 2024–Nov 2025) is temporally disjoint from prior holdouts. Positive results on data the strategy was not calibrated on reduces the likelihood that observed performance is an artifact of specific date ranges. The regime-filtered breakout mechanism continues to produce directional accuracy on BTC.

3. Is RFB still justified as a BTC-only research candidate after this fresh-data test?
   **ANSWER: YES.** The strategy maintains positive expectancy on a fresh, independent data source. There is no evidence in this run to disqualify RFB from continued BTC-only research. This does not constitute proof of robustness beyond this specific symbol and timeframe.

4. What is the honest next step after this result?
   **ANSWER:** Extend temporal coverage. A single disjoint holdout is insufficient to establish durability. The next step is to run additional out-of-sample periods (e.g., earlier non-overlapping windows) and, if available, data from a different exchange or vendor to rule out Binance-specific artifacts. No live trading claims are warranted.

## What was NOT done
- No downloader infrastructure added
- No parameter tuning
- No new families
- No live trading claims
- No cross-symbol work reopened
- No architecture changes

## Conclusion

The RFB BASELINE, run unchanged on a fresh BTCUSDT 8h holdout fixture spanning Dec 2024–Nov 2025, produced positive net returns under both tested parameter configurations. The smaller-window strategy (rw=10, t=5) delivered 0.834 net return with a sharpe-like ratio of 3.57; the larger-window strategy (rw=20, t=10) delivered 0.106 net return with a sharpe-like ratio of 1.07. These results survive genuine out-of-sample testing on data that was not used in calibration. However, this represents one holdout period on one symbol. Claims of robustness are not yet justified. The strategy remains a BTC-only research candidate with positive early validation; sustained out-of-sample performance across multiple temporal windows and data sources is required before any promotion-worthy conclusion.
