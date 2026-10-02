"""Post-deployment smoke test over real HTTP (docs/operations/release-runbook.md).

    SMOKE_PASSWORD=... python -m app.cli.smoke --base-url https://pilot.example.org --email smoke@example.org
    SMOKE_PASSWORD=... python -m app.cli.smoke ... --keep --tree-name "Restore drill"   # leave the data
    SMOKE_PASSWORD=... python -m app.cli.smoke ... --verify-existing "Restore drill"    # after a restore

Full mode, in order:
- health and readiness (RLS in force);
- the SPA shell with its CSP;
- log in;
- create a tree;
- add two people and a parent link;
- the tree loads (family and descendants);
- upload a photo;
- import a GEDZIP package (with a photo), read the import report, commit;
- create a property;
- upload a property document;
- log out and log back in;
- check that everything is still there, and that both files download with the checksum the server
  recorded.

Finally the smoke tree is deleted (unless ``--keep``).

``--verify-existing NAME`` checks a tree a previous ``--keep`` run created (people, property,
documents downloadable with matching checksums, GEDCOM export, audit trail) without writing
anything except the login itself. Use it to verify a restore.

Uses only synthetic data ("Smoke" family, generated images). Needs a verified account dedicated to
smoke tests; its password comes from ``SMOKE_PASSWORD``, never from the command line. Only the
standard library is used, so it runs from the production image or any Python 3.11.
Exit status 0 means every step passed.
"""

from __future__ import annotations

import argparse
import hashlib
import http.cookiejar
import io
import json
import os
import ssl
import struct
import sys
import time
import urllib.error
import urllib.request
import uuid
import zipfile
import zlib
from typing import Any
from urllib.parse import urljoin

API = "/api/v1"


class SmokeFailure(Exception):
    pass


def png(width: int = 64, height: int = 48, rgb: tuple[int, int, int] = (180, 120, 60)) -> bytes:
    """A valid, solid-colour PNG (no external imaging library needed)."""

    def chunk(kind: bytes, data: bytes) -> bytes:
        return struct.pack(">I", len(data)) + kind + data + struct.pack(">I", zlib.crc32(kind + data))

    row = b"\x00" + bytes(rgb) * width
    raw = zlib.compress(row * height)
    header = struct.pack(">IIBBBBB", width, height, 8, 2, 0, 0, 0)
    return b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", header) + chunk(b"IDAT", raw) + chunk(b"IEND", b"")


def gedzip(photo: bytes, tag: str) -> bytes:
    ged = (
        "0 HEAD\n1 GEDC\n2 VERS 7.0\n1 CHAR UTF-8\n"
        f"0 @I1@ INDI\n1 NAME Imported /Smoke{tag}/\n1 SEX M\n1 DEAT Y\n1 FAMS @F1@\n"
        "1 OBJE\n2 FILE media/imported.png\n3 FORM image/png\n"
        f"0 @I2@ INDI\n1 NAME Imported Child /Smoke{tag}/\n1 SEX F\n1 DEAT Y\n1 FAMC @F1@\n"
        "0 @F1@ FAM\n1 HUSB @I1@\n1 CHIL @I2@\n0 TRLR\n"
    )
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as z:
        z.writestr("gedcom.ged", ged)
        z.writestr("media/imported.png", photo)
    return buf.getvalue()


