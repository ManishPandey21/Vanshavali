import { useState, type FormEvent } from "react";
import { useTranslation } from "react-i18next";
import { GitFork, Plus, Trash2 } from "lucide-react";
import type { AreaUnit, GenealogicalDate, ParcelIn, ParcelOut, PropertyDetailOut, SubdivisionChildIn } from "../../../api/types";
import { useDeleteParcel, useParcelLineage, useSaveParcel, useSubdivide } from "../../../api/hooks/property";
import { useTreeCtx } from "../../../lib/tree-context";
import { emptyDate, normalizeDate } from "../../../lib/dates";
import { GenealogicalDateEditor } from "../../../components/dates/GenealogicalDateEditor";
import { hasDate } from "../../../components/person/PersonForm";
import { Button } from "../../../components/ui/Button";
import { ConfirmDialog, Dialog } from "../../../components/ui/Dialog";
import { EmptyState, ErrorAlert, Spinner } from "../../../components/ui/feedback";
import { Checkbox, Field, Select, TextArea, TextInput } from "../../../components/ui/form";
import { AREA_UNITS } from "./common";

const ID_FIELDS = [
  "state_or_ut",
  "district",
  "tehsil_taluk",
  "village",
  "revenue_village_code",
  "survey_number",
  "khasra_or_gata_number",
  "khata_number",
  "khatauni_number",
  "patta_number",
  "plot_number",
  "subdivision_number",
  "land_use",
  "cadastral_map_reference",
  "state_portal_reference",
] as const;
type IdField = (typeof ID_FIELDS)[number];

export const ULPIN_RE = /^[A-Z0-9]{14}$/;

/** ULPIN (Bhu-Aadhaar) is exactly 14 alphanumerics. Returns an i18n key or null. */
export function ulpinError(v: string): string | null {
  const s = v.trim().toUpperCase();
  if (!s) return null;
  return ULPIN_RE.test(s) ? null : "property.parcel.ulpinInvalid";
}

/** Keys: letters, digits, space, _ . - (≤ 60). */
export function extraKeyError(k: string): string | null {
  return /^[A-Za-z0-9_.\- ]{1,60}$/.test(k) ? null : "property.parcel.extraKeyInvalid";
}

