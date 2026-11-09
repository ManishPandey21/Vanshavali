"""Render jobs and artifacts (ADR-0017). The stub renderer covers the lifecycle; the real Remotion
path is exercised by ``renderer/scripts/smoke.mjs`` (CI) and by the opt-in test at the end."""

from __future__ import annotations

import os
import shutil
from pathlib import Path
from typing import Any

import pytest
from sqlalchemy import select

from app.core.config import get_settings
from app.core.storage import get_store
from app.models import RenderJob
from app.modules.render import renderers
from tests.conftest import owner_session
from tests.helpers import create_person, exact, link
from tests.test_life_events import life_event, upload_photo


@pytest.fixture
def stub(monkeypatch):
    monkeypatch.setattr(get_settings(), "render_backend", "stub")


@pytest.fixture
def captured(monkeypatch, stub):
    """Record what the renderer is given (the payload is purged after the job)."""
    seen: list[dict[str, Any]] = []
    original = renderers.StubRenderer.render

    def spy(self, composition, props, output, progress):  # type: ignore[no-untyped-def]
        seen.append({"composition": composition, "props": props, "output": output})
        return original(self, composition, props, output, progress)

    monkeypatch.setattr(renderers.StubRenderer, "render", spy)
    return seen


def small_family(owner: Any, tid: str) -> dict[str, Any]:
    root = create_person(owner, tid, "Raju", sex="male", birth={"date": exact(1950, 1, 1)})
    dad = create_person(owner, tid, "Mohan", sex="male", birth={"date": exact(1920, 2, 2)})
    hidden = create_person(
        owner, tid, "Hiddenmum", sex="female", status="living", privacy_level="PRIVATE_TREE_ADMINS"
    )
    link(owner, tid, dad["id"], root["id"], "biological_parent")
    link(owner, tid, hidden["id"], root["id"], "biological_parent")
    return {"root": root, "dad": dad, "hidden": hidden}


def job(client: Any, tid: str, chart: str = "fan", output: str = "poster", **settings: Any) -> Any:
    return client.post(
        f"/trees/{tid}/render-jobs", json={"chart_type": chart, "output": output, "settings": settings}
    )


def test_render_disabled_by_default(owner, tree):
    r = job(owner, tree["id"])
    assert r.status_code == 503 and r.json()["error"]["code"] == "render_unavailable"


def test_poster_and_video_lifecycle_and_download(owner, tree, stub):
    tid = tree["id"]
    f = small_family(owner, tid)
    r = job(owner, tid, "fan", "poster", root_person_id=f["root"]["id"], generations=3, color_by="side")
    assert r.status_code == 202, r.text
    j = r.json()
    assert j["status"] == "succeeded" and j["progress"] == 100 and j["renderer"] == "stub"
    assert [a["kind"] for a in j["artifacts"]] == ["poster_png"]
    url = owner.post(
        f"/trees/{tid}/render-jobs/{j['id']}/artifacts/{j['artifacts'][0]['id']}/download-url"
    ).json()["url"]
    got = owner.get(url)
    assert got.status_code == 200 and got.content[:4] == b"\x89PNG"
    assert got.headers["cache-control"] == "no-store, private"
    # the encrypted payload is removed once the job ends
    with owner_session() as db:
        row = db.scalar(select(RenderJob))
        assert row.payload_storage_key is None
    assert not get_store().exists(f"STANDARD/{tid}/render/{j['id']}/payload.json")
    v = job(owner, tid, "event_timeline", "mp4", root_person_id=f["root"]["id"]).json()
    assert v["status"] == "succeeded" and {a["kind"] for a in v["artifacts"]} == {"poster_png", "video_mp4"}
    listing = owner.get(f"/trees/{tid}/render-jobs").json()
    assert [x["id"] for x in listing] == [v["id"], j["id"]]
    assert owner.delete(f"/trees/{tid}/render-jobs/{j['id']}").status_code == 200
    assert owner.get(url).status_code == 403  # deleted: the link no longer works


