# QNTY Funding Source Immutable Source Bundle Semantics Plan

## Status Boundary

- `EDGE_UNPROVEN` remains.
- `BLOCK_LIVE_INTEGRATION` remains.
- This is a plan only. It is docs-only.
- This plan changes no code, tests, schema, verifier, reporter, or writer.
- This plan authorizes no DB mutation, writer run, trader run, live
  integration, deployment, backfill, official report overwrite, source CSV
  mutation, or service/timer/cron/systemd mutation.
- This plan does not prove edge, profitability, statistical significance,
  shorting readiness, live readiness, or production deployment.
- `clean` / `CLEAN_NET_OF_CARRY` means "not killed by this verifier gate" —
  never an edge, profitability, or live-approval signal.

## Why This Plan Exists

- **PR #101** — real shadow DB recommit succeeded and the full-ledger path
  reached `CLEAN_NET_OF_CARRY` (not killed by the carry gate; still
  `EDGE_UNPROVEN`).
- **PR #103** — official report promotion was **blocked** because the funding
  source CSVs drifted before the candidate verifier ran.
- **PR #104** — diagnosis proved the root cause: the `qnty-data-refresh.timer`
  `16:05 UTC` slot rewrote all ten `/srv/qnty/repo/data/*_8h_funding.csv`
  files (via `scripts/fetch_funding_rest.py`, between `16:06:23Z` and
  `16:07:25Z`) — after the PR #103 promotion backup (`16:05:26Z`) but before
  the PR #103 candidate verifier (`16:08:09Z`). The verifier read drifted
  source digests and correctly raised `funding_source_file_digest_mismatch`,
  refusing promotion. This is expected, non-anomalous automated behavior; the
  verifier opens funding CSVs read-only and cannot mutate them.
- Diagnosis verdict:
  `FUNDING_SOURCE_CSV_DRIFT_DIAGNOSIS_RECORDED_SOURCE_REFRESH_ACTIVE`.
- **Design flaw:** the verifier validates a *historical, DB-linked* funding
  snapshot against *live, mutable* CSVs. Any fresh verifier run can therefore
  flip a previously clean, correctly recorded ledger to
  `funding_source_file_digest_mismatch` the moment a scheduled refresh lands —
  even when nothing about the recorded evidence is wrong. The evidence is
  frozen; the thing it is checked against is not.

## Problem Statement

1. **Live CSV resolution races scheduled refresh.** The verifier resolves
   funding rows and per-file digests from `/srv/qnty/repo/data/*_8h_funding.csv`
   at run time. Those files are rewritten on a schedule
   (`qnty-data-refresh.timer`). A verifier run and a refresh are concurrent,
   independent events with no lock or barrier between them, so a verifier run
   that starts after a refresh sees bytes that differ from the ones the
   DB-linked snapshot was committed against.
2. **PR #104 proves the race is active and expected.** The `16:05 UTC` refresh
   slot demonstrably fired and rewrote all ten funding CSVs inside the PR #103
   promotion window. This is not a rare or anomalous condition — it recurs on
   every scheduled slot and will recur on future promotion attempts.
3. **Source-freeze is only a stopgap.** Pausing/masking the refresh timer
   around a promotion narrows the race window but does not remove it: it
   depends on manual timing, on the timer staying masked, and on no
   out-of-band refresh. It also degrades data currency for other consumers.
   It is an emergency measure, not a durable contract.
4. **Immutable bundle semantics are the durable fix.** If the DB-linked
   funding snapshot points at an *immutable, content-addressed source bundle*
   captured at commit time, the verifier can validate against frozen bytes
   whose digest can never go stale, and scheduled refresh of the live CSVs
   becomes irrelevant to the recorded evidence. This is the design this plan
   specifies (planned, not implemented).

## 1. Proposed Verifier Contract

- A DB-linked funding snapshot **points to an immutable source bundle**
  (content-addressed by hash) captured at snapshot-commit time. The bundle is
  the authoritative "source of truth" bytes for that snapshot.
