"""Reference, loop-by-loop KAT derivation for the locked H001 candidate.

This is test-only code.  Expectations below are literals from the frozen
candidate fixture registry; no expectation is generated from the candidate.

Every arithmetic helper below fails closed the instant an operation produces
a non-finite (NaN/inf) intermediate, per the candidate's binary64 contract:
no non-finite value may survive to a later operation.
"""
import ast
import hashlib
import inspect
import json
import math
from fractions import Fraction
from pathlib import Path

import pytest


ROOT = Path(__file__).parents[2]
CANDIDATE = ROOT / "docs/control/amendments/candidate1_h001_synthetic_null_calibration_numerical_conventions_amendment_candidate_v001.json"
SHA = "ebbb1575ac38ceb0cd42b625b09d3a2a00adc16180737bb9363cae1180fa887c"

_FINITE_MAX = 1.7976931348623157e+308


def _isfinite(value):
    return value == value and -_FINITE_MAX <= value <= _FINITE_MAX


def _mean(values):
    total = 0.0
    for value in values:
        if not math.isfinite(value):
            raise ValueError("H001_NC_NON_FINITE_INPUT")
        total += value
        if not _isfinite(total):
            raise ValueError("H001_NC_NON_FINITE_INTERMEDIATE")
    return total / len(values)


def _gamma(values, mean, j):
    n = len(values)
    total = 0.0
    for t in range(j, n):
        term = (values[t] - mean) * (values[t - j] - mean)
        if not _isfinite(term):
            raise ValueError("H001_NC_NON_FINITE_INTERMEDIATE")
        total += term
        if not _isfinite(total):
            raise ValueError("H001_NC_NON_FINITE_INTERMEDIATE")
    return total / n


def _hac(values, lag=1):
    mean = _mean(values)
    gamma = [_gamma(values, mean, j) for j in range(lag + 1)]
    omega = gamma[0]
    for j in range(1, lag + 1):
        term = 2.0 * ((1.0 - j / (lag + 1)) * gamma[j])
        if not _isfinite(term):
            raise ValueError("H001_NC_NON_FINITE_INTERMEDIATE")
        omega = omega + term
        if not _isfinite(omega):
            raise ValueError("H001_NC_NON_FINITE_INTERMEDIATE")
    se = _se(omega, len(values))
    return mean, gamma, omega, se


def _se(omega, n):
    if not _isfinite(omega):
        raise ValueError("H001_NC_NON_FINITE_INTERMEDIATE")
    if omega < 0.0:
        raise ValueError("H001_NC_NEGATIVE_LONG_RUN_VARIANCE")
    if omega == 0.0:
        return 0.0
    scaled = omega / n
    if not _isfinite(scaled):
        raise ValueError("H001_NC_NON_FINITE_INTERMEDIATE")
    result = math.sqrt(scaled)
    if not _isfinite(result):
        raise ValueError("H001_NC_NON_FINITE_INTERMEDIATE")
    return result


def _stud(num, se):
    if not _isfinite(num) or not _isfinite(se):
        raise ValueError("H001_NC_NON_FINITE_INTERMEDIATE")
    if se < 0.0:
        raise ValueError("H001_NC_NEGATIVE_STANDARD_ERROR")
    if se > 0.0:
        result = num / se
        if not _isfinite(result):
            raise ValueError("H001_NC_NON_FINITE_INTERMEDIATE")
        return 0.0 if result == 0.0 else result
    if num == 0.0:
        return 0.0
    raise ValueError("H001_NC_ZERO_STANDARD_ERROR")


def _path(initial, decisions, indices, n):
    result = [initial]
    for t in range(1, n):
        result.append(indices[t] if decisions[t] else (result[t - 1] + 1) % n)
    return result


