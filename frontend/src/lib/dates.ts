/**
 * Genealogical dates and times (ADR-0003, PRS §8/§9/§52).
 *
 * Rules enforced here mirror the server's validators so users get errors before submitting:
 * - `exact` needs year + month + day; `day_unknown` needs month but no day; `year_only` carries no
 *   month/day; `month_unknown` carries no month; `range` needs an end year; `unknown` needs nothing.
 * - A time can only be `exact` when its source is a record (certificate, hospital, kundli,
 *   family-recorded); a verbal / approximate / unknown-source time is never exact.
 * - Display always shows qualifiers ("c.", "before", "about", calendar name) so an approximate value
 *   is never presented as exact.
 */
import type { TFunction } from "i18next";
import type { DateCalendar, DatePrecision, GenealogicalDate, GenealogicalTime, TimePrecision, TimeSource } from "../api/types";
import { lunarLabel } from "./lunar";

export const DATE_PRECISIONS: DatePrecision[] = [
  "exact",
  "day_unknown",
  "month_unknown",
  "year_only",
  "circa",
  "before",
  "after",
  "range",
  "unknown",
];

/** Calendars offered in the editor. The API also accepts julian/hijri/other; those still display. */
export const EDITOR_CALENDARS: DateCalendar[] = ["gregorian", "vikram_samvat", "shaka"];

export const TIME_PRECISIONS: TimePrecision[] = [
  "exact",
  "document_recorded",
  "approximate",
  "family_recollection",
  "unknown",
];

export const TIME_SOURCES: TimeSource[] = [
  "birth_certificate",
  "hospital_record",
  "kundli",
  "family_recorded",
  "verbal",
  "approximate",
  "unknown",
];

/** Sources that can never back an `exact` time (server rule in core/dates.py). */
export const NON_EXACT_SOURCES: ReadonlySet<TimeSource> = new Set<TimeSource>(["verbal", "approximate", "unknown"]);

/** Which parts of a date each precision accepts. */
export function datePartsFor(precision: DatePrecision): {
  year: boolean;
  month: boolean;
  day: boolean;
  end: boolean;
} {
  switch (precision) {
    case "exact":
      return { year: true, month: true, day: true, end: false };
    case "day_unknown":
      return { year: true, month: true, day: false, end: false };
    case "month_unknown":
      return { year: true, month: false, day: true, end: false };
    case "year_only":
      return { year: true, month: false, day: false, end: false };
    case "circa":
    case "before":
    case "after":
      return { year: true, month: true, day: true, end: false };
    case "range":
      return { year: true, month: true, day: true, end: true };
    case "unknown":
    default:
      return { year: false, month: false, day: false, end: false };
  }
}

export type DateErrors = Partial<Record<"year" | "month" | "day" | "end_year" | "end_month" | "end_day", string>>;

function daysInMonth(year: number, month: number): number {
  return new Date(Date.UTC(year, month, 0)).getUTCDate();
}

/** Returns i18n keys for each invalid part (empty object = valid). */
export function validateDate(d: GenealogicalDate): DateErrors {
  const errs: DateErrors = {};
  const p = d.precision ?? "exact";
  if (p === "unknown") return errs;
  const inRange = (v: number | null | undefined, lo: number, hi: number) =>
    v === null || v === undefined || (Number.isInteger(v) && v >= lo && v <= hi);
  if (d.year == null) errs.year = "date.err.yearRequired";
  else if (!inRange(d.year, 1, 9999)) errs.year = "date.err.yearRange";
  if (!inRange(d.month, 1, 12)) errs.month = "date.err.monthRange";
  if (!inRange(d.day, 1, 31)) errs.day = "date.err.dayRange";
  if (p === "exact") {
    if (d.month == null) errs.month = "date.err.exactNeedsMonth";
    if (d.day == null) errs.day = "date.err.exactNeedsDay";
  }
  if (p === "day_unknown") {
    if (d.month == null) errs.month = "date.err.monthRequired";
    if (d.day != null) errs.day = "date.err.noDayForPrecision";
  }
  if (p === "year_only" && (d.month != null || d.day != null)) errs.month = "date.err.yearOnlyNoParts";
  if (p === "month_unknown" && d.month != null) errs.month = "date.err.noMonthForPrecision";
  if (p === "range") {
    if (d.end_year == null) errs.end_year = "date.err.endYearRequired";
    else if (d.year != null && d.end_year < d.year) errs.end_year = "date.err.endBeforeStart";
  }
  if (
    (d.calendar ?? "gregorian") === "gregorian" &&
    d.year != null &&
    d.month != null &&
    d.day != null &&
    !errs.day &&
    d.day > daysInMonth(d.year, d.month)
  ) {
    errs.day = "date.err.invalidDay";
  }
  return errs;
}

