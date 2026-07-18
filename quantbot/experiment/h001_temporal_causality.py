"""Pure, synthetic-only temporal selection for the H001 amendment candidate."""

from __future__ import annotations

import datetime as _datetime
import json
import math
import re
from dataclasses import dataclass
from typing import Sequence


_TIMESTAMP = re.compile(r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z")
_CANDIDATE_RULE = "latest funding_time_utc < bar[t].open_time_utc"


class TemporalCausalityError(ValueError):
    """Fail-closed error for malformed or causally invalid synthetic inputs."""


@dataclass(frozen=True)
class FundingEvent:
    funding_time_utc: str
    funding_rate_decimal: float


def _parse_timestamp(value: object) -> _datetime.datetime:
    if type(value) is not str or not _TIMESTAMP.fullmatch(value):
        raise TemporalCausalityError("NONCANONICAL_TIMESTAMP")
    try:
        return _datetime.datetime.strptime(value, "%Y-%m-%dT%H:%M:%SZ").replace(
            tzinfo=_datetime.timezone.utc
        )
    except ValueError as exc:
        raise TemporalCausalityError("NONCANONICAL_TIMESTAMP") from exc


def _validate_events(events: Sequence[FundingEvent]) -> tuple[tuple[_datetime.datetime, FundingEvent], ...]:
    previous = None
    parsed = []
    for event in events:
        if not isinstance(event, FundingEvent):
            raise TemporalCausalityError("INVALID_FUNDING_EVENT")
        timestamp = _parse_timestamp(event.funding_time_utc)
        rate = event.funding_rate_decimal
        if isinstance(rate, bool) or not isinstance(rate, (int, float)) or not math.isfinite(rate):
            raise TemporalCausalityError("NONFINITE_FUNDING_RATE")
        if previous is not None and timestamp == previous:
            raise TemporalCausalityError("DUPLICATE_FUNDING_TIMESTAMP")
        if previous is not None and timestamp < previous:
            raise TemporalCausalityError("NONMONOTONIC_FUNDING_TIMESTAMPS")
        previous = timestamp
        parsed.append((timestamp, event))
    return tuple(parsed)


def load_and_validate_temporal_candidate(raw: bytes) -> dict:
    """Validate the candidate design document without filesystem or network access."""
    if not isinstance(raw, bytes):
        raise TemporalCausalityError("CANDIDATE_BYTES_REQUIRED")
    try:
        parsed = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise TemporalCausalityError("INVALID_CANDIDATE_JSON") from exc
    if not isinstance(parsed, dict):
        raise TemporalCausalityError("INVALID_CANDIDATE_JSON")
    try:
        rule = parsed["temporal_join_contract"]["prior_funding"]
    except (KeyError, TypeError) as exc:
        raise TemporalCausalityError("CANDIDATE_TEMPORAL_RULE_MISSING") from exc
    if rule != _CANDIDATE_RULE:
        raise TemporalCausalityError("CANDIDATE_TEMPORAL_RULE_INVALID")
    contract = parsed["temporal_join_contract"]
    if contract.get("funding_cashflow_events") != "bar[t].open_time_utc < funding_time_utc <= bar[t].close_time_utc":
        raise TemporalCausalityError("HELD_FUNDING_RULE_CHANGED")
    return parsed


def select_signal_funding_event(
    funding_events: Sequence[FundingEvent],
    decision_timestamp_utc: str,
    *,
    max_staleness_hours: int = 12,
) -> FundingEvent:
    decision = _parse_timestamp(decision_timestamp_utc)
    if type(max_staleness_hours) is not int or max_staleness_hours < 0:
        raise TemporalCausalityError("INVALID_MAX_STALENESS")
    eligible = [item for item in _validate_events(funding_events) if item[0] < decision]
    if not eligible:
        raise TemporalCausalityError("NO_ELIGIBLE_PRIOR_FUNDING")
    timestamp, event = eligible[-1]
    if decision - timestamp > _datetime.timedelta(hours=max_staleness_hours):
        raise TemporalCausalityError("FUNDING_STALENESS_EXCEEDS_MAXIMUM")
    return event


def select_held_funding_events(
    funding_events: Sequence[FundingEvent],
    decision_timestamp_utc: str,
    interval_close_utc: str,
) -> tuple[FundingEvent, ...]:
    decision = _parse_timestamp(decision_timestamp_utc)
    interval_close = _parse_timestamp(interval_close_utc)
    if interval_close <= decision:
        raise TemporalCausalityError("INVALID_INTERVAL_ORDERING")
    return tuple(
        event
        for timestamp, event in _validate_events(funding_events)
        if decision < timestamp <= interval_close
    )
