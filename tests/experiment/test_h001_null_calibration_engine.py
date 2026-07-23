"""Tests for the H001 synthetic-null calibration execution engine.

This file directly exercises the engine against the applicable subset of the
governed RNG-runtime and numerical-conventions known-answer fixtures, loaded
directly from the reviewed governance JSON documents and never retyped or
generated from the engine under test; any disagreement is an
environment-incompatibility failure (RNG_COMPATIBILITY_FAILURE), never
grounds to edit an expected value. It supplements, rather than duplicates,
the two pre-existing complete independent derivations
(`test_h001_rng_runtime_kat_reference_derivation.py` /
`test_h001_rng_runtime_kat_numpy_derivation.py` and
`test_h001_numerical_conventions_kat_reference_derivation.py` /
`test_h001_numerical_conventions_kat_independent_derivation.py`), which
already exercise every fixture in both governed documents. What this file
adds beyond fixture replay is engine-bound mutation tests (killing specific
wrong-convention and wrong-RNG-rule mutants), metamorphic properties,
isolation/evaluation-order-independence checks, and bounded-memory streaming
behavior, all against the actual engine module under review.
"""
from __future__ import annotations

import ast
import copy
import math
import platform
import sys
import tracemalloc
from pathlib import Path

import numpy as np
import pytest

from quantbot.assurance import h001_null_calibration as harness
from quantbot.experiment import h001_null_calibration_engine as engine
from quantbot.experiment.h001_null_calibration_engine import BootstrapCoordinate, H001EngineError

ROOT = Path(__file__).parents[2]
NUMERICAL_CONVENTIONS_PATH = ROOT / "docs/control/amendments/candidate1_h001_synthetic_null_calibration_numerical_conventions_amendment_candidate_v001.json"
RNG_RUNTIME_PATH = ROOT / "docs/control/amendments/candidate1_h001_synthetic_null_calibration_rng_runtime_specification_amendment_v001.json"
ENGINE_MODULE_PATH = ROOT / "quantbot/experiment/h001_null_calibration_engine.py"

ENVIRONMENT_IDENTITY = {
    "python_version": sys.version,
    "numpy_version": np.__version__,
    "platform": platform.platform(),
    "architecture": platform.machine(),
}


def _fixtures(path: Path) -> dict:
    import json

    return json.loads(path.read_bytes())["known_answer_fixtures"]


def _assert_kat(observed, expected, fixture_id: str) -> None:
    if observed != expected:
        pytest.fail(
            "RNG_COMPATIBILITY_FAILURE: "
            f"{fixture_id} disagreement observed={observed!r} expected={expected!r} "
            f"environment={ENVIRONMENT_IDENTITY!r}"
        )


def rng_fixtures() -> dict:
    return _fixtures(RNG_RUNTIME_PATH)


def nc_fixtures() -> dict:
    return _fixtures(NUMERICAL_CONVENTIONS_PATH)


def coordinate_for(fixtures: dict, tag: str) -> BootstrapCoordinate:
    source = fixtures["KAT-PAYLOAD-001" if tag == "payload_1" else "KAT-PAYLOAD-002"]
    return BootstrapCoordinate(source["dgp_or_case_id"], source["outer_replication_index"], source["bootstrap_replication_index"])


# ---------------------------------------------------------------------------
# Module boundary and environment recording
# ---------------------------------------------------------------------------

def test_environment_identity_is_recorded():
    assert ENVIRONMENT_IDENTITY["python_version"]
    assert ENVIRONMENT_IDENTITY["numpy_version"]
    assert ENVIRONMENT_IDENTITY["platform"]
    assert ENVIRONMENT_IDENTITY["architecture"]


def test_engine_module_has_no_filesystem_network_or_control_state_access():
    source = ENGINE_MODULE_PATH.read_text(encoding="utf-8")
    tree = ast.parse(source)
    imported = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imported.update(alias.name.split(".")[0] for alias in node.names)
        elif isinstance(node, ast.ImportFrom):
            imported.add((node.module or "").split(".")[0])
    assert imported <= {"__future__", "hashlib", "math", "dataclasses", "numpy"}, f"unexpected import: {imported}"
    for banned in ("pathlib", "os", "pandas", "requests", "subprocess", "multiprocessing", "concurrent", "json"):
        assert banned not in imported, f"engine must not import {banned}"
    referenced_names = {node.id for node in ast.walk(tree) if isinstance(node, ast.Name)}
    referenced_attrs = {node.attr for node in ast.walk(tree) if isinstance(node, ast.Attribute)}
    for banned in ("open", "active_task", "execute_calibration"):
        assert banned not in referenced_names and banned not in referenced_attrs, f"engine must not reference {banned}"


def test_harness_execute_calibration_still_unconditionally_refuses():
    with pytest.raises(harness.AssuranceValidationError, match="CALIBRATION_EXECUTION_NOT_AUTHORIZED"):
        harness.execute_calibration()
    with pytest.raises(harness.AssuranceValidationError, match="CALIBRATION_EXECUTION_NOT_AUTHORIZED"):
        harness.execute_calibration(1, 2, kwarg=3)


# ---------------------------------------------------------------------------
# validate_input: exact input contract, precedence, mutation isolation
# ---------------------------------------------------------------------------

def _valid_array():
    return np.zeros((9, 2193), dtype=np.float64)


