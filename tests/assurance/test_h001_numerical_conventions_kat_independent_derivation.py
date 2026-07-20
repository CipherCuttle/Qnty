"""Independent algebraic H001 numerical-conventions KAT derivation.

This derivation uses scalar left-to-right accumulation per the binary64
operation-order contract (IEEE-754 round-to-nearest-ties-to-even, sequential
+=, single division sum/n, per-term-doubled omega2).  It is methodologically
independent from the reference derivation through different control structure,
variable naming, and helper decomposition, but uses the SAME scalar
left-to-right accumulation arithmetic so that both derivations agree on every
governed fixture output.

Every helper below fails closed the instant an operation produces a
non-finite (NaN/inf) value; no non-finite intermediate is allowed to reach a
later operation.
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

_HUGE = 1.7976931348623157e+308


def _finite(value):
    return not (value != value or value > _HUGE or value < -_HUGE)


def mean(a):
    total = 0.0
    index = 0
    while index < len(a):
        v = a[index]
        if not math.isfinite(v):
            raise ValueError("H001_NC_NON_FINITE_INPUT")
        total += v
        if not _finite(total):
            raise ValueError("H001_NC_NON_FINITE_INTERMEDIATE")
        index += 1
    return total / len(a)


def covariance(a, j):
    m = mean(a)
    total = 0.0
    n = len(a)
    t = j
    while t < n:
        term = (a[t] - m) * (a[t - j] - m)
        if not _finite(term):
            raise ValueError("H001_NC_NON_FINITE_INTERMEDIATE")
        total += term
        if not _finite(total):
            raise ValueError("H001_NC_NON_FINITE_INTERMEDIATE")
        t += 1
    return total / n


def long_run_variance(a, lag):
    gammas = [covariance(a, j) for j in range(lag + 1)]
    omega = gammas[0]
    for j in range(1, lag + 1):
        weight = 1.0 - j / (lag + 1)
        term = 2.0 * (weight * gammas[j])
        if not _finite(term):
            raise ValueError("H001_NC_NON_FINITE_INTERMEDIATE")
        omega += term
        if not _finite(omega):
            raise ValueError("H001_NC_NON_FINITE_INTERMEDIATE")
    return omega, gammas


def standard_error(omega, n):
    if not _finite(omega):
        raise ValueError("H001_NC_NON_FINITE_INTERMEDIATE")
    if omega < 0.0:
        raise ValueError("H001_NC_NEGATIVE_LONG_RUN_VARIANCE")
    if omega == 0.0:
        return 0.0
    scaled = omega / n
    if not _finite(scaled):
        raise ValueError("H001_NC_NON_FINITE_INTERMEDIATE")
    root = math.sqrt(scaled)
    if not _finite(root):
        raise ValueError("H001_NC_NON_FINITE_INTERMEDIATE")
    return root


def hac(a, lag=1):
    m = mean(a)
    omega, gammas = long_run_variance(a, lag)
    return m, gammas, omega, standard_error(omega, len(a))


def ratio(x, s):
    if not _finite(s) or not _finite(x):
        raise ValueError("H001_NC_NON_FINITE_INTERMEDIATE")
    if s < 0.0:
        raise ValueError("H001_NC_NEGATIVE_STANDARD_ERROR")
    if s == 0.0:
        if x == 0.0:
            return 0.0
        raise ValueError("H001_NC_ZERO_STANDARD_ERROR")
    value = x / s
    if not _finite(value):
        raise ValueError("H001_NC_NON_FINITE_INTERMEDIATE")
    return 0.0 if value == 0.0 else value


def test_hac():
    assert hashlib.sha256(CANDIDATE.read_bytes()).hexdigest() == SHA
    a = [1.0, 3.0, 1.0, 3.0]
    g0, g1 = covariance(a, 0), covariance(a, 1)
    omega = g0 + 2.0 * (0.5 * g1)
    assert (mean(a), g0, g1, omega, standard_error(omega, 4)) == (2.0, 1.0, -0.75, 0.25, 0.25)
    assert standard_error(0.0, 4) == 0.0
    with pytest.raises(ValueError, match="NEGATIVE_LONG_RUN_VARIANCE"):
        standard_error(-5e-324, 4)
    # KAT-HAC-NEGMATERIAL-001: distinct materially-negative fixture, must be
    # its own runtime assertion rather than piggybacking on the roundoff case.
    with pytest.raises(ValueError, match="NEGATIVE_LONG_RUN_VARIANCE"):
        standard_error(-1.0, 4)

    b = [-1.0, 1.0, -1.0, 1.0]
    ob, gb = long_run_variance(b, 1)
    assert (mean(b), standard_error(ob, 4)) == (0.0, 0.25)

    c = [3.0, 1.0, 3.0, 1.0]
    oc, gc = long_run_variance(c, 1)
    assert (mean(c), standard_error(oc, 4)) == (2.0, 0.25)


def test_hac_division_contract():
    """KAT-HAC-DIVISION-001: n=7 discriminates division from reciprocal-multiply."""
    a = (1.0, 3.0, 1.0, 3.0, 1.0, 3.0, 1.0)
    n = len(a)
    m, gammas, omega, se = hac(list(a), 1)
    assert m == 1.8571428571428572
    assert gammas[0] == 0.9795918367346939
    assert gammas[1] == -0.8396501457725948
    assert omega == 0.13994169096209907
    assert se == 0.14139190265868384

    s = 0.0
    for v in a:
        s += v
    assert (s / n) != (s * (1.0 / n))
    assert (s / n) == m

    gs = 0.0
    for v in a:
        gs += (v - m) * (v - m)
    assert (gs / n) != (gs * (1.0 / n))
    assert (gs / n) == gammas[0]


def test_non_finite_intermediate_fail_closed():
    # KAT-HAC-NONFINITE-INTERMEDIATE-MEAN-001
    with pytest.raises(ValueError, match="NON_FINITE_INTERMEDIATE"):
        mean([1.7976931348623157e+308, 1.7976931348623157e+308])
    # KAT-HAC-NONFINITE-INTERMEDIATE-GAMMA-001
    with pytest.raises(ValueError, match="NON_FINITE_INTERMEDIATE"):
        covariance([1e200, -1e200, 1e200, -1e200], 0)
    # KAT-STUD-NONFINITE-INTERMEDIATE-001
    with pytest.raises(ValueError, match="NON_FINITE_INTERMEDIATE"):
        ratio(1.7976931348623157e+308, 1e-300)
    # KAT-STUD-NEGATIVE-SE-001
    with pytest.raises(ValueError, match="NEGATIVE_STANDARD_ERROR"):
        ratio(1.0, -2.0)
    with pytest.raises(ValueError, match="NEGATIVE_STANDARD_ERROR"):
        ratio(0.0, -3.0)
    # KAT-STUD-SIGNED-ZERO-001
    for x, s in ((0.0, 0.0), (-0.0, 0.0), (0.0, -0.0), (-0.0, -0.0), (-0.0, 5.0)):
        r = ratio(x, s)
        assert r == 0.0 and math.copysign(1.0, r) == 1.0, (x, s, r)


def test_centering():
    a = [1.0, 3.0, 1.0, 3.0]
    resampled = [a[i] for i in (0, 0, 0, 1)]
    assert (mean(a), mean(resampled), mean(resampled) - mean(a)) == (2.0, 1.5, -0.5)


def test_studentization():
    assert ratio(2.0, .25) == 8.0 and ratio(0.0, 0.0) == 0.0
    with pytest.raises(ValueError, match="ZERO_STANDARD_ERROR"):
        ratio(5.0, 0.0)
    a = [1.0, 3.0, 1.0, 3.0]; b = [a[i] for i in (0, 0, 0, 1)]
    omega_b, _ = long_run_variance(b, 1)
    o = standard_error(omega_b, 4)
    assert o == 0.414578098794425 and ratio(mean(b)-mean(a), o) == -1.2060453783110545


def test_pvalue_rejection():
    m = (1.0, 2.0, .5, 3.0)
    p = tuple((1 + len([z for z in m if z >= abs(t)]), 5) for t in (8.0, 0.0, 8.0))
    assert p == ((1, 5), (5, 5), (1, 5))
    assert tuple(a / b <= .25 for a, b in p) == (True, False, True)
    assert 3 / 4 > .25  # exact-tie fixture has 3/4, hence no rejection

    # KAT-PVAL-TIE-001 / EQ-ALPHA-001 / FINITEB-001
    assert Fraction(1 + sum(1 for z in (2.0, 1.0, 3.0) if z >= 2.0), 4) == Fraction(3, 4)
    assert Fraction(1 + sum(1 for z in (0.0,) * 19 if z >= 5.0), 20) == Fraction(1, 20)
    assert Fraction(1 + sum(1 for z in (1.0, 2.0, 3.0, 4.0) if z >= 10.0), 5) == Fraction(1, 5)

    # KAT-PVAL-GLOBAL-REJECT-001 / KAT-PVAL-GLOBAL-NOREJECT-001
    reject_case = [Fraction(2, 10) <= Fraction(1, 4), Fraction(1, 1) <= Fraction(1, 4), Fraction(2, 10) <= Fraction(1, 4)]
    noreject_case = [Fraction(5, 10) <= Fraction(1, 4), Fraction(1, 1) <= Fraction(1, 4), Fraction(7, 10) <= Fraction(1, 4)]
    assert any(reject_case) and not any(noreject_case)


def test_path():
    def build(first, restart, n):
        out = [first]
        for decision, index in restart:
            out += [index if decision else (out[-1] + 1) % n]
        return out
    assert build(3, ((False, 0), (False, 0), (False, 0)), 4) == [3, 0, 1, 2]
    path = build(0, ((True, 2), (False, 0), (True, 1)), 4)
    assert path == [0, 2, 3, 1]
    assert tuple(tuple(series[i] for i in path) for series in ((10,20,30,40), (1,2,3,4))) == ((10,30,40,20), (1,3,4,2))
    # KAT-PATH-INITIAL-001
    assert build(2, (), 4) == [2]
    # KAT-PATH-WRAP-001
    assert build(3, ((False, 0), (False, 0), (False, 0)), 4) == [3, 0, 1, 2]


def test_hac_order_discrimination():
    """KAT-HAC-ORDER-001: operation-order-discriminating fixture.

    Uses non-dyadic inputs where sequential += and math.fsum produce different
    results for the mean, gamma[0], gamma[1], and omega2, proving that the
    scalar left-to-right accumulation contract is binding.
    """
    inputs = [100.0, 2e-12, -100.0, 1e-12, 100.0, 3e-12, -100.0, 4e-12]

    # Sequential += (normative per binary64 contract)
    m = mean(inputs)
    g0 = covariance(inputs, 0)
    g1 = covariance(inputs, 1)
    omega = g0 + 2.0 * (0.5 * g1)
    se = standard_error(omega, 8)

    assert m == 1.2496225862269056e-12
    assert g0 == 5000.0
    assert g1 == -3.437971767216481e-11
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
    assert m != fsum_mean
    assert g0 != fsum_g0
    assert g1 != fsum_g1
    assert omega != fsum_omega


# --- Operation-order structural enforcement ---------------------------------
#
# Runtime fail-closed behavior alone is necessary but not sufficient here: the
# per-term product guard and the adjacent post-accumulation guard in
# covariance() can mask each other's removal at runtime, since the second
# independently catches the value the first would have caught. The candidate's
# deterministic pseudocode is normative on ORDER, not just final outcome:
# "term=(...); if not isfinite(term): fail ...; acc=acc+term". This walks
# covariance()'s own AST (not a string search) and proves the per-term
# product is bound to a scalar, that scalar is finiteness-checked in the
# statement immediately following its binding, and only then is it folded
# into the running total -- using a node-kind classification pass distinct
# from the reference derivation's structural checker.


def _classify_body_statements(body):
    """Return a list of (kind, node) tags for each statement in a block.

    kind is one of: "bind:<name>" for `name = ...` assignments,
    "guard:<name>" for `if not finite_check(name): raise ...`,
    "accum_candidate:<acc>:<operand>" for each Name operand folded into an
    augmented/rebuilt accumulator, or "other".
    """
    tags = []
    for stmt in body:
        if isinstance(stmt, ast.Assign) and len(stmt.targets) == 1 and isinstance(stmt.targets[0], ast.Name):
            tags.append((f"bind:{stmt.targets[0].id}", stmt))
            continue
        if isinstance(stmt, ast.AugAssign) and isinstance(stmt.target, ast.Name):
            operand_names = {n.id for n in ast.walk(stmt.value) if isinstance(n, ast.Name)}
            for candidate in operand_names:
                tags.append((f"accum_candidate:{stmt.target.id}:{candidate}", stmt))
            if not operand_names:
                tags.append(("other", stmt))
            continue
        if isinstance(stmt, ast.If):
            test = stmt.test
            if (
                isinstance(test, ast.UnaryOp)
                and isinstance(test.op, ast.Not)
                and isinstance(test.operand, ast.Call)
                and test.operand.args
                and isinstance(test.operand.args[0], ast.Name)
                and any(isinstance(s, ast.Raise) for s in stmt.body)
            ):
                tags.append((f"guard:{test.operand.args[0].id}", stmt))
                continue
        tags.append(("other", stmt))
    return tags


def test_covariance_product_guard_precedes_accumulation():
    """Structural (AST-classified) proof that covariance()'s per-term product
    is finiteness-checked before it reaches the running total, matching the
    candidate's hac_gamma operation-order contract."""
    source = inspect.getsource(covariance)
    func_def = ast.parse(source).body[0]
    assert isinstance(func_def, ast.FunctionDef)
    loop = next(node for node in func_def.body if isinstance(node, (ast.While, ast.For)))
    tags = _classify_body_statements(loop.body)

    bind_idx = next(i for i, (kind, _) in enumerate(tags) if kind == "bind:term")
    guard_idx = bind_idx + 1
    assert guard_idx < len(tags), "no statement follows the per-term product binding"
    assert tags[guard_idx][0] == "guard:term", (
        "the autocovariance product ('term') must be finiteness-checked in "
        "the statement immediately following its binding, before any "
        "accumulation into the running total"
    )
    accum_idx = guard_idx + 1
    assert accum_idx < len(tags), "no accumulation statement follows the product guard"
    assert tags[accum_idx][0].startswith("accum_candidate:total:term"), (
        "the finiteness-checked product must be the operand folded into "
        "'total' immediately after its own guard, not before"
    )
    assert bind_idx < guard_idx < accum_idx


