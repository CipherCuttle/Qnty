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

# Every consumed per_bar_obs row must carry the full observer contract. A row missing any
# of these (or with a non-list active_symbols) is malformed and must abort — it must never
# be silently skipped or interpreted as a FLAT bar (Blocker 3).
REQUIRED_OBS_FIELDS = (
    "bar_index",
    "timestamp",
    "active_symbols",
    "portfolio_heat",
    "heat_cap_triggered",
    "weighted_return",
)

# Clock-skew tolerance for "future" observation/heartbeat timestamps. A timestamp beyond
# now + this is treated as corrupt (negative age must never pass as "fresh").
DEFAULT_MAX_FUTURE_SKEW_HOURS = 1.0


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


def _latest_heartbeat_ts(hb_path: Path) -> tuple[str, str | None]:
    """Inspect bar_decisions.jsonl. Returns (status, latest_bar_processed_at).

    status:
      - "absent"    : file does not exist (the observer may not have written one yet — ok).
      - "ok"        : file present and every non-empty line is a JSON OBJECT carrying a
                      string `bar_processed_at` and a `commit_sha`; ts is the newest
                      `bar_processed_at` (None only if the file had no non-empty lines, which
                      the caller treats as malformed/fail-closed).
      - "malformed" : file present but a line is not valid JSON, is not an object, is missing
                      `bar_processed_at`/`commit_sha`, or it cannot be read.

    A present-but-malformed heartbeat must fail closed (Blocker 3), never be silently
    downgraded to "unavailable". A bare JSON array line (`[]`) or a row missing required
    fields is malformed, not "ok with no timestamp".
    """
    if not hb_path.exists():
        return "absent", None
    last: str | None = None
    try:
        with open(hb_path, encoding="utf-8") as fh:
            for line in fh:
                line = line.strip()
                if not line:
                    continue
                rec = json.loads(line)
                # Each heartbeat row must be an object with a valid bar_processed_at and a
                # commit_sha (schema § 1.4). A list/scalar row (`[]`, `123`) would crash
                # `.get` with AttributeError — fail closed instead (Blocker 3).
                if not isinstance(rec, dict):
                    return "malformed", None
                ts = rec.get("bar_processed_at")
                if not isinstance(ts, str) or not ts or "commit_sha" not in rec:
                    return "malformed", None
                last = ts
    except (json.JSONDecodeError, OSError, ValueError):
        return "malformed", None
    return "ok", last


