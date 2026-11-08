"""Duplicates at entry (ADR-0021 §8, phase J): suggestions with reasons, never a hidden person."""

from __future__ import annotations

from typing import Any

from tests.conftest import ApiClient
from tests.helpers import create_person, exact, link


def check(client: ApiClient, tid: str, **body: Any) -> Any:
    return client.post(f"/trees/{tid}/duplicates/check", json=body)


def test_a_likely_duplicate_is_suggested_with_reasons(owner: ApiClient, tree: dict[str, Any]) -> None:
    tid = tree["id"]
    father = create_person(owner, tid, "Ramesh", "Sharma", sex="male")
    kamla = create_person(owner, tid, "Kamla", "Sharma", sex="female", birth={"date": exact(1932, 1, 1)})
    link(owner, tid, father["id"], kamla["id"], "biological_parent")
    create_person(owner, tid, "Mohan", "Verma", sex="male")
    r = check(
        owner,
        tid,
        names=[{"given_name": "Kamala", "surname": "Sharma"}],
        birth_year=1931,
        sex_at_birth="female",
        parent_ids=[father["id"]],
    )
    assert r.status_code == 200, r.text
    cands = r.json()["candidates"]
    assert [c["person"]["id"] for c in cands] == [kamla["id"]]
    assert cands[0]["likely"] is True
    assert {"birth year 1932", "same parent"} <= set(cands[0]["reasons"])


def test_names_in_another_script_meet(owner: ApiClient, tree: dict[str, Any]) -> None:
    tid = tree["id"]
    p = create_person(owner, tid, "सुनीता", "शर्मा")
    cands = check(owner, tid, names=[{"given_name": "सुनीता", "surname": "शर्मा"}]).json()["candidates"]
    assert cands and cands[0]["person"]["id"] == p["id"] and "same name" in cands[0]["reasons"]


def test_a_different_sex_or_distant_birth_year_is_not_suggested(
    owner: ApiClient, tree: dict[str, Any]
) -> None:
    tid = tree["id"]
    create_person(owner, tid, "Kiran", "Rao", sex="male", birth={"date": exact(1950, 1, 1)})
    assert (
        check(
            owner,
            tid,
            names=[{"given_name": "Kiran", "surname": "Rao"}],
            sex_at_birth="female",
            birth_year=1950,
        ).json()["candidates"]
        == []
    )
    assert (
        check(owner, tid, names=[{"given_name": "Kiran", "surname": "Rao"}], birth_year=1990).json()[
            "candidates"
        ]
        == []
    )


def test_hidden_people_are_never_revealed(
    owner: ApiClient, tree: dict[str, Any], member_factory: Any
) -> None:
    tid = tree["id"]
    secret = create_person(owner, tid, "Leela", "Menon", status="living")
    r = owner.put(
        f"/trees/{tid}/people/{secret['id']}/privacy", json={"privacy_level": "PRIVATE_TREE_ADMINS"}
    )
    assert r.status_code == 200, r.text
    contributor = member_factory(["CONTRIBUTOR"])
    out = check(contributor, tid, names=[{"given_name": "Leela", "surname": "Menon"}]).json()
    assert out == {"candidates": []}  # not shown, not counted
    assert check(owner, tid, names=[{"given_name": "Leela", "surname": "Menon"}]).json()["candidates"]


def test_the_anchor_and_chosen_people_are_excluded_and_viewers_cannot_check(
    owner: ApiClient, tree: dict[str, Any], member_factory: Any
) -> None:
    tid = tree["id"]
    p = create_person(owner, tid, "Anand", "Iyer")
    assert (
        check(owner, tid, names=[{"given_name": "Anand", "surname": "Iyer"}], exclude_ids=[p["id"]]).json()[
            "candidates"
        ]
        == []
    )
    viewer = member_factory(["VIEWER"])
    assert check(viewer, tid, names=[{"given_name": "Anand", "surname": "Iyer"}]).status_code == 403