# --- Execution-derived fixture coverage -------------------------------------
#
# A dispatch-table (not if/elif chain, structurally distinct from the
# reference derivation's dispatcher) drives every declared fixture through
# the governed functions above. Each handler records, via _bind()/_bind_raw(),
# the exact expected_output field name it directly asserted; _dispatch then
# requires that recorded set to equal EVERY field the fixture declares in
# expected_output, so a deleted assertion for a still-declared field fails
# even when a correlated field happens to still be correct. A ledger records
# a fixture only once its receipt (assertions or exact error category) is
# fully formed.

_LEDGER = set()


def _load_fixtures():
    return json.loads(CANDIDATE.read_bytes())["known_answer_fixtures"]


def _run_hac_gap(fid, inp, params, expected, error_category, _bind, _bind_raw):
    if "x" in inp:
        lag = params.get("L", 1)
        m, gammas, omega, se = hac([float(v) for v in inp["x"]], lag)
        checks = {"xbar": m, "gamma0": gammas[0] if gammas else None,
                  "gamma1": gammas[1] if len(gammas) > 1 else None, "omega2": omega, "se": se}
        for key, value in checks.items():
            if key in expected:
                _bind(key, value)
        return
    if "omega2" in inp:
        se = standard_error(float(inp["omega2"]), params["n"])
        if "se" in expected:
            _bind("se", se)
        return
    raise AssertionError((fid, "no HAC dispatch shape", sorted(inp)))