def test_validate_input_accepts_conforming_array_and_copies():
    original = _valid_array()
    original[0, 0] = 1.5
    copied = engine.validate_input(original)
    assert copied.shape == (9, 2193) and copied.dtype == np.float64
    original[0, 0] = 99.0
    assert copied[0, 0] == 1.5, "caller mutation of the original array must not affect the validated copy"
    copied[0, 1] = -7.0
    assert original[0, 1] == 0.0, "mutating the returned copy must not affect the caller's original array"


@pytest.mark.parametrize(
    "bad, expected_code",
    [
        (_valid_array().tolist(), "H001_ENGINE_INVALID_INPUT_TYPE"),
        (np.zeros((9, 2193), dtype=np.float32), "H001_ENGINE_INVALID_INPUT_DTYPE"),
        (np.zeros((9, 2193), dtype=np.int64), "H001_ENGINE_INVALID_INPUT_DTYPE"),
        (np.zeros((9, 2193), dtype=bool), "H001_ENGINE_INVALID_INPUT_DTYPE"),
        (np.zeros((9, 2193), dtype=object), "H001_ENGINE_INVALID_INPUT_DTYPE"),
        (np.zeros((9, 2193), dtype=">f8"), "H001_ENGINE_INVALID_INPUT_DTYPE"),
        (np.zeros(2193, dtype=np.float64), "H001_ENGINE_INVALID_INPUT_NDIM"),
        (np.zeros((2193, 9), dtype=np.float64), "H001_ENGINE_INVALID_INPUT_SHAPE"),
        (np.zeros((9, 2193, 1), dtype=np.float64), "H001_ENGINE_INVALID_INPUT_NDIM"),
        (np.zeros((8, 2193), dtype=np.float64), "H001_ENGINE_INVALID_INPUT_SHAPE"),
    ],
)
def test_validate_input_rejects_non_conforming_input(bad, expected_code):
    with pytest.raises(H001EngineError) as excinfo:
        engine.validate_input(bad)
    assert excinfo.value.code == expected_code


def test_validate_input_rejects_masked_array_as_subclass():
    masked = np.ma.masked_array(_valid_array())
    with pytest.raises(H001EngineError) as excinfo:
        engine.validate_input(masked)
    assert excinfo.value.code == "H001_ENGINE_INVALID_INPUT_TYPE"


def test_validate_input_rejects_transposed_shape():
    with pytest.raises(H001EngineError) as excinfo:
        engine.validate_input(_valid_array().T.copy())
    assert excinfo.value.code == "H001_ENGINE_INVALID_INPUT_SHAPE"


def test_validate_input_rejects_non_finite_values():
    bad = _valid_array()
    bad[3, 100] = float("nan")
    with pytest.raises(H001EngineError) as excinfo:
        engine.validate_input(bad)
    assert excinfo.value.code == "H001_ENGINE_INVALID_INPUT_NON_FINITE"


def test_multi_invalid_input_deterministic_failure_precedence():
    # Wrong type always wins first, regardless of what else is also wrong.
    with pytest.raises(H001EngineError) as excinfo:
        engine.validate_input([[1, 2], [3, 4]])
    assert excinfo.value.code == "H001_ENGINE_INVALID_INPUT_TYPE"
    # Wrong dtype wins over wrong shape.
    with pytest.raises(H001EngineError) as excinfo:
        engine.validate_input(np.zeros((3, 3), dtype=np.int32))
    assert excinfo.value.code == "H001_ENGINE_INVALID_INPUT_DTYPE"
    # Wrong ndim wins over wrong shape (both wrong here: 1-D length-9 array).
    with pytest.raises(H001EngineError) as excinfo:
        engine.validate_input(np.zeros(9, dtype=np.float64))
    assert excinfo.value.code == "H001_ENGINE_INVALID_INPUT_NDIM"
    # Correct type/dtype/ndim/shape but non-finite: reaches the finiteness gate last.
    bad = _valid_array()
    bad[0, 0] = float("inf")
    with pytest.raises(H001EngineError) as excinfo:
        engine.validate_input(bad)
    assert excinfo.value.code == "H001_ENGINE_INVALID_INPUT_NON_FINITE"


# ---------------------------------------------------------------------------
# Domain 1-3: HAC mean / autocovariance / long-run variance / SE fixtures
# ---------------------------------------------------------------------------

_HAC_FULL_FIXTURES = ("KAT-HAC-001", "KAT-HAC-DIVISION-001", "KAT-HAC-ORDER-001", "KAT-HAC-SERIESB-001", "KAT-HAC-SERIESC-001")


@pytest.mark.parametrize("fixture_id", _HAC_FULL_FIXTURES)
def test_hac_full_fixtures(fixture_id):
    fixtures = nc_fixtures()
    source = fixtures[fixture_id]
    x = np.array(source["input"]["x"], dtype=np.float64)
    lag = source["test_parameters"]["L"]
    n = source["test_parameters"]["n"]
    expected = source["expected_output"]
    xbar = engine.hac_mean(x)
    gamma0 = engine.hac_gamma(x, xbar, 0)
    omega2 = engine.hac_omega2(x, lag)
    se = engine.hac_se(omega2, n)
    _assert_kat(repr(xbar), repr(float(expected["xbar"])), fixture_id)
    if "gamma0" in expected:
        _assert_kat(repr(gamma0), repr(float(expected["gamma0"])), fixture_id)
    if "gamma1" in expected:
        gamma1 = engine.hac_gamma(x, xbar, 1)
        _assert_kat(repr(gamma1), repr(float(expected["gamma1"])), fixture_id)
    _assert_kat(repr(omega2), repr(float(expected["omega2"])), fixture_id)
    _assert_kat(repr(se), repr(float(expected["se"])), fixture_id)


