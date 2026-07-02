"""Shared funding timestamp normalization for paper funding coverage.

FUNDING_TIMESTAMP_NORMALIZATION_SPEC_V2 keeps funding windows open-closed while
matching the engine's current whole-second funding timestamp behavior: a source
timestamp in the same UTC second as a nominal endpoint canonicalizes to that
endpoint second. The helper is pure: it parses no files, mutates no state, and
only classifies already-parsed UTC datetimes for one funding window.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Iterable

FUNDING_TIMESTAMP_NORMALIZATION_SPEC_V2 = "FUNDING_TIMESTAMP_NORMALIZATION_SPEC_V2"
ENDPOINT_SAME_SECOND_TOLERANCE_MS = 999

REASON_ACCEPTED = "accepted"
REASON_DUPLICATE_CANONICAL_ENDPOINT = "duplicate_canonical_endpoint"
REASON_MISSING_SOURCE_ROW = "missing_source_row"
REASON_CANONICALIZED_TO_OPEN_BOUNDARY = "canonicalized_to_open_boundary"
REASON_OUTSIDE_TOLERANCE = "outside_tolerance"


@dataclass(frozen=True)
class FundingTimestampClassification:
    spec_name: str
    clean_net_of_carry_allowed: bool
    reason: str
    canonical_endpoint: datetime | None = None


@dataclass(frozen=True)
class FundingTimestampWindowClassification:
    spec_name: str
    clean_net_of_carry_allowed: bool
    reason: str
    source_row_count: int = 0
    canonical_endpoint: datetime | None = None


def _utc(dt: datetime) -> datetime:
    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def _is_same_utc_second_at_or_after_endpoint(
    source_utc: datetime,
    endpoint_utc: datetime,
) -> bool:
    delta = source_utc - endpoint_utc
    return timedelta(0) <= delta < timedelta(
        milliseconds=ENDPOINT_SAME_SECOND_TOLERANCE_MS + 1
    )


def canonicalize_funding_timestamp(
    source_ts: datetime,
    *,
    window_start: datetime,
    window_end: datetime,
) -> datetime | None:
    """Return the boundary a source timestamp canonicalizes to, if any.

    Canonicalization is one-sided: only timestamps in the same UTC second as a
    boundary, at or after that boundary, canonicalize to that boundary. The open
    boundary is intentionally checked first so a row a few milliseconds after
    ``window_start`` is not counted inside ``(window_start, window_end]``.
    """
    source_utc = _utc(source_ts)
    for endpoint in (_utc(window_start), _utc(window_end)):
        if _is_same_utc_second_at_or_after_endpoint(source_utc, endpoint):
            return endpoint
    return None


def classify_funding_timestamp_for_window(
    source_ts: datetime,
    *,
    window_start: datetime,
    window_end: datetime,
) -> FundingTimestampClassification:
    """Classify one source timestamp against one funding window."""
    ws = _utc(window_start)
    we = _utc(window_end)
    source_utc = _utc(source_ts)
    canonical_endpoint = canonicalize_funding_timestamp(
        source_utc,
        window_start=ws,
        window_end=we,
    )

    if canonical_endpoint == ws:
        return FundingTimestampClassification(
            FUNDING_TIMESTAMP_NORMALIZATION_SPEC_V2,
            False,
            REASON_CANONICALIZED_TO_OPEN_BOUNDARY,
            ws,
        )
    if canonical_endpoint == we:
        return FundingTimestampClassification(
            FUNDING_TIMESTAMP_NORMALIZATION_SPEC_V2,
            True,
            REASON_ACCEPTED,
            we,
        )
    if ws < source_utc <= we:
        return FundingTimestampClassification(
            FUNDING_TIMESTAMP_NORMALIZATION_SPEC_V2,
            True,
            REASON_ACCEPTED,
            None,
        )
    return FundingTimestampClassification(
        FUNDING_TIMESTAMP_NORMALIZATION_SPEC_V2,
        False,
        REASON_OUTSIDE_TOLERANCE,
        None,
    )


def classify_funding_timestamps_for_window(
    source_timestamps: Iterable[datetime],
    *,
    window_start: datetime,
    window_end: datetime,
) -> FundingTimestampWindowClassification:
    """Classify all relevant source timestamps for one funding window.

    Multiple source rows canonicalizing to the same inclusive endpoint are
    ambiguous for clean-carry purposes, so the aggregate rejects the window even
    though the rows prove source data exists.
    """
    ws = _utc(window_start)
    we = _utc(window_end)
    classifications = [
        classify_funding_timestamp_for_window(
            ts,
            window_start=ws,
            window_end=we,
        )
        for ts in source_timestamps
    ]
    if not classifications:
        return FundingTimestampWindowClassification(
            FUNDING_TIMESTAMP_NORMALIZATION_SPEC_V2,
            False,
            REASON_MISSING_SOURCE_ROW,
        )

    accepted = [c for c in classifications if c.clean_net_of_carry_allowed]
    endpoint_hits = [c for c in accepted if c.canonical_endpoint == we]
    accepted_count = len(accepted)

    if len(endpoint_hits) > 1:
        return FundingTimestampWindowClassification(
            FUNDING_TIMESTAMP_NORMALIZATION_SPEC_V2,
            False,
            REASON_DUPLICATE_CANONICAL_ENDPOINT,
            accepted_count,
            we,
        )
    if accepted_count:
        return FundingTimestampWindowClassification(
            FUNDING_TIMESTAMP_NORMALIZATION_SPEC_V2,
            True,
            REASON_ACCEPTED,
            accepted_count,
            we if endpoint_hits else None,
        )
    if any(c.reason == REASON_CANONICALIZED_TO_OPEN_BOUNDARY for c in classifications):
        return FundingTimestampWindowClassification(
            FUNDING_TIMESTAMP_NORMALIZATION_SPEC_V2,
            False,
            REASON_CANONICALIZED_TO_OPEN_BOUNDARY,
            0,
            ws,
        )
    return FundingTimestampWindowClassification(
        FUNDING_TIMESTAMP_NORMALIZATION_SPEC_V2,
        False,
        REASON_OUTSIDE_TOLERANCE,
    )
