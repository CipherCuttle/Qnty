"""H001 synthetic-null calibration execution engine: statistic and bootstrap-path core.

A deterministic, synthetic-only statistic and bootstrap-path computational core,
implemented here for independent review only. This module is not wired into
`execute_calibration` or any control-state file, is never executed by any
caller in this repository, and produces no calibration results. It requires no
real-data access and carries no scientific, paper-trade, shadow, or live
authorization.

Pure computation only: this module performs no filesystem, network, process,
or repository-state access of any kind. The module-level ``*_SHA256``
constants below bind (by value, for comparison only) the three governed
specification documents this engine implements; verifying those constants
against the committed document bytes is the responsibility of tests and
continuity code, never of this module.
"""
from __future__ import annotations

import hashlib
import math
from dataclasses import dataclass

import numpy as np
from numpy.random import Philox

# --- governed document bindings (comparison-only; never read from disk here) ---
H001_SPEC_FREEZE_CANDIDATE_SHA256 = "04b6ea5b7453fccf4787abb26c230e2a02a77545c741c19f6686df16fc2cb7a2"
H001_NUMERICAL_CONVENTIONS_AMENDMENT_SHA256 = "28551aa041aff2985e0023e61516b08f528d93cf72c23c8c3541793f6f61c691"
H001_RNG_RUNTIME_SPECIFICATION_AMENDMENT_SHA256 = "e52b1a4733024e4255cf771b97765cff19f7f5e59cf824732784a1abd594812f"

# --- registered constants (docs/assurance/h001_synthetic_null_calibration_spec_freeze_candidate_v001.json) ---
SEED_DOMAIN = "h001-null-calibration/h001-synthetic-null-calibration-spec-freeze-candidate-v001/synthetic-only"
SAMPLE_LENGTH = 2193
SERIES_COUNT = 9
HAC_LAG = 21
STATIONARY_BLOCK_LENGTH = 63
BOOTSTRAP_REPETITIONS = 10000
RESTART_PROBABILITY_NUMERATOR = 1
RESTART_PROBABILITY_DENOMINATOR = STATIONARY_BLOCK_LENGTH
ALPHA_NUMERATOR = 1
ALPHA_DENOMINATOR = 20
RETRY_CAP = 8

_TWO_POW_64 = 1 << 64
_MASK_256 = (1 << 256) - 1

# Closed registry: the six required stationary DGPs plus the four diagnostic
# stress-case identifiers frozen in the spec-freeze candidate.
DGP_OR_CASE_IDS = frozenset(
    {
        "iid_gaussian",
        "iid_student_t_df5_standardized",
        "nine_series_common_factor_dependence",
        "stationary_ar1_phi_0p3",
        "stationary_ar1_phi_0p7",
        "stationary_garch11_like",
        "autocorrelation_structural_break",
        "mean_zero_regime_switching",
        "sparse_extreme_outliers",
        "variance_structural_break",
    }
)

_DRAW_PURPOSE_IDS = {"INITIAL_INDEX": 1, "RESTART_DECISION": 2, "RESTART_INDEX": 3}


class H001EngineError(Exception):
    """Structured, machine-readable engine failure.

    Tests must assert on ``.code``; message text is not part of the contract.
    """

    def __init__(self, code: str) -> None:
        super().__init__(code)
        self.code = code


def _fail(code: str) -> None:
    raise H001EngineError(code)


def _finite(value: float, code: str) -> float:
    if not math.isfinite(value):
        _fail(code)
    return value


def _canon_zero(value: float) -> float:
    return 0.0 if value == 0.0 else value


# --------------------------------------------------------------------------
# Input contract
# --------------------------------------------------------------------------

def validate_input(x: object) -> np.ndarray:
    """Enforce the exact input contract and return a private contiguous copy.

    Accepts only a plain ``numpy.ndarray`` (no subclass, so masked arrays and
    other ndarray subclasses are rejected), dtype exactly native float64,
    shape exactly ``(9, 2193)``, and every element finite. Nothing is ever
    silently cast.
    """
    if type(x) is not np.ndarray:
        _fail("H001_ENGINE_INVALID_INPUT_TYPE")
    if x.dtype != np.dtype("float64") or not x.dtype.isnative:
        _fail("H001_ENGINE_INVALID_INPUT_DTYPE")
    if x.ndim != 2:
        _fail("H001_ENGINE_INVALID_INPUT_NDIM")
    if x.shape != (SERIES_COUNT, SAMPLE_LENGTH):
        _fail("H001_ENGINE_INVALID_INPUT_SHAPE")
    if not bool(np.isfinite(x).all()):
        _fail("H001_ENGINE_INVALID_INPUT_NON_FINITE")
    return np.array(x, dtype=np.float64, order="C", copy=True)


