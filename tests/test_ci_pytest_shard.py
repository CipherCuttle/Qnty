"""Synthetic-only checks for deterministic CI suite sharding."""
from __future__ import annotations

from types import SimpleNamespace

import pytest

from ci_pytest_shard import ShardPlugin, module_to_shard, pytest_collection_modifyitems


def test_partitions_every_module_once_and_balances_by_test_count():
    ids = (["tests/a.py::test_" + str(i) for i in range(13)]
           + ["tests/b.py::test_" + str(i) for i in range(7)]
           + ["tests/c.py::test_" + str(i) for i in range(5)]
           + ["tests/d.py::test_" + str(i) for i in range(3)]
           + ["tests/e.py::test_" + str(i) for i in range(2)])
    allocation = module_to_shard(ids, 3)
    assert set(allocation) == {"tests/a.py", "tests/b.py", "tests/c.py", "tests/d.py", "tests/e.py"}
    weights = [sum(1 for node in ids if allocation[node.split("::")[0]] == shard) for shard in range(3)]
    assert sum(weights) == len(ids)
    assert max(weights) - min(weights) <= 5
    assert allocation == module_to_shard(list(reversed(ids)), 3)


def test_shard_selection_is_disjoint_and_exhaustive(monkeypatch):
    nodeids = [f"tests/{module}.py::test_{n}" for module in "abcde" for n in range(3)]
    selected_by_shard = []
    for index in range(3):
        items = [SimpleNamespace(nodeid=x) for x in nodeids]
        deselections = []
        hook = SimpleNamespace(pytest_deselected=lambda items: deselections.extend(items))
        config = SimpleNamespace(hook=hook)
        ShardPlugin(index, 3).pytest_collection_modifyitems(None, config, items)
        selected_by_shard.append({item.nodeid for item in items})
        assert len(items) + len(deselections) == len(nodeids)
    assert set.union(*selected_by_shard) == set(nodeids)
    assert all(a.isdisjoint(b) for i, a in enumerate(selected_by_shard) for b in selected_by_shard[i+1:])


@pytest.mark.parametrize("index,count", [(-1, 4), (4, 4), (0, 0), (0, -1)])
def test_invalid_shards_fail_closed(index, count):
    with pytest.raises(ValueError):
        ShardPlugin(index, count)


def test_empty_shard_fails_closed():
    hook = SimpleNamespace(pytest_deselected=lambda items: None)
    config = SimpleNamespace(hook=hook)
    with pytest.raises(RuntimeError, match="selected no tests"):
        ShardPlugin(3, 4).pytest_collection_modifyitems(None, config, [SimpleNamespace(nodeid="tests/a.py::test_a")])


def test_plugin_env_loading_routes_to_deterministic_assignment(monkeypatch):
    monkeypatch.setenv("QNTY_CI_SHARD_INDEX", "1")
    monkeypatch.setenv("QNTY_CI_SHARD_COUNT", "2")
    ids = ["tests/a.py::test_a", "tests/b.py::test_b"]
    items = [SimpleNamespace(nodeid=x) for x in ids]
    dropped = []
    config = SimpleNamespace(hook=SimpleNamespace(pytest_deselected=lambda items: dropped.extend(items)))
    pytest_collection_modifyitems(None, config, items)
    assert len(items) == len(dropped) == 1
    assert {items[0].nodeid, dropped[0].nodeid} == set(ids)


def test_plugin_env_without_contract_fails_closed(monkeypatch):
    monkeypatch.delenv("QNTY_CI_SHARD_INDEX", raising=False)
    monkeypatch.delenv("QNTY_CI_SHARD_COUNT", raising=False)
    with pytest.raises(RuntimeError, match="missing or invalid"):
        pytest_collection_modifyitems(None, SimpleNamespace(), [])
