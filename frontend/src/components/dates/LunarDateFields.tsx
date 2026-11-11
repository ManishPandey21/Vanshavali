import { useContext, useState } from "react";
import { useTranslation } from "react-i18next";
import type { GenealogicalDate, LunarDate, MonthConvention, Paksha, Samvat } from "../../api/types";
import { useCalendarSettings, useConvertLunar } from "../../api/hooks/calendar";
import { TreeContext } from "../../lib/tree-context";
import { MASAS, masaLabel, pakshaLabel, tithiLabel } from "../../lib/lunar";
import { intOrNull } from "../ui/form";
import { Button } from "../ui/Button";
import { ErrorAlert } from "../ui/feedback";

const EMPTY: LunarDate = { masa: "chaitra", paksha: "shukla", tithi: 1, month_convention: "purnimanta", is_adhik: false };

/**
 * The Hindu calendar part of a date (ADR-0022 §2): masa, paksha, tithi as the family gives them.
 * It never fills in the Gregorian date; "Find the Gregorian date" only suggests one, and only
 * for a convention that has passed its accuracy checks.
 */
export function LunarDateFields({ value, onChange, id }: { value: GenealogicalDate; onChange: (d: GenealogicalDate) => void; id: string }) {
  const { t, i18n } = useTranslation();
  const lang = i18n.language;
  const lunar = value.lunar ?? null;
  const [open, setOpen] = useState(!!lunar);
  const set = (patch: Partial<LunarDate>) => onChange({ ...value, lunar: { ...(lunar ?? EMPTY), ...patch } });

  if (!open) {
    return (
      <button type="button" className="text-xs font-medium text-kumkum-800 underline" onClick={() => { setOpen(true); onChange({ ...value, lunar: lunar ?? EMPTY }); }}>
        {t("lunar.add")}
      </button>
    );
  }
  const l = lunar ?? EMPTY;
  return (
    <fieldset className="rounded-lg border border-dashed border-stone-300 p-3">
      <legend className="px-1 text-sm font-medium">{t("lunar.legend")}</legend>
      <p className="mb-2 text-xs text-ink-muted">{t("lunar.hint")}</p>
      <div className="grid grid-cols-2 gap-3 sm:grid-cols-4">
        <div>
          <label htmlFor={`${id}-masa`} className="label">
            {t("lunar.masa")}
          </label>
          <select id={`${id}-masa`} className="input" value={l.masa} onChange={(e) => set({ masa: e.target.value })}>
            {MASAS.map((m) => (
              <option key={m} value={m}>
                {masaLabel(m, lang)}
              </option>
            ))}
          </select>
        </div>
        <div>
          <label htmlFor={`${id}-paksha`} className="label">
            {t("lunar.paksha")}
          </label>
          <select id={`${id}-paksha`} className="input" value={l.paksha} onChange={(e) => set({ paksha: e.target.value as Paksha })}>
            {(["shukla", "krishna"] as Paksha[]).map((p) => (
              <option key={p} value={p}>
                {pakshaLabel(p, lang)}
              </option>
            ))}
          </select>
        </div>
        <div>
          <label htmlFor={`${id}-tithi`} className="label">
            {t("lunar.tithi")}
          </label>
          <select id={`${id}-tithi`} className="input" value={l.tithi} onChange={(e) => set({ tithi: Number(e.target.value) })}>
            {Array.from({ length: 15 }, (_, i) => i + 1).map((n) => (
              <option key={n} value={n}>
                {tithiLabel(l.paksha, n, lang)}
              </option>
            ))}
          </select>
        </div>
        <div>
          <label htmlFor={`${id}-mc`} className="label">
            {t("lunar.monthConvention")}
          </label>
          <select id={`${id}-mc`} className="input" value={l.month_convention} onChange={(e) => set({ month_convention: e.target.value as MonthConvention })}>
            <option value="purnimanta">{t("lunar.purnimanta")}</option>
            <option value="amanta">{t("lunar.amanta")}</option>
          </select>
        </div>
        <div className="col-span-2 flex items-end gap-2 sm:col-span-1">
          <input id={`${id}-adhik`} type="checkbox" className="mb-2 size-4 accent-kumkum-700" checked={!!l.is_adhik} onChange={(e) => set({ is_adhik: e.target.checked })} />
          <label htmlFor={`${id}-adhik`} className="mb-1.5 text-sm">
            {t("lunar.adhik")}
          </label>
        </div>
        <div>
          <label htmlFor={`${id}-samvat`} className="label">
            {t("lunar.samvat")}
          </label>
          <select
            id={`${id}-samvat`}
            className="input"
            value={l.samvat ?? ""}
            onChange={(e) => set({ samvat: (e.target.value || null) as Samvat | null, year: e.target.value ? l.year : null })}
          >
            <option value="">{t("lunar.samvatUnknown")}</option>
            <option value="vikram">{t("lunar.vikram")}</option>
            <option value="shaka">{t("lunar.shaka")}</option>
          </select>
        </div>
        {l.samvat && (
          <div>
            <label htmlFor={`${id}-syear`} className="label">
              {t("lunar.samvatYear")}
            </label>
            <input id={`${id}-syear`} className="input" type="number" inputMode="numeric" min={1} max={9999} value={l.year ?? ""} onChange={(e) => set({ year: intOrNull(e.target.value) })} />
          </div>
        )}
      </div>
      <div className="mt-2 flex flex-wrap items-center gap-3">
        <button
          type="button"
          className="text-xs text-red-800 underline"
          onClick={() => {
            setOpen(false);
            onChange({ ...value, lunar: null });
          }}
        >
          {t("lunar.remove")}
        </button>
      </div>
      <ConvertSuggestion value={value} onChange={onChange} />
    </fieldset>
  );
}

