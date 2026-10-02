"""Input the database cannot store is a client error, never a 500 (DAST finding, Oct 2026).

ZAP sent ``action=…%00…`` to the audit log filter; PostgreSQL rejects NUL in text, and the
psycopg DataError escaped as an unhandled 500. Every free-text input path is checked here.
"""

from __future__ import annotations

import pytest

from tests.helpers import create_person, person_body

NUL = "Ra\x00mesh"


@pytest.mark.parametrize(
    "path",
    [
        "/audit?action={v}",
        "/people?q={v}",
        "/search?q={v}&kinds=person",
        "/sources?q={v}",
        "/places?q={v}",
    ],
)
def test_nul_in_query_parameters_is_422_not_500(owner, tree, path):
    url = f"/trees/{tree['id']}" + path.format(v="Ra%00mesh")
    r = owner.get(url)
    assert r.status_code in (200, 404, 422), (url, r.status_code, r.text[:200])
    if r.status_code == 422:
        assert r.json()["error"]["code"] in ("invalid_input", "validation_error")
        assert "\x00" not in r.text  # the offending input is not echoed back


def test_nul_in_a_json_body_is_422_and_the_session_recovers(owner, tree):
    t = tree["id"]
    r = owner.post(f"/trees/{t}/people", json=person_body(NUL))
    assert r.status_code == 422, r.text
    assert r.json()["error"]["code"] in ("invalid_input", "validation_error")
    # the failed transaction was rolled back: the same client keeps working
    p = create_person(owner, t, "Ramesh")
    assert owner.get(f"/trees/{t}/people/{p['id']}").status_code == 200
