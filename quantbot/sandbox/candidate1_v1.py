"""Candidate 1 V1 synthetic strategy sandbox.

This is a deterministic software-path harness, not a scientific protocol.
All values are dimensionless assumptions for mechanical coverage only.
"""
from __future__ import annotations

import contextlib
import hashlib
import json
import os
import re
import secrets
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
POSITION_DOMAIN = (-1, 0, 1)
LOOKBACK_MIN = 1
LOOKBACK_MAX = 16
_BUNDLE_KEYS = {"bundle_id", "bundle_kind", "schema_version", "variants"}
_VARIANT_KEYS = {"variant_id", "rule_kind", "parameters", "rationale_kind", "rationale"}
_HEX64_RE = re.compile(r"\A[0-9a-f]{64}\Z")


class SandboxValidationError(ValueError):
    """Expected validation failure (base class for input and verification errors)."""


class SandboxInputError(SandboxValidationError):
    """Invalid or unreadable variant input. Maps to CLI exit code 2."""


class SandboxVerificationError(SandboxValidationError):
    """Receipt verification failure. Maps to CLI exit code 3."""


class SandboxPublicationError(OSError):
    """Output publication failure. Maps to CLI exit code 4."""


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


def _require_hex_sha(value: Any, label: str) -> str:
    if type(value) is not str or not _HEX64_RE.match(value):
        raise SandboxVerificationError(f"{label} must be a lowercase 64-character hex sha256")
    return value


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

# Machine-readable rule contract. The fingerprint binds the exact rule
# identities, accepted parameters, parameter types/ranges, deadband and warm-up
# semantics, the information set available at each decision, the position
# domain, and every position formula. These are generic sandbox assumptions,
# not scientific choices.
_LAGGED_PARAMS = {
    "lookback": {"type": "int", "min": LOOKBACK_MIN, "max": LOOKBACK_MAX},
    "deadband": {"type": "decimal_string", "min": "0", "finite": True},
}
RULE_PARAMETER_SCHEMA = {
    "ALWAYS_FLAT": {},
    "ALWAYS_LONG": {},
    "ALWAYS_SHORT": {},
    "LAGGED_RETURN_SIGN": dict(_LAGGED_PARAMS),
    "LAGGED_RETURN_FADE": dict(_LAGGED_PARAMS),
    "FUNDING_SIGN_FADE": {"deadband": {"type": "decimal_string", "min": "0", "finite": True}},
}
RULE_WARMUP = {
    "ALWAYS_FLAT": "none",
    "ALWAYS_LONG": "none",
    "ALWAYS_SHORT": "none",
    "LAGGED_RETURN_SIGN": "position(t) = 0 while t <= lookback",
    "LAGGED_RETURN_FADE": "position(t) = 0 while t <= lookback",
    "FUNDING_SIGN_FADE": "position(t) = 0 while t == 0",
}
RULE_FORMULAS = {
    "ALWAYS_FLAT": "position(t) = 0",
    "ALWAYS_LONG": "position(t) = 1",
    "ALWAYS_SHORT": "position(t) = -1",
    "LAGGED_RETURN_SIGN": "d = price[t-1] - price[t-1-lookback]; position(t) = 0 if t <= lookback else (0 if abs(d) <= deadband else sign(d))",
    "LAGGED_RETURN_FADE": "d = price[t-1] - price[t-1-lookback]; position(t) = 0 if t <= lookback else (0 if abs(d) <= deadband else -sign(d))",
    "FUNDING_SIGN_FADE": "g = funding[t-1]; position(t) = 0 if t == 0 else (0 if abs(g) <= deadband else -sign(g))",
}
RULE_CONTRACT = {
    "schema_version": SCHEMA_VERSION,
    "rule_kinds": list(RULE_KINDS),
    "position_domain": list(POSITION_DOMAIN),
    "sign_definition": "sign(x) = 1 if x > 0, -1 if x < 0, 0 if x == 0",
    "deadband_comparison": "a decision is flat when abs(signal) <= deadband; the deadband upper bound is inclusive",
    "information_set": "a decision at evaluated interval index t may read only observations with index strictly less than t (indices 0..t-1)",
    "decision_constraint": "indices strictly less than evaluated interval index",
    "parameter_schema": RULE_PARAMETER_SCHEMA,
    "warmup": RULE_WARMUP,
    "formulas": RULE_FORMULAS,
}

