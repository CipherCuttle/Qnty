"""Derivation A: verify the H001 RNG-runtime known-answer fixtures through the
declared numpy Philox raw-word boundary.

This module is one of two structurally independent derivations required by the
RNG-runtime amendment candidate. It re-implements payload encoding, key
derivation, counter packing, bounded-integer mapping, rational Bernoulli, and
the stationary-bootstrap logical order from the candidate text alone, and it
consumes randomness only through numpy.random.Philox(counter=..., key=...)
.random_raw at the exact permitted raw-word boundary. It shares no code with
the reference derivation and never generates expected values from itself: every
expectation is a static fixture bound inside the reviewed candidate document.

Test-only: this is not a production calibration RNG engine.
"""

import hashlib
import json
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import pytest
from numpy.random import Philox, SeedSequence

ROOT = Path(__file__).parents[2]
CANDIDATE_PATH = ROOT / "docs/control/amendments/candidate1_h001_synthetic_null_calibration_rng_runtime_specification_amendment_v001.json"

SEED_DOMAIN = "h001-null-calibration/h001-synthetic-null-calibration-spec-freeze-candidate-v001/synthetic-only"
SAMPLE_LENGTH = 2193
RETRY_CAP = 8
PURPOSE_IDS = {"INITIAL_INDEX": 1, "RESTART_DECISION": 2, "RESTART_INDEX": 3}
TWO_POW_64 = 1 << 64
MASK_256 = (1 << 256) - 1


def fixtures():
    return json.loads(CANDIDATE_PATH.read_bytes())["known_answer_fixtures"]


def payload_string(dgp, outer, bootstrap):
    return f"{SEED_DOMAIN}:{dgp}:outer:{outer}:bootstrap:{bootstrap}"


def key_integer(payload):
    digest = hashlib.sha256(payload.encode("utf-8")).hexdigest()
    return int(digest[0:16], 16) | (int(digest[16:32], 16) << 64)


def counter_integer(purpose, position, attempt):
    return attempt | (PURPOSE_IDS[purpose] << 8) | (position << 16)


def raw_block(payload, purpose, position, attempt):
    bit_generator = Philox(counter=(counter_integer(purpose, position, attempt) - 1) & MASK_256, key=key_integer(payload))
    return [int(word) for word in bit_generator.random_raw(4)]


def raw_word(payload, purpose, position, attempt):
    return raw_block(payload, purpose, position, attempt)[0]


def uniform_bounded(payload, purpose, position, n):
    if not (1 <= n <= TWO_POW_64):
        raise ValueError("H001_RNG_INVALID_BOUND")
    limit = TWO_POW_64 - (TWO_POW_64 % n)
    for attempt in range(RETRY_CAP):
        x = raw_word(payload, purpose, position, attempt)
        if x < limit:
            return x % n
    raise ValueError("H001_RNG_RETRY_CAP_EXHAUSTED")


def bernoulli_rational(payload, position, p, q):
    if not (isinstance(p, int) and isinstance(q, int) and q >= 1 and 0 <= p <= q):
        raise ValueError("H001_RNG_INVALID_RATIONAL")
    return uniform_bounded(payload, "RESTART_DECISION", position, q) < p


def bootstrap_path(payload, positions=None):
    order = list(range(1, SAMPLE_LENGTH)) if positions is None else list(positions)
    initial = uniform_bounded(payload, "INITIAL_INDEX", 0, SAMPLE_LENGTH)
    restarts = {}
    for t in order:
        if bernoulli_rational(payload, t, 1, 63):
            restarts[t] = uniform_bounded(payload, "RESTART_INDEX", t, SAMPLE_LENGTH)
    path = [initial]
    for t in range(1, SAMPLE_LENGTH):
        path.append(restarts[t] if t in restarts else (path[t - 1] + 1) % SAMPLE_LENGTH)
    return path, sorted(restarts)


def fixture_payload(kat, name):
    entry = kat[f"KAT-{'PAYLOAD-001' if name == 'payload_1' else 'PAYLOAD-002'}"]
    return payload_string(entry["dgp_or_case_id"], entry["outer_replication_index"], entry["bootstrap_replication_index"])


def test_payload_and_key_fixtures():
    kat = fixtures()
    for fixture_id in ("KAT-PAYLOAD-001", "KAT-PAYLOAD-002"):
        entry = kat[fixture_id]
        payload = payload_string(entry["dgp_or_case_id"], entry["outer_replication_index"], entry["bootstrap_replication_index"])
        assert payload == entry["payload_string"]
        digest = hashlib.sha256(payload.encode("utf-8")).hexdigest()
        assert digest == entry["payload_utf8_sha256"]
        assert int(digest[0:16], 16) == int(entry["derived_seed64"])
        assert int(digest[0:16], 16) == int(entry["philox_key_word_0"])
        assert int(digest[16:32], 16) == int(entry["philox_key_word_1"])


