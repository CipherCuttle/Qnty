"""Non-executable planning boundary for a future H001 null calibration."""
from __future__ import annotations

from dataclasses import dataclass
from .contracts import AssuranceValidationError, validate_calibration_spec_draft

SUPPORTED_DGPS = ("IID Gaussian", "IID Student-t with df=5", "stationary AR(1), phi=0.3", "stationary AR(1), phi=0.7", "stationary GARCH(1,1)-like volatility", "nine-series common-factor dependence")

@dataclass(frozen=True)
class CalibrationExecutionPlan:
    spec_id: str
    seed_domain: str
    dgp_identities: tuple[str, ...]

def deterministic_seed_domain(spec_id: str) -> str:
    return f"h001-null-calibration/{spec_id}/synthetic-only"

def build_calibration_execution_plan(spec: object) -> CalibrationExecutionPlan:
    try:
        validate_calibration_spec_draft(spec)
    except AssuranceValidationError as error:
        raise AssuranceValidationError("CALIBRATION_SPEC_NOT_FROZEN") from error
    raise AssuranceValidationError("CALIBRATION_SPEC_NOT_FROZEN")

def execute_calibration(*args: object, **kwargs: object) -> None:
    raise AssuranceValidationError("CALIBRATION_EXECUTION_NOT_AUTHORIZED")