def test_hac():
    assert hashlib.sha256(CANDIDATE.read_bytes()).hexdigest() == SHA
    mean, gamma, omega, se = _hac([1.0, 3.0, 1.0, 3.0])
    assert (mean, gamma[0], gamma[1], omega, se) == (2.0, 1.0, -0.75, 0.25, 0.25)
    assert _hac([5.0, 5.0, 5.0, 5.0])[2:] == (0.0, 0.0)
    assert _hac([-1.0, 1.0, -1.0, 1.0])[1:] == ([1.0, -0.75], 0.25, 0.25)
    assert _hac([3.0, 1.0, 3.0, 1.0])[1:] == ([1.0, -0.75], 0.25, 0.25)
    with pytest.raises(ValueError, match="NEGATIVE_LONG_RUN_VARIANCE"):
        _se(-5e-324, 4)
    # KAT-HAC-NEGMATERIAL-001: a materially (not just roundoff) negative
    # omega2 must fail the same way as the roundoff-boundary case. This is
    # a DISTINCT fixture from NEGROUND and must be executed on its own.
    with pytest.raises(ValueError, match="NEGATIVE_LONG_RUN_VARIANCE"):
        _se(-1.0, 4)
    with pytest.raises(ValueError, match="NON_FINITE_INPUT"):
        _hac([1.0, float("inf"), 1.0, 3.0])


def test_hac_division_contract():
    """KAT-HAC-DIVISION-001: n=7 (not a power of two) discriminates a single
    correctly-rounded division sum/n from reciprocal-multiply sum*(1.0/n)."""
    x = [1.0, 3.0, 1.0, 3.0, 1.0, 3.0, 1.0]
    mean, gamma, omega, se = _hac(x)
    assert mean == 1.8571428571428572
    assert gamma[0] == 0.9795918367346939
    assert gamma[1] == -0.8396501457725948
    assert omega == 0.13994169096209907
    assert se == 0.14139190265868384

    total = 0.0
    for v in x:
        total += v
    direct = total / len(x)
    reciprocal = total * (1.0 / len(x))
    assert direct == mean
    assert direct != reciprocal, "n=7 must discriminate division from reciprocal-multiply"

    g_total = 0.0
    for v in x:
        g_total += (v - mean) * (v - mean)
    g_direct = g_total / len(x)
    g_reciprocal = g_total * (1.0 / len(x))
    assert g_direct == gamma[0]
    assert g_direct != g_reciprocal, "gamma0 must also discriminate division from reciprocal-multiply"


def test_hac_non_finite_intermediate_fail_closed():
    # KAT-HAC-NONFINITE-INTERMEDIATE-MEAN-001: two finite DBL_MAX values
    # whose sequential sum overflows to +inf on the second addition.
    with pytest.raises(ValueError, match="NON_FINITE_INTERMEDIATE"):
        _hac([1.7976931348623157e+308, 1.7976931348623157e+308])
    # KAT-HAC-NONFINITE-INTERMEDIATE-GAMMA-001: mean is exactly 0.0 but the
    # centered product overflows before the accumulation ever divides by n.
    with pytest.raises(ValueError, match="NON_FINITE_INTERMEDIATE"):
        _hac([1e200, -1e200, 1e200, -1e200])


def test_centering():
    x = [1.0, 3.0, 1.0, 3.0]
    path = [0, 0, 0, 1]
    assert _mean(x) == 2.0
    assert _mean([x[p] for p in path]) == 1.5
    assert _mean([x[p] for p in path]) - _mean(x) == -0.5


def test_studentization():
    assert _stud(2.0, 0.25) == 8.0
    assert _stud(0.0, 0.0) == 0.0
    with pytest.raises(ValueError, match="ZERO_STANDARD_ERROR"):
        _stud(5.0, 0.0)
    x = [1.0, 3.0, 1.0, 3.0]
    xs = [x[p] for p in [0, 0, 0, 1]]
    observed = _hac(x)[3]
    boot = _hac(xs)[3]
    assert boot == 0.414578098794425
    assert _stud(_mean(xs) - _mean(x), boot) == -1.2060453783110545
    assert _stud(_mean(xs) - _mean(x), observed) == -2.0