def test_historical_seedsequence_prototype_reconstruction():
    kat = fixtures()
    historical = kat["KAT-HISTORICAL-SEEDSEQUENCE-001"]
    assert historical["normative"] is False
    seed = int(historical["seed_sequence_entropy"])
    assert seed == int(kat["KAT-PAYLOAD-001"]["derived_seed64"])
    state = [int(word) for word in SeedSequence(seed).generate_state(4, "uint64")]
    assert state == [int(word) for word in historical["seed_sequence_generate_state_4_uint64"]]
    prototype = Philox(seed)
    assert [int(word) for word in prototype.state["state"]["key"]] == [int(word) for word in historical["philox_seedsequence_key_words"]]
    assert [int(word) for word in prototype.random_raw(4)] == [int(word) for word in historical["first_four_random_raw_words"]]


def test_raw_word_fixtures():
    kat = fixtures()
    for index in range(1, 10):
        entry = kat[f"KAT-RAW-{index:03d}"]
        payload = fixture_payload(kat, entry["payload_fixture"])
        assert counter_integer(entry["draw_purpose"], entry["sample_position"], entry["attempt_index"]) == int(entry["counter_word_0"])
        block = raw_block(payload, entry["draw_purpose"], entry["sample_position"], entry["attempt_index"])
        assert block == [int(word) for word in entry["block_words"]]
        assert block[0] == int(entry["normative_lane0_word"])


def test_bounded_integer_fixtures():
    kat = fixtures()
    for fixture_id in ("KAT-BOUNDED-N1-001", "KAT-BOUNDED-N63-001", "KAT-BOUNDED-N2193-001", "KAT-BOUNDED-NMAX-001"):
        entry = kat[fixture_id]
        payload = fixture_payload(kat, entry["payload_fixture"])
        n = int(entry["bound_n"])
        assert TWO_POW_64 - (TWO_POW_64 % n) == int(entry["acceptance_limit"])
        assert uniform_bounded(payload, entry["draw_purpose"], entry["sample_position"], n) == int(entry["result"])
    with pytest.raises(ValueError, match="H001_RNG_INVALID_BOUND"):
        uniform_bounded(fixture_payload(kat, "payload_1"), "INITIAL_INDEX", 0, 0)
    with pytest.raises(ValueError, match="H001_RNG_INVALID_BOUND"):
        uniform_bounded(fixture_payload(kat, "payload_1"), "INITIAL_INDEX", 0, TWO_POW_64 + 1)


def test_bernoulli_fixtures():
    kat = fixtures()
    for fixture_id in ("KAT-BERNOULLI-TRUE-001", "KAT-BERNOULLI-FALSE-001", "KAT-BERNOULLI-P0-001", "KAT-BERNOULLI-P1Q1-001"):
        entry = kat[fixture_id]
        payload = fixture_payload(kat, entry["payload_fixture"])
        result = bernoulli_rational(payload, entry["sample_position"], entry["probability_numerator"], entry["probability_denominator"])
        assert result is entry["result"]
    with pytest.raises(ValueError, match="H001_RNG_INVALID_RATIONAL"):
        bernoulli_rational(fixture_payload(kat, "payload_1"), 1, 2, 1)
    with pytest.raises(ValueError, match="H001_RNG_INVALID_RATIONAL"):
        bernoulli_rational(fixture_payload(kat, "payload_1"), 1, 1, 0)


def test_rejection_retry_fixture():
    kat = fixtures()
    entry = kat["KAT-RETRY-001"]
    payload = fixture_payload(kat, entry["payload_fixture"])
    n = int(entry["bound_n"])
    limit = int(entry["acceptance_limit"])
    words = [raw_word(payload, entry["draw_purpose"], entry["sample_position"], attempt) for attempt in range(len(entry["raw_words_consumed"]))]
    assert words == [int(word) for word in entry["raw_words_consumed"]]
    for attempt in entry["rejected_attempt_indices"]:
        assert words[attempt] >= limit
    assert words[entry["accepted_attempt_index"]] < limit
    assert uniform_bounded(payload, entry["draw_purpose"], entry["sample_position"], n) == int(entry["result"])


def test_rejection_exhaustion_fixture():
    kat = fixtures()
    entry = kat["KAT-EXHAUSTION-001"]
    payload = fixture_payload(kat, entry["payload_fixture"])
    n = int(entry["bound_n"])
    limit = int(entry["acceptance_limit"])
    words = [raw_word(payload, entry["draw_purpose"], entry["sample_position"], attempt) for attempt in range(RETRY_CAP)]
    assert words == [int(word) for word in entry["raw_words_all_rejected"]]
    assert all(word >= limit for word in words)
    with pytest.raises(ValueError, match=entry["failure_category"]):
        uniform_bounded(payload, entry["draw_purpose"], entry["sample_position"], n)


