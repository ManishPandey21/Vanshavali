"""Super Admin master-data console (ADR-0026): capability, MFA, drafts and publication, optimistic
concurrency, duplicates, retirement, closed sets, pack coexistence, audit, and the guarantee that
curating global data opens no door into any family's tree."""

from __future__ import annotations

import copy
from typing import Any

import pytest
from sqlalchemy import select

from app.core import totp
from app.core.config import get_settings
from app.models import AuditEvent, TreeVocabularyTerm, User, VocabularyChange, VocabularyTerm
from app.models.enums import VocabularyTermManagedBy, VocabularyTermStatus
from app.modules.masterdata.loader import load_packs, read_packs
from tests.conftest import new_tree, owner_session
from tests.helpers import create_person

ADMIN = "/admin/master-data"


@pytest.fixture
def vocab() -> list[dict[str, Any]]:
    packs = read_packs()
    with owner_session() as db:
        load_packs(db, packs)
    return packs


def _make_system_admin(client: Any, *, mfa: bool = True) -> Any:
    client.register(name="Platform Admin")
    with owner_session() as db:
        db.execute(
            User.__table__.update().where(User.email == client.user["email"]).values(is_system_admin=True)
        )
        db.commit()
    if mfa:
        secret = client.post("/auth/mfa/setup").json()["secret"]
        r = client.post("/auth/mfa/enable", json={"code": totp.now_code(secret)})
        assert r.status_code == 200, r.text
    return client


@pytest.fixture
def admin(make_client: Any) -> Any:
    return _make_system_admin(make_client())


def _term(key: str, en: str, hi: str, **extra: Any) -> dict[str, Any]:
    return {"labels": {"en": en, "hi": hi}, **extra}


def _create(client: Any, key: str, code: str, en: str, hi: str, *, publish: bool = True, **kw: Any) -> Any:
    body = {
        "action": "create",
        "code": code,
        "term": _term(key, en, hi, **kw.pop("term", {})),
        "reason": "Requested by several families",
        "publish": publish,
        **kw,
    }
    return client.post(f"{ADMIN}/vocabularies/{key}/changes", json=body)


def _detail(client: Any, key: str, code: str) -> dict[str, Any]:
    r = client.get(f"{ADMIN}/vocabularies/{key}/terms/{code}")
    assert r.status_code == 200, r.text
    return r.json()


def _user_codes(client: Any, key: str, **params: Any) -> list[str]:
    r = client.get(f"/vocabularies/{key}", params=params)
    assert r.status_code == 200, r.text
    return [t["code"] for t in r.json()["items"]]


# ---------------------------------------------------------------- who may use the console
ENDPOINTS = [
    ("GET", f"{ADMIN}/vocabularies", None),
    ("GET", f"{ADMIN}/vocabularies/gotra/terms", None),
    ("GET", f"{ADMIN}/vocabularies/gotra/terms/kashyapa", None),
    ("POST", f"{ADMIN}/vocabularies/gotra/duplicates", {"labels": {"en": "Kashyap"}}),
    ("POST", f"{ADMIN}/vocabularies/gotra/changes", {"action": "create", "code": "x", "reason": "x"}),
    ("GET", f"{ADMIN}/changes", None),
    ("GET", f"{ADMIN}/changes/0190a1a2-0000-7000-8000-000000000000", None),
    ("POST", f"{ADMIN}/changes/0190a1a2-0000-7000-8000-000000000000/publish", {}),
    ("POST", f"{ADMIN}/changes/0190a1a2-0000-7000-8000-000000000000/reject", {"note": "no thanks"}),
    ("POST", f"{ADMIN}/changes/0190a1a2-0000-7000-8000-000000000000/withdraw", {}),
]


@pytest.mark.parametrize("method, path, body", ENDPOINTS)
def test_ordinary_users_cannot_reach_the_console(client, owner, tree, vocab, method, path, body):
    # signed out: 401; a tree owner (the most powerful *family* role): 404, nothing advertised
    assert client.request(method, path, json=body).status_code == 401
    r = owner.request(method, path, json=body)
    assert r.status_code == 404, r.text


