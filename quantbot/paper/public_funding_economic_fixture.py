"""Public funding economic reconstruction fixture.

This module is an additive Decimal-only path for one bounded public funding
fixture. It does not read or write SQLite and does not interact with paper
engine accounting.
"""

from __future__ import annotations

import argparse
import json
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation, localcontext
from enum import Enum
from pathlib import Path
from typing import Any, Mapping, Sequence

from quantbot.core.determinism import canonical_json_dumps, sha256_file

RECEIPT_VERSION = "PUBLIC_ECONOMIC_RECONSTRUCTION_RECEIPT_V0"
FORMULA_VERSION = "PUBLIC_FUNDING_ECONOMIC_FORMULA_V0"
CLAIM_VERDICT = "PROVEN_FOR_PINNED_FIXTURE"
SUCCESS_VERDICT = "PUBLIC_ECONOMIC_FIXTURE_V0_VERIFIED"

CLAIM_SCOPE = "HYPOTHETICAL_PUBLIC_FUNDING_ECONOMIC_RECONSTRUCTION_ONLY"
EVIDENCE_LEVEL = "AUTHORITATIVE_PUBLIC_EVENT_PLUS_SYNTHETIC_POSITION"
PRECISION_STATUS = "EXACT_DECIMAL_ECONOMIC_AMOUNT"
ACCOUNT_POSTING_STATUS = "ACCOUNT_POSTING_NOT_APPLICABLE_NO_REAL_POSITION"
RESEARCH_STATE_POLICY = "DO_NOT_REGISTER_AS_CANDIDATE_TRIAL_OR_DECISION"
IMPLEMENTATION_OWNER = "QNTY"

REQUIRED_NON_CLAIMS = (
    "not an account receipt",
    "not a real wallet posting",
    "not a real position",
    "not a real trade",
    "not evidence of execution",
    "not evidence of a spot hedge",
    "not evidence of capital efficiency",
    "not evidence of margin survival",
    "not evidence of liquidation survival",
    "not evidence about ADL",
    "not evidence of profitability",
    "not evidence of alpha",
    "not a strategy trial",
    "not a research candidate",
)

FORBIDDEN_SCOPE_FIELDS = frozenset(
    {
        "profitability",
        "alpha",
        "strategy_authorization",
        "candidate_authorization",
        "trial_authorization",
        "wallet_balance",
        "account_receipt",
        "real_position",
        "real_trade",
    }
)


class PublicEconomicFixtureReason(str, Enum):
    SOURCE_FIXTURE_MISSING = "SOURCE_FIXTURE_MISSING"
    SOURCE_HASH_MISMATCH = "SOURCE_HASH_MISMATCH"
    SOURCE_EVENT_NOT_FOUND = "SOURCE_EVENT_NOT_FOUND"
    EVENT_IDENTITY_MISMATCH = "EVENT_IDENTITY_MISMATCH"
    SYMBOL_MISMATCH = "SYMBOL_MISMATCH"
    MARK_PRICE_MISSING = "MARK_PRICE_MISSING"
    MARK_PRICE_NON_POSITIVE = "MARK_PRICE_NON_POSITIVE"
    FUNDING_RATE_INVALID = "FUNDING_RATE_INVALID"
    FUNDING_TIME_INVALID = "FUNDING_TIME_INVALID"
    RATE_TYPE_INVALID = "RATE_TYPE_INVALID"
    QUANTITY_INVALID = "QUANTITY_INVALID"
    QUANTITY_UNIT_UNRESOLVED = "QUANTITY_UNIT_UNRESOLVED"
    CONTRACT_MULTIPLIER_UNRESOLVED = "CONTRACT_MULTIPLIER_UNRESOLVED"
    SIGN_CONVENTION_UNRESOLVED = "SIGN_CONVENTION_UNRESOLVED"
    NUMERIC_POLICY_VIOLATION = "NUMERIC_POLICY_VIOLATION"
    DUPLICATE_APPLICATION = "DUPLICATE_APPLICATION"
    RECEIPT_IDENTITY_MISMATCH = "RECEIPT_IDENTITY_MISMATCH"
    CALCULATED_NOTIONAL_MISMATCH = "CALCULATED_NOTIONAL_MISMATCH"
    CALCULATED_TRANSFER_MISMATCH = "CALCULATED_TRANSFER_MISMATCH"
    QNTY_EXTENSION_BOUNDARY_UNSAFE = "QNTY_EXTENSION_BOUNDARY_UNSAFE"


