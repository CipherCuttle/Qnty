import ast
import copy
import hashlib
import importlib
import json
from pathlib import Path

import pytest

control = importlib.import_module("quantbot" + ".control")
LegacyAdapterError = control.LegacyAdapterError
LegacyDocument = control.LegacyDocument
RuntimeAction = control.RuntimeAction
authorize = control.authorize
project_legacy_control_state = control.project_legacy_control_state

ROOT = Path(__file__).resolve().parents[2]
ACTIVE_PATH = "docs/control/active_task.json"
RECEIPT_PATH = "docs/control/tasks/RECOVER_OR_RETIRE_CANDIDATE1_V0_FROZEN_INPUT/handoff_v031.json"
HEAD = "5504f4f348a153fe8248055fe762fb15f5065503"
EFFECTIVE = tuple(
    sorted(
        path for path in (ROOT / "docs/control/amendments").glob("*.json")
        if json.loads(path.read_text()).get("effective") is True
    )
)
RUNTIME_ENTRYPOINTS = (
    "quantbot/continuity/__main__.py",
    "scripts/fetch_ohlcv_rest.py",
    "scripts/fetch_funding_rest.py",
    "scripts/fetch_first_statistic_btcusdt_1h.py",
    "scripts/run_stage4_volnorm.py",
    "scripts/run_validation_v2.py",
    "scripts/qnty-paper-sqlite-accounting.py",
    "ops/bin/qnty-data-refresh.sh",
    "ops/bin/qnty-paper-pnl-run.sh",
    "ops/bin/qnty-shadow-run.sh",
)
FORBIDDEN_RUNTIME_REFERENCES = ("legacy_adapter", "project_legacy_control_state", "quantbot" + ".control")


def _doc(path):
    path = Path(path)
    return LegacyDocument(str(path.relative_to(ROOT)), path.read_bytes())


def _inputs():
    return dict(active_task=_doc(ROOT / ACTIVE_PATH), source_receipt=_doc(ROOT / RECEIPT_PATH), amendments=tuple(_doc(path) for path in EFFECTIVE), source_head_commit=HEAD)


def _canonical(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True).encode()


def _mutate_receipt(mutator):
    inputs = _inputs()
    value = json.loads(inputs["source_receipt"].raw)
    mutator(value)
    inputs["source_receipt"] = LegacyDocument(RECEIPT_PATH, _canonical(value))
    active = json.loads(inputs["active_task"].raw)
    active["handoff_receipt_sha256"] = hashlib.sha256(inputs["source_receipt"].raw).hexdigest()
    inputs["active_task"] = LegacyDocument(ACTIVE_PATH, _canonical(active))
    return inputs


def _rebind_amendment(inputs, index, parsed_mutator=None, new_path=None):
    """Replace amendments[index] and re-bind the receipt evidence to match."""
    original = inputs["amendments"][index]
    parsed = json.loads(original.raw)
    if parsed_mutator is not None:
        parsed_mutator(parsed)
    mutated_raw = _canonical(parsed)
    mutated_path = new_path if new_path is not None else original.path
    mutated = LegacyDocument(mutated_path, mutated_raw)
    inputs = dict(inputs)
    inputs["amendments"] = inputs["amendments"][:index] + (mutated,) + inputs["amendments"][index + 1 :]
    receipt = json.loads(inputs["source_receipt"].raw)
    for item in receipt["evidence"]:
        if item.get("path") == original.path:
            item["path"] = mutated_path
            item["sha256"] = hashlib.sha256(mutated_raw).hexdigest()
    inputs["source_receipt"] = LegacyDocument(RECEIPT_PATH, _canonical(receipt))
    active = json.loads(inputs["active_task"].raw)
    active["handoff_receipt_sha256"] = hashlib.sha256(inputs["source_receipt"].raw).hexdigest()
    inputs["active_task"] = LegacyDocument(ACTIVE_PATH, _canonical(active))
    return inputs


def _fails(code, **inputs):
    with pytest.raises(LegacyAdapterError) as excinfo:
        project_legacy_control_state(**inputs)
    assert excinfo.value.code == code
    assert excinfo.value.path


