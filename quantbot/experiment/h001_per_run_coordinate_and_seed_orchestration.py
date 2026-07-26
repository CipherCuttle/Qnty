"""H001 per-run coordinate and seed orchestration.

Caller-side derivation and binding of a specific run's logical coordinates
and seed material into the reviewed engine's pure functions
(``quantbot.experiment.h001_null_calibration_engine``), implemented here for
independent review only. This module is not wired into `execute_calibration`
or any control-state file, is never invoked by any caller in this
repository, and produces no calibration results. It performs no filesystem,
network, process, or repository-state access of any kind, requires no
real-data access, and carries no scientific, paper-trade, shadow, or live
authorization.

Scope, precisely: given a run's logical coordinate (a registered DGP or
diagnostic stress-case identifier plus an outer-replication index), produce
the exact, immutable, bounded set of engine-facing ``BootstrapCoordinate``
values that address every bootstrap replication of that run. No new seed
material, key derivation, or RNG rule is introduced here; every coordinate
constructed by this module is validated and keyed entirely by the
already-reviewed engine (``BootstrapCoordinate.__post_init__`` and the
engine's closed RNG interface). This module determines no execution order --
it produces a run's addressable coordinate set only.

Out of scope, governed separately, never absorbed here: execute_calibration
wiring, pipeline failure/partial-execution handling, calibration result
materialization, result provenance binding, calibration execution receipt
emission, calibration output verification, restart/duplicate/replay
prevention, and cleanup semantics for failed or partial runs.
"""
from __future__ import annotations

from dataclasses import dataclass

from quantbot.experiment.h001_null_calibration_engine import (
    BOOTSTRAP_REPETITIONS,
    BootstrapCoordinate,
)


@dataclass(frozen=True)
class RunCoordinate:
    """A single calibration run's logical identity: which registered DGP or
    diagnostic stress-case, and which outer replication.

    Bootstrap-replication identity is deliberately not part of a run's
    coordinate: a run addresses the full closed range of bootstrap
    replications, enumerated by ``bootstrap_coordinates_for_run`` below, not
    any single one of them.
    """

    dgp_or_case_id: str
    outer_replication_index: int

    def __post_init__(self) -> None:
        # Delegate every domain rule to the already-reviewed engine rather
        # than re-deriving it here: constructing a boundary probe coordinate
        # (bootstrap_replication_index=0, itself always in-domain) exercises
        # the engine's exact validation and raises its exact failure codes.
        BootstrapCoordinate(self.dgp_or_case_id, self.outer_replication_index, 0)


def bootstrap_coordinates_for_run(run: RunCoordinate) -> tuple[BootstrapCoordinate, ...]:
    """The exact, immutable, canonically-ordered set of engine-facing
    ``BootstrapCoordinate`` values for one run.

    Cardinality is exactly ``BOOTSTRAP_REPETITIONS``. The returned tuple is
    ordered by ascending ``bootstrap_replication_index``, but every
    coordinate's Philox key/counter material is fully self-contained --
    bound only to ``dgp_or_case_id``, ``outer_replication_index``, and its
    own ``bootstrap_replication_index`` -- so no computation the reviewed
    engine performs over these coordinates depends on the order in which
    they are produced or consumed.
    """
    if type(run) is not RunCoordinate:
        raise TypeError("bootstrap_coordinates_for_run requires a RunCoordinate")
    return tuple(
        BootstrapCoordinate(run.dgp_or_case_id, run.outer_replication_index, bootstrap_replication_index)
        for bootstrap_replication_index in range(BOOTSTRAP_REPETITIONS)
    )
