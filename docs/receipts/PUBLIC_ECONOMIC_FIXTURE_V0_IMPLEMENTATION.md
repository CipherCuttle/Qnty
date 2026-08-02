# PUBLIC_ECONOMIC_FIXTURE_V0_IMPLEMENTATION

Task ID: `IMPLEMENT_PUBLIC_ECONOMIC_FIXTURE_V0`

Verdict: `PUBLIC_ECONOMIC_FIXTURE_V0_IMPLEMENTED`

Next action: `INDEPENDENTLY_REVIEW_PUBLIC_ECONOMIC_FIXTURE_V0`

## Repository Identity

QNTY root: `/home/swirky/DevHub/repos/Qnty`

QNTY branch: `chore/external-trust-root-dispatcher-repair-v046`

QNTY starting HEAD: `8ebe61bdecd2d72239cf8d0618df87d6e1171c5a`

QNTY final HEAD: local Git commit created from this implementation receipt and the bounded changeset; the containing commit hash is the Git envelope and is reported by `git rev-parse HEAD` after commit.

QntyLab root: `/home/swirky/DevHub/repos/QntyLab`

QntyLab HEAD verified during implementation: `5ba89e5c5f320391ee9321b1929bb079be590aa8`

## Contract And Source Hashes

Contract Markdown SHA-256: `fd60173f71c9a7180ce0ce5c31023ae4b63ea6c8df6259620cc5646b8e6f347d`

Contract JSON SHA-256: `b6c9ad8f3b21c983952820c6bb05d4ca6e8a8695cc3b5b57db34413e7391b5c3`

Raw REST response SHA-256: `01d38d5b8c8581388621015a2bc618673cac1ff51ff88672aea52f9bdb31bafd`

Selected event SHA-256: `fcc0682d5a30976d860fbbefaf415b0e0c0d0585835a4a8ef089acd9c5376b59`

Source receipt SHA-256: `456e7918e3d9c7caeee67a8bde729867cbe0143f2002e7496ef5234382278c1c`

Selected event: `BTCUSDT`, `fundingTime=1780272000001`, `fundingTimeUtc=2026-06-01T00:00:00.001Z`, `fundingRate="0.00005703"`, `markPrice="73653.56663043"`, `rateType="Regular"`, raw source index `0`.

## Changeset

Added `quantbot/paper/public_funding_economic_fixture.py`: pure Decimal parser, source verifier, reconstruction receipt builder, receipt verifier, duplicate-application batch verifier, and offline CLI.

Added `tests/fixtures/public_funding_economic_v0/input.json`: QNTY-local immutable fixture with pinned public source hashes and synthetic quantity `0.001 BTC`.

Added `tests/fixtures/public_funding_economic_v0/expected_receipt.json`: canonical golden receipt for the long positive-rate vector.

Added `tests/test_public_funding_economic_fixture_v0.py`: focused tests for arithmetic, numeric safety, source integrity, receipt integrity, idempotency, scope safety, and fixture execution.

Added this receipt: `docs/receipts/PUBLIC_ECONOMIC_FIXTURE_V0_IMPLEMENTATION.md`.

## Implementation Boundary

The implementation is additive and semantically separate from existing paper accounting. It does not modify `quantbot/paper/engine.py`, existing paper results, SQLite schemas, production strategies, network acquisition code, candidate registries, trial registries, research decisions, QntyLab files, or any margin/liquidation/ADL/capital/spot/SOFR machinery.

No SQLite write path exists in V0.

## Formula And Quantity Policy

Formula:

```text
economic_funding_transfer =
  -signed_position_quantity
  * funding_mark_price
  * finalized_funding_rate
  * contract_multiplier
```

Synthetic signed quantity: `"0.001"`.

Quantity unit: `BTC`.

Contract multiplier: `"1"`, used only as a bounded dimensional contract rule for this fixture, not as proof of an authentic account-posting convention.

## Golden Vectors

`VECTOR_LONG_POSITIVE_RATE`: signed quantity `0.001`, notional `73.65356663043`, transfer `-0.0042004629049334229`, direction `PAYS`.

`VECTOR_SHORT_POSITIVE_RATE`: signed quantity `-0.001`, notional `73.65356663043`, transfer `0.0042004629049334229`, direction `RECEIVES`.

`VECTOR_ZERO_QUANTITY`: signed quantity `0`, notional `0`, transfer `0`, direction `ZERO`.

## Numeric Policy

All load-bearing source decimals remain strings and are parsed with `decimal.Decimal` inside `localcontext()` with precision `50`.

Binary float inputs, malformed decimals, `NaN`, `Infinity`, and non-positive mark prices are rejected.

Calculated amounts are unrounded and unquantized. The receipt precision status is `EXACT_DECIMAL_ECONOMIC_AMOUNT`.

## Receipt Identity Policy

