import ast
import copy
import dataclasses
import json
from pathlib import Path

import pytest

import quantbot.control.state as control_state_module
from quantbot.control import (
    ControlState,
    ControlStateValidationError,
    RuntimeAction,
    authorize,
    load_and_validate_control_state,
    validate_transition,
)

BASE_STATE = {
    "control_kind": "qnty_control_state",
    "schema_version": "1.0.0",
    "state_revision": 32,
    "protocol_id": "real_btc_candidate1_train_mechanism_decomposition_v0",
    "scientific_state": {
        "hypothesis_id": "H001",
        "edge_status": "EDGE_UNPROVEN",
        "live_status": "BLOCK_LIVE_INTEGRATION",
        "real_data_access": "FORBIDDEN",
        "synthetic_calibration_execution": "NOT_AUTHORIZED",
        "execution_count": 0,
        "execution_budget": 0,
    },
    "administrative_state": {
        "workflow_status": "UNDER_REVIEW",
        "proposal_ref": "docs/control/amendments/example.json",
        "superseded_by": None,
    },
    "runtime_authorization": {
        "public_data_fetch": "DENIED",
        "h001_real_data_fetch": "DENIED",
        "synthetic_calibration": "DENIED",
        "paper_execution": "DENIED",
        "shadow_execution": "DENIED",
        "live_execution": "DENIED",
    },
    "provenance": {
        "source_receipt_path": "docs/control/tasks/RECOVER_OR_RETIRE_CANDIDATE1_V0_FROZEN_INPUT/handoff_v031.json",
        "source_receipt_sha256": "a" * 64,
        "source_head_commit": "b" * 40,
    },
}

TOP_KEYS = list(BASE_STATE)
NESTED_OBJECTS = {
    "scientific_state": list(BASE_STATE["scientific_state"]),
    "administrative_state": list(BASE_STATE["administrative_state"]),
    "runtime_authorization": list(BASE_STATE["runtime_authorization"]),
    "provenance": list(BASE_STATE["provenance"]),
}
PATH_FIELDS = [
    ("administrative_state", "proposal_ref"),
    ("provenance", "source_receipt_path"),
]
BAD_PATHS = [
    "/etc/passwd",
    "../../etc/passwd",
    "docs/../../../etc/passwd",
    "https://example.com/x.json",
    "file:///etc/passwd",
    "docs/*.json",
    "docs/control/[abc].json",
    "docs/control/{a,b}.json",
]
BAD_SHA256 = ["a" * 63, "a" * 65, "A" * 64, "g" * 64, "not-a-hash"]
BAD_COMMIT_SHA = ["b" * 39, "b" * 41, "B" * 40, "z" * 40, "not-a-sha"]
UNSUPPORTED_SCHEMA_VERSIONS = ["0.9.0", "2.0.0", "1.0", "1.0.0.0"]
SCIENTIFIC_LITERAL_FIELDS = [
    ("hypothesis_id", "H002"),
    ("edge_status", "EDGE_PROVEN"),
    ("live_status", "ALLOW_LIVE_INTEGRATION"),
    ("real_data_access", "AUTHORIZED"),
    ("synthetic_calibration_execution", "AUTHORIZED"),
]


def _canonical_bytes(value: object) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True).encode("utf-8")


def _clone() -> dict:
    return copy.deepcopy(BASE_STATE)


def _set_path(document: dict, path: tuple, value) -> dict:
    cursor = document
    for key in path[:-1]:
        cursor = cursor[key]
    cursor[path[-1]] = value
    return document


def _del_path(document: dict, path: tuple) -> dict:
    cursor = document
    for key in path[:-1]:
        cursor = cursor[key]
    del cursor[path[-1]]
    return document


def _mutated(path: tuple, value) -> dict:
    return _set_path(_clone(), path, value)


def _missing(path: tuple) -> dict:
    return _del_path(_clone(), path)


def _with_unknown(path_prefix: tuple) -> dict:
    document = _clone()
    cursor = document
    for key in path_prefix:
        cursor = cursor[key]
    cursor["unexpected_field"] = "x"
    return document


def _load(document: dict) -> ControlState:
    return load_and_validate_control_state(_canonical_bytes(document))


def _assert_fails(raw: bytes, code: str) -> None:
    with pytest.raises(ControlStateValidationError) as excinfo:
        load_and_validate_control_state(raw)
    assert excinfo.value.code == code


def test_valid_fixture_loads():
    state = _load(BASE_STATE)
    assert state.control_kind == "qnty_control_state"
    assert state.schema_version == "1.0.0"
    assert state.state_revision == 32
    assert state.scientific_state.hypothesis_id == "H001"
    assert state.scientific_state.execution_count == 0
    assert state.runtime_authorization.live_execution == "DENIED"


