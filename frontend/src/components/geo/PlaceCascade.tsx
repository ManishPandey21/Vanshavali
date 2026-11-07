import { useEffect, useId, useRef, useState } from "react";
import { useTranslation } from "react-i18next";
import { Landmark, Mail, Search, X } from "lucide-react";
import type { GeoLevel, GeoUnitOut } from "../../api/types";
import { useGeoPincode, useGeoUnits } from "../../api/hooks/geo";
import { useDebounced } from "../../lib/useDebounced";
import { ancestryLabel, langOfScript } from "../../lib/lgd";
import { Combobox, type ComboOption } from "../ui/Combobox";
import { Button } from "../ui/Button";

export interface NotListed {
  state: GeoUnitOut | null;
  district: GeoUnitOut | null;
}

/** "Prayagraj · प्रयागराज": the English name with the local-script name marked up with its language. */
export function UnitName({ unit, className }: { unit: Pick<GeoUnitOut, "name_en" | "name_local" | "local_script">; className?: string }) {
  return (
    <span className={className}>
      <span>{unit.name_en}</span>
      {unit.name_local && unit.name_local !== unit.name_en && (
        <>
          <span aria-hidden> · </span>
          <span lang={langOfScript(unit.local_script)}>{unit.name_local}</span>
        </>
      )}
    </span>
  );
}

function useUnitOptions(units: GeoUnitOut[], showPath: boolean): ComboOption<GeoUnitOut>[] {
  const { t } = useTranslation();
  return units.map((u) => ({
    key: `${u.level}:${u.lgd_code}`,
    value: u,
    textValue: u.name_en,
    label: (
      <span className="flex flex-col">
        <UnitName unit={u} className="font-medium" />
        <span className="text-xs text-ink-muted">
          {[showPath ? ancestryLabel(u) : null, u.level === "urban_body" ? (u.category ?? t("lgd.level.urban_body")) : null, u.match?.reason === "alias" ? t("lgd.matchAlias", { name: u.match.text }) : null]
            .filter(Boolean)
            .join(" · ")}
        </span>
      </span>
    ),
  }));
}

/** One level of the cascade: a type-ahead over the children of `parent`, or a chosen unit with "Change". */
function LevelPicker({
  label,
  level,
  parent,
  parentLevel,
  value,
  onChange,
  extraLevel,
}: {
  label: string;
  level: GeoLevel;
  parent: GeoUnitOut | null;
  parentLevel?: GeoLevel;
  value: GeoUnitOut | null;
  onChange: (u: GeoUnitOut | null) => void;
  /** also list this level under the parent's district (urban bodies next to villages) */
  extraLevel?: { level: GeoLevel; parent: GeoUnitOut | null };
}) {
  const { t } = useTranslation();
  const [text, setText] = useState("");
  const q = useDebounced(text.trim(), 300);
  const searching = q.length >= 2;
  const ready = level === "state" || !!parent;
  const scope = parent ? { parent: parent.lgd_code, parentLevel: parentLevel ?? parent.level } : {};
  const list = useGeoUnits({ level, ...scope }, ready && !searching && !value);
  const extra = useGeoUnits(
    { level: extraLevel?.level, parent: extraLevel?.parent?.lgd_code, parentLevel: extraLevel?.parent?.level },
    ready && !searching && !value && !!extraLevel?.parent,
  );
  // a search covers both villages and urban bodies when both are offered (no level filter)
  const search = useGeoUnits({ level: extraLevel ? undefined : level, q, limit: 30, ...(extraLevel?.parent ? { parent: extraLevel.parent.lgd_code, parentLevel: extraLevel.parent.level } : scope) }, ready && searching && !value);
  const units = searching ? (search.data?.items ?? []) : [...(list.data?.items ?? []), ...(extra.data?.items ?? [])];
  const filtered = units.slice(0, 50);
  const options = useUnitOptions(filtered, false);
  const rootRef = useRef<HTMLDivElement>(null);
  const refocus = useRef<"clear" | "input" | null>(null);
  const labelId = useId();
  useEffect(() => {
    const target = refocus.current;
    refocus.current = null;
    if (target === "clear") rootRef.current?.querySelector<HTMLElement>("button")?.focus();
    else if (target === "input") rootRef.current?.querySelector<HTMLElement>("input")?.focus();
  }, [value]);

  if (!ready) return null;
  if (value) {
    return (
      <div ref={rootRef} role="group" aria-labelledby={labelId}>
        <p id={labelId} className="label">
          {label}
        </p>
        <div className="flex items-center justify-between gap-2 rounded-lg border border-kumkum-200 bg-kumkum-50 px-3 py-2 text-sm">
          <UnitName unit={value} className="font-medium" />
          <button
            type="button"
            className="rounded p-1 hover:bg-white"
            aria-label={t("lgd.change", { level: label, name: value.name_en })}
            onClick={() => {
              refocus.current = "input";
              onChange(null);
            }}
          >
            <X className="size-4" aria-hidden />
          </button>
        </div>
      </div>
    );
  }
  return (
    <div ref={rootRef}>
      <Combobox
        label={label}
        text={text}
        onTextChange={setText}
        options={options}
        onSelect={(u) => {
          refocus.current = "clear";
          onChange(u);
          setText("");
        }}
        loading={list.isFetching || search.isFetching || extra.isFetching}
        placeholder={t("lgd.typeToFilter")}
        emptyText={t("lgd.noResults")}
      />
    </div>
  );
}

