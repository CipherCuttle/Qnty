import copy
import json
import re
from decimal import Decimal
from pathlib import Path

import pytest

from quantbot.sandbox import candidate1_v1 as s
from quantbot.sandbox import candidate1_v1_cli as cli

ROOT = Path(__file__).parents[2]
EXAMPLE = ROOT / "docs/sandbox/example_candidate1_v1_variants.json"

# Stable contract fingerprints after the accounting/contract repair. They change
# only when the generic mechanical assumptions change, which must be deliberate.
RULE_CONTRACT_SHA256 = "7f55506bd7b6f43988fb4c2eb2aefac6e7526e9064231649ae1f0495bab1ecad"
ACCOUNTING_CONTRACT_SHA256 = "922977fc74ad59ba32c848bf27977f0579a61f544d830bac64fbb25abd15436c"
SCENARIO_CONTRACT_SHA256 = "7c42391951b2e4cc3dc56402504a47827d2898f8a32d211b71f125ad6f0b516a"

HEX64 = re.compile(r"\A[0-9a-f]{64}\Z")


def bundle():
    return s.load_bundle(EXAMPLE)[0]


def _variant(rule, **params):
    return {"variant_id": "x", "rule_kind": rule, "parameters": params,
            "rationale_kind": "SOFTWARE_PATH_COVERAGE", "rationale": "x"}


def _reference(variant, scenario):
    """Independent recomputation of a result strictly from the declared contract."""
    prices = [Decimal(x) for x in scenario["price_path"]]
    funding = [Decimal(x) for x in scenario["funding_path"]]
    positions = [s.position_for(variant, prices, funding, t) for t in range(len(prices) - 1)]
    prev = 0
    turnover = 0
    costs = []
    for pos in positions:
        costs.append(s.TRANSACTION_COST * abs(pos - prev))
        if pos != prev:
            turnover += 1
        prev = pos
    mean_cost = str(sum(costs, Decimal(0)) / len(costs))
    return {
        "positions": positions,
        "long": positions.count(1),
        "short": positions.count(-1),
        "flat": positions.count(0),
        "turnover": turnover,
        "mean_cost": mean_cost,
        "interval_count": len(positions),
    }


# --------------------------------------------------------------------------- #
# Determinism, provenance, and existing invariants
# --------------------------------------------------------------------------- #

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


# --------------------------------------------------------------------------- #
# Accounting correctness over every variant/scenario result
# --------------------------------------------------------------------------- #

def test_accounting_invariants_over_all_results():
    b = bundle()
    receipt = s.build_receipt(b, *s.load_bundle(EXAMPLE)[1:])
    by_variant = {v["variant_id"]: v for v in b["variants"]}
    scenarios = {sc["scenario_id"]: sc for sc in s.SCENARIOS}
    for result in receipt["results"]:
        variant = by_variant[result["variant_id"]]
        scenario = scenarios[result["scenario_id"]]
        ref = _reference(variant, scenario)
        active = result["active_slot_count"]
        # active = long + short and active + flat = evaluated interval count
        assert active == result["long_slot_count"] + result["short_slot_count"]
        assert active + result["flat_slot_count"] == ref["interval_count"]
        assert active + result["flat_slot_count"] == scenario["observation_count"] - 1
        # counts agree with the independent contract recomputation
        assert result["long_slot_count"] == ref["long"]
        assert result["short_slot_count"] == ref["short"]
        assert result["flat_slot_count"] == ref["flat"]
        # turnover and mean cost agree with the declared contract
        assert result["turnover_count"] == ref["turnover"]
        assert result["mean_cost_drag"] == ref["mean_cost"]
        # terminal-position semantics: exactly N-1 evaluated intervals, no
        # terminal liquidation cost beyond those intervals.
        assert len(ref["positions"]) == scenario["observation_count"] - 1


def test_always_flat_long_short_counts():
    b = bundle()
    receipt = s.build_receipt(b, *s.load_bundle(EXAMPLE)[1:])
    flat = [r for r in receipt["results"] if r["variant_id"] == "always-flat-v001"]
    lng = [r for r in receipt["results"] if r["variant_id"] == "always-long-v001"]
    sht = [r for r in receipt["results"] if r["variant_id"] == "always-short-v001"]
    assert flat and lng and sht
    for r in flat:
        interval_count = r["active_slot_count"] + r["flat_slot_count"]
        assert r["active_slot_count"] == 0
        assert r["flat_slot_count"] == interval_count
        assert Decimal(r["mean_cost_drag"]) == 0
        assert r["turnover_count"] == 0
    for r in lng:
        interval_count = r["active_slot_count"] + r["flat_slot_count"]
        assert r["active_slot_count"] == interval_count
        assert r["long_slot_count"] == interval_count and r["short_slot_count"] == 0
    for r in sht:
        interval_count = r["active_slot_count"] + r["flat_slot_count"]
        assert r["active_slot_count"] == interval_count
        assert r["short_slot_count"] == interval_count and r["long_slot_count"] == 0


