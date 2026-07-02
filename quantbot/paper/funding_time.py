"""Shared funding timestamp normalization for paper funding coverage.

FUNDING_TIMESTAMP_NORMALIZATION_SPEC_V1 keeps funding windows open-closed while
allowing tiny source-side jitter after a funding endpoint. The helper is pure:
it parses no files, mutates no state, and only classifies already-parsed UTC
datetimes for one funding window.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Iterable

FUNDING_TIMESTAMP_NORMALIZATION_SPEC_V1 = "FUNDING_TIMESTAMP_NORMALIZATION_SPEC_V1"
AFTER_ENDPOINT_TOLERANCE_MS = 10

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


def _delta_ms(later: datetime, earlier: datetime) -> int:
    return round((later - earlier).total_seconds() * 1000)


def canonicalize_funding_timestamp(
    source_ts: datetime,
    *,
    window_start: datetime,
    window_end: datetime,
    tolerance_ms: int = AFTER_ENDPOINT_TOLERANCE_MS,
) -> datetime | None:
    """Return the boundary a source timestamp canonicalizes to, if any.

    Canonicalization is one-sided: only timestamps exactly on or after a boundary
    by at most ``tolerance_ms`` canonicalize to that boundary. The open boundary
    is intentionally checked first so a row a few milliseconds after
    ``window_start`` is not counted inside ``(window_start, window_end]``.
    """
    source_utc = _utc(source_ts)
    for endpoint in (_utc(window_start), _utc(window_end)):
        delta_ms = _delta_ms(source_utc, endpoint)
        if 0 <= delta_ms <= tolerance_ms:
            return endpoint
    return None


def classify_funding_timestamp_for_window(
    source_ts: datetime,
    *,
    window_start: datetime,
    window_end: datetime,
    tolerance_ms: int = AFTER_ENDPOINT_TOLERANCE_MS,
) -> FundingTimestampClassification:
    """Classify one source timestamp against one funding window."""
    ws = _utc(window_start)
    we = _utc(window_end)
    source_utc = _utc(source_ts)
    canonical_endpoint = canonicalize_funding_timestamp(
        source_utc,
        window_start=ws,
        window_end=we,
        tolerance_ms=tolerance_ms,
    )

    if canonical_endpoint == ws:
        return FundingTimestampClassification(
            FUNDING_TIMESTAMP_NORMALIZATION_SPEC_V1,
            False,
            REASON_CANONICALIZED_TO_OPEN_BOUNDARY,
            ws,
        )
    if canonical_endpoint == we:
        return FundingTimestampClassification(
            FUNDING_TIMESTAMP_NORMALIZATION_SPEC_V1,
            True,
            REASON_ACCEPTED,
            we,
        )
    if ws < source_utc <= we:
        return FundingTimestampClassification(
            FUNDING_TIMESTAMP_NORMALIZATION_SPEC_V1,
            True,
            REASON_ACCEPTED,
            None,
        )
    return FundingTimestampClassification(
        FUNDING_TIMESTAMP_NORMALIZATION_SPEC_V1,
        False,
        REASON_OUTSIDE_TOLERANCE,
        None,
    )


def classify_funding_timestamps_for_window(
    source_timestamps: Iterable[datetime],
    *,
    window_start: datetime,
    window_end: datetime,
    tolerance_ms: int = AFTER_ENDPOINT_TOLERANCE_MS,
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
            tolerance_ms=tolerance_ms,
        )
        for ts in source_timestamps
    ]
    if not classifications:
        return FundingTimestampWindowClassification(
            FUNDING_TIMESTAMP_NORMALIZATION_SPEC_V1,
            False,
            REASON_MISSING_SOURCE_ROW,
        )

    accepted = [c for c in classifications if c.clean_net_of_carry_allowed]
    endpoint_hits = [c for c in accepted if c.canonical_endpoint == we]
    accepted_count = len(accepted)

    if len(endpoint_hits) > 1:
        return FundingTimestampWindowClassification(
            FUNDING_TIMESTAMP_NORMALIZATION_SPEC_V1,
            False,
            REASON_DUPLICATE_CANONICAL_ENDPOINT,
            accepted_count,
            we,
        )
    if accepted_count:
        return FundingTimestampWindowClassification(
            FUNDING_TIMESTAMP_NORMALIZATION_SPEC_V1,
            True,
            REASON_ACCEPTED,
            accepted_count,
            we if endpoint_hits else None,
        )
    if any(c.reason == REASON_CANONICALIZED_TO_OPEN_BOUNDARY for c in classifications):
        return FundingTimestampWindowClassification(
            FUNDING_TIMESTAMP_NORMALIZATION_SPEC_V1,
            False,
            REASON_CANONICALIZED_TO_OPEN_BOUNDARY,
            0,
            ws,
        )
    return FundingTimestampWindowClassification(
        FUNDING_TIMESTAMP_NORMALIZATION_SPEC_V1,
        False,
        REASON_OUTSIDE_TOLERANCE,
    )