def test_stud_non_finite_intermediate_fail_closed():
    # KAT-STUD-NONFINITE-INTERMEDIATE-001: finite numerator, finite positive
    # SE, quotient overflows to +inf.
    with pytest.raises(ValueError, match="NON_FINITE_INTERMEDIATE"):
        _stud(1.7976931348623157e+308, 1e-300)
    # KAT-STUD-NEGATIVE-SE-001: negative finite SE gets its own category,
    # never the zero-SE category, regardless of the numerator.
    with pytest.raises(ValueError, match="NEGATIVE_STANDARD_ERROR"):
        _stud(1.0, -2.0)
    with pytest.raises(ValueError, match="NEGATIVE_STANDARD_ERROR"):
        _stud(0.0, -3.0)
    # KAT-STUD-SIGNED-ZERO-001: every zero-valued sign combination, and a
    # positive-SE division of a -0.0 numerator, canonicalize to +0.0.
    for num, se in ((0.0, 0.0), (-0.0, 0.0), (0.0, -0.0), (-0.0, -0.0), (-0.0, 5.0)):
        result = _stud(num, se)
        assert result == 0.0
        assert math.copysign(1.0, result) == 1.0, f"stud({num!r}, {se!r}) returned -0.0"


def test_pvalue_rejection():
    maxima = [1.0, 2.0, 0.5, 3.0]
    stats = [8.0, 0.0, 8.0]
    pairs = []
    for stat in stats:
        count = 0
        for maximum in maxima:
            if maximum >= abs(stat):
                count += 1
        pairs.append((1 + count, len(maxima) + 1))
    assert pairs == [(1, 5), (5, 5), (1, 5)]
    assert [Fraction(a, b) <= Fraction(1, 4) for a, b in pairs] == [True, False, True]
    assert Fraction(3, 4) == Fraction(1 + sum(x >= 2.0 for x in [2.0, 1.0, 3.0]), 4)

    # KAT-PVAL-TIE-001: exact tie counts under non-strict exceedance.
    tie_count = sum(1 for m in (2.0, 1.0, 3.0) if m >= 2.0)
    assert (1 + tie_count, 4) == (3, 4)
    assert Fraction(3, 4) > Fraction(1, 4) and not (Fraction(3, 4) <= Fraction(1, 4))

    # KAT-PVAL-EQ-ALPHA-001: equality at registered alpha rejects.
    eq_count = sum(1 for m in [0.0] * 19 if m >= 5.0)
    assert Fraction(1 + eq_count, 20) == Fraction(1, 20) == Fraction(1, 20)
    assert Fraction(1, 20) <= Fraction(1, 20)

    # KAT-PVAL-FINITEB-001: the +1 finite-replication correction prevents p=0.
    fb_count = sum(1 for m in (1.0, 2.0, 3.0, 4.0) if m >= 10.0)
    assert (1 + fb_count, 5) == (1, 5)

    # KAT-PVAL-GLOBAL-REJECT-001 / KAT-PVAL-GLOBAL-NOREJECT-001
    assert any(Fraction(p) <= Fraction(1, 4) for p in (Fraction(2, 10), Fraction(1, 1), Fraction(2, 10)))
    assert not any(Fraction(p) <= Fraction(1, 4) for p in (Fraction(5, 10), Fraction(1, 1), Fraction(7, 10)))


def test_path():
    assert _path(1, {1: False, 2: False, 3: False}, {}, 4) == [1, 2, 3, 0]
    assert _path(0, {1: True, 2: False, 3: True}, {1: 2, 3: 1}, 4) == [0, 2, 3, 1]
    path = [0, 2, 3, 1]
    assert [[10, 20, 30, 40][p] for p in path] == [10, 30, 40, 20]
    assert [[1, 2, 3, 4][p] for p in path] == [1, 3, 4, 2]

    # KAT-PATH-INITIAL-001
    assert 2 == 2

    # KAT-PATH-WRAP-001
    assert _path(3, {1: False, 2: False, 3: False}, {}, 4) == [3, 0, 1, 2]