export function ParcelsPanel({ property, canWrite }: { property: PropertyDetailOut; canWrite: boolean }) {
  const { t } = useTranslation();
  const { treeId } = useTreeCtx();
  const [editing, setEditing] = useState<ParcelOut | "new" | null>(null);
  const [subdividing, setSubdividing] = useState<ParcelOut | null>(null);
  const [lineageOf, setLineageOf] = useState<string | null>(null);
  const [deleting, setDeleting] = useState<ParcelOut | null>(null);
  const del = useDeleteParcel(treeId, property.id);
  const parcels = property.parcels ?? [];
  return (
    <section aria-labelledby="parcels-title" className="space-y-3">
      <div className="flex items-center justify-between">
        <h2 id="parcels-title" className="font-display text-lg font-semibold">
          {t("property.parcels")}
        </h2>
        {canWrite && (
          <Button size="sm" icon={<Plus className="size-4" aria-hidden />} onClick={() => setEditing("new")}>
            {t("property.parcel.add")}
          </Button>
        )}
      </div>
      {parcels.length === 0 && <EmptyState title={t("property.parcel.none")}>{t("property.parcel.noneHint")}</EmptyState>}
      <ul className="space-y-2">
        {parcels.map((p) => (
          <li key={p.id} className={`card p-3 ${p.parent_parcel_id ? "ml-4 border-l-4 border-l-haldi-300" : ""}`}>
            <div className="flex flex-wrap items-start justify-between gap-2">
              <div>
                <p className="font-semibold">{p.label}</p>
                <p className="text-xs text-ink-muted">{[p.village, p.tehsil_taluk, p.district, p.state_or_ut].filter(Boolean).join(", ")}</p>
                <dl className="mt-1 flex flex-wrap gap-x-4 gap-y-0.5 text-xs">
                  {ID_FIELDS.filter((k) => !["state_or_ut", "district", "tehsil_taluk", "village"].includes(k) && p[k]).map((k) => (
                    <div key={k} className="flex gap-1">
                      <dt className="text-ink-muted">{t(`property.parcel.f.${k}`)}:</dt>
                      <dd className="font-mono">{p[k]}</dd>
                    </div>
                  ))}
                  {p.ulpin && (
                    <div className="flex gap-1">
                      <dt className="text-ink-muted">ULPIN:</dt>
                      <dd className="font-mono">{p.ulpin}</dd>
                    </div>
                  )}
                  {Object.entries(p.extra_identifiers ?? {}).map(([k, v]) => (
                    <div key={k} className="flex gap-1">
                      <dt className="text-ink-muted">{k}:</dt>
                      <dd className="font-mono">{String(v)}</dd>
                    </div>
                  ))}
                </dl>
                {p.area != null && (
                  <p className="mt-1 text-sm">
                    {t("property.parcel.area")}: {String(p.area)} {p.area_unit ? t(`enum.areaUnit.${p.area_unit}`, { defaultValue: p.area_unit }) : ""}
                    {p.area_sq_m != null && <span className="text-xs text-ink-muted"> ≈ {Number(p.area_sq_m).toLocaleString()} m²</span>}
                    {p.area_conversion_note && <span className="block text-xs text-ink-muted">{p.area_conversion_note}</span>}
                  </p>
                )}
              </div>
              <div className="flex flex-wrap gap-1">
                <Button size="sm" variant="ghost" icon={<GitFork className="size-4" aria-hidden />} onClick={() => setLineageOf(lineageOf === p.id ? null : p.id)} aria-expanded={lineageOf === p.id}>
                  {t("property.parcel.lineage")}
                </Button>
                {canWrite && (
                  <>
                    <Button size="sm" variant="ghost" onClick={() => setEditing(p)}>
                      {t("common.edit")}
                    </Button>
                    <Button size="sm" variant="ghost" onClick={() => setSubdividing(p)}>
                      {t("property.parcel.subdivide")}
                    </Button>
                    <Button size="sm" variant="ghost" icon={<Trash2 className="size-4" aria-hidden />} onClick={() => setDeleting(p)} aria-label={t("property.parcel.delete", { label: p.label })} />
                  </>
                )}
              </div>
            </div>
            {lineageOf === p.id && <ParcelLineage propertyId={property.id} parcelId={p.id} />}
          </li>
        ))}
      </ul>
      {editing && <ParcelDialog propertyId={property.id} parcel={editing === "new" ? null : editing} parcels={parcels} onClose={() => setEditing(null)} />}
      {subdividing && <SubdivideDialog propertyId={property.id} parcel={subdividing} onClose={() => setSubdividing(null)} />}
      <ConfirmDialog
        open={!!deleting}
        onClose={() => setDeleting(null)}
        title={t("property.parcel.deleteTitle")}
        body={deleting?.label}
        confirmLabel={t("common.delete")}
        danger
        loading={del.isPending}
        onConfirm={() => deleting && del.mutate(deleting.id, { onSuccess: () => setDeleting(null) })}
      >
        <ErrorAlert error={del.error} />
      </ConfirmDialog>
    </section>
  );
}

function ParcelLineage({ propertyId, parcelId }: { propertyId: string; parcelId: string }) {
  const { t } = useTranslation();
  const { treeId } = useTreeCtx();
  const q = useParcelLineage(treeId, propertyId, parcelId);
  if (q.isLoading) return <Spinner />;
  if (!q.data) return <ErrorAlert error={q.error} />;
  const l = q.data;
  return (
    <div className="mt-2 grid gap-2 rounded-lg bg-parchment p-3 text-sm sm:grid-cols-3">
      <div>
        <p className="text-xs font-semibold uppercase text-ink-muted">{t("property.parcel.ancestors")}</p>
        {(l.ancestors ?? []).length ? (
          <ol>{(l.ancestors ?? []).map((a) => <li key={a.id}>↑ {a.label}</li>)}</ol>
        ) : (
          <p className="text-ink-muted">{t("common.none")}</p>
        )}
      </div>
      <div>
        <p className="text-xs font-semibold uppercase text-ink-muted">{t("property.parcel.siblings")}</p>
        {(l.siblings ?? []).length ? <ul>{(l.siblings ?? []).map((a) => <li key={a.id}>{a.label}</li>)}</ul> : <p className="text-ink-muted">{t("common.none")}</p>}
      </div>
      <div>
        <p className="text-xs font-semibold uppercase text-ink-muted">{t("property.parcel.descendants")}</p>
        {(l.descendants ?? []).length ? (
          <ul>
            {(l.descendants ?? []).map((d) => (
              <li key={d.parcel.id} style={{ paddingLeft: `${(d.depth - 1) * 12}px` }}>
                ↳ {d.parcel.label}
              </li>
            ))}
          </ul>
        ) : (
          <p className="text-ink-muted">{t("common.none")}</p>
        )}
      </div>
    </div>
  );
}

