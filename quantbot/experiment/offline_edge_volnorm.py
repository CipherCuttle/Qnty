"""Fixture-only V2 volnorm reconstruction helpers for offline edge validation.

PR D — deterministic, pure reconstruction of a volatility-normalized weight
object from *tiny fixture bar data only*.  Stdlib only (``csv``, ``math``,
``pathlib``).  **No** engine, exchange, DB, paper, live, or file-write imports.

Scope boundary (do not violate):
- These helpers parse a fixture bars CSV and rebuild a V2-*style* inverse-vol,
  heat-capped weight for a single instrument.  They are pure arithmetic over
  fixture rows read from disk.
- This is a *fixture-only mirror* of the concepts in
  ``quantbot.experiment.volnorm_portfolio`` (``HEAT_CAP``, ``VOL_LOOKBACK_BARS``,
  ``VOL_FLOOR``, inverse-vol sizing).  It is intentionally NOT imported from that
  module and it is NOT full V2: it computes a single-instrument realized-vol
  weight from simple returns, not the multi-symbol portfolio-heat scaling.
- These functions do **not** compute strategy performance / PnL, do **not**
  generate trades, do **not** call the paper engine, do **not** replay real or
  prod funding, do **not** run walk-forward, and do **not** touch prod data.
- Reconstructing a weight here is NOT an edge/profit/live-readiness claim.
  EDGE_UNPROVEN / BLOCK_LIVE_INTEGRATION remain in force; long-only / 1x is the
  only assumed lane.
"""

from __future__ import annotations

import csv
import math
from pathlib import Path

# Version of the fixture-only reconstruction shape.  Distinct from the real V2
# package version on purpose — this is a mirror, not full V2.
FIXTURE_VOLNORM_VERSION: str = "fixture-0.1"

# Concept defaults mirrored from volnorm_portfolio (not imported to avoid
# dragging any heavier dependency surface into the offline validator).
DEFAULT_VOL_LOOKBACK_BARS: int = 90
DEFAULT_VOL_FLOOR: float = 1e-6
DEFAULT_HEAT_CAP: float = 1.0


# ── Fixture parsing ────────────────────────────────────────────────────────


def parse_fixture_bars(path: Path) -> list[dict]:
    """Parse a fixture OHLCV bars CSV into a list of row dicts.

    Expects a header row with at least ``timestamp`` and ``close`` columns.
    Returns rows in file order with ``timestamp`` coerced to ``int`` and
    ``close`` coerced to ``float``.

    Raises
    ------
    FileNotFoundError
        If *path* does not exist.
    ValueError
        If the file has no header, no data rows (missing bars), is missing the
        required columns, contains a non-monotonic-increasing timestamp, or has
        a null/invalid ``close`` value.
    """
    path = Path(path)
    if not path.exists():
        raise FileNotFoundError(f"Fixture bars file does not exist: {path}")

    with open(path, newline="") as f:
        reader = csv.DictReader(f)
        if reader.fieldnames is None:
            raise ValueError(f"Fixture bars file has no header: {path}")
        fields = {name.strip() for name in reader.fieldnames}
        for required in ("timestamp", "close"):
            if required not in fields:
                raise ValueError(
                    f"Fixture bars file missing required column '{required}': {path}"
                )
        rows = list(reader)

    if not rows:
        raise ValueError(f"Fixture bars file has no data rows (missing bars): {path}")

    parsed: list[dict] = []
    prev_ts: int | None = None
    for i, row in enumerate(rows):
        raw_ts = (row.get("timestamp") or "").strip()
        raw_close = (row.get("close") or "").strip()
        if raw_ts == "":
            raise ValueError(f"Null/empty timestamp at row {i} in {path}")
        if raw_close == "":
            raise ValueError(f"Null/empty close at row {i} in {path}")
        try:
            ts = int(raw_ts)
        except ValueError as exc:
            raise ValueError(f"Invalid timestamp '{raw_ts}' at row {i} in {path}") from exc
        try:
            close = float(raw_close)
        except ValueError as exc:
            raise ValueError(f"Invalid close '{raw_close}' at row {i} in {path}") from exc
        if not math.isfinite(close):
            raise ValueError(f"Non-finite close '{raw_close}' at row {i} in {path}")
        if close <= 0:
            raise ValueError(f"Non-positive close {close} at row {i} in {path}")
        if prev_ts is not None and ts <= prev_ts:
            raise ValueError(
                f"Non-monotonic timestamp at row {i} in {path}: {ts} <= {prev_ts}"
            )
        prev_ts = ts
        parsed.append({"timestamp": ts, "close": close})

    return parsed


# ── Reconstruction math ────────────────────────────────────────────────────


