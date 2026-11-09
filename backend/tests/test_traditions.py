"""Family traditions archive (ADR-0026 §7).

Threat T47: an entry keeps its own privacy level whatever it mentions; it is never shown on a
public tree; text is plain text; links name only what the reader can see; editing someone else's
entry follows the tree's review policy; the archive export includes only what the exporter may read.
"""

from __future__ import annotations

import io
import json
import zipfile
from typing import Any

from sqlalchemy import select

from app.models import AuditEvent, RecordRevision
from tests.conftest import new_tree, owner_session
from tests.helpers import create_person

RECIPE = {
    "kind": "recipe",
    "title": "Dadi's  gujiya",
    "body": "Maida, khoya, sugar.\r\n\r\n- Fry slowly\x07 on a low flame   \n- **Never** rush it",
}


def _new(client: Any, t: str, **kw: Any) -> dict[str, Any]:
    r = client.post(f"/trees/{t}/traditions", json={**RECIPE, **kw})
    assert r.status_code == 201, r.text
    return r.json()


def _ids(resp: Any) -> list[str]:
    assert resp.status_code == 200, resp.text
    return [i["id"] for i in resp.json()["items"]]


def test_add_read_search_and_plain_text(owner, tree, member_factory):
    t = tree["id"]
    e = _new(owner, t)
    assert e["title"] == "Dadi's gujiya"
    # normalised plain text: no control characters, no trailing spaces, line breaks kept
    assert e["body"] == "Maida, khoya, sugar.\n\n- Fry slowly on a low flame\n- **Never** rush it"
    assert (e["revision"], e["review_state"], e["can_withdraw"], e["edit_needs_review"]) == (
        1,
        "unreviewed",
        True,
        False,
    )
    markup = _new(
        owner, t, kind="story", title="<script>alert(1)</script>", body="<img src=x onerror=alert(1)>"
    )
    # stored and returned as text, never interpreted (the UI renders text nodes only)
    assert markup["title"] == "<script>alert(1)</script>" and markup["body"].startswith("<img")
    song = _new(owner, t, kind="song", title="होली की परंपरा", body="फागुन के गीत", language="hi")
    assert song["script"] == "Deva"
    # search in any script
    assert _ids(owner.get(f"/trees/{t}/traditions", params={"q": "holi"})) == [song["id"]]
    assert _ids(owner.get(f"/trees/{t}/traditions", params={"q": "होली"})) == [song["id"]]
    assert _ids(owner.get(f"/trees/{t}/traditions", params={"q": "gujiya"})) == [e["id"]]
    assert _ids(owner.get(f"/trees/{t}/traditions", params={"kind": "recipe"})) == [e["id"]]
    page = owner.get(f"/trees/{t}/traditions", params={"limit": 2}).json()
    assert len(page["items"]) == 2 and page["next_cursor"]
    rest = owner.get(f"/trees/{t}/traditions", params={"limit": 2, "cursor": page["next_cursor"]}).json()
    assert len(rest["items"]) == 1 and rest["next_cursor"] is None
    # too long, blank title, unknown kind
    assert owner.post(f"/trees/{t}/traditions", json={**RECIPE, "body": "x" * 50_001}).status_code == 422
    assert owner.post(f"/trees/{t}/traditions", json={**RECIPE, "title": " \x07 "}).status_code == 422
    assert owner.post(f"/trees/{t}/traditions", json={**RECIPE, "kind": "spell"}).status_code == 422
    # permissions: viewers read, family writers add
    viewer = member_factory(["VIEWER"])
    assert viewer.get(f"/trees/{t}/traditions/{e['id']}").json()["can_edit"] is False
    assert viewer.post(f"/trees/{t}/traditions", json=RECIPE).status_code == 403
    with owner_session() as db:
        ev = db.scalars(select(AuditEvent).where(AuditEvent.action == "tradition.created")).first()
        assert ev is not None and "gujiya" not in json.dumps(ev.details)  # the fact, never the text


