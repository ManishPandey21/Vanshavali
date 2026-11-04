# Open questions (requirements review)

> **Update (PRS v1.0 received):** Q1 (FastAPI + Alembic + PostgreSQL), Q2 (invite-only, public is
> deceased-only), Q3 (multiple unions, adoption incl. *dattak*), Q4 (jati optional and highly
> private), Q5 (matrilineal/bilateral descent rules), Q7 (no external AI by default), Q9 (Kundli
> as evidence, calculation deferred), Q10 (no Aadhaar storage) and Q11 (10k people per tree) are
> now **resolved** by the PRS and ADRs 0001–0010. **Still open:** Q6 (which regional calendars
> beyond Gregorian/Julian/Vikram Samvat/Shaka), Q8 (UI languages beyond en/hi), Q12 (hosting
> region and RPO/RTO). None of these block development.
>
> **Update (Oct 2026, pilot):** Q12's topology is decided by ADR-0014: an Indian region, one VM,
> managed PostgreSQL and S3. The provider account and the RPO/RTO targets still need the owner's
> confirmation. The proposed targets, and the drill that measures them, are in
> `docs/operations/backup-restore-runbook.md`.

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
| Q13 | **Lawful basis for living relatives who never claim their profile** (DPDP Act 2023 s.4–s.7). The onboarding checkbox (ADR-0011) records the entering user's confirmation, not the relative's consent. Also: legal review of the notice/attestation wording and its Hindi translation. | The platform is a Data Fiduciary. Self-attestation is not s.6 consent. The household-purpose exemption (s.3(c)(i)) covers the individual user, not the platform. | Private-by-default trees; living people hidden from everyone but members; attestation recorded per contributor; relatives get real notice and consent when they claim, and can restrict or erase their profile. Needs counsel's sign-off before a public launch. |
| Q14 | Which regional kinship vocabularies come after Hindi, and who reviews them? ([plan](india-master-data-and-smart-forms-plan.md) Phase C) | Wrong kinship words undermine trust in the core feature. | Hindi first (North-Indian set), then Marathi, Gujarati, Punjabi, Bengali, Tamil, Telugu, Kannada, Malayalam, each marked `draft` until a native speaker reviews it. |
| Q15 | LGD and India Post refresh cadence; are pre-1947 district boundaries needed? (Phase B) | Decides import tooling and how historical places are linked. | Quarterly LGD snapshot; pre-1947 places stay free text with a historical-name flag. |
| Q16 | Panchang engine licence: Swiss Ephemeris (AGPL or commercial) or an own implementation? (Phase H) | Tithi reminders need an astronomical engine; AGPL affects the whole backend. | Evaluate a permissively licensed algorithm first; no tithi reminders until decided. |
| Q17 | Speech-to-text for elders' voice notes: self-hosted only, or BHASHINI as an opt-in provider? Raw-audio retention? (Phase I) | External processing of voice data (Q7, DPDP). | Self-hosted only; raw audio kept until the family deletes it; transcripts are proposals. |
| Q18 | Is matrimonial biodata in scope for the pilot audience? (Phase M) | Consent and misuse risk (caste/gotra matching). | Out of scope until P2; never any compatibility scoring. |
| Q19 | Product name: an external review calls the product "Parampara"; the repo and UI say "Vanshavali", and vanshavali.net.in is another product. | Branding, domain and trademark before public launch. | Keep "Vanshavali" in code and UI until the owner decides. |
