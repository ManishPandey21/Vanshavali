"""The bidirectional relationship search returns a valid shortest path (checked against plain BFS)."""

from __future__ import annotations

import random
import uuid
from collections import deque
from itertools import pairwise

from app.models.enums import RelationshipType
from app.modules.genealogy.engine import _bfs_path, _Edge, _LazyAdjacency


class _StubGraph:
    """Everything already 'loaded': exercises the search without a database."""

    def __init__(self) -> None:
        self.loaded: set[uuid.UUID] = set()

    def prefetch(self, ids: object) -> None:
        return None


def _graph(n: int, edges: int, rng: random.Random):  # type: ignore[no-untyped-def]
    nodes = [uuid.UUID(int=i + 1) for i in range(n)]
    stub = _StubGraph()
    stub.loaded.update(nodes)
    par: dict = {}
    chi: dict = {}
    spo: dict = {}
    adj: dict[uuid.UUID, set[uuid.UUID]] = {x: set() for x in nodes}
    for _ in range(edges):
        a, b = rng.sample(nodes, 2)
        e = _Edge(uuid.uuid4(), a, b, RelationshipType.BIOLOGICAL_PARENT, None)
        if rng.random() < 0.8:
            par.setdefault(b, []).append((a, e))
            chi.setdefault(a, []).append((b, e))
        else:
            spo.setdefault(a, []).append((b, e))
            spo.setdefault(b, []).append((a, e))
        adj[a].add(b)
        adj[b].add(a)
    views = tuple(_LazyAdjacency(stub, d) for d in (par, chi, spo))  # type: ignore[arg-type]
    return nodes, adj, views


def _reference_distance(adj: dict[uuid.UUID, set[uuid.UUID]], a: uuid.UUID, b: uuid.UUID) -> int | None:
    dist = {a: 0}
    q = deque([a])
    while q:
        cur = q.popleft()
        for n in adj[cur]:
            if n not in dist:
                dist[n] = dist[cur] + 1
                q.append(n)
    return dist.get(b)


def test_bidirectional_search_matches_plain_bfs_on_random_graphs():
    rng = random.Random(20260925)
    for trial in range(300):
        n = rng.randint(2, 60)
        nodes, adj, (par, chi, spo) = _graph(n, rng.randint(0, n * 2), rng)
        a, b = rng.choice(nodes), rng.choice(nodes)
        path = _bfs_path(a, b, par, chi, spo)
        expected = _reference_distance(adj, a, b)
        if expected is None:
            assert path == [], trial
            continue
        assert path[0] == a and path[-1] == b, trial
        assert len(path) - 1 == expected, (trial, path, expected)
        assert all(y in adj[x] for x, y in pairwise(path)), trial
        assert len(set(path)) == len(path), trial