def test_system_admin_needs_two_step_sign_in(make_client, vocab):
    no_mfa = _make_system_admin(make_client(), mfa=False)
    r = no_mfa.get(f"{ADMIN}/vocabularies")
    assert r.status_code == 403
    assert r.json()["error"]["code"] == "admin_mfa_required"
    assert _create(no_mfa, "gotra", "new_one", "New", "नया").status_code == 403
    assert no_mfa.get("/auth/me").json()["is_system_admin"] is True


def test_console_writes_need_the_csrf_token(admin, vocab):
    r = admin.client.post(
        f"/api/v1{ADMIN}/vocabularies/gotra/changes",
        json={"action": "create", "code": "x", "reason": "x"},
    )  # no X-CSRF-Token header
    assert r.status_code == 403
    assert r.json()["error"]["code"] == "csrf_failed"


def test_console_lists_only_vocabularies_never_controlled_values(admin, vocab):
    r = admin.get(f"{ADMIN}/vocabularies")
    assert r.status_code == 200
    keys = {v["key"] for v in r.json()}
    assert keys == {p["key"] for p in vocab}
    # roles, privacy levels, relationship types and the astronomical sets are code, not catalogues
    for controlled in (
        "role",
        "privacy_level",
        "relationship_type",
        "nakshatra",
        "rashi",
        "religion",
        "jati",
    ):
        assert controlled not in keys
        assert admin.get(f"{ADMIN}/vocabularies/{controlled}/terms").status_code == 404
        assert _create(admin, controlled, "thirteenth", "Thirteenth", "तेरहवाँ").status_code == 404
    lang = next(v for v in r.json() if v["key"] == "language")
    assert lang["fixed_membership"] is True and lang["category"] == "languages_terminology"


def test_system_admin_still_has_no_tree_access(admin, owner, tree, vocab):
    t = tree["id"]
    person = create_person(owner, t, "Ramesh", "Sharma")
    fam = owner.post(f"/trees/{t}/vocabularies/kuladevata/terms", json={"label": "Khandoba"})
    assert fam.status_code == 201
    # the admin is no member: every tree route is 404 (ADR-0006 §6, T12)
    for path in (
        f"/trees/{t}",
        f"/trees/{t}/people/{person['id']}",
        f"/trees/{t}/vocabularies/kuladevata",
    ):
        assert admin.get(path).status_code == 404, path
    trees = admin.get("/trees").json()
    assert (trees["items"] if isinstance(trees, dict) else trees) == []
    # the console shows global terms only: the family's entry is in no list, count or search
    terms = admin.get(f"{ADMIN}/vocabularies/kuladevata/terms", params={"q": "Khandoba"}).json()
    assert terms["items"] == [] and terms["total"] == 0
    listed = next(v for v in admin.get(f"{ADMIN}/vocabularies").json() if v["key"] == "kuladevata")
    assert sum(listed["counts"].values()) == 0
    dupes = admin.post(f"{ADMIN}/vocabularies/kuladevata/duplicates", json={"labels": {"en": "Khandoba"}})
    assert dupes.json() == []
    # and publishing a global term with the same name leaves the family's entry untouched
    assert _create(admin, "kuladevata", "khandoba", "Khandoba", "खंडोबा").status_code == 201
    with owner_session() as db:
        rows = db.scalars(select(TreeVocabularyTerm)).all()
        assert [(r.label, str(r.tree_id)) for r in rows] == [("Khandoba", t)]