def check_freshness(
    obs_path: Path,
    obs_log: Any,
    obs_dir: Path,
    now: datetime,
    freshness_cfg: dict[str, Any] | None,
    forward_start_ts: str | None = None,
) -> FreshnessResult:
    """Validate observer output before processing. Returns FreshnessResult (ok or abort code).

    The WHOLE observation file needed for trust is validated — not only consumed rows. Every
    row (including pre-`forward_start_ts` rows) must carry the full observer contract, a list
    of STRINGS `active_symbols`, and a parseable on-grid, non-duplicate, non-future timestamp;
    the latest bar must be fresh; a configured heartbeat must be present-valid-fresh. Any
    violation aborts; stale/malformed/missing/future output is never treated as FLAT or as a
    silent OK. When the file is clean but no bar has reached forward_start_ts, returns a
    controlled ok=True/`NO_ELIGIBLE_BARS_YET` no-op (the engine then writes zero rows).

    Abort codes: MISSING_OBSERVATION_LOG, MALFORMED_OBSERVATION_LOG, EMPTY_PER_BAR_OBS,
    MALFORMED_BAR_TIMESTAMP, OFF_GRID_BAR, DUPLICATE_OBSERVATION_TS, FUTURE_OBSERVATION,
    STALE_OBSERVATION, MALFORMED_HEARTBEAT, FUTURE_HEARTBEAT, STALE_HEARTBEAT.
    """
    cfg = freshness_cfg or {}
    interval_hours = int(cfg.get("bar_interval_hours", 8))
    max_staleness = timedelta(hours=float(cfg.get("max_bar_staleness_hours", 24)))
    heartbeat_max_age = timedelta(hours=float(cfg.get("heartbeat_max_age_hours", 24)))
    future_skew = timedelta(
        hours=float(cfg.get("max_future_skew_hours", DEFAULT_MAX_FUTURE_SKEW_HOURS))
    )

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

    # Validate the WHOLE observation file needed for trust — not only consumed rows
    # (Blocker 2). Pre-`forward_start_ts` rows must still pass timestamp/grid/duplicate/
    # future validation: a stale, off-grid, duplicate, or future-dated observation must
    # abort even before the forward boundary, never silently return a normal OK. Required
    # fields and a list-of-STRINGS active_symbols are checked for every row (Blocker 3).
    seen_ts: set[str] = set()
    consumed_count = 0
    latest_consumed_ts: str | None = None
    latest_overall_ts: str | None = None
    latest_overall_dt: datetime | None = None
    for i, row in enumerate(per_bar):
        if not isinstance(row, dict):
            return FreshnessResult(
                False, "MALFORMED_OBSERVATION_LOG", f"per_bar_obs[{i}] is not an object"
            )
        for field_name in REQUIRED_OBS_FIELDS:
            if field_name not in row:
                return FreshnessResult(
                    False,
                    "MALFORMED_OBSERVATION_LOG",
                    f"per_bar_obs[{i}] missing required field {field_name!r}",
                )
        active = row.get("active_symbols")
        # active_symbols must be a list of strings (Blocker 3): a list of objects (`[{}]`)
        # passes a bare isinstance(list) check but then crashes the engine with a TypeError
        # on `set(active_symbols)`. Fail closed here instead.
        if not isinstance(active, list) or not all(isinstance(s, str) for s in active):
            return FreshnessResult(
                False,
                "MALFORMED_OBSERVATION_LOG",
                f"per_bar_obs[{i}] active_symbols must be a list of strings "
                f"(got {type(active).__name__} with non-string element(s))",
            )

        ts = row.get("timestamp")
        try:
            dt = _parse_bar(ts)
        except (TypeError, ValueError):
            return FreshnessResult(
                False,
                "MALFORMED_BAR_TIMESTAMP",
                f"per_bar_obs[{i}] timestamp {ts!r} cannot be parsed",
            )
        if not _on_grid(dt, interval_hours):
            return FreshnessResult(
                False,
                "OFF_GRID_BAR",
                f"per_bar_obs[{i}] bar {ts} is not on the {interval_hours}h grid (00/08/16 UTC)",
                latest_bar_ts=ts,
            )
        if dt - now > future_skew:
            return FreshnessResult(
                False,
                "FUTURE_OBSERVATION",
                f"per_bar_obs[{i}] bar {ts} is in the future beyond skew {future_skew} "
                f"(now {now.strftime(_BAR_FMT)}) — a negative age must not pass as fresh",
                latest_bar_ts=ts,
            )
        if ts in seen_ts:
            return FreshnessResult(
                False,
                "DUPLICATE_OBSERVATION_TS",
                f"per_bar_obs has a duplicate timestamp {ts!r}; refusing to process "
                f"an ambiguous observation set",
                latest_bar_ts=ts,
            )
        seen_ts.add(ts)

        if latest_overall_dt is None or dt > latest_overall_dt:
            latest_overall_dt = dt
            latest_overall_ts = ts

        # Track the consumed (forward) set separately for the no-eligible-bars no-op.
        if forward_start_ts is not None and ts < forward_start_ts:
            continue
        consumed_count += 1
        if latest_consumed_ts is None or ts > latest_consumed_ts:
            latest_consumed_ts = ts

    # Staleness is checked against the latest bar that exists in the file (consumed if any,
    # else the latest overall): a dead observer must abort with STALE_OBSERVATION even before
    # the forward boundary, not slip through as a no-op (Blocker 2).
    latest_ts = latest_consumed_ts or latest_overall_ts
    latest_dt = _parse_bar(latest_ts)
    age = now - latest_dt
    if age > max_staleness:
        return FreshnessResult(
            False,
            "STALE_OBSERVATION",
            f"latest bar {latest_ts} is stale: age {age} > {max_staleness}",
            latest_bar_ts=latest_ts,
        )

    # Heartbeat: absent is allowed (observer may not have written it), but a present-but-
    # malformed or unparseable heartbeat fails closed (Blocker 3).
    hb_status, hb_ts = _latest_heartbeat_ts(obs_dir / "bar_decisions.jsonl")
    if hb_status == "malformed":
        return FreshnessResult(
            False,
            "MALFORMED_HEARTBEAT",
            f"{obs_dir / 'bar_decisions.jsonl'} is present but malformed; failing closed",
            latest_bar_ts=latest_ts,
        )
    if hb_status == "ok":
        if hb_ts is None:
            return FreshnessResult(
                False,
                "MALFORMED_HEARTBEAT",
                "bar_decisions.jsonl present but no record carried bar_processed_at; failing closed",
                latest_bar_ts=latest_ts,
            )
        try:
            hb_dt = datetime.strptime(hb_ts, _HEARTBEAT_FMT).replace(tzinfo=timezone.utc)
        except ValueError:
            try:
                hb_dt = _parse_bar(hb_ts)
            except (TypeError, ValueError):
                return FreshnessResult(
                    False,
                    "MALFORMED_HEARTBEAT",
                    f"bar_decisions heartbeat {hb_ts!r} cannot be parsed; failing closed",
                    latest_bar_ts=latest_ts,
                    heartbeat_ts=hb_ts,
                )
        # A future-dated heartbeat beyond clock-skew tolerance is corrupt: a negative age
        # must not pass as fresh (Blocker 3). Fail closed.
        if hb_dt - now > future_skew:
            return FreshnessResult(
                False,
                "FUTURE_HEARTBEAT",
                f"bar_decisions heartbeat {hb_ts} is in the future beyond skew {future_skew} "
                f"(now {now.strftime(_BAR_FMT)}); failing closed",
                latest_bar_ts=latest_ts,
                heartbeat_ts=hb_ts,
            )
        if (now - hb_dt) > heartbeat_max_age:
            return FreshnessResult(
                False,
                "STALE_HEARTBEAT",
                f"bar_decisions heartbeat {hb_ts} is stale: age {now - hb_dt} > {heartbeat_max_age}",
                latest_bar_ts=latest_ts,
                heartbeat_ts=hb_ts,
            )

    if consumed_count == 0:
        # The whole file validated clean (on-grid, fresh, no dup/future rows, valid
        # heartbeat) but nothing is at/after forward_start_ts yet. This is a controlled
        # no-op, NOT a normal misleading OK: the engine will write zero ledger rows.
        return FreshnessResult(
            ok=True,
            code="NO_ELIGIBLE_BARS_YET",
            reason="observer output is present, on-grid, and fresh, but no bar has reached "
            "forward_start_ts yet — controlled no-op (no ledger rows written)",
            latest_bar_ts=latest_ts,
            heartbeat_ts=hb_ts,
        )

    return _ok(latest_ts, hb_ts)