class PublicEconomicFixtureError(ValueError):
    """Typed local failure for the bounded fixture."""

    def __init__(self, reason: PublicEconomicFixtureReason, detail: str = "") -> None:
        self.reason = reason
        message = reason.value if not detail else f"{reason.value}: {detail}"
        super().__init__(message)


@dataclass(frozen=True)
class PublicFundingEvent:
    venue: str
    market: str
    symbol: str
    funding_time: int
    funding_time_utc: str
    funding_rate: str
    funding_mark_price: str
    rate_type: str
    source_event_identity: Mapping[str, Any]


@dataclass(frozen=True)
class SyntheticPosition:
    signed_position_quantity: str
    quantity_unit: str
    contract_multiplier: str


@dataclass(frozen=True)
class ParsedPublicEconomicFixture:
    contract_id: str
    contract_version: str
    claim_scope: str
    source_raw_sha256: str
    source_selected_event_sha256: str
    source_receipt_sha256: str
    event: PublicFundingEvent
    position: SyntheticPosition
    numeric_policy: str
    sign_convention: str
    required_non_claims: tuple[str, ...]
    source_artifacts: Mapping[str, str]


def canonical_receipt_bytes(receipt: Mapping[str, Any]) -> bytes:
    return canonical_json_dumps(receipt).encode("utf-8")


def receipt_sha256(receipt: Mapping[str, Any]) -> str:
    return _sha256_bytes(canonical_receipt_bytes(receipt))


def parse_fixture(
    fixture_path: str | Path,
    *,
    source_root: str | Path | None = None,
    verify_source: bool = True,
) -> ParsedPublicEconomicFixture:
    path = Path(fixture_path)
    if not path.is_file():
        raise PublicEconomicFixtureError(
            PublicEconomicFixtureReason.SOURCE_FIXTURE_MISSING, str(path)
        )
    fixture = _load_json(path)
    _reject_boundary_fields(fixture)

    source_event_identity = _expect_mapping(fixture, "source_event_identity")
    selected_hash = _expect_str(fixture, "source_selected_event_sha256")
    if source_event_identity.get("selected_event_sha256") != selected_hash:
        raise PublicEconomicFixtureError(
            PublicEconomicFixtureReason.EVENT_IDENTITY_MISMATCH,
            "selected-event hash differs from source event identity",
        )

    event = PublicFundingEvent(
        venue=_expect_str(fixture, "venue"),
        market=_expect_str(fixture, "market"),
        symbol=_expect_str(fixture, "symbol"),
        funding_time=_expect_int(fixture, "funding_time"),
        funding_time_utc=_expect_str(fixture, "funding_time_utc"),
        funding_rate=_expect_str(fixture, "funding_rate"),
        funding_mark_price=_expect_str(fixture, "funding_mark_price"),
        rate_type=_expect_str(fixture, "rate_type"),
        source_event_identity=dict(source_event_identity),
    )
    position = SyntheticPosition(
        signed_position_quantity=_expect_str(fixture, "signed_position_quantity"),
        quantity_unit=_expect_str(fixture, "quantity_unit"),
        contract_multiplier=_expect_str(fixture, "contract_multiplier"),
    )
    parsed = ParsedPublicEconomicFixture(
        contract_id=_expect_str(fixture, "contract_id"),
        contract_version=_expect_str(fixture, "contract_version"),
        claim_scope=_expect_str(fixture, "claim_scope"),
        source_raw_sha256=_expect_str(fixture, "source_raw_sha256"),
        source_selected_event_sha256=selected_hash,
        source_receipt_sha256=_expect_str(fixture, "source_receipt_sha256"),
        event=event,
        position=position,
        numeric_policy=_expect_str(fixture, "numeric_policy"),
        sign_convention=_expect_str(fixture, "sign_convention"),
        required_non_claims=tuple(_expect_str_list(fixture, "required_non_claims")),
        source_artifacts=dict(_expect_mapping(fixture, "source_artifacts")),
    )
    _validate_fixture(parsed)
    if verify_source:
        verify_source_artifacts(parsed, source_root=source_root)
    return parsed