# ---------------------------------------------------------------- create, draft, publish
def test_published_term_reaches_users_without_a_deployment(admin, owner, tree, vocab):
    before = next(v for v in owner.get("/vocabularies").json() if v["key"] == "gotra")
    r = _create(
        admin,
        "gotra",
        "mudgala",
        "Mudgala",
        "मुद्गल",
        term={"aliases": ["Mudgal"], "source_url": "https://example.org/gotra-list"},
        source_reference="Family submissions reviewed 5 Nov 2026",
    )
    assert r.status_code == 201, r.text
    change = r.json()
    assert change["status"] == "published" and change["previous"] == {}
    assert change["proposed"]["labels"] == {"en": "Mudgala", "hi": "मुद्गल"}
    # every spelling finds it, in either script
    for q in ("Mudgala", "mudgal", "मुद्गल"):
        assert "mudgala" in _user_codes(owner, "gotra", q=q), q
    after = next(v for v in owner.get("/vocabularies").json() if v["key"] == "gotra")
    assert after["revision"] == before["revision"] + 1
    with owner_session() as db:
        term = db.scalar(select(VocabularyTerm).where(VocabularyTerm.code == "mudgala"))
        assert term is not None and term.managed_by == VocabularyTermManagedBy.ADMIN
        events = db.scalars(select(AuditEvent).where(AuditEvent.action.like("masterdata.%"))).all()
        assert [e.action for e in events] == ["masterdata.change_proposed", "masterdata.change_published"]
        assert all(e.tree_id is None for e in events)
        assert events[1].details == {"vocabulary": "gotra", "code": "mudgala", "action": "create"}
    # a new suggestion never fills anything in for anybody (ADR-0018: suggest, never infer)
    p = create_person(owner, tree["id"], "Raghav", "Mudgal")
    assert owner.get(f"/trees/{tree['id']}/people/{p['id']}/heritage").json()["attributes"] == []


def test_draft_is_invisible_until_published(admin, owner, vocab):
    r = _create(admin, "occupation", "fishing", "Fishing", "मछली पालन", publish=False)
    assert r.status_code == 201, r.text
    change = r.json()
    assert change["status"] == "pending" and change["proposed_by_me"] is True
    assert "fishing" not in _user_codes(owner, "occupation")
    resp = admin.get(f"{ADMIN}/changes", params={"status": "pending"})
    assert resp.status_code == 200, resp.text
    pending = resp.json()["items"]
    assert [c["id"] for c in pending] == [change["id"]]
    vocabs = {v["key"]: v for v in admin.get(f"{ADMIN}/vocabularies").json()}
    assert vocabs["occupation"]["pending_changes"] == 1
    # one open change per term
    again = _create(admin, "occupation", "fishing", "Fishing", "मछली पालन", publish=False)
    assert again.status_code == 409 and again.json()["error"]["code"] == "change_pending"

    r = admin.post(f"{ADMIN}/changes/{change['id']}/publish", json={"note": "checked"})
    assert r.status_code == 200, r.text
    assert r.json()["status"] == "published" and r.json()["decision_note"] == "checked"
    assert "fishing" in _user_codes(owner, "occupation")
    # a decided change cannot be decided again
    for action, body in (("publish", {}), ("reject", {"note": "too late"}), ("withdraw", {})):
        r = admin.post(f"{ADMIN}/changes/{change['id']}/{action}", json=body)
        assert r.status_code == 409 and r.json()["error"]["code"] == "change_decided"


def test_reject_needs_a_note_and_only_the_proposer_withdraws(admin, make_client, vocab):
    other = _make_system_admin(make_client())
    a = _create(admin, "occupation", "potter", "Potter", "कुम्हार", publish=False).json()
    assert admin.post(f"{ADMIN}/changes/{a['id']}/reject", json={}).status_code == 422
    r = other.post(f"{ADMIN}/changes/{a['id']}/withdraw")
    assert r.status_code == 403 and r.json()["error"]["code"] == "not_proposer"
    r = other.post(f"{ADMIN}/changes/{a['id']}/reject", json={"note": "Already listed as 'artisan'"})
    assert r.status_code == 200 and r.json()["status"] == "rejected"
    assert r.json()["decided_by_name"] == "Platform Admin"
    b = _create(admin, "occupation", "potter", "Potter", "कुम्हार", publish=False).json()
    assert admin.post(f"{ADMIN}/changes/{b['id']}/withdraw").json()["status"] == "withdrawn"
    assert admin.get(f"{ADMIN}/changes", params={"status": "pending"}).json()["items"] == []


