# Architecture Decision Records

Format: Status / Context / Decision / Consequences / Alternatives. Statuses go *Proposed →
Accepted → Superseded by NNNN*. Stress-test a new ADR against the requirements (PRS) before
accepting it. The superseded project-start drafts (typed edges, provenance, property) were folded
into 0003, 0009 and 0010.

| # | Title | Status |
|---|---|---|
| 0001 | [Application architecture: modular monolith, SPA + FastAPI](0001-application-architecture.md) | Accepted |
| 0002 | [PostgreSQL as the canonical store; tree = tenant](0002-database-choice.md) | Accepted |
| 0003 | [Genealogy relationship, event and assertion model](0003-genealogy-relationship-model.md) | Accepted |
| 0004 | [Document storage, scanning and encryption](0004-document-storage.md) | Accepted |
| 0005 | [Authentication: server-side sessions](0005-authentication.md) | Accepted |
| 0006 | [Authorisation and privacy evaluation](0006-authorization.md) | Accepted; amendment of 9 Nov 2026 (Family Admin nominations) Accepted |
| 0007 | [Search in PostgreSQL](0007-search.md) | Accepted |
| 0008 | [GEDCOM 7 interoperability and Indian extensions](0008-gedcom.md) | Accepted |
| 0009 | [OCR / AI extraction and provenance](0009-ocr-ai-provenance.md) | Accepted |
| 0010 | [Ancestral property model](0010-property-model.md) | Accepted |
| 0011 | [Onboarding, family-data attestation and shareable claim invites](0011-onboarding-attestation-claim-invites.md) | Accepted |
| 0012 | [Sign in with Google (OIDC) and forced password change](0012-google-sign-in.md) | Accepted |
| 0013 | [Importing photos with a GEDCOM file](0013-gedcom-photo-import.md) | Accepted |
| 0014 | [Pilot hosting: one VM with Docker Compose, managed PostgreSQL and S3, in India](0014-pilot-hosting.md) | Accepted (provider to confirm) |
| 0015 | [Important life events, geo-tagged places and event photo albums](0015-life-events-geotags-event-media.md) | Accepted |
| 0016 | [Event reminders and notification delivery (email, SMS, WhatsApp)](0016-reminders-and-notifications.md) | Accepted |
| 0017 | [Visualization data APIs and Remotion animated exports](0017-visualizations-and-animated-exports.md) | Accepted |
| 0018 | [Master data: controlled values vs extensible vocabularies](0018-master-data-vocabularies.md) | Accepted |
| 0019 | [Indian geography reference data (LGD) and place cascades](0019-india-geography-reference-lgd.md) | Accepted |
| 0020 | [Smart Add Relative, provisional people and recorded age order](0020-smart-add-relative-provisional-people-age-order.md) | Accepted |
| 0021 | [Change proposals, family review and duplicates at entry](0021-change-proposals-family-review.md) | Accepted |
| 0022 | [Indian family calendar: tithi dates, Punyatithi reminders, family calendar and ICS feed](0022-family-calendar-tithi-punyatithi.md) | Accepted |
| 0025 | [Name transliteration suggestions](0025-name-transliteration-suggestions.md) | Accepted |
| 0026 | [Cultural depth: pravara, devak and kuladevata, regional kinship packs, family traditions](0026-cultural-depth-heritage-vocabularies-kinship-packs-traditions.md) | Accepted |
| 0027 | [Record visibility and selective sharing for family media and records](0027-record-visibility-and-selective-sharing.md) | Accepted (implementation in progress) |
| 0029 | [Agent ticket factory (Infra Code Factory) for locally verified draft PRs](0029-agent-ticket-factory.md) | Proposed |
