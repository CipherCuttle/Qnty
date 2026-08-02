# Public Economic Fixture V0 Repair Receipt

Task ID: `REPAIR_PUBLIC_ECONOMIC_FIXTURE_V0_REVIEW_FINDINGS`

Review commit: `7f65d858074846697586d12449606540922fcdb3`

Implementation commit under repair: `432d5326a7e0d63c704b170cf663d74929257df5`

Starting QNTY HEAD: `432d5326a7e0d63c704b170cf663d74929257df5`

QNTY branch: `chore/external-trust-root-dispatcher-repair-v046`

QntyLab observed HEAD: `7f65d858074846697586d12449606540922fcdb3`

## Reproduced Blocker

The blocker was reproduced before repair with a temporary receipt copy:
`verification.source_hashes_verified` changed from `true` to `false`.
`verify_receipt()` accepted the tampered receipt.

Pre-repair verification subfields observed:

- `account_posting`
- `arithmetic_verified`
- `claim_scope`
- `claim_verdict`
- `reason_codes`
- `source_event_identity_verified`
- `source_hashes_verified`

Pre-repair behavior accepted removals, type changes, value changes, and an
unexpected key for most nested verification metadata. Only `claim_scope`,
`claim_verdict`, and the entire missing object were rejected, and they used
`RECEIPT_IDENTITY_MISMATCH`.

## Root Cause

`verify_receipt()` only checked that the nested `verification` object existed
and that two subfields matched. The remaining deterministic derived metadata
was trusted from the supplied receipt.

## Exact Repair

The verifier now independently derives the complete expected `verification`
mapping and compares the supplied object exactly as a mapping:

- all expected keys must be present;
- no unexpected keys are allowed;
- all values must match exactly;
- value types must match exactly;
- supplied verification flags are not trusted.

Tampering now fails with `VERIFICATION_METADATA_MISMATCH`.

## Verification-Metadata Policy

Verification metadata is deterministic derived metadata outside the
load-bearing receipt identity. Receipt identity binds the economic and public
source inputs. Receipt verification separately enforces the exact derived
verification metadata.

## Decimal Lexical Policy

Policy name: `CANONICAL_PLAIN_DECIMAL_V1`

Maximum decimal lexical length: `128` characters.

Source-event decimal fields:

- `funding_rate`
- `funding_mark_price`

Source-event decimals must be strings in plain decimal notation, with no
exponent notation, leading plus sign, whitespace, over-length value, or
non-finite value. Source strings may preserve trailing fractional zeros because
they are authoritative source representations. Source-event decimal identity
binds the authoritative source representation plus the preserved source hashes.

Synthetic and contract decimal fields:

- `signed_position_quantity`
- `contract_multiplier`

Synthetic and contract decimals must be strings in canonical normalized plain
notation: no exponent notation, leading plus sign, whitespace, leading integer
zeros except zero itself, trailing fractional zeros, decimal point without
fractional digits, negative zero, over-length value, or non-finite value. Zero
is represented only as `0`.

Invalid decimal lexical forms are rejected before unsafe Decimal operations can
surface raw `decimal.InvalidOperation`, `decimal.Overflow`, or `ValueError`.

## Independent Oracle Additions

Added independent arithmetic oracle coverage using only standard-library
`Decimal` to derive long, short, and zero vectors:

- long notional `73.65356663043`, transfer `-0.0042004629049334229`;
- short notional `73.65356663043`, transfer `0.0042004629049334229`;
- zero notional `0`, transfer `0`.

Added independent identity oracle coverage that constructs the load-bearing
identity payload directly from the frozen fixture contract, serializes it with
standard-library canonical JSON policy, hashes UTF-8 bytes, and checks receipt
ID `3833f2fb83a0c59031236cf5bb29b2de0ad2122765f03074f219a2c24bf5bd9b`.

Added independent verification metadata oracle coverage that constructs the
exact expected mapping in the test rather than importing a verifier constant.

## Changed Paths

- `quantbot/paper/public_funding_economic_fixture.py`
- `tests/test_public_funding_economic_fixture_v0.py`
- `docs/receipts/PUBLIC_ECONOMIC_FIXTURE_V0_REPAIR.md`

Valid fixture files were not changed.

## Test Results

