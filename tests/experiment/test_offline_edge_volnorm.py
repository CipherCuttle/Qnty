"""Tests for quantbot/experiment/offline_edge_volnorm.py

PR D — fixture-only V2 volnorm reconstruction.  Deterministic pure helpers.
No exchange, engine, DB, or paper imports; no file writes; no PnL.
"""

from __future__ import annotations

import ast
import json
from pathlib import Path

import pytest

from quantbot.experiment.offline_edge_volnorm import (
    FIXTURE_VOLNORM_VERSION,
    calculate_inverse_vol_weight,
    calculate_realized_volatility,
    calculate_simple_returns,
    parse_fixture_bars,
    reconstruct_fixture_volnorm_weights,
)

TOL = 1e-12

FIXTURE_DIR = Path("tests/fixtures/edge_validation_golden").resolve()
VOLNORM_BARS = FIXTURE_DIR / "sample_volnorm_bars.csv"
EXPECTED_WEIGHTS = FIXTURE_DIR / "expected_volnorm_weights.json"
MODULE_PATH = (
    Path(__file__).resolve().parent.parent.parent
    / "quantbot"
    / "experiment"
    / "offline_edge_volnorm.py"
)


# ── Fixture parsing ────────────────────────────────────────────────────────


class TestParseFixtureBars:
    def test_parses_fixture_bars(self) -> None:
        bars = parse_fixture_bars(VOLNORM_BARS)
        assert len(bars) == 6
        assert bars[0]["timestamp"] == 1000000000000
        assert bars[0]["close"] == 100.0
        assert bars[-1]["close"] == 104.0

    def test_missing_file_rejected(self) -> None:
        with pytest.raises(FileNotFoundError):
            parse_fixture_bars(FIXTURE_DIR / "does_not_exist.csv")

    def test_missing_bars_rejected(self, tmp_path: Path) -> None:
        p = tmp_path / "empty.csv"
        p.write_text("timestamp,open,high,low,close,volume\n")
        with pytest.raises(ValueError, match="no data rows"):
            parse_fixture_bars(p)

    def test_missing_close_column_rejected(self, tmp_path: Path) -> None:
        p = tmp_path / "nocol.csv"
        p.write_text("timestamp,open,high,low,volume\n1000,1,1,1,1\n")
        with pytest.raises(ValueError, match="close"):
            parse_fixture_bars(p)

    def test_non_monotonic_timestamps_rejected(self, tmp_path: Path) -> None:
        p = tmp_path / "nonmono.csv"
        p.write_text(
            "timestamp,close\n"
            "1000003600000,100.0\n"
            "1000000000000,101.0\n"
        )
        with pytest.raises(ValueError, match="[Nn]on-monotonic"):
            parse_fixture_bars(p)

    def test_duplicate_timestamps_rejected(self, tmp_path: Path) -> None:
        p = tmp_path / "dup.csv"
        p.write_text("timestamp,close\n1000,100.0\n1000,101.0\n")
        with pytest.raises(ValueError, match="[Nn]on-monotonic"):
            parse_fixture_bars(p)

    def test_null_close_rejected(self, tmp_path: Path) -> None:
        p = tmp_path / "null.csv"
        p.write_text("timestamp,close\n1000,100.0\n2000,\n")
        with pytest.raises(ValueError, match="[Nn]ull"):
            parse_fixture_bars(p)

    def test_invalid_close_rejected(self, tmp_path: Path) -> None:
        p = tmp_path / "bad.csv"
        p.write_text("timestamp,close\n1000,100.0\n2000,not_a_number\n")
        with pytest.raises(ValueError, match="[Ii]nvalid close"):
            parse_fixture_bars(p)

    def test_non_positive_close_rejected(self, tmp_path: Path) -> None:
        p = tmp_path / "neg.csv"
        p.write_text("timestamp,close\n1000,100.0\n2000,-5.0\n")
        with pytest.raises(ValueError, match="[Nn]on-positive"):
            parse_fixture_bars(p)


# ── Simple returns ─────────────────────────────────────────────────────────


