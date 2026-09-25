"""Every tree-scoped route rejects non-members without revealing existence (ADR-0006, IDOR/BOLA)."""

from __future__ import annotations

import re
import uuid

from app.main import create_app


def _tree_routes() -> list[tuple[str, str]]:
    spec = create_app().openapi()
    out = []
    for path, ops in spec["paths"].items():
        if "{tree_id}" not in path:
            continue
        for method in ops:
            if method in ("get", "post", "put", "patch", "delete"):
                out.append((method.upper(), path))
    return out


def test_all_tree_routes_hide_trees_from_strangers(owner, tree, make_client):
    stranger = make_client()
    stranger.register()
    routes = _tree_routes()
    assert len(routes) > 40
    failures = []
    for method, path in routes:
        url = path.replace("/api/v1", "").replace("{tree_id}", tree["id"])
        url = re.sub(r"\{[a-z_]+\}", str(uuid.uuid4()), url)
        kw = {"json": {}} if method in ("POST", "PUT", "PATCH") else {}
        r = stranger.request(method, url, **kw)
        # 404 = not found; 422 = request shape rejected before any data access. Never 2xx/403/500.
        if r.status_code not in (404, 422):
            failures.append((method, path, r.status_code))
        if r.status_code == 422:
            assert "Iyer Family" not in r.text
    assert failures == []


def test_anonymous_requests_rejected_everywhere(tree, make_client):
    anon = make_client()
    failures = []
    for method, path in _tree_routes():
        url = re.sub(
            r"\{[a-z_]+\}", str(uuid.uuid4()), path.replace("/api/v1", "").replace("{tree_id}", tree["id"])
        )
        r = anon.request(method, url, **({"json": {}} if method in ("POST", "PUT", "PATCH") else {}))
        if r.status_code not in (401, 422):
            failures.append((method, path, r.status_code))
    assert failures == []
