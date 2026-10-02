import { useState, type FormEvent } from "react";
import { useTranslation } from "react-i18next";
import { History, MapPin, Plus, Trash2 } from "lucide-react";
import type { GenealogicalDate, PlaceName, PlaceOut, PlaceType } from "../../api/types";
import { useCreatePlace, useGeotaggedPlaces, usePlaces, useUpdatePlace } from "../../api/hooks/people";
import { useTreeCtx } from "../../lib/tree-context";
import { Perm } from "../../lib/permissions";
import { useDebounced } from "../../lib/useDebounced";
import { emptyDate, normalizeDate } from "../../lib/dates";
import { SCRIPTS, detectScript } from "../../lib/names";
import { GenealogicalDateEditor } from "../../components/dates/GenealogicalDateEditor";
import { DateText } from "../../components/dates/DateText";
import { hasDate } from "../../components/person/PersonForm";
import { Button } from "../../components/ui/Button";
import { Dialog } from "../../components/ui/Dialog";
import { EmptyState, ErrorAlert, PageHeader, Spinner } from "../../components/ui/feedback";
import { Field, Select, TextInput } from "../../components/ui/form";
import { Badge } from "../../components/ui/Badge";
import { GeoFields, geoBody, geoDraftFrom, geoErrors } from "../../components/geo/GeoFields";
import { MapPreview } from "../../components/geo/MapPreview";
import { formatCoords } from "../../lib/geo";

export const PLACE_TYPES: PlaceType[] = ["village", "town", "city", "tehsil", "district", "state", "country", "temple", "shrine", "ancestral_house", "property", "land_parcel", "neighbourhood", "other"];

export function PlacesPage() {
  const { t } = useTranslation();
  const { treeId, can } = useTreeCtx();
  const [q, setQ] = useState("");
  const debounced = useDebounced(q.trim(), 250);
  const places = usePlaces(treeId, debounced);
  const [editing, setEditing] = useState<PlaceOut | "new" | null>(null);
  // Researchers (source.write) may add places but not edit canonical ones (server SEC-8).
  const canCreate = can(Perm.PERSON_WRITE) || can(Perm.PROPERTY_WRITE) || can(Perm.SOURCE_WRITE);
  const canWrite = can(Perm.PERSON_WRITE) || can(Perm.PROPERTY_WRITE);
  return (
    <div>
      <PageHeader
        title={t("places.title")}
        subtitle={t("places.subtitle")}
        actions={
          canCreate ? (
            <Button icon={<Plus className="size-4" aria-hidden />} onClick={() => setEditing("new")}>
              {t("places.create")}
            </Button>
          ) : undefined
        }
      />
      <div className="mb-4 max-w-md">
        <Field label={t("places.search")} labelHidden>
          {(p) => <TextInput {...p} type="search" placeholder={t("places.searchPlaceholder")} value={q} onChange={(e) => setQ(e.target.value)} />}
        </Field>
      </div>
      {places.isLoading && <Spinner />}
      <ErrorAlert error={places.error} />
      <PlacesMap />
      {places.data?.items.length === 0 && <EmptyState icon={<MapPin className="size-10" aria-hidden />} title={t("places.empty")}>{t("places.emptyHint")}</EmptyState>}
      <ul className="grid gap-3 md:grid-cols-2">
        {places.data?.items.map((p) => (
          <li key={p.id} className="card p-4">
            <div className="flex items-start justify-between gap-2">
              <div>
                <h2 className="font-display text-lg font-semibold">{p.canonical_name}</h2>
                {(p.hierarchy ?? []).length > 1 && <p className="text-xs text-ink-muted">{(p.hierarchy ?? []).join(" › ")}</p>}
              </div>
              <Badge tone="stone">{t(`enum.placeType.${p.place_type}`)}</Badge>
            </div>
            {p.local_names.length > 0 && (
              <p className="mt-2 text-sm">
                {p.local_names.map((n, i) => (
                  <span key={i} lang={(n.language as string) ?? undefined} className="mr-2">
                    {String(n.name)}
                  </span>
                ))}
              </p>
            )}
            {p.historical_names.length > 0 && (
              <div className="mt-2">
                <p className="flex items-center gap-1 text-xs font-semibold uppercase tracking-wide text-ink-muted">
                  <History className="size-3.5" aria-hidden /> {t("places.historicalNames")}
                </p>
                <ul className="text-sm">
                  {p.historical_names.map((n, i) => (
                    <li key={i}>
                      <span lang={(n.language as string) ?? undefined}>{String(n.name)}</span>
                      {!!(n.valid_from || n.valid_to) && (
                        <span className="ml-1 text-xs text-ink-muted">
                          ({n.valid_from ? <DateText date={n.valid_from as GenealogicalDate} showOriginal={false} /> : "?"} – {n.valid_to ? <DateText date={n.valid_to as GenealogicalDate} showOriginal={false} /> : "?"})
                        </span>
                      )}
                      {n.note ? <span className="block text-xs text-ink-muted">{String(n.note)}</span> : null}
                    </li>
                  ))}
                </ul>
              </div>
            )}
            {[p.district, p.state, p.country].some(Boolean) && <p className="mt-1 text-sm">{[p.locality, p.district, p.state, p.country].filter(Boolean).join(", ")}</p>}
            {p.latitude != null && p.longitude != null ? (
              <p className="mt-1 flex flex-wrap items-center gap-1 text-xs text-ink-muted">
                <MapPin className="size-3.5" aria-hidden />
                {formatCoords({ latitude: p.latitude, longitude: p.longitude })} · {t(`enum.locationPrecision.${p.location_precision ?? "unknown"}`)}
                {p.coordinates_coarsened && <Badge tone="stone">{t("geo.coarsened")}</Badge>}
              </p>
            ) : (
              <p className="mt-1 text-xs text-ink-muted">{t("geo.notGeotagged")}</p>
            )}
            {p.lgd_code && <p className="mt-1 text-xs text-ink-muted">LGD: {p.lgd_code}</p>}
            {canWrite && (
              <Button size="sm" variant="ghost" className="mt-2" onClick={() => setEditing(p)}>
                {t("common.edit")}
              </Button>
            )}
          </li>
        ))}
      </ul>
      {editing && <PlaceDialog place={editing === "new" ? null : editing} onClose={() => setEditing(null)} />}
    </div>
  );
}

