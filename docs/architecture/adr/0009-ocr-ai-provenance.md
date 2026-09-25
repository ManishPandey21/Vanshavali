# ADR-0009: OCR / AI extraction produces proposals with provenance

- Status: Accepted · Date: 2026-09-25

## Decision
1. **OCR engines**, behind the interface `OcrEngine.extract(document) -> OcrResult(pages, text,
   confidence, engine, version)`: `PdfTextLayerEngine` (pypdf) and `TesseractEngine` (local
   `tesseract`, languages configurable, default `eng+hin`; PDFs are rendered with pypdfium2). OCR
   text is stored as an encrypted derivative, **separate from facts**.
2. **Extractors**, per document category: birth certificate, Kundli/Janampatri and land records.
   They produce `ExtractionProposal(field, proposed_value, confidence, source_location, extractor,
   extractor_version, engine, engine_version)`. Aadhaar-shaped numbers are masked before storage.
3. **Proposals never change canonical data.** Only `POST /extraction-proposals/{id}/review`
   (`accept | edit | reject`) by a user with `extraction.review` can. Accepting creates *new* claims
   (a name record, a non-preferred birth event, an assertion, an astrology profile or parcel
   fields), each with:
   - a `Citation` to the document's `Source`;
   - provenance `origin=ocr, algorithm_or_model, model_version, source_document_id,
     source_location, extracted_at, confirmed_by, confirmed_at`;
   - `evidence_status=SOURCED`.
   Existing preferred facts are never overwritten. If the new claim disagrees, it's flagged as a
   conflict for review.
4. The UI labels values as **extracted** (proposal), **user-confirmed** (accepted proposal),
   **source-verified** (SOURCED/CORROBORATED) or **inferred**. We don't produce inferred values.
5. **External AI providers**: none are used by default. Adding one requires a per-tree opt-in
   consent record plus an amendment to this ADR. Provider, model and version are always recorded.
