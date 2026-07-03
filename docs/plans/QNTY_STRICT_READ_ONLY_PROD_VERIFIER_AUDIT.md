# QNTY Strict Read-Only Prod Verifier Audit

## 1. Purpose

Run the newly deployed read-only SQLite verifier CLI
(`quantbot.paper.sqlite_verify`, `CLI_CONTRACT_VERSION=1.0.0`, added in PR
#70) against the prod paper ledger DB, to determine whether the existing
prod timer-created DB-linked snapshot batch (previously inspected manually
in PR #68) passes the strict verifier's clean-carry gate.

## 2. Scope

Read-only inspection only:

- No writer run (prod or shadow).
- No mutation of prod DB, shadow DB, or `forward_obs`.
- No data refresh, migration, or schema-ensure helper run.
- No systemd/timer changes.
- No dependency installs.
- No WAL checkpoint.
- CLI invoked only with `--db-path`, `--read-only`, `--json`, and
  `--strict-clean-carry`.

## 3. VM/repo state

VM repo at `/srv/qnty/repo` was checked read-only prior to inspection:

```txt
## main...origin/main
8576d6f feat: add read-only sqlite verifier cli (#70)
0b4054d test: specify read-only sqlite verifier cli contract (#69)
cdd2263 docs: add read-only prod db-linked snapshot audit (#68)
c8a475c docs: add shadow db-linked dry run receipt (#67)
f615dde docs: add live schema ensure receipt (#66)
```

Working tree was clean (no local modifications). `py_compile` against
`quantbot/paper/sqlite_verify.py` succeeded, and `--help` output showed
`--db-path`, `--read-only`, `--json`, `--strict-clean-carry`, and
`--no-wal-checkpoint` as documented flags — precheck stop conditions were
not triggered.

## 4. Prod DB target

```txt
/srv/qnty/output/paper_pnl_v1/paper_ledger.db
```

## 5. CLI command

```bash
/srv/qnty/venv/bin/python -m quantbot.paper.sqlite_verify \
  --db-path /srv/qnty/output/paper_pnl_v1/paper_ledger.db \
  --read-only \
  --json \
  --strict-clean-carry
```

Exit code: **4** (nonzero because `--strict-clean-carry` fails closed on a
non-`CLEAN_NET_OF_CARRY` decision — per the audit brief this is not treated
as a command failure). Stderr was empty; a single JSON report was emitted on
stdout, per contract.

Report-level fields confirm the read-only contract was honored:

```txt
read_only:                 true
query_only_pragma_enabled: true
sqlite_open_mode:          file_uri_mode_ro_immutable
db_mutation_performed:     false
wal_shm_files_created:     false
verifier_cli_contract_version: 1.0.0
status:                    OK
```

Non-strict JSON mode was not additionally run: the strict-mode JSON output
was complete and unambiguous (explicit `decision`/`status`/reason-code
fields), so the audit brief's fallback condition ("if strict mode exits
nonzero but emits unclear output") did not apply.

## 6. Strict verifier JSON result

Key fields from the emitted JSON report:

```txt
batches:        39
equity_rows:    39
events:         178
failure_count:  0
funding_clean_carry_decision: CAVEATED_ENGINE_SEMANTICS
funding_clean_carry_status:   refused_digest_mismatch
```

## 7. Clean-carry decision

```txt
CAVEATED_ENGINE_SEMANTICS
```

The verifier did **not** return `CLEAN_NET_OF_CARRY`. Per the audit's
interpretation rules, prod remains `CAVEATED_ENGINE_SEMANTICS`.

## 8. Reason codes

```txt
funding_source_coverage_not_complete
funding_source_file_digest_mismatch
funding_source_row_digest_mismatch
funding_source_snapshot_window_mismatch
```

`funding_clean_carry.funding_coverage_decision`: `missing`. The
`funding_coverage.per_symbol` map shows all five tracked symbols
(`BNBUSDT`, `BTCUSDT`, `ETHUSDT`, `SOLUSDT`, `XRPUSDT`) as `missing`, with 36
individual `missing_window_ids` entries (`source_issue:
missing_source_row`) spanning 2026-06-21 through 2026-07-03.
`funding_coverage_diagnostic_label`:
`missing_funding_treated_as_zero_like_current_engine_not_net_of_carry_clean`.

## 9. Snapshot reference status

The DB-linked snapshot itself (the same batch-39 snapshot manually inspected
in PR #68) reads as structurally valid:

```txt
funding_source_snapshot_status: present_valid
snapshot_sha256:      71c8027fb7c53b8d2e57557fca95b8d2b7041185f9e1844a4a4653fd84553417
source_bundle_sha256: 05db004f04572a5ecb288014d7c411767f1d95c9df0271f0bdb49eb68dfae3ea
write_state:          committed
batch_identity_matches: true
coverage_decision:    complete
```

However, structural/envelope validity of the snapshot file is **not**
sufficient for the strict clean-carry gate — the verifier's digest/coverage
checks against the underlying funding source rows still reason-code the
batch as `funding_source_file_digest_mismatch` /
`funding_source_row_digest_mismatch` / `funding_source_coverage_not_complete`
/ `funding_source_snapshot_window_mismatch`, which is why the overall
decision is `CAVEATED_ENGINE_SEMANTICS` rather than `CLEAN_NET_OF_CARRY`
despite `snapshot_status: present_valid`.

## 10. Funding re-sum/arithmetic status

```txt
resum_check.status:              ok
resum_check.arithmetic_status:   OK
resum_check.arithmetic_ok:       true
funding_amount_sum:              1.58617019
funding_rows:                    36
latest_equity_bar_ts:            2026-07-03T08:00:00
latest_equity_funding_cum:       1.58617021
ledger_state_funding_cum:        1.586170210203532
tolerance_abs:                   1e-06
issues:                          []
```

Arithmetic re-sum passes within tolerance, matching the prior manual
observation from PR #68. As the verifier's own `note` states, arithmetic
correctness and complete source coverage are necessary but not sufficient
for `CLEAN_NET_OF_CARRY` — the missing-funding-source-row reason codes above
independently keep the decision at `CAVEATED_ENGINE_SEMANTICS`.

## 11. DB immutability check

```txt
sha256 before: 5274a1cfbdcdf9810197e3e60ff43d6bd93a2f4ea5c376182314c4d35b53fdd3
sha256 after:  5274a1cfbdcdf9810197e3e60ff43d6bd93a2f4ea5c376182314c4d35b53fdd3
```

Identical. File size (160K) and mtime (Jul 3 16:21) were also unchanged
before and after the verifier run. `db_mutation_performed: false` was also
self-reported in the JSON.

## 12. WAL/SHM side-file check

```txt
before: paper_ledger.db-shm (32K, mtime 21:00), paper_ledger.db-wal (0 bytes, mtime 16:21)
after:  paper_ledger.db-shm (32K, mtime 21:00), paper_ledger.db-wal (0 bytes, mtime 16:21)
```

No new `-wal`/`-shm` sidecars were created by the verifier run; the
pre-existing sidecars (owned by the live prod timer process, not this
audit) were unchanged. `wal_shm_files_created: false` was also
self-reported in the JSON.

## 13. What was not done

No writer, migration, schema ensure, data refresh, timer change,
`forward_obs` mutation, or DB mutation was performed. No WAL checkpoint was
run. No dependencies were installed. No systemd/timer configuration was
touched. Only the strict read-only verifier CLI was invoked against the
prod DB via the documented immutable read-only URI contract.

## 14. Interpretation

No edge claim. No profitability claim. `EDGE_UNPROVEN` remains preserved.

The verifier did not return `CLEAN_NET_OF_CARRY`, so this audit does not
claim strict verifier-confirmed clean-carry status. Current/prod remains
`CAVEATED_ENGINE_SEMANTICS`, with the reason codes listed in section 8
(missing funding source rows across all five tracked symbols cause a
digest/coverage mismatch against the DB-linked snapshot, independent of the
snapshot's own structural validity and independent of the arithmetic re-sum
passing within tolerance).

## 15. Verdict

```txt
STRICT_READ_ONLY_PROD_VERIFIER_AUDIT_CAVEATED
```

No edge claim.
No profitability claim.
EDGE_UNPROVEN remains preserved.
No writer, migration, schema ensure, data refresh, timer change,
forward_obs mutation, or DB mutation was performed.
