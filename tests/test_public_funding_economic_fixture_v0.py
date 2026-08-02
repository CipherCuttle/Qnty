from __future__ import annotations

import json
import shutil
import subprocess
import sys
from dataclasses import replace
from decimal import Decimal, getcontext
from hashlib import sha256
from pathlib import Path

import pytest

import quantbot.paper.public_funding_economic_fixture as public_funding_economic_fixture
from quantbot.paper.public_funding_economic_fixture import (
    ACCOUNT_POSTING_STATUS,
    CLAIM_SCOPE,
    DECIMAL_LEXICAL_MAX_LENGTH,
    DECIMAL_LEXICAL_POLICY,
    QNTYLAB_ROOT_ENV_VAR,
    PublicEconomicFixtureError,
    PublicEconomicFixtureReason,
    canonical_receipt_bytes,
    fixture_with_quantity,
    parse_fixture,
    receipt_sha256,
    reconstruct_transfer,
    resolve_source_root,
    verify_receipt,
    verify_receipt_batch,
    verify_source_artifacts,
)

FIXTURE_PATH = Path("tests/fixtures/public_funding_economic_v0/input.json")
EXPECTED_RECEIPT_PATH = Path(
    "tests/fixtures/public_funding_economic_v0/expected_receipt.json"
)


def _real_qntylab_root() -> Path:
    """Resolve the actual local QntyLab checkout via the production resolver
    instead of hardcoding an absolute path in committed test code."""
    return resolve_source_root()


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
    source_dir = (
        _real_qntylab_root() / "docs/forensics/evidence/binance_public_funding_event_v0"
    )
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


def _independent_canonical_json_bytes(value) -> bytes:
    return json.dumps(
        value, sort_keys=True, separators=(",", ":"), ensure_ascii=True
    ).encode("utf-8")


def _independent_expected_verification() -> dict[str, object]:
    return {
        "claim_scope": "HYPOTHETICAL_PUBLIC_FUNDING_ECONOMIC_RECONSTRUCTION_ONLY",
        "claim_verdict": "PROVEN_FOR_PINNED_FIXTURE",
        "reason_codes": [],
        "source_hashes_verified": True,
        "source_event_identity_verified": True,
        "arithmetic_verified": True,
        "account_posting": "NOT_APPLICABLE",
    }


def test_independent_arithmetic_oracle_vectors_are_exact() -> None:
    mark = Decimal("73653.56663043")
    rate = Decimal("0.00005703")
    multiplier = Decimal("1")
    vectors = [
        (Decimal("0.001"), "73.65356663043", "-0.0042004629049334229", "PAYS"),
        (Decimal("-0.001"), "73.65356663043", "0.0042004629049334229", "RECEIVES"),
        (Decimal("0"), "0", "0", "ZERO"),
    ]

    fixture = _fixture()
    for quantity, expected_notional, expected_transfer, expected_direction in vectors:
        notional = abs(quantity) * mark * multiplier
        transfer = -quantity * mark * rate * multiplier
        assert ("0" if notional.is_zero() else format(notional, "f")) == expected_notional
        assert ("0" if transfer.is_zero() else format(transfer, "f")) == expected_transfer

        receipt = reconstruct_transfer(fixture_with_quantity(fixture, format(quantity, "f")))
        assert receipt["calculated_notional"] == expected_notional
        assert receipt["calculated_transfer"] == expected_transfer
        assert receipt["transfer_direction"] == expected_direction


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