class TestSimpleReturns:
    def test_simple_returns_math(self) -> None:
        returns = calculate_simple_returns([100.0, 110.0, 99.0])
        assert returns[0] == pytest.approx(0.1, abs=TOL)
        assert returns[1] == pytest.approx(-0.1, abs=TOL)

    def test_n_closes_yields_n_minus_one_returns(self) -> None:
        assert len(calculate_simple_returns([1.0, 2.0, 3.0, 4.0])) == 3

    def test_fewer_than_two_closes_rejected(self) -> None:
        with pytest.raises(ValueError, match="at least 2"):
            calculate_simple_returns([100.0])

    def test_deterministic(self) -> None:
        closes = [100.0, 101.0, 102.5, 101.0]
        assert calculate_simple_returns(closes) == calculate_simple_returns(closes)


# ── Realized volatility ────────────────────────────────────────────────────


class TestRealizedVolatility:
    def test_realized_volatility_deterministic(self) -> None:
        returns = [0.01, -0.02, 0.015, -0.005]
        a = calculate_realized_volatility(returns)
        b = calculate_realized_volatility(returns)
        assert a == b

    def test_known_sample_std(self) -> None:
        # Sample std dev (n-1) of [0.01, -0.01] == 0.01 * sqrt(2) ... compute:
        # mean=0, m2 = 0.01^2 + 0.01^2 = 2e-4, var = 2e-4/1, std = sqrt(2e-4)
        import math

        got = calculate_realized_volatility([0.01, -0.01])
        assert got == pytest.approx(math.sqrt(2e-4), abs=TOL)

    def test_floor_returned_for_fewer_than_two(self) -> None:
        assert calculate_realized_volatility([], vol_floor=1e-6) == 1e-6
        assert calculate_realized_volatility([0.05], vol_floor=1e-6) == 1e-6

    def test_floor_applied_to_tiny_vol(self) -> None:
        # Constant returns → zero variance → floored.
        assert calculate_realized_volatility([0.0, 0.0, 0.0], vol_floor=1e-3) == 1e-3

    def test_zero_vol_floor_rejected(self) -> None:
        with pytest.raises(ValueError, match="vol_floor"):
            calculate_realized_volatility([0.01, -0.01], vol_floor=0.0)

    def test_negative_vol_floor_rejected(self) -> None:
        with pytest.raises(ValueError, match="vol_floor"):
            calculate_realized_volatility([0.01, -0.01], vol_floor=-1e-6)


# ── Inverse-vol weight + heat cap clamp ────────────────────────────────────


class TestInverseVolWeight:
    def test_inverse_vol_weight_deterministic(self) -> None:
        assert calculate_inverse_vol_weight(0.5) == calculate_inverse_vol_weight(0.5)

    def test_inverse_vol_weight_math(self) -> None:
        # 1/0.5 == 2.0, but heat_cap default 1.0 clamps → 1.0
        assert calculate_inverse_vol_weight(0.5, heat_cap=10.0) == pytest.approx(
            2.0, abs=TOL
        )

    def test_heat_cap_clamp(self) -> None:
        # 1/0.01 == 100 → clamped to heat_cap 1.0
        assert calculate_inverse_vol_weight(0.01, heat_cap=1.0) == 1.0

    def test_no_clamp_when_below_cap(self) -> None:
        # 1/2.0 == 0.5 < heat_cap → unclamped
        assert calculate_inverse_vol_weight(2.0, heat_cap=1.0) == pytest.approx(
            0.5, abs=TOL
        )

    def test_zero_volatility_rejected(self) -> None:
        with pytest.raises(ValueError, match="volatility"):
            calculate_inverse_vol_weight(0.0)

    def test_negative_volatility_rejected(self) -> None:
        with pytest.raises(ValueError, match="volatility"):
            calculate_inverse_vol_weight(-0.1)

    def test_zero_heat_cap_rejected(self) -> None:
        with pytest.raises(ValueError, match="heat_cap"):
            calculate_inverse_vol_weight(0.5, heat_cap=0.0)


# ── Full reconstruction ────────────────────────────────────────────────────


