"""Public site impact counters: never inspect or expose tree contents."""

from __future__ import annotations

import pytest
import redis

from app.core.ratelimit import get_limiter
from app.modules.public import site_impact as module
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


@pytest.fixture
def visitor_stats(monkeypatch):
    """Visitor measurement on, against an in-memory HyperLogLog stand-in."""
    fake = FakeRedis()
    monkeypatch.setattr(module, "_redis_client", lambda: fake)
    original_settings = module.get_settings()
    monkeypatch.setattr(
        module,
        "get_settings",
        lambda: original_settings.model_copy(update={"visitor_stats_enabled": True}),
    )
    get_limiter().reset()
    yield fake
    get_limiter().reset()


def test_visitor_cookie_deduplicates_browser_and_does_not_expose_id(client, visitor_stats):
    first = client.get("/public/site-impact")
    assert first.status_code == 200
    assert first.json()["unique_visitors_30d"] == 1
    set_cookie = first.headers["set-cookie"]
    assert "vsh_impact_visitor" in set_cookie
    assert "httponly" in set_cookie.lower()
    assert "path=/api/v1/public" in set_cookie.lower()
    assert first.headers["cache-control"] == "no-store"
    cookie = client.client.cookies.get("vsh_impact_visitor")
    # Only an HMAC digest reaches the store, never the cookie token itself.
    stored = set().union(*visitor_stats.days.values())
    assert cookie.split(".")[0] not in stored
    assert all(len(v) == 64 for v in stored)
    second = client.get("/public/site-impact")
    assert second.json()["unique_visitors_30d"] == 1
    assert "set-cookie" not in second.headers


def test_separate_browser_counts_separately(client, visitor_stats):
    assert client.get("/public/site-impact").json()["unique_visitors_30d"] == 1
    client.client.cookies.clear()
    assert client.get("/public/site-impact").json()["unique_visitors_30d"] == 2


def test_forged_cookie_is_not_trusted(client, visitor_stats):
    client.client.cookies.set("vsh_impact_visitor", "A" * 32 + ".deadbeef", path="/api/v1/public")
    answer = client.get("/public/site-impact")
    assert answer.json()["unique_visitors_30d"] == 1
    # A fresh, correctly signed cookie replaces the forged one.
    assert "vsh_impact_visitor" in answer.headers["set-cookie"]
    assert "A" * 32 not in answer.headers["set-cookie"]


@pytest.mark.parametrize("header", [{"Sec-GPC": "1"}, {"DNT": "1"}])
def test_privacy_signal_is_neither_counted_nor_tagged(client, visitor_stats, header):
    answer = client.get("/public/site-impact", headers=header)
    assert answer.status_code == 200
    assert answer.json()["unique_visitors_30d"] == 0
    assert "set-cookie" not in answer.headers
    assert visitor_stats.days == {}


def test_cookieless_flood_from_one_address_is_capped(client, visitor_stats):
    for _ in range(module._NEW_VISITORS_PER_ADDRESS_HOURLY + 10):
        client.client.cookies.clear()
        assert client.get("/public/site-impact").status_code == 200
    assert (
        client.get("/public/site-impact").json()["unique_visitors_30d"]
        == module._NEW_VISITORS_PER_ADDRESS_HOURLY
    )


def test_visitor_service_failure_does_not_falsely_show_zero(client, monkeypatch):
    def broken():
        raise redis.RedisError("simulated outage")

    monkeypatch.setattr(module, "_redis_client", broken)
    original_settings = module.get_settings()
    monkeypatch.setattr(
        module,
        "get_settings",
        lambda: original_settings.model_copy(update={"visitor_stats_enabled": True}),
    )
    answer = client.get("/public/site-impact")
    assert answer.status_code == 200
    assert answer.json()["unique_visitors_30d"] is None


def test_disabled_measurement_sets_no_cookie(client):
    answer = client.get("/public/site-impact")
    assert answer.json()["unique_visitors_30d"] is None
    assert "set-cookie" not in answer.headers