/** Drops parts the chosen precision does not allow, so hidden inputs never leak stale values. */
export function normalizeDate(d: GenealogicalDate): GenealogicalDate {
  const p = d.precision ?? "exact";
  const parts = datePartsFor(p);
  const out: GenealogicalDate = { calendar: d.calendar ?? "gregorian", precision: p };
  if (parts.year && d.year != null) out.year = d.year;
  if (parts.month && d.month != null) out.month = d.month;
  if (parts.day && d.day != null) out.day = d.day;
  if (parts.end) {
    if (d.end_year != null) out.end_year = d.end_year;
    if (d.end_month != null) out.end_month = d.end_month;
    if (d.end_day != null) out.end_day = d.end_day;
  }
  if (d.original_text && d.original_text.trim()) out.original_text = d.original_text.trim();
  return out;
}

export function isDateEmpty(d: GenealogicalDate | null | undefined): boolean {
  if (!d) return true;
  return (d.precision ?? "exact") !== "unknown" && d.year == null && !d.original_text;
}

export function validateTime(t: GenealogicalTime): string | null {
  const precision = t.precision ?? "unknown";
  const source = t.source ?? "unknown";
  if (precision !== "unknown" && !t.value) return "time.err.valueRequired";
  if (t.value && !/^([01]\d|2[0-3]):[0-5]\d$/.test(t.value)) return "time.err.format";
  if (precision === "exact" && NON_EXACT_SOURCES.has(source)) return "time.err.exactNotAllowed";
  return null;
}

/** Is `precision` selectable for this `source`? (UI disables the combination.) */
export function isTimeCombinationAllowed(precision: TimePrecision, source: TimeSource): boolean {
  return !(precision === "exact" && NON_EXACT_SOURCES.has(source));
}

// ------------------------------------------------------------------ display
const HINDU_MONTHS_EN = [
  "Chaitra",
  "Vaishakha",
  "Jyeshtha",
  "Ashadha",
  "Shravana",
  "Bhadrapada",
  "Ashvin",
  "Kartika",
  "Margashirsha",
  "Pausha",
  "Magha",
  "Phalguna",
];
const HINDU_MONTHS_HI = [
  "चैत्र",
  "वैशाख",
  "ज्येष्ठ",
  "आषाढ़",
  "श्रावण",
  "भाद्रपद",
  "आश्विन",
  "कार्तिक",
  "मार्गशीर्ष",
  "पौष",
  "माघ",
  "फाल्गुन",
];

export function monthName(month: number, calendar: DateCalendar | undefined, lang: string): string {
  if (calendar === "vikram_samvat" || calendar === "shaka") {
    return (lang.startsWith("hi") ? HINDU_MONTHS_HI : HINDU_MONTHS_EN)[month - 1] ?? String(month);
  }
  try {
    return new Intl.DateTimeFormat(lang, { month: "long", timeZone: "UTC" }).format(new Date(Date.UTC(2000, month - 1, 1)));
  } catch {
    return String(month);
  }
}

function core(year: number, month: number | null | undefined, day: number | null | undefined, cal: DateCalendar | undefined, lang: string) {
  const parts: string[] = [];
  if (day != null && month != null) parts.push(String(day));
  if (month != null) parts.push(monthName(month, cal, lang));
  parts.push(String(year));
  return parts.join(" ");
}

/**
 * Human-readable date with qualifiers. Never drops a qualifier: circa/before/after/range, the
 * calendar (unless Gregorian), "month unknown"/"day unknown", and a privacy note when redacted.
 */
