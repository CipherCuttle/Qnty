import ast
import copy
import json
from pathlib import Path

import pytest

from quantbot.experiment.offline_edge_candidate1_decomposition_binding import (
    validate_candidate1_decomposition_implementation_binding_v0,
)


ROOT = Path(__file__).parents[2]
REGISTRY_PATH = ROOT / "docs/registries/real_btc_candidate1_train_mechanism_decomposition_registry.json"
RECEIPT_PATH = ROOT / "docs/receipts/real_btc_candidate1_train_mechanism_decomposition_v0/implementation_binding_v0.json"


def artifacts():
    registry = json.loads(REGISTRY_PATH.read_text(encoding="utf-8"))
    return registry["entries"][0], RECEIPT_PATH.read_bytes()


def canonical(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True).encode()


def test_production_artifacts_bind_without_execution_or_authorization():
    entry, receipt = artifacts()
    parsed = validate_candidate1_decomposition_implementation_binding_v0(entry, receipt)
    assert parsed["qualified_implementation"]["merge_commit_sha"] == "6d4b0c7fd11afe614edb0d1070ef4a9637e91542"
    assert parsed["qualified_environment"]["environment_manifest_sha256"] == "25f92f2c99f989de7553930ef09ff34e39d9893bcf008cbfd6992a242312b213"
    assert entry["decomposition_execution_count"] == 0
    assert entry["authorization_state"] == {"scientific_use_authorized": False, "paper_trade_authorized": False, "live_integration_authorized": False, "edge_status": "EDGE_UNPROVEN", "live_status": "BLOCK_LIVE_INTEGRATION"}


@pytest.mark.parametrize("mutation", [
    lambda e, r: e.pop("implementation_binding"),
    lambda e, r: e["implementation_binding"].update(extra="no"),
    lambda e, r: e["implementation_binding"].pop("binding_kind"),
    lambda e, r: e["implementation_binding"].update(binding_kind="wrong"),
    lambda e, r: e["implementation_binding"].update(binding_receipt_path="wrong"),
    lambda e, r: e["implementation_binding"].update(binding_receipt_sha256="0" * 64),
    lambda e, r: e["implementation_binding"].update(qualified_implementation_commit="0" * 40),
    lambda e, r: e["implementation_binding"].update(qualified_environment_manifest_sha256="0" * 64),
    lambda e, r: e["implementation_binding"].update(qualified_source_manifest_sha256="0" * 64),
    lambda e, r: e["source_binding"].update(bound_implementation_sha="0" * 40),
    lambda e, r: e["source_binding"].update(source_classification="changed"),
    lambda e, r: e.update(decomposition_execution_budget=True),
    lambda e, r: e.update(decomposition_execution_count=True),
    lambda e, r: e.update(quarantine_access="allowed"),
    lambda e, r: e["authorization_state"].update(scientific_use_authorized=True),
    lambda e, r: e["authorization_state"].update(paper_trade_authorized=True),
    lambda e, r: e["authorization_state"].update(live_integration_authorized=True),
    lambda e, r: e["authorization_state"].update(edge_status="EDGE_PROVEN"),
    lambda e, r: e["authorization_state"].update(live_status="ALLOW_LIVE"),
])
def test_registry_binding_failures_are_closed(mutation):
    entry, receipt = artifacts(); entry = copy.deepcopy(entry)
    mutation(entry, receipt)
    with pytest.raises(ValueError):
        validate_candidate1_decomposition_implementation_binding_v0(entry, receipt)