interface NameDraft {
  name: string;
  language: string;
  script: string;
  from: GenealogicalDate;
  to: GenealogicalDate;
  note: string;
}

function toNameDraft(n: Record<string, unknown>): NameDraft {
  return {
    name: String(n.name ?? ""),
    language: String(n.language ?? ""),
    script: String(n.script ?? ""),
    from: (n.valid_from as GenealogicalDate) ?? emptyDate(),
    to: (n.valid_to as GenealogicalDate) ?? emptyDate(),
    note: String(n.note ?? ""),
  };
}

function fromNameDraft(n: NameDraft): PlaceName {
  return {
    name: n.name.trim(),
    language: n.language || null,
    script: n.script || null,
    valid_from: hasDate(n.from) ? normalizeDate(n.from) : null,
    valid_to: hasDate(n.to) ? normalizeDate(n.to) : null,
    note: n.note.trim() || null,
  };
}

/** Every geotagged place in the tree on the tile-free map preview. */
function PlacesMap() {
  const { t } = useTranslation();
  const { treeId } = useTreeCtx();
  const [open, setOpen] = useState(false);
  const geo = useGeotaggedPlaces(treeId, open);
  return (
    <details className="card mb-4 p-3" open={open} onToggle={(e) => setOpen((e.target as HTMLDetailsElement).open)}>
      <summary className="cursor-pointer font-semibold">{t("geo.placesMap")}</summary>
      {open && geo.isLoading && <Spinner />}
      {geo.data && (
        <div className="mt-3">
          <MapPreview
            title={t("places.title")}
            pins={geo.data.items
              .filter((p) => p.latitude != null && p.longitude != null)
              .map((p) => ({ id: p.id, label: p.map_label || p.canonical_name, kind: "place", latitude: p.latitude!, longitude: p.longitude!, precision: p.location_precision, coarsened: p.coordinates_coarsened }))}
          />
        </div>
      )}
    </details>
  );
}

