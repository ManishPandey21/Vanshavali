# Open questions (requirements review)

> **Update (PRS v1.0 received):** Q1 (FastAPI + Alembic + PostgreSQL), Q2 (invite-only, public is
> deceased-only), Q3 (multiple unions, adoption incl. *dattak*), Q4 (jati optional and highly
> private), Q5 (matrilineal/bilateral descent rules), Q7 (no external AI by default), Q9 (Kundli
> as evidence, calculation deferred), Q10 (no Aadhaar storage) and Q11 (10k people per tree) are
> now **resolved** by the PRS and ADRs 0001–0010. **Still open:** Q6 (which regional calendars
> beyond Gregorian/Julian/Vikram Samvat/Shaka), Q8 (UI languages beyond en/hi), Q12 (hosting
> region and RPO/RTO). None of these block development.

These came out of a grill-me style review at project start. Each one blocks or shapes an ADR.
Record the owner's answer here and update the ADR it affects.

| # | Question | Why it matters | Default assumed until answered |
|---|---|---|---|
| Q1 | **Backend stack:** custom API (e.g. FastAPI + SQLAlchemy + Alembic) or Supabase (Postgres + Auth + RLS + Storage)? `@supabase/supabase-js` is installed but unused. | Decides the migration tooling, where authorisation lives and how auth works. The working-methods brief mentions Alembic. | Custom Python API with Alembic, on plain Postgres. |
| Q2 | **Who uses it?** A private family tool (invite-only) or a platform with public trees and search? | Public trees widen the threat model a lot (scraping, living-person leakage). | Invite-only. Public view is opt-in per tree, and deceased people only. |
| Q3 | Must we model polygamous marriages, levirate/niyoga, and adoption within the gotra (dattak)? | Affects relationship constraints and tree layout. | Yes: several spouse edges, each with order and status, plus adoptive and dattak subtypes. |
| Q4 | Should caste/jati be stored at all? If it is, who can see it? | It is sensitive, and the DPDP Act 2023 raises consent and purpose-limitation concerns. It could also be misused for discrimination. | Optional field. Private to tree members, never shown in public views or exports unless the owner allows it. |
| Q5 | Do we need to support matrilineal systems (Marumakkathayam/tharavad, Khasi)? | Changes how branches and inheritance work, not just a label. | Yes, as a branch-level `descent_rule` (patrilineal/matrilineal/bilateral). |
| Q6 | Which calendars must date entry support: Vikram Samvat, Shaka, Bengali, Tamil, Malayalam (Kollam)? Do we need tithi? | Affects the GenealogicalDate design and the Kundli review UI. | Gregorian and Vikram Samvat at launch. The original text is always kept. |
| Q7 | Is sending documents to external OCR/AI providers acceptable? If so, where may the data be processed? | Privacy, cost and data residency. | Opt-in per tree. Self-hosted OCR (Tesseract with Indic language packs) is the default. |
| Q8 | Which UI languages at launch? Should the names of Indian states be written in the local scripts? | Affects i18n, fonts and search (transliteration). | English and Hindi UI. Names can be entered in any script, with search across Latin transliteration. |
| Q9 | Is a Kundli/Janampatri an evidence document only, or do we compute charts? | Computing charts means a new domain and new liability. | Evidence only. Birth time, place and nakshatra are extracted as proposals. |
| Q10 | Should property records hold owners' identity numbers (Aadhaar, PAN)? | Very high risk. | **No.** Aadhaar numbers are rejected or masked on upload review. |
| Q11 | Target tree size? | Decides whether the tree needs virtualised rendering and how recursive queries must be tuned. | 10k people per tree, with rendering capped at a 500-node viewport. |
| Q12 | Hosting and data residency (only in India)? | DPDP Act, cost, choice of object storage. | Region ap-south-1 or an equivalent Indian region. |
