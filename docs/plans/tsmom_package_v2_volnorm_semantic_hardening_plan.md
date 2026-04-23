# Package V2 Vol-Norm Semantic Hardening Plan

## Objective

Test whether Package V2 still survives after semantic hardening.

## What stays frozen

- Signal family: TSMOM (same as tested)
- Thresholds: same as Package V2 test
- Universe: same multi-asset universe
- Vol-normalized sizing logic: same as tested
- Heat cap setting: 1.0 (same)
- No new filters or overlays
- K2 threshold: 0.35 (same)

## What may change

- Benchmark/carry semantics: make explicit and honest
- K3 computation: compute if feasible, fail closed if not
- Artifact labels/metadata only
- No changes to signal logic, thresholds, heat cap, vol lookback, or universe

## Key questions

1. Is benchmark/carry treatment honest and symmetric?
2. Can K3 be computed meaningfully?
3. Does Package V2 still pass K2 after semantic hardening?

## Semantic hardening targets

### A. Benchmark/carry semantics

Current state:
- Benchmark mode: gross (unfunded)
- Strategy mode: net (funded)

Required action:
- Either make this fully explicit and keep intentionally asymmetric, OR
- Implement funded benchmark parity if feasible
- Choose the smallest honest option
- If funded benchmark parity is not feasible, fail closed and state Package V2 remains provisional

### B. K3 truth

Current k3_funding_drag_ratio = 0.0 is not trustworthy unless genuinely computed.

Required action:
- Either compute gross return, funding cost, and drag ratio honestly and enable K3, OR
- Mark K3 as unavailable and remove any fake implication that it passed
- Fail closed over fake zeros

### C. Artifact truth

Ensure outputs record:
- Package name
- Benchmark mode
- Carry mode
- Sizing mode
- Heat cap
- Engine/version if available
- Whether K3 is real or unavailable

## Stop rule

If semantic hardening materially changes package verdict to fail, record that plainly.

Do NOT:
- Tighten heat cap
- Change signal logic
- Add new filters or overlays
- Mutate package logic

## After hardening

Rerun the same Package V2 package and report:
- Did K2 remain ≤ 0.35?
- Is benchmark mode now explicit and honest?
- Is K3 now real, or explicitly unavailable?
- Did verdict change?
