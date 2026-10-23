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


def _unchecked_tail_pvalues_and_rejections(
    counts: tuple[int, ...], observed_t: tuple[float, ...],
    *, total_bootstrap_repetitions: int = REGISTERED_BOOTSTRAP_REPETITIONS,
) -> tuple[tuple[int, int, bool], ...]:
    """Exact adjusted one-sided max-t p-values and unmodified rejection rule.

    Statistical rejection is determined solely by adjusted p <= alpha.
    It is NOT a finding of positive net returns or strategy eligibility.
    A separate registered positive-net-mean gate must be applied before any
    economic interpretation. A caller must also prove all B draws completed:
    counts alone cannot establish completed-replication provenance.
    """
    total = _bootstrap_repetitions(total_bootstrap_repetitions)
    counts = _counts(counts, total)
    _vector(observed_t, "OBSERVED_T")
    denominator = total + 1
    return tuple(
        (1 + count, denominator,
         (1 + count) * ALPHA_DENOMINATOR <= denominator * ALPHA_NUMERATOR)
        for count in counts
    )


def upper_tail_pvalues_and_rejections(
    completed_run: CompletedBootstrapRun, observed_t: tuple[float, ...],
    variant_ids: tuple[str, ...],
) -> tuple[tuple[int, int, bool], ...]:
    """Public finalization only through a complete bound review accumulator.

    This does not independently certify bootstrap RNG/path provenance.
    """
    if type(completed_run) not in (CompletedBootstrapRun, EngineBoundBootstrapRun):
        _failure("H001_CANDIDATE_UNSEALED_COUNTS_FORBIDDEN")
    return completed_run.finalize(observed_t, variant_ids)


def positive_net_means_gate(base_cost_net_mean: float, stress_1_net_mean: float) -> bool:
    """Only the two registered positive-net-mean conditions, never a p-value.

    This is a PARTIAL strategy eligibility predicate, not complete validation:
    activity/entries, annual positivity, concentration and other frozen
    acceptance rules must also hold. It makes no scientific inference.
    """
    for value in (base_cost_net_mean, stress_1_net_mean):
        if type(value) is not float or not math.isfinite(value):
            _failure("H001_CANDIDATE_INVALID_NET_MEAN")
    return base_cost_net_mean > 0.0 and stress_1_net_mean > 0.0


def validate_closed_rng_draw(
    coordinate: object, draw_purpose: object, sample_position: object,
    attempt_index: object,
) -> None:
    """Review-only guard before invoking the existing Philox raw-word helper.

    This does not modify the engine's public raw_word method: callers of that
    method directly retain the baseline gap until an authorized code repair.
    """
    from quantbot.experiment.h001_null_calibration_engine import BootstrapCoordinate, DGP_OR_CASE_IDS

    if type(coordinate) is not BootstrapCoordinate:
        _failure("H001_CANDIDATE_INVALID_COORDINATE_TYPE")
    if type(coordinate.dgp_or_case_id) is not str or coordinate.dgp_or_case_id not in DGP_OR_CASE_IDS:
        _failure("H001_CANDIDATE_INVALID_COORDINATE_DOMAIN")
    if type(coordinate.outer_replication_index) is not int or not (0 <= coordinate.outer_replication_index < 2000):
        _failure("H001_CANDIDATE_INVALID_COORDINATE_DOMAIN")
    if type(coordinate.bootstrap_replication_index) is not int or not (0 <= coordinate.bootstrap_replication_index < REGISTERED_BOOTSTRAP_REPETITIONS):
        _failure("H001_CANDIDATE_INVALID_COORDINATE_DOMAIN")
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

