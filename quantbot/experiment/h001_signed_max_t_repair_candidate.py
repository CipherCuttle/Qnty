"""Non-effective H001 positive-mean max-t repair candidate (ADMIN_LANE).

Synthetic review helper only. NOT a replacement for the effective, hash-bound
numerical convention; not connected to calibration, H001 execution, or trading.
The actual frozen-contract remediation requires separate protocol governance.
"""
from __future__ import annotations

import math

SERIES_COUNT = 9
REGISTERED_BOOTSTRAP_REPETITIONS = 10_000
ALPHA_NUMERATOR = 1
ALPHA_DENOMINATOR = 20
SAMPLE_LENGTH = 2193
RETRY_CAP = 8
_PURPOSES = frozenset({"INITIAL_INDEX", "RESTART_DECISION", "RESTART_INDEX"})


class H001RepairCandidateError(ValueError):
    """Structured review-only validation failure."""
    def __init__(self, code: str):
        super().__init__(code)
        self.code = code


def _failure(code: str) -> None:
    raise H001RepairCandidateError(code)


def _vector(value: object, name: str) -> tuple[float, ...]:
    if type(value) is not tuple or len(value) != SERIES_COUNT:
        _failure(f"H001_CANDIDATE_INVALID_{name}_VECTOR")
    for component in value:
        if type(component) is not float or not math.isfinite(component):
            _failure(f"H001_CANDIDATE_INVALID_{name}_VECTOR")
    return value


def _counts(value: object, upper_bound: int) -> tuple[int, ...]:
    if type(value) is not tuple or len(value) != SERIES_COUNT:
        _failure("H001_CANDIDATE_INVALID_COUNTS")
    for count in value:
        if type(count) is not int or not (0 <= count <= upper_bound):
            _failure("H001_CANDIDATE_INVALID_COUNTS")
    return value


def _bootstrap_repetitions(value: object) -> int:
    if type(value) is not int or value < 1:
        _failure("H001_CANDIDATE_INVALID_BOOTSTRAP_REPETITIONS")
    return value


def upper_tail_exceedance_update(
    counts: tuple[int, ...], observed_t: tuple[float, ...], bootstrap_tstar: tuple[float, ...],
    *, total_bootstrap_repetitions: int = REGISTERED_BOOTSTRAP_REPETITIONS,
) -> tuple[int, ...]:
    """One synchronous positive-direction max-t bootstrap comparison.

    The **signed** maximum of the same resampling path across nine candidates
    is compared to each observed signed t. Never apply abs() here.
    """
    total = _bootstrap_repetitions(total_bootstrap_repetitions)
    counts = _counts(counts, total - 1)
    observed_t = _vector(observed_t, "OBSERVED_T")
    bootstrap_tstar = _vector(bootstrap_tstar, "BOOTSTRAP_TSTAR")
    max_bootstrap_tstar = max(bootstrap_tstar)
    return tuple(
        count + int(max_bootstrap_tstar >= t)
        for count, t in zip(counts, observed_t)
    )


def positive_mean_pvalues_and_rejections(
    counts: tuple[int, ...], observed_t: tuple[float, ...],
    *, total_bootstrap_repetitions: int = REGISTERED_BOOTSTRAP_REPETITIONS,
) -> tuple[tuple[int, int, bool], ...]:
    """Adjusted upper-tail p-value triples and explicit positive-mean eligibility.

    The sign guard is a conservative *proposed* decision, not yet an effective
    amendment. It avoids reporting evidence for H1: mean>0 for negative t
    even when a pathological bootstrap distribution lies entirely below it.
    """
    total = _bootstrap_repetitions(total_bootstrap_repetitions)
    counts = _counts(counts, total)
    observed_t = _vector(observed_t, "OBSERVED_T")
    denominator = total + 1
    return tuple(
        (1 + count, denominator,
         (t > 0.0 and (1 + count) * ALPHA_DENOMINATOR <= denominator * ALPHA_NUMERATOR))
        for count, t in zip(counts, observed_t)
    )


def validate_closed_rng_draw(
    coordinate: object, draw_purpose: object, sample_position: object,
    attempt_index: object,
) -> None:
    """Review-only guard before invoking the existing Philox raw-word helper.

    This does not modify the engine's public raw_word method: callers of that
    method directly retain the baseline gap until an authorized code repair.
    """
    from quantbot.experiment.h001_null_calibration_engine import BootstrapCoordinate

    if type(coordinate) is not BootstrapCoordinate:
        _failure("H001_CANDIDATE_INVALID_COORDINATE_TYPE")
    if type(draw_purpose) is not str or draw_purpose not in _PURPOSES:
        _failure("H001_CANDIDATE_UNKNOWN_PURPOSE")
    if type(sample_position) is not int or not (0 <= sample_position < SAMPLE_LENGTH):
        _failure("H001_CANDIDATE_INVALID_SAMPLE_POSITION")
    if type(attempt_index) is not int or not (0 <= attempt_index < RETRY_CAP):
        _failure("H001_CANDIDATE_INVALID_ATTEMPT_INDEX")
    if (draw_purpose == "INITIAL_INDEX") != (sample_position == 0):
        _failure("H001_CANDIDATE_FORBIDDEN_PURPOSE_POSITION")


def guarded_raw_word(coordinate: object, draw_purpose: object, sample_position: object,
                     attempt_index: object) -> int:
    validate_closed_rng_draw(coordinate, draw_purpose, sample_position, attempt_index)
    from quantbot.experiment.h001_null_calibration_engine import raw_word
    return raw_word(coordinate, draw_purpose, sample_position, attempt_index)