def test_current_state_projects_exactly_and_is_repeatable():
    state = project_legacy_control_state(**_inputs())
    assert project_legacy_control_state(**_inputs()) == state
    assert state.state_revision == 32
    assert state.protocol_id == "real_btc_candidate1_train_mechanism_decomposition_v0"
    assert state.administrative_state.workflow_status == "UNDER_REVIEW"
    assert state.administrative_state.proposal_ref == "docs/control/amendments/candidate1_h001_synthetic_null_calibration_numerical_conventions_amendment_candidate_v001.json"
    assert state.provenance.source_receipt_path == RECEIPT_PATH
    assert state.provenance.source_receipt_sha256 == hashlib.sha256((ROOT / RECEIPT_PATH).read_bytes()).hexdigest()
    assert state.provenance.source_head_commit == HEAD
    assert state.scientific_state == type(state.scientific_state)("H001", "EDGE_UNPROVEN", "BLOCK_LIVE_INTEGRATION", "FORBIDDEN", "NOT_AUTHORIZED", 0, 0)
    assert set(vars(state.runtime_authorization).values()) == {"DENIED"}
    assert all(not authorize(state, action).authorized for action in RuntimeAction)


def test_amendment_order_does_not_matter():
    inputs = _inputs()
    inputs["amendments"] = tuple(reversed(inputs["amendments"]))
    assert project_legacy_control_state(**inputs) == project_legacy_control_state(**_inputs())


def test_next_action_is_only_administrative_evidence():
    inputs = _mutate_receipt(lambda value: value.__setitem__("next_actions", ["ANY_ADMINISTRATIVE_REVIEW_STAGE"]))
    state = project_legacy_control_state(**inputs)
    assert set(vars(state.runtime_authorization).values()) == {"DENIED"}


@pytest.mark.parametrize("mutator,code", [
    (lambda value: value["safety_state"].__setitem__("decomposition_execution_count", 1), "LEGACY_AUTHORITY_ESCALATION"),
    (lambda value: value["decisions"].remove("H001_EXECUTION=0/0"), "LEGACY_REQUIRED_EVIDENCE_MISSING"),
    (lambda value: value["safety_state"].__setitem__("edge_status", "EDGE_PROVEN"), "LEGACY_AUTHORITY_ESCALATION"),
    (lambda value: value["safety_state"].__setitem__("live_status", "ALLOW_LIVE_INTEGRATION"), "LEGACY_AUTHORITY_ESCALATION"),
    (lambda value: value.__setitem__("receipt_index", 30), "LEGACY_REVISION_MISMATCH"),
    (lambda value: value.__setitem__("protocol_id", "wrong"), "LEGACY_IDENTITY_MISMATCH"),
    (lambda value: value.__setitem__("runtime_permission", "AUTHORIZED"), "LEGACY_AUTHORITY_ESCALATION"),
])
def test_receipt_contradictions_fail_closed(mutator, code):
    _fails(code, **_mutate_receipt(mutator))


def test_active_path_mismatch_and_duplicate_amendment_fail():
    inputs = _inputs()
    active = json.loads(inputs["active_task"].raw)
    active["handoff_receipt_path"] = "docs/control/tasks/other.json"
    inputs["active_task"] = LegacyDocument(ACTIVE_PATH, _canonical(active))
    _fails("ACTIVE_RECEIPT_MISMATCH", **inputs)
    inputs = _inputs()
    inputs["amendments"] += (inputs["amendments"][0],)
    _fails("DUPLICATE_AMENDMENT_PATH", **inputs)


def test_missing_or_conflicting_effective_amendment_fails():
    inputs = _inputs()
    inputs["amendments"] = inputs["amendments"][1:]
    _fails("LEGACY_REQUIRED_EVIDENCE_MISSING", **inputs)
    inputs = _inputs()
    extra = LegacyDocument("docs/control/amendments/extra.json", _canonical({"effective": True, "governed_h001_protocol_id": "real_btc_h001_funding_crowding_reversal_falsification_v0"}))
    inputs["amendments"] += (extra,)
    _fails("LEGACY_UNKNOWN_AMENDMENT_ROLE", **inputs)


@pytest.mark.parametrize("raw,code", [
    (b"{not-json", "INVALID_LEGACY_JSON"),
    (b'{"x":1,"x":2}', "DUPLICATE_LEGACY_KEY"),
])
def test_bad_legacy_json_fails(raw, code):
    inputs = _inputs()
    inputs["source_receipt"] = LegacyDocument(RECEIPT_PATH, raw)
    _fails(code, **inputs)