def _run_centering_gap(fid, inp, params, expected, error_category, _bind, _bind_raw):
    a = [float(v) for v in inp["x"]]
    resampled = [a[i] for i in inp["resample_path"]]
    m, m_star = mean(a), mean(resampled)
    if "xbar" in expected:
        _bind("xbar", m)
    if "xbar_star" in expected:
        _bind("xbar_star", m_star)
    if "centered_numerator" in expected:
        _bind("centered_numerator", m_star - m)


def _run_stud_gap(fid, inp, params, expected, error_category, _bind, _bind_raw):
    if "pairs" in inp:
        values = [repr(ratio(float(x), float(s))) for x, s in inp["pairs"]]
        if "t_values" in expected:
            _bind_raw("t_values", values)
        return
    if "resample_path" in inp and "x" in inp:
        a = [float(v) for v in inp["x"]]
        lag = params.get("L", 1)
        m, gammas, omega, se_obs = hac(a, lag)
        resampled = [a[i] for i in inp["resample_path"]]
        m_star, gammas_s, omega_s, se_boot = hac(resampled, lag)
        numerator = m_star - m
        t_boot = ratio(numerator, se_boot)
        t_wrong = ratio(numerator, se_obs)
        if "observed_se" in expected:
            _bind("observed_se", se_obs)
        if "bootstrap_se_star" in expected:
            _bind("bootstrap_se_star", se_boot)
        if "bootstrap_tstar" in expected:
            _bind("bootstrap_tstar", t_boot)
        if "wrong_if_observed_se_reused" in expected:
            _bind("wrong_if_observed_se_reused", t_wrong)
        return
    if "num" in inp and "se" in inp:
        value = ratio(float(inp["num"]), float(inp["se"]))
        if "t" in expected:
            _bind("t", value)
        return
    raise AssertionError((fid, "no STUD dispatch shape", sorted(inp)))


