"""Parallelism planner — dependency graph before agents are spawned.

docs/superpowers/specs/new-lola-cognitive-mesh-controls.md, Module E.

Build the dependency structure first, then decide the execution order:
items in the same wave run in parallel; waves are strictly sequential.
A dependency cycle is a hard error (fail-closed) — it is never
silently linearized, because that would hide a broken decomposition.
"""
from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass, field
from typing import Any, Sequence


@dataclass(frozen=True)
class ParallelPlan:
    waves: tuple                    # tuple[list[str], ...]; wave i before wave i+1
    is_parallel: bool               # any wave with >= 2 items
    order: tuple                    # deterministic flattened execution order

def plan_parallelism(
    nodes: Sequence[str],
    edges: Sequence[tuple],
) -> ParallelPlan:
    """Kahn's algorithm in waves.

    nodes: item ids (unique, order preserved for determinism)
    edges: (upstream, downstream) — upstream must finish before downstream
    """
    if len(set(nodes)) != len(nodes):
        raise ValueError("duplicate node id")
    node_list = list(nodes)
    node_set = set(node_list)
    for u, d in edges:
        if u not in node_set or d not in node_set:
            raise ValueError("edge references unknown node")
    indeg = {n: 0 for n in node_list}
    adj: dict = defaultdict(list)
    for u, d in edges:
        adj[u].append(d)
        indeg[d] += 1
    waves = []
    ready = [n for n in node_list if indeg[n] == 0]
    placed = set()
    while ready:
        waves.append(list(ready))
        placed.update(ready)
        nxt = []
        for n in ready:
            for d in adj.get(n, ()):
                indeg[d] -= 1
                if indeg[d] == 0 and d not in placed:
                    nxt.append(d)
        # keep node-list order for determinism
        order_idx = {n: i for i, n in enumerate(node_list)}
        ready = sorted(set(nxt), key=lambda n: order_idx[n])
    if len(placed) != len(node_list):
        raise ValueError("dependency cycle detected")
    flat = tuple(n for w in waves for n in w)
    return ParallelPlan(
        waves=tuple(w for w in waves),
        is_parallel=any(len(w) >= 2 for w in waves),
        order=flat,
    )