def test_independent_identity_oracle_binds_load_bearing_payload() -> None:
    fixture_json = json.loads(FIXTURE_PATH.read_text())
    identity_payload = {
        "contract_id": fixture_json["contract_id"],
        "contract_version": fixture_json["contract_version"],
        "claim_scope": fixture_json["claim_scope"],
        "source_raw_sha256": fixture_json["source_raw_sha256"],
        "source_selected_event_sha256": fixture_json["source_selected_event_sha256"],
        "source_event_identity": fixture_json["source_event_identity"],
        "symbol": fixture_json["symbol"],
        "funding_time": fixture_json["funding_time"],
        "funding_rate": fixture_json["funding_rate"],
        "funding_mark_price": fixture_json["funding_mark_price"],
        "rate_type": fixture_json["rate_type"],
        "signed_position_quantity": fixture_json["signed_position_quantity"],
        "quantity_unit": fixture_json["quantity_unit"],
        "contract_multiplier": fixture_json["contract_multiplier"],
        "formula_version": "PUBLIC_FUNDING_ECONOMIC_FORMULA_V0",
        "numeric_policy": fixture_json["numeric_policy"],
    }
    receipt = _receipt()

    digest = sha256(_independent_canonical_json_bytes(identity_payload)).hexdigest()
    assert digest == "3833f2fb83a0c59031236cf5bb29b2de0ad2122765f03074f219a2c24bf5bd9b"
    assert receipt["receipt_id"] == digest


def test_independent_verification_metadata_oracle() -> None:
    receipt = _receipt()
    expected = _independent_expected_verification()

    assert receipt["verification"] == expected
    assert type(receipt["verification"]["reason_codes"]) is list
    for key in (
        "source_hashes_verified",
        "source_event_identity_verified",
        "arithmetic_verified",
    ):
        assert type(receipt["verification"][key]) is bool


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


@pytest.mark.parametrize(
    "value",
    ["0", "0.001", "-0.001", "1", "73653.56663043"],
)
def test_canonical_plain_decimal_v1_accepts_synthetic_examples(
    tmp_path: Path, value: str
) -> None:
    assert DECIMAL_LEXICAL_POLICY == "CANONICAL_PLAIN_DECIMAL_V1"
    assert DECIMAL_LEXICAL_MAX_LENGTH == 128
    parse_fixture(
        _mutated_fixture(tmp_path, signed_position_quantity=value),
        verify_source=False,
    )


@pytest.mark.parametrize(
    "value",
    [
        "+0.001",
        "0.0010",
        "1E-3",
        "1e-3",
        " 0.001",
        "0.001 ",
        "00.001",
        "01",
        "1.",
        ".001",
        "-0",
        "-0.0",
        "0.0",
        "1e1000000",
    ],
)
def test_canonical_plain_decimal_v1_rejects_synthetic_aliases(
    tmp_path: Path, value: str
) -> None:
    with pytest.raises(PublicEconomicFixtureError) as exc:
        parse_fixture(
            _mutated_fixture(tmp_path, signed_position_quantity=value),
            verify_source=False,
        )
    _assert_reason(exc, PublicEconomicFixtureReason.QUANTITY_INVALID)


@pytest.mark.parametrize(
    ("field", "value", "reason"),
    [
        ("funding_rate", "0.0010", PublicEconomicFixtureReason.FUNDING_RATE_INVALID),
        (
            "funding_mark_price",
            "73653.5666304300",
            PublicEconomicFixtureReason.MARK_PRICE_MISSING,
        ),
    ],
)
def test_source_decimal_plain_policy_preserves_fractional_zeros(
    tmp_path: Path, field: str, value: str, reason: PublicEconomicFixtureReason
) -> None:
    parse_fixture(_mutated_fixture(tmp_path, **{field: value}), verify_source=False)
    with pytest.raises(PublicEconomicFixtureError) as exc:
        parse_fixture(_mutated_fixture(tmp_path, **{field: "1e1000000"}), verify_source=False)
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


@pytest.mark.parametrize(
    "field", ["signed_position_quantity", "funding_rate", "funding_mark_price"]
)
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


