import { useId, useMemo } from "react";
import { useTranslation } from "react-i18next";
import type { GenealogicalTime, TimePrecision, TimeSource } from "../../api/types";
import { NON_EXACT_SOURCES, TIME_PRECISIONS, TIME_SOURCES, formatTime, isTimeCombinationAllowed, validateTime } from "../../lib/dates";

/**
 * Birth-time input: value + precision + source. `exact` cannot be combined with a verbal,
 * approximate or unknown source (server rule) — that option is disabled, and switching to such a
 * source downgrades an `exact` precision to `approximate` with a visible explanation.
 */
export function TimeEditor({
  value,
  onChange,
  legend,
  showErrors = false,
}: {
  value: GenealogicalTime;
  onChange: (v: GenealogicalTime) => void;
  legend: string;
  showErrors?: boolean;
}) {
  const { t } = useTranslation();
  const id = useId();
  const precision = (value.precision ?? "unknown") as TimePrecision;
  const source = (value.source ?? "unknown") as TimeSource;
  const error = showErrors ? validateTime(value) : null;
  const preview = formatTime(value, t);
  const exactBlocked = NON_EXACT_SOURCES.has(source);

  const setSource = (s: TimeSource) => {
    const next: GenealogicalTime = { ...value, source: s };
    if (!isTimeCombinationAllowed(precision, s)) next.precision = "approximate";
    onChange(next);
  };

  return (
    <fieldset className="rounded-lg border border-stone-300 p-3">
      <legend className="px-1 text-sm font-semibold">{legend}</legend>
      <div className="grid grid-cols-1 gap-3 sm:grid-cols-3">
        <div>
          <label htmlFor={`${id}-value`} className="label">
            {t("time.value")}
          </label>
          <input
            id={`${id}-value`}
            type="time"
            className="input"
            value={value.value ?? ""}
            aria-invalid={!!error || undefined}
            aria-describedby={error ? `${id}-err` : undefined}
            onChange={(e) => {
              const v = e.target.value || null;
              onChange({ ...value, value: v, precision: v ? (precision === "unknown" ? "approximate" : precision) : "unknown" });
            }}
          />
        </div>
        <div>
          <label htmlFor={`${id}-source`} className="label">
            {t("time.source")}
          </label>
          <select id={`${id}-source`} className="input" value={source} onChange={(e) => setSource(e.target.value as TimeSource)}>
            {TIME_SOURCES.map((s) => (
              <option key={s} value={s}>
                {t(`enum.timeSource.${s}`)}
              </option>
            ))}
          </select>
        </div>
        <div>
          <label htmlFor={`${id}-precision`} className="label">
            {t("time.precision")}
          </label>
          <select
            id={`${id}-precision`}
            className="input"
            value={precision}
            aria-describedby={exactBlocked ? `${id}-exact-hint` : undefined}
            onChange={(e) => onChange({ ...value, precision: e.target.value as TimePrecision })}
          >
            {TIME_PRECISIONS.map((p) => (
              <option key={p} value={p} disabled={!isTimeCombinationAllowed(p, source)}>
                {t(`enum.timePrecision.${p}`)}
              </option>
            ))}
          </select>
        </div>
      </div>
      {exactBlocked && (
        <p id={`${id}-exact-hint`} className="hint">
          {t("time.exactBlocked", { source: t(`enum.timeSource.${source}`) })}
        </p>
      )}
      {error && (
        <p id={`${id}-err`} className="field-error" role="alert">
          {t(error)}
        </p>
      )}
      {preview && (
        <p className="mt-2 text-xs text-ink-muted" aria-live="polite">
          {t("date.preview")}: <span className="font-medium text-ink">{preview}</span>
        </p>
      )}
    </fieldset>
  );
}

const COMMON_ZONES = ["Asia/Kolkata", "Asia/Kathmandu", "Asia/Dhaka", "Asia/Karachi", "Asia/Colombo", "Asia/Dubai", "Asia/Singapore", "Europe/London", "America/New_York", "Africa/Nairobi", "Pacific/Fiji"];

export function TimezoneSelect({ value, onChange }: { value: string; onChange: (v: string) => void }) {
  const { t } = useTranslation();
  const id = useId();
  const zones = useMemo(() => {
    let all: string[] = [];
    try {
      all = (Intl as unknown as { supportedValuesOf?: (k: string) => string[] }).supportedValuesOf?.("timeZone") ?? [];
    } catch {
      all = [];
    }
    return all.filter((z) => !COMMON_ZONES.includes(z));
  }, []);
  return (
    <div>
      <label htmlFor={id} className="label">
        {t("time.timezone")}
      </label>
      <select id={id} className="input" value={value} onChange={(e) => onChange(e.target.value)}>
        <option value="">{t("time.timezoneNone")}</option>
        <optgroup label={t("time.timezoneCommon")}>
          {COMMON_ZONES.map((z) => (
            <option key={z} value={z}>
              {z === "Asia/Kolkata" ? `${z} (IST)` : z}
            </option>
          ))}
        </optgroup>
        {zones.length > 0 && (
          <optgroup label={t("time.timezoneAll")}>
            {zones.map((z) => (
              <option key={z} value={z}>
                {z}
              </option>
            ))}
          </optgroup>
        )}
      </select>
      <p className="hint">{t("time.timezoneHint")}</p>
    </div>
  );
}