class Http:
    def __init__(self, base_url: str, ca_file: str | None, timeout: float) -> None:
        self.base = base_url.rstrip("/")
        self.jar = http.cookiejar.CookieJar()
        ctx = ssl.create_default_context(cafile=ca_file) if ca_file else ssl.create_default_context()
        self.opener = urllib.request.build_opener(
            urllib.request.HTTPCookieProcessor(self.jar),
            urllib.request.HTTPSHandler(context=ctx),
            urllib.request.ProxyHandler({}),  # talk to the deployment directly
        )
        self.timeout = timeout

    def _csrf(self) -> str | None:
        return next((c.value for c in self.jar if c.name == "vsh_csrf"), None)

    def call(
        self,
        method: str,
        path: str,
        *,
        json_body: Any = None,
        form: dict[str, str] | None = None,
        file: tuple[str, bytes, str] | None = None,
        expect: tuple[int, ...] = (200,),
    ) -> tuple[int, dict[str, str], bytes]:
        url = path if path.startswith("http") else urljoin(self.base + "/", path.lstrip("/"))
        headers = {"Accept": "application/json"}
        data: bytes | None = None
        if json_body is not None:
            data = json.dumps(json_body).encode()
            headers["Content-Type"] = "application/json"
        elif file is not None:
            boundary = uuid.uuid4().hex
            parts = []
            for k, v in (form or {}).items():
                parts.append(
                    f'--{boundary}\r\nContent-Disposition: form-data; name="{k}"\r\n\r\n{v}\r\n'.encode()
                )
            name, content, mime = file
            parts.append(
                f'--{boundary}\r\nContent-Disposition: form-data; name="file"; filename="{name}"\r\n'
                f"Content-Type: {mime}\r\n\r\n".encode()
                + content
                + b"\r\n"
            )
            parts.append(f"--{boundary}--\r\n".encode())
            data = b"".join(parts)
            headers["Content-Type"] = f"multipart/form-data; boundary={boundary}"
        if method not in ("GET", "HEAD") and (token := self._csrf()):
            headers["X-CSRF-Token"] = token
        req = urllib.request.Request(url, data=data, method=method, headers=headers)  # noqa: S310 - https/http only
        try:
            with self.opener.open(req, timeout=self.timeout) as resp:
                status, hdrs, body = resp.status, dict(resp.headers.items()), resp.read()
        except urllib.error.HTTPError as err:
            status, hdrs, body = err.code, dict(err.headers.items()), err.read()
        if status not in expect:
            raise SmokeFailure(f"{method} {path} -> {status} (expected {expect}): {body[:300]!r}")
        return status, {k.lower(): v for k, v in hdrs.items()}, body

    def json(self, method: str, path: str, **kw: Any) -> Any:
        _, _, body = self.call(method, path, **kw)
        return json.loads(body) if body else None