The deterministic receipt identity binds contract id/version, claim scope, source raw hash, selected-event hash, source event identity, symbol, funding time, funding rate, funding mark price, rate type, signed quantity, quantity unit, contract multiplier, formula version, and numeric policy.

The identity excludes current time, hostname, absolute path, Git working-tree state, random UUID, process id, and temporary directory.

Receipt ID: `3833f2fb83a0c59031236cf5bb29b2de0ad2122765f03074f219a2c24bf5bd9b`.

Expected receipt canonical SHA-256: `d7a8827d8054ac2a843baf25dcc9dd547f4235ef10571e30d43cb69ef20b294f`.

Expected receipt file SHA-256: `35a42ea4c3dfbd62c9c0aeac8e30975723193df7f85b2a4edb30cf165f88044d`.

## Idempotency Behavior

Reconstructing the same inputs again returns the same deterministic receipt bytes and receipt id.

Applying the same receipt twice in one supplied batch is rejected with `DUPLICATE_APPLICATION`.

## Failure Reasons

Implemented V0 reason codes:

`SOURCE_FIXTURE_MISSING`, `SOURCE_HASH_MISMATCH`, `SOURCE_EVENT_NOT_FOUND`, `EVENT_IDENTITY_MISMATCH`, `SYMBOL_MISMATCH`, `MARK_PRICE_MISSING`, `MARK_PRICE_NON_POSITIVE`, `FUNDING_RATE_INVALID`, `FUNDING_TIME_INVALID`, `RATE_TYPE_INVALID`, `QUANTITY_INVALID`, `QUANTITY_UNIT_UNRESOLVED`, `CONTRACT_MULTIPLIER_UNRESOLVED`, `SIGN_CONVENTION_UNRESOLVED`, `NUMERIC_POLICY_VIOLATION`, `DUPLICATE_APPLICATION`, `RECEIPT_IDENTITY_MISMATCH`, `CALCULATED_NOTIONAL_MISMATCH`, `CALCULATED_TRANSFER_MISMATCH`, `QNTY_EXTENSION_BOUNDARY_UNSAFE`.

Missing account receipt remains `NOT_APPLICABLE` for this public economic reconstruction.

## Tests

New focused tests:

```text
.venv/bin/python -m pytest tests/test_public_funding_economic_fixture_v0.py -q
26 passed in 0.13s
```

Relevant existing regression slice:

```text
.venv/bin/python -m pytest tests/test_paper_pnl.py tests/test_funding_source_snapshot_schema.py tests/test_funding_source_digest_window_semantics.py tests/test_funding_source_immutable_bundle_semantics.py tests/test_paper_sqlite_writer.py tests/test_paper_sqlite_verify.py tests/test_paper_sqlite_verify_report.py tests/test_paper_matched_null.py tests/test_receipt_schema.py -q
413 passed in 37.09s
```

Runnable fixture:

```text
.venv/bin/python -m quantbot.paper.public_funding_economic_fixture --fixture tests/fixtures/public_funding_economic_v0/input.json --verify
PUBLIC_ECONOMIC_FIXTURE_V0_VERIFIED
```

Temporary independent validator:

```text
/home/swirky/.cache/agent-tmp/codex/public-economic-fixture-v0/independent_public_economic_fixture_validator.py
INDEPENDENT_PUBLIC_ECONOMIC_FIXTURE_VALIDATION_PASS
```

## Non-Claims

This fixture is not an account receipt, not a real wallet posting, not a real position, not a real trade, not evidence of execution, not evidence of a spot hedge, not evidence of capital efficiency, not evidence of margin survival, not evidence of liquidation survival, not evidence about ADL, not evidence of profitability, not evidence of alpha, not a strategy trial, and not a research candidate.

## Known Limitations

This implementation does not prove Binance account posting precision, wallet rounding, authenticated account income, historical executability, real position existence, spot hedge existence, capital efficiency, margin survival, liquidation survival, ADL survival, profitability, alpha, or strategy validity.

## Artifact Hashes

`quantbot/paper/public_funding_economic_fixture.py`: `394d6cdb60e1f873a08996dc35c083036f8af6b012db604483c1df2fd8df7ed3`

`tests/fixtures/public_funding_economic_v0/input.json`: `26eaa573a3f1ba74878218a56eafa0b2e47e714c48604e7f319c2a2419af08bc`

`tests/fixtures/public_funding_economic_v0/expected_receipt.json`: `35a42ea4c3dfbd62c9c0aeac8e30975723193df7f85b2a4edb30cf165f88044d`

`tests/test_public_funding_economic_fixture_v0.py`: `2cb5d0ddeb65249c88e6edcb6dca26c66e5cc443f7d53196320491ce16bc57ab`

Implementation receipt SHA-256 is computed after this file is written and reported in the final task verdict.
