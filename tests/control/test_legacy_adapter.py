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
    _fails("LEGACY_AMENDMENT_CONFLICT", **inputs)


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
    inputs = _inputs()
    replacement = LegacyDocument(inputs["amendments"][0].path, _canonical({"effective": True, "governed_h001_protocol_id": "real_btc_h001_funding_crowding_reversal_falsification_v0", "runtime": "AUTHORIZED"}))
    inputs["amendments"] = (replacement,) + inputs["amendments"][1:]
    _fails("LEGACY_AUTHORITY_ESCALATION", **inputs)


def test_adapter_is_pure_and_unreachable_from_runtime():
    source = (ROOT / "quantbot/control/legacy_adapter.py").read_text()
    tree = ast.parse(source)
    assert not {node.id for node in ast.walk(tree) if isinstance(node, ast.Name)} & {"open", "Path", "environ", "subprocess"}
    runtime_entrypoints = [ROOT / "quantbot/continuity/__main__.py"]
    assert all("legacy_adapter" not in path.read_text() for path in runtime_entrypoints)
    assert (ROOT / "quantbot/control/state.py").read_bytes() == __import__("subprocess").check_output(["git", "show", f"{HEAD}:quantbot/control/state.py"], cwd=ROOT)
    assert not list(ROOT.rglob("*control_state*.json"))
