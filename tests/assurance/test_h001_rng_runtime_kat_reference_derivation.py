"""Derivation B: verify the H001 RNG-runtime known-answer fixtures through an
independent pure-Python Philox4x64-10 reference implementation.

This module is the second of two structurally independent derivations required
by the RNG-runtime amendment candidate. It implements the Philox4x64-10 block
function directly from the published algorithm of Salmon, Moraes, Dror, and
Shaw (2011), together with its own payload encoding, key derivation, counter
packing, lane extraction, bounded-integer mapping, rational Bernoulli mapping,
and stationary-bootstrap path logic. It never imports numpy and never calls the
production or numpy-derivation helpers; every expectation is a static fixture
bound inside the reviewed candidate document.

Test-only: this is not a production calibration RNG engine, and the historical
SeedSequence prototype fixture is verified here only at the payload-identity
layer because SeedSequence expansion is a declared numpy runtime dependency
outside the normative bootstrap-index path.
"""

import hashlib
import json
from pathlib import Path

import pytest

REPO = Path(__file__).parents[2]
CANDIDATE_FILE = REPO / "docs/control/amendments/candidate1_h001_synthetic_null_calibration_rng_runtime_specification_amendment_v001.json"

DOMAIN_PREFIX = "h001-null-calibration/h001-synthetic-null-calibration-spec-freeze-candidate-v001/synthetic-only"
PATH_LENGTH = 2193
ATTEMPT_CAP = 8
PURPOSE_CODES = {"INITIAL_INDEX": 1, "RESTART_DECISION": 2, "RESTART_INDEX": 3}
WORD_MODULUS = 1 << 64
WORD_MASK = WORD_MODULUS - 1

PHILOX_MULTIPLIER_0 = 0xD2E7470EE14C6C93
PHILOX_MULTIPLIER_1 = 0xCA5A826395121157
PHILOX_WEYL_0 = 0x9E3779B97F4A7C15
PHILOX_WEYL_1 = 0xBB67AE8584CAA73B


def load_fixtures():
    return json.loads(CANDIDATE_FILE.read_bytes())["known_answer_fixtures"]


def compose_payload(dgp, outer, bootstrap):
    return DOMAIN_PREFIX + ":" + dgp + ":outer:" + str(outer) + ":bootstrap:" + str(bootstrap)


def derive_key_words(payload):
    hex_digest = hashlib.sha256(payload.encode("utf-8")).hexdigest()
    return int(hex_digest[0:16], 16), int(hex_digest[16:32], 16)


def pack_counter_word(purpose, position, attempt):
    if purpose not in PURPOSE_CODES:
        raise ValueError("H001_RNG_UNKNOWN_DRAW_PURPOSE")
    if not (0 <= position < PATH_LENGTH and 0 <= attempt < ATTEMPT_CAP):
        raise ValueError("H001_RNG_COORDINATE_OUT_OF_DOMAIN")
    return attempt + 256 * PURPOSE_CODES[purpose] + 65536 * position


def philox_block(counter_words, key_words):
    c0, c1, c2, c3 = counter_words
    k0, k1 = key_words
    for _ in range(10):
        product_0 = PHILOX_MULTIPLIER_0 * c0
        product_1 = PHILOX_MULTIPLIER_1 * c2
        c0, c1, c2, c3 = (
            ((product_1 >> 64) ^ c1 ^ k0) & WORD_MASK,
            product_1 & WORD_MASK,
            ((product_0 >> 64) ^ c3 ^ k1) & WORD_MASK,
            product_0 & WORD_MASK,
        )
        k0 = (k0 + PHILOX_WEYL_0) & WORD_MASK
        k1 = (k1 + PHILOX_WEYL_1) & WORD_MASK
    return [c0, c1, c2, c3]


def reference_block(payload, purpose, position, attempt):
    return philox_block([pack_counter_word(purpose, position, attempt), 0, 0, 0], derive_key_words(payload))


def reference_word(payload, purpose, position, attempt):
    return reference_block(payload, purpose, position, attempt)[0]


def draw_bounded(payload, purpose, position, bound):
    if not (isinstance(bound, int) and 1 <= bound <= WORD_MODULUS):
        raise ValueError("H001_RNG_INVALID_BOUND")
    threshold = WORD_MODULUS - (WORD_MODULUS % bound)
    for attempt in range(ATTEMPT_CAP):
        candidate_word = reference_word(payload, purpose, position, attempt)
        if candidate_word < threshold:
            return candidate_word % bound
    raise ValueError("H001_RNG_RETRY_CAP_EXHAUSTED")


def draw_bernoulli(payload, position, numerator, denominator):
    if not (isinstance(numerator, int) and isinstance(denominator, int) and denominator >= 1 and 0 <= numerator <= denominator):
        raise ValueError("H001_RNG_INVALID_RATIONAL")
    return draw_bounded(payload, "RESTART_DECISION", position, denominator) < numerator


