import copy
import json
from pathlib import Path

import pytest

from quantbot.sandbox import candidate1_v1 as s

ROOT = Path(__file__).parents[2]
EXAMPLE = ROOT / "docs/sandbox/example_candidate1_v1_variants.json"

def bundle():
    return s.load_bundle(EXAMPLE)[0]

def test_example_and_determinism(tmp_path):
    b, raw, digest = s.load_bundle(EXAMPLE)
    a = s.build_receipt(b, raw, digest)
    c = s.build_receipt(b, raw, digest)
    assert s.canonical_json_bytes(a) == s.canonical_json_bytes(c)
    assert len(a["results"]) == len(b["variants"]) * len(s.SCENARIOS)
    assert a["explored_variant_count"] == 7
    assert all(not key in a for key in ("winner", "rank", "recommendation", "best_variant"))
    assert a["scientific_evidence"] is False and a["real_data_accessed"] is False

def test_pretty_and_compact_semantically_match(tmp_path):
    parsed = json.loads(EXAMPLE.read_text())
    pretty = tmp_path / "pretty.json"; pretty.write_text(json.dumps(parsed, indent=2))
    compact = tmp_path / "compact.json"; compact.write_bytes(s.canonical_json_bytes(parsed))
    pretty_receipt = s.build_receipt(*s.load_bundle(pretty))
    compact_receipt = s.build_receipt(*s.load_bundle(compact))
    assert pretty_receipt["results"] == compact_receipt["results"]
    assert pretty_receipt["variant_bundle"] == compact_receipt["variant_bundle"]

@pytest.mark.parametrize("mutation", [
    lambda b: b["variants"].clear(),
    lambda b: b["variants"].__setitem__(1, copy.deepcopy(b["variants"][0])),
    lambda b: b.update(extra=True),
    lambda b: b["variants"][0].update(rule_kind="NOPE"),
    lambda b: b["variants"][0].update(rationale_kind="NOPE"),
    lambda b: b["variants"][0].update(source_reference="bad"),
    lambda b: b["variants"][3]["parameters"].update(lookback=0),
    lambda b: b["variants"][3]["parameters"].update(deadband=0.0),
    lambda b: b["variants"][3]["parameters"].update(deadband="NaN"),
])
def test_bundle_rejects_bad_shapes(mutation):
    value = copy.deepcopy(bundle()); mutation(value)
    with pytest.raises(s.SandboxValidationError): s.validate_bundle(value)

def test_duplicate_keys_rejected():
    with pytest.raises(s.SandboxValidationError): s.parse_json_bytes(b'{"a":1,"a":2}', "x")

def test_rules_and_no_lookahead():
    v = {"variant_id":"x", "rule_kind":"LAGGED_RETURN_SIGN", "parameters":{"lookback":1,"deadband":"0"}, "rationale_kind":"SOFTWARE_PATH_COVERAGE", "rationale":"x"}
    p = [s.Decimal("1"), s.Decimal("2"), s.Decimal("1")]
    f = [s.Decimal("0")] * 3
    before = s.position_for(v, p, f, 1)
    assert before == 0
    p[-1] = s.Decimal("999")
    assert s.position_for(v, p, f, 1) == before

def test_funding_no_lookahead_and_deadband():
    v = {"variant_id":"x", "rule_kind":"FUNDING_SIGN_FADE", "parameters":{"deadband":"0.1"}, "rationale_kind":"SOFTWARE_PATH_COVERAGE", "rationale":"x"}
    p = [s.Decimal("1")] * 3; f = [s.Decimal("0.1"), s.Decimal("0.2"), s.Decimal("-999")]
    assert s.position_for(v, p, f, 1) == 0
    assert s.position_for(v, p, f, 2) == -1
    f[-1] = s.Decimal("999")
    assert s.position_for(v, p, f, 1) == 0

def test_receipt_verification_and_tamper(tmp_path):
    b, raw, digest = s.load_bundle(EXAMPLE)
    receipt = s.build_receipt(b, raw, digest)
    data = s.canonical_json_bytes(receipt)
    assert s.verify_receipt_bytes(data) == receipt
    bad = copy.deepcopy(receipt); bad["results"][0]["turnover_count"] += 1
    with pytest.raises(s.SandboxValidationError): s.verify_receipt_bytes(s.canonical_json_bytes(bad))
    with pytest.raises(s.SandboxValidationError): s.verify_receipt_bytes(json.dumps(receipt, indent=2).encode())

def test_publication_refuses_existing_and_missing_parent(tmp_path):
    out = tmp_path / "receipt.json"
    s.run_bundle(EXAMPLE, out)
    with pytest.raises(FileExistsError): s.run_bundle(EXAMPLE, out)
    with pytest.raises(FileNotFoundError): s.run_bundle(EXAMPLE, tmp_path / "missing" / "receipt.json")
