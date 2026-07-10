"""Fixture-only walk-forward / counterfactual replay scaffolding.

PR E — deterministic, tiny fixture-only walk-forward *scaffold* over fixture
bars.  Stdlib only (``math``, ``pathlib``) plus the sibling fixture-only helpers
in :mod:`quantbot.experiment.offline_edge_volnorm` and
:mod:`quantbot.experiment.offline_edge_cost_model`.  **No** engine, exchange,
DB, paper, live, backfill, or file-write imports.

Scope boundary (do not violate):
- These helpers split fixture bars into tiny deterministic train/test windows,
  reconstruct a fixture-only volnorm weight per split, apply fixture-only cost
  assumptions, and emit a toy replay summary.
- This is a *fixture-only mirror* of the walk-forward concept in
  ``quantbot.experiment.walkforward`` / ``walkforward_runner``.  It is
  intentionally NOT imported from those modules because they drag strategy,
  loader, gate, and engine dependencies.  This is not the full runner.
- These functions do **not** compute strategy performance / PnL, do **not**
  generate trades, do **not** call the paper engine, do **not** replay real or
  prod funding, do **not** create Lane B, and do **not** touch prod data.
- Any toy per-split number is labelled ``fixture_counterfactual_return`` — it is
  explicitly NOT ``pnl``, NOT ``strategy_performance``, NOT ``sharpe``, and NOT
  ``edge``.  Reconstructing it is NOT an edge/profit/live-readiness claim.
  EDGE_UNPROVEN / BLOCK_LIVE_INTEGRATION remain in force; long-only / 1x is the
  only assumed lane.
"""

from __future__ import annotations

from pathlib import Path

from quantbot.experiment.offline_edge_cost_model import (
    COST_MODEL_VERSION,
    calculate_round_trip_cost,
)
from quantbot.experiment.offline_edge_volnorm import (
    DEFAULT_HEAT_CAP,
    DEFAULT_VOL_FLOOR,
    DEFAULT_VOL_LOOKBACK_BARS,
    calculate_inverse_vol_weight,
    calculate_realized_volatility,
    calculate_simple_returns,
    parse_fixture_bars,
)

# Prod data root.  PR E is fixture-only and MUST NOT read prod data, so the
# helpers below fail closed on any path that resolves under this root.
PROD_BASE = Path("/srv/qnty")

# Version tag for the fixture-only walk-forward scaffold shape.  Distinct from
# the real walk-forward runner on purpose — this is a mirror, not the runner.
FIXTURE_WALKFORWARD_VERSION: str = "fixture-0.1"

# Fixture-only cost assumptions (bps per side).  Mirror the CLI receipt defaults.
# These are *assumptions* applied to a toy counterfactual only — not a live cost
# model and not applied to any real trade or ledger.
DEFAULT_COMMISSION_BPS_PER_SIDE: float = 5.0
DEFAULT_SLIPPAGE_BPS_PER_SIDE: float = 5.0
DEFAULT_SPREAD_BPS_PER_SIDE: float = 1.0

_BPS_DENOMINATOR: float = 10_000.0


def _refuse_prod_path(path: Path) -> None:
    """Raise ValueError if *path* resolves under the prod root ``/srv/qnty``.

    Uses path-boundary comparison on resolved parts (not a string prefix) so
    traversal (``/tmp/../../srv/qnty/...``) and sibling names (``/srv/qnty2``)
    are handled correctly.  Called before any file open to keep PR E fixture-only.
    """
    resolved = Path(path).resolve()
    prod = PROD_BASE.resolve()
    try:
        common = Path(*resolved.parts[: len(prod.parts)])
    except ValueError:
        return
    if common == prod:
        raise ValueError(f"Path resolves under prod path {PROD_BASE}: {path}")


# ── Split construction ─────────────────────────────────────────────────────


def build_fixture_splits(
    rows: list[dict], train_size: int, test_size: int
) -> list[dict]:
    """Build deterministic non-overlapping walk-forward splits over *rows*.

    Windows advance by ``test_size`` (step = test_size), mirroring the honest
    walk-forward split concept.  Each split is a plain dict of index bounds; no
    row data is copied so the result stays small and deterministic.

    Parameters
    ----------
    rows : list[dict]
        Parsed fixture bar rows (only their count / ordering is used here).
    train_size : int
        Number of rows in each train window (must be >= 2).
    test_size : int
        Number of rows in each test window (must be >= 1).

    Returns
    -------
    list[dict]
        One dict per split with ``split_index``, ``train_start``, ``train_end``,
        ``test_start``, ``test_end`` (half-open index ranges).

    Raises
    ------
    ValueError
        If ``train_size < 2``, ``test_size < 1``, or there are too few rows to
        form a single train+test window.
    """
    if train_size < 2:
        raise ValueError(f"train_size must be >= 2, got {train_size}")
    if test_size < 1:
        raise ValueError(f"test_size must be >= 1, got {test_size}")

    n = len(rows)
    window = train_size + test_size
    if n < window:
        raise ValueError(
            f"too few rows for a walk-forward split: need at least "
            f"{window} (train_size + test_size), got {n}"
        )

    splits: list[dict] = []
    position = 0
    split_index = 0
    step = test_size
    while position + window <= n:
        splits.append(
            {
                "split_index": split_index,
                "train_start": position,
                "train_end": position + train_size,
                "test_start": position + train_size,
                "test_end": position + train_size + test_size,
            }
        )
        position += step
        split_index += 1
    return splits


# ── Per-split fixture reconstruction ───────────────────────────────────────