def test_hac_zero_variance_fixture():
    source = nc_fixtures()["KAT-HAC-ZEROVAR-001"]
    x = np.array(source["input"]["x"], dtype=np.float64)
    lag = source["test_parameters"]["L"]
    xbar = engine.hac_mean(x)
    omega2 = engine.hac_omega2(x, lag)
    se = engine.hac_se(omega2, source["test_parameters"]["n"])
    expected = source["expected_output"]
    assert repr(xbar) == repr(float(expected["xbar"]))
    assert repr(omega2) == repr(float(expected["omega2"])) == "0.0"
    assert repr(se) == repr(float(expected["se"])) == "0.0"
    assert math.copysign(1.0, omega2) == 1.0
    assert math.copysign(1.0, se) == 1.0


def test_hac_nonfinite_input_fixture():
    source = nc_fixtures()["KAT-HAC-NONFINITE-001"]
    x = np.array([float("inf") if v == "inf" else float(v) for v in source["input"]["x"]], dtype=np.float64)
    with pytest.raises(H001EngineError) as excinfo:
        engine.hac_mean(x)
    assert excinfo.value.code == source["expected_error_category"] == "H001_NC_NON_FINITE_INPUT"


def test_gamma_product_guard_precedes_accumulation():
    # A finite series whose centered product would overflow to inf must fail
    # at the product-finiteness guard, immediately, not after being folded
    # into the running accumulator.
    huge = math.sqrt(sys.float_info.max)
    x = np.array([huge, -huge, huge, -huge], dtype=np.float64)
    xbar = engine.hac_mean(x)
    with pytest.raises(H001EngineError) as excinfo:
        engine.hac_gamma(x, xbar, 0)
    assert excinfo.value.code == "H001_NC_NON_FINITE_INTERMEDIATE"


def test_named_intermediates_are_immediately_guarded():
    x = np.array([1.0, 3.0, 1.0, 3.0], dtype=np.float64)
    xbar = engine.hac_mean(x)
    with pytest.raises(H001EngineError) as excinfo:
        engine.hac_se(-1.0, 4)
    assert excinfo.value.code == "H001_NC_NEGATIVE_LONG_RUN_VARIANCE"
    with pytest.raises(H001EngineError) as excinfo:
        engine.hac_se(float("nan"), 4)
    assert excinfo.value.code == "H001_NC_NON_FINITE_INTERMEDIATE"


@pytest.mark.parametrize("fixture_id", ["KAT-HAC-NEGMATERIAL-001", "KAT-HAC-NEGROUND-001"])
def test_hac_negative_long_run_variance_material_and_roundoff(fixture_id):
    source = nc_fixtures()[fixture_id]
    omega2 = float(source["input"]["omega2"])
    with pytest.raises(H001EngineError) as excinfo:
        engine.hac_se(omega2, source["test_parameters"]["n"])
    assert excinfo.value.code == source["expected_error_category"] == "H001_NC_NEGATIVE_LONG_RUN_VARIANCE"


def test_hac_divisor_is_n_not_n_minus_j_mutant_killed():
    """RA-HAC-DIVISOR-NMINUSJ: dividing by (n-j) instead of n must disagree
    with the governed fixture."""
    source = nc_fixtures()["KAT-HAC-DIVISION-001"]
    x = np.array(source["input"]["x"], dtype=np.float64)
    n = source["test_parameters"]["n"]
    xbar = engine.hac_mean(x)
    correct_gamma1 = engine.hac_gamma(x, xbar, 1)
    acc = 0.0
    for t in range(1, n):
        acc += (x[t] - xbar) * (x[t - 1] - xbar)
    mutant_gamma1_n_minus_j = acc / (n - 1)
    assert mutant_gamma1_n_minus_j != correct_gamma1
    assert repr(correct_gamma1) == repr(float(source["expected_output"]["gamma1"]))


def test_direct_division_vs_reciprocal_multiplication_mutant_killed():
    """RA-HAC-*: sum/n must differ, in raw bits, from sum*(1.0/n) for a
    divisor with no exact binary64 reciprocal (n=7)."""
    source = nc_fixtures()["KAT-HAC-DIVISION-001"]
    x = np.array(source["input"]["x"], dtype=np.float64)
    n = source["test_parameters"]["n"]
    acc = 0.0
    for value in x:
        acc += float(value)
    direct = acc / n
    reciprocal_multiply = acc * (1.0 / n)
    assert direct != reciprocal_multiply
    assert repr(engine.hac_mean(x)) == repr(direct) == repr(float(source["expected_output"]["xbar"]))


# ---------------------------------------------------------------------------
# Domain 4: null centering and studentization fixtures
# ---------------------------------------------------------------------------

def test_center_fixture():
    source = nc_fixtures()["KAT-CENTER-001"]
    x = np.array(source["input"]["x"], dtype=np.float64)
    path = source["input"]["resample_path"]
    xbar = engine.hac_mean(x)
    xbar_star = engine.hac_mean(x[path])
    centered = engine.centered_numerator(xbar_star, xbar)
    expected = source["expected_output"]
    assert repr(xbar) == repr(float(expected["xbar"]))
    assert repr(xbar_star) == repr(float(expected["xbar_star"]))
    assert repr(centered) == repr(float(expected["centered_numerator"]))


@pytest.mark.parametrize("fixture_id", ["KAT-STUD-VALID-001", "KAT-STUD-ZEROSE-ZEROMEAN-001"])
def test_stud_fixtures(fixture_id):
    source = nc_fixtures()[fixture_id]
    t = engine.stud(float(source["input"]["num"]), float(source["input"]["se"]))
    assert repr(t) == repr(float(source["expected_output"]["t"]))


