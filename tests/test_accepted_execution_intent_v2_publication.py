from __future__ import annotations

import hashlib
import json
from pathlib import Path

from quantbot.core.determinism import canonical_json_dumps
from quantbot.paper import accepted_execution_intent_v2 as subject

ROOT = Path(__file__).resolve().parents[1]
ARTIFACTS = ROOT / "artifacts" / "h003_bridge_v0"
HANDOFF = ARTIFACTS / "H003_SIGNAL_INTENT_V0.json"
RECEIPT = ARTIFACTS / "H003_ACCEPTANCE_V0.json"
PUBLISHED = ARTIFACTS / "QNTY_ACCEPTED_EXECUTION_INTENT_V2.json"
SIDECAR = ARTIFACTS / "QNTY_ACCEPTED_EXECUTION_INTENT_V2.sha256"
EXPECTED_INTENT_DIGEST = "18d9f32c5afe5ba3c6f15b4596d4bb44a1ef9c8175e6d4715c9ccba23508f48f"
EXPECTED_FILE_SHA256 = "262f2eeea5c7fea979f1500538ffd146686e9c4ac8069a1ac5ae4d3ae7cd76db"


def test_published_v2_artifact_is_exact_producer_output() -> None:
    intent = subject.emit_accepted_execution_intent_v2(HANDOFF, RECEIPT, ARTIFACTS)
    published = json.loads(PUBLISHED.read_text(encoding="utf-8"))

    assert published == intent
    assert published["intent_digest"] == EXPECTED_INTENT_DIGEST
    assert SIDECAR.read_text(encoding="utf-8") == EXPECTED_INTENT_DIGEST + "\n"
    assert PUBLISHED.read_bytes() == (canonical_json_dumps(intent) + "\n").encode("utf-8")
    assert hashlib.sha256(PUBLISHED.read_bytes()).hexdigest() == EXPECTED_FILE_SHA256


def test_v2_writer_replays_published_bytes_idempotently(tmp_path: Path) -> None:
    intent = subject.emit_accepted_execution_intent_v2(HANDOFF, RECEIPT, ARTIFACTS)
    artifact = tmp_path / PUBLISHED.name
    sidecar = tmp_path / SIDECAR.name

    subject.write_accepted_execution_intent_v2(intent, artifact, sidecar)
    first = artifact.read_bytes(), sidecar.read_bytes()
    subject.write_accepted_execution_intent_v2(intent, artifact, sidecar)

    assert (artifact.read_bytes(), sidecar.read_bytes()) == first
    assert artifact.read_bytes() == PUBLISHED.read_bytes()
    assert sidecar.read_bytes() == SIDECAR.read_bytes()