def verify_source_artifacts(
    fixture: ParsedPublicEconomicFixture,
    *,
    source_root: str | Path | None = None,
) -> None:
    root = _default_source_root() if source_root is None else Path(source_root)
    artifacts = fixture.source_artifacts
    raw_path = root / _expect_artifact(artifacts, "raw")
    selected_path = root / _expect_artifact(artifacts, "selected_event")
    receipt_path = root / _expect_artifact(artifacts, "source_receipt")
    for path in (raw_path, selected_path, receipt_path):
        if not path.is_file():
            raise PublicEconomicFixtureError(
                PublicEconomicFixtureReason.SOURCE_FIXTURE_MISSING, str(path)
            )
    expected = {
        raw_path: fixture.source_raw_sha256,
        selected_path: fixture.source_selected_event_sha256,
        receipt_path: fixture.source_receipt_sha256,
    }
    for path, digest in expected.items():
        if sha256_file(path) != digest:
            raise PublicEconomicFixtureError(
                PublicEconomicFixtureReason.SOURCE_HASH_MISMATCH, str(path)
            )

    raw = _load_json(raw_path)
    selected = _load_json(selected_path)
    source_receipt = _load_json(receipt_path)
    _verify_selected_event_from_raw(fixture, raw, selected)
    _verify_source_receipt(fixture, source_receipt)


def reconstruct_transfer(
    fixture: ParsedPublicEconomicFixture,
) -> dict[str, Any]:
    _validate_fixture(fixture)
    with localcontext() as ctx:
        ctx.prec = 50
        quantity = _decimal_from_string(
            fixture.position.signed_position_quantity,
            PublicEconomicFixtureReason.QUANTITY_INVALID,
        )
        mark = _decimal_from_string(
            fixture.event.funding_mark_price,
            PublicEconomicFixtureReason.MARK_PRICE_MISSING,
        )
        rate = _decimal_from_string(
            fixture.event.funding_rate,
            PublicEconomicFixtureReason.FUNDING_RATE_INVALID,
        )
        multiplier = _decimal_from_string(
            fixture.position.contract_multiplier,
            PublicEconomicFixtureReason.CONTRACT_MULTIPLIER_UNRESOLVED,
        )
        if mark <= 0:
            raise PublicEconomicFixtureError(
                PublicEconomicFixtureReason.MARK_PRICE_NON_POSITIVE
            )
        notional = abs(quantity) * mark * multiplier
        transfer = -quantity * mark * rate * multiplier

    identity_payload = _identity_payload(
        fixture,
        signed_position_quantity=fixture.position.signed_position_quantity,
    )
    receipt_id = _sha256_bytes(canonical_json_dumps(identity_payload).encode("utf-8"))
    direction = _transfer_direction(transfer)
    receipt = {
        "receipt_id": receipt_id,
        "receipt_version": RECEIPT_VERSION,
        "contract_id": fixture.contract_id,
        "contract_version": fixture.contract_version,
        "claim_scope": fixture.claim_scope,
        "evidence_level": EVIDENCE_LEVEL,
        "source_event_identity": dict(fixture.event.source_event_identity),
        "source_raw_sha256": fixture.source_raw_sha256,
        "source_selected_event_sha256": fixture.source_selected_event_sha256,
        "source_receipt_sha256": fixture.source_receipt_sha256,
        "venue": fixture.event.venue,
        "market": fixture.event.market,
        "symbol": fixture.event.symbol,
        "funding_time": fixture.event.funding_time,
        "funding_time_utc": fixture.event.funding_time_utc,
        "funding_rate": fixture.event.funding_rate,
        "funding_mark_price": fixture.event.funding_mark_price,
        "rate_type": fixture.event.rate_type,
        "signed_position_quantity": fixture.position.signed_position_quantity,
        "quantity_unit": fixture.position.quantity_unit,
        "contract_multiplier": fixture.position.contract_multiplier,
        "formula_version": FORMULA_VERSION,
        "notional_formula": "abs(signed_position_quantity) * funding_mark_price * contract_multiplier",
        "transfer_formula": "-signed_position_quantity * funding_mark_price * finalized_funding_rate * contract_multiplier",
        "sign_convention": fixture.sign_convention,
        "numeric_policy": fixture.numeric_policy,
        "precision_status": PRECISION_STATUS,
        "calculated_notional": _decimal_to_string(notional),
        "calculated_transfer": _decimal_to_string(transfer),
        "transfer_direction": direction,
        "account_posting_status": ACCOUNT_POSTING_STATUS,
        "implementation_owner": IMPLEMENTATION_OWNER,
        "research_state_policy": RESEARCH_STATE_POLICY,
        "non_claims": list(fixture.required_non_claims),
        "verification": {
            "claim_scope": fixture.claim_scope,
            "claim_verdict": CLAIM_VERDICT,
            "reason_codes": [],
            "source_hashes_verified": True,
            "source_event_identity_verified": True,
            "arithmetic_verified": True,
            "account_posting": "NOT_APPLICABLE",
        },
    }
    verify_receipt(fixture, receipt)
    return receipt


