"""Deterministic, module-atomic pytest sharding for GitHub's full suite.

All jobs collect the complete suite, then partition it by test-module count.
No pytest temp-root overrides, test exclusions, or external plugins.
"""
from __future__ import annotations

import argparse
import os
from collections import Counter
from collections.abc import Iterable


def module_to_shard(nodeids: Iterable[str], shard_count: int) -> dict[str, int]:
    """Balance test modules by number of collected cases, deterministically."""
    if shard_count < 1:
        raise ValueError("shard_count must be positive")
    counts = Counter(nodeid.split("::", 1)[0] for nodeid in nodeids)
    sizes = [0] * shard_count
    assignments = {}
    for module, count in sorted(counts.items(), key=lambda p: (-p[1], p[0])):
        shard = min(range(shard_count), key=lambda index: (sizes[index], index))
        assignments[module] = shard
        sizes[shard] += count
    return assignments


class ShardPlugin:
    def __init__(self, index: int, count: int) -> None:
        if not 0 <= index < count:
            raise ValueError("shard index out of range")
        self.index, self.count = index, count

    def pytest_collection_modifyitems(self, session, config, items) -> None:
        # Keep module-level fixtures and test-order dependencies in one job.
        assignments = module_to_shard((item.nodeid for item in items), self.count)
        selected = [item for item in items if assignments[item.nodeid.split("::", 1)[0]] == self.index]
        deselected = [item for item in items if assignments[item.nodeid.split("::", 1)[0]] != self.index]
        if not selected:
            raise RuntimeError(f"shard {self.index} selected no tests")
        if deselected:
            config.hook.pytest_deselected(items=deselected)
        items[:] = selected
        print(f"QNTY_SHARD={self.index}/{self.count}: selected {len(selected)} of {len(selected) + len(deselected)} tests across {sum(value == self.index for value in assignments.values())} modules", flush=True)


def pytest_collection_modifyitems(session, config, items) -> None:
    """Entry point when CI loads this module via PYTEST_ADDOPTS=-p."""
    try:
        index = int(os.environ["QNTY_CI_SHARD_INDEX"])
        count = int(os.environ["QNTY_CI_SHARD_COUNT"])
    except (KeyError, ValueError) as exc:
        raise RuntimeError("missing or invalid QNTY CI shard environment") from exc
    ShardPlugin(index, count).pytest_collection_modifyitems(session, config, items)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--index", type=int, required=True)
    parser.add_argument("--count", type=int, required=True)
    args = parser.parse_args()
    plugin = ShardPlugin(args.index, args.count)
    import pytest
    return int(pytest.main(["-q"], plugins=[plugin]))


if __name__ == "__main__":
    raise SystemExit(main())