class CompletedBootstrapRun:
    """Review-only sequential accumulator; never accepts caller-provided counts.

    Each replication is one completed, synchronized nine-series bootstrap draw.
    Identical realized paths from distinct replication indices are permitted.
    """

    __slots__ = ("_observed", "_variants", "_counts", "_next", "_total")

    def __init__(self, observed_t: tuple[float, ...], variant_ids: tuple[str, ...],
                 *, total_bootstrap_repetitions: int = REGISTERED_BOOTSTRAP_REPETITIONS):
        self._observed = _vector(observed_t, "OBSERVED_T")
        if (type(variant_ids) is not tuple or len(variant_ids) != SERIES_COUNT
                or any(type(v) is not str or not v for v in variant_ids)
                or len(set(variant_ids)) != SERIES_COUNT):
            _failure("H001_CANDIDATE_INVALID_VARIANT_IDS")
        self._variants = variant_ids
        self._total = _bootstrap_repetitions(total_bootstrap_repetitions)
        self._counts = (0,) * SERIES_COUNT
        self._next = 0

    def add_completed_replication(self, replication_index: int,
                                  bootstrap_tstar: tuple[float, ...]) -> None:
        if type(replication_index) is not int or replication_index != self._next or self._next >= self._total:
            _failure("H001_CANDIDATE_REPLICATION_ORDER_OR_COMPLETENESS")
        values = _vector(bootstrap_tstar, "BOOTSTRAP_TSTAR")
        self._counts = upper_tail_exceedance_update(
            self._counts, self._observed, values,
            total_bootstrap_repetitions=self._total,
        )
        self._next += 1

    def finalize(self, observed_t: tuple[float, ...], variant_ids: tuple[str, ...]
                 ) -> tuple[tuple[int, int, bool], ...]:
        if self._next != self._total:
            _failure("H001_CANDIDATE_INCOMPLETE_BOOTSTRAP_RUN")
        if _vector(observed_t, "OBSERVED_T") != self._observed or variant_ids != self._variants:
            _failure("H001_CANDIDATE_OBSERVED_OR_VARIANT_MISMATCH")
        return _unchecked_tail_pvalues_and_rejections(
            self._counts, self._observed, total_bootstrap_repetitions=self._total,
        )

class EngineBoundBootstrapRun(CompletedBootstrapRun):
    """Synthetic-only engine-computed path; caller cannot submit t-star vectors.

    The input is copied, made read-only, and hashed. This remains review-only,
    not a cryptographic attestation or an effective scientific protocol.
    """

    __slots__ = ("_x", "_means", "_case", "_outer", "_digest")

    def __init__(self, x: object, variant_ids: tuple[str, ...],
                 dgp_or_case_id: str, outer_replication_index: int,
                 *, total_bootstrap_repetitions: int = REGISTERED_BOOTSTRAP_REPETITIONS):
        import hashlib
        import numpy as np
        from quantbot.experiment.h001_null_calibration_engine import (
            BootstrapCoordinate, compute_observed_statistics, validate_input,
        )
        BootstrapCoordinate(dgp_or_case_id, outer_replication_index, 0)
        checked = validate_input(x)
        frozen = np.array(checked, dtype=np.float64, copy=True, order="C")
        frozen.setflags(write=False)
        means, _, observed = compute_observed_statistics(frozen)
        super().__init__(observed, variant_ids,
                         total_bootstrap_repetitions=total_bootstrap_repetitions)
        self._x = frozen
        self._means = means
        self._case = dgp_or_case_id
        self._outer = outer_replication_index
        self._digest = hashlib.sha256(frozen.tobytes(order="C")).hexdigest()

    @property
    def input_sha256(self) -> str:
        return self._digest

    def add_completed_replication(self, replication_index: int,
                                  bootstrap_tstar: tuple[float, ...]) -> None:
        _failure("H001_CANDIDATE_EXTERNAL_BOOTSTRAP_VECTOR_FORBIDDEN")

    def compute_next_replication(self) -> None:
        from quantbot.experiment.h001_null_calibration_engine import (
            BootstrapCoordinate, compute_one_bootstrap_replication,
        )
        if self._next >= self._total:
            _failure("H001_CANDIDATE_REPLICATION_ORDER_OR_COMPLETENESS")
        coordinate = BootstrapCoordinate(self._case, self._outer, self._next)
        values = compute_one_bootstrap_replication(self._x, self._means, coordinate)
        super().add_completed_replication(self._next, _vector(values, "BOOTSTRAP_TSTAR"))

    def finalize(self, observed_t: tuple[float, ...], variant_ids: tuple[str, ...]
                 ) -> tuple[tuple[int, int, bool], ...]:
        import hashlib
        if hashlib.sha256(self._x.tobytes(order="C")).hexdigest() != self._digest:
            _failure("H001_CANDIDATE_INPUT_DRIFT")
        return super().finalize(observed_t, variant_ids)
