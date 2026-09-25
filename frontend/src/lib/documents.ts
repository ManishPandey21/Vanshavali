import type { DocumentCategory, DocumentLinkTarget } from "../api/types";

export const DOCUMENT_CATEGORIES: DocumentCategory[] = [
  "birth_certificate",
  "death_certificate",
  "marriage_record",
  "kundli",
  "photo",
  "letter",
  "diary",
  "family_register",
  "traditional_register",
  "school_record",
  "service_record",
  "obituary",
  "identity_document",
  "audio",
  "video",
  "historical_family_paper",
  "record_of_rights",
  "khatauni",
  "jamabandi",
  "khasra",
  "rtc",
  "patta",
  "mutation_record",
  "cadastral_map",
  "title_deed",
  "sale_deed",
  "gift_deed",
  "partition_deed",
  "family_settlement",
  "relinquishment_deed",
  "will",
  "probate",
  "succession_certificate",
  "revenue_order",
  "court_order",
  "tax_receipt",
  "municipal_record",
  "encumbrance",
  "possession_record",
  "other",
];

/** Mirrors backend VAULT_CATEGORIES: stored in the encrypted vault class with stricter access. */
export const VAULT_CATEGORIES: ReadonlySet<DocumentCategory> = new Set<DocumentCategory>([
  "birth_certificate",
  "death_certificate",
  "marriage_record",
  "kundli",
  "identity_document",
  "record_of_rights",
  "khatauni",
  "jamabandi",
  "khasra",
  "rtc",
  "patta",
  "mutation_record",
  "cadastral_map",
  "title_deed",
  "sale_deed",
  "gift_deed",
  "partition_deed",
  "family_settlement",
  "relinquishment_deed",
  "will",
  "probate",
  "succession_certificate",
  "revenue_order",
  "court_order",
  "encumbrance",
  "possession_record",
  "tax_receipt",
  "municipal_record",
]);

export const PROPERTY_DOCUMENT_CATEGORIES: DocumentCategory[] = DOCUMENT_CATEGORIES.filter(
  (c) =>
    VAULT_CATEGORIES.has(c) &&
    !["birth_certificate", "death_certificate", "marriage_record", "kundli", "identity_document"].includes(c),
);

export const LINK_TARGETS: DocumentLinkTarget[] = ["person", "event", "place", "property", "land_parcel", "property_event", "source", "household", "relationship"];

export function formatBytes(n: number): string {
  if (n < 1024) return `${n} B`;
  if (n < 1024 * 1024) return `${(n / 1024).toFixed(0)} KB`;
  return `${(n / (1024 * 1024)).toFixed(1)} MB`;
}

/** Value kinds of extraction fields (mirrors backend extraction/fields.py FIELD_SPECS). */
export type FieldKind = "text" | "name" | "identifier" | "date" | "time" | "sex" | "nakshatra" | "rashi" | "tithi" | "paksha" | "ayanamsha" | "pada" | "area";

export const FIELD_KINDS: Record<string, FieldKind> = {
  name: "name",
  date_of_birth: "date",
  time_of_birth: "time",
  sex: "sex",
  place_of_birth: "text",
  father_name: "name",
  mother_name: "name",
  registration_number: "identifier",
  registration_date: "date",
  issuing_authority: "text",
  chart_birth_date: "date",
  chart_birth_time: "time",
  chart_birth_place: "text",
  nakshatra: "nakshatra",
  nakshatra_pada: "pada",
  rashi: "rashi",
  lagna: "rashi",
  tithi: "tithi",
  paksha: "paksha",
  ayanamsha: "ayanamsha",
  khasra_or_gata_number: "identifier",
  khata_number: "identifier",
  khatauni_number: "identifier",
  survey_number: "identifier",
  patta_number: "identifier",
  village: "text",
  tehsil_taluk: "text",
  district: "text",
  area: "area",
  holder_name: "name",
  holder_relative_name: "name",
  mutation_number: "identifier",
  mutation_date: "date",
  deed_registration_number: "identifier",
  deed_registration_date: "date",
};

export function fieldKind(field: string): FieldKind {
  return FIELD_KINDS[field] ?? "text";
}

/**
 * Review label shown next to each extracted value (ADR-0009 §4):
 * - "extracted": machine-read, not yet reviewed
 * - "source-verified": a reviewer confirmed it matches the source document as read
 * - "user-confirmed": a reviewer corrected it before accepting
 * - "rejected"
 */
export type ValueLabel = "extracted" | "source-verified" | "user-confirmed" | "rejected";

export function valueLabel(status: string): ValueLabel {
  switch (status) {
    case "accepted":
      return "source-verified";
    case "edited":
      return "user-confirmed";
    case "rejected":
      return "rejected";
    default:
      return "extracted";
  }
}
