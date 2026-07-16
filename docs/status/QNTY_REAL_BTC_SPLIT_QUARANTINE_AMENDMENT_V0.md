# QNTY Real BTC Split and Quarantine Amendment v0

**Status:** structural declaration only. `EDGE_UNPROVEN` and
`BLOCK_LIVE_INTEGRATION` remain in force.

No real-cut split existed before this amendment. The first execution attempt
correctly stopped with execution count zero, and emitted no `T`.

The source-ordered boundary is permanently frozen at index `33735`, computed
as `floor(42169 x 0.80)`, with purge `8` and embargo `90`. The 80/20 choice
was made outcome-blind after acquisition and before any Candidate 1 result; it
is not claimed to be optimal. This boundary may never change after observing
`T`.

The first and last five OHLCV rows had previously been exposed. Accordingly,
the current post-boundary tail is `quarantine_only`, not a scientific holdout.
Its structural `gate_passed` state is not scientific authorization. Any later
confirmation requires genuinely unseen data from a separately reviewed data
cut strictly after `2026-04-23T01:00:00Z`.

Candidate 1, the null, the statistic, warmup, hold, costs, purge, embargo, and
existing data/rule fingerprints are unchanged. Paper trading and live
integration remain false. This amendment computes no candidate/null return,
no `T`, and grants no paper or live authorization.
