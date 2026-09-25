from __future__ import annotations

from app.cli.seed_demo import seed


def test_seed_demo_loads_and_is_idempotent(client):
    tree_id = seed("seed@example.com", "seed-password-123")
    assert seed("seed@example.com", "seed-password-123") == tree_id
    r = client.post("/auth/login", json={"email": "seed@example.com", "password": "seed-password-123"})
    assert r.status_code == 200
    people = client.get(f"/trees/{tree_id}/people?limit=50").json()["items"]
    assert len(people) == 10
    arjun = next(p for p in people if p["display_name"] == "Arjun Iyer")
    assert arjun["is_minor"] is True
    kavya = next(p for p in people if p["display_name"] == "Kavya Iyer")
    fam = client.get(f"/trees/{tree_id}/people/{kavya['id']}/family").json()
    assert fam["parents"][0]["relationship_type"] == "adoptive_parent"