- When a bundle is **present and valid**, the verifier resolves funding rows
  and digests **from the pinned bundle**, not from the live CSVs under
  `/srv/qnty/repo/data`. Scheduled refresh of the live CSVs then has no effect
  on the verdict.
- **Live CSV validation remains available**, but only as an explicit,
  opt-in **current-source mode** (`--source-mode=live-current` or equivalent).
  It is not the default when a valid bundle is present.
- **Two distinct modes, never silently mixed:**
  - `bundle` — resolve from the pinned immutable bundle (durable evidence
    mode; default when a valid bundle is present).
  - `live-current` — resolve from live CSVs (drift-detection mode; must still
    detect current CSV drift, as today).
- The report output **must expose `source_resolution_mode`** (one of
  `bundle` / `live-current`) plus the identity of the source materials it
  actually used (bundle hash + path, or live CSV paths + digests). A reader
  must be able to tell from the report alone which bytes were validated.
- Bundle mode must **not** weaken any existing check: coverage/window,
  per-symbol presence, row counts, canonical ordering, arithmetic, and funding
  re-sum all still apply — they are simply computed over the pinned bytes.

## 2. Snapshot / Bundle Schema Options

The bundle binds a set of canonical funding rows to a hash and to the
DB-linked snapshot. Two layout options (decision deferred to the spec PR):

- **Option A — embedded canonical rows.** The canonical rows are serialized
  directly inside the snapshot/bundle envelope. Simplest to verify (single
  object, single hash); larger envelope; good for modest row counts.
- **Option B — external immutable row chunks.** The bundle envelope holds
  metadata + hashes; canonical rows live in separate content-addressed,
  read-only chunk files referenced by hash. Smaller envelope, de-duplicable
  across batches/snapshots; requires chunk-presence and per-chunk hash checks.

Regardless of layout, the bundle **must carry**:

- **Required hashes:** per-file / per-chunk `sha256`, a `source_bundle_sha256`
  over the canonical serialization, and the **original source digests** of the
  live CSVs as they were at capture time (so drift against original source is
  auditable).
- **Row counts:** total and per symbol.
- **Windows:** overall `window_start`/`window_end` and, where applicable, per
  symbol; sufficient to prove full-ledger funding-window coverage.
- **Symbols:** the exact symbol set covered (e.g. the ten
  `*_8h_funding` instruments).
- **Canonical serialization:** an explicit, versioned serialization spec
  (field order, numeric formatting, encoding, line endings) so that
  recomputing `source_bundle_sha256` over the rows is deterministic.
- **Deterministic ordering:** a defined total order for rows (e.g. by symbol
  then `window_start`) so serialization is reproducible byte-for-byte.
- **Bundle path/hash binding:** the DB-linked snapshot stores both the bundle
  path and the bundle hash; the verifier checks that the file at the path
  hashes to the recorded value (path and hash must agree).

The bundle format must be **versioned** so future canonicalization changes are
explicit and old bundles remain interpretable.

## 3. Acceptance / Refusal Rules

**Bundle mode — accept (`clean`, meaning not killed by this gate) only if all hold:**

- bundle present at the recorded path;
- bundle **path and hash agree** (file hashes to recorded `source_bundle_sha256`);
- bundle **schema/version** valid and parseable;
- **coverage/window** complete (spans the full-ledger funding window; no gaps);
- symbol set matches expectation;
- row counts match recorded counts;
- **funding re-sum** over bundle rows matches the ledger funding re-sum.

**Bundle mode — refuse if any hold:**

- bundle **missing**;
- bundle **corrupt** / unparseable / schema-invalid;
- bundle **hash mismatch** (path/hash disagree, or `source_bundle_sha256`
  does not recompute);
- **coverage/window incomplete** (window does not cover the ledger, or gaps);
- **funding re-sum mismatch** between bundle rows and ledger funding.

**When only live CSVs are available (no bundle):**

- the verifier runs in `live-current` mode and emits an explicit **caveat**
  (evidence is not frozen; result may flip on scheduled refresh);
