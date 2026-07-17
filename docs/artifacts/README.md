# QNTY durable artifact plane (v1)

Provider-neutral, content-addressed identity and verification for frozen
research inputs. This directory holds the **Git-owned** registry:

- `<artifact_id>.json` — one artifact record per frozen input (canonical
  QNTY JSON bytes, no trailing newline).
- `stores.json` — the provider-neutral store registry (committed empty until
  an operator configures real stores; no credentials, tokens, secret URLs,
  cloud keys, private hostnames, or user-specific absolute roots are ever
  committed).

Code lives in `quantbot/artifacts/` (pure stdlib). CLI:

```bash
.venv/bin/python -m quantbot.artifacts manifest --artifact-id ID --role bars=DIR --role funding=DIR --out FILE
.venv/bin/python -m quantbot.artifacts ingest --manifest FILE --role bars=DIR ... --store-root DIR
.venv/bin/python -m quantbot.artifacts verify-copy --manifest-sha SHA --store-root DIR
.venv/bin/python -m quantbot.artifacts restore --manifest-sha SHA --store-root DIR --dest DIR
.venv/bin/python -m quantbot.artifacts verify-registry
.venv/bin/python -m quantbot.artifacts status
```

## Identity contract

- **Portable content identity**: the portable artifact manifest v1
  (`qnty_portable_artifact_manifest`). Per file it records exactly `role`,
  `relative_path`, `size_bytes`, `sha256`, deterministically ordered by
  `(role, relative_path)`. The manifest SHA-256 is computed over the exact
  canonical manifest bytes (UTF-8, sorted keys, `separators=(",", ":")`,
  ASCII, no trailing newline). The hash domain contains **no** source root,
  absolute path, machine name, timestamp, uid, gid, inode, mtime, or storage
  location: the same role trees under two different roots hash identically.
- **Legacy protocol identities**: the historical fingerprints recorded under
  `legacy_bindings` (for `candidate1-real-input-v0`: the path-sensitive
  input-manifest fingerprint `3dec9941…`, the outer data-cut fingerprint
  `020eac5e…`, and the nested first-statistic data binding `7c8552f1…`).
  These mix resolved absolute paths or protocol context into their hash
  domain. They are **historical and immutable**, they are **not** portable
  artifact content digests, and they must never be overwritten,
  reinterpreted, or silently replaced. `HASHED DOES NOT MEAN PRESERVED`: a
  recorded fingerprint proves what the bytes were, not that any copy of the
  bytes still exists.

## Storage contract

- Content-addressed store layout:
  `objects/sha256/<2-hex>/<file-sha256>` and
  `manifests/sha256/<2-hex>/<manifest-sha256>.json`.
- Writes are atomic (temp file + `os.replace` + fsync); every ingest verifies
  all bytes (hash-while-copy plus independent read-back rehash) before
  reporting success; an existing exact object is idempotent; an existing
  mismatched object fails closed; symlinks are never followed.
- Canonical artifact copy locations are stable store URIs:
  `qnty-artifact://<store-id>/sha256/<manifest-sha256>` — never ephemeral
  materialization paths. `/tmp` is a workspace, `/srv/qnty` is production;
  **neither is ever canonical storage** and neither can back a durable copy.
  A temporary restore/materialization directory is a workspace, not an
  artifact location, even when a future bounded recovery task is explicitly
  authorized to use one.
- Store contract fields (per configured store): `store_id`, `backend_kind`,
  `failure_domain`, `root_environment_variable` (the *name* of the
  environment variable an operator sets to the store root — never the root
  itself), `read_enabled`, `write_enabled`. Backends remain replaceable;
  this plane provides the QNTY scientific identity and verification layer,
  not a cloud-vendor dependency.

## Availability contract (two-copy, fail-closed)

`VERIFIED_AVAILABLE` requires, enforced by `quantbot.artifacts.registry` and
cross-checked by `quantbot.continuity`:

- a bound `portable_manifest_sha256`;
- at least two copy records with unique `store_id` values, unique canonical
  locations, and **at least two distinct `failure_domain` values** (two
  directories on the same disk or in the same failure domain never qualify);
- every copy referencing the same portable manifest;
- every copy having passed full object verification (complete rehash, not a
  metadata-only existence check);
- every copy having passed an independent restore test whose recomputed
  portable manifest matched exactly.

Anything less is `UNAVAILABLE`: zero copies, no canonical locations, and a
`null` portable manifest until real bytes are ingested and verified under an
explicitly authorized task.

## Continuity cross-binding

The active handoff receipt's `required_artifacts` summary must agree with the
artifact records here (identity, legacy fingerprint, availability, copy
count, canonical locations), and the active receipt's `evidence` must pin the
exact record bytes by SHA-256. `python -m quantbot.continuity verify` fails
closed on any divergence. Every agent resolves artifacts through these
Git-owned records — never through chat history, `/tmp`, or a single machine.
