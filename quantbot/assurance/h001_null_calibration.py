"""Non-executable planning boundary for a future H001 null calibration.

This module recognizes and validates calibration specification documents but
never executes anything. It implements no DGP generation, no bootstrap, no FWER
calculation, no multiprocessing, no output writing, and no result
serialization. Both entry points below terminate in a fail-closed error; the
error identifies *why* the boundary held, which is the only reviewable signal
this module produces.
"""
from __future__ import annotations

from typing import NoReturn
from .contracts import (
    H001_FREEZE_CANDIDATE_DOCUMENT_KIND,
    AssuranceValidationError,
    validate_calibration_spec_draft,
    validate_calibration_spec_freeze_candidate,
    validate_h001_synthetic_null_calibration_spec_freeze_activation,
)

SUPPORTED_DGPS = ("IID Gaussian", "IID Student-t with df=5", "stationary AR(1), phi=0.3", "stationary AR(1), phi=0.7", "stationary GARCH(1,1)-like volatility", "nine-series common-factor dependence")

def deterministic_seed_domain(spec_id: str) -> str:
    return f"h001-null-calibration/{spec_id}/synthetic-only"

def build_calibration_execution_plan(spec: object, activation: object | None = None) -> NoReturn:
    """Validate a calibration specification, then refuse to plan execution.

    The historical draft is refused as unfrozen; the freeze candidate is refused
    as not effective. An exact activation is recognized but still refused at
    the execution-authorization boundary. Neither refusal is weaker than the
    other: no execution plan object exists in this module at all.
    """
    if isinstance(spec, dict) and spec.get("document_kind") == H001_FREEZE_CANDIDATE_DOCUMENT_KIND:
        validate_calibration_spec_freeze_candidate(spec)
        if activation is not None:
            validate_h001_synthetic_null_calibration_spec_freeze_activation(activation)
            raise AssuranceValidationError("CALIBRATION_EXECUTION_NOT_AUTHORIZED")
        raise AssuranceValidationError("CALIBRATION_SPEC_NOT_EFFECTIVE")
    validate_calibration_spec_draft(spec)
    raise AssuranceValidationError("CALIBRATION_SPEC_NOT_FROZEN")

def execute_calibration(*args: object, **kwargs: object) -> None:
    raise AssuranceValidationError("CALIBRATION_EXECUTION_NOT_AUTHORIZED")
