# Qnty

**Status:** Research preview / shadow-only  
**Not a trading bot. Not investment advice. Not live-capital approved.**

Qnty is a cleanroom crypto quant research harness for deterministic paper replay, falsification workflows, kill criteria, validation receipts, and shadow observation.

The current lead candidate, Package V2 / volnorm, is **not deployment-ready**. Current evidence supports continued shadow observation only. It does not prove deployable alpha.

---

## What this is

- A research and evaluation system for crypto quant strategies.
- A falsification-driven workflow with explicit kill criteria and validation receipts.
- A deterministic paper-replay engine for backtesting and diagnostics.
- A place for receipts, provenance, and careful claims.

## What this is not

- A trading bot.
- Investment advice.
- A proof of alpha by default.
- A place for unverified optimism.

## Current state

- **Current candidate:** Package V2 / volnorm
- **Mode:** shadow-only
- **Deployment-ready:** no
- **Live-capital approved:** no
- **K3:** unavailable / caveated
- **Benchmark comparison:** gross-vs-net caveat remains active
- **Strategy figures:** net of realistic funding assumptions where implemented, but benchmark comparison caveat remains
- **90-day observer:** not official unless explicitly documented
- **Operational burn-in:** machine-health evidence only, not alpha proof

Historical artifacts (e.g., `verdict: GO`, `verdict: PASSED`, `SURVIVED`) mean only "continued research / not killed by this test." They are not live trading approval.

## Install

```bash
# Requires Python >=3.10
python -m venv .venv
source .venv/bin/activate
pip install -U pip
pip install -e ".[test]"
```

## Minimal smoke test

```bash
./scripts/release_smoke.sh
```

Or manually:

```bash
python -c "import quantbot, numpy, pandas, requests; print('IMPORT_OK')"
python -m pytest tests/test_determinism_smoke.py -q
```

## Known limitations

See [KNOWN_LIMITATIONS.md](KNOWN_LIMITATIONS.md) for the full list. Highlights:

- Not deployment-ready.
- No live trading.
- No exchange keys required for public-data workflows.
- K3 is unavailable / caveated.
- Benchmark comparison is gross-vs-net; this is a known modeling gap.
- Historical validation does not prove alpha.
- Forward observer / burn-in checks operations, not edge.
- Generated outputs may differ as market data changes.

## Project boundaries

- **Qnty** is the research / falsification layer.
- **Franken** is a separate paper-flow / reconciliation shell.
- **THT0** is a separate strategy stack.

Any Franken references in this repo are legacy / integration-boundary artifacts. They are not public Qnty release claims.

## Safety / disclaimer

See [DISCLAIMER.md](DISCLAIMER.md) and [SECURITY.md](SECURITY.md).

This project is for research and educational use only. Do not trade based on this repo. You are responsible for your own decisions. There is no guarantee of profit.

## Contributing

See [CONTRIBUTING.md](CONTRIBUTING.md).

## License

MIT. See [LICENSE](LICENSE).
