import hashlib
import json
from pathlib import Path

import pytest

from quantbot.experiment.h001_temporal_causality import (
    FundingEvent,
    TemporalCausalityError,
    load_and_validate_temporal_candidate,
    select_held_funding_events,
    select_signal_funding_event,
)


ROOT = Path(__file__).parents[2]
CURRENT = ROOT / "docs/experiments/candidate1_h001_real_data_falsification_v0.json"
CANDIDATE = ROOT / "docs/experiments/candidate1_h001_real_data_falsification_temporal_candidate_v001.json"
CURRENT_SHA = "055ea162a11d4042320daeb74e153ebbd27969dd29a60c226cb84a8fc38b8900"
VALIDATOR_SHA = "888bc4663e3d7fb9b398f944bf2b67553e8959e0173be77183ca8b288156172a"
DRAFT_SHA = "03c57d0c0935eb37d53ee68410935e258e3bde0f5b2c8d19048e4c1d979d5639"
PRE_DATA_SHA = "a22d0cf260f31d7104fc4d4fe96030c8666179c20c7737dfe20a59f3c7200ddc"


def event(timestamp, rate=0.001):
    return FundingEvent(timestamp, rate)


def test_candidate_is_canonical_and_valid():
    raw = CANDIDATE.read_bytes()
    assert raw == json.dumps(json.loads(raw), sort_keys=True, separators=(",", ":"), ensure_ascii=True).encode()
    assert load_and_validate_temporal_candidate(raw)["temporal_join_contract"]["prior_funding"].endswith("< bar[t].open_time_utc")


def test_current_bindings_and_one_leaf_difference():
    assert hashlib.sha256(CURRENT.read_bytes()).hexdigest() == CURRENT_SHA
    assert hashlib.sha256((ROOT / "quantbot/experiment/h001_real_falsification_preregistration.py").read_bytes()).hexdigest() == VALIDATOR_SHA
    assert hashlib.sha256((ROOT / "docs/assurance/h001_temporal_causality_amendment_draft_v001.json").read_bytes()).hexdigest() == DRAFT_SHA
    assert hashlib.sha256((ROOT / "docs/control/amendments/candidate1_h001_pre_data_assurance_v001.json").read_bytes()).hexdigest() == PRE_DATA_SHA
    current, candidate = json.loads(CURRENT.read_bytes()), json.loads(CANDIDATE.read_bytes())
    differences = []
    def walk(a, b, path=""):
        if isinstance(a, dict) and isinstance(b, dict):
            assert set(a) == set(b)
            for key in a:
                walk(a[key], b[key], f"{path}/{key}")
        elif a != b:
            differences.append((path, a, b))
    walk(current, candidate)
    assert differences == [("/temporal_join_contract/prior_funding", "latest funding_time_utc <= bar[t].open_time_utc", "latest funding_time_utc < bar[t].open_time_utc")]


@pytest.mark.parametrize("bad", [b"{}", b"not-json"])
def test_candidate_validation_rejects_bad_documents(bad):
    with pytest.raises(TemporalCausalityError):
        load_and_validate_temporal_candidate(bad)


def test_signal_strict_precedence_and_latest_selection():
    events = [event("2024-01-01T00:00:00Z"), event("2024-01-01T07:59:59Z", 0.002), event("2024-01-01T08:00:00Z", 0.003), event("2024-01-01T08:00:01Z")]
    assert select_signal_funding_event(events, "2024-01-01T08:00:00Z") == events[1]
    with pytest.raises(TemporalCausalityError, match="NO_ELIGIBLE_PRIOR_FUNDING"):
        select_signal_funding_event([events[2]], "2024-01-01T08:00:00Z")


def test_signal_staleness_boundary():
    assert select_signal_funding_event([event("2024-01-01T00:00:00Z")], "2024-01-01T12:00:00Z")
    with pytest.raises(TemporalCausalityError, match="FUNDING_STALENESS_EXCEEDS_MAXIMUM"):
        select_signal_funding_event([event("2024-01-01T00:00:00Z")], "2024-01-01T12:00:01Z")


def test_held_funding_dynamic_intervals_and_boundaries():
    events = [event("2024-01-01T04:00:00Z"), event("2024-01-01T08:00:00Z"), event("2024-01-01T12:00:00Z"), event("2024-01-01T12:00:01Z")]
    assert select_held_funding_events(events, "2024-01-01T04:00:00Z", "2024-01-01T12:00:00Z") == (events[1], events[2])
    assert select_held_funding_events(events, "2024-01-01T00:00:00Z", "2024-01-01T04:00:00Z") == (events[0],)
    assert select_held_funding_events(events, "2024-01-01T00:00:00Z", "2024-01-01T08:00:00Z") == (events[0], events[1])
    with pytest.raises(TemporalCausalityError, match="INVALID_INTERVAL_ORDERING"):
        select_held_funding_events(events, "2024-01-01T08:00:00Z", "2024-01-01T08:00:00Z")


@pytest.mark.parametrize("events, error", [
    ([event("2024-01-01T01:00:00Z"), event("2024-01-01T01:00:00Z")], "DUPLICATE_FUNDING_TIMESTAMP"),
    ([event("2024-01-01T02:00:00Z"), event("2024-01-01T01:00:00Z")], "NONMONOTONIC_FUNDING_TIMESTAMPS"),
    ([event("2024-01-01T01:00:00+00:00Z")], "NONCANONICAL_TIMESTAMP"),
    ([event("2024-02-30T01:00:00Z")], "NONCANONICAL_TIMESTAMP"),
    ([FundingEvent("2024-01-01T01:00:00Z", True)], "NONFINITE_FUNDING_RATE"),
    ([FundingEvent("2024-01-01T01:00:00Z", float("nan"))], "NONFINITE_FUNDING_RATE"),
    ([FundingEvent("2024-01-01T01:00:00Z", float("inf"))], "NONFINITE_FUNDING_RATE"),
])
def test_event_validation_rejects_malformed_inputs(events, error):
    with pytest.raises(TemporalCausalityError, match=error):
        select_held_funding_events(events, "2024-01-01T00:00:00Z", "2024-01-01T04:00:00Z")


@pytest.mark.parametrize("timestamp", ["2024-01-01T01:00:00.000Z", "2024-01-01T01:00:00z", "2024-01-01 01:00:00Z", "2024-01-01T01:00:00"])
def test_timestamp_forms_are_strict(timestamp):
    with pytest.raises(TemporalCausalityError, match="NONCANONICAL_TIMESTAMP"):
        select_held_funding_events([event(timestamp)], "2024-01-01T00:00:00Z", "2024-01-01T04:00:00Z")
