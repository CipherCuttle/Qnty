import ast
import json
from pathlib import Path
from typing import NoReturn

import pytest

from quantbot.assurance.contracts import AssuranceValidationError, build_synthetic_canary_payloads, validate_synthetic_canary_scaffold
import quantbot.assurance.h001_null_calibration as calibration
from quantbot.assurance.h001_null_calibration import build_calibration_execution_plan, execute_calibration

ROOT = Path(__file__).parents[2]

def test_current_draft_cannot_build_or_execute_calibration_plan():
    assert not hasattr(calibration, "CalibrationExecutionPlan")
    spec = json.loads((ROOT / "docs/assurance/h001_synthetic_null_calibration_spec_draft_v001.json").read_bytes())
    with pytest.raises(AssuranceValidationError, match="CALIBRATION_SPEC_NOT_FROZEN"):
        build_calibration_execution_plan(spec)
    with pytest.raises(AssuranceValidationError, match="CALIBRATION_EXECUTION_NOT_AUTHORIZED"):
        execute_calibration()

def test_invalid_calibration_spec_preserves_contract_error():
    spec = json.loads((ROOT / "docs/assurance/h001_synthetic_null_calibration_spec_draft_v001.json").read_bytes())
    spec["proposed_design"]["hac_lag"] = 22
    with pytest.raises(AssuranceValidationError, match="proposed calibration design drifted"):
        build_calibration_execution_plan(spec)

def test_canary_payloads_are_in_memory_and_exact():
    descriptor = json.loads((ROOT / "docs/assurance/synthetic_artifact_canary_scaffold_v001.json").read_bytes())
    validate_synthetic_canary_scaffold(descriptor)
    payloads = build_synthetic_canary_payloads()
    assert payloads == {"alpha/payload.txt": b"QNTY_SYNTHETIC_CANARY_ALPHA_V1", "beta/payload.bin": bytes.fromhex("00514e5459ff")}
    assert not (ROOT / "alpha").exists()
    with pytest.raises(ValueError): validate_synthetic_canary_scaffold(dict(descriptor, status="EXECUTED"))


FREEZE_CANDIDATE = ROOT / "docs/assurance/h001_synthetic_null_calibration_spec_freeze_candidate_v001.json"


def freeze_candidate():
    return json.loads(FREEZE_CANDIDATE.read_bytes())


def freeze_activation():
    return json.loads((ROOT / "docs/control/amendments/candidate1_h001_synthetic_null_calibration_spec_freeze_activation_v001.json").read_bytes())


def test_freeze_candidate_cannot_build_an_execution_plan():
    """The candidate is recognized and fully validated, then refused: recognized
    is not the same as effective."""
    with pytest.raises(AssuranceValidationError, match="CALIBRATION_SPEC_NOT_EFFECTIVE"):
        build_calibration_execution_plan(freeze_candidate())


def test_historical_draft_and_candidate_fail_closed_with_distinct_reasons():
    draft = json.loads((ROOT / "docs/assurance/h001_synthetic_null_calibration_spec_draft_v001.json").read_bytes())
    with pytest.raises(AssuranceValidationError, match="CALIBRATION_SPEC_NOT_FROZEN"):
        build_calibration_execution_plan(draft)
    with pytest.raises(AssuranceValidationError, match="CALIBRATION_SPEC_NOT_EFFECTIVE"):
        build_calibration_execution_plan(freeze_candidate())


def test_reviewed_candidate_with_exact_activation_reaches_execution_boundary():
    with pytest.raises(AssuranceValidationError, match="CALIBRATION_EXECUTION_NOT_AUTHORIZED"):
        build_calibration_execution_plan(freeze_candidate(), freeze_activation())


def test_invalid_activation_is_rejected_by_strict_activation_validation():
    activation = freeze_activation()
    activation["hash_bindings"]["effective_specification"]["sha256"] = "0" * 64
    with pytest.raises(AssuranceValidationError, match="hash binding"):
        build_calibration_execution_plan(freeze_candidate(), activation)


def test_no_execution_plan_object_can_be_constructed():
    assert not hasattr(calibration, "CalibrationExecutionPlan")
    assert "NoReturn" in str(calibration.build_calibration_execution_plan.__annotations__["return"])


@pytest.mark.parametrize("argument", [
    None, {}, [], "spec", 0,
    pytest.param("candidate", id="candidate"),
    pytest.param("draft", id="draft"),
])
def test_execute_calibration_is_never_authorized(argument):
    if argument == "candidate":
        argument = freeze_candidate()
    elif argument == "draft":
        argument = json.loads((ROOT / "docs/assurance/h001_synthetic_null_calibration_spec_draft_v001.json").read_bytes())
    with pytest.raises(AssuranceValidationError, match="CALIBRATION_EXECUTION_NOT_AUTHORIZED"):
        execute_calibration(argument)
    with pytest.raises(AssuranceValidationError, match="CALIBRATION_EXECUTION_NOT_AUTHORIZED"):
        execute_calibration(spec=argument)


def test_invalid_freeze_candidate_is_rejected_before_the_boundary_message():
    """A candidate that overstates its authority must fail contract validation
    rather than reaching the (weaker-sounding) not-effective refusal."""
    spec = freeze_candidate()
    spec["authorization_state"]["execution_authorized"] = True
    with pytest.raises(AssuranceValidationError) as error:
        build_calibration_execution_plan(spec)
    assert "CALIBRATION_SPEC_NOT_EFFECTIVE" not in str(error.value)
    spec = freeze_candidate()
    spec["registered_test_target"]["hac_lag"] = 22
    with pytest.raises(AssuranceValidationError, match="hac_lag"):
        build_calibration_execution_plan(spec)


def test_harness_implements_no_calibration_machinery():
    source = (ROOT / "quantbot/assurance/h001_null_calibration.py").read_text(encoding="utf-8")
    tree = ast.parse(source)
    assert {node.name for node in tree.body if isinstance(node, ast.FunctionDef)} == {
        "deterministic_seed_domain", "build_calibration_execution_plan", "execute_calibration",
    }
    assert not [node for node in tree.body if isinstance(node, ast.ClassDef)]
    # Scan imports and executable references, not prose: the module docstring
    # legitimately names the machinery it refuses to implement.
    imported = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imported.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom):
            imported.add(node.module or "")
    assert imported <= {"__future__", "typing", "contracts"}, f"unexpected import: {imported}"
    for banned in ("numpy", "multiprocessing", "concurrent", "random", "pandas", "os", "pathlib", "csv"):
        assert banned not in imported, f"calibration harness must not import {banned}"
    referenced = {node.id for node in ast.walk(tree) if isinstance(node, ast.Name)}
    referenced |= {node.attr for node in ast.walk(tree) if isinstance(node, ast.Attribute)}
    for banned in ("open", "Pool", "to_csv", "dump", "dumps", "write_bytes", "write_text", "mkdir", "normal", "standard_normal", "default_rng", "Philox", "Generator"):
        assert banned not in referenced, f"calibration harness must not call {banned}"


def test_seed_domain_helper_matches_the_candidate_seed_contract():
    candidate = freeze_candidate()
    assert calibration.deterministic_seed_domain(candidate["document_id"]) == candidate["seed_contract"]["seed_domain"]