# Machine-readable accounting contract. The fingerprint binds the evaluated
# interval definition, position timing, each component formula, transaction-cost
# and turnover definitions, the initial and terminal position semantics, the
# mean denominator, the slot-count definitions, and the position serialization.
ACCOUNTING_CONTRACT = {
    "schema_version": SCHEMA_VERSION,
    "transaction_cost": str(TRANSACTION_COST),
    "transaction_cost_rationale": TRANSACTION_COST_RATIONALE,
    "evaluated_interval": "a scenario with N observations has N-1 evaluated intervals indexed t = 0..N-2; interval t spans observations t and t+1",
    "position_timing": "position(t) is decided before interval t using only observations with index < t and is held across the whole of interval t",
    "initial_position": "flat: position(-1) = 0 before the first evaluated interval",
    "price_component": "price_component(t) = position(t) * (price[t+1] - price[t])",
    "funding_component": "funding_component(t) = -position(t) * funding[t]",
    "transaction_cost_formula": "cost(t) = transaction_cost * abs(position(t) - position(t-1)) with position(-1) = 0",
    "net": "net(t) = price_component(t) + funding_component(t) - cost(t)",
    "turnover_definition": "turnover_count = number of evaluated intervals t where position(t) != position(t-1), with position(-1) = 0",
    "terminal_liquidation": "excluded: the position held over the final evaluated interval is not flattened at the end and incurs no terminal closing transaction cost",
    "mean_denominator": "every mean divides the summed component by the evaluated-interval count (N-1)",
    "active_slot_count": "number of evaluated intervals whose position is in {-1, 1}",
    "long_slot_count": "number of evaluated intervals whose position == 1",
    "short_slot_count": "number of evaluated intervals whose position == -1",
    "flat_slot_count": "number of evaluated intervals whose position == 0",
    "count_invariants": [
        "active_slot_count == long_slot_count + short_slot_count",
        "active_slot_count + flat_slot_count == evaluated_interval_count",
    ],
    "position_series_serialization": "position_series_sha256 = sha256(canonical_json_bytes(list_of_integer_positions))",
    "components": [
        "active_slot_count", "long_slot_count", "short_slot_count", "flat_slot_count",
        "turnover_count", "mean_price_component", "mean_funding_component",
        "mean_cost_drag", "mean_net", "position_series_sha256",
    ],
}


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
            if set(parameters) != expected or type(parameters.get("lookback")) is not int or not LOOKBACK_MIN <= parameters["lookback"] <= LOOKBACK_MAX:
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
    try:
        data = path.read_bytes()
    except FileNotFoundError as exc:
        raise SandboxInputError(f"variant bundle not found: {path}") from exc
    except OSError as exc:
        raise SandboxInputError(f"cannot read variant bundle {path}: {exc}") from exc
    try:
        parsed = parse_json_bytes(data, "variant bundle")
        bundle = validate_bundle(parsed)
    except SandboxValidationError as exc:
        raise SandboxInputError(str(exc)) from exc
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
    long_count = positions.count(1)
    short_count = positions.count(-1)
    flat_count = positions.count(0)
    def avg(values: list[Decimal]) -> str:
        return str(sum(values, Decimal(0)) / len(values))
    series = canonical_json_bytes(positions)
    return {"active_slot_count": long_count + short_count, "flat_slot_count": flat_count, "long_slot_count": long_count,
            "mean_cost_drag": avg(costs), "mean_funding_component": avg(funding_components), "mean_net": avg(nets),
            "mean_price_component": avg(price_components), "position_series_sha256": hashlib.sha256(series).hexdigest(),
            "scenario_id": scenario["scenario_id"], "short_slot_count": short_count,
            "turnover_count": sum(1 for i in range(len(positions)) if positions[i] != (positions[i-1] if i else 0)),
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


_RECEIPT_KEYS = {"schema_version", "receipt_kind", "sandbox_id", "sandbox_status", "scientific_evidence", "edge_claim_authorized",
                 "official_v1_protocol", "real_data_accessed", "selection_performed", "all_variants_included", "explored_variant_count",
                 "raw_input_sha256", "canonical_bundle_sha256", "variant_bundle", "scenario_contract_sha256", "rule_contract_sha256",
                 "accounting_contract_sha256", "results", "run_fingerprint"}
_RECEIPT_SHA_FIELDS = ("raw_input_sha256", "canonical_bundle_sha256", "scenario_contract_sha256", "rule_contract_sha256", "accounting_contract_sha256", "run_fingerprint")


def verify_receipt_bytes(data: bytes) -> dict[str, Any]:
    try:
        parsed = parse_json_bytes(data, "receipt")
    except SandboxValidationError as exc:
        raise SandboxVerificationError(str(exc)) from exc
    if data != canonical_json_bytes(parsed):
        raise SandboxVerificationError("receipt is not canonical QNTY JSON")
    if type(parsed) is not dict or set(parsed) != _RECEIPT_KEYS:
        actual = set(parsed) if type(parsed) is dict else set()
        raise SandboxVerificationError(f"receipt keys mismatch (missing={sorted(_RECEIPT_KEYS-actual)} extra={sorted(actual-_RECEIPT_KEYS)})")
    for key, value in {"schema_version": SCHEMA_VERSION, "receipt_kind": RECEIPT_KIND, "sandbox_id": SANDBOX_ID, "sandbox_status": SANDBOX_STATUS}.items():
        if parsed[key] != value: raise SandboxVerificationError(f"receipt {key} is wrong")
    for key in ("scientific_evidence", "edge_claim_authorized", "official_v1_protocol", "real_data_accessed", "selection_performed"):
        if parsed[key] is not False: raise SandboxVerificationError(f"receipt {key} must be false")
    if parsed["all_variants_included"] is not True: raise SandboxVerificationError("all_variants_included must be true")
    for field in _RECEIPT_SHA_FIELDS:
        _require_hex_sha(parsed[field], field)
    try:
        bundle = validate_bundle(parsed["variant_bundle"])
    except SandboxValidationError as exc:
        raise SandboxVerificationError(f"embedded variant bundle invalid: {exc}") from exc
    if parsed["explored_variant_count"] != len(bundle["variants"]): raise SandboxVerificationError("explored variant count mismatch")
    if parsed["canonical_bundle_sha256"] != _canonical_digest(bundle): raise SandboxVerificationError("canonical bundle fingerprint mismatch")
    if parsed["scenario_contract_sha256"] != _canonical_digest(SCENARIO_CONTRACT) or parsed["rule_contract_sha256"] != _canonical_digest(RULE_CONTRACT) or parsed["accounting_contract_sha256"] != _canonical_digest(ACCOUNTING_CONTRACT): raise SandboxVerificationError("contract fingerprint mismatch")
    if type(parsed["results"]) is not list: raise SandboxVerificationError("results must be a list")
    for result in parsed["results"]:
        if type(result) is not dict or "position_series_sha256" not in result: raise SandboxVerificationError("result is missing position_series_sha256")
        _require_hex_sha(result["position_series_sha256"], "result position_series_sha256")
    expected_results = sorted((_result(v, s) for v in bundle["variants"] for s in SCENARIOS), key=lambda x: (x["variant_id"], x["scenario_id"]))
    if parsed["results"] != expected_results: raise SandboxVerificationError("receipt results do not replay exactly")
    unsigned = dict(parsed); unsigned.pop("run_fingerprint")
    if parsed["run_fingerprint"] != _canonical_digest(unsigned): raise SandboxVerificationError("run fingerprint mismatch")
    return parsed


def _fsync_dir(path: Path) -> None:
    """Fsync a directory where the platform supports it; ignore where it does not."""
    try:
        fd = os.open(path, os.O_RDONLY)
    except OSError:
        return
    try:
        os.fsync(fd)
    except OSError:
        pass  # directory fsync is unsupported on some platforms
    finally:
        os.close(fd)


def _publish_bytes(out: Path, data: bytes) -> None:
    """Atomically publish canonical bytes to *out* with no-overwrite semantics.

    Requires the parent directory to already exist and refuses if the
    destination exists. Writes to a uniquely named temporary file in the same
    directory, flushes and fsyncs it, publishes to the final path via an atomic
    hard link that fails if the destination exists, fsyncs the directory where
    supported, then verifies the published bytes. The temporary file is removed
    on success or failure, and any final file this call created is removed if a
    later step fails, so no partial or unverified destination is ever left.
    """
    parent = out.parent
    if not parent.is_dir():
        raise SandboxPublicationError(f"output parent directory does not exist: {parent}")
    if out.exists():
        raise SandboxPublicationError(f"output path already exists: {out}")
    tmp = parent / f".{out.name}.{os.getpid()}.{secrets.token_hex(8)}.tmp"
    published = False
    try:
        try:
            fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        except OSError as exc:
            raise SandboxPublicationError(f"cannot create temporary output {tmp}: {exc}") from exc
        try:
            with os.fdopen(fd, "wb") as handle:
                handle.write(data)
                handle.flush()
                os.fsync(handle.fileno())
        except OSError as exc:
            raise SandboxPublicationError(f"cannot write temporary output: {exc}") from exc
        try:
            os.link(tmp, out)
        except FileExistsError as exc:
            raise SandboxPublicationError(f"output path already exists: {out}") from exc
        except OSError as exc:
            raise SandboxPublicationError(f"cannot publish output {out}: {exc}") from exc
        published = True
        _fsync_dir(parent)
        if out.read_bytes() != data:
            raise SandboxPublicationError("published bytes do not match the canonical receipt")
    except BaseException:
        if published:
            with contextlib.suppress(OSError):
                os.unlink(out)
        raise
    finally:
        with contextlib.suppress(OSError):
            os.unlink(tmp)


def run_bundle(path: Path, out: Path) -> tuple[dict[str, Any], str]:
    bundle, raw_sha, bundle_sha = load_bundle(path)
    receipt = build_receipt(bundle, raw_sha, bundle_sha)
    data = canonical_json_bytes(receipt)
    _publish_bytes(out, data)
    return receipt, hashlib.sha256(data).hexdigest()
