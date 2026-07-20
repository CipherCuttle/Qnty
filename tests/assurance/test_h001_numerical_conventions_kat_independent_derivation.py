"""Independent algebraic H001 numerical-conventions KAT derivation.

This derivation uses scalar left-to-right accumulation per the binary64
operation-order contract (IEEE-754 round-to-nearest-ties-to-even, sequential
+=, single division sum/n, per-term-doubled omega2).  It is methodologically
independent from the reference derivation through different control structure,
variable naming, and helper decomposition, but uses the SAME scalar
left-to-right accumulation arithmetic so that both derivations agree on every
governed fixture output.
"""
import hashlib
import math
from pathlib import Path

import pytest

ROOT = Path(__file__).parents[2]
CANDIDATE = ROOT / "docs/control/amendments/candidate1_h001_synthetic_null_calibration_numerical_conventions_amendment_candidate_v001.json"
SHA = "f538fa50692c149b652aff7a91b2111123c7e20abf3eb82ae3a6e74daffdb1cb"


def mean(a):
    total = 0.0
    for v in a:
        total += v
    return total / len(a)


def covariance(a, j):
    m = mean(a)
    total = 0.0
    for t in range(j, len(a)):
        total += (a[t] - m) * (a[t - j] - m)
    return total / len(a)


def standard_error(omega, n):
    if omega < 0.0:
        raise ValueError("H001_NC_NEGATIVE_LONG_RUN_VARIANCE")
    return 0.0 if omega == 0.0 else math.sqrt(omega / n)


def test_hac():
    assert hashlib.sha256(CANDIDATE.read_bytes()).hexdigest() == SHA
    a = [1.0, 3.0, 1.0, 3.0]
    g0, g1 = covariance(a, 0), covariance(a, 1)
    omega = g0 + 2.0 * (0.5 * g1)
    assert (mean(a), g0, g1, omega, standard_error(omega, 4)) == (2.0, 1.0, -0.75, 0.25, 0.25)
    assert standard_error(0.0, 4) == 0.0
    with pytest.raises(ValueError, match="NEGATIVE_LONG_RUN_VARIANCE"):
        standard_error(-5e-324, 4)


def test_centering():
    a = [1.0, 3.0, 1.0, 3.0]
    resampled = [a[i] for i in (0, 0, 0, 1)]
    assert (mean(a), mean(resampled), mean(resampled) - mean(a)) == (2.0, 1.5, -0.5)


def test_studentization():
    ratio = lambda x, s: x / s if s else (0.0 if x == 0.0 else (_ for _ in ()).throw(ValueError("H001_NC_ZERO_STANDARD_ERROR")))
    assert ratio(2.0, .25) == 8.0 and ratio(0.0, 0.0) == 0.0
    with pytest.raises(ValueError, match="ZERO_STANDARD_ERROR"):
        ratio(5.0, 0.0)
    a = [1.0, 3.0, 1.0, 3.0]; b = [a[i] for i in (0, 0, 0, 1)]
    o = standard_error(covariance(b, 0) + covariance(b, 1), 4)
    assert o == 0.414578098794425 and ratio(mean(b)-mean(a), o) == -1.2060453783110545


def test_pvalue_rejection():
    m = (1.0, 2.0, .5, 3.0)
    p = tuple((1 + len([z for z in m if z >= abs(t)]), 5) for t in (8.0, 0.0, 8.0))
    assert p == ((1, 5), (5, 5), (1, 5))
    assert tuple(a / b <= .25 for a, b in p) == (True, False, True)
    assert 3 / 4 > .25  # exact-tie fixture has 3/4, hence no rejection


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