def test_four_eyes_publication_when_switched_on(admin, make_client, vocab, monkeypatch):
    monkeypatch.setattr(get_settings(), "masterdata_require_second_admin", True)
    r = _create(admin, "occupation", "carpenter", "Carpenter", "बढ़ई")
    assert r.status_code == 403 and r.json()["error"]["code"] == "second_admin_required"
    draft = _create(admin, "occupation", "carpenter", "Carpenter", "बढ़ई", publish=False).json()
    r = admin.post(f"{ADMIN}/changes/{draft['id']}/publish", json={})
    assert r.status_code == 403 and r.json()["error"]["code"] == "second_admin_required"
    other = _make_system_admin(make_client())
    assert other.post(f"{ADMIN}/changes/{draft['id']}/publish", json={}).json()["status"] == "published"


# ---------------------------------------------------------------- edits and concurrency
def _update(client: Any, key: str, code: str, revision: int, term: dict[str, Any], **kw: Any) -> Any:
    body = {
        "action": "update",
        "code": code,
        "base_revision": revision,
        "term": term,
        "reason": "Fix label",
        **kw,
    }
    return client.post(f"{ADMIN}/vocabularies/{key}/changes", json={"publish": True, **body})


def test_edits_are_refused_when_someone_else_changed_the_term(admin, make_client, vocab):
    other = _make_system_admin(make_client())
    t = _detail(admin, "gotra", "kashyapa")["term"]
    fields = {
        k: t[k]
        for k in ("labels", "aliases", "scope", "parent_code", "attributes", "source_url", "sort_order")
    }
    fields["status"] = t["status"]
    first = _update(
        other, "gotra", "kashyapa", t["revision"], {**fields, "aliases": [*t["aliases"], "Kasyap"]}
    )
    assert first.status_code == 201, first.text
    # the admin still has the old revision open: their edit must not silently overwrite it
    lost = _update(admin, "gotra", "kashyapa", t["revision"], {**fields, "status": "reviewed"})
    assert lost.status_code == 409
    assert lost.json()["error"]["code"] == "stale_revision"
    assert lost.json()["error"]["details"]["current_revision"] == t["revision"] + 1
    assert _update(admin, "gotra", "kashyapa", t["revision"], fields).status_code == 409
    # an unchanged "edit" is refused too
    fresh = _detail(admin, "gotra", "kashyapa")["term"]
    same = {**fields, "aliases": fresh["aliases"]}
    r = _update(admin, "gotra", "kashyapa", fresh["revision"], same)
    assert r.status_code == 422 and r.json()["error"]["code"] == "no_change"


def test_a_draft_goes_stale_when_the_term_moves_on(admin, vocab):
    t = _detail(admin, "gotra", "garga")["term"]
    term = {"labels": {**t["labels"], "en": "Gargya"}, "aliases": t["aliases"], "status": "draft"}
    draft = _update(admin, "gotra", "garga", t["revision"], term, publish=False)
    assert draft.status_code == 201 and draft.json()["stale"] is False
    # a new pack release changes the same (still pack-managed) term meanwhile
    packs = copy.deepcopy(vocab)
    gotra = next(p for p in packs if p["key"] == "gotra")
    next(x for x in gotra["terms"] if x["code"] == "garga")["aliases"].append("Garg rishi")
    with owner_session() as db:
        assert load_packs(db, packs).updated == 1
    assert admin.get(f"{ADMIN}/changes/{draft.json()['id']}").json()["stale"] is True
    r = admin.post(f"{ADMIN}/changes/{draft.json()['id']}/publish", json={})
    assert r.status_code == 409 and r.json()["error"]["code"] == "stale_change"