# --------------------------------------------------------------------------
# Domain 1-3: HAC mean / autocovariance / long-run variance / standard error
# --------------------------------------------------------------------------

def hac_mean(x: np.ndarray) -> float:
    n = x.shape[0]
    if n < 1:
        _fail("H001_NC_NON_FINITE_INPUT")
    acc = 0.0
    for t in range(n):
        value = float(x[t])
        if not math.isfinite(value):
            _fail("H001_NC_NON_FINITE_INPUT")
        acc = acc + value
        _finite(acc, "H001_NC_NON_FINITE_INTERMEDIATE")
    result = acc / n
    _finite(result, "H001_NC_NON_FINITE_INTERMEDIATE")
    return _canon_zero(result)


def hac_gamma(x: np.ndarray, xbar: float, lag: int) -> float:
    n = x.shape[0]
    acc = 0.0
    for t in range(lag, n):
        left_centered = float(x[t]) - xbar
        _finite(left_centered, "H001_NC_NON_FINITE_INTERMEDIATE")
        right_centered = float(x[t - lag]) - xbar
        _finite(right_centered, "H001_NC_NON_FINITE_INTERMEDIATE")
        product = left_centered * right_centered
        _finite(product, "H001_NC_NON_FINITE_INTERMEDIATE")
        acc = acc + product
        _finite(acc, "H001_NC_NON_FINITE_INTERMEDIATE")
    gamma = acc / n
    _finite(gamma, "H001_NC_NON_FINITE_INTERMEDIATE")
    return gamma


def hac_omega2(x: np.ndarray, lag_order: int) -> float:
    xbar = hac_mean(x)
    omega2 = hac_gamma(x, xbar, 0)
    for j in range(1, lag_order + 1):
        ratio = j / (lag_order + 1)
        _finite(ratio, "H001_NC_NON_FINITE_INTERMEDIATE")
        weight = 1.0 - ratio
        _finite(weight, "H001_NC_NON_FINITE_INTERMEDIATE")
        weighted_gamma = weight * hac_gamma(x, xbar, j)
        _finite(weighted_gamma, "H001_NC_NON_FINITE_INTERMEDIATE")
        doubled_term = 2.0 * weighted_gamma
        _finite(doubled_term, "H001_NC_NON_FINITE_INTERMEDIATE")
        omega2 = omega2 + doubled_term
        _finite(omega2, "H001_NC_NON_FINITE_INTERMEDIATE")
    return omega2


def hac_se(omega2: float, n: int) -> float:
    _finite(omega2, "H001_NC_NON_FINITE_INTERMEDIATE")
    if omega2 < 0.0:
        _fail("H001_NC_NEGATIVE_LONG_RUN_VARIANCE")
    if omega2 == 0.0:
        return 0.0
    scaled = omega2 / n
    _finite(scaled, "H001_NC_NON_FINITE_INTERMEDIATE")
    se = math.sqrt(scaled)
    _finite(se, "H001_NC_NON_FINITE_INTERMEDIATE")
    return se


# --------------------------------------------------------------------------
# Domain 4: null centering and studentization
# --------------------------------------------------------------------------

def centered_numerator(xbar_star: float, xbar: float) -> float:
    _finite(xbar_star, "H001_NC_NON_FINITE_INTERMEDIATE")
    _finite(xbar, "H001_NC_NON_FINITE_INTERMEDIATE")
    centered = xbar_star - xbar
    _finite(centered, "H001_NC_NON_FINITE_INTERMEDIATE")
    return _canon_zero(centered)