def test_privacy_levels(owner, tree, member_factory):
    t = tree["id"]
    branch = owner.post(f"/trees/{t}/branches", json={"name": "Pune branch"}).json()
    contributor = member_factory(["CONTRIBUTOR"], name="Cousin")
    in_branch = member_factory(["VIEWER"], branch_id=branch["id"], name="Branch viewer")
    viewer = member_factory(["VIEWER"], name="Viewer")
    researcher = member_factory(["RESEARCHER"], name="Researcher")
    mine = _new(contributor, t, privacy_level="PRIVATE_SELF")
    admins = _new(contributor, t, privacy_level="PRIVATE_TREE_ADMINS")
    branch_only = _new(owner, t, privacy_level="FAMILY_BRANCH", branch_id=branch["id"])
    members = _new(owner, t)
    open_ = _new(owner, t, privacy_level="INVITED_RESEARCHER")

    def sees(c: Any) -> set[str]:
        return set(_ids(c.get(f"/trees/{t}/traditions")))

    assert sees(contributor) == {mine["id"], admins["id"], members["id"], open_["id"]}
    assert sees(owner) == {
        admins["id"],
        branch_only["id"],
        members["id"],
        open_["id"],
    }  # not someone's private note
    assert sees(in_branch) == {branch_only["id"], members["id"], open_["id"]}
    assert sees(viewer) == {members["id"], open_["id"]}
    assert sees(researcher) == {open_["id"]}
    for hidden in (mine, admins, branch_only):
        assert viewer.get(f"/trees/{t}/traditions/{hidden['id']}").status_code == 404
        assert viewer.get(f"/trees/{t}/traditions/{hidden['id']}/history").status_code == 404
    # another tree's member, and a public view, get nothing
    other = new_tree(viewer, "Viewer's own family")
    assert viewer.get(f"/trees/{other['id']}/traditions/{members['id']}").status_code == 404
    assert _ids(viewer.get(f"/trees/{other['id']}/traditions")) == []


def test_links_never_widen_privacy_or_name_hidden_people(owner, tree, member_factory):
    t = tree["id"]
    # deceased: hidden from viewers, but it does not cap the entry (a protected living person would
    # narrow it, ADR-0027 §5: test_traditions_sharing.py::test_linking_a_private_living_person_narrows)
    living = create_person(owner, t, "Asha", status="deceased", privacy_level="PRIVATE_TREE_ADMINS")
    elder = create_person(owner, t, "Kamla")
    place = owner.post(f"/trees/{t}/places", json={"canonical_name": "Banaras", "place_type": "city"}).json()
    e = _new(
        owner,
        t,
        links=[
            {"target_type": "person", "target_id": living["id"]},
            {"target_type": "person", "target_id": elder["id"]},
            {"target_type": "place", "target_id": place["id"]},
        ],
    )
    assert {link["label"] for link in e["links"]} == {"Asha Iyer", "Kamla Iyer", "Banaras"}
    viewer = member_factory(["VIEWER"])
    seen = viewer.get(f"/trees/{t}/traditions/{e['id']}").json()
    # the hidden living person is left out entirely, not shown as "someone"
    assert {link["label"] for link in seen["links"]} == {"Kamla Iyer", "Banaras"}
    assert living["id"] not in json.dumps(seen)
    # filtering by a person the reader cannot see is a 404, not an empty list
    assert viewer.get(f"/trees/{t}/traditions", params={"person_id": living["id"]}).status_code == 404
    assert _ids(viewer.get(f"/trees/{t}/traditions", params={"person_id": elder["id"]})) == [e["id"]]
    # a writer cannot link what they cannot see, or anything in another tree
    contributor = member_factory(["CONTRIBUTOR"], name="Cousin")
    r = contributor.post(
        f"/trees/{t}/traditions",
        json={**RECIPE, "links": [{"target_type": "person", "target_id": living["id"]}]},
    )
    assert r.status_code == 404
    other = new_tree(owner, "Other family")
    far = create_person(owner, other["id"], "Far")
    r = owner.post(
        f"/trees/{t}/traditions",
        json={**RECIPE, "links": [{"target_type": "person", "target_id": far["id"]}]},
    )
    assert r.status_code == 404
    # editing links never drops a link the editor cannot see
    contributor.patch(
        f"/trees/{t}/traditions/{e['id']}",
        json={"links": [{"target_type": "place", "target_id": place["id"]}]},
    )
    labels = {link["label"] for link in owner.get(f"/trees/{t}/traditions/{e['id']}").json()["links"]}
    assert labels == {"Asha Iyer", "Banaras"}
    # erasing a person removes their link; the tradition stays
    r = owner.post(
        f"/trees/{t}/people/{living['id']}/erase", json={"reason": "DPDP request", "confirm": True}
    )
    assert r.status_code == 200, r.text
    assert [link["label"] for link in owner.get(f"/trees/{t}/traditions/{e['id']}").json()["links"]] == [
        "Banaras"
    ]


