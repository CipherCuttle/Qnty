# Partition-Use Quarantine Policy v0

`holdout_open_gate_state` remains a structural attestation. Its closed
vocabulary remains `blocked`, `mismatch`, and `gate_passed`; `gate_passed`
is necessary but not sufficient for any scientific use and is not trading,
paper, or live authorization.

Scientific eligibility is represented separately by `partition_use_policy_v0`.
v0 supports `quarantine_only` only. The declaration is registry-metadata-only,
canonical-fingerprinted, exact-schema-closed, and fails closed when it is
absent, malformed, unknown, not preregistered, or changed without a matching
fingerprint. It never reads bars, funding, train, purge, embargo, or holdout
rows, and it cannot invoke a scorer.

The current real BTC protocol need is `quarantine_only` because final-row
economic values were displayed before a split boundary was frozen. The v0
declaration binds the future-confirmatory cutoff `2026-04-23T01:00:00Z` for
that future real declaration, but does not authorize confirmatory use. This
memo does not amend the real registry or choose a boundary.

Confirmatory eligibility is intentionally deferred to a separately reviewed
protocol. That protocol must verify a genuinely new data cut, actual temporal
bounds after the quarantine cutoff, an actual prior quarantine declaration in
the authoritative registry, prior policy-fingerprint lineage, declaration
before confirmatory evaluation, and no same-cut reclassification. A matching
fingerprint in one registry snapshot proves declaration consistency only; it
does not independently prove append-only history. Historical mutation
detection remains a git and registry-review responsibility.

Structural `gate_passed` remains necessary but insufficient for scientific use.
No Candidate 1 result or statistic value T has been observed. Paper trading and
live integration remain false.