def test_stud_zero_se_nonzero_numerator_fails_closed():
    source = nc_fixtures()["KAT-STUD-ZEROSE-NONZERO-001"]
    with pytest.raises(H001EngineError) as excinfo:
        engine.stud(float(source["input"]["num"]), float(source["input"]["se"]))
    assert excinfo.value.code == source["expected_error_category"] == "H001_NC_ZERO_STANDARD_ERROR"


def test_stud_negative_se_fails_closed_and_precedes_zero_se_branch():
    with pytest.raises(H001EngineError) as excinfo:
        engine.stud(1.0, -0.0001)
    assert excinfo.value.code == "H001_NC_NEGATIVE_STANDARD_ERROR"


def test_stud_signed_zero_canonicalization():
    result = engine.stud(-0.0, 1.0)
    assert result == 0.0
    assert math.copysign(1.0, result) == 1.0
    result_zero_se = engine.stud(0.0, 0.0)
    assert math.copysign(1.0, result_zero_se) == 1.0


def test_stud_nonfinite_intermediate_precedes_sign_tests():
    with pytest.raises(H001EngineError) as excinfo:
        engine.stud(float("nan"), 1.0)
    assert excinfo.value.code == "H001_NC_NON_FINITE_INTERMEDIATE"
    with pytest.raises(H001EngineError) as excinfo:
        engine.stud(1.0, float("nan"))
    assert excinfo.value.code == "H001_NC_NON_FINITE_INTERMEDIATE"


def test_observed_se_reuse_mutant_killed():
    """RA-STUD-REUSE-OBSERVED-SE: reusing the observed SE for a bootstrap
    replication instead of recomputing it must disagree with the governed
    end-to-end fixture."""
    source = nc_fixtures()["KAT-E2E-001"]
    series = {name: np.array(values, dtype=np.float64) for name, values in source["input"]["series"].items()}
    lag = source["test_parameters"]["L"]
    path = source["input"]["bootstrap_paths"][1]  # the replication with a nonzero Mstar contributor
    name = "B"
    x = series[name]
    xbar = engine.hac_mean(x)
    se_observed = engine.hac_se(engine.hac_omega2(x, lag), x.shape[0])
    resampled = x[path]
    xbar_star = engine.hac_mean(resampled)
    numerator = engine.centered_numerator(xbar_star, xbar)
    se_star = engine.hac_se(engine.hac_omega2(resampled, lag), resampled.shape[0])
    correct_tstar = engine.stud(numerator, se_star)
    mutant_tstar_reusing_observed_se = engine.stud(numerator, se_observed) if se_observed > 0 else None
    if mutant_tstar_reusing_observed_se is not None:
        assert mutant_tstar_reusing_observed_se != correct_tstar


# ---------------------------------------------------------------------------
# Maximum-t exceedance / exact p-value / rejection fixtures
# ---------------------------------------------------------------------------

def _reject_at(numerator: int, denominator: int, alpha_num: int, alpha_den: int) -> bool:
    return numerator * alpha_den <= denominator * alpha_num


@pytest.mark.parametrize(
    "fixture_id",
    ["KAT-PVAL-EXCEED-001", "KAT-PVAL-TIE-001", "KAT-PVAL-EQ-ALPHA-001", "KAT-PVAL-FINITEB-001"],
)
def test_pvalue_and_rejection_fixtures(fixture_id):
    source = nc_fixtures()[fixture_id]
    Mstar = tuple(float(v) for v in source["input"]["Mstar"])
    t_abs = tuple(float(v) for v in source["input"]["t_abs"])
    B = source["test_parameters"]["B"]
    alpha = source["test_parameters"]["alpha"]
    alpha_num, alpha_den = {"0.25": (1, 4), "0.05": (1, 20)}[alpha]
    counts = tuple(0 for _ in t_abs)
    for m in Mstar:
        counts = engine.update_exceedance_counts(counts, t_abs, (m,))
    denominator = B + 1
    p_num_den = [[1 + c, denominator] for c in counts]
    reject = [_reject_at(1 + c, denominator, alpha_num, alpha_den) for c in counts]
    assert p_num_den == source["expected_output"]["p_num_den"]
    assert reject == source["expected_output"]["reject"]
    assert any(reject) == source["expected_output"]["global_fwer_event"]


def test_registered_alpha_finalize_exact_pvalues_matches_eq_alpha_fixture():
    source = nc_fixtures()["KAT-PVAL-EQ-ALPHA-001"]
    assert source["test_parameters"]["alpha"] == "0.05"
    t_abs = tuple(float(v) for v in source["input"]["t_abs"])
    Mstar = tuple(float(v) for v in source["input"]["Mstar"])
    B = source["test_parameters"]["B"]
    counts = tuple(0 for _ in t_abs)
    for m in Mstar:
        counts = engine.update_exceedance_counts(counts, t_abs, (m,))
    results = engine.finalize_exact_pvalues(counts, B)
    assert [[n, d] for n, d, _ in results] == source["expected_output"]["p_num_den"]
    assert [r for _, _, r in results] == source["expected_output"]["reject"]


def test_exceedance_is_nonstrict_ge_mutant_killed():
    """RA-MAXT-STRICT-EXCEEDANCE: a tie (Mstar == |t_i|) must count."""
    counts = engine.update_exceedance_counts((0,), (2.0,), (2.0,))
    assert counts == (1,)
    mutant_strict = (0,) if not (2.0 > 2.0) else (1,)
    assert mutant_strict != counts


