"""Tests for quantbot/experiment/offline_edge_walkforward.py

PR E — fixture-only walk-forward / counterfactual replay scaffolding.
Deterministic pure helpers.  No exchange, engine, DB, or paper imports; no file
writes; no strategy PnL.
"""

from __future__ import annotations

import ast
import json
from pathlib import Path

import pytest

from quantbot.experiment.offline_edge_walkforward import (
    FIXTURE_WALKFORWARD_VERSION,
    build_fixture_splits,
    run_fixture_walkforward,
)

TOL = 1e-12

FIXTURE_DIR = Path("tests/fixtures/edge_validation_golden").resolve()
WALKFORWARD_BARS = FIXTURE_DIR / "sample_walkforward_bars.csv"
EXPECTED_SUMMARY = FIXTURE_DIR / "expected_walkforward_summary.json"
MODULE_PATH = (
    Path(__file__).resolve().parent.parent.parent
    / "quantbot"
    / "experiment"
    / "offline_edge_walkforward.py"
)


# ── Split construction ─────────────────────────────────────────────────────


class TestBuildFixtureSplits:
    def _rows(self, n: int) -> list[dict]:
        return [{"timestamp": i, "close": 100.0 + i} for i in range(n)]

    def test_deterministic_split_bounds(self) -> None:
        rows = self._rows(8)
        splits = build_fixture_splits(rows, train_size=3, test_size=1)
        assert splits == [
            {"split_index": 0, "train_start": 0, "train_end": 3, "test_start": 3, "test_end": 4},
            {"split_index": 1, "train_start": 1, "train_end": 4, "test_start": 4, "test_end": 5},
            {"split_index": 2, "train_start": 2, "train_end": 5, "test_start": 5, "test_end": 6},
            {"split_index": 3, "train_start": 3, "train_end": 6, "test_start": 6, "test_end": 7},
            {"split_index": 4, "train_start": 4, "train_end": 7, "test_start": 7, "test_end": 8},
        ]

    def test_deterministic_repeat(self) -> None:
        rows = self._rows(8)
        assert build_fixture_splits(rows, 3, 1) == build_fixture_splits(rows, 3, 1)

    def test_at_least_two_splits(self) -> None:
        rows = self._rows(8)
        assert len(build_fixture_splits(rows, 3, 1)) >= 2

    def test_step_equals_test_size(self) -> None:
        rows = self._rows(10)
        splits = build_fixture_splits(rows, train_size=3, test_size=2)
        # step = test_size = 2 → starts 0, 2, 4
        assert [s["train_start"] for s in splits] == [0, 2, 4]

    def test_too_few_rows_rejected(self) -> None:
        rows = self._rows(3)  # need train+test = 4
        with pytest.raises(ValueError, match="too few rows"):
            build_fixture_splits(rows, train_size=3, test_size=1)

    def test_train_size_below_two_rejected(self) -> None:
        rows = self._rows(8)
        with pytest.raises(ValueError, match="train_size"):
            build_fixture_splits(rows, train_size=1, test_size=1)

    def test_test_size_below_one_rejected(self) -> None:
        rows = self._rows(8)
        with pytest.raises(ValueError, match="test_size"):
            build_fixture_splits(rows, train_size=3, test_size=0)


# ── Prod-path refusal (fail closed; PR E is fixture-only) ──────────────────


class TestProdPathRefusal:
    def test_run_rejects_prod_path(self) -> None:
        with pytest.raises(ValueError, match="prod path"):
            run_fixture_walkforward(Path("/srv/qnty/bars/sample.csv"))

    def test_traversal_prod_path_rejected(self) -> None:
        with pytest.raises(ValueError, match="prod path"):
            run_fixture_walkforward(Path("/tmp/../../srv/qnty/bars/sample.csv"))

    def test_prod_base_itself_rejected(self) -> None:
        with pytest.raises(ValueError, match="prod path"):
            run_fixture_walkforward(Path("/srv/qnty"))

    def test_sibling_prefix_not_rejected(self) -> None:
        # /srv/qnty2 must NOT be treated as under /srv/qnty (boundary, not prefix).
        with pytest.raises(FileNotFoundError):
            run_fixture_walkforward(Path("/srv/qnty2/bars/sample.csv"))


# ── Full replay summary ────────────────────────────────────────────────────