@pytest.mark.parametrize(
    "raw",
    [
        json.dumps(BASE_STATE, separators=(",", ":"), ensure_ascii=True).encode("utf-8"),
        json.dumps(BASE_STATE, sort_keys=True, separators=(", ", ": "), ensure_ascii=True).encode("utf-8"),
        _canonical_bytes(BASE_STATE) + b"\n",
    ],
)
def test_non_canonical_json_rejected(raw):
    _assert_fails(raw, "NON_CANONICAL_JSON")


def test_duplicate_key_fails():
    text = _canonical_bytes(BASE_STATE).decode("utf-8")
    duplicated = text.replace('"state_revision":32', '"state_revision":32,"state_revision":32', 1)
    _assert_fails(duplicated.encode("utf-8"), "DUPLICATE_KEY")


def test_invalid_json_fails():
    _assert_fails(b"{not valid json", "INVALID_JSON")


@pytest.mark.parametrize("key", TOP_KEYS)
def test_missing_top_level_field(key):
    _assert_fails(_canonical_bytes(_missing((key,))), "MISSING_FIELD")


def test_unknown_top_level_field():
    _assert_fails(_canonical_bytes(_with_unknown(())), "UNKNOWN_FIELD")


@pytest.mark.parametrize(
    "obj_key,field_key",
    [(obj_key, field_key) for obj_key, fields in NESTED_OBJECTS.items() for field_key in fields],
)
def test_missing_nested_field(obj_key, field_key):
    _assert_fails(_canonical_bytes(_missing((obj_key, field_key))), "MISSING_FIELD")


@pytest.mark.parametrize("obj_key", list(NESTED_OBJECTS))
def test_unknown_nested_field(obj_key):
    _assert_fails(_canonical_bytes(_with_unknown((obj_key,))), "UNKNOWN_FIELD")


def test_boolean_state_revision_fails():
    _assert_fails(_canonical_bytes(_mutated(("state_revision",), True)), "WRONG_TYPE")


@pytest.mark.parametrize("bad_revision", [0, -1, -100])
def test_non_positive_state_revision_fails(bad_revision):
    _assert_fails(_canonical_bytes(_mutated(("state_revision",), bad_revision)), "INVALID_REVISION")


@pytest.mark.parametrize("field,bad_value", SCIENTIFIC_LITERAL_FIELDS)
def test_wrong_scientific_invariant_fails(field, bad_value):
    _assert_fails(_canonical_bytes(_mutated(("scientific_state", field), bad_value)), "INVALID_LITERAL")


@pytest.mark.parametrize("bad_count", [1, -1, 100])
def test_nonzero_execution_count_fails(bad_count):
    _assert_fails(
        _canonical_bytes(_mutated(("scientific_state", "execution_count"), bad_count)), "INVALID_LITERAL"
    )


@pytest.mark.parametrize("bad_budget", [1, -1, 100])
def test_nonzero_execution_budget_fails(bad_budget):
    _assert_fails(
        _canonical_bytes(_mutated(("scientific_state", "execution_budget"), bad_budget)), "INVALID_LITERAL"
    )


@pytest.mark.parametrize("field", NESTED_OBJECTS["runtime_authorization"])
def test_runtime_action_must_be_denied(field):
    _assert_fails(
        _canonical_bytes(_mutated(("runtime_authorization", field), "AUTHORIZED")), "INVALID_LITERAL"
    )


@pytest.mark.parametrize("obj_key,field_key", PATH_FIELDS)
@pytest.mark.parametrize("bad_path", BAD_PATHS)
def test_unsafe_path_rejected(obj_key, field_key, bad_path):
    _assert_fails(_canonical_bytes(_mutated((obj_key, field_key), bad_path)), "INVALID_PATH")


@pytest.mark.parametrize("bad_sha", BAD_SHA256)
def test_malformed_receipt_sha_fails(bad_sha):
    _assert_fails(
        _canonical_bytes(_mutated(("provenance", "source_receipt_sha256"), bad_sha)), "INVALID_SHA256"
    )


@pytest.mark.parametrize("bad_sha", BAD_COMMIT_SHA)
def test_malformed_commit_sha_fails(bad_sha):
    _assert_fails(
        _canonical_bytes(_mutated(("provenance", "source_head_commit"), bad_sha)), "INVALID_COMMIT_SHA"
    )


@pytest.mark.parametrize("bad_version", UNSUPPORTED_SCHEMA_VERSIONS)
def test_unsupported_schema_version_fails(bad_version):
    _assert_fails(_canonical_bytes(_mutated(("schema_version",), bad_version)), "UNSUPPORTED_SCHEMA_VERSION")


