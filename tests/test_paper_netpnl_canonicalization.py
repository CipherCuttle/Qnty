"""Regression + invariant tests for net_pnl canonicalization.

Incident: paper-PnL failed closed when the engine computed net from unrounded
inputs and stored round(net, 8), while the in-tx verifier re-derives net from the
stored (independently rounded) gross/fees/funding columns and rejects at
ABS(net - (gross - fees - funding)) > 1e-8. On the failing trade the two paths
differed by exactly 1e-8.

The fix (quantbot/paper/engine.canonical_net_pnl) derives net from the same
rounded components that are persisted, so every stored row satisfies the verifier
invariant by construction. All paths here are pure / tmp_path -- no live data,
no VM, no /srv/qnty mutation.
"""

from __future__ import annotations

import random
import sqlite3
import sys
from pathlib import Path

# Ensure repo root is on sys.path (matches sibling paper tests).
REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from quantbot.paper.engine import canonical_net_pnl, _round8

# The strict gate the in-tx verifier enforces (quantbot/paper/sqlite_writer.py).
TOLERANCE = 1e-8

# The exact failing trade captured in the incident evidence.
FAILING_GROSS = -34.98456328
FAILING_FEES = 0.98250772
FAILING_FUNDING = 0.26784162
# Old (buggy) stored net, computed from unrounded inputs then rounded.
OLD_BUGGY_NET = -36.23491261
# Canonical net derived from the rounded components actually persisted.
CANONICAL_NET = -36.23491262


def _verifier_residual(net: float, gross: float, fees: float, funding: float) -> float:
    """Mirror the verifier predicate's left-hand side, on rounded components."""
    return abs(net - (_round8(gross) - _round8(fees) - _round8(funding)))


# --------------------------------------------------------------------------- (1)


def test_failing_row_canonical_net():
    """The exact incident row now canonicalizes to -36.23491262 and passes the gate."""
    net = canonical_net_pnl(FAILING_GROSS, FAILING_FEES, FAILING_FUNDING)
    assert net == CANONICAL_NET
    assert _verifier_residual(net, FAILING_GROSS, FAILING_FEES, FAILING_FUNDING) <= TOLERANCE


def test_old_buggy_net_would_have_failed():
    """Teeth check: the pre-fix stored net violates the verifier gate."""
    residual = _verifier_residual(
        OLD_BUGGY_NET, FAILING_GROSS, FAILING_FEES, FAILING_FUNDING
    )
    assert residual > TOLERANCE


# --------------------------------------------------------------------------- (2)


def test_invariant_holds_for_random_triples():
    """For arbitrary money triples, the canonical net always satisfies the gate."""
    rng = random.Random(20260618)  # seeded: deterministic
    for _ in range(50_000):
        gross = rng.uniform(-1e5, 1e5)
        fees = rng.uniform(0, 1e3)
        funding = rng.uniform(-1e3, 1e3)
        net = canonical_net_pnl(gross, fees, funding)
        assert _verifier_residual(net, gross, fees, funding) <= TOLERANCE


def test_invariant_holds_near_rounding_boundaries():
    """Golden cases: 9th-decimal values that force opposite rounding on net vs parts."""
    cases = [
        (1.000000005, 0.000000004, 0.000000004),
        (-1.000000005, 0.000000005, -0.000000005),
        (123.456789015, 0.123456785, 0.000000005),
        (0.000000015, 0.000000005, 0.000000005),
        (-999.999999995, 0.000000005, 0.000000005),
    ]
    for gross, fees, funding in cases:
        net = canonical_net_pnl(gross, fees, funding)
        assert _verifier_residual(net, gross, fees, funding) <= TOLERANCE


# --------------------------------------------------------------------------- (3)


def _verifier_predicate_flags(db_path: Path, batch_id: int) -> list:
    """Run the EXACT trade-arithmetic predicate from the writer against a fixture DB.

    Faithful to the production check: REAL-affinity columns, SQLite double
    arithmetic, strict > 1e-8 gate, joined through ledger_events by batch.
    """
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    try:
        return conn.execute(
            """
            SELECT t.seq, t.gross_pnl, t.fees, t.funding, t.net_pnl
            FROM trades t
            JOIN ledger_events e ON e.seq = t.seq
            WHERE e.batch_id = ?
              AND ABS(t.net_pnl - (t.gross_pnl - t.fees - t.funding)) > 1e-8
            """,
            (batch_id,),
        ).fetchall()
    finally:
        conn.close()


def _make_fixture_db(path: Path) -> None:
    conn = sqlite3.connect(path)
    conn.executescript(
        """
        CREATE TABLE ledger_events (seq INTEGER PRIMARY KEY, batch_id INTEGER NOT NULL);
        CREATE TABLE trades (
            seq        INTEGER PRIMARY KEY,
            gross_pnl  REAL NOT NULL,
            fees       REAL NOT NULL,
            funding    REAL NOT NULL,
            net_pnl    REAL NOT NULL
        );
        """
    )
    conn.commit()
    conn.close()


def test_reconcile_predicate_passes_on_canonical_row(tmp_path):
    """Writing the failing trade with the canonical net produces NO mismatch."""
    db = tmp_path / "fixture.db"
    _make_fixture_db(db)
    net = canonical_net_pnl(FAILING_GROSS, FAILING_FEES, FAILING_FUNDING)
    conn = sqlite3.connect(db)
    conn.execute("INSERT INTO ledger_events (seq, batch_id) VALUES (104, 13)")
    conn.execute(
        "INSERT INTO trades (seq, gross_pnl, fees, funding, net_pnl) VALUES (?,?,?,?,?)",
        (104, _round8(FAILING_GROSS), _round8(FAILING_FEES), _round8(FAILING_FUNDING), net),
    )
    conn.commit()
    conn.close()
    assert _verifier_predicate_flags(db, 13) == []


def test_reconcile_predicate_flags_old_buggy_row(tmp_path):
    """Negative control: the pre-fix net would have tripped the verifier."""
    db = tmp_path / "fixture_buggy.db"
    _make_fixture_db(db)
    conn = sqlite3.connect(db)
    conn.execute("INSERT INTO ledger_events (seq, batch_id) VALUES (104, 13)")
    conn.execute(
        "INSERT INTO trades (seq, gross_pnl, fees, funding, net_pnl) VALUES (?,?,?,?,?)",
        (104, _round8(FAILING_GROSS), _round8(FAILING_FEES), _round8(FAILING_FUNDING), OLD_BUGGY_NET),
    )
    conn.commit()
    conn.close()
    flagged = _verifier_predicate_flags(db, 13)
    assert len(flagged) == 1 and flagged[0]["seq"] == 104
