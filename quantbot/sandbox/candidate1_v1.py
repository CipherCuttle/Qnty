"""Candidate 1 V1 synthetic strategy sandbox.

This is a deterministic software-path harness, not a scientific protocol.
All values are dimensionless assumptions for mechanical coverage only.
"""
from __future__ import annotations

import hashlib
import json
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any

from quantbot.continuity.context import canonical_json_bytes

SCHEMA_VERSION = "0.1.0"
RECEIPT_KIND = "qnty_candidate1_v1_synthetic_sandbox_receipt"
BUNDLE_KIND = "qnty_candidate1_v1_synthetic_variant_bundle"
SANDBOX_ID = "candidate1-v1-synthetic-design-sandbox-v0"
SANDBOX_STATUS = "AUTHORIZED_EXPLORATORY_ENGINEERING_ONLY"
TRANSACTION_COST = Decimal("0.001")
TRANSACTION_COST_RATIONALE = "DECLARED_ARBITRARY_ASSUMPTION_FOR_MECHANICAL_PATH_COVERAGE"
RULE_KINDS = (
    "ALWAYS_FLAT", "ALWAYS_LONG", "ALWAYS_SHORT", "LAGGED_RETURN_SIGN",
    "LAGGED_RETURN_FADE", "FUNDING_SIGN_FADE",
)
RATIONALE_KINDS = (
    "MECHANICAL_BASELINE", "SOFTWARE_PATH_COVERAGE",
    "DECLARED_ARBITRARY_ASSUMPTION", "GENERIC_STYLIZED_FACT",
)
_BUNDLE_KEYS = {"bundle_id", "bundle_kind", "schema_version", "variants"}
_VARIANT_KEYS = {"variant_id", "rule_kind", "parameters", "rationale_kind", "rationale"}


class SandboxValidationError(ValueError):
    """Expected user or receipt validation failure."""


