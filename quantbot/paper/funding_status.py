"""Funding-coverage verdict constants (frozen strings).

Frozen by architect spec (docs/plans/FUNDING_COVERAGE_FAIL_CLOSED_GATE_PLAN.md §3.1).
Tests and the verifier import these symbols by name — do not introduce additional symbols,
do not change these literal values.

Coverage decision constants describe per-symbol and overall funding-source coverage.
Verdict constants describe the batch-level classification reported by the paper verifier.

Coverage scope (after this PR):
  - emitted by the legacy JSONL verifier (``quantbot.paper.verify``);
  - emitted by the SQLite verifier (``quantbot.paper.sqlite_verify``).

NOT covered (follow-on):
  - runner pre-batch abort in ``quantbot.paper.runner`` — out of scope here. The
    runner is not currently pre-aborted on coverage failure; only the verifier
    stamps the diagnostic label.
"""

from __future__ import annotations

# Verdict constants (batch-level classification reported by the paper verifier).
CLEAN_NET_OF_CARRY = "CLEAN_NET_OF_CARRY"
CAVEATED_ENGINE_SEMANTICS = "CAVEATED_ENGINE_SEMANTICS"
CAVEATED_EX_FUNDING = "CAVEATED_EX_FUNDING"
FAIL = "FAIL"

# Diagnostic labels (attached to CAVEATED_* verdicts; empty for CLEAN_NET_OF_CARRY).
CAVEATED_ENGINE_SEMANTICS_LABEL = "missing_funding_treated_as_zero_like_current_engine_not_net_of_carry_clean"
CAVEATED_EX_FUNDING_LABEL = "funding_excluded_not_net_of_carry_comparable"

# Per-symbol / overall coverage decision constants (drives the verdict above).
COVERAGE_COMPLETE = "complete"
COVERAGE_PARTIAL = "partial"
COVERAGE_MISSING = "missing"
COVERAGE_NOT_REQUIRED = "not_required"
