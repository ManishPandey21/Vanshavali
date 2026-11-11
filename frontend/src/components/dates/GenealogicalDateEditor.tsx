import { useId } from "react";
import { useTranslation } from "react-i18next";
import type { DateCalendar, DatePrecision, GenealogicalDate } from "../../api/types";
import { DATE_PRECISIONS, EDITOR_CALENDARS, datePartsFor, formatDate, monthName, validateDate } from "../../lib/dates";
import { intOrNull } from "../ui/form";
import { LunarDateFields } from "./LunarDateFields";

/**
 * Structured genealogical date input. Only the parts the chosen precision allows are rendered
 * (e.g. "year only" shows no month/day), and the server's rules are checked inline.
 */
export function GenealogicalDateEditor({
  value,
  onChange,
  legend,
  showErrors = false,
  idPrefix,
}: {
  value: GenealogicalDate;
  onChange: (d: GenealogicalDate) => void;
  legend: string;
  showErrors?: boolean;
  idPrefix?: string;
}) {
  const { t, i18n } = useTranslation();
  const auto = useId();
  const id = idPrefix ?? auto;
  const precision = (value.precision ?? "exact") as DatePrecision;
  const calendar = (value.calendar ?? "gregorian") as DateCalendar;
  const parts = datePartsFor(precision);
  const errors = showErrors ? validateDate(value) : {};
  // editing the Gregorian parts by hand means they are no longer the accepted calculation
  const set = (patch: Partial<GenealogicalDate>) => onChange({ ...value, ...patch, ...("lunar" in patch ? {} : { derived: null }) });

  const setPrecision = (p: DatePrecision) => {
    const allowed = datePartsFor(p);
    onChange({
      ...value,
      precision: p,
      year: allowed.year ? value.year : null,
      month: allowed.month ? value.month : null,
      day: allowed.day ? value.day : null,
      end_year: allowed.end ? value.end_year : null,
      end_month: allowed.end ? value.end_month : null,
      end_day: allowed.end ? value.end_day : null,
    });
  };

  const err = (k: keyof typeof errors) =>
    errors[k] ? (
      <p id={`${id}-${k}-err`} className="field-error">
        {t(errors[k]!)}
      </p>
    ) : null;
  const describe = (k: keyof typeof errors) => (errors[k] ? `${id}-${k}-err` : undefined);

  const months = Array.from({ length: 12 }, (_, i) => i + 1);
  const preview = precision === "unknown" && !value.original_text && !value.lunar ? null : formatDate(value, t, i18n.language);

  return (
    <fieldset className="rounded-lg border border-stone-300 p-3" data-testid={`date-editor-${id}`}>
      <legend className="px-1 text-sm font-semibold">{legend}</legend>
      <div className="grid grid-cols-2 gap-3 sm:grid-cols-4">
        <div className="col-span-2 sm:col-span-2">
          <label htmlFor={`${id}-precision`} className="label">
            {t("date.precision")}
          </label>
          <select id={`${id}-precision`} className="input" value={precision} onChange={(e) => setPrecision(e.target.value as DatePrecision)}>
            {DATE_PRECISIONS.map((p) => (
              <option key={p} value={p}>
                {t(`enum.datePrecision.${p}`)}
              </option>
            ))}
          </select>
        </div>
        <div className="col-span-2 sm:col-span-2">
          <label htmlFor={`${id}-calendar`} className="label">
            {t("date.calendar")}
          </label>
          <select id={`${id}-calendar`} className="input" value={calendar} onChange={(e) => set({ calendar: e.target.value as DateCalendar })}>
            {(EDITOR_CALENDARS.includes(calendar) ? EDITOR_CALENDARS : [...EDITOR_CALENDARS, calendar]).map((c) => (
              <option key={c} value={c}>
                {t(`enum.calendar.${c}`)}
              </option>
            ))}
          </select>
        </div>
        {parts.day && (
          <div>
            <label htmlFor={`${id}-day`} className="label">
              {t("date.day")}
              {precision === "exact" && <span aria-hidden> *</span>}
            </label>
            <input
              id={`${id}-day`}
              className="input"
              type="number"
              inputMode="numeric"
              min={1}
              max={31}
              value={value.day ?? ""}
              aria-invalid={!!errors.day || undefined}
              aria-describedby={describe("day")}
              aria-required={precision === "exact" || undefined}
              onChange={(e) => set({ day: intOrNull(e.target.value) })}
            />
            {err("day")}
          </div>
        )}
        {parts.month && (
          <div>
            <label htmlFor={`${id}-month`} className="label">
              {t("date.month")}
              {(precision === "exact" || precision === "day_unknown") && <span aria-hidden> *</span>}
            </label>
            <select
              id={`${id}-month`}
              className="input"
              value={value.month ?? ""}
              aria-invalid={!!errors.month || undefined}
              aria-describedby={describe("month")}
              onChange={(e) => set({ month: intOrNull(e.target.value) })}
            >
              <option value="">{t("date.monthNotKnown")}</option>
              {months.map((m) => (
                <option key={m} value={m}>
                  {monthName(m, calendar, i18n.language)}
                </option>
              ))}
            </select>
            {err("month")}
          </div>
        )}
        {parts.year && (
          <div>
            <label htmlFor={`${id}-year`} className="label">
              {t("date.year")}
              <span aria-hidden> *</span>
            </label>
            <input
              id={`${id}-year`}
              className="input"
              type="number"
              inputMode="numeric"
              min={1}
              max={9999}
              value={value.year ?? ""}
              aria-invalid={!!errors.year || undefined}
              aria-describedby={describe("year")}
              aria-required
              onChange={(e) => set({ year: intOrNull(e.target.value) })}
            />
            {err("year")}
          </div>
        )}
        {!parts.month && !parts.day && parts.year && errors.month && <div className="col-span-2">{err("month")}</div>}
        {parts.end && (
          <div className="col-span-2 grid grid-cols-3 gap-3 sm:col-span-4">
            <p className="col-span-3 text-xs font-medium text-ink-muted">{t("date.rangeEnd")}</p>
            <div>
              <label htmlFor={`${id}-end-day`} className="label">
                {t("date.day")}
              </label>
              <input id={`${id}-end-day`} className="input" type="number" min={1} max={31} value={value.end_day ?? ""} onChange={(e) => set({ end_day: intOrNull(e.target.value) })} />
            </div>
            <div>
              <label htmlFor={`${id}-end-month`} className="label">
                {t("date.month")}
              </label>
              <select id={`${id}-end-month`} className="input" value={value.end_month ?? ""} onChange={(e) => set({ end_month: intOrNull(e.target.value) })}>
                <option value="">{t("date.monthNotKnown")}</option>
                {months.map((m) => (
                  <option key={m} value={m}>
                    {monthName(m, calendar, i18n.language)}
                  </option>
                ))}
              </select>
            </div>
            <div>
              <label htmlFor={`${id}-end-year`} className="label">
                {t("date.year")} *
              </label>
              <input
                id={`${id}-end-year`}
                className="input"
                type="number"
                min={1}
                max={9999}
                value={value.end_year ?? ""}
                aria-invalid={!!errors.end_year || undefined}
                aria-describedby={describe("end_year")}
                onChange={(e) => set({ end_year: intOrNull(e.target.value) })}
              />
              {err("end_year")}
            </div>
          </div>
        )}
        <div className="col-span-2 sm:col-span-4">
          <label htmlFor={`${id}-orig`} className="label">
            {t("date.originalText")}
          </label>
          <input
            id={`${id}-orig`}
            className="input"
            value={value.original_text ?? ""}
            placeholder={t("date.originalTextPlaceholder")}
            onChange={(e) => set({ original_text: e.target.value || null })}
          />
          <p className="hint">{t("date.originalTextHint")}</p>
        </div>
        <div className="col-span-2 sm:col-span-4">
          <LunarDateFields value={value} onChange={onChange} id={`${id}-lunar`} />
        </div>
      </div>
      {preview && (
        <p className="mt-2 text-xs text-ink-muted" aria-live="polite">
          {t("date.preview")}: <span className="font-medium text-ink">{preview}</span>
        </p>
      )}
    </fieldset>
  );
}
