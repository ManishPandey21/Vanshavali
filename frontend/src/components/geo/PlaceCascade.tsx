import { useState } from "react";
import { useTranslation } from "react-i18next";
import { Landmark, MapPin, X } from "lucide-react";
import { useGeoPin, useGeoUnits } from "../../api/hooks/geo";
import type { GeoUnit } from "../../api/types";
import { useDebounced } from "../../lib/useDebounced";
import { Button } from "../ui/Button";
import { Combobox, type ComboOption } from "../ui/Combobox";
import { Field, Select, TextInput } from "../ui/form";

/** "Pindra, Varanasi, Uttar Pradesh" — the unit's ancestors, nearest first. */
export function unitTrail(u: GeoUnit): string {
  return [...(u.path ?? [])].reverse().map((p) => p.name_en).join(", ");
}

function unitLabel(u: GeoUnit) {
  return (
    <span className="flex flex-col">
      <span>
        <span className="font-medium">{u.name_en}</span>
        {u.name_local && (
          <span className="text-ink-muted" lang={u.local_script === "Deva" ? "hi" : undefined}>
            {" "}
            · {u.name_local}
          </span>
        )}
      </span>
      <span className="text-xs text-ink-muted">{unitTrail(u)}</span>
    </span>
  );
}

const option = (u: GeoUnit, level: string): ComboOption<GeoUnit> => ({
  key: `${u.level}:${u.code}`,
  value: u,
  label: (
    <span className="flex items-start justify-between gap-2">
      {unitLabel(u)}
      <span className="shrink-0 text-[11px] uppercase tracking-wide text-ink-muted">{level}</span>
    </span>
  ),
  textValue: u.name_en,
});

/**
 * Optional link from a family place to the official directory (ADR-0019 §5). Three ways in: search
 * any name (English, Hindi, other spellings, former names), step by step from the state, or PIN
 * first. Picking a unit only *suggests* values to the form (via `onPick`); the family's own place
 * name and historical names are never overwritten. If the directory is switched off or has no
 * active snapshot, nothing is shown and the form stays free text.
 */
