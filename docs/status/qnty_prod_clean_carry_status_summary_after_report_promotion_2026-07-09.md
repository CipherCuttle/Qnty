# QNTY Prod Clean Carry Status Summary — After Report Promotion

**Date:** 2026-07-09
**Branch:** `docs/qnty-prod-clean-carry-status-summary-after-report-promotion`
**Status:** CLEAN_NET_OF_CARRY (prod official report)
**Verdict:** QNTY_PROD_CLEAN_CARRY_STATUS_SUMMARY_AFTER_REPORT_PROMOTION_RECORDED

---

## 1. Final Prod State Summary

| Property | Value |
|---|---|
| Official prod report schema | 42-key publication schema (promoted by PR #132) |
| Official prod report hash | `3de74774f715b2b20948e303c1dfb179498ab573ed0b53269ea3b650f608bcc2` |
| Backup hash (pre-promotion original) | `2c6af12ba74d92b52d827263225760145c5e7c2eef5b6053ff18779a8f9c10c3` |
| Prod DB hash | `94874dab6d82701785fdf7379777b3e8a5850c3f869a42625edd90dcdc18bc11` (unchanged) |
| `status` | `OK` |
| `failure_count` | `0` |
| `funding_clean_carry_decision` | `CLEAN_NET_OF_CARRY` |
| `source_path_resolution_mode` | `explicit_data_dir` |
| Full-window sidecar | `funding_source_full_window_snapshot_v1_batch57.json` (batch57, `present_valid`) |
| `EDGE_UNPROVEN` | Remains in effect |
| `BLOCK_LIVE_INTEGRATION` | Remains in effect |

---

## 2. Artifact Chain Summary (PRs #120 → #133)

| PR | Document | What It Did |
|---|---|---|
| #120 | [`docs/status/qnty_full_window_funding_source_snapshot_semantics_2026-07-09.md`](docs/status/qnty_full_window_funding_source_snapshot_semantics_2026-07-09.md) | Full-window snapshot semantics defined and merged |
| #121 | [`docs/status/qnty_full_window_funding_source_snapshot_semantics_2026-07-09.md`](docs/status/qnty_full_window_funding_source_snapshot_semantics_2026-07-09.md) | Writer-side full-window emission support (see also `funding_source_full_window_emit_cli.py`) |
| #123 | [`docs/status/qnty_full_window_emit_cli_entrypoint_2026-07-09.md`](docs/status/qnty_full_window_emit_cli_entrypoint_2026-07-09.md) | CLI entrypoint for full-window emission |
| #126 | [`docs/status/qnty_prod_full_window_artifact_emission_execution_2026-07-09.md`](docs/status/qnty_prod_full_window_artifact_emission_execution_2026-07-09.md) | Controlled prod full-window artifact emission (snapshot + bundle) |
| #130 | [`docs/status/qnty_prod_full_window_report_promotion_schema_reconciliation_implementation_2026-07-09.md`](docs/status/qnty_prod_full_window_report_promotion_schema_reconciliation_implementation_2026-07-09.md) | Schema-compatible candidate report producer (`verify_and_publish_candidate`) |
| #131 | [`docs/status/qnty_prod_full_window_publication_candidate_vm_validation_2026-07-09.md`](docs/status/qnty_prod_full_window_publication_candidate_vm_validation_2026-07-09.md) | VM validation of publication-schema candidate against real prod lane |
| #132 | [`docs/status/qnty_prod_full_window_report_promotion_execution_v2_2026-07-09.md`](docs/status/qnty_prod_full_window_report_promotion_execution_v2_2026-07-09.md) | Official report promotion (42-key publication schema, `CLEAN_NET_OF_CARRY`) |
| #133 | [`docs/status/qnty_prod_full_window_report_promotion_post_merge_audit_2026-07-09.md`](docs/status/qnty_prod_full_window_report_promotion_post_merge_audit_2026-07-09.md) | Post-merge audit (13/13 checks pass, hashes confirmed) |

---

## 3. What IS Proven

- Prod official report is now publication-schema clean-carry under full-window source state.
- Hashes (`3de74774...bcc2` promoted, `2c6af12b...10c3` backup) are recorded in two independent receipts (PR #132 execution + PR #133 audit).
- Prod DB hash (`94874dab...bc11`) is unchanged — no DB mutation by report promotion.
- All 20 source CSV hashes are unchanged from preflight baseline.
- All 20 snapshot hashes (19 per-batch + 1 full-window) are unchanged.
- Bundle hash (`af27385a...`) is unchanged.
- No stray `.tmp_*` files in prod lane.
- No systemd services/timers or system processes were disturbed.
- Verifier gate no longer blocks prod on the prior batch-vs-ledger window issue. The full-window sidecar (`funding_source_full_window_snapshot_v1_batch57.json`) provides the full-ledger window scope that resolves `funding_source_snapshot_window_mismatch`.
- `source_path_unavailable` is resolved when the verify invocation supplies `--data-dir` (as the prod publish path does from its `/srv/qnty/repo` working directory).

---

## 4. What IS NOT Proven

- **Edge / profit**: No edge or profitability has been proven by this promotion. `CLEAN_NET_OF_CARRY` means only that the verifier gate no longer blocks the report — it does not imply a profitable strategy.
- **Live trading readiness**: No live exchange integration, no exchange key deployment, no order routing, no risk controls for live execution.
- **2x / shorting readiness**: No 2x leverage or short-position strategy has been validated.
- **Exchange integration approval**: No exchange has approved or reviewed this research output.
- **Future data stability guarantee**: No guarantee that future data ingest cycles will not introduce new discrepancies. The clean-carry status is a point-in-time property of the current prod DB + source CSVs.
- **Clean-carry = profitable strategy**: No claim that clean-carry status implies a profitable trading strategy. Carry-positive funding regimes may or may not persist.

---

## 5. Current Decision Matrix

| Gate | Status | Notes |
|---|---|---|
| Prod clean-carry report | **CLEAN** | Verified by PR #132 execution + PR #133 audit |
| Shadow clean-carry | **CLEAN** | Already clean from prior shadow receipts |
| Live integration | **BLOCKED** | `BLOCK_LIVE_INTEGRATION` remains in force |
| Edge status | **UNPROVEN** | `EDGE_UNPROVEN` remains in force |
| 2x / shorting | **BLOCKED** | Not validated; no strategy-level approval |
| Next allowed work | **Risk-readiness analysis only** | See recommended next task |

---

## 6. Recommended Next Task

**`QNTY_RISK_AND_READINESS_GAP_ANALYSIS_AFTER_CLEAN_CARRY`**

Produce a risk-readiness analysis document (`docs/status/`) that enumerates the open requirements for taking the next step beyond clean-carry. The analysis should:

1. Inventory all current guardrails (`EDGE_UNPROVEN`, `BLOCK_LIVE_INTEGRATION`, no 2x/shorting) and document what would need to be true for each to be lifted.
2. Identify the specific verifier/infrastructure gaps between current state and a shadow/live trading deployment.
3. Document risk controls that would need to exist before any live integration could be considered.
4. Recommend the next concrete technical milestone.

This is a **docs-only** analysis. No source code, no DB mutation, no production changes.

---

*Prepared 2026-07-09. All references verified against on-disk receipts.*