def test_unsafe_paths_and_authority_claiming_amendment_fail():
    inputs = _inputs()
    inputs["source_receipt"] = LegacyDocument("../unsafe.json", inputs["source_receipt"].raw)
    _fails("INVALID_LEGACY_PATH", **inputs)
    inputs = _rebind_amendment(_inputs(), 0, parsed_mutator=lambda parsed: parsed.__setitem__("runtime_permission", "AUTHORIZED"))
    _fails("LEGACY_AUTHORITY_ESCALATION", **inputs)


# --- Defect 1: semantic identity comes only from explicit `amendment_kind`,
# never from path/basename/suffix/directory. ---


def test_relocated_amendment_still_classifies_by_explicit_semantic_fields():
    inputs = _inputs()
    original = inputs["amendments"][0]
    relocated_path = "docs/control/amendments/relocated_in_memory_only/" + Path(original.path).name
    inputs = _rebind_amendment(inputs, 0, new_path=relocated_path)
    assert inputs["amendments"][0].path == relocated_path
    state = project_legacy_control_state(**inputs)
    baseline = project_legacy_control_state(**_inputs())
    # The receipt's evidence binding changed (new path), so its bytes and
    # sha256 legitimately differ; every other projected field must not.
    assert state.state_revision == baseline.state_revision
    assert state.protocol_id == baseline.protocol_id
    assert state.scientific_state == baseline.scientific_state
    assert state.administrative_state == baseline.administrative_state
    assert state.runtime_authorization == baseline.runtime_authorization


def test_unknown_amendment_kind_role_fails():
    inputs = _rebind_amendment(_inputs(), 0, parsed_mutator=lambda parsed: parsed.__setitem__("amendment_kind", "not_a_recognized_role"))
    _fails("LEGACY_UNKNOWN_AMENDMENT_ROLE", **inputs)


def test_duplicate_amendment_kind_role_fails():
    inputs = _inputs()
    donor_role = json.loads(inputs["amendments"][1].raw)["amendment_kind"]
    inputs = _rebind_amendment(inputs, 0, parsed_mutator=lambda parsed: parsed.__setitem__("amendment_kind", donor_role))
    _fails("LEGACY_DUPLICATE_AMENDMENT_ROLE", **inputs)


def test_conflicting_document_kind_and_amendment_kind_fails():
    inputs = _rebind_amendment(_inputs(), 0, parsed_mutator=lambda parsed: parsed.__setitem__("document_kind", "some_other_document_kind"))
    _fails("LEGACY_AMENDMENT_ROLE_CONFLICT", **inputs)


# --- Defect 2: structural, field-aware authority validation. ---


@pytest.mark.parametrize("mutator", [
    lambda value: value.__setitem__("review_status", "APPROVED"),
    lambda value: value.__setitem__("review_verdict", "PASS"),
    lambda value: value.__setitem__("next_actions", ["IMPLEMENT_H001_SYNTHETIC_NULL_CALIBRATION_NUMERICAL_CONVENTIONS_AMENDMENT_ACTIVATION_FOR_INDEPENDENT_REVIEW"]),
    lambda value: value["decisions"].append("REVIEW_STATUS=APPROVED"),
    lambda value: value["decisions"].append("NEXT_ACTIONS=CANDIDATE_IMPLEMENTATION_FOR_INDEPENDENT_REVIEW_ONLY"),
])
def test_administrative_evidence_variations_stay_administrative(mutator):
    inputs = _mutate_receipt(mutator)
    state = project_legacy_control_state(**inputs)
    assert set(vars(state.runtime_authorization).values()) == {"DENIED"}
    assert all(not authorize(state, action).authorized for action in RuntimeAction)


@pytest.mark.parametrize("token", [
    "LIVE_EXECUTION=AUTHORIZED_ONLY",
    "PAPER_EXECUTION=AUTHORIZED_FOR_REVIEW_ONLY",
    "SHADOW_EXECUTION=ENABLED_FOR_INDEPENDENT_REVIEW",
    "REAL_DATA_ACCESS=PERMITTED_FOR_REVIEW_ONLY",
    "SYNTHETIC_CALIBRATION_EXECUTABLE=TRUE",
    "SCIENTIFIC_AUTHORIZATION=AUTHORIZED",
])
def test_decision_token_runtime_escalation_fails_closed(token):
    inputs = _mutate_receipt(lambda value: value["decisions"].append(token))
    _fails("LEGACY_AUTHORITY_ESCALATION", **inputs)


