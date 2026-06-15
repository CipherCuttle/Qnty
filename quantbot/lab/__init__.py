"""QNTY Fast Truth Lab — additive, diagnostic, implementation-truth only.

This package is import-only. It NEVER touches systemd, the live paper DB, or
``/srv/qnty/output``. It re-derives the paper witness from source inputs to make the
implementation harder to fool. It makes NO profitability/edge claim.

Lanes (see docs/lab/FAST_TRUTH_LAB.md):
  FORWARD     — authoritative (production paper engine; NOT in this package)
  REPLAY      — diagnostic independent re-derive (replay_engine)
  ADVERSARIAL — diagnostic falsifiers (tests/lab/*)
  CROSS_CHECK — diagnostic engine-vs-replay disagreement classifier (cross_check)

Verdict semantics:
  PASS         = witness harder to fool (NOT "strategy has edge")
  FAIL         = stop & fix witness
  INCONCLUSIVE = blocker / spec ambiguity; no edge claim either way
"""

from __future__ import annotations

LANE_FORWARD = "FORWARD"  # authoritative production lane (reference only)
LANE_REPLAY = "REPLAY"  # diagnostic
LANE_ADVERSARIAL = "ADVERSARIAL"  # diagnostic
LANE_CROSS_CHECK = "CROSS_CHECK"  # diagnostic

DIAGNOSTIC_LANES = (LANE_REPLAY, LANE_ADVERSARIAL, LANE_CROSS_CHECK)

__all__ = [
    "LANE_FORWARD",
    "LANE_REPLAY",
    "LANE_ADVERSARIAL",
    "LANE_CROSS_CHECK",
    "DIAGNOSTIC_LANES",
]