/**
 * Pick an Indian place from the Local Government Directory (ADR-0019 §7): State → District →
 * Sub-district (Tehsil, Taluka, Mandal… as the state calls it) → Village or town, a search over
 * all villages, and a PIN box that only *suggests* the district. "My village is not listed" keeps
 * free text. Nothing is filled until the user picks; the caller decides what a pick changes.
 *
 * Renders nothing when the directory is switched off or not loaded: the form keeps its free-text
 * place fields.
 */
export function PlaceCascade({
  onPick,
  onNotListed,
  headingLevel = 3,
}: {
  onPick: (u: GeoUnitOut) => void;
  onNotListed?: (n: NotListed) => void;
  headingLevel?: 2 | 3 | 4;
}) {
  const { t } = useTranslation();
  const H = `h${headingLevel}` as "h2" | "h3" | "h4";
  const states = useGeoUnits({ level: "state" });
  const [state, setState] = useState<GeoUnitOut | null>(null);
  const [district, setDistrict] = useState<GeoUnitOut | null>(null);
  const [sub, setSub] = useState<GeoUnitOut | null>(null);
  const [all, setAll] = useState("");
  const [pin, setPin] = useState("");
  const [notListed, setNotListed] = useState(false);
  const allQ = useDebounced(all.trim(), 300);
  const scope = district ? { parent: district.lgd_code, parentLevel: "district" as GeoLevel } : state ? { parent: state.lgd_code, parentLevel: "state" as GeoLevel } : {};
  const allSearch = useGeoUnits({ q: allQ, limit: 30, ...scope }, allQ.length >= (state ? 2 : 3));
  const allOptions = useUnitOptions(allSearch.data?.items ?? [], true);
  const pinQ = useGeoPincode(pin.trim());
  const headingId = useId();

  if (states.isError || (states.data && states.data.items.length === 0)) return null;
  if (!states.data) return null;
  const snapshot = states.data.snapshot;
  const subLabel = t(`lgd.subDistrict.${state?.sub_district_label ?? "sub_district"}`);

  const chooseState = (u: GeoUnitOut | null) => {
    setState(u);
    setDistrict(null);
    setSub(null);
  };
  const chooseDistrict = (u: GeoUnitOut | null) => {
    setDistrict(u);
    setSub(null);
  };
  const deepest = sub ?? district ?? state;
  const levelName = (u: GeoUnitOut) => (u.level === "sub_district" ? subLabel : t(`lgd.level.${u.level}`));
  const pinDistricts = pinQ.data?.districts ?? [];

  return (
    <section aria-labelledby={headingId} className="space-y-3 rounded-lg border border-haldi-300 bg-haldi-100/40 p-3">
      <div>
        <H id={headingId} className="flex items-center gap-1.5 font-semibold">
          <Landmark className="size-4" aria-hidden />
          {t("lgd.title")}
        </H>
        <p className="hint">{t("lgd.hint")}</p>
      </div>

      <Combobox
        label={
          <span className="inline-flex items-center gap-1">
            <Search className="size-3.5" aria-hidden />
            {t("lgd.searchAll")}
          </span>
        }
        text={all}
        onTextChange={setAll}
        options={allOptions}
        onSelect={(u) => {
          setAll("");
          onPick(u);
        }}
        loading={allSearch.isFetching}
        placeholder={t("lgd.searchAllPlaceholder")}
        hint={state ? t("lgd.searchAllScoped", { place: (district ?? state).name_en }) : t("lgd.searchAllHint")}
        emptyText={t("lgd.noResults")}
      />

      <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
        <LevelPicker label={t("lgd.level.state")} level="state" parent={null} value={state} onChange={chooseState} />
        <LevelPicker label={t("lgd.level.district")} level="district" parent={state} value={district} onChange={chooseDistrict} />
        <LevelPicker label={subLabel} level="sub_district" parent={district} value={sub} onChange={setSub} />
        {district && (
          <LevelPicker
            label={t("lgd.level.villageOrTown")}
            level="village"
            parent={sub ?? district}
            value={null}
            onChange={(u) => u && onPick(u)}
            extraLevel={{ level: "urban_body", parent: district }}
          />
        )}
      </div>

      <div className="grid grid-cols-1 gap-2 sm:grid-cols-[10rem_1fr] sm:items-start">
        <div>
          <label htmlFor={`${headingId}-pin`} className="label inline-flex items-center gap-1">
            <Mail className="size-3.5" aria-hidden />
            {t("lgd.pin")}
          </label>
          <input
            id={`${headingId}-pin`}
            className="input"
            inputMode="numeric"
            autoComplete="postal-code"
            maxLength={6}
            value={pin}
            aria-describedby={`${headingId}-pin-hint`}
            onChange={(e) => setPin(e.target.value.replace(/\D/g, ""))}
          />
        </div>
        <div id={`${headingId}-pin-hint`} className="text-sm" aria-live="polite">
          {!pinQ.data && !pinQ.isError && <p className="hint">{t("lgd.pinHint")}</p>}
          {pinQ.isError && <p className="hint">{t("lgd.pinUnknown")}</p>}
          {pinQ.data && (
            <div className="space-y-1">
              <p className="text-xs text-ink-muted">{t("lgd.pinOffices", { pin: pinQ.data.pincode, offices: pinQ.data.offices.map((o) => o.office_name).join(", ") })}</p>
              {pinDistricts.length === 0 && <p className="hint">{t("lgd.pinNoDistrict")}</p>}
              <div className="flex flex-wrap gap-2">
                {pinDistricts.map((d) => {
                  const st = pinQ.data!.states.find((s) => s.lgd_code === d.state_code) ?? null;
                  return (
                    <Button
                      key={d.lgd_code}
                      size="sm"
                      variant="secondary"
                      onClick={() => {
                        setState(st);
                        setDistrict(d);
                        setSub(null);
                      }}
                    >
                      {t("lgd.useDistrict", { district: d.name_en, state: st?.name_en ?? "" })}
                    </Button>
                  );
                })}
              </div>
            </div>
          )}
        </div>
      </div>

      <div className="flex flex-wrap items-center gap-2">
        {deepest && (
          <Button size="sm" variant="secondary" onClick={() => onPick(deepest)}>
            {t("lgd.useUnit", { name: deepest.name_en, level: levelName(deepest) })}
          </Button>
        )}
        {onNotListed && (
          <Button
            size="sm"
            variant="ghost"
            onClick={() => {
              setNotListed(true);
              onNotListed({ state, district });
            }}
          >
            {t("lgd.notListed")}
          </Button>
        )}
      </div>
      <div aria-live="polite">{notListed && <p className="hint">{t("lgd.notListedDone")}</p>}</div>
      <p className="text-xs text-ink-muted">{t("lgd.attribution", { snapshot: snapshot.id })}</p>
    </section>
  );
}
