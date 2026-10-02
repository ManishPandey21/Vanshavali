import { useTranslation } from "react-i18next";
import type { Confidence, LocationPrecision, PlaceOut, PrivacyLevel } from "../../api/types";
import { parseCoordinate } from "../../lib/geo";
import { Field, Fieldset, Select, TextArea, TextInput } from "../ui/form";

export const PRECISIONS: LocationPrecision[] = ["exact", "approximate", "locality", "district", "state", "country", "unknown"];
const CONFIDENCES: Confidence[] = ["high", "medium", "low", "unknown"];
const COORD_PRIVACY: (PrivacyLevel | "")[] = ["", "FAMILY_BRANCH", "PRIVATE_TREE_ADMINS"];

export interface GeoDraft {
  locality: string;
  district: string;
  state: string;
  country: string;
  map_label: string;
  latitude: string;
  longitude: string;
  location_precision: LocationPrecision;
  geo_confidence: Confidence;
  geo_note: string;
  geocoding_source: string;
  coordinate_privacy: PrivacyLevel | "";
}

export function geoDraftFrom(p: PlaceOut | null): GeoDraft {
  return {
    locality: p?.locality ?? "",
    district: p?.district ?? "",
    state: p?.state ?? "",
    country: p?.country ?? "",
    map_label: p?.map_label ?? "",
    latitude: p?.latitude != null ? String(p.latitude) : "",
    longitude: p?.longitude != null ? String(p.longitude) : "",
    location_precision: p?.location_precision ?? "unknown",
    geo_confidence: p?.geo_confidence ?? "unknown",
    geo_note: p?.geo_note ?? "",
    geocoding_source: p?.geocoding_source ?? "",
    coordinate_privacy: p?.coordinate_privacy ?? "",
  };
}

export function geoErrors(d: GeoDraft): { latitude?: string; longitude?: string; pair?: boolean } {
  const lat = parseCoordinate(d.latitude, "lat");
  const lng = parseCoordinate(d.longitude, "lng");
  return {
    latitude: lat === "invalid" ? "lat" : undefined,
    longitude: lng === "invalid" ? "lng" : undefined,
    pair: (lat === null) !== (lng === null) && lat !== "invalid" && lng !== "invalid",
  };
}

/** Body fields for PlaceIn/PlaceUpdate. Coordinates are sent only when entered or changed. */
export function geoBody(d: GeoDraft, original: PlaceOut | null, canPrivacy: boolean): Record<string, unknown> {
  const s = (v: string) => v.trim() || null;
  const lat = parseCoordinate(d.latitude, "lat");
  const lng = parseCoordinate(d.longitude, "lng");
  const body: Record<string, unknown> = {
    locality: s(d.locality),
    district: s(d.district),
    state: s(d.state),
    country: s(d.country),
    map_label: s(d.map_label),
    geo_note: s(d.geo_note),
    geocoding_source: s(d.geocoding_source),
    geo_confidence: d.geo_confidence,
    location_precision: d.location_precision,
  };
  const changed = !original || String(original.latitude ?? "") !== d.latitude.trim() || String(original.longitude ?? "") !== d.longitude.trim();
  // a coarsened view must never be written back over the exact coordinates
  if (changed && !original?.coordinates_coarsened) {
    body.latitude = typeof lat === "number" ? lat : null;
    body.longitude = typeof lng === "number" ? lng : null;
  }
  if (canPrivacy && (original?.coordinate_privacy ?? "") !== d.coordinate_privacy) body.coordinate_privacy = d.coordinate_privacy || null;
  if (original?.coordinates_coarsened) delete body.location_precision;
  return body;
}

