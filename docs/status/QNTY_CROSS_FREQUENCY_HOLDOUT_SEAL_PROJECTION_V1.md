# Cross-frequency holdout seal projection v1

## Decision

Hourly bars and event-based funding cannot share a row-equality holdout seal:
the bars source has hourly rows while funding is sparse (roughly eight-hour)
events. `bars_timestamp_partition_projection_v1` therefore derives partition
windows from source-ordered bars and projects normalized UTC funding-event
timestamps into them. It reads only the role timestamp and preserves selected
source rows as opaque raw bytes for hashing.

## Timestamp policy

For boundary `B`, purge `P`, embargo `E`, and bars in source order, the windows
are `before_bars: t < bars[0]`, `train: bars[0] <= t < bars[B-P]`, `purge:
bars[B-P] <= t < bars[B]`, `embargo: bars[B] <= t < bars[B+E]`, `quarantine:
bars[B+E] <= t <= bars[-1]`, and `after_bars: t > bars[-1]`. Events exactly
on a boundary belong to the partition that begins there. Before/after events
are explicit non-contributing classifications. Small 28,799/28,800-second
cadence variation is harmless because assignment is timestamp-based, not
cadence-based.

## Seal and registry consequences

The two-role seal binds the projection policy, canonical roles, role-relative
source identity, selected opaque quarantine bytes, and frozen bars partition.
The current registered bars-only seal is insufficient for a bars-plus-funding
execution surface and must fail closed. A separate reviewed, post-merge
registry correction must disclose the old bars-only fingerprint
`46cde529296e9bde4a884e3ea51950474ed75667a8b9a46d632581e76cd9a2cf` and
the reviewed replacement fingerprint; this change does not modify that
registry.

Candidate 1 remains untested. This is a structural pre-execution repair, not
edge or experimental evidence, and it changes no paper or live authorization.