def test_verification_metadata_tampering_is_rejected() -> None:
    fixture = _fixture()
    receipt = reconstruct_transfer(fixture)
    assert list(receipt["verification"]) == [
        "claim_scope",
        "claim_verdict",
        "reason_codes",
        "source_hashes_verified",
        "source_event_identity_verified",
        "arithmetic_verified",
        "account_posting",
    ]
    mutations = []
    for key, value in receipt["verification"].items():
        removed = json.loads(json.dumps(receipt))
        removed["verification"].pop(key)
        mutations.append((f"{key} removed", removed))

        changed = json.loads(json.dumps(receipt))
        if isinstance(value, bool):
            changed["verification"][key] = not value
        elif isinstance(value, str):
            changed["verification"][key] = f"{value}_TAMPERED"
        elif isinstance(value, list):
            changed["verification"][key] = ["TAMPERED"]
        mutations.append((f"{key} changed", changed))

        wrong_type = json.loads(json.dumps(receipt))
        wrong_type["verification"][key] = {"wrong": "type"}
        mutations.append((f"{key} wrong type", wrong_type))

    unexpected = json.loads(json.dumps(receipt))
    unexpected["verification"]["unexpected_key"] = True
    mutations.append(("unexpected key", unexpected))
    missing = json.loads(json.dumps(receipt))
    missing.pop("verification")
    mutations.append(("verification missing", missing))

    for _label, mutated in mutations:
        with pytest.raises(PublicEconomicFixtureError) as exc:
            verify_receipt(fixture, mutated)
        _assert_reason(exc, PublicEconomicFixtureReason.VERIFICATION_METADATA_MISMATCH)


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
    assert (
        receipt["receipt_id"]
        == "3833f2fb83a0c59031236cf5bb29b2de0ad2122765f03074f219a2c24bf5bd9b"
    )
    assert (
        receipt_sha256(receipt)
        == "d7a8827d8054ac2a843baf25dcc9dd547f4235ef10571e30d43cb69ef20b294f"
    )


def test_rejected_decimal_aliases_cannot_create_alternate_receipt_ids(tmp_path: Path) -> None:
    original = _receipt()
    aliases = ["+0.001", "0.0010", "1E-3", "1e-3", " 0.001 ", "00.001"]
    for value in aliases:
        with pytest.raises(PublicEconomicFixtureError):
            parse_fixture(
                _mutated_fixture(tmp_path, signed_position_quantity=value),
                verify_source=False,
            )
    assert _receipt()["receipt_id"] == original["receipt_id"]


def test_cli_reports_typed_decimal_failure_without_traceback(tmp_path: Path) -> None:
    bad_fixture = _mutated_fixture(tmp_path, signed_position_quantity="1e1000000")
    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "quantbot.paper.public_funding_economic_fixture",
            "--fixture",
            str(bad_fixture),
            "--verify",
        ],
        check=False,
        capture_output=True,
        text=True,
    )
    assert result.returncode != 0
    assert result.stdout == ""
    assert "Traceback" not in result.stderr
    payload = json.loads(result.stderr)
    assert payload["reason"] == "QUANTITY_INVALID"


def _run_cli(*extra_args: str, env: dict[str, str] | None = None) -> subprocess.CompletedProcess:
    return subprocess.run(
        [
            sys.executable,
            "-m",
            "quantbot.paper.public_funding_economic_fixture",
            "--fixture",
            str(FIXTURE_PATH),
            "--verify",
            *extra_args,
        ],
        check=False,
        capture_output=True,
        text=True,
        env=env,
    )


def test_runnable_module_returns_bounded_verdict(tmp_path: Path) -> None:
    # Hermetic: explicit --source-root, no dependence on absolute local paths.
    source_root = _source_copy(tmp_path)
    first = _run_cli("--source-root", str(source_root))
    second = _run_cli("--source-root", str(source_root))
    assert first.returncode == 0, first.stderr
    assert first.stdout == second.stdout
    payload = json.loads(first.stdout)
    assert payload["verdict"] == "PUBLIC_ECONOMIC_FIXTURE_V0_VERIFIED"
    assert payload["claim_scope"] == CLAIM_SCOPE


def test_runnable_module_resolves_real_qntylab_checkout_from_worktree() -> None:
    # Integration-level proof: default resolution (no --source-root, no env
    # override) must find the actual local QntyLab checkout from this
    # isolated worktree via the worktree-aware Git-common-dir fallback.
    result = _run_cli()
    assert result.returncode == 0, result.stderr
    payload = json.loads(result.stdout)
    assert payload["verdict"] == "PUBLIC_ECONOMIC_FIXTURE_V0_VERIFIED"


