"""Public site impact counters: never inspect or expose tree contents."""
from __future__ import annotations

from unittest.mock import patch

from tests.conftest import new_tree


def test_public_impact_counts_active_trees_without_names(client, owner):
    first = client.get("/public/site-impact")
    assert first.status_code == 200
    assert first.json() == {"family_trees": 0, "unique_visitors_30d": None}
    a = new_tree(owner, "Private Example Family")
    new_tree(owner, "Second Private Family")
    counted = client.get("/public/site-impact")
    assert counted.status_code == 200
    assert counted.json()["family_trees"] == 2
    assert "Private Example Family" not in counted.text
    assert "Second Private Family" not in counted.text
    deleted = owner.delete(f"/trees/{a['id']}")
    assert deleted.status_code == 200
    assert client.get("/public/site-impact").json()["family_trees"] == 1


class FakeRedis:
    def __init__(self):
        self.days = {}

    def pipeline(self):
        return self

    def pfadd(self, key, value):
        self.days.setdefault(key, set()).add(value)
        return self

    def expire(self, key, seconds):
        return self

    def execute(self):
        return []

    def pfcount(self, *keys):
        return len(set().union(*(self.days.get(key, set()) for key in keys)))


def test_visitor_cookie_deduplicates_browser_and_does_not_expose_id(client, monkeypatch):
    from app.modules.public import site_impact as module

    monkeypatch.setattr(module, "_redis_client", lambda: FakeRedis())
    with patch.object(module, "get_settings", wraps=module.get_settings) as settings:
        settings.return_value = settings.return_value.model_copy(
            update={"visitor_stats_enabled": True}
        )
        first = client.get("/public/site-impact")
        assert first.status_code == 200
        assert first.json()["unique_visitors_30d"] == 1
        assert "vsh_impact_visitor" in first.headers["set-cookie"]
        second = client.get("/public/site-impact")
        assert second.json()["unique_visitors_30d"] == 1


def test_visitor_service_failure_does_not_falsely_show_zero(client, monkeypatch):
    from app.modules.public import site_impact as module
    import redis

    def broken():
        raise redis.RedisError("simulated outage")

    monkeypatch.setattr(module, "_redis_client", broken)
    with patch.object(module, "get_settings", wraps=module.get_settings) as settings:
        settings.return_value = settings.return_value.model_copy(
            update={"visitor_stats_enabled": True}
        )
        answer = client.get("/public/site-impact")
        assert answer.status_code == 200
        assert answer.json()["unique_visitors_30d"] is None