def calculate_simple_returns(closes: list[float]) -> list[float]:
    """Simple period returns from a list of close prices.

    ``r[i] = closes[i + 1] / closes[i] - 1`` for consecutive closes.  A list of
    ``n`` closes yields ``n - 1`` returns.

    Raises
    ------
    ValueError
        If fewer than two closes are provided, or any close is non-positive /
        non-finite (which would make the ratio undefined).
    """
    if len(closes) < 2:
        raise ValueError(
            f"Need at least 2 closes to compute returns, got {len(closes)}"
        )
    returns: list[float] = []
    for prev, curr in zip(closes, closes[1:]):
        if not math.isfinite(prev) or prev <= 0:
            raise ValueError(f"Invalid prior close for return: {prev}")
        if not math.isfinite(curr):
            raise ValueError(f"Invalid close for return: {curr}")
        returns.append(curr / prev - 1.0)
    return returns


def calculate_realized_volatility(
    returns: list[float], vol_floor: float = DEFAULT_VOL_FLOOR
) -> float:
    """Sample standard deviation of *returns*, floored at *vol_floor*.

    Uses the (n-1) sample-variance convention, mirroring
    ``volnorm_portfolio.VolatilityTracker``.  With fewer than two returns the
    volatility is undefined, so the floor is returned.

    Raises
    ------
    ValueError
        If *vol_floor* is not strictly positive.
    """
    if vol_floor <= 0:
        raise ValueError(f"vol_floor must be > 0, got {vol_floor}")
    n = len(returns)
    if n < 2:
        return vol_floor
    mean = math.fsum(returns) / n
    m2 = math.fsum((r - mean) ** 2 for r in returns)
    variance = m2 / (n - 1)
    return max(math.sqrt(variance), vol_floor)


def calculate_inverse_vol_weight(
    volatility: float, heat_cap: float = DEFAULT_HEAT_CAP
) -> float:
    """Inverse-vol weight ``1 / volatility``, clamped to *heat_cap*.

    Mirrors the V2 concept that a position is sized proportionally to inverse
    volatility, with an explicit heat cap bounding the maximum weight.

    Raises
    ------
    ValueError
        If *volatility* is not strictly positive or *heat_cap* is not strictly
        positive.
    """
    if volatility <= 0:
        raise ValueError(f"volatility must be > 0, got {volatility}")
    if heat_cap <= 0:
        raise ValueError(f"heat_cap must be > 0, got {heat_cap}")
    raw = 1.0 / volatility
    return min(raw, heat_cap)


def reconstruct_fixture_volnorm_weights(
    path: Path,
    vol_lookback_bars: int = DEFAULT_VOL_LOOKBACK_BARS,
    vol_floor: float = DEFAULT_VOL_FLOOR,
    heat_cap: float = DEFAULT_HEAT_CAP,
) -> dict:
    """Rebuild a deterministic fixture-only V2-style volnorm weight object.

    Reads fixture bars from *path*, computes simple returns over the last
    ``vol_lookback_bars`` returns, estimates realized volatility, and derives an
    inverse-vol weight clamped to *heat_cap*.  Returns a plain dict summary.

    This is fixture-only reconstruction — NOT strategy validation.  It computes
    no PnL, generates no trades, and replays no funding.

    Raises
    ------
    FileNotFoundError
        If *path* does not exist.
    ValueError
        On missing bars, non-monotonic timestamps, null/invalid closes,
        non-positive *vol_floor*, non-positive *heat_cap*, or a
        *vol_lookback_bars* < 1.
    """
    if vol_floor <= 0:
        raise ValueError(f"vol_floor must be > 0, got {vol_floor}")
    if heat_cap <= 0:
        raise ValueError(f"heat_cap must be > 0, got {heat_cap}")
    if vol_lookback_bars < 1:
        raise ValueError(f"vol_lookback_bars must be >= 1, got {vol_lookback_bars}")

    bars = parse_fixture_bars(path)
    closes = [bar["close"] for bar in bars]
    returns = calculate_simple_returns(closes)

    # Keep only the trailing lookback window of returns (mirrors bounded buffer).
    windowed = returns[-vol_lookback_bars:]
    volatility = calculate_realized_volatility(windowed, vol_floor=vol_floor)
    weight = calculate_inverse_vol_weight(volatility, heat_cap=heat_cap)

    return {
        "volnorm_version": FIXTURE_VOLNORM_VERSION,
        "source": "fixture-only reconstruction (not full V2, not strategy PnL)",
        "bar_count": len(bars),
        "return_count": len(returns),
        "returns_used": len(windowed),
        "vol_lookback_bars": vol_lookback_bars,
        "vol_floor": vol_floor,
        "heat_cap": heat_cap,
        "realized_volatility": volatility,
        "inverse_vol_weight": weight,
        "weight_clamped_to_heat_cap": weight >= heat_cap,
    }