def verify_receipt(
    fixture: ParsedPublicEconomicFixture,
    receipt: Mapping[str, Any],
) -> dict[str, Any]:
    _reject_boundary_fields(receipt)
    expected = _receipt_without_self_verification_drift(reconstruct=False, fixture=fixture)
    for key, value in expected.items():
        if receipt.get(key) != value:
            reason = _reason_for_field(key)
            raise PublicEconomicFixtureError(reason, key)

    with localcontext() as ctx:
        ctx.prec = 50
        quantity = _decimal_from_string(
            fixture.position.signed_position_quantity,
            PublicEconomicFixtureReason.QUANTITY_INVALID,
        )
        mark = _decimal_from_string(
            fixture.event.funding_mark_price,
            PublicEconomicFixtureReason.MARK_PRICE_MISSING,
        )
        rate = _decimal_from_string(
            fixture.event.funding_rate,
            PublicEconomicFixtureReason.FUNDING_RATE_INVALID,
        )
        multiplier = _decimal_from_string(
            fixture.position.contract_multiplier,
            PublicEconomicFixtureReason.CONTRACT_MULTIPLIER_UNRESOLVED,
        )
        notional = abs(quantity) * mark * multiplier
        transfer = -quantity * mark * rate * multiplier

    expected_id = _sha256_bytes(
        canonical_json_dumps(
            _identity_payload(
                fixture,
                signed_position_quantity=fixture.position.signed_position_quantity,
            )
        ).encode("utf-8")
    )
    if receipt.get("receipt_id") != expected_id:
        raise PublicEconomicFixtureError(
            PublicEconomicFixtureReason.RECEIPT_IDENTITY_MISMATCH
        )
    if receipt.get("calculated_notional") != _decimal_to_string(notional):
        raise PublicEconomicFixtureError(
            PublicEconomicFixtureReason.CALCULATED_NOTIONAL_MISMATCH
        )
    if receipt.get("calculated_transfer") != _decimal_to_string(transfer):
        raise PublicEconomicFixtureError(
            PublicEconomicFixtureReason.CALCULATED_TRANSFER_MISMATCH
        )
    if receipt.get("transfer_direction") != _transfer_direction(transfer):
        raise PublicEconomicFixtureError(
            PublicEconomicFixtureReason.CALCULATED_TRANSFER_MISMATCH
        )
    verification = receipt.get("verification")
    if not isinstance(verification, Mapping):
        raise PublicEconomicFixtureError(
            PublicEconomicFixtureReason.RECEIPT_IDENTITY_MISMATCH,
            "verification missing",
        )
    if verification.get("claim_scope") != CLAIM_SCOPE:
        raise PublicEconomicFixtureError(
            PublicEconomicFixtureReason.RECEIPT_IDENTITY_MISMATCH,
            "verification claim scope mismatch",
        )
    if verification.get("claim_verdict") != CLAIM_VERDICT:
        raise PublicEconomicFixtureError(
            PublicEconomicFixtureReason.RECEIPT_IDENTITY_MISMATCH,
            "verification claim verdict mismatch",
        )
    return {"claim_scope": CLAIM_SCOPE, "claim_verdict": CLAIM_VERDICT}


def verify_receipt_batch(
    fixture: ParsedPublicEconomicFixture,
    receipts: Sequence[Mapping[str, Any]],
) -> dict[str, Any]:
    seen: set[str] = set()
    for receipt in receipts:
        verify_receipt(fixture, receipt)
        receipt_id = _expect_str(receipt, "receipt_id")
        if receipt_id in seen:
            raise PublicEconomicFixtureError(
                PublicEconomicFixtureReason.DUPLICATE_APPLICATION, receipt_id
            )
        seen.add(receipt_id)
    return {
        "claim_scope": CLAIM_SCOPE,
        "claim_verdict": CLAIM_VERDICT,
        "receipt_count": len(receipts),
    }