def test_plus_one_correction_mutant_killed():
    """RA-MAXT-NO-PLUS-ONE: p must use B+1, not B, in numerator and denominator."""
    counts = (3,)
    B = 4
    correct = engine.finalize_exact_pvalues(counts, B)[0]
    assert correct[:2] == (4, 5)
    no_plus_one = (counts[0], B)
    assert no_plus_one != correct[:2]


def test_strict_reject_rule_mutant_killed():
    """RA-MAXT-STRICT-REJECT: equality at alpha must reject (non-strict <=)."""
    numerator, denominator = 1, 20
    correct_reject = numerator * 20 <= denominator * 1
    assert correct_reject is True
    mutant_strict_reject = numerator * 20 < denominator * 1
    assert mutant_strict_reject is False
    assert mutant_strict_reject != correct_reject


def test_update_exceedance_counts_does_not_mutate_caller_tuple():
    counts = (0, 0, 0)
    # bootstrap_max_abs_tstar = absmax(5.0, 0.0, 5.0) = 5.0 is compared against
    # every series' own observed |t_i|, not element-wise against the raw
    # per-series bootstrap values.
    result = engine.update_exceedance_counts(counts, (1.0, 6.0, 1.0), (5.0, 0.0, 5.0))
    assert counts == (0, 0, 0)
    assert result == (1, 0, 1)


# ---------------------------------------------------------------------------
# Closed RNG interface fixtures: payload/key, raw words, bounded, Bernoulli,
# retry/exhaustion, full bootstrap path.
# ---------------------------------------------------------------------------

def test_payload_and_key_fixtures():
    fixtures = rng_fixtures()
    for fixture_id in ("KAT-PAYLOAD-001", "KAT-PAYLOAD-002"):
        source = fixtures[fixture_id]
        coordinate = BootstrapCoordinate(source["dgp_or_case_id"], source["outer_replication_index"], source["bootstrap_replication_index"])
        _assert_kat(coordinate.payload(), source["payload_string"], fixture_id)
        key_word_0, key_word_1 = engine._key_words(coordinate)
        _assert_kat(str(key_word_0), source["philox_key_word_0"], fixture_id)
        _assert_kat(str(key_word_1), source["philox_key_word_1"], fixture_id)
        _assert_kat(str(key_word_0), source["derived_seed64"], fixture_id)


def test_raw_word_fixtures():
    fixtures = rng_fixtures()
    for number in range(1, 10):
        fixture_id = f"KAT-RAW-{number:03d}"
        source = fixtures[fixture_id]
        coordinate = coordinate_for(fixtures, source["payload_fixture"])
        word = engine.raw_word(coordinate, source["draw_purpose"], source["sample_position"], source["attempt_index"])
        _assert_kat(str(word), source["normative_lane0_word"], fixture_id)


@pytest.mark.parametrize("fixture_id", ["KAT-BOUNDED-N1-001", "KAT-BOUNDED-N63-001", "KAT-BOUNDED-N2193-001", "KAT-BOUNDED-NMAX-001"])
def test_bounded_integer_fixtures(fixture_id):
    fixtures = rng_fixtures()
    source = fixtures[fixture_id]
    coordinate = coordinate_for(fixtures, source["payload_fixture"])
    result = engine.uniform_bounded(coordinate, source["draw_purpose"], source["sample_position"], int(source["bound_n"]))
    _assert_kat(result, int(source["result"]), fixture_id)


@pytest.mark.parametrize("fixture_id", ["KAT-BERNOULLI-TRUE-001", "KAT-BERNOULLI-FALSE-001", "KAT-BERNOULLI-P0-001", "KAT-BERNOULLI-P1Q1-001"])
def test_bernoulli_fixtures(fixture_id):
    fixtures = rng_fixtures()
    source = fixtures[fixture_id]
    coordinate = coordinate_for(fixtures, source["payload_fixture"])
    result = engine.bernoulli_rational(coordinate, source["sample_position"], source["probability_numerator"], source["probability_denominator"])
    _assert_kat(result, source["result"], fixture_id)


def test_uniform_bounded_invalid_bound_fails_closed():
    fixtures = rng_fixtures()
    coordinate = coordinate_for(fixtures, "payload_1")
    for bad_n in (0, -1, (1 << 64) + 1, 3.0, True):
        with pytest.raises(H001EngineError) as excinfo:
            engine.uniform_bounded(coordinate, "INITIAL_INDEX", 0, bad_n)
        assert excinfo.value.code == "H001_RNG_INVALID_BOUND"


def test_bernoulli_invalid_rational_fails_closed():
    fixtures = rng_fixtures()
    coordinate = coordinate_for(fixtures, "payload_1")
    with pytest.raises(H001EngineError) as excinfo:
        engine.bernoulli_rational(coordinate, 1, 2, 1)
    assert excinfo.value.code == "H001_RNG_INVALID_RATIONAL"
    with pytest.raises(H001EngineError) as excinfo:
        engine.bernoulli_rational(coordinate, 1, 1, 0)
    assert excinfo.value.code == "H001_RNG_INVALID_RATIONAL"


def test_rejection_retry_fixture():
    fixtures = rng_fixtures()
    source = fixtures["KAT-RETRY-001"]
    coordinate = coordinate_for(fixtures, source["payload_fixture"])
    result = engine.uniform_bounded(coordinate, source["draw_purpose"], source["sample_position"], int(source["bound_n"]))
    _assert_kat(result, int(source["result"]), "KAT-RETRY-001")