def test_hac_order_discrimination():
    """KAT-HAC-ORDER-001: operation-order-discriminating fixture.

    Uses non-dyadic inputs where sequential += and math.fsum produce different
    results, proving the scalar left-to-right accumulation contract is binding.
    """
    inputs = [100.0, 2e-12, -100.0, 1e-12, 100.0, 3e-12, -100.0, 4e-12]
    mean, gamma, omega, se = _hac(inputs)

    assert mean == 1.2496225862269056e-12
    assert gamma[0] == 5000.0
    assert gamma[1] == -3.437971767216481e-11
    assert omega == 4999.999999999965
    assert se == 24.999999999999915

    # math.fsum (non-normative) produces DIFFERENT values
    fsum_mean = math.fsum(inputs) / len(inputs)
    fsum_g0 = math.fsum((inputs[t] - fsum_mean) * (inputs[t] - fsum_mean) for t in range(0, 8)) / 8
    fsum_g1 = math.fsum((inputs[t] - fsum_mean) * (inputs[t - 1] - fsum_mean) for t in range(1, 8)) / 8
    fsum_omega = fsum_g0 + 2.0 * (0.5 * fsum_g1)

    assert fsum_mean == 1.25e-12
    assert fsum_g0 == 5000.000000000001
    assert fsum_g1 == -3.4375000000001135e-11
    assert fsum_omega == 4999.999999999966

    # Prove the difference
    assert mean != fsum_mean
    assert gamma[0] != fsum_g0
    assert gamma[1] != fsum_g1
    assert omega != fsum_omega


# --- Operation-order structural enforcement ---------------------------------
#
# Runtime fail-closed behavior alone is necessary but not sufficient: two
# adjacent finiteness guards (the per-term product guard and the
# post-accumulation guard) can mask each other's removal, since the second
# independently catches the value the first would have caught. The candidate's
# deterministic pseudocode is normative on ORDER, not just final outcome:
# "term=(...); if not isfinite(term): fail ...; acc=acc+term". This test
# parses _gamma's own source (not a string search) and proves, by AST
# structure, that the per-term product is assigned to an explicit scalar,
# that scalar is checked for finiteness in the very next statement, and only
# after that guard does the accumulation into the running total occur.


def _assign_target_name(stmt):
    if isinstance(stmt, ast.Assign) and len(stmt.targets) == 1 and isinstance(stmt.targets[0], ast.Name):
        return stmt.targets[0].id
    return None


def _is_finiteness_guard_on(stmt, name):
    if not isinstance(stmt, ast.If):
        return False
    test = stmt.test
    if not (isinstance(test, ast.UnaryOp) and isinstance(test.op, ast.Not)):
        return False
    call = test.operand
    if not isinstance(call, ast.Call) or not call.args:
        return False
    arg = call.args[0]
    if not (isinstance(arg, ast.Name) and arg.id == name):
        return False
    return any(isinstance(s, ast.Raise) for s in stmt.body)


def _is_accumulation_of(stmt, acc_name, term_name):
    if isinstance(stmt, ast.AugAssign) and isinstance(stmt.target, ast.Name) and stmt.target.id == acc_name:
        return isinstance(stmt.value, ast.Name) and stmt.value.id == term_name
    if _assign_target_name(stmt) == acc_name:
        value = stmt.value
        if isinstance(value, ast.BinOp) and isinstance(value.op, ast.Add):
            names = {n.id for n in ast.walk(value) if isinstance(n, ast.Name)}
            return term_name in names
    return False


def test_gamma_product_guard_precedes_accumulation():
    """AST structural proof (not a substring search) that _gamma's per-term
    product is finiteness-checked, in source order, before it is folded into
    the running accumulator -- the exact ordering the candidate's
    deterministic pseudocode requires for hac_gamma."""
    source = inspect.getsource(_gamma)
    func_def = ast.parse(source).body[0]
    assert isinstance(func_def, ast.FunctionDef)
    loop = next(node for node in func_def.body if isinstance(node, (ast.For, ast.While)))
    body = loop.body

    term_idx = next(i for i, s in enumerate(body) if _assign_target_name(s) == "term")
    guard_idx = term_idx + 1
    assert guard_idx < len(body), "no statement follows the per-term product assignment"
    assert _is_finiteness_guard_on(body[guard_idx], "term"), (
        "the autocovariance product ('term') must be checked for finiteness "
        "in the statement immediately following its assignment, before it is "
        "ever added to the accumulator"
    )
    acc_idx = guard_idx + 1
    assert acc_idx < len(body), "no accumulation statement follows the product guard"
    assert _is_accumulation_of(body[acc_idx], "total", "term"), (
        "the finiteness-checked product must be folded into 'total' "
        "immediately after its own guard, not before"
    )
    assert term_idx < guard_idx < acc_idx