def test_full_bootstrap_path_fixtures():
    kat = fixtures()
    for fixture_id in ("KAT-PATH-001", "KAT-PATH-002"):
        entry = kat[fixture_id]
        payload = fixture_payload(kat, entry["payload_fixture"])
        path, restarts = bootstrap_path(payload)
        assert path == entry["index_path"]
        assert restarts == entry["restart_positions"]
        assert hashlib.sha256(json.dumps(path, sort_keys=True, separators=(",", ":"), ensure_ascii=True).encode("utf-8")).hexdigest() == entry["index_path_canonical_json_sha256"]
        restart_set = set(restarts)
        wraps = [t for t in range(1, SAMPLE_LENGTH) if t not in restart_set and path[t] == 0 and path[t - 1] == SAMPLE_LENGTH - 1]
        assert wraps == entry["wraparound_continuation_positions"]


def test_rejection_isolation_and_evaluation_order_independence():
    kat = fixtures()
    entry = kat["KAT-PATH-001"]
    payload = fixture_payload(kat, entry["payload_fixture"])
    expected_path = entry["index_path"]

    forward, _ = bootstrap_path(payload)
    reverse_order, _ = bootstrap_path(payload, positions=range(SAMPLE_LENGTH - 1, 0, -1))
    permuted = sorted(range(1, SAMPLE_LENGTH), key=lambda t: (t * 7919) % SAMPLE_LENGTH)
    permuted_order, _ = bootstrap_path(payload, positions=permuted)
    chunked = []
    for start in range(1, SAMPLE_LENGTH, 97):
        chunked.extend(range(start, min(start + 97, SAMPLE_LENGTH)))
    chunked_order, _ = bootstrap_path(payload, positions=chunked)
    assert forward == expected_path
    assert reverse_order == expected_path
    assert permuted_order == expected_path
    assert chunked_order == expected_path

    # Forced rejection at coordinate A (the exhausting test bound) leaves B unchanged.
    exhaustion = kat["KAT-EXHAUSTION-001"]
    before = raw_word(payload, "RESTART_DECISION", 100, 0)
    with pytest.raises(ValueError, match="H001_RNG_RETRY_CAP_EXHAUSTED"):
        uniform_bounded(payload, exhaustion["draw_purpose"], exhaustion["sample_position"], int(exhaustion["bound_n"]))
    assert raw_word(payload, "RESTART_DECISION", 100, 0) == before

    # Scalar versus batched raw-word consumption at the numpy boundary.
    raw_entry = kat["KAT-RAW-001"]
    scalar = raw_word(payload, raw_entry["draw_purpose"], raw_entry["sample_position"], raw_entry["attempt_index"])
    bit_generator = Philox(counter=(int(raw_entry["counter_word_0"]) - 1) & MASK_256, key=key_integer(payload))
    batched = [int(word) for word in bit_generator.random_raw(8)]
    assert batched[0] == scalar == int(raw_entry["normative_lane0_word"])

    # Dictionary insertion order does not influence any output.
    coordinates_a = {("RESTART_DECISION", 1): None, ("RESTART_DECISION", 2): None, ("INITIAL_INDEX", 0): None}
    coordinates_b = {("INITIAL_INDEX", 0): None, ("RESTART_DECISION", 2): None, ("RESTART_DECISION", 1): None}
    values_a = {key: raw_word(payload, key[0], key[1], 0) for key in coordinates_a}
    values_b = {key: raw_word(payload, key[0], key[1], 0) for key in coordinates_b}
    assert values_a == values_b

    # Parallel scheduling equivalence.
    def evaluate(t):
        return t, raw_word(payload, "RESTART_DECISION", t, 0)

    with ThreadPoolExecutor(max_workers=4) as pool:
        parallel = dict(pool.map(evaluate, range(1, 200)))
    serial = {t: raw_word(payload, "RESTART_DECISION", t, 0) for t in range(1, 200)}
    assert parallel == serial

    # Adding an unrelated variant or future draw purpose does not alter outputs.
    other_payload = payload_string("unrelated_future_variant", 0, 0)
    assert key_integer(other_payload) != key_integer(payload)
    future_purpose_counter = 0 | (4 << 8) | (0 << 16)
    Philox(counter=(future_purpose_counter - 1) & MASK_256, key=key_integer(payload)).random_raw(4)
    assert raw_word(payload, "INITIAL_INDEX", 0, 0) == int(kat["KAT-RAW-001"]["normative_lane0_word"])
