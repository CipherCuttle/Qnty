"""Pure lane identity model (Phase 3, slice 2 — LANE_IDENTITY_PHASE3_PLAN §3/§10.2).

A *pure*, frozen, validated value object for future first-class lane identity. It
is deliberately NOT connected to config hashing, the DB schema, the writer, or the
verifier — those are later slices. This module exists only to provide a safe model
foundation so future shadow lanes cannot contaminate or impersonate the clean
production baseline.

Purity contract (enforced by tests/test_paper_lane_identity.py):
  * no filesystem, DB, env var, network, or path operations;
  * stdlib only (``dataclasses`` + ``re``); no sqlite, no subprocess, no sockets;
  * reject-only validation (values are never silently normalized/mutated).

This is a SIMULATION-support model. It makes NO profitability or edge claim; the
strategy edge remains EDGE_UNPROVEN.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

# Conservative identifier charset: lowercase letters, digits, '_', '-', '.'.
# This single allow-list already rejects whitespace, uppercase, '/' and '\'
# (so no relative/absolute paths), and any other punctuation. Path traversal
# ('..') is rejected separately below because '.' is an allowed character.
_IDENT_RE = re.compile(r"^[a-z0-9._-]+$")

# 64-char lowercase hex (SHA-256) for the optional digest fields.
_SHA256_RE = re.compile(r"^[0-9a-f]{64}$")

# The production baseline lane. It is IMPLICIT v1 and is NOT instantiated through
# this new model yet (slice 2 is model-only). A new lane may not claim this id, so
# a future shadow lane cannot impersonate the clean baseline.
BASELINE_LANE_ID = "paper_pnl_v1"


def _validate_identifier(value: str, field_name: str) -> str:
    """Reject anything that is not a conservative, non-empty identifier.

    Rejects: non-strings, empty strings, whitespace, uppercase, slashes/backslashes
    (relative or absolute paths), path traversal ('..'), and any character outside
    ``[a-z0-9._-]``. Returns the value unchanged on success (never normalizes).
    """
    if not isinstance(value, str):
        raise TypeError(f"{field_name} must be a str (got {type(value).__name__})")
    if value == "":
        raise ValueError(f"{field_name} must be non-empty")
    if not _IDENT_RE.match(value):
        raise ValueError(
            f"{field_name} {value!r} may contain only lowercase letters, digits, "
            f"'_', '-', '.' (no whitespace, slashes, uppercase, or other characters)"
        )
    if ".." in value:
        raise ValueError(f"{field_name} {value!r} must not contain '..' (path traversal)")
    if value in (".", "-", "_"):
        raise ValueError(f"{field_name} {value!r} is not a meaningful identifier")
    return value


def validate_lane_id(value: str) -> str:
    """Validate a NEW lane id.

    Same identifier rules as the other ids, plus a guard refusing the production
    baseline id ``paper_pnl_v1``: the baseline is implicit v1 and is not created
    through this model, so a new lane cannot impersonate it.
    """
    lane_id = _validate_identifier(value, "lane_id")
    if lane_id == BASELINE_LANE_ID:
        raise ValueError(
            f"lane_id {lane_id!r} is the production baseline lane; the baseline is "
            f"implicit v1 and is not instantiated through this model. Choose a "
            f"distinct lane_id for a new lane."
        )
    return lane_id


def validate_strategy_id(value: str) -> str:
    """Validate a strategy id (conservative non-empty identifier)."""
    return _validate_identifier(value, "strategy_id")


def validate_strategy_version(value: str) -> str:
    """Validate a strategy version (conservative non-empty identifier).

    Kept as a string (not an int) so versions like ``"1"`` or ``"1.2.0"`` are both
    expressible under the same conservative charset.
    """
    return _validate_identifier(value, "strategy_version")


def validate_optional_sha256(value: str | None, field_name: str) -> str | None:
    """Validate an optional digest: either ``None`` or a 64-char lowercase hex string."""
    if value is None:
        return None
    if not isinstance(value, str):
        raise TypeError(
            f"{field_name} must be a str or None (got {type(value).__name__})"
        )
    if not _SHA256_RE.match(value):
        raise ValueError(
            f"{field_name} must be a 64-char lowercase hex SHA-256 string "
            f"(got {value!r})"
        )
    return value


@dataclass(frozen=True)
class LaneIdentity:
    """Immutable identity for a single accounting lane.

    Validated on construction (reject-only). Frozen so an identity cannot be mutated
    after creation. No I/O of any kind happens here.
    """

    lane_id: str
    strategy_id: str
    strategy_version: str
    source_data_digest: str | None = None
    pre_registration_hash: str | None = None

    def __post_init__(self) -> None:
        validate_lane_id(self.lane_id)
        validate_strategy_id(self.strategy_id)
        validate_strategy_version(self.strategy_version)
        validate_optional_sha256(self.source_data_digest, "source_data_digest")
        validate_optional_sha256(self.pre_registration_hash, "pre_registration_hash")