def test_env_root_succeeds(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    source_root = _source_copy(tmp_path)
    monkeypatch.setenv(QNTYLAB_ROOT_ENV_VAR, str(source_root))
    fixture = parse_fixture(FIXTURE_PATH, verify_source=True)
    receipt = reconstruct_transfer(fixture)
    assert receipt["receipt_id"] == "3833f2fb83a0c59031236cf5bb29b2de0ad2122765f03074f219a2c24bf5bd9b"


def test_explicit_root_overrides_env_root(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    valid_root = _source_copy(tmp_path / "valid")
    monkeypatch.setenv(QNTYLAB_ROOT_ENV_VAR, str(tmp_path / "does-not-exist"))
    fixture = parse_fixture(FIXTURE_PATH, source_root=valid_root, verify_source=True)
    assert reconstruct_transfer(fixture)["receipt_id"] == (
        "3833f2fb83a0c59031236cf5bb29b2de0ad2122765f03074f219a2c24bf5bd9b"
    )


def test_invalid_explicit_root_fails(tmp_path: Path) -> None:
    fixture = _fixture()
    with pytest.raises(PublicEconomicFixtureError) as exc:
        verify_source_artifacts(fixture, source_root=tmp_path / "missing")
    _assert_reason(exc, PublicEconomicFixtureReason.QNTYLAB_ROOT_INVALID)


def test_invalid_env_root_fails_without_fallthrough(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setenv(QNTYLAB_ROOT_ENV_VAR, str(tmp_path / "missing"))
    with pytest.raises(PublicEconomicFixtureError) as exc:
        resolve_source_root()
    _assert_reason(exc, PublicEconomicFixtureReason.QNTYLAB_ROOT_INVALID)


def test_ambiguous_fallback_candidates_rejected(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    first = tmp_path / "candidate-a"
    second = tmp_path / "candidate-b"
    first.mkdir()
    second.mkdir()
    monkeypatch.setattr(
        public_funding_economic_fixture,
        "_worktree_aware_sibling_candidate",
        lambda: first,
    )
    monkeypatch.setattr(
        public_funding_economic_fixture,
        "_local_layout_sibling_candidate",
        lambda: second,
    )
    with pytest.raises(PublicEconomicFixtureError) as exc:
        public_funding_economic_fixture._default_source_root()
    _assert_reason(exc, PublicEconomicFixtureReason.QNTYLAB_ROOT_AMBIGUOUS)


def test_layout_sibling_fallback_used_when_worktree_candidate_absent(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    only_candidate = tmp_path / "only-candidate"
    only_candidate.mkdir()
    monkeypatch.setattr(
        public_funding_economic_fixture,
        "_worktree_aware_sibling_candidate",
        lambda: None,
    )
    monkeypatch.setattr(
        public_funding_economic_fixture,
        "_local_layout_sibling_candidate",
        lambda: only_candidate,
    )
    assert public_funding_economic_fixture._default_source_root() == only_candidate.resolve()


def test_receipt_identity_independent_of_source_root_location(tmp_path: Path) -> None:
    root_a = _source_copy(tmp_path / "location-a")
    root_b = _source_copy(tmp_path / "location-b")
    fixture_a = parse_fixture(FIXTURE_PATH, source_root=root_a, verify_source=True)
    fixture_b = parse_fixture(FIXTURE_PATH, source_root=root_b, verify_source=True)
    receipt_a = reconstruct_transfer(fixture_a)
    receipt_b = reconstruct_transfer(fixture_b)
    assert receipt_a["receipt_id"] == receipt_b["receipt_id"]
    assert canonical_receipt_bytes(receipt_a) == canonical_receipt_bytes(receipt_b)
    assert str(tmp_path) not in canonical_receipt_bytes(receipt_a).decode("utf-8")