def test_amendment_boolean_authority_field_escalation_fails_closed():
    inputs = _rebind_amendment(_inputs(), 0, parsed_mutator=lambda parsed: parsed.__setitem__("scientific_authorization", True))
    _fails("LEGACY_AUTHORITY_ESCALATION", **inputs)


def test_administrative_implementation_authorization_stays_allowed():
    # execution_implementation_authorized=true is genuine, current, effective
    # evidence in the real execution-governance amendment; it must not be
    # treated as a runtime-authority escalation.
    state = project_legacy_control_state(**_inputs())
    assert set(vars(state.runtime_authorization).values()) == {"DENIED"}
    assert all(not authorize(state, action).authorized for action in RuntimeAction)


# --- Defect 3: malformed `amendments` input fails closed before sorting. ---


def test_amendments_must_be_a_tuple():
    inputs = _inputs()
    inputs["amendments"] = list(inputs["amendments"])
    _fails("LEGACY_WRONG_TYPE", **inputs)


@pytest.mark.parametrize("bad_item", [None, {"path": "x", "raw": b"{}"}])
def test_amendments_items_must_be_legacy_documents(bad_item):
    inputs = _inputs()
    inputs["amendments"] = inputs["amendments"] + (bad_item,)
    _fails("LEGACY_WRONG_TYPE", **inputs)


def test_amendments_item_path_must_be_str():
    inputs = _inputs()
    inputs["amendments"] = inputs["amendments"] + (LegacyDocument(123, b"{}"),)
    _fails("INVALID_LEGACY_PATH", **inputs)


def test_amendments_item_raw_must_be_bytes():
    inputs = _inputs()
    inputs["amendments"] = inputs["amendments"] + (LegacyDocument("docs/control/amendments/x.json", "not-bytes"),)
    _fails("LEGACY_WRONG_TYPE", **inputs)


def test_amendments_item_path_must_be_safe():
    inputs = _inputs()
    inputs["amendments"] = inputs["amendments"] + (LegacyDocument("../unsafe.json", b"{}"),)
    _fails("INVALID_LEGACY_PATH", **inputs)


def test_amendments_reject_duplicate_paths():
    inputs = _inputs()
    inputs["amendments"] = inputs["amendments"] + (inputs["amendments"][0],)
    _fails("DUPLICATE_AMENDMENT_PATH", **inputs)


def test_no_raw_python_exception_escapes_malformed_amendments():
    for bad_amendments in (
        list(_inputs()["amendments"]),
        _inputs()["amendments"] + (None,),
        _inputs()["amendments"] + ({"not": "a document"},),
        _inputs()["amendments"] + (LegacyDocument(123, b"{}"),),
        _inputs()["amendments"] + (LegacyDocument("docs/control/amendments/x.json", "not-bytes"),),
        _inputs()["amendments"] + (LegacyDocument("../unsafe.json", b"{}"),),
        _inputs()["amendments"] + (_inputs()["amendments"][0],),
    ):
        inputs = _inputs()
        inputs["amendments"] = bad_amendments
        with pytest.raises(LegacyAdapterError):
            project_legacy_control_state(**inputs)


# --- Runtime-unreachability coverage. ---


def test_adapter_is_pure_and_unreachable_from_runtime():
    source = (ROOT / "quantbot/control/legacy_adapter.py").read_text()
    tree = ast.parse(source)
    assert not {node.id for node in ast.walk(tree) if isinstance(node, ast.Name)} & {"open", "Path", "environ", "subprocess"}
    for relative in RUNTIME_ENTRYPOINTS:
        text = (ROOT / relative).read_text()
        for forbidden in FORBIDDEN_RUNTIME_REFERENCES:
            assert forbidden not in text, f"{relative} must not reference {forbidden!r}"
    assert (ROOT / "quantbot/control/state.py").read_bytes() == __import__("subprocess").check_output(["git", "show", f"{HEAD}:quantbot/control/state.py"], cwd=ROOT)
    assert not list(ROOT.rglob("*control_state*.json"))
