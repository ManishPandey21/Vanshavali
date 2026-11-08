# Family calendar: licence and data-use evidence (ADR-0022 §1)

**Status: evidence prepared by the development team, 8 Nov 2026. NOT signed off.** Per the
product owner's decision of 8 Nov 2026, a qualified licensing reviewer signs this off and the
product owner then gives the final activation approval. Until a sign-off is recorded in
`backend/app/modules/calendar/data/approvals.json` (see
[family-calendar-approvals.md](family-calendar-approvals.md)), the code refuses every computed
lunar date. This document states facts and where they come from; it is not legal advice and
reaches no conclusion for the reviewer.

## 1. What runs and what ships

| Component | Version (pinned in `backend/uv.lock`) | Role | Shipped in the Docker image |
|---|---|---|---|
| Skyfield | 1.55 (sdist sha256 `05dce8aa…2fc14b`) | positions of Sun and Moon, sunrise and sunset | yes (pip package) |
| jplephem | 2.24 (sdist sha256 `354fe1ad…93bc11`) | reads the JPL SPK file | yes |
| sgp4 | 2.27 (sdist sha256 `06d37247…3985f9`) | a Skyfield dependency; not used by the calendar | yes |
| numpy | 2.4.6 on Python 3.11 (the image), 2.5.4 on 3.12+ | arrays | yes |
| certifi | 2026.10.23 | a Skyfield dependency (CA bundle) | yes |
| Skyfield's bundled data (`skyfield/data/`: `iers.npz`, `delta_t.npz`, `nutation.npz`, `historic_deltat.npy`, `morrison_stephenson_deltat.npy`, …) | as packaged in Skyfield 1.55 | ΔT and Earth orientation; the engine uses `timescale(builtin=True)`, so nothing is downloaded at run time | yes (inside the package) |
| JPL DE440s ephemeris, `de440s.bsp` | 32,726,016 bytes, SHA-256 `c1c7feeab882263fc493a9d5a5b2ddd71b54826cdf65d8d17a76126b260a49f2` | the ephemeris itself | yes: fetched **unmodified** at image build to `/app/ephemeris/de440s.bsp` and accepted only with that checksum (`backend/app/modules/calendar/ephemeris.py`); never committed to git |

### About the "18.5 MB excerpt"
During development an 18.5 MB excerpt of DE440s (a shorter date range) was tried as a way to keep
the file in git. **It was not adopted.** Nothing in the repository, its history, CI or the image
contains an excerpt or any modified ephemeris: the build downloads the original JPL file and
checks its SHA-256 (verified on 8 Nov 2026 with `git grep` and `git log --all -- '*.bsp'`). If an
excerpt is ever proposed again, it is a **material change**: it needs its own entry in this
document (how it was made, its SHA-256, and a statement that it is modified, as JPL asks below), a
new licence sign-off, and revalidation of every accuracy approval (the ephemeris checksum is part
of each approval and of `ENGINE_VERSION`).

## 2. Licence evidence for the libraries

Taken from each installed package's own metadata and licence file (Python 3.11 environment matching
the image), 8 Nov 2026:

| Package | Declared licence | Licence file in the wheel | Copyright line |
|---|---|---|---|
| skyfield 1.55 | `License: MIT`, classifier "OSI Approved :: MIT License" | `skyfield-1.55.dist-info/LICENSE` | "Copyright © 2013–2018 Brandon Rhodes and available under the MIT license" |
| jplephem 2.24 | `License: MIT` | `jplephem-2.24.dist-info/licenses/LICENSE.txt` | "Copyright 2012-2018 Brandon Rhodes" |
| sgp4 2.27 | `License-Expression: MIT` | `sgp4-2.27.dist-info/licenses/LICENSE` | "Copyright © 2012–2016 Brandon Rhodes" |
| numpy 2.4.6 | `License-Expression: BSD-3-Clause AND 0BSD AND MIT AND Zlib AND CC0-1.0` | `LICENSE.txt` plus bundled component licences (libdivide, highway, x86-simd-sort, dragon4, pythoncapi-compat, …) | per file |
| certifi 2026.10.23 | `License: MPL-2.0` | `certifi-2026.10.23.dist-info/licenses/LICENSE` | — |

Notes for the reviewer:
- MIT and BSD require the copyright and permission notices to be kept with copies of the software.
  The image keeps the packages' `dist-info` licence files as installed; whether that is sufficient,
  or a third-party notices file is needed, is the reviewer's call.