def stud(num: float, se: float) -> float:
    _finite(num, "H001_NC_NON_FINITE_INTERMEDIATE")
    _finite(se, "H001_NC_NON_FINITE_INTERMEDIATE")
    if se < 0.0:
        _fail("H001_NC_NEGATIVE_STANDARD_ERROR")
    if se > 0.0:
        result = num / se
        _finite(result, "H001_NC_NON_FINITE_INTERMEDIATE")
        return _canon_zero(result)
    if num == 0.0:
        return 0.0
    _fail("H001_NC_ZERO_STANDARD_ERROR")


# --------------------------------------------------------------------------
# Closed RNG interface: frozen bootstrap coordinate, Philox4x64-10 raw words,
# exact bounded-integer mapping, exact rational Bernoulli mapping.
# --------------------------------------------------------------------------

@dataclass(frozen=True)
class BootstrapCoordinate:
    """Governed fields only. The engine builds the exact payload internally;
    no caller-supplied payload, callback, or callable is ever accepted."""

    dgp_or_case_id: str
    outer_replication_index: int
    bootstrap_replication_index: int

    def __post_init__(self) -> None:
        if type(self.dgp_or_case_id) is not str or self.dgp_or_case_id not in DGP_OR_CASE_IDS:
            _fail("H001_RNG_INVALID_COORDINATE")
        if type(self.outer_replication_index) is not int or not (0 <= self.outer_replication_index <= 1999):
            _fail("H001_RNG_COORDINATE_OUT_OF_DOMAIN")
        if type(self.bootstrap_replication_index) is not int or not (0 <= self.bootstrap_replication_index <= 9999):
            _fail("H001_RNG_COORDINATE_OUT_OF_DOMAIN")

    def payload(self) -> str:
        return (
            f"{SEED_DOMAIN}:{self.dgp_or_case_id}"
            f":outer:{self.outer_replication_index}:bootstrap:{self.bootstrap_replication_index}"
        )


def _key_words(coordinate: BootstrapCoordinate) -> tuple[int, int]:
    hex_digest = hashlib.sha256(coordinate.payload().encode("utf-8")).hexdigest()
    return int(hex_digest[0:16], 16), int(hex_digest[16:32], 16)


def _counter_word_0(draw_purpose: str, sample_position: int, attempt_index: int) -> int:
    if draw_purpose not in _DRAW_PURPOSE_IDS:
        _fail("H001_RNG_UNKNOWN_DRAW_PURPOSE")
    if type(sample_position) is not int or not (0 <= sample_position <= SAMPLE_LENGTH - 1):
        _fail("H001_RNG_COORDINATE_OUT_OF_DOMAIN")
    if type(attempt_index) is not int or not (0 <= attempt_index <= RETRY_CAP - 1):
        _fail("H001_RNG_COORDINATE_OUT_OF_DOMAIN")
    return attempt_index + 256 * _DRAW_PURPOSE_IDS[draw_purpose] + 65536 * sample_position


def raw_word(coordinate: BootstrapCoordinate, draw_purpose: str, sample_position: int, attempt_index: int) -> int:
    """Lane 0 of the Philox4x64-10 block addressed by this coordinate/draw."""
    counter_word_0 = _counter_word_0(draw_purpose, sample_position, attempt_index)
    key_word_0, key_word_1 = _key_words(coordinate)
    bit_generator = Philox(counter=(counter_word_0 - 1) & _MASK_256, key=key_word_0 + (key_word_1 << 64))
    return int(bit_generator.random_raw(4)[0])


def uniform_bounded(coordinate: BootstrapCoordinate, draw_purpose: str, sample_position: int, n: int) -> int:
    if type(n) is not int or not (1 <= n <= _TWO_POW_64):
        _fail("H001_RNG_INVALID_BOUND")
    limit = _TWO_POW_64 - (_TWO_POW_64 % n)
    for attempt_index in range(RETRY_CAP):
        word = raw_word(coordinate, draw_purpose, sample_position, attempt_index)
        if word < limit:
            return word % n
    _fail("H001_RNG_RETRY_CAP_EXHAUSTED")


def bernoulli_rational(coordinate: BootstrapCoordinate, sample_position: int, p: int, q: int) -> bool:
    if type(p) is not int or type(q) is not int or q < 1 or p < 0 or p > q:
        _fail("H001_RNG_INVALID_RATIONAL")
    u = uniform_bounded(coordinate, "RESTART_DECISION", sample_position, q)
    return u < p


