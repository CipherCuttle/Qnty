from __future__ import annotations

import copy
import hashlib
import json
from pathlib import Path

import pytest

from quantbot.core.determinism import canonical_json_dumps
from quantbot.paper import accepted_execution_intent_publication as subject

ROOT = Path(__file__).resolve().parents[1]
ARTIFACTS = ROOT / "artifacts" / "h003_bridge_v0"
INTENT = ARTIFACTS / "QNTY_ACCEPTED_EXECUTION_INTENT_V2.json"
QNTY_COMMIT = "2ebed2af94127f2e018de46069d1bbe27178ca8a"
PUBLIC_KEY_FINGERPRINT = "10ba682c8ad13513971e8b56881aab8bd702bb807796eca81932c735a94d6e6d"
FIXED_EXTERNAL_SIGNATURE = bytes.fromhex(
    "138d0c26efd28d6634611ee3754fe0b51e82b01559f34efd5d41888028645f9f"
    "051e8cecec4410ef79282012f339a9da9367c2974f2dfd0bbeae8068be6e8609"
)
EXPECTED_INTENT_DIGEST = "18d9f32c5afe5ba3c6f15b4596d4bb44a1ef9c8175e6d4715c9ccba23508f48f"
EXPECTED_ARTIFACT_SHA256 = "262f2eeea5c7fea979f1500538ffd146686e9c4ac8069a1ac5ae4d3ae7cd76db"
EXPECTED_SIGNED_BODY_SHA256 = "2822e54e696248f3ac700b662706fefc65eaad80a064cc422f837b5fa98ee69b"
EXPECTED_RECEIPT_ID = "393a5decca6d325acd72f9016e8004022a6234460007552573ba172983cb1488"
EXPECTED_RECEIPT_FILE_SHA256 = "9087abfbded6eba0947f29fbbeb005d0f230669f97a3cacd59bbaab689890c8e"


def _body(intent: Path | bytes = INTENT) -> dict[str, object]:
    return subject.build_publication_body_v0(
        intent,
        qnty_repository_commit=QNTY_COMMIT,
        public_key_fingerprint=PUBLIC_KEY_FINGERPRINT,
        publication_epoch=1,
        serial=1,
        published_at_epoch_s=1789056614,
    )


def _rehash_intent(intent: dict[str, object]) -> None:
    probe = copy.deepcopy(intent)
    probe["intent_digest"] = ""
    intent["intent_digest"] = hashlib.sha256(
        canonical_json_dumps(probe).encode("utf-8")
    ).hexdigest()


def test_publication_body_binds_exact_published_v2_bytes_and_qnty_commit() -> None:
    body = _body()
    assert body == {
        "accepted_intent_schema_name": "QNTY_ACCEPTED_EXECUTION_INTENT_V2",
        "accepted_intent_schema_version": "V2",
        "artifact_sha256": EXPECTED_ARTIFACT_SHA256,
        "intent_digest": EXPECTED_INTENT_DIGEST,
        "publication_epoch": 1,
        "published_at_epoch_s": 1789056614,
        "public_key_fingerprint": PUBLIC_KEY_FINGERPRINT,
        "purpose": "QNTY_ACCEPTED_INTENT_ORIGIN_AUTHENTICATION_ONLY",
        "qnty_repository": "CipherCuttle/Qnty",
        "qnty_repository_commit": QNTY_COMMIT,
        "root_id": "qnty-accepted-intent-publication",
        "schema": "qntyspot.qnty_publication_auth.v0.receipt",
        "serial": 1,
        "signature_algorithm": "Ed25519",
    }
    signed = subject.publication_body_bytes_v0(body)
    assert hashlib.sha256(signed).hexdigest() == EXPECTED_SIGNED_BODY_SHA256


def test_external_signature_assembles_qntyspot_compatible_receipt_vector() -> None:
    receipt = subject.assemble_publication_receipt_v0(
        _body(), signature=FIXED_EXTERNAL_SIGNATURE
    )
    assert receipt["receipt_id"] == EXPECTED_RECEIPT_ID
    assert receipt["signature"] == FIXED_EXTERNAL_SIGNATURE.hex()
    data = subject.publication_receipt_bytes_v0(receipt)
    assert hashlib.sha256(data).hexdigest() == EXPECTED_RECEIPT_FILE_SHA256


