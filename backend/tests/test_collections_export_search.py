"""Photo collections in the global search and the archive export (ADR-0027 §6, increment 5).

Both follow the exporter's or searcher's own view: a collection they may not see is never a hit and
never exported, and inside a collection only the photos they may see are listed.
"""

from __future__ import annotations

import io
import json
import zipfile
from typing import Any

from tests.doc_fixtures import unique_png, upload

_n = 1000


def _photo(client: Any, t: str, level: str) -> str:
    global _n
    _n += 1
    r = upload(
        client,
        t,
        unique_png(_n, "Export photo"),
        mime="image/png",
        category="photo",
        title=f"P{_n}",
        privacy_level=level,
    )
    assert r.status_code == 201, r.text
    return r.json()["id"]


def _collection(client: Any, t: str, title: str, **body: Any) -> str:
    r = client.post(f"/trees/{t}/collections", json={"title": title, **body})
    assert r.status_code == 201, r.text
    return r.json()["id"]


def _add(client: Any, t: str, cid: str, doc: str) -> None:
    r = client.post(f"/trees/{t}/collections/{cid}/items", json={"document_id": doc})
    assert r.status_code == 201, r.text


def _hits(client: Any, t: str, q: str, kinds: list[str] | None = None) -> list[dict[str, Any]]:
    params: dict[str, Any] = {"q": q}
    if kinds:
        params["kinds"] = kinds
    r = client.get(f"/trees/{t}/search", params=params)
    assert r.status_code == 200, r.text
    return [h for h in r.json()["hits"] if h["kind"] == "collection"]


def _archive(client: Any, t: str) -> tuple[list[dict[str, Any]], dict[str, Any], str]:
    r = client.get(f"/trees/{t}/exports/archive")
    assert r.status_code == 200, r.text
    z = zipfile.ZipFile(io.BytesIO(r.content))
    name = next(n for n in z.namelist() if n.endswith("collections/index.json"))
    manifest = json.loads(z.read(next(n for n in z.namelist() if n.endswith("manifest.json"))))
    everything = "".join(
        z.read(n).decode("utf-8", "ignore")
        for n in z.namelist()
        if n.endswith((".json", ".txt", ".csv", ".ged"))
    )
    return json.loads(z.read(name)), manifest, everything


def test_search_finds_only_collections_the_caller_may_see(owner, tree, member_factory):
    t = tree["id"]
    author = member_factory(["CONTRIBUTOR"], name="Author")
    viewer = member_factory(["VIEWER"], name="Viewer")
    researcher = member_factory(["RESEARCHER"], name="Researcher")
    admin = member_factory(["FAMILY_ADMIN"], name="Admin")
    shared = _collection(author, t, "Banaras ghats", privacy_level="TREE_MEMBERS")
    private = _collection(author, t, "Banaras secrets", description="Nani's letters")
    by_description = _collection(
        author, t, "Village", privacy_level="TREE_MEMBERS", description="Photos near Banaras station"
    )

    assert {h["id"] for h in _hits(author, t, "Banaras")} == {shared, private, by_description}
    for who in (viewer, admin, owner):
        found = _hits(who, t, "Banaras")
        assert {h["id"] for h in found} == {shared, by_description}, who
        assert private not in json.dumps(who.get(f"/trees/{t}/search", params={"q": "Banaras"}).json())
    reasons = {h["id"]: h["match_reason"] for h in _hits(viewer, t, "banaras")}
    assert "title" in reasons[shared] and "description" in reasons[by_description]
    # a private collection's description never makes it a hit
    assert _hits(admin, t, "letters") == []
    # researchers are not "all family members"
    assert _hits(researcher, t, "Banaras") == []
    # the kind filter works, and other kinds still search
    assert {h["id"] for h in _hits(viewer, t, "Banaras", kinds=["collection"])} == {shared, by_description}


def test_archive_exports_the_exporters_view_of_collections(owner, tree, member_factory):
    t = tree["id"]
    author = member_factory(["CONTRIBUTOR"], name="Author")
    shared = _collection(author, t, "Wedding", privacy_level="TREE_MEMBERS")
    private = _collection(author, t, "Only mine")
    open_photo = _photo(author, t, "TREE_MEMBERS")
    hidden_photo = _photo(author, t, "ONLY_ME")
    _add(author, t, shared, open_photo)
    _add(author, t, shared, hidden_photo)
    _add(author, t, private, hidden_photo)

    # the tree owner sees the shared collection with the open photo only; the private one not at all
    cols, manifest, everything = _archive(owner, t)
    assert [c["id"] for c in cols] == [shared] and manifest["counts"]["collections"] == 1
    assert [i["document_id"] for i in cols[0]["items"]] == [open_photo]
    assert cols[0]["items"][0]["in_documents_index"] is True
    assert private not in everything and hidden_photo not in everything and "Only mine" not in everything

    # the author's export holds both collections and every photo they may see
    cols, manifest, _ = _archive(author, t)
    by = {c["id"]: c for c in cols}
    assert set(by) == {shared, private} and manifest["counts"]["collections"] == 2
    assert {i["document_id"] for i in by[shared]["items"]} == {open_photo, hidden_photo}
    assert by[private]["privacy_level"] == "ONLY_ME"
    assert all(i["in_documents_index"] for c in cols for i in c["items"])