export function PlaceCascade({ linked, onPick, onUnlink }: { linked: GeoUnit | null; onPick: (u: GeoUnit) => void; onUnlink: () => void }) {
  const { t } = useTranslation();
  const levelName = (u: GeoUnit) => (u.level === "subdistrict" && u.local_term ? u.local_term : t(`geoDir.level.${u.level}`));
  const [q, setQ] = useState("");
  const debounced = useDebounced(q.trim(), 250);
  const search = useGeoUnits({ q: debounced }, debounced.length >= 2);
  const states = useGeoUnits({});
  const [stateCode, setStateCode] = useState("");
  const [districtCode, setDistrictCode] = useState("");
  const [subCode, setSubCode] = useState("");
  const [villageQ, setVillageQ] = useState("");
  const districts = useGeoUnits({ parent_level: "state", parent_code: stateCode, level: "district" }, !!stateCode);
  const subs = useGeoUnits({ parent_level: "district", parent_code: districtCode, level: "subdistrict" }, !!districtCode);
  const towns = useGeoUnits({ parent_level: "district", parent_code: districtCode, level: "town" }, !!districtCode);
  const villageDebounced = useDebounced(villageQ.trim(), 200);
  const villages = useGeoUnits({ parent_level: "subdistrict", parent_code: subCode, q: villageDebounced }, !!subCode);
  const [pin, setPin] = useState("");
  const pinQ = useGeoPin(pin);

  if (states.isError || (states.data && !states.data.snapshot)) return null;
  const snapshot = states.data?.snapshot;
  const subLabel = subs.data?.items.find((s) => s.local_term)?.local_term ?? t("geoDir.level.subdistrict");
  const pick = (u: GeoUnit) => {
    onPick(u);
    setQ("");
  };
  const lastStep = [...(villages.data?.items ?? []), ...(subCode ? [] : (towns.data?.items ?? []))];

  return (
    <fieldset className="space-y-3 rounded-lg border border-stone-300 p-3">
      <legend className="flex items-center gap-1.5 px-1 text-sm font-semibold">
        <Landmark className="size-4" aria-hidden />
        {t("geoDir.title")}
      </legend>
      <p className="text-xs text-ink-muted">{t("geoDir.intro")}</p>

      {linked ? (
        <div role="status" className="flex flex-wrap items-start justify-between gap-2 rounded-md bg-leaf-50 p-2 text-sm">
          <div>
            <p className="font-medium">
              {t("geoDir.linked")}: {linked.name_en}
              {linked.name_local && <span lang="hi"> · {linked.name_local}</span>}
            </p>
            <p className="text-xs text-ink-muted">
              {unitTrail(linked)} · {levelName(linked)} {linked.code}
              {linked.status !== "current" && <> · {t(`geoDir.status.${linked.status}`)}</>}
            </p>
          </div>
          <Button size="sm" variant="ghost" icon={<X className="size-3.5" aria-hidden />} onClick={onUnlink}>
            {t("geoDir.unlink")}
          </Button>
        </div>
      ) : (
        <>
          <Combobox<GeoUnit>
            label={t("geoDir.search")}
            hint={t("geoDir.searchHint")}
            text={q}
            onTextChange={setQ}
            options={(search.data?.items ?? []).map((u) => option(u, levelName(u)))}
            onSelect={pick}
            loading={search.isFetching}
            emptyText={debounced.length >= 2 ? t("geoDir.noMatch") : t("geoDir.typeMore")}
          />
          <details className="rounded-md border border-stone-200 p-2">
            <summary className="cursor-pointer text-sm font-medium">{t("geoDir.stepByStep")}</summary>
            <div className="mt-2 grid grid-cols-1 gap-2 sm:grid-cols-2">
              <Field label={t("geoDir.level.state")}>
                {(p) => (
                  <Select
                    {...p}
                    value={stateCode}
                    onChange={(e) => {
                      setStateCode(e.target.value);
                      setDistrictCode("");
                      setSubCode("");
                    }}
                  >
                    <option value="">{t("geoDir.choose")}</option>
                    {(states.data?.items ?? []).map((s) => (
                      <option key={s.code} value={s.code}>
                        {s.name_en}
                        {s.name_local ? ` · ${s.name_local}` : ""}
                      </option>
                    ))}
                  </Select>
                )}
              </Field>
              <Field label={t("geoDir.level.district")}>
                {(p) => (
                  <Select
                    {...p}
                    value={districtCode}
                    disabled={!stateCode}
                    onChange={(e) => {
                      setDistrictCode(e.target.value);
                      setSubCode("");
                    }}
                  >
                    <option value="">{t("geoDir.choose")}</option>
                    {(districts.data?.items ?? []).map((s) => (
                      <option key={s.code} value={s.code}>
                        {s.name_en}
                        {s.name_local ? ` · ${s.name_local}` : ""}
                      </option>
                    ))}
                  </Select>
                )}
              </Field>
              <Field label={subLabel}>
                {(p) => (
                  <Select {...p} value={subCode} disabled={!districtCode} onChange={(e) => setSubCode(e.target.value)}>
                    <option value="">{t("geoDir.choose")}</option>
                    {(subs.data?.items ?? []).map((s) => (
                      <option key={s.code} value={s.code}>
                        {s.name_en}
                        {s.name_local ? ` · ${s.name_local}` : ""}
                      </option>
                    ))}
                  </Select>
                )}
              </Field>
              <div>
                <Combobox<GeoUnit>
                  label={t("geoDir.villageOrTown")}
                  text={villageQ}
                  onTextChange={setVillageQ}
                  options={lastStep.map((u) => option(u, levelName(u)))}
                  onSelect={pick}
                  loading={villages.isFetching}
                  emptyText={districtCode ? t("geoDir.noMatch") : t("geoDir.chooseAbove")}
                />
              </div>
            </div>
            <div className="mt-2 flex flex-wrap gap-2">
              {(
                [
                  [stateCode, states.data?.items],
                  [districtCode, districts.data?.items],
                  [subCode, subs.data?.items],
                ] as const
              ).map(([code, items]) => {
                const u = code ? items?.find((x) => x.code === code) : undefined;
                return u ? (
                  <Button key={`${u.level}:${u.code}`} size="sm" variant="secondary" onClick={() => pick(u)}>
                    {t("geoDir.useThis", { name: u.name_en, level: levelName(u) })}
                  </Button>
                ) : null;
              })}
            </div>
          </details>
          <div className="grid grid-cols-1 gap-2 sm:grid-cols-[10rem_1fr]">
            <Field label={t("geoDir.pin")} hint={t("geoDir.pinHint")}>
              {(p) => <TextInput {...p} inputMode="numeric" maxLength={6} value={pin} onChange={(e) => setPin(e.target.value.replace(/\D/g, ""))} />}
            </Field>
            <div aria-live="polite" className="text-sm">
              {pinQ.data && !pinQ.data.offices.length && <p className="mt-6 text-ink-muted">{t("geoDir.pinNone")}</p>}
              {pinQ.data?.offices.map((o) => (
                <div key={o.office_name} className="mt-1">
                  <p className="flex items-center gap-1 text-xs font-semibold">
                    <MapPin className="size-3.5" aria-hidden />
                    {o.office_name} {o.office_type && <span className="font-normal text-ink-muted">({o.office_type})</span>}
                  </p>
                  <ul className="ml-5 flex flex-wrap gap-1">
                    {(o.units ?? []).map((u) => (
                      <li key={`${u.level}:${u.code}`}>
                        <Button size="sm" variant="subtle" onClick={() => pick(u)}>
                          {u.name_en} <span className="sr-only">({unitTrail(u)})</span>
                        </Button>
                      </li>
                    ))}
                  </ul>
                </div>
              ))}
              {pinQ.data && pinQ.data.offices.length > 0 && <p className="text-xs text-ink-muted">{t("geoDir.pinCaveat")}</p>}
            </div>
          </div>
        </>
      )}
      {snapshot && (
        <p className="text-[11px] text-ink-muted">
          {t("geoDir.source", { attribution: snapshot.attribution, label: snapshot.label })}
        </p>
      )}
    </fieldset>
  );
}

/** Place type that matches a directory level (the family can still change it). */
export function placeTypeFor(level: GeoUnit["level"]): "village" | "town" | "tehsil" | "district" | "state" | "country" | "other" {
  switch (level) {
    case "village":
      return "village";
    case "town":
    case "ulb":
      return "town";
    case "subdistrict":
    case "block":
      return "tehsil";
    case "district":
      return "district";
    case "state":
      return "state";
    case "country":
      return "country";
    default:
      return "other";
  }
}