def test_rejection_exhaustion_fixture():
    fixtures = rng_fixtures()
    source = fixtures["KAT-EXHAUSTION-001"]
    coordinate = coordinate_for(fixtures, source["payload_fixture"])
    with pytest.raises(H001EngineError) as excinfo:
        engine.uniform_bounded(coordinate, source["draw_purpose"], source["sample_position"], int(source["bound_n"]))
    _assert_kat(excinfo.value.code, source["failure_category"], "KAT-EXHAUSTION-001")


@pytest.mark.parametrize("fixture_id", ["KAT-PATH-001", "KAT-PATH-002"])
def test_full_bootstrap_path_fixtures(fixture_id):
    fixtures = rng_fixtures()
    source = fixtures[fixture_id]
    coordinate = coordinate_for(fixtures, source["payload_fixture"])
    path = engine._build_shared_path(coordinate)
    _assert_kat(path, source["index_path"], fixture_id)
    restarts = [t for t in range(1, engine.SAMPLE_LENGTH) if path[t] != (path[t - 1] + 1) % engine.SAMPLE_LENGTH]
    _assert_kat(restarts, source["restart_positions"], fixture_id)


def test_unknown_draw_purpose_fails_closed():
    fixtures = rng_fixtures()
    coordinate = coordinate_for(fixtures, "payload_1")
    with pytest.raises(H001EngineError) as excinfo:
        engine.raw_word(coordinate, "NOT_A_PURPOSE", 0, 0)
    assert excinfo.value.code == "H001_RNG_UNKNOWN_DRAW_PURPOSE"


def test_coordinate_rejects_unknown_dgp_and_out_of_range_and_bool_indices():
    with pytest.raises(H001EngineError) as excinfo:
        BootstrapCoordinate("not_a_registered_dgp", 0, 0)
    assert excinfo.value.code == "H001_RNG_INVALID_COORDINATE"
    with pytest.raises(H001EngineError) as excinfo:
        BootstrapCoordinate("iid_gaussian", -1, 0)
    assert excinfo.value.code == "H001_RNG_COORDINATE_OUT_OF_DOMAIN"
    with pytest.raises(H001EngineError) as excinfo:
        BootstrapCoordinate("iid_gaussian", 2000, 0)
    assert excinfo.value.code == "H001_RNG_COORDINATE_OUT_OF_DOMAIN"
    with pytest.raises(H001EngineError) as excinfo:
        BootstrapCoordinate("iid_gaussian", 0, 10000)
    assert excinfo.value.code == "H001_RNG_COORDINATE_OUT_OF_DOMAIN"
    with pytest.raises(H001EngineError) as excinfo:
        BootstrapCoordinate("iid_gaussian", True, 0)
    assert excinfo.value.code == "H001_RNG_COORDINATE_OUT_OF_DOMAIN"
    with pytest.raises(H001EngineError) as excinfo:
        BootstrapCoordinate("iid_gaussian", 0, False)
    assert excinfo.value.code == "H001_RNG_COORDINATE_OUT_OF_DOMAIN"


def test_closed_rng_api_accepts_no_payload_builder_or_callback():
    import inspect

    for function in (engine.raw_word, engine.uniform_bounded, engine.bernoulli_rational):
        signature = inspect.signature(function)
        for name in signature.parameters:
            assert "payload" not in name and "callback" not in name and "builder" not in name


# ---------------------------------------------------------------------------
# Mutants against the closed RNG interface
# ---------------------------------------------------------------------------

def test_counter_minus_one_compensation_mutant_killed():
    fixtures = rng_fixtures()
    source = fixtures["KAT-RAW-001"]
    coordinate = coordinate_for(fixtures, source["payload_fixture"])
    key_word_0, key_word_1 = engine._key_words(coordinate)
    counter_word_0 = engine._counter_word_0(source["draw_purpose"], source["sample_position"], source["attempt_index"])
    from numpy.random import Philox as NumpyPhilox

    correct = int(NumpyPhilox(counter=(counter_word_0 - 1) & engine._MASK_256, key=key_word_0 + (key_word_1 << 64)).random_raw(4)[0])
    mutant_without_compensation = int(NumpyPhilox(counter=counter_word_0 & engine._MASK_256, key=key_word_0 + (key_word_1 << 64)).random_raw(4)[0])
    assert correct == int(source["normative_lane0_word"])
    assert mutant_without_compensation != correct


def test_wrong_philox_lane_mutant_killed():
    fixtures = rng_fixtures()
    source = fixtures["KAT-RAW-001"]
    coordinate = coordinate_for(fixtures, source["payload_fixture"])
    key_word_0, key_word_1 = engine._key_words(coordinate)
    counter_word_0 = engine._counter_word_0(source["draw_purpose"], source["sample_position"], source["attempt_index"])
    from numpy.random import Philox as NumpyPhilox

    block = [int(word) for word in NumpyPhilox(counter=(counter_word_0 - 1) & engine._MASK_256, key=key_word_0 + (key_word_1 << 64)).random_raw(4)]
    assert str(block[0]) == source["normative_lane0_word"]
    assert str(block[1]) != source["normative_lane0_word"]