def fixture_with_quantity(
    fixture: ParsedPublicEconomicFixture,
    signed_position_quantity: str,
) -> ParsedPublicEconomicFixture:
    if not isinstance(signed_position_quantity, str):
        raise PublicEconomicFixtureError(PublicEconomicFixtureReason.QUANTITY_INVALID)
    return ParsedPublicEconomicFixture(
        contract_id=fixture.contract_id,
        contract_version=fixture.contract_version,
        claim_scope=fixture.claim_scope,
        source_raw_sha256=fixture.source_raw_sha256,
        source_selected_event_sha256=fixture.source_selected_event_sha256,
        source_receipt_sha256=fixture.source_receipt_sha256,
        event=fixture.event,
        position=SyntheticPosition(
            signed_position_quantity=signed_position_quantity,
            quantity_unit=fixture.position.quantity_unit,
            contract_multiplier=fixture.position.contract_multiplier,
        ),
        numeric_policy=fixture.numeric_policy,
        sign_convention=fixture.sign_convention,
        required_non_claims=fixture.required_non_claims,
        source_artifacts=fixture.source_artifacts,
    )


def _receipt_without_self_verification_drift(
    *,
    reconstruct: bool,
    fixture: ParsedPublicEconomicFixture,
) -> dict[str, Any]:
    if reconstruct:
        return reconstruct_transfer(fixture)
    return {
        "receipt_version": RECEIPT_VERSION,
        "contract_id": fixture.contract_id,
        "contract_version": fixture.contract_version,
        "claim_scope": fixture.claim_scope,
        "evidence_level": EVIDENCE_LEVEL,
        "source_event_identity": dict(fixture.event.source_event_identity),
        "source_raw_sha256": fixture.source_raw_sha256,
        "source_selected_event_sha256": fixture.source_selected_event_sha256,
        "source_receipt_sha256": fixture.source_receipt_sha256,
        "venue": fixture.event.venue,
        "market": fixture.event.market,
        "symbol": fixture.event.symbol,
        "funding_time": fixture.event.funding_time,
        "funding_time_utc": fixture.event.funding_time_utc,
        "funding_rate": fixture.event.funding_rate,
        "funding_mark_price": fixture.event.funding_mark_price,
        "rate_type": fixture.event.rate_type,
        "signed_position_quantity": fixture.position.signed_position_quantity,
        "quantity_unit": fixture.position.quantity_unit,
        "contract_multiplier": fixture.position.contract_multiplier,
        "formula_version": FORMULA_VERSION,
        "notional_formula": "abs(signed_position_quantity) * funding_mark_price * contract_multiplier",
        "transfer_formula": "-signed_position_quantity * funding_mark_price * finalized_funding_rate * contract_multiplier",
        "sign_convention": fixture.sign_convention,
        "numeric_policy": fixture.numeric_policy,
        "precision_status": PRECISION_STATUS,
        "account_posting_status": ACCOUNT_POSTING_STATUS,
        "implementation_owner": IMPLEMENTATION_OWNER,
        "research_state_policy": RESEARCH_STATE_POLICY,
        "non_claims": list(fixture.required_non_claims),
    }


def _validate_fixture(fixture: ParsedPublicEconomicFixture) -> None:
    if fixture.claim_scope != CLAIM_SCOPE:
        raise PublicEconomicFixtureError(
            PublicEconomicFixtureReason.EVENT_IDENTITY_MISMATCH, "claim scope"
        )
    if fixture.event.symbol != fixture.event.source_event_identity.get("symbol"):
        raise PublicEconomicFixtureError(PublicEconomicFixtureReason.SYMBOL_MISMATCH)
    if fixture.event.funding_time != fixture.event.source_event_identity.get("fundingTime"):
        raise PublicEconomicFixtureError(
            PublicEconomicFixtureReason.FUNDING_TIME_INVALID
        )
    if fixture.event.funding_time_utc != fixture.event.source_event_identity.get(
        "fundingTimeUtc"
    ):
        raise PublicEconomicFixtureError(
            PublicEconomicFixtureReason.EVENT_IDENTITY_MISMATCH
        )
    if fixture.event.rate_type != "Regular":
        raise PublicEconomicFixtureError(PublicEconomicFixtureReason.RATE_TYPE_INVALID)
    if fixture.position.quantity_unit != "BTC":
        raise PublicEconomicFixtureError(
            PublicEconomicFixtureReason.QUANTITY_UNIT_UNRESOLVED
        )
    if fixture.position.contract_multiplier != "1":
        raise PublicEconomicFixtureError(
            PublicEconomicFixtureReason.CONTRACT_MULTIPLIER_UNRESOLVED
        )
    if "positive signed quantity is long" not in fixture.sign_convention:
        raise PublicEconomicFixtureError(
            PublicEconomicFixtureReason.SIGN_CONVENTION_UNRESOLVED
        )
    if fixture.numeric_policy != "Decimal strings, context precision 50, no binary float":
        raise PublicEconomicFixtureError(
            PublicEconomicFixtureReason.NUMERIC_POLICY_VIOLATION
        )
    for claim in REQUIRED_NON_CLAIMS:
        if claim not in fixture.required_non_claims:
            raise PublicEconomicFixtureError(
                PublicEconomicFixtureReason.QNTY_EXTENSION_BOUNDARY_UNSAFE, claim
            )
    with localcontext() as ctx:
        ctx.prec = 50
        _decimal_from_string(
            fixture.position.signed_position_quantity,
            PublicEconomicFixtureReason.QUANTITY_INVALID,
        )
        mark = _decimal_from_string(
            fixture.event.funding_mark_price,
            PublicEconomicFixtureReason.MARK_PRICE_MISSING,
        )
        _decimal_from_string(
            fixture.event.funding_rate,
            PublicEconomicFixtureReason.FUNDING_RATE_INVALID,
        )
        _decimal_from_string(
            fixture.position.contract_multiplier,
            PublicEconomicFixtureReason.CONTRACT_MULTIPLIER_UNRESOLVED,
        )
    if mark <= 0:
        raise PublicEconomicFixtureError(
            PublicEconomicFixtureReason.MARK_PRICE_NON_POSITIVE
        )