# --------------------------------------------------------------------------- #
# Contract completeness and fingerprint stability
# --------------------------------------------------------------------------- #

def test_rule_contract_binds_all_rules():
    contract = s.RULE_CONTRACT
    assert set(contract["rule_kinds"]) == set(s.RULE_KINDS)
    assert contract["position_domain"] == [-1, 0, 1]
    for rule in s.RULE_KINDS:
        assert rule in contract["formulas"] and contract["formulas"][rule]
        assert rule in contract["warmup"]
        assert rule in contract["parameter_schema"]
    # parameter types and ranges are bound
    for rule in ("LAGGED_RETURN_SIGN", "LAGGED_RETURN_FADE"):
        schema = contract["parameter_schema"][rule]
        assert schema["lookback"] == {"type": "int", "min": 1, "max": 16}
        assert schema["deadband"]["type"] == "decimal_string"
    assert contract["parameter_schema"]["FUNDING_SIGN_FADE"]["deadband"]["type"] == "decimal_string"
    for key in ("sign_definition", "deadband_comparison", "information_set", "decision_constraint"):
        assert contract[key]


def test_accounting_contract_binds_all_formulas():
    contract = s.ACCOUNTING_CONTRACT
    for key in ("evaluated_interval", "position_timing", "initial_position", "price_component",
                "funding_component", "transaction_cost_formula", "net", "turnover_definition",
                "terminal_liquidation", "mean_denominator", "active_slot_count", "long_slot_count",
                "short_slot_count", "flat_slot_count", "position_series_serialization"):
        assert contract[key]
    assert "excluded" in contract["terminal_liquidation"]
    assert contract["count_invariants"] == [
        "active_slot_count == long_slot_count + short_slot_count",
        "active_slot_count + flat_slot_count == evaluated_interval_count",
    ]


def test_contract_fingerprints_are_stable():
    assert s._canonical_digest(s.RULE_CONTRACT) == RULE_CONTRACT_SHA256
    assert s._canonical_digest(s.ACCOUNTING_CONTRACT) == ACCOUNTING_CONTRACT_SHA256
    assert s._canonical_digest(s.SCENARIO_CONTRACT) == SCENARIO_CONTRACT_SHA256


def test_receipt_records_contract_fingerprints():
    receipt = s.build_receipt(*s.load_bundle(EXAMPLE))
    assert receipt["rule_contract_sha256"] == RULE_CONTRACT_SHA256
    assert receipt["accounting_contract_sha256"] == ACCOUNTING_CONTRACT_SHA256
    assert receipt["scenario_contract_sha256"] == SCENARIO_CONTRACT_SHA256


@pytest.mark.parametrize("field", ["rule_contract_sha256", "accounting_contract_sha256", "scenario_contract_sha256"])
def test_tampering_contract_fingerprint_fails_verification(field):
    receipt = s.build_receipt(*s.load_bundle(EXAMPLE))
    bad = copy.deepcopy(receipt)
    bad[field] = "0" * 64
    with pytest.raises(s.SandboxVerificationError):
        s.verify_receipt_bytes(s.canonical_json_bytes(bad))


def test_all_sha_fields_are_lowercase_hex():
    receipt = s.build_receipt(*s.load_bundle(EXAMPLE))
    for field in ("raw_input_sha256", "canonical_bundle_sha256", "scenario_contract_sha256",
                  "rule_contract_sha256", "accounting_contract_sha256", "run_fingerprint"):
        assert HEX64.match(receipt[field]), field
    for result in receipt["results"]:
        assert HEX64.match(result["position_series_sha256"])


def test_non_hex_sha_field_fails_verification():
    receipt = s.build_receipt(*s.load_bundle(EXAMPLE))
    bad = copy.deepcopy(receipt)
    bad["rule_contract_sha256"] = bad["rule_contract_sha256"].upper()
    with pytest.raises(s.SandboxVerificationError):
        s.verify_receipt_bytes(s.canonical_json_bytes(bad))


# --------------------------------------------------------------------------- #
# No-lookahead on active (non-warm-up) decisions
# --------------------------------------------------------------------------- #

# rule, prices, funding, decision index t, expected active position, a prior
# index the formula legitimately reads, and a replacement value that flips it.
_LOOKAHEAD_CASES = [
    ("LAGGED_RETURN_SIGN", {"lookback": 1, "deadband": "0"},
     ["1", "2", "3", "4", "5", "6"], ["0"] * 6, 2, 1, 1, "0"),
    ("LAGGED_RETURN_FADE", {"lookback": 1, "deadband": "0"},
     ["1", "2", "3", "4", "5", "6"], ["0"] * 6, 2, -1, 1, "0"),
    ("FUNDING_SIGN_FADE", {"deadband": "0"},
     ["1"] * 6, ["0.1", "0.2", "0.3", "0.4", "0.5", "0.6"], 1, -1, 0, "-0.5"),
]