def test_payload_is_built_as_the_requester(owner, tree, member_factory, captured):
    tid = tree["id"]
    f = small_family(owner, tid)
    viewer = member_factory(["VIEWER"])
    assert job(viewer, tid, "pedigree", root_person_id=f["root"]["id"]).status_code == 202
    props = captured[-1]["props"]
    text = str(props)
    assert "Hiddenmum" not in text and f["hidden"]["id"] not in text
    slots = {n["slot"]: n for n in props["data"]["nodes"]}
    assert slots[3]["hidden"] is True and slots[3]["person"] is None
    assert slots[2]["person"]["name"] == "Mohan Iyer"
    assert props["branding"]["treeName"] == tree["name"]
    assert props["music"] is None and props["narration"] is None
    # the owner's render of the same chart does include the private person
    job(owner, tid, "pedigree", root_person_id=f["root"]["id"])
    assert "Hiddenmum" in str(captured[-1]["props"])


def test_event_timeline_embeds_only_photos_the_requester_may_open(owner, tree, member_factory, captured):
    tid = tree["id"]
    p = create_person(owner, tid, "Kamla", birth={"date": exact(1940, 3, 3)})
    open_ev = life_event(owner, tid, p["id"], category="marriage", title="Wedding", date=exact(1960, 5, 5))
    upload_photo(owner, tid, open_ev["id"], caption="Open photo")
    upload_photo(
        owner,
        tid,
        open_ev["id"],
        caption="Admins photo",
        privacy_level="PRIVATE_TREE_ADMINS",
        color=(1, 1, 1),
    )
    viewer = member_factory(["VIEWER"])
    assert job(viewer, tid, "event_timeline", "mp4", root_person_id=p["id"]).status_code == 202
    events = captured[-1]["props"]["data"]["events"]
    wedding = next(e for e in events if e["label"] == "Wedding")
    assert [ph["caption"] for ph in wedding["photos"]] == ["Open photo"]
    assert wedding["photos"][0]["src"].startswith("data:image/")
    job(viewer, tid, "event_timeline", root_person_id=p["id"], include_photos=False)
    assert all(not e["photos"] for e in captured[-1]["props"]["data"]["events"])


def test_jobs_and_artifacts_are_private_to_the_requester(owner, tree, member_factory, stub):
    tid = tree["id"]
    f = small_family(owner, tid)
    a = member_factory(["CONTRIBUTOR"], name="A")
    b = member_factory(["CONTRIBUTOR"], name="B")
    j = job(a, tid, "fan", root_person_id=f["root"]["id"]).json()
    art = j["artifacts"][0]["id"]
    assert b.get(f"/trees/{tid}/render-jobs/{j['id']}").status_code == 404
    assert b.get(f"/trees/{tid}/render-jobs").json() == []
    assert b.post(f"/trees/{tid}/render-jobs/{j['id']}/artifacts/{art}/download-url").status_code == 404
    assert b.delete(f"/trees/{tid}/render-jobs/{j['id']}").status_code == 404
    # a link issued to A does not work for B, even with a valid signature
    url = a.post(f"/trees/{tid}/render-jobs/{j['id']}/artifacts/{art}/download-url").json()["url"]
    assert b.get(url).status_code == 403
    assert a.get(url).status_code == 200
    assert a.get(url.replace("render-files/", "render-files/x")).status_code == 403
    # tree admins can see every export, but only its requester opens the files: a render may embed
    # the requester's private photos (ADR-0027 §1)
    assert owner.get(f"/trees/{tid}/render-jobs/{j['id']}").json()["mine"] is False
    assert owner.post(f"/trees/{tid}/render-jobs/{j['id']}/artifacts/{art}/download-url").status_code == 404
    assert owner.get(url).status_code == 403


