"""Name transliteration suggestions (ADR-0025; issue #34).

Suggestions only, local and deterministic: a reviewed lexicon first, Hindi rules second. The
endpoint is signed-in, size- and rate-limited, and never logs or stores the text. An accepted
suggestion is a separate transliteration name with calculated-then-confirmed provenance.
"""

from __future__ import annotations

import json
import logging
import unicodedata
from typing import Any

import pytest

from app.modules.translit import engine
from app.modules.translit.engine import suggest
from tests.helpers import create_person, person_body


def texts(text: str, target: str) -> list[str]:
    return [c.text for c in suggest(text, target)]  # type: ignore[arg-type]


# ------------------------------------------------------------------ engine: lexicon
@pytest.mark.parametrize(
    ("latin", "deva"),
    [
        ("Sunita", "सुनीता"),
        ("Sharma", "शर्मा"),
        ("Lakshmi", "लक्ष्मी"),
        ("Laxmi", "लक्ष्मी"),
        ("Iyer", "अय्यर"),
        ("Singh", "सिंह"),
    ],
)
def test_lexicon_latin_to_devanagari(latin: str, deva: str) -> None:
    cands = suggest(latin, "Deva")
    assert cands[0].text == deva and cands[0].method == "lexicon"


def test_lexicon_devanagari_to_latin_lists_known_spellings_in_order() -> None:
    assert texts("लक्ष्मी", "Latn")[:2] == ["Lakshmi", "Laxmi"]
    assert texts("सिंह", "Latn") == ["Singh"]
    assert suggest("गीता", "Latn")[0].method == "lexicon"


def test_full_names_combine_per_word() -> None:
    assert texts("Sunita Sharma", "Deva")[0] == "सुनीता शर्मा"
    assert texts("सुनीता शर्मा", "Latn")[0] == "Sunita Sharma"


# ------------------------------------------------------------------ engine: rules
def test_rules_latin_to_devanagari_hindi_orthography() -> None:
    # not in the lexicon on purpose: names the rules must handle
    assert texts("Ramprakash", "Deva")[0].endswith("श")  # no stray final halant
    assert not texts("Ramprakash", "Deva")[0].endswith("्")
    assert texts("Tanuja", "Deva")[0].endswith("ा")  # final "a" is long
    assert texts("Pinki", "Deva")[0].endswith("ी")  # final "i" is long
    # medial vowel length is ambiguous: offered, not guessed
    assert texts("Vinita", "Deva")[:2] == ["विनिता", "विनीता"]
    assert all(c.method == "rules" for c in suggest("Vinita", "Deva"))


def test_rules_devanagari_to_latin_schwa_deletion() -> None:
    assert texts("नरोत्तम", "Latn")[0] == "Narottam"  # final schwa dropped
    assert texts("पुरुषोत्तम", "Latn")[0] == "Purushottam"
    assert texts("मिश्र", "Latn")[0] == "Mishra"  # kept after a conjunct
    assert texts("विमल", "Latn")[0] == "Vimal"
    assert texts("सरला", "Latn")[:2] == ["Sarla", "Sarala"]  # medial V-C-a-C-V, both offered
    assert texts("आकाश", "Latn")[0] == "Aakash"  # word-initial आ is "Aa"
    assert texts("रूपा", "Latn")[:2] == ["Rupa", "Roopa"]  # medial ऊ: u, or oo as an alternative


def test_nukta_and_marks() -> None:
    assert texts("ज़ुबैर", "Latn")[0].startswith("Z")
    assert texts("संतोष", "Latn")[0] == "Santosh"


def test_no_suggestion_rather_than_a_bad_one() -> None:
    assert suggest("", "Deva") == []
    assert suggest("Sunita", "Latn") == []  # already in the target script
    assert suggest("सुनीता", "Deva") == []
    assert suggest("சுனிதா", "Latn") == []  # Tamil: not in v1 (ADR-0025 §3)
    assert suggest("1234 --", "Deva") == []
    assert suggest("a" * (engine.MAX_TEXT + 1), "Deva") == []


def test_mixed_text_keeps_the_other_script_untouched() -> None:
    assert texts("Sunita शर्मा", "Deva")[0] == "सुनीता शर्मा"


def test_at_most_three_candidates_and_deterministic() -> None:
    for name, target in (("Vinita Ramprakash", "Deva"), ("सरला विमल", "Latn")):
        first = suggest(name, target)  # type: ignore[arg-type]
        assert 1 <= len(first) <= engine.MAX_CANDIDATES
        assert first == suggest(name, target)  # type: ignore[arg-type]
        assert len({c.text for c in first}) == len(first)


def test_lexicon_file_is_well_formed() -> None:
    raw = json.loads(engine._LEXICON_PATH.read_text(encoding="utf-8"))
    assert raw["licence"] and raw["source"] and "review" in raw["review_status"]
    assert len(raw["entries"]) >= 300
    for e in raw["entries"]:
        assert e["kind"] in ("given", "surname")
        assert e["latin"] and all(s.strip() == s and " " not in s and s[0].isupper() for s in e["latin"])
        assert e["deva"] == unicodedata.normalize("NFC", e["deva"]) and engine.script_of(e["deva"]) == "Deva"


# ------------------------------------------------------------------ API
def _tl(client: Any, text: str, target: str = "Deva") -> Any:
    return client.post("/transliterate", json={"text": text, "target_script": target})


def test_endpoint_needs_sign_in(client) -> None:
    assert _tl(client, "Sunita").status_code == 401