function PlaceDialog({ place, onClose }: { place: PlaceOut | null; onClose: () => void }) {
  const { t } = useTranslation();
  const { treeId, can } = useTreeCtx();
  const [geo, setGeo] = useState(() => geoDraftFrom(place));
  const create = useCreatePlace(treeId);
  const update = useUpdatePlace(treeId);
  const parents = usePlaces(treeId, "");
  const [name, setName] = useState(place?.canonical_name ?? "");
  const [type, setType] = useState<PlaceType>(place?.place_type ?? "village");
  const [parent, setParent] = useState(place?.parent_place_id ?? "");
  const [lgd, setLgd] = useState(place?.lgd_code ?? "");
  const [local, setLocal] = useState<NameDraft[]>((place?.local_names ?? []).map(toNameDraft));
  const [historical, setHistorical] = useState<NameDraft[]>((place?.historical_names ?? []).map(toNameDraft));
  const [submitted, setSubmitted] = useState(false);
  const mutation = place ? update : create;
  const submit = (e: FormEvent) => {
    e.preventDefault();
    setSubmitted(true);
    const ge = geoErrors(geo);
    if (!name.trim() || ge.latitude || ge.longitude || ge.pair) return;
    const body = {
      ...geoBody(geo, place, can(Perm.PRIVACY_MANAGE)),
      canonical_name: name.trim(),
      place_type: type,
      parent_place_id: parent || null,
      lgd_code: lgd.trim() || null,
      local_names: local.filter((n) => n.name.trim()).map(fromNameDraft),
      historical_names: historical.filter((n) => n.name.trim()).map(fromNameDraft),
    };
    if (place) update.mutate({ id: place.id, body }, { onSuccess: onClose });
    else create.mutate(body, { onSuccess: onClose });
  };
  const blank = (): NameDraft => ({ name: "", language: "", script: "", from: emptyDate(), to: emptyDate(), note: "" });

  const renderNames = (list: NameDraft[], set: (l: NameDraft[]) => void, withDates: boolean, label: string) => (
    <fieldset className="space-y-2 rounded-lg border border-stone-300 p-3">
      <legend className="px-1 text-sm font-semibold">{label}</legend>
      {list.map((n, i) => (
        <div key={i} className="space-y-2 rounded-md bg-parchment p-2">
          <div className="grid grid-cols-1 gap-2 sm:grid-cols-[1fr_12rem_auto]">
            <Field label={t("places.nameN", { n: i + 1 })}>
              {(p) => (
                <TextInput
                  {...p}
                  lang={n.language || undefined}
                  value={n.name}
                  onChange={(e) => {
                    const det = detectScript(e.target.value);
                    set(list.map((x, j) => (j === i ? { ...x, name: e.target.value, ...(det && !x.script ? { script: det.script, language: det.language } : {}) } : x)));
                  }}
                />
              )}
            </Field>
            <Field label={t("names.script")}>
              {(p) => (
                <Select
                  {...p}
                  value={`${n.language}|${n.script}`}
                  onChange={(e) => {
                    const [language, script] = e.target.value.split("|");
                    set(list.map((x, j) => (j === i ? { ...x, language, script } : x)));
                  }}
                >
                  <option value="|">{t("common.none")}</option>
                  {SCRIPTS.map((s) => (
                    <option key={`${s.language}|${s.script}`} value={`${s.language}|${s.script}`}>
                      {s.label}
                    </option>
                  ))}
                </Select>
              )}
            </Field>
            <button type="button" className="self-end rounded p-2 text-red-800 hover:bg-red-50" onClick={() => set(list.filter((_, j) => j !== i))} aria-label={t("places.removeName", { n: i + 1 })}>
              <Trash2 className="size-4" aria-hidden />
            </button>
          </div>
          {withDates && (
            <div className="grid grid-cols-1 gap-2 md:grid-cols-2">
              <GenealogicalDateEditor legend={t("places.validFrom")} value={n.from} onChange={(from) => set(list.map((x, j) => (j === i ? { ...x, from } : x)))} />
              <GenealogicalDateEditor legend={t("places.validTo")} value={n.to} onChange={(to) => set(list.map((x, j) => (j === i ? { ...x, to } : x)))} />
            </div>
          )}
        </div>
      ))}
      <Button size="sm" variant="secondary" icon={<Plus className="size-3.5" aria-hidden />} onClick={() => set([...list, blank()])}>
        {t("places.addName")}
      </Button>
    </fieldset>
  );

  return (
    <Dialog
      open
      onClose={onClose}
      size="lg"
      title={place ? t("places.editTitle") : t("places.create")}
      footer={
        <>
          <Button variant="secondary" onClick={onClose}>
            {t("common.cancel")}
          </Button>
          <Button type="submit" form="place-form" loading={mutation.isPending}>
            {t("common.save")}
          </Button>
        </>
      }
    >
      <form id="place-form" onSubmit={submit} className="space-y-3" noValidate>
        <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
          <Field label={t("places.canonicalName")} required error={submitted && !name.trim() ? t("common.required") : null}>
            {(p) => <TextInput {...p} value={name} onChange={(e) => setName(e.target.value)} />}
          </Field>
          <Field label={t("places.type")}>
            {(p) => (
              <Select {...p} value={type} onChange={(e) => setType(e.target.value as PlaceType)}>
                {PLACE_TYPES.map((pt) => (
                  <option key={pt} value={pt}>
                    {t(`enum.placeType.${pt}`)}
                  </option>
                ))}
              </Select>
            )}
          </Field>
          <Field label={t("places.parent")} hint={t("places.parentHint")}>
            {(p) => (
              <Select {...p} value={parent} onChange={(e) => setParent(e.target.value)}>
                <option value="">{t("common.none")}</option>
                {parents.data?.items
                  .filter((x) => x.id !== place?.id)
                  .map((x) => (
                    <option key={x.id} value={x.id}>
                      {(x.hierarchy ?? []).length ? (x.hierarchy ?? []).join(", ") : x.canonical_name}
                    </option>
                  ))}
              </Select>
            )}
          </Field>
          <Field label={t("places.lgd")} hint={t("places.lgdHint")}>
            {(p) => <TextInput {...p} value={lgd} onChange={(e) => setLgd(e.target.value)} />}
          </Field>
        </div>
        <GeoFields value={geo} onChange={setGeo} showErrors={submitted} canPrivacy={can(Perm.PRIVACY_MANAGE)} coarsened={!!place?.coordinates_coarsened} />
        {renderNames(local, setLocal, false, t("places.localNames"))}
        {renderNames(historical, setHistorical, true, t("places.historicalNames"))}
        <ErrorAlert error={mutation.error} />
      </form>
    </Dialog>
  );
}
