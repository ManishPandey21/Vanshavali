from __future__ import annotations

from typing import Any


def person_body(
    given: str,
    surname: str = "Iyer",
    *,
    status: str = "deceased",
    sex: str | None = None,
    birth: dict[str, Any] | None = None,
    **extra: Any,
) -> dict[str, Any]:
    body: dict[str, Any] = {
        "profile_status": status,
        "names": [{"given_name": given, "surname": surname, "is_preferred": True}],
    }
    if sex:
        body["sex_at_birth"] = sex
    if birth:
        body["birth"] = birth
    body.update(extra)
    return body


def create_person(client: Any, tree_id: str, given: str, surname: str = "Iyer", **kw: Any) -> dict[str, Any]:
    r = client.post(f"/trees/{tree_id}/people", json=person_body(given, surname, **kw))
    assert r.status_code == 201, r.text
    return r.json()


def link(client: Any, tree_id: str, a: str, b: str, type_: str, **kw: Any) -> dict[str, Any]:
    r = client.post(
        f"/trees/{tree_id}/relationships", json={"person_a_id": a, "person_b_id": b, "type": type_, **kw}
    )
    assert r.status_code == 201, r.text
    return r.json()


def exact(y: int, m: int, d: int) -> dict[str, Any]:
    return {"precision": "exact", "year": y, "month": m, "day": d}