def test_endpoint_returns_labelled_candidates_and_versions(owner) -> None:
    r = _tl(owner, "Sunita Sharma")
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["candidates"][0] == {"text": "सुनीता शर्मा", "method": "lexicon"}
    assert body["engine"] == engine.ENGINE and body["version"] == engine.VERSION
    assert body["lexicon_version"] == engine.lexicon().version
    assert _tl(owner, "सुनीता", "Latn").json()["candidates"][0]["text"] == "Sunita"
    assert _tl(owner, "Sunita", "Latn").json()["candidates"] == []


def test_endpoint_validates_size_and_target(owner) -> None:
    assert _tl(owner, "").status_code == 422
    assert _tl(owner, "a" * (engine.MAX_TEXT + 1)).status_code == 422
    assert _tl(owner, "Sunita", "Taml").status_code == 422


def test_endpoint_is_rate_limited_per_user(owner, make_client) -> None:
    from app.modules.translit.router import RATE_LIMIT_PER_MINUTE

    codes = [_tl(owner, "Sunita").status_code for _ in range(RATE_LIMIT_PER_MINUTE + 1)]
    assert codes[:-1] == [200] * RATE_LIMIT_PER_MINUTE and codes[-1] == 429
    other = make_client()
    other.register(name="Other")
    assert _tl(other, "Sunita").status_code == 200  # per user, not global


def test_text_is_never_logged(owner, caplog) -> None:
    secret = "Zubairuddin Qadri"
    with caplog.at_level(logging.DEBUG):
        assert _tl(owner, secret).status_code == 200
        assert _tl(owner, secret + "x" * engine.MAX_TEXT).status_code == 422
    assert "Zubairuddin" not in caplog.text and "Qadri" not in caplog.text


# ------------------------------------------------------------------ accepting a suggestion
def test_accepted_suggestion_is_a_separate_calculated_then_confirmed_name(owner, tree) -> None:
    t = tree["id"]
    p = create_person(owner, t, "Sunita", "Sharma", status="deceased")
    r = owner.post(
        f"/trees/{t}/people/{p['id']}/names",
        json={
            "type": "transliteration",
            "given_name": "सुनीता",
            "surname": "शर्मा",
            "language": "hi",
            "script": "Deva",
            "suggestion": {"method": "lexicon"},
        },
    )
    assert r.status_code == 201, r.text
    name = r.json()
    assert name["is_preferred"] is False and name["evidence_status"] == "USER_ASSERTION"
    prov = name["provenance"]
    assert prov["origin"] == "calculation"
    assert prov["algorithm_or_model"] == f"{engine.ENGINE} {engine.VERSION} (lexicon)"
    assert prov["confirmed_by"] == owner.user["id"] and prov["confirmed_at"]
    # the typed name is untouched and still preferred
    person = owner.get(f"/trees/{t}/people/{p['id']}").json()
    assert person["display_name"].startswith("Sunita")
    typed = next(n for n in person["names"] if n["given_name"] == "Sunita")
    assert typed["is_preferred"] is True and typed["provenance"]["origin"] == "manual"
    # and search finds the person by the new spelling
    hits = owner.get(f"/trees/{t}/search", params={"q": "सुनीता"}).json()["hits"]
    assert p["id"] in {h["id"] for h in hits}


@pytest.mark.parametrize(
    "bad",
    [
        {"type": "birth"},
        {"is_preferred": True},
        {"evidence_status": "SOURCED"},
        {"suggestion": {"method": "magic"}},
    ],
)
def test_a_suggestion_cannot_be_dressed_up_as_something_else(owner, tree, bad: dict[str, Any]) -> None:
    t = tree["id"]
    p = create_person(owner, t, "Sunita", "Sharma", status="deceased")
    body = {
        "type": "transliteration",
        "given_name": "सुनीता",
        "script": "Deva",
        "language": "hi",
        "suggestion": {"method": "rules"},
        **bad,
    }
    assert owner.post(f"/trees/{t}/people/{p['id']}/names", json=body).status_code == 422


def test_suggested_name_on_person_create_and_cross_tree(owner, tree) -> None:
    t = tree["id"]
    body = person_body("Sunita", "Sharma")
    body["names"].append(
        {
            "type": "transliteration",
            "given_name": "सुनीता",
            "surname": "शर्मा",
            "language": "hi",
            "script": "Deva",
            "suggestion": {"method": "rules"},
        }
    )
    r = owner.post(f"/trees/{t}/people", json=body)
    assert r.status_code == 201, r.text
    deva = next(n for n in r.json()["names"] if n["script"] == "Deva")
    assert deva["provenance"]["algorithm_or_model"].endswith("(rules)")
    # a name record of this tree cannot be reached from another tree
    from tests.conftest import new_tree

    other = new_tree(owner, "Other family")
    assert owner.get(f"/trees/{other['id']}/people/{r.json()['id']}").status_code == 404


def test_viewer_cannot_save_a_suggested_name(owner, tree, member_factory) -> None:
    t = tree["id"]
    p = create_person(owner, t, "Sunita", "Sharma", status="deceased")
    viewer = member_factory(["VIEWER"])
    assert _tl(viewer, "Sunita").status_code == 200  # suggestions read no tree data
    r = viewer.post(
        f"/trees/{t}/people/{p['id']}/names",
        json={
            "type": "transliteration",
            "given_name": "सुनीता",
            "script": "Deva",
            "language": "hi",
            "suggestion": {"method": "lexicon"},
        },
    )
    assert r.status_code == 403