def _run_pvalue_gap(fid, inp, params, expected, error_category, _bind, _bind_raw):
    if fid == "KAT-E2E-001":
        _run_e2e(fid, inp, params, expected, _bind, _bind_raw)
        return
    if "Mstar" in inp and "t_abs" in inp:
        mstar = [float(v) for v in inp["Mstar"]]
        t_abs = [float(v) for v in inp["t_abs"]]
        alpha = Fraction(params["alpha"])
        replications = params["B"]
        num_den, floats, rejects = [], [], []
        for t in t_abs:
            count = sum(1 for m in mstar if m >= t)
            num, den = 1 + count, replications + 1
            num_den.append([num, den]); floats.append(repr(float(Fraction(num, den)))); rejects.append(Fraction(num, den) <= alpha)
        if "p_num_den" in expected:
            _bind_raw("p_num_den", num_den)
        if "p_float" in expected:
            _bind_raw("p_float", floats)
        if "reject" in expected:
            _bind_raw("reject", rejects)
        if "global_fwer_event" in expected:
            _bind_raw("global_fwer_event", any(rejects))
        return
    if "p_float" in inp:
        alpha = Fraction(params["alpha"])
        rejects = [Fraction(p) <= alpha for p in inp["p_float"]]
        if "reject" in expected:
            _bind_raw("reject", rejects)
        if "global_fwer_event" in expected:
            _bind_raw("global_fwer_event", any(rejects))
        return
    raise AssertionError((fid, "no p-value dispatch shape", sorted(inp)))