class Smoke:
    def __init__(self, http: Http, email: str, password: str, scan_timeout: float) -> None:
        self.http, self.email, self.password, self.scan_timeout = http, email, password, scan_timeout
        self.results: list[dict[str, Any]] = []

    def step(self, name: str, fn: Any) -> Any:
        t0 = time.perf_counter()
        try:
            out = fn()
        except Exception as exc:
            self.results.append({"step": name, "ok": False, "ms": _ms(t0), "error": str(exc)[:500]})
            print(f"[FAIL] {name}: {exc}")
            raise
        self.results.append({"step": name, "ok": True, "ms": _ms(t0)})
        print(f"[PASS] {name} ({_ms(t0)} ms)")
        return out

    # ---- shared steps
    def health(self) -> None:
        self.http.call("GET", f"{API}/health")
        ready = self.http.json("GET", f"{API}/health/ready")
        if ready.get("checks", {}).get("rls") != "enforced":
            raise SmokeFailure(f"readiness does not report RLS enforced: {ready}")

    def spa(self) -> None:
        _, hdrs, body = self.http.call("GET", "/login")
        if b'id="root"' not in body or "default-src 'self'" not in hdrs.get("content-security-policy", ""):
            raise SmokeFailure("the SPA shell or its Content-Security-Policy is missing")

    def login(self) -> dict[str, Any]:
        self.http.call("GET", f"{API}/auth/providers")  # sets the CSRF cookie
        self.http.call(
            "POST", f"{API}/auth/login", json_body={"email": self.email, "password": self.password}
        )
        me: dict[str, Any] = self.http.json("GET", f"{API}/auth/me")
        if me.get("must_change_password"):
            raise SmokeFailure("the smoke account must change its password first; sign in once in the UI")
        return me

    def logout_and_login(self) -> None:
        self.http.call("POST", f"{API}/auth/logout")
        self.http.call("GET", f"{API}/auth/me", expect=(401,))
        self.login()

    def wait_clean(self, tree: str, doc_id: str) -> dict[str, Any]:
        deadline = time.monotonic() + self.scan_timeout
        while True:
            doc: dict[str, Any] = self.http.json("GET", f"{API}/trees/{tree}/documents/{doc_id}")
            if doc["scan_status"] == "clean":
                return doc
            if doc["scan_status"] in ("infected", "error"):
                raise SmokeFailure(f"document {doc_id} scan_status={doc['scan_status']}")
            if time.monotonic() > deadline:
                raise SmokeFailure(f"document {doc_id} still {doc['scan_status']} after {self.scan_timeout}s")
            time.sleep(2)

    def download_matches(self, tree: str, doc: dict[str, Any]) -> None:
        url = self.http.json("POST", f"{API}/trees/{tree}/documents/{doc['id']}/download-url")["url"]
        _, _, body = self.http.call("GET", url)
        if hashlib.sha256(body).hexdigest() != doc["checksum_sha256"]:
            raise SmokeFailure(f"document {doc['id']} downloaded with a different checksum")

    # ---- full run
    def full(self, tree_name: str, keep: bool) -> None:
        tag = uuid.uuid4().hex[:6]
        self.step("1 health and readiness (RLS enforced)", self.health)
        self.step("2 SPA login page and CSP", self.spa)
        self.step("3 log in with the smoke account", self.login)

        def create_tree() -> str:
            tree = self.http.json("POST", f"{API}/trees", json_body={"name": tree_name}, expect=(201,))
            stmt = self.http.json("GET", f"{API}/consent-statements/family_data?lang=en")
            self.http.call(
                "POST",
                f"{API}/trees/{tree['id']}/attestation",
                json_body={"statement_version": stmt["version"], "language": "en"},
                expect=(201,),
            )
            return str(tree["id"])

        t = self.step("4 create a tree", create_tree)

        def add_people() -> tuple[str, str]:
            def person(given: str) -> str:
                body = {
                    "profile_status": "deceased",
                    "names": [{"given_name": given, "surname": f"Smoke{tag}", "is_preferred": True}],
                }
                return str(
                    self.http.json("POST", f"{API}/trees/{t}/people", json_body=body, expect=(201,))["id"]
                )

            parent, child = person("Parent"), person("Child")
            self.http.call(
                "POST",
                f"{API}/trees/{t}/relationships",
                json_body={"person_a_id": parent, "person_b_id": child, "type": "biological_parent"},
                expect=(201,),
            )
            return parent, child

        parent, child = self.step("5 add people and a parent link", add_people)

        def tree_loads() -> None:
            fam = self.http.json("GET", f"{API}/trees/{t}/people/{child}/family")
            desc = self.http.json("GET", f"{API}/trees/{t}/people/{parent}/descendants")
            if child not in json.dumps(desc) or parent not in json.dumps(fam):
                raise SmokeFailure("family/descendants do not show the new link")

        self.step("6 family tree loads", tree_loads)
        photo_bytes = png()

        def upload_photo() -> dict[str, Any]:
            doc = self.http.json(
                "POST",
                f"{API}/trees/{t}/documents",
                form={
                    "category": "photo",
                    "title": "Smoke photo",
                    "link_target_type": "person",
                    "link_target_id": parent,
                },
                file=("smoke-photo.png", photo_bytes, "image/png"),
                expect=(201,),
            )
            return self.wait_clean(t, doc["id"])

        photo = self.step("7 upload a photo (scanned clean)", upload_photo)

        def import_gdz() -> dict[str, Any]:
            return self.http.json(
                "POST",
                f"{API}/trees/{t}/imports",
                file=("smoke.gdz", gedzip(png(rgb=(40, 90, 160)), tag), "application/zip"),
                expect=(201,),
            )

        job = self.step("8 upload a GEDZIP package", import_gdz)

        def import_report() -> None:
            j = self.http.json("GET", f"{API}/trees/{t}/imports/{job['id']}")
            if j["status"] != "ready" or j["report"].get("photos", {}).get("matched", 0) < 1:
                raise SmokeFailure(
                    f"import not ready or photo unmatched: status={j['status']} report={j['report']}"
                )
            c = self.http.json(
                "POST", f"{API}/trees/{t}/imports/{job['id']}/commit", json_body={"decisions": {}}
            )
            if c["status"] != "committed":
                raise SmokeFailure(f"import commit status {c['status']}")

        self.step("9 import report reviewed and committed", import_report)

        def create_property() -> str:
            body = {
                "property_type": "agricultural_land",
                "classification": "ancestral",
                "display_name": f"Smoke khet {tag}",
            }
            return str(
                self.http.json("POST", f"{API}/trees/{t}/properties", json_body=body, expect=(201,))["id"]
            )

        prop = self.step("10 create a property", create_property)

        def upload_property_doc() -> dict[str, Any]:
            doc = self.http.json(
                "POST",
                f"{API}/trees/{t}/documents",
                form={
                    "category": "khatauni",
                    "title": "Smoke khatauni",
                    "link_target_type": "property",
                    "link_target_id": prop,
                },
                file=("smoke-khatauni.png", png(rgb=(10, 140, 10)), "image/png"),
                expect=(201,),
            )
            return self.wait_clean(t, doc["id"])

        pdoc = self.step("11 upload a property document (scanned clean)", upload_property_doc)
        self.step("12 log out and log back in", self.logout_and_login)

        def persisted() -> None:
            people = self.http.json("GET", f"{API}/trees/{t}/people?limit=50")["items"]
            surnames = json.dumps(people)
            if surnames.count(f"Smoke{tag}") < 4:  # 2 added + 2 imported
                raise SmokeFailure(
                    f"expected 4 smoke people after re-login, found {surnames.count(f'Smoke{tag}')}"
                )
            self.http.json("GET", f"{API}/trees/{t}/properties/{prop}")
            self.download_matches(t, photo)
            self.download_matches(t, pdoc)

        self.step("13 data persists after re-login; files download intact", persisted)
        if not keep:
            self.step("cleanup: delete the smoke tree", lambda: self.http.call("DELETE", f"{API}/trees/{t}"))

    # ---- verify an existing tree (after a restore)
    def verify_existing(self, tree_name: str) -> None:
        self.step("1 health and readiness (RLS enforced)", self.health)
        self.step("2 SPA login page and CSP", self.spa)
        self.step("3 log in with the smoke account", self.login)

        def find_tree() -> str:
            trees = self.http.json("GET", f"{API}/trees")
            items = trees["items"] if isinstance(trees, dict) else trees
            match = [x for x in items if x["name"] == tree_name]
            if not match:
                raise SmokeFailure(f"tree {tree_name!r} not found for this account")
            return str(match[0]["id"])

        t = self.step("4 the tree exists", find_tree)

        def people() -> None:
            items = self.http.json("GET", f"{API}/trees/{t}/people?limit=50")["items"]
            if len(items) < 4:
                raise SmokeFailure(f"expected at least 4 people, found {len(items)}")

        self.step("5 people restored", people)

        def properties() -> None:
            items = self.http.json("GET", f"{API}/trees/{t}/properties")
            items = items["items"] if isinstance(items, dict) else items
            if not items:
                raise SmokeFailure("no property restored")

        self.step("6 property records restored", properties)

        def documents() -> None:
            docs = self.http.json("GET", f"{API}/trees/{t}/documents?limit=50")["items"]
            if len(docs) < 2:
                raise SmokeFailure(f"expected at least 2 documents, found {len(docs)}")
            for d in docs:
                self.download_matches(t, d)

        self.step("7 photos and documents download with matching checksums", documents)

        def export() -> None:
            _, _, body = self.http.call("GET", f"{API}/trees/{t}/exports/gedcom?exclude_living=false")
            if b"0 HEAD" not in body or b"INDI" not in body:
                raise SmokeFailure("GEDCOM export is not a GEDCOM file")

        self.step("8 GEDCOM export", export)

        def audit() -> None:
            events = self.http.json("GET", f"{API}/trees/{t}/audit?limit=200")
            items = events["items"] if isinstance(events, dict) else events
            actions = {e.get("action") for e in items}
            if "tree.created" not in actions:
                raise SmokeFailure(f"audit trail is missing tree.created (found {sorted(actions)[:10]})")

        self.step("9 audit trail present", audit)


