# Known Limitations

This document lists known limitations of Qnty as of the current research preview release. It is not exhaustive.

## Capability limitations

- **Not deployment-ready.** Qnty is a research harness, not a production trading system.
- **No live trading.** The codebase is designed for deterministic paper replay and shadow observation only.
- **No exchange keys required** for public-data workflows. Any live integration would require separate, audited infrastructure.
- **K3 is unavailable / caveated.** The K3 kill criterion is not implemented or is explicitly marked as unreliable in the current candidate.

## Modeling limitations

- **Benchmark gross-vs-net caveat.** Strategy returns are net of realistic funding assumptions where implemented, but the benchmark comparison remains a gross-vs-net comparison. This is a known modeling gap.
- **Historical validation does not prove alpha.** All backtests and validation runs are historical evidence only. They do not guarantee forward performance.
- **Forward observer / burn-in checks operations, not edge.** Successful VM burn-in or operational health checks validate machine and scheduling health, not strategy edge.
- **Generated outputs may differ** as underlying market data changes or as data refresh windows shift.

## Documentation limitations

- **VM and ops docs are example / operator notes.** They are not a verified public deployment recipe. Operators are responsible for their own infrastructure decisions.