- `live-current` mode **must still detect current CSV drift** — i.e. if the
  live CSVs differ from the DB-linked recorded digests, it still raises
  `funding_source_file_digest_mismatch` exactly as today. Bundle mode must not
  be used to *hide* live drift; it is a separate, explicitly labeled path.

`source_resolution_mode` is recorded in the report in every case.

## 4. Test Plan

All tests operate on copied/`/tmp` DBs and synthetic/fixture bundles; **no
real DB, no official report, no live CSV, no service is touched.**

1. **Live CSV drift after bundle creation does not break bundle-mode
   verifier:** create a valid bundle, then mutate the (fixture) live CSVs;
   bundle-mode verifier still reads `clean` from the frozen bundle.
2. **Corrupt bundle refuses:** truncated/garbled bundle → refuse.
3. **Missing bundle refuses:** recorded bundle path absent → refuse (in bundle
   mode).
4. **Hash mismatch refuses:** bundle bytes altered so recorded hash no longer
   recomputes → refuse.
5. **Incomplete window refuses:** bundle covers less than the full-ledger
   funding window → refuse with window-coverage reason.
6. **Live mode still detects current CSV drift:** in `live-current` mode with
   drifted CSVs → still raises `funding_source_file_digest_mismatch`.
7. **Report output records source materials and resolution mode:** report
   exposes `source_resolution_mode` and the exact source identity (bundle
   hash+path, or live CSV paths+digests) for both modes.
8. **Funding re-sum mismatch refuses:** bundle rows whose funding re-sum
   disagrees with the ledger → refuse.

## 5. Migration Plan

Strict ordering; each step gated on the previous:

1. **Plan-only first** — this document (docs-only, no code/tests/schema).
2. **Tests/spec PR second** — canonical serialization spec + acceptance/refusal
   tests + schema spec. Tests may be written before implementation (spec-first).
3. **Implementation PR third** — writer captures the immutable bundle at
   commit time; verifier resolves from bundle when present and valid; report
   exposes `source_resolution_mode`. Additive/nullable schema only; old DBs
   without bundle references remain readable and fall back to `live-current`
   with caveat.
4. **Copied DB dry run** — before any real report promotion, apply and verify
   bundle-mode on a **copied** shadow DB in `/tmp`; prove the gate clears on a
   DB-linked path with **no** real DB mutation.
5. **No official report promotion until the verifier tests pass.**
6. **Real report promotion only after immutable bundle mode is proven** on the
   copied-DB dry run and under explicit approval.
7. **Source-freeze allowed only as an emergency stopgap**, never as the durable
   design; the durable design is immutable bundle semantics.

## 6. Stop Conditions

Halt and report (do not proceed / do not guess) on any of:

- **Ambiguity in funding semantics** — unclear window boundaries, symbol set,
  re-sum definition, or canonical serialization.
- **Accidental DB / report / source mutation** — any write to a real DB,
  official report, or live CSV, or to any service/timer.
- **Mismatch between bundle rows and ledger funding re-sum.**
- **Any attempt to weaken `EDGE_UNPROVEN` or `BLOCK_LIVE_INTEGRATION`.**
- **Any attempt to treat clean-carry as edge / profit / live approval.**

## 7. Non-Goals

- No edge, profitability, or significance claim.
- No live integration, deployment, backfill, writer/trader run.
- No change to what `CLEAN_NET_OF_CARRY` means.
- No mutation of any real DB, official report, live CSV, or service.

## 8. Verdict

- `FUNDING_SOURCE_IMMUTABLE_SOURCE_BUNDLE_SEMANTICS_PLAN_RECORDED` — this
  docs-only plan is complete, internally consistent, and diff-verified
  docs-only.
- `FUNDING_SOURCE_IMMUTABLE_SOURCE_BUNDLE_SEMANTICS_PLAN_BLOCKED` — a stop
  condition fired or the plan could not be recorded docs-only.

**Verdict:** `FUNDING_SOURCE_IMMUTABLE_SOURCE_BUNDLE_SEMANTICS_PLAN_RECORDED`
