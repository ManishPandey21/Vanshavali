# Privacy model

Status: baseline written at project start. Enforcement happens **on the server**. The UI hides
things only for convenience and is never the control.

## 1. Principles
1. **Living people are private by default.** If `living_status` is `unknown` and the person was
   born less than 110 years ago, or their birth date is unknown, they are treated as living.
2. **Least visibility.** Being able to see a person does not mean you can see their sensitive facts
   or documents.
3. **Minors (under 18) are always private.** They never appear in public views, share links or
   public exports, whatever the tree settings say.
4. **Consent and purpose (DPDP Act 2023).** A living adult can ask to view, correct or be removed
   from a tree. Removal redacts the person's details and keeps a placeholder, so the tree's shape
   doesn't break.
5. **Data minimisation.** We don't collect government ID numbers (Aadhaar or PAN). See Q10.

## 2. Sensitivity classes

| Class | Examples | Default visibility |
|---|---|---|
| S0 Public-safe | Deceased person's name, years, place, relationships | Tree members, and the public view if the tree has turned it on |
| S1 Family | Living person's name and relationships, photos, occupation | Tree members only |
| S2 Sensitive | Exact birth date/time/place of living people, nakshatra/rashi, caste/jati, notes, contact details | Tree members with the `editor` role or higher, plus the person themselves |
| S3 Restricted | Birth certificates, Kundli, medical notes, **all property documents and parcels**, wills | `owner` and `property_manager`, or a per-document grant |

## 3. Enforcement points
- **Serialisers** remove fields the caller isn't allowed to see. A living person in a public or
  share-link context comes back as `{id, display: "Living person", relationships}`.
- **Search** indexes only fields visible to the caller's role, or filters results after the query
  by role. Results never reveal a hidden match (no counts, no snippets).
- **Exports** (GEDCOM or PDF) apply the exporting user's view. A public export removes S1–S3 data and
  anyone who is living.
- **Share links** are scoped to one tree and one view (`public-safe`), expire, can be revoked, and
  are stored as hashed tokens.
- **Audit log** records every S3 read or download and every privacy-setting change.

## 4. Known gaps in the current prototype
- `AddPerson` defaults `isPrivate: false` for a new living person. This should be private by
  default (architecture README F4).
- `isPrivate` is only displayed, never enforced (F5). That's acceptable until a backend exists.