- certifi is MPL-2.0 (file-level copyleft); it is used unmodified.
- The Swiss Ephemeris (`pyswisseph`, AGPL-3.0) is **not** used (ADR-0022 §1).
- Skyfield's bundled data files are described by Skyfield as "third-party data that gets bundled
  with Skyfield" (`skyfield/data/__init__.py`). Their upstream terms (IERS and the ΔT sources) are
  **not yet documented here**; see open item L-3.

## 3. Data-use evidence for JPL DE440s

| Item | Evidence |
|---|---|
| Source | `https://ssd.jpl.nasa.gov/ftp/eph/planets/bsp/de440s.bsp`; the directory listing shows `de440s.bsp`, 2020-12-22 00:56, 31.2M (retrieved 8 Nov 2026) |
| Checksum | SHA-256 `c1c7feeab882263fc493a9d5a5b2ddd71b54826cdf65d8d17a76126b260a49f2`, size 32,726,016 bytes, pinned in `ephemeris.py` |
| Terms published by JPL | JPL Solar System Dynamics FAQ (`https://ssd.jpl.nasa.gov/faq.html`, retrieved 8 Nov 2026; page SHA-256 in `docs/release/evidence/calendar-2026-11-08/jpl-pages.sha256`): *"No permissions are needed. The data provided on this site are considered public domain. However, use of information from this site does not imply NASA/Caltech/JPL endorsement. We recommend a source citation such as: 'NASA/JPL Solar System Dynamics. Data retrieved on (Downloaded Year, Month, Date). (Title of the Page). https://ssd.jpl.nasa.gov' … If the data obtained is subsequently modified, that modification should be made clear."* |
| Fair-use policy | The FAQ refers to a "JPL Solar System Dynamics Fair Use Policy"; its link on the FAQ page is malformed (`https://https://ssd-api.jpl.nasa.gov/`), so its text was **not** retrieved. It concerns access to the site's network services; this project downloads one file once per image build. See open item L-4. |
| The ephemeris paper | As JPL's ephemeris page (`https://ssd.jpl.nasa.gov/planets/eph_export.html`) cites it: "Park et al., The JPL Planetary and Lunar Ephemerides DE440 and DE441, 2021, https://doi.org/10.3847/1538-3881/abd414" |
| Newer ephemerides | JPL published DE442 on 2026-07-15. This project stays pinned to DE440s; switching is a material change (new checksum, new sign-off, revalidation). |
| Other JPL README facts | `README.txt` in the same directory (2021-01-20) describes the DE440 file variants (Mars planet centre, TT−TDB, KBOs). Nothing in it addresses use or redistribution. |

### Proposed attribution (for the reviewer to approve or change)
Shown in the app's "About" / credits and in the calendar's operator documentation:

> Astronomical positions: NASA/JPL Solar System Dynamics, planetary ephemeris DE440s
> (Park et al. 2021, doi:10.3847/1538-3881/abd414), retrieved 2026-11-08 from
> https://ssd.jpl.nasa.gov, unmodified.
> Use does not imply NASA/Caltech/JPL endorsement. Computed with Skyfield (MIT) and jplephem (MIT).

The attribution is not shown in the UI yet: it should be added only in the form the reviewer approves
(open item L-5), and before activation.

## 4. Open items for the licensing reviewer

| # | Question | Evidence above |
|---|---|---|
| L-1 | Are the MIT/BSD/MPL obligations met by keeping the packages' licence files in the image, or is a third-party notices file needed (and should it ship with the web app as well)? | §2 |
| L-2 | Is redistributing the **unmodified** `de440s.bsp` inside the Docker image consistent with JPL's statement that the data are "considered public domain", with the attribution in §3? | §3 |
| L-3 | Terms of the third-party data bundled inside Skyfield 1.55 (`skyfield/data/`, IERS and ΔT sources). | §1, §2 |
| L-4 | Does the JPL SSD "Fair Use Policy" (text not retrievable from the FAQ link) add any condition for a one-off file download per build? | §3 |
| L-5 | Approve the attribution text and where it is shown. | §3 |
| L-6 | Confirm that Rashtriya Panchang values transcribed into the test table may be kept in the repository (see [family-calendar-sources.md](family-calendar-sources.md), item S-1). | sources inventory |

When signed off, the reviewer's record (name, role, date, the versions and checksum above) is added
to `approvals.json` as the `licence` entry in a reviewed change; see
[family-calendar-approvals.md](family-calendar-approvals.md).
