"""Pure 8h-boundary math for the watermark watchdog (no I/O).

The paper lane runs on an 8-hour grid at 00:00 / 08:00 / 16:00 UTC and intentionally
processes one closed bar behind the latest boundary. A run also does not commit instantly,
so the watchdog allows one further bar of tolerance during the grace window.

All functions require timezone-aware datetimes and operate in UTC.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

# 8h grid: 00:00 / 08:00 / 16:00 UTC. Mirrors BAR_INTERVAL in scripts/run_validation_v2.py.
BOUNDARY_HOURS = (0, 8, 16)
BAR_INTERVAL = timedelta(hours=8)
DEFAULT_GRACE_MINUTES = 60
DEFAULT_PROCESSING_LAG_BARS = 1


def _as_utc(value: datetime) -> datetime:
    """Return *value* as a timezone-aware UTC datetime (assume UTC if naive)."""
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


def parse_ts(value: str | datetime) -> datetime:
    """Parse a watermark/boundary timestamp into a tz-aware UTC datetime.

    Accepts ``datetime`` objects and ISO-8601 strings, including a trailing ``Z``.
    Naive timestamps are interpreted as UTC (the ledger stores naive UTC strings).
    """
    if isinstance(value, datetime):
        return _as_utc(value)
    text = value.strip()
    if text.endswith("Z"):
        text = text[:-1] + "+00:00"
    return _as_utc(datetime.fromisoformat(text))


def latest_boundary(now: datetime) -> datetime:
    """Latest 8h boundary <= *now* (floor to the 00/08/16 grid)."""
    now_utc = _as_utc(now)
    hour = (now_utc.hour // 8) * 8
    return now_utc.replace(hour=hour, minute=0, second=0, microsecond=0)


def previous_boundary(now: datetime) -> datetime:
    """The 8h boundary immediately before ``latest_boundary(now)``."""
    return latest_boundary(now) - BAR_INTERVAL


def expected_min_watermark(
    now: datetime,
    grace_minutes: int = DEFAULT_GRACE_MINUTES,
    processing_lag_bars: int = DEFAULT_PROCESSING_LAG_BARS,
) -> datetime:
    """Minimum watermark a healthy ledger must have committed by *now*.

    QNTY intentionally processes ``processing_lag_bars`` closed bars behind the latest
    boundary. Within grace, allow one further bar because the current cycle may not have
    committed yet.
    """
    latest = latest_boundary(now)
    grace = timedelta(minutes=grace_minutes)
    grace_lag_bars = 1 if _as_utc(now) - latest < grace else 0
    return latest - BAR_INTERVAL * (processing_lag_bars + grace_lag_bars)


def evaluate_watchdog(
    observed_watermark: str | datetime | None,
    now: datetime,
    grace_minutes: int = DEFAULT_GRACE_MINUTES,
    processing_lag_bars: int = DEFAULT_PROCESSING_LAG_BARS,
) -> tuple[str, dict[str, object]]:
    """Compare the observed watermark against the expected minimum.

    Returns ``("OK"|"STALE", detail)`` where *detail* carries the boundary timestamps used
    (ISO-8601 UTC strings) for the receipt. A missing watermark is treated as STALE.
    """
    now_utc = _as_utc(now)
    expected = expected_min_watermark(now_utc, grace_minutes, processing_lag_bars)
    latest = latest_boundary(now_utc)

    detail: dict[str, object] = {
        "now_utc": _iso(now_utc),
        "grace_minutes": grace_minutes,
        "processing_lag_bars": processing_lag_bars,
        "latest_boundary": _iso(latest),
        "expected_min_watermark": _iso(expected),
        "observed_watermark": None,
    }

    if observed_watermark is None or observed_watermark == "":
        detail["observed_watermark"] = None
        return "STALE", detail

    observed = parse_ts(observed_watermark)
    detail["observed_watermark"] = _iso(observed)
    status = "OK" if observed >= expected else "STALE"
    return status, detail


def _iso(value: datetime) -> str:
    """Render a tz-aware datetime as an ISO-8601 UTC string with a ``Z`` suffix."""
    return _as_utc(value).strftime("%Y-%m-%dT%H:%M:%SZ")