function ConvertSuggestion({ value, onChange }: { value: GenealogicalDate; onChange: (d: GenealogicalDate) => void }) {
  const { t, i18n } = useTranslation();
  const tree = useContext(TreeContext);
  const treeId = tree?.treeId ?? null;
  const settings = useCalendarSettings(treeId);
  const convert = useConvertLunar(treeId ?? "");
  const lunar = value.lunar;
  const conv = settings.data?.conventions.find((c) => c.key === settings.data?.convention);
  if (!treeId || !lunar || !conv?.offered || !settings.data?.observance_city) return null;
  if (!lunar.year || !lunar.samvat) return <p className="mt-2 text-xs text-ink-muted">{t("lunar.convertNeedsYear")}</p>;
  const s = convert.data;
  const city = settings.data.cities.find((c) => c.key === s?.city)?.label ?? s?.city;
  return (
    <div className="mt-2 space-y-1">
      <Button size="sm" variant="secondary" loading={convert.isPending} onClick={() => convert.mutate({ lunar })}>
        {t("lunar.convert")}
      </Button>
      <ErrorAlert error={convert.error} />
      {s?.suggestion && (
        <div role="status" className="rounded-lg bg-haldi-100 p-2 text-xs">
          <p>
            {t("lunar.suggestion", {
              date: new Date(`${s.suggestion}T00:00:00`).toLocaleDateString(i18n.language, { day: "numeric", month: "long", year: "numeric" }),
              convention: conv.label,
              city,
            })}
          </p>
          <button
            type="button"
            className="mt-1 font-medium text-kumkum-800 underline"
            onClick={() => {
              const [y, m, d] = s.suggestion!.split("-").map(Number);
              onChange({
                ...value,
                calendar: "gregorian",
                precision: "exact",
                year: y,
                month: m,
                day: d,
                derived: { source: "lunar", convention: s.convention, city: s.city, engine_version: s.engine_version },
              });
            }}
          >
            {t("lunar.accept")}
          </button>
        </div>
      )}
    </div>
  );
}