def build_path(payload, evaluation_order=None):
    positions = list(evaluation_order) if evaluation_order is not None else list(range(1, PATH_LENGTH))
    start_index = draw_bounded(payload, "INITIAL_INDEX", 0, PATH_LENGTH)
    restart_values = {}
    for position in positions:
        if draw_bernoulli(payload, position, 1, 63):
            restart_values[position] = draw_bounded(payload, "RESTART_INDEX", position, PATH_LENGTH)
    indices = [start_index]
    for position in range(1, PATH_LENGTH):
        if position in restart_values:
            indices.append(restart_values[position])
        else:
            indices.append((indices[position - 1] + 1) % PATH_LENGTH)
    return indices, sorted(restart_values)


def payload_for(fixtures, tag):
    source = fixtures["KAT-PAYLOAD-001" if tag == "payload_1" else "KAT-PAYLOAD-002"]
    return compose_payload(source["dgp_or_case_id"], source["outer_replication_index"], source["bootstrap_replication_index"])


def test_payload_and_key_fixtures():
    fixtures = load_fixtures()
    for fixture_id in ("KAT-PAYLOAD-001", "KAT-PAYLOAD-002"):
        source = fixtures[fixture_id]
        payload = compose_payload(source["dgp_or_case_id"], source["outer_replication_index"], source["bootstrap_replication_index"])
        assert payload == source["payload_string"]
        assert hashlib.sha256(payload.encode("utf-8")).hexdigest() == source["payload_utf8_sha256"]
        word_0, word_1 = derive_key_words(payload)
        assert word_0 == int(source["derived_seed64"]) == int(source["philox_key_word_0"])
        assert word_1 == int(source["philox_key_word_1"])


def test_historical_seedsequence_prototype_reconstruction():
    fixtures = load_fixtures()
    historical = fixtures["KAT-HISTORICAL-SEEDSEQUENCE-001"]
    assert historical["normative"] is False
    word_0, _ = derive_key_words(payload_for(fixtures, "payload_1"))
    assert str(word_0) == historical["seed_sequence_entropy"]
    assert historical["first_four_random_raw_words"] != [
        str(reference_word(payload_for(fixtures, "payload_1"), "INITIAL_INDEX", 0, attempt)) for attempt in range(4)
    ], "the SeedSequence prototype words must differ from the direct-construction words"


def test_raw_word_fixtures():
    fixtures = load_fixtures()
    for number in range(1, 10):
        source = fixtures[f"KAT-RAW-{number:03d}"]
        payload = payload_for(fixtures, source["payload_fixture"])
        packed = pack_counter_word(source["draw_purpose"], source["sample_position"], source["attempt_index"])
        assert packed == int(source["counter_word_0"])
        block = reference_block(payload, source["draw_purpose"], source["sample_position"], source["attempt_index"])
        assert [str(word) for word in block] == source["block_words"]
        assert str(block[0]) == source["normative_lane0_word"]


def test_bounded_integer_fixtures():
    fixtures = load_fixtures()
    for fixture_id in ("KAT-BOUNDED-N1-001", "KAT-BOUNDED-N63-001", "KAT-BOUNDED-N2193-001", "KAT-BOUNDED-NMAX-001"):
        source = fixtures[fixture_id]
        payload = payload_for(fixtures, source["payload_fixture"])
        bound = int(source["bound_n"])
        assert WORD_MODULUS - (WORD_MODULUS % bound) == int(source["acceptance_limit"])
        assert draw_bounded(payload, source["draw_purpose"], source["sample_position"], bound) == int(source["result"])
    with pytest.raises(ValueError, match="H001_RNG_INVALID_BOUND"):
        draw_bounded(payload_for(fixtures, "payload_1"), "INITIAL_INDEX", 0, 0)
    with pytest.raises(ValueError, match="H001_RNG_INVALID_BOUND"):
        draw_bounded(payload_for(fixtures, "payload_1"), "INITIAL_INDEX", 0, WORD_MODULUS + 1)


def test_bernoulli_fixtures():
    fixtures = load_fixtures()
    for fixture_id in ("KAT-BERNOULLI-TRUE-001", "KAT-BERNOULLI-FALSE-001", "KAT-BERNOULLI-P0-001", "KAT-BERNOULLI-P1Q1-001"):
        source = fixtures[fixture_id]
        payload = payload_for(fixtures, source["payload_fixture"])
        outcome = draw_bernoulli(payload, source["sample_position"], source["probability_numerator"], source["probability_denominator"])
        assert outcome is source["result"]
    with pytest.raises(ValueError, match="H001_RNG_INVALID_RATIONAL"):
        draw_bernoulli(payload_for(fixtures, "payload_1"), 1, 2, 1)
    with pytest.raises(ValueError, match="H001_RNG_INVALID_RATIONAL"):
        draw_bernoulli(payload_for(fixtures, "payload_1"), 1, 1, 0)


