"""Adversarial tests for the H001 per-run coordinate and seed orchestration
candidate.

This candidate is implemented for independent review only: these tests
exercise the reviewed engine's already-governed pure functions against
synthetic in-test data, never real data, never any filesystem or network
access, and prove no execution-order dependence. They do not authorize,
wire, or execute calibration.
"""
from __future__ import annotations

import ast
import inspect

import numpy as np
import pytest

from quantbot.experiment import h001_null_calibration_engine as engine
from quantbot.experiment.h001_per_run_coordinate_and_seed_orchestration import (
    RunCoordinate,
    bootstrap_coordinates_for_run,
)


def test_run_coordinate_rejects_unknown_dgp_or_case_id():
    with pytest.raises(engine.H001EngineError) as exc:
        RunCoordinate("not_a_registered_case", 0)
    assert exc.value.code == "H001_RNG_INVALID_COORDINATE"


@pytest.mark.parametrize("outer_replication_index", [-1, 2000, 10**9])
def test_run_coordinate_rejects_out_of_domain_outer_replication_index(outer_replication_index):
    with pytest.raises(engine.H001EngineError) as exc:
        RunCoordinate("iid_gaussian", outer_replication_index)
    assert exc.value.code == "H001_RNG_COORDINATE_OUT_OF_DOMAIN"


def test_run_coordinate_rejects_non_int_outer_replication_index():
    with pytest.raises(engine.H001EngineError) as exc:
        RunCoordinate("iid_gaussian", 0.0)
    assert exc.value.code == "H001_RNG_COORDINATE_OUT_OF_DOMAIN"


def test_run_coordinate_accepts_domain_boundaries():
    RunCoordinate("iid_gaussian", 0)
    RunCoordinate("iid_gaussian", 1999)


def test_bootstrap_coordinates_for_run_requires_run_coordinate_type():
    with pytest.raises(TypeError):
        bootstrap_coordinates_for_run(("iid_gaussian", 0))


def test_bootstrap_coordinates_for_run_cardinality_matches_registered_repetitions():
    coords = bootstrap_coordinates_for_run(RunCoordinate("iid_gaussian", 0))
    assert len(coords) == engine.BOOTSTRAP_REPETITIONS == 10000


def test_bootstrap_coordinates_for_run_is_ascending_and_unique():
    coords = bootstrap_coordinates_for_run(RunCoordinate("stationary_ar1_phi_0p3", 7))
    indices = [c.bootstrap_replication_index for c in coords]
    assert indices == list(range(engine.BOOTSTRAP_REPETITIONS))
    assert len(set(indices)) == engine.BOOTSTRAP_REPETITIONS


def test_bootstrap_coordinates_for_run_binds_run_identity_to_every_coordinate():
    run = RunCoordinate("sparse_extreme_outliers", 123)
    coords = bootstrap_coordinates_for_run(run)
    assert all(c.dgp_or_case_id == "sparse_extreme_outliers" for c in coords)
    assert all(c.outer_replication_index == 123 for c in coords)


def test_bootstrap_coordinates_for_run_is_pure_and_deterministic():
    run = RunCoordinate("iid_gaussian", 0)
    first = bootstrap_coordinates_for_run(run)
    second = bootstrap_coordinates_for_run(run)
    assert first == second
    assert first is not second


def test_two_distinct_outer_replications_never_collide_in_key_material():
    run_a = bootstrap_coordinates_for_run(RunCoordinate("iid_gaussian", 0))
    run_b = bootstrap_coordinates_for_run(RunCoordinate("iid_gaussian", 1))
    keys_a = {engine._key_words(c) for c in run_a[:50]}
    keys_b = {engine._key_words(c) for c in run_b[:50]}
    assert keys_a.isdisjoint(keys_b)


def test_two_distinct_dgp_ids_never_collide_in_key_material():
    run_a = bootstrap_coordinates_for_run(RunCoordinate("iid_gaussian", 0))
    run_b = bootstrap_coordinates_for_run(RunCoordinate("iid_student_t_df5_standardized", 0))
    keys_a = {engine._key_words(c) for c in run_a[:50]}
    keys_b = {engine._key_words(c) for c in run_b[:50]}
    assert keys_a.isdisjoint(keys_b)


def test_bootstrap_replication_index_within_one_run_never_collides_in_key_material():
    run = bootstrap_coordinates_for_run(RunCoordinate("iid_gaussian", 0))
    keys = [engine._key_words(c) for c in run[:200]]
    assert len(set(keys)) == len(keys)


def _synthetic_input() -> np.ndarray:
    rng = np.random.default_rng(1234567)
    return np.asarray(rng.standard_normal((engine.SERIES_COUNT, engine.SAMPLE_LENGTH)), dtype=np.float64, order="C")


def test_bootstrap_computation_over_run_coordinates_is_order_independent():
    x = engine.validate_input(_synthetic_input())
    xbar, _se, t = engine.compute_observed_statistics(x)
    observed_abs_t = tuple(abs(v) for v in t)
    run = RunCoordinate("iid_gaussian", 0)
    sample = bootstrap_coordinates_for_run(run)[:20]

    forward_counts = tuple(0 for _ in observed_abs_t)
    for coordinate in sample:
        tstar = engine.compute_one_bootstrap_replication(x, xbar, coordinate)
        forward_counts = engine.update_exceedance_counts(forward_counts, observed_abs_t, tstar)

    reversed_counts = tuple(0 for _ in observed_abs_t)
    for coordinate in reversed(sample):
        tstar = engine.compute_one_bootstrap_replication(x, xbar, coordinate)
        reversed_counts = engine.update_exceedance_counts(reversed_counts, observed_abs_t, tstar)

    shuffled = [sample[i] for i in (5, 0, 19, 3, 11, 1, 17, 2, 8, 14, 6, 13, 4, 18, 9, 15, 7, 12, 10, 16)]
    shuffled_counts = tuple(0 for _ in observed_abs_t)
    for coordinate in shuffled:
        tstar = engine.compute_one_bootstrap_replication(x, xbar, coordinate)
        shuffled_counts = engine.update_exceedance_counts(shuffled_counts, observed_abs_t, tstar)

    assert forward_counts == reversed_counts == shuffled_counts


def test_per_run_orchestration_module_performs_no_io():
    import quantbot.experiment.h001_per_run_coordinate_and_seed_orchestration as module

    source = inspect.getsource(module)
    tree = ast.parse(source)
    banned = {"os", "socket", "requests", "subprocess", "pathlib", "shutil", "urllib", "http"}
    imported = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imported.update(alias.name.split(".")[0] for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            imported.add(node.module.split(".")[0])
    assert imported.isdisjoint(banned)