def test_receipt_writer_is_write_once_and_idempotent(tmp_path: Path) -> None:
    receipt = subject.assemble_publication_receipt_v0(
        _body(), signature=FIXED_EXTERNAL_SIGNATURE
    )
    artifact = tmp_path / "publication_receipt.json"
    sidecar = tmp_path / "publication_receipt.sha256"

    subject.write_publication_receipt_v0(receipt, artifact, sidecar)
    first = artifact.read_bytes(), sidecar.read_bytes()
    subject.write_publication_receipt_v0(receipt, artifact, sidecar)
    assert (artifact.read_bytes(), sidecar.read_bytes()) == first
    assert sidecar.read_text(encoding="ascii") == EXPECTED_RECEIPT_FILE_SHA256 + "\n"

    artifact.write_bytes(artifact.read_bytes() + b"\n")
    with pytest.raises(subject.PublicationReceiptRejected, match="OUTPUT_CONFLICT"):
        subject.write_publication_receipt_v0(receipt, artifact, sidecar)


def test_byte_different_intent_is_not_silently_normalized() -> None:
    raw = INTENT.read_bytes()
    with pytest.raises(subject.PublicationReceiptRejected, match="NON_CANONICAL_BYTES"):
        _body(raw.rstrip(b"\n"))


def test_dynamic_self_consistent_v2_event_needs_no_event_digest_allowlist() -> None:
    intent = json.loads(INTENT.read_text(encoding="utf-8"))
    intent["decision"] = {
        "current_target": "LONG",
        "effective_source_timestamp": "2026-09-05T08:00:00Z",
        "execution_action_required": True,
        "previous_target": "FLAT",
        "transition": "TARGET_CHANGE",
    }
    intent["provenance"]["upstream_handoff_digest"] = "3" * 64
    intent["provenance"]["qnty_acceptance_record_id"] = "H003_ACCEPTANCE_V0:" + "3" * 64
    intent["provenance"]["qnty_acceptance_receipt_digest"] = "4" * 64
    _rehash_intent(intent)
    raw = (canonical_json_dumps(intent) + "\n").encode("utf-8")

    body = _body(raw)
    assert body["intent_digest"] == intent["intent_digest"]
    assert body["artifact_sha256"] == hashlib.sha256(raw).hexdigest()
    assert body["purpose"] == subject.PUBLICATION_PURPOSE


def test_unknown_body_fields_and_wrong_qnty_identity_fail_closed() -> None:
    body = _body()
    extra = dict(body)
    extra["authority_level"] = 3
    with pytest.raises(subject.PublicationReceiptRejected, match="SCHEMA_FIELDS"):
        subject.validate_publication_body_v0(extra)

    wrong_repo = dict(body)
    wrong_repo["qnty_repository"] = "not-qnty"
    with pytest.raises(subject.PublicationReceiptRejected, match="REPOSITORY_MISMATCH"):
        subject.validate_publication_body_v0(wrong_repo)


def test_signature_shape_and_receipt_identity_fail_closed() -> None:
    with pytest.raises(subject.PublicationReceiptRejected, match="SIGNATURE_INVALID"):
        subject.assemble_publication_receipt_v0(_body(), signature=b"short")

    receipt = subject.assemble_publication_receipt_v0(
        _body(), signature=FIXED_EXTERNAL_SIGNATURE
    )
    tampered = dict(receipt)
    tampered["receipt_id"] = "0" * 64
    with pytest.raises(subject.PublicationReceiptRejected, match="RECEIPT_ID_INVALID"):
        subject.validate_publication_receipt_v0(tampered)


def test_publication_module_cannot_sign_or_gain_execution_authority() -> None:
    source = (ROOT / "quantbot/paper/accepted_execution_intent_publication.py").read_text(
        encoding="utf-8"
    )
    forbidden = (
        "Ed25519" + "PrivateKey",
        "from_" + "private_bytes",
        ".si" + "gn(",
        "private_" + "key",
        "os.environ",
        "getenv(",
        "requests.",
        "urllib.",
        "socket.",
        "submit_transaction",
    )
    for token in forbidden:
        assert token not in source


def test_admin_lane_does_not_touch_qnty_control_state_or_v2_authority() -> None:
    source = (ROOT / "quantbot/paper/accepted_execution_intent_publication.py").read_text(
        encoding="utf-8"
    )
    assert "docs/control" not in source
    assert "active_task" not in source
    assert "handoff_v" not in source
    assert "AUTHORITY_NONE" not in source
    assert "execution_action" not in source