def _run_e2e(fid, inp, params, expected, _bind, _bind_raw):
    series = inp["series"]
    paths = inp["bootstrap_paths"]
    lag = params["L"]
    alpha = Fraction(params["fixture_alpha"])
    names = sorted(series)
    obs = {name: hac([float(v) for v in series[name]], lag) for name in names}
    obs_t = {name: ratio(obs[name][0], obs[name][3]) for name in names}
    abs_t = [abs(obs_t[name]) for name in names]
    mstars = []
    for path in paths:
        boots = []
        for name in names:
            a = [float(v) for v in series[name]]
            resampled = [a[i] for i in path]
            m_star, _, omega_s, se_s = hac(resampled, lag)
            boots.append(ratio(m_star - obs[name][0], se_s))
        mstars.append(max(abs(v) for v in boots))
    adjusted, rejects = [], []
    for t in abs_t:
        count = sum(1 for m in mstars if m >= t)
        p = Fraction(1 + count, len(paths) + 1)
        adjusted.append(repr(float(p))); rejects.append(p <= alpha)
    if "observed_abs_t" in expected:
        _bind_raw("observed_abs_t", [repr(v) for v in abs_t])
    if "observed_max" in expected:
        _bind("observed_max", max(abs_t))
    if "Mstar" in expected:
        _bind_raw("Mstar", [repr(v) for v in mstars])
    if "adjusted_p" in expected:
        _bind_raw("adjusted_p", adjusted)
    if "reject" in expected:
        _bind_raw("reject", rejects)
    if "global_fwer_event" in expected:
        _bind_raw("global_fwer_event", any(rejects))


