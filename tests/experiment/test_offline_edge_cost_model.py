"""Tests for quantbot/experiment/offline_edge_cost_model.py

PR C — fixture-only cost-model math.  Deterministic pure functions.
No exchange, engine, DB, or paper imports; no file writes.
"""

from __future__ import annotations

import ast
from pathlib import Path

import pytest

from quantbot.experiment.offline_edge_cost_model import (
    COST_MODEL_VERSION,
    calculate_commission_cost,
    calculate_fixture_funding_cost,
    calculate_round_trip_cost,
    calculate_slippage_cost,
    calculate_spread_cost,
)

# notional * bps / 10_000 → 100_000 * 5 / 10_000 == 50.0
TOL = 1e-9


# ── Per-side cost math ─────────────────────────────────────────────────────


class TestCommissionCost:
    def test_commission_math(self) -> None:
        assert calculate_commission_cost(100_000.0, 5.0) == pytest.approx(50.0, abs=TOL)

    def test_zero_notional_returns_zero(self) -> None:
        assert calculate_commission_cost(0.0, 5.0) == 0.0

    def test_zero_bps_returns_zero(self) -> None:
        assert calculate_commission_cost(100_000.0, 0.0) == 0.0

    def test_negative_notional_rejected(self) -> None:
        with pytest.raises(ValueError, match="notional"):
            calculate_commission_cost(-1.0, 5.0)

    def test_negative_bps_rejected(self) -> None:
        with pytest.raises(ValueError, match="commission_bps_per_side"):
            calculate_commission_cost(100_000.0, -1.0)


class TestSlippageCost:
    def test_slippage_math(self) -> None:
        assert calculate_slippage_cost(100_000.0, 5.0) == pytest.approx(50.0, abs=TOL)

    def test_zero_notional_returns_zero(self) -> None:
        assert calculate_slippage_cost(0.0, 5.0) == 0.0

    def test_negative_notional_rejected(self) -> None:
        with pytest.raises(ValueError, match="notional"):
            calculate_slippage_cost(-100.0, 5.0)

    def test_negative_bps_rejected(self) -> None:
        with pytest.raises(ValueError, match="slippage_bps_per_side"):
            calculate_slippage_cost(100_000.0, -0.5)


class TestSpreadCost:
    def test_spread_math(self) -> None:
        # 100_000 * 1 / 10_000 == 10.0
        assert calculate_spread_cost(100_000.0, 1.0) == pytest.approx(10.0, abs=TOL)

    def test_zero_notional_returns_zero(self) -> None:
        assert calculate_spread_cost(0.0, 1.0) == 0.0

    def test_negative_notional_rejected(self) -> None:
        with pytest.raises(ValueError, match="notional"):
            calculate_spread_cost(-100.0, 1.0)

    def test_negative_bps_rejected(self) -> None:
        with pytest.raises(ValueError, match="spread_bps_per_side"):
            calculate_spread_cost(100_000.0, -1.0)


# ── Round-trip aggregation ─────────────────────────────────────────────────


