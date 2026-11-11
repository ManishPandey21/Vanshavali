import { useState } from "react";
import { useTranslation } from "react-i18next";
import { useCalendarSettings, useSetCalendarSettings } from "../../api/hooks/calendar";
import { useTreeCtx } from "../../lib/tree-context";
import { Button } from "../ui/Button";
import { Badge } from "../ui/Badge";
import { ErrorAlert, LiveRegion, Spinner } from "../ui/feedback";
import { Field, Select } from "../ui/form";

/**
 * The family's month system and the city whose sunrise decides tithi days (ADR-0022 §3-§4).
 * A convention is only used for computed dates once it has passed its golden-table checks.
 */
export function CalendarSettingsCard() {
  const { t } = useTranslation();
  const { treeId } = useTreeCtx();
  const settings = useCalendarSettings(treeId);
  const set = useSetCalendarSettings(treeId);
  const [convention, setConvention] = useState<string | null>(null);
  const [city, setCity] = useState<string | null>(null);
  const [saved, setSaved] = useState("");
  if (settings.isLoading) return <Spinner />;
  const s = settings.data;
  if (!s) return <ErrorAlert error={settings.error} />;
  const conv = convention ?? s.convention ?? "";
  const place = city ?? s.observance_city ?? "";
  const chosen = s.conventions.find((c) => c.key === conv);
  return (
    <section className="card space-y-3 p-5" aria-labelledby="cal-settings">
      <h2 id="cal-settings" className="font-display text-lg font-semibold">
        {t("calendar.settingsTitle")}
      </h2>
      <p className="text-sm text-ink-muted">{t("calendar.settingsHint")}</p>
      <Field label={t("calendar.convention")} hint={chosen && !chosen.offered ? t("calendar.notOfferedHint") : undefined}>
        {(p) => (
          <Select {...p} value={conv} onChange={(e) => setConvention(e.target.value)}>
            <option value="">{t("calendar.noConvention")}</option>
            {s.conventions.map((c) => (
              <option key={c.key} value={c.key}>
                {c.label}
                {c.offered ? "" : ` (${t("calendar.notVerified")})`}
              </option>
            ))}
          </Select>
        )}
      </Field>
      <Field label={t("calendar.city")} hint={t("calendar.cityHint")}>
        {(p) => (
          <Select {...p} value={place} onChange={(e) => setCity(e.target.value)}>
            <option value="">{t("calendar.noCity")}</option>
            {s.cities.map((c) => (
              <option key={c.key} value={c.key}>
                {c.label}
              </option>
            ))}
          </Select>
        )}
      </Field>
      {!s.lunar_enabled && <Badge tone="saffron">{t("calendar.lunarOff")}</Badge>}
      <ErrorAlert error={set.error} />
      <LiveRegion message={saved} />
      <div className="flex items-center gap-3">
        <Button
          loading={set.isPending}
          onClick={() => set.mutate({ convention: conv || null, observance_city: place || null }, { onSuccess: () => setSaved(t("common.saved")) })}
        >
          {t("common.save")}
        </Button>
        {saved && <span className="text-sm text-green-800">{saved}</span>}
      </div>
    </section>
  );
}
