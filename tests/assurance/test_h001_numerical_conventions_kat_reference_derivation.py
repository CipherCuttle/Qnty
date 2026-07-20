"""Reference, loop-by-loop KAT derivation for the locked H001 candidate.

This is test-only code.  Expectations below are literals from the frozen
candidate fixture registry; no expectation is generated from the candidate.
"""
import hashlib
import math
from fractions import Fraction
from pathlib import Path

import pytest


ROOT = Path(__file__).parents[2]
CANDIDATE = ROOT / "docs/control/amendments/candidate1_h001_synthetic_null_calibration_numerical_conventions_amendment_candidate_v001.json"
SHA = "f538fa50692c149b652aff7a91b2111123c7e20abf3eb82ae3a6e74daffdb1cb"


def _mean(values):
    total = 0.0
    for value in values:
        if not math.isfinite(value):
            raise ValueError("H001_NC_NON_FINITE_INPUT")
        total += value
    return total / len(values)


def _hac(values, lag=1):
    mean = _mean(values)
    n = len(values)
    gamma = []
    for j in range(lag + 1):
        total = 0.0
        for t in range(j, n):
            total += (values[t] - mean) * (values[t - j] - mean)
        gamma.append(total / n)
    omega = gamma[0]
    for j in range(1, lag + 1):
        omega = omega + 2.0 * ((1.0 - j / (lag + 1)) * gamma[j])
    if omega < 0.0:
        raise ValueError("H001_NC_NEGATIVE_LONG_RUN_VARIANCE")
    return mean, gamma, omega, 0.0 if omega == 0.0 else math.sqrt(omega / n)


def _stud(num, se):
    if se > 0.0:
        return num / se
    if num == 0.0:
        return 0.0
    raise ValueError("H001_NC_ZERO_STANDARD_ERROR")


def _se(omega, n):
    if omega < 0.0:
        raise ValueError("H001_NC_NEGATIVE_LONG_RUN_VARIANCE")
    return 0.0 if omega == 0.0 else math.sqrt(omega / n)


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
    with pytest.raises(ValueError, match="NEGATIVE_LONG_RUN_VARIANCE"):
        _se(-5e-324, 4)
    with pytest.raises(ValueError, match="NON_FINITE_INPUT"):
        _hac([1.0, float("inf"), 1.0, 3.0])


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


def test_path():
    assert _path(1, {1: False, 2: False, 3: False}, {}, 4) == [1, 2, 3, 0]
    assert _path(0, {1: True, 2: False, 3: True}, {1: 2, 3: 1}, 4) == [0, 2, 3, 1]
    path = [0, 2, 3, 1]
    assert [[10, 20, 30, 40][p] for p in path] == [10, 30, 40, 20]
    assert [[1, 2, 3, 4][p] for p in path] == [1, 3, 4, 2]


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