def test_pack_loader_never_overwrites_console_curation(admin, vocab):
    t = _detail(admin, "gotra", "vashishtha")["term"]
    term = {"labels": {**t["labels"], "en": "Vasishta"}, "aliases": t["aliases"], "status": "reviewed"}
    assert _update(admin, "gotra", "vashishtha", t["revision"], term).status_code == 201
    assert _create(admin, "gotra", "mudgala", "Mudgala", "मुद्गल").status_code == 201
    with owner_session() as db:
        report = load_packs(db, read_packs())  # the shipped pack still has the old label
        assert report.kept == 1 and report.updated == 0 and report.retired == 0
        rows = {
            r.code: r
            for r in db.scalars(select(VocabularyTerm).where(VocabularyTerm.vocabulary_key == "gotra"))
        }
        assert rows["vashishtha"].labels["en"] == "Vasishta"
        assert rows["vashishtha"].status == VocabularyTermStatus.REVIEWED
        # a console-added term is not "missing from the pack" and is never retired by a load
        assert rows["mudgala"].status == VocabularyTermStatus.DRAFT


# ---------------------------------------------------------------- duplicates
def test_duplicates_are_caught_before_they_are_created(admin, vocab):
    r = _create(admin, "gotra", "bhardwaj", "Bhardwaj", "भारद्वाज")
    assert r.status_code == 409
    err = r.json()["error"]
    assert err["code"] == "possible_duplicate"
    assert [m["code"] for m in err["details"]["matches"]] == ["bharadwaja"]
    check = admin.post(f"{ADMIN}/vocabularies/gotra/duplicates", json={"labels": {"en": "Bhardwaj"}})
    assert [m["code"] for m in check.json()] == ["bharadwaja"]
    # the same code is never reused, even when the admin confirms a similar label
    r = _create(admin, "gotra", "bharadwaja", "Bharadvaja II", "भरद्वाज २", allow_similar=True)
    assert r.status_code == 409 and r.json()["error"]["code"] == "code_taken"
    # a genuinely different entry with a resembling name can be confirmed
    assert (
        _create(admin, "gotra", "bhardwaj_regional", "Bhardwaj", "भारद्वाज", allow_similar=True).status_code
        == 201
    )


# ---------------------------------------------------------------- retirement
def test_retired_terms_keep_stored_values_readable(admin, owner, tree, vocab):
    t = tree["id"]
    p = create_person(owner, t, "Ramesh", "Sharma")
    url = f"/trees/{t}/people/{p['id']}/heritage"
    stored = owner.post(
        url,
        json={
            "attribute": "gotra",
            "value_text": "Garg",
            "value_json": {"vocabulary": "gotra", "code": "garga"},
        },
    )
    assert stored.status_code == 201
    rev = _detail(admin, "gotra", "garga")["term"]["revision"]
    body = {"action": "retire", "code": "garga", "base_revision": rev, "reason": "Merged", "publish": True}
    bad = admin.post(f"{ADMIN}/vocabularies/gotra/changes", json={**body, "successor_code": "garga"})
    assert bad.status_code == 422 and bad.json()["error"]["code"] == "invalid_successor"
    bad = admin.post(f"{ADMIN}/vocabularies/gotra/changes", json={**body, "successor_code": "nope"})
    assert bad.status_code == 422
    r = admin.post(f"{ADMIN}/vocabularies/gotra/changes", json={**body, "successor_code": "kashyapa"})
    assert r.status_code == 201, r.text
    # gone from suggestions, still resolvable, with its successor
    assert "garga" not in _user_codes(owner, "gotra")
    retired = owner.get("/vocabularies/gotra", params={"include_retired": "true", "q": "garga"}).json()[
        "items"
    ]
    assert retired[0]["status"] == "retired" and retired[0]["successor_code"] == "kashyapa"
    # the family's stored value is untouched and still readable; a new reference still validates
    attrs = owner.get(url).json()["attributes"]
    assert [(a["attribute"], a["preferred"]["value_text"]) for a in attrs] == [("gotra", "Garg")]
    q = create_person(owner, t, "Suresh", "Sharma")
    again = owner.post(
        f"/trees/{t}/people/{q['id']}/heritage",
        json={
            "attribute": "gotra",
            "value_text": "Garg",
            "value_json": {"vocabulary": "gotra", "code": "garga"},
        },
    )
    assert again.status_code == 201
    # nothing is ever deleted; retired terms can come back
    term = _detail(admin, "gotra", "garga")["term"]
    edit = _update(admin, "gotra", "garga", term["revision"], {"labels": term["labels"]})
    assert edit.status_code == 409 and edit.json()["error"]["code"] == "term_retired"
    back = admin.post(
        f"{ADMIN}/vocabularies/gotra/changes",
        json={
            "action": "reactivate",
            "code": "garga",
            "base_revision": term["revision"],
            "reactivate_as": "reviewed",
            "reason": "Split again after review",
            "publish": True,
        },
    )
    assert back.status_code == 201, back.text
    assert "garga" in _user_codes(owner, "gotra")
    history = _detail(admin, "gotra", "garga")["history"]
    assert [h["action"] for h in history] == ["reactivate", "retire"]
    assert history[1]["previous"]["status"] == "draft" and history[1]["proposed"]["status"] == "retired"