export function GeoFields({ value, onChange, showErrors, canPrivacy, coarsened }: { value: GeoDraft; onChange: (d: GeoDraft) => void; showErrors: boolean; canPrivacy: boolean; coarsened?: boolean }) {
  const { t } = useTranslation();
  const set = (patch: Partial<GeoDraft>) => onChange({ ...value, ...patch });
  const errs = geoErrors(value);
  return (
    <Fieldset legend={t("geo.fieldset")} description={t("geo.fieldsetHint")}>
      <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
        <Field label={t("geo.locality")}>{(p) => <TextInput {...p} value={value.locality} onChange={(e) => set({ locality: e.target.value })} />}</Field>
        <Field label={t("geo.district")}>{(p) => <TextInput {...p} value={value.district} onChange={(e) => set({ district: e.target.value })} />}</Field>
        <Field label={t("geo.state")}>{(p) => <TextInput {...p} value={value.state} onChange={(e) => set({ state: e.target.value })} />}</Field>
        <Field label={t("geo.country")}>{(p) => <TextInput {...p} value={value.country} onChange={(e) => set({ country: e.target.value })} />}</Field>
        <Field label={t("geo.mapLabelField")} hint={t("geo.mapLabelHint")}>{(p) => <TextInput {...p} value={value.map_label} onChange={(e) => set({ map_label: e.target.value })} />}</Field>
      </div>
      {coarsened ? (
        <p className="mt-3 rounded-md bg-parchment-deep p-2 text-sm">{t("geo.coarsenedEdit")}</p>
      ) : (
        <div className="mt-3 grid grid-cols-1 gap-3 sm:grid-cols-3">
          <Field label={t("geo.latitude")} hint="25.3912" error={showErrors && (errs.latitude || errs.pair) ? t(errs.pair ? "geo.pairError" : "geo.latError") : null}>
            {(p) => <TextInput {...p} inputMode="decimal" value={value.latitude} onChange={(e) => set({ latitude: e.target.value })} />}
          </Field>
          <Field label={t("geo.longitude")} hint="82.5712" error={showErrors && errs.longitude ? t("geo.lngError") : null}>
            {(p) => <TextInput {...p} inputMode="decimal" value={value.longitude} onChange={(e) => set({ longitude: e.target.value })} />}
          </Field>
          <Field label={t("geo.precision")} hint={t("geo.precisionHint")}>
            {(p) => (
              <Select {...p} value={value.location_precision} onChange={(e) => set({ location_precision: e.target.value as LocationPrecision })}>
                {PRECISIONS.map((x) => (
                  <option key={x} value={x}>
                    {t(`enum.locationPrecision.${x}`)}
                  </option>
                ))}
              </Select>
            )}
          </Field>
        </div>
      )}
      <div className="mt-3 grid grid-cols-1 gap-3 sm:grid-cols-2">
        <Field label={t("geo.confidence")}>
          {(p) => (
            <Select {...p} value={value.geo_confidence} onChange={(e) => set({ geo_confidence: e.target.value as Confidence })}>
              {CONFIDENCES.map((c) => (
                <option key={c} value={c}>
                  {t(`enum.confidence.${c}`)}
                </option>
              ))}
            </Select>
          )}
        </Field>
        <Field label={t("geo.source")} hint={t("geo.sourceHint")}>{(p) => <TextInput {...p} value={value.geocoding_source} onChange={(e) => set({ geocoding_source: e.target.value })} />}</Field>
        {canPrivacy && (
          <Field label={t("geo.coordinatePrivacy")} hint={t("geo.coordinatePrivacyHint")}>
            {(p) => (
              <Select {...p} value={value.coordinate_privacy} onChange={(e) => set({ coordinate_privacy: e.target.value as PrivacyLevel | "" })}>
                {COORD_PRIVACY.map((lv) => (
                  <option key={lv} value={lv}>
                    {lv ? t(`enum.privacy.${lv}`) : t("geo.coordinatesAllMembers")}
                  </option>
                ))}
              </Select>
            )}
          </Field>
        )}
      </div>
      <Field label={t("geo.note")} hint={t("geo.noteHint")}>{(p) => <TextArea {...p} rows={2} value={value.geo_note} onChange={(e) => set({ geo_note: e.target.value })} />}</Field>
    </Fieldset>
  );
}