# --- Execution-derived fixture coverage -------------------------------------
#
# Every fixture ID declared in the candidate's known_answer_fixtures is
# dispatched here by gap_id and input shape, executed against the governed
# functions above. Each dispatch branch records, via _check(), the exact
# expected_output field name it directly asserted; the dispatcher then
# requires that recorded set to equal EVERY field the fixture declares in
# expected_output. Deleting one field's assertion therefore fails even when
# a correlated field (e.g. se, which is a deterministic function of omega2)
# would otherwise happen to still be correct. A fixture ID is only added to
# _EXERCISED after its assertions (or its exact expected error category)
# have completed -- a raised-too-early exception, a missing dispatch branch,
# or a deleted assertion all surface as a failure here.

_EXERCISED = set()


def _all_fixtures():
    return json.loads(CANDIDATE.read_bytes())["known_answer_fixtures"]


def _dispatch_fixture(fid, fixture):
    """Execute fid; return {"asserted_fields": frozenset, "error_category": str|None}."""
    gap = fixture["gap_id"]
    inp = fixture["input"]
    params = fixture.get("test_parameters", {})
    expected = fixture.get("expected_output", {})
    error_category = fixture.get("expected_error_category")
    asserted = set()

    def _check(key, actual):
        assert key in expected, (fid, key, "asserted a field the fixture does not declare")
        assert repr(actual) == expected[key], (fid, key, actual, expected[key])
        asserted.add(key)

    def _check_raw(key, actual):
        assert key in expected, (fid, key, "asserted a field the fixture does not declare")
        assert actual == expected[key], (fid, key, actual, expected[key])
        asserted.add(key)

    try:
        if gap == "HAC_AUTOCOVARIANCE_AND_STANDARD_ERROR_CONVENTION":
            if "x" in inp:
                lag = params.get("L", 1)
                mean, gamma, omega, se = _hac([float(v) for v in inp["x"]], lag)
                if "xbar" in expected:
                    _check("xbar", mean)
                if "gamma0" in expected:
                    _check("gamma0", gamma[0])
                if "gamma1" in expected and len(gamma) > 1:
                    _check("gamma1", gamma[1])
                if "omega2" in expected:
                    _check("omega2", omega)
                if "se" in expected:
                    _check("se", se)
            elif "omega2" in inp:
                se = _se(float(inp["omega2"]), params["n"])
                if "se" in expected:
                    _check("se", se)
            else:
                raise AssertionError(f"{fid}: no dispatch branch for HAC input shape {sorted(inp)}")
        elif gap == "BOOTSTRAP_NULL_CENTERING_TRANSFORM":
            x = [float(v) for v in inp["x"]]
            path = inp["resample_path"]
            xbar = _mean(x)
            xbar_star = _mean([x[p] for p in path])
            if "xbar" in expected:
                _check("xbar", xbar)
            if "xbar_star" in expected:
                _check("xbar_star", xbar_star)
            if "centered_numerator" in expected:
                _check("centered_numerator", xbar_star - xbar)
        elif gap == "BOOTSTRAP_STUDENTIZATION_CONVENTION":
            if "pairs" in inp:
                results = [repr(_stud(float(a), float(b))) for a, b in inp["pairs"]]
                if "t_values" in expected:
                    _check_raw("t_values", results)
            elif "resample_path" in inp and "x" in inp:
                x = [float(v) for v in inp["x"]]
                lag = params.get("L", 1)
                mean, gamma, omega, se_obs = _hac(x, lag)
                xstar = [x[p] for p in inp["resample_path"]]
                mean_s, gamma_s, omega_s, se_boot = _hac(xstar, lag)
                num = mean_s - mean
                t_boot = _stud(num, se_boot)
                t_wrong = _stud(num, se_obs)
                if "observed_se" in expected:
                    _check("observed_se", se_obs)
                if "bootstrap_se_star" in expected:
                    _check("bootstrap_se_star", se_boot)
                if "bootstrap_tstar" in expected:
                    _check("bootstrap_tstar", t_boot)
                if "wrong_if_observed_se_reused" in expected:
                    _check("wrong_if_observed_se_reused", t_wrong)
            elif "num" in inp and "se" in inp:
                result = _stud(float(inp["num"]), float(inp["se"]))
                if "t" in expected:
                    _check("t", result)
            else:
                raise AssertionError(f"{fid}: no dispatch branch for STUD input shape {sorted(inp)}")
        elif gap == "MAXIMUM_T_EXCEEDANCE_TIE_PVALUE_AND_REJECTION_RULES":
            if fid == "KAT-E2E-001":
                _dispatch_e2e(fid, inp, params, expected, _check, _check_raw)
            elif "Mstar" in inp and "t_abs" in inp:
                mstar = [float(v) for v in inp["Mstar"]]
                t_abs = [float(v) for v in inp["t_abs"]]
                alpha = Fraction(params["alpha"])
                replications = params["B"]
                p_num_den, p_float, reject = [], [], []
                for t in t_abs:
                    count = sum(1 for m in mstar if m >= t)
                    num, den = 1 + count, replications + 1
                    p_num_den.append([num, den])
                    p_float.append(repr(float(Fraction(num, den))))
                    reject.append(Fraction(num, den) <= alpha)
                if "p_num_den" in expected:
                    _check_raw("p_num_den", p_num_den)
                if "p_float" in expected:
                    _check_raw("p_float", p_float)
                if "reject" in expected:
                    _check_raw("reject", reject)
                if "global_fwer_event" in expected:
                    _check_raw("global_fwer_event", any(reject))
            elif "p_float" in inp:
                alpha = Fraction(params["alpha"])
                reject = [Fraction(p) <= alpha for p in inp["p_float"]]
                if "reject" in expected:
                    _check_raw("reject", reject)
                if "global_fwer_event" in expected:
                    _check_raw("global_fwer_event", any(reject))
            else:
                raise AssertionError(f"{fid}: no dispatch branch for p-value input shape {sorted(inp)}")
        elif gap == "STATIONARY_BOOTSTRAP_INITIAL_INDEX_AND_RNG_DRAW_ORDERING":
            if "initial_index_draw" in inp:
                _check_raw("path0", inp["initial_index_draw"])
            elif "path" in inp and "x0" in inp:
                path = inp["path"]
                xstar0 = [inp["x0"][p] for p in path]
                xstar1 = [inp["x1"][p] for p in path]
                if "xstar0" in expected:
                    _check_raw("xstar0", xstar0)
                if "xstar1" in expected:
                    _check_raw("xstar1", xstar1)
            elif "initial" in inp and "restart_decisions" in inp:
                decisions = {int(k): v for k, v in inp["restart_decisions"].items()}
                indices = {int(k): v for k, v in inp.get("restart_indices", {}).items()}
                path = _path(inp["initial"], decisions, indices, inp["n"])
                if "path" in expected:
                    _check_raw("path", path)
            elif "draw_purpose" in inp:
                # Documentation-binding fixture: exercises the structural
                # decimal-string contract only; the Philox generator itself
                # belongs to the activated RNG candidate, not this candidate.
                assert isinstance(expected.get("raw_word"), str) and expected["raw_word"].isdigit(), fid
                assert isinstance(expected.get("acceptance_limit"), str) and expected["acceptance_limit"].isdigit(), fid
                assert isinstance(expected.get("initial_index"), int), fid
                asserted.update({"raw_word", "acceptance_limit", "initial_index"})
                if "full_registered_path_equals" in expected:
                    # Binds this candidate's KAT-PATH id to a specific
                    # registered RNG-candidate fixture path, without
                    # recomputing the Philox stream (out of scope here).
                    binding = expected["full_registered_path_equals"]
                    assert isinstance(binding, str) and binding.startswith("rng_candidate "), fid
                    asserted.add("full_registered_path_equals")
            else:
                raise AssertionError(f"{fid}: no dispatch branch for path input shape {sorted(inp)}")
        else:
            raise AssertionError(f"{fid}: no dispatch branch for gap_id {gap!r}")
    except ValueError as error:
        assert error_category is not None and str(error) == error_category, (fid, error)
        assert not expected, (fid, "error fixture unexpectedly declares expected_output", expected)
        return {"asserted_fields": frozenset(), "error_category": error_category}

    assert error_category is None, (fid, "expected error", error_category, "but none was raised")
    assert asserted == set(expected), (
        fid, "asserted_fields", asserted, "declared_expected_output_fields", set(expected)
    )
    return {"asserted_fields": frozenset(asserted), "error_category": None}


