"""Pure lane-aware config hash v2 (Phase 3, slice 3 — CONFIG_HASH_V2_PHASE3_PLAN).

A *pure* helper that composes a lane-aware identity hash for NEW lanes ONLY, over a
frozen v1 accounting ``config_hash`` plus a validated :class:`LaneIdentity`. It does
NOT redefine, recompute, or touch the v1 accounting contract: the v1 hash is consumed
as an opaque string, never rebuilt. This module is deliberately decoupled from
``config.py``/``db.py`` so it can never perturb the production baseline lane
(whose v1 ``config_hash`` and ``bar_commit_id`` must stay byte-identical).

Out of scope (later slices): ``source_data_digest`` and ``pre_registration_hash`` are
NOT folded into the v2 payload (see plan §5/§6 — per-run input identity and the
separate pre-registration commitment, respectively). ``paper_engine_version`` /
``schema_version`` are already bound transitively inside ``accounting_config_hash_v1``,
so they are not re-added; ``db_schema_version`` is a storage concern, not lane identity.

Purity: stdlib + ``canonical_json_dumps`` only. No I/O, DB, env, network, or paths.
Makes NO profitability or edge claim; the strategy edge remains EDGE_UNPROVEN.
"""

from __future__ import annotations

import hashlib
import re

from quantbot.core.determinism import canonical_json_dumps
from quantbot.paper.lane_identity import LaneIdentity

CONFIG_HASH_VERSION = 2

# Required v1 accounting hash: a 64-char lowercase hex SHA-256 string.
_SHA256_RE = re.compile(r"^[0-9a-f]{64}$")


def _validate_v1_hash(accounting_config_hash_v1: str) -> str:
    """Reject anything that is not a 64-char lowercase hex SHA-256 string (required)."""
    if not isinstance(accounting_config_hash_v1, str):
        raise TypeError(
            "accounting_config_hash_v1 must be a str "
            f"(got {type(accounting_config_hash_v1).__name__})"
        )
    if not _SHA256_RE.match(accounting_config_hash_v1):
        raise ValueError(
            "accounting_config_hash_v1 must be a 64-char lowercase hex SHA-256 string "
            f"(got {accounting_config_hash_v1!r})"
        )
    return accounting_config_hash_v1


def config_hash_v2_payload(
    accounting_config_hash_v1: str, identity: LaneIdentity
) -> dict:
    """Build the exact canonical v2 payload (no source/pre-registration/version fields).

    The v1 hash is validated and embedded verbatim; lane identity is taken from the
    already-validated :class:`LaneIdentity`. Nothing else is included.
    """
    v1 = _validate_v1_hash(accounting_config_hash_v1)
    return {
        "config_hash_version": CONFIG_HASH_VERSION,
        "accounting_config_hash_v1": v1,
        "lane_identity": {
            "lane_id": identity.lane_id,
            "strategy_id": identity.strategy_id,
            "strategy_version": identity.strategy_version,
        },
    }


def config_hash_v2(accounting_config_hash_v1: str, identity: LaneIdentity) -> str:
    """SHA-256 over the canonical JSON of the v2 payload.

    Deterministic for a fixed ``(accounting_config_hash_v1, identity)``; changes if the
    v1 hash or any of ``lane_id`` / ``strategy_id`` / ``strategy_version`` changes.
    """
    payload = config_hash_v2_payload(accounting_config_hash_v1, identity)
    return hashlib.sha256(canonical_json_dumps(payload).encode("utf-8")).hexdigest()
