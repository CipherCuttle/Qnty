"""Real offline validation receipt skeleton for offline edge validation.

Scope boundary (do not violate) — see
docs/status/QNTY_OFFLINE_EDGE_VALIDATION_REAL_VALIDATION_EXECUTION_PLAN.md:

This module builds the *schema and first descriptive calculation scaffold*
for the real offline validation receipt. It only computes close-to-close gross
observational metadata. It does **not**:

- compute strategy, net, cost-adjusted, or funding-adjusted returns
- compute PnL
- compute Sharpe or any risk-adjusted metric
- run the paper engine
- import any live/exchange code
- emit ``OFFLINE_EDGE_CANDIDATE`` (that constant exists only for
  schema/refusal tests — see ``offline_edge_schema.py``)
- claim edge, profit, or live readiness

Every receipt built by this module has ``final_offline_verdict`` fixed to
``BLOCKED_BY_VALIDATION_IMPLEMENTATION`` and every
``forbidden_calculation_status`` flag fixed to ``False``. Stdlib only —
no pandas, numpy, engine, exchange, ccxt, sqlite, or paper imports.
"""

from __future__ import annotations

import argparse
import bisect
import csv
from decimal import Decimal, InvalidOperation
import hashlib
import json
import math
import os
import re
import subprocess
import sys
from collections import Counter
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import Any

from quantbot.experiment.offline_edge_schema import (
    BLOCKED_BY_DATA_QUALITY_REGRESSION,
    BLOCKED_BY_VALIDATION_IMPLEMENTATION,
    INCONCLUSIVE,
    NO_EDGE,
    OFFLINE_EDGE_CANDIDATE,
)

__all__ = [
    "build_real_validation_receipt",
    "build_deterministic_split_definitions",
    "build_cost_case_matrix",
    "validate_real_validation_receipt",
    "write_real_validation_receipt",
    "build_real_validation_input_inventory",
    "materialize_split_definitions_from_inventory",
    "materialize_input_rows_for_splits",
    "materialize_gross_observational_returns",
    "materialize_cost_case_observational_drag",
    "materialize_funding_observational_adjustments",
    "materialize_funding_to_bars_alignment_diagnostics",
    "materialize_funding_to_bars_temporal_joinability_diagnostics",
    "materialize_funding_to_bars_timestamp_convention_diagnostics",
    "materialize_funding_to_bars_timestamp_canonicalization_diagnostics",
    "materialize_funding_application_readiness_gate_diagnostics",
    "materialize_funding_adjusted_bars_scaffold_diagnostics",
    "materialize_funding_adjustment_policy_contract_diagnostics",
    "materialize_funding_adjustment_arithmetic_scaffold_diagnostics",
    "materialize_funding_adjustment_row_scaffold_diagnostics",
    "_build_split_leakage_audit_diagnostics",
    "materialize_strategy_rule_contract_instance_diagnostics",
    "_build_strategy_rule_contract_diagnostics",
    "_build_trial_manifest_diagnostics",
    "_build_oos_seal_diagnostics",
    "materialize_oos_seal_preregistration_diagnostics",
    "_derive_oos_seal_preregistration_gate",
    "_build_null_benchmark_contract_diagnostics",
    "materialize_null_benchmark_preregistration_diagnostics",
    "_derive_null_benchmark_preregistration_gate",
    "_build_multiple_testing_control_diagnostics",
    "_build_trade_position_simulation_contract_diagnostics",
    "_build_net_pnl_equity_risk_contract_diagnostics",
    "_build_final_offline_edge_verdict_logic_diagnostics",
    "_derive_strategy_rule_contract_packet_gate",
]

RECEIPT_SCHEMA_KIND: str = "qnty_offline_edge_real_validation_receipt"
RECEIPT_SCHEMA_VERSION: str = "0.1.0"

# Only these final verdicts are recognized by this schema's validator.
ALLOWED_FINAL_VERDICTS = frozenset(
    {
        OFFLINE_EDGE_CANDIDATE,
        NO_EDGE,
        INCONCLUSIVE,
        BLOCKED_BY_VALIDATION_IMPLEMENTATION,
        BLOCKED_BY_DATA_QUALITY_REGRESSION,
    }
)

# This PR (receipt skeleton) may only ever emit this verdict.
_SKELETON_ALLOWED_VERDICTS = frozenset({BLOCKED_BY_VALIDATION_IMPLEMENTATION})

# Top-level keys that must never appear on a receipt from this module.
FORBIDDEN_TOP_LEVEL_KEYS = frozenset({"pnl", "sharpe", "edge", "strategy_performance"})

# Keys that must never appear at any nesting level in a receipt.
# Matched by exact dict-key equality only (no substring/prefix/regex/case folding).
# OFFLINE_EDGE_CANDIDATE / EDGE_CANDIDATE are listed as forbidden *dict keys* only --
# defense-in-depth against verdict-named maps. Verdict control itself is owned by
# ALLOWED_FINAL_VERDICTS / _SKELETON_ALLOWED_VERDICTS, not by this set.
FORBIDDEN_CALCULATION_KEYS = frozenset(
    {
        "pnl",
        "sharpe",
        "edge",
        "strategy_performance",
        "return",
        "returns",
        "gross_observational_return",
        "gross_return_value",
        "net_return_value",
        "cost_adjusted_return",
        "funding_adjusted_return",
        "price_change",
        "trade",
        "trades",
        "signal",
        "signals",
        "position",
        "positions",
        "portfolio",
        "live_ready",
        "deploy_ready",
        "profitable",
        "drawdown",
        "risk",
        "baseline_result",
        "benchmark_result",
        "OFFLINE_EDGE_CANDIDATE",
        "EDGE_CANDIDATE",
        "p_value",
        "confidence_interval",
        "score",
        "metric",
        "performance",
        "profit",
        "order",
        "orders",
        "fill",
        "fills",
        "execution",
        "executions",
        "equity",
        "equity_curve",
    }
)

# === Scaffold readiness gate constants ===
FUNDING_APPLICATION_READINESS_GATE_DIAGNOSTIC_ONLY = "FUNDING_APPLICATION_READINESS_GATE_DIAGNOSTIC_ONLY"
NOT_EXECUTED = "NOT_EXECUTED"
STRICT_CANONICAL_TIMESTAMP_EXACT_MATCH_NO_COLLISION_NO_AMBIGUITY = "STRICT_CANONICAL_TIMESTAMP_EXACT_MATCH_NO_COLLISION_NO_AMBIGUITY"
FLOOR_TO_SECOND = "floor_to_second"
ELIGIBLE_FOR_FUTURE_FUNDING_APPLICATION = "ELIGIBLE_FOR_FUTURE_FUNDING_APPLICATION"
BLOCKED_FOR_FUTURE_FUNDING_APPLICATION = "BLOCKED_FOR_FUTURE_FUNDING_APPLICATION"
EXACT_CANONICAL_TIMESTAMP_SET_MATCH = "EXACT_CANONICAL_TIMESTAMP_SET_MATCH"
MATCHING_RANGES = "MATCHING_RANGES"
SKIPPED_BY_READINESS_GATE = "SKIPPED_BY_READINESS_GATE"
EMPTY_BOTH_NOT_BLOCKING = "EMPTY_BOTH_NOT_BLOCKING"

_VALID_READINESS_STATUSES = {
    ELIGIBLE_FOR_FUTURE_FUNDING_APPLICATION,
    BLOCKED_FOR_FUTURE_FUNDING_APPLICATION,
}

# === Funding adjustment policy contract constants ===
FUNDING_ADJUSTMENT_POLICY_CONTRACT_DIAGNOSTIC_ONLY = "FUNDING_ADJUSTMENT_POLICY_CONTRACT_DIAGNOSTIC_ONLY"
FUNDING_ADJUSTED_BARS_SCAFFOLD_DIAGNOSTIC_ONLY = "FUNDING_ADJUSTED_BARS_SCAFFOLD_DIAGNOSTIC_ONLY"
DIAGNOSTIC_SCAFFOLD_ONLY_NOT_APPLIED_TO_STRATEGY = "DIAGNOSTIC_SCAFFOLD_ONLY_NOT_APPLIED_TO_STRATEGY"
MATERIALIZED_DIAGNOSTIC_ROWS = "MATERIALIZED_DIAGNOSTIC_ROWS"
ELIGIBLE_FOR_FUTURE_FUNDING_ADJUSTMENT_POLICY = "ELIGIBLE_FOR_FUTURE_FUNDING_ADJUSTMENT_POLICY"
BLOCKED_BY_READINESS_GATE = "BLOCKED_BY_READINESS_GATE"
EXACT_CANONICAL_FUNDING_TIMESTAMP_TO_BAR_TIMESTAMP = "EXACT_CANONICAL_FUNDING_TIMESTAMP_TO_BAR_TIMESTAMP"

# === Funding adjustment arithmetic scaffold constants ===
FUNDING_ADJUSTMENT_ARITHMETIC_SCAFFOLD_DIAGNOSTIC_ONLY = "FUNDING_ADJUSTMENT_ARITHMETIC_SCAFFOLD_DIAGNOSTIC_ONLY"
FIXTURE_ONLY_NOT_APPLIED_TO_STRATEGY = "FIXTURE_ONLY_NOT_APPLIED_TO_STRATEGY"
LONG_NEGATES_FUNDING_RATE_SHORT_PRESERVES_FUNDING_RATE_TIMES_NOTIONAL = "LONG_NEGATES_FUNDING_RATE_SHORT_PRESERVES_FUNDING_RATE_TIMES_NOTIONAL"
EXPLICIT_FIXTURE_ONLY = "EXPLICIT_FIXTURE_ONLY"

# === Funding adjustment row scaffold constants ===
FUNDING_ADJUSTMENT_ROW_SCAFFOLD_DIAGNOSTIC_ONLY = "FUNDING_ADJUSTMENT_ROW_SCAFFOLD_DIAGNOSTIC_ONLY"
DIAGNOSTIC_ROW_SCAFFOLD_ONLY_NOT_APPLIED_TO_STRATEGY = "DIAGNOSTIC_ROW_SCAFFOLD_ONLY_NOT_APPLIED_TO_STRATEGY"

# === Funding adjustment sample aggregate diagnostics constants ===
FUNDING_ADJUSTMENT_SAMPLE_AGGREGATE_DIAGNOSTIC_ONLY = "FUNDING_ADJUSTMENT_SAMPLE_AGGREGATE_DIAGNOSTIC_ONLY"
DIAGNOSTIC_SAMPLE_AGGREGATE_ONLY_NOT_APPLIED_TO_STRATEGY = "DIAGNOSTIC_SAMPLE_AGGREGATE_ONLY_NOT_APPLIED_TO_STRATEGY"
MATERIALIZED_DIAGNOSTIC_SAMPLE_AGGREGATES = "MATERIALIZED_DIAGNOSTIC_SAMPLE_AGGREGATES"
DIAGNOSTIC_CAPPED_SAMPLE_AGGREGATE_ONLY_NOT_STRATEGY = "DIAGNOSTIC_CAPPED_SAMPLE_AGGREGATE_ONLY_NOT_STRATEGY"

# === Split leakage audit diagnostics constants ===
# Diagnostic-only audit of the current split windows' leakage posture. It
# records that the existing deterministic splits are NOT safe for strategy
# scoring / OOS verdicts (zero purge gap, zero embargo gap, no scoring
# prerequisites, no OOS seal / trial manifest / frozen symbol universe). It
# implements no purge/embargo splits, no OOS seal, no trial manifest, and no
# strategy — and computes no returns/PnL/Sharpe/risk/edge.
SPLIT_LEAKAGE_AUDIT_VERSION = "split-leakage-audit-0.1"
SPLIT_LEAKAGE_AUDIT_DIAGNOSTIC_ONLY = "SPLIT_LEAKAGE_AUDIT_DIAGNOSTIC_ONLY"
SPLIT_LEAKAGE_AUDIT_INSUFFICIENT_FOR_SCORING = (
    "SPLIT_LEAKAGE_AUDIT_INSUFFICIENT_FOR_SCORING"
)
SPLIT_LEAKAGE_AUDIT_BLOCKED = "SPLIT_LEAKAGE_AUDIT_BLOCKED"
SPLIT_LEAKAGE_AUDIT_ROW_COUNT_NOT_COMPUTED = "NOT_COMPUTED_IN_SPLIT_LEAKAGE_AUDIT"
_SPLIT_BUILDER_INVENTORY = "materialize_split_definitions_from_inventory"
_SPLIT_BUILDER_FALLBACK = "build_deterministic_split_definitions"
_VALID_SPLIT_BUILDERS = frozenset({_SPLIT_BUILDER_INVENTORY, _SPLIT_BUILDER_FALLBACK})

# === Strategy rule contract diagnostics constants ===
# Diagnostic-only section that records that no strategy rule contract exists
# yet and therefore strategy scoring is blocked. It does not define a strategy,
# generate signals, or compute returns/PnL/Sharpe/risk/edge. Every field is
# either None, NOT_DEFINED, or False — this is a diagnostic of absence, not a
# definition of presence.
STRATEGY_RULE_CONTRACT_VERSION = "strategy-rule-contract-0.1"
STRATEGY_RULE_CONTRACT_DIAGNOSTIC_ONLY = "STRATEGY_RULE_CONTRACT_DIAGNOSTIC_ONLY"
STRATEGY_RULE_CONTRACT_NOT_DEFINED = "CONTRACT_NOT_DEFINED"
STRATEGY_RULE_CONTRACT_BLOCKED_REASON_NOT_DEFINED = "STRATEGY_RULE_CONTRACT_NOT_DEFINED"
STRATEGY_RULE_CONTRACT_LOADED_DIAGNOSTIC_ONLY = "STRATEGY_RULE_CONTRACT_LOADED_DIAGNOSTIC_ONLY"
STRATEGY_RULE_CONTRACT_LOADED_AND_HASH_CHECKED = "CONTRACT_LOADED_AND_HASH_CHECKED"
STRATEGY_RULE_CONTRACT_BLOCKED_REASON_INSTANCE_READ_ONLY = "CONTRACT_INSTANCE_READ_ONLY_DIAGNOSTIC"
NOT_DEFINED = "NOT_DEFINED"

# === Trial manifest diagnostics constants ===
TRIAL_MANIFEST_VERSION = "trial-manifest-0.1"
TRIAL_MANIFEST_DIAGNOSTIC_ONLY = "TRIAL_MANIFEST_DIAGNOSTIC_ONLY"
TRIAL_MANIFEST_NOT_DEFINED = "TRIAL_MANIFEST_NOT_DEFINED"
TRIAL_MANIFEST_BLOCKED_REASON_NOT_DEFINED = "TRIAL_MANIFEST_NOT_DEFINED"

_REQUIRED_FALSE_TRIAL_MANIFEST_FIELDS: tuple[str, ...] = (
    "trial_execution_authorized",
    "scoring_authorization",
    "live_integration_authorized",
    "paper_integration_authorized",
    "final_verdict_authorization",
    "oos_seal_dependency_satisfied",
    "null_benchmark_dependency_satisfied",
    "multiple_testing_dependency_satisfied",
    "trade_position_simulation_dependency_satisfied",
    "net_pnl_equity_risk_dependency_satisfied",
)

# === OOS seal diagnostics constants ===
OOS_SEAL_VERSION = "oos-seal-0.1"
OOS_SEAL_DIAGNOSTIC_ONLY = "OOS_SEAL_DIAGNOSTIC_ONLY"
OOS_SEAL_NOT_DEFINED = "OOS_SEAL_NOT_DEFINED"
OOS_SEAL_BLOCKED_REASON_NOT_DEFINED = "OOS_SEAL_NOT_DEFINED"
OOS_SEAL_PREREGISTERED_DIAGNOSTIC_ONLY = "OOS_SEAL_PREREGISTERED_DIAGNOSTIC_ONLY"

_REQUIRED_FALSE_OOS_SEAL_FIELDS: tuple[str, ...] = (
    "split_mutation_authorized",
    "oos_scoring_authorized",
    "trial_execution_authorized",
    "scoring_authorization",
    "live_integration_authorized",
    "paper_integration_authorized",
    "final_verdict_authorization",
    "null_benchmark_dependency_satisfied",
    "multiple_testing_dependency_satisfied",
    "trade_position_simulation_dependency_satisfied",
    "net_pnl_equity_risk_dependency_satisfied",
)

# === Null benchmark contract diagnostics constants ===
NULL_BENCHMARK_CONTRACT_VERSION = "null-benchmark-contract-0.1"
NULL_BENCHMARK_CONTRACT_DIAGNOSTIC_ONLY = "NULL_BENCHMARK_CONTRACT_DIAGNOSTIC_ONLY"
NULL_BENCHMARK_CONTRACT_NOT_DEFINED = "NULL_BENCHMARK_CONTRACT_NOT_DEFINED"
NULL_BENCHMARK_CONTRACT_BLOCKED_REASON_NOT_DEFINED = "NULL_BENCHMARK_CONTRACT_NOT_DEFINED"
NULL_BENCHMARK_PREREGISTERED_DIAGNOSTIC_ONLY = (
    "NULL_BENCHMARK_PREREGISTERED_DIAGNOSTIC_ONLY"
)

_REQUIRED_FALSE_NULL_BENCHMARK_FIELDS: tuple[str, ...] = (
    "null_generation_authorized",
    "candidate_comparison_authorized",
    "trial_execution_authorized",
    "oos_scoring_authorized",
    "scoring_authorization",
    "live_integration_authorized",
    "paper_integration_authorized",
    "final_verdict_authorization",
    "multiple_testing_dependency_satisfied",
    "trade_position_simulation_dependency_satisfied",
    "net_pnl_equity_risk_dependency_satisfied",
)

# === Multiple testing control diagnostics constants ===
MULTIPLE_TESTING_CONTROL_VERSION = "multiple-testing-control-0.1"
MULTIPLE_TESTING_CONTROL_DIAGNOSTIC_ONLY = "MULTIPLE_TESTING_CONTROL_DIAGNOSTIC_ONLY"
MULTIPLE_TESTING_CONTROL_NOT_DEFINED = "MULTIPLE_TESTING_CONTROL_NOT_DEFINED"
MULTIPLE_TESTING_CONTROL_BLOCKED_REASON_NOT_DEFINED = "MULTIPLE_TESTING_CONTROL_NOT_DEFINED"

# === Trade position simulation contract diagnostics constants ===
# Diagnostic-only section that records that no trade/position simulation
# contract exists yet, no simulator policies are defined, and simulation-based
# scoring remains unauthorized. It does not define a simulator, generate
# signals, implement trades/positions/orders/fills/execution, or compute
# returns/PnL/Sharpe/risk/edge/portfolio values. Every field is either None,
# NOT_DEFINED, or False — this is a diagnostic of absence, not a definition
# of presence.
TRADE_POSITION_SIMULATION_CONTRACT_VERSION = "trade-position-simulation-contract-0.1"
TRADE_POSITION_SIMULATION_CONTRACT_DIAGNOSTIC_ONLY = "TRADE_POSITION_SIMULATION_CONTRACT_DIAGNOSTIC_ONLY"
TRADE_POSITION_SIMULATION_CONTRACT_NOT_DEFINED = "TRADE_POSITION_SIMULATION_CONTRACT_NOT_DEFINED"
TRADE_POSITION_SIMULATION_CONTRACT_BLOCKED_REASON_NOT_DEFINED = "TRADE_POSITION_SIMULATION_CONTRACT_NOT_DEFINED"

# === Net PnL / equity / risk contract diagnostics constants ===
# Diagnostic-only section that records that no net PnL/equity/risk contract
# exists yet, no accounting/risk policies are defined, and scoring remains
# unauthorized. It does not define a capital base, accounting policy, equity
# curve policy, drawdown policy, risk measure, or any computed metric. Every
# field is either None, NOT_DEFINED, or False — this is a diagnostic of
# absence, not a definition of presence.
NET_PNL_EQUITY_RISK_CONTRACT_VERSION = "net-pnl-equity-risk-contract-0.1"
NET_PNL_EQUITY_RISK_CONTRACT_DIAGNOSTIC_ONLY = "NET_PNL_EQUITY_RISK_CONTRACT_DIAGNOSTIC_ONLY"
NET_PNL_EQUITY_RISK_CONTRACT_NOT_DEFINED = "NET_PNL_EQUITY_RISK_CONTRACT_NOT_DEFINED"
NET_PNL_EQUITY_RISK_CONTRACT_BLOCKED_REASON_NOT_DEFINED = "NET_PNL_EQUITY_RISK_CONTRACT_NOT_DEFINED"

# === Final offline-edge verdict logic diagnostics constants ===
# Diagnostic-only section that records that final offline-edge scoring and
# verdict advancement remain blocked because every decisive upstream gate is
# still NOT_DEFINED or unsafe. It is a *static absence record*: it does not
# read sibling receipt sections, does not derive readiness dynamically, does
# not score anything, and does not advance ``final_offline_verdict``. It
# implements no strategy, signals, trades, positions, orders, fills,
# execution, returns, PnL, equity, drawdown, risk, edge, or benchmark
# comparison. Every field is either a NOT_DEFINED marker or ``False`` — this
# is a diagnostic of absence, not a definition of presence.
FINAL_OFFLINE_EDGE_VERDICT_LOGIC_VERSION = "final-offline-edge-verdict-logic-0.1"
FINAL_OFFLINE_EDGE_VERDICT_LOGIC_DIAGNOSTIC_ONLY = "FINAL_OFFLINE_EDGE_VERDICT_LOGIC_DIAGNOSTIC_ONLY"
FINAL_OFFLINE_EDGE_VERDICT_LOGIC_BLOCKED = "FINAL_OFFLINE_EDGE_VERDICT_LOGIC_BLOCKED"
FINAL_VERDICT_ADVANCEMENT_BLOCKED_REASON = "UPSTREAM_VALIDATION_CONTRACTS_NOT_DEFINED"
FINAL_VERDICT_SPLIT_SCORING_NOT_SAFE = "SPLIT_SCORING_NOT_SAFE"
UPSTREAM_REDUCTION_MODE_STATIC = "STATIC_ABSENCE_RECORD_NO_UPSTREAM_INTROSPECTION"

# Deterministic in-code fixture rows proving the funding cashflow sign
# convention from funding_adjustment_policy_contract_diagnostics. Inputs and
# expected outputs are both hardcoded here so a future edit to the formula
# that silently breaks the sign convention fails closed instead of passing.
_FUNDING_ARITHMETIC_FIXTURE_CASES: tuple[dict[str, Any], ...] = (
    {
        "case_id": "case_1_long_positive_funding",
        "side": "LONG",
        "funding_rate": 0.01,
        "notional_per_unit": 100,
        "expected_cashflow_per_notional_unit": "-1.0",
    },
    {
        "case_id": "case_2_long_negative_funding",
        "side": "LONG",
        "funding_rate": -0.01,
        "notional_per_unit": 100,
        "expected_cashflow_per_notional_unit": "1.0",
    },
    {
        "case_id": "case_3_short_positive_funding",
        "side": "SHORT",
        "funding_rate": 0.01,
        "notional_per_unit": 100,
        "expected_cashflow_per_notional_unit": "1.0",
    },
    {
        "case_id": "case_4_short_negative_funding",
        "side": "SHORT",
        "funding_rate": -0.01,
        "notional_per_unit": 100,
        "expected_cashflow_per_notional_unit": "-1.0",
    },
    {
        "case_id": "case_5_long_zero_funding",
        "side": "LONG",
        "funding_rate": 0.0,
        "notional_per_unit": 100,
        "expected_cashflow_per_notional_unit": "0.0",
    },
    {
        "case_id": "case_6_short_zero_funding",
        "side": "SHORT",
        "funding_rate": 0.0,
        "notional_per_unit": 100,
        "expected_cashflow_per_notional_unit": "0.0",
    },
)

PROD_BASE = Path("/srv/qnty")
TMP_BASE = Path("/tmp")


# ── Path guards ─────────────────────────────────────────────────────────


def _resolve(path: Path) -> Path:
    return path.resolve()


def _is_under(resolved: Path, base: Path) -> bool:
    base_resolved = base.resolve()
    try:
        common = os.path.commonpath([str(resolved), str(base_resolved)])
    except ValueError:
        return False
    return common == str(base_resolved)


def _refuse_if_prod_path(resolved: Path) -> None:
    if _is_under(resolved, PROD_BASE):
        raise ValueError(f"Refusing path under prod base {PROD_BASE}: {resolved}")


def _refuse_if_not_tmp(resolved: Path) -> None:
    if not _is_under(resolved, TMP_BASE):
        raise ValueError(f"Refusing path not under /tmp: {resolved}")


def _assert_no_prod_paths_in_receipt(value: Any, path: str = "$") -> None:
    """Recursively scan *value* for any occurrence of PROD_BASE (/srv/qnty).

    Scans dict values, list/tuple values, and string values.

    For strings:
    - If the string contains ``/srv/qnty/`` as a substring, reject immediately
      with ``AssertionError``.
    - If the string looks like an absolute path, resolve it via ``_resolve``
      and reject if it resolves under ``PROD_BASE`` using
      ``os.path.commonpath`` boundary logic.
    - Sibling safety: ``/srv/qnty2`` must NOT be falsely rejected by the
      boundary check (``/srv/qnty/`` with trailing slash avoids false
      positives on ``/srv/qnty2/...``).

    For other types (int, float, bool, None): skip.
    """
    if isinstance(value, str):
        # Raw substring check with trailing slash for sibling safety.
        if "/srv/qnty/" in value:
            raise AssertionError(
                f"Receipt field {path!r} contains PROD_BASE path: {value!r}"
            )
        # Boundary check for absolute paths.
        if value.startswith("/"):
            try:
                resolved = _resolve(Path(value))
                if _is_under(resolved, PROD_BASE):
                    raise AssertionError(
                        f"Receipt field {path!r} resolves under PROD_BASE: {value!r}"
                    )
            except (OSError, ValueError):
                pass
    elif isinstance(value, dict):
        for key, v in value.items():
            _assert_no_prod_paths_in_receipt(v, path + "." + key)
    elif isinstance(value, (list, tuple)):
        for i, v in enumerate(value):
            _assert_no_prod_paths_in_receipt(v, path + "[" + str(i) + "]")


# ── Timestamp helpers ───────────────────────────────────────────────────


def _parse_timestamp(ts: str) -> datetime:
    """Parse an ISO-8601 or Unix epoch timestamp as a UTC datetime.

    Digit-only values are treated as epoch milliseconds when they contain
    at least 13 digits (or exceed a 10-digit epoch-seconds range), otherwise
    as epoch seconds. Naive ISO timestamps are deterministically interpreted
    as UTC.
    """
    value = ts.strip()
    if value.isdigit():
        epoch_value = int(value)
        if len(value) >= 13 or epoch_value > 10_000_000_000:
            epoch_value /= 1000
        return datetime.fromtimestamp(epoch_value, tz=timezone.utc)

    if value.endswith("Z"):
        value = value[:-1] + "+00:00"
    parsed = datetime.fromisoformat(value)
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def _format_timestamp(dt: datetime) -> str:
    """Format a datetime as ISO-8601 UTC string ending in 'Z'."""
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


# ── Input inventory ─────────────────────────────────────────────────────


def _build_role_inventory(
    role: str,
    directory: Path,
    timestamp_column: str,
) -> dict[str, Any]:
    """Build the inventory dict for a single role (bars or funding).

    *role* is ``"bars"`` or ``"funding"``.
    *directory* is the resolved ``Path`` containing CSV files.
    *timestamp_column* is the column name to scan for metadata
    (``"timestamp"`` for bars, ``"fundingTime"`` for funding).

    Returns a dict with keys:
    - role, directory, csv_file_count, filenames, total_size_bytes, files,
      aggregate_role_fingerprint
    - each file entry has: filename, size_bytes, sha256
    - each file entry also has: row_count, min_timestamp, max_timestamp,
      has_timestamp_column

    No price columns are parsed. No returns/PnL/Sharpe are computed.
    """
    csv_paths: list[Path] = []
    filenames: list[str] = []
    files: list[dict[str, Any]] = []
    total_size_bytes: int = 0
    sha256_digests: list[str] = []

    for csv_path in sorted(directory.glob("*.csv")):
        resolved_csv = csv_path.resolve()
        _refuse_if_prod_path(resolved_csv)
        if not resolved_csv.is_file():
            continue

        csv_paths.append(csv_path)
        filename = csv_path.name
        filenames.append(filename)
        size_bytes = resolved_csv.stat().st_size
        total_size_bytes += size_bytes

        # SHA256 of file content.
        sha256_hex = hashlib.sha256(resolved_csv.read_bytes()).hexdigest()
        sha256_digests.append(sha256_hex)

        # Timestamp metadata (CSV header scan, timestamp column only).
        row_count: int = 0
        min_timestamp_dt: datetime | None = None
        max_timestamp_dt: datetime | None = None
        has_timestamp_column: bool = False

        with open(resolved_csv, newline="") as f:
            reader = csv.DictReader(f)
            if reader.fieldnames is None:
                # Empty file — no columns at all.
                pass
            else:
                # Case-insensitive column lookup.
                col_lower_map = {h.lower(): h for h in reader.fieldnames}
                target_lower = timestamp_column.lower()
                actual_col = col_lower_map.get(target_lower)

                if actual_col is not None:
                    has_timestamp_column = True
                    for row_number, row in enumerate(reader, start=2):
                        row_count += 1
                        ts_val = row.get(actual_col)
                        if ts_val is not None and ts_val.strip():
                            ts_val = ts_val.strip()
                            try:
                                parsed_ts = _parse_timestamp(ts_val)
                            except (OverflowError, OSError, ValueError) as exc:
                                raise ValueError(
                                    f"Malformed timestamp in {filename} row "
                                    f"{row_number}, column {actual_col}: {ts_val!r}"
                                ) from exc
                            if min_timestamp_dt is None or parsed_ts < min_timestamp_dt:
                                min_timestamp_dt = parsed_ts
                            if max_timestamp_dt is None or parsed_ts > max_timestamp_dt:
                                max_timestamp_dt = parsed_ts
                else:
                    # Column not found — still count rows but no timestamp info.
                    for _ in reader:
                        row_count += 1

        file_entry: dict[str, Any] = {
            "filename": filename,
            "size_bytes": size_bytes,
            "sha256": sha256_hex,
            "row_count": row_count,
            "min_timestamp": (
                _format_timestamp(min_timestamp_dt)
                if min_timestamp_dt is not None
                else None
            ),
            "max_timestamp": (
                _format_timestamp(max_timestamp_dt)
                if max_timestamp_dt is not None
                else None
            ),
            "has_timestamp_column": has_timestamp_column,
        }
        files.append(file_entry)

    # Aggregate fingerprint: SHA256 of sorted concatenation of per-file digests.
    sorted_digests = sorted(sha256_digests)
    concatenated = "".join(sorted_digests).encode("utf-8")
    aggregate_fingerprint = hashlib.sha256(concatenated).hexdigest()

    return {
        "role": role,
        "directory": str(directory),
        "csv_file_count": len(csv_paths),
        "filenames": filenames,
        "total_size_bytes": total_size_bytes,
        "files": files,
        "aggregate_role_fingerprint": aggregate_fingerprint,
    }


def build_real_validation_input_inventory(
    *,
    bars_dir: Path,
    funding_dir: Path | None = None,
) -> dict[str, Any]:
    """Build an input inventory from real CSV data directories.

    Enumerates CSV files in *bars_dir* (and optionally *funding_dir*),
    records file metadata (size, SHA256), timestamp metadata (min/max per
    file), and computes an aggregate role fingerprint.

    Refuses paths under ``/srv/qnty`` and nonexistent directories.

    No returns/PnL/Sharpe are computed. No price columns are parsed.
    """
    # Guard checks.
    bars_resolved = bars_dir.resolve()
    _refuse_if_prod_path(bars_resolved)
    if not bars_resolved.is_dir():
        raise ValueError(f"bars_dir does not exist: {bars_resolved}")

    funding_resolved: Path | None = None
    if funding_dir is not None:
        funding_resolved = funding_dir.resolve()
        _refuse_if_prod_path(funding_resolved)
        if not funding_resolved.is_dir():
            raise ValueError(f"funding_dir does not exist: {funding_resolved}")

    roles: list[dict[str, Any]] = [
        _build_role_inventory("bars", bars_resolved, "timestamp"),
    ]
    if funding_resolved is not None:
        roles.append(
            _build_role_inventory("funding", funding_resolved, "fundingTime")
        )

    return {
        "roles": roles,
    }


# ── Split builder skeleton ──────────────────────────────────────────────


def build_deterministic_split_definitions(
    *,
    global_min_timestamp: str,
    global_max_timestamp: str,
    split_count: int = 3,
) -> list[dict[str, Any]]:
    """Build deterministic placeholder split definitions.

    This does **not** inspect any real data file and does **not** compute
    returns. It only partitions the provided ``[global_min_timestamp,
    global_max_timestamp]`` bounds (treated as opaque strings) into
    ``split_count`` deterministic, evenly-labeled placeholder windows, each
    marked ``calculation_status: NOT_EXECUTED``.
    """
    if split_count < 1:
        raise ValueError(f"split_count must be >= 1, got {split_count}")

    splits: list[dict[str, Any]] = []
    for i in range(split_count):
        splits.append(
            {
                "split_id": f"split_{i:02d}",
                "train_window": {
                    "start": global_min_timestamp,
                    "end": global_max_timestamp,
                },
                "validation_window": {
                    "start": global_min_timestamp,
                    "end": global_max_timestamp,
                },
                "split_index": i,
                "split_count": split_count,
                "calculation_status": "NOT_EXECUTED",
            }
        )
    return splits


def _derive_global_timestamp_bounds(
    inventory: dict[str, Any],
) -> tuple[str, str, int, int]:
    """Derive global min/max timestamp and file counts from inventory.

    Returns ``(global_min_str, global_max_str, bars_file_count,
    funding_file_count)``.

    Raises ``ValueError`` if no timestamp data is available.
    """
    global_min: datetime | None = None
    global_max: datetime | None = None
    bars_file_count: int = 0
    funding_file_count: int = 0

    roles = inventory.get("roles", [])
    for role_entry in roles:
        role = role_entry.get("role", "")
        files = role_entry.get("files", [])
        if role == "bars":
            bars_file_count = len(files)
        elif role == "funding":
            funding_file_count = len(files)

        for file_entry in files:
            fmin = file_entry.get("min_timestamp")
            fmax = file_entry.get("max_timestamp")
            if fmin is not None:
                parsed_min = _parse_timestamp(fmin)
                if global_min is None or parsed_min < global_min:
                    global_min = parsed_min
            if fmax is not None:
                parsed_max = _parse_timestamp(fmax)
                if global_max is None or parsed_max > global_max:
                    global_max = parsed_max

    if global_min is None or global_max is None:
        raise ValueError(
            "Cannot derive global timestamp bounds from inventory: "
            "no timestamp data available"
        )

    return (
        _format_timestamp(global_min),
        _format_timestamp(global_max),
        bars_file_count,
        funding_file_count,
    )


def materialize_split_definitions_from_inventory(
    *,
    inventory: dict[str, Any],
    split_count: int = 3,
) -> list[dict[str, Any]]:
    """Derive deterministic split definitions from an input inventory.

    Extracts global min/max timestamps from the inventory's per-file
    timestamp metadata, partitions the time range into equal segments,
    and creates expanding-window split definitions.

    Each split i gets:
    - a validation window covering one segment
    - a training window covering everything before the validation window

    No returns/PnL/Sharpe fields are included.
    """
    if split_count < 1:
        raise ValueError(f"split_count must be >= 1, got {split_count}")

    global_min_str, global_max_str, bars_file_count, funding_file_count = (
        _derive_global_timestamp_bounds(inventory)
    )

    global_min_dt = _parse_timestamp(global_min_str)
    global_max_dt = _parse_timestamp(global_max_str)
    total_seconds = (global_max_dt - global_min_dt).total_seconds()
    segment_duration = total_seconds / split_count

    # Build segment boundaries.
    boundaries: list[str] = []
    for i in range(split_count + 1):
        boundary_dt = global_min_dt + timedelta(seconds=i * segment_duration)
        boundaries.append(_format_timestamp(boundary_dt))

    splits: list[dict[str, Any]] = []
    for i in range(split_count):
        train_start = boundaries[0]
        train_end = boundaries[i]  # up to start of validation segment
        val_start = boundaries[i]
        val_end = boundaries[i + 1]

        splits.append(
            {
                "split_id": f"split_{i:02d}",
                "split_index": i,
                "split_count": split_count,
                "train_window": {
                    "start": train_start,
                    "end": train_end,
                },
                "validation_window": {
                    "start": val_start,
                    "end": val_end,
                },
                "calculation_status": "NOT_EXECUTED",
                "bars_file_count": bars_file_count,
                "funding_file_count": funding_file_count,
            }
        )

    return splits


# ── Row assignment metadata ──────────────────────────────────────────


_ROLE_TIMESTAMP_COLUMNS = {
    "bars": "timestamp",
    "funding": "fundingTime",
}


def _timestamp_in_window(
    timestamp: datetime,
    *,
    start: datetime,
    end: datetime,
    include_end: bool = False,
) -> bool:
    """Return whether *timestamp* is in a deterministic split window."""
    if include_end:
        return start <= timestamp <= end
    return start <= timestamp < end


def materialize_input_rows_for_splits(
    *,
    inventory: dict,
    split_definitions: list[dict],
) -> dict:
    """Count inventoried timestamp rows assigned to existing split windows.

    Only the role-specific timestamp column is accessed. Empty timestamp cells
    and rows outside every window are counted as unassigned; malformed
    timestamps fail closed, matching inventory construction. Windows are
    start-inclusive and end-exclusive, except the final validation window,
    whose end is inclusive so the inventoried global maximum is covered.

    The result contains coverage metadata only. It performs no calculations
    and does not retain timestamps or any non-timestamp CSV values.
    """
    if not split_definitions:
        raise ValueError("split_definitions must not be empty")

    windows: list[dict[str, Any]] = []
    final_validation_index = max(
        range(len(split_definitions)),
        key=lambda index: split_definitions[index].get("split_index", index),
    )
    for index, split in enumerate(split_definitions):
        try:
            train = split["train_window"]
            validation = split["validation_window"]
            windows.append(
                {
                    "split_id": str(split["split_id"]),
                    "train_start": _parse_timestamp(str(train["start"])),
                    "train_end": _parse_timestamp(str(train["end"])),
                    "validation_start": _parse_timestamp(str(validation["start"])),
                    "validation_end": _parse_timestamp(str(validation["end"])),
                    "include_validation_end": index == final_validation_index,
                }
            )
        except (KeyError, TypeError, ValueError) as exc:
            raise ValueError(f"Invalid split definition at index {index}") from exc

    role_results: list[dict[str, Any]] = []
    for role_entry in inventory.get("roles", []):
        role = role_entry.get("role")
        timestamp_column = _ROLE_TIMESTAMP_COLUMNS.get(role)
        if timestamp_column is None:
            raise ValueError(f"Unsupported inventoried role: {role!r}")

        role_directory = Path(str(role_entry.get("directory", ""))).resolve()
        _refuse_if_prod_path(role_directory)
        if not role_directory.is_dir():
            raise ValueError(f"Inventoried role directory is missing: {role_directory}")

        role_split_counts = {
            window["split_id"]: {"train_rows": 0, "validation_rows": 0}
            for window in windows
        }
        file_results: list[dict[str, Any]] = []
        role_total_rows = 0
        role_assigned_rows = 0

        for file_entry in role_entry.get("files", []):
            filename = file_entry.get("filename")
            if not isinstance(filename, str) or not filename:
                raise ValueError(f"Invalid inventoried filename for role {role!r}")

            filename_path = Path(filename)
            if filename_path.is_absolute() or "/" in filename or ".." in filename:
                raise ValueError(
                    f"Inventoried filename must be a simple filename: {filename!r}"
                )

            inventoried_path = role_directory / filename
            if inventoried_path.parent != role_directory:
                raise ValueError(
                    f"Inventoried file path is outside role directory: {filename}"
                )
            if not inventoried_path.exists():
                raise ValueError(f"Inventoried file is missing: {inventoried_path}")

            resolved_file = inventoried_path.resolve()
            _refuse_if_prod_path(resolved_file)
            if (
                not _is_under(resolved_file, role_directory)
                and not inventoried_path.is_symlink()
            ):
                raise ValueError(
                    f"Inventoried file resolves outside role directory: {filename}"
                )
            if not resolved_file.is_file():
                raise ValueError(f"Inventoried path is not a file: {resolved_file}")

            inventoried_sha256 = file_entry.get("sha256")
            reopened_sha256 = hashlib.sha256(resolved_file.read_bytes()).hexdigest()
            if reopened_sha256 != inventoried_sha256:
                raise ValueError(
                    f"Inventoried SHA256 changed for {filename}: "
                    f"expected {inventoried_sha256}, found {reopened_sha256}"
                )

            per_split_counts = {
                window["split_id"]: {"train_rows": 0, "validation_rows": 0}
                for window in windows
            }
            total_rows = 0
            assigned_rows = 0

            with open(resolved_file, newline="") as csv_file:
                reader = csv.reader(csv_file)
                header = next(reader, None)
                timestamp_index: int | None = None
                if header is not None:
                    header_lookup = {name.lower(): i for i, name in enumerate(header)}
                    timestamp_index = header_lookup.get(timestamp_column.lower())

                for row_number, row in enumerate(reader, start=2):
                    total_rows += 1
                    timestamp_value = (
                        row[timestamp_index].strip()
                        if timestamp_index is not None and timestamp_index < len(row)
                        else ""
                    )
                    if not timestamp_value:
                        continue
                    try:
                        timestamp = _parse_timestamp(timestamp_value)
                    except (OverflowError, OSError, ValueError) as exc:
                        raise ValueError(
                            f"Malformed timestamp in {filename} row {row_number}, "
                            f"column {timestamp_column}: {timestamp_value!r}"
                        ) from exc

                    row_was_assigned = False
                    for window in windows:
                        split_counts = per_split_counts[window["split_id"]]
                        if _timestamp_in_window(
                            timestamp,
                            start=window["train_start"],
                            end=window["train_end"],
                        ):
                            split_counts["train_rows"] += 1
                            row_was_assigned = True
                        if _timestamp_in_window(
                            timestamp,
                            start=window["validation_start"],
                            end=window["validation_end"],
                            include_end=window["include_validation_end"],
                        ):
                            split_counts["validation_rows"] += 1
                            row_was_assigned = True
                    if row_was_assigned:
                        assigned_rows += 1

            inventoried_rows = file_entry.get("row_count")
            if inventoried_rows is not None and total_rows != inventoried_rows:
                raise ValueError(
                    f"Inventoried row count changed for {filename}: "
                    f"expected {inventoried_rows}, found {total_rows}"
                )

            split_counts_list = []
            for window in windows:
                split_id = window["split_id"]
                counts = per_split_counts[split_id]
                split_counts_list.append({"split_id": split_id, **counts})
                role_split_counts[split_id]["train_rows"] += counts["train_rows"]
                role_split_counts[split_id]["validation_rows"] += counts[
                    "validation_rows"
                ]

            file_results.append(
                {
                    "role": role,
                    "filename": filename,
                    "timestamp_column": timestamp_column,
                    "total_rows": total_rows,
                    "assigned_rows": assigned_rows,
                    "unassigned_rows": total_rows - assigned_rows,
                    "per_split_counts": split_counts_list,
                    "calculation_status": "NOT_EXECUTED",
                }
            )
            role_total_rows += total_rows
            role_assigned_rows += assigned_rows

        role_results.append(
            {
                "role": role,
                "total_rows": role_total_rows,
                "assigned_rows": role_assigned_rows,
                "unassigned_rows": role_total_rows - role_assigned_rows,
                "files": file_results,
                "per_split_counts": [
                    {"split_id": window["split_id"], **role_split_counts[window["split_id"]]}
                    for window in windows
                ],
                "calculation_status": "NOT_EXECUTED",
            }
        )

    return {
        "metadata_only": True,
        "timestamp_policy": {
            "empty_timestamp": "UNASSIGNED",
            "malformed_timestamp": "FAIL_CLOSED",
            "window_start": "INCLUSIVE",
            "window_end": "EXCLUSIVE_EXCEPT_FINAL_VALIDATION_INCLUSIVE",
        },
        "roles": role_results,
        "calculation_status": "NOT_EXECUTED",
    }


# ── Gross observational return metadata ────────────────────────────────


def _gross_return_summary(values: list[float]) -> dict[str, Any]:
    """Summarize close-to-close observations without strategy semantics."""
    return {
        "observation_count": len(values),
        "positive_count": sum(value > 0.0 for value in values),
        "negative_count": sum(value < 0.0 for value in values),
        "zero_count": sum(value == 0.0 for value in values),
        "min_gross_return": min(values) if values else None,
        "max_gross_return": max(values) if values else None,
        "mean_gross_return": math.fsum(values) / len(values) if values else None,
    }


def materialize_gross_observational_returns(
    *,
    inventory: dict,
    split_definitions: list[dict],
) -> dict:
    """Materialize bars-only close-to-close descriptive return metadata.

    Each observation is ``(close_t / close_t_minus_1) - 1`` and is assigned to
    train/validation windows by the current row timestamp. Files must retain
    their inventoried SHA256, timestamps must be strictly increasing, and only
    the timestamp and close columns are accessed. Funding inventory entries are
    recorded as ignored and are never opened.
    """
    if not split_definitions:
        raise ValueError("split_definitions must not be empty")

    windows: list[dict[str, Any]] = []
    final_validation_index = max(
        range(len(split_definitions)),
        key=lambda index: split_definitions[index].get("split_index", index),
    )
    for index, split in enumerate(split_definitions):
        try:
            train = split["train_window"]
            validation = split["validation_window"]
            windows.append(
                {
                    "split_id": str(split["split_id"]),
                    "train_start": _parse_timestamp(str(train["start"])),
                    "train_end": _parse_timestamp(str(train["end"])),
                    "validation_start": _parse_timestamp(str(validation["start"])),
                    "validation_end": _parse_timestamp(str(validation["end"])),
                    "include_validation_end": index == final_validation_index,
                }
            )
        except (KeyError, TypeError, ValueError) as exc:
            raise ValueError(f"Invalid split definition at index {index}") from exc

    file_results: list[dict[str, Any]] = []
    ignored_roles: list[str] = []
    for role_entry in inventory.get("roles", []):
        role = role_entry.get("role")
        if role != "bars":
            ignored_roles.append(str(role))
            continue

        role_directory = Path(str(role_entry.get("directory", ""))).resolve()
        _refuse_if_prod_path(role_directory)
        if not role_directory.is_dir():
            raise ValueError(f"Inventoried bars directory is missing: {role_directory}")

        for file_entry in role_entry.get("files", []):
            filename = file_entry.get("filename")
            if not isinstance(filename, str) or not filename:
                raise ValueError("Invalid inventoried filename for role 'bars'")
            filename_path = Path(filename)
            if filename_path.is_absolute() or "/" in filename or ".." in filename:
                raise ValueError(
                    f"Inventoried filename must be a simple filename: {filename!r}"
                )

            inventoried_path = role_directory / filename
            if inventoried_path.parent != role_directory:
                raise ValueError(
                    f"Inventoried file path is outside role directory: {filename}"
                )
            if not inventoried_path.exists():
                raise ValueError(f"Inventoried file is missing: {inventoried_path}")

            resolved_file = inventoried_path.resolve()
            _refuse_if_prod_path(resolved_file)
            if (
                not _is_under(resolved_file, role_directory)
                and not inventoried_path.is_symlink()
            ):
                raise ValueError(
                    f"Inventoried file resolves outside role directory: {filename}"
                )
            if not resolved_file.is_file():
                raise ValueError(f"Inventoried path is not a file: {resolved_file}")

            inventoried_sha256 = file_entry.get("sha256")
            reopened_sha256 = hashlib.sha256(resolved_file.read_bytes()).hexdigest()
            if reopened_sha256 != inventoried_sha256:
                raise ValueError(
                    f"Inventoried SHA256 changed for {filename}: "
                    f"expected {inventoried_sha256}, found {reopened_sha256}"
                )

            observations: list[tuple[datetime, float]] = []
            previous_timestamp: datetime | None = None
            previous_close: float | None = None
            total_rows = 0
            with open(resolved_file, newline="") as csv_file:
                reader = csv.reader(csv_file)
                header = next(reader, None)
                if header is None:
                    raise ValueError(f"Missing CSV header in {filename}")
                header_lookup = {name.lower(): i for i, name in enumerate(header)}
                timestamp_index = header_lookup.get("timestamp")
                close_index = header_lookup.get("close")
                if timestamp_index is None:
                    raise ValueError(f"Missing timestamp column in {filename}")
                if close_index is None:
                    raise ValueError(f"Missing close column in {filename}")

                for row_number, row in enumerate(reader, start=2):
                    total_rows += 1
                    timestamp_value = (
                        row[timestamp_index].strip()
                        if timestamp_index < len(row)
                        else ""
                    )
                    close_value = (
                        row[close_index].strip() if close_index < len(row) else ""
                    )
                    try:
                        timestamp = _parse_timestamp(timestamp_value)
                    except (OverflowError, OSError, ValueError) as exc:
                        raise ValueError(
                            f"Malformed timestamp in {filename} row {row_number}: "
                            f"{timestamp_value!r}"
                        ) from exc
                    try:
                        close = float(close_value)
                    except ValueError as exc:
                        raise ValueError(
                            f"Malformed close in {filename} row {row_number}: "
                            f"{close_value!r}"
                        ) from exc
                    if not math.isfinite(close):
                        raise ValueError(
                            f"Malformed close in {filename} row {row_number}: "
                            f"{close_value!r}"
                        )
                    if previous_timestamp is not None and timestamp <= previous_timestamp:
                        raise ValueError(
                            f"Non-monotonic timestamp in {filename} row {row_number}: "
                            f"{timestamp_value!r}"
                        )
                    if previous_close is not None:
                        if previous_close == 0.0:
                            raise ValueError(
                                f"Zero prior close in {filename} row {row_number}"
                            )
                        gross_return = (close / previous_close) - 1.0
                        if not math.isfinite(gross_return):
                            raise ValueError(
                                f"Non-finite gross observation in {filename} row "
                                f"{row_number}"
                            )
                        observations.append((timestamp, gross_return))
                    previous_timestamp = timestamp
                    previous_close = close

            inventoried_rows = file_entry.get("row_count")
            if inventoried_rows is not None and total_rows != inventoried_rows:
                raise ValueError(
                    f"Inventoried row count changed for {filename}: "
                    f"expected {inventoried_rows}, found {total_rows}"
                )

            per_split_windows: list[dict[str, Any]] = []
            for window in windows:
                train_values = [
                    value
                    for timestamp, value in observations
                    if _timestamp_in_window(
                        timestamp,
                        start=window["train_start"],
                        end=window["train_end"],
                    )
                ]
                validation_values = [
                    value
                    for timestamp, value in observations
                    if _timestamp_in_window(
                        timestamp,
                        start=window["validation_start"],
                        end=window["validation_end"],
                        include_end=window["include_validation_end"],
                    )
                ]
                per_split_windows.append(
                    {
                        "split_id": window["split_id"],
                        "train_window": _gross_return_summary(train_values),
                        "validation_window": _gross_return_summary(validation_values),
                        "calculation_status": "GROSS_OBSERVATIONAL_RETURNS_ONLY",
                    }
                )

            file_results.append(
                {
                    "role": "bars",
                    "filename": filename,
                    "timestamp_column": "timestamp",
                    "close_column": "close",
                    **_gross_return_summary([value for _, value in observations]),
                    "per_split_windows": per_split_windows,
                    "calculation_status": "GROSS_OBSERVATIONAL_RETURNS_ONLY",
                }
            )

    return {
        "processed_role": "bars",
        "ignored_roles": ignored_roles,
        "files": file_results,
        "funding_adjusted_status": "NOT_EXECUTED",
        "calculation_status": "GROSS_OBSERVATIONAL_RETURNS_ONLY",
    }


# ── Cost-case matrix skeleton ────────────────────────────────────────────


def _cost_drag_summary(summary: dict, drag_fraction: float) -> dict[str, Any]:
    """Describe an existing gross summary after subtracting an assumption."""
    count = summary.get("observation_count")
    if not isinstance(count, int) or isinstance(count, bool) or count < 0:
        raise ValueError("gross observation_count must be a non-negative integer")

    def adjusted(source_key: str) -> float | None:
        value = summary.get(source_key)
        if value is None:
            return None
        if not isinstance(value, (int, float)) or isinstance(value, bool):
            raise ValueError(f"gross {source_key} must be numeric or null")
        result = float(value) - drag_fraction
        if not math.isfinite(result):
            raise ValueError(f"gross {source_key} must be finite")
        return result

    return {
        "gross_observation_count": count,
        "gross_minus_drag_observation_mean": adjusted("mean_gross_return"),
        "gross_minus_drag_observation_min": adjusted("min_gross_return"),
        "gross_minus_drag_observation_max": adjusted("max_gross_return"),
    }


def materialize_cost_case_observational_drag(
    *, gross_observational_returns: dict, cost_cases: list[dict]
) -> dict:
    """Apply descriptive round-trip cost assumptions to gross observations.

    This consumes only the already-materialized gross receipt section and does
    no I/O. Each per-side assumption is doubled to describe a two-sided drag
    for one close-to-close observation.
    """
    files = gross_observational_returns.get("files")
    if not isinstance(files, list):
        raise ValueError("gross_observational_returns.files must be a list")

    cases: list[dict[str, Any]] = []
    for case in cost_cases:
        case_name = case.get("cost_case")
        if not isinstance(case_name, str) or not case_name:
            raise ValueError("cost case name must be a non-empty string")
        components: list[float] = []
        for key in (
            "commission_bps_per_side",
            "slippage_bps_per_side",
            "spread_bps_per_side",
        ):
            value = case.get(key)
            if (
                not isinstance(value, (int, float))
                or isinstance(value, bool)
                or not math.isfinite(value)
                or value < 0.0
            ):
                raise ValueError(f"cost case {case_name!r} has invalid {key}")
            components.append(float(value))
        drag_bps = 2.0 * math.fsum(components)
        drag_fraction = drag_bps / 10_000.0

        file_summaries: list[dict[str, Any]] = []
        for file_summary in files:
            windows = file_summary.get("per_split_windows")
            if not isinstance(windows, list):
                raise ValueError("gross per_split_windows must be a list")
            split_summaries = [
                {
                    "split_id": window.get("split_id"),
                    "train_window": _cost_drag_summary(
                        window.get("train_window", {}), drag_fraction
                    ),
                    "validation_window": _cost_drag_summary(
                        window.get("validation_window", {}), drag_fraction
                    ),
                }
                for window in windows
            ]
            file_summaries.append(
                {
                    "filename": file_summary.get("filename"),
                    **_cost_drag_summary(file_summary, drag_fraction),
                    "per_split_windows": split_summaries,
                }
            )
        cases.append(
            {
                "cost_case": case_name,
                "assumed_drag_bps_per_observation": drag_bps,
                "files": file_summaries,
                "calculation_status": "DESCRIPTIVE_OBSERVATIONAL_DRAG_ONLY",
            }
        )

    return {
        "cost_cases": cases,
        "calculation_status": "DESCRIPTIVE_OBSERVATIONAL_DRAG_ONLY",
    }


# ── Funding observational adjustment metadata ─────────────────────────


def _funding_rate_summary(values: list[float]) -> dict[str, Any]:
    """Summarize observed funding rates without strategy semantics."""
    return {
        "observation_count": len(values),
        "positive_count": sum(value > 0.0 for value in values),
        "negative_count": sum(value < 0.0 for value in values),
        "zero_count": sum(value == 0.0 for value in values),
        "min_funding_rate": min(values) if values else None,
        "max_funding_rate": max(values) if values else None,
        "mean_funding_rate": math.fsum(values) / len(values) if values else None,
    }


def materialize_funding_observational_adjustments(
    *, inventory: dict, split_definitions: list[dict]
) -> dict:
    """Materialize funding-only descriptive metadata by split window.

    Only ``fundingTime`` and ``fundingRate`` are accessed. Inventoried files
    must retain their SHA256, timestamps must be strictly increasing, and bars
    inventory entries are recorded as ignored and never opened. This does not
    adjust bars or calculate strategy or portfolio results.
    """
    if not split_definitions:
        raise ValueError("split_definitions must not be empty")

    windows: list[dict[str, Any]] = []
    final_validation_index = max(
        range(len(split_definitions)),
        key=lambda index: split_definitions[index].get("split_index", index),
    )
    for index, split in enumerate(split_definitions):
        try:
            train = split["train_window"]
            validation = split["validation_window"]
            windows.append(
                {
                    "split_id": str(split["split_id"]),
                    "train_start": _parse_timestamp(str(train["start"])),
                    "train_end": _parse_timestamp(str(train["end"])),
                    "validation_start": _parse_timestamp(str(validation["start"])),
                    "validation_end": _parse_timestamp(str(validation["end"])),
                    "include_validation_end": index == final_validation_index,
                }
            )
        except (KeyError, TypeError, ValueError) as exc:
            raise ValueError(f"Invalid split definition at index {index}") from exc

    file_results: list[dict[str, Any]] = []
    ignored_roles: list[str] = []
    for role_entry in inventory.get("roles", []):
        role = role_entry.get("role")
        if role != "funding":
            ignored_roles.append(str(role))
            continue

        role_directory = Path(str(role_entry.get("directory", ""))).resolve()
        _refuse_if_prod_path(role_directory)
        if not role_directory.is_dir():
            raise ValueError(
                f"Inventoried funding directory is missing: {role_directory}"
            )

        for file_entry in role_entry.get("files", []):
            filename = file_entry.get("filename")
            if not isinstance(filename, str) or not filename:
                raise ValueError("Invalid inventoried filename for role 'funding'")
            filename_path = Path(filename)
            if filename_path.is_absolute() or "/" in filename or ".." in filename:
                raise ValueError(
                    f"Inventoried filename must be a simple filename: {filename!r}"
                )

            inventoried_path = role_directory / filename
            if inventoried_path.parent != role_directory:
                raise ValueError(
                    f"Inventoried file path is outside role directory: {filename}"
                )
            if not inventoried_path.exists():
                raise ValueError(f"Inventoried file is missing: {inventoried_path}")

            resolved_file = inventoried_path.resolve()
            _refuse_if_prod_path(resolved_file)
            if (
                not _is_under(resolved_file, role_directory)
                and not inventoried_path.is_symlink()
            ):
                raise ValueError(
                    f"Inventoried file resolves outside role directory: {filename}"
                )
            if not resolved_file.is_file():
                raise ValueError(f"Inventoried path is not a file: {resolved_file}")

            inventoried_sha256 = file_entry.get("sha256")
            reopened_sha256 = hashlib.sha256(resolved_file.read_bytes()).hexdigest()
            if reopened_sha256 != inventoried_sha256:
                raise ValueError(
                    f"Inventoried SHA256 changed for {filename}: "
                    f"expected {inventoried_sha256}, found {reopened_sha256}"
                )

            observations: list[tuple[datetime, float]] = []
            previous_timestamp: datetime | None = None
            total_rows = 0
            with open(resolved_file, newline="") as csv_file:
                reader = csv.reader(csv_file)
                header = next(reader, None)
                if header is None:
                    raise ValueError(f"Missing CSV header in {filename}")
                header_lookup = {name.lower(): i for i, name in enumerate(header)}
                timestamp_index = header_lookup.get("fundingtime")
                rate_index = header_lookup.get("fundingrate")
                if timestamp_index is None:
                    raise ValueError(f"Missing fundingTime column in {filename}")
                if rate_index is None:
                    raise ValueError(f"Missing fundingRate column in {filename}")

                for row_number, row in enumerate(reader, start=2):
                    total_rows += 1
                    timestamp_value = (
                        row[timestamp_index].strip()
                        if timestamp_index < len(row)
                        else ""
                    )
                    rate_value = row[rate_index].strip() if rate_index < len(row) else ""
                    try:
                        timestamp = _parse_timestamp(timestamp_value)
                    except (OverflowError, OSError, ValueError) as exc:
                        raise ValueError(
                            f"Malformed fundingTime in {filename} row {row_number}: "
                            f"{timestamp_value!r}"
                        ) from exc
                    try:
                        funding_rate = float(rate_value)
                    except ValueError as exc:
                        raise ValueError(
                            f"Malformed fundingRate in {filename} row {row_number}: "
                            f"{rate_value!r}"
                        ) from exc
                    if not math.isfinite(funding_rate):
                        raise ValueError(
                            f"Malformed fundingRate in {filename} row {row_number}: "
                            f"{rate_value!r}"
                        )
                    if previous_timestamp is not None and timestamp <= previous_timestamp:
                        raise ValueError(
                            f"Non-monotonic fundingTime in {filename} row {row_number}: "
                            f"{timestamp_value!r}"
                        )
                    observations.append((timestamp, funding_rate))
                    previous_timestamp = timestamp

            inventoried_rows = file_entry.get("row_count")
            if inventoried_rows is not None and total_rows != inventoried_rows:
                raise ValueError(
                    f"Inventoried row count changed for {filename}: "
                    f"expected {inventoried_rows}, found {total_rows}"
                )

            per_split_windows: list[dict[str, Any]] = []
            for window in windows:
                train_values = [
                    value
                    for timestamp, value in observations
                    if _timestamp_in_window(
                        timestamp,
                        start=window["train_start"],
                        end=window["train_end"],
                    )
                ]
                validation_values = [
                    value
                    for timestamp, value in observations
                    if _timestamp_in_window(
                        timestamp,
                        start=window["validation_start"],
                        end=window["validation_end"],
                        include_end=window["include_validation_end"],
                    )
                ]
                per_split_windows.append(
                    {
                        "split_id": window["split_id"],
                        "train_window": _funding_rate_summary(train_values),
                        "validation_window": _funding_rate_summary(validation_values),
                        "calculation_status": "FUNDING_OBSERVATIONAL_ADJUSTMENT_ONLY",
                    }
                )

            file_results.append(
                {
                    "role": "funding",
                    "filename": filename,
                    "timestamp_column": "fundingTime",
                    "funding_rate_column": "fundingRate",
                    **_funding_rate_summary([value for _, value in observations]),
                    "per_split_windows": per_split_windows,
                    "calculation_status": "FUNDING_OBSERVATIONAL_ADJUSTMENT_ONLY",
                }
            )

    return {
        "processed_role": "funding",
        "ignored_roles": ignored_roles,
        "files": file_results,
        "bars_adjusted_status": "NOT_EXECUTED",
        "calculation_status": "FUNDING_OBSERVATIONAL_ADJUSTMENT_ONLY",
    }


# ── Funding-to-bars alignment diagnostics ────────────────────────────


def _symbol_from_filename(filename: Any, suffix: str, role: str) -> str:
    if not isinstance(filename, str):
        raise ValueError(
            f"Invalid {role} filename {filename!r}; expected a string"
        )

    if suffix == "_8h_ohlcv.csv":
        match = re.fullmatch(r"(?P<symbol>[A-Za-z0-9]+)_8h_ohlcv\.csv", filename)
        expected = "<symbol>_8h_ohlcv.csv"
    elif suffix == "_funding.csv":
        match = re.fullmatch(
            r"(?P<symbol>[A-Za-z0-9]+)(?:_(?P<interval>[1-9][0-9]*[mhd]))?_funding\.csv",
            filename,
        )
        expected = "<symbol>[_<interval>]_funding.csv"
    else:
        raise ValueError(f"Unsupported filename suffix parser: {suffix!r}")

    if match is None:
        raise ValueError(
            f"Invalid {role} filename {filename!r}; expected {expected}"
        )
    return match.group("symbol")


def _files_by_symbol(files: Any, suffix: str, role: str) -> dict[str, dict]:
    if not isinstance(files, list):
        raise ValueError(f"{role} files must be a list")
    indexed: dict[str, dict] = {}
    for entry in files:
        if not isinstance(entry, dict):
            raise ValueError(f"{role} file entry must be a mapping")
        symbol = _symbol_from_filename(entry.get("filename"), suffix, role)
        if symbol in indexed:
            raise ValueError(f"Duplicate {role} symbol: {symbol}")
        indexed[symbol] = entry
    return indexed


def _non_negative_count(value: Any, field: str) -> int:
    if not isinstance(value, int) or isinstance(value, bool) or value < 0:
        raise ValueError(f"{field} must be a non-negative integer")
    return value


def materialize_funding_to_bars_alignment_diagnostics(
    *,
    row_materialization: dict,
    gross_observational_returns: dict,
    funding_observational_adjustments: dict,
    outlier_threshold_abs_rate: float = 0.01,
) -> dict:
    """Pair existing bars/funding receipt summaries for diagnostics only.

    This helper performs no I/O and derives no adjusted values. It only joins
    already-materialized row, observation, split, and funding-rate metadata.
    """
    if (
        not isinstance(outlier_threshold_abs_rate, (int, float))
        or isinstance(outlier_threshold_abs_rate, bool)
        or not math.isfinite(outlier_threshold_abs_rate)
        or outlier_threshold_abs_rate < 0.0
    ):
        raise ValueError("outlier_threshold_abs_rate must be finite and non-negative")
    threshold = float(outlier_threshold_abs_rate)

    roles = row_materialization.get("roles")
    if not isinstance(roles, list):
        raise ValueError("row_materialization.roles must be a list")
    role_files: dict[str, Any] = {}
    for role in roles:
        if not isinstance(role, dict) or role.get("role") not in {"bars", "funding"}:
            continue
        role_name = str(role["role"])
        if role_name in role_files:
            raise ValueError(f"Duplicate row materialization role: {role_name}")
        role_files[role_name] = role.get("files")

    bars_rows = _files_by_symbol(
        role_files.get("bars"), "_8h_ohlcv.csv", "bars row materialization"
    )
    funding_rows = _files_by_symbol(
        role_files.get("funding"), "_funding.csv", "funding row materialization"
    )
    gross_files = _files_by_symbol(
        gross_observational_returns.get("files"),
        "_8h_ohlcv.csv",
        "gross observation",
    )
    funding_files = _files_by_symbol(
        funding_observational_adjustments.get("files"),
        "_funding.csv",
        "funding observation",
    )

    expected = set(bars_rows)
    for label, indexed in (
        ("funding row materialization", funding_rows),
        ("gross observation", gross_files),
        ("funding observation", funding_files),
    ):
        missing = sorted(expected - set(indexed))
        extra = sorted(set(indexed) - expected)
        if missing or extra:
            raise ValueError(
                f"Symbol mismatch for {label}: missing={missing}, extra={extra}"
            )

    symbols: list[dict[str, Any]] = []
    for symbol in sorted(expected):
        bars_row = bars_rows[symbol]
        funding_row = funding_rows[symbol]
        gross = gross_files[symbol]
        funding = funding_files[symbol]
        bars_unassigned = _non_negative_count(
            bars_row.get("unassigned_rows"), "bars_unassigned_rows"
        )
        funding_unassigned = _non_negative_count(
            funding_row.get("unassigned_rows"), "funding_unassigned_rows"
        )

        def split_index(entry: dict, field: str) -> dict[str, dict]:
            windows = entry.get(field)
            if not isinstance(windows, list):
                raise ValueError(f"{field} must be a list for {symbol}")
            result: dict[str, dict] = {}
            for window in windows:
                split_id = window.get("split_id") if isinstance(window, dict) else None
                if not isinstance(split_id, str) or not split_id or split_id in result:
                    raise ValueError(f"Invalid or duplicate split_id for {symbol}")
                result[split_id] = window
            return result

        bars_splits = split_index(bars_row, "per_split_counts")
        funding_row_splits = split_index(funding_row, "per_split_counts")
        gross_splits = split_index(gross, "per_split_windows")
        funding_splits = split_index(funding, "per_split_windows")
        if not (
            set(bars_splits)
            == set(funding_row_splits)
            == set(gross_splits)
            == set(funding_splits)
        ):
            raise ValueError(f"Split mismatch for symbol {symbol}")

        split_diagnostics = []
        for split_id in bars_splits:
            bars_counts = bars_splits[split_id]
            funding_counts = funding_row_splits[split_id]
            gross_windows = gross_splits[split_id]
            funding_windows = funding_splits[split_id]
            split_diagnostics.append(
                {
                    "split_id": split_id,
                    "bars_train_rows": _non_negative_count(
                        bars_counts.get("train_rows"), "bars_train_rows"
                    ),
                    "bars_validation_rows": _non_negative_count(
                        bars_counts.get("validation_rows"), "bars_validation_rows"
                    ),
                    "funding_train_rows": _non_negative_count(
                        funding_counts.get("train_rows"), "funding_train_rows"
                    ),
                    "funding_validation_rows": _non_negative_count(
                        funding_counts.get("validation_rows"),
                        "funding_validation_rows",
                    ),
                    "gross_train_observations": _non_negative_count(
                        gross_windows.get("train_window", {}).get("observation_count"),
                        "gross_train_observations",
                    ),
                    "gross_validation_observations": _non_negative_count(
                        gross_windows.get("validation_window", {}).get(
                            "observation_count"
                        ),
                        "gross_validation_observations",
                    ),
                    "funding_train_observations": _non_negative_count(
                        funding_windows.get("train_window", {}).get(
                            "observation_count"
                        ),
                        "funding_train_observations",
                    ),
                    "funding_validation_observations": _non_negative_count(
                        funding_windows.get("validation_window", {}).get(
                            "observation_count"
                        ),
                        "funding_validation_observations",
                    ),
                }
            )

        minimum = funding.get("min_funding_rate")
        maximum = funding.get("max_funding_rate")
        for name, value in (("min_funding_rate", minimum), ("max_funding_rate", maximum)):
            if value is not None and (
                not isinstance(value, (int, float))
                or isinstance(value, bool)
                or not math.isfinite(value)
            ):
                raise ValueError(f"{name} must be finite or null for {symbol}")
        outlier_present = any(
            value is not None and abs(float(value)) > threshold
            for value in (minimum, maximum)
        )
        symbols.append(
            {
                "symbol": symbol,
                "bars_file": bars_row["filename"],
                "funding_file": funding_row["filename"],
                "bars_total_rows": _non_negative_count(
                    bars_row.get("total_rows"), "bars_total_rows"
                ),
                "funding_total_rows": _non_negative_count(
                    funding_row.get("total_rows"), "funding_total_rows"
                ),
                "gross_observation_count": _non_negative_count(
                    gross.get("observation_count"), "gross_observation_count"
                ),
                "funding_observation_count": _non_negative_count(
                    funding.get("observation_count"), "funding_observation_count"
                ),
                "bars_unassigned_rows": bars_unassigned,
                "funding_unassigned_rows": funding_unassigned,
                "coverage_status": (
                    "COMPLETE"
                    if bars_unassigned == 0 and funding_unassigned == 0
                    else "DIAGNOSTIC_ONLY"
                ),
                "min_funding_rate": minimum,
                "max_funding_rate": maximum,
                "outlier_threshold_abs_rate": threshold,
                "funding_rate_outlier_present": outlier_present,
                "funding_rate_outlier_reason": (
                    "ABS_RATE_EXCEEDS_THRESHOLD" if outlier_present else "NONE"
                ),
                "splits": split_diagnostics,
                "calculation_status": "FUNDING_TO_BARS_ALIGNMENT_DIAGNOSTIC_ONLY",
            }
        )

    complete_count = sum(item["coverage_status"] == "COMPLETE" for item in symbols)
    return {
        "calculation_status": "FUNDING_TO_BARS_ALIGNMENT_DIAGNOSTIC_ONLY",
        "symbol_count": len(symbols),
        "complete_symbol_count": complete_count,
        "diagnostic_symbol_count": len(symbols) - complete_count,
        "outlier_symbol_count": sum(
            item["funding_rate_outlier_present"] for item in symbols
        ),
        "outlier_threshold_abs_rate": threshold,
        "symbols": symbols,
    }


# ── Funding-to-bars temporal joinability diagnostics ─────────────────


_JOINABILITY_EXACT = "EXACT_TIMESTAMP_SET_MATCH"
_JOINABILITY_PARTIAL = "PARTIAL_TIMESTAMP_SET_MATCH"
_JOINABILITY_NONE = "NO_EXACT_TIMESTAMP_MATCH"
_JOINABILITY_EMPTY_BOTH = "EMPTY_BOTH"


def _classify_timestamp_set_match(
    left: set[datetime], right: set[datetime]
) -> tuple[int, str]:
    """Classify exact timestamp-set overlap between *left* and *right*."""
    if not left and not right:
        return 0, _JOINABILITY_EMPTY_BOTH
    matched = len(left & right)
    if matched == 0:
        return 0, _JOINABILITY_NONE
    if left == right:
        return matched, _JOINABILITY_EXACT
    return matched, _JOINABILITY_PARTIAL


def _load_role_symbol_timestamps(
    *,
    role_entry: dict[str, Any],
    filename_suffix: str,
    timestamp_column: str,
    role: str,
) -> dict[str, dict[str, Any]]:
    """Re-open inventoried *role* CSV files and extract validated timestamps.

    Only *timestamp_column* is read. Verifies the inventoried SHA256 and row
    count still match the file on disk, rejects duplicate/non-monotonic/
    malformed/missing timestamp values, and returns each file's strictly
    increasing timestamp list keyed by normalized symbol.
    """
    role_directory = Path(str(role_entry.get("directory", ""))).resolve()
    _refuse_if_prod_path(role_directory)
    if not role_directory.is_dir():
        raise ValueError(f"Inventoried {role} directory is missing: {role_directory}")

    files = role_entry.get("files")
    if not isinstance(files, list):
        raise ValueError(f"{role} files must be a list")

    result: dict[str, dict[str, Any]] = {}
    for file_entry in files:
        if not isinstance(file_entry, dict):
            raise ValueError(f"{role} file entry must be a mapping")
        filename = file_entry.get("filename")
        symbol = _symbol_from_filename(filename, filename_suffix, role)
        if symbol in result:
            raise ValueError(f"Duplicate {role} symbol: {symbol}")
        filename = str(filename)

        filename_path = Path(filename)
        if filename_path.is_absolute() or "/" in filename or ".." in filename:
            raise ValueError(
                f"Inventoried filename must be a simple filename: {filename!r}"
            )

        inventoried_path = role_directory / filename
        if inventoried_path.parent != role_directory:
            raise ValueError(
                f"Inventoried file path is outside role directory: {filename}"
            )
        if not inventoried_path.exists():
            raise ValueError(f"Inventoried file is missing: {inventoried_path}")

        resolved_file = inventoried_path.resolve()
        _refuse_if_prod_path(resolved_file)
        if (
            not _is_under(resolved_file, role_directory)
            and not inventoried_path.is_symlink()
        ):
            raise ValueError(
                f"Inventoried file resolves outside role directory: {filename}"
            )
        if not resolved_file.is_file():
            raise ValueError(f"Inventoried path is not a file: {resolved_file}")

        inventoried_sha256 = file_entry.get("sha256")
        reopened_sha256 = hashlib.sha256(resolved_file.read_bytes()).hexdigest()
        if reopened_sha256 != inventoried_sha256:
            raise ValueError(
                f"Inventoried SHA256 changed for {filename}: "
                f"expected {inventoried_sha256}, found {reopened_sha256}"
            )

        timestamps: list[datetime] = []
        seen: set[datetime] = set()
        previous_timestamp: datetime | None = None
        total_rows = 0
        with open(resolved_file, newline="") as csv_file:
            reader = csv.reader(csv_file)
            header = next(reader, None)
            if header is None:
                raise ValueError(f"Missing CSV header in {filename}")
            header_lookup = {name.lower(): i for i, name in enumerate(header)}
            timestamp_index = header_lookup.get(timestamp_column.lower())
            if timestamp_index is None:
                raise ValueError(f"Missing {timestamp_column} column in {filename}")

            for row_number, row in enumerate(reader, start=2):
                total_rows += 1
                timestamp_value = (
                    row[timestamp_index].strip()
                    if timestamp_index < len(row)
                    else ""
                )
                if not timestamp_value:
                    raise ValueError(
                        f"Missing {timestamp_column} value in {filename} row "
                        f"{row_number}"
                    )
                try:
                    timestamp = _parse_timestamp(timestamp_value)
                except (OverflowError, OSError, ValueError) as exc:
                    raise ValueError(
                        f"Malformed {timestamp_column} in {filename} row "
                        f"{row_number}: {timestamp_value!r}"
                    ) from exc
                if timestamp in seen:
                    raise ValueError(
                        f"Duplicate {timestamp_column} in {filename} row "
                        f"{row_number}: {timestamp_value!r}"
                    )
                if previous_timestamp is not None and timestamp <= previous_timestamp:
                    raise ValueError(
                        f"Non-monotonic {timestamp_column} in {filename} row "
                        f"{row_number}: {timestamp_value!r}"
                    )
                seen.add(timestamp)
                timestamps.append(timestamp)
                previous_timestamp = timestamp

        inventoried_rows = file_entry.get("row_count")
        if inventoried_rows is not None and total_rows != inventoried_rows:
            raise ValueError(
                f"Inventoried row count changed for {filename}: "
                f"expected {inventoried_rows}, found {total_rows}"
            )

        result[symbol] = {"filename": filename, "timestamps": timestamps}

    return result


def _build_split_windows_for_joinability(
    split_definitions: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    if not split_definitions:
        raise ValueError("split_definitions must not be empty")

    for index, split in enumerate(split_definitions):
        if not isinstance(split, dict):
            raise ValueError(f"Invalid split definition at index {index}")

    windows: list[dict[str, Any]] = []
    seen_split_ids: set[str] = set()
    final_validation_index = max(
        range(len(split_definitions)),
        key=lambda index: split_definitions[index].get("split_index", index),
    )
    for index, split in enumerate(split_definitions):
        try:
            split_id = split["split_id"]
            if not isinstance(split_id, str) or not split_id:
                raise ValueError(f"Invalid split_id at index {index}")
            train = split["train_window"]
            validation = split["validation_window"]
            window = {
                "split_id": split_id,
                "train_start": _parse_timestamp(str(train["start"])),
                "train_end": _parse_timestamp(str(train["end"])),
                "validation_start": _parse_timestamp(str(validation["start"])),
                "validation_end": _parse_timestamp(str(validation["end"])),
                "include_validation_end": index == final_validation_index,
            }
        except (KeyError, TypeError, ValueError) as exc:
            raise ValueError(f"Invalid split definition at index {index}") from exc
        if split_id in seen_split_ids:
            raise ValueError(f"Duplicate split_id at index {index}")
        seen_split_ids.add(split_id)
        windows.append(window)
    return windows


def _joinability_window_summary(
    bars: set[datetime], funding: set[datetime]
) -> dict[str, Any]:
    matched, status = _classify_timestamp_set_match(bars, funding)
    return {
        "bars_timestamp_count": len(bars),
        "funding_timestamp_count": len(funding),
        "exact_matched_timestamp_count": matched,
        "bars_unmatched_count": len(bars - funding),
        "funding_unmatched_count": len(funding - bars),
        "status": status,
    }


def materialize_funding_to_bars_temporal_joinability_diagnostics(
    *,
    inventory: dict[str, Any],
    split_definitions: list[dict[str, Any]],
) -> dict[str, Any]:
    """Diagnose exact-timestamp joinability between bars and funding files.

    Reads only the ``timestamp`` (bars) and ``fundingTime`` (funding)
    columns directly from the inventoried CSV files and reports, per
    normalized symbol and per existing deterministic split window, whether
    the timestamp sets match exactly, partially overlap, contain no exact
    matches, or are both empty. Matching is exact UTC-timestamp equality
    only — no nearest-neighbour matching, forward/backward fill, tolerance
    windows, interpolation, or assumed offsets.

    This performs no price/rate reads, applies no funding to bars, and
    computes no strategy, PnL, Sharpe, risk, or portfolio values.
    """
    windows = _build_split_windows_for_joinability(split_definitions)

    roles = inventory.get("roles")
    if not isinstance(roles, list):
        raise ValueError("inventory.roles must be a list")
    role_entries: dict[str, dict[str, Any]] = {}
    for role_entry in roles:
        if not isinstance(role_entry, dict):
            raise ValueError("inventory role entry must be a mapping")
        role = role_entry.get("role")
        if role not in _ROLE_TIMESTAMP_COLUMNS:
            raise ValueError(f"Unsupported inventoried role: {role!r}")
        if role in role_entries:
            raise ValueError(f"Duplicate inventoried role: {role}")
        role_entries[role] = role_entry

    if "bars" not in role_entries or "funding" not in role_entries:
        raise ValueError(
            "funding-to-bars temporal joinability diagnostics require both "
            "bars and funding roles in the inventory"
        )

    bars_by_symbol = _load_role_symbol_timestamps(
        role_entry=role_entries["bars"],
        filename_suffix="_8h_ohlcv.csv",
        timestamp_column="timestamp",
        role="bars",
    )
    funding_by_symbol = _load_role_symbol_timestamps(
        role_entry=role_entries["funding"],
        filename_suffix="_funding.csv",
        timestamp_column="fundingTime",
        role="funding",
    )

    bars_symbols = set(bars_by_symbol)
    funding_symbols = set(funding_by_symbol)
    if bars_symbols != funding_symbols:
        missing = sorted(bars_symbols - funding_symbols)
        extra = sorted(funding_symbols - bars_symbols)
        raise ValueError(
            f"Symbol mismatch between bars and funding: missing={missing}, "
            f"extra={extra}"
        )

    symbols: list[dict[str, Any]] = []
    exact_count = 0
    partial_count = 0
    none_count = 0
    for symbol in sorted(bars_symbols):
        bars_entry = bars_by_symbol[symbol]
        funding_entry = funding_by_symbol[symbol]
        bars_timestamps: list[datetime] = bars_entry["timestamps"]
        funding_timestamps: list[datetime] = funding_entry["timestamps"]
        bars_set = set(bars_timestamps)
        funding_set = set(funding_timestamps)

        bars_first = bars_timestamps[0] if bars_timestamps else None
        bars_last = bars_timestamps[-1] if bars_timestamps else None
        funding_first = funding_timestamps[0] if funding_timestamps else None
        funding_last = funding_timestamps[-1] if funding_timestamps else None

        overlap_start: datetime | None = None
        overlap_end: datetime | None = None
        if bars_first is not None and funding_first is not None:
            candidate_start = max(bars_first, funding_first)
            candidate_end = min(bars_last, funding_last)
            if candidate_start <= candidate_end:
                overlap_start, overlap_end = candidate_start, candidate_end

        bars_without_funding = bars_set - funding_set
        funding_without_bars = funding_set - bars_set

        if overlap_start is not None and overlap_end is not None:
            bars_without_funding_in_overlap = sum(
                1
                for ts in bars_without_funding
                if overlap_start <= ts <= overlap_end
            )
            funding_without_bars_in_overlap = sum(
                1
                for ts in funding_without_bars
                if overlap_start <= ts <= overlap_end
            )
            bars_outside_overlap = sum(
                1 for ts in bars_timestamps if ts < overlap_start or ts > overlap_end
            )
            funding_outside_overlap = sum(
                1
                for ts in funding_timestamps
                if ts < overlap_start or ts > overlap_end
            )
        else:
            bars_without_funding_in_overlap = 0
            funding_without_bars_in_overlap = 0
            bars_outside_overlap = len(bars_timestamps)
            funding_outside_overlap = len(funding_timestamps)

        matched_count, status = _classify_timestamp_set_match(bars_set, funding_set)
        if status == _JOINABILITY_EXACT:
            exact_count += 1
        elif status == _JOINABILITY_PARTIAL:
            partial_count += 1
        elif status == _JOINABILITY_NONE:
            none_count += 1

        split_diagnostics: list[dict[str, Any]] = []
        for window in windows:
            train_bars = {
                ts
                for ts in bars_set
                if _timestamp_in_window(
                    ts, start=window["train_start"], end=window["train_end"]
                )
            }
            train_funding = {
                ts
                for ts in funding_set
                if _timestamp_in_window(
                    ts, start=window["train_start"], end=window["train_end"]
                )
            }
            validation_bars = {
                ts
                for ts in bars_set
                if _timestamp_in_window(
                    ts,
                    start=window["validation_start"],
                    end=window["validation_end"],
                    include_end=window["include_validation_end"],
                )
            }
            validation_funding = {
                ts
                for ts in funding_set
                if _timestamp_in_window(
                    ts,
                    start=window["validation_start"],
                    end=window["validation_end"],
                    include_end=window["include_validation_end"],
                )
            }
            split_diagnostics.append(
                {
                    "split_id": window["split_id"],
                    "train_window": _joinability_window_summary(
                        train_bars, train_funding
                    ),
                    "validation_window": _joinability_window_summary(
                        validation_bars, validation_funding
                    ),
                }
            )

        symbols.append(
            {
                "symbol": symbol,
                "bars_file": bars_entry["filename"],
                "funding_file": funding_entry["filename"],
                "bars_timestamp_count": len(bars_timestamps),
                "funding_timestamp_count": len(funding_timestamps),
                "bars_first_timestamp": (
                    _format_timestamp(bars_first) if bars_first is not None else None
                ),
                "bars_last_timestamp": (
                    _format_timestamp(bars_last) if bars_last is not None else None
                ),
                "funding_first_timestamp": (
                    _format_timestamp(funding_first)
                    if funding_first is not None
                    else None
                ),
                "funding_last_timestamp": (
                    _format_timestamp(funding_last)
                    if funding_last is not None
                    else None
                ),
                "overlap_start": (
                    _format_timestamp(overlap_start)
                    if overlap_start is not None
                    else None
                ),
                "overlap_end": (
                    _format_timestamp(overlap_end) if overlap_end is not None else None
                ),
                "exact_matched_timestamp_count": matched_count,
                "bars_without_funding_timestamp_count": len(bars_without_funding),
                "funding_without_bars_timestamp_count": len(funding_without_bars),
                "bars_without_funding_in_overlap_count": (
                    bars_without_funding_in_overlap
                ),
                "funding_without_bars_in_overlap_count": (
                    funding_without_bars_in_overlap
                ),
                "bars_outside_overlap_count": bars_outside_overlap,
                "funding_outside_overlap_count": funding_outside_overlap,
                "exact_match_status": status,
                "funding_application_status": "NOT_EXECUTED",
                "calculation_status": (
                    "FUNDING_TO_BARS_TEMPORAL_JOINABILITY_DIAGNOSTIC_ONLY"
                ),
                "splits": split_diagnostics,
            }
        )

    return {
        "calculation_status": "FUNDING_TO_BARS_TEMPORAL_JOINABILITY_DIAGNOSTIC_ONLY",
        "timestamp_match_policy": "EXACT_UTC_TIMESTAMP_ONLY",
        "funding_application_status": "NOT_EXECUTED",
        "symbol_count": len(symbols),
        "exact_set_match_symbol_count": exact_count,
        "partial_match_symbol_count": partial_count,
        "no_exact_match_symbol_count": none_count,
        "symbols": symbols,
    }


# ── Funding-to-bars timestamp convention / offset diagnostics ───────────


_SHIFTED_EXACT = "EXACT_SHIFTED_TIMESTAMP_SET_MATCH"
_SHIFTED_PARTIAL = "PARTIAL_SHIFTED_TIMESTAMP_SET_MATCH"
_SHIFTED_NONE = "NO_SHIFTED_TIMESTAMP_MATCH"
_SHIFTED_EMPTY_BOTH = "EMPTY_BOTH"

_SHIFT_DIRECTION_LABEL = "BARS_SHIFTED_BEFORE_COMPARISON_TO_FUNDING"

_EIGHT_HOURS_SECONDS = 8 * 3600

_NEAREST_DELTA_HISTOGRAM_CAP = 200

_DEFAULT_CANDIDATE_OFFSETS: tuple[tuple[str, int], ...] = (
    ("-24h", -86400),
    ("-16h", -57600),
    ("-12h", -43200),
    ("-8h", -28800),
    ("-4h", -14400),
    ("-1h", -3600),
    ("0h", 0),
    ("+1h", 3600),
    ("+4h", 14400),
    ("+8h", 28800),
    ("+12h", 43200),
    ("+16h", 57600),
    ("+24h", 86400),
)


def _validate_candidate_offsets(candidate_offsets: Any) -> list[tuple[str, int]]:
    """Validate a candidate-offset definition, failing closed on malformed input."""
    if not isinstance(candidate_offsets, (list, tuple)) or not candidate_offsets:
        raise ValueError("candidate_offsets must be a non-empty list")

    seen_labels: set[str] = set()
    seen_seconds: set[int] = set()
    validated: list[tuple[str, int]] = []
    for entry in candidate_offsets:
        if (
            not isinstance(entry, (tuple, list))
            or len(entry) != 2
        ):
            raise ValueError(f"Invalid candidate offset definition: {entry!r}")
        label, seconds = entry
        if not isinstance(label, str) or not label:
            raise ValueError(f"Invalid candidate offset label: {label!r}")
        if not isinstance(seconds, int) or isinstance(seconds, bool):
            raise ValueError(f"Invalid candidate offset seconds: {seconds!r}")
        if label in seen_labels:
            raise ValueError(f"Duplicate candidate offset label: {label}")
        if seconds in seen_seconds:
            raise ValueError(f"Duplicate candidate offset seconds: {seconds}")
        seen_labels.add(label)
        seen_seconds.add(seconds)
        validated.append((label, seconds))

    if 0 not in seen_seconds:
        raise ValueError("candidate_offsets must include a 0-second baseline offset")

    return validated


def _safe_ratio(numerator: int, denominator: int) -> float:
    if denominator == 0:
        return 0.0
    ratio = numerator / denominator
    if not math.isfinite(ratio):
        raise ValueError(f"Non-finite match ratio computed: {numerator}/{denominator}")
    return ratio


def _classify_shifted_set_match(shifted: set[datetime], funding: set[datetime]) -> str:
    if not shifted and not funding:
        return _SHIFTED_EMPTY_BOTH
    matched = len(shifted & funding)
    if matched == 0:
        return _SHIFTED_NONE
    if shifted == funding:
        return _SHIFTED_EXACT
    return _SHIFTED_PARTIAL


def _offset_matched_counts(
    bars_set: set[datetime],
    funding_set: set[datetime],
    candidate_offsets: list[tuple[str, int]],
) -> list[dict[str, Any]]:
    """Compare *bars_set* shifted by each candidate offset against *funding_set*.

    Bars timestamps are shifted before comparison to funding; this performs
    no application of funding to bars and computes no financial values.
    """
    results: list[dict[str, Any]] = []
    for label, seconds in candidate_offsets:
        shifted = {ts + timedelta(seconds=seconds) for ts in bars_set}
        matched = len(shifted & funding_set)
        results.append(
            {
                "offset_label": label,
                "offset_seconds": seconds,
                "shift_direction": _SHIFT_DIRECTION_LABEL,
                "matched_timestamp_count": matched,
                "bars_unmatched_after_shift_count": len(shifted - funding_set),
                "funding_unmatched_after_shift_count": len(funding_set - shifted),
                "match_ratio_of_bars": _safe_ratio(matched, len(bars_set)),
                "match_ratio_of_funding": _safe_ratio(matched, len(funding_set)),
                "exact_shifted_set_status": _classify_shifted_set_match(
                    shifted, funding_set
                ),
            }
        )
    return results


def _select_best_offset(
    offset_results: list[dict[str, Any]], key_field: str
) -> dict[str, Any]:
    """Pick the best offset by *key_field*, deterministic on ties.

    Ties are broken by candidate-list order (the first tied candidate in
    the deterministic candidate order wins); ``tie_count`` and
    ``tied_offset_labels`` record every tied candidate.
    """
    best_value = max(entry[key_field] for entry in offset_results)
    tied = [entry for entry in offset_results if entry[key_field] == best_value]
    winner = tied[0]
    return {
        "offset_label": winner["offset_label"],
        "offset_seconds": winner["offset_seconds"],
        key_field: best_value,
        "tie_count": len(tied),
        "tied_offset_labels": [entry["offset_label"] for entry in tied],
    }


def _split_offset_window_summary(
    bars_window: set[datetime],
    funding_window: set[datetime],
    candidate_offsets: list[tuple[str, int]],
) -> dict[str, Any]:
    offset_results = _offset_matched_counts(
        bars_window, funding_window, candidate_offsets
    )
    zero_entry = next(
        entry for entry in offset_results if entry["offset_seconds"] == 0
    )
    best = _select_best_offset(offset_results, "matched_timestamp_count")
    best_entry = next(
        entry for entry in offset_results if entry["offset_label"] == best["offset_label"]
    )
    return {
        "best_offset_by_matched_count": best,
        "matched_count_at_0h": zero_entry["matched_timestamp_count"],
        "matched_count_at_best_offset": best_entry["matched_timestamp_count"],
        "bars_count": len(bars_window),
        "funding_count": len(funding_window),
        "status_at_0h": zero_entry["exact_shifted_set_status"],
        "status_at_best_offset": best_entry["exact_shifted_set_status"],
    }


def _mode_step_seconds(timestamps: list[datetime]) -> tuple[int | None, int]:
    """Return ``(mode_step_seconds, non_mode_step_count)`` for consecutive diffs.

    Ties in the step-count mode are broken deterministically by preferring
    the smallest step value. Fewer than two timestamps yields
    ``(None, 0)``.
    """
    if len(timestamps) < 2:
        return None, 0
    steps = [
        int((timestamps[i] - timestamps[i - 1]).total_seconds())
        for i in range(1, len(timestamps))
    ]
    counts = Counter(steps)
    max_count = max(counts.values())
    mode_step = min(step for step, count in counts.items() if count == max_count)
    non_mode_count = sum(1 for step in steps if step != mode_step)
    return mode_step, non_mode_count


def _residue_mod_8h_counts(timestamps: list[datetime]) -> list[dict[str, Any]]:
    """Histogram of timestamp-seconds modulo 8h, deterministically ordered."""
    counts: dict[int, int] = {}
    for ts in timestamps:
        residue = int(ts.timestamp()) % _EIGHT_HOURS_SECONDS
        counts[residue] = counts.get(residue, 0) + 1
    result: list[dict[str, Any]] = []
    for residue in sorted(counts):
        hours, remainder = divmod(residue, 3600)
        minutes, seconds = divmod(remainder, 60)
        result.append(
            {
                "residue_seconds": residue,
                "residue_label": f"{hours:02d}:{minutes:02d}:{seconds:02d}",
                "count": counts[residue],
            }
        )
    return result


def _timedelta_to_microseconds(delta: timedelta) -> int:
    """Exact signed microseconds represented by *delta*.

    Uses ``timedelta``'s exact integer day/second/microsecond components
    instead of a float ``total_seconds()`` multiplication, so no
    sub-second precision is lost or rounded away.
    """
    return (delta.days * 86_400 + delta.seconds) * 1_000_000 + delta.microseconds


def _nearest_funding_delta_microseconds(
    bar_ts: datetime, funding_sorted: list[datetime]
) -> int:
    """Signed microseconds from *bar_ts* to its nearest funding timestamp.

    Diagnostic only: this is never used to join or apply funding, only to
    record the observed nearest-neighbour delta distribution. Ties in
    absolute distance are broken toward the smaller (more negative) signed
    delta, matching the prior seconds-based tie-break policy.
    """
    idx = bisect.bisect_left(funding_sorted, bar_ts)
    candidate_deltas: list[int] = []
    if idx < len(funding_sorted):
        candidate_deltas.append(
            _timedelta_to_microseconds(funding_sorted[idx] - bar_ts)
        )
    if idx > 0:
        candidate_deltas.append(
            _timedelta_to_microseconds(funding_sorted[idx - 1] - bar_ts)
        )
    return min(candidate_deltas, key=lambda us: (abs(us), us))


def _nearest_delta_histogram(
    unmatched_bars_sorted: list[datetime], funding_sorted: list[datetime]
) -> dict[str, Any]:
    """Diagnostic nearest-delta histogram for 0h-unmatched bars timestamps.

    Never used to join or apply funding. Deltas are signed integer
    microseconds computed with no sub-second truncation (see
    ``_timedelta_to_microseconds``). Deterministically truncated to
    ``_NEAREST_DELTA_HISTOGRAM_CAP`` entries, ordered by descending count
    then ascending ``delta_microseconds``.
    """
    if not unmatched_bars_sorted or not funding_sorted:
        return {
            "histogram": [],
            "most_common_delta_microseconds": None,
            "most_common_delta_seconds": None,
            "sample_size": 0,
            "zero_microseconds_count": 0,
            "subsecond_nonzero_count": 0,
            "max_abs_microseconds": 0,
        }

    counts: dict[int, int] = {}
    zero_microseconds_count = 0
    subsecond_nonzero_count = 0
    max_abs_microseconds = 0
    for bar_ts in unmatched_bars_sorted:
        delta_us = _nearest_funding_delta_microseconds(bar_ts, funding_sorted)
        counts[delta_us] = counts.get(delta_us, 0) + 1
        if delta_us == 0:
            zero_microseconds_count += 1
        elif abs(delta_us) < 1_000_000:
            subsecond_nonzero_count += 1
        max_abs_microseconds = max(max_abs_microseconds, abs(delta_us))

    ordered = sorted(counts.items(), key=lambda item: (-item[1], item[0]))
    truncated = ordered[:_NEAREST_DELTA_HISTOGRAM_CAP]
    histogram = [
        {
            "delta_microseconds": delta_us,
            "delta_seconds": delta_us / 1_000_000,
            "count": count,
        }
        for delta_us, count in truncated
    ]
    most_common_us = ordered[0][0]
    return {
        "histogram": histogram,
        "most_common_delta_microseconds": most_common_us,
        "most_common_delta_seconds": most_common_us / 1_000_000,
        "sample_size": len(unmatched_bars_sorted),
        "zero_microseconds_count": zero_microseconds_count,
        "subsecond_nonzero_count": subsecond_nonzero_count,
        "max_abs_microseconds": max_abs_microseconds,
    }


# ── Funding-to-bars timestamp canonicalization helpers ─────────────────


def _canonicalize_timestamp_floor(ts: datetime) -> str:
    """Truncate sub-second to get ``YYYY-MM-DDTHH:MM:SS`` UTC from a datetime."""
    return ts.strftime("%Y-%m-%dT%H:%M:%SZ")


def _canonicalize_timestamp_ceil(ts: datetime) -> str:
    """If sub-second > 0, round up to next whole second in UTC from a datetime."""
    if ts.microsecond > 0:
        ts = ts + timedelta(seconds=1)
    return ts.strftime("%Y-%m-%dT%H:%M:%SZ")


def _canonicalize_timestamp_round_half_away_from_zero(ts: datetime) -> str:
    """Round to nearest second with .5 rounding away from zero from a datetime."""
    if ts.microsecond >= 500_000:
        ts = ts + timedelta(seconds=1)
    return ts.strftime("%Y-%m-%dT%H:%M:%SZ")


def _detect_canonicalized_collisions(
    canonicalized: list[str],
) -> dict[str, Any]:
    """Find buckets with >= 2 raw timestamps mapping to same canonical timestamp.

    Returns dict with ``collision_count``, ``max_bucket_size``,
    ``collision_examples`` (capped at 5, deterministically sorted).
    """
    counts: dict[str, int] = {}
    for canon in canonicalized:
        counts[canon] = counts.get(canon, 0) + 1
    collisions = {canon: cnt for canon, cnt in counts.items() if cnt >= 2}
    collision_count = len(collisions)
    max_bucket_size = max(collisions.values()) if collisions else 0
    sorted_buckets = sorted(collisions.items(), key=lambda item: (-item[1], item[0]))
    examples = [
        {"canonical_timestamp": canon, "collision_size": cnt}
        for canon, cnt in sorted_buckets[:5]
    ]
    return {
        "collision_count": collision_count,
        "max_bucket_size": max_bucket_size,
        "collision_examples": examples,
    }


def _detect_ambiguous_nearest_bars(
    raw_funding_ts: list[datetime],
    bar_ts: list[datetime],
    canonicalized: list[str],
) -> int:
    """Count raw funding timestamps equidistant to two bar timestamps.

    Only funding timestamps that map to the same canonical timestamp
    are counted, since the diagnostic concerns canonicalization ambiguity.
    """
    if not raw_funding_ts or not bar_ts or not canonicalized:
        return 0
    bar_sorted: list[datetime] = sorted(bar_ts)
    canonicalized_set = set(canonicalized)
    ambiguous_count = 0
    for canon in canonicalized_set:
        canon_dt = _parse_timestamp(canon)
        idx = bisect.bisect_left(bar_sorted, canon_dt)
        left_delta = None
        if idx > 0:
            left_delta = abs(
                _timedelta_to_microseconds(canon_dt - bar_sorted[idx - 1])
            )
        right_delta = None
        if idx < len(bar_sorted):
            right_delta = abs(
                _timedelta_to_microseconds(bar_sorted[idx] - canon_dt)
            )
        if left_delta is not None and right_delta is not None and left_delta == right_delta:
            ambiguous_count += 1
    return ambiguous_count


def _compute_subsecond_jitter_stats(
    funding_timestamps: list[datetime],
) -> dict[str, Any]:
    """Detect if any sub-second component exists, count, max abs microseconds."""
    count = 0
    max_abs = 0
    for ts in funding_timestamps:
        us = ts.microsecond
        if us != 0:
            count += 1
            max_abs = max(max_abs, us)
    return {
        "has_subsecond_funding_jitter": count > 0,
        "funding_subsecond_timestamp_count": count,
        "max_abs_subsecond_jitter_microseconds": max_abs,
    }


def _compute_history_range_status(
    bars_ts: list[datetime],
    funding_ts: list[datetime],
) -> str:
    """Compare the time ranges of bars and funding timestamp sets.

    Returns one of: MATCHING_RANGES, BARS_END_BEFORE_FUNDING,
    FUNDING_END_BEFORE_BARS, DISJOINT_RANGES, EMPTY_RANGE.
    """
    if not bars_ts and not funding_ts:
        return "EMPTY_RANGE"
    if not bars_ts or not funding_ts:
        return "EMPTY_RANGE"
    bars_first = min(bars_ts)
    bars_last = max(bars_ts)
    funding_first = min(funding_ts)
    funding_last = max(funding_ts)
    if bars_first == funding_first and bars_last == funding_last:
        return "MATCHING_RANGES"
    if bars_last < funding_first or funding_last < bars_first:
        return "DISJOINT_RANGES"
    if bars_last < funding_last:
        return "BARS_END_BEFORE_FUNDING"
    if funding_last < bars_last:
        return "FUNDING_END_BEFORE_BARS"
    return "MATCHING_RANGES"


def _select_best_policy(policy_results: list[dict]) -> dict[str, Any]:
    """Deterministic policy selection with three independent selectors.

    Each selector picks by its own metric, with tie-breaking by
    deterministic policy order: floor > round > ceil.
    Returns a dict with structured objects for each selector.
    """
    policy_order = {"floor_to_second": 0, "round_half_away_from_zero": 1, "ceil_to_second": 2}

    def _select_by_key(key: str) -> dict[str, Any]:
        best_value = max(p[key] for p in policy_results)
        tied = [p for p in policy_results if p[key] == best_value]
        winner = min(tied, key=lambda p: policy_order[p["policy_name"]])
        return {
            "policy_name": winner["policy_name"],
            key: best_value,
            "tie_count": len(tied),
            "tied_policy_names": [p["policy_name"] for p in tied],
        }

    def _select_by_collision() -> dict[str, Any]:
        best_value = min(p["funding_timestamp_collision_count"] for p in policy_results)
        tied = [p for p in policy_results if p["funding_timestamp_collision_count"] == best_value]
        winner = min(tied, key=lambda p: policy_order[p["policy_name"]])
        return {
            "policy_name": winner["policy_name"],
            "funding_timestamp_collision_count": best_value,
            "tie_count": len(tied),
            "tied_policy_names": [p["policy_name"] for p in tied],
        }

    return {
        "best_policy_by_exact_matched_count": _select_by_key(
            "exact_matched_after_canonicalization_count"
        ),
        "best_policy_by_bars_match_ratio": _select_by_key(
            "bars_match_ratio_after_canonicalization"
        ),
        "best_policy_by_funding_match_ratio": _select_by_key(
            "funding_match_ratio_after_canonicalization"
        ),
        "best_policy_by_lowest_collision_count": _select_by_collision(),
    }


def materialize_funding_to_bars_timestamp_convention_diagnostics(
    *,
    inventory: dict[str, Any],
    split_definitions: list[dict[str, Any]],
    candidate_offsets: Any = None,
) -> dict[str, Any]:
    """Diagnose why exact-UTC bars/funding timestamp sets only partially match.

    For each symbol, compares bars timestamps shifted by a fixed set of
    candidate offsets against funding timestamps, emits bars/funding
    cadence (mode step, residue-mod-8h) evidence, and records a diagnostic
    nearest-delta histogram for timestamps unmatched at 0h. This performs
    no price/rate reads, applies no funding to bars, and computes no
    strategy, PnL, Sharpe, risk, or portfolio values. Nearest-neighbour
    deltas are recorded for diagnosis only and are never used to join.
    """
    validated_offsets = _validate_candidate_offsets(
        candidate_offsets if candidate_offsets is not None else _DEFAULT_CANDIDATE_OFFSETS
    )

    windows = _build_split_windows_for_joinability(split_definitions)

    roles = inventory.get("roles")
    if not isinstance(roles, list):
        raise ValueError("inventory.roles must be a list")
    role_entries: dict[str, dict[str, Any]] = {}
    for role_entry in roles:
        if not isinstance(role_entry, dict):
            raise ValueError("inventory role entry must be a mapping")
        role = role_entry.get("role")
        if role not in _ROLE_TIMESTAMP_COLUMNS:
            raise ValueError(f"Unsupported inventoried role: {role!r}")
        if role in role_entries:
            raise ValueError(f"Duplicate inventoried role: {role}")
        role_entries[role] = role_entry

    if "bars" not in role_entries or "funding" not in role_entries:
        raise ValueError(
            "funding-to-bars timestamp convention diagnostics require both "
            "bars and funding roles in the inventory"
        )

    bars_by_symbol = _load_role_symbol_timestamps(
        role_entry=role_entries["bars"],
        filename_suffix="_8h_ohlcv.csv",
        timestamp_column="timestamp",
        role="bars",
    )
    funding_by_symbol = _load_role_symbol_timestamps(
        role_entry=role_entries["funding"],
        filename_suffix="_funding.csv",
        timestamp_column="fundingTime",
        role="funding",
    )

    bars_symbols = set(bars_by_symbol)
    funding_symbols = set(funding_by_symbol)
    if bars_symbols != funding_symbols:
        missing = sorted(bars_symbols - funding_symbols)
        extra = sorted(funding_symbols - bars_symbols)
        raise ValueError(
            f"Symbol mismatch between bars and funding: missing={missing}, "
            f"extra={extra}"
        )

    symbols: list[dict[str, Any]] = []
    for symbol in sorted(bars_symbols):
        bars_entry = bars_by_symbol[symbol]
        funding_entry = funding_by_symbol[symbol]
        bars_timestamps: list[datetime] = bars_entry["timestamps"]
        funding_timestamps: list[datetime] = funding_entry["timestamps"]
        bars_set = set(bars_timestamps)
        funding_set = set(funding_timestamps)

        offset_results = _offset_matched_counts(bars_set, funding_set, validated_offsets)

        bars_first = bars_timestamps[0] if bars_timestamps else None
        bars_last = bars_timestamps[-1] if bars_timestamps else None
        funding_first = funding_timestamps[0] if funding_timestamps else None
        funding_last = funding_timestamps[-1] if funding_timestamps else None

        bars_mode_step, bars_non_mode_count = _mode_step_seconds(bars_timestamps)
        funding_mode_step, funding_non_mode_count = _mode_step_seconds(
            funding_timestamps
        )

        bars_residue = _residue_mod_8h_counts(bars_timestamps)
        funding_residue = _residue_mod_8h_counts(funding_timestamps)

        unmatched_bars_sorted = sorted(bars_set - funding_set)
        nearest_delta = _nearest_delta_histogram(
            unmatched_bars_sorted, funding_timestamps
        )

        split_diagnostics: list[dict[str, Any]] = []
        for window in windows:
            train_bars = {
                ts
                for ts in bars_set
                if _timestamp_in_window(
                    ts, start=window["train_start"], end=window["train_end"]
                )
            }
            train_funding = {
                ts
                for ts in funding_set
                if _timestamp_in_window(
                    ts, start=window["train_start"], end=window["train_end"]
                )
            }
            validation_bars = {
                ts
                for ts in bars_set
                if _timestamp_in_window(
                    ts,
                    start=window["validation_start"],
                    end=window["validation_end"],
                    include_end=window["include_validation_end"],
                )
            }
            validation_funding = {
                ts
                for ts in funding_set
                if _timestamp_in_window(
                    ts,
                    start=window["validation_start"],
                    end=window["validation_end"],
                    include_end=window["include_validation_end"],
                )
            }
            split_diagnostics.append(
                {
                    "split_id": window["split_id"],
                    "train_window": _split_offset_window_summary(
                        train_bars, train_funding, validated_offsets
                    ),
                    "validation_window": _split_offset_window_summary(
                        validation_bars, validation_funding, validated_offsets
                    ),
                }
            )

        symbols.append(
            {
                "symbol": symbol,
                "bars_file": bars_entry["filename"],
                "funding_file": funding_entry["filename"],
                "offsets": offset_results,
                "best_offset_by_matched_count": _select_best_offset(
                    offset_results, "matched_timestamp_count"
                ),
                "best_offset_by_bars_match_ratio": _select_best_offset(
                    offset_results, "match_ratio_of_bars"
                ),
                "best_offset_by_funding_match_ratio": _select_best_offset(
                    offset_results, "match_ratio_of_funding"
                ),
                "bars_timestamp_count": len(bars_timestamps),
                "bars_first_timestamp": (
                    _format_timestamp(bars_first) if bars_first is not None else None
                ),
                "bars_last_timestamp": (
                    _format_timestamp(bars_last) if bars_last is not None else None
                ),
                "bars_mode_step_seconds": bars_mode_step,
                "bars_non_mode_step_count": bars_non_mode_count,
                "bars_residue_mod_8h_counts": bars_residue,
                "funding_timestamp_count": len(funding_timestamps),
                "funding_first_timestamp": (
                    _format_timestamp(funding_first)
                    if funding_first is not None
                    else None
                ),
                "funding_last_timestamp": (
                    _format_timestamp(funding_last)
                    if funding_last is not None
                    else None
                ),
                "funding_mode_step_seconds": funding_mode_step,
                "funding_non_mode_step_count": funding_non_mode_count,
                "funding_residue_mod_8h_counts": funding_residue,
                "nearest_funding_delta_seconds_histogram": nearest_delta["histogram"],
                "most_common_nearest_funding_delta_microseconds": (
                    nearest_delta["most_common_delta_microseconds"]
                ),
                "most_common_nearest_funding_delta_seconds": (
                    nearest_delta["most_common_delta_seconds"]
                ),
                "nearest_delta_sample_size": nearest_delta["sample_size"],
                "nearest_delta_zero_microseconds_count": (
                    nearest_delta["zero_microseconds_count"]
                ),
                "nearest_delta_subsecond_nonzero_count": (
                    nearest_delta["subsecond_nonzero_count"]
                ),
                "nearest_delta_max_abs_microseconds": (
                    nearest_delta["max_abs_microseconds"]
                ),
                "nearest_delta_precision": "SIGNED_MICROSECONDS",
                "nearest_delta_truncation_policy": "NO_TRUNCATION",
                "splits": split_diagnostics,
                "calculation_status": (
                    "FUNDING_TO_BARS_TIMESTAMP_CONVENTION_DIAGNOSTIC_ONLY"
                ),
                "funding_application_status": "NOT_EXECUTED",
            }
        )

    return {
        "calculation_status": "FUNDING_TO_BARS_TIMESTAMP_CONVENTION_DIAGNOSTIC_ONLY",
        "timestamp_match_policy": (
            "DIAGNOSTIC_EXACT_AND_SHIFTED_UTC_TIMESTAMP_SETS_ONLY"
        ),
        "funding_application_status": "NOT_EXECUTED",
        "symbol_count": len(symbols),
        "candidate_offsets": [
            {"offset_label": label, "offset_seconds": seconds}
            for label, seconds in validated_offsets
        ],
        "symbols": symbols,
    }


# ── Funding-to-bars timestamp canonicalization diagnostics ─────────────


_CANONICALIZATION_POLICIES: tuple[tuple[str, Any], ...] = (
    ("floor_to_second", _canonicalize_timestamp_floor),
    ("round_half_away_from_zero", _canonicalize_timestamp_round_half_away_from_zero),
    ("ceil_to_second", _canonicalize_timestamp_ceil),
)


def _validate_canonicalization_policy(policy_name: str) -> None:
    """Fail closed if *policy_name* is not a known canonicalization policy."""
    known = {p[0] for p in _CANONICALIZATION_POLICIES}
    if policy_name not in known:
        raise ValueError(
            f"Invalid canonicalization policy: {policy_name!r}. "
            f"Known: {sorted(known)}"
        )


def _canonicalization_delta_histogram(
    raw_timestamps: list[datetime],
    canonicalized: list[str],
) -> dict[str, int]:
    """Compute histogram of absolute delta microseconds between raw and canonical.

    Returns dict mapping ``"<delta_us>"`` (as string) to count, deterministically
    ordered by ascending delta.
    """
    deltas: dict[int, int] = {}
    for raw_dt, canon_str in zip(raw_timestamps, canonicalized):
        canon_dt = _parse_timestamp(canon_str)
        delta_us = abs(_timedelta_to_microseconds(raw_dt - canon_dt))
        deltas[delta_us] = deltas.get(delta_us, 0) + 1
    return {str(k): deltas[k] for k in sorted(deltas)}


def _canonicalization_status(
    canonicalized_set: set[str],
    bars_set: set[str],
) -> str:
    """Classify the relationship between canonicalized funding and bars timestamp sets."""
    if not canonicalized_set and not bars_set:
        return "EMPTY_BOTH"
    matched = len(canonicalized_set & bars_set)
    if matched == 0:
        return "NO_CANONICAL_TIMESTAMP_MATCH"
    if canonicalized_set == bars_set:
        return "EXACT_CANONICAL_TIMESTAMP_SET_MATCH"
    return "PARTIAL_CANONICAL_TIMESTAMP_SET_MATCH"


def _per_policy_canonicalization_diagnostics(
    *,
    policy_name: str,
    policy_fn: Any,
    raw_funding_ts: list[datetime],
    bars_ts: list[datetime],
    bars_ts_strs: list[str],
) -> dict[str, Any]:
    """Compute canonicalization diagnostics for a single policy."""
    canonicalized_strs: list[str] = [policy_fn(ts) for ts in raw_funding_ts]
    canonicalized_set: set[str] = set(canonicalized_strs)
    bars_set: set[str] = set(bars_ts_strs)

    collision = _detect_canonicalized_collisions(canonicalized_strs)
    status = _canonicalization_status(canonicalized_set, bars_set)
    exact_matched = len(canonicalized_set & bars_set)
    bars_without = len(bars_set - canonicalized_set)
    funding_without = len(canonicalized_set - bars_set)
    bars_ratio = _safe_ratio(exact_matched, len(bars_set))
    funding_ratio = _safe_ratio(exact_matched, len(canonicalized_set))
    ambiguous = _detect_ambiguous_nearest_bars(
        raw_funding_ts, bars_ts, canonicalized_strs
    )
    delta_hist = _canonicalization_delta_histogram(raw_funding_ts, canonicalized_strs)
    max_abs_delta = max((int(k) for k in delta_hist), default=0)

    return {
        "policy_name": policy_name,
        "canonicalized_funding_timestamp_count": len(canonicalized_set),
        "bars_timestamp_count": len(bars_set),
        "exact_matched_after_canonicalization_count": exact_matched,
        "bars_without_canonicalized_funding_count": bars_without,
        "canonicalized_funding_without_bars_count": funding_without,
        "bars_match_ratio_after_canonicalization": bars_ratio,
        "funding_match_ratio_after_canonicalization": funding_ratio,
        "canonicalization_status": status,
        "funding_timestamp_collision_count": collision["collision_count"],
        "max_collision_bucket_size": collision["max_bucket_size"],
        "collision_examples": collision["collision_examples"],
        "ambiguous_nearest_bar_count": ambiguous,
        "max_abs_canonicalization_delta_microseconds": max_abs_delta,
        "canonicalization_delta_microseconds_histogram": delta_hist,
    }


def materialize_funding_to_bars_timestamp_canonicalization_diagnostics(
    *,
    inventory: dict[str, Any],
    split_definitions: list[dict[str, Any]],
) -> dict[str, Any]:
    """Diagnose timestamp canonicalization between funding and bars timestamps.

    For each symbol, applies three canonicalization policies (floor, round,
    ceil) to funding timestamps and compares the resulting whole-second UTC
    sets against bars timestamps. Reports collisions, ambiguous nearest bars,
    subsecond jitter, history range status, and per-split diagnostics.

    This performs no price/rate reads, applies no funding to bars, and
    computes no strategy, PnL, Sharpe, risk, or portfolio values.
    """
    windows = _build_split_windows_for_joinability(split_definitions)

    roles = inventory.get("roles")
    if not isinstance(roles, list):
        raise ValueError("inventory.roles must be a list")
    role_entries: dict[str, dict[str, Any]] = {}
    for role_entry in roles:
        if not isinstance(role_entry, dict):
            raise ValueError("inventory role entry must be a mapping")
        role = role_entry.get("role")
        if role not in _ROLE_TIMESTAMP_COLUMNS:
            raise ValueError(f"Unsupported inventoried role: {role!r}")
        if role in role_entries:
            raise ValueError(f"Duplicate inventoried role: {role}")
        role_entries[role] = role_entry

    if "bars" not in role_entries or "funding" not in role_entries:
        raise ValueError(
            "funding-to-bars timestamp canonicalization diagnostics require both "
            "bars and funding roles in the inventory"
        )

    bars_by_symbol = _load_role_symbol_timestamps(
        role_entry=role_entries["bars"],
        filename_suffix="_8h_ohlcv.csv",
        timestamp_column="timestamp",
        role="bars",
    )
    funding_by_symbol = _load_role_symbol_timestamps(
        role_entry=role_entries["funding"],
        filename_suffix="_funding.csv",
        timestamp_column="fundingTime",
        role="funding",
    )

    bars_symbols = set(bars_by_symbol)
    funding_symbols = set(funding_by_symbol)
    if bars_symbols != funding_symbols:
        missing = sorted(bars_symbols - funding_symbols)
        extra = sorted(funding_symbols - bars_symbols)
        raise ValueError(
            f"Symbol mismatch between bars and funding: missing={missing}, "
            f"extra={extra}"
        )

    symbols: list[dict[str, Any]] = []
    for symbol in sorted(bars_symbols):
        bars_entry = bars_by_symbol[symbol]
        funding_entry = funding_by_symbol[symbol]
        bars_timestamps: list[datetime] = bars_entry["timestamps"]
        funding_timestamps: list[datetime] = funding_entry["timestamps"]

        bars_ts_strs: list[str] = [_format_timestamp(ts) for ts in bars_timestamps]
        funding_ts_strs: list[str] = [
            _format_timestamp(ts) for ts in funding_timestamps
        ]

        # Per-policy diagnostics.
        policy_results: list[dict[str, Any]] = []
        for policy_name, policy_fn in _CANONICALIZATION_POLICIES:
            policy_result = _per_policy_canonicalization_diagnostics(
                policy_name=policy_name,
                policy_fn=policy_fn,
                raw_funding_ts=funding_timestamps,
                bars_ts=bars_timestamps,
                bars_ts_strs=bars_ts_strs,
            )
            policy_results.append(policy_result)

        # Best policy selection.
        best_policy = _select_best_policy(policy_results)

        # Structural flags.
        raw_history_range_status = _compute_history_range_status(
            bars_timestamps, funding_timestamps
        )
        jitter = _compute_subsecond_jitter_stats(funding_timestamps)

        # Per-policy canonicalized range status (avoids false range mismatch
        # when bars are whole-second and funding has subsecond jitter).
        per_policy_range_status: dict[str, str] = {}
        for pname, pfn in _CANONICALIZATION_POLICIES:
            canon_funding_dts = [_parse_timestamp(pfn(ts)) for ts in funding_timestamps]
            per_policy_range_status[pname] = _compute_history_range_status(
                bars_timestamps, canon_funding_dts
            )

        bars_set = set(bars_ts_strs)
        canonicalized_sets = {
            p["policy_name"]: set(
                _canonicalize_timestamp_floor(ts) if p["policy_name"] == "floor_to_second"
                else _canonicalize_timestamp_ceil(ts) if p["policy_name"] == "ceil_to_second"
                else _canonicalize_timestamp_round_half_away_from_zero(ts)
                for ts in funding_timestamps
            )
            for p in policy_results
        }
        # Use floor as reference for outside-range counts.
        floor_canonicalized = set(
            _canonicalize_timestamp_floor(ts) for ts in funding_timestamps
        )
        bars_first = bars_timestamps[0] if bars_timestamps else None
        bars_last = bars_timestamps[-1] if bars_timestamps else None
        funding_first = funding_timestamps[0] if funding_timestamps else None
        funding_last = funding_timestamps[-1] if funding_timestamps else None

        extra_funding_outside = 0
        if bars_first is not None and bars_last is not None:
            for ts_str in floor_canonicalized:
                ts_dt = _parse_timestamp(ts_str)
                if ts_dt < bars_first or ts_dt > bars_last:
                    extra_funding_outside += 1

        extra_bars_outside = 0
        if funding_first is not None and funding_last is not None:
            for ts_str in bars_ts_strs:
                ts_dt = _parse_timestamp(ts_str)
                if ts_dt < funding_first or ts_dt > funding_last:
                    extra_bars_outside += 1

        # Per-split diagnostics.
        per_split_diagnostics: dict[str, dict[str, Any]] = {}
        for window in windows:
            split_id = window["split_id"]
            train_bars = {
                ts
                for ts in bars_timestamps
                if _timestamp_in_window(
                    ts, start=window["train_start"], end=window["train_end"]
                )
            }
            train_funding = {
                ts
                for ts in funding_timestamps
                if _timestamp_in_window(
                    ts, start=window["train_start"], end=window["train_end"]
                )
            }
            validation_bars = {
                ts
                for ts in bars_timestamps
                if _timestamp_in_window(
                    ts,
                    start=window["validation_start"],
                    end=window["validation_end"],
                    include_end=window["include_validation_end"],
                )
            }
            validation_funding = {
                ts
                for ts in funding_timestamps
                if _timestamp_in_window(
                    ts,
                    start=window["validation_start"],
                    end=window["validation_end"],
                    include_end=window["include_validation_end"],
                )
            }

            train_bars_strs = [_format_timestamp(ts) for ts in sorted(train_bars)]
            val_bars_strs = [_format_timestamp(ts) for ts in sorted(validation_bars)]

            train_policy_results: list[dict[str, Any]] = []
            for policy_name, policy_fn in _CANONICALIZATION_POLICIES:
                train_policy_results.append(
                    _per_policy_canonicalization_diagnostics(
                        policy_name=policy_name,
                        policy_fn=policy_fn,
                        raw_funding_ts=sorted(train_funding),
                        bars_ts=sorted(train_bars),
                        bars_ts_strs=train_bars_strs,
                    )
                )

            val_policy_results: list[dict[str, Any]] = []
            for policy_name, policy_fn in _CANONICALIZATION_POLICIES:
                val_policy_results.append(
                    _per_policy_canonicalization_diagnostics(
                        policy_name=policy_name,
                        policy_fn=policy_fn,
                        raw_funding_ts=sorted(validation_funding),
                        bars_ts=sorted(validation_bars),
                        bars_ts_strs=val_bars_strs,
                    )
                )

            per_split_diagnostics[split_id] = {
                "train": train_policy_results,
                "validation": val_policy_results,
            }

        symbols.append(
            {
                "symbol": symbol,
                "bars_file": bars_entry["filename"],
                "funding_file": funding_entry["filename"],
                "canonicalization_policies": policy_results,
                "best_policy_summary": best_policy,
                "structural_flags": {
                    "raw_history_range_status": raw_history_range_status,
                    "extra_funding_timestamps_outside_bars_range_count": (
                        extra_funding_outside
                    ),
                    "bars_timestamps_outside_funding_range_count": extra_bars_outside,
                    "has_subsecond_funding_jitter": jitter["has_subsecond_funding_jitter"],
                    "funding_subsecond_timestamp_count": jitter[
                        "funding_subsecond_timestamp_count"
                    ],
                    "max_abs_subsecond_jitter_microseconds": jitter[
                        "max_abs_subsecond_jitter_microseconds"
                    ],
                    "floor_canonicalized_history_range_status": (
                        per_policy_range_status["floor_to_second"]
                    ),
                    "round_canonicalized_history_range_status": (
                        per_policy_range_status["round_half_away_from_zero"]
                    ),
                    "ceil_canonicalized_history_range_status": (
                        per_policy_range_status["ceil_to_second"]
                    ),
                },
                "per_split_diagnostics": per_split_diagnostics,
                "calculation_status": (
                    "FUNDING_TO_BARS_TIMESTAMP_CANONICALIZATION_DIAGNOSTIC_ONLY"
                ),
                "funding_application_status": "NOT_EXECUTED",
            }
        )

    return {
        "calculation_status": "FUNDING_TO_BARS_TIMESTAMP_CANONICALIZATION_DIAGNOSTIC_ONLY",
        "canonicalization_policy": "DIAGNOSTIC_WHOLE_SECOND_UTC_ONLY",
        "funding_application_status": "NOT_EXECUTED",
        "symbol_count": len(symbols),
        "symbols": symbols,
    }


_READINESS_POLICY = "floor_to_second"
_READINESS_EXACT_STATUS = "EXACT_CANONICAL_TIMESTAMP_SET_MATCH"


def _diagnostic_symbols(section: Any) -> dict[str, dict[str, Any]]:
    if not isinstance(section, dict) or not isinstance(section.get("symbols"), list):
        return {}
    return {
        str(item["symbol"]): item
        for item in section["symbols"]
        if isinstance(item, dict) and isinstance(item.get("symbol"), str)
    }


def _readiness_reasons(evidence: dict[str, Any]) -> list[str]:
    """Return controlled, deterministically ordered readiness blockers."""
    reasons: list[str] = []
    bars = evidence.get("bars_timestamp_count")
    funding = evidence.get("canonicalized_funding_timestamp_count")
    matched = evidence.get("exact_matched_after_canonicalization_count")
    status = evidence.get("canonicalization_status")
    if not all(isinstance(value, int) for value in (bars, funding, matched)):
        reasons.append("MISSING_POLICY_DIAGNOSTICS")
    elif bars != funding or matched != bars or matched != funding:
        reasons.append("COUNT_MISMATCH")
    if status == "PARTIAL_CANONICAL_TIMESTAMP_SET_MATCH":
        reasons.append("PARTIAL_CANONICAL_TIMESTAMP_SET_MATCH")
    elif status == "NO_CANONICAL_TIMESTAMP_MATCH":
        reasons.append("NO_CANONICAL_TIMESTAMP_MATCH")
    elif status != _READINESS_EXACT_STATUS:
        reasons.append("UNEXPECTED_STATUS")
    checks = (
        (
            "canonicalized_funding_without_bars_count",
            "CANONICALIZED_FUNDING_WITHOUT_BARS",
        ),
        (
            "bars_without_canonicalized_funding_count",
            "BARS_WITHOUT_CANONICALIZED_FUNDING",
        ),
        ("funding_timestamp_collision_count", "CANONICALIZED_TIMESTAMP_COLLISION"),
        ("ambiguous_nearest_bar_count", "AMBIGUOUS_NEAREST_BAR"),
    )
    for field, reason in checks:
        value = evidence.get(field)
        if not isinstance(value, int):
            if "MISSING_POLICY_DIAGNOSTICS" not in reasons:
                reasons.append("MISSING_POLICY_DIAGNOSTICS")
        elif value > 0:
            reasons.append(reason)
    return reasons


def _split_readiness(split_id: str, partition: str, policies: Any) -> dict[str, Any]:
    floor = (
        next(
            (
                policy
                for policy in policies
                if isinstance(policy, dict)
                and policy.get("policy_name") == _READINESS_POLICY
            ),
            None,
        )
        if isinstance(policies, list)
        else None
    )
    if floor is None:
        evidence: dict[str, Any] = {}
        reasons = ["MISSING_POLICY_DIAGNOSTICS"]
        empty_status = "NOT_EMPTY"
    else:
        evidence = {
            "bars_count": floor.get("bars_timestamp_count"),
            "canonicalized_funding_count": floor.get(
                "canonicalized_funding_timestamp_count"
            ),
            "exact_matched_after_canonicalization_count": floor.get(
                "exact_matched_after_canonicalization_count"
            ),
            "bars_without_canonicalized_funding_count": floor.get(
                "bars_without_canonicalized_funding_count"
            ),
            "canonicalized_funding_without_bars_count": floor.get(
                "canonicalized_funding_without_bars_count"
            ),
            "canonicalization_status": floor.get("canonicalization_status"),
            "funding_timestamp_collision_count": floor.get(
                "funding_timestamp_collision_count"
            ),
            "ambiguous_nearest_bar_count": floor.get("ambiguous_nearest_bar_count"),
        }
        normalized = dict(evidence)
        normalized["bars_timestamp_count"] = evidence["bars_count"]
        normalized["canonicalized_funding_timestamp_count"] = evidence[
            "canonicalized_funding_count"
        ]
        bars, funding = evidence["bars_count"], evidence["canonicalized_funding_count"]
        if bars == 0 and funding == 0:
            empty_status, reasons = "EMPTY_BOTH_NOT_BLOCKING", []
        elif bars == 0 and isinstance(funding, int) and funding > 0:
            empty_status = "EMPTY_BARS_NONEMPTY_FUNDING_BLOCKING"
            reasons = ["EMPTY_BARS_NONEMPTY_FUNDING"] + _readiness_reasons(
                normalized
            )
        elif funding == 0 and isinstance(bars, int) and bars > 0:
            empty_status = "EMPTY_FUNDING_NONEMPTY_BARS_BLOCKING"
            reasons = ["EMPTY_FUNDING_NONEMPTY_BARS"] + _readiness_reasons(
                normalized
            )
        else:
            empty_status, reasons = "NOT_EMPTY", _readiness_reasons(normalized)
    eligible = not reasons
    return {
        "split_id": split_id,
        "partition": partition,
        "readiness_status": (
            "ELIGIBLE_FOR_FUTURE_FUNDING_APPLICATION" if eligible
            else "BLOCKED_FOR_FUTURE_FUNDING_APPLICATION"
        ),
        "eligible_for_future_funding_application": eligible,
        "empty_window_status": empty_status,
        "blocked_reasons": list(dict.fromkeys(reasons)),
        "evidence": evidence,
    }


def materialize_funding_application_readiness_gate_diagnostics(
    *,
    funding_to_bars_alignment_diagnostics: dict,
    funding_to_bars_temporal_joinability_diagnostics: dict,
    funding_to_bars_timestamp_convention_diagnostics: dict,
    funding_to_bars_timestamp_canonicalization_diagnostics: dict,
) -> dict[str, Any]:
    """Classify future funding-application readiness from existing evidence only."""
    canonical = _diagnostic_symbols(
        funding_to_bars_timestamp_canonicalization_diagnostics
    )
    corroborating = [
        _diagnostic_symbols(funding_to_bars_alignment_diagnostics),
        _diagnostic_symbols(funding_to_bars_temporal_joinability_diagnostics),
        _diagnostic_symbols(funding_to_bars_timestamp_convention_diagnostics),
    ]
    all_symbols = sorted(set(canonical).union(*(set(item) for item in corroborating)))
    symbols: list[dict[str, Any]] = []
    for symbol_name in all_symbols:
        source = canonical.get(symbol_name)
        missing_canonical = source is None
        floor = (
            next(
                (
                    policy
                    for policy in source.get("canonicalization_policies", [])
                    if isinstance(policy, dict)
                    and policy.get("policy_name") == _READINESS_POLICY
                ),
                None,
            )
            if source
            else None
        )
        evidence = {
            key: (floor.get(key) if floor else None)
            for key in (
                "bars_timestamp_count",
                "canonicalized_funding_timestamp_count",
                "exact_matched_after_canonicalization_count",
                "bars_without_canonicalized_funding_count",
                "canonicalized_funding_without_bars_count",
                "canonicalization_status",
                "funding_timestamp_collision_count",
                "ambiguous_nearest_bar_count",
            )
        }
        flags = source.get("structural_flags", {}) if source else {}
        evidence.update(
            {
                "floor_canonicalized_history_range_status": flags.get(
                    "floor_canonicalized_history_range_status"
                ),
                "extra_funding_timestamps_outside_bars_range_count": flags.get(
                    "extra_funding_timestamps_outside_bars_range_count"
                ),
                "bars_timestamps_outside_funding_range_count": flags.get(
                    "bars_timestamps_outside_funding_range_count"
                ),
            }
        )
        reasons = (
            ["MISSING_CANONICALIZATION_DIAGNOSTICS"]
            if missing_canonical
            else _readiness_reasons(evidence)
        )
        if any(symbol_name not in item for item in corroborating):
            reasons.append("MISSING_POLICY_DIAGNOSTICS")
        if evidence["floor_canonicalized_history_range_status"] != "MATCHING_RANGES":
            reasons.append(
                "RANGE_MISMATCH"
                if evidence["floor_canonicalized_history_range_status"] is not None
                else "MISSING_POLICY_DIAGNOSTICS"
            )
        for field, reason in (
            (
                "extra_funding_timestamps_outside_bars_range_count",
                "EXTRA_FUNDING_OUTSIDE_BARS_RANGE",
            ),
            (
                "bars_timestamps_outside_funding_range_count",
                "BARS_OUTSIDE_FUNDING_RANGE",
            ),
        ):
            value = evidence[field]
            if isinstance(value, int) and value > 0:
                reasons.append(reason)
            elif not isinstance(value, int):
                reasons.append("MISSING_POLICY_DIAGNOSTICS")
        splits = [
            _split_readiness(split_id, partition, partitions.get(partition))
            for split_id, partitions in sorted(
                (source or {}).get("per_split_diagnostics", {}).items()
            )
            for partition in ("train", "validation")
        ]
        if not isinstance((source or {}).get("per_split_diagnostics"), dict):
            reasons.append("MISSING_POLICY_DIAGNOSTICS")
        if any(not split["eligible_for_future_funding_application"] for split in splits):
            reasons.extend(
                reason for split in splits for reason in split["blocked_reasons"]
            )
        reasons = list(dict.fromkeys(reasons))
        eligible = not reasons
        symbols.append(
            {
                "symbol": symbol_name,
                "readiness_status": (
                    "ELIGIBLE_FOR_FUTURE_FUNDING_APPLICATION"
                    if eligible
                    else "BLOCKED_FOR_FUTURE_FUNDING_APPLICATION"
                ),
                "eligible_for_future_funding_application": eligible,
                "canonicalization_policy": _READINESS_POLICY,
                "blocked_reasons": reasons,
                "evidence": evidence,
                "splits": splits,
            }
        )
    eligible_count = sum(
        item["eligible_for_future_funding_application"] for item in symbols
    )
    return {
        "calculation_status": "FUNDING_APPLICATION_READINESS_GATE_DIAGNOSTIC_ONLY",
        "funding_application_status": "NOT_EXECUTED",
        "readiness_policy": (
            "STRICT_CANONICAL_TIMESTAMP_EXACT_MATCH_NO_COLLISION_NO_AMBIGUITY"
        ),
        "canonicalization_policy_considered": _READINESS_POLICY,
        "symbol_count": len(symbols),
        "eligible_symbol_count": eligible_count,
        "blocked_symbol_count": len(symbols) - eligible_count,
        "symbols": symbols,
    }


def _canonicalize_floor_to_second(ts: str) -> str:
    """Canonicalize a timestamp by truncating sub-second precision (floor)."""
    dt = _parse_timestamp(ts)
    dt = dt.replace(microsecond=0)
    return _format_timestamp(dt)


# ── Scaffold readiness gate validators ──────────────────────────────────


def _validate_scaffold_readiness_gate(rd: dict) -> None:
    """Validate top-level readiness gate fields. Fail closed on any mismatch."""
    if not isinstance(rd, dict):
        raise ValueError(f"Readiness gate must be a dict, got {type(rd).__name__}")

    expected_calculation_status = FUNDING_APPLICATION_READINESS_GATE_DIAGNOSTIC_ONLY
    actual_calculation_status = rd.get("calculation_status")
    if actual_calculation_status != expected_calculation_status:
        raise ValueError(
            f"Expected calculation_status={expected_calculation_status!r}, "
            f"got {actual_calculation_status!r}"
        )

    expected_funding_application_status = NOT_EXECUTED
    actual_funding_application_status = rd.get("funding_application_status")
    if actual_funding_application_status != expected_funding_application_status:
        raise ValueError(
            f"Expected funding_application_status={expected_funding_application_status!r}, "
            f"got {actual_funding_application_status!r}"
        )

    expected_readiness_policy = STRICT_CANONICAL_TIMESTAMP_EXACT_MATCH_NO_COLLISION_NO_AMBIGUITY
    actual_readiness_policy = rd.get("readiness_policy")
    if actual_readiness_policy != expected_readiness_policy:
        raise ValueError(
            f"Expected readiness_policy={expected_readiness_policy!r}, "
            f"got {actual_readiness_policy!r}"
        )

    expected_canonicalization_policy = FLOOR_TO_SECOND
    actual_canonicalization_policy = rd.get("canonicalization_policy_considered")
    if actual_canonicalization_policy != expected_canonicalization_policy:
        raise ValueError(
            f"Expected canonicalization_policy_considered={expected_canonicalization_policy!r}, "
            f"got {actual_canonicalization_policy!r}"
        )

    symbols = rd.get("symbols")
    if not isinstance(symbols, list):
        raise ValueError(f"Expected symbols to be a list, got {type(symbols).__name__}")

    symbol_count = rd.get("symbol_count")
    if not isinstance(symbol_count, int) or symbol_count != len(symbols):
        raise ValueError(
            f"symbol_count ({symbol_count}) must equal len(symbols) ({len(symbols)})"
        )

    eligible_count = rd.get("eligible_symbol_count")
    blocked_count = rd.get("blocked_symbol_count")

    counted_eligible = sum(
        1 for s in symbols
        if isinstance(s, dict) and s.get("readiness_status") == ELIGIBLE_FOR_FUTURE_FUNDING_APPLICATION
    )
    counted_blocked = sum(
        1 for s in symbols
        if isinstance(s, dict) and s.get("readiness_status") == BLOCKED_FOR_FUTURE_FUNDING_APPLICATION
    )

    if eligible_count != counted_eligible:
        raise ValueError(
            f"eligible_symbol_count ({eligible_count}) must equal counted eligible ({counted_eligible})"
        )
    if blocked_count != counted_blocked:
        raise ValueError(
            f"blocked_symbol_count ({blocked_count}) must equal counted blocked ({counted_blocked})"
        )


def _validate_readiness_symbol_entry(entry: dict) -> str:
    """Validate a single readiness symbol entry. Returns the readiness_status."""
    if not isinstance(entry, dict):
        raise ValueError(f"Symbol entry must be a dict, got {type(entry).__name__}")

    symbol = entry.get("symbol")
    if not isinstance(symbol, str) or not symbol:
        raise ValueError(f"Symbol must be a non-empty string, got {symbol!r}")

    status = entry.get("readiness_status")
    if status not in _VALID_READINESS_STATUSES:
        raise ValueError(
            f"Invalid readiness_status {status!r} for symbol {symbol!r}. "
            f"Must be one of {_VALID_READINESS_STATUSES}"
        )

    eligible_bool = entry.get("eligible_for_future_funding_application")
    if not isinstance(eligible_bool, bool):
        raise ValueError(
            f"eligible_for_future_funding_application must be bool for {symbol!r}, "
            f"got {type(eligible_bool).__name__}"
        )

    is_eligible = (status == ELIGIBLE_FOR_FUTURE_FUNDING_APPLICATION)
    if eligible_bool != is_eligible:
        raise ValueError(
            f"eligible_for_future_funding_application={eligible_bool} inconsistent "
            f"with readiness_status={status!r} for {symbol!r}"
        )

    policy = entry.get("canonicalization_policy")
    if policy != FLOOR_TO_SECOND:
        raise ValueError(
            f"Expected canonicalization_policy={FLOOR_TO_SECOND!r} for {symbol!r}, "
            f"got {policy!r}"
        )

    reasons = entry.get("blocked_reasons")
    if not isinstance(reasons, list):
        raise ValueError(
            f"blocked_reasons must be a list for {symbol!r}, got {type(reasons).__name__}"
        )

    return status


def _validate_eligible_readiness_evidence(
    entry: dict,
    symbol: str,
    canonicalization_diagnostics: dict,
) -> None:
    """Validate that an eligible symbol has exact readiness evidence."""
    reasons = entry.get("blocked_reasons", [])
    if reasons:
        raise ValueError(
            f"Eligible symbol {symbol!r} has non-empty blocked_reasons: {reasons}"
        )

    evidence = entry.get("evidence")
    if not isinstance(evidence, dict):
        raise ValueError(
            f"Eligible symbol {symbol!r} missing evidence or evidence is not a dict"
        )

    bars_count = evidence.get("bars_timestamp_count")
    if not isinstance(bars_count, int):
        raise ValueError(f"bars_timestamp_count must be int for {symbol!r}")

    canonicalized_funding_count = evidence.get("canonicalized_funding_timestamp_count")
    if not isinstance(canonicalized_funding_count, int):
        raise ValueError(f"canonicalized_funding_timestamp_count must be int for {symbol!r}")

    exact_matched_count = evidence.get("exact_matched_after_canonicalization_count")
    if not isinstance(exact_matched_count, int):
        raise ValueError(f"exact_matched_after_canonicalization_count must be int for {symbol!r}")

    bars_without_funding = evidence.get("bars_without_canonicalized_funding_count")
    if bars_without_funding != 0:
        raise ValueError(
            f"bars_without_canonicalized_funding_count must be 0 for eligible {symbol!r}, "
            f"got {bars_without_funding}"
        )

    funding_without_bars = evidence.get("canonicalized_funding_without_bars_count")
    if funding_without_bars != 0:
        raise ValueError(
            f"canonicalized_funding_without_bars_count must be 0 for eligible {symbol!r}, "
            f"got {funding_without_bars}"
        )

    can_status = evidence.get("canonicalization_status")
    if can_status != EXACT_CANONICAL_TIMESTAMP_SET_MATCH:
        raise ValueError(
            f"Expected canonicalization_status={EXACT_CANONICAL_TIMESTAMP_SET_MATCH!r} "
            f"for eligible {symbol!r}, got {can_status!r}"
        )

    collision_count = evidence.get("funding_timestamp_collision_count")
    if collision_count != 0:
        raise ValueError(
            f"funding_timestamp_collision_count must be 0 for eligible {symbol!r}, "
            f"got {collision_count}"
        )

    ambiguous_count = evidence.get("ambiguous_nearest_bar_count")
    if ambiguous_count != 0:
        raise ValueError(
            f"ambiguous_nearest_bar_count must be 0 for eligible {symbol!r}, "
            f"got {ambiguous_count}"
        )

    range_status = evidence.get("floor_canonicalized_history_range_status")
    if range_status != MATCHING_RANGES:
        raise ValueError(
            f"Expected floor_canonicalized_history_range_status={MATCHING_RANGES!r} "
            f"for eligible {symbol!r}, got {range_status!r}"
        )

    extra_funding = evidence.get("extra_funding_timestamps_outside_bars_range_count")
    if extra_funding != 0:
        raise ValueError(
            f"extra_funding_timestamps_outside_bars_range_count must be 0 "
            f"for eligible {symbol!r}, got {extra_funding}"
        )

    extra_bars = evidence.get("bars_timestamps_outside_funding_range_count")
    if extra_bars != 0:
        raise ValueError(
            f"bars_timestamps_outside_funding_range_count must be 0 "
            f"for eligible {symbol!r}, got {extra_bars}"
        )

    # Cross-checks: bars_count == canonicalized_funding_count == exact_matched_count
    if bars_count != canonicalized_funding_count:
        raise ValueError(
            f"bars_timestamp_count ({bars_count}) != canonicalized_funding_timestamp_count "
            f"({canonicalized_funding_count}) for eligible {symbol!r}"
        )
    if exact_matched_count != bars_count:
        raise ValueError(
            f"exact_matched_after_canonicalization_count ({exact_matched_count}) "
            f"!= bars_timestamp_count ({bars_count}) for eligible {symbol!r}"
        )
    if exact_matched_count != canonicalized_funding_count:
        raise ValueError(
            f"exact_matched_after_canonicalization_count ({exact_matched_count}) "
            f"!= canonicalized_funding_timestamp_count ({canonicalized_funding_count}) "
            f"for eligible {symbol!r}"
        )

    # Split partitions validation — split diagnostics live at the symbol-entry
    # level (entry["splits"]) as emitted by
    # materialize_funding_application_readiness_gate_diagnostics, not inside
    # evidence. Missing or malformed split diagnostics must fail closed rather
    # than be silently skipped.
    splits = entry.get("splits")
    if not isinstance(splits, list):
        raise ValueError(
            f"Eligible symbol {symbol!r} missing splits or splits is not a list, "
            f"got {type(splits).__name__}"
        )

    for index, split_entry in enumerate(splits):
        if not isinstance(split_entry, dict):
            raise ValueError(
                f"Split partition at index {index} must be a dict for eligible "
                f"symbol {symbol!r}, got {type(split_entry).__name__}"
            )

        split_id = split_entry.get("split_id")
        split_eligible = split_entry.get("eligible_for_future_funding_application")
        split_readiness_status = split_entry.get("readiness_status")
        empty_window_status = split_entry.get("empty_window_status")
        split_blocked_reasons = split_entry.get("blocked_reasons")

        if not isinstance(split_blocked_reasons, list):
            raise ValueError(
                f"Split partition {split_id!r} blocked_reasons must be a list "
                f"for eligible symbol {symbol!r}, got "
                f"{type(split_blocked_reasons).__name__}"
            )

        is_eligible_split = (
            split_eligible is True
            and split_readiness_status == ELIGIBLE_FOR_FUTURE_FUNDING_APPLICATION
        )
        is_empty_not_blocking_split = (
            empty_window_status == EMPTY_BOTH_NOT_BLOCKING
            and not split_blocked_reasons
        )

        if not (is_eligible_split or is_empty_not_blocking_split):
            raise ValueError(
                f"Blocked, malformed, or one-sided-empty split partition "
                f"{split_id!r} for eligible symbol {symbol!r}: "
                f"eligible_for_future_funding_application={split_eligible!r}, "
                f"readiness_status={split_readiness_status!r}, "
                f"empty_window_status={empty_window_status!r}, "
                f"blocked_reasons={split_blocked_reasons!r}"
            )

    # Cross-check canonicalization diagnostics
    _canonicalization_symbol_policy(symbol, canonicalization_diagnostics, bars_count)


def _canonicalization_symbol_policy(
    symbol: str,
    canonicalization_diagnostics: dict,
    bars_count: int,
) -> None:
    """Cross-check that readiness evidence agrees with canonicalization diagnostics.

    The canonicalization diagnostics dict has per-symbol entries, each containing
    a list of per-policy diagnostic dicts. We find the floor_to_second policy
    entry and validate it against the readiness evidence.
    """
    if not isinstance(canonicalization_diagnostics, dict):
        raise ValueError("canonicalization_diagnostics must be a dict")

    diag_symbols = canonicalization_diagnostics.get("symbols")
    if not isinstance(diag_symbols, list):
        raise ValueError("canonicalization_diagnostics.symbols must be a list")

    # Find this symbol in canonicalization diagnostics
    diag_entry = None
    for entry in diag_symbols:
        if isinstance(entry, dict) and entry.get("symbol") == symbol:
            diag_entry = entry
            break

    if diag_entry is None:
        raise ValueError(
            f"Symbol {symbol!r} not found in canonicalization_diagnostics.symbols"
        )

    # Find the floor_to_second policy in the per-symbol policies list
    policies = diag_entry.get("canonicalization_policies", [])
    if not isinstance(policies, list):
        raise ValueError(
            f"canonicalization_policies must be a list for {symbol!r}"
        )

    floor_policy = None
    for policy in policies:
        if isinstance(policy, dict) and policy.get("policy_name") == FLOOR_TO_SECOND:
            floor_policy = policy
            break

    if floor_policy is None:
        raise ValueError(
            f"No floor_to_second policy found in canonicalization_policies for {symbol!r}"
        )

    # All policy-level fields below are mandatory for eligible funding scaffold
    # materialization: a missing field must raise, not be silently treated as
    # a pass-through optional value.
    _missing = object()

    def _require_policy_field(field: str) -> Any:
        value = floor_policy.get(field, _missing)
        if value is _missing:
            raise ValueError(
                f"Missing required canonicalization policy field {field!r} "
                f"for {symbol!r}"
            )
        return value

    policy_name = _require_policy_field("policy_name")
    if policy_name != FLOOR_TO_SECOND:
        raise ValueError(
            f"Canonicalization diagnostic policy_name={policy_name!r} "
            f"for {symbol!r}, expected {FLOOR_TO_SECOND!r}"
        )

    can_status = _require_policy_field("canonicalization_status")
    if can_status != EXACT_CANONICAL_TIMESTAMP_SET_MATCH:
        raise ValueError(
            f"Canonicalization diagnostic canonicalization_status={can_status!r} "
            f"for {symbol!r}, expected {EXACT_CANONICAL_TIMESTAMP_SET_MATCH!r}"
        )

    matched = _require_policy_field("exact_matched_after_canonicalization_count")
    if matched != bars_count:
        raise ValueError(
            f"Canonicalization matched count ({matched}) != bars count ({bars_count}) "
            f"for {symbol!r}"
        )

    funding_count = _require_policy_field("canonicalized_funding_timestamp_count")
    if funding_count != bars_count:
        raise ValueError(
            f"Canonicalization funding count ({funding_count}) != bars count ({bars_count}) "
            f"for {symbol!r}"
        )

    bars_without = _require_policy_field("bars_without_canonicalized_funding_count")
    if bars_without != 0:
        raise ValueError(
            f"bars_without_canonicalized_funding_count ({bars_without}) != 0 "
            f"for {symbol!r}"
        )

    funding_without = _require_policy_field("canonicalized_funding_without_bars_count")
    if funding_without != 0:
        raise ValueError(
            f"canonicalized_funding_without_bars_count ({funding_without}) != 0 "
            f"for {symbol!r}"
        )

    collision = _require_policy_field("funding_timestamp_collision_count")
    if collision != 0:
        raise ValueError(
            f"funding_timestamp_collision_count ({collision}) != 0 for {symbol!r}"
        )

    ambiguous = _require_policy_field("ambiguous_nearest_bar_count")
    if ambiguous != 0:
        raise ValueError(
            f"ambiguous_nearest_bar_count ({ambiguous}) != 0 for {symbol!r}"
        )

    # structural_flags is mandatory and must be a dict.
    structural = diag_entry.get("structural_flags", _missing)
    if structural is _missing:
        raise ValueError(f"Missing required structural_flags for {symbol!r}")
    if not isinstance(structural, dict):
        raise ValueError(
            f"structural_flags must be a dict for {symbol!r}, "
            f"got {type(structural).__name__}"
        )

    range_status = structural.get("floor_canonicalized_history_range_status", _missing)
    if range_status is _missing:
        raise ValueError(
            f"Missing required floor_canonicalized_history_range_status for {symbol!r}"
        )
    if range_status != MATCHING_RANGES:
        raise ValueError(
            f"floor_canonicalized_history_range_status ({range_status!r}) != "
            f"{MATCHING_RANGES!r} for {symbol!r}"
        )


def _validate_blocked_readiness_evidence(entry: dict, symbol: str) -> None:
    """Validate a blocked symbol entry and emit skip signal."""
    status = entry.get("readiness_status")
    if status != BLOCKED_FOR_FUTURE_FUNDING_APPLICATION:
        raise ValueError(
            f"Expected readiness_status={BLOCKED_FOR_FUTURE_FUNDING_APPLICATION!r} "
            f"for blocked symbol {symbol!r}, got {status!r}"
        )

    eligible_bool = entry.get("eligible_for_future_funding_application")
    if eligible_bool is not False:
        raise ValueError(
            f"eligible_for_future_funding_application must be False for blocked "
            f"symbol {symbol!r}, got {eligible_bool!r}"
        )

    reasons = entry.get("blocked_reasons", [])
    if not reasons:
        raise ValueError(
            f"Blocked symbol {symbol!r} has empty blocked_reasons"
        )


def materialize_funding_adjusted_bars_scaffold_diagnostics(
    *,
    funding_application_readiness_gate_diagnostics: dict[str, Any],
    funding_to_bars_timestamp_canonicalization_diagnostics: dict[str, Any],
    bars_inventory: dict[str, Any],
    funding_inventory: dict[str, Any],
    bars_dir: str | None,
    funding_dir: str | None,
    source_sha: str | None,
) -> dict[str, Any]:
    """Materialize diagnostic scaffold rows for funding-adjusted bars.

    This is a scaffold-only diagnostic. It loads bars and funding CSVs for
    symbols deemed eligible by the readiness gate, canonicalizes funding
    timestamps using floor_to_second, and emits row-level metadata proving
    alignment and funding-rate availability.

    No PnL, Sharpe, returns, edge, trades, positions, signals, portfolio,
    drawdown, risk, or live readiness is computed.
    """
    # ── Fail closed ─────────────────────────────────────────────────────
    if not funding_application_readiness_gate_diagnostics:
        raise ValueError(
            "funding_application_readiness_gate_diagnostics is required"
        )
    if not funding_to_bars_timestamp_canonicalization_diagnostics:
        raise ValueError(
            "funding_to_bars_timestamp_canonicalization_diagnostics is required"
        )
    if not source_sha:
        raise ValueError("source_sha is required")

    # Step A: Validate readiness gate top-level structure
    rd = funding_application_readiness_gate_diagnostics
    _validate_scaffold_readiness_gate(rd)

    # ── Index inventory files by symbol ──────────────────────────────────
    bars_files = (
        bars_inventory.get("files") if isinstance(bars_inventory, dict) else None
    )
    funding_files = (
        funding_inventory.get("files")
        if isinstance(funding_inventory, dict)
        else None
    )

    if not isinstance(bars_files, list):
        raise ValueError("bars_inventory must contain a 'files' list")
    if not isinstance(funding_files, list):
        raise ValueError("funding_inventory must contain a 'files' list")

    bars_by_symbol = _files_by_symbol(bars_files, "_8h_ohlcv.csv", "bars")
    funding_by_symbol = _files_by_symbol(funding_files, "_funding.csv", "funding")

    # ── Resolve directories ─────────────────────────────────────────────
    if bars_dir is None:
        raise ValueError("bars_dir is required")
    if funding_dir is None:
        raise ValueError("funding_dir is required")
    bars_dir_path = Path(bars_dir)
    funding_dir_path = Path(funding_dir)

    # ── Extract symbols from readiness gate ─────────────────────────────
    readiness_symbols = rd.get("symbols", [])
    if not isinstance(readiness_symbols, list):
        raise ValueError(
            "funding_application_readiness_gate_diagnostics must contain "
            "a 'symbols' list"
        )

    # Step B: Validate ALL symbol entries, check duplicates, classify BEFORE CSV reads
    seen_symbols: set[str] = set()
    eligible_symbol_entries: list[dict[str, Any]] = []
    blocked_symbol_entries: list[dict[str, Any]] = []

    for entry in readiness_symbols:
        status = _validate_readiness_symbol_entry(entry)
        sym = entry["symbol"]

        if sym in seen_symbols:
            raise ValueError(f"Duplicate symbol {sym!r} in readiness gate symbols")
        seen_symbols.add(sym)

        if status == ELIGIBLE_FOR_FUTURE_FUNDING_APPLICATION:
            eligible_symbol_entries.append(entry)
        else:
            blocked_symbol_entries.append(entry)

    # Step C: Validate eligible symbol evidence + cross-check canonicalization
    #         BEFORE any CSV read
    canon_diag = funding_to_bars_timestamp_canonicalization_diagnostics
    for entry in eligible_symbol_entries:
        sym = entry["symbol"]
        _validate_eligible_readiness_evidence(entry, sym, canon_diag)

    # Step D: Validate blocked symbols (emit skip, no rows)
    #         BEFORE any CSV read
    for entry in blocked_symbol_entries:
        sym = entry["symbol"]
        _validate_blocked_readiness_evidence(entry, sym)

    # ── Build output ────────────────────────────────────────────────────
    symbols_out: list[dict[str, Any]] = []
    eligible_count = 0
    blocked_count = 0
    materialized_count = 0
    skipped_count = 0

    # Emit blocked symbol entries first (no CSV reads needed).
    for entry in blocked_symbol_entries:
        sym = entry["symbol"]
        reasons = entry.get("blocked_reasons", [])
        symbols_out.append(
            {
                "symbol": sym,
                "readiness_status": BLOCKED_FOR_FUTURE_FUNDING_APPLICATION,
                "scaffold_status": SKIPPED_BY_READINESS_GATE,
                "blocked_reasons": list(dict.fromkeys(reasons)),
            }
        )
        blocked_count += 1
        skipped_count += 1

    # Process eligible symbols: read CSVs and materialize diagnostic rows.
    for entry in eligible_symbol_entries:
        symbol_name = entry["symbol"]

        # Check inventory presence for this symbol.
        bars_entry = bars_by_symbol.get(symbol_name)
        funding_entry = funding_by_symbol.get(symbol_name)

        if bars_entry is None:
            raise ValueError(
                f"Eligible symbol {symbol_name} is missing bars inventory"
            )
        if funding_entry is None:
            raise ValueError(
                f"Eligible symbol {symbol_name} is missing funding inventory"
            )

        # Load bars CSV and verify SHA.
        bars_filename = bars_entry["filename"]
        bars_path = bars_dir_path / bars_filename
        if not bars_path.is_file():
            raise ValueError(f"Bars CSV not found: {bars_path}")

        bars_sha256 = hashlib.sha256(
            bars_path.read_bytes()
        ).hexdigest()
        if bars_sha256 != bars_entry.get("sha256"):
            raise ValueError(
                f"Bars SHA mismatch for {symbol_name}: "
                f"expected {bars_entry['sha256']}, got {bars_sha256}"
            )

        # Load funding CSV and verify SHA.
        funding_filename = funding_entry["filename"]
        funding_path = funding_dir_path / funding_filename
        if not funding_path.is_file():
            raise ValueError(f"Funding CSV not found: {funding_path}")

        funding_sha256 = hashlib.sha256(
            funding_path.read_bytes()
        ).hexdigest()
        if funding_sha256 != funding_entry.get("sha256"):
            raise ValueError(
                f"Funding SHA mismatch for {symbol_name}: "
                f"expected {funding_entry['sha256']}, got {funding_sha256}"
            )

        # Read bar timestamps (timestamp column only).
        bars_timestamps: list[str] = []
        with open(bars_path, newline="") as f:
            reader = csv.DictReader(f)
            if reader.fieldnames is None:
                raise ValueError(f"Empty bars CSV: {bars_path}")
            col_lower = {h.lower(): h for h in reader.fieldnames}
            ts_col = col_lower.get("timestamp")
            if ts_col is None:
                raise ValueError(
                    f"Bars CSV missing timestamp column: {bars_path}"
                )
            for row in reader:
                ts_val = row.get(ts_col, "").strip()
                if ts_val:
                    bars_timestamps.append(ts_val)

        # Read funding rows (fundingTime, fundingRate columns only).
        funding_rows: list[dict[str, Any]] = []
        with open(funding_path, newline="") as f:
            reader = csv.DictReader(f)
            if reader.fieldnames is None:
                raise ValueError(f"Empty funding CSV: {funding_path}")
            col_lower = {h.lower(): h for h in reader.fieldnames}
            ts_col = col_lower.get("fundingtime")
            rate_col = col_lower.get("fundingrate")
            if ts_col is None:
                raise ValueError(
                    f"Funding CSV missing fundingTime column: {funding_path}"
                )
            if rate_col is None:
                raise ValueError(
                    f"Funding CSV missing fundingRate column: {funding_path}"
                )
            for row in reader:
                ts_val = row.get(ts_col, "").strip()
                rate_val = row.get(rate_col, "").strip()
                if ts_val:
                    funding_rows.append(
                        {
                            "timestamp": ts_val,
                            "fundingRate": rate_val,
                        }
                    )

        # Canonicalize funding timestamps (floor_to_second).
        # Build canonical -> list of original indices to detect duplicates.
        canonical_to_indices: dict[str, list[int]] = {}
        for idx, frow in enumerate(funding_rows):
            canonical = _canonicalize_floor_to_second(frow["timestamp"])
            if canonical not in canonical_to_indices:
                canonical_to_indices[canonical] = []
            canonical_to_indices[canonical].append(idx)

        # Count and fail closed on duplicate canonical funding timestamps.
        duplicate_canonical_funding_rows = sum(
            1 for indices in canonical_to_indices.values()
            if len(indices) > 1
        )
        if duplicate_canonical_funding_rows > 0:
            raise ValueError(
                f"Eligible symbol {symbol_name} has "
                f"duplicate canonical funding timestamp"
            )

        # Build canonical funding lookup.
        # canonical_ts -> {funding_rate, funding_row_index}
        funding_lookup: dict[str, dict[str, Any]] = {}
        for idx, frow in enumerate(funding_rows):
            canonical = _canonicalize_floor_to_second(frow["timestamp"])
            rate_str = frow["fundingRate"]
            rate: float | None = None
            if rate_str:
                try:
                    rate = float(rate_str)
                except (ValueError, TypeError):
                    rate = None
            funding_lookup[canonical] = {
                "funding_rate": rate,
                "funding_row_index": idx,
            }

        # Canonicalize all bar timestamps.
        bars_canonical = [
            _canonicalize_floor_to_second(ts) for ts in bars_timestamps
        ]

        # Fail closed: check for missing funding timestamps.
        missing_funding_canonicals = [
            bc for bc in bars_canonical if bc not in funding_lookup
        ]
        if missing_funding_canonicals:
            raise ValueError(
                f"Eligible symbol {symbol_name} has missing funding "
                f"timestamp after canonicalization: "
                f"{missing_funding_canonicals[0]}"
            )

        # Check for malformed funding rate (fail closed).
        for canonical, entry in funding_lookup.items():
            rate = entry["funding_rate"]
            if rate is None:
                raise ValueError(
                    f"Eligible symbol {symbol_name} has missing or "
                    f"malformed funding rate at canonical timestamp "
                    f"{canonical}"
                )

        # Join bar rows with funding by canonical timestamp.
        matched_rows: list[dict[str, Any]] = []
        for bar_idx, (bar_ts, bar_canonical) in enumerate(
            zip(bars_timestamps, bars_canonical)
        ):
            fentry = funding_lookup[bar_canonical]
            rate = fentry["funding_rate"]
            is_present = (
                rate is not None
                and not (isinstance(rate, float) and math.isnan(rate))
            )
            matched_rows.append(
                {
                    "timestamp": bar_ts,
                    "canonical_funding_timestamp": bar_canonical,
                    "bar_row_index": bar_idx,
                    "funding_row_index": fentry["funding_row_index"],
                    "funding_rate": rate,
                    "funding_rate_present": is_present,
                    "readiness_status": (
                        ELIGIBLE_FOR_FUTURE_FUNDING_APPLICATION
                    ),
                }
            )

        # Collect sample rows (5 first + 5 last, capped).
        if len(matched_rows) <= 10:
            sample_rows = list(matched_rows)
        else:
            sample_rows = matched_rows[:5] + matched_rows[-5:]

        # Compute funding-rate summary statistics.
        present_rates = [
            r["funding_rate"]
            for r in matched_rows
            if r["funding_rate_present"]
        ]
        funding_rate_present_count = len(present_rates)
        funding_rate_missing_count = (
            len(matched_rows) - funding_rate_present_count
        )
        funding_rate_min = min(present_rates) if present_rates else None
        funding_rate_max = max(present_rates) if present_rates else None
        funding_rate_zero_count = sum(
            1 for r in present_rates if r == 0.0
        )
        funding_rate_positive_count = sum(
            1 for r in present_rates if r > 0
        )
        funding_rate_negative_count = sum(
            1 for r in present_rates if r < 0
        )

        # Build per-symbol output.
        symbol_diag: dict[str, Any] = {
            "symbol": symbol_name,
            "readiness_status": ELIGIBLE_FOR_FUTURE_FUNDING_APPLICATION,
            "scaffold_status": "MATERIALIZED_DIAGNOSTIC_ROWS",
            "canonicalization_policy": FLOOR_TO_SECOND,
            "total_rows": len(bars_timestamps),
            "matched_rows": len(matched_rows),
            "missing_funding_rows": len(missing_funding_canonicals),
            "duplicate_canonical_funding_rows": (
                duplicate_canonical_funding_rows
            ),
            "funding_rate_present_rows": funding_rate_present_count,
            "funding_rate_missing_rows": funding_rate_missing_count,
            "funding_rate_min": funding_rate_min,
            "funding_rate_max": funding_rate_max,
            "funding_rate_zero_count": funding_rate_zero_count,
            "funding_rate_positive_count": funding_rate_positive_count,
            "funding_rate_negative_count": funding_rate_negative_count,
            "first_timestamp": (
                _canonicalize_floor_to_second(bars_timestamps[0])
                if bars_timestamps
                else None
            ),
            "last_timestamp": (
                _canonicalize_floor_to_second(bars_timestamps[-1])
                if bars_timestamps
                else None
            ),
            "sample_rows": sample_rows,
        }
        eligible_count += 1
        materialized_count += 1
        symbols_out.append(symbol_diag)

    return {
        "calculation_status": (
            "FUNDING_ADJUSTED_BARS_SCAFFOLD_DIAGNOSTIC_ONLY"
        ),
        "funding_application_status": (
            "DIAGNOSTIC_SCAFFOLD_ONLY_NOT_APPLIED_TO_STRATEGY"
        ),
        "readiness_gate_required": True,
        "canonicalization_policy_used": FLOOR_TO_SECOND,
        "source_sha": source_sha,
        "symbol_count": len(symbols_out),
        "eligible_symbol_count": eligible_count,
        "blocked_symbol_count": blocked_count,
        "materialized_symbol_count": materialized_count,
        "skipped_symbol_count": skipped_count,
        "symbols": symbols_out,
    }


# ── Funding adjustment policy contract diagnostics ──────────────────────


def _validate_materialized_scaffold_entry(entry: dict[str, Any], symbol: str) -> None:
    """Validate a MATERIALIZED_DIAGNOSTIC_ROWS scaffold entry before carrying
    its row-availability facts forward into the policy contract."""
    for field in (
        "total_rows",
        "matched_rows",
        "missing_funding_rows",
        "duplicate_canonical_funding_rows",
        "funding_rate_present_rows",
        "funding_rate_missing_rows",
    ):
        value = entry.get(field)
        if not isinstance(value, int) or isinstance(value, bool) or value < 0:
            raise ValueError(
                f"Materialized scaffold symbol {symbol!r} has invalid {field}: {value!r}"
            )

    if entry["missing_funding_rows"] != 0:
        raise ValueError(
            f"Materialized scaffold symbol {symbol!r} has nonzero "
            f"missing_funding_rows: {entry['missing_funding_rows']}"
        )
    if entry["duplicate_canonical_funding_rows"] != 0:
        raise ValueError(
            f"Materialized scaffold symbol {symbol!r} has nonzero "
            f"duplicate_canonical_funding_rows: "
            f"{entry['duplicate_canonical_funding_rows']}"
        )
    if entry["matched_rows"] != entry["total_rows"]:
        raise ValueError(
            f"Materialized scaffold symbol {symbol!r} has matched_rows "
            f"({entry['matched_rows']}) != total_rows ({entry['total_rows']})"
        )
    if entry["funding_rate_present_rows"] != entry["total_rows"]:
        raise ValueError(
            f"Materialized scaffold symbol {symbol!r} has "
            f"funding_rate_present_rows ({entry['funding_rate_present_rows']}) "
            f"!= total_rows ({entry['total_rows']})"
        )
    if entry["funding_rate_missing_rows"] != 0:
        raise ValueError(
            f"Materialized scaffold symbol {symbol!r} has nonzero "
            f"funding_rate_missing_rows: {entry['funding_rate_missing_rows']}"
        )

    canonicalization_policy = entry.get("canonicalization_policy")
    if canonicalization_policy != FLOOR_TO_SECOND:
        raise ValueError(
            f"Materialized scaffold symbol {symbol!r} has canonicalization_policy "
            f"{canonicalization_policy!r}, expected {FLOOR_TO_SECOND!r}"
        )

    if "sample_rows" not in entry:
        raise ValueError(
            f"Materialized scaffold symbol {symbol!r} is missing sample_rows"
        )


def _validate_skipped_scaffold_entry(entry: dict[str, Any], symbol: str) -> None:
    """Validate a SKIPPED_BY_READINESS_GATE scaffold entry before carrying its
    blocked reasons forward into the policy contract."""
    reasons = entry.get("blocked_reasons")
    if not isinstance(reasons, list) or not reasons:
        raise ValueError(
            f"Skipped scaffold symbol {symbol!r} has empty or missing "
            f"blocked_reasons"
        )
    if "sample_rows" in entry:
        raise ValueError(
            f"Skipped scaffold symbol {symbol!r} must not carry sample_rows"
        )
    if "future_application_required_inputs" in entry:
        raise ValueError(
            f"Skipped scaffold symbol {symbol!r} must not carry "
            f"future_application_required_inputs"
        )
    funding_rate_fields = sorted(
        key for key in entry if key.startswith("funding_rate_")
    )
    if funding_rate_fields:
        raise ValueError(
            f"Skipped scaffold symbol {symbol!r} must not carry funding-rate "
            f"summary fields: {funding_rate_fields}"
        )


def materialize_funding_adjustment_policy_contract_diagnostics(
    *,
    funding_adjusted_bars_scaffold_diagnostics: dict[str, Any],
) -> dict[str, Any]:
    """Materialize the diagnostic-only funding adjustment policy contract.

    Defines the exact policy a future funding-adjustment calculation must
    obey — timestamp matching, symbol eligibility, funding-rate parsing, and
    long/short funding-cashflow sign conventions — using only the
    eligibility and row-availability facts already proven by the
    funding-adjusted bars scaffold. This function performs no PnL, Sharpe,
    returns, edge, strategy, trade, position, signal, portfolio, drawdown,
    risk, or live-readiness calculation. It does not infer or apply either
    side of the long/short funding-cashflow convention it documents.
    """
    scaffold = funding_adjusted_bars_scaffold_diagnostics
    if not scaffold or not isinstance(scaffold, dict):
        raise ValueError(
            "funding_adjusted_bars_scaffold_diagnostics is required and must "
            "be a non-empty dict"
        )

    calc_status = scaffold.get("calculation_status")
    if calc_status != FUNDING_ADJUSTED_BARS_SCAFFOLD_DIAGNOSTIC_ONLY:
        raise ValueError(
            f"Expected scaffold calculation_status="
            f"{FUNDING_ADJUSTED_BARS_SCAFFOLD_DIAGNOSTIC_ONLY!r}, got {calc_status!r}"
        )

    funding_app_status = scaffold.get("funding_application_status")
    if funding_app_status != DIAGNOSTIC_SCAFFOLD_ONLY_NOT_APPLIED_TO_STRATEGY:
        raise ValueError(
            f"Expected scaffold funding_application_status="
            f"{DIAGNOSTIC_SCAFFOLD_ONLY_NOT_APPLIED_TO_STRATEGY!r}, "
            f"got {funding_app_status!r}"
        )

    canon_policy = scaffold.get("canonicalization_policy_used")
    if canon_policy != FLOOR_TO_SECOND:
        raise ValueError(
            f"Expected scaffold canonicalization_policy_used={FLOOR_TO_SECOND!r}, "
            f"got {canon_policy!r}"
        )

    symbols = scaffold.get("symbols")
    if not isinstance(symbols, list):
        raise ValueError("scaffold symbols must be a list")

    symbol_count = scaffold.get("symbol_count")
    if (
        not isinstance(symbol_count, int)
        or isinstance(symbol_count, bool)
        or symbol_count != len(symbols)
    ):
        raise ValueError(
            f"scaffold symbol_count ({symbol_count!r}) must equal "
            f"len(symbols) ({len(symbols)})"
        )

    count_fields = {}
    for field in (
        "eligible_symbol_count",
        "blocked_symbol_count",
        "materialized_symbol_count",
        "skipped_symbol_count",
    ):
        value = scaffold.get(field)
        if not isinstance(value, int) or isinstance(value, bool) or value < 0:
            raise ValueError(
                f"scaffold {field} must be a non-negative integer, got {value!r}"
            )
        count_fields[field] = value

    if (
        count_fields["eligible_symbol_count"] + count_fields["blocked_symbol_count"]
        != symbol_count
    ):
        raise ValueError(
            f"scaffold eligible_symbol_count "
            f"({count_fields['eligible_symbol_count']}) + blocked_symbol_count "
            f"({count_fields['blocked_symbol_count']}) != symbol_count "
            f"({symbol_count})"
        )
    if count_fields["materialized_symbol_count"] != count_fields["eligible_symbol_count"]:
        raise ValueError(
            f"scaffold materialized_symbol_count "
            f"({count_fields['materialized_symbol_count']}) != "
            f"eligible_symbol_count ({count_fields['eligible_symbol_count']})"
        )
    if count_fields["skipped_symbol_count"] != count_fields["blocked_symbol_count"]:
        raise ValueError(
            f"scaffold skipped_symbol_count "
            f"({count_fields['skipped_symbol_count']}) != blocked_symbol_count "
            f"({count_fields['blocked_symbol_count']})"
        )

    seen_symbols: set[str] = set()
    policy_symbols: list[dict[str, Any]] = []
    counted_eligible = 0
    counted_blocked = 0

    for index, entry in enumerate(symbols):
        if not isinstance(entry, dict):
            raise ValueError(f"scaffold symbol entry at index {index} must be a dict")

        symbol = entry.get("symbol")
        if not isinstance(symbol, str) or not symbol:
            raise ValueError(
                f"scaffold symbol entry at index {index} has invalid symbol "
                f"{symbol!r}"
            )
        if symbol in seen_symbols:
            raise ValueError(f"Duplicate scaffold symbol: {symbol}")
        seen_symbols.add(symbol)

        scaffold_status = entry.get("scaffold_status")

        if scaffold_status == MATERIALIZED_DIAGNOSTIC_ROWS:
            _validate_materialized_scaffold_entry(entry, symbol)
            policy_symbols.append(
                {
                    "symbol": symbol,
                    "scaffold_status": MATERIALIZED_DIAGNOSTIC_ROWS,
                    "policy_status": ELIGIBLE_FOR_FUTURE_FUNDING_ADJUSTMENT_POLICY,
                    "canonicalization_policy": FLOOR_TO_SECOND,
                    "funding_rate_column": "fundingRate",
                    "funding_rate_unit": "decimal_rate_not_percent",
                    "timestamp_match_policy": (
                        EXACT_CANONICAL_FUNDING_TIMESTAMP_TO_BAR_TIMESTAMP
                    ),
                    "row_availability_status": "COMPLETE",
                    "total_rows": entry["total_rows"],
                    "matched_rows": entry["matched_rows"],
                    "funding_rate_present_rows": entry["funding_rate_present_rows"],
                    "missing_funding_rows": entry["missing_funding_rows"],
                    "duplicate_canonical_funding_rows": (
                        entry["duplicate_canonical_funding_rows"]
                    ),
                    "future_application_required_inputs": {
                        "explicit_position_side": (
                            "FUTURE_STRATEGY_POSITION_SIDE_REQUIRED"
                        ),
                        "notional_or_size_source": (
                            "FUTURE_STRATEGY_NOTIONAL_SOURCE_REQUIRED"
                        ),
                        "strategy_rule_source": (
                            "FUTURE_STRATEGY_RULE_SOURCE_REQUIRED"
                        ),
                    },
                }
            )
            counted_eligible += 1
        elif scaffold_status == SKIPPED_BY_READINESS_GATE:
            _validate_skipped_scaffold_entry(entry, symbol)
            policy_symbols.append(
                {
                    "symbol": symbol,
                    "scaffold_status": SKIPPED_BY_READINESS_GATE,
                    "policy_status": BLOCKED_BY_READINESS_GATE,
                    "blocked_reasons": list(entry["blocked_reasons"]),
                }
            )
            counted_blocked += 1
        else:
            raise ValueError(
                f"Unrecognized scaffold_status {scaffold_status!r} for symbol "
                f"{symbol!r}"
            )

    if counted_eligible != count_fields["eligible_symbol_count"]:
        raise ValueError(
            f"Counted eligible symbols ({counted_eligible}) != scaffold "
            f"eligible_symbol_count ({count_fields['eligible_symbol_count']})"
        )
    if counted_blocked != count_fields["blocked_symbol_count"]:
        raise ValueError(
            f"Counted blocked symbols ({counted_blocked}) != scaffold "
            f"blocked_symbol_count ({count_fields['blocked_symbol_count']})"
        )

    return {
        "calculation_status": FUNDING_ADJUSTMENT_POLICY_CONTRACT_DIAGNOSTIC_ONLY,
        "funding_adjustment_application_status": NOT_EXECUTED,
        "strategy_application_status": NOT_EXECUTED,
        "pnl_application_status": NOT_EXECUTED,
        "requires_scaffold_diagnostics": True,
        "scaffold_section_required": "funding_adjusted_bars_scaffold_diagnostics",
        "canonicalization_policy_required": FLOOR_TO_SECOND,
        "funding_rate_column": "fundingRate",
        "funding_rate_unit": "decimal_rate_not_percent",
        "funding_rate_annualization_status": "NOT_ANNUALIZED",
        "timestamp_match_policy": EXACT_CANONICAL_FUNDING_TIMESTAMP_TO_BAR_TIMESTAMP,
        "timestamp_policy_contract": {
            "source": "SCAFFOLD_OUTPUT_ONLY",
            "funding_timestamp_canonicalization_required": FLOOR_TO_SECOND,
            "future_match_rule": (
                EXACT_CANONICAL_FUNDING_TIMESTAMP_TO_BAR_TIMESTAMP
            ),
            "nearest_neighbor_matching_allowed": False,
            "forward_fill_allowed": False,
            "backfill_allowed": False,
            "interpolation_allowed": False,
            "timezone_inference_allowed": False,
            "exchange_clock_inference_allowed": False,
        },
        "eligibility_policy_contract": {
            "eligible_scaffold_status_required": MATERIALIZED_DIAGNOSTIC_ROWS,
            "skipped_scaffold_status_carried_forward": SKIPPED_BY_READINESS_GATE,
            "blocked_reasons_carried_forward": True,
            "hardcoded_symbol_list_used": False,
        },
        "funding_rate_policy_contract": {
            "funding_rate_column": "fundingRate",
            "funding_rate_unit": "decimal_rate_not_percent",
            "annualization_allowed": False,
            "compounding_allowed": False,
            "missing_rate_inference_allowed": False,
            "fail_closed_on_missing_or_invalid": True,
        },
        "position_side_policy_contract": {
            "long_side_contract": (
                "LONG_PAYS_POSITIVE_FUNDING_RECEIVES_NEGATIVE_FUNDING"
            ),
            "short_side_contract": (
                "SHORT_RECEIVES_POSITIVE_FUNDING_PAYS_NEGATIVE_FUNDING"
            ),
            "position_side_source_required": (
                "FUTURE_STRATEGY_POSITION_SIDE_REQUIRED"
            ),
            "position_side_inference_status": NOT_EXECUTED,
            "position_side_application_status": NOT_EXECUTED,
        },
        "output_policy_contract": {
            "may_summarize_eligible_and_skipped_symbols": True,
            "may_include_policy_strings_and_validation_flags": True,
            "emits_full_row_dataset": False,
            "emits_ohlcv_values": False,
            "emits_row_level_adjusted_values": False,
            "emits_strategy_values": False,
            "emits_performance_values": False,
        },
        "eligible_symbol_count": counted_eligible,
        "blocked_symbol_count": counted_blocked,
        "policy_symbol_count": len(policy_symbols),
        "symbols": policy_symbols,
    }


_VALID_FUNDING_ARITHMETIC_FIXTURE_SIDES = frozenset({"LONG", "SHORT"})


def _to_finite_decimal(value: Any, field_name: str, case_id: Any) -> Decimal:
    """Convert *value* to a finite ``Decimal`` via ``Decimal(str(value))``.

    Accepts ``int``, ``float``, or ``str``. Raises ``ValueError`` for any
    other type, and for any value that converts to a non-finite (NaN or
    Infinity) or malformed ``Decimal``.
    """
    if not isinstance(value, (int, float, str)):
        raise ValueError(
            f"fixture case {case_id!r} {field_name} must be int, float, or "
            f"str, got {type(value).__name__}"
        )
    try:
        decimal_value = Decimal(str(value))
    except InvalidOperation as exc:
        raise ValueError(
            f"fixture case {case_id!r} {field_name} is malformed: {value!r}"
        ) from exc
    if not decimal_value.is_finite():
        raise ValueError(
            f"fixture case {case_id!r} {field_name} must be finite "
            f"(no NaN/Infinity), got {value!r}"
        )
    return decimal_value


def _materialize_fixture_case(case: dict[str, Any]) -> dict[str, Any]:
    """Validate one funding-cashflow fixture case and compute its diagnostic
    cashflow-per-notional-unit value.

    Consumes only explicit fixture inputs (``case_id``, ``side``,
    ``funding_rate``, ``notional_per_unit``). Performs no strategy, PnL,
    returns, or bar-row calculation. Fails closed on any missing,
    unsupported, non-finite, or non-positive input, and on any mismatch
    between the computed cashflow and an explicit
    ``expected_cashflow_per_notional_unit`` fixture field, if present.
    """
    if not isinstance(case, dict):
        raise ValueError("fixture case must be a dict")

    case_id = case.get("case_id")
    if not isinstance(case_id, str) or not case_id:
        raise ValueError(f"fixture case_id is required, got {case_id!r}")

    side = case.get("side")
    if side is None:
        raise ValueError(f"fixture case {case_id!r} is missing side")
    if side not in _VALID_FUNDING_ARITHMETIC_FIXTURE_SIDES:
        raise ValueError(
            f"fixture case {case_id!r} has unsupported side {side!r}; must "
            f"be one of {sorted(_VALID_FUNDING_ARITHMETIC_FIXTURE_SIDES)}"
        )

    if "funding_rate" not in case or case["funding_rate"] is None:
        raise ValueError(f"fixture case {case_id!r} is missing funding_rate")
    funding_rate = _to_finite_decimal(case["funding_rate"], "funding_rate", case_id)

    if "notional_per_unit" not in case or case["notional_per_unit"] is None:
        raise ValueError(
            f"fixture case {case_id!r} is missing notional_per_unit"
        )
    notional_per_unit = _to_finite_decimal(
        case["notional_per_unit"], "notional_per_unit", case_id
    )
    if notional_per_unit <= 0:
        raise ValueError(
            f"fixture case {case_id!r} notional_per_unit must be positive, "
            f"got {notional_per_unit}"
        )

    if side == "LONG":
        cashflow = -funding_rate * notional_per_unit
    else:
        cashflow = funding_rate * notional_per_unit

    expected_raw = case.get("expected_cashflow_per_notional_unit")
    if expected_raw is not None:
        expected_decimal = _to_finite_decimal(
            expected_raw, "expected_cashflow_per_notional_unit", case_id
        )
        if cashflow != expected_decimal:
            raise ValueError(
                f"fixture case {case_id!r} computed cashflow_per_notional_unit "
                f"{cashflow} does not equal expected {expected_decimal}"
            )
    else:
        expected_decimal = cashflow

    return {
        "case_id": case_id,
        "side": side,
        "funding_rate": case["funding_rate"],
        "notional_per_unit": case["notional_per_unit"],
        "cashflow_per_notional_unit": str(cashflow),
        "expected_cashflow_per_notional_unit": str(expected_decimal),
        "fixture_status": "PASS",
        "formula": LONG_NEGATES_FUNDING_RATE_SHORT_PRESERVES_FUNDING_RATE_TIMES_NOTIONAL,
        "application_scope": "EXPLICIT_FIXTURE_ONLY_NOT_STRATEGY",
    }


def materialize_funding_adjustment_arithmetic_scaffold_diagnostics(
    *,
    funding_adjustment_policy_contract_diagnostics: dict[str, Any],
) -> dict[str, Any]:
    """Materialize the diagnostic-only funding adjustment arithmetic scaffold.

    Proves the long/short funding cashflow sign convention documented by
    ``funding_adjustment_policy_contract_diagnostics`` on tiny, deterministic,
    in-code fixture rows only. This function performs no strategy, bars,
    returns, PnL, Sharpe, edge, trade, position, signal, portfolio,
    drawdown, risk, or live-readiness calculation, and consumes no real row
    samples, symbols, timestamps, or OHLCV data.
    """
    contract = funding_adjustment_policy_contract_diagnostics
    if not contract or not isinstance(contract, dict):
        raise ValueError(
            "funding_adjustment_policy_contract_diagnostics is required and "
            "must be a non-empty dict"
        )

    def _require(d: dict[str, Any], key: str, expected: Any, prefix: str = "") -> None:
        actual = d.get(key)
        if actual != expected:
            raise ValueError(
                f"Expected funding_adjustment_policy_contract_diagnostics."
                f"{prefix}{key}={expected!r}, got {actual!r}"
            )

    _require(contract, "calculation_status", FUNDING_ADJUSTMENT_POLICY_CONTRACT_DIAGNOSTIC_ONLY)
    _require(contract, "funding_adjustment_application_status", NOT_EXECUTED)
    _require(contract, "strategy_application_status", NOT_EXECUTED)
    _require(contract, "pnl_application_status", NOT_EXECUTED)
    _require(contract, "funding_rate_unit", "decimal_rate_not_percent")
    _require(contract, "funding_rate_annualization_status", "NOT_ANNUALIZED")
    _require(
        contract,
        "timestamp_match_policy",
        EXACT_CANONICAL_FUNDING_TIMESTAMP_TO_BAR_TIMESTAMP,
    )

    side_contract = contract.get("position_side_policy_contract")
    if not isinstance(side_contract, dict):
        raise ValueError(
            "funding_adjustment_policy_contract_diagnostics."
            "position_side_policy_contract must be a dict"
        )
    _require(
        side_contract,
        "long_side_contract",
        "LONG_PAYS_POSITIVE_FUNDING_RECEIVES_NEGATIVE_FUNDING",
        prefix="position_side_policy_contract.",
    )
    _require(
        side_contract,
        "short_side_contract",
        "SHORT_RECEIVES_POSITIVE_FUNDING_PAYS_NEGATIVE_FUNDING",
        prefix="position_side_policy_contract.",
    )
    _require(
        side_contract,
        "position_side_inference_status",
        NOT_EXECUTED,
        prefix="position_side_policy_contract.",
    )
    _require(
        side_contract,
        "position_side_application_status",
        NOT_EXECUTED,
        prefix="position_side_policy_contract.",
    )

    output_contract = contract.get("output_policy_contract")
    if not isinstance(output_contract, dict):
        raise ValueError(
            "funding_adjustment_policy_contract_diagnostics."
            "output_policy_contract must be a dict"
        )
    _require(
        output_contract,
        "emits_row_level_adjusted_values",
        False,
        prefix="output_policy_contract.",
    )
    _require(
        output_contract,
        "emits_strategy_values",
        False,
        prefix="output_policy_contract.",
    )
    _require(
        output_contract,
        "emits_performance_values",
        False,
        prefix="output_policy_contract.",
    )

    fixture_cases = [
        _materialize_fixture_case(dict(raw_case))
        for raw_case in _FUNDING_ARITHMETIC_FIXTURE_CASES
    ]

    passed_count = sum(
        1 for case in fixture_cases if case["fixture_status"] == "PASS"
    )
    failed_count = len(fixture_cases) - passed_count
    if failed_count:
        raise ValueError(
            f"{failed_count} funding adjustment arithmetic fixture case(s) "
            f"did not pass"
        )

    result = {
        "calculation_status": FUNDING_ADJUSTMENT_ARITHMETIC_SCAFFOLD_DIAGNOSTIC_ONLY,
        "funding_adjustment_application_status": FIXTURE_ONLY_NOT_APPLIED_TO_STRATEGY,
        "strategy_application_status": NOT_EXECUTED,
        "pnl_application_status": NOT_EXECUTED,
        "requires_policy_contract_diagnostics": True,
        "policy_contract_section_required": (
            "funding_adjustment_policy_contract_diagnostics"
        ),
        "funding_rate_unit": "decimal_rate_not_percent",
        "annualization_status": "NOT_ANNUALIZED",
        "compounding_status": "NOT_COMPOUNDED",
        "side_source": EXPLICIT_FIXTURE_ONLY,
        "notional_source": EXPLICIT_FIXTURE_ONLY,
        "strategy_rule_source": NOT_EXECUTED,
        "fixture_case_count": len(fixture_cases),
        "passed_fixture_case_count": passed_count,
        "failed_fixture_case_count": failed_count,
        "fixture_cases": fixture_cases,
    }
    _assert_no_forbidden_calculation_keys(
        result, "$.funding_adjustment_arithmetic_scaffold_diagnostics"
    )
    return result


def _validate_funding_rate(value: Any) -> Decimal:
    """Validate and return a finite Decimal funding rate.

    Rejects None, bool, NaN, Inf, and malformed values.
    Accepts int, float, str, and Decimal, converts via Decimal(str(value)),
    and requires the result to be finite.
    """
    if value is None:
        raise ValueError("funding_rate is None")
    if isinstance(value, bool):
        raise ValueError(
            f"funding_rate must not be bool: {value}"
        )
    if not isinstance(value, (int, float, str, Decimal)):
        raise ValueError(
            f"funding_rate must be int, float, str, or Decimal, got {type(value).__name__}"
        )
    # Float-specific NaN/Inf checks preserve existing error messages
    if isinstance(value, float):
        if math.isnan(value):
            raise ValueError("Funding rate is NaN")
        if math.isinf(value):
            raise ValueError("Funding rate is infinite")
    try:
        decimal_value = Decimal(str(value))
    except (ValueError, ArithmeticError) as exc:
        raise ValueError(
            f"funding_rate is malformed: {value!r}"
        ) from exc
    if not decimal_value.is_finite():
        raise ValueError(
            f"funding_rate must be finite: {value!r}"
        )
    return decimal_value


def materialize_funding_adjustment_row_scaffold_diagnostics(
    funding_adjustment_policy_contract_diagnostics,
    funding_adjustment_arithmetic_scaffold_diagnostics,
    funding_adjusted_bars_scaffold_diagnostics,
) -> dict:
    """Materialize the diagnostic-only funding adjustment row scaffold.

    Validates the upstream policy contract, arithmetic scaffold, and bars
    scaffold sections, then builds per-symbol cashflow samples from the
    bars scaffold sample rows using unit notional and both hypothetical
    sides. This function performs no strategy, PnL, Sharpe, edge, trade,
    position, signal, portfolio, drawdown, risk, or live-readiness
    calculation, and emits no timestamps, OHLCV, returns, or real
    strategy-side/notional data.
    """
    # ── Step 1: Validate policy contract section exists and is dict ──────
    if not isinstance(funding_adjustment_policy_contract_diagnostics, dict):
        raise ValueError(
            "funding_adjustment_policy_contract_diagnostics must be a dict"
        )

    # ── Step 2: Validate policy contract status fields ───────────────────
    policy = funding_adjustment_policy_contract_diagnostics
    if policy.get("calculation_status") != FUNDING_ADJUSTMENT_POLICY_CONTRACT_DIAGNOSTIC_ONLY:
        raise ValueError(
            f"Expected policy contract calculation_status="
            f"{FUNDING_ADJUSTMENT_POLICY_CONTRACT_DIAGNOSTIC_ONLY!r}, "
            f"got {policy.get('calculation_status')!r}"
        )
    if policy.get("funding_adjustment_application_status") != NOT_EXECUTED:
        raise ValueError(
            f"Expected policy contract funding_adjustment_application_status="
            f"{NOT_EXECUTED!r}, "
            f"got {policy.get('funding_adjustment_application_status')!r}"
        )
    if policy.get("strategy_application_status") != NOT_EXECUTED:
        raise ValueError(
            f"Expected policy contract strategy_application_status="
            f"{NOT_EXECUTED!r}, "
            f"got {policy.get('strategy_application_status')!r}"
        )
    if policy.get("pnl_application_status") != NOT_EXECUTED:
        raise ValueError(
            f"Expected policy contract pnl_application_status="
            f"{NOT_EXECUTED!r}, "
            f"got {policy.get('pnl_application_status')!r}"
        )
    if policy.get("funding_rate_unit") != "decimal_rate_not_percent":
        raise ValueError(
            f"Expected policy contract funding_rate_unit='decimal_rate_not_percent', "
            f"got {policy.get('funding_rate_unit')!r}"
        )
    if policy.get("funding_rate_annualization_status") != "NOT_ANNUALIZED":
        raise ValueError(
            f"Expected policy contract funding_rate_annualization_status="
            f"'NOT_ANNUALIZED', "
            f"got {policy.get('funding_rate_annualization_status')!r}"
        )
    if policy.get("timestamp_match_policy") != EXACT_CANONICAL_FUNDING_TIMESTAMP_TO_BAR_TIMESTAMP:
        raise ValueError(
            f"Expected policy contract timestamp_match_policy="
            f"{EXACT_CANONICAL_FUNDING_TIMESTAMP_TO_BAR_TIMESTAMP!r}, "
            f"got {policy.get('timestamp_match_policy')!r}"
        )

    # ── Step 3: Validate arithmetic scaffold section exists and is dict ──
    if not isinstance(funding_adjustment_arithmetic_scaffold_diagnostics, dict):
        raise ValueError(
            "funding_adjustment_arithmetic_scaffold_diagnostics must be a dict"
        )

    # ── Step 4: Validate arithmetic scaffold status fields ───────────────
    arith = funding_adjustment_arithmetic_scaffold_diagnostics
    if arith.get("calculation_status") != FUNDING_ADJUSTMENT_ARITHMETIC_SCAFFOLD_DIAGNOSTIC_ONLY:
        raise ValueError(
            f"Expected arithmetic scaffold calculation_status="
            f"{FUNDING_ADJUSTMENT_ARITHMETIC_SCAFFOLD_DIAGNOSTIC_ONLY!r}, "
            f"got {arith.get('calculation_status')!r}"
        )
    if arith.get("funding_adjustment_application_status") != FIXTURE_ONLY_NOT_APPLIED_TO_STRATEGY:
        raise ValueError(
            f"Expected arithmetic scaffold "
            f"funding_adjustment_application_status="
            f"{FIXTURE_ONLY_NOT_APPLIED_TO_STRATEGY!r}, "
            f"got {arith.get('funding_adjustment_application_status')!r}"
        )
    if arith.get("strategy_application_status") != NOT_EXECUTED:
        raise ValueError(
            f"Expected arithmetic scaffold strategy_application_status="
            f"{NOT_EXECUTED!r}, "
            f"got {arith.get('strategy_application_status')!r}"
        )
    if arith.get("pnl_application_status") != NOT_EXECUTED:
        raise ValueError(
            f"Expected arithmetic scaffold pnl_application_status="
            f"{NOT_EXECUTED!r}, "
            f"got {arith.get('pnl_application_status')!r}"
        )
    if arith.get("funding_rate_unit") != "decimal_rate_not_percent":
        raise ValueError(
            f"Expected arithmetic scaffold funding_rate_unit="
            f"'decimal_rate_not_percent', "
            f"got {arith.get('funding_rate_unit')!r}"
        )
    if arith.get("annualization_status") != "NOT_ANNUALIZED":
        raise ValueError(
            f"Expected arithmetic scaffold annualization_status="
            f"'NOT_ANNUALIZED', "
            f"got {arith.get('annualization_status')!r}"
        )
    if arith.get("compounding_status") != "NOT_COMPOUNDED":
        raise ValueError(
            f"Expected arithmetic scaffold compounding_status="
            f"'NOT_COMPOUNDED', "
            f"got {arith.get('compounding_status')!r}"
        )
    if arith.get("side_source") != EXPLICIT_FIXTURE_ONLY:
        raise ValueError(
            f"Expected arithmetic scaffold side_source="
            f"{EXPLICIT_FIXTURE_ONLY!r}, "
            f"got {arith.get('side_source')!r}"
        )
    if arith.get("notional_source") != EXPLICIT_FIXTURE_ONLY:
        raise ValueError(
            f"Expected arithmetic scaffold notional_source="
            f"{EXPLICIT_FIXTURE_ONLY!r}, "
            f"got {arith.get('notional_source')!r}"
        )
    if arith.get("fixture_case_count") != 6:
        raise ValueError(
            f"Expected arithmetic scaffold fixture_case_count=6, "
            f"got {arith.get('fixture_case_count')!r}"
        )
    if arith.get("passed_fixture_case_count") != 6:
        raise ValueError(
            f"Expected arithmetic scaffold passed_fixture_case_count=6, "
            f"got {arith.get('passed_fixture_case_count')!r}"
        )
    if arith.get("failed_fixture_case_count") != 0:
        raise ValueError(
            f"Expected arithmetic scaffold failed_fixture_case_count=0, "
            f"got {arith.get('failed_fixture_case_count')!r}"
        )

    # ── Step 5: Validate bars scaffold section exists and is dict ────────
    if not isinstance(funding_adjusted_bars_scaffold_diagnostics, dict):
        raise ValueError(
            "funding_adjusted_bars_scaffold_diagnostics must be a dict"
        )

    # ── Step 6: Validate bars scaffold status fields ─────────────────────
    bars = funding_adjusted_bars_scaffold_diagnostics
    if bars.get("calculation_status") != FUNDING_ADJUSTED_BARS_SCAFFOLD_DIAGNOSTIC_ONLY:
        raise ValueError(
            f"Expected bars scaffold calculation_status="
            f"{FUNDING_ADJUSTED_BARS_SCAFFOLD_DIAGNOSTIC_ONLY!r}, "
            f"got {bars.get('calculation_status')!r}"
        )
    if bars.get("funding_application_status") != DIAGNOSTIC_SCAFFOLD_ONLY_NOT_APPLIED_TO_STRATEGY:
        raise ValueError(
            f"Expected bars scaffold funding_application_status="
            f"{DIAGNOSTIC_SCAFFOLD_ONLY_NOT_APPLIED_TO_STRATEGY!r}, "
            f"got {bars.get('funding_application_status')!r}"
        )
    if bars.get("canonicalization_policy_used") != FLOOR_TO_SECOND:
        raise ValueError(
            f"Expected bars scaffold canonicalization_policy_used="
            f"{FLOOR_TO_SECOND!r}, "
            f"got {bars.get('canonicalization_policy_used')!r}"
        )

    # ── Step 7: Validate scaffold counts are internally consistent ───────
    symbols = bars.get("symbols", [])
    if not isinstance(symbols, list):
        raise ValueError("bars scaffold symbols must be a list")

    seen_symbols: set[str] = set()
    eligible_symbol_entries: list[dict] = []
    blocked_symbol_entries: list[dict] = []

    for entry in symbols:
        if not isinstance(entry, dict):
            raise ValueError("bars scaffold symbol entry must be a dict")
        symbol = entry.get("symbol")
        if not isinstance(symbol, str) or not symbol:
            raise ValueError(f"bars scaffold symbol entry has invalid symbol {symbol!r}")
        if symbol in seen_symbols:
            raise ValueError(f"Duplicate scaffold symbol: {symbol}")
        seen_symbols.add(symbol)

        scaffold_status = entry.get("scaffold_status")
        if scaffold_status == MATERIALIZED_DIAGNOSTIC_ROWS:
            total_rows = entry.get("total_rows")
            if not isinstance(total_rows, int) or isinstance(total_rows, bool) or total_rows < 0:
                raise ValueError(
                    f"Eligible symbol {symbol!r} has invalid total_rows: {total_rows!r}"
                )
            matched_rows = entry.get("matched_rows")
            if matched_rows != total_rows:
                raise ValueError(
                    f"Eligible symbol {symbol!r} matched_rows ({matched_rows}) "
                    f"!= total_rows ({total_rows})"
                )
            funding_rate_present_rows = entry.get("funding_rate_present_rows")
            if funding_rate_present_rows != total_rows:
                raise ValueError(
                    f"Eligible symbol {symbol!r} funding_rate_present_rows "
                    f"({funding_rate_present_rows}) != total_rows ({total_rows})"
                )
            missing_funding_rows = entry.get("missing_funding_rows")
            if missing_funding_rows != 0:
                raise ValueError(
                    f"Eligible symbol {symbol!r} missing_funding_rows "
                    f"({missing_funding_rows}) != 0"
                )
            duplicate_canonical_funding_rows = entry.get("duplicate_canonical_funding_rows")
            if duplicate_canonical_funding_rows != 0:
                raise ValueError(
                    f"Eligible symbol {symbol!r} "
                    f"duplicate_canonical_funding_rows "
                    f"({duplicate_canonical_funding_rows}) != 0"
                )
            funding_rate_missing_rows = entry.get("funding_rate_missing_rows")
            if funding_rate_missing_rows != 0:
                raise ValueError(
                    f"Eligible symbol {symbol!r} funding_rate_missing_rows "
                    f"({funding_rate_missing_rows}) != 0"
                )
            sample_rows = entry.get("sample_rows")
            if not isinstance(sample_rows, list):
                raise ValueError(
                    f"Eligible symbol {symbol!r} sample_rows must be a list, "
                    f"got {type(sample_rows).__name__}"
                )
            eligible_symbol_entries.append(entry)
        elif scaffold_status == SKIPPED_BY_READINESS_GATE:
            blocked_symbol_entries.append(entry)
        else:
            raise ValueError(
                f"Symbol {symbol!r} has unexpected scaffold_status "
                f"{scaffold_status!r}"
            )

    # ── Step 8: Build the output section ─────────────────────────────────
    eligible_count = len(eligible_symbol_entries)
    blocked_count = len(blocked_symbol_entries)

    # ── Step 9: Build per-symbol entries ─────────────────────────────────
    output_symbols: list[dict] = []

    for entry in eligible_symbol_entries:
        symbol = entry["symbol"]
        sample_rows = entry["sample_rows"]
        sample_row_count = len(sample_rows)

        if sample_row_count > 10:
            raise ValueError(
                f"Eligible symbol {symbol!r} sample row count "
                f"{sample_row_count} exceeds maximum of 10"
            )

        cashflow_samples = []
        for row in sample_rows:
            if "bar_row_index" not in row:
                raise ValueError(
                    f"Eligible symbol {symbol!r} sample row missing bar_row_index"
                )
            if "funding_row_index" not in row:
                raise ValueError(
                    f"Eligible symbol {symbol!r} sample row missing funding_row_index"
                )
            if "funding_rate" not in row:
                raise ValueError(
                    f"Eligible symbol {symbol!r} sample row missing funding_rate"
                )

            funding_rate = row["funding_rate"]
            funding_rate_dec = _validate_funding_rate(funding_rate)

            dr = funding_rate_dec
            unit_notional = Decimal("1")

            long_cashflow_factor = -dr * unit_notional
            short_cashflow_factor = dr * unit_notional

            cashflow_samples.append({
                "bar_row_index": row["bar_row_index"],
                "funding_row_index": row["funding_row_index"],
                "funding_rate": str(funding_rate_dec),
                "unit_notional": "1",
                "long_cashflow_factor": str(long_cashflow_factor),
                "short_cashflow_factor": str(short_cashflow_factor),
                "formula": LONG_NEGATES_FUNDING_RATE_SHORT_PRESERVES_FUNDING_RATE_TIMES_NOTIONAL,
                "application_scope": "DIAGNOSTIC_SAMPLE_ONLY_NOT_STRATEGY",
            })

        output_symbols.append({
            "symbol": symbol,
            "scaffold_status": MATERIALIZED_DIAGNOSTIC_ROWS,
            "row_scaffold_status": "MATERIALIZED_DIAGNOSTIC_CASHFLOW_SAMPLES",
            "notional_policy": "UNIT_NOTIONAL_DIAGNOSTIC_ONLY",
            "side_policy": "BOTH_HYPOTHETICAL_SIDES_DIAGNOSTIC_ONLY",
            "funding_rate_unit": "decimal_rate_not_percent",
            "total_rows": entry["total_rows"],
            "sample_row_count": sample_row_count,
            "sample_rows": cashflow_samples,
        })

    for entry in blocked_symbol_entries:
        symbol = entry["symbol"]
        blocked_reasons = entry.get("blocked_reasons", [])

        # Blocked/skipped symbols must NOT carry sample/cashflow-like data
        BLOCKED_SYMBOL_FORBIDDEN_KEYS = {
            "sample_rows",
            "cashflow_samples",
            "long_cashflow_factor",
            "short_cashflow_factor",
            "funding_rate",
            "bar_row_index",
            "funding_row_index",
            "unit_notional",
        }
        for forbidden_key in BLOCKED_SYMBOL_FORBIDDEN_KEYS:
            if forbidden_key in entry:
                raise ValueError(
                    f"Blocked symbol {symbol!r} must not contain "
                    f"'{forbidden_key}'"
                )

        blocked_output = {
            "symbol": symbol,
            "scaffold_status": SKIPPED_BY_READINESS_GATE,
            "row_scaffold_status": SKIPPED_BY_READINESS_GATE,
            "blocked_reasons": blocked_reasons,
        }
        # Ensure blocked output is limited to symbol, statuses, blocked_reasons
        allowed_output_keys = {"symbol", "scaffold_status", "row_scaffold_status", "blocked_reasons"}
        extra_keys = set(blocked_output.keys()) - allowed_output_keys
        if extra_keys:
            raise ValueError(
                f"Blocked symbol {symbol!r} output has extra keys: {extra_keys}"
            )
        output_symbols.append(blocked_output)

    # ── Step 10: Reconcile top-level counts against derived values ──────
    symbol_count = bars.get("symbol_count")
    eligible_symbol_count = bars.get("eligible_symbol_count")
    blocked_symbol_count = bars.get("blocked_symbol_count")
    materialized_symbol_count = bars.get("materialized_symbol_count")
    skipped_symbol_count = bars.get("skipped_symbol_count")

    recon_symbol_count = len(output_symbols)
    recon_eligible = sum(
        1 for s in output_symbols
        if s.get("scaffold_status") == "MATERIALIZED_DIAGNOSTIC_ROWS"
    )
    recon_blocked = sum(
        1 for s in output_symbols
        if s.get("scaffold_status") == "SKIPPED_BY_READINESS_GATE"
    )
    recon_materialized = recon_eligible
    recon_skipped = recon_blocked

    if symbol_count != recon_symbol_count:
        raise ValueError(
            f"symbol_count {symbol_count} != len(symbols) {recon_symbol_count}"
        )
    if eligible_symbol_count != recon_eligible:
        raise ValueError(
            f"eligible_symbol_count {eligible_symbol_count} != derived {recon_eligible}"
        )
    if blocked_symbol_count != recon_blocked:
        raise ValueError(
            f"blocked_symbol_count {blocked_symbol_count} != derived {recon_blocked}"
        )
    if materialized_symbol_count != recon_materialized:
        raise ValueError(
            f"materialized_symbol_count {materialized_symbol_count} != derived {recon_materialized}"
        )
    if skipped_symbol_count != recon_skipped:
        raise ValueError(
            f"skipped_symbol_count {skipped_symbol_count} != derived {recon_skipped}"
        )

    section = {
        "calculation_status": FUNDING_ADJUSTMENT_ROW_SCAFFOLD_DIAGNOSTIC_ONLY,
        "funding_adjustment_application_status": (
            DIAGNOSTIC_ROW_SCAFFOLD_ONLY_NOT_APPLIED_TO_STRATEGY
        ),
        "strategy_application_status": NOT_EXECUTED,
        "pnl_application_status": NOT_EXECUTED,
        "requires_policy_contract_diagnostics": True,
        "requires_arithmetic_scaffold_diagnostics": True,
        "requires_funding_adjusted_bars_scaffold_diagnostics": True,
        "policy_contract_section_required": (
            "funding_adjustment_policy_contract_diagnostics"
        ),
        "arithmetic_scaffold_section_required": (
            "funding_adjustment_arithmetic_scaffold_diagnostics"
        ),
        "funding_adjusted_bars_scaffold_section_required": (
            "funding_adjusted_bars_scaffold_diagnostics"
        ),
        "funding_rate_unit": "decimal_rate_not_percent",
        "notional_policy": "UNIT_NOTIONAL_DIAGNOSTIC_ONLY",
        "side_policy": "BOTH_HYPOTHETICAL_SIDES_DIAGNOSTIC_ONLY",
        "sample_policy": "CAPPED_DETERMINISTIC_SAMPLES_ONLY",
        "sample_size_per_symbol": 10,
        "eligible_symbol_count": recon_eligible,
        "blocked_symbol_count": recon_blocked,
        "materialized_symbol_count": recon_materialized,
        "skipped_symbol_count": recon_skipped,
        "symbols": output_symbols,
    }

    _assert_no_forbidden_calculation_keys(
        section, "$.funding_adjustment_row_scaffold_diagnostics"
    )
    return section


def _build_funding_adjustment_sample_aggregate_diagnostics(
    row_scaffold_section: dict,
) -> dict:
    """Build diagnostic-only sample aggregate summary over capped scaffold rows.

    Consumes ``funding_adjustment_row_scaffold_diagnostics`` only. Validates
    all row scaffold statuses and per-symbol data (fail closed), then computes
    aggregate statistics over the capped deterministic sample rows. Emits no
    strategy, PnL, Sharpe, edge, trade, position, signal, portfolio, drawdown,
    risk, or live-readiness data.
    """
    # ── Step 1: Validate row scaffold section exists and is dict ──────
    if not isinstance(row_scaffold_section, dict):
        raise ValueError(
            "funding_adjustment_row_scaffold_diagnostics is required and "
            "must be a non-empty dict"
        )

    # ── Step 2: Validate row scaffold top-level status fields ─────────
    scaffold = row_scaffold_section

    _expected_statuses = {
        "calculation_status": FUNDING_ADJUSTMENT_ROW_SCAFFOLD_DIAGNOSTIC_ONLY,
        "funding_adjustment_application_status": (
            DIAGNOSTIC_ROW_SCAFFOLD_ONLY_NOT_APPLIED_TO_STRATEGY
        ),
        "strategy_application_status": NOT_EXECUTED,
        "pnl_application_status": NOT_EXECUTED,
        "funding_rate_unit": "decimal_rate_not_percent",
        "notional_policy": "UNIT_NOTIONAL_DIAGNOSTIC_ONLY",
        "side_policy": "BOTH_HYPOTHETICAL_SIDES_DIAGNOSTIC_ONLY",
        "sample_policy": "CAPPED_DETERMINISTIC_SAMPLES_ONLY",
        "sample_size_per_symbol": 10,
    }
    for key, expected in _expected_statuses.items():
        actual = scaffold.get(key)
        if actual != expected:
            raise ValueError(
                f"Expected funding_adjustment_row_scaffold_diagnostics."
                f"{key}={expected!r}, got {actual!r}"
            )

    # ── Step 3: Validate counts are internally consistent ─────────────
    symbols = scaffold.get("symbols", [])
    if not isinstance(symbols, list):
        raise ValueError("row scaffold symbols must be a list")

    seen_symbols: set[str] = set()
    eligible_entries: list[dict] = []
    blocked_entries: list[dict] = []

    for entry in symbols:
        if not isinstance(entry, dict):
            raise ValueError("row scaffold symbol entry must be a dict")
        symbol = entry.get("symbol")
        if not isinstance(symbol, str) or not symbol:
            raise ValueError(f"row scaffold symbol entry has invalid symbol {symbol!r}")
        if symbol in seen_symbols:
            raise ValueError(f"Duplicate scaffold symbol in aggregate: {symbol}")
        seen_symbols.add(symbol)

        scaffold_status = entry.get("scaffold_status")
        row_scaffold_status = entry.get("row_scaffold_status")

        if scaffold_status == MATERIALIZED_DIAGNOSTIC_ROWS:
            # ── Validate eligible symbol ──────────────────────────────
            if row_scaffold_status != "MATERIALIZED_DIAGNOSTIC_CASHFLOW_SAMPLES":
                raise ValueError(
                    f"Eligible symbol {symbol!r} expected "
                    f"row_scaffold_status='MATERIALIZED_DIAGNOSTIC_CASHFLOW_SAMPLES', "
                    f"got {row_scaffold_status!r}"
                )

            sample_rows = entry.get("sample_rows")
            if not isinstance(sample_rows, list):
                raise ValueError(
                    f"Eligible symbol {symbol!r} sample_rows must be a list, "
                    f"got {type(sample_rows).__name__}"
                )

            sample_row_count = entry.get("sample_row_count")
            if sample_row_count != len(sample_rows):
                raise ValueError(
                    f"Eligible symbol {symbol!r} sample_row_count "
                    f"({sample_row_count}) != len(sample_rows) "
                    f"({len(sample_rows)})"
                )

            if sample_row_count > 10:
                raise ValueError(
                    f"Eligible symbol {symbol!r} sample row count "
                    f"{sample_row_count} exceeds maximum of 10"
                )

            # ── Validate each sample row ────────────────────────────
            EXPECTED_SAMPLE_ROW_KEYS = {
                "bar_row_index",
                "funding_row_index",
                "funding_rate",
                "unit_notional",
                "long_cashflow_factor",
                "short_cashflow_factor",
                "formula",
                "application_scope",
            }

            for row_idx, row in enumerate(sample_rows):
                if not isinstance(row, dict):
                    raise ValueError(
                        f"Eligible symbol {symbol!r} sample row "
                        f"{row_idx} is not a dict"
                    )
                actual_keys = set(row.keys())
                if actual_keys != EXPECTED_SAMPLE_ROW_KEYS:
                    extra = actual_keys - EXPECTED_SAMPLE_ROW_KEYS
                    missing = EXPECTED_SAMPLE_ROW_KEYS - actual_keys
                    parts = []
                    if extra:
                        parts.append(f"extra keys: {sorted(extra)}")
                    if missing:
                        parts.append(f"missing keys: {sorted(missing)}")
                    raise ValueError(
                        f"Eligible symbol {symbol!r} sample row {row_idx} "
                        f"key mismatch: {'; '.join(parts)}"
                    )

                if row.get("unit_notional") != "1":
                    raise ValueError(
                        f"Eligible symbol {symbol!r} sample row {row_idx} "
                        f"unit_notional={row.get('unit_notional')!r}, expected '1'"
                    )
                if row.get("formula") != LONG_NEGATES_FUNDING_RATE_SHORT_PRESERVES_FUNDING_RATE_TIMES_NOTIONAL:
                    raise ValueError(
                        f"Eligible symbol {symbol!r} sample row {row_idx} "
                        f"formula={row.get('formula')!r}, expected "
                        f"{LONG_NEGATES_FUNDING_RATE_SHORT_PRESERVES_FUNDING_RATE_TIMES_NOTIONAL!r}"
                    )
                if row.get("application_scope") != "DIAGNOSTIC_SAMPLE_ONLY_NOT_STRATEGY":
                    raise ValueError(
                        f"Eligible symbol {symbol!r} sample row {row_idx} "
                        f"application_scope={row.get('application_scope')!r}, "
                        f"expected 'DIAGNOSTIC_SAMPLE_ONLY_NOT_STRATEGY'"
                    )

                # Validate funding_rate and cashflow factors are finite decimals
                funding_rate_str = row.get("funding_rate")
                long_cf_str = row.get("long_cashflow_factor")
                short_cf_str = row.get("short_cashflow_factor")

                for field_name, raw in [
                    ("funding_rate", funding_rate_str),
                    ("long_cashflow_factor", long_cf_str),
                    ("short_cashflow_factor", short_cf_str),
                ]:
                    if not isinstance(raw, str):
                        raise ValueError(
                            f"Eligible symbol {symbol!r} sample row {row_idx} "
                            f"{field_name} must be a string, got {type(raw).__name__}"
                        )
                    try:
                        dec = Decimal(raw)
                    except (ValueError, ArithmeticError, InvalidOperation) as exc:
                        raise ValueError(
                            f"Eligible symbol {symbol!r} sample row {row_idx} "
                            f"{field_name} is malformed: {raw!r}"
                        ) from exc
                    if not dec.is_finite():
                        raise ValueError(
                            f"Eligible symbol {symbol!r} sample row {row_idx} "
                            f"{field_name} must be finite: {raw!r}"
                        )

                # Validate arithmetic invariants
                funding_rate_dec = Decimal(funding_rate_str)
                long_cf_dec = Decimal(long_cf_str)
                short_cf_dec = Decimal(short_cf_str)

                expected_long_cf = -funding_rate_dec
                expected_short_cf = funding_rate_dec

                if long_cf_dec != expected_long_cf:
                    raise ValueError(
                        f"Eligible symbol {symbol!r} sample row {row_idx} "
                        f"long_cashflow_factor={long_cf_str}, expected "
                        f"{str(expected_long_cf)} (=-funding_rate)"
                    )
                if short_cf_dec != expected_short_cf:
                    raise ValueError(
                        f"Eligible symbol {symbol!r} sample row {row_idx} "
                        f"short_cashflow_factor={short_cf_str}, expected "
                        f"{str(expected_short_cf)} (=funding_rate)"
                    )
                if long_cf_dec != -short_cf_dec:
                    raise ValueError(
                        f"Eligible symbol {symbol!r} sample row {row_idx} "
                        f"long_cashflow_factor ({long_cf_str}) != "
                        f"-short_cashflow_factor ({short_cf_str})"
                    )

            eligible_entries.append(entry)

        elif scaffold_status == SKIPPED_BY_READINESS_GATE:
            # ── Validate blocked/skipped symbol ─────────────────────
            if row_scaffold_status != SKIPPED_BY_READINESS_GATE:
                raise ValueError(
                    f"Blocked symbol {symbol!r} expected "
                    f"row_scaffold_status={SKIPPED_BY_READINESS_GATE!r}, "
                    f"got {row_scaffold_status!r}"
                )

            blocked_reasons = entry.get("blocked_reasons")
            if not isinstance(blocked_reasons, list):
                raise ValueError(
                    f"Blocked symbol {symbol!r} blocked_reasons must be a list"
                )

            # Must have exactly four keys
            ALLOWED_BLOCKED_KEYS = {
                "symbol", "scaffold_status", "row_scaffold_status",
                "blocked_reasons",
            }
            actual_entry_keys = set(entry.keys())
            if actual_entry_keys != ALLOWED_BLOCKED_KEYS:
                extra = actual_entry_keys - ALLOWED_BLOCKED_KEYS
                missing = ALLOWED_BLOCKED_KEYS - actual_entry_keys
                parts = []
                if extra:
                    parts.append(f"extra keys: {sorted(extra)}")
                if missing:
                    parts.append(f"missing keys: {sorted(missing)}")
                raise ValueError(
                    f"Blocked symbol {symbol!r} entry has unexpected keys: "
                    f"{'; '.join(parts)}"
                )

            blocked_entries.append(entry)

        else:
            raise ValueError(
                f"Symbol {symbol!r} has unexpected scaffold_status "
                f"{scaffold_status!r}"
            )

    # ── Step 4: Build per-symbol aggregate output ─────────────────────
    output_symbols: list[dict] = []
    total_sample_rows = 0
    global_long_sum = Decimal("0")
    global_short_sum = Decimal("0")

    for entry in eligible_entries:
        symbol = entry["symbol"]
        sample_rows = entry["sample_rows"]
        sample_row_count = len(sample_rows)
        total_sample_rows += sample_row_count

        # Compute aggregates
        long_factors = [Decimal(row["long_cashflow_factor"]) for row in sample_rows]
        short_factors = [Decimal(row["short_cashflow_factor"]) for row in sample_rows]

        long_sum = sum(long_factors, Decimal("0"))
        short_sum = sum(short_factors, Decimal("0"))
        long_min = min(long_factors)
        long_max = max(long_factors)
        short_min = min(short_factors)
        short_max = max(short_factors)

        long_short_check = long_sum + short_sum
        if long_short_check != Decimal("0"):
            raise ValueError(
                f"Eligible symbol {symbol!r} long_short_sum_check "
                f"({str(long_short_check)}) != 0"
            )

        global_long_sum += long_sum
        global_short_sum += short_sum

        output_symbols.append({
            "symbol": symbol,
            "aggregate_status": MATERIALIZED_DIAGNOSTIC_SAMPLE_AGGREGATES,
            "sample_row_count": sample_row_count,
            "long_cashflow_factor_sum": str(long_sum),
            "short_cashflow_factor_sum": str(short_sum),
            "long_cashflow_factor_min": str(long_min),
            "long_cashflow_factor_max": str(long_max),
            "short_cashflow_factor_min": str(short_min),
            "short_cashflow_factor_max": str(short_max),
            "long_short_sum_check": str(long_short_check),
            "application_scope": DIAGNOSTIC_CAPPED_SAMPLE_AGGREGATE_ONLY_NOT_STRATEGY,
        })

    for entry in blocked_entries:
        symbol = entry["symbol"]
        blocked_reasons = entry.get("blocked_reasons", [])
        output_symbols.append({
            "symbol": symbol,
            "aggregate_status": SKIPPED_BY_READINESS_GATE,
            "blocked_reasons": blocked_reasons,
        })

    # ── Step 5: Compute top-level counts ──────────────────────────────
    eligible_count = scaffold.get("eligible_symbol_count")
    blocked_count = scaffold.get("blocked_symbol_count")
    materialized_count = scaffold.get("materialized_symbol_count")
    skipped_count = scaffold.get("skipped_symbol_count")

    recon_eligible = len(eligible_entries)
    recon_blocked = len(blocked_entries)
    recon_materialized = recon_eligible
    recon_skipped = recon_blocked

    if eligible_count != recon_eligible:
        raise ValueError(
            f"eligible_symbol_count {eligible_count} != derived {recon_eligible}"
        )
    if blocked_count != recon_blocked:
        raise ValueError(
            f"blocked_symbol_count {blocked_count} != derived {recon_blocked}"
        )
    if materialized_count != recon_materialized:
        raise ValueError(
            f"materialized_symbol_count {materialized_count} != derived "
            f"{recon_materialized}"
        )
    if skipped_count != recon_skipped:
        raise ValueError(
            f"skipped_symbol_count {skipped_count} != derived {recon_skipped}"
        )

    # ── Step 6: Build global long/short summary ───────────────────────
    global_long_short_check = global_long_sum + global_short_sum
    if global_long_short_check != Decimal("0"):
        raise ValueError(
            f"global_long_short_sum_check ({str(global_long_short_check)}) != 0"
        )

    section = {
        "calculation_status": FUNDING_ADJUSTMENT_SAMPLE_AGGREGATE_DIAGNOSTIC_ONLY,
        "funding_adjustment_application_status": (
            DIAGNOSTIC_SAMPLE_AGGREGATE_ONLY_NOT_APPLIED_TO_STRATEGY
        ),
        "strategy_application_status": NOT_EXECUTED,
        "pnl_application_status": NOT_EXECUTED,
        "requires_row_scaffold_diagnostics": True,
        "row_scaffold_section_required": (
            "funding_adjustment_row_scaffold_diagnostics"
        ),
        "aggregation_scope": "CAPPED_SAMPLE_ROWS_ONLY",
        "full_dataset_aggregation_status": "NOT_EXECUTED",
        "funding_rate_unit": "decimal_rate_not_percent",
        "notional_policy": "UNIT_NOTIONAL_DIAGNOSTIC_ONLY",
        "side_policy": "BOTH_HYPOTHETICAL_SIDES_DIAGNOSTIC_ONLY",
        "sample_policy": "CAPPED_DETERMINISTIC_SAMPLES_ONLY",
        "eligible_symbol_count": recon_eligible,
        "blocked_symbol_count": recon_blocked,
        "materialized_symbol_count": recon_materialized,
        "skipped_symbol_count": recon_skipped,
        "total_sample_row_count": total_sample_rows,
        "global_long_cashflow_factor_sum": str(global_long_sum),
        "global_short_cashflow_factor_sum": str(global_short_sum),
        "global_long_short_sum_check": str(global_long_short_check),
        "symbols": output_symbols,
    }

    _assert_no_forbidden_calculation_keys(
        section, "$.funding_adjustment_sample_aggregate_diagnostics"
    )
    return section


def build_cost_case_matrix() -> list[dict[str, Any]]:
    """Build the low/base/high cost-case sensitivity matrix skeleton.

    ``base`` mirrors the existing cost-model assumptions used elsewhere in
    this repo (5 bps commission/slippage per side, 1 bps spread per side).
    ``low`` and ``high`` are conservative skeleton-only bracketing
    assumptions, not derived from any measured execution data. No costs
    are actually applied here — ``calculation_status`` stays
    ``NOT_EXECUTED`` for every case.
    """
    return [
        {
            "cost_case": "low",
            "commission_bps_per_side": 2.0,
            "slippage_bps_per_side": 2.0,
            "spread_bps_per_side": 0.5,
            "funding_included": True,
            "calculation_status": "NOT_EXECUTED",
        },
        {
            "cost_case": "base",
            "commission_bps_per_side": 5.0,
            "slippage_bps_per_side": 5.0,
            "spread_bps_per_side": 1.0,
            "funding_included": True,
            "calculation_status": "NOT_EXECUTED",
        },
        {
            "cost_case": "high",
            "commission_bps_per_side": 10.0,
            "slippage_bps_per_side": 10.0,
            "spread_bps_per_side": 2.0,
            "funding_included": True,
            "calculation_status": "NOT_EXECUTED",
        },
    ]


# ── Split leakage audit diagnostics ──────────────────────────────────────


def _build_split_leakage_audit_diagnostics(
    *,
    split_definitions: list[dict[str, Any]],
    split_builder_inspected: str,
) -> dict[str, Any]:
    """Build a diagnostic-only audit of the split windows' leakage posture.

    Inspects the provided split window definitions and records whether they are
    safe for strategy scoring / OOS verdicts. They are **not**: the current
    deterministic splits have a zero purge gap, a zero embargo gap, and none of
    the strategy-dependent scoring prerequisites (decision-time convention,
    feature lookback, label horizon, holding period, funding interval exposure,
    cost event timing) are defined. There is no independent OOS seal, no trial
    manifest, and no frozen symbol universe. This section therefore always
    records ``split_scoring_safe=False`` and blocks strategy scoring.

    It does **not** implement purged/embargoed splits, an OOS seal, or a trial
    manifest, and computes no returns, PnL, Sharpe, drawdown, risk, edge, trade,
    position, signal, or portfolio quantities. Every per-split
    ``calculation_status`` is ``NOT_EXECUTED``; validation row counts are
    deliberately not computed here.

    Fail-closed rules: any overlapping train/validation window forces
    ``split_leakage_audit_status = SPLIT_LEAKAGE_AUDIT_BLOCKED``; otherwise the
    zero-purge/zero-embargo, prerequisite-missing posture yields
    ``SPLIT_LEAKAGE_AUDIT_INSUFFICIENT_FOR_SCORING``. ``split_scoring_safe`` can
    never be ``True`` at this stage.
    """
    if not isinstance(split_definitions, list) or not split_definitions:
        raise ValueError("split_definitions must be a non-empty list")
    if split_builder_inspected not in _VALID_SPLIT_BUILDERS:
        raise ValueError(
            f"split_builder_inspected must be one of "
            f"{sorted(_VALID_SPLIT_BUILDERS)}, got {split_builder_inspected!r}"
        )

    # Strategy-dependent scoring prerequisites — none are defined yet. Named
    # ``scoring_prerequisites_present`` (not strategy_*) to avoid introducing
    # strategy-ish key names into the receipt.
    scoring_prerequisites_present = {
        "decision_time_convention": False,
        "feature_lookback": False,
        "label_horizon": False,
        "holding_period": False,
        "funding_interval_exposure": False,
        "cost_event_timing": False,
    }

    # Open leakage risks that remain until purge/embargo/OOS seal exist.
    leakage_risk_register = {
        "temporal_purge_leakage": True,
        "embargo_leakage": True,
        "same_bar_lookahead": True,
        "future_bar_leakage": True,
        "symbol_universe_leakage": True,
        "no_independent_oos_seal": True,
    }

    ordered_indices = sorted(
        range(len(split_definitions)),
        key=lambda index: split_definitions[index].get("split_index", index),
    )

    per_split: list[dict[str, Any]] = []
    train_validation_overlap_detected = False
    for position, index in enumerate(ordered_indices):
        split = split_definitions[index]
        if not isinstance(split, dict):
            raise ValueError("each split definition must be a dict")

        train_window = split.get("train_window")
        validation_window = split.get("validation_window")
        if not isinstance(train_window, dict) or not isinstance(
            validation_window, dict
        ):
            raise ValueError(
                "each split definition must have train_window and "
                "validation_window dicts"
            )

        train_start = train_window.get("start")
        train_end = train_window.get("end")
        validation_start = validation_window.get("start")
        validation_end = validation_window.get("end")
        for label, value in (
            ("train_window.start", train_start),
            ("train_window.end", train_end),
            ("validation_window.start", validation_start),
            ("validation_window.end", validation_end),
        ):
            if not isinstance(value, str) or not value:
                raise ValueError(
                    f"split {split.get('split_id')!r} has invalid {label}={value!r}"
                )

        train_start_dt = _parse_timestamp(train_start)
        train_end_dt = _parse_timestamp(train_end)
        validation_start_dt = _parse_timestamp(validation_start)
        validation_end_dt = _parse_timestamp(validation_end)

        # Gap between end of train and start of validation. Zero for adjacent
        # windows; negative when train extends past the validation start.
        boundary_gap_seconds = int(
            (validation_start_dt - train_end_dt).total_seconds()
        )

        # Overlap when the train and validation intervals intersect on more
        # than a single shared boundary point.
        overlap_start = max(train_start_dt, validation_start_dt)
        overlap_end = min(train_end_dt, validation_end_dt)
        train_validation_overlap = overlap_start < overlap_end
        if train_validation_overlap:
            train_validation_overlap_detected = True

        per_split.append(
            {
                "split_id": split.get("split_id", f"split_{position:02d}"),
                "split_index": split.get("split_index", index),
                "train_start": train_start,
                "train_end": train_end,
                "validation_start": validation_start,
                "validation_end": validation_end,
                "boundary_gap_seconds": boundary_gap_seconds,
                "train_validation_overlap": train_validation_overlap,
                "validation_row_count_status": (
                    SPLIT_LEAKAGE_AUDIT_ROW_COUNT_NOT_COMPUTED
                ),
                "calculation_status": NOT_EXECUTED,
            }
        )

    # "Adjacent" == no positive purge gap anywhere separates train from
    # validation (touching or overlapping — never separated by a purge/embargo).
    windows_adjacent = all(
        entry["boundary_gap_seconds"] <= 0 for entry in per_split
    )

    # Fail closed on status: any overlap ⇒ BLOCKED; else the zero-purge /
    # zero-embargo / prerequisites-missing posture ⇒ INSUFFICIENT_FOR_SCORING.
    if train_validation_overlap_detected:
        split_leakage_audit_status = SPLIT_LEAKAGE_AUDIT_BLOCKED
    else:
        split_leakage_audit_status = SPLIT_LEAKAGE_AUDIT_INSUFFICIENT_FOR_SCORING

    oos_seal_present = False
    trial_manifest_present = False
    symbol_universe_frozen = False

    # Scoring is safe only when every prerequisite is met, there is no overlap,
    # and an independent OOS seal, trial manifest, and frozen symbol universe
    # all exist. None hold today, so this is always False.
    split_scoring_safe = (
        all(scoring_prerequisites_present.values())
        and not train_validation_overlap_detected
        and oos_seal_present
        and trial_manifest_present
        and symbol_universe_frozen
    )

    return {
        "audit_version": SPLIT_LEAKAGE_AUDIT_VERSION,
        "calculation_status": SPLIT_LEAKAGE_AUDIT_DIAGNOSTIC_ONLY,
        "split_leakage_audit_status": split_leakage_audit_status,
        "split_builder_inspected": split_builder_inspected,
        "split_count": len(per_split),
        "purge_gap_seconds": 0,
        "embargo_gap_seconds": 0,
        "windows_adjacent": windows_adjacent,
        "train_validation_overlap_detected": train_validation_overlap_detected,
        "scoring_prerequisites_present": scoring_prerequisites_present,
        "leakage_risk_register": leakage_risk_register,
        "oos_seal_present": oos_seal_present,
        "trial_manifest_present": trial_manifest_present,
        "symbol_universe_frozen": symbol_universe_frozen,
        "split_scoring_safe": split_scoring_safe,
        "per_split": per_split,
        "per_symbol": None,
    }

# === Strategy-rule contract instance diagnostic constants ===

# Reference allowed input ceiling the materializer enforces.
_CONTRACT_BARS_ALLOWED: frozenset[str] = frozenset({"timestamp", "close"})
_CONTRACT_FUNDING_ALLOWED: frozenset[str] = frozenset({"fundingTime", "fundingRate"})

# Required top-level keys that must survive JSON parsing.
_REQUIRED_STRATEGY_CONTRACT_KEYS: frozenset[str] = frozenset({
    "contract_id",
    "contract_version",
    "contract_frozen",
    "contract_hash",
    "contract_hash_algorithm",
    "contract_hash_status",
    "contract_status",
    "allowed_input_columns",
    "allowed_input_roles",
    "output_boundary",
    "forbidden_output_keys",
    "receipt_key_naming_constraint",
    "scoring_authorization",
    "live_integration_authorized",
    "trial_manifest_dependency_satisfied",
    "oos_seal_dependency_satisfied",
    "null_benchmark_dependency_satisfied",
    "multiple_testing_dependency_satisfied",
    "split_scoring_safe_dependency_satisfied",
    "trade_position_simulation_dependency_satisfied",
    "net_pnl_equity_risk_dependency_satisfied",
    "contract_commit_sha",
})

# Downstream dependency booleans that must all be exactly false.
_DOWNSTREAM_CONTRACT_DEPENDENCY_BOOLEANS: list[str] = [
    "trial_manifest_dependency_satisfied",
    "oos_seal_dependency_satisfied",
    "null_benchmark_dependency_satisfied",
    "multiple_testing_dependency_satisfied",
    "split_scoring_safe_dependency_satisfied",
    "trade_position_simulation_dependency_satisfied",
    "net_pnl_equity_risk_dependency_satisfied",
    "live_integration_authorized",
    "scoring_authorization",
]

# Output-boundary fields that must be present in the contract.
_CONTRACT_OUTPUT_BOUNDARY_KEYS: frozenset[str] = frozenset({
    "output_boundary",
    "forbidden_output_keys",
    "receipt_key_naming_constraint",
})


# Required keys that must survive in the commit-binding sidecar JSON.
_REQUIRED_COMMIT_BINDING_KEYS: frozenset[str] = frozenset({
    "binding_id",
    "binding_version",
    "binding_kind",
    "contract_id",
    "contract_source_path",
    "contract_sha256_sidecar_path",
    "contract_sha256",
    "contract_containing_commit_sha",
    "contract_containing_commit_role",
    "contract_commit_binding_model",
    "self_reference_avoidance",
    "contract_commit_sha_field_policy",
    "scoring_authorization",
    "live_integration_authorized",
    "contract_scoring_ready",
    "contract_instance_readiness",
})


def _find_git_repo_root_for_path(path: str | Path) -> Path:
    """Find the nearest ancestor containing .git for a supplied file path.

    The contract path is expected to live inside the repository. This avoids
    relying on the caller's current working directory.
    """
    current = Path(path).resolve()
    if current.is_file():
        current = current.parent

    for candidate in (current, *current.parents):
        if (candidate / ".git").exists():
            return candidate

    raise ValueError(
        f"Could not find git repository root for path: {path}"
    )


def _read_git_blob_bytes_at_commit(
    *,
    commit_sha: str,
    repo_relative_path: str,
    repo_root: str | Path,
) -> bytes:
    """Read the bytes of a file at a given git commit.

    Uses ``git show <commit_sha>:<repo_relative_path>`` via subprocess,
    running from *repo_root* to avoid depending on the caller's current
    working directory. Fails closed with ``ValueError`` on any nonzero exit.

    *commit_sha* must be a valid git commit SHA (40 hex chars).
    *repo_relative_path* must be a path relative to the repo root as git
    would resolve it (forward slashes, no leading ``./``).
    *repo_root* must be the absolute path to the git repository root.
    """
    if not re.fullmatch(r"[0-9a-fA-F]{40}", commit_sha):
        raise ValueError(
            f"commit_sha must be exactly 40 hex characters, got {commit_sha!r}"
        )

    try:
        result = subprocess.run(
            ["git", "show", f"{commit_sha}:{repo_relative_path}"],
            capture_output=True,
            check=False,
            cwd=str(repo_root),
            timeout=30,
        )
    except FileNotFoundError:
        raise ValueError(
            "git executable not found — cannot verify commit containment"
        )
    except subprocess.TimeoutExpired:
        raise ValueError(
            "git show timed out while reading commit blob"
        )
    except OSError as exc:
        raise ValueError(
            f"git subprocess error: {exc}"
        )

    if result.returncode != 0:
        stderr = result.stderr.decode("utf-8", errors="replace").strip()
        raise ValueError(
            f"git show {commit_sha}:{repo_relative_path} failed "
            f"(exit {result.returncode}): {stderr}"
        )

    return result.stdout


def _find_forbidden_contract_dict_keys(
    value: Any,
    *,
    path: str = "$",
) -> list[dict[str, str]]:
    """Recursively scan *value* for any dict key matching a forbidden calculation
    pattern.

    This is a **strict** scanner for the contract packet only. Unlike the receipt
    scanner (:func:`_assert_no_forbidden_calculation_keys`), it has **no**
    exemptions — ``gross_observational_return`` is rejected at any nesting level,
    including under ``$.gross_observational_returns``.

    Matching is exact dict-key equality against :data:`FORBIDDEN_CALCULATION_KEYS`
    (42 names). Returns a list of ``{path, key}`` dicts for each collision.
    """
    collisions: list[dict[str, str]] = []
    if isinstance(value, dict):
        for key, child in value.items():
            child_path = f"{path}.{key}"
            if key in FORBIDDEN_CALCULATION_KEYS:
                collisions.append({"path": child_path, "key": key})
            collisions.extend(
                _find_forbidden_contract_dict_keys(child, path=child_path)
            )
    elif isinstance(value, (list, tuple)):
        for index, child in enumerate(value):
            collisions.extend(
                _find_forbidden_contract_dict_keys(child, path=f"{path}[{index}]")
            )
    return collisions


def materialize_strategy_rule_contract_instance_diagnostics(
    *,
    contract_path: str,
    sidecar_path: str,
    commit_binding_path: str | None = None,
) -> dict[str, Any]:
    """Read, parse, hash-check, and audit the frozen strategy-rule contract
    packet, returning a diagnostic-only dict.

    When *commit_binding_path* is supplied, the function also loads the
    commit-binding sidecar and verifies that the referenced prior git commit
    contains the exact contract bytes matching the SHA-256 sidecar digest.
    This is a non-self-referential containment check: the binding points to
    a prior commit that already exists on main, not to the current PR's own
    merge commit.

    This function performs **no** scoring, strategy definition, signal
    calculation, PnL, edge, or live-readiness. The returned diagnostic is
    explicitly ``DIAGNOSTIC_READ_ONLY`` — it records the contract's load
    status, hash integrity, forbidden-key survival, input-ceiling alignment,
    output-boundary presence, and downstream boolean posture, but does
    **not** authorize scoring or advance any gate.

    Raises ``ValueError`` on any fail-closed condition:
    - missing / malformed JSON or sidecar
    - sidecar digest mismatch
    - forbidden dict key found (contract or commit-binding sidecar)
    - required field missing (contract or commit-binding sidecar)
    - input ceiling violation
    - output-boundary missing
    - downstream dependency boolean true
    - commit-binding sidecar missing / malformed / invalid
    - commit-binding contract_id mismatch
    - commit-binding sha256 mismatch with computed contract bytes
    - referenced commit SHA not 40 hex chars
    - git show fails for the referenced commit + path
    - prior commit blob digest does not match expected sha256
    """
    # --- Read contract JSON bytes ---
    try:
        contract_bytes = Path(contract_path).read_bytes()
    except FileNotFoundError:
        raise ValueError(
            f"Contract JSON not found: {contract_path}"
        )
    except OSError as exc:
        raise ValueError(
            f"Contract JSON read error {contract_path}: {exc}"
        )

    json_sha256 = hashlib.sha256(contract_bytes).hexdigest()

    # --- Parse JSON ---
    try:
        contract: dict = json.loads(contract_bytes)
    except json.JSONDecodeError as exc:
        raise ValueError(
            f"Contract JSON parse error: {exc}"
        )

    if not isinstance(contract, dict):
        raise ValueError(
            "Contract JSON root must be a dict"
        )

    # --- Read sidecar ---
    try:
        sidecar_text = Path(sidecar_path).read_text().strip()
    except FileNotFoundError:
        raise ValueError(
            f"Contract sidecar not found: {sidecar_path}"
        )
    except OSError as exc:
        raise ValueError(
            f"Contract sidecar read error {sidecar_path}: {exc}"
        )

    # Parse sidecar: expected format "<sha256>  <filename>"
    parts = sidecar_text.split(None, 1)
    if not parts or len(parts) != 2:
        raise ValueError(
            f"Sidecar format invalid: expected '<sha256>  <filename>', "
            f"got {sidecar_text!r}"
        )
    sidecar_sha256 = parts[0]
    sidecar_filename = parts[1]

    if len(sidecar_sha256) != 64:
        raise ValueError(
            f"Sidecar SHA-256 digest length invalid: "
            f"expected 64 hex chars, got {len(sidecar_sha256)}"
        )

    try:
        int(sidecar_sha256, 16)
    except ValueError:
        raise ValueError(
            f"Sidecar SHA-256 digest is not valid hex: {sidecar_sha256!r}"
        )

    sidecar_digest_matches = sidecar_sha256 == json_sha256
    if not sidecar_digest_matches:
        raise ValueError(
            f"Sidecar digest mismatch: "
            f"sidecar={sidecar_sha256}, computed={json_sha256}"
        )

    # --- Check required field presence ---
    missing_fields = _REQUIRED_STRATEGY_CONTRACT_KEYS - set(contract.keys())
    if missing_fields:
        raise ValueError(
            f"Contract missing required fields: {sorted(missing_fields)}"
        )

    # --- Check forbidden dict keys (strict, no receipt-only exemptions) ---
    forbidden_collisions = _find_forbidden_contract_dict_keys(contract)
    if forbidden_collisions:
        collision_repr = ", ".join(
            f"{c['key']!r} at {c['path']}" for c in forbidden_collisions
        )
        raise ValueError(
            f"Contract contains forbidden dict keys: {collision_repr}"
        )

    # --- Check input ceiling ---
    allowed_columns = contract.get("allowed_input_columns", {})
    if not isinstance(allowed_columns, dict):
        raise ValueError(
            "allowed_input_columns must be a dict"
        )

    bars_allowed = allowed_columns.get("bars")
    if not isinstance(bars_allowed, list) or frozenset(bars_allowed) != _CONTRACT_BARS_ALLOWED:
        raise ValueError(
            f"allowed_input_columns.bars must be exactly "
            f"{sorted(_CONTRACT_BARS_ALLOWED)}, got {bars_allowed}"
        )

    funding_allowed = allowed_columns.get("funding")
    if not isinstance(funding_allowed, list) or frozenset(funding_allowed) != _CONTRACT_FUNDING_ALLOWED:
        raise ValueError(
            f"allowed_input_columns.funding must be exactly "
            f"{sorted(_CONTRACT_FUNDING_ALLOWED)}, got {funding_allowed}"
        )

    # Verify that non_materialized_input_columns exist but are separated.
    non_mat = contract.get("non_materialized_input_columns", {})
    if not isinstance(non_mat, dict):
        raise ValueError("non_materialized_input_columns must be a dict")

    # --- Check output-boundary fields ---
    output_boundary_missing = _CONTRACT_OUTPUT_BOUNDARY_KEYS - set(contract.keys())
    if output_boundary_missing:
        raise ValueError(
            f"Contract missing output-boundary keys: "
            f"{sorted(output_boundary_missing)}"
        )

    # --- Check downstream dependency booleans (must be exactly False) ---
    bad_false_fields: dict[str, Any] = {
        field: contract.get(field)
        for field in _DOWNSTREAM_CONTRACT_DEPENDENCY_BOOLEANS
        if contract.get(field) is not False
    }
    if bad_false_fields:
        raise ValueError(
            f"Strategy rule contract fields must be exactly false: "
            + ", ".join(
                f"{k}={v!r}" for k, v in sorted(bad_false_fields.items())
            )
        )

    # --- Build diagnostic dict ---
    contract_commit_sha_field = contract.get("contract_commit_sha", "")
    commit_is_placeholder = contract_commit_sha_field == "TO_BE_FILLED_AFTER_MERGE"

    # Default commit binding diagnostics (unresolved).
    contract_commit_sha_bound = False
    contract_commit_binding_read = False
    contract_commit_binding_path_value = None
    contract_commit_binding_model = None
    contract_containing_commit_sha = None
    contract_containing_commit_path_verified = False
    contract_containing_commit_digest_matches = False
    if commit_is_placeholder:
        contract_commit_sha_binding_status = "UNRESOLVED_SELF_REFERENCE_PLACEHOLDER"
    else:
        contract_commit_sha_binding_status = "UNBOUND"

    # --- Commit binding sidecar (optional C2) ---
    if commit_binding_path is not None:
        # Load and parse the commit-binding JSON.
        try:
            commit_binding_bytes = Path(commit_binding_path).read_bytes()
        except FileNotFoundError:
            raise ValueError(
                f"Commit binding sidecar not found: {commit_binding_path}"
            )
        except OSError as exc:
            raise ValueError(
                f"Commit binding sidecar read error {commit_binding_path}: {exc}"
            )

        try:
            commit_binding: dict = json.loads(commit_binding_bytes)
        except json.JSONDecodeError as exc:
            raise ValueError(
                f"Commit binding sidecar JSON parse error: {exc}"
            )

        if not isinstance(commit_binding, dict):
            raise ValueError(
                "Commit binding sidecar root must be a dict"
            )

        # Verify required binding keys exist.
        missing_binding_keys = _REQUIRED_COMMIT_BINDING_KEYS - set(commit_binding.keys())
        if missing_binding_keys:
            raise ValueError(
                f"Commit binding sidecar missing required keys: "
                f"{sorted(missing_binding_keys)}"
            )

        # Scan commit binding sidecar dict keys against forbidden set.
        binding_forbidden_collisions = _find_forbidden_contract_dict_keys(
            commit_binding
        )
        if binding_forbidden_collisions:
            collision_repr = ", ".join(
                f"{c['key']!r} at {c['path']}"
                for c in binding_forbidden_collisions
            )
            raise ValueError(
                f"Commit binding sidecar contains forbidden dict keys: "
                f"{collision_repr}"
            )

        # Verify contract_id matches.
        binding_contract_id = commit_binding.get("contract_id", "")
        expected_contract_id = contract.get("contract_id", "")
        if binding_contract_id != expected_contract_id:
            raise ValueError(
                f"Commit binding contract_id mismatch: "
                f"binding={binding_contract_id!r}, "
                f"contract={expected_contract_id!r}"
            )

        # Verify contract_source_path matches (normalized repo-relative).
        binding_source_path = commit_binding.get("contract_source_path", "")
        expected_source_path = "docs/contracts/instances/qnty_offline_edge_strategy_rule_contract_v1.json"
        if binding_source_path != expected_source_path:
            raise ValueError(
                f"Commit binding contract_source_path mismatch: "
                f"binding={binding_source_path!r}, "
                f"expected={expected_source_path!r}"
            )

        # Verify contract_sha256 matches computed SHA-256.
        binding_sha256 = commit_binding.get("contract_sha256", "")
        if binding_sha256 != json_sha256:
            raise ValueError(
                f"Commit binding contract_sha256 mismatch: "
                f"binding={binding_sha256}, "
                f"computed={json_sha256}"
            )

        # Verify contract_containing_commit_sha is 40 hex characters.
        containing_commit_sha = commit_binding.get("contract_containing_commit_sha", "")
        if not re.fullmatch(r"[0-9a-fA-F]{40}", containing_commit_sha):
            raise ValueError(
                f"Commit binding contract_containing_commit_sha is not a valid "
                f"40-hex-char SHA: {containing_commit_sha!r}"
            )

        # Resolve repo root from the contract path (not from process cwd)
        # so that commit-binding verification works when the CLI is invoked
        # from outside the repository.
        repo_root = _find_git_repo_root_for_path(contract_path)

        # Verify that the prior commit contains the contract source path
        # with exact bytes matching the expected SHA-256.
        prior_blob_bytes = _read_git_blob_bytes_at_commit(
            commit_sha=containing_commit_sha,
            repo_relative_path=binding_source_path,
            repo_root=repo_root,
        )
        prior_blob_sha256 = hashlib.sha256(prior_blob_bytes).hexdigest()
        prior_digest_matches = prior_blob_sha256 == binding_sha256

        if not prior_digest_matches:
            raise ValueError(
                f"Prior commit {containing_commit_sha} contains "
                f"{binding_source_path} but bytes digest mismatch: "
                f"expected {binding_sha256}, got {prior_blob_sha256}"
            )

        # Commit binding succeeded.
        contract_commit_sha_bound = True
        contract_commit_binding_read = True
        contract_commit_binding_path_value = str(commit_binding_path)
        contract_commit_binding_model = str(
            commit_binding.get("contract_commit_binding_model", "")
        )
        contract_containing_commit_sha = containing_commit_sha
        contract_containing_commit_path_verified = True
        contract_containing_commit_digest_matches = True
        contract_commit_sha_binding_status = (
            "BOUND_BY_PRIOR_COMMIT_CONTAINMENT_SIDECAR"
        )

    return {
        "diagnostic_kind": "strategy_rule_contract_instance",
        "contract_source_path": contract_path,
        "contract_sidecar_path": sidecar_path,
        "contract_commit_binding_path": contract_commit_binding_path_value,
        "contract_id": str(contract.get("contract_id", "")),
        "contract_version": str(contract.get("contract_version", "")),
        "contract_status": str(contract.get("contract_status", "")),
        "contract_packet_read": True,
        "json_parse_ok": True,
        "sidecar_parse_ok": True,
        "json_sha256": json_sha256,
        "sidecar_sha256": sidecar_sha256,
        "sidecar_digest_matches_json_bytes": True,
        "contract_hash_authority": "SIDECAR",
        "contract_hash_field_value": str(contract.get("contract_hash", "")),
        "contract_hash_status": str(contract.get("contract_hash_status", "")),
        "required_fields_present": True,
        "missing_required_fields": [],
        "forbidden_dict_key_scan_passed": True,
        "forbidden_dict_key_collisions": [],
        "input_ceiling_check_passed": True,
        "output_boundary_fields_present": True,
        "scoring_authorization": False,
        "live_integration_authorized": False,
        "downstream_dependency_booleans_all_false": True,
        "contract_runner_read_status": "DIAGNOSTIC_READ_ONLY",
        "contract_commit_sha_field_value": contract_commit_sha_field,
        "contract_commit_sha_bound": contract_commit_sha_bound,
        "contract_commit_sha_binding_status": contract_commit_sha_binding_status,
        "contract_commit_binding_read": contract_commit_binding_read,
        "contract_commit_binding_model": contract_commit_binding_model,
        "contract_containing_commit_sha": contract_containing_commit_sha,
        "contract_containing_commit_path_verified": (
            contract_containing_commit_path_verified
        ),
        "contract_containing_commit_digest_matches": (
            contract_containing_commit_digest_matches
        ),
        "contract_instance_readiness": False,
        "contract_scoring_ready": False,
        "contract_validation_status": (
            "COMMIT_BOUND_DIAGNOSTIC_ONLY_NOT_SCORING_READY"
            if contract_commit_sha_bound
            else "BLOCKED_BY_COMMIT_BINDING_PLACEHOLDER"
        ),
    }


def materialize_trial_manifest_preregistration_diagnostics(
    *,
    manifest_path: str,
    sidecar_path: str,
    strategy_rule_contract_diagnostics: dict[str, Any],
) -> dict[str, Any]:
    """Read, parse, hash-check, and audit the frozen trial manifest
    pre-registration packet, returning a diagnostic-only dict.

    This function performs **no** scoring, strategy definition, signal
    calculation, PnL, edge, or live-readiness. The returned diagnostic is
    explicitly diagnostic-only — it records the manifest's load status,
    hash integrity, forbidden-key survival, contract binding, and
    authorization posture, but does **not** authorize scoring or advance
    any gate.

    Raises ``ValueError`` on any fail-closed condition:
    - missing / malformed JSON or sidecar
    - sidecar digest mismatch
    - forbidden dict key found
    - required field missing
    - manifest_hash not ``FROZEN_IN_SIDECAR``
    - bound contract digest mismatch
    - contract packet gate missing or false
    - authorized_trial_count != 1
    - trial_count_frozen is not True
    - hyperparameter_search_policy != ``NO_SEARCH``
    - free_parameter_count != 0
    - declared_parameter_names non-empty
    - any authorization boolean not exactly False
    - any downstream dependency boolean not exactly False
    """
    # --- Read manifest JSON bytes ---
    try:
        manifest_bytes = Path(manifest_path).read_bytes()
    except FileNotFoundError:
        raise ValueError(
            f"Trial manifest JSON not found: {manifest_path}"
        )
    except OSError as exc:
        raise ValueError(
            f"Trial manifest JSON read error {manifest_path}: {exc}"
        )

    json_sha256 = hashlib.sha256(manifest_bytes).hexdigest()

    # --- Parse JSON ---
    try:
        manifest: dict = json.loads(manifest_bytes)
    except json.JSONDecodeError as exc:
        raise ValueError(
            f"Trial manifest JSON parse error: {exc}"
        )

    if not isinstance(manifest, dict):
        raise ValueError(
            "Trial manifest JSON root must be a dict"
        )

    # --- Read sidecar ---
    try:
        sidecar_text = Path(sidecar_path).read_text().strip()
    except FileNotFoundError:
        raise ValueError(
            f"Trial manifest sidecar not found: {sidecar_path}"
        )
    except OSError as exc:
        raise ValueError(
            f"Trial manifest sidecar read error {sidecar_path}: {exc}"
        )

    # Parse sidecar: expected format "<sha256>  <filename>"
    parts = sidecar_text.split(None, 1)
    if not parts or len(parts) != 2:
        raise ValueError(
            f"Trial manifest sidecar format invalid: "
            f"expected '<sha256>  <filename>', got {sidecar_text!r}"
        )
    sidecar_sha256 = parts[0]
    sidecar_filename = parts[1]

    if len(sidecar_sha256) != 64:
        raise ValueError(
            f"Trial manifest sidecar SHA-256 digest length invalid: "
            f"expected 64 hex chars, got {len(sidecar_sha256)}"
        )

    try:
        int(sidecar_sha256, 16)
    except ValueError:
        raise ValueError(
            f"Trial manifest sidecar SHA-256 digest is not valid hex: "
            f"{sidecar_sha256!r}"
        )

    sidecar_digest_matches = sidecar_sha256 == json_sha256
    if not sidecar_digest_matches:
        raise ValueError(
            f"Trial manifest sidecar digest mismatch: "
            f"sidecar={sidecar_sha256}, computed={json_sha256}"
        )

    # --- Check required field presence ---
    _REQUIRED_TRIAL_MANIFEST_KEYS: set[str] = {
        "manifest_id",
        "manifest_version",
        "manifest_kind",
        "manifest_status",
        "manifest_hash",
        "manifest_hash_algorithm",
        "manifest_hash_scope",
        "manifest_hash_status",
        "bound_contract_id",
        "bound_contract_sha256",
        "candidate_id",
        "hypothesis_id",
        "trial_policy",
        "authorized_trial_count",
        "trial_count_frozen",
        "hyperparameter_search_policy",
        "free_parameter_count",
        "declared_parameter_names",
        "trial_execution_authorized",
        "scoring_authorization",
        "live_integration_authorized",
        "paper_integration_authorized",
        "final_verdict_authorization",
        "oos_seal_dependency_satisfied",
        "null_benchmark_dependency_satisfied",
        "multiple_testing_dependency_satisfied",
        "trade_position_simulation_dependency_satisfied",
        "net_pnl_equity_risk_dependency_satisfied",
    }
    missing_fields = _REQUIRED_TRIAL_MANIFEST_KEYS - set(manifest.keys())
    if missing_fields:
        raise ValueError(
            f"Trial manifest missing required fields: {sorted(missing_fields)}"
        )

    # --- Check forbidden dict keys (strict, no exemptions) ---
    forbidden_collisions = _find_forbidden_contract_dict_keys(manifest)
    if forbidden_collisions:
        collision_repr = ", ".join(
            f"{c['key']!r} at {c['path']}" for c in forbidden_collisions
        )
        raise ValueError(
            f"Trial manifest contains forbidden dict keys: {collision_repr}"
        )

    # --- Verify manifest hash fields ---
    if manifest.get("manifest_hash") != "FROZEN_IN_SIDECAR":
        raise ValueError(
            f"Trial manifest manifest_hash must be 'FROZEN_IN_SIDECAR', "
            f"got {manifest.get('manifest_hash')!r}"
        )
    if manifest.get("manifest_hash_status") != "FROZEN_IN_SIDECAR":
        raise ValueError(
            f"Trial manifest manifest_hash_status must be 'FROZEN_IN_SIDECAR', "
            f"got {manifest.get('manifest_hash_status')!r}"
        )
    if manifest.get("manifest_hash_algorithm") != "sha256":
        raise ValueError(
            f"Trial manifest manifest_hash_algorithm must be 'sha256', "
            f"got {manifest.get('manifest_hash_algorithm')!r}"
        )

    # --- Verify bound contract digest ---
    contract_diag = strategy_rule_contract_diagnostics
    contract_json_sha256 = contract_diag.get("json_sha256")
    contract_id = contract_diag.get("contract_id")
    bound_contract_sha256 = manifest.get("bound_contract_sha256")
    bound_contract_id = manifest.get("bound_contract_id")

    if bound_contract_sha256 != contract_json_sha256:
        raise ValueError(
            f"Trial manifest bound_contract_sha256 mismatch: "
            f"manifest says {bound_contract_sha256}, "
            f"contract diagnostic says {contract_json_sha256}"
        )
    if bound_contract_id != contract_id:
        raise ValueError(
            f"Trial manifest bound_contract_id mismatch: "
            f"manifest says {bound_contract_id}, "
            f"contract diagnostic says {contract_id}"
        )

    # --- Verify contract packet gate ---
    contract_packet_gate = contract_diag.get("contract_packet_gate", {})
    if not isinstance(contract_packet_gate, dict):
        raise ValueError(
            "Contract packet gate is not a dict"
        )
    if not contract_packet_gate.get("gate_passed"):
        raise ValueError(
            "Contract packet gate not passed: "
            f"trial manifest cannot proceed without contract packet gate"
        )
    gate_status = contract_packet_gate.get("gate_status")
    if gate_status != "CONTRACT_PACKET_COMMIT_BOUND_DIAGNOSTIC_ONLY":
        raise ValueError(
            f"Contract packet gate status must be "
            f"'CONTRACT_PACKET_COMMIT_BOUND_DIAGNOSTIC_ONLY', got {gate_status!r}"
        )

    # --- Verify trial count and search policy ---
    if manifest.get("authorized_trial_count") != 1:
        raise ValueError(
            f"Trial manifest authorized_trial_count must be 1, "
            f"got {manifest.get('authorized_trial_count')!r}"
        )
    if manifest.get("trial_count_frozen") is not True:
        raise ValueError(
            f"Trial manifest trial_count_frozen must be True, "
            f"got {manifest.get('trial_count_frozen')!r}"
        )
    if manifest.get("hyperparameter_search_policy") != "NO_SEARCH":
        raise ValueError(
            f"Trial manifest hyperparameter_search_policy must be 'NO_SEARCH', "
            f"got {manifest.get('hyperparameter_search_policy')!r}"
        )
    if manifest.get("free_parameter_count") != 0:
        raise ValueError(
            f"Trial manifest free_parameter_count must be 0, "
            f"got {manifest.get('free_parameter_count')!r}"
        )
    declared_params = manifest.get("declared_parameter_names", [])
    if not isinstance(declared_params, list) or len(declared_params) > 0:
        raise ValueError(
            f"Trial manifest declared_parameter_names must be empty, "
            f"got {declared_params!r}"
        )

    # --- Verify authorization booleans are exactly False ---
    bad_false_fields: dict[str, Any] = {
        field: manifest.get(field)
        for field in _REQUIRED_FALSE_TRIAL_MANIFEST_FIELDS
        if manifest.get(field) is not False
    }
    if bad_false_fields:
        raise ValueError(
            f"Trial manifest fields must be exactly false: "
            + ", ".join(
                f"{k}={v!r}" for k, v in bad_false_fields.items()
            )
        )

    return {
        "diagnostic_kind": "trial_manifest_preregistration",
        "manifest_source_path": manifest_path,
        "manifest_sidecar_path": sidecar_path,
        "manifest_packet_read": True,
        "manifest_json_parse_ok": True,
        "manifest_sidecar_parse_ok": True,
        "manifest_json_sha256": json_sha256,
        "manifest_sidecar_sha256": sidecar_sha256,
        "manifest_sidecar_digest_matches_json_bytes": True,
        "manifest_hash_authority": "SIDECAR",
        "manifest_hash_field_value": "FROZEN_IN_SIDECAR",
        "manifest_hash_status": "FROZEN_IN_SIDECAR",
        "manifest_required_fields_present": True,
        "manifest_forbidden_dict_key_scan_passed": True,
        "manifest_id": str(manifest.get("manifest_id", "")),
        "manifest_version": str(manifest.get("manifest_version", "")),
        "manifest_status": str(manifest.get("manifest_status", "")),
        "bound_contract_id": str(bound_contract_id),
        "bound_contract_sha256": str(bound_contract_sha256),
        "bound_contract_digest_matches": True,
        "contract_packet_gate_required": True,
        "contract_packet_gate_passed": True,
        "contract_packet_gate_status": str(gate_status),
        "authorized_trial_count": 1,
        "trial_count_frozen": True,
        "hyperparameter_search_policy": "NO_SEARCH",
        "free_parameter_count": 0,
        "declared_parameter_names": [],
        "trial_manifest_readiness": False,
        "trial_execution_authorized": False,
        "trial_scoring_ready": False,
        "trial_manifest_validation_status": (
            "TRIAL_MANIFEST_PREREGISTERED_DIAGNOSTIC_ONLY"
        ),
    }


def _derive_trial_manifest_preregistration_gate(
    diagnostics: dict[str, Any],
) -> dict[str, Any]:
    """Derive a trial-manifest pre-registration gate from diagnostics.

    The gate passes only when all of the following hold:
    - manifest packet read
    - manifest sidecar matches
    - manifest strict forbidden-key scan passed
    - bound contract digest matches
    - contract packet gate passed
    - trial count is exactly 1
    - no-search policy
    - zero free params
    - all authorization booleans false
    - all downstream dependency booleans false
    """
    evidence: dict[str, Any] = {
        "manifest_sidecar_digest_matches_json_bytes": (
            diagnostics.get("manifest_sidecar_digest_matches_json_bytes")
            is True
        ),
        "bound_contract_digest_matches": (
            diagnostics.get("bound_contract_digest_matches") is True
        ),
        "contract_packet_gate_passed": (
            diagnostics.get("contract_packet_gate_passed") is True
        ),
        "authorized_trial_count": (
            diagnostics.get("authorized_trial_count") == 1
        ),
        "trial_count_frozen": (
            diagnostics.get("trial_count_frozen") is True
        ),
        "hyperparameter_search_policy": (
            diagnostics.get("hyperparameter_search_policy") == "NO_SEARCH"
        ),
        "free_parameter_count": (
            diagnostics.get("free_parameter_count") == 0
        ),
    }

    extra_pass = (
        diagnostics.get("diagnostic_kind")
        == "trial_manifest_preregistration"
        and diagnostics.get("manifest_packet_read") is True
        and diagnostics.get("manifest_json_parse_ok") is True
        and diagnostics.get("manifest_sidecar_parse_ok") is True
        and diagnostics.get("manifest_hash_authority") == "SIDECAR"
        and diagnostics.get("manifest_hash_field_value") == "FROZEN_IN_SIDECAR"
        and diagnostics.get("manifest_hash_status") == "FROZEN_IN_SIDECAR"
        and diagnostics.get("manifest_required_fields_present") is True
        and diagnostics.get("manifest_forbidden_dict_key_scan_passed") is True
        and diagnostics.get("trial_execution_authorized") is False
        and diagnostics.get("trial_scoring_ready") is False
        and diagnostics.get("trial_manifest_readiness") is False
    )

    all_pass = all(evidence.values()) and extra_pass

    if all_pass:
        gate_status = "TRIAL_MANIFEST_PREREGISTERED_DIAGNOSTIC_ONLY"
        blocked_reason = None
    elif diagnostics.get("diagnostic_kind") != "trial_manifest_preregistration":
        gate_status = "TRIAL_MANIFEST_NOT_LOADED"
        blocked_reason = "TRIAL_MANIFEST_NOT_PROVIDED"
    else:
        gate_status = "BLOCKED_BY_INCOMPLETE_TRIAL_MANIFEST_EVIDENCE"
        blocked_reason = "TRIAL_MANIFEST_GATE_EVIDENCE_INCOMPLETE"

    return {
        "gate_kind": "trial_manifest_preregistration_gate",
        "gate_scope": (
            "TRIAL_COUNT_CANDIDATE_AND_CONTRACT_BINDING_ONLY"
        ),
        "gate_status": gate_status,
        "gate_passed": all_pass,
        "gate_scoring_authorization": False,
        "gate_live_authorization": False,
        "gate_final_verdict_authorization": False,
        "gate_downstream_unlocks": [],
        "evidence": evidence,
        "blocked_reason": blocked_reason,
    }


def materialize_oos_seal_preregistration_diagnostics(
    *,
    seal_path: str,
    sidecar_path: str,
    trial_manifest_diagnostics: dict[str, Any],
    strategy_rule_contract_diagnostics: dict[str, Any],
) -> dict[str, Any]:
    """Read, parse, hash-check, and audit the frozen OOS seal pre-scoring
    declaration packet, returning a diagnostic-only dict.

    This function performs **no** scoring, OOS evaluation, strategy definition,
    signal calculation, PnL, edge, or live-readiness. The returned diagnostic is
    explicitly diagnostic-only — it records the seal's load status, hash
    integrity, forbidden-key survival, bound contract/trial-manifest digest
    checking, trial-manifest gate verification, OOS boundary/split-lock policy
    presence, and authorization posture, but does **not** authorize scoring or
    advance any gate.

    Raises ``ValueError`` on any fail-closed condition:
    - missing / malformed JSON or sidecar
    - sidecar digest mismatch
    - forbidden dict key found
    - required field missing
    - seal_hash not ``FROZEN_IN_SIDECAR``
    - seal_hash_status not ``FROZEN_IN_SIDECAR``
    - seal_hash_algorithm not ``sha256``
    - bound contract digest mismatch
    - bound trial manifest digest mismatch
    - trial manifest gate missing or false
    - OOS boundary policy not frozen
    - OOS split selection not frozen
    - any authorization boolean not exactly False
    - any downstream dependency boolean not exactly False
    """
    # --- Read seal JSON bytes ---
    try:
        seal_bytes = Path(seal_path).read_bytes()
    except FileNotFoundError:
        raise ValueError(
            f"OOS seal JSON not found: {seal_path}"
        )
    except OSError as exc:
        raise ValueError(
            f"OOS seal JSON read error {seal_path}: {exc}"
        )

    json_sha256 = hashlib.sha256(seal_bytes).hexdigest()

    # --- Parse JSON ---
    try:
        seal: dict = json.loads(seal_bytes)
    except json.JSONDecodeError as exc:
        raise ValueError(
            f"OOS seal JSON parse error: {exc}"
        )

    if not isinstance(seal, dict):
        raise ValueError(
            "OOS seal JSON root must be a dict"
        )

    # --- Read sidecar ---
    try:
        sidecar_text = Path(sidecar_path).read_text().strip()
    except FileNotFoundError:
        raise ValueError(
            f"OOS seal sidecar not found: {sidecar_path}"
        )
    except OSError as exc:
        raise ValueError(
            f"OOS seal sidecar read error {sidecar_path}: {exc}"
        )

    # Parse sidecar: expected format "<sha256>  <filename>"
    parts = sidecar_text.split(None, 1)
    if not parts or len(parts) != 2:
        raise ValueError(
            f"OOS seal sidecar format invalid: "
            f"expected '<sha256>  <filename>', got {sidecar_text!r}"
        )
    sidecar_sha256 = parts[0]
    sidecar_filename = parts[1]

    if len(sidecar_sha256) != 64:
        raise ValueError(
            f"OOS seal sidecar SHA-256 digest length invalid: "
            f"expected 64 hex chars, got {len(sidecar_sha256)}"
        )

    try:
        int(sidecar_sha256, 16)
    except ValueError:
        raise ValueError(
            f"OOS seal sidecar SHA-256 digest is not valid hex: "
            f"{sidecar_sha256!r}"
        )

    sidecar_digest_matches = sidecar_sha256 == json_sha256
    if not sidecar_digest_matches:
        raise ValueError(
            f"OOS seal sidecar digest mismatch: "
            f"sidecar={sidecar_sha256}, computed={json_sha256}"
        )

    # --- Check required field presence ---
    _REQUIRED_OOS_SEAL_KEYS: set[str] = {
        "seal_id",
        "seal_version",
        "seal_kind",
        "seal_status",
        "seal_hash",
        "seal_hash_algorithm",
        "seal_hash_scope",
        "seal_hash_status",
        "bound_contract_id",
        "bound_contract_sha256",
        "bound_trial_manifest_id",
        "bound_trial_manifest_sha256",
        "required_trial_manifest_gate_status",
        "oos_boundary_policy",
        "oos_boundary_policy_frozen",
        "oos_split_selection_policy",
        "oos_split_selection_frozen",
        "split_mutation_authorized",
        "oos_scoring_authorized",
        "trial_execution_authorized",
        "scoring_authorization",
        "live_integration_authorized",
        "paper_integration_authorized",
        "final_verdict_authorization",
        "null_benchmark_dependency_satisfied",
        "multiple_testing_dependency_satisfied",
        "trade_position_simulation_dependency_satisfied",
        "net_pnl_equity_risk_dependency_satisfied",
    }
    missing_fields = _REQUIRED_OOS_SEAL_KEYS - set(seal.keys())
    if missing_fields:
        raise ValueError(
            f"OOS seal missing required fields: {sorted(missing_fields)}"
        )

    # --- Check forbidden dict keys (strict, no exemptions) ---
    forbidden_collisions = _find_forbidden_contract_dict_keys(seal)
    if forbidden_collisions:
        collision_repr = ", ".join(
            f"{c['key']!r} at {c['path']}" for c in forbidden_collisions
        )
        raise ValueError(
            f"OOS seal contains forbidden dict keys: {collision_repr}"
        )

    # --- Verify seal hash fields ---
    if seal.get("seal_hash") != "FROZEN_IN_SIDECAR":
        raise ValueError(
            f"OOS seal seal_hash must be 'FROZEN_IN_SIDECAR', "
            f"got {seal.get('seal_hash')!r}"
        )
    if seal.get("seal_hash_status") != "FROZEN_IN_SIDECAR":
        raise ValueError(
            f"OOS seal seal_hash_status must be 'FROZEN_IN_SIDECAR', "
            f"got {seal.get('seal_hash_status')!r}"
        )
    if seal.get("seal_hash_algorithm") != "sha256":
        raise ValueError(
            f"OOS seal seal_hash_algorithm must be 'sha256', "
            f"got {seal.get('seal_hash_algorithm')!r}"
        )

    # --- Verify bound contract digest ---
    contract_diag = strategy_rule_contract_diagnostics
    contract_json_sha256 = contract_diag.get("json_sha256")
    contract_id = contract_diag.get("contract_id")
    bound_contract_sha256 = seal.get("bound_contract_sha256")
    bound_contract_id = seal.get("bound_contract_id")

    if bound_contract_sha256 != contract_json_sha256:
        raise ValueError(
            f"OOS seal bound_contract_sha256 mismatch: "
            f"seal says {bound_contract_sha256}, "
            f"contract diagnostic says {contract_json_sha256}"
        )
    if bound_contract_id != contract_id:
        raise ValueError(
            f"OOS seal bound_contract_id mismatch: "
            f"seal says {bound_contract_id}, "
            f"contract diagnostic says {contract_id}"
        )

    # --- Verify trial manifest gate (before digest check, gate is more fundamental) ---
    tmd = trial_manifest_diagnostics
    trial_manifest_gate = tmd.get("trial_manifest_preregistration_gate", {})
    if not isinstance(trial_manifest_gate, dict):
        raise ValueError(
            "Trial manifest gate is not a dict"
        )
    if not trial_manifest_gate.get("gate_passed"):
        raise ValueError(
            "Trial manifest gate not passed: "
            f"OOS seal cannot proceed without trial manifest gate"
        )
    gate_status = trial_manifest_gate.get("gate_status")
    if gate_status != "TRIAL_MANIFEST_PREREGISTERED_DIAGNOSTIC_ONLY":
        raise ValueError(
            f"Trial manifest gate status must be "
            f"'TRIAL_MANIFEST_PREREGISTERED_DIAGNOSTIC_ONLY', "
            f"got {gate_status!r}"
        )

    # --- Verify bound trial manifest digest (after gate check) ---
    manifest_json_sha256 = tmd.get("manifest_json_sha256")
    manifest_id = tmd.get("manifest_id")
    bound_trial_manifest_sha256 = seal.get("bound_trial_manifest_sha256")
    bound_trial_manifest_id = seal.get("bound_trial_manifest_id")

    if bound_trial_manifest_sha256 != manifest_json_sha256:
        raise ValueError(
            f"OOS seal bound_trial_manifest_sha256 mismatch: "
            f"seal says {bound_trial_manifest_sha256}, "
            f"trial manifest diagnostic says {manifest_json_sha256}"
        )
    if bound_trial_manifest_id != manifest_id:
        raise ValueError(
            f"OOS seal bound_trial_manifest_id mismatch: "
            f"seal says {bound_trial_manifest_id}, "
            f"trial manifest diagnostic says {manifest_id}"
        )

    # --- Verify OOS boundary policy fields ---
    if seal.get("oos_boundary_policy_frozen") is not True:
        raise ValueError(
            f"OOS seal oos_boundary_policy_frozen must be True, "
            f"got {seal.get('oos_boundary_policy_frozen')!r}"
        )
    if seal.get("oos_split_selection_frozen") is not True:
        raise ValueError(
            f"OOS seal oos_split_selection_frozen must be True, "
            f"got {seal.get('oos_split_selection_frozen')!r}"
        )

    # --- Verify authorization booleans are exactly False ---
    bad_false_fields: dict[str, Any] = {
        field: seal.get(field)
        for field in _REQUIRED_FALSE_OOS_SEAL_FIELDS
        if seal.get(field) is not False
    }
    if bad_false_fields:
        raise ValueError(
            f"OOS seal fields must be exactly false: "
            + ", ".join(
                f"{k}={v!r}" for k, v in bad_false_fields.items()
            )
        )

    return {
        "diagnostic_kind": "oos_seal_preregistration",
        "seal_source_path": seal_path,
        "seal_sidecar_path": sidecar_path,
        "seal_id": str(seal.get("seal_id", "")),
        "seal_version": str(seal.get("seal_version", "")),
        "seal_status": str(seal.get("seal_status", "")),
        "seal_packet_read": True,
        "seal_json_parse_ok": True,
        "seal_sidecar_parse_ok": True,
        "seal_json_sha256": json_sha256,
        "seal_sidecar_sha256": sidecar_sha256,
        "seal_sidecar_digest_matches_json_bytes": True,
        "seal_hash_authority": "SIDECAR",
        "seal_hash_field_value": "FROZEN_IN_SIDECAR",
        "seal_hash_status": "FROZEN_IN_SIDECAR",
        "seal_required_fields_present": True,
        "seal_forbidden_dict_key_scan_passed": True,
        "bound_contract_id": str(bound_contract_id),
        "bound_contract_sha256": str(bound_contract_sha256),
        "bound_contract_digest_matches": True,
        "bound_trial_manifest_id": str(bound_trial_manifest_id),
        "bound_trial_manifest_sha256": str(bound_trial_manifest_sha256),
        "bound_trial_manifest_digest_matches": True,
        "trial_manifest_gate_required": True,
        "trial_manifest_gate_passed": True,
        "trial_manifest_gate_status": str(gate_status),
        "oos_boundary_policy": str(seal.get("oos_boundary_policy", "")),
        "oos_boundary_policy_frozen": True,
        "oos_split_selection_policy": str(seal.get("oos_split_selection_policy", "")),
        "oos_split_selection_frozen": True,
        "oos_seal_readiness": False,
        "oos_scoring_authorized": False,
        "trial_execution_authorized": False,
        "oos_seal_validation_status": (
            "OOS_SEAL_PREREGISTERED_DIAGNOSTIC_ONLY"
        ),
    }


def _derive_oos_seal_preregistration_gate(
    diagnostics: dict[str, Any],
) -> dict[str, Any]:
    """Derive an OOS seal pre-registration gate from diagnostics.

    The gate passes only when all of the following hold:
    - seal packet read
    - seal sidecar matches
    - seal strict forbidden-key scan passed
    - bound contract digest matches
    - bound trial manifest digest matches
    - trial manifest gate passed
    - OOS boundary policy frozen
    - OOS split selection frozen
    - all authorization booleans false
    - all downstream dependency booleans false
    """
    evidence: dict[str, Any] = {
        "seal_sidecar_digest_matches_json_bytes": (
            diagnostics.get("seal_sidecar_digest_matches_json_bytes")
            is True
        ),
        "bound_contract_digest_matches": (
            diagnostics.get("bound_contract_digest_matches") is True
        ),
        "bound_trial_manifest_digest_matches": (
            diagnostics.get("bound_trial_manifest_digest_matches") is True
        ),
        "trial_manifest_gate_passed": (
            diagnostics.get("trial_manifest_gate_passed") is True
        ),
        "oos_boundary_policy_frozen": (
            diagnostics.get("oos_boundary_policy_frozen") is True
        ),
        "oos_split_selection_frozen": (
            diagnostics.get("oos_split_selection_frozen") is True
        ),
    }

    extra_pass = (
        diagnostics.get("diagnostic_kind")
        == "oos_seal_preregistration"
        and diagnostics.get("seal_packet_read") is True
        and diagnostics.get("seal_json_parse_ok") is True
        and diagnostics.get("seal_sidecar_parse_ok") is True
        and diagnostics.get("seal_hash_authority") == "SIDECAR"
        and diagnostics.get("seal_hash_field_value") == "FROZEN_IN_SIDECAR"
        and diagnostics.get("seal_hash_status") == "FROZEN_IN_SIDECAR"
        and diagnostics.get("seal_required_fields_present") is True
        and diagnostics.get("seal_forbidden_dict_key_scan_passed") is True
        and diagnostics.get("oos_scoring_authorized") is False
        and diagnostics.get("trial_execution_authorized") is False
        and diagnostics.get("oos_seal_readiness") is False
    )

    all_pass = all(evidence.values()) and extra_pass

    if all_pass:
        gate_status = "OOS_SEAL_PREREGISTERED_DIAGNOSTIC_ONLY"
        blocked_reason = None
    elif diagnostics.get("diagnostic_kind") != "oos_seal_preregistration":
        gate_status = "OOS_SEAL_NOT_LOADED"
        blocked_reason = "OOS_SEAL_NOT_PROVIDED"
    else:
        gate_status = "BLOCKED_BY_INCOMPLETE_OOS_SEAL_EVIDENCE"
        blocked_reason = "OOS_SEAL_GATE_EVIDENCE_INCOMPLETE"

    return {
        "gate_kind": "oos_seal_preregistration_gate",
        "gate_scope": (
            "OOS_BOUNDARY_AND_TRIAL_MANIFEST_BINDING_ONLY"
        ),
        "gate_status": gate_status,
        "gate_passed": all_pass,
        "gate_scoring_authorization": False,
        "gate_live_authorization": False,
        "gate_final_verdict_authorization": False,
        "gate_downstream_unlocks": [],
        "evidence": evidence,
        "blocked_reason": blocked_reason,
    }


def materialize_null_benchmark_preregistration_diagnostics(
    *,
    null_benchmark_path: str,
    sidecar_path: str,
    oos_seal_diagnostics: dict[str, Any],
    trial_manifest_diagnostics: dict[str, Any],
    strategy_rule_contract_diagnostics: dict[str, Any],
) -> dict[str, Any]:
    """Read, parse, hash-check, and audit the frozen null benchmark pre-scoring
    declaration packet, returning a diagnostic-only dict.

    This function performs **no** null generation, candidate-vs-null comparison,
    scoring, strategy definition, signal calculation, PnL, edge, or
    live-readiness. The returned diagnostic records only the packet's load
    status, hash integrity, forbidden-key survival, bound
    contract/trial-manifest/OOS-seal digest checking, OOS-seal gate
    verification, null reference policy freeze, and authorization posture. It
    does **not** authorize scoring or advance any gate.

    Raises ``ValueError`` on any fail-closed condition:
    - missing / malformed JSON or sidecar
    - sidecar digest mismatch
    - forbidden dict key found
    - required field missing
    - null_benchmark_hash not ``FROZEN_IN_SIDECAR``
    - null_benchmark_hash_status not ``FROZEN_IN_SIDECAR``
    - null_benchmark_hash_algorithm not ``sha256``
    - bound contract / trial manifest / OOS seal digest or id mismatch
    - OOS seal gate missing or not passed
    - null reference selection or count not frozen
    - null reference count != 1
    - any authorization boolean not exactly False
    - any downstream dependency boolean not exactly False
    """
    # --- Read null benchmark JSON bytes ---
    try:
        packet_bytes = Path(null_benchmark_path).read_bytes()
    except FileNotFoundError:
        raise ValueError(
            f"Null benchmark JSON not found: {null_benchmark_path}"
        )
    except OSError as exc:
        raise ValueError(
            f"Null benchmark JSON read error {null_benchmark_path}: {exc}"
        )

    json_sha256 = hashlib.sha256(packet_bytes).hexdigest()

    # --- Parse JSON ---
    try:
        packet: dict = json.loads(packet_bytes)
    except json.JSONDecodeError as exc:
        raise ValueError(
            f"Null benchmark JSON parse error: {exc}"
        )

    if not isinstance(packet, dict):
        raise ValueError(
            "Null benchmark JSON root must be a dict"
        )

    # --- Read sidecar ---
    try:
        sidecar_text = Path(sidecar_path).read_text().strip()
    except FileNotFoundError:
        raise ValueError(
            f"Null benchmark sidecar not found: {sidecar_path}"
        )
    except OSError as exc:
        raise ValueError(
            f"Null benchmark sidecar read error {sidecar_path}: {exc}"
        )

    # Parse sidecar: expected format "<sha256>  <filename>"
    parts = sidecar_text.split(None, 1)
    if not parts or len(parts) != 2:
        raise ValueError(
            f"Null benchmark sidecar format invalid: "
            f"expected '<sha256>  <filename>', got {sidecar_text!r}"
        )
    sidecar_sha256 = parts[0]

    if len(sidecar_sha256) != 64:
        raise ValueError(
            f"Null benchmark sidecar SHA-256 digest length invalid: "
            f"expected 64 hex chars, got {len(sidecar_sha256)}"
        )

    try:
        int(sidecar_sha256, 16)
    except ValueError:
        raise ValueError(
            f"Null benchmark sidecar SHA-256 digest is not valid hex: "
            f"{sidecar_sha256!r}"
        )

    if sidecar_sha256 != json_sha256:
        raise ValueError(
            f"Null benchmark sidecar digest mismatch: "
            f"sidecar={sidecar_sha256}, computed={json_sha256}"
        )

    # --- Check required field presence ---
    _REQUIRED_NULL_BENCHMARK_KEYS: set[str] = {
        "null_benchmark_id",
        "null_benchmark_version",
        "null_benchmark_kind",
        "null_benchmark_status",
        "null_benchmark_hash",
        "null_benchmark_hash_algorithm",
        "null_benchmark_hash_scope",
        "null_benchmark_hash_status",
        "bound_contract_id",
        "bound_contract_sha256",
        "bound_trial_manifest_id",
        "bound_trial_manifest_sha256",
        "bound_oos_seal_id",
        "bound_oos_seal_sha256",
        "required_oos_seal_gate_status",
        "null_reference_policy",
        "null_reference_family",
        "null_reference_selection_frozen",
        "null_reference_count",
        "null_reference_count_frozen",
        *_REQUIRED_FALSE_NULL_BENCHMARK_FIELDS,
    }
    missing_fields = _REQUIRED_NULL_BENCHMARK_KEYS - set(packet.keys())
    if missing_fields:
        raise ValueError(
            f"Null benchmark missing required fields: {sorted(missing_fields)}"
        )

    # --- Check forbidden dict keys (strict, no exemptions) ---
    forbidden_collisions = _find_forbidden_contract_dict_keys(packet)
    if forbidden_collisions:
        collision_repr = ", ".join(
            f"{c['key']!r} at {c['path']}" for c in forbidden_collisions
        )
        raise ValueError(
            f"Null benchmark contains forbidden dict keys: {collision_repr}"
        )

    # --- Verify null benchmark hash fields ---
    if packet.get("null_benchmark_hash") != "FROZEN_IN_SIDECAR":
        raise ValueError(
            f"Null benchmark null_benchmark_hash must be 'FROZEN_IN_SIDECAR', "
            f"got {packet.get('null_benchmark_hash')!r}"
        )
    if packet.get("null_benchmark_hash_status") != "FROZEN_IN_SIDECAR":
        raise ValueError(
            f"Null benchmark null_benchmark_hash_status must be "
            f"'FROZEN_IN_SIDECAR', "
            f"got {packet.get('null_benchmark_hash_status')!r}"
        )
    if packet.get("null_benchmark_hash_algorithm") != "sha256":
        raise ValueError(
            f"Null benchmark null_benchmark_hash_algorithm must be 'sha256', "
            f"got {packet.get('null_benchmark_hash_algorithm')!r}"
        )

    # --- Verify bound contract identity + digest ---
    contract_diag = strategy_rule_contract_diagnostics
    contract_json_sha256 = contract_diag.get("json_sha256")
    contract_id = contract_diag.get("contract_id")
    bound_contract_sha256 = packet.get("bound_contract_sha256")
    bound_contract_id = packet.get("bound_contract_id")

    if bound_contract_sha256 != contract_json_sha256:
        raise ValueError(
            f"Null benchmark bound_contract_sha256 mismatch: "
            f"packet says {bound_contract_sha256}, "
            f"contract diagnostic says {contract_json_sha256}"
        )
    if bound_contract_id != contract_id:
        raise ValueError(
            f"Null benchmark bound_contract_id mismatch: "
            f"packet says {bound_contract_id}, "
            f"contract diagnostic says {contract_id}"
        )

    # --- Verify bound trial manifest identity + digest ---
    tmd = trial_manifest_diagnostics
    manifest_json_sha256 = tmd.get("manifest_json_sha256")
    manifest_id = tmd.get("manifest_id")
    bound_trial_manifest_sha256 = packet.get("bound_trial_manifest_sha256")
    bound_trial_manifest_id = packet.get("bound_trial_manifest_id")

    if bound_trial_manifest_sha256 != manifest_json_sha256:
        raise ValueError(
            f"Null benchmark bound_trial_manifest_sha256 mismatch: "
            f"packet says {bound_trial_manifest_sha256}, "
            f"trial manifest diagnostic says {manifest_json_sha256}"
        )
    if bound_trial_manifest_id != manifest_id:
        raise ValueError(
            f"Null benchmark bound_trial_manifest_id mismatch: "
            f"packet says {bound_trial_manifest_id}, "
            f"trial manifest diagnostic says {manifest_id}"
        )

    # --- Verify OOS seal gate (fail closed before any seal digest trust) ---
    osd = oos_seal_diagnostics
    oos_seal_gate = osd.get("oos_seal_preregistration_gate", {})
    if not isinstance(oos_seal_gate, dict):
        raise ValueError(
            "OOS seal gate is not a dict"
        )
    if not oos_seal_gate.get("gate_passed"):
        raise ValueError(
            "OOS seal gate not passed: "
            "null benchmark pre-registration cannot proceed without the "
            "OOS seal gate"
        )
    oos_seal_gate_status = oos_seal_gate.get("gate_status")
    if oos_seal_gate_status != OOS_SEAL_PREREGISTERED_DIAGNOSTIC_ONLY:
        raise ValueError(
            f"OOS seal gate status must be "
            f"{OOS_SEAL_PREREGISTERED_DIAGNOSTIC_ONLY!r}, "
            f"got {oos_seal_gate_status!r}"
        )
    required_oos_seal_gate_status = packet.get("required_oos_seal_gate_status")
    if required_oos_seal_gate_status != oos_seal_gate_status:
        raise ValueError(
            f"Null benchmark required_oos_seal_gate_status mismatch: "
            f"packet says {required_oos_seal_gate_status!r}, "
            f"OOS seal gate says {oos_seal_gate_status!r}"
        )

    # --- Verify bound OOS seal identity + digest (after gate check) ---
    seal_json_sha256 = osd.get("seal_json_sha256")
    seal_id = osd.get("seal_id")
    bound_oos_seal_sha256 = packet.get("bound_oos_seal_sha256")
    bound_oos_seal_id = packet.get("bound_oos_seal_id")

    if bound_oos_seal_sha256 != seal_json_sha256:
        raise ValueError(
            f"Null benchmark bound_oos_seal_sha256 mismatch: "
            f"packet says {bound_oos_seal_sha256}, "
            f"OOS seal diagnostic says {seal_json_sha256}"
        )
    if bound_oos_seal_id != seal_id:
        raise ValueError(
            f"Null benchmark bound_oos_seal_id mismatch: "
            f"packet says {bound_oos_seal_id}, "
            f"OOS seal diagnostic says {seal_id}"
        )

    # --- Verify null reference policy freeze ---
    if packet.get("null_reference_selection_frozen") is not True:
        raise ValueError(
            f"Null benchmark null_reference_selection_frozen must be True, "
            f"got {packet.get('null_reference_selection_frozen')!r}"
        )
    if packet.get("null_reference_count_frozen") is not True:
        raise ValueError(
            f"Null benchmark null_reference_count_frozen must be True, "
            f"got {packet.get('null_reference_count_frozen')!r}"
        )
    null_reference_count = packet.get("null_reference_count")
    if isinstance(null_reference_count, bool) or not isinstance(
        null_reference_count, int
    ):
        raise ValueError(
            f"Null benchmark null_reference_count must be a JSON integer, "
            f"got {null_reference_count!r}"
        )
    if null_reference_count != 1:
        raise ValueError(
            f"Null benchmark null_reference_count must be exactly 1, "
            f"got {null_reference_count!r}"
        )

    # --- Verify authorization booleans are exactly False ---
    bad_false_fields: dict[str, Any] = {
        field: packet.get(field)
        for field in _REQUIRED_FALSE_NULL_BENCHMARK_FIELDS
        if packet.get(field) is not False
    }
    if bad_false_fields:
        raise ValueError(
            "Null benchmark fields must be exactly false: "
            + ", ".join(
                f"{k}={v!r}" for k, v in bad_false_fields.items()
            )
        )

    return {
        "diagnostic_kind": "null_benchmark_preregistration",
        "null_benchmark_source_path": null_benchmark_path,
        "null_benchmark_sidecar_path": sidecar_path,
        "null_benchmark_id": str(packet.get("null_benchmark_id", "")),
        "null_benchmark_packet_version": str(
            packet.get("null_benchmark_version", "")
        ),
        "null_benchmark_packet_status": str(
            packet.get("null_benchmark_status", "")
        ),
        "null_benchmark_packet_read": True,
        "null_benchmark_json_parse_ok": True,
        "null_benchmark_sidecar_parse_ok": True,
        "null_benchmark_json_sha256": json_sha256,
        "null_benchmark_sidecar_sha256": sidecar_sha256,
        "null_benchmark_sidecar_digest_matches_json_bytes": True,
        "null_benchmark_hash_authority": "SIDECAR",
        "null_benchmark_hash_field_value": "FROZEN_IN_SIDECAR",
        "null_benchmark_hash_status": "FROZEN_IN_SIDECAR",
        "null_benchmark_required_fields_present": True,
        "null_benchmark_forbidden_dict_key_scan_passed": True,
        "bound_contract_id": str(bound_contract_id),
        "bound_contract_sha256": str(bound_contract_sha256),
        "bound_contract_digest_matches": True,
        "bound_trial_manifest_id": str(bound_trial_manifest_id),
        "bound_trial_manifest_sha256": str(bound_trial_manifest_sha256),
        "bound_trial_manifest_digest_matches": True,
        "bound_oos_seal_id": str(bound_oos_seal_id),
        "bound_oos_seal_sha256": str(bound_oos_seal_sha256),
        "bound_oos_seal_digest_matches": True,
        "oos_seal_gate_required": True,
        "oos_seal_gate_passed": True,
        "oos_seal_gate_status": str(oos_seal_gate_status),
        "null_reference_policy": str(packet.get("null_reference_policy", "")),
        "null_reference_family": str(packet.get("null_reference_family", "")),
        "null_reference_selection_frozen": True,
        "null_reference_count": null_reference_count,
        "null_reference_count_frozen": True,
        "null_benchmark_readiness": False,
        "null_generation_authorized": False,
        "candidate_comparison_authorized": False,
        "scoring_authorized": False,
        "null_benchmark_validation_status": (
            NULL_BENCHMARK_PREREGISTERED_DIAGNOSTIC_ONLY
        ),
    }


def _derive_null_benchmark_preregistration_gate(
    diagnostics: dict[str, Any],
) -> dict[str, Any]:
    """Derive a null benchmark pre-registration gate from diagnostics.

    Pure projection — no I/O, no scoring, no null generation, no
    candidate-vs-null comparison. The gate passes only when all of the
    following hold:
    - null benchmark packet read
    - null benchmark sidecar digest matches the JSON bytes
    - strict forbidden-key scan passed
    - bound contract digest matches
    - bound trial manifest digest matches
    - bound OOS seal digest matches
    - OOS seal gate passed
    - null reference policy frozen (selection + count)
    - null reference count is exactly 1
    - all authorization booleans false
    - all downstream dependency booleans false

    A missing / failed OOS seal gate blocks this gate: null benchmark
    pre-registration can never pass without it.
    """
    evidence: dict[str, Any] = {
        "null_benchmark_sidecar_digest_matches_json_bytes": (
            diagnostics.get("null_benchmark_sidecar_digest_matches_json_bytes")
            is True
        ),
        "bound_contract_digest_matches": (
            diagnostics.get("bound_contract_digest_matches") is True
        ),
        "bound_trial_manifest_digest_matches": (
            diagnostics.get("bound_trial_manifest_digest_matches") is True
        ),
        "bound_oos_seal_digest_matches": (
            diagnostics.get("bound_oos_seal_digest_matches") is True
        ),
        "oos_seal_gate_passed": (
            diagnostics.get("oos_seal_gate_passed") is True
        ),
        "null_reference_selection_frozen": (
            diagnostics.get("null_reference_selection_frozen") is True
        ),
        "null_reference_count_frozen": (
            diagnostics.get("null_reference_count_frozen") is True
        ),
        "null_reference_count": diagnostics.get("null_reference_count"),
    }

    evidence_pass = all(
        value is True
        for key, value in evidence.items()
        if key != "null_reference_count"
    ) and evidence["null_reference_count"] == 1

    extra_pass = (
        diagnostics.get("diagnostic_kind")
        == "null_benchmark_preregistration"
        and diagnostics.get("null_benchmark_packet_read") is True
        and diagnostics.get("null_benchmark_json_parse_ok") is True
        and diagnostics.get("null_benchmark_sidecar_parse_ok") is True
        and diagnostics.get("null_benchmark_hash_authority") == "SIDECAR"
        and diagnostics.get("null_benchmark_hash_field_value")
        == "FROZEN_IN_SIDECAR"
        and diagnostics.get("null_benchmark_hash_status") == "FROZEN_IN_SIDECAR"
        and diagnostics.get("null_benchmark_required_fields_present") is True
        and diagnostics.get("null_benchmark_forbidden_dict_key_scan_passed")
        is True
        and diagnostics.get("oos_seal_gate_status")
        == OOS_SEAL_PREREGISTERED_DIAGNOSTIC_ONLY
        and diagnostics.get("null_generation_authorized") is False
        and diagnostics.get("candidate_comparison_authorized") is False
        and diagnostics.get("scoring_authorized") is False
        and diagnostics.get("null_benchmark_readiness") is False
    )

    all_pass = evidence_pass and extra_pass

    if all_pass:
        gate_status = NULL_BENCHMARK_PREREGISTERED_DIAGNOSTIC_ONLY
        blocked_reason = None
    elif diagnostics.get("diagnostic_kind") != "null_benchmark_preregistration":
        gate_status = "NULL_BENCHMARK_NOT_LOADED"
        blocked_reason = "NULL_BENCHMARK_NOT_PROVIDED"
    elif diagnostics.get("oos_seal_gate_passed") is not True:
        gate_status = "BLOCKED_BY_OOS_SEAL_GATE"
        blocked_reason = "OOS_SEAL_GATE_NOT_PASSED"
    else:
        gate_status = "BLOCKED_BY_INCOMPLETE_NULL_BENCHMARK_EVIDENCE"
        blocked_reason = "NULL_BENCHMARK_GATE_EVIDENCE_INCOMPLETE"

    return {
        "gate_kind": "null_benchmark_preregistration_gate",
        "gate_scope": (
            "NULL_REFERENCE_POLICY_AND_OOS_SEAL_BINDING_ONLY"
        ),
        "gate_status": gate_status,
        "gate_passed": all_pass,
        "gate_scoring_authorization": False,
        "gate_live_authorization": False,
        "gate_final_verdict_authorization": False,
        "gate_downstream_unlocks": [],
        "evidence": evidence,
        "blocked_reason": blocked_reason,
    }


def _build_strategy_rule_contract_diagnostics(
    contract_path: str | None = None,
    sidecar_path: str | None = None,
    commit_binding_path: str | None = None,
) -> dict[str, Any]:
    """Build a diagnostic-only section for the strategy rule contract.

    If *contract_path* and *sidecar_path* are both provided and resolve to
    existing files, the frozen contract instance is loaded, hash-checked, and
    audited via :func:`materialize_strategy_rule_contract_instance_diagnostics`.

    When *commit_binding_path* is provided, the materializer additionally
    verifies non-self-referential prior-commit containment of the contract bytes.

    Otherwise a hardcoded ``CONTRACT_NOT_DEFINED`` diagnostic is returned.

    This section does **not** define a strategy, generate signals, or compute
    returns, PnL, Sharpe, drawdown, risk, edge, trades, positions, portfolio
    metrics, or baseline comparisons.

    Raises ``ValueError`` if the contract path is provided but the packet is
    corrupted (delegated to the materializer).
    """
    if contract_path is not None and sidecar_path is not None:
        diagnostics = (
            materialize_strategy_rule_contract_instance_diagnostics(
                contract_path=contract_path,
                sidecar_path=sidecar_path,
                commit_binding_path=commit_binding_path,
            )
        )
    else:
        diagnostics = {
            "contract_version": STRATEGY_RULE_CONTRACT_VERSION,
            "calculation_status": STRATEGY_RULE_CONTRACT_DIAGNOSTIC_ONLY,
            "contract_status": STRATEGY_RULE_CONTRACT_NOT_DEFINED,
            "scoring_authorized": False,
            "scoring_blocked_reason": STRATEGY_RULE_CONTRACT_BLOCKED_REASON_NOT_DEFINED,
            "allowed_input_roles": None,
            "allowed_input_columns": None,
            "forbidden_input_roles": None,
            "forbidden_input_columns": None,
            "forbidden_future_columns": None,
            "decision_time_convention": None,
            "decision_time_column": None,
            "decision_time_offset": None,
            "feature_lookback": None,
            "feature_lookback_bars": None,
            "label_horizon": None,
            "label_horizon_bars": None,
            "holding_period": None,
            "holding_period_bars": None,
            "side_semantics": None,
            "side_source": None,
            "notional_semantics": None,
            "notional_source": None,
            "notional_currency": None,
            "cost_dependency": NOT_DEFINED,
            "funding_dependency": NOT_DEFINED,
            "scoring_prerequisites_present": {
                "decision_time_convention": False,
                "feature_lookback": False,
                "label_horizon": False,
                "holding_period": False,
                "funding_interval_exposure": False,
                "cost_event_timing": False,
            },
        }

    # Derive contract-packet gate from diagnostics (pure, no I/O).
    diagnostics["contract_packet_gate"] = (
        _derive_strategy_rule_contract_packet_gate(diagnostics)
    )
    return diagnostics


def _derive_strategy_rule_contract_packet_gate(
    diagnostics: dict[str, Any],
) -> dict[str, Any]:
    """Derive a narrow contract-packet gate projection from existing diagnostics.

    This is a pure function: it never reads files, never calls git, never
    mutates *diagnostics*, and is fully deterministic. It compresses the
    existing strategy-rule contract diagnostics into a gate object that
    records whether the frozen contract packet is loaded, hash-bound,
    strict-key checked, input/output bounded, dependency-false, and
    commit-bound to a prior containing commit.

    The gate does **not** authorize scoring, strategy execution, PnL, live
    readiness, or final verdict advancement.

    Returns a dict with ``gate_passed``, ``gate_status``, ``evidence``,
    and authorization fields all set to ``False`` / empty / blocked.
    """
    # Detect absence: no diagnostic_kind or contract not defined.
    if diagnostics.get("diagnostic_kind") != "strategy_rule_contract_instance":
        return {
            "gate_kind": "strategy_rule_contract_packet_gate",
            "gate_scope": (
                "CONTRACT_PACKET_EXISTENCE_HASH_AND_COMMIT_BINDING_ONLY"
            ),
            "gate_status": "CONTRACT_PACKET_NOT_LOADED",
            "gate_passed": False,
            "gate_scoring_authorization": False,
            "gate_live_authorization": False,
            "gate_final_verdict_authorization": False,
            "gate_downstream_unlocks": [],
            "evidence": {},
            "blocked_reason": "CONTRACT_PACKET_NOT_LOADED",
        }

    # Check commit binding status.
    contract_commit_sha_bound = diagnostics.get(
        "contract_commit_sha_bound", False
    )
    if not contract_commit_sha_bound:
        return {
            "gate_kind": "strategy_rule_contract_packet_gate",
            "gate_scope": (
                "CONTRACT_PACKET_EXISTENCE_HASH_AND_COMMIT_BINDING_ONLY"
            ),
            "gate_status": "BLOCKED_BY_COMMIT_BINDING_PLACEHOLDER",
            "gate_passed": False,
            "gate_scoring_authorization": False,
            "gate_live_authorization": False,
            "gate_final_verdict_authorization": False,
            "gate_downstream_unlocks": [],
            "evidence": {
                "contract_packet_read": diagnostics.get(
                    "contract_packet_read", False
                ),
                "sidecar_digest_matches_json_bytes": diagnostics.get(
                    "sidecar_digest_matches_json_bytes", False
                ),
                "contract_commit_sha_bound": False,
            },
            "blocked_reason": "CONTRACT_COMMIT_BINDING_NOT_VERIFIED",
        }

    # Full pass criteria — all must be true/exact for gate_passed = True.
    evidence: dict[str, Any] = {
        "contract_packet_read": (
            diagnostics.get("contract_packet_read") is True
        ),
        "sidecar_digest_matches_json_bytes": (
            diagnostics.get("sidecar_digest_matches_json_bytes") is True
        ),
        "forbidden_dict_key_scan_passed": (
            diagnostics.get("forbidden_dict_key_scan_passed") is True
        ),
        "input_ceiling_check_passed": (
            diagnostics.get("input_ceiling_check_passed") is True
        ),
        "output_boundary_fields_present": (
            diagnostics.get("output_boundary_fields_present") is True
        ),
        "downstream_dependency_booleans_all_false": (
            diagnostics.get("downstream_dependency_booleans_all_false") is True
        ),
        "contract_commit_sha_bound": (
            diagnostics.get("contract_commit_sha_bound") is True
        ),
        "contract_commit_sha_binding_status": (
            diagnostics.get("contract_commit_sha_binding_status")
            == "BOUND_BY_PRIOR_COMMIT_CONTAINMENT_SIDECAR"
        ),
        "contract_containing_commit_digest_matches": (
            diagnostics.get("contract_containing_commit_digest_matches")
            is True
        ),
    }

    # Additional checks not included in evidence dict.
    extra_pass = (
        diagnostics.get("diagnostic_kind")
        == "strategy_rule_contract_instance"
        and diagnostics.get("json_parse_ok") is True
        and diagnostics.get("sidecar_parse_ok") is True
        and diagnostics.get("contract_hash_authority") == "SIDECAR"
        and diagnostics.get("contract_hash_field_value") == "FROZEN_IN_SIDECAR"
        and diagnostics.get("contract_hash_status") == "FROZEN_IN_SIDECAR"
        and diagnostics.get("required_fields_present") is True
        and diagnostics.get("scoring_authorization") is False
        and diagnostics.get("live_integration_authorized") is False
        and diagnostics.get("contract_containing_commit_path_verified")
        is True
        and diagnostics.get("contract_instance_readiness") is False
        and diagnostics.get("contract_scoring_ready") is False
    )

    all_pass = all(evidence.values()) and extra_pass

    if all_pass:
        gate_status = "CONTRACT_PACKET_COMMIT_BOUND_DIAGNOSTIC_ONLY"
        blocked_reason = None
    else:
        gate_status = "BLOCKED_BY_INCOMPLETE_EVIDENCE"
        blocked_reason = "CONTRACT_PACKET_GATE_EVIDENCE_INCOMPLETE"

    return {
        "gate_kind": "strategy_rule_contract_packet_gate",
        "gate_scope": (
            "CONTRACT_PACKET_EXISTENCE_HASH_AND_COMMIT_BINDING_ONLY"
        ),
        "gate_status": gate_status,
        "gate_passed": all_pass,
        "gate_scoring_authorization": False,
        "gate_live_authorization": False,
        "gate_final_verdict_authorization": False,
        "gate_downstream_unlocks": [],
        "evidence": evidence,
        "blocked_reason": blocked_reason,
    }


def _build_trial_manifest_diagnostics(
    *,
    manifest_path: str | None = None,
    sidecar_path: str | None = None,
    strategy_rule_contract_diagnostics: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Build a diagnostic-only section for the trial manifest.

    If *manifest_path* and *sidecar_path* are both provided and
    *strategy_rule_contract_diagnostics* is provided with a passing
    contract packet gate, the frozen trial manifest pre-registration
    packet is loaded, hash-checked, and audited via
    :func:`materialize_trial_manifest_preregistration_diagnostics`.

    Otherwise a hardcoded ``TRIAL_MANIFEST_NOT_DEFINED`` diagnostic is
    returned with a failing gate.

    This section does **not** define a trial manifest, count trials,
    register candidates, search for parameters, or compute any scoring
    metric. Every trial-manifest field is either ``None``, ``NOT_DEFINED``,
    or ``False`` — this is a diagnostic of absence, not a definition.

    Fail-closed rules:
    * ``scoring_authorized`` is always ``False`` at this stage.
    * ``trial_manifest_status`` is always ``TRIAL_MANIFEST_NOT_DEFINED``
      when no manifest is loaded.
    * ``scoring_blocked_reason`` is always ``TRIAL_MANIFEST_NOT_DEFINED``.
    * All ``trial_manifest_prerequisites_present`` values are always ``False``.

    Raises ``ValueError`` if manifest paths are provided but the packet is
    corrupted (delegated to the materializer).
    """
    if (
        manifest_path is not None
        and sidecar_path is not None
        and strategy_rule_contract_diagnostics is not None
    ):
        diagnostics = (
            materialize_trial_manifest_preregistration_diagnostics(
                manifest_path=manifest_path,
                sidecar_path=sidecar_path,
                strategy_rule_contract_diagnostics=(
                    strategy_rule_contract_diagnostics
                ),
            )
        )
    else:
        diagnostics = {
            "manifest_version": TRIAL_MANIFEST_VERSION,
            "calculation_status": TRIAL_MANIFEST_DIAGNOSTIC_ONLY,
            "trial_manifest_status": TRIAL_MANIFEST_NOT_DEFINED,
            "trial_manifest_present": False,
            "manifest_id": None,
            "manifest_status": None,
            "trial_manifest_hash": None,
            "trial_manifest_source": None,
            "scoring_authorized": False,
            "scoring_blocked_reason": TRIAL_MANIFEST_BLOCKED_REASON_NOT_DEFINED,
            "trial_count_known": False,
            "trial_count": None,
            "candidate_count_known": False,
            "candidate_count": None,
            "rejected_trial_count_known": False,
            "rejected_trial_count": None,
            "strategy_candidate_id": None,
            "hypothesis_id": None,
            "parameter_search_space_defined": False,
            "parameter_search_space_hash": None,
            "llm_generated_trials_recorded": False,
            "human_generated_trials_recorded": False,
            "manual_rejected_trials_recorded": False,
            "symbol_universe_frozen": False,
            "split_policy_frozen": False,
            "oos_seal_present": False,
            "null_benchmark_contract_present": False,
            "multiple_testing_policy_present": False,
            "trial_manifest_prerequisites_present": {
                "strategy_rule_contract": False,
                "split_scoring_safe": False,
                "trial_count": False,
                "candidate_registry": False,
                "parameter_search_space": False,
                "symbol_universe_freeze": False,
                "split_policy_freeze": False,
                "oos_seal": False,
                "null_benchmark_contract": False,
                "multiple_testing_policy": False,
            },
        }

    # Derive trial-manifest pre-registration gate from diagnostics (pure, no I/O).
    diagnostics["trial_manifest_preregistration_gate"] = (
        _derive_trial_manifest_preregistration_gate(diagnostics)
    )
    return diagnostics


def _build_oos_seal_diagnostics(
    *,
    seal_path: str | None = None,
    sidecar_path: str | None = None,
    trial_manifest_diagnostics: dict[str, Any] | None = None,
    strategy_rule_contract_diagnostics: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Build a diagnostic-only section for the OOS seal.

    If *seal_path*, *sidecar_path*, *trial_manifest_diagnostics*, and
    *strategy_rule_contract_diagnostics* are all provided, the frozen OOS
    seal pre-scoring declaration packet is loaded, hash-checked, and audited
    via :func:`materialize_oos_seal_preregistration_diagnostics`.

    Otherwise a hardcoded ``OOS_SEAL_NOT_DEFINED`` diagnostic is returned
    with a failing gate.

    This section does **not** define an OOS period, choose dates, choose
    splits, hash data, freeze the symbol universe, score anything, inspect
    performance, compare variants, or authorize scoring. Every seal field is
    either ``None``, ``False``, or ``NOT_DEFINED`` — this is a diagnostic of
    absence, not a definition of presence.

    Raises ``ValueError`` if seal paths are provided but the packet is
    corrupted (delegated to the materializer).
    """
    if (
        seal_path is not None
        and sidecar_path is not None
        and trial_manifest_diagnostics is not None
        and strategy_rule_contract_diagnostics is not None
    ):
        diagnostics = (
            materialize_oos_seal_preregistration_diagnostics(
                seal_path=seal_path,
                sidecar_path=sidecar_path,
                trial_manifest_diagnostics=trial_manifest_diagnostics,
                strategy_rule_contract_diagnostics=(
                    strategy_rule_contract_diagnostics
                ),
            )
        )
    else:
        diagnostics = {
            "seal_version": OOS_SEAL_VERSION,
            "calculation_status": OOS_SEAL_DIAGNOSTIC_ONLY,
            "oos_seal_status": OOS_SEAL_NOT_DEFINED,
            "oos_seal_present": False,
            "oos_seal_hash": None,
            "oos_seal_source": None,
            "scoring_authorized": False,
            "scoring_blocked_reason": OOS_SEAL_BLOCKED_REASON_NOT_DEFINED,
            "oos_split_id": None,
            "oos_period_start": None,
            "oos_period_end": None,
            "oos_period_frozen": False,
            "oos_symbol_universe_frozen": False,
            "oos_symbol_universe_hash": None,
            "oos_data_hash_present": False,
            "oos_data_hash": None,
            "sealed_before_scoring": False,
            "seal_timestamp_utc": None,
            "seal_commit_sha": None,
            "holdout_access_policy_defined": False,
            "holdout_access_policy": "NOT_DEFINED",
            "strategy_rule_contract_dependency_satisfied": False,
            "trial_manifest_dependency_satisfied": False,
            "split_scoring_safe_dependency_satisfied": False,
            "null_benchmark_contract_present": False,
            "multiple_testing_policy_present": False,
            "oos_seal_prerequisites_present": {
                "strategy_rule_contract": False,
                "trial_manifest": False,
                "trial_count": False,
                "candidate_registry": False,
                "symbol_universe_freeze": False,
                "split_policy_freeze": False,
                "holdout_access_policy": False,
                "oos_period": False,
                "oos_data_hash": False,
                "null_benchmark_contract": False,
                "multiple_testing_policy": False,
            },
        }

    # Derive OOS seal pre-registration gate from diagnostics (pure, no I/O).
    diagnostics["oos_seal_preregistration_gate"] = (
        _derive_oos_seal_preregistration_gate(diagnostics)
    )
    return diagnostics


def _build_null_benchmark_contract_diagnostics(
    *,
    null_benchmark_path: str | None = None,
    sidecar_path: str | None = None,
    oos_seal_diagnostics: dict[str, Any] | None = None,
    trial_manifest_diagnostics: dict[str, Any] | None = None,
    strategy_rule_contract_diagnostics: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Build a diagnostic-only section for the null benchmark.

    If *null_benchmark_path*, *sidecar_path*, *oos_seal_diagnostics*,
    *trial_manifest_diagnostics*, and *strategy_rule_contract_diagnostics* are
    all provided, the frozen null benchmark pre-scoring declaration packet is
    loaded, hash-checked, and audited via
    :func:`materialize_null_benchmark_preregistration_diagnostics`.

    Otherwise a hardcoded ``NULL_BENCHMARK_CONTRACT_NOT_DEFINED`` diagnostic is
    returned with a failing gate.

    This section does **not** define a benchmark, choose a baseline, generate a
    null reference, compute returns, compare a candidate against a null, score
    anything, or authorize scoring. Loading the packet only records that a
    reference policy was declared and hash-bound *before* any outcome math
    exists.

    Fail-closed rules:
    * ``scoring_authorized`` is always ``False`` at this stage.
    * ``null_generation_authorized`` /  ``candidate_comparison_authorized``
      are always ``False`` at this stage.
    * A missing or failed OOS seal gate blocks the null benchmark gate.

    Raises ``ValueError`` if null benchmark paths are provided but the packet is
    corrupted or its prerequisites are unmet (delegated to the materializer).
    """
    if (
        null_benchmark_path is not None
        and sidecar_path is not None
        and oos_seal_diagnostics is not None
        and trial_manifest_diagnostics is not None
        and strategy_rule_contract_diagnostics is not None
    ):
        diagnostics = (
            materialize_null_benchmark_preregistration_diagnostics(
                null_benchmark_path=null_benchmark_path,
                sidecar_path=sidecar_path,
                oos_seal_diagnostics=oos_seal_diagnostics,
                trial_manifest_diagnostics=trial_manifest_diagnostics,
                strategy_rule_contract_diagnostics=(
                    strategy_rule_contract_diagnostics
                ),
            )
        )
    else:
        diagnostics = _null_benchmark_contract_absence_diagnostics()

    # Derive null benchmark pre-registration gate from diagnostics (pure, no I/O).
    diagnostics["null_benchmark_preregistration_gate"] = (
        _derive_null_benchmark_preregistration_gate(diagnostics)
    )
    return diagnostics


def _null_benchmark_contract_absence_diagnostics() -> dict[str, Any]:
    """Diagnostic-only section recording that no null benchmark contract is
    loaded and therefore scoring is blocked.

    Every contract field is either ``None``, ``NOT_DEFINED``, or ``False`` —
    this is a diagnostic of absence, not a definition of presence.
    """
    return {
        "contract_version": NULL_BENCHMARK_CONTRACT_VERSION,
        "calculation_status": NULL_BENCHMARK_CONTRACT_DIAGNOSTIC_ONLY,
        "null_benchmark_contract_status": NULL_BENCHMARK_CONTRACT_NOT_DEFINED,
        "null_benchmark_contract_present": False,
        "null_benchmark_contract_hash": None,
        "null_benchmark_contract_source": None,
        "scoring_authorized": False,
        "scoring_blocked_reason": NULL_BENCHMARK_CONTRACT_BLOCKED_REASON_NOT_DEFINED,
        "benchmark_family_defined": False,
        "benchmark_family": NOT_DEFINED,
        "benchmark_generation_policy_defined": False,
        "benchmark_generation_policy": NOT_DEFINED,
        "random_seed_policy_defined": False,
        "random_seed_policy": NOT_DEFINED,
        "shuffle_policy_defined": False,
        "shuffle_policy": NOT_DEFINED,
        "permutation_policy_defined": False,
        "permutation_policy": NOT_DEFINED,
        "cost_inclusion_policy_defined": False,
        "cost_inclusion_policy": NOT_DEFINED,
        "funding_inclusion_policy_defined": False,
        "funding_inclusion_policy": NOT_DEFINED,
        "oos_application_policy_defined": False,
        "oos_application_policy": NOT_DEFINED,
        "strategy_rule_contract_dependency_satisfied": False,
        "trial_manifest_dependency_satisfied": False,
        "oos_seal_dependency_satisfied": False,
        "split_scoring_safe_dependency_satisfied": False,
        "multiple_testing_policy_present": False,
        "null_benchmark_contract_prerequisites_present": {
            "strategy_rule_contract": False,
            "trial_manifest": False,
            "oos_seal": False,
            "split_scoring_safe": False,
            "benchmark_family": False,
            "benchmark_generation_policy": False,
            "random_seed_policy": False,
            "shuffle_policy": False,
            "permutation_policy": False,
            "cost_inclusion_policy": False,
            "funding_inclusion_policy": False,
            "oos_application_policy": False,
            "multiple_testing_policy": False,
            },
    }


def _build_multiple_testing_control_diagnostics() -> dict[str, Any]:
    """Build a diagnostic-only section recording that no multiple-testing
    control exists yet, no trial-adjustment policy exists, no
    DSR/PBO/CSCV/SPA/Reality Check/FDR control exists, no
    model/parameter-selection lock exists, and scoring remains unauthorized.

    This section does **not** implement any multiple-testing control, compute
    p-values, define thresholds, calculate confidence intervals, define
    statistical decision rules, scores, metrics, performance fields, or
    profit fields. It does not choose a benchmark, define a benchmark family,
    define a random seed/shuffle/permutation policy, define OOS dates or
    split selection, nor compute returns, PnL, Sharpe, drawdown, risk, edge,
    portfolio, baseline result, benchmark result, or benchmark comparison.

    Fail-closed rules:
    * ``multiple_testing_control_status`` is always
      ``MULTIPLE_TESTING_CONTROL_NOT_DEFINED``.
    * ``scoring_authorized`` is always ``False`` at this stage.
    * ``scoring_blocked_reason`` is always
      ``MULTIPLE_TESTING_CONTROL_NOT_DEFINED``.
    * All ``multiple_testing_control_prerequisites_present`` values are always
      ``False``.
    * All control-policy fields are always ``NOT_DEFINED``.
    """
    return {
        "control_version": MULTIPLE_TESTING_CONTROL_VERSION,
        "calculation_status": MULTIPLE_TESTING_CONTROL_DIAGNOSTIC_ONLY,
        "multiple_testing_control_status": MULTIPLE_TESTING_CONTROL_NOT_DEFINED,
        "multiple_testing_control_present": False,
        "multiple_testing_control_hash": None,
        "multiple_testing_control_source": None,

        "scoring_authorized": False,
        "scoring_blocked_reason": MULTIPLE_TESTING_CONTROL_BLOCKED_REASON_NOT_DEFINED,

        "trial_adjustment_policy_defined": False,
        "trial_adjustment_policy": NOT_DEFINED,
        "rejected_trial_accounting_policy_defined": False,
        "rejected_trial_accounting_policy": NOT_DEFINED,
        "family_definition_policy_defined": False,
        "family_definition_policy": NOT_DEFINED,

        "dsr_control_defined": False,
        "dsr_control_policy": NOT_DEFINED,
        "pbo_control_defined": False,
        "pbo_control_policy": NOT_DEFINED,
        "cscv_control_defined": False,
        "cscv_control_policy": NOT_DEFINED,
        "spa_control_defined": False,
        "spa_control_policy": NOT_DEFINED,
        "reality_check_control_defined": False,
        "reality_check_control_policy": NOT_DEFINED,
        "false_discovery_control_defined": False,
        "false_discovery_control_policy": NOT_DEFINED,

        "model_selection_lock_defined": False,
        "model_selection_lock": NOT_DEFINED,
        "parameter_selection_lock_defined": False,
        "parameter_selection_lock": NOT_DEFINED,

        "strategy_rule_contract_dependency_satisfied": False,
        "trial_manifest_dependency_satisfied": False,
        "oos_seal_dependency_satisfied": False,
        "null_benchmark_contract_dependency_satisfied": False,
        "split_scoring_safe_dependency_satisfied": False,

        "multiple_testing_control_prerequisites_present": {
            "strategy_rule_contract": False,
            "trial_manifest": False,
            "trial_count": False,
            "rejected_trial_accounting": False,
            "candidate_registry": False,
            "oos_seal": False,
            "null_benchmark_contract": False,
            "split_scoring_safe": False,
            "trial_adjustment_policy": False,
            "family_definition_policy": False,
            "dsr_control": False,
            "pbo_control": False,
            "cscv_control": False,
            "spa_control": False,
            "reality_check_control": False,
            "false_discovery_control": False,
            "model_selection_lock": False,
            "parameter_selection_lock": False,
        },
    }

def _build_trade_position_simulation_contract_diagnostics() -> dict[str, Any]:
    """Build a diagnostic-only section recording that no trade/position
    simulation contract exists yet, no simulator policies are defined, and
    simulation-based scoring remains unauthorized.

    This section does **not** implement a simulator, generate signals,
    implement trades/positions/orders/fills/execution, or compute
    returns/PnL/Sharpe/drawdown/risk/edge/portfolio values. It does not
    define fees, slippage, fill model, side policy, sizing values, entry
    rules, exit rules, benchmark family, OOS dates, random seed, shuffle
    policy, or permutation policy.

    Fail-closed rules:
    * ``trade_position_simulation_contract_status`` is always
      ``TRADE_POSITION_SIMULATION_CONTRACT_NOT_DEFINED``.
    * ``trade_position_simulation_contract_present`` is always ``False``.
    * ``scoring_authorized`` is always ``False`` at this stage.
    * ``scoring_blocked_reason`` is always
      ``TRADE_POSITION_SIMULATION_CONTRACT_NOT_DEFINED``.
    * All ``trade_position_simulation_contract_prerequisites_present`` values
      are always ``False``.
    * All policy fields are always ``NOT_DEFINED``.
    """
    return {
        "contract_version": TRADE_POSITION_SIMULATION_CONTRACT_VERSION,
        "calculation_status": TRADE_POSITION_SIMULATION_CONTRACT_DIAGNOSTIC_ONLY,
        "trade_position_simulation_contract_status": (
            TRADE_POSITION_SIMULATION_CONTRACT_NOT_DEFINED
        ),
        "trade_position_simulation_contract_present": False,
        "trade_position_simulation_contract_hash": None,
        "trade_position_simulation_contract_source": None,

        "scoring_authorized": False,
        "scoring_blocked_reason": (
            TRADE_POSITION_SIMULATION_CONTRACT_BLOCKED_REASON_NOT_DEFINED
        ),

        "decision_timestamp_policy_defined": False,
        "decision_timestamp_policy": NOT_DEFINED,
        "order_timing_policy_defined": False,
        "order_timing_policy": NOT_DEFINED,
        "fill_policy_defined": False,
        "fill_policy": NOT_DEFINED,
        "slippage_policy_defined": False,
        "slippage_policy": NOT_DEFINED,
        "fee_application_policy_defined": False,
        "fee_application_policy": NOT_DEFINED,
        "funding_application_dependency_satisfied": False,

        "side_policy_defined": False,
        "side_policy": NOT_DEFINED,
        "notional_sizing_policy_defined": False,
        "notional_sizing_policy": NOT_DEFINED,
        "entry_lifecycle_policy_defined": False,
        "entry_lifecycle_policy": NOT_DEFINED,
        "exit_lifecycle_policy_defined": False,
        "exit_lifecycle_policy": NOT_DEFINED,
        "holding_period_policy_defined": False,
        "holding_period_policy": NOT_DEFINED,
        "state_transition_policy_defined": False,
        "state_transition_policy": NOT_DEFINED,
        "concurrent_symbol_policy_defined": False,
        "concurrent_symbol_policy": NOT_DEFINED,
        "portfolio_accounting_policy_defined": False,
        "portfolio_accounting_policy": NOT_DEFINED,
        "invalid_state_policy_defined": False,
        "invalid_state_policy": NOT_DEFINED,
        "missing_data_policy_defined": False,
        "missing_data_policy": NOT_DEFINED,

        "strategy_rule_contract_dependency_satisfied": False,
        "trial_manifest_dependency_satisfied": False,
        "oos_seal_dependency_satisfied": False,
        "null_benchmark_contract_dependency_satisfied": False,
        "multiple_testing_control_dependency_satisfied": False,
        "split_scoring_safe_dependency_satisfied": False,

        "trade_position_simulation_contract_prerequisites_present": {
            "strategy_rule_contract": False,
            "trial_manifest": False,
            "oos_seal": False,
            "null_benchmark_contract": False,
            "multiple_testing_control": False,
            "split_scoring_safe": False,
            "decision_timestamp_policy": False,
            "order_timing_policy": False,
            "fill_policy": False,
            "slippage_policy": False,
            "fee_application_policy": False,
            "funding_application_policy": False,
            "side_policy": False,
            "notional_sizing_policy": False,
            "entry_lifecycle_policy": False,
            "exit_lifecycle_policy": False,
            "holding_period_policy": False,
            "state_transition_policy": False,
            "concurrent_symbol_policy": False,
            "portfolio_accounting_policy": False,
            "invalid_state_policy": False,
            "missing_data_policy": False,
        },
    }


def _build_net_pnl_equity_risk_contract_diagnostics() -> dict[str, Any]:
    """Build a diagnostic-only section recording that no net PnL/equity/risk
    contract exists yet, no accounting/risk policies are defined, and scoring
    remains unauthorized.

    This section does **not** define a capital base, accounting policy, equity
    curve policy, drawdown policy, risk measure, or any computed metric. It
    does not compute PnL, returns, equity curves, drawdown, risk, Sharpe,
    volatility, exposure, benchmark comparison, edge, score, performance,
    profit, trades, positions, orders, fills, signals, or strategy outputs.
    Every field is either ``None``, ``NOT_DEFINED``, or ``False`` — this is a
    diagnostic of absence, not a definition of presence.

    Fail-closed rules:
    * ``net_pnl_equity_risk_contract_status`` is always
      ``NET_PNL_EQUITY_RISK_CONTRACT_NOT_DEFINED``.
    * ``net_pnl_equity_risk_contract_present`` is always ``False``.
    * ``scoring_authorized`` is always ``False`` at this stage.
    * ``scoring_blocked_reason`` is always
      ``NET_PNL_EQUITY_RISK_CONTRACT_NOT_DEFINED``.
    * All ``net_pnl_equity_risk_contract_prerequisites_present`` values are
      always ``False``.
    * All policy fields are always ``NOT_DEFINED``.
    """
    return {
        "contract_version": NET_PNL_EQUITY_RISK_CONTRACT_VERSION,
        "calculation_status": NET_PNL_EQUITY_RISK_CONTRACT_DIAGNOSTIC_ONLY,
        "net_pnl_equity_risk_contract_status": (
            NET_PNL_EQUITY_RISK_CONTRACT_NOT_DEFINED
        ),
        "net_pnl_equity_risk_contract_present": False,
        "net_pnl_equity_risk_contract_hash": None,
        "net_pnl_equity_risk_contract_source": None,

        "scoring_authorized": False,
        "scoring_blocked_reason": (
            NET_PNL_EQUITY_RISK_CONTRACT_BLOCKED_REASON_NOT_DEFINED
        ),

        "capital_base_policy_defined": False,
        "capital_base_policy": NOT_DEFINED,
        "net_accounting_policy_defined": False,
        "net_accounting_policy": NOT_DEFINED,
        "realized_unrealized_policy_defined": False,
        "realized_unrealized_policy": NOT_DEFINED,
        "cost_inclusion_dependency_satisfied": False,
        "funding_inclusion_dependency_satisfied": False,
        "simulator_dependency_satisfied": False,

        "mark_to_market_policy_defined": False,
        "mark_to_market_policy": NOT_DEFINED,
        "equity_curve_policy_defined": False,
        "equity_curve_policy": NOT_DEFINED,
        "aggregation_policy_defined": False,
        "aggregation_policy": NOT_DEFINED,
        "drawdown_policy_defined": False,
        "drawdown_policy": NOT_DEFINED,
        "exposure_policy_defined": False,
        "exposure_policy": NOT_DEFINED,
        "risk_measure_policy_defined": False,
        "risk_measure_policy": NOT_DEFINED,

        "benchmark_comparison_dependency_satisfied": False,
        "final_verdict_scoring_dependency_satisfied": False,

        "strategy_rule_contract_dependency_satisfied": False,
        "trial_manifest_dependency_satisfied": False,
        "oos_seal_dependency_satisfied": False,
        "null_benchmark_contract_dependency_satisfied": False,
        "multiple_testing_control_dependency_satisfied": False,
        "trade_position_simulation_contract_dependency_satisfied": False,
        "split_scoring_safe_dependency_satisfied": False,

        "net_pnl_equity_risk_contract_prerequisites_present": {
            "strategy_rule_contract": False,
            "trial_manifest": False,
            "oos_seal": False,
            "null_benchmark_contract": False,
            "multiple_testing_control": False,
            "trade_position_simulation_contract": False,
            "split_scoring_safe": False,
            "capital_base_policy": False,
            "net_accounting_policy": False,
            "realized_unrealized_policy": False,
            "cost_inclusion_policy": False,
            "funding_inclusion_policy": False,
            "mark_to_market_policy": False,
            "equity_curve_policy": False,
            "aggregation_policy": False,
            "drawdown_policy": False,
            "exposure_policy": False,
            "risk_measure_policy": False,
            "benchmark_comparison_policy": False,
            "final_verdict_scoring_policy": False,
        },
    }


def _build_final_offline_edge_verdict_logic_diagnostics() -> dict[str, Any]:
    """Build a diagnostic-only section recording that final offline-edge
    scoring and verdict advancement remain blocked because every decisive
    upstream gate is still NOT_DEFINED or unsafe.

    This is a **static absence record**. It performs no I/O, reads no sibling
    receipt section, derives no readiness dynamically, and computes nothing —
    it returns a constant dict. It does not score, does not compare against a
    benchmark, and does not advance ``final_offline_verdict``. It implements
    no strategy, signals, trades, positions, orders, fills, execution,
    returns, PnL, equity, drawdown, risk, or edge.

    Fail-closed rules:
    * ``final_verdict_logic_status`` is always
      ``FINAL_OFFLINE_EDGE_VERDICT_LOGIC_BLOCKED``.
    * Every ``*_authorized`` flag is always ``False``.
    * ``current_final_offline_verdict`` and ``next_final_offline_verdict`` are
      both always ``BLOCKED_BY_VALIDATION_IMPLEMENTATION`` — this section can
      never advance the verdict.
    * All ``required_upstream_gates`` values are NOT_DEFINED / not-safe markers.
    * All ``final_verdict_prerequisites_present`` values are always ``False``.
    """
    return {
        "logic_version": FINAL_OFFLINE_EDGE_VERDICT_LOGIC_VERSION,
        "calculation_status": FINAL_OFFLINE_EDGE_VERDICT_LOGIC_DIAGNOSTIC_ONLY,
        "final_verdict_logic_status": FINAL_OFFLINE_EDGE_VERDICT_LOGIC_BLOCKED,

        "final_scoring_authorized": False,
        "final_verdict_advancement_authorized": False,
        "edge_candidate_authorized": False,
        "live_integration_authorized": False,
        "report_promotion_authorized": False,

        "current_final_offline_verdict": BLOCKED_BY_VALIDATION_IMPLEMENTATION,
        "next_final_offline_verdict": BLOCKED_BY_VALIDATION_IMPLEMENTATION,
        "final_verdict_advancement_blocked_reason": (
            FINAL_VERDICT_ADVANCEMENT_BLOCKED_REASON
        ),
        "upstream_reduction_mode": UPSTREAM_REDUCTION_MODE_STATIC,

        "required_upstream_gates": {
            "strategy_rule_contract": STRATEGY_RULE_CONTRACT_NOT_DEFINED,
            "trial_manifest": TRIAL_MANIFEST_NOT_DEFINED,
            "oos_seal": OOS_SEAL_NOT_DEFINED,
            "null_benchmark_contract": NULL_BENCHMARK_CONTRACT_NOT_DEFINED,
            "multiple_testing_control": MULTIPLE_TESTING_CONTROL_NOT_DEFINED,
            "trade_position_simulation_contract": (
                TRADE_POSITION_SIMULATION_CONTRACT_NOT_DEFINED
            ),
            "net_pnl_equity_risk_contract": NET_PNL_EQUITY_RISK_CONTRACT_NOT_DEFINED,
            "split_scoring_safe": FINAL_VERDICT_SPLIT_SCORING_NOT_SAFE,
        },

        "final_verdict_prerequisites_present": {
            "strategy_rule_contract": False,
            "trial_manifest": False,
            "oos_seal": False,
            "split_scoring_safe": False,
            "null_benchmark_contract": False,
            "multiple_testing_control": False,
            "trade_position_simulation_contract": False,
            "net_pnl_equity_risk_contract": False,
            "final_scoring_policy": False,
            "edge_candidate_policy": False,
            "report_promotion_policy": False,
            "live_integration_policy": False,
        },
    }


# ── Receipt builder ──────────────────────────────────────────────────────


def _default_rationale(output_status: str) -> str:
    if output_status == BLOCKED_BY_VALIDATION_IMPLEMENTATION:
        return (
            "BLOCKED_BY_VALIDATION_IMPLEMENTATION: this is a schema/skeleton-only "
            "receipt. Gross observational close-to-close metadata may be present, "
            "but no strategy returns, PnL, Sharpe, or paper-engine calculation has "
            "been implemented. No edge/profit/live-readiness claim is made."
        )
    return f"{output_status}: skeleton receipt, no calculation implemented."


def build_real_validation_receipt(
    *,
    input_manifest_fingerprint: str,
    data_quality_receipt_sha256: str,
    code_commit_sha: str,
    split_definitions: list[dict[str, Any]],
    cost_cases: list[dict[str, Any]],
    output_status: str = BLOCKED_BY_VALIDATION_IMPLEMENTATION,
    rationale: str | None = None,
    input_inventory: dict[str, Any] | None = None,
    row_materialization: dict | None = None,
    gross_observational_returns: dict | None = None,
    cost_case_observational_drag: dict | None = None,
    funding_observational_adjustments: dict | None = None,
    funding_to_bars_alignment_diagnostics: dict | None = None,
    funding_to_bars_temporal_joinability_diagnostics: dict | None = None,
    funding_to_bars_timestamp_convention_diagnostics: dict | None = None,
    funding_to_bars_timestamp_canonicalization_diagnostics: dict | None = None,
    funding_application_readiness_gate_diagnostics: dict | None = None,
    funding_adjusted_bars_scaffold_diagnostics: dict | None = None,
    funding_adjustment_policy_contract_diagnostics: dict | None = None,
    funding_adjustment_arithmetic_scaffold_diagnostics: dict | None = None,
    funding_adjustment_row_scaffold_diagnostics: dict | None = None,
    funding_adjustment_sample_aggregate_diagnostics: dict | None = None,
    split_leakage_audit_diagnostics: dict | None = None,
    strategy_rule_contract_diagnostics: dict | None = None,
    trial_manifest_diagnostics: dict | None = None,
    oos_seal_diagnostics: dict | None = None,
    null_benchmark_contract_diagnostics: dict | None = None,
    multiple_testing_control_diagnostics: dict | None = None,
    trade_position_simulation_contract_diagnostics: dict | None = None,
    net_pnl_equity_risk_contract_diagnostics: dict | None = None,
    final_offline_edge_verdict_logic_diagnostics: dict | None = None,
) -> dict[str, Any]:
    """Build the real offline validation receipt skeleton.

    This is a pure function: it performs no I/O, computes no PnL/Sharpe, and
    does not run any engine. ``output_status`` defaults to and
    (in this PR) must remain ``BLOCKED_BY_VALIDATION_IMPLEMENTATION`` —
    ``OFFLINE_EDGE_CANDIDATE`` is rejected by ``validate_real_validation_receipt``
    at this phase.

    If *input_inventory* is provided, it is included in the receipt under
    the ``input_inventory`` key, and *split_definitions* is overridden with
    definitions derived from the inventory via
    ``materialize_split_definitions_from_inventory``.
    """
    if rationale is None:
        rationale = _default_rationale(output_status)

    # If input_inventory is provided, derive split_definitions from it.
    effective_split_definitions = split_definitions
    if input_inventory is not None:
        effective_split_definitions = materialize_split_definitions_from_inventory(
            inventory=input_inventory,
            split_count=len(split_definitions) if split_definitions else 3,
        )

    receipt: dict[str, Any] = {
        "validation_receipt": {
            "kind": RECEIPT_SCHEMA_KIND,
            "version": RECEIPT_SCHEMA_VERSION,
            "timestamp_utc": datetime.now(timezone.utc).isoformat(),
        },
        "input_manifest_fingerprint": input_manifest_fingerprint,
        "data_quality_receipt_sha256": data_quality_receipt_sha256,
        "code_commit_sha": code_commit_sha,
        "split_definitions": effective_split_definitions,
        "cost_cases": cost_cases,
        "required_outputs_present": {
            "gross_return": False,
            "net_return_after_costs": False,
            "max_drawdown": False,
            "sharpe_or_risk_metric": False,
            "baseline_comparison": False,
            "sensitivity_cases": False,
        },
        "forbidden_calculation_status": {
            "returns_computed": False,
            "pnl_computed": False,
            "sharpe_computed": False,
            "paper_engine_run": False,
            "live_integration_used": False,
        },
        "guardrail_status": {
            "edge_unproven": True,
            "block_live_integration": True,
            "no_report_promotion": True,
            "output_under_tmp_only": True,
        },
        "final_offline_verdict": output_status,
        "final_offline_verdict_rationale": rationale,
    }

    if input_inventory is not None:
        receipt["input_inventory"] = input_inventory
    if row_materialization is not None:
        receipt["row_materialization"] = row_materialization
    if gross_observational_returns is not None:
        receipt["gross_observational_returns"] = gross_observational_returns
    if cost_case_observational_drag is not None:
        receipt["cost_case_observational_drag"] = cost_case_observational_drag
    if funding_observational_adjustments is not None:
        receipt["funding_observational_adjustments"] = funding_observational_adjustments
    if funding_to_bars_alignment_diagnostics is not None:
        receipt["funding_to_bars_alignment_diagnostics"] = (
            funding_to_bars_alignment_diagnostics
        )
    if funding_to_bars_temporal_joinability_diagnostics is not None:
        receipt["funding_to_bars_temporal_joinability_diagnostics"] = (
            funding_to_bars_temporal_joinability_diagnostics
        )
    if funding_to_bars_timestamp_convention_diagnostics is not None:
        receipt["funding_to_bars_timestamp_convention_diagnostics"] = (
            funding_to_bars_timestamp_convention_diagnostics
        )
    if funding_to_bars_timestamp_canonicalization_diagnostics is not None:
        receipt["funding_to_bars_timestamp_canonicalization_diagnostics"] = (
            funding_to_bars_timestamp_canonicalization_diagnostics
        )
    if funding_application_readiness_gate_diagnostics is not None:
        receipt["funding_application_readiness_gate_diagnostics"] = (
            funding_application_readiness_gate_diagnostics
        )

    if funding_adjusted_bars_scaffold_diagnostics is not None:
        receipt["funding_adjusted_bars_scaffold_diagnostics"] = (
            funding_adjusted_bars_scaffold_diagnostics
        )
    if funding_adjustment_policy_contract_diagnostics is not None:
        receipt["funding_adjustment_policy_contract_diagnostics"] = (
            funding_adjustment_policy_contract_diagnostics
        )
    if funding_adjustment_arithmetic_scaffold_diagnostics is not None:
        receipt["funding_adjustment_arithmetic_scaffold_diagnostics"] = (
            funding_adjustment_arithmetic_scaffold_diagnostics
        )
    if funding_adjustment_row_scaffold_diagnostics is not None:
        receipt["funding_adjustment_row_scaffold_diagnostics"] = (
            funding_adjustment_row_scaffold_diagnostics
        )
    if funding_adjustment_sample_aggregate_diagnostics is not None:
        receipt["funding_adjustment_sample_aggregate_diagnostics"] = (
            funding_adjustment_sample_aggregate_diagnostics
        )
    if split_leakage_audit_diagnostics is not None:
        receipt["split_leakage_audit_diagnostics"] = split_leakage_audit_diagnostics
    if strategy_rule_contract_diagnostics is not None:
        receipt["strategy_rule_contract_diagnostics"] = (
            strategy_rule_contract_diagnostics
        )
    if trial_manifest_diagnostics is not None:
        receipt["trial_manifest_diagnostics"] = trial_manifest_diagnostics
    if oos_seal_diagnostics is not None:
        receipt["oos_seal_diagnostics"] = oos_seal_diagnostics
    if null_benchmark_contract_diagnostics is not None:
        receipt["null_benchmark_contract_diagnostics"] = (
            null_benchmark_contract_diagnostics
        )
    if multiple_testing_control_diagnostics is not None:
        receipt["multiple_testing_control_diagnostics"] = (
            multiple_testing_control_diagnostics
        )
    if trade_position_simulation_contract_diagnostics is not None:
        receipt["trade_position_simulation_contract_diagnostics"] = (
            trade_position_simulation_contract_diagnostics
        )
    if net_pnl_equity_risk_contract_diagnostics is not None:
        receipt["net_pnl_equity_risk_contract_diagnostics"] = (
            net_pnl_equity_risk_contract_diagnostics
        )
    if final_offline_edge_verdict_logic_diagnostics is not None:
        receipt["final_offline_edge_verdict_logic_diagnostics"] = (
            final_offline_edge_verdict_logic_diagnostics
        )

    return receipt


# ── Validation ────────────────────────────────────────────────────────────


_REQUIRED_TOP_LEVEL_KEYS = frozenset(
    {
        "validation_receipt",
        "input_manifest_fingerprint",
        "data_quality_receipt_sha256",
        "code_commit_sha",
        "split_definitions",
        "cost_cases",
        "required_outputs_present",
        "forbidden_calculation_status",
        "guardrail_status",
        "final_offline_verdict",
        "final_offline_verdict_rationale",
    }
)

_REQUIRED_GUARDRAIL_KEYS = frozenset(
    {
        "edge_unproven",
        "block_live_integration",
        "no_report_promotion",
        "output_under_tmp_only",
    }
)

_REQUIRED_FORBIDDEN_CALC_KEYS = frozenset(
    {
        "returns_computed",
        "pnl_computed",
        "sharpe_computed",
        "paper_engine_run",
        "live_integration_used",
    }
)


_GROSS_OBSERVATIONAL_RETURNS_EXEMPT_PATH = "$.gross_observational_returns"


def _is_under_gross_observational_returns_exempt_path(path: str) -> bool:
    return (
        path == _GROSS_OBSERVATIONAL_RETURNS_EXEMPT_PATH
        or path.startswith(_GROSS_OBSERVATIONAL_RETURNS_EXEMPT_PATH + ".")
        or path.startswith(_GROSS_OBSERVATIONAL_RETURNS_EXEMPT_PATH + "[")
    )


def _assert_no_forbidden_calculation_keys(value: Any, path: str = "$") -> None:
    """Recursively scan *value* for any key matching a forbidden calculation pattern.

    The forbidden set is :data:`FORBIDDEN_CALCULATION_KEYS` (42 names covering
    return/pnl/risk, strategy/signal/position, order/fill/execution, equity,
    scoring/significance, and verdict-named keys).

    Matching is **exact dict-key equality only**: no substring, prefix, regex,
    or case-insensitive matching. Sibling names that merely contain a forbidden
    name (e.g. ``max_drawdown``, ``fill_policy``, ``equity_curve_policy``) are
    therefore accepted by design.

    The sole exemption is ``gross_observational_return`` nested under the
    ``$.gross_observational_returns`` section.

    Raises ``ValueError`` if any forbidden key is found at any nesting level.
    """
    if isinstance(value, dict):
        for key, v in value.items():
            gross_observation_key_allowed = (
                key == "gross_observational_return"
                and _is_under_gross_observational_returns_exempt_path(path)
            )
            if key in FORBIDDEN_CALCULATION_KEYS and not gross_observation_key_allowed:
                raise ValueError(
                    f"Forbidden calculation key found at {path}.{key!r}"
                )
            _assert_no_forbidden_calculation_keys(v, path + "." + key)
    elif isinstance(value, (list, tuple)):
        for i, v in enumerate(value):
            _assert_no_forbidden_calculation_keys(v, path + "[" + str(i) + "]")


def validate_real_validation_receipt(receipt: dict[str, Any]) -> None:
    """Validate a real-validation receipt dict.

    Raises ``ValueError`` for any of: missing required top-level keys,
    a forbidden top-level key (``pnl``/``sharpe``/``edge``/
    ``strategy_performance``), a ``final_offline_verdict`` outside the
    allowed vocabulary, ``OFFLINE_EDGE_CANDIDATE`` at this skeleton phase,
    a missing/false ``guardrail_status`` entry, a missing/true
    ``forbidden_calculation_status`` entry, or an ``output_path`` that is
    not under ``/tmp`` or that resolves under ``/srv/qnty``.

    Also recursively scans for forbidden calculation keys at any nesting
    level; see :func:`_assert_no_forbidden_calculation_keys` and
    :data:`FORBIDDEN_CALCULATION_KEYS`.
    """
    missing = _REQUIRED_TOP_LEVEL_KEYS - set(receipt.keys())
    if missing:
        raise ValueError(f"Missing required keys: {sorted(missing)}")

    forbidden_present = FORBIDDEN_TOP_LEVEL_KEYS & set(receipt.keys())
    if forbidden_present:
        raise ValueError(f"Forbidden top-level keys present: {sorted(forbidden_present)}")

    verdict = receipt["final_offline_verdict"]
    if verdict not in ALLOWED_FINAL_VERDICTS:
        raise ValueError(
            f"final_offline_verdict '{verdict}' is not in allowed vocabulary: "
            f"{sorted(ALLOWED_FINAL_VERDICTS)}"
        )
    if verdict not in _SKELETON_ALLOWED_VERDICTS:
        raise ValueError(
            f"final_offline_verdict '{verdict}' is not allowed in the "
            f"receipt-skeleton phase. Only {sorted(_SKELETON_ALLOWED_VERDICTS)} "
            "may be emitted until a real validator is implemented."
        )

    guardrail_status = receipt.get("guardrail_status")
    if not isinstance(guardrail_status, dict):
        raise ValueError("guardrail_status must be a dict")
    missing_guardrails = _REQUIRED_GUARDRAIL_KEYS - set(guardrail_status.keys())
    if missing_guardrails:
        raise ValueError(f"Missing guardrail_status keys: {sorted(missing_guardrails)}")
    for key in _REQUIRED_GUARDRAIL_KEYS:
        if guardrail_status[key] is not True:
            raise ValueError(f"guardrail_status['{key}'] must be True, got {guardrail_status[key]!r}")

    forbidden_calc = receipt.get("forbidden_calculation_status")
    if not isinstance(forbidden_calc, dict):
        raise ValueError("forbidden_calculation_status must be a dict")
    missing_calc = _REQUIRED_FORBIDDEN_CALC_KEYS - set(forbidden_calc.keys())
    if missing_calc:
        raise ValueError(f"Missing forbidden_calculation_status keys: {sorted(missing_calc)}")
    for key in _REQUIRED_FORBIDDEN_CALC_KEYS:
        if forbidden_calc[key] is not False:
            raise ValueError(
                f"forbidden_calculation_status['{key}'] must be False, got {forbidden_calc[key]!r}"
            )

    output_path = receipt.get("output_path")
    if output_path is not None:
        resolved = Path(str(output_path)).resolve()
        _refuse_if_prod_path(resolved)
        _refuse_if_not_tmp(resolved)

    _assert_no_prod_paths_in_receipt(receipt)

    # Recursive scan for forbidden calculation keys at any nesting level.
    _assert_no_forbidden_calculation_keys(receipt)


# ── Output writer ─────────────────────────────────────────────────────────


def write_real_validation_receipt(receipt: dict[str, Any], output_path: Path) -> str:
    """Validate and write *receipt* as JSON to *output_path* under ``/tmp`` only.

    Returns the SHA256 hex digest of the exact bytes written. Refuses to
    write anywhere that does not resolve under ``/tmp``, and refuses any
    path resolving under ``/srv/qnty``.
    """
    validate_real_validation_receipt(receipt)

    resolved = output_path.resolve()
    _refuse_if_prod_path(resolved)
    _refuse_if_not_tmp(resolved)

    resolved.parent.mkdir(parents=True, exist_ok=True)
    payload = json.dumps(receipt, indent=2)
    with open(resolved, "w") as f:
        f.write(payload)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


# ── CLI skeleton ───────────────────────────────────────────────────────────


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Real offline validation receipt skeleton (no-op). "
            "Emits BLOCKED_BY_VALIDATION_IMPLEMENTATION only."
        )
    )
    parser.add_argument("--read-only", action="store_true", required=True)
    parser.add_argument("--output-dir", required=True, help="Must resolve under /tmp.")
    parser.add_argument("--input-manifest-fingerprint", required=True)
    parser.add_argument("--data-quality-receipt-sha256", required=True)
    parser.add_argument("--code-commit-sha", required=True)
    parser.add_argument(
        "--global-min-timestamp",
        default=None,
        help="Required if --bars-dir is not provided.",
    )
    parser.add_argument(
        "--global-max-timestamp",
        default=None,
        help="Required if --bars-dir is not provided.",
    )
    parser.add_argument("--split-count", type=int, default=3)
    parser.add_argument(
        "--bars-dir",
        default=None,
        type=str,
        help="Path to bars CSV directory. Alternative to --global-min/--global-max.",
    )
    parser.add_argument(
        "--funding-dir",
        default=None,
        type=str,
        help="Optional path to funding CSV directory (used with --bars-dir).",
    )
    parser.add_argument(
        "--strategy-contract-path",
        default=None,
        type=str,
        help=(
            "Path to frozen strategy-rule contract JSON. "
            "If provided, the contract is loaded and hash-checked (diagnostic only, "
            "no scoring). Requires --strategy-contract-sha256-path."
        ),
    )
    parser.add_argument(
        "--strategy-contract-sha256-path",
        default=None,
        type=str,
        help=(
            "Path to the SHA-256 sidecar for the frozen strategy-rule contract. "
            "Required if --strategy-contract-path is provided."
        ),
    )
    parser.add_argument(
        "--strategy-contract-commit-binding-path",
        default=None,
        type=str,
        help=(
            "Optional path to the commit-binding sidecar JSON for the frozen "
            "strategy-rule contract. If provided, the materializer verifies "
            "non-self-referential prior-commit containment of the contract bytes. "
            "Requires --strategy-contract-path and --strategy-contract-sha256-path."
        ),
    )
    parser.add_argument(
        "--trial-manifest-path",
        default=None,
        type=str,
        help=(
            "Path to frozen trial manifest pre-registration JSON. "
            "If provided, the manifest is loaded and hash-checked (diagnostic only, "
            "no scoring). Requires --trial-manifest-sha256-path and "
            "--strategy-contract-path/--strategy-contract-sha256-path."
        ),
    )
    parser.add_argument(
        "--trial-manifest-sha256-path",
        default=None,
        type=str,
        help=(
            "Path to the SHA-256 sidecar for the frozen trial manifest. "
            "Required if --trial-manifest-path is provided."
        ),
    )
    parser.add_argument(
        "--oos-seal-path",
        default=None,
        type=str,
        help=(
            "Path to frozen OOS seal pre-scoring declaration JSON. "
            "If provided, the seal is loaded and hash-checked (diagnostic only, "
            "no scoring). Requires --oos-seal-sha256-path, "
            "--trial-manifest-path/--trial-manifest-sha256-path, and "
            "--strategy-contract-path/--strategy-contract-sha256-path."
        ),
    )
    parser.add_argument(
        "--oos-seal-sha256-path",
        default=None,
        type=str,
        help=(
            "Path to the SHA-256 sidecar for the frozen OOS seal. "
            "Required if --oos-seal-path is provided."
        ),
    )
    parser.add_argument(
        "--null-benchmark-path",
        default=None,
        type=str,
        help=(
            "Path to frozen null benchmark pre-scoring declaration JSON. "
            "If provided, the packet is loaded and hash-checked (diagnostic "
            "only, no scoring, no null generation, no candidate comparison). "
            "Requires --null-benchmark-sha256-path, --oos-seal-path/"
            "--oos-seal-sha256-path, --trial-manifest-path/"
            "--trial-manifest-sha256-path, and --strategy-contract-path/"
            "--strategy-contract-sha256-path."
        ),
    )
    parser.add_argument(
        "--null-benchmark-sha256-path",
        default=None,
        type=str,
        help=(
            "Path to the SHA-256 sidecar for the frozen null benchmark packet. "
            "Required if --null-benchmark-path is provided."
        ),
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    output_dir = Path(args.output_dir).resolve()
    try:
        _refuse_if_prod_path(output_dir)
        _refuse_if_not_tmp(output_dir)
    except ValueError as exc:
        print(f"FATAL: {exc}")
        return 3

    cost_cases = build_cost_case_matrix()

    if args.bars_dir is not None:
        # Inventory-based path: derive everything from real data directories.
        bars_dir = Path(args.bars_dir)
        funding_dir = Path(args.funding_dir) if args.funding_dir else None

        try:
            inventory = build_real_validation_input_inventory(
                bars_dir=bars_dir,
                funding_dir=funding_dir,
            )
            split_definitions = materialize_split_definitions_from_inventory(
                inventory=inventory,
                split_count=args.split_count,
            )
            row_materialization = materialize_input_rows_for_splits(
                inventory=inventory,
                split_definitions=split_definitions,
            )
            gross_observational_returns = materialize_gross_observational_returns(
                inventory=inventory,
                split_definitions=split_definitions,
            )
            cost_case_observational_drag = materialize_cost_case_observational_drag(
                gross_observational_returns=gross_observational_returns,
                cost_cases=cost_cases,
            )
            funding_observational_adjustments = (
                materialize_funding_observational_adjustments(
                    inventory=inventory,
                    split_definitions=split_definitions,
                )
            )
            funding_to_bars_alignment_diagnostics = (
                materialize_funding_to_bars_alignment_diagnostics(
                    row_materialization=row_materialization,
                    gross_observational_returns=gross_observational_returns,
                    funding_observational_adjustments=(
                        funding_observational_adjustments
                    ),
                )
                if funding_dir is not None
                else None
            )
            funding_to_bars_temporal_joinability_diagnostics = (
                materialize_funding_to_bars_temporal_joinability_diagnostics(
                    inventory=inventory,
                    split_definitions=split_definitions,
                )
                if funding_dir is not None
                else None
            )
            funding_to_bars_timestamp_convention_diagnostics = (
                materialize_funding_to_bars_timestamp_convention_diagnostics(
                    inventory=inventory,
                    split_definitions=split_definitions,
                )
                if funding_dir is not None
                else None
            )
            funding_to_bars_timestamp_canonicalization_diagnostics = (
                materialize_funding_to_bars_timestamp_canonicalization_diagnostics(
                    inventory=inventory,
                    split_definitions=split_definitions,
                )
                if funding_dir is not None
                else None
            )
            funding_application_readiness_gate_diagnostics = (
                materialize_funding_application_readiness_gate_diagnostics(
                    funding_to_bars_alignment_diagnostics=(
                        funding_to_bars_alignment_diagnostics
                    ),
                    funding_to_bars_temporal_joinability_diagnostics=(
                        funding_to_bars_temporal_joinability_diagnostics
                    ),
                    funding_to_bars_timestamp_convention_diagnostics=(
                        funding_to_bars_timestamp_convention_diagnostics
                    ),
                    funding_to_bars_timestamp_canonicalization_diagnostics=(
                        funding_to_bars_timestamp_canonicalization_diagnostics
                    ),
                )
                if funding_dir is not None
                else None
            )
            funding_adjusted_bars_scaffold_diagnostics = (
                materialize_funding_adjusted_bars_scaffold_diagnostics(
                    funding_application_readiness_gate_diagnostics=(
                        funding_application_readiness_gate_diagnostics
                    ),
                    funding_to_bars_timestamp_canonicalization_diagnostics=(
                        funding_to_bars_timestamp_canonicalization_diagnostics
                    ),
                    bars_inventory=next(
                        r for r in inventory["roles"]
                        if r["role"] == "bars"
                    ),
                    funding_inventory=next(
                        r for r in inventory["roles"]
                        if r["role"] == "funding"
                    ),
                    bars_dir=str(bars_dir),
                    funding_dir=str(funding_dir),
                    source_sha=args.code_commit_sha,
                )
                if funding_dir is not None
                else None
            )
            funding_adjustment_policy_contract_diagnostics = (
                materialize_funding_adjustment_policy_contract_diagnostics(
                    funding_adjusted_bars_scaffold_diagnostics=(
                        funding_adjusted_bars_scaffold_diagnostics
                    ),
                )
                if funding_dir is not None
                else None
            )
            funding_adjustment_arithmetic_scaffold_diagnostics = (
                materialize_funding_adjustment_arithmetic_scaffold_diagnostics(
                    funding_adjustment_policy_contract_diagnostics=(
                        funding_adjustment_policy_contract_diagnostics
                    ),
                )
                if funding_dir is not None
                else None
            )
            funding_adjustment_row_scaffold_diagnostics = (
                materialize_funding_adjustment_row_scaffold_diagnostics(
                    funding_adjustment_policy_contract_diagnostics=(
                        funding_adjustment_policy_contract_diagnostics
                    ),
                    funding_adjustment_arithmetic_scaffold_diagnostics=(
                        funding_adjustment_arithmetic_scaffold_diagnostics
                    ),
                    funding_adjusted_bars_scaffold_diagnostics=(
                        funding_adjusted_bars_scaffold_diagnostics
                    ),
                )
                if funding_dir is not None
                else None
            )
            funding_adjustment_sample_aggregate_diagnostics = (
                _build_funding_adjustment_sample_aggregate_diagnostics(
                    funding_adjustment_row_scaffold_diagnostics,
                )
                if funding_dir is not None
                else None
            )
            split_leakage_audit_diagnostics = (
                _build_split_leakage_audit_diagnostics(
                    split_definitions=split_definitions,
                    split_builder_inspected=_SPLIT_BUILDER_INVENTORY,
                )
            )
            strategy_rule_contract_diagnostics = (
                _build_strategy_rule_contract_diagnostics(
                    contract_path=args.strategy_contract_path,
                    sidecar_path=args.strategy_contract_sha256_path,
                    commit_binding_path=args.strategy_contract_commit_binding_path,
                )
            )
            trial_manifest_diagnostics = _build_trial_manifest_diagnostics(
                manifest_path=args.trial_manifest_path,
                sidecar_path=args.trial_manifest_sha256_path,
                strategy_rule_contract_diagnostics=(
                    strategy_rule_contract_diagnostics
                ),
            )
            oos_seal_diagnostics = _build_oos_seal_diagnostics(
                seal_path=args.oos_seal_path,
                sidecar_path=args.oos_seal_sha256_path,
                trial_manifest_diagnostics=trial_manifest_diagnostics,
                strategy_rule_contract_diagnostics=(
                    strategy_rule_contract_diagnostics
                ),
            )
            null_benchmark_contract_diagnostics = (
                _build_null_benchmark_contract_diagnostics(
                    null_benchmark_path=args.null_benchmark_path,
                    sidecar_path=args.null_benchmark_sha256_path,
                    oos_seal_diagnostics=oos_seal_diagnostics,
                    trial_manifest_diagnostics=trial_manifest_diagnostics,
                    strategy_rule_contract_diagnostics=(
                        strategy_rule_contract_diagnostics
                    ),
                )
            )
            multiple_testing_control_diagnostics = (
                _build_multiple_testing_control_diagnostics()
            )
            trade_position_simulation_contract_diagnostics = (
                _build_trade_position_simulation_contract_diagnostics()
            )
            net_pnl_equity_risk_contract_diagnostics = (
                _build_net_pnl_equity_risk_contract_diagnostics()
            )
            final_offline_edge_verdict_logic_diagnostics = (
                _build_final_offline_edge_verdict_logic_diagnostics()
            )
        except ValueError as exc:
            print(f"FATAL: offline materialization failed: {exc}")
            return 4

        receipt = build_real_validation_receipt(
            input_manifest_fingerprint=args.input_manifest_fingerprint,
            data_quality_receipt_sha256=args.data_quality_receipt_sha256,
            code_commit_sha=args.code_commit_sha,
            split_definitions=split_definitions,
            cost_cases=cost_cases,
            input_inventory=inventory,
            row_materialization=row_materialization,
            gross_observational_returns=gross_observational_returns,
            cost_case_observational_drag=cost_case_observational_drag,
            funding_observational_adjustments=funding_observational_adjustments,
            funding_to_bars_alignment_diagnostics=(
                funding_to_bars_alignment_diagnostics
            ),
            funding_to_bars_temporal_joinability_diagnostics=(
                funding_to_bars_temporal_joinability_diagnostics
            ),
            funding_to_bars_timestamp_convention_diagnostics=(
                funding_to_bars_timestamp_convention_diagnostics
            ),
            funding_to_bars_timestamp_canonicalization_diagnostics=(
                funding_to_bars_timestamp_canonicalization_diagnostics
            ),
            funding_application_readiness_gate_diagnostics=(
                funding_application_readiness_gate_diagnostics
            ),
            funding_adjusted_bars_scaffold_diagnostics=(
                funding_adjusted_bars_scaffold_diagnostics
            ),
            funding_adjustment_policy_contract_diagnostics=(
                funding_adjustment_policy_contract_diagnostics
            ),
            funding_adjustment_arithmetic_scaffold_diagnostics=(
                funding_adjustment_arithmetic_scaffold_diagnostics
            ),
            funding_adjustment_row_scaffold_diagnostics=(
                funding_adjustment_row_scaffold_diagnostics
            ),
            funding_adjustment_sample_aggregate_diagnostics=(
                funding_adjustment_sample_aggregate_diagnostics
            ),
            split_leakage_audit_diagnostics=split_leakage_audit_diagnostics,
            strategy_rule_contract_diagnostics=(
                strategy_rule_contract_diagnostics
            ),
            trial_manifest_diagnostics=trial_manifest_diagnostics,
            oos_seal_diagnostics=oos_seal_diagnostics,
            null_benchmark_contract_diagnostics=(
                null_benchmark_contract_diagnostics
            ),
            multiple_testing_control_diagnostics=(
                multiple_testing_control_diagnostics
            ),
            trade_position_simulation_contract_diagnostics=(
                trade_position_simulation_contract_diagnostics
            ),
            net_pnl_equity_risk_contract_diagnostics=(
                net_pnl_equity_risk_contract_diagnostics
            ),
            final_offline_edge_verdict_logic_diagnostics=(
                final_offline_edge_verdict_logic_diagnostics
            ),
        )
    else:
        # Legacy path: use CLI-provided timestamp bounds.
        if args.global_min_timestamp is None or args.global_max_timestamp is None:
            print(
                "FATAL: --global-min-timestamp and --global-max-timestamp are "
                "required when --bars-dir is not provided."
            )
            return 5

        split_definitions = build_deterministic_split_definitions(
            global_min_timestamp=args.global_min_timestamp,
            global_max_timestamp=args.global_max_timestamp,
            split_count=args.split_count,
        )

        try:
            split_leakage_audit_diagnostics = (
                _build_split_leakage_audit_diagnostics(
                    split_definitions=split_definitions,
                    split_builder_inspected=_SPLIT_BUILDER_FALLBACK,
                )
            )
            strategy_rule_contract_diagnostics = (
                _build_strategy_rule_contract_diagnostics(
                    contract_path=args.strategy_contract_path,
                    sidecar_path=args.strategy_contract_sha256_path,
                    commit_binding_path=args.strategy_contract_commit_binding_path,
                )
            )
            trial_manifest_diagnostics = _build_trial_manifest_diagnostics(
                manifest_path=args.trial_manifest_path,
                sidecar_path=args.trial_manifest_sha256_path,
                strategy_rule_contract_diagnostics=(
                    strategy_rule_contract_diagnostics
                ),
            )
            oos_seal_diagnostics = _build_oos_seal_diagnostics(
                seal_path=args.oos_seal_path,
                sidecar_path=args.oos_seal_sha256_path,
                trial_manifest_diagnostics=trial_manifest_diagnostics,
                strategy_rule_contract_diagnostics=(
                    strategy_rule_contract_diagnostics
                ),
            )
            null_benchmark_contract_diagnostics = (
                _build_null_benchmark_contract_diagnostics(
                    null_benchmark_path=args.null_benchmark_path,
                    sidecar_path=args.null_benchmark_sha256_path,
                    oos_seal_diagnostics=oos_seal_diagnostics,
                    trial_manifest_diagnostics=trial_manifest_diagnostics,
                    strategy_rule_contract_diagnostics=(
                        strategy_rule_contract_diagnostics
                    ),
                )
            )
            multiple_testing_control_diagnostics = (
                _build_multiple_testing_control_diagnostics()
            )
            trade_position_simulation_contract_diagnostics = (
                _build_trade_position_simulation_contract_diagnostics()
            )
            net_pnl_equity_risk_contract_diagnostics = (
                _build_net_pnl_equity_risk_contract_diagnostics()
            )
            final_offline_edge_verdict_logic_diagnostics = (
                _build_final_offline_edge_verdict_logic_diagnostics()
            )
        except ValueError as exc:
            print(f"FATAL: split leakage audit failed: {exc}")
            return 4

        receipt = build_real_validation_receipt(
            input_manifest_fingerprint=args.input_manifest_fingerprint,
            data_quality_receipt_sha256=args.data_quality_receipt_sha256,
            code_commit_sha=args.code_commit_sha,
            split_definitions=split_definitions,
            cost_cases=cost_cases,
            split_leakage_audit_diagnostics=split_leakage_audit_diagnostics,
            strategy_rule_contract_diagnostics=(
                strategy_rule_contract_diagnostics
            ),
            trial_manifest_diagnostics=trial_manifest_diagnostics,
            oos_seal_diagnostics=oos_seal_diagnostics,
            null_benchmark_contract_diagnostics=(
                null_benchmark_contract_diagnostics
            ),
            multiple_testing_control_diagnostics=(
                multiple_testing_control_diagnostics
            ),
            trade_position_simulation_contract_diagnostics=(
                trade_position_simulation_contract_diagnostics
            ),
            net_pnl_equity_risk_contract_diagnostics=(
                net_pnl_equity_risk_contract_diagnostics
            ),
            final_offline_edge_verdict_logic_diagnostics=(
                final_offline_edge_verdict_logic_diagnostics
            ),
        )

    output_path = output_dir / "real_validation_receipt.json"
    digest = write_real_validation_receipt(receipt, output_path)

    print(f"final_offline_verdict={receipt['final_offline_verdict']}")
    print(f"receipt_sha256={digest}")
    print(f"receipt_path={output_path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