def _verify_selected_event_from_raw(
    fixture: ParsedPublicEconomicFixture,
    raw: Any,
    selected: Mapping[str, Any],
) -> None:
    if not isinstance(raw, list):
        raise PublicEconomicFixtureError(
            PublicEconomicFixtureReason.SOURCE_EVENT_NOT_FOUND, "raw not array"
        )
    index = fixture.event.source_event_identity.get("source_array_index")
    if not isinstance(index, int) or index < 0 or index >= len(raw):
        raise PublicEconomicFixtureError(PublicEconomicFixtureReason.SOURCE_EVENT_NOT_FOUND)
    raw_event = raw[index]
    if not isinstance(raw_event, Mapping):
        raise PublicEconomicFixtureError(PublicEconomicFixtureReason.SOURCE_EVENT_NOT_FOUND)
    expected_selected = {
        "symbol": fixture.event.symbol,
        "fundingTime": fixture.event.funding_time,
        "fundingTimeUtc": fixture.event.funding_time_utc,
        "fundingRate": fixture.event.funding_rate,
        "markPrice": fixture.event.funding_mark_price,
        "rateType": fixture.event.rate_type,
        "source_array_index": index,
    }
    for key, expected in expected_selected.items():
        if selected.get(key) != expected:
            raise PublicEconomicFixtureError(
                _reason_for_source_key(key), f"selected {key}"
            )
    for key in ("symbol", "fundingTime", "fundingRate", "markPrice", "rateType"):
        if raw_event.get(key) != selected.get(key):
            raise PublicEconomicFixtureError(_reason_for_source_key(key), f"raw {key}")
    if not isinstance(raw_event.get("fundingRate"), str) or not isinstance(
        raw_event.get("markPrice"), str
    ):
        raise PublicEconomicFixtureError(
            PublicEconomicFixtureReason.NUMERIC_POLICY_VIOLATION,
            "source decimals must remain strings",
        )


def _verify_source_receipt(
    fixture: ParsedPublicEconomicFixture, source_receipt: Mapping[str, Any]
) -> None:
    artifact_hashes = source_receipt.get("artifact_hashes")
    if not isinstance(artifact_hashes, Mapping):
        raise PublicEconomicFixtureError(
            PublicEconomicFixtureReason.EVENT_IDENTITY_MISMATCH,
            "source receipt missing artifact hashes",
        )
    raw_name = "docs/forensics/evidence/binance_public_funding_event_v0/BTCUSDT-fundingRate-2026-06.raw.json"
    selected_name = "docs/forensics/evidence/binance_public_funding_event_v0/BTCUSDT-fundingRate-2026-06.selected-event.json"
    if artifact_hashes.get(raw_name) != fixture.source_raw_sha256:
        raise PublicEconomicFixtureError(
            PublicEconomicFixtureReason.SOURCE_HASH_MISMATCH, "source receipt raw"
        )
    if artifact_hashes.get(selected_name) != fixture.source_selected_event_sha256:
        raise PublicEconomicFixtureError(
            PublicEconomicFixtureReason.SOURCE_HASH_MISMATCH,
            "source receipt selected",
        )
    selected_event = source_receipt.get("selected_event")
    if not isinstance(selected_event, Mapping):
        raise PublicEconomicFixtureError(
            PublicEconomicFixtureReason.EVENT_IDENTITY_MISMATCH,
            "source receipt selected event missing",
        )
    expected = {
        "symbol": fixture.event.symbol,
        "fundingTime": fixture.event.funding_time,
        "fundingTimeUtc": fixture.event.funding_time_utc,
        "fundingRate": fixture.event.funding_rate,
        "markPrice": fixture.event.funding_mark_price,
        "rateType": fixture.event.rate_type,
        "source_array_index": fixture.event.source_event_identity.get(
            "source_array_index"
        ),
    }
    for key, value in expected.items():
        if selected_event.get(key) != value:
            raise PublicEconomicFixtureError(_reason_for_source_key(key), key)