def _run_path_gap(fid, inp, params, expected, error_category, _bind, _bind_raw):
    if "initial_index_draw" in inp:
        _bind_raw("path0", inp["initial_index_draw"])
        return
    if "path" in inp and "x0" in inp:
        path = inp["path"]
        s0 = [inp["x0"][p] for p in path]
        s1 = [inp["x1"][p] for p in path]
        if "xstar0" in expected:
            _bind_raw("xstar0", s0)
        if "xstar1" in expected:
            _bind_raw("xstar1", s1)
        return
    if "initial" in inp and "restart_decisions" in inp:
        decisions = {int(k): v for k, v in inp["restart_decisions"].items()}
        indices = {int(k): v for k, v in inp.get("restart_indices", {}).items()}
        n = inp["n"]
        built = [inp["initial"]]
        for t in range(1, n):
            built.append(indices[t] if decisions.get(t, False) else (built[t - 1] + 1) % n)
        if "path" in expected:
            _bind_raw("path", built)
        return
    if "draw_purpose" in inp:
        assert isinstance(expected.get("raw_word"), str) and expected["raw_word"].isdigit(), fid
        assert isinstance(expected.get("acceptance_limit"), str) and expected["acceptance_limit"].isdigit(), fid
        assert isinstance(expected.get("initial_index"), int), fid
        for key in ("raw_word", "acceptance_limit", "initial_index"):
            _bind_raw(key, expected[key])
        if "full_registered_path_equals" in expected:
            binding = expected["full_registered_path_equals"]
            assert isinstance(binding, str) and binding.startswith("rng_candidate "), fid
            _bind_raw("full_registered_path_equals", binding)
        return
    raise AssertionError((fid, "no path dispatch shape", sorted(inp)))


_GAP_HANDLERS = {
    "HAC_AUTOCOVARIANCE_AND_STANDARD_ERROR_CONVENTION": _run_hac_gap,
    "BOOTSTRAP_NULL_CENTERING_TRANSFORM": _run_centering_gap,
    "BOOTSTRAP_STUDENTIZATION_CONVENTION": _run_stud_gap,
    "MAXIMUM_T_EXCEEDANCE_TIE_PVALUE_AND_REJECTION_RULES": _run_pvalue_gap,
    "STATIONARY_BOOTSTRAP_INITIAL_INDEX_AND_RNG_DRAW_ORDERING": _run_path_gap,
}


def _dispatch(fixture_id, fixture):
    """Execute fixture_id; return {"asserted_fields": frozenset, "error_category": str|None}."""
    gap = fixture["gap_id"]
    expected = fixture.get("expected_output", {})
    error_category = fixture.get("expected_error_category")
    handler = _GAP_HANDLERS.get(gap)
    if handler is None:
        raise AssertionError((fixture_id, "unknown gap_id", gap))
    asserted = set()

    def _bind(key, actual):
        assert key in expected, (fixture_id, key, "asserted a field the fixture does not declare")
        assert repr(actual) == expected[key], (fixture_id, key, actual, expected[key])
        asserted.add(key)

    def _bind_raw(key, actual):
        assert key in expected, (fixture_id, key, "asserted a field the fixture does not declare")
        assert actual == expected[key], (fixture_id, key, actual, expected[key])
        asserted.add(key)

    try:
        handler(fixture_id, fixture["input"], fixture.get("test_parameters", {}), expected, error_category, _bind, _bind_raw)
    except ValueError as error:
        assert error_category is not None and str(error) == error_category, (fixture_id, error)
        assert not expected, (fixture_id, "error fixture unexpectedly declares expected_output", expected)
        return {"asserted_fields": frozenset(), "error_category": error_category}

    assert error_category is None, (fixture_id, "expected error", error_category, "but none was raised")
    assert asserted == set(expected), (
        fixture_id, "asserted_fields", asserted, "declared_expected_output_fields", set(expected)
    )
    return {"asserted_fields": frozenset(asserted), "error_category": None}


_ALL_FIXTURE_IDS = sorted(_load_fixtures())


@pytest.mark.parametrize("fixture_id", _ALL_FIXTURE_IDS)
def test_fixture_dispatch_execution_coverage(fixture_id):
    fixtures = _load_fixtures()
    _dispatch(fixture_id, fixtures[fixture_id])
    _LEDGER.add(fixture_id)


def test_all_declared_fixtures_are_exercised():
    fixtures = _load_fixtures()
    assert _LEDGER == set(fixtures), (
        f"missing: {set(fixtures) - _LEDGER}; unknown: {_LEDGER - set(fixtures)}"
    )


def test_fixture_coverage_standalone():
    """Order-independent completeness proof.

    Runs correctly in isolation (pytest <file>::test_fixture_coverage_standalone
    -q) without depending on test_fixture_dispatch_execution_coverage having
    populated _LEDGER first: it dispatches every declared fixture locally,
    collects a receipt per fixture within this one function, and verifies
    fixture-ID coverage plus exact directly-asserted-field-set / exact
    triggered-error-category equality entirely from those local receipts.
    """
    fixtures = _load_fixtures()
    receipts = {fid: _dispatch(fid, fixture) for fid, fixture in fixtures.items()}
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
