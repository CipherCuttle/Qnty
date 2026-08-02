from __future__ import annotations

import json
import shutil
import subprocess
import sys
from dataclasses import replace
from decimal import getcontext
from pathlib import Path

import pytest

from quantbot.paper.public_funding_economic_fixture import (
    ACCOUNT_POSTING_STATUS,
    CLAIM_SCOPE,
    PublicEconomicFixtureError,
    PublicEconomicFixtureReason,
    canonical_receipt_bytes,
    fixture_with_quantity,
    parse_fixture,
    receipt_sha256,
    reconstruct_transfer,
    verify_receipt,
    verify_receipt_batch,
    verify_source_artifacts,
)

FIXTURE_PATH = Path("tests/fixtures/public_funding_economic_v0/input.json")
EXPECTED_RECEIPT_PATH = Path(
    "tests/fixtures/public_funding_economic_v0/expected_receipt.json"
)
QNTYLAB_ROOT = Path("/home/swirky/DevHub/repos/QntyLab")


def _fixture(*, verify_source: bool = False):
    return parse_fixture(FIXTURE_PATH, verify_source=verify_source)


def _receipt():
    return reconstruct_transfer(_fixture())


def _assert_reason(exc: pytest.ExceptionInfo[PublicEconomicFixtureError], reason):
    assert exc.value.reason == reason


def _mutated_fixture(tmp_path: Path, **updates):
    data = json.loads(FIXTURE_PATH.read_text())
    data.update(updates)
    path = tmp_path / "input.json"
    path.write_text(json.dumps(data, sort_keys=True), encoding="utf-8")
    return path


def _source_copy(tmp_path: Path) -> Path:
    source_dir = QNTYLAB_ROOT / "docs/forensics/evidence/binance_public_funding_event_v0"
    target = tmp_path / "docs/forensics/evidence/binance_public_funding_event_v0"
    target.mkdir(parents=True)
    for name in (
        "BTCUSDT-fundingRate-2026-06.raw.json",
        "BTCUSDT-fundingRate-2026-06.selected-event.json",
        "BTCUSDT-fundingRate-2026-06.receipt.json",
    ):
        shutil.copy2(source_dir / name, target / name)
    return tmp_path


def _write_json(path: Path, value) -> None:
    path.write_text(json.dumps(value, sort_keys=True), encoding="utf-8")


def test_golden_arithmetic_vectors_are_exact() -> None:
    fixture = _fixture()

    long_receipt = reconstruct_transfer(fixture_with_quantity(fixture, "0.001"))
    short_receipt = reconstruct_transfer(fixture_with_quantity(fixture, "-0.001"))
    zero_receipt = reconstruct_transfer(fixture_with_quantity(fixture, "0"))

    assert long_receipt["calculated_notional"] == "73.65356663043"
    assert long_receipt["calculated_transfer"] == "-0.0042004629049334229"
    assert long_receipt["transfer_direction"] == "PAYS"
    assert short_receipt["calculated_notional"] == "73.65356663043"
    assert short_receipt["calculated_transfer"] == "0.0042004629049334229"
    assert short_receipt["transfer_direction"] == "RECEIVES"
    assert zero_receipt["calculated_notional"] == "0"
    assert zero_receipt["calculated_transfer"] == "0"
    assert zero_receipt["transfer_direction"] == "ZERO"
    assert short_receipt["calculated_transfer"] == long_receipt[
        "calculated_transfer"
    ].removeprefix("-")


@pytest.mark.parametrize(
    ("updates", "reason"),
    [
        ({"funding_rate": 0.00005703}, PublicEconomicFixtureReason.NUMERIC_POLICY_VIOLATION),
        ({"funding_rate": "not-decimal"}, PublicEconomicFixtureReason.FUNDING_RATE_INVALID),
        ({"funding_rate": "NaN"}, PublicEconomicFixtureReason.FUNDING_RATE_INVALID),
        ({"funding_rate": "Infinity"}, PublicEconomicFixtureReason.FUNDING_RATE_INVALID),
        ({"funding_mark_price": "-1"}, PublicEconomicFixtureReason.MARK_PRICE_NON_POSITIVE),
        ({"funding_mark_price": "0"}, PublicEconomicFixtureReason.MARK_PRICE_NON_POSITIVE),
        ({"signed_position_quantity": "NaN"}, PublicEconomicFixtureReason.QUANTITY_INVALID),
    ],
)
def test_numeric_safety_rejects_invalid_inputs(tmp_path: Path, updates, reason) -> None:
    with pytest.raises(PublicEconomicFixtureError) as exc:
        parse_fixture(_mutated_fixture(tmp_path, **updates), verify_source=False)
    _assert_reason(exc, reason)


def test_global_decimal_context_is_unchanged() -> None:
    before = getcontext().copy()
    reconstruct_transfer(_fixture())
    after = getcontext()
    assert after.prec == before.prec
    assert after.rounding == before.rounding
    assert after.Emax == before.Emax
    assert after.Emin == before.Emin


@pytest.mark.parametrize(
    ("artifact_key", "filename"),
    [
        ("raw", "BTCUSDT-fundingRate-2026-06.raw.json"),
        ("selected_event", "BTCUSDT-fundingRate-2026-06.selected-event.json"),
    ],
)
def test_source_hash_mutation_rejected(
    tmp_path: Path, artifact_key: str, filename: str
) -> None:
    source_root = _source_copy(tmp_path)
    target = (
        source_root / "docs/forensics/evidence/binance_public_funding_event_v0" / filename
    )
    target.write_text(target.read_text() + "\n", encoding="utf-8")

    fixture = _fixture()
    with pytest.raises(PublicEconomicFixtureError) as exc:
        verify_source_artifacts(fixture, source_root=source_root)
    _assert_reason(exc, PublicEconomicFixtureReason.SOURCE_HASH_MISMATCH)