class TestRunFixtureWalkforward:
    def test_matches_golden_summary(self) -> None:
        got = run_fixture_walkforward(WALKFORWARD_BARS)
        with open(EXPECTED_SUMMARY) as f:
            expected = json.load(f)
        assert got["walkforward_version"] == expected["walkforward_version"]
        assert got["bar_count"] == expected["bar_count"]
        assert got["train_size"] == expected["train_size"]
        assert got["test_size"] == expected["test_size"]
        assert got["split_count"] == expected["split_count"]
        assert got["cost_model_version"] == expected["cost_model_version"]
        assert got["round_trip_cost_fraction"] == pytest.approx(
            expected["round_trip_cost_fraction"], abs=TOL
        )
        assert got["fixture_counterfactual_return_total"] == pytest.approx(
            expected["fixture_counterfactual_return_total"], abs=TOL
        )
        assert got["fixture_counterfactual_return_mean"] == pytest.approx(
            expected["fixture_counterfactual_return_mean"], abs=TOL
        )

    def test_deterministic(self) -> None:
        assert run_fixture_walkforward(WALKFORWARD_BARS) == run_fixture_walkforward(
            WALKFORWARD_BARS
        )

    def test_version_tag(self) -> None:
        assert (
            run_fixture_walkforward(WALKFORWARD_BARS)["walkforward_version"]
            == FIXTURE_WALKFORWARD_VERSION
        )

    def test_summary_contains_split_count(self) -> None:
        got = run_fixture_walkforward(WALKFORWARD_BARS)
        assert "split_count" in got
        assert got["split_count"] >= 2

    def test_summary_has_fixture_counterfactual_labels(self) -> None:
        got = run_fixture_walkforward(WALKFORWARD_BARS)
        assert "fixture_counterfactual_return_total" in got
        for split in got["splits"]:
            assert "fixture_counterfactual_return" in split

    def test_summary_has_no_pnl_or_edge_keys(self) -> None:
        got = run_fixture_walkforward(WALKFORWARD_BARS)
        forbidden = ("pnl", "edge", "sharpe", "strategy_performance", "returns_pnl")
        # top-level keys
        for key in got:
            assert key not in forbidden
        # nested split keys
        for split in got["splits"]:
            for key in split:
                assert key not in forbidden

    def test_missing_bars_rejected(self, tmp_path: Path) -> None:
        p = tmp_path / "empty.csv"
        p.write_text("timestamp,close\n")
        with pytest.raises(ValueError, match="no data rows"):
            run_fixture_walkforward(p)

    def test_too_few_rows_rejected(self, tmp_path: Path) -> None:
        p = tmp_path / "tiny.csv"
        p.write_text("timestamp,close\n1000,100.0\n2000,101.0\n")
        with pytest.raises(ValueError, match="too few rows"):
            run_fixture_walkforward(p, train_size=3, test_size=1)

    def test_bad_train_size_rejected(self) -> None:
        with pytest.raises(ValueError, match="train_size"):
            run_fixture_walkforward(WALKFORWARD_BARS, train_size=1)

    def test_bad_test_size_rejected(self) -> None:
        with pytest.raises(ValueError, match="test_size"):
            run_fixture_walkforward(WALKFORWARD_BARS, test_size=0)

    def test_non_monotonic_rejected(self, tmp_path: Path) -> None:
        p = tmp_path / "nonmono.csv"
        p.write_text(
            "timestamp,close\n"
            "5000,100.0\n4000,101.0\n3000,102.0\n2000,103.0\n1000,104.0\n"
        )
        with pytest.raises(ValueError, match="[Nn]on-monotonic"):
            run_fixture_walkforward(p)


# ── Import safety ──────────────────────────────────────────────────────────


class TestNoEngineOrExchangeImports:
    def test_no_forbidden_imports(self) -> None:
        """Walk-forward module must not import engine/exchange/DB/paper modules."""
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

    def test_no_runner_or_paper_import(self) -> None:
        """Must not *import* the real walk-forward runner or any paper/live module.

        The docstring may reference ``walkforward_runner`` to document that it is
        a mirror; only actual import statements are forbidden.
        """
        tree = ast.parse(MODULE_PATH.read_text())
        forbidden_substrings = ("walkforward_runner", "paper", "exec", "live", "loaders")
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