class TestRoundTripCost:
    def test_round_trip_components_and_total(self) -> None:
        result = calculate_round_trip_cost(
            notional=100_000.0,
            commission_bps_per_side=5.0,
            slippage_bps_per_side=5.0,
            spread_bps_per_side=1.0,
        )
        # Each per-side component doubled for entry + exit.
        assert result["commission_cost"] == pytest.approx(100.0, abs=TOL)
        assert result["slippage_cost"] == pytest.approx(100.0, abs=TOL)
        assert result["spread_cost"] == pytest.approx(20.0, abs=TOL)
        assert result["total_cost"] == pytest.approx(220.0, abs=TOL)
        # (5 + 5 + 1) * 2 == 22 bps round trip
        assert result["total_round_trip_bps"] == pytest.approx(22.0, abs=TOL)
        assert result["notional"] == 100_000.0
        assert result["cost_model_version"] == COST_MODEL_VERSION

    def test_round_trip_total_equals_sum_of_components(self) -> None:
        result = calculate_round_trip_cost(50_000.0, 3.0, 4.0, 2.0)
        expected_total = (
            result["commission_cost"]
            + result["slippage_cost"]
            + result["spread_cost"]
        )
        assert result["total_cost"] == pytest.approx(expected_total, abs=TOL)

    def test_round_trip_zero_notional_returns_zero(self) -> None:
        result = calculate_round_trip_cost(0.0, 5.0, 5.0, 1.0)
        assert result["total_cost"] == 0.0
        assert result["commission_cost"] == 0.0
        assert result["slippage_cost"] == 0.0
        assert result["spread_cost"] == 0.0

    def test_round_trip_negative_notional_rejected(self) -> None:
        with pytest.raises(ValueError, match="notional"):
            calculate_round_trip_cost(-1.0, 5.0, 5.0, 1.0)

    def test_round_trip_negative_bps_rejected(self) -> None:
        with pytest.raises(ValueError):
            calculate_round_trip_cost(100_000.0, 5.0, -5.0, 1.0)

    def test_round_trip_deterministic(self) -> None:
        a = calculate_round_trip_cost(100_000.0, 5.0, 5.0, 1.0)
        b = calculate_round_trip_cost(100_000.0, 5.0, 5.0, 1.0)
        assert a == b


# ── Optional fixture funding placeholder ───────────────────────────────────


class TestFixtureFundingCost:
    def test_positive_funding_rate(self) -> None:
        # funding paid: 100_000 * 0.0001 == 10.0
        assert calculate_fixture_funding_cost(100_000.0, 0.0001) == pytest.approx(
            10.0, abs=TOL
        )

    def test_negative_funding_rate_allowed(self) -> None:
        # funding received: negative rate is meaningful, not rejected
        assert calculate_fixture_funding_cost(100_000.0, -0.0001) == pytest.approx(
            -10.0, abs=TOL
        )

    def test_zero_notional_returns_zero(self) -> None:
        assert calculate_fixture_funding_cost(0.0, 0.0001) == 0.0

    def test_negative_notional_rejected(self) -> None:
        with pytest.raises(ValueError, match="notional"):
            calculate_fixture_funding_cost(-1.0, 0.0001)


# ── Import safety ──────────────────────────────────────────────────────────


class TestNoEngineOrExchangeImports:
    def test_no_forbidden_imports(self) -> None:
        """Cost-model module must not import engine/exchange/DB modules."""
        module_path = (
            Path(__file__).resolve().parent.parent.parent
            / "quantbot"
            / "experiment"
            / "offline_edge_cost_model.py"
        )
        assert module_path.exists(), f"Module not found: {module_path}"
        with open(module_path) as f:
            tree = ast.parse(f.read())

        forbidden_keywords = {
            "engine",
            "exchange",
            "ccxt",
            "sqlite",
            "sqlite3",
            "sqlalchemy",
            "django",
            "requests",
            "numpy",
            "pandas",
        }

        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    name = alias.name.split(".")[0]
                    assert name not in forbidden_keywords, (
                        f"Forbidden import '{alias.name}' in "
                        f"offline_edge_cost_model.py at line {node.lineno}"
                    )
            elif isinstance(node, ast.ImportFrom):
                if node.module:
                    name = node.module.split(".")[0]
                    assert name not in forbidden_keywords, (
                        f"Forbidden import '{node.module}' in "
                        f"offline_edge_cost_model.py at line {node.lineno}"
                    )

    def test_no_file_writes(self) -> None:
        """Module source must not open files for writing."""
        module_path = (
            Path(__file__).resolve().parent.parent.parent
            / "quantbot"
            / "experiment"
            / "offline_edge_cost_model.py"
        )
        source = module_path.read_text()
        assert "open(" not in source
        assert ".write(" not in source
        assert "Path(" not in source