def _strict_pairs(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise SandboxValidationError(f"duplicate JSON key: {key}")
        result[key] = value
    return result


def parse_json_bytes(data: bytes, label: str) -> Any:
    try:
        return json.loads(data.decode("utf-8"), object_pairs_hook=_strict_pairs,
                          parse_constant=lambda value: (_ for _ in ()).throw(
                              SandboxValidationError(f"non-finite JSON value in {label}: {value}")))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise SandboxValidationError(f"{label} is not strict UTF-8 JSON") from exc


def _exact_keys(value: Any, expected: set[str], label: str) -> dict[str, Any]:
    if type(value) is not dict or set(value) != expected:
        actual = set(value) if type(value) is dict else set()
        raise SandboxValidationError(f"{label} keys mismatch (missing={sorted(expected-actual)} extra={sorted(actual-expected)})")
    return value


def _text(value: Any, label: str) -> str:
    if type(value) is not str or not value:
        raise SandboxValidationError(f"{label} must be a non-empty string")
    return value


def _decimal(value: Any, label: str, *, nonnegative: bool = False) -> Decimal:
    if type(value) is not str:
        raise SandboxValidationError(f"{label} must be a decimal string")
    try:
        result = Decimal(value)
    except InvalidOperation as exc:
        raise SandboxValidationError(f"{label} is not a decimal string") from exc
    if not result.is_finite() or (nonnegative and result < 0):
        raise SandboxValidationError(f"{label} must be finite and non-negative")
    return result


def _canonical_digest(value: Any) -> str:
    return hashlib.sha256(canonical_json_bytes(value)).hexdigest()


def _scenario(scenario_id: str, description: str, prices: tuple[str, ...], funding: tuple[str, ...]) -> dict[str, Any]:
    item = {"scenario_id": scenario_id, "description": description,
            "observation_count": len(prices), "price_path": list(prices), "funding_path": list(funding)}
    item["scenario_fingerprint"] = _canonical_digest(item)
    return item


SCENARIOS = (
    _scenario("FLAT_ZERO_FUNDING", "Constant dimensionless price and zero funding.", ("1", "1", "1", "1", "1", "1"), ("0",) * 6),
    _scenario("UPTREND_ZERO_FUNDING", "Monotone dimensionless increase with zero funding.", ("1", "2", "3", "4", "5", "6"), ("0",) * 6),
    _scenario("DOWNTREND_ZERO_FUNDING", "Monotone dimensionless decrease with zero funding.", ("6", "5", "4", "3", "2", "1"), ("0",) * 6),
    _scenario("ALTERNATING_REVERSAL_ZERO_FUNDING", "Alternating dimensionless reversals with zero funding.", ("1", "2", "1", "2", "1", "2"), ("0",) * 6),
    _scenario("FLAT_POSITIVE_FUNDING", "Constant price with positive generic funding.", ("1",) * 6, ("0.1",) * 6),
    _scenario("FLAT_NEGATIVE_FUNDING", "Constant price with negative generic funding.", ("1",) * 6, ("-0.1",) * 6),
    _scenario("TREND_WITH_OPPOSING_FUNDING", "Increasing price with negative generic funding.", ("1", "2", "3", "4", "5", "6"), ("-0.1",) * 6),
)
SCENARIO_CONTRACT = {"schema_version": SCHEMA_VERSION, "scenarios": list(SCENARIOS)}
RULE_CONTRACT = {"schema_version": SCHEMA_VERSION, "rule_kinds": list(RULE_KINDS), "decision_constraint": "indices strictly less than evaluated interval index"}
ACCOUNTING_CONTRACT = {"schema_version": SCHEMA_VERSION, "transaction_cost": str(TRANSACTION_COST), "transaction_cost_rationale": TRANSACTION_COST_RATIONALE,
                       "components": ["active_slot_count", "long_slot_count", "short_slot_count", "flat_slot_count", "turnover_count", "mean_price_component", "mean_funding_component", "mean_cost_drag", "mean_net", "position_series_sha256"]}


def validate_bundle(bundle: Any) -> dict[str, Any]:
    bundle = _exact_keys(bundle, _BUNDLE_KEYS, "bundle")
    _text(bundle["bundle_id"], "bundle_id")
    if bundle["bundle_kind"] != BUNDLE_KIND or bundle["schema_version"] != SCHEMA_VERSION:
        raise SandboxValidationError("bundle kind or schema version is wrong")
    variants = bundle["variants"]
    if type(variants) is not list or not variants:
        raise SandboxValidationError("variants must be a non-empty list")
    seen: set[str] = set()
    normalized = []
    for raw in variants:
        item = _exact_keys(raw, _VARIANT_KEYS | ({"source_reference"} if type(raw) is dict and raw.get("rationale_kind") == "GENERIC_STYLIZED_FACT" else set()), "variant")
        variant_id = _text(item["variant_id"], "variant_id")
        if variant_id in seen:
            raise SandboxValidationError(f"duplicate variant_id: {variant_id}")
        seen.add(variant_id)
        if item["rule_kind"] not in RULE_KINDS:
            raise SandboxValidationError("unknown rule_kind")
        if item["rationale_kind"] not in RATIONALE_KINDS:
            raise SandboxValidationError("unknown rationale_kind")
        _text(item["rationale"], "rationale")
        parameters = item["parameters"]
        if type(parameters) is not dict:
            raise SandboxValidationError("parameters must be an object")
        rule = item["rule_kind"]
        expected = set()
        if rule in ("ALWAYS_FLAT", "ALWAYS_LONG", "ALWAYS_SHORT"):
            expected = set()
        elif rule in ("LAGGED_RETURN_SIGN", "LAGGED_RETURN_FADE"):
            expected = {"lookback", "deadband"}
            if set(parameters) != expected or type(parameters.get("lookback")) is not int or not 1 <= parameters["lookback"] <= 16:
                raise SandboxValidationError("invalid lagged return parameters")
            _decimal(parameters["deadband"], "deadband", nonnegative=True)
        elif rule == "FUNDING_SIGN_FADE":
            expected = {"deadband"}
            if set(parameters) != expected:
                raise SandboxValidationError("invalid funding parameters")
            _decimal(parameters["deadband"], "deadband", nonnegative=True)
        if set(parameters) != expected:
            raise SandboxValidationError(f"parameters for {rule} must be {sorted(expected)}")
        if item["rationale_kind"] == "GENERIC_STYLIZED_FACT":
            _text(item.get("source_reference"), "source_reference")
        elif "source_reference" in item:
            raise SandboxValidationError("source_reference is only allowed for GENERIC_STYLIZED_FACT")
        normalized.append(dict(item))
    return {"bundle_id": bundle["bundle_id"], "bundle_kind": bundle["bundle_kind"], "schema_version": bundle["schema_version"], "variants": normalized}


def load_bundle(path: Path) -> tuple[dict[str, Any], str, str]:
    data = path.read_bytes()
    parsed = parse_json_bytes(data, "variant bundle")
    bundle = validate_bundle(parsed)
    return bundle, hashlib.sha256(data).hexdigest(), _canonical_digest(bundle)


def _sign(value: Decimal) -> int:
    return 1 if value > 0 else -1 if value < 0 else 0


def position_for(variant: dict[str, Any], prices: list[Decimal], funding: list[Decimal], t: int) -> int:
    rule, params = variant["rule_kind"], variant["parameters"]
    if rule == "ALWAYS_FLAT": return 0
    if rule == "ALWAYS_LONG": return 1
    if rule == "ALWAYS_SHORT": return -1
    deadband = _decimal(params["deadband"], "deadband")
    if rule in ("LAGGED_RETURN_SIGN", "LAGGED_RETURN_FADE"):
        lookback = params["lookback"]
        if t <= lookback: return 0
        value = prices[t - 1] - prices[t - 1 - lookback]
        position = 0 if abs(value) <= deadband else _sign(value)
        return -position if rule == "LAGGED_RETURN_FADE" else position
    if t == 0: return 0
    prior = funding[t - 1]
    return 0 if abs(prior) <= deadband else -_sign(prior)


def _result(variant: dict[str, Any], scenario: dict[str, Any]) -> dict[str, Any]:
    prices = [Decimal(x) for x in scenario["price_path"]]
    funding = [Decimal(x) for x in scenario["funding_path"]]
    positions = [position_for(variant, prices, funding, t) for t in range(len(prices) - 1)]
    price_components = [positions[t] * (prices[t + 1] - prices[t]) for t in range(len(positions))]
    funding_components = [-positions[t] * funding[t] for t in range(len(positions))]
    costs = [TRANSACTION_COST * abs(positions[t] - (positions[t - 1] if t else 0)) for t in range(len(positions))]
    nets = [price_components[i] + funding_components[i] - costs[i] for i in range(len(positions))]
    def avg(values: list[Decimal]) -> str:
        return str(sum(values, Decimal(0)) / len(values))
    series = canonical_json_bytes(positions)
    return {"active_slot_count": len(positions), "flat_slot_count": positions.count(0), "long_slot_count": positions.count(1),
            "mean_cost_drag": avg(costs), "mean_funding_component": avg(funding_components), "mean_net": avg(nets),
            "mean_price_component": avg(price_components), "position_series_sha256": hashlib.sha256(series).hexdigest(),
            "scenario_id": scenario["scenario_id"], "short_slot_count": positions.count(-1), "turnover_count": sum(1 for i in range(len(positions)) if positions[i] != (positions[i-1] if i else 0)),
            "variant_id": variant["variant_id"]}


def build_receipt(bundle: dict[str, Any], raw_sha: str, bundle_sha: str) -> dict[str, Any]:
    results = sorted((_result(variant, scenario) for variant in bundle["variants"] for scenario in SCENARIOS), key=lambda x: (x["variant_id"], x["scenario_id"]))
    receipt = {"schema_version": SCHEMA_VERSION, "receipt_kind": RECEIPT_KIND, "sandbox_id": SANDBOX_ID, "sandbox_status": SANDBOX_STATUS,
               "scientific_evidence": False, "edge_claim_authorized": False, "official_v1_protocol": False, "real_data_accessed": False,
               "selection_performed": False, "all_variants_included": True, "explored_variant_count": len(bundle["variants"]),
               "raw_input_sha256": raw_sha, "canonical_bundle_sha256": bundle_sha, "variant_bundle": bundle,
               "scenario_contract_sha256": _canonical_digest(SCENARIO_CONTRACT), "rule_contract_sha256": _canonical_digest(RULE_CONTRACT),
               "accounting_contract_sha256": _canonical_digest(ACCOUNTING_CONTRACT), "results": results}
    receipt["run_fingerprint"] = _canonical_digest(receipt)
    return receipt


def verify_receipt_bytes(data: bytes) -> dict[str, Any]:
    parsed = parse_json_bytes(data, "receipt")
    if data != canonical_json_bytes(parsed):
        raise SandboxValidationError("receipt is not canonical QNTY JSON")
    expected_keys = {"schema_version", "receipt_kind", "sandbox_id", "sandbox_status", "scientific_evidence", "edge_claim_authorized", "official_v1_protocol", "real_data_accessed", "selection_performed", "all_variants_included", "explored_variant_count", "raw_input_sha256", "canonical_bundle_sha256", "variant_bundle", "scenario_contract_sha256", "rule_contract_sha256", "accounting_contract_sha256", "results", "run_fingerprint"}
    _exact_keys(parsed, expected_keys, "receipt")
    for key, value in {"schema_version": SCHEMA_VERSION, "receipt_kind": RECEIPT_KIND, "sandbox_id": SANDBOX_ID, "sandbox_status": SANDBOX_STATUS}.items():
        if parsed[key] != value: raise SandboxValidationError(f"receipt {key} is wrong")
    for key in ("scientific_evidence", "edge_claim_authorized", "official_v1_protocol", "real_data_accessed", "selection_performed"):
        if parsed[key] is not False: raise SandboxValidationError(f"receipt {key} must be false")
    if parsed["all_variants_included"] is not True: raise SandboxValidationError("all_variants_included must be true")
    bundle = validate_bundle(parsed["variant_bundle"])
    if parsed["explored_variant_count"] != len(bundle["variants"]): raise SandboxValidationError("explored variant count mismatch")
    if parsed["canonical_bundle_sha256"] != _canonical_digest(bundle): raise SandboxValidationError("canonical bundle fingerprint mismatch")
    if parsed["scenario_contract_sha256"] != _canonical_digest(SCENARIO_CONTRACT) or parsed["rule_contract_sha256"] != _canonical_digest(RULE_CONTRACT) or parsed["accounting_contract_sha256"] != _canonical_digest(ACCOUNTING_CONTRACT): raise SandboxValidationError("contract fingerprint mismatch")
    expected_results = sorted((_result(v, s) for v in bundle["variants"] for s in SCENARIOS), key=lambda x: (x["variant_id"], x["scenario_id"]))
    if parsed["results"] != expected_results: raise SandboxValidationError("receipt results do not replay exactly")
    unsigned = dict(parsed); unsigned.pop("run_fingerprint")
    if parsed["run_fingerprint"] != _canonical_digest(unsigned): raise SandboxValidationError("run fingerprint mismatch")
    return parsed


def run_bundle(path: Path, out: Path) -> tuple[dict[str, Any], str]:
    if out.exists(): raise FileExistsError(out)
    if not out.parent.is_dir(): raise FileNotFoundError(out.parent)
    bundle, raw_sha, bundle_sha = load_bundle(path)
    receipt = build_receipt(bundle, raw_sha, bundle_sha)
    data = canonical_json_bytes(receipt)
    with out.open("xb") as handle:
        handle.write(data); handle.flush(); __import__("os").fsync(handle.fileno())
    return receipt, hashlib.sha256(data).hexdigest()