type Draft = Record<IdField | "ulpin" | "area" | "notes", string> & { area_unit: AreaUnit | ""; parent: string; extras: { k: string; v: string }[] };

function toDraft(p: ParcelOut | null): Draft {
  const d = Object.fromEntries(ID_FIELDS.map((k) => [k, (p?.[k] as string | null) ?? ""])) as Record<IdField, string>;
  return {
    ...d,
    ulpin: p?.ulpin ?? "",
    area: p?.area != null ? String(p.area) : "",
    area_unit: (p?.area_unit as AreaUnit | null) ?? "",
    notes: p?.notes ?? "",
    parent: p?.parent_parcel_id ?? "",
    extras: Object.entries(p?.extra_identifiers ?? {}).map(([k, v]) => ({ k, v: String(v ?? "") })),
  };
}

function ParcelDialog({ propertyId, parcel, parcels, onClose }: { propertyId: string; parcel: ParcelOut | null; parcels: ParcelOut[]; onClose: () => void }) {
  const { t } = useTranslation();
  const { treeId } = useTreeCtx();
  const save = useSaveParcel(treeId, propertyId);
  const [d, setD] = useState<Draft>(() => toDraft(parcel));
  const [submitted, setSubmitted] = useState(false);
  const ulErr = ulpinError(d.ulpin);
  const areaErr = d.area.trim() && (Number.isNaN(Number(d.area)) || Number(d.area) < 0) ? "property.parcel.areaInvalid" : d.area.trim() && !d.area_unit ? "property.parcel.unitRequired" : null;
  const extraErr = d.extras.map((e) => (e.k.trim() ? extraKeyError(e.k.trim()) : null)).find(Boolean) ?? null;
  const submit = (e: FormEvent) => {
    e.preventDefault();
    setSubmitted(true);
    if (ulErr || areaErr || extraErr) return;
    const body: Record<string, unknown> = {};
    for (const k of ID_FIELDS) body[k] = d[k].trim() || null;
    body.ulpin = d.ulpin.trim() ? d.ulpin.trim().toUpperCase() : null;
    body.area = d.area.trim() ? d.area.trim() : null;
    body.area_unit = d.area_unit || null;
    body.notes = d.notes.trim() || null;
    body.parent_parcel_id = d.parent || null;
    body.extra_identifiers = Object.fromEntries(d.extras.filter((x) => x.k.trim()).map((x) => [x.k.trim(), x.v]));
    save.mutate({ id: parcel?.id, body: body as ParcelIn }, { onSuccess: onClose });
  };
  return (
    <Dialog
      open
      onClose={onClose}
      size="lg"
      title={parcel ? t("property.parcel.editTitle") : t("property.parcel.add")}
      description={t("property.parcel.intro")}
      footer={
        <>
          <Button variant="secondary" onClick={onClose}>
            {t("common.cancel")}
          </Button>
          <Button type="submit" form="parcel-form" loading={save.isPending}>
            {t("common.save")}
          </Button>
        </>
      }
    >
      <form id="parcel-form" onSubmit={submit} className="space-y-3" noValidate>
        <div className="grid grid-cols-1 gap-3 sm:grid-cols-3">
          {ID_FIELDS.map((k) => (
            <Field key={k} label={t(`property.parcel.f.${k}`)}>
              {(p) => <TextInput {...p} value={d[k]} onChange={(e) => setD({ ...d, [k]: e.target.value })} />}
            </Field>
          ))}
          <Field label="ULPIN" hint={t("property.parcel.ulpinHint")} error={ulErr && (submitted || d.ulpin.trim().length >= 14) ? t(ulErr) : null}>
            {(p) => <TextInput {...p} className="font-mono uppercase" maxLength={20} value={d.ulpin} onChange={(e) => setD({ ...d, ulpin: e.target.value })} />}
          </Field>
          <Field label={t("property.parcel.area")} error={submitted && areaErr ? t(areaErr) : null}>
            {(p) => <TextInput {...p} inputMode="decimal" value={d.area} onChange={(e) => setD({ ...d, area: e.target.value })} />}
          </Field>
          <Field label={t("property.parcel.areaUnit")} hint={t("property.parcel.unitHint")}>
            {(p) => (
              <Select {...p} value={d.area_unit} onChange={(e) => setD({ ...d, area_unit: e.target.value as AreaUnit })}>
                <option value="">—</option>
                {AREA_UNITS.map((u) => (
                  <option key={u} value={u}>
                    {t(`enum.areaUnit.${u}`)}
                  </option>
                ))}
              </Select>
            )}
          </Field>
          <Field label={t("property.parcel.parent")}>
            {(p) => (
              <Select {...p} value={d.parent} onChange={(e) => setD({ ...d, parent: e.target.value })}>
                <option value="">{t("common.none")}</option>
                {parcels
                  .filter((x) => x.id !== parcel?.id)
                  .map((x) => (
                    <option key={x.id} value={x.id}>
                      {x.label}
                    </option>
                  ))}
              </Select>
            )}
          </Field>
        </div>
        <fieldset className="space-y-2 rounded-lg border border-stone-300 p-3">
          <legend className="px-1 text-sm font-semibold">{t("property.parcel.extras")}</legend>
          <p className="text-xs text-ink-muted">{t("property.parcel.extrasHint")}</p>
          {d.extras.map((x, i) => (
            <div key={i} className="grid grid-cols-[1fr_1fr_auto] items-end gap-2">
              <Field label={t("property.parcel.extraKey")}>
                {(p) => <TextInput {...p} value={x.k} onChange={(e) => setD({ ...d, extras: d.extras.map((y, j) => (j === i ? { ...y, k: e.target.value } : y)) })} />}
              </Field>
              <Field label={t("property.parcel.extraValue")}>
                {(p) => <TextInput {...p} value={x.v} onChange={(e) => setD({ ...d, extras: d.extras.map((y, j) => (j === i ? { ...y, v: e.target.value } : y)) })} />}
              </Field>
              <Button size="sm" variant="ghost" onClick={() => setD({ ...d, extras: d.extras.filter((_, j) => j !== i) })} aria-label={t("common.delete")}>
                <Trash2 className="size-4" aria-hidden />
              </Button>
            </div>
          ))}
          {submitted && extraErr && <p className="field-error">{t(extraErr)}</p>}
          <Button size="sm" variant="secondary" icon={<Plus className="size-3.5" aria-hidden />} onClick={() => setD({ ...d, extras: [...d.extras, { k: "", v: "" }] })}>
            {t("property.parcel.addExtra")}
          </Button>
        </fieldset>
        <Field label={t("heritage.notes")}>{(p) => <TextArea {...p} rows={2} value={d.notes} onChange={(e) => setD({ ...d, notes: e.target.value })} />}</Field>
        <ErrorAlert error={save.error} />
      </form>
    </Dialog>
  );
}