@pytest.mark.parametrize("mutation", [
    lambda r: r.update(extra="no"), lambda r: r.pop("binding_kind"),
    lambda r: r.update(binding_schema_version="9"), lambda r: r.update(protocol_id="wrong"),
    lambda r: r.update(source_binding_canonical_json_sha256="0" * 64),
    lambda r: r["qualified_implementation"].update(merge_commit_sha="0" * 40),
    lambda r: r["qualified_implementation"].update(main_parent_sha="0" * 40),
    lambda r: r["qualified_implementation"].update(feature_parent_sha="0" * 40),
    lambda r: r["qualified_implementation"].update(qualified_source_files=[]),
    lambda r: r["qualified_implementation"].update(qualified_source_files=r["qualified_implementation"]["qualified_source_files"][:5]),
    lambda r: r["qualified_implementation"]["qualified_source_files"].append(copy.deepcopy(r["qualified_implementation"]["qualified_source_files"][0])),
    lambda r: r["qualified_implementation"]["qualified_source_files"][0].update(path="/absolute"),
    lambda r: r["qualified_implementation"]["qualified_source_files"][0].update(path="../parent"),
    lambda r: r["qualified_implementation"]["qualified_source_files"][0].update(sha256="BAD"),
    lambda r: r["qualified_implementation"].update(qualified_source_manifest_sha256="0" * 64),
    lambda r: r["qualified_environment"].update(python_version="3.11"),
    lambda r: r["qualified_environment"].update(python_soabi="wrong"),
    lambda r: r["qualified_environment"].update(architecture="arm"),
    lambda r: r["qualified_environment"].update(package_count=15),
    lambda r: r["qualified_environment"].update(package_count=True),
    lambda r: r["qualified_environment"].update(package_lock_kind="wrong"),
    lambda r: r["qualified_environment"].update(wheelhouse_manifest_sha256="0" * 64),
    lambda r: r["qualification"].update(qualification_log_manifest_sha256="0" * 64),
    lambda r: r["qualification"]["focused"].update(passed=0),
    lambda r: r["qualification"]["release_smoke"].update(exit_code=1),
    lambda r: r["qualification"]["full_suite"].update(failed=1),
    lambda r: r["qualification"]["full_suite"].update(skipped=1),
    lambda r: r["qualification"]["full_suite"].update(xfail=1),
    lambda r: r["qualification"]["full_suite"].update(duration_seconds=1),
    lambda r: r["safety_snapshot"].update(real_data_executed=True),
    lambda r: r["safety_snapshot"].update(decomposition_executed=True),
    lambda r: r["precondition_state"].update(final_no_computation_preflight_passed="satisfied"),
])
def test_receipt_fact_failures_are_closed(mutation):
    entry, receipt = artifacts(); parsed = json.loads(receipt); mutation(parsed)
    with pytest.raises(ValueError):
        validate_candidate1_decomposition_implementation_binding_v0(entry, canonical(parsed))


@pytest.mark.parametrize("receipt", [b"\xff", b"{", b"[]"])
def test_invalid_receipt_encoding_json_and_shape_fail_closed(receipt):
    entry, _ = artifacts()
    with pytest.raises(ValueError):
        validate_candidate1_decomposition_implementation_binding_v0(entry, receipt)


def test_noncanonical_and_trailing_newline_fail_closed():
    entry, receipt = artifacts()
    with pytest.raises(ValueError): validate_candidate1_decomposition_implementation_binding_v0(entry, b"{ }" )
    with pytest.raises(ValueError): validate_candidate1_decomposition_implementation_binding_v0(entry, receipt + b"\n")


def test_validation_is_deterministic_and_does_not_mutate_inputs():
    entry, receipt = artifacts(); before = copy.deepcopy(entry); bytes_before = bytes(receipt)
    assert validate_candidate1_decomposition_implementation_binding_v0(entry, receipt) == validate_candidate1_decomposition_implementation_binding_v0(entry, receipt)
    assert entry == before and receipt == bytes_before


def test_validator_has_no_forbidden_runtime_imports():
    path = ROOT / "quantbot/experiment/offline_edge_candidate1_decomposition_binding.py"
    tree = ast.parse(path.read_text(encoding="utf-8"))
    imports = {alias.name.split(".")[0] for node in ast.walk(tree) if isinstance(node, (ast.Import, ast.ImportFrom)) for alias in node.names}
    assert not imports & {"pandas", "numpy", "requests", "sqlalchemy", "sqlite3", "quantbot.engine", "quantbot.exchange", "quantbot.paper", "quantbot.observer"}