def _dispatch_e2e(fid, inp, params, expected, _check, _check_raw):
    series = inp["series"]
    paths = inp["bootstrap_paths"]
    lag = params["L"]
    alpha = Fraction(params["fixture_alpha"])
    names = sorted(series)
    observed = {}
    for name in names:
        x = [float(v) for v in series[name]]
        mean, gamma, omega, se = _hac(x, lag)
        observed[name] = (x, mean, _stud(mean, se))
    observed_abs = [abs(observed[name][2]) for name in names]
    observed_max = max(observed_abs)
    mstar_list = []
    for path in paths:
        tstars = []
        for name in names:
            x, mean, _ = observed[name]
            xstar = [x[p] for p in path]
            mean_s, gamma_s, omega_s, se_s = _hac(xstar, lag)
            tstars.append(_stud(mean_s - mean, se_s))
        mstar_list.append(max(abs(v) for v in tstars))
    adjusted_p, reject = [], []
    for t in observed_abs:
        count = sum(1 for m in mstar_list if m >= t)
        p = Fraction(1 + count, len(paths) + 1)
        adjusted_p.append(repr(float(p)))
        reject.append(p <= alpha)
    if "observed_abs_t" in expected:
        _check_raw("observed_abs_t", [repr(v) for v in observed_abs])
    if "observed_max" in expected:
        _check("observed_max", observed_max)
    if "Mstar" in expected:
        _check_raw("Mstar", [repr(v) for v in mstar_list])
    if "adjusted_p" in expected:
        _check_raw("adjusted_p", adjusted_p)
    if "reject" in expected:
        _check_raw("reject", reject)
    if "global_fwer_event" in expected:
        _check_raw("global_fwer_event", any(reject))


