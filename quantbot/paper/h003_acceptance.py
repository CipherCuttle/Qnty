"""Downstream acceptance for the frozen H003_SIGNAL_INTENT_V0 external signal snapshot.

Phase: QNTY_H003_SOL_TO_QNTYSPOT_SHADOW_BRIDGE_V0 (Subtask D — Qnty independent
downstream acceptance).

Boundary: QntyLab owns research/signal semantics; Qnty owns downstream
acceptance/accounting. This module NEVER recomputes or re-derives the H003
signal — it consumes the already-computed, frozen artifact as an untrusted
external input and makes Qnty's OWN accept/reject decision, fail-closed, using
Qnty's existing append-only ledger machinery (``quantbot.paper.ledger``) and
provenance conventions (``quantbot.paper.provenance``). No parallel store, no
parallel strategy engine, no execution authority: the acceptance record and
receipt carry ``capital/signing/submission = NONE`` and grant nothing.

Validation is fail-closed: any fault raises :class:`AcceptanceRejected` with a
machine-readable reason BEFORE any ledger row or receipt is written (no
partial acceptance). Re-acceptance of the same artifact is an id-keyed no-op
via ``ledger.append_new``; any byte-level mutation of the artifact changes its
digest and is REJECTED.
"""

from __future__ import annotations

import hashlib
import json
import re
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from quantbot.core.determinism import canonical_json_dumps, sha256_file
from quantbot.paper import ledger
from quantbot.paper.provenance import resolve_git_sha

PHASE = "QNTY_H003_SOL_TO_QNTYSPOT_SHADOW_BRIDGE_V0"
SCHEMA_NAME = "H003_SIGNAL_INTENT_V0"
SCHEMA_VERSION = "V0"
RECEIPT_SCHEMA_NAME = "H003_ACCEPTANCE_V0"

# The exact no-authority block the frozen artifact must carry. Any other value
# or extra key rejects the artifact: this artifact exists to be READ, not obeyed.
REQUIRED_AUTHORITY = {
    "capital": "NONE",
    "execution": "FORBIDDEN",
    "signing": "NONE",
    "submission": "NONE",
}

# Receipt authority block: acceptance NEVER grants execution authority.
RECEIPT_AUTHORITY = {
    "capital": "NONE",
    "signing": "NONE",
    "submission": "NONE",
}

REQUIRED_TOP_LEVEL = frozenset(
    {
        "artifact_digest",
        "authority",
        "bar_window",
        "close_series",
        "computed_at",
        "computed_at_rule",
        "phase",
        "schema_name",
        "schema_version",
        "signal",
        "upstream",
    }
)

REQUIRED_UPSTREAM = frozenset(
    {
        "candidate_id",
        "strategy_id",
        "strategy_version",
        "variant_id",
        "parameters",
        "source_semantic",
        "qntylab_head",
    }
)

REQUIRED_BAR_WINDOW = frozenset(
    {"first_bar_open", "last_bar_open", "bar_count", "close_of_bar_t"}
)

REQUIRED_CLOSE_SERIES = frozenset({"digest_rule", "path", "sha256"})

REQUIRED_SIGNAL = frozenset(
    {
        "causal_target_t_plus_1",
        "decision_bar_t_open",
        "decision_rule",
        "ma192",
        "ma48",
        "raw_signal_at_t",
    }
)

REQUIRED_MA = frozenset({"numerator", "denominator"})

_FULL_SHA_RE = re.compile(r"\A[0-9a-f]{64}\Z")
_FULL_GIT_SHA_RE = re.compile(r"\A[0-9a-f]{40}\Z")

ARTIFACT_SOURCE_REPO = "QntySpot"
ARTIFACT_SOURCE_PATH = "qualifications/h003_bridge_v0/H003_SIGNAL_INTENT_V0.json"
LEDGER_FILENAME = "h003_acceptance_ledger.jsonl"
RECEIPT_FILENAME = "H003_ACCEPTANCE_V0.json"
RECEIPT_SIDECAR_FILENAME = "H003_ACCEPTANCE_V0.sha256"


class AcceptanceRejected(Exception):
    """A frozen artifact failed Qnty's independent validation. Fail closed.

    Raised BEFORE any ledger row or receipt is written, so a rejected artifact
    can never be partially accepted. ``code`` is a stable machine-readable
    reason; ``detail`` carries the evidence.
    """

    def __init__(self, code: str, detail: str) -> None:
        super().__init__(f"{code}: {detail}")
        self.code = code
        self.detail = detail


