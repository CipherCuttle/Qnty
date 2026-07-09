# QNTY Offline Edge Validation — Implementation Skeleton Plan

**Status:** Planning only — no code implementation.
**Verdict target:** `QNTY_OFFLINE_EDGE_VALIDATION_IMPLEMENTATION_SKELETON_PLAN_RECORDED`
**Branch:** `docs/qnty-offline-edge-validation-implementation-skeleton-plan`
**Guardrails active:** `EDGE_UNPROVEN`, `BLOCK_LIVE_INTEGRATION`

## 1. Executive Summary

This document is the final docs-only pre-implementation skeleton plan for the offline edge-validation runner. It defines the smallest safe first implementation slice — a non-prod, fixture-only skeleton that creates schema dataclasses, a CLI stub with `--read-only` required, prod-path refusal helpers, and a fixture-only golden test.

**This PR contains no code.** All file references below are proposed future files that will be created in a subsequent code PR.

- `EDGE_UNPROVEN` remains in effect — no edge claim is made by this plan.
- `BLOCK_LIVE_INTEGRATION` remains in effect — no live, shadow, or deploy path is created.
- `CLEAN_NET_OF_CARRY` means only "not killed by verifier gate," not edge/profit/live readiness.
- Long-only / 1x remains the only assumed lane.
- `INCONCLUSIVE` or `SKELETON_ONLY` are the only permitted first-PR verdicts — never `EDGE_CANDIDATE`.

## 2. Minimal First Implementation Slice

The smallest safe code PR (PR A) shall consist of:

1. **Schema dataclasses / TypedDicts** — define the output receipt structure with stable top-level keys. No validation logic, no cost model math, no engine integration.
2. **CLI stub with `--read-only` required** — a CLI that parses args, validates safety constraints, refuses prod paths, and writes a placeholder skeleton output. No actual edge computation.
3. **Prod-path refusal helpers** — hard-coded refusals for known prod paths (`/srv/qnty/output/paper_pnl_v1`, official report paths).
4. **Fixture-only golden test** — tests that the CLI accepts fixture paths, writes only to `/tmp`, refuses prod paths, and validates the schema.
5. **No actual edge verdict** — output is `SKELETON_ONLY` or `INCONCLUSIVE`. No `EDGE_CANDIDATE` emission.

This slice is independently verifiable: it leaves zero footprint outside `/tmp`, makes no DB/CSV mutations, and contains no exchange or live integration code.

## 3. Proposed First Code PR Files (PR A)

The following files shall be created in PR A. They do not exist yet and are NOT created in this PR.

| File | Purpose |
|------|---------|
| `quantbot/experiment/offline_edge_schema.py` | TypedDicts/dataclasses for validation receipt structure |
| `quantbot/experiment/offline_edge_validation_cli.py` | CLI entry point with `--read-only` safety contract |
| `tests/experiment/test_offline_edge_validation_cli.py` | CLI contract tests (safety, path refusal, fixture acceptance) |
| `tests/experiment/test_offline_edge_schema.py` | Schema validation tests (required keys, field types) |
| `tests/fixtures/edge_validation_golden/README.md` | Document the golden fixture structure (optional, recommended) |

These files will be created in a future code-only PR. This PR contains only this plan document.

## 4. What Must NOT Be Included in PR A

The following are explicitly excluded from PR A:

- ❌ No engine integration (no calls to `run_engine()` or `PriceBook`)
- ❌ No Lane B creation (no `paper_pnl_volnorm_v1` or equivalent)
- ❌ No prod data access (no SQLite readers, no DB path resolution)
- ❌ No funding replay (no `funding_in_interval()` or `check_funding_coverage()` calls)
- ❌ No walk-forward execution (no `build_walkforward_splits()` or `run_walkforward_experiment()`)
- ❌ No V2 performance claim (no `EDGE_CANDIDATE` verdict)
- ❌ No live/shadow deployment (no wrangler, systemd, or ops integration)
- ❌ No report promotion (no `promotion_contract.py` or publication logic)
- ❌ No CSV/DB writes outside `/tmp` (output directory must be under `/tmp` or explicit scratch)
- ❌ No exchange modules imported (no `exchange.*`, `ccxt`, or live data fetchers)
- ❌ No `--write`, `--live`, `--deploy`, `--promote` CLI flags

## 5. CLI Skeleton Contract for PR A

The CLI (`offline_edge_validation_cli.py`) shall implement this minimum contract:

### Required Flags
- `--read-only` — **REQUIRED**. Script MUST refuse to run without this flag. Exit code 1, message: `"FATAL: --read-only flag is required. This is a read-only validation tool."`
- `--output-dir` — **REQUIRED**. Must resolve to a path under `/tmp/` or a configured scratch prefix. If the resolved path is not under an allowed prefix, exit code 2, message: `"FATAL: --output-dir must be under /tmp or scratch. Refusing: {resolved_path}"`

### Accepted But Fixture-Only (no production behavior)
- `--bars-dir` — Accepted but fixture-only in PR A. No production data access. If pointing to `/srv/qnty/`, exit code 3.
- `--funding-dir` — Accepted but fixture-only. Same prod-path refusal.
- `--manifest-dir` — Accepted but fixture-only. Same prod-path refusal.

### Forbidden Flags That Must NOT Exist
- `--write` — MUST NOT be accepted
- `--live` — MUST NOT be accepted
- `--deploy` — MUST NOT be accepted
- `--promote` — MUST NOT be accepted

### Prod Path Refusal
The following paths shall be hard-coded as refused with exit code 3:
- `/srv/qnty/output/paper_pnl_v1`
- Any path under `/srv/qnty/` (configurable via constant `PROD_PATH_PREFIX = "/srv/qnty"`)
- Official report output paths from the report promotion system

### Output Behavior
- Writes a `validation_receipt.json` to `--output-dir`
- Receipt must validate against the schema
- `final_verdict` must be `SKELETON_ONLY` or `INCONCLUSIVE` — never `EDGE_CANDIDATE`
- No prod-state mutation, no DB writes, no CSV writes outside `/tmp`

## 6. Schema Skeleton Contract for PR A

The schema (`offline_edge_schema.py`) shall define these stable top-level keys using TypedDict:

```python
class ValidationReceipt(TypedDict):
    validation_receipt: ReceiptMetadata       # tool identity, timestamp, version
    input_manifest_fingerprint: str           # SHA256 of input manifest(s)
    cost_model_assumptions: CostModelAssumptions  # slippage, commission, thresholds
    per_stage_metrics: dict[str, StageMetrics]    # metrics per pipeline stage A-F
    final_verdict: str                        # one of the allowed verdict strings
```

### ReceiptMetadata (TypedDict)
- `tool_name: str` — always `"offline_edge_validation"`
- `tool_version: str` — semver string
- `timestamp_utc: str` — ISO 8601 UTC timestamp
- `pipeline_description: str` — human-readable pipeline stage description

### CostModelAssumptions (TypedDict)
- `slippage_bps_per_side: float` — default 5.0
- `commission_bps_per_side: float` — default 5.0
- `heat_cap: float` — from volnorm_portfolio, default 1.0
- `vol_lookback_bars: int` — default 90
- `vol_floor: float` — default 1e-6

### StageMetrics (TypedDict)
- `stage_id: str` — one of `"A"`, `"B"`, `"C"`, `"D"`, `"E"`, `"F"`
- `stage_name: str` — human-readable name
- `status: str` — one of `"PASS"`, `"FAIL"`, `"SKIP"`, `"SKELETON_ONLY"`
- `summary: str` — human-readable summary

### Allowed Verdict Strings
- `"SKELETON_ONLY"` — only permitted in PR A
- `"INCONCLUSIVE"` — may also be emitted in PR A
- `"EDGE_CANDIDATE"` — FORBIDDEN in PR A
- `"NO_EDGE"` — FORBIDDEN in PR A
- `"NEEDS_MORE_DATA"` — FORBIDDEN in PR A
- `"BLOCKED_BY_DATA_QUALITY"` — FORBIDDEN in PR A

Later PRs may extend these verdicts. PR A must not emit `EDGE_CANDIDATE`.

## 7. Test Requirements for PR A

`tests/experiment/test_offline_edge_validation_cli.py` shall include:

| Test | What It Verifies |
|------|-----------------|
| `test_refuses_without_read_only` | CLI exits with code 1 and expected message when `--read-only` is omitted |
| `test_refuses_srv_qnty_output` | CLI exits with code 3 when `--output-dir` points to `/srv/qnty/output/paper_pnl_v1` |
| `test_refuses_srv_qnty_prefix` | CLI exits with code 3 when `--output-dir` is any path under `/srv/qnty/` |
| `test_refuses_official_report_path` | CLI exits with code 3 when `--output-dir` matches an official report output path |
| `test_accepts_tmp_output_with_fixtures` | CLI accepts `--output-dir` under `/tmp/` with fixture `--bars-dir`, writes `validation_receipt.json` |
| `test_receipt_contains_required_keys` | JSON receipt written to `/tmp` contains all 5 top-level keys from the schema |
| `test_final_verdict_is_skeleton_only` | Receipt's `final_verdict` is `SKELETON_ONLY` or `INCONCLUSIVE`, never `EDGE_CANDIDATE` |
| `test_no_mutation_of_fixture_files` | Fixture file SHA256s are unchanged after CLI run (checksum proof) |
| `test_no_exchange_modules_imported` | Test verifies that no `exchange.*`, `ccxt`, or live data modules are importable from the validation module |

`tests/experiment/test_offline_edge_schema.py` shall include:

| Test | What It Verifies |
|------|-----------------|
| `test_receipt_all_required_keys` | `ValidationReceipt` TypedDict has all required keys |
| `test_cost_model_defaults_match_spec` | `CostModelAssumptions` defaults match the volnorm_portfolio constants |
| `test_verdict_strings_are_constrained` | Verdict validation function allows only the permitted strings |
| `test_receipt_metadata_structure` | `ReceiptMetadata` has correct field types |

## 8. Acceptance Gates for PR A

The following gates must be satisfied before PR A can be merged:

| Gate | Criteria |
|------|----------|
| ✅ Tests pass | All tests in `tests/experiment/test_offline_edge_validation_cli.py` and `tests/experiment/test_offline_edge_schema.py` pass |
| ✅ Only allowed files changed | Git diff shows only the 4-5 proposed files (no modifications to existing files) |
| ✅ No prod paths touched | No code references to `/srv/qnty/` as a readable/writable path (only as a refused pattern) |
| ✅ No DB mutation | No SQLite imports, no `ledger.py` calls, no DB path references in the CLI or tests |
| ✅ No CSV mutation | No CSV writes outside `/tmp/` in tests, no production CSV path references |
| ✅ No edge verdict claim | `final_verdict` is `SKELETON_ONLY` or `INCONCLUSIVE` — never `EDGE_CANDIDATE` |
| ✅ No live integration | No import of `exchange.*`, `ccxt`, live data fetchers, wrangler, or deployment modules |
| ✅ No Lane B creation | No `paper_pnl_volnorm_v1`, no lane creation, no lane config |
| ✅ No engine integration | No import of `run_engine()`, `PriceBook`, `run_walkforward_experiment()` |

## 9. Future PR Sequence

Proposed safe implementation sequence beyond PR A:

| PR | Focus | Description |
|----|-------|-------------|
| **PR A** | Schema + CLI safety skeleton | Schema dataclasses, CLI with `--read-only` safety, prod-path refusal, fixture-only golden tests. *This is what this plan describes.* |
| **PR B** | Manifest/hash input inventory | Read input manifests, compute fingerprints, verify fixture integrity. No engine integration. |
| **PR C** | Cost model math with fixtures | Implement the cost model (slippage, commission, funding) using fixture data. Verify against known values. |
| **PR D** | V2 volnorm reconstruction with fixtures | Reconstruct the V2 volnorm portfolio weights offline using `compute_vol_normed_weights()` on fixture bars. Verify weight stability. |
| **PR E** | Walk-forward / counterfactual replay | Run walk-forward splits on fixture data, replay with V2 weights, compare to `paper_pnl_v1` baseline. No prod data. |
| **PR F** | Full offline validation receipt | Produce complete validation receipt with `per_stage_metrics` for all 6 stages. Still fixture-only, still `EDGE_UNPROVEN`. |

**Design principle:** Each PR must be independently verifiable — testable with fixtures only, no prod data required, no DB/CSV mutation, no live integration.

## 10. Recommended Next Task

The recommended next task is:

> **QNTY_OFFLINE_EDGE_VALIDATION_SCHEMA_CLI_SKELETON**

This task shall:
1. Switch to `Code` mode
2. Create the 4-5 files listed in Section 3
3. Implement the CLI contract from Section 5
4. Implement the schema contract from Section 6
5. Implement the tests from Section 7
6. Verify all acceptance gates from Section 8
7. Open a PR titled "PR A: Offline edge validation schema + CLI safety skeleton"
8. Do NOT merge — open and stop