export function formatDate(d: GenealogicalDate | Record<string, unknown> | null | undefined, t: TFunction, lang = "en"): string {
  if (!d) return t("date.display.unknown");
  const g = d as GenealogicalDate;
  const p = g.precision ?? "exact";
  // a tithi date as the family gives it (ADR-0022 §2); a redacted date never carries one
  const tithi = g.lunar ? lunarLabel(g.lunar, lang) : null;
  if (p === "unknown" || g.year == null) {
    if (tithi) return tithi;
    return g.original_text ? t("date.display.asRecorded", { text: g.original_text }) : t("date.display.unknown");
  }
  const base = core(g.year, g.month, p === "month_unknown" ? null : g.day, g.calendar, lang);
  let text: string;
  switch (p) {
    case "circa":
      text = t("date.display.circa", { date: base });
      break;
    case "before":
      text = t("date.display.before", { date: base });
      break;
    case "after":
      text = t("date.display.after", { date: base });
      break;
    case "range":
      text = t("date.display.range", {
        from: base,
        to: g.end_year != null ? core(g.end_year, g.end_month, g.end_day, g.calendar, lang) : "?",
      });
      break;
    case "month_unknown":
      text = t("date.display.monthUnknown", { date: base });
      break;
    default:
      text = base;
  }
  if (g.calendar && g.calendar !== "gregorian") text = `${text} (${t(`enum.calendar.${g.calendar}`)})`;
  if (tithi) text = `${text} · ${tithi}`;
  return text;
}

/** Short qualifier badge for a date, or null when the date is exact Gregorian. */
export function dateQualifier(d: GenealogicalDate | Record<string, unknown> | null | undefined): DatePrecision | null {
  if (!d) return null;
  const p = ((d as GenealogicalDate).precision ?? "exact") as DatePrecision;
  return p === "exact" ? null : p;
}

/**
 * A time is shown as exact only when its precision is `exact`. Everything else is prefixed with
 * "about"/"recalled"/"as recorded" and the source is always appended.
 */
export function formatTime(time: GenealogicalTime | Record<string, unknown> | null | undefined, t: TFunction): string | null {
  if (!time) return null;
  const g = time as GenealogicalTime;
  const precision = (g.precision ?? "unknown") as TimePrecision;
  if (!g.value || precision === "unknown") {
    return g.value ? t("time.display.unknownPrecision", { time: g.value }) : null;
  }
  const value = String(g.value).slice(0, 5);
  const source = (g.source ?? "unknown") as TimeSource;
  const src = t(`enum.timeSource.${source}`);
  switch (precision) {
    case "exact":
      return t("time.display.exact", { time: value, source: src });
    case "document_recorded":
      return t("time.display.documentRecorded", { time: value, source: src });
    case "approximate":
      return t("time.display.approximate", { time: value, source: src });
    case "family_recollection":
      return t("time.display.recollection", { time: value, source: src });
    default:
      return t("time.display.unknownPrecision", { time: value });
  }
}

export function emptyDate(): GenealogicalDate {
  return { calendar: "gregorian", precision: "exact" };
}

// ------------------------------------------------------------------ compact (lists, tree nodes)
const SHORT_PREFIX: Partial<Record<DatePrecision, string>> = { circa: "date.short.circa", before: "date.short.before", after: "date.short.after" };

/**
 * Short year-level form for dense places (lists, tree boxes): keeps the qualifier ("c.", "bef.")
 * and a calendar tag so "c. 1840 Śaka" is never shown as a bare "1840".
 */
export function compactDate(d: GenealogicalDate | Record<string, unknown> | null | undefined, t: TFunction): string | null {
  if (!d) return null;
  const g = d as GenealogicalDate;
  const p = (g.precision ?? "exact") as DatePrecision;
  if (p === "unknown" || g.year == null) return null;
  let text = String(g.year);
  if (p === "range" && g.end_year != null && g.end_year !== g.year) text = `${g.year}/${g.end_year}`;
  const prefix = SHORT_PREFIX[p];
  if (prefix) text = `${t(prefix)} ${text}`;
  if (g.calendar && g.calendar !== "gregorian") text = `${text} ${t(`date.short.calendar.${g.calendar}`)}`;
  return text;
}

interface LifeDates {
  birth_date?: Record<string, unknown> | null;
  death_date?: Record<string, unknown> | null;
  profile_status: string;
}

/** "1921–1990", "c. 1840 Śaka–?", "1950–" (living). Null when nothing is known. */
export function lifespan(p: LifeDates, t: TFunction): string | null {
  const b = compactDate(p.birth_date, t);
  const dd = compactDate(p.death_date, t);
  if (!b && !dd) return null;
  return `${b ?? "?"}–${dd ?? (p.profile_status === "living" ? "" : "?")}`;
}