def test_fixed_sets_can_be_relabelled_but_not_grown_or_shrunk(admin, vocab):
    r = _create(admin, "language", "awadhi", "Awadhi", "अवधी")
    assert r.status_code == 422 and r.json()["error"]["code"] == "fixed_vocabulary"
    t = _detail(admin, "language", "ta")["term"]
    retire = {
        "action": "retire",
        "code": "ta",
        "base_revision": t["revision"],
        "reason": "x y z",
        "publish": True,
    }
    r = admin.post(f"{ADMIN}/vocabularies/language/changes", json=retire)
    assert r.status_code == 422 and r.json()["error"]["code"] == "fixed_vocabulary"
    term = {"labels": {**t["labels"], "ta": "தமிழ்"}, "aliases": t["aliases"], "attributes": t["attributes"]}
    assert _update(admin, "language", "ta", t["revision"], term).status_code == 201


# ---------------------------------------------------------------- input validation
@pytest.mark.parametrize(
    "patch, where",
    [
        ({"term": {"labels": {"en": "Only English"}}}, "hi"),
        ({"term": {"labels": {"en": "X", "hi": "एक्स"}, "source_url": "javascript:alert(1)"}}, "source"),
        ({"term": {"labels": {"en": "X", "hi": "एक्स"}, "source_url": "data:text/html,<b>"}}, "source"),
        ({"term": {"labels": {"en": "X" * 201, "hi": "एक्स"}}}, "200"),
        ({"term": {"labels": {"en": "X", "hi": "एक्स", "<script>": "x"}}}, "language tag"),
        ({"term": {"labels": {"en": "X", "hi": "एक्स"}, "managed_by": "pack"}}, "managed_by"),
        ({"term": {"labels": {"en": "X", "hi": "एक्स"}}, "revision": 7}, "revision"),
        ({"term": {"labels": {"en": "X", "hi": "एक्स"}}, "code": "Bad Code"}, "code"),
        ({"term": {"labels": {"en": "X", "hi": "एक्स"}, "status": "retired"}}, "status"),
        ({"term": {"labels": {"en": "X", "hi": "एक्स"}, "attributes": {"Bad Key": 1}}}, "attribute"),
        ({"term": {"labels": {"en": "X", "hi": "एक्स"}}, "reason": "  "}, "reason"),
        ({"term": None}, "term fields"),
        ({"base_revision": 3}, "base revision"),
    ],
)
def test_malicious_or_malformed_changes_are_refused(admin, vocab, patch, where):
    body = {
        "action": "create",
        "code": "new_term",
        "term": {"labels": {"en": "X", "hi": "एक्स"}},
        "reason": "Needed",
    }
    body.update(patch)
    r = admin.post(f"{ADMIN}/vocabularies/occupation/changes", json=body)
    assert r.status_code == 422, (where, r.text)
    with owner_session() as db:
        assert db.scalar(select(VocabularyChange.id)) is None