def _identity_payload(
    fixture: ParsedPublicEconomicFixture,
    *,
    signed_position_quantity: str,
) -> dict[str, Any]:
    return {
        "contract_id": fixture.contract_id,
        "contract_version": fixture.contract_version,
        "claim_scope": fixture.claim_scope,
        "source_raw_sha256": fixture.source_raw_sha256,
        "source_selected_event_sha256": fixture.source_selected_event_sha256,
        "source_event_identity": dict(fixture.event.source_event_identity),
        "symbol": fixture.event.symbol,
        "funding_time": fixture.event.funding_time,
        "funding_rate": fixture.event.funding_rate,
        "funding_mark_price": fixture.event.funding_mark_price,
        "rate_type": fixture.event.rate_type,
        "signed_position_quantity": signed_position_quantity,
        "quantity_unit": fixture.position.quantity_unit,
        "contract_multiplier": fixture.position.contract_multiplier,
        "formula_version": FORMULA_VERSION,
        "numeric_policy": fixture.numeric_policy,
    }


def _decimal_from_string(value: Any, reason: PublicEconomicFixtureReason) -> Decimal:
    if isinstance(value, float):
        raise PublicEconomicFixtureError(
            PublicEconomicFixtureReason.NUMERIC_POLICY_VIOLATION,
            "binary float rejected",
        )
    if not isinstance(value, str):
        raise PublicEconomicFixtureError(reason, "decimal input must be string")
    try:
        parsed = Decimal(value)
    except InvalidOperation as exc:
        raise PublicEconomicFixtureError(reason, repr(value)) from exc
    if not parsed.is_finite():
        raise PublicEconomicFixtureError(reason, repr(value))
    return parsed


def _decimal_to_string(value: Decimal) -> str:
    if value.is_zero():
        return "0"
    return format(value, "f")


def _transfer_direction(value: Decimal) -> str:
    if value > 0:
        return "RECEIVES"
    if value < 0:
        return "PAYS"
    return "ZERO"


def _load_json(path: Path) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise PublicEconomicFixtureError(
            PublicEconomicFixtureReason.SOURCE_FIXTURE_MISSING, str(path)
        ) from exc


def _expect_mapping(obj: Mapping[str, Any], key: str) -> Mapping[str, Any]:
    value = obj.get(key)
    if not isinstance(value, Mapping):
        raise PublicEconomicFixtureError(
            PublicEconomicFixtureReason.EVENT_IDENTITY_MISMATCH, key
        )
    return value


def _expect_str(obj: Mapping[str, Any], key: str) -> str:
    value = obj.get(key)
    if isinstance(value, float):
        raise PublicEconomicFixtureError(
            PublicEconomicFixtureReason.NUMERIC_POLICY_VIOLATION, key
        )
    if not isinstance(value, str) or value == "":
        raise PublicEconomicFixtureError(_reason_for_field(key), key)
    return value


def _expect_int(obj: Mapping[str, Any], key: str) -> int:
    value = obj.get(key)
    if isinstance(value, bool) or not isinstance(value, int):
        raise PublicEconomicFixtureError(_reason_for_field(key), key)
    return value


def _expect_str_list(obj: Mapping[str, Any], key: str) -> list[str]:
    value = obj.get(key)
    if not isinstance(value, list) or not all(isinstance(item, str) for item in value):
        raise PublicEconomicFixtureError(
            PublicEconomicFixtureReason.QNTY_EXTENSION_BOUNDARY_UNSAFE, key
        )
    return value


def _expect_artifact(artifacts: Mapping[str, Any], key: str) -> str:
    value = artifacts.get(key)
    if not isinstance(value, str) or value.startswith("/"):
        raise PublicEconomicFixtureError(
            PublicEconomicFixtureReason.EVENT_IDENTITY_MISMATCH, key
        )
    return value