class TestReconstructFixtureVolnormWeights:
    def test_matches_golden_fixture(self) -> None:
        got = reconstruct_fixture_volnorm_weights(VOLNORM_BARS)
        with open(EXPECTED_WEIGHTS) as f:
            expected = json.load(f)
        assert got["volnorm_version"] == expected["volnorm_version"]
        assert got["bar_count"] == expected["bar_count"]
        assert got["return_count"] == expected["return_count"]
        assert got["realized_volatility"] == pytest.approx(
            expected["realized_volatility"], abs=TOL
        )
        assert got["inverse_vol_weight"] == pytest.approx(
            expected["inverse_vol_weight"], abs=TOL
        )
        assert got["weight_clamped_to_heat_cap"] == expected["weight_clamped_to_heat_cap"]

    def test_deterministic(self) -> None:
        assert reconstruct_fixture_volnorm_weights(
            VOLNORM_BARS
        ) == reconstruct_fixture_volnorm_weights(VOLNORM_BARS)

    def test_version_tag(self) -> None:
        got = reconstruct_fixture_volnorm_weights(VOLNORM_BARS)
        assert got["volnorm_version"] == FIXTURE_VOLNORM_VERSION

    def test_weight_unclamped_with_large_heat_cap(self) -> None:
        got = reconstruct_fixture_volnorm_weights(VOLNORM_BARS, heat_cap=1000.0)
        # 1/vol is large but < 1000 → unclamped and > 1.0
        assert got["weight_clamped_to_heat_cap"] is False
        assert got["inverse_vol_weight"] > 1.0

    def test_missing_bars_rejected(self, tmp_path: Path) -> None:
        p = tmp_path / "empty.csv"
        p.write_text("timestamp,close\n")
        with pytest.raises(ValueError, match="no data rows"):
            reconstruct_fixture_volnorm_weights(p)

    def test_non_monotonic_rejected(self, tmp_path: Path) -> None:
        p = tmp_path / "nonmono.csv"
        p.write_text("timestamp,close\n2000,100.0\n1000,101.0\n")
        with pytest.raises(ValueError, match="[Nn]on-monotonic"):
            reconstruct_fixture_volnorm_weights(p)

    def test_zero_vol_floor_rejected(self) -> None:
        with pytest.raises(ValueError, match="vol_floor"):
            reconstruct_fixture_volnorm_weights(VOLNORM_BARS, vol_floor=0.0)

    def test_negative_vol_floor_rejected(self) -> None:
        with pytest.raises(ValueError, match="vol_floor"):
            reconstruct_fixture_volnorm_weights(VOLNORM_BARS, vol_floor=-1.0)

    def test_zero_heat_cap_rejected(self) -> None:
        with pytest.raises(ValueError, match="heat_cap"):
            reconstruct_fixture_volnorm_weights(VOLNORM_BARS, heat_cap=0.0)

    def test_bad_lookback_rejected(self) -> None:
        with pytest.raises(ValueError, match="vol_lookback_bars"):
            reconstruct_fixture_volnorm_weights(VOLNORM_BARS, vol_lookback_bars=0)

    def test_no_pnl_or_trade_keys(self) -> None:
        got = reconstruct_fixture_volnorm_weights(VOLNORM_BARS)
        for forbidden in ("pnl", "trades", "returns_pnl", "edge_candidate", "sharpe"):
            assert forbidden not in got


# ── Import safety ──────────────────────────────────────────────────────────


class TestNoEngineOrExchangeImports:
    def test_no_forbidden_imports(self) -> None:
        """Volnorm module must not import engine/exchange/DB/paper modules."""
        assert MODULE_PATH.exists(), f"Module not found: {MODULE_PATH}"
        tree = ast.parse(MODULE_PATH.read_text())

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
                        f"Forbidden import '{alias.name}' at line {node.lineno}"
                    )
            elif isinstance(node, ast.ImportFrom):
                if node.module:
                    name = node.module.split(".")[0]
                    assert name not in forbidden_keywords, (
                        f"Forbidden import '{node.module}' at line {node.lineno}"
                    )

    def test_no_paper_engine_import(self) -> None:
        """Must not *import* the real volnorm_portfolio or any paper/live module.

        The docstring may reference ``volnorm_portfolio`` to document that it is a
        mirror; only actual import statements are forbidden.
        """
        tree = ast.parse(MODULE_PATH.read_text())
        forbidden_substrings = ("volnorm_portfolio", "paper", "exec", "live")
        for node in ast.walk(tree):
            names: list[str] = []
            if isinstance(node, ast.Import):
                names = [alias.name for alias in node.names]
            elif isinstance(node, ast.ImportFrom) and node.module:
                names = [node.module]
            for name in names:
                for bad in forbidden_substrings:
                    assert bad not in name, f"Forbidden import '{name}'"

    def test_no_file_writes(self) -> None:
        """Module source must not open files for writing."""
        source = MODULE_PATH.read_text()
        assert ".write(" not in source
        assert '"w"' not in source
        assert "'w'" not in source