def test_parent_must_be_an_active_term_and_labels_are_stored_as_text(admin, vocab):
    r = _create(admin, "occupation", "handloom", "Handloom", "हथकरघा", term={"parent_code": "nope"})
    assert r.status_code == 422 and r.json()["error"]["code"] == "invalid_parent"
    r = _create(admin, "occupation", "handloom", "Handloom", "हथकरघा", term={"parent_code": "handloom"})
    assert r.status_code == 422
    label = '<img src=x onerror="alert(1)">'
    r = _create(admin, "occupation", "odd_label", label, "विचित्र")
    assert r.status_code == 201
    # stored and returned verbatim as data; the SPA renders it as text (React escaping)
    assert _detail(admin, "occupation", "odd_label")["term"]["labels"]["en"] == label


# ---------------------------------------------------------------- browsing
def test_term_list_search_filter_and_cursor_pagination(admin, vocab):
    gotra = next(p for p in vocab if p["key"] == "gotra")
    page1 = admin.get(f"{ADMIN}/vocabularies/gotra/terms", params={"limit": 3}).json()
    assert page1["total"] == len(gotra["terms"]) and len(page1["items"]) == 3
    page2 = admin.get(
        f"{ADMIN}/vocabularies/gotra/terms", params={"limit": 3, "cursor": page1["next_cursor"]}
    ).json()
    assert {t["code"] for t in page1["items"]}.isdisjoint({t["code"] for t in page2["items"]})
    assert [
        t["code"]
        for t in admin.get(f"{ADMIN}/vocabularies/gotra/terms", params={"q": "भरद्वाज"}).json()["items"]
    ] == ["bharadwaja"]
    reviewed = admin.get(f"{ADMIN}/vocabularies/gotra/terms", params={"status": "reviewed"}).json()
    assert reviewed["total"] == 0
    assert admin.get(f"{ADMIN}/vocabularies/gotra/terms", params={"sort": "drop"}).status_code == 422
    assert admin.get(f"{ADMIN}/vocabularies/gotra/terms/nope").status_code == 404
    # change history pages too
    for i in range(3):
        _create(
            admin, "occupation", f"trade_{i}", f"Trade number {i}", f"व्यवसाय क्रमांक {i}", allow_similar=True
        )
    h1 = admin.get(f"{ADMIN}/changes", params={"limit": 2, "vocabulary": "occupation"}).json()
    assert len(h1["items"]) == 2 and h1["next_cursor"]
    h2 = admin.get(
        f"{ADMIN}/changes", params={"limit": 2, "vocabulary": "occupation", "cursor": h1["next_cursor"]}
    )
    assert len(h2.json()["items"]) == 1


def test_new_tree_after_publication_sees_the_term(admin, owner, vocab):
    _create(
        admin, "kuladevi", "tulja_bhavani", "Tulja Bhavani", "तुळजा भवानी", term={"aliases": ["Tuljabhavani"]}
    )
    t2 = new_tree(owner, "Second family")
    r = owner.get(f"/trees/{t2['id']}/vocabularies/kuladevi", params={"q": "tulja"}).json()
    assert [i["code"] for i in r["items"]] == ["tulja_bhavani"]
    assert r["items"][0]["origin"] == "global"


def test_the_database_allows_one_open_change_per_term(vocab):
    """Backs the 409 `change_pending` check even if two proposals race (ADR-0026 §3)."""
    from sqlalchemy.exc import IntegrityError

    def change(status: str) -> VocabularyChange:
        return VocabularyChange(
            vocabulary_key="gotra",
            term_code="garga",
            action="update",
            status=status,
            reason="race",
            base_revision=1,
        )

    with owner_session() as db:
        db.add_all([change("published"), change("rejected"), change("pending")])
        db.commit()
        db.add(change("pending"))
        with pytest.raises(IntegrityError):
            db.commit()