def _reason_for_source_key(key: str) -> PublicEconomicFixtureReason:
    return {
        "symbol": PublicEconomicFixtureReason.SYMBOL_MISMATCH,
        "fundingTime": PublicEconomicFixtureReason.FUNDING_TIME_INVALID,
        "fundingTimeUtc": PublicEconomicFixtureReason.EVENT_IDENTITY_MISMATCH,
        "fundingRate": PublicEconomicFixtureReason.FUNDING_RATE_INVALID,
        "markPrice": PublicEconomicFixtureReason.MARK_PRICE_MISSING,
        "rateType": PublicEconomicFixtureReason.RATE_TYPE_INVALID,
        "source_array_index": PublicEconomicFixtureReason.SOURCE_EVENT_NOT_FOUND,
    }.get(key, PublicEconomicFixtureReason.EVENT_IDENTITY_MISMATCH)


def _reason_for_field(key: str) -> PublicEconomicFixtureReason:
    if key == "receipt_id":
        return PublicEconomicFixtureReason.RECEIPT_IDENTITY_MISMATCH
    if key == "symbol":
        return PublicEconomicFixtureReason.SYMBOL_MISMATCH
    if key in {"funding_time", "fundingTime"}:
        return PublicEconomicFixtureReason.FUNDING_TIME_INVALID
    if key in {"funding_rate", "fundingRate"}:
        return PublicEconomicFixtureReason.FUNDING_RATE_INVALID
    if key in {"funding_mark_price", "markPrice"}:
        return PublicEconomicFixtureReason.MARK_PRICE_MISSING
    if key in {"rate_type", "rateType"}:
        return PublicEconomicFixtureReason.RATE_TYPE_INVALID
    if key == "signed_position_quantity":
        return PublicEconomicFixtureReason.QUANTITY_INVALID
    if key == "quantity_unit":
        return PublicEconomicFixtureReason.QUANTITY_UNIT_UNRESOLVED
    if key == "contract_multiplier":
        return PublicEconomicFixtureReason.CONTRACT_MULTIPLIER_UNRESOLVED
    if key == "numeric_policy":
        return PublicEconomicFixtureReason.NUMERIC_POLICY_VIOLATION
    if key == "calculated_notional":
        return PublicEconomicFixtureReason.CALCULATED_NOTIONAL_MISMATCH
    if key == "calculated_transfer":
        return PublicEconomicFixtureReason.CALCULATED_TRANSFER_MISMATCH
    return PublicEconomicFixtureReason.EVENT_IDENTITY_MISMATCH


def _reject_boundary_fields(value: Mapping[str, Any]) -> None:
    found = FORBIDDEN_SCOPE_FIELDS.intersection(value)
    if found:
        raise PublicEconomicFixtureError(
            PublicEconomicFixtureReason.QNTY_EXTENSION_BOUNDARY_UNSAFE,
            ",".join(sorted(found)),
        )


def _sha256_bytes(value: bytes) -> str:
    import hashlib

    return hashlib.sha256(value).hexdigest()


def _default_source_root() -> Path:
    return Path(__file__).resolve().parents[3] / "QntyLab"


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Verify the bounded public funding economic fixture."
    )
    parser.add_argument("--fixture", required=True, type=Path)
    parser.add_argument("--expected-receipt", type=Path)
    parser.add_argument("--source-root", type=Path)
    parser.add_argument("--verify", action="store_true")
    args = parser.parse_args(argv)

    fixture = parse_fixture(args.fixture, source_root=args.source_root, verify_source=True)
    receipt = reconstruct_transfer(fixture)
    expected_path = args.expected_receipt
    if expected_path is None:
        expected_path = args.fixture.with_name("expected_receipt.json")
    if args.verify:
        expected = _load_json(expected_path)
        if canonical_receipt_bytes(receipt) != canonical_receipt_bytes(expected):
            raise PublicEconomicFixtureError(
                PublicEconomicFixtureReason.RECEIPT_IDENTITY_MISMATCH,
                "expected receipt bytes differ",
            )
        verify_receipt(fixture, expected)
    print(
        canonical_json_dumps(
            {
                "verdict": SUCCESS_VERDICT,
                "claim_scope": CLAIM_SCOPE,
                "claim_verdict": CLAIM_VERDICT,
                "receipt_id": receipt["receipt_id"],
                "receipt_sha256": receipt_sha256(receipt),
            }
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