@pytest.mark.parametrize("rule,params,prices,funding,t,expected,prior_idx,prior_new", _LOOKAHEAD_CASES)
def test_no_lookahead_on_active_decision(rule, params, prices, funding, t, expected, prior_idx, prior_new):
    variant = _variant(rule, **params)
    p = [Decimal(x) for x in prices]
    f = [Decimal(x) for x in funding]
    baseline = s.position_for(variant, p, f, t)
    assert baseline == expected  # the probe exercises an active long/short decision, not warm-up

    # Mutating every observation at or after t must not change position(t).
    p_future = [v + Decimal("1000") if i >= t else v for i, v in enumerate(p)]
    f_future = [v + Decimal("1000") if i >= t else v for i, v in enumerate(f)]
    assert s.position_for(variant, p_future, f_future, t) == baseline

    # Changing a permitted prior observation must be able to change the decision,
    # proving the probe reads the real rule rather than a constant/warm-up branch.
    if rule.startswith("LAGGED"):
        p_prior = list(p); p_prior[prior_idx] = Decimal(prior_new)
        changed = s.position_for(variant, p_prior, f, t)
    else:
        f_prior = list(f); f_prior[prior_idx] = Decimal(prior_new)
        changed = s.position_for(variant, p, f_prior, t)
    assert changed != baseline


def test_funding_deadband_inclusive():
    variant = _variant("FUNDING_SIGN_FADE", deadband="0.1")
    p = [Decimal("1")] * 3
    f = [Decimal("0.1"), Decimal("0.2"), Decimal("-999")]
    assert s.position_for(variant, p, f, 1) == 0   # abs(0.1) <= deadband -> flat
    assert s.position_for(variant, p, f, 2) == -1  # abs(0.2) > deadband -> fade short


# --------------------------------------------------------------------------- #
# Receipt verification and tampering
# --------------------------------------------------------------------------- #

def test_receipt_verification_and_tamper(tmp_path):
    b, raw, digest = s.load_bundle(EXAMPLE)
    receipt = s.build_receipt(b, raw, digest)
    data = s.canonical_json_bytes(receipt)
    assert s.verify_receipt_bytes(data) == receipt
    bad = copy.deepcopy(receipt); bad["results"][0]["turnover_count"] += 1
    with pytest.raises(s.SandboxValidationError): s.verify_receipt_bytes(s.canonical_json_bytes(bad))
    with pytest.raises(s.SandboxValidationError): s.verify_receipt_bytes(json.dumps(receipt, indent=2).encode())


def test_tampered_active_slot_count_fails_verification():
    receipt = s.build_receipt(*s.load_bundle(EXAMPLE))
    bad = copy.deepcopy(receipt)
    bad["results"][0]["active_slot_count"] += 1
    with pytest.raises(s.SandboxVerificationError):
        s.verify_receipt_bytes(s.canonical_json_bytes(bad))


# --------------------------------------------------------------------------- #
# Publication integrity
# --------------------------------------------------------------------------- #

def _no_partial(out: Path):
    assert not out.exists()
    assert list(out.parent.glob(".*.tmp")) == []


def test_publication_refuses_existing_and_missing_parent(tmp_path):
    out = tmp_path / "receipt.json"
    s.run_bundle(EXAMPLE, out)
    with pytest.raises(s.SandboxPublicationError): s.run_bundle(EXAMPLE, out)
    with pytest.raises(s.SandboxPublicationError): s.run_bundle(EXAMPLE, tmp_path / "missing" / "receipt.json")


def test_publication_writes_expected_bytes(tmp_path):
    out = tmp_path / "receipt.json"
    receipt, digest = s.run_bundle(EXAMPLE, out)
    assert out.read_bytes() == s.canonical_json_bytes(receipt)
    assert s.hashlib.sha256(out.read_bytes()).hexdigest() == digest
    assert list(out.parent.glob(".*.tmp")) == []


def test_publication_does_not_overwrite_existing(tmp_path):
    out = tmp_path / "receipt.json"
    out.write_bytes(b"ORIGINAL")
    with pytest.raises(s.SandboxPublicationError):
        s.run_bundle(EXAMPLE, out)
    assert out.read_bytes() == b"ORIGINAL"


def _boom(*args, **kwargs):
    raise OSError("simulated failure")


