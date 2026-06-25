# LANE_CONFIG_INIT_TEMP_E2E_PHASE3_RECEIPT

## 1. Purpose

Temp-only end-to-end proof that the merged lane-init wrapper materializes a NEW
accounting lane on disk and that the resulting DB passes the read-only verifier.

- No writer run (init only).
- No shadow lane.
- No production path touched.
- SIMULATION-support tooling only. **No profitability or edge claim.** Strategy
  remains `EDGE_UNPROVEN`.

## 2. Commit / context

- Main commit (branch base): `c53c6ef` ("Add lane config init wrapper (#21)")
- Receipt branch: `phase3/lane-config-init-temp-e2e`
- Wrapper CLI: `scripts/qnty-paper-lane-init.py`
- Helper: `quantbot/paper/lane_init.py`
- Read-only verifier CLI: `scripts/qnty-paper-sqlite-verify.py`

## 3. Temp proof location

- Root: `/tmp/qnty_lane_init_e2e_v0`
- Output dir: `/tmp/qnty_lane_init_e2e_v0/lane_out`
- DB: `/tmp/qnty_lane_init_e2e_v0/lane_out/paper_ledger.db`

All artifacts live under `/tmp` only — nothing was written inside the repo (besides
this receipt).

## 4. Command shape

Lane init (init only — never runs the writer):

```bash
python scripts/qnty-paper-lane-init.py \
  --output-dir /tmp/qnty_lane_init_e2e_v0/lane_out \
  --db-path /tmp/qnty_lane_init_e2e_v0/lane_out/paper_ledger.db \
  --lane-id temp_lane_e2e_v0 \
  --strategy-id matched_null_shadow_v0 \
  --strategy-version 0.0.0-temp \
  --forward-start-ts 2026-07-01T00:00:00
```

Read-only verifier (no artifacts published):

```bash
python scripts/qnty-paper-sqlite-verify.py \
  --db-path /tmp/qnty_lane_init_e2e_v0/lane_out/paper_ledger.db \
  --no-emit --json
```

Verifier exit code observed: **5** (`PRE_START`). This is the **expected** status for
a freshly initialized, batch-less lane DB (zero committed eligible bars).

## 5. Lane identity (clearly fake / non-production)

- `lane_id = temp_lane_e2e_v0`
- `strategy_id = matched_null_shadow_v0`
- `strategy_version = 0.0.0-temp`
- `forward_start_ts = 2026-07-01T00:00:00` (future, on the 8h 00/08/16 UTC grid)

## 6. Generated files

Under `/tmp/qnty_lane_init_e2e_v0/lane_out`:

- `paper_config.json`
- `lane_identity.json`
- `lane_config_v2.json`
- `paper_ledger.db` (plus SQLite-managed `paper_ledger.db-shm` / `paper_ledger.db-wal`)

## 7. Hashes

- `accounting_config_hash_v1`:
  `3529706a4b9d00a977b957143ec856379e152d0d4106e50b8a2b927e5a68dca0`
- `config_hash_v2`:
  `d4fee15ac64c84003b2297cdeef83eeda7ffeee56fc9e2a525973398b7fb047b`
- `pre_registration_hash`: `null` (existing null-sidecar behavior; no generation)

File sha256 (init output, captured at proof time):

```
b33517a08384ccfd4048aa362363f09c760b123db486c123b98c91b1a348212b  paper_config.json
548acd458ee794864013e557adbde0fb35ac49b825952f329e7160646bc8b0cd  lane_identity.json
69a6b2439baee84406648d929470f0fd18de6c82619782057b1f8a7a71cb5d15  lane_config_v2.json
ddfe1a14c4c572462c858727c85b2c70ecabbe6ae295a81bb0363f3b524816bd  paper_ledger.db
```

(The `.db` sha256 is informational only; live SQLite WAL/shm sidecars mean the `.db`
digest is not a stable commitment — the authoritative identity is the DB
`paper_config` row + the `config_hash_v2` commitment above.)

## 8. DB inspection (read-only, `mode=ro`)

`paper_config` row (id = 1) matched the sidecars exactly:

- `lane_id = temp_lane_e2e_v0`
- `strategy_id = matched_null_shadow_v0`
- `strategy_version = 0.0.0-temp`
- `config_hash = 3529706a...dca0` (== `accounting_config_hash_v1`)
- `config_hash_v2 = d4fee15a...047b`
- `pre_registration_hash = null`

Row counts:

- `ledger_batches = 0`
- `signal_snapshots = 0`
- `fills = 0`
- `events` — table not present in this schema (no such table)
- `positions` — table not present in this schema (no such table)

No writer was run; the zero `ledger_batches` / `fills` / `signal_snapshots` counts
confirm only init + read-only verification occurred.

## 9. Verifier result

- Status: `PRE_START` (exit code `5`).
- `failures: []`, `failure_count: 0`, `query_only: 1`.
- `--no-emit` used → no `paper_verify_report.json` / receipt / log artifacts published
  (`report_path: null`).

## 10. Safety verification

- All artifacts under `/tmp/qnty_lane_init_e2e_v0` only.
- `git status` unchanged except `.claude/` (untracked, not staged) and this receipt.
- No `/srv/qnty` touched.
- No production `paper_pnl_v1` touched.
- No VM / SSH / systemd / timers / services / network.
- No migrations / `ALTER`.
- No live trading / keys / orders.
- No edge / profitability claims.

## 11. Scope exclusions

Explicitly excluded:

- production DB
- `/srv/qnty`
- VM / SSH
- systemd / timers / services
- migration / `ALTER`
- production `paper_pnl_v1`
- writer run
- real shadow output directory
- `source_data_digest`
- `pre_registration_hash` generation beyond existing `null` sidecar
- V2
- live / shadow lane runs
- cross-lane reporter
- live trading / keys / orders
- profitability or edge claims

## 12. Verdict

- `TEMP_E2E_PROOF_RECEIPT_READY`
- `EDGE_UNPROVEN`
