# Edge test: deploy/pilot/Caddyfile (2 Oct 2026, sandbox)

Setup:
- Caddy v2.10.2 (release tarball, sha512 verified against `caddy_2.10.2_checksums.txt`) running
  `deploy/pilot/Caddyfile` with `VSH_DOMAIN=pilot.test VSH_TLS=internal`, on a Docker network
  `172.30.0.0/24` with Caddy at `172.30.0.10`.
- Upstreams: two `backend` replicas (nginx stand-ins under the `backend` alias, so `dynamic a`
  sees two addresses) and the frontend image.
- For the body-limit test the stand-ins proxied to a server that **reads the whole body**: an
  upstream that answers without reading never triggers the limit.

| # | Check | Result |
|---|---|---|
| 1 | `http://pilot.test/trees` | `308` → `https://pilot.test/trees` |
| 2 | `GET /` over TLS | TLS 1.3, HTTP/2 200; `content-security-policy` (nginx), `strict-transport-security: max-age=63072000; includeSubDomains`, `x-frame-options: DENY`; no `Server` header |
| 3 | Client sends `X-Forwarded-For: 203.0.113.66` to `/api/v1/health` (4 requests) | upstream saw `xff=<the client address Caddy saw>`, `peer=172.30.0.10`; spoofed value dropped; requests alternated between the two replicas |
| 4 | Body limits, `/api/v1/trees/x/documents` | 50 MB → 201; 60 MB → **413** |
| 5 | Body limits, `/api/v1/trees/x/imports` | 60 MB → 201 (0.17 s); 250 MB → 201 (0.99 s); 270 MB → **413** |
| 6 | Unknown host (SNI `other.test`) | TLS handshake refused (no certificate, no default site) |

Also in this test: frontend `nginx.conf` before/after the import-limit fix (nginx 1.27):
- 70 MB to `/api/v1/trees/abc/imports`: 413 with the old config, 201 with the new one.
- 70 MB to `/documents`: still 413.

The same Caddyfile then served the full drill stack (`drill-2026-10-02.md`): real backend and
worker containers and the 13-step smoke test through it.
