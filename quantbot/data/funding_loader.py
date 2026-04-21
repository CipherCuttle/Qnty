"""Funding rate loader utilities.

Loads 8h funding CSVs from data/{SYM}_8h_funding.csv and provides
fast lookup by (symbol, timestamp).

Funding rates are decimals (e.g. 0.0001 = 0.01%).
Per-bar cost = |funding_rate| * 3 (3 × 8h periods per day).
"""

from pathlib import Path

import pandas as pd

from quantbot.data.multi_asset_loader import SYMBOLS


def load_funding_csv(symbol: str) -> pd.DataFrame:
    """Load funding CSV for a single symbol.

    Args:
        symbol: e.g. "BTCUSDT"

    Returns:
        DataFrame with columns: dt (Timestamp, UTC-aware), fundingRate (float), abs_rate (float)
    """
    path = Path("data") / f"{symbol}_8h_funding.csv"
    df = pd.read_csv(path)
    # Parse as UTC-aware to match bar timestamps
    df["dt"] = pd.to_datetime(df["fundingTime"], unit="ms", utc=True)
    df["abs_rate"] = df["fundingRate"].abs()
    return df[["dt", "fundingRate", "abs_rate"]]


def load_all_funding() -> pd.DataFrame:
    """Load funding data for all 10 symbols.

    Returns:
        DataFrame with columns: symbol, dt, fundingRate, abs_rate
    """
    rows = []
    for symbol in SYMBOLS:
        path = Path("data") / f"{symbol}_8h_funding.csv"
        if not path.exists():
            continue
        df = load_funding_csv(symbol)
        df = df.copy()
        df["symbol"] = symbol
        rows.append(df)

    if not rows:
        return pd.DataFrame(columns=["symbol", "dt", "fundingRate", "abs_rate"])

    combined = pd.concat(rows, ignore_index=True)
    combined = combined.sort_values(["symbol", "dt"]).reset_index(drop=True)
    return combined


def get_funding_at(
    dt: pd.Timestamp,
    symbol: str,
    funding_df: pd.DataFrame,
) -> float:
    """Return funding rate for symbol at or before the given timestamp.

    Uses forward-fill logic: returns the most recent rate <= dt.

    Args:
        dt: Query timestamp
        symbol: e.g. "BTCUSDT"
        funding_df: DataFrame from load_all_funding()

    Returns:
        Funding rate (decimal, e.g. 0.0001), or 0.0 if no data available.
    """
    if funding_df is None or funding_df.empty:
        return 0.0

    sub = funding_df[funding_df["symbol"] == symbol]
    if sub.empty:
        return 0.0

    # Normalize dt to UTC-aware for comparison
    dt_utc = pd.Timestamp(dt, tz="UTC") if dt.tz is None else dt

    # Find rows at or before dt
    leq = sub[sub["dt"] <= dt_utc]
    if leq.empty:
        return 0.0

    return float(leq.iloc[-1]["fundingRate"])


def build_funding_lookup(funding_df: pd.DataFrame) -> dict[tuple[str, pd.Timestamp], float]:
    """Build a dict keyed by (symbol, dt) for O(1) funding lookups.

    Args:
        funding_df: DataFrame from load_all_funding()

    Returns:
        Dict mapping (symbol, dt) -> fundingRate
    """
    if funding_df is None or funding_df.empty:
        return {}

    lookup: dict[tuple[str, pd.Timestamp], float] = {}
    for _, row in funding_df.iterrows():
        dt_val = row["dt"]
        # Ensure UTC-aware timestamp for consistent key matching
        if dt_val.tz is None:
            dt_val = pd.Timestamp(dt_val, tz="UTC")
        key = (str(row["symbol"]), dt_val)
        lookup[key] = float(row["fundingRate"])
    return lookup


def get_funding_fast(
    symbol: str,
    dt: pd.Timestamp,
    lookup: dict[tuple[str, pd.Timestamp], float],
    funding_df: pd.DataFrame,
) -> float:
    """O(1) funding lookup using pre-built dict.

    Falls back to linear search if key not found.

    Args:
        symbol: e.g. "BTCUSDT"
        dt: Query timestamp
        lookup: Pre-built dict from build_funding_lookup()
        funding_df: Full DataFrame for fallback search

    Returns:
        Funding rate (decimal), or 0.0 if unavailable.
    """
    key = (symbol, dt)
    if key in lookup:
        return lookup[key]

    # Fallback: forward-fill from nearest prior
    return get_funding_at(dt, symbol, funding_df)