Focused fixture tests:

- command: `.venv/bin/python -m pytest tests/test_public_funding_economic_fixture_v0.py -q`
- return code: `0`
- passed: `53`
- failed: `0`
- skipped: `0`
- duration: `0.30s`
- proves: repaired verifier, decimal policy, hostile fixture cases, and
  independent arithmetic/identity/verification oracles for the bounded fixture.
- does not prove: private account posting, strategy validity, live execution,
  or integration readiness.

Focused regression set:

- command: `.venv/bin/python -m pytest tests/test_paper_pnl.py tests/test_funding_source_snapshot_schema.py tests/test_funding_source_digest_window_semantics.py tests/test_funding_source_immutable_bundle_semantics.py tests/test_paper_sqlite_writer.py tests/test_paper_sqlite_verify.py tests/test_paper_sqlite_verify_report.py tests/test_paper_matched_null.py tests/test_receipt_schema.py -q`
- return code: `0`
- passed: `413`
- failed: `0`
- skipped: `0`
- duration: `45.15s`
- proves: the reported bounded paper/funding/sqlite regression slice remains
  green.
- does not prove: full offline suite coverage or integration approval.

Fixture command, run twice:

- command: `.venv/bin/python -m quantbot.paper.public_funding_economic_fixture --fixture tests/fixtures/public_funding_economic_v0/input.json --verify`
- return code: `0` both runs
- stdout bytes: identical
- stderr bytes: identical empty output
- durations: `0.03s`, `0.03s`
- proves: valid CLI output remains deterministic and byte-stable.
- does not prove: independent source refetch or real account posting.

Compile:

- command: `.venv/bin/python -m compileall quantbot/paper/public_funding_economic_fixture.py`
- return code: `0`
- duration: `0.02s`
- proves: repaired module compiles.
- does not prove: type-check completeness.

Installed lint/type tools:

- `ruff`: not available in the venv
- `mypy`: not available in the venv

## Stability Results

Receipt ID before repair:
`3833f2fb83a0c59031236cf5bb29b2de0ad2122765f03074f219a2c24bf5bd9b`

Receipt ID after repair:
`3833f2fb83a0c59031236cf5bb29b2de0ad2122765f03074f219a2c24bf5bd9b`

Expected canonical receipt SHA-256 before repair:
`d7a8827d8054ac2a843baf25dcc9dd547f4235ef10571e30d43cb69ef20b294f`

Expected canonical receipt SHA-256 after repair:
`d7a8827d8054ac2a843baf25dcc9dd547f4235ef10571e30d43cb69ef20b294f`

## Independent Repair Validator

Validator path:
`$TMPDIR/public-economic-fixture-v0-repair/repair_validator.py`

The validator does not import the implementation module. It independently
recomputes arithmetic and identity, inspects the committed receipt verification
object, generates verification metadata tampers, invokes the public verifier
through isolated subprocesses, tests rejected decimal aliases through the CLI,
confirms no raw decimal exception escapes, confirms valid CLI output is stable,
and confirms QntyLab state did not change.

Result: `PUBLIC_ECONOMIC_FIXTURE_V0_REPAIR_VALIDATION_PASS`

## Remaining Review Findings

The required correctness findings are repaired:

- tampered verification metadata is rejected;
- decimal lexical policy is explicit and tested;
- independent arithmetic, identity, and verification oracles were added.

The branch-isolation concern remains an integration-process concern for a later
operator action. This repair intentionally does not switch branches, cherry-pick,
push, or claim integration readiness.

Unexpected extra fixture fields remain outside this required repair scope.

## Non-Claims

This repair does not add strategy logic, SQLite writes, paper-engine behavior,
network calls, account-posting logic, spot logic, capital logic, margin logic,
liquidation logic, ADL logic, or SOFR logic.

This repair does not claim profitability, alpha, real account verification, real
position verification, real trade verification, production readiness, or
integration approval.

## Final Verdict

`PUBLIC_ECONOMIC_FIXTURE_V0_CORRECTNESS_REPAIRED`

Integration status: `READY_FOR_FRESH_HOSTILE_REREVIEW`

Immediate next action: `FRESH_HOSTILE_REREVIEW_PUBLIC_ECONOMIC_FIXTURE_V0`