def _build_shared_path(coordinate: BootstrapCoordinate) -> list[int]:
    path = [uniform_bounded(coordinate, "INITIAL_INDEX", 0, SAMPLE_LENGTH)]
    for t in range(1, SAMPLE_LENGTH):
        if bernoulli_rational(coordinate, t, RESTART_PROBABILITY_NUMERATOR, RESTART_PROBABILITY_DENOMINATOR):
            path.append(uniform_bounded(coordinate, "RESTART_INDEX", t, SAMPLE_LENGTH))
        else:
            path.append((path[t - 1] + 1) % SAMPLE_LENGTH)
    return path


# --------------------------------------------------------------------------
# Streaming statistic / bootstrap-path API
# --------------------------------------------------------------------------

def compute_observed_statistics(x: np.ndarray) -> tuple[tuple[float, ...], tuple[float, ...], tuple[float, ...]]:
    """Per-series observed (xbar, se, t) over Domains 1-3, one series at a time."""
    xbar_values: list[float] = []
    se_values: list[float] = []
    t_values: list[float] = []
    for i in range(x.shape[0]):
        series = x[i]
        xbar_i = hac_mean(series)
        se_i = hac_se(hac_omega2(series, HAC_LAG), series.shape[0])
        t_i = stud(xbar_i, se_i)
        xbar_values.append(xbar_i)
        se_values.append(se_i)
        t_values.append(t_i)
    return tuple(xbar_values), tuple(se_values), tuple(t_values)


def compute_one_bootstrap_replication(
    x: np.ndarray, xbar: tuple[float, ...], coordinate: BootstrapCoordinate
) -> tuple[float, ...]:
    """Build one shared synchronous index path and studentize all series against
    it, without materializing any batch of paths or replications.

    ``xbar`` is the fixed observed per-series mean (Domain 1, computed once by
    `compute_observed_statistics`). The bootstrap standard error is always
    recomputed on the resampled series here; the observed standard error is
    never accepted or reused (STUDENTIZE-RECOMPUTE-BOOTSTRAP-SE).
    """
    path = _build_shared_path(coordinate)
    tstar_values: list[float] = []
    for i in range(x.shape[0]):
        series = x[i]
        resampled = series[path]
        xbar_star = hac_mean(resampled)
        numerator = centered_numerator(xbar_star, xbar[i])
        se_star = hac_se(hac_omega2(resampled, HAC_LAG), resampled.shape[0])
        tstar_values.append(stud(numerator, se_star))
    return tuple(tstar_values)


def _absmax(values: tuple[float, ...]) -> float:
    m = 0.0
    for value in values:
        a = abs(value)
        _finite(a, "H001_NC_NON_FINITE_INTERMEDIATE")
        if a > m:
            m = a
    return m


def update_exceedance_counts(
    counts: tuple[int, ...], observed_abs_t: tuple[float, ...], bootstrap_tstar: tuple[float, ...]
) -> tuple[int, ...]:
    """Pure integer counter update for one bootstrap replication; never mutates
    the caller's ``counts`` tuple/list."""
    bootstrap_max_abs_tstar = _absmax(bootstrap_tstar)
    updated = list(counts)
    for i in range(len(observed_abs_t)):
        if bootstrap_max_abs_tstar >= observed_abs_t[i]:
            updated[i] = updated[i] + 1
    return tuple(updated)


def finalize_exact_pvalues(
    counts: tuple[int, ...], total_bootstrap_replications: int
) -> tuple[tuple[int, int, bool], ...]:
    """Exact integer (numerator, denominator, reject) triples per series.

    ``denominator = total_bootstrap_replications + 1``; rejection uses the
    exact integer comparison ``numerator * ALPHA_DENOMINATOR <= denominator *
    ALPHA_NUMERATOR`` -- never a float threshold.
    """
    denominator = total_bootstrap_replications + 1
    results = []
    for count in counts:
        numerator = 1 + count
        reject = numerator * ALPHA_DENOMINATOR <= denominator * ALPHA_NUMERATOR
        results.append((numerator, denominator, reject))
    return tuple(results)
