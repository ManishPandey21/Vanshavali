/** Helpers for multilingual / multi-script names. */
import type { NameOut } from "../api/types";

export interface ScriptOption {
  script: string; // ISO 15924
  language: string; // BCP 47
  label: string;
}

/** Common Indian scripts offered in the names editor (value = ISO 15924 code). */
export const SCRIPTS: ScriptOption[] = [
  { script: "Latn", language: "en", label: "Latin (English)" },
  { script: "Deva", language: "hi", label: "देवनागरी (Hindi)" },
  { script: "Deva", language: "mr", label: "देवनागरी (Marathi)" },
  { script: "Deva", language: "sa", label: "देवनागरी (Sanskrit)" },
  { script: "Beng", language: "bn", label: "বাংলা (Bengali)" },
  { script: "Guru", language: "pa", label: "ਗੁਰਮੁਖੀ (Punjabi)" },
  { script: "Gujr", language: "gu", label: "ગુજરાતી (Gujarati)" },
  { script: "Orya", language: "or", label: "ଓଡ଼ିଆ (Odia)" },
  { script: "Taml", language: "ta", label: "தமிழ் (Tamil)" },
  { script: "Telu", language: "te", label: "తెలుగు (Telugu)" },
  { script: "Knda", language: "kn", label: "ಕನ್ನಡ (Kannada)" },
  { script: "Mlym", language: "ml", label: "മലയാളം (Malayalam)" },
  { script: "Arab", language: "ur", label: "اردو (Urdu)" },
];

const RANGES: [RegExp, string, string][] = [
  [/[ऀ-ॿ]/, "Deva", "hi"],
  [/[ঀ-৿]/, "Beng", "bn"],
  [/[਀-੿]/, "Guru", "pa"],
  [/[઀-૿]/, "Gujr", "gu"],
  [/[଀-୿]/, "Orya", "or"],
  [/[஀-௿]/, "Taml", "ta"],
  [/[ఀ-౿]/, "Telu", "te"],
  [/[ಀ-೿]/, "Knda", "kn"],
  [/[ഀ-ൿ]/, "Mlym", "ml"],
  [/[؀-ۿ]/, "Arab", "ur"],
];

/** Detect the script of typed text (first matching Indic block), defaulting to Latin. */
export function detectScript(text: string): { script: string; language: string } | null {
  if (!text.trim()) return null;
  for (const [re, script, language] of RANGES) if (re.test(text)) return { script, language };
  if (/[A-Za-z]/.test(text)) return { script: "Latn", language: "en" };
  return null;
}

export function isNonLatin(name: Pick<NameOut, "script">): boolean {
  return !!name.script && name.script !== "Latn";
}

export function isRtl(script: string | null | undefined): boolean {
  return script === "Arab";
}

/** The composed name text from a NameOut (API supplies `display`; fall back to parts). */
export function nameText(n: NameOut): string {
  if (n.display) return n.display;
  if (n.full_name_as_recorded) return n.full_name_as_recorded;
  return [n.honorific_prefix, n.given_name, n.middle_names, n.surname, n.honorific_suffix].filter(Boolean).join(" ");
}

/** Native-script (non-Latin) names to show under a display name. */
export function nativeScriptNames(names: NameOut[] | undefined): NameOut[] {
  return (names ?? []).filter(isNonLatin);
}

/**
 * `lang` for text shown outside a known-language context (display names, labels): the default
 * language of its script when that is not Latin, so screen readers switch voice for Devanagari,
 * Tamil, Urdu… names (WCAG 3.1.2). Latin text inherits the page language. Where a NameOut carries
 * its own `language`, use that instead.
 */
export function langOfText(text: string | null | undefined): string | undefined {
  const d = text ? detectScript(text) : null;
  return d && d.script !== "Latn" ? d.language : undefined;
}

/** `dir` for text in a right-to-left script (Urdu / Arabic), else undefined. */
export function dirOfText(text: string | null | undefined): "rtl" | undefined {
  const d = text ? detectScript(text) : null;
  return d && isRtl(d.script) ? "rtl" : undefined;
}