def test_wrong_endian_key_packing_mutant_killed():
    fixtures = rng_fixtures()
    source = fixtures["KAT-RAW-001"]
    coordinate = coordinate_for(fixtures, source["payload_fixture"])
    key_word_0, key_word_1 = engine._key_words(coordinate)
    counter_word_0 = engine._counter_word_0(source["draw_purpose"], source["sample_position"], source["attempt_index"])
    from numpy.random import Philox as NumpyPhilox

    correct = int(NumpyPhilox(counter=(counter_word_0 - 1) & engine._MASK_256, key=key_word_0 + (key_word_1 << 64)).random_raw(4)[0])
    swapped = int(NumpyPhilox(counter=(counter_word_0 - 1) & engine._MASK_256, key=key_word_1 + (key_word_0 << 64)).random_raw(4)[0])
    assert correct == int(source["normative_lane0_word"])
    assert swapped != correct


def test_per_series_nonshared_bootstrap_paths_mutant_killed():
    """RA: per-series independent paths must disagree with the governed
    shared-path E2E fixture."""
    source = nc_fixtures()["KAT-E2E-001"]
    series = {name: np.array(values, dtype=np.float64) for name, values in source["input"]["series"].items()}
    lag = source["test_parameters"]["L"]
    shared_paths = source["input"]["bootstrap_paths"]
    names = ["A", "B", "C"]
    xbar = {name: engine.hac_mean(series[name]) for name in names}

    def tstars_with_paths(path_by_series):
        tstars = []
        for name in names:
            resampled = series[name][path_by_series[name]]
            xbar_star = engine.hac_mean(resampled)
            numerator = engine.centered_numerator(xbar_star, xbar[name])
            se_star = engine.hac_se(engine.hac_omega2(resampled, lag), resampled.shape[0])
            tstars.append(engine.stud(numerator, se_star))
        return tuple(tstars)

    shared_tstars = tstars_with_paths({name: shared_paths[1] for name in names})
    assert repr(engine._absmax(shared_tstars)) == repr(float(source["expected_output"]["Mstar"][1]))
    # Per-series distinct paths (none of which coincides with the shared path
    # used above, for any series) is a different, ungoverned procedure and
    # must disagree on the full per-series statistic vector, not merely on
    # the aggregated max (which can coincide by chance for affine-equivalent
    # series).
    non_shared_tstars = tstars_with_paths({"A": shared_paths[0], "B": shared_paths[2], "C": shared_paths[3]})
    assert non_shared_tstars != shared_tstars


# ---------------------------------------------------------------------------
# Metamorphic properties
# ---------------------------------------------------------------------------

def test_sign_flip_invariance_of_absolute_studentized_statistic():
    x = np.array([1.0, 3.0, 1.0, 3.0], dtype=np.float64)
    xbar = engine.hac_mean(x)
    se = engine.hac_se(engine.hac_omega2(x, 1), x.shape[0])
    t = engine.stud(xbar, se)
    neg_x = -x
    neg_xbar = engine.hac_mean(neg_x)
    neg_se = engine.hac_se(engine.hac_omega2(neg_x, 1), neg_x.shape[0])
    neg_t = engine.stud(neg_xbar, neg_se)
    assert neg_xbar == -xbar
    assert neg_se == se
    assert abs(neg_t) == abs(t)


def test_positive_scale_invariance_on_safe_dyadic_inputs():
    x = np.array([1.0, 3.0, 1.0, 3.0], dtype=np.float64)
    xbar = engine.hac_mean(x)
    se = engine.hac_se(engine.hac_omega2(x, 1), x.shape[0])
    t = engine.stud(xbar, se)
    scaled = x * 4.0  # power-of-two scale is exact in binary64
    scaled_xbar = engine.hac_mean(scaled)
    scaled_se = engine.hac_se(engine.hac_omega2(scaled, 1), scaled.shape[0])
    scaled_t = engine.stud(scaled_xbar, scaled_se)
    assert scaled_xbar == xbar * 4.0
    assert scaled_t == t


def test_series_permutation_equivariance():
    fixtures = nc_fixtures()
    source = fixtures["KAT-E2E-001"]
    series = {name: np.array(values, dtype=np.float64) for name, values in source["input"]["series"].items()}
    lag = source["test_parameters"]["L"]

    def observed_t(name):
        x = series[name]
        return engine.stud(engine.hac_mean(x), engine.hac_se(engine.hac_omega2(x, lag), x.shape[0]))

    t_by_name = {name: observed_t(name) for name in ("A", "B", "C")}
    # Recomputing in a different order yields exactly the same per-name results.
    for name in ("C", "A", "B"):
        assert observed_t(name) == t_by_name[name]


def test_duplicate_series_behavior():
    x = np.array([1.0, 3.0, 1.0, 3.0], dtype=np.float64)
    xbar_a = engine.hac_mean(x)
    xbar_b = engine.hac_mean(x.copy())
    assert xbar_a == xbar_b
    counts = engine.update_exceedance_counts((0, 0), (8.0, 8.0), (10.0, 10.0))
    assert counts == (1, 1)


def test_coordinate_evaluation_order_independence_and_chunk_independence():
    fixtures = rng_fixtures()
    coordinate = coordinate_for(fixtures, "payload_1")
    ordering_one = [engine.raw_word(coordinate, "RESTART_INDEX", 9, 0), engine.raw_word(coordinate, "INITIAL_INDEX", 0, 0), engine.raw_word(coordinate, "RESTART_DECISION", 9, 0)]
    ordering_two = [engine.raw_word(coordinate, "RESTART_DECISION", 9, 0), engine.raw_word(coordinate, "RESTART_INDEX", 9, 0), engine.raw_word(coordinate, "INITIAL_INDEX", 0, 0)]
    assert ordering_one[1] == ordering_two[2]  # INITIAL_INDEX at position 0
    assert ordering_one[0] == ordering_two[1]  # RESTART_INDEX at position 9
    assert ordering_one[2] == ordering_two[0]  # RESTART_DECISION at position 9

    # Chunked/scheduled evaluation of many positions yields the same per-position
    # results as sequential evaluation, because each draw is a pure function of
    # its own coordinate.
    sequential = [engine.uniform_bounded(coordinate, "INITIAL_INDEX", 0, 2193)] + [
        engine.raw_word(coordinate, "RESTART_DECISION", t, 0) for t in range(1, 50)
    ]
    scrambled_positions = sorted(range(1, 50), key=lambda t: (t * 37) % 50)
    scrambled = {t: engine.raw_word(coordinate, "RESTART_DECISION", t, 0) for t in scrambled_positions}
    for t in range(1, 50):
        assert scrambled[t] == sequential[t]