def test_rejection_retry_fixture():
    fixtures = load_fixtures()
    source = fixtures["KAT-RETRY-001"]
    payload = payload_for(fixtures, source["payload_fixture"])
    bound = int(source["bound_n"])
    threshold = int(source["acceptance_limit"])
    observed = [reference_word(payload, source["draw_purpose"], source["sample_position"], attempt) for attempt in range(len(source["raw_words_consumed"]))]
    assert [str(word) for word in observed] == source["raw_words_consumed"]
    for attempt in source["rejected_attempt_indices"]:
        assert observed[attempt] >= threshold
    assert observed[source["accepted_attempt_index"]] < threshold
    assert draw_bounded(payload, source["draw_purpose"], source["sample_position"], bound) == int(source["result"])


def test_rejection_exhaustion_fixture():
    fixtures = load_fixtures()
    source = fixtures["KAT-EXHAUSTION-001"]
    payload = payload_for(fixtures, source["payload_fixture"])
    threshold = int(source["acceptance_limit"])
    observed = [reference_word(payload, source["draw_purpose"], source["sample_position"], attempt) for attempt in range(ATTEMPT_CAP)]
    assert [str(word) for word in observed] == source["raw_words_all_rejected"]
    assert min(observed) >= threshold
    with pytest.raises(ValueError, match=source["failure_category"]):
        draw_bounded(payload, source["draw_purpose"], source["sample_position"], int(source["bound_n"]))


def test_full_bootstrap_path_fixtures():
    fixtures = load_fixtures()
    for fixture_id in ("KAT-PATH-001", "KAT-PATH-002"):
        source = fixtures[fixture_id]
        payload = payload_for(fixtures, source["payload_fixture"])
        indices, restarts = build_path(payload)
        assert indices == source["index_path"]
        assert restarts == source["restart_positions"]
        canonical = json.dumps(indices, sort_keys=True, separators=(",", ":"), ensure_ascii=True).encode("utf-8")
        assert hashlib.sha256(canonical).hexdigest() == source["index_path_canonical_json_sha256"]
        excluded = set(restarts)
        wraps = [t for t in range(1, PATH_LENGTH) if t not in excluded and indices[t] == 0 and indices[t - 1] == PATH_LENGTH - 1]
        assert wraps == source["wraparound_continuation_positions"]


def test_rejection_isolation_and_evaluation_order_independence():
    fixtures = load_fixtures()
    source = fixtures["KAT-PATH-001"]
    payload = payload_for(fixtures, source["payload_fixture"])
    expected = source["index_path"]

    assert build_path(payload)[0] == expected
    assert build_path(payload, evaluation_order=range(PATH_LENGTH - 1, 0, -1))[0] == expected
    scrambled = sorted(range(1, PATH_LENGTH), key=lambda t: (t * 5081) % PATH_LENGTH)
    assert build_path(payload, evaluation_order=scrambled)[0] == expected
    blocks = [t for start in range(1, PATH_LENGTH, 211) for t in range(start, min(start + 211, PATH_LENGTH))]
    assert build_path(payload, evaluation_order=blocks)[0] == expected

    exhaustion = fixtures["KAT-EXHAUSTION-001"]
    untouched_before = reference_word(payload, "RESTART_DECISION", 500, 0)
    with pytest.raises(ValueError, match="H001_RNG_RETRY_CAP_EXHAUSTED"):
        draw_bounded(payload, exhaustion["draw_purpose"], exhaustion["sample_position"], int(exhaustion["bound_n"]))
    assert reference_word(payload, "RESTART_DECISION", 500, 0) == untouched_before

    ordering_one = {}
    for key in (("RESTART_INDEX", 9), ("INITIAL_INDEX", 0), ("RESTART_DECISION", 9)):
        ordering_one[key] = reference_word(payload, key[0], key[1], 0)
    ordering_two = {}
    for key in (("RESTART_DECISION", 9), ("RESTART_INDEX", 9), ("INITIAL_INDEX", 0)):
        ordering_two[key] = reference_word(payload, key[0], key[1], 0)
    assert ordering_one == ordering_two

    other_variant = compose_payload("unrelated_future_variant", 0, 0)
    assert derive_key_words(other_variant) != derive_key_words(payload)
    philox_block([0 + 256 * 4 + 65536 * 0, 0, 0, 0], derive_key_words(payload))
    assert str(reference_word(payload, "INITIAL_INDEX", 0, 0)) == fixtures["KAT-RAW-001"]["normative_lane0_word"]
