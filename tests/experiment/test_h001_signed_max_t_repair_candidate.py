"""Synthetic proof of the non-effective signed H001 max-t correction."""
import sys
import types

import pytest

from quantbot.experiment.h001_signed_max_t_repair_candidate import (
    H001RepairCandidateError, guarded_raw_word, positive_net_means_gate,
    upper_tail_pvalues_and_rejections, _unchecked_tail_pvalues_and_rejections, upper_tail_exceedance_update,
    validate_closed_rng_draw,
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
    result = _unchecked_tail_pvalues_and_rejections(counts, t, total_bootstrap_repetitions=19)
    assert result[0] == (20, 20, False)


def test_positive_t_strictly_exceeding_bootstrap_max_rejects_at_alpha():
    counts = (0,) * NINE
    for _ in range(19):
        counts = upper_tail_exceedance_update(counts, vector(2.0), vector(0.5), total_bootstrap_repetitions=19)
    result = _unchecked_tail_pvalues_and_rejections(counts, vector(2.0), total_bootstrap_repetitions=19)
    assert result[0] == (1, 20, True)


def test_negative_observed_can_have_small_raw_p_but_is_not_positive_economic_evidence():
    # Deliberately pathological synthetic bootstrap: 19 signed maxima < -2.
    counts = (0,) * NINE
    for _ in range(19):
        counts = upper_tail_exceedance_update(
            counts, vector(-2.0), vector(-3.0, -3.0),
            total_bootstrap_repetitions=19,
        )
    adjusted = _unchecked_tail_pvalues_and_rejections(counts, vector(-2.0),
                                                   total_bootstrap_repetitions=19)
    assert adjusted[0] == (1, 20, True)
    # Economic eligibility is separately governed by base AND stress net means.
    assert positive_net_means_gate(-0.01, 0.01) is False


def test_zero_or_negative_means_do_not_pass_economic_gate():
    assert positive_net_means_gate(0.0, 0.01) is False
    assert positive_net_means_gate(0.01, 0.0) is False
    assert positive_net_means_gate(-0.01, 0.01) is False
    assert positive_net_means_gate(0.01, -0.01) is False
    assert positive_net_means_gate(0.01, 0.02) is True


@pytest.mark.parametrize('bad', [float('nan'), float('inf'), float('-inf'), True, 0, '0.1'])
def test_invalid_economic_mean_fails_closed(bad):
    with pytest.raises(H001RepairCandidateError, match='H001_CANDIDATE_INVALID_NET_MEAN'):
        positive_net_means_gate(bad, 0.01)
    with pytest.raises(H001RepairCandidateError, match='H001_CANDIDATE_INVALID_NET_MEAN'):
        positive_net_means_gate(0.01, bad)


def test_tie_counts_non_strict_exceedance():
    counts = upper_tail_exceedance_update((0,) * NINE, vector(1.0), vector(1.0), total_bootstrap_repetitions=19)
    assert counts[0] == 1


@pytest.mark.parametrize('observed', [float('nan'), float('inf'), float('-inf')])
def test_invalid_observed_fails_closed(observed):
    with pytest.raises(H001RepairCandidateError):
        upper_tail_exceedance_update((0,) * NINE, vector(observed), vector(0.5))


@pytest.mark.parametrize('bad', [-1, True, 10001, 1.5])
def test_invalid_count_fails_closed(bad):
    with pytest.raises(H001RepairCandidateError):
        _unchecked_tail_pvalues_and_rejections((bad,) + (0,) * (NINE - 1), vector(2.0))


def test_invalid_vector_length_fails_closed():
    with pytest.raises(H001RepairCandidateError):
        upper_tail_exceedance_update((0,) * NINE, (1.0,), vector(0.0))


def test_update_prevents_count_overflow():
    with pytest.raises(H001RepairCandidateError):
        upper_tail_exceedance_update((19,) * NINE, vector(1.0), vector(2.0), total_bootstrap_repetitions=19)


def test_rng_strict_types_and_purpose_position(monkeypatch):
    module = types.ModuleType('quantbot.experiment.h001_null_calibration_engine')
    class Coord:
        dgp_or_case_id = 'iid_gaussian'
        outer_replication_index = 0
        bootstrap_replication_index = 0
    module.DGP_OR_CASE_IDS = frozenset({'iid_gaussian'})
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

def test_mutated_coordinate_fields_fail_closed(monkeypatch):
    from quantbot.experiment.h001_null_calibration_engine import BootstrapCoordinate, DGP_OR_CASE_IDS
    valid_id = sorted(DGP_OR_CASE_IDS)[0]
    for field, invalid in [('dgp_or_case_id', 'unregistered'),
                           ('outer_replication_index', True),
                           ('outer_replication_index', 2000),
                           ('bootstrap_replication_index', -1),
                           ('bootstrap_replication_index', 10000)]:
        coord = BootstrapCoordinate(valid_id, 0, 0)
        object.__setattr__(coord, field, invalid)
        with pytest.raises(H001RepairCandidateError, match='H001_CANDIDATE_INVALID_COORDINATE_DOMAIN'):
            validate_closed_rng_draw(coord, 'INITIAL_INDEX', 0, 0)


def test_completed_run_rejects_missing_duplicate_and_wrong_order():
    from quantbot.experiment.h001_signed_max_t_repair_candidate import CompletedBootstrapRun
    ids = tuple(f"variant-{i}" for i in range(NINE))
    run = CompletedBootstrapRun(vector(2.0), ids, total_bootstrap_repetitions=19)
    with pytest.raises(H001RepairCandidateError, match="INCOMPLETE"):
        run.finalize(vector(2.0), ids)
    with pytest.raises(H001RepairCandidateError, match="ORDER_OR_COMPLETENESS"):
        run.add_completed_replication(1, vector(0.5))
    for i in range(19):
        run.add_completed_replication(i, vector(0.5))
    with pytest.raises(H001RepairCandidateError, match="ORDER_OR_COMPLETENESS"):
        run.add_completed_replication(18, vector(0.5))
    assert run.finalize(vector(2.0), ids)[0] == (1, 20, True)


def test_completed_run_binds_observed_vector_and_variant_order():
    from quantbot.experiment.h001_signed_max_t_repair_candidate import CompletedBootstrapRun
    ids = tuple(f"variant-{i}" for i in range(NINE))
    run = CompletedBootstrapRun(vector(2.0), ids, total_bootstrap_repetitions=19)
    for i in range(19):
        run.add_completed_replication(i, vector(0.5))
    with pytest.raises(H001RepairCandidateError, match="MISMATCH"):
        run.finalize(vector(-2.0), ids)
    with pytest.raises(H001RepairCandidateError, match="MISMATCH"):
        run.finalize(vector(2.0), ids[::-1])


def test_completed_run_rejects_invalid_draw_without_advancing():
    from quantbot.experiment.h001_signed_max_t_repair_candidate import CompletedBootstrapRun
    ids = tuple(f"variant-{i}" for i in range(NINE))
    run = CompletedBootstrapRun(vector(2.0), ids, total_bootstrap_repetitions=2)
    with pytest.raises(H001RepairCandidateError):
        run.add_completed_replication(0, vector(float('nan')))
    run.add_completed_replication(0, vector(0.5))
    run.add_completed_replication(1, vector(0.5))
    assert run.finalize(vector(2.0), ids)[0] == (1, 3, False)


def test_public_finalizer_rejects_unsealed_counts_even_when_significant():
    ids = tuple(f"variant-{i}" for i in range(NINE))
    with pytest.raises(H001RepairCandidateError, match="UNSEALED_COUNTS_FORBIDDEN"):
        upper_tail_pvalues_and_rejections((0,) * NINE, vector(2.0), ids)


def test_public_finalizer_rejects_legacy_accumulator_even_if_complete():
    from quantbot.experiment.h001_signed_max_t_repair_candidate import CompletedBootstrapRun
    ids = tuple(f"variant-{i}" for i in range(NINE))
    run = CompletedBootstrapRun(vector(2.0), ids, total_bootstrap_repetitions=19)
    for i in range(19):
        run.add_completed_replication(i, vector(0.5))
    with pytest.raises(H001RepairCandidateError, match="UNSEALED_COUNTS_FORBIDDEN"):
        upper_tail_pvalues_and_rejections(run, vector(2.0), ids)


def test_engine_bound_run_rejects_external_values_and_uses_coordinates(monkeypatch):
    import numpy as np
    import quantbot.experiment.h001_null_calibration_engine as engine
    from quantbot.experiment.h001_signed_max_t_repair_candidate import EngineBoundBootstrapRun
    ids = tuple(f"variant-{i}" for i in range(NINE))
    x = np.random.default_rng(17).normal(size=(9, 2193)).astype(np.float64)
    seen = []
    def synthetic_replication(data, means, coordinate):
        seen.append((coordinate.dgp_or_case_id, coordinate.outer_replication_index,
                     coordinate.bootstrap_replication_index))
        return (0.5,) * 9
    monkeypatch.setattr(engine, 'compute_one_bootstrap_replication', synthetic_replication)
    run = EngineBoundBootstrapRun(x, ids, 'iid_gaussian', 2, total_bootstrap_repetitions=2)
    with pytest.raises(H001RepairCandidateError, match="EXTERNAL_BOOTSTRAP_VECTOR_FORBIDDEN"):
        run.add_completed_replication(0, (0.5,) * 9)
    x[:] = 999.0
    run.compute_next_replication()
    with pytest.raises(H001RepairCandidateError, match="INCOMPLETE"):
        upper_tail_pvalues_and_rejections(run, run._observed, ids)
    run.compute_next_replication()
    assert seen == [('iid_gaussian', 2, 0), ('iid_gaussian', 2, 1)]
    assert len(upper_tail_pvalues_and_rejections(run, run._observed, ids)) == 9
    with pytest.raises(H001RepairCandidateError, match="ORDER_OR_COMPLETENESS"):
        run.compute_next_replication()


def test_engine_bound_run_detects_accumulator_tampering(monkeypatch):
    import numpy as np
    import quantbot.experiment.h001_null_calibration_engine as engine
    from quantbot.experiment.h001_signed_max_t_repair_candidate import EngineBoundBootstrapRun
    ids = tuple(f"variant-{i}" for i in range(NINE))
    x = np.random.default_rng(18).normal(size=(9, 2193)).astype(np.float64)
    monkeypatch.setattr(engine, "compute_one_bootstrap_replication", lambda *args: (0.5,) * 9)
    run = EngineBoundBootstrapRun(x, ids, "iid_gaussian", 0, total_bootstrap_repetitions=2)
    run.compute_next_replication()
    run._counts = (0,) * 9
    with pytest.raises(H001RepairCandidateError, match="STATE_DRIFT"):
        run.compute_next_replication()


def test_engine_bound_real_philox_shared_path_smoke():
    import numpy as np
    from quantbot.experiment.h001_signed_max_t_repair_candidate import EngineBoundBootstrapRun
    ids = tuple(f"variant-{i}" for i in range(NINE))
    rng = np.random.default_rng(19)
    x = rng.normal(size=(9, 2193)).astype(np.float64)
    run = EngineBoundBootstrapRun(x, ids, "iid_gaussian", 0, total_bootstrap_repetitions=1)
    run.compute_next_replication()  # real Philox + one shared index path + nine studentized statistics
    assert len(upper_tail_pvalues_and_rejections(run, run._observed, ids)) == 9
