# Package V2 — Bounded Validation Caveat Note

## Benchmark Semantics
- This validation uses gross benchmark (always-long equal-weight), consistent with Stage 4.
- The gross benchmark does not account for funding costs, which may cause apparent
  "excess return" that could differ under a net-of-carry benchmark.
- This is the same benchmark interpretation used in Stage 4 qualification.

## K3 Status
- K3 (funding drag ratio) was not measured in this validation run.
- K3 requires gross return retro-computation which was deferred from Stage 4.
- If K3 were measurable and > 0.40, this would trigger an INCONCLUSIVE classification
  due to benchmark/K3 ambiguity.

## Heat Cap Behavior
- Heat cap is set to 1.0 (never triggered in Stage 4; avg heat 0.0614).
- Heat cap triggers are tracked but are not expected in normal regime operation.
- Trigger rate > 5% would trigger FAIL per the validation protocol.

## Conclusion
No benchmark/K3 interpretation problems observed that would prevent verdict determination.
The gross benchmark interpretation is consistent with the frozen Package V2 definition.