def _reject_floats(obj: Any, where: str) -> None:
    """Recursively reject any JSON float anywhere in a parsed artifact."""
    if isinstance(obj, float):
        raise AcceptanceRejected(
            "FLOAT_IN_ARTIFACT",
            f"{where}: JSON floats are forbidden (got {obj!r})",
        )
    if isinstance(obj, dict):
        for key, value in obj.items():
            _reject_floats(value, f"{where}.{key}")
    elif isinstance(obj, list):
        for idx, value in enumerate(obj):
            _reject_floats(value, f"{where}[{idx}]")


def _no_float_hook(text: str) -> None:
    raise AcceptanceRejected(
        "FLOAT_IN_ARTIFACT",
        f"JSON floats are forbidden (parser saw literal {text!r})",
    )


def _no_dupes_hook(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    obj: dict[str, Any] = {}
    for key, value in pairs:
        if key in obj:
            raise AcceptanceRejected(
                "DUPLICATE_KEY",
                f"duplicate JSON object key {key!r}; refusing ambiguous artifact",
            )
        obj[key] = value
    return obj


def load_strict_json_object(path: Path) -> dict[str, Any]:
    """Load a JSON object fail-closed: UTF-8, no floats, no duplicate keys, object only."""
    try:
        raw = path.read_bytes()
    except OSError as exc:
        raise AcceptanceRejected(
            "ARTIFACT_UNREADABLE",
            f"{path.name} could not be read ({type(exc).__name__}: {exc})",
        ) from exc
    try:
        text = raw.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise AcceptanceRejected(
            "ARTIFACT_NOT_UTF8",
            f"{path.name} is not valid UTF-8 ({exc})",
        ) from exc
    try:
        obj = json.loads(text, parse_float=_no_float_hook, object_pairs_hook=_no_dupes_hook)
    except json.JSONDecodeError as exc:
        raise AcceptanceRejected(
            "ARTIFACT_NOT_JSON",
            f"{path.name} is not valid JSON ({exc})",
        ) from exc
    if not isinstance(obj, dict):
        raise AcceptanceRejected(
            "ARTIFACT_NOT_OBJECT",
            f"{path.name} parses but is not a JSON object (got {type(obj).__name__})",
        )
    _reject_floats(obj, path.name)
    return obj


def _parse_utc(value: Any, where: str) -> datetime:
    if not isinstance(value, str):
        raise AcceptanceRejected("SCHEMA_INVALID", f"{where} must be a string")
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise AcceptanceRejected(
            "SCHEMA_INVALID", f"{where} is not a parseable UTC timestamp ({value!r})"
        ) from exc


def _require_exact_keys(obj: Any, expected: frozenset[str], where: str) -> None:
    if not isinstance(obj, dict):
        raise AcceptanceRejected("SCHEMA_INVALID", f"{where} must be an object")
    missing = sorted(expected - set(obj))
    unknown = sorted(set(obj) - expected)
    if missing or unknown:
        raise AcceptanceRejected(
            "SCHEMA_FIELDS",
            f"{where} missing field(s) {missing} and/or unknown field(s) {unknown}",
        )


def _require_hex64(value: Any, where: str) -> str:
    if not isinstance(value, str) or not _FULL_SHA_RE.match(value):
        raise AcceptanceRejected(
            "SCHEMA_INVALID", f"{where} must be a 64-char lowercase hex sha256"
        )
    return value


def _canonical_digest(artifact: dict[str, Any]) -> str:
    """sha256 over canonical JSON (sorted keys, no whitespace, UTF-8) with
    artifact_digest set to "" — the documented digest rule."""
    probe = dict(artifact)
    probe["artifact_digest"] = ""
    return hashlib.sha256(canonical_json_dumps(probe).encode("utf-8")).hexdigest()


def validate_h003_signal_intent(
    artifact_path: Path, sidecar_path: Path
) -> tuple[dict[str, Any], dict[str, dict[str, str]], str]:
    """Run Qnty's independent validators. Returns (artifact, validator_results, file_sha256).

    Raises :class:`AcceptanceRejected` on the first fault (fail closed, no
    partial acceptance). The returned validator results are all PASS by
    construction; they are embedded in the acceptance receipt.
    """
    # (a) Byte-level: the .sha256 sidecar carries the artifact's declared
    # artifact_digest (canonical-JSON digest, per the artifact README); the raw
    # file-bytes sha256 is recorded separately in the receipt for byte identity.
    artifact = load_strict_json_object(artifact_path)
    try:
        sidecar_text = sidecar_path.read_text(encoding="utf-8").strip()
    except OSError as exc:
        raise AcceptanceRejected(
            "SIDECAR_UNREADABLE",
            f"{sidecar_path.name} could not be read ({type(exc).__name__}: {exc})",
        ) from exc
    declared = artifact.get("artifact_digest")
    if not isinstance(declared, str) or not _FULL_SHA_RE.match(declared):
        raise AcceptanceRejected(
            "SCHEMA_INVALID", "artifact_digest must be a 64-char lowercase hex sha256"
        )
    if sidecar_text != declared:
        raise AcceptanceRejected(
            "SIDECAR_MISMATCH",
            f"sidecar {sidecar_text!r} != artifact_digest {declared!r}",
        )
    file_sha256 = sha256_file(artifact_path)
    validators = {
        "byte_sidecar": {
            "status": "PASS",
            "detail": f"sidecar == artifact_digest ({declared}); file bytes sha256 {file_sha256}",
        }
    }

    # (b) Digest rule: recompute canonical-JSON digest with artifact_digest="".
    recomputed = _canonical_digest(artifact)
    if recomputed != declared:
        raise AcceptanceRejected(
            "DIGEST_MISMATCH",
            f"recomputed canonical digest {recomputed} != declared {declared} "
            "(artifact mutated or mis-canonicalized)",
        )
    validators["canonical_digest"] = {
        "status": "PASS",
        "detail": f"recomputed canonical-JSON digest == {declared}",
    }

    # (c) Schema: exact field sets, no unknown fields, no floats (already
    # enforced at parse time), fixed identity labels.
    _require_exact_keys(artifact, REQUIRED_TOP_LEVEL, "artifact")
    if artifact["schema_name"] != SCHEMA_NAME or artifact["schema_version"] != SCHEMA_VERSION:
        raise AcceptanceRejected(
            "SCHEMA_INVALID",
            f"schema_name/schema_version must be {SCHEMA_NAME}/{SCHEMA_VERSION} "
            f"(got {artifact['schema_name']!r}/{artifact['schema_version']!r})",
        )
    if artifact["phase"] != PHASE:
        raise AcceptanceRejected(
            "SCHEMA_INVALID", f"phase must be {PHASE!r} (got {artifact['phase']!r})"
        )
    if not isinstance(artifact["computed_at_rule"], str) or not artifact["computed_at_rule"]:
        raise AcceptanceRejected("SCHEMA_INVALID", "computed_at_rule must be a non-empty string")
    _parse_utc(artifact["computed_at"], "computed_at")
    validators["schema"] = {
        "status": "PASS",
        "detail": "exact top-level field set; no unknown fields; no JSON floats "
        "(parse-time rejection); identity labels match H003_SIGNAL_INTENT_V0/V0",
    }

    # (c-cont) Authority block must be EXACTLY the no-authority block.
    if artifact["authority"] != REQUIRED_AUTHORITY:
        raise AcceptanceRejected(
            "AUTHORITY_BLOCK_INVALID",
            f"authority must be exactly {REQUIRED_AUTHORITY} (got {artifact['authority']!r})",
        )
    validators["authority_block"] = {
        "status": "PASS",
        "detail": "authority == {capital: NONE, execution: FORBIDDEN, signing: NONE, submission: NONE}",
    }

    # (d) Provenance: upstream identities present and internally consistent.
    upstream = artifact["upstream"]
    _require_exact_keys(upstream, REQUIRED_UPSTREAM, "upstream")
    for field in ("candidate_id", "strategy_id", "strategy_version", "variant_id"):
        if not isinstance(upstream[field], str) or not upstream[field]:
            raise AcceptanceRejected("SCHEMA_INVALID", f"upstream.{field} must be a non-empty string")
    if upstream["source_semantic"] != "BINANCE_SPOT_SOLUSDT_1H":
        raise AcceptanceRejected(
            "SCHEMA_INVALID",
            f"upstream.source_semantic must be BINANCE_SPOT_SOLUSDT_1H "
            f"(got {upstream['source_semantic']!r})",
        )
    qntylab_head = upstream["qntylab_head"]
    if not isinstance(qntylab_head, str) or not _FULL_GIT_SHA_RE.match(qntylab_head):
        raise AcceptanceRejected(
            "SCHEMA_INVALID", "upstream.qntylab_head must be a 40-char lowercase git sha"
        )
    parameters = upstream["parameters"]
    _require_exact_keys(parameters, frozenset({"fast", "slow", "mode"}), "upstream.parameters")
    for field in ("fast", "slow"):
        value = parameters[field]
        if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
            raise AcceptanceRejected(
                "SCHEMA_INVALID", f"upstream.parameters.{field} must be a positive int"
            )
    if parameters["mode"] != "long_flat":
        raise AcceptanceRejected(
            "SCHEMA_INVALID",
            f"upstream.parameters.mode must be 'long_flat' (got {parameters['mode']!r})",
        )

    bar_window = artifact["bar_window"]
    _require_exact_keys(bar_window, REQUIRED_BAR_WINDOW, "bar_window")
    bar_count = bar_window["bar_count"]
    if isinstance(bar_count, bool) or not isinstance(bar_count, int) or bar_count <= 0:
        raise AcceptanceRejected("SCHEMA_INVALID", "bar_window.bar_count must be a positive int")
    first = _parse_utc(bar_window["first_bar_open"], "bar_window.first_bar_open")
    last = _parse_utc(bar_window["last_bar_open"], "bar_window.last_bar_open")
    close_t = _parse_utc(bar_window["close_of_bar_t"], "bar_window.close_of_bar_t")
    for label, ts in (("first_bar_open", first), ("last_bar_open", last), ("close_of_bar_t", close_t)):
        if ts.minute != 0 or ts.second != 0 or ts.microsecond != 0:
            raise AcceptanceRejected(
                "SCHEMA_INVALID", f"bar_window.{label} is not hour-aligned ({ts.isoformat()})"
            )
    if not first < last:
        raise AcceptanceRejected(
            "SCHEMA_INVALID",
            "bar_window timestamps not strictly increasing (first_bar_open >= last_bar_open)",
        )
    if close_t != last + timedelta(hours=1):
        raise AcceptanceRejected(
            "SCHEMA_INVALID",
            "bar_window.close_of_bar_t must be last_bar_open + 1h",
        )
    span_hours = int((last - first).total_seconds()) // 3600
    if span_hours < bar_count - 1:
        raise AcceptanceRejected(
            "SCHEMA_INVALID",
            f"bar window span ({span_hours}h) < bar_count-1 ({bar_count - 1}); "
            "window cannot contain the declared bar count",
        )

    close_series = artifact["close_series"]
    _require_exact_keys(close_series, REQUIRED_CLOSE_SERIES, "close_series")
    _require_hex64(close_series["sha256"], "close_series.sha256")
    if not isinstance(close_series["path"], str) or not close_series["path"]:
        raise AcceptanceRejected("SCHEMA_INVALID", "close_series.path must be a non-empty string")
    if not isinstance(close_series["digest_rule"], str) or not close_series["digest_rule"]:
        raise AcceptanceRejected("SCHEMA_INVALID", "close_series.digest_rule must be a non-empty string")

    signal = artifact["signal"]
    _require_exact_keys(signal, REQUIRED_SIGNAL, "signal")
    for ma_field in ("ma48", "ma192"):
        ma = signal[ma_field]
        _require_exact_keys(ma, REQUIRED_MA, f"signal.{ma_field}")
        for part in ("numerator", "denominator"):
            if isinstance(ma[part], bool) or not isinstance(ma[part], int):
                raise AcceptanceRejected(
                    "SCHEMA_INVALID", f"signal.{ma_field}.{part} must be an int"
                )
        if ma["denominator"] <= 0:
            raise AcceptanceRejected(
                "SCHEMA_INVALID", f"signal.{ma_field}.denominator must be positive"
            )
    raw = signal["raw_signal_at_t"]
    if isinstance(raw, bool) or not isinstance(raw, int) or raw not in (-1, 0, 1):
        raise AcceptanceRejected("SCHEMA_INVALID", "signal.raw_signal_at_t must be in {-1, 0, 1}")
    if signal["causal_target_t_plus_1"] not in ("LONG", "FLAT"):
        raise AcceptanceRejected(
            "SCHEMA_INVALID",
            f"signal.causal_target_t_plus_1 must be LONG or FLAT "
            f"(got {signal['causal_target_t_plus_1']!r})",
        )
    if not isinstance(signal["decision_rule"], str) or not signal["decision_rule"]:
        raise AcceptanceRejected("SCHEMA_INVALID", "signal.decision_rule must be a non-empty string")
    decision_bar = _parse_utc(signal["decision_bar_t_open"], "signal.decision_bar_t_open")
    if decision_bar != last:
        raise AcceptanceRejected(
            "SCHEMA_INVALID",
            "signal.decision_bar_t_open must equal bar_window.last_bar_open",
        )
    validators["provenance"] = {
        "status": "PASS",
        "detail": (
            f"candidate_id={upstream['candidate_id']}; strategy_id={upstream['strategy_id']}; "
            f"variant_id={upstream['variant_id']}; parameters={parameters}; "
            f"qntylab_head={qntylab_head}; bar window {bar_window['first_bar_open']}.."
            f"{bar_window['last_bar_open']} strictly increasing 1h "
            f"(close_of_bar_t == last+1h, span {span_hours}h >= bar_count-1); "
            f"close_series sha256 present; decision_bar_t_open == last_bar_open"
        ),
    }

    return artifact, validators, file_sha256


def acceptance_id_for(artifact_digest: str) -> str:
    """Stable idempotency key for an accepted artifact digest."""
    return f"{RECEIPT_SCHEMA_NAME}:{artifact_digest}"


def _receipt_digest(receipt: dict[str, Any]) -> str:
    probe = dict(receipt)
    probe["receipt_digest"] = ""
    return hashlib.sha256(canonical_json_dumps(probe).encode("utf-8")).hexdigest()


def accept_h003_signal_intent(
    artifact_path: Path,
    sidecar_path: Path,
    artifacts_dir: Path,
    now: datetime | None = None,
    qnty_head: str | None = None,
) -> dict[str, Any]:
    """Accept (or idempotently re-accept) a frozen H003_SIGNAL_INTENT_V0 artifact.

    Validates fail-closed, appends an id-keyed acceptance record to the
    append-only acceptance ledger via ``ledger.append_new`` (re-run with the
    same artifact is a no-op), and writes the H003_ACCEPTANCE_V0 receipt
    (+ .sha256 sidecar) with the same canonical-JSON digest discipline as the
    upstream artifact (no floats). Returns the receipt dict.

    Raises :class:`AcceptanceRejected` before ANY write on any validation fault.
    """
    artifact, validators, file_sha256 = validate_h003_signal_intent(artifact_path, sidecar_path)
    artifact_digest = artifact["artifact_digest"]

    resolved_head = qnty_head or resolve_git_sha()
    if not resolved_head or not _FULL_GIT_SHA_RE.match(resolved_head):
        raise AcceptanceRejected(
            "QNTY_HEAD_UNRESOLVED",
            "Qnty repo HEAD could not be resolved to a full 40-char sha; refusing "
            "to accept without provenance",
        )

    artifacts_dir = Path(artifacts_dir)
    ledger_path = artifacts_dir / LEDGER_FILENAME
    record_id = acceptance_id_for(artifact_digest)

    already = record_id in ledger.existing_ids(ledger_path, "acceptance_id")
    if already:
        # Idempotent re-acceptance: the id-keyed append is a no-op and the
        # existing receipt is left untouched (no second acceptance record).
        receipt_path = artifacts_dir / RECEIPT_FILENAME
        if not receipt_path.exists():
            raise AcceptanceRejected(
                "RECEIPT_MISSING_ON_REACCEPT",
                f"acceptance record {record_id} exists but {RECEIPT_FILENAME} is absent; "
                "refusing to silently regenerate — investigate",
            )
        return {
            "decision": "ACCEPT",
            "idempotent_no_op": True,
            "acceptance_id": record_id,
            "artifact_digest": artifact_digest,
            "receipt_path": str(receipt_path),
        }

    accepted_at = (now or datetime.now(timezone.utc)).astimezone(timezone.utc).strftime(
        "%Y-%m-%dT%H:%M:%SZ"
    )
    record = {
        "acceptance_id": record_id,
        "schema_name": "H003_ACCEPTANCE_RECORD_V0",
        "phase": PHASE,
        "decision": "ACCEPT",
        "artifact_schema": SCHEMA_NAME,
        "artifact_digest": artifact_digest,
        "artifact_file_sha256": file_sha256,
        "artifact_source_repo": ARTIFACT_SOURCE_REPO,
        "artifact_source_path": ARTIFACT_SOURCE_PATH,
        "upstream_qntylab_head": artifact["upstream"]["qntylab_head"],
        "qnty_head_at_acceptance": resolved_head,
        "accepted_at_utc": accepted_at,
        "authority": dict(RECEIPT_AUTHORITY),
    }
    written = ledger.append_new(ledger_path, [record], "acceptance_id")

    receipt: dict[str, Any] = {
        "schema_name": RECEIPT_SCHEMA_NAME,
        "schema_version": SCHEMA_VERSION,
        "phase": PHASE,
        "decision": "ACCEPT",
        "accepted_artifact": {
            "schema_name": SCHEMA_NAME,
            "artifact_digest": artifact_digest,
            "artifact_file_sha256": file_sha256,
            "source_repo": ARTIFACT_SOURCE_REPO,
            "source_path": ARTIFACT_SOURCE_PATH,
            "upstream_qntylab_head": artifact["upstream"]["qntylab_head"],
            "signal_causal_target_t_plus_1": artifact["signal"]["causal_target_t_plus_1"],
            "decision_bar_t_open": artifact["signal"]["decision_bar_t_open"],
        },
        "validators": validators,
        "qnty_head_at_acceptance": resolved_head,
        "ledger": {
            "path": LEDGER_FILENAME,
            "id_field": "acceptance_id",
            "record_id": record_id,
            "rows_appended_this_run": written,
            "append_machinery": "quantbot.paper.ledger.append_new (append-only, id-keyed, idempotent)",
        },
        "authority": dict(RECEIPT_AUTHORITY),
        "accepted_at_utc": accepted_at,
        "receipt_digest": "",
    }
    digest = _receipt_digest(receipt)
    receipt["receipt_digest"] = digest

    # Canonical bytes (sorted keys, no whitespace, UTF-8) + trailing newline
    # (newline not part of the digest) — same discipline as the upstream artifact.
    receipt_bytes = (canonical_json_dumps(receipt) + "\n").encode("utf-8")
    ledger.write_bytes_atomic(artifacts_dir / RECEIPT_FILENAME, receipt_bytes)
    ledger.write_bytes_atomic(
        artifacts_dir / RECEIPT_SIDECAR_FILENAME, (digest + "\n").encode("utf-8")
    )
    return {
        "decision": "ACCEPT",
        "idempotent_no_op": False,
        "acceptance_id": record_id,
        "artifact_digest": artifact_digest,
        "receipt_digest": digest,
        "receipt_path": str(artifacts_dir / RECEIPT_FILENAME),
        "ledger_path": str(ledger_path),
    }


def main() -> int:
    """CLI: accept the frozen artifact into artifacts/h003_bridge_v0 (repo root)."""
    import argparse

    repo_root = Path(__file__).resolve().parents[2]
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--artifact",
        type=Path,
        default=repo_root / "artifacts" / "h003_bridge_v0" / "H003_SIGNAL_INTENT_V0.json",
    )
    parser.add_argument(
        "--sidecar",
        type=Path,
        default=repo_root / "artifacts" / "h003_bridge_v0" / "H003_SIGNAL_INTENT_V0.sha256",
    )
    parser.add_argument(
        "--artifacts-dir", type=Path, default=repo_root / "artifacts" / "h003_bridge_v0"
    )
    args = parser.parse_args()
    try:
        result = accept_h003_signal_intent(args.artifact, args.sidecar, args.artifacts_dir)
    except AcceptanceRejected as exc:
        print(
            json.dumps({"decision": "REJECT", "reason_code": exc.code, "detail": exc.detail}),
            flush=True,
        )
        return 2
    print(json.dumps(result, sort_keys=True), flush=True)
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
