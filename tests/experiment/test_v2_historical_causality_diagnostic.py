"""Synthetic diagnostic against original Qnty V2 historical validation and corrected adapter.

This is a test-only path: it loads neither external price data nor private artifacts.
Its purpose is falsifying the historical evaluator's causal accounting, NOT to
retroactively estimate V2's true historical profitability.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from math import isclose, log

import pandas as pd
import pytest

from quantbot.data.types import Bar as QntyBar
from quantbot.experiment.causal_v2_evaluation import (
    Bar as CausalBar,
    Config,
    evaluate,
)
from scripts.run_validation_v2 import run_validation_window


@pytest.mark.parametrize("asset_count", [1, 5])
def test_historical_v2_credits_same_bar_jump_that_causal_v2_cannot_earn(asset_count: int):
    symbols = ["BTCUSDT", "ETHUSDT", "SOLUSDT", "XRPUSDT", "BNBUSDT"][:asset_count]
    start = datetime(2026, 1, 1, tzinfo=timezone.utc)
    closes = [100.0] * 21 + [200.0] * 4
    opens = [100.0] * 22 + [200.0] * 3
    stamps = [(start + timedelta(hours=8 * i)).isoformat() for i in range(len(closes))]
    historical_bars = {
        symbol: [
            QntyBar(t, opening, max(opening, closing), min(opening, closing), closing, 1_000.0)
            for t, opening, closing in zip(stamps, opens, closes)
        ] for symbol in symbols
    }
    corrected_bars = {
        symbol: [CausalBar(t, opening, closing) for t, opening, closing in zip(stamps, opens, closes)]
        for symbol in symbols
    }

    # Diagnostic only: the historical evaluator uses no funding lookup, while
    # the corrected side receives explicit zero rates. No carry claim is made.
    historical = run_validation_window(
        historical_bars,
        pd.DataFrame(columns=["symbol", "dt", "fundingRate"]),
        None,
    )
    corrected = evaluate(
        corrected_bars,
        {(symbol, t): 0.0 for symbol in symbols for t in stamps},
        config=Config(fee_bps_per_side=0.0, slippage_bps_per_side=0.0),
        mode="v2",
    )
    phantom = log(2.0)
    assert isclose(historical["net_return"], phantom, abs_tol=1e-8)
    assert isclose(historical["per_bar_obs"][21]["weighted_return"], phantom, abs_tol=1e-8)
    # The original code sums constituent returns rather than normalizing
    # the benchmark to a 1x equally weighted exposure.
    assert isclose(historical["benchmark_return"], asset_count * phantom, abs_tol=1e-8)
    assert isclose(corrected.summary()["final_equity"], 10_000.0, abs_tol=1e-8)
    assert isclose(corrected.summary()["simple_return"], 0.0, abs_tol=1e-12)
    assert all(fill.decision_timestamp == stamps[21] for fill in corrected.fills)
    assert all(fill.fill_timestamp == stamps[22] for fill in corrected.fills)
    assert len(corrected.fills) == asset_count
