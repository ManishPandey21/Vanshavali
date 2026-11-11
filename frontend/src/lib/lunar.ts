import type { LunarDate } from "../api/types";

/**
 * Tithi dates as families write them (ADR-0022 §2). Labels mirror the backend's
 * `app/core/lunar.py`; nothing here computes or converts a date.
 */
export const MASAS = [
  "chaitra",
  "vaishakha",
  "jyeshtha",
  "ashadha",
  "shravana",
  "bhadrapada",
  "ashvin",
  "kartika",
  "margashirsha",
  "pausha",
  "magha",
  "phalguna",
] as const;

const MASA_LABELS: Record<string, [string, string]> = {
  chaitra: ["Chaitra", "चैत्र"],
  vaishakha: ["Vaishakha", "वैशाख"],
  jyeshtha: ["Jyeshtha", "ज्येष्ठ"],
  ashadha: ["Ashadha", "आषाढ़"],
  shravana: ["Shravana", "श्रावण"],
  bhadrapada: ["Bhadrapada", "भाद्रपद"],
  ashvin: ["Ashvin", "आश्विन"],
  kartika: ["Kartika", "कार्तिक"],
  margashirsha: ["Margashirsha", "मार्गशीर्ष"],
  pausha: ["Pausha", "पौष"],
  magha: ["Magha", "माघ"],
  phalguna: ["Phalguna", "फाल्गुन"],
};

const TITHIS: [string, string][] = [
  ["Pratipada", "प्रतिपदा"],
  ["Dvitiya", "द्वितीया"],
  ["Tritiya", "तृतीया"],
  ["Chaturthi", "चतुर्थी"],
  ["Panchami", "पंचमी"],
  ["Shashthi", "षष्ठी"],
  ["Saptami", "सप्तमी"],
  ["Ashtami", "अष्टमी"],
  ["Navami", "नवमी"],
  ["Dashami", "दशमी"],
  ["Ekadashi", "एकादशी"],
  ["Dvadashi", "द्वादशी"],
  ["Trayodashi", "त्रयोदशी"],
  ["Chaturdashi", "चतुर्दशी"],
];

const hi = (lang: string) => (lang.startsWith("hi") ? 1 : 0);

export function masaLabel(masa: string, lang: string): string {
  return MASA_LABELS[masa]?.[hi(lang)] ?? masa;
}

export function pakshaLabel(paksha: string, lang: string): string {
  return paksha === "shukla" ? ["Shukla", "शुक्ल"][hi(lang)] : ["Krishna", "कृष्ण"][hi(lang)];
}

export function tithiLabel(paksha: string, tithi: number, lang: string): string {
  if (tithi === 15) return paksha === "shukla" ? ["Purnima", "पूर्णिमा"][hi(lang)] : ["Amavasya", "अमावस्या"][hi(lang)];
  return TITHIS[tithi - 1]?.[hi(lang)] ?? String(tithi);
}

/** "Bhadrapada Krishna Ashtami" / "भाद्रपद कृष्ण अष्टमी", with "Adhik" and the samvat year when given. */
export function lunarLabel(l: LunarDate, lang: string): string {
  const h = hi(lang);
  const adhik = l.is_adhik ? ["Adhik ", "अधिक "][h] : "";
  let out = `${adhik}${masaLabel(l.masa, lang)} ${pakshaLabel(l.paksha, lang)} ${tithiLabel(l.paksha, l.tithi, lang)}`;
  if (l.year && l.samvat) {
    const name = l.samvat === "vikram" ? ["Vikram Samvat", "विक्रम संवत"][h] : ["Shaka", "शक संवत"][h];
    out += `, ${name} ${l.year}`;
  }
  return out;
}
