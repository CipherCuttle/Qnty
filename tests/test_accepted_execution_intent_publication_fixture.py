from __future__ import annotations

import hashlib
from pathlib import Path

from quantbot.paper import accepted_execution_intent_publication as subject

ROOT = Path(__file__).resolve().parents[1]
FIXTURE = ROOT / "tests/fixtures/QNTY_ACCEPTED_EXECUTION_INTENT_PUBLICATION_RECEIPT_V0.json"
SIDECAR = ROOT / "tests/fixtures/QNTY_ACCEPTED_EXECUTION_INTENT_PUBLICATION_RECEIPT_V0.sha256"
INTENT = ROOT / "artifacts/h003_bridge_v0/QNTY_ACCEPTED_EXECUTION_INTENT_V2.json"
PUBLIC_KEY_FINGERPRINT = "10ba682c8ad13513971e8b56881aab8bd702bb807796eca81932c735a94d6e6d"
SIGNATURE = bytes.fromhex(
    "138d0c26efd28d6634611ee3754fe0b51e82b01559f34efd5d41888028645f9f"
    "051e8cecec4410ef79282012f339a9da9367c2974f2dfd0bbeae8068be6e8609"
)
EXPECTED_FILE_SHA256 = "9087abfbded6eba0947f29fbbeb005d0f230669f97a3cacd59bbaab689890c8e"


def test_compatibility_fixture_is_exact_qnty_assembler_output() -> None:
    body = subject.build_publication_body_v0(
        INTENT,
        qnty_repository_commit="2ebed2af94127f2e018de46069d1bbe27178ca8a",
        public_key_fingerprint=PUBLIC_KEY_FINGERPRINT,
        publication_epoch=1,
        serial=1,
        published_at_epoch_s=1789056614,
    )
    receipt = subject.assemble_publication_receipt_v0(body, signature=SIGNATURE)
    assert FIXTURE.read_bytes() == subject.publication_receipt_bytes_v0(receipt)
    assert hashlib.sha256(FIXTURE.read_bytes()).hexdigest() == EXPECTED_FILE_SHA256
    assert SIDECAR.read_text(encoding="ascii") == EXPECTED_FILE_SHA256 + "\n"


def test_compatibility_fixture_is_not_a_production_trust_root() -> None:
    assert "tests/fixtures" in FIXTURE.as_posix()
    assert "artifacts/h003_bridge_v0" not in FIXTURE.as_posix()