def test_validation_quotas_and_failures(owner, tree, stub, monkeypatch):
    tid = tree["id"]
    f = small_family(owner, tid)
    assert (
        job(owner, tid, "graph", root_person_id=f["root"]["id"]).json()["error"]["code"] == "not_animatable"
    )
    assert job(owner, tid, "fan").json()["error"]["code"] == "root_required"
    assert job(owner, tid, "fan", root_person_id=f["root"]["id"], generations=9).status_code == 422
    assert job(owner, tid, "fan", root_person_id=f["root"]["id"], title="x" * 200).status_code == 422

    def boom(self, composition, props, output, progress):  # type: ignore[no-untyped-def]
        raise renderers.RenderError("render_timeout", "Rendering took too long")

    monkeypatch.setattr(renderers.StubRenderer, "render", boom)
    j = job(owner, tid, "fan", root_person_id=f["root"]["id"]).json()
    assert j["status"] == "failed" and j["error_code"] == "render_timeout" and j["artifacts"] == []
    with owner_session() as db:
        assert db.get(RenderJob, j["id"]).payload_storage_key is None

    monkeypatch.setattr(get_settings(), "render_max_per_day_per_tree", 1)
    r = job(owner, tid, "fan", root_person_id=f["root"]["id"])
    assert r.status_code == 422 and r.json()["error"]["code"] == "render_quota_reached"
    monkeypatch.setattr(get_settings(), "render_max_per_day_per_tree", 50)
    monkeypatch.setattr(get_settings(), "render_max_active_per_user", 0)
    r = job(owner, tid, "fan", root_person_id=f["root"]["id"])
    assert r.json()["error"]["code"] == "too_many_active_renders"


def test_hidden_root_is_not_renderable(owner, tree, member_factory, stub):
    tid = tree["id"]
    f = small_family(owner, tid)
    viewer = member_factory(["VIEWER"])
    assert job(viewer, tid, "event_timeline", root_person_id=f["hidden"]["id"]).status_code == 404


def test_lifespan_and_family_tree_payloads(owner, tree, captured):
    tid = tree["id"]
    f = small_family(owner, tid)
    life_event(
        owner,
        tid,
        f["dad"]["id"],
        category="migration",
        title="Moved",
        date={"precision": "year_only", "year": 1947},
        significance="milestone",
    )
    assert job(owner, tid, "lifespan", root_person_id=f["root"]["id"]).status_code == 202
    rows = {r["name"]: r for r in captured[-1]["props"]["data"]["rows"]}
    assert rows["Mohan Iyer"]["events"] == [{"year": 1947, "label": "Moved"}]
    assert (
        job(owner, tid, "family_tree", root_person_id=f["dad"]["id"], direction="descendants").status_code
        == 202
    )
    data = captured[-1]["props"]["data"]
    assert data["rootId"] == f["dad"]["id"] and {n["person"]["name"] for n in data["nodes"]} >= {
        "Mohan Iyer",
        "Raju Iyer",
    }


@pytest.mark.skipif(
    os.environ.get("VSH_TEST_REMOTION") != "1", reason="real Remotion render: set VSH_TEST_REMOTION=1"
)
def test_real_remotion_render_end_to_end(owner, tree, monkeypatch):
    renderer_dir = Path(__file__).resolve().parents[2] / "renderer"
    if not (renderer_dir / "build" / "bundle" / "index.html").exists() or shutil.which("node") is None:
        pytest.skip("renderer bundle not built")
    s = get_settings()
    monkeypatch.setattr(s, "render_backend", "remotion")
    monkeypatch.setattr(s, "renderer_dir", str(renderer_dir))
    tid = tree["id"]
    f = small_family(owner, tid)
    j = job(owner, tid, "fan", "mp4", root_person_id=f["root"]["id"], generations=2).json()
    assert j["status"] == "succeeded", j
    assert j["renderer"].startswith("remotion@")
    video = next(a for a in j["artifacts"] if a["kind"] == "video_mp4")
    assert video["size_bytes"] > 10_000 and video["duration_s"] > 4
    url = owner.post(f"/trees/{tid}/render-jobs/{j['id']}/artifacts/{video['id']}/download-url").json()["url"]
    body = owner.get(url).content
    assert body[4:8] == b"ftyp"
