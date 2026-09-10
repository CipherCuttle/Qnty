# Qnty accepted execution intent publication receipt V0

Lane: `ADMIN_LANE`.

This phase adds the producer-side compatibility seam for authenticating `QNTY_ACCEPTED_EXECUTION_INTENT_V2` across the Qnty → QntySpot repository boundary.

## What Qnty does

Qnty validates an already-produced V2 accepted-intent artifact, preserves its exact canonical bytes, and derives a domain-separated publication body containing:

- exact artifact SHA-256
- V2 `intent_digest`
- Qnty repository identity and repository commit
- publication epoch and serial
- publication timestamp
- publication root id and public-key fingerprint
- V2 schema name/version
- publication-only purpose and Ed25519 algorithm identifier

`publication_body_bytes_v0(...)` returns the exact canonical bytes an external publication signer must sign.

Qnty then accepts an externally supplied 64-byte signature and assembles a deterministic canonical receipt. Receipt persistence is write-once and idempotent; its sidecar is the SHA-256 of the exact receipt bytes.

## What Qnty does not do

This repository does not:

- contain or generate a publication private key
- expose a signer callback
- call a KMS/HSM or network signer
- read signer material from environment variables
- reuse a wallet or transaction-signing key
- change H003 acceptance or V2 research semantics
- recompute research
- change Qnty protocol control state
- grant paper/shadow/live authorization
- grant policy, venue, network, signing, submission, execution, or capital authority

A malformed or incorrect externally supplied signature can be assembled structurally, but it will fail cryptographic verification at the QntySpot verifier. This producer seam intentionally does not add a new cryptography dependency merely to duplicate the downstream verification boundary.

## Compatibility vector

`tests/fixtures/QNTY_ACCEPTED_EXECUTION_INTENT_PUBLICATION_RECEIPT_V0.json` is a producer-authored interoperability fixture assembled from the canonical V2 publication artifact and a fixed signature generated outside Qnty.

It is **test verification material only**. It is deliberately stored under `tests/fixtures`, not the canonical artifact plane, and its public-key fingerprint is not a production trust root.

The fixed vector binds Qnty commit:

`2ebed2af94127f2e018de46069d1bbe27178ca8a`

and the canonical V2 artifact file SHA-256:

`262f2eeea5c7fea979f1500538ffd146686e9c4ac8069a1ac5ae4d3ae7cd76db`

## Production provisioning boundary

A production deployment still needs an operator-owned, publication-only Ed25519 key and an out-of-repository signing mechanism. That key must be distinct from all economic authority, wallet, transaction-signing, and execution keys.

The production signer receives only the canonical publication body bytes and returns only a 64-byte signature. Qnty may assemble the resulting receipt; QntySpot independently authenticates it against explicitly provisioned public trust material.

No production secret or live authority is introduced by this phase.