def _ms(t0: float) -> int:
    return round((time.perf_counter() - t0) * 1000)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--base-url", required=True)
    ap.add_argument("--email", default=os.environ.get("SMOKE_EMAIL"), help="default: $SMOKE_EMAIL")
    ap.add_argument(
        "--tree-name", default=None, help="name of the tree to create (default: Smoke <timestamp>)"
    )
    ap.add_argument("--keep", action="store_true", help="leave the smoke tree in place")
    ap.add_argument("--verify-existing", metavar="TREE_NAME", help="verify a tree a --keep run created")
    ap.add_argument("--ca-file", help="trust this CA (drills with an internal CA)")
    ap.add_argument("--scan-timeout", type=float, default=240.0, help="seconds to wait for malware scanning")
    ap.add_argument("--timeout", type=float, default=60.0)
    ap.add_argument("--report", help="write the step results as JSON here")
    args = ap.parse_args(argv)
    password = os.environ.get("SMOKE_PASSWORD")
    if not args.email:
        ap.error("--email or SMOKE_EMAIL is required")
    if not password:
        print("SMOKE_PASSWORD is not set", file=sys.stderr)
        return 2
    smoke = Smoke(Http(args.base_url, args.ca_file, args.timeout), args.email, password, args.scan_timeout)
    t0 = time.perf_counter()
    ok = True
    try:
        if args.verify_existing:
            smoke.verify_existing(args.verify_existing)
        else:
            name = args.tree_name or f"Smoke {time.strftime('%Y-%m-%d %H:%M:%S', time.gmtime())}"
            smoke.full(name, args.keep)
    except Exception:
        ok = False
    total = _ms(t0)
    print(
        f"{'PASSED' if ok else 'FAILED'}: {sum(r['ok'] for r in smoke.results)}/{len(smoke.results)} steps in {total} ms"
    )
    if args.report:
        with open(args.report, "w", encoding="utf-8") as f:
            json.dump(
                {"ok": ok, "total_ms": total, "base_url": args.base_url, "steps": smoke.results}, f, indent=1
            )
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