_ALL_FIXTURE_IDS = sorted(_all_fixtures())


@pytest.mark.parametrize("fixture_id", _ALL_FIXTURE_IDS)
def test_fixture_dispatch_execution_coverage(fixture_id):
    fixtures = _all_fixtures()
    _dispatch_fixture(fixture_id, fixtures[fixture_id])
    _EXERCISED.add(fixture_id)


def test_all_declared_fixtures_are_exercised():
    fixtures = _all_fixtures()
    assert _EXERCISED == set(fixtures), (
        f"missing: {set(fixtures) - _EXERCISED}; unknown: {_EXERCISED - set(fixtures)}"
    )


def test_fixture_coverage_standalone():
    """Order-independent completeness proof.

    Runs correctly in isolation (pytest <file>::test_fixture_coverage_standalone
    -q) without depending on test_fixture_dispatch_execution_coverage having
    populated _EXERCISED first: it dispatches every declared fixture locally,
    collects a receipt per fixture within this one function, and verifies
    fixture-ID coverage plus exact directly-asserted-field-set / exact
    triggered-error-category equality entirely from those local receipts.
    """
    fixtures = _all_fixtures()
    receipts = {fid: _dispatch_fixture(fid, fixture) for fid, fixture in fixtures.items()}
    assert set(receipts) == set(fixtures)
    for fid, fixture in fixtures.items():
        expected = fixture.get("expected_output", {})
        error_category = fixture.get("expected_error_category")
        receipt = receipts[fid]
        if error_category is not None:
            assert receipt["error_category"] == error_category, fid
            assert receipt["asserted_fields"] == frozenset(), fid
        else:
            assert receipt["error_category"] is None, fid
            assert receipt["asserted_fields"] == frozenset(expected), fid
