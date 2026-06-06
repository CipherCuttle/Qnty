"""Hard pre-run freshness gate for paper_pnl_v1.

The paper layer is a downstream reader of the frozen observer. If the observer output is
missing, malformed, off-grid, or stale, we must NOT process it and must NOT silently treat
it as FLAT. This gate runs before any ledger row is written; a failure aborts the run loudly
and the run is marked ABORTED/STALE in the summary, receipt, and provenance log.

See docs/paper_pnl_v1_schema.md section 9.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

# Observer bar timestamps are naive UTC "%Y-%m-%dT%H:%M:%S" (matches OHLCV labels).
_BAR_FMT = "%Y-%m-%dT%H:%M:%S"
# bar_decisions heartbeat uses a trailing-Z UTC stamp written by qnty-shadow-run.sh.
_HEARTBEAT_FMT = "%Y-%m-%dT%H:%M:%SZ"


@dataclass
class FreshnessResult:
    ok: bool
    code: str  # "OK" or an UPPER_SNAKE abort code
    reason: str
    latest_bar_ts: str | None = None
    heartbeat_ts: str | None = None

    @property
    def aborted(self) -> bool:
        return not self.ok


def _ok(latest_bar_ts: str, heartbeat_ts: str | None) -> FreshnessResult:
    return FreshnessResult(
        ok=True,
        code="OK",
        reason="observer output present, on-grid, and fresh",
        latest_bar_ts=latest_bar_ts,
        heartbeat_ts=heartbeat_ts,
    )


def _parse_bar(ts: str) -> datetime:
    """Parse a naive observer bar timestamp as UTC (tolerates a trailing Z)."""
    return datetime.strptime(ts.rstrip("Z"), _BAR_FMT).replace(tzinfo=timezone.utc)


def _on_grid(dt: datetime, interval_hours: int) -> bool:
    return dt.minute == 0 and dt.second == 0 and dt.microsecond == 0 and (
        interval_hours <= 0 or dt.hour % interval_hours == 0
    )


def _latest_heartbeat_ts(hb_path: Path) -> str | None:
    """Return the newest bar_processed_at from bar_decisions.jsonl, or None if unavailable."""
    if not hb_path.exists():
        return None
    last: str | None = None
    try:
        with open(hb_path, encoding="utf-8") as fh:
            for line in fh:
                line = line.strip()
                if not line:
                    continue
                rec = json.loads(line)
                ts = rec.get("bar_processed_at")
                if ts:
                    last = ts
    except (json.JSONDecodeError, OSError):
        return None
    return last


def check_freshness(
    obs_path: Path,
    obs_log: Any,
    obs_dir: Path,
    now: datetime,
    freshness_cfg: dict[str, Any] | None,
) -> FreshnessResult:
    """Validate observer output before processing. Returns FreshnessResult (ok or abort code).

    Abort codes: MISSING_OBSERVATION_LOG, MALFORMED_OBSERVATION_LOG, EMPTY_PER_BAR_OBS,
    MALFORMED_BAR_TIMESTAMP, OFF_GRID_BAR, STALE_OBSERVATION, STALE_HEARTBEAT.
    """
    cfg = freshness_cfg or {}
    interval_hours = int(cfg.get("bar_interval_hours", 8))
    max_staleness = timedelta(hours=float(cfg.get("max_bar_staleness_hours", 24)))
    heartbeat_max_age = timedelta(hours=float(cfg.get("heartbeat_max_age_hours", 24)))

    if not obs_path.exists():
        return FreshnessResult(False, "MISSING_OBSERVATION_LOG", f"{obs_path} does not exist")

    if not isinstance(obs_log, dict) or "per_bar_obs" not in obs_log:
        return FreshnessResult(
            False, "MALFORMED_OBSERVATION_LOG", "observation_log.json has no per_bar_obs key"
        )

    per_bar = obs_log.get("per_bar_obs")
    if not isinstance(per_bar, list) or not per_bar:
        return FreshnessResult(
            False, "EMPTY_PER_BAR_OBS", "per_bar_obs is missing, empty, or not a list"
        )

    # Every row must be a dict with a usable timestamp + active_symbols list — a malformed
    # mid-stream row must abort, never be silently skipped or treated as FLAT.
    for i, row in enumerate(per_bar):
        if not isinstance(row, dict) or "timestamp" not in row:
            return FreshnessResult(
                False, "MALFORMED_OBSERVATION_LOG", f"per_bar_obs[{i}] missing timestamp"
            )
        active = row.get("active_symbols", [])
        if active is not None and not isinstance(active, list):
            return FreshnessResult(
                False, "MALFORMED_OBSERVATION_LOG", f"per_bar_obs[{i}] active_symbols not a list"
            )

    latest = per_bar[-1]
    latest_ts = latest.get("timestamp")
    try:
        latest_dt = _parse_bar(latest_ts)
    except (TypeError, ValueError):
        return FreshnessResult(
            False, "MALFORMED_BAR_TIMESTAMP", f"cannot parse latest bar timestamp {latest_ts!r}"
        )

    if not _on_grid(latest_dt, interval_hours):
        return FreshnessResult(
            False,
            "OFF_GRID_BAR",
            f"latest bar {latest_ts} is not on the {interval_hours}h grid (00/08/16 UTC)",
            latest_bar_ts=latest_ts,
        )

    age = now - latest_dt
    if age > max_staleness:
        return FreshnessResult(
            False,
            "STALE_OBSERVATION",
            f"latest bar {latest_ts} is stale: age {age} > {max_staleness}",
            latest_bar_ts=latest_ts,
        )

    # Heartbeat is checked only if available (the observer may not have written it yet).
    hb_ts = _latest_heartbeat_ts(obs_dir / "bar_decisions.jsonl")
    if hb_ts is not None:
        try:
            hb_dt = datetime.strptime(hb_ts, _HEARTBEAT_FMT).replace(tzinfo=timezone.utc)
        except ValueError:
            try:
                hb_dt = _parse_bar(hb_ts)
            except (TypeError, ValueError):
                hb_dt = None
        if hb_dt is not None and (now - hb_dt) > heartbeat_max_age:
            return FreshnessResult(
                False,
                "STALE_HEARTBEAT",
                f"bar_decisions heartbeat {hb_ts} is stale: age {now - hb_dt} > {heartbeat_max_age}",
                latest_bar_ts=latest_ts,
                heartbeat_ts=hb_ts,
            )

    return _ok(latest_ts, hb_ts)
