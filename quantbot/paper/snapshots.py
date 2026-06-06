"""Frozen consumed-signal snapshots for paper_pnl_v1.

`observation_log.json` is a rolling 500-bar recompute with full overwrite (schema doc
section 1.1 / 5). That means a forward bar we already consumed can be silently recomputed
to different values on a later run. To defeat this provenance hole we freeze the exact
source row consumed for every processed bar into an append-only
`paper_signal_snapshots.jsonl`:

- A snapshot is written exactly once per consumed bar (idempotent by snapshot_id).
- An existing snapshot is NEVER rewritten.
- If a later observation row for an already-snapshotted bar_ts diverges from the frozen
  snapshot, the run aborts with SIGNAL_SNAPSHOT_DIVERGENCE before writing any ledger row.

See docs/paper_pnl_v1_schema.md section 10.
"""

from __future__ import annotations

import hashlib
from pathlib import Path
from typing import Any

from quantbot.core.determinism import canonical_json_dumps

SNAPSHOT_FILE = "paper_signal_snapshots.jsonl"

def snapshot_id(bar_ts: str) -> str:
    """Stable id for a bar's snapshot (deterministic across runs -> idempotent append)."""
    return hashlib.sha256(f"snap|{bar_ts}".encode("utf-8")).hexdigest()[:16]


def consumed_row_digest(obs: dict[str, Any]) -> str:
    """SHA-256 over the canonical FULL consumed source row of a per_bar_obs entry.

    The digest covers the entire row (every field, canonical JSON) — not a hand-picked
    subset — so ANY change to the recomputed observation (including a field the paper layer
    does not directly consume for sizing) is detected as a divergence (Blocker 5). The row
    is canonicalized with sorted keys; list values keep their order so a real reordering of
    active_symbols is also treated as a change (fail-closed).
    """
    return hashlib.sha256(canonical_json_dumps(obs).encode("utf-8")).hexdigest()


def check_divergence(
    existing_snapshots: list[dict[str, Any]],
    forward_obs: list[dict[str, Any]],
) -> str | None:
    """Compare current forward obs rows against frozen snapshots for the same bar_ts.

    Returns a SIGNAL_SNAPSHOT_DIVERGENCE reason string on the first mismatch, else None.
    """
    snap_by_ts = {s.get("bar_ts"): s for s in existing_snapshots}
    for obs in forward_obs:
        ts = obs.get("timestamp")
        snap = snap_by_ts.get(ts)
        if snap is None:
            continue
        frozen = snap.get("source_observation_digest")
        current = consumed_row_digest(obs)
        if frozen != current:
            return (
                f"SIGNAL_SNAPSHOT_DIVERGENCE at bar {ts}: frozen snapshot digest {frozen} "
                f"!= current observation digest {current}. The rolling observer window "
                f"recomputed an already-consumed bar to different values; refusing to "
                f"process to protect ledger provenance."
            )
    return None


def build_snapshots(
    forward_obs: list[dict[str, Any]],
    processed_bar_ts: set[str],
    existing_ids: set[str],
    source_mtime: float | None,
    run_ts: str,
) -> list[dict[str, Any]]:
    """Build snapshot rows for newly processed bars not already snapshotted.

    `existing_ids` is updated in-memory as rows are built (Blocker 5) so a duplicate
    timestamp within the SAME run can never produce two snapshots sharing one snapshot_id.
    (The freshness gate already aborts duplicate consumed timestamps; this is defence in
    depth so the snapshot writer is independently safe.)
    """
    seen = set(existing_ids)
    rows: list[dict[str, Any]] = []
    for obs in forward_obs:
        ts = obs.get("timestamp")
        if ts not in processed_bar_ts:
            continue
        sid = snapshot_id(ts)
        if sid in seen:
            continue
        seen.add(sid)
        rows.append(
            {
                "snapshot_id": sid,
                "bar_ts": ts,
                "bar_index": obs.get("bar_index"),
                "active_symbols": sorted(obs.get("active_symbols", []) or []),
                "portfolio_heat": obs.get("portfolio_heat"),
                "heat_cap_triggered": obs.get("heat_cap_triggered"),
                "weighted_return": obs.get("weighted_return"),
                "source_observation_digest": consumed_row_digest(obs),
                "source_observation_mtime": source_mtime,
                "run_ts": run_ts,
                "backfill": False,
            }
        )
    return rows


def read_snapshots(output_dir: Path) -> list[dict[str, Any]]:
    from quantbot.paper import ledger

    return ledger.read_jsonl(output_dir / SNAPSHOT_FILE)
