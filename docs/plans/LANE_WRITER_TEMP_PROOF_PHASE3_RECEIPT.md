# Lane Writer Temp Proof — Phase 3 Receipt

**First non-production writer proof.** This records the first time an *actual*
`qnty-paper-sqlite-accounting.py` writer invocation committed a batch into a NEW-lane
SQLite ledger and stamped `ledger_batches.lane_id`. Until now the lane stamping path had
only been exercised by direct `_insert_ledger_batch` unit tests and mocked-loader tests —
never by a real `run_sqlite_accounting` run.

> **SIMULATION-support tooling only.** No profitability or edge claim is made. The strategy
> edge remains **EDGE_UNPROVEN**. This is a throwaway `/tmp` lane: no production, no live
> lane, no real shadow lane.

---

## What was proven

1. The writer can run against a **temp lane output dir + temp lane DB**.
2. `ledger_batches.lane_id` is stamped by an **actual writer invocation** to
   `temp_lane_writer_proof_v0`.
3. The read-only verifier **accepts** the resulting lane DB (status `OK`, 0 failures),
   including the lane/batch consistency rule.

---

## Temp path

All artifacts confined to `/tmp/qnty_lane_writer_proof_v0`:

```
/tmp/qnty_lane_writer_proof_v0/
  lane_out/                       # QNTY_PAPER_OUTPUT_DIR (+ paper_ledger.db, sidecars)
  forward_obs_fixture/            # synthetic observation_log.json
  data_fixture/                   # MANDATORY --data-dir (empty: null book needs no CSVs)
  logs/                           # writer/verifier/init/db-inspection captures
```

No path under `/srv/qnty` was read or written (`/srv/qnty` is absent on this dev box).

---

## Lane identity

| field              | value                       |
|--------------------|-----------------------------|
| `lane_id`          | `temp_lane_writer_proof_v0` |
| `strategy_id`      | `matched_null_shadow_v0`    |
| `strategy_version` | `0.0.0-temp`                |
| `config_hash` (v1) | `65e5b9cfd0056fdacfb0c5fb9fe8ef46e8070249da239865585ab24d07096d3d` |
| `config_hash_v2`   | `5e606d994f653c9cd83a8409c3268823a4551e4a16175cb99f05baef9f720503` |
| `pre_registration_hash` | `null` (unchanged sidecar behavior; no generation implemented) |

---

## Chosen timestamps (UTC, on the 8h grid)

| field              | value                 | note                                  |
|--------------------|-----------------------|---------------------------------------|
| `forward_start_ts` | `2026-06-25T00:00:00` | one 8h interval before the obs bar    |
| obs bar timestamp  | `2026-06-25T08:00:00` | latest closed 8h boundary; fresh      |

Run wall-clock (UTC) was ~`2026-06-25T13:06`, so the obs bar was ~5h old — within the
freshness window and strictly after `forward_start_ts` ⇒ eligible.

---

## Fixture source (synthetic, non-production)

- **observation_log.json** (`forward_obs_fixture/`): one `per_bar_obs` entry,
  `active_symbols: []` (matched-null book), `portfolio_heat=0.0`,
  `heat_cap_triggered=false`, `weighted_return=0.0`, `timestamp=2026-06-25T08:00:00`.
- **market data** (`data_fixture/`): intentionally **empty**. With an empty active-symbol
  set the engine references no symbol bars/funding, and both loaders
  (`load_all_ohlcv` / `load_all_funding`) skip missing CSVs gracefully. `--data-dir` was
  still passed explicitly so the loaders could never fall back to a default data path.
  CSV schema is known (`{SYMBOL}_8h_ohlcv.csv`, `{SYMBOL}_8h_funding.csv`) but no CSVs were
  needed for the null book.

---

## Command shape (exactly one writer invocation)

```bash
# init (writer NOT run)
python scripts/qnty-paper-lane-init.py \
  --output-dir /tmp/qnty_lane_writer_proof_v0/lane_out \
  --db-path /tmp/qnty_lane_writer_proof_v0/lane_out/paper_ledger.db \
  --lane-id temp_lane_writer_proof_v0 \
  --strategy-id matched_null_shadow_v0 \
  --strategy-version 0.0.0-temp \
  --forward-start-ts 2026-06-25T00:00:00

# single writer invocation
QNTY_PAPER_OUTPUT_DIR=/tmp/qnty_lane_writer_proof_v0/lane_out \
QNTY_PAPER_DB_PATH=/tmp/qnty_lane_writer_proof_v0/lane_out/paper_ledger.db \
python scripts/qnty-paper-sqlite-accounting.py \
  --db-path /tmp/qnty_lane_writer_proof_v0/lane_out/paper_ledger.db \
  --forward-obs-dir /tmp/qnty_lane_writer_proof_v0/forward_obs_fixture \
  --data-dir /tmp/qnty_lane_writer_proof_v0/data_fixture \
  --json

# read-only verifier
python scripts/qnty-paper-sqlite-verify.py \
  --db-path /tmp/qnty_lane_writer_proof_v0/lane_out/paper_ledger.db \
  --no-emit --json
```

---

## Writer status / exit code

- exit code: **0** (OK)
- status_message: `Committed batch 1: 1 bars, 3 events`
- **Run exactly once. No rerun.**

## Verifier status / exit code

- exit code: **0**, status: **OK**, `failure_count`: 0
- `batches`: 1, `events`: 3, `equity_rows`: 1
- `funding_coverage.decision`: `not_required` (`CLEAN_NET_OF_CARRY`)
- `git_provenance`: every batch provenanced; `latest_batch_git_sha`
  `cb95ff9a0235ac99c8537b7ca7712ba3e2630eeb`; none missing
- `watermark_bar_ts`: `2026-06-25T08:00:00`
- (`--no-emit`: pure read-only check; nothing written to the DB or disk.)

---

## DB row counts (read-only inspection)

| table              | count |
|--------------------|-------|
| `ledger_batches`   | 1     |
| `ledger_events`    | 3     |
| `signal_snapshots` | 1     |
| `equity_snapshots` | 1     |
| `fills`            | 0     |
| `trades`           | 0     |
| `funding`          | 0     |
| `open_positions`   | 0     |

Null book ⇒ zero fills/trades/funding; one equity + one signal snapshot, as expected.

## Per-batch `lane_id` values

| batch_id | lane_id                     | committed_at          | event_count | git_sha    |
|----------|-----------------------------|-----------------------|-------------|------------|
| 1        | `temp_lane_writer_proof_v0` | `2026-06-25T13:06:14Z`| 3           | `cb95ff9…` |

`paper_config.lane_id` = `temp_lane_writer_proof_v0` — matches every committed batch.

---

## Guarantees

- **No rerun** — exactly one writer invocation.
- **No production mutation** — all paths under `/tmp/qnty_lane_writer_proof_v0`; nothing
  under `/srv/qnty`; production `paper_pnl_v1` untouched.
- **No live/shadow lane** — no real shadow output dir; no VM/SSH; no systemd/timers; no
  migrations/ALTER; no live exchange keys; no real orders.
- **No new mechanisms implemented** — no `source_data_digest`; no
  `pre_registration_hash` generation beyond the existing `null` sidecar; no V2; no
  cross-lane reporter.
- Strategy label: **EDGE_UNPROVEN**.