@pytest.mark.parametrize(
    ("field", "value", "reason"),
    [
        ("symbol", "ETHUSDT", PublicEconomicFixtureReason.SYMBOL_MISMATCH),
        ("fundingTime", 1780272000002, PublicEconomicFixtureReason.FUNDING_TIME_INVALID),
        ("rateType", "Special", PublicEconomicFixtureReason.RATE_TYPE_INVALID),
    ],
)
def test_source_event_mutation_rejected(
    tmp_path: Path, field: str, value, reason: PublicEconomicFixtureReason
) -> None:
    source_root = _source_copy(tmp_path)
    selected_path = (
        source_root
        / "docs/forensics/evidence/binance_public_funding_event_v0"
        / "BTCUSDT-fundingRate-2026-06.selected-event.json"
    )
    selected = json.loads(selected_path.read_text())
    selected[field] = value
    _write_json(selected_path, selected)

    fixture = _fixture()
    fixture = replace(fixture, source_selected_event_sha256=receipt_sha256(selected))
    with pytest.raises(PublicEconomicFixtureError) as exc:
        verify_source_artifacts(fixture, source_root=source_root)
    _assert_reason(exc, PublicEconomicFixtureReason.SOURCE_HASH_MISMATCH)


def test_source_event_identity_mutation_rejected(tmp_path: Path) -> None:
    identity = dict(json.loads(FIXTURE_PATH.read_text())["source_event_identity"])
    identity["fundingTime"] = 1780272000002
    with pytest.raises(PublicEconomicFixtureError) as exc:
        parse_fixture(
            _mutated_fixture(tmp_path, source_event_identity=identity),
            verify_source=False,
        )
    _assert_reason(exc, PublicEconomicFixtureReason.FUNDING_TIME_INVALID)


def test_same_inputs_produce_identical_bytes_and_receipt_id() -> None:
    fixture = _fixture()
    first = reconstruct_transfer(fixture)
    second = reconstruct_transfer(fixture)
    assert canonical_receipt_bytes(first) == canonical_receipt_bytes(second)
    assert first["receipt_id"] == second["receipt_id"]


@pytest.mark.parametrize("field", ["signed_position_quantity", "funding_rate", "funding_mark_price"])
def test_load_bearing_mutation_changes_identity(field: str) -> None:
    fixture = _fixture()
    if field == "signed_position_quantity":
        mutated = fixture_with_quantity(fixture, "-0.001")
    elif field == "funding_rate":
        mutated = replace(fixture, event=replace(fixture.event, funding_rate="0.00005704"))
    else:
        mutated = replace(
            fixture, event=replace(fixture.event, funding_mark_price="73653.56663044")
        )
    assert reconstruct_transfer(mutated)["receipt_id"] != reconstruct_transfer(fixture)[
        "receipt_id"
    ]


@pytest.mark.parametrize(
    ("field", "value", "reason"),
    [
        ("receipt_id", "tampered", PublicEconomicFixtureReason.RECEIPT_IDENTITY_MISMATCH),
        (
            "calculated_notional",
            "73.65356663044",
            PublicEconomicFixtureReason.CALCULATED_NOTIONAL_MISMATCH,
        ),
        (
            "calculated_transfer",
            "-0.0042004629049334230",
            PublicEconomicFixtureReason.CALCULATED_TRANSFER_MISMATCH,
        ),
    ],
)
def test_receipt_tampering_detected(field: str, value: str, reason) -> None:
    fixture = _fixture()
    receipt = reconstruct_transfer(fixture)
    receipt[field] = value
    with pytest.raises(PublicEconomicFixtureError) as exc:
        verify_receipt(fixture, receipt)
    _assert_reason(exc, reason)


def test_idempotency_repeat_same_receipt_and_duplicate_batch_rejected() -> None:
    fixture = _fixture()
    first = reconstruct_transfer(fixture)
    second = reconstruct_transfer(fixture)
    assert first == second
    with pytest.raises(PublicEconomicFixtureError) as exc:
        verify_receipt_batch(fixture, [first, second])
    _assert_reason(exc, PublicEconomicFixtureReason.DUPLICATE_APPLICATION)


def test_scope_safety_fields_and_non_claims() -> None:
    receipt = _receipt()
    assert set(receipt["non_claims"]) >= {
        "not an account receipt",
        "not a real wallet posting",
        "not a real position",
        "not evidence of profitability",
        "not evidence of alpha",
        "not a strategy trial",
        "not a research candidate",
    }
    assert receipt["account_posting_status"] == ACCOUNT_POSTING_STATUS
    assert (
        receipt["research_state_policy"]
        == "DO_NOT_REGISTER_AS_CANDIDATE_TRIAL_OR_DECISION"
    )
    assert "profitability" not in receipt
    assert "strategy_authorization" not in receipt


def test_committed_fixture_matches_committed_expected_receipt() -> None:
    expected = json.loads(EXPECTED_RECEIPT_PATH.read_text())
    receipt = _receipt()
    assert canonical_receipt_bytes(receipt) == canonical_receipt_bytes(expected)
    assert receipt["claim_scope"] == CLAIM_SCOPE


def test_runnable_module_returns_bounded_verdict() -> None:
    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "quantbot.paper.public_funding_economic_fixture",
            "--fixture",
            str(FIXTURE_PATH),
            "--verify",
        ],
        check=False,
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, result.stderr
    payload = json.loads(result.stdout)
    assert payload["verdict"] == "PUBLIC_ECONOMIC_FIXTURE_V0_VERIFIED"
    assert payload["claim_scope"] == CLAIM_SCOPE
