"""Synthetic proof of the non-effective signed H001 max-t correction."""
import sys
import types

import pytest

from quantbot.experiment.h001_signed_max_t_repair_candidate import (
    H001RepairCandidateError, guarded_raw_word, positive_mean_pvalues_and_rejections,
    upper_tail_exceedance_update, validate_closed_rng_draw,
)

NINE = 9


def vector(first, rest=0.0):
    return (float(first),) + (float(rest),) * (NINE - 1)


def test_negative_t_never_becomes_profitable_signal():
    t = vector(-2.0)
    one = vector(0.5)
    counts = (0,) * NINE
    for _ in range(19):
        counts = upper_tail_exceedance_update(counts, t, one, total_bootstrap_repetitions=19)
    result = positive_mean_pvalues_and_rejections(counts, t, total_bootstrap_repetitions=19)
    assert result[0] == (20, 20, False)


def test_positive_t_strictly_exceeding_bootstrap_max_rejects_at_alpha():
    counts = (0,) * NINE
    for _ in range(19):
        counts = upper_tail_exceedance_update(counts, vector(2.0), vector(0.5), total_bootstrap_repetitions=19)
    result = positive_mean_pvalues_and_rejections(counts, vector(2.0), total_bootstrap_repetitions=19)
    assert result[0] == (1, 20, True)


def test_observed_zero_or_negative_do_not_pass_even_with_pathological_bootstrap():
    counts = (0,) * NINE
    result = positive_mean_pvalues_and_rejections(counts, vector(-3.0), total_bootstrap_repetitions=19)
    assert result[0] == (1, 20, False)
    result = positive_mean_pvalues_and_rejections(counts, vector(0.0), total_bootstrap_repetitions=19)
    assert result[0] == (1, 20, False)


def test_tie_counts_and_sign_guard_independent():
    counts = upper_tail_exceedance_update((0,) * NINE, vector(1.0), vector(1.0), total_bootstrap_repetitions=19)
    assert counts[0] == 1


@pytest.mark.parametrize('observed', [float('nan'), float('inf'), float('-inf')])
def test_invalid_observed_fails_closed(observed):
    with pytest.raises(H001RepairCandidateError):
        upper_tail_exceedance_update((0,) * NINE, vector(observed), vector(0.5))


@pytest.mark.parametrize('bad', [-1, True, 10001, 1.5])
def test_invalid_count_fails_closed(bad):
    with pytest.raises(H001RepairCandidateError):
        positive_mean_pvalues_and_rejections((bad,) + (0,) * (NINE - 1), vector(2.0))


def test_invalid_vector_length_fails_closed():
    with pytest.raises(H001RepairCandidateError):
        upper_tail_exceedance_update((0,) * NINE, (1.0,), vector(0.0))


def test_update_prevents_count_overflow():
    with pytest.raises(H001RepairCandidateError):
        upper_tail_exceedance_update((19,) * NINE, vector(1.0), vector(2.0), total_bootstrap_repetitions=19)


def test_rng_strict_types_and_purpose_position(monkeypatch):
    module = types.ModuleType('quantbot.experiment.h001_null_calibration_engine')
    class Coord:
        pass
    module.BootstrapCoordinate = Coord
    module.raw_word = lambda *args: 101
    root = types.ModuleType('quantbot')
    root.__path__ = []
    experiment = types.ModuleType('quantbot.experiment')
    experiment.__path__ = []
    monkeypatch.setitem(sys.modules, 'quantbot', root)
    monkeypatch.setitem(sys.modules, 'quantbot.experiment', experiment)
    monkeypatch.setitem(sys.modules, 'quantbot.experiment.h001_null_calibration_engine', module)
    coord = Coord()
    assert guarded_raw_word(coord, 'INITIAL_INDEX', 0, 0) == 101
    assert guarded_raw_word(coord, 'RESTART_INDEX', 1, 0) == 101
    for bad in [object(), Coord]:
        with pytest.raises(H001RepairCandidateError):
            validate_closed_rng_draw(bad, 'INITIAL_INDEX', 0, 0)
    for purpose, pos in [('INITIAL_INDEX', 1), ('RESTART_INDEX', 0), ('RESTART_DECISION', 0)]:
        with pytest.raises(H001RepairCandidateError):
            validate_closed_rng_draw(coord, purpose, pos, 0)
    for purpose in ['INVALID_PURPOSE', None]:
        with pytest.raises(H001RepairCandidateError):
            validate_closed_rng_draw(coord, purpose, 1, 0)
    for sample, attempt in [(True, 0), (2193, 0), (1, True), (1, 8), (1, -1)]:
        with pytest.raises(H001RepairCandidateError):
            validate_closed_rng_draw(coord, 'RESTART_DECISION', sample, attempt)