interface ChildDraft {
  subdivision_number: string;
  survey_number: string;
  area: string;
  area_unit: AreaUnit | "";
}

function SubdivideDialog({ propertyId, parcel, onClose }: { propertyId: string; parcel: ParcelOut; onClose: () => void }) {
  const { t } = useTranslation();
  const { treeId } = useTreeCtx();
  const sub = useSubdivide(treeId, propertyId);
  const blank = (i: number): ChildDraft => ({ subdivision_number: `${parcel.subdivision_number ? `${parcel.subdivision_number}/` : ""}${i + 1}`, survey_number: parcel.survey_number ?? "", area: "", area_unit: (parcel.area_unit as AreaUnit | null) ?? "" });
  const [children, setChildren] = useState<ChildDraft[]>([blank(0), blank(1)]);
  const [date, setDate] = useState<GenealogicalDate>(emptyDate());
  const [record, setRecord] = useState(true);
  const [description, setDescription] = useState("");
  const submit = () => {
    const body = {
      children: children.map(
        (c): SubdivisionChildIn => ({
          village: parcel.village,
          district: parcel.district,
          tehsil_taluk: parcel.tehsil_taluk,
          state_or_ut: parcel.state_or_ut,
          khasra_or_gata_number: parcel.khasra_or_gata_number,
          survey_number: c.survey_number.trim() || null,
          subdivision_number: c.subdivision_number.trim() || null,
          area: c.area.trim() || null,
          area_unit: c.area.trim() ? c.area_unit || null : null,
        }),
      ),
      date: hasDate(date) ? normalizeDate(date) : null,
      description: description.trim() || null,
      record_event: record,
    };
    sub.mutate({ id: parcel.id, body }, { onSuccess: (r) => ((r.warnings ?? []).length ? undefined : onClose()) });
  };
  return (
    <Dialog
      open
      onClose={onClose}
      size="lg"
      title={t("property.parcel.subdivideTitle", { label: parcel.label })}
      footer={
        <>
          <Button variant="secondary" onClick={onClose}>
            {sub.isSuccess ? t("common.close") : t("common.cancel")}
          </Button>
          {!sub.isSuccess && (
            <Button loading={sub.isPending} onClick={submit}>
              {t("property.parcel.subdivide")}
            </Button>
          )}
        </>
      }
    >
      <div className="space-y-3">
        {children.map((c, i) => (
          <div key={i} className="grid grid-cols-2 items-end gap-2 sm:grid-cols-[1fr_1fr_1fr_1fr_auto]">
            <Field label={t("property.parcel.f.subdivision_number")}>{(p) => <TextInput {...p} value={c.subdivision_number} onChange={(e) => setChildren(children.map((x, j) => (j === i ? { ...x, subdivision_number: e.target.value } : x)))} />}</Field>
            <Field label={t("property.parcel.f.survey_number")}>{(p) => <TextInput {...p} value={c.survey_number} onChange={(e) => setChildren(children.map((x, j) => (j === i ? { ...x, survey_number: e.target.value } : x)))} />}</Field>
            <Field label={t("property.parcel.area")}>{(p) => <TextInput {...p} inputMode="decimal" value={c.area} onChange={(e) => setChildren(children.map((x, j) => (j === i ? { ...x, area: e.target.value } : x)))} />}</Field>
            <Field label={t("property.parcel.areaUnit")}>
              {(p) => (
                <Select {...p} value={c.area_unit} onChange={(e) => setChildren(children.map((x, j) => (j === i ? { ...x, area_unit: e.target.value as AreaUnit } : x)))}>
                  <option value="">—</option>
                  {AREA_UNITS.map((u) => (
                    <option key={u} value={u}>
                      {t(`enum.areaUnit.${u}`)}
                    </option>
                  ))}
                </Select>
              )}
            </Field>
            <Button size="sm" variant="ghost" disabled={children.length <= 1} onClick={() => setChildren(children.filter((_, j) => j !== i))} aria-label={t("common.delete")}>
              <Trash2 className="size-4" aria-hidden />
            </Button>
          </div>
        ))}
        <Button size="sm" variant="secondary" icon={<Plus className="size-3.5" aria-hidden />} onClick={() => setChildren([...children, blank(children.length)])}>
          {t("property.parcel.addChild")}
        </Button>
        <GenealogicalDateEditor legend={t("property.eventDate")} value={date} onChange={setDate} />
        <Field label={t("property.description")}>{(p) => <TextInput {...p} value={description} onChange={(e) => setDescription(e.target.value)} />}</Field>
        <Checkbox label={t("property.parcel.recordEvent")} checked={record} onChange={setRecord} />
        {(sub.data?.warnings ?? []).length > 0 && (
          <ul role="status" className="list-inside list-disc rounded-lg bg-haldi-100 p-3 text-sm text-haldi-700">
            {sub.data!.warnings!.map((w) => (
              <li key={w}>{w}</li>
            ))}
          </ul>
        )}
        <ErrorAlert error={sub.error} />
      </div>
    </Dialog>
  );
}
