"""Independent algebraic H001 numerical-conventions KAT derivation."""
import hashlib
import math
from pathlib import Path

import pytest

ROOT = Path(__file__).parents[2]
CANDIDATE = ROOT / "docs/control/amendments/candidate1_h001_synthetic_null_calibration_numerical_conventions_amendment_candidate_v001.json"
SHA = "4f7f50e85c7be5eae54cfde1360c1fee08b7cb6869432f49272134d2a1424e3a"


def mean(a):
    return math.fsum(a) / len(a)


def covariance(a, j):
    m = mean(a)
    return math.fsum((a[t] - m) * (a[t - j] - m) for t in range(j, len(a))) / len(a)


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
