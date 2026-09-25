# ADR-0007: Search inside PostgreSQL

- Status: Accepted · Date: 2026-09-25

## Decision
- Every `name_record` stores `search_text`: its Unicode text normalised to NFKC, with Indic scripts
  transliterated to Latin (via `indic-transliteration`, ITRANS then folded to ASCII), then
  lowercased and accent-stripped. It also stores `search_phonetic`, a space-separated metaphone
  key per token (`jellyfish`).
- A GIN trigram index on `search_text`.
- The query is normalised the same way. Matches are tried in tiers (exact → prefix → trigram
  similarity ≥ 0.3 → phonetic token match). Each result reports **`match_reason`**, e.g.
  `alias "Ramaswami" ≈ "Ramaswamy" (trigram 0.62)`, as PRS §23.3 requires.
- Results pass through `can_view` and redaction. Hidden people are never counted or snippeted.
- Places, documents (title and category) and properties get `ILIKE` + trigram search over their
  names.
- **Duplicate candidates** are scored on name similarity, birth-year proximity, birthplace, and
  shared parents or spouses. Outcomes: `NOT_MATCH < POSSIBLE < PROBABLE`. Merging always needs a
  user.

## Deferred
OpenSearch or Meilisearch, when cross-tree discovery or more than 1M names are needed. CLDR/ICU
transliteration (PyICU) as a better-quality transform.
