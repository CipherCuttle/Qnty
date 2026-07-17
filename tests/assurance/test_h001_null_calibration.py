import json
from pathlib import Path

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