def test_editing_someone_elses_entry_follows_the_review_policy(owner, tree, member_factory):
    t = tree["id"]
    contributor = member_factory(["CONTRIBUTOR"], name="Cousin Ravi")
    e = _new(owner, t, title="Holi at the haveli")
    # with review off, any family writer edits directly; history records it
    assert (
        contributor.patch(f"/trees/{t}/traditions/{e['id']}", json={"body": "Colours at noon."}).status_code
        == 200
    )
    assert owner.put(f"/trees/{t}/review-policy", json={"review_policy": "all"}).status_code == 200
    got = contributor.get(f"/trees/{t}/traditions/{e['id']}").json()
    assert got["edit_needs_review"] is True and got["revision"] == 2
    r = contributor.patch(f"/trees/{t}/traditions/{e['id']}", json={"body": "Colours from dawn."})
    assert r.status_code == 409 and r.json()["error"]["code"] == "review_required"
    # only the author or an admin decides who may read it
    r = contributor.patch(f"/trees/{t}/traditions/{e['id']}", json={"privacy_level": "INVITED_RESEARCHER"})
    assert r.status_code in (403, 409)
    # the contributor's own entry is theirs to edit
    own = _new(contributor, t, title="Ravi's notes")
    assert contributor.patch(f"/trees/{t}/traditions/{own['id']}", json={"body": "More."}).status_code == 200

    prop = contributor.post(
        f"/trees/{t}/proposals",
        json={
            "rationale": "Dadi said the colours started at dawn",
            "items": [
                {
                    "target_type": "tradition",
                    "op": "update",
                    "target_id": e["id"],
                    "patch": {"body": "Colours from dawn."},
                }
            ],
            "submit": True,
        },
    )
    assert prop.status_code == 201, prop.text
    inbox = owner.get(f"/trees/{t}/inbox").json()["items"]
    assert "Cousin Ravi proposed 1 change(s) to a family tradition" in inbox[0]["text"]
    detail = owner.get(f"/trees/{t}/proposals/{prop.json()['id']}").json()
    assert detail["can_decide"] is True, detail
    assert (detail["person_label"], detail["family_subject"]) == (None, "tradition")
    summaries = owner.get(f"/trees/{t}/proposals", params={"view": "to_review"}).json()["items"]
    assert summaries[0]["family_subject"] == "tradition"
    r = owner.post(f"/trees/{t}/proposals/{prop.json()['id']}/approve", json={})
    assert r.status_code == 200, r.text
    got = owner.get(f"/trees/{t}/traditions/{e['id']}").json()
    assert (got["body"], got["review_state"], got["revision"]) == ("Colours from dawn.", "family_reviewed", 3)
    history = owner.get(f"/trees/{t}/traditions/{e['id']}/history").json()
    assert history[0]["actor_name"] == "Cousin Ravi" and history[0]["reviewer_name"] == "Tree Owner"
    assert history[0]["before"] == {"body": "Colours at noon."} and history[-1]["op"] == "create"


def test_withdrawing(owner, tree, member_factory):
    t = tree["id"]
    contributor = member_factory(["CONTRIBUTOR"], name="Cousin")
    e = _new(owner, t)
    assert contributor.get(f"/trees/{t}/traditions/{e['id']}").json()["can_withdraw"] is False
    assert contributor.delete(f"/trees/{t}/traditions/{e['id']}").status_code == 403
    own = _new(contributor, t)
    assert contributor.delete(f"/trees/{t}/traditions/{own['id']}").status_code == 200
    assert owner.delete(f"/trees/{t}/traditions/{e['id']}").status_code == 200
    assert _ids(owner.get(f"/trees/{t}/traditions")) == []
    assert owner.get(f"/trees/{t}/traditions/{e['id']}").status_code == 404
    with owner_session() as db:  # history is kept
        ops = [
            r.op.value for r in db.scalars(select(RecordRevision).where(RecordRevision.record_id == e["id"]))
        ]
        assert sorted(ops) == ["create", "update"]


def test_citations_follow_the_entrys_privacy(owner, tree, member_factory):
    t = tree["id"]
    e = _new(owner, t, privacy_level="PRIVATE_TREE_ADMINS")
    s = owner.post(f"/trees/{t}/sources", json={"title": "Dadi's recipe notebook"}).json()
    c = owner.post(
        f"/trees/{t}/citations", json={"source_id": s["id"], "target_type": "tradition", "target_id": e["id"]}
    )
    assert c.status_code == 201, c.text
    assert (
        len(
            owner.get(
                f"/trees/{t}/citations", params={"target_type": "tradition", "target_id": e["id"]}
            ).json()
        )
        == 1
    )
    viewer = member_factory(["VIEWER"])
    r = viewer.get(f"/trees/{t}/citations", params={"target_type": "tradition", "target_id": e["id"]})
    assert r.status_code == 404


def test_archive_export_includes_only_readable_entries(owner, tree, member_factory):
    t = tree["id"]
    readable = _new(owner, t, title="Everyone's recipe")
    contributor = member_factory(["CONTRIBUTOR", "VIEWER"], name="Cousin")
    _new(contributor, t, title="Cousin's private note", privacy_level="PRIVATE_SELF")
    r = owner.get(f"/trees/{t}/exports/archive")
    assert r.status_code == 200, r.text
    z = zipfile.ZipFile(io.BytesIO(r.content))
    canonical = next(n for n in z.namelist() if n.endswith("genealogy/canonical-data.json"))
    data = json.loads(z.read(canonical))
    assert [x["title"] for x in data["traditions"]] == [readable["title"]]
    ged = z.read(next(n for n in z.namelist() if n.endswith("genealogy/tree.ged"))).decode()
    assert "Everyone's recipe" not in ged  # GEDCOM has no place for traditions