def _fixture_round_trip_cost_fraction(
    commission_bps_per_side: float = DEFAULT_COMMISSION_BPS_PER_SIDE,
    slippage_bps_per_side: float = DEFAULT_SLIPPAGE_BPS_PER_SIDE,
    spread_bps_per_side: float = DEFAULT_SPREAD_BPS_PER_SIDE,
) -> float:
    """Round-trip cost as a fraction of notional, from fixture bps assumptions.

    Reuses the fixture-only cost-model helper with a unit notional so the result
    is a pure fraction (``total_round_trip_bps / 10_000``).  Not applied to any
    real trade — only to a toy counterfactual number.
    """
    breakdown = calculate_round_trip_cost(
        notional=1.0,
        commission_bps_per_side=commission_bps_per_side,
        slippage_bps_per_side=slippage_bps_per_side,
        spread_bps_per_side=spread_bps_per_side,
    )
    return breakdown["total_round_trip_bps"] / _BPS_DENOMINATOR


def _replay_one_split(
    closes: list[float],
    split: dict,
    vol_lookback_bars: int,
    vol_floor: float,
    heat_cap: float,
    cost_fraction: float,
) -> dict:
    """Reconstruct fixture weight + toy counterfactual for a single split.

    Fixture-only: reconstructs an inverse-vol weight from the *train* window and
    computes a toy ``fixture_counterfactual_return`` over the *test* window,
    net of the fixture cost assumption.  Not a PnL, not a trade, not an edge.
    """
    train_closes = closes[split["train_start"] : split["train_end"]]
    train_returns = calculate_simple_returns(train_closes)
    windowed = train_returns[-vol_lookback_bars:]
    volatility = calculate_realized_volatility(windowed, vol_floor=vol_floor)
    weight = calculate_inverse_vol_weight(volatility, heat_cap=heat_cap)

    # Toy counterfactual: hypothetical return of holding the reconstructed
    # weight across the test window (last train close -> last test close), net
    # of the fixture round-trip cost.  Deliberately NOT called pnl / edge.
    anchor_close = closes[split["train_end"] - 1]
    exit_close = closes[split["test_end"] - 1]
    test_window_return = exit_close / anchor_close - 1.0
    fixture_counterfactual_return = weight * (test_window_return - cost_fraction)

    return {
        "split_index": split["split_index"],
        "train_start": split["train_start"],
        "train_end": split["train_end"],
        "test_start": split["test_start"],
        "test_end": split["test_end"],
        "realized_volatility": volatility,
        "inverse_vol_weight": weight,
        "test_window_return": test_window_return,
        "round_trip_cost_fraction": cost_fraction,
        "fixture_counterfactual_return": fixture_counterfactual_return,
    }


def run_fixture_walkforward(
    path: Path,
    train_size: int = 3,
    test_size: int = 1,
    vol_lookback_bars: int = DEFAULT_VOL_LOOKBACK_BARS,
    vol_floor: float = DEFAULT_VOL_FLOOR,
    heat_cap: float = DEFAULT_HEAT_CAP,
) -> dict:
    """Run a deterministic fixture-only walk-forward replay over fixture bars.

    Parses fixture bars from *path*, builds tiny deterministic train/test
    splits, reconstructs a fixture volnorm weight per split, applies fixture-only
    cost assumptions, and returns a plain-dict summary.

    This is fixture-only scaffolding — NOT real strategy validation.  It computes
    no strategy PnL, generates no trades, calls no paper engine, replays no real
    funding, runs no full historical walk-forward, and creates no Lane B.

    Raises
    ------
    FileNotFoundError
        If *path* does not exist.
    ValueError
        On prod paths, missing/invalid bars, ``train_size < 2``, ``test_size <
        1``, too few rows for a split, or invalid vol params.
    """
    if vol_floor <= 0:
        raise ValueError(f"vol_floor must be > 0, got {vol_floor}")
    if heat_cap <= 0:
        raise ValueError(f"heat_cap must be > 0, got {heat_cap}")
    if vol_lookback_bars < 1:
        raise ValueError(f"vol_lookback_bars must be >= 1, got {vol_lookback_bars}")

    _refuse_prod_path(Path(path))
    bars = parse_fixture_bars(path)
    closes = [bar["close"] for bar in bars]

    splits = build_fixture_splits(bars, train_size, test_size)
    cost_fraction = _fixture_round_trip_cost_fraction()

    split_results: list[dict] = [
        _replay_one_split(
            closes,
            split,
            vol_lookback_bars=vol_lookback_bars,
            vol_floor=vol_floor,
            heat_cap=heat_cap,
            cost_fraction=cost_fraction,
        )
        for split in splits
    ]

    counterfactual_total = sum(
        r["fixture_counterfactual_return"] for r in split_results
    )
    counterfactual_mean = (
        counterfactual_total / len(split_results) if split_results else 0.0
    )

    return {
        "walkforward_version": FIXTURE_WALKFORWARD_VERSION,
        "source": (
            "fixture-only walk-forward replay (not full V2, not the real "
            "walk-forward runner, not strategy PnL)"
        ),
        "bar_count": len(bars),
        "train_size": train_size,
        "test_size": test_size,
        "split_count": len(split_results),
        "vol_lookback_bars": vol_lookback_bars,
        "vol_floor": vol_floor,
        "heat_cap": heat_cap,
        "cost_model_version": COST_MODEL_VERSION,
        "round_trip_cost_fraction": cost_fraction,
        "splits": split_results,
        "fixture_counterfactual_return_total": counterfactual_total,
        "fixture_counterfactual_return_mean": counterfactual_mean,
    }