@pytest.mark.parametrize("action", list(RuntimeAction))
def test_authorize_denies_all_actions(action):
    state = _load(BASE_STATE)
    decision = authorize(state, action)
    assert decision.authorized is False
    assert decision.action is action
    assert decision.state_revision == state.state_revision


def test_authorize_ignores_administrative_state():
    state_a = _load(BASE_STATE)
    other = _mutated(("administrative_state", "workflow_status"), "APPROVED")
    other = _set_path(other, ("administrative_state", "proposal_ref"), "docs/control/amendments/other.json")
    other = _set_path(other, ("administrative_state", "superseded_by"), "docs/control/amendments/example.json")
    state_b = _load(other)
    for action in RuntimeAction:
        assert authorize(state_a, action) == authorize(state_b, action)


@pytest.mark.parametrize("bad_action", ["live_execution", "totally_unknown_action"])
def test_authorize_rejects_non_enum_action(bad_action):
    state = _load(BASE_STATE)
    with pytest.raises(TypeError):
        authorize(state, bad_action)


def test_authorize_rejects_raw_dict_state():
    with pytest.raises(TypeError):
        authorize(BASE_STATE, RuntimeAction.LIVE_EXECUTION)


def test_valid_transition_passes():
    previous = _load(BASE_STATE)
    candidate = _load(_mutated(("state_revision",), 33))
    validate_transition(previous, candidate)


@pytest.mark.parametrize(
    "new_revision,expected_code",
    [(32, "STALE_REVISION"), (31, "STALE_REVISION"), (34, "REVISION_GAP"), (100, "REVISION_GAP")],
)
def test_invalid_revision_transition(new_revision, expected_code):
    previous = _load(BASE_STATE)
    candidate = _load(_mutated(("state_revision",), new_revision))
    with pytest.raises(ControlStateValidationError) as excinfo:
        validate_transition(previous, candidate)
    assert excinfo.value.code == expected_code


def test_transition_rejects_protocol_change():
    previous = _load(BASE_STATE)
    candidate_doc = _mutated(("state_revision",), 33)
    candidate_doc = _set_path(candidate_doc, ("protocol_id",), "different_protocol_v0")
    candidate = _load(candidate_doc)
    with pytest.raises(ControlStateValidationError) as excinfo:
        validate_transition(previous, candidate)
    assert excinfo.value.code == "IDENTITY_CHANGED"


def test_transition_rejects_hypothesis_change():
    previous = _load(BASE_STATE)
    candidate = dataclasses.replace(
        previous,
        state_revision=33,
        scientific_state=dataclasses.replace(previous.scientific_state, hypothesis_id="H002"),
    )
    with pytest.raises(ControlStateValidationError) as excinfo:
        validate_transition(previous, candidate)
    assert excinfo.value.code == "IDENTITY_CHANGED"


def test_transition_rejects_schema_version_change():
    previous = _load(BASE_STATE)
    candidate = dataclasses.replace(previous, state_revision=33, schema_version="2.0.0")
    with pytest.raises(ControlStateValidationError) as excinfo:
        validate_transition(previous, candidate)
    assert excinfo.value.code == "IDENTITY_CHANGED"


def test_validate_transition_rejects_non_control_state_arguments():
    previous = _load(BASE_STATE)
    with pytest.raises(TypeError):
        validate_transition(previous, BASE_STATE)
    with pytest.raises(TypeError):
        validate_transition(BASE_STATE, previous)


def _module_ast() -> ast.Module:
    source_path = Path(control_state_module.__file__)
    return ast.parse(source_path.read_text(encoding="utf-8"))


def test_module_imports_are_standard_library_only():
    allowed = {"json", "re", "dataclasses", "enum"}
    tree = _module_ast()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                assert alias.name.split(".")[0] in allowed
        elif isinstance(node, ast.ImportFrom):
            assert node.module is not None
            assert node.module.split(".")[0] in allowed


def test_module_has_no_dangerous_capabilities():
    forbidden_calls = {"eval", "exec", "compile", "__import__", "open", "input"}
    tree = _module_ast()
    for node in ast.walk(tree):
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Name):
            assert node.func.id not in forbidden_calls


def test_no_existing_module_imports_new_package_outside_this_pr():
    repo_root = Path(__file__).resolve().parents[2]
    excluded_dir_parts = {".git", ".venv", "__pycache__"}
    hits = []
    for path in repo_root.rglob("*.py"):
        rel = path.relative_to(repo_root)
        if excluded_dir_parts & set(rel.parts):
            continue
        if rel.parts[:2] == ("quantbot", "control"):
            continue
        if rel == Path("tests/control/test_control_state.py"):
            continue
        text = path.read_text(encoding="utf-8", errors="ignore")
        if "quantbot.control" in text or "quantbot import control" in text:
            hits.append(str(rel))
    assert hits == []
