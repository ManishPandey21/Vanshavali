# ADR-0013: Importing photos with a GEDCOM file

- Status: Accepted · Date: 2026-09-26
- Relates to: ADR-0004 (document storage, scanning, encryption), ADR-0008 (GEDCOM), ADR-0006 (authorisation)

## Context
Family-tree apps export the tree as a `.ged` file and the photos as a separate folder. For example,
MyHeritage Family Tree Builder writes `Pandey Family Tree.ged` next to `Pandey Family Tree_Photos/`.
Inside the `.ged`, each person's `OBJE` points at a photo by an absolute path on the exporter's
computer (`FILE C:\Users\…\Pandey Family Tree_Photos\P500001_3648_2451.jpg`). GEDCOM 7 defines GEDZIP
(`.gdz`): a zip with `gedcom.ged` at the root and media referenced by relative paths.

Until now the importer rejected zip uploads, and only counted `OBJE` references (`media_refs`).
Users lost every photo on import.

## Decision

### Package upload
- The GEDCOM upload also accepts a **zip**: a GEDZIP (`.gdz`), or an ordinary `.zip` holding one
  `.ged` file and its photos in any folders.
- **Nothing is ever extracted to disk.** Members are read into memory one at a time, with bounded
  reads. This zip safety is enforced before any member is used:
  - at most 5,000 entries;
  - total uncompressed size no more than `max_gedcom_package_bytes` (default 250 MB);
  - each photo no more than `max_upload_bytes`;
  - a compression ratio above 100:1 is refused as a zip bomb;
  - encrypted entries, and nested archives, are ignored;
  - member names are only used for matching, never as filesystem paths, so path traversal is
    moot.
- **The `.ged` file inside:** `gedcom.ged` at the root if present, otherwise the only `.ged`/`.gedcom`
  file. More than one candidate gives `422 multiple_gedcom`; none gives `422 no_gedcom_in_package`.
- The whole package is stored as the import's immutable original (ADR-0008 "keep the original").
  It is encrypted with the STANDARD key, like a `.ged`.

### Matching photos to people
- The stager records each person's `OBJE` photos: inline `OBJE`, or a pointer to a top-level
  `OBJE` record, with every `FILE`, plus `TITL` and `FORM`.
- A `FILE` is matched to a package member in two steps:
  1. by normalised relative path, which is what GEDZIP uses;
  2. otherwise by its **file name** (case-insensitive, after dropping any drive, absolute folders and
     `file://`), which is what MyHeritage's absolute Windows paths need.
- Two members with the same file name are only used if the `FILE` path picks one uniquely.
  Otherwise the photo is reported as ambiguous and skipped.
- The upload report lists how many photos were matched, which are missing from the package, and
  which are ambiguous. It gives names only, never contents.
- Photos on records that are not people (e.g. MyHeritage's "Unassociated photos" album, which
  ADR-0008's photo-container rule already skips) are **not imported**, and are counted as
  `photos_unlinked`.

### Commit
- For every **newly created** person, each matched photo goes through the **normal document upload
  pipeline** (ADR-0004), exactly like a photo uploaded by hand:
  magic-byte allowlist → malware scan (fail closed) → encrypted write-once storage → a document with
  category `photo` → a document link to the person → background previews. Anything else the allowlist
  accepts (e.g. a scanned PDF certificate referenced by `OBJE`) is filed as category `other`, never
  in the vault classes.
- **Privacy:** the photo document gets the **person's privacy level**, so a hidden or admin-only
  person's photo is equally hidden. Seeing the photo still requires seeing the document, as for any
  document.
- **Duplicates:** the same file used for several people is stored once and linked to each. A file
  the importer can already see in the tree is linked instead of stored again.
- **Rejected photos** (not an allowed image type, or flagged by the scanner) are skipped with a
  warning, and the rest of the import still commits. If the scanner is **unavailable**, the whole
  commit fails and can be retried (fail closed). Nothing is half-imported.
- People **attached** to an existing person get no photos, just as they get no heritage or astrology
  data (ADR-0008 attach rule). The report says so.
- Committing needs `gedcom.import`. Photos are imported only if the importer also holds
  `document.upload`; otherwise they are skipped with a warning. The import is audited with photo
  counts, and each document gets its own `document.uploaded` audit event.
- `_PRIM` (MyHeritage primary photo) and `_POSITION`/`_CUTOUT` (face crops) are not modelled yet.
  The photo is imported whole.

## Consequences
- Users keep their photos by zipping the export folder. The UI says how.
- Imports are synchronous. A 250 MB package with many photos makes a slow request. A background job
  for large packages is deferred (it is already deferred for large GEDCOM files).
- Package members that no person references are never stored. Only the original package is kept.

## Alternatives considered
- **Separate "attach photos" step after import:** rejected. People would have to match
  hundreds of files by hand, and the `.ged` already says which photo belongs to whom.
- **Extracting the zip to a temporary folder:** rejected. It is a path-traversal and disk-exhaustion
  risk, and nothing needs it.
- **Importing unassociated photos as unlinked documents:** rejected for now. They would fill the
  vault with unlabelled files the user did not ask for. They are counted, so a later option can
  add them.
