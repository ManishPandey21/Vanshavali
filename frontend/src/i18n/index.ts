import i18n from "i18next";
import { initReactI18next } from "react-i18next";
import en from "./locales/en.json";
import hi from "./locales/hi.json";

export const SUPPORTED_LANGUAGES = [
  { code: "en", label: "English" },
  { code: "hi", label: "हिन्दी" },
] as const;

export type UiLanguage = (typeof SUPPORTED_LANGUAGES)[number]["code"];

const STORAGE_KEY = "vsh_lang";

export function storedLanguage(): UiLanguage | null {
  try {
    const v = localStorage.getItem(STORAGE_KEY);
    return v === "en" || v === "hi" ? v : null;
  } catch {
    return null;
  }
}

export function rememberLanguage(lang: string) {
  try {
    localStorage.setItem(STORAGE_KEY, lang);
  } catch {
    /* storage may be unavailable (private mode) */
  }
}

export function normalizeLanguage(lang: string | null | undefined): UiLanguage {
  return lang && lang.toLowerCase().startsWith("hi") ? "hi" : "en";
}

function initialLanguage(): UiLanguage {
  const stored = storedLanguage();
  if (stored) return stored;
  if (typeof navigator !== "undefined") return normalizeLanguage(navigator.language);
  return "en";
}

void i18n.use(initReactI18next).init({
  resources: { en: { translation: en }, hi: { translation: hi } },
  lng: initialLanguage(),
  fallbackLng: "en",
  interpolation: { escapeValue: false },
  returnNull: false,
});

function syncDocumentLang(lng: string) {
  if (typeof document !== "undefined") document.documentElement.lang = lng;
}
syncDocumentLang(i18n.language);
i18n.on("languageChanged", syncDocumentLang);

export default i18n;
