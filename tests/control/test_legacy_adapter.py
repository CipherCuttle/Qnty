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
_legacy_adapter = importlib.import_module("quantbot" + ".control.legacy_adapter")

ROOT = Path(__file__).resolve().parents[2]
ACTIVE_PATH = "docs/control/active_task.json"
RECEIPT_PATH = "docs/control/tasks/RECOVER_OR_RETIRE_CANDIDATE1_V0_FROZEN_INPUT/handoff_v034.json"
HEAD = "0bd455ed236fe69ecca6484e3c9318070db889f0"
# `legacy_adapter` is a pure projection of one frozen historical packet
# (receipt index 34): its docstring is explicit that it "does not inspect
# the repository ... state". This test module therefore pins the exact
# active-task pointer bytes that were live when receipt index 34 was the
# active task, rather than reading the live (and, from v035 onward,
# advancing) `docs/control/active_task.json` off disk -- reading the live
# file would silently break every test in this module the moment the
# continuity pointer legitimately advances past receipt 34, even though the
# frozen adapter under test has not changed at all.
_PINNED_V034_ACTIVE_TASK_BYTES = (
    b'{"control_kind":"qnty_active_task_pointer",'
    b'"handoff_receipt_path":"docs/control/tasks/RECOVER_OR_RETIRE_CANDIDATE1_V0_FROZEN_INPUT/handoff_v034.json",'
    b'"handoff_receipt_sha256":"c1187bc4387bd299bdf975c411620aefb09a9b7db8040f4456f5c811b8f72037",'
    b'"phase":"candidate1_h001_synthetic_null_calibration_execution_engine_implementation_review_completed",'
    b'"protocol_id":"real_btc_candidate1_train_mechanism_decomposition_v0",'
    b'"schema_version":"0.1.0",'
    b'"task_id":"RECOVER_OR_RETIRE_CANDIDATE1_V0_FROZEN_INPUT"}'
)
# Similarly, the seven currently-effective amendments are a frozen set as of
# receipt index 34; a live glob over `docs/control/amendments/` would pick up
# any later, unrelated governance document marked `effective` for reasons
# outside this frozen adapter's scope. Pin the exact seven paths instead.
_PINNED_V034_EFFECTIVE_BASENAMES = (
    "candidate1_h001_synthetic_null_calibration_execution_governance_v001.json",
    "candidate1_h001_synthetic_null_calibration_numerical_conventions_amendment_governance_v001.json",
    "candidate1_h001_synthetic_null_calibration_rng_runtime_specification_amendment_activation_v001.json",
    "candidate1_h001_synthetic_null_calibration_rng_runtime_specification_amendment_governance_v001.json",
    "candidate1_h001_synthetic_null_calibration_numerical_conventions_amendment_activation_v001.json",
    "candidate1_h001_temporal_causality_activation_v001.json",
    "candidate1_h001_synthetic_null_calibration_spec_freeze_activation_v001.json",
)
EFFECTIVE = tuple(
    sorted(
        ROOT / "docs/control/amendments" / basename
        for basename in _PINNED_V034_EFFECTIVE_BASENAMES
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
    return dict(active_task=LegacyDocument(ACTIVE_PATH, _PINNED_V034_ACTIVE_TASK_BYTES), source_receipt=_doc(ROOT / RECEIPT_PATH), amendments=tuple(_doc(path) for path in EFFECTIVE), source_head_commit=HEAD)


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
    assert state.state_revision == 35
    assert state.protocol_id == "real_btc_candidate1_train_mechanism_decomposition_v0"
    assert state.administrative_state.workflow_status == "REVIEW_COMPLETED"
    assert state.administrative_state.proposal_ref == "quantbot/experiment/h001_null_calibration_engine.py"
    assert state.provenance.source_receipt_path == RECEIPT_PATH
    assert state.provenance.source_receipt_sha256 == hashlib.sha256((ROOT / RECEIPT_PATH).read_bytes()).hexdigest()
    assert state.provenance.source_head_commit == HEAD
    assert state.scientific_state == type(state.scientific_state)("H001", "EDGE_UNPROVEN", "BLOCK_LIVE_INTEGRATION", "FORBIDDEN", "NOT_AUTHORIZED", 0, 0)
    assert set(vars(state.runtime_authorization).values()) == {"DENIED"}
    assert all(not authorize(state, action).authorized for action in RuntimeAction)
    roles = {json.loads(document.raw)["amendment_kind"] for document in _inputs()["amendments"]}
    assert len(roles) == 7
    activation = next(document for document in _inputs()["amendments"] if json.loads(document.raw)["amendment_kind"] == "qnty_h001_numerical_conventions_amendment_activation_amendment")
    assert hashlib.sha256(activation.raw).hexdigest() == "c497359a292f5a9b1333e5d881fee16c39d80f68ec1a6613f625a368532ae200"


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


def test_relabeled_amendment_kind_fails_content_binding_before_duplicate_check():
    # Relabeling amendment_kind to impersonate another role changes the raw
    # bytes, so the exact role-to-content binding now rejects it before the
    # (still-present) duplicate-role check is even reached -- a strictly
    # stronger guarantee than the pre-repair "duplicate role" classification.
    inputs = _inputs()
    donor_role = json.loads(inputs["amendments"][1].raw)["amendment_kind"]
    inputs = _rebind_amendment(inputs, 0, parsed_mutator=lambda parsed: parsed.__setitem__("amendment_kind", donor_role))
    _fails("LEGACY_AMENDMENT_CONTENT_MISMATCH", **inputs)


def test_duplicate_amendment_role_fails_via_byte_identical_second_copy():
    # A genuine duplicate role claim: the exact same frozen bytes supplied
    # twice at two distinct, safe paths. Both copies pass the content
    # binding individually; the second is rejected only for claiming a role
    # already supplied.
    inputs = _inputs()
    original = inputs["amendments"][0]
    duplicate_path = "docs/control/amendments/duplicate_role_probe.json"
    duplicate = LegacyDocument(duplicate_path, original.raw)
    inputs["amendments"] = inputs["amendments"] + (duplicate,)
    receipt = json.loads(inputs["source_receipt"].raw)
    receipt["evidence"].append({"path": duplicate_path, "sha256": hashlib.sha256(original.raw).hexdigest()})
    inputs["source_receipt"] = LegacyDocument(RECEIPT_PATH, _canonical(receipt))
    active = json.loads(inputs["active_task"].raw)
    active["handoff_receipt_sha256"] = hashlib.sha256(inputs["source_receipt"].raw).hexdigest()
    inputs["active_task"] = LegacyDocument(ACTIVE_PATH, _canonical(active))
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


# --- Repair regression: exact role-content binding closes the authority-
# field validation gap where keys ending in "_granted" (and other names not
# covered by the old suffix tuple) were silently accepted. ---


def _assert_deny_only(state):
    assert state.scientific_state.edge_status == "EDGE_UNPROVEN"
    assert state.scientific_state.live_status == "BLOCK_LIVE_INTEGRATION"
    assert state.scientific_state.real_data_access == "FORBIDDEN"
    assert state.scientific_state.synthetic_calibration_execution == "NOT_AUTHORIZED"
    assert state.scientific_state.execution_count == 0
    assert state.scientific_state.execution_budget == 0
    assert set(vars(state.runtime_authorization).values()) == {"DENIED"}
    assert all(not authorize(state, action).authorized for action in RuntimeAction)


def test_exact_reported_reproducer_live_authorization_granted_now_rejected():
    """The exact defect reproducer: false -> true on a `_granted`-suffixed
    field inside the real currently-effective RNG-runtime activation
    amendment, with the receipt evidence hash correctly updated to bind the
    mutated bytes. Previously silently accepted; must now fail closed."""
    inputs = _rebind_amendment(
        _inputs(),
        [i for i, d in enumerate(_inputs()["amendments"]) if "rng_runtime_specification_amendment_activation" in d.path][0],
        parsed_mutator=lambda parsed: parsed["authority_non_effects"].__setitem__("live_authorization_granted", True),
    )
    _fails("LEGACY_AUTHORITY_ESCALATION", **inputs)


@pytest.mark.parametrize("field", ["live_authorization_granted", "paper_trade_authorization_granted", "scientific_authorization_granted"])
def test_existing_granted_fields_reject_true(field):
    inputs = _rebind_amendment(
        _inputs(),
        [i for i, d in enumerate(_inputs()["amendments"]) if "rng_runtime_specification_amendment_activation" in d.path][0],
        parsed_mutator=lambda parsed: parsed["authority_non_effects"].__setitem__(field, True),
    )
    _fails("LEGACY_AUTHORITY_ESCALATION", **inputs)


@pytest.mark.parametrize("field", ["live_authorization_granted", "paper_trade_authorization_granted", "scientific_authorization_granted"])
def test_existing_granted_fields_stay_deny_safe_at_false(field):
    inputs = _rebind_amendment(
        _inputs(),
        [i for i, d in enumerate(_inputs()["amendments"]) if "rng_runtime_specification_amendment_activation" in d.path][0],
        parsed_mutator=lambda parsed: parsed["authority_non_effects"].__setitem__(field, False),
    )
    state = project_legacy_control_state(**inputs)
    _assert_deny_only(state)


@pytest.mark.parametrize("field", ["runtime_permission_granted", "shadow_execution_granted", "real_data_access_granted", "Live_Authorization_Granted"])
def test_unknown_authority_bearing_fields_reject_true(field):
    # Exercised on the source receipt, which (unlike the six pinned
    # amendments) is not byte-frozen -- this isolates the structural
    # classifier itself rather than the separate content-binding guarantee.
    inputs = _mutate_receipt(lambda value: value.__setitem__(field, True))
    _fails("LEGACY_AUTHORITY_ESCALATION", **inputs)


@pytest.mark.parametrize("field", ["runtime_permission_granted", "shadow_execution_granted", "real_data_access_granted", "Live_Authorization_Granted"])
def test_unknown_authority_bearing_fields_stay_deny_safe_at_false(field):
    inputs = _mutate_receipt(lambda value: value.__setitem__(field, False))
    state = project_legacy_control_state(**inputs)
    _assert_deny_only(state)


@pytest.mark.parametrize(("key", "container", "path"), [
    ("runtime_permission", {"granted": False}, "source_receipt.runtime_permission"),
    ("live_authorization", [{"granted": False}], "source_receipt.live_authorization"),
    ("paper_trade_authorized", {"value": False}, "source_receipt.paper_trade_authorized"),
    ("Live_Authorization_Granted", {"value": False}, "source_receipt.Live_Authorization_Granted"),
])
def test_recognized_authority_containers_fail_closed(key, container, path):
    inputs = _mutate_receipt(lambda value: value.__setitem__(key, container))
    with pytest.raises(LegacyAdapterError) as excinfo:
        project_legacy_control_state(**inputs)
    assert excinfo.value.code == "LEGACY_AUTHORITY_ESCALATION"
    assert excinfo.value.path == path


@pytest.mark.parametrize(("container", "path"), [
    ({"authority_non_effects": {"live_authorization_granted": True}}, "source_receipt.authority_non_effects.live_authorization_granted"),
    ({"metadata": {"nested": {"runtime_permission_granted": True}}}, "source_receipt.metadata.nested.runtime_permission_granted"),
])
def test_unrecognized_grouping_containers_recurse_to_reject_positive_authority_leaf(container, path):
    inputs = _mutate_receipt(lambda value: value.update(container))
    with pytest.raises(LegacyAdapterError) as excinfo:
        project_legacy_control_state(**inputs)
    assert excinfo.value.code == "LEGACY_AUTHORITY_ESCALATION"
    assert excinfo.value.path == path


@pytest.mark.parametrize("container", [
    {"authority_non_effects": {"live_authorization_granted": False}},
    {"metadata": {"nested": {"runtime_permission_granted": False}}},
])
def test_unrecognized_grouping_containers_recurse_to_accept_deny_safe_authority_leaf(container):
    state = project_legacy_control_state(**_mutate_receipt(lambda value: value.update(container)))
    _assert_deny_only(state)


def test_current_frozen_authorization_status_values_are_all_accepted():
    found = {
        json.loads(document.raw)["authorization_status"]
        for document in _inputs()["amendments"]
        if "authorization_status" in json.loads(document.raw)
    }
    assert found  # the current packet does exercise this field
    assert found == _legacy_adapter._ADMINISTRATIVE_STATUS_ALLOWED_VALUES
    state = project_legacy_control_state(**_inputs())
    _assert_deny_only(state)


@pytest.mark.parametrize("bad_status", [
    "AUTHORIZED_LIVE_EXECUTION",
    "LIVE_EXECUTION_AUTHORIZED",
    "AUTHORIZED_PAPER_EXECUTION_FOR_REVIEW_ONLY",
    "REAL_DATA_ACCESS_AUTHORIZED_CANDIDATE",
    "SCIENTIFIC_USE_AUTHORIZED_PROPOSED",
])
def test_unknown_authorization_status_values_are_rejected(bad_status):
    index = [i for i, d in enumerate(_inputs()["amendments"]) if "execution_governance" in d.path][0]
    inputs = _rebind_amendment(_inputs(), index, parsed_mutator=lambda parsed: parsed.__setitem__("authorization_status", bad_status))
    _fails("LEGACY_AUTHORITY_ESCALATION", **inputs)


def test_all_six_current_effective_amendments_match_frozen_role_digests():
    digests = _legacy_adapter._REQUIRED_EFFECTIVE_AMENDMENT_ROLE_DIGESTS
    assert set(digests) == _legacy_adapter._REQUIRED_EFFECTIVE_AMENDMENT_ROLES
    for document in _inputs()["amendments"]:
        role = json.loads(document.raw)["amendment_kind"]
        assert hashlib.sha256(document.raw).hexdigest() == digests[role]
    # The digest map is keyed by role, never by path or filename.
    for key in digests:
        assert "/" not in key and not key.endswith(".json")


def test_relocation_with_identical_bytes_preserves_role_content_binding():
    inputs = _inputs()
    original = inputs["amendments"][0]
    relocated_path = "docs/control/amendments/relocated_content_binding_probe/" + Path(original.path).name
    inputs = _rebind_amendment(inputs, 0, new_path=relocated_path)
    state = project_legacy_control_state(**inputs)
    baseline = project_legacy_control_state(**_inputs())
    _assert_deny_only(state)
    # The receipt's evidence binding legitimately changed (new path), so its
    # bytes/sha256 (reflected only in provenance) differ; every other
    # projected field -- including the role-to-content-bound scientific and
    # administrative state -- must not.
    assert state.state_revision == baseline.state_revision
    assert state.protocol_id == baseline.protocol_id
    assert state.scientific_state == baseline.scientific_state
    assert state.administrative_state == baseline.administrative_state
    assert state.runtime_authorization == baseline.runtime_authorization


def test_any_byte_mutation_fails_content_binding_even_with_rebound_evidence():
    inputs = _rebind_amendment(_inputs(), 0, parsed_mutator=lambda parsed: parsed.__setitem__("amendment_id", parsed.get("amendment_id", "") + "-tampered"))
    _fails("LEGACY_AMENDMENT_CONTENT_MISMATCH", **inputs)


def test_active_receipt_mismatch_precedes_combined_amendment_and_evidence_failures_regardless_of_order():
    """Freeze the existing validation order without creating a new hierarchy."""
    inputs = _inputs()
    amendments = list(inputs["amendments"])
    for index, document in enumerate(amendments):
        parsed = json.loads(document.raw)
        if "execution_governance" in document.path:
            parsed["runtime_permission"] = True
            mutated_raw = _canonical(parsed)
            amendments[index] = LegacyDocument(document.path, mutated_raw)
            break
    else:  # pragma: no cover - frozen fixture must retain this amendment.
        raise AssertionError("missing execution-governance amendment")
    inputs["amendments"] = tuple(amendments)
    receipt = json.loads(inputs["source_receipt"].raw)
    receipt["evidence"][0]["sha256"] = "0" * 64
    # Deliberately leave active_task's receipt hash stale.  This creates an
    # active-receipt mismatch alongside the receipt-evidence mismatch and the
    # authority/content failures above; current behavior must fail here first.
    inputs["source_receipt"] = LegacyDocument(RECEIPT_PATH, _canonical(receipt))

    observed = []
    for ordering in (inputs["amendments"], tuple(reversed(inputs["amendments"]))):
        ordered_inputs = dict(inputs, amendments=ordering)
        with pytest.raises(LegacyAdapterError) as excinfo:
            project_legacy_control_state(**ordered_inputs)
        observed.append((excinfo.value.code, excinfo.value.path))
    assert observed == [
        ("ACTIVE_RECEIPT_MISMATCH", "active_task.handoff_receipt_sha256"),
        ("ACTIVE_RECEIPT_MISMATCH", "active_task.handoff_receipt_sha256"),
    ]


def test_false_to_true_content_mutation_fails_content_binding():
    index = [i for i, d in enumerate(_inputs()["amendments"]) if "spec_freeze_activation" in d.path][0]
    inputs = _rebind_amendment(_inputs(), index, parsed_mutator=lambda parsed: parsed["authorization_state"].__setitem__("execution_authorized", True))
    # The structural classifier fires first (defense-in-depth); either code
    # proves the mutation cannot slip through.
    with pytest.raises(LegacyAdapterError) as excinfo:
        project_legacy_control_state(**inputs)
    assert excinfo.value.code in ("LEGACY_AUTHORITY_ESCALATION", "LEGACY_AMENDMENT_CONTENT_MISMATCH")


def test_swapping_content_between_roles_fails_content_binding():
    inputs = _inputs()
    amendments = list(inputs["amendments"])
    temporal_index = [i for i, d in enumerate(amendments) if "temporal_causality_activation" in d.path][0]
    donor_index = [i for i, d in enumerate(amendments) if "execution_governance" in d.path][0]
    temporal_role = json.loads(amendments[temporal_index].raw)["amendment_kind"]
    donor_parsed = json.loads(amendments[donor_index].raw)
    assert donor_parsed.get("document_kind") is None  # no document_kind conflict to muddy the result
    donor_parsed["amendment_kind"] = temporal_role
    swapped_raw = _canonical(donor_parsed)
    swapped_path = "docs/control/amendments/swapped_role_probe.json"
    swapped = LegacyDocument(swapped_path, swapped_raw)
    # Replace the genuine temporal-causality slot with the swapped content;
    # keep the genuine donor document in place so its own role is unaffected.
    amendments[temporal_index] = swapped
    inputs["amendments"] = tuple(amendments)
    receipt = json.loads(inputs["source_receipt"].raw)
    receipt["evidence"].append({"path": swapped_path, "sha256": hashlib.sha256(swapped_raw).hexdigest()})
    inputs["source_receipt"] = LegacyDocument(RECEIPT_PATH, _canonical(receipt))
    active = json.loads(inputs["active_task"].raw)
    active["handoff_receipt_sha256"] = hashlib.sha256(inputs["source_receipt"].raw).hexdigest()
    inputs["active_task"] = LegacyDocument(ACTIVE_PATH, _canonical(active))
    _fails("LEGACY_AMENDMENT_CONTENT_MISMATCH", **inputs)


def test_role_content_binding_survives_amendment_reordering():
    inputs = _inputs()
    inputs["amendments"] = tuple(reversed(inputs["amendments"]))
    state = project_legacy_control_state(**inputs)
    assert state == project_legacy_control_state(**_inputs())


@pytest.mark.parametrize("key", ["mixed_Case_Live_Authorization", "REAL_DATA_ACCESS_PERMISSION", "shadow_execution_granted"])
def test_source_receipt_mixed_case_authority_like_keys_reject_true(key):
    inputs = _mutate_receipt(lambda value: value.__setitem__(key, True))
    _fails("LEGACY_AUTHORITY_ESCALATION", **inputs)


@pytest.mark.parametrize("key", ["mixed_Case_Live_Authorization", "REAL_DATA_ACCESS_PERMISSION", "shadow_execution_granted"])
def test_source_receipt_authority_like_keys_stay_deny_safe_at_false(key):
    inputs = _mutate_receipt(lambda value: value.__setitem__(key, False))
    state = project_legacy_control_state(**inputs)
    _assert_deny_only(state)


# --- v033 transition: receipt index 33, engine-implementation-for-review
# evidence only, no new effective amendment role. ---


@pytest.mark.parametrize("bad_index", [33, 35])
def test_receipt_index_33_and_35_fail_under_current_v034_adapter(bad_index):
    _fails("LEGACY_REVISION_MISMATCH", **_mutate_receipt(lambda value: value.__setitem__("receipt_index", bad_index)))


def test_missing_engine_implementation_binding_fails():
    inputs = _mutate_receipt(lambda value: value.pop("engine_implementation_binding"))
    _fails("LEGACY_MISSING_FIELD", **inputs)


def test_missing_engine_implementation_status_fails():
    inputs = _mutate_receipt(lambda value: value["engine_implementation_binding"].pop("engine_implementation_status"))
    _fails("LEGACY_AUTHORITY_ESCALATION", **inputs)


@pytest.mark.parametrize("bad_status", [
    "EXECUTED",
    "AUTHORIZED",
    "EXECUTION_AUTHORIZED",
    "EFFECTIVE_FOR_EXECUTION",
    "RESULTS_AVAILABLE",
    "SCIENTIFICALLY_VALIDATED",
])
def test_engine_implementation_status_variants_fail_closed(bad_status):
    inputs = _mutate_receipt(lambda value: value["engine_implementation_binding"].__setitem__("engine_implementation_status", bad_status))
    _fails("LEGACY_AUTHORITY_ESCALATION", **inputs)


def test_engine_implementation_status_is_the_only_allowed_value():
    assert _legacy_adapter._ENGINE_IMPLEMENTATION_STATUS_ALLOWED_VALUES == {"IMPLEMENTED_FOR_INDEPENDENT_REVIEW_ONLY"}
    state = project_legacy_control_state(**_inputs())
    _assert_deny_only(state)


def test_engine_implemented_false_fails():
    inputs = _mutate_receipt(lambda value: value["engine_implementation_binding"].__setitem__("engine_implemented", False))
    _fails("LEGACY_REQUIRED_EVIDENCE_MISSING", **inputs)


@pytest.mark.parametrize("field", ["engine_executed", "engine_wired_into_execute_calibration"])
def test_engine_binding_boolean_escalation_fails_closed(field):
    inputs = _mutate_receipt(lambda value: value["engine_implementation_binding"].__setitem__(field, True))
    _fails("LEGACY_AUTHORITY_ESCALATION", **inputs)


@pytest.mark.parametrize("field", ["engine_executed", "engine_wired_into_execute_calibration"])
def test_engine_binding_boolean_stays_deny_safe_at_false(field):
    inputs = _mutate_receipt(lambda value: value["engine_implementation_binding"].__setitem__(field, False))
    state = project_legacy_control_state(**inputs)
    _assert_deny_only(state)

def test_engine_reviewed_false_or_wrong_verdict_fails_closed():
    _fails("LEGACY_AUTHORITY_ESCALATION", **_mutate_receipt(lambda value: value["engine_implementation_binding"].__setitem__("engine_reviewed", False)))
    _fails("LEGACY_AUTHORITY_ESCALATION", **_mutate_receipt(lambda value: value["engine_implementation_binding"].__setitem__("engine_review_verdict", "FWER_PASSED")))


def test_no_new_effective_amendment_role_exists_for_v033():
    roles = {json.loads(document.raw)["amendment_kind"] for document in _inputs()["amendments"]}
    assert roles == _legacy_adapter._REQUIRED_EFFECTIVE_AMENDMENT_ROLES
    assert len(roles) == 7


def test_all_seven_current_effective_amendments_match_frozen_role_digests_v033():
    digests = _legacy_adapter._REQUIRED_EFFECTIVE_AMENDMENT_ROLE_DIGESTS
    assert set(digests) == _legacy_adapter._REQUIRED_EFFECTIVE_AMENDMENT_ROLES
    assert len(digests) == 7
    for document in _inputs()["amendments"]:
        role = json.loads(document.raw)["amendment_kind"]
        assert hashlib.sha256(document.raw).hexdigest() == digests[role]


def test_every_runtime_action_remains_denied_at_v033():
    state = project_legacy_control_state(**_inputs())
    assert set(vars(state.runtime_authorization).values()) == {"DENIED"}
    for action in RuntimeAction:
        result = authorize(state, action)
        assert result.authorized is False


def test_no_raw_python_exception_escapes_content_binding_or_status_mutations():
    mutators = [
        lambda parsed: parsed["authority_non_effects"].__setitem__("live_authorization_granted", True),
        lambda parsed: parsed.__setitem__("amendment_id", "tampered"),
        lambda parsed: parsed.__setitem__("authorization_status", "AUTHORIZED_LIVE_EXECUTION"),
    ]
    for mutator in mutators:
        base = _inputs()
        index = [i for i, d in enumerate(base["amendments"]) if "rng_runtime_specification_amendment_activation" in d.path][0]
        inputs = _rebind_amendment(base, index, parsed_mutator=mutator)
        with pytest.raises(LegacyAdapterError) as excinfo:
            project_legacy_control_state(**inputs)
        assert excinfo.value.code
        assert excinfo.value.path
