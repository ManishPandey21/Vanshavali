# Geography fixture (SYNTHETIC)

**These files are synthetic.** They follow the published column layouts of the Local Government
Directory (LGD) downloads and the India Post "All India Pincode Directory", but the codes, PIN
offices and village list are made up for tests. Names of real states and districts are used only so
the cascade reads naturally; the LGD codes (99xx…) are not real LGD codes. Do not load them into a
pilot or production database.

Why synthetic: LGD's download directory is a session form with a captcha and data.gov.in is not
reachable from the build environment (ADR-0019, implementation note). Replacing these with a real
one-district extract under GODL-India, downloaded by hand, is a tracked follow-up.

What they exercise (ADR-0019 §Consequences):

| Snapshot | Change |
|---|---|
| 2026-02 | 2 states, 2 districts, 3 sub-districts, 6 villages, 1 urban body, 5 PIN offices; one office's district (Kaushambi) is not in the data |
| 2026-05 | district 9901 renamed Allahabad → Prayagraj; village 9900003 Bhagwatpur split into 9900007 and 9900008 (`successors.csv`); PIN offices now list Prayagraj |

Load them (from `backend/`):

```
uv run python -m app.cli.geo import --stage 1 --snapshot 2026-02 --file tests/fixtures/geo/2026-02/states.csv --sha256 … …
```

`e2e/global-setup` and `tests/test_geo.py` do this with the checksums computed on the fly.