def test_publication_write_failure_leaves_no_partial(tmp_path, monkeypatch):
    out = tmp_path / "receipt.json"

    def bad_fdopen(fd, *args, **kwargs):
        s.os.close(fd)
        raise OSError("simulated write failure")

    monkeypatch.setattr(s.os, "fdopen", bad_fdopen)
    with pytest.raises(s.SandboxPublicationError):
        s.run_bundle(EXAMPLE, out)
    _no_partial(out)


def test_publication_fsync_failure_leaves_no_partial(tmp_path, monkeypatch):
    out = tmp_path / "receipt.json"
    monkeypatch.setattr(s.os, "fsync", _boom)
    with pytest.raises(s.SandboxPublicationError):
        s.run_bundle(EXAMPLE, out)
    _no_partial(out)


def test_publication_link_failure_leaves_no_partial(tmp_path, monkeypatch):
    out = tmp_path / "receipt.json"
    monkeypatch.setattr(s.os, "link", _boom)
    with pytest.raises(s.SandboxPublicationError):
        s.run_bundle(EXAMPLE, out)
    _no_partial(out)


# --------------------------------------------------------------------------- #
# CLI exit-code contract (0 ok, 2 input, 3 verification, 4 publication)
# --------------------------------------------------------------------------- #

def _assert_no_traceback(capsys):
    err = capsys.readouterr().err
    assert "Traceback" not in err
    return err


def test_cli_run_and_verify_success(tmp_path, capsys):
    out = tmp_path / "a.json"
    assert cli.main(["run", "--variants", str(EXAMPLE), "--out", str(out)]) == 0
    printed = capsys.readouterr().out.strip()
    assert printed.startswith("RECEIPT_SHA256=")
    printed_sha = printed.split("=", 1)[1]
    assert printed_sha == s.hashlib.sha256(out.read_bytes()).hexdigest()
    assert cli.main(["verify", "--receipt", str(out)]) == 0
    assert "RECEIPT_VERIFY_OK" in capsys.readouterr().out


def test_cli_missing_variants_file(tmp_path, capsys):
    out = tmp_path / "a.json"
    assert cli.main(["run", "--variants", str(tmp_path / "nope.json"), "--out", str(out)]) == 2
    _assert_no_traceback(capsys)


def test_cli_invalid_variant_bundle(tmp_path, capsys):
    bad = tmp_path / "bad.json"; bad.write_text("{ not json")
    out = tmp_path / "a.json"
    assert cli.main(["run", "--variants", str(bad), "--out", str(out)]) == 2
    _assert_no_traceback(capsys)


def test_cli_missing_receipt(tmp_path, capsys):
    assert cli.main(["verify", "--receipt", str(tmp_path / "nope.json")]) == 3
    _assert_no_traceback(capsys)


def test_cli_tampered_receipt(tmp_path, capsys):
    out = tmp_path / "a.json"
    cli.main(["run", "--variants", str(EXAMPLE), "--out", str(out)])
    capsys.readouterr()
    receipt = json.loads(out.read_bytes())
    receipt["results"][0]["turnover_count"] += 1
    tampered = tmp_path / "t.json"; tampered.write_bytes(s.canonical_json_bytes(receipt))
    assert cli.main(["verify", "--receipt", str(tampered)]) == 3
    _assert_no_traceback(capsys)


def test_cli_existing_output(tmp_path, capsys):
    out = tmp_path / "a.json"; out.write_text("x")
    assert cli.main(["run", "--variants", str(EXAMPLE), "--out", str(out)]) == 4
    _assert_no_traceback(capsys)


def test_cli_missing_output_parent(tmp_path, capsys):
    out = tmp_path / "missing" / "a.json"
    assert cli.main(["run", "--variants", str(EXAMPLE), "--out", str(out)]) == 4
    _assert_no_traceback(capsys)


def test_cli_write_failure(tmp_path, capsys, monkeypatch):
    out = tmp_path / "a.json"

    def bad_fdopen(fd, *args, **kwargs):
        s.os.close(fd)
        raise OSError("simulated write failure")

    monkeypatch.setattr(s.os, "fdopen", bad_fdopen)
    assert cli.main(["run", "--variants", str(EXAMPLE), "--out", str(out)]) == 4
    _assert_no_traceback(capsys)
    assert not out.exists()


def test_cli_fsync_failure(tmp_path, capsys, monkeypatch):
    out = tmp_path / "a.json"
    monkeypatch.setattr(s.os, "fsync", _boom)
    assert cli.main(["run", "--variants", str(EXAMPLE), "--out", str(out)]) == 4
    _assert_no_traceback(capsys)
    assert not out.exists()


def test_cli_publication_failure(tmp_path, capsys, monkeypatch):
    out = tmp_path / "a.json"
    monkeypatch.setattr(s.os, "link", _boom)
    assert cli.main(["run", "--variants", str(EXAMPLE), "--out", str(out)]) == 4
    _assert_no_traceback(capsys)
    assert not out.exists()