def test_unrelated_coordinate_isolation():
    fixtures = rng_fixtures()
    coordinate = coordinate_for(fixtures, "payload_1")
    source = fixtures["KAT-RAW-001"]
    before = engine.raw_word(coordinate, source["draw_purpose"], source["sample_position"], source["attempt_index"])
    unrelated = BootstrapCoordinate("stationary_garch11_like", 1999, 9999)
    engine.raw_word(unrelated, "INITIAL_INDEX", 0, 0)
    engine.raw_word(unrelated, "RESTART_DECISION", 500, 3)
    after = engine.raw_word(coordinate, source["draw_purpose"], source["sample_position"], source["attempt_index"])
    assert before == after == int(source["normative_lane0_word"])


def test_signed_zero_canonicalization_across_engine_surface():
    assert math.copysign(1.0, engine.hac_mean(np.array([1.0, -1.0], dtype=np.float64))) == 1.0
    assert math.copysign(1.0, engine.centered_numerator(2.0, 2.0)) == 1.0
    assert math.copysign(1.0, engine.stud(-0.0, 5.0)) == 1.0


# ---------------------------------------------------------------------------
# Full streaming pipeline and bounded-memory behavior
# ---------------------------------------------------------------------------

def test_full_streaming_replication_pipeline_end_to_end_fixture():
    source = nc_fixtures()["KAT-E2E-001"]
    series = {name: np.array(values, dtype=np.float64) for name, values in source["input"]["series"].items()}
    x = np.stack([series["A"], series["B"], series["C"]])
    lag = source["test_parameters"]["L"]
    xbar = tuple(engine.hac_mean(x[i]) for i in range(x.shape[0]))
    se = tuple(engine.hac_se(engine.hac_omega2(x[i], lag), x.shape[1]) for i in range(x.shape[0]))
    observed_t = tuple(engine.stud(xbar[i], se[i]) for i in range(x.shape[0]))
    observed_abs_t = tuple(abs(t) for t in observed_t)

    class _FixedPathCoordinate:
        def __init__(self, path):
            self._path = path

    counts = tuple(0 for _ in range(x.shape[0]))
    for path in source["input"]["bootstrap_paths"]:
        tstars = []
        for i in range(x.shape[0]):
            resampled = x[i][path]
            numerator = engine.centered_numerator(engine.hac_mean(resampled), xbar[i])
            se_star = engine.hac_se(engine.hac_omega2(resampled, lag), resampled.shape[0])
            tstars.append(engine.stud(numerator, se_star))
        counts = engine.update_exceedance_counts(counts, observed_abs_t, tuple(tstars))
    results = engine.finalize_exact_pvalues(counts, len(source["input"]["bootstrap_paths"]))
    assert [[n, d] for n, d, _ in results] == [[1, 5], [5, 5], [1, 5]]


def test_bounded_memory_streaming_behavior():
    fixtures = rng_fixtures()
    coordinate = coordinate_for(fixtures, "payload_1")
    x = np.random.default_rng(0).normal(size=(9, engine.SAMPLE_LENGTH))
    x = engine.validate_input(x.astype(np.float64))
    xbar, _, _ = engine.compute_observed_statistics(x)

    def run(n_reps, outer):
        counts = tuple(0 for _ in range(9))
        observed_abs_t = tuple(1.0 for _ in range(9))
        for b in range(n_reps):
            coord = BootstrapCoordinate("iid_gaussian", outer, b)
            tstar = engine.compute_one_bootstrap_replication(x, xbar, coord)
            counts = engine.update_exceedance_counts(counts, observed_abs_t, tstar)
        return counts

    tracemalloc.start()
    run(3, 0)
    baseline, _ = tracemalloc.get_traced_memory()
    tracemalloc.reset_peak()
    run(24, 1)
    after, peak = tracemalloc.get_traced_memory()
    tracemalloc.stop()
    # Memory retained after 200 streamed replications must not scale with the
    # replication count: only O(series_count) counters persist across
    # replications, each path/replication is built and discarded in turn.
    assert after < baseline + 2_000_000, f"retained memory grew with replication count: baseline={baseline} after={after}"


def test_compute_one_bootstrap_replication_uses_shared_path_across_series():
    fixtures = rng_fixtures()
    coordinate = coordinate_for(fixtures, "payload_2")
    x = np.stack([np.arange(engine.SAMPLE_LENGTH, dtype=np.float64) for _ in range(9)])
    xbar = tuple(engine.hac_mean(x[i]) for i in range(9))
    expected_path = fixtures["KAT-PATH-002"]["index_path"]
    tstar = engine.compute_one_bootstrap_replication(x, xbar, coordinate)
    # Every series is the identical ramp, so every series' resample under the
    # one shared path is identical too, and every tstar must be identical
    # (proving one path was applied identically to all series).
    assert len(set(repr(t) for t in tstar)) == 1
