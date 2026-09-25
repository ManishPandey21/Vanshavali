import { useState, type FormEvent } from "react";
import { useTranslation } from "react-i18next";
import { AlertTriangle, Edit3, Plus, Star, Trash2 } from "lucide-react";
import type { AstrologyIn, AstrologyOut, AstrologyProvenance, EvidenceStatus, GenealogicalDate, GenealogicalTime, PersonOut, PrivacyLevel } from "../../../api/types";
import { useAstrology, useBirthConflicts, useDeleteAstrology, useSaveAstrology } from "../../../api/hooks/documents";
import { useTreeCtx } from "../../../lib/tree-context";
import { Perm } from "../../../lib/permissions";
import { emptyDate, normalizeDate, validateDate, validateTime } from "../../../lib/dates";
import { nakshatras } from "../../../data/masterData/nakshatras";
import { rashis } from "../../../data/masterData/rashis";
import { DateText, TimeText } from "../../../components/dates/DateText";
import { GenealogicalDateEditor } from "../../../components/dates/GenealogicalDateEditor";
import { TimeEditor, TimezoneSelect } from "../../../components/dates/TimeEditor";
import { EvidenceBadge, PrivacyBadge, RedactionNotice } from "../../../components/person/badges";
import { EVIDENCE_STATUSES } from "../../../components/person/NameFields";
import { PRIVACY_LEVELS, hasDate } from "../../../components/person/PersonForm";
import { Button } from "../../../components/ui/Button";
import { ConfirmDialog, Dialog } from "../../../components/ui/Dialog";
import { EmptyState, ErrorAlert, Spinner } from "../../../components/ui/feedback";
import { Checkbox, Field, Select, TextArea, TextInput } from "../../../components/ui/form";
import { Badge } from "../../../components/ui/Badge";

const PROVENANCES: AstrologyProvenance[] = ["entered", "uploaded_chart", "calculated", "imported"];
const PAKSHAS = ["Shukla", "Krishna"];
const AYANAMSHAS = ["Lahiri", "Raman", "Krishnamurti"];

export function AstrologyTab({ person }: { person: PersonOut }) {
  const { t } = useTranslation();
  const { treeId, can } = useTreeCtx();
  const profiles = useAstrology(treeId, person.id);
  const del = useDeleteAstrology(treeId);
  const [editing, setEditing] = useState<AstrologyOut | "new" | null>(null);
  const [deleting, setDeleting] = useState<AstrologyOut | null>(null);
  const canWrite = can(Perm.ASTROLOGY_WRITE) && !!person.can_edit;
  const hidden = (person.redacted_fields ?? []).includes("astrology");
  return (
    <div className="space-y-6">
      <section aria-labelledby="astro-title" className="space-y-3">
        <div className="flex flex-wrap items-center justify-between gap-2">
          <h2 id="astro-title" className="font-display text-lg font-semibold">
            {t("astrology.title")}
          </h2>
          {canWrite && (
            <Button size="sm" icon={<Plus className="size-4" aria-hidden />} onClick={() => setEditing("new")}>
              {t("astrology.add")}
            </Button>
          )}
        </div>
        <p className="rounded-lg bg-parchment-deep p-3 text-xs text-ink-muted">{t("astrology.noCalculation")}</p>
        {profiles.isLoading && <Spinner />}
        <ErrorAlert error={profiles.error} />
        {hidden && <RedactionNotice />}
        {profiles.data && profiles.data.length === 0 && !hidden && <EmptyState title={t("astrology.none")} />}
        <ul className="grid gap-3 md:grid-cols-2">
          {profiles.data?.map((a) => (
            <li key={a.id} className="card p-4">
              <div className="flex flex-wrap items-center justify-between gap-2">
                <p className="flex items-center gap-1.5 text-xs font-semibold uppercase tracking-wide text-ink-muted">
                  {a.is_preferred && <Star className="size-3.5 fill-haldi-500 text-haldi-500" aria-label={t("astrology.preferred")} />}
                  {t(`enum.astroProvenance.${a.provenance_kind}`)}
                </p>
                <span className="flex flex-wrap gap-1">
                  <EvidenceBadge status={a.evidence_status} />
                  <PrivacyBadge level={a.privacy_level} />
                </span>
              </div>
              <dl className="mt-2 grid grid-cols-2 gap-x-3 gap-y-1 text-sm">
                {(
                  [
                    ["nakshatra", a.nakshatra ? `${a.nakshatra}${a.nakshatra_pada ? ` (${t("astrology.padaN", { n: a.nakshatra_pada })})` : ""}` : null],
                    ["rashi", a.rashi],
                    ["lagna", a.lagna],
                    ["tithi", a.tithi ? `${a.tithi}${a.paksha ? ` · ${a.paksha}` : ""}` : null],
                    ["lunar_month", a.lunar_month],
                    ["ayanamsha", a.ayanamsha],
                  ] as const
                ).map(([k, v]) =>
                  v ? (
                    <div key={k}>
                      <dt className="text-xs text-ink-muted">{t(`astrology.f.${k}`)}</dt>
                      <dd>{v}</dd>
                    </div>
                  ) : null,
                )}
              </dl>
              {(a.chart_birth_date || a.chart_birth_time || a.chart_birth_place) && (
                <div className="mt-2 rounded-lg bg-parchment p-2 text-sm">
                  <p className="text-xs font-semibold text-ink-muted">{t("astrology.chartBirth")}</p>
                  {a.chart_birth_date && <DateText date={a.chart_birth_date} />}
                  {a.chart_birth_time && (
                    <div>
                      <TimeText time={a.chart_birth_time} />
                    </div>
                  )}
                  {a.chart_birth_place && <p>{a.chart_birth_place}</p>}
                </div>
              )}
              {(a.calculation_system || a.ephemeris_version) && (
                <p className="mt-2 text-xs text-ink-muted">
                  {t("astrology.calcMeta", { system: a.calculation_system ?? "?", eph: a.ephemeris_version ?? "?" })}
                </p>
              )}
              {a.provenance?.origin && a.provenance.origin !== "manual" && <p className="text-xs text-ink-muted">{t("astrology.origin", { origin: a.provenance.origin })}</p>}
              {a.notes && <p className="mt-1 text-xs">{a.notes}</p>}
              {canWrite && (
                <div className="mt-2 flex gap-1">
                  <Button size="sm" variant="ghost" icon={<Edit3 className="size-4" aria-hidden />} onClick={() => setEditing(a)}>
                    {t("common.edit")}
                  </Button>
                  <Button size="sm" variant="ghost" icon={<Trash2 className="size-4" aria-hidden />} onClick={() => setDeleting(a)}>
                    {t("common.delete")}
                  </Button>
                </div>
              )}
            </li>
          ))}
        </ul>
      </section>
      <BirthConflictsPanel personId={person.id} />
      {editing && <AstrologyDialog personId={person.id} profile={editing === "new" ? null : editing} onClose={() => setEditing(null)} />}
      <ConfirmDialog
        open={!!deleting}
        onClose={() => setDeleting(null)}
        title={t("astrology.deleteTitle")}
        confirmLabel={t("common.delete")}
        danger
        loading={del.isPending}
        onConfirm={() => deleting && del.mutate(deleting.id, { onSuccess: () => setDeleting(null) })}
      >
        <ErrorAlert error={del.error} />
      </ConfirmDialog>
    </div>
  );
}

function BirthConflictsPanel({ personId }: { personId: string }) {
  const { t } = useTranslation();
  const { treeId } = useTreeCtx();
  const c = useBirthConflicts(treeId, personId);
  return (
    <section aria-labelledby="bc-title" className="space-y-3">
      <h2 id="bc-title" className="font-display text-lg font-semibold">
        {t("astrology.conflictsTitle")}
      </h2>
      <p className="text-xs text-ink-muted">{t("astrology.conflictsIntro")}</p>
      {c.isLoading && <Spinner />}
      <ErrorAlert error={c.error} />
      {c.data && (
        <>
          {c.data.has_conflicts ? (
            <ul className="space-y-2" aria-label={t("astrology.disagreements")}>
              {c.data.conflicts.map((x, i) => (
                <li key={i} className="flex items-start gap-2 rounded-lg border border-haldi-300 bg-haldi-100 p-3 text-sm text-haldi-700">
                  <AlertTriangle className="mt-0.5 size-4 shrink-0" aria-hidden />
                  <span>
                    <strong>{t(`astrology.conflictField.${x.field}`, { defaultValue: x.field })}:</strong> {x.message}
                    <span className="block text-xs">{x.values.map((v) => v.value).join(" ≠ ")}</span>
                  </span>
                </li>
              ))}
            </ul>
          ) : (
            <p className="rounded-lg bg-leaf-50 p-2 text-sm text-leaf-700">{c.data.claims.length ? t("astrology.noConflicts") : t("astrology.noClaims")}</p>
          )}
          {(c.data.withheld_fields ?? []).length > 0 && <RedactionNotice label={t("astrology.withheld", { fields: c.data.withheld_fields!.join(", ") })} />}
          <div className="relative overflow-x-auto">
            <table className="w-full text-sm">
              <caption className="sr-only">{t("astrology.claims")}</caption>
              <thead className="text-left text-xs uppercase tracking-wide text-ink-muted">
                <tr>
                  <th scope="col" className="py-1 pr-3">
                    {t("astrology.claim")}
                  </th>
                  <th scope="col" className="py-1 pr-3">
                    {t("events.date")}
                  </th>
                  <th scope="col" className="py-1 pr-3">
                    {t("person.birthTime")}
                  </th>
                  <th scope="col" className="py-1 pr-3">
                    {t("events.place")}
                  </th>
                  <th scope="col" className="py-1 pr-3">
                    {t("astrology.sourceProvenance")}
                  </th>
                </tr>
              </thead>
              <tbody className="divide-y divide-stone-100">
                {c.data.claims.map((cl) => (
                  <tr key={cl.id} className="align-top">
                    <td className="py-2 pr-3">
                      {t(`astrology.claimType.${cl.claim_type}`, { defaultValue: cl.claim_type })}
                      {cl.is_preferred && (
                        <span className="ml-1">
                          <Badge tone="saffron">{t("events.preferred")}</Badge>
                        </span>
                      )}
                    </td>
                    <td className="py-2 pr-3">{cl.date ? <DateText date={cl.date} /> : "—"}</td>
                    <td className="py-2 pr-3">{cl.time ? <TimeText time={cl.time} /> : "—"}</td>
                    <td className="py-2 pr-3">{cl.place ?? "—"}</td>
                    <td className="py-2 pr-3">
                      <span className="flex flex-wrap gap-1">
                        <EvidenceBadge status={cl.evidence_status} />
                        <Badge tone="stone">{cl.provenance_kind ? t(`enum.astroProvenance.${cl.provenance_kind}`) : cl.provenance.origin}</Badge>
                      </span>
                      {(cl.sources ?? []).map((s) => (
                        <span key={s.source_id} className="block text-xs text-ink-muted">
                          {s.title} ({t(`enum.sourceType.${s.source_type}`, { defaultValue: s.source_type })})
                        </span>
                      ))}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </>
      )}
    </section>
  );
}

interface Draft {
  provenance_kind: AstrologyProvenance;
  nakshatra: string;
  nakshatra_pada: string;
  rashi: string;
  lagna: string;
  tithi: string;
  paksha: string;
  lunar_month: string;
  ayanamsha: string;
  calculation_system: string;
  ephemeris_version: string;
  chart_birth_date: GenealogicalDate;
  chart_birth_time: GenealogicalTime;
  chart_birth_place: string;
  timezone_id: string;
  privacy_level: PrivacyLevel | "";
  evidence_status: EvidenceStatus;
  is_preferred: boolean;
  notes: string;
}

function toDraft(a: AstrologyOut | null): Draft {
  return {
    provenance_kind: a?.provenance_kind ?? "entered",
    nakshatra: a?.nakshatra ?? "",
    nakshatra_pada: a?.nakshatra_pada ? String(a.nakshatra_pada) : "",
    rashi: a?.rashi ?? "",
    lagna: a?.lagna ?? "",
    tithi: a?.tithi ?? "",
    paksha: a?.paksha ?? "",
    lunar_month: a?.lunar_month ?? "",
    ayanamsha: a?.ayanamsha ?? "",
    calculation_system: a?.calculation_system ?? "",
    ephemeris_version: a?.ephemeris_version ?? "",
    chart_birth_date: (a?.chart_birth_date as GenealogicalDate | null) ?? emptyDate(),
    chart_birth_time: (a?.chart_birth_time as GenealogicalTime | null) ?? { value: null, precision: "unknown", source: "kundli" },
    chart_birth_place: a?.chart_birth_place ?? "",
    timezone_id: a?.timezone_id ?? "Asia/Kolkata",
    privacy_level: a?.privacy_level ?? "",
    evidence_status: a?.evidence_status ?? "USER_ASSERTION",
    is_preferred: a?.is_preferred ?? true,
    notes: a?.notes ?? "",
  };
}

function AstrologyDialog({ personId, profile, onClose }: { personId: string; profile: AstrologyOut | null; onClose: () => void }) {
  const { t } = useTranslation();
  const { treeId } = useTreeCtx();
  const save = useSaveAstrology(treeId, personId);
  const [d, setD] = useState<Draft>(() => toDraft(profile));
  const [submitted, setSubmitted] = useState(false);
  const set = (patch: Partial<Draft>) => setD({ ...d, ...patch });
  const calcMissing = d.provenance_kind === "calculated" && (!d.calculation_system.trim() || !d.ephemeris_version.trim());
  const dateBad = hasDate(d.chart_birth_date) && Object.keys(validateDate(d.chart_birth_date)).length > 0;
  const timeBad = !!d.chart_birth_time.value && !!validateTime(d.chart_birth_time);
  const submit = (e: FormEvent) => {
    e.preventDefault();
    setSubmitted(true);
    if (calcMissing || dateBad || timeBad) return;
    const s = (v: string) => v.trim() || null;
    const body: AstrologyIn = {
      provenance_kind: d.provenance_kind,
      nakshatra: s(d.nakshatra),
      nakshatra_pada: d.nakshatra_pada ? Number(d.nakshatra_pada) : null,
      rashi: s(d.rashi),
      lagna: s(d.lagna),
      tithi: s(d.tithi),
      paksha: s(d.paksha),
      lunar_month: s(d.lunar_month),
      ayanamsha: s(d.ayanamsha),
      calculation_system: s(d.calculation_system),
      ephemeris_version: s(d.ephemeris_version),
      chart_birth_date: hasDate(d.chart_birth_date) ? normalizeDate(d.chart_birth_date) : null,
      chart_birth_time: d.chart_birth_time.value ? { value: d.chart_birth_time.value, precision: d.chart_birth_time.precision, source: d.chart_birth_time.source } : null,
      chart_birth_place: s(d.chart_birth_place),
      timezone_id: d.chart_birth_time.value && d.timezone_id ? d.timezone_id : null,
      privacy_level: d.privacy_level || null,
      evidence_status: d.evidence_status,
      is_preferred: d.is_preferred,
      notes: s(d.notes),
    };
    save.mutate({ id: profile?.id, body }, { onSuccess: onClose });
  };
  const text = (k: keyof Draft, list?: string[]) => (
    <Field label={t(`astrology.f.${k}`)}>
      {(p) => (
        <>
          <TextInput {...p} list={list ? `dl-${k}` : undefined} value={d[k] as string} onChange={(e) => set({ [k]: e.target.value } as Partial<Draft>)} />
          {list && (
            <datalist id={`dl-${k}`}>
              {list.map((x) => (
                <option key={x} value={x} />
              ))}
            </datalist>
          )}
        </>
      )}
    </Field>
  );
  return (
    <Dialog
      open
      onClose={onClose}
      size="lg"
      title={profile ? t("astrology.editTitle") : t("astrology.add")}
      footer={
        <>
          <Button variant="secondary" onClick={onClose}>
            {t("common.cancel")}
          </Button>
          <Button type="submit" form="astro-form" loading={save.isPending}>
            {t("common.save")}
          </Button>
        </>
      }
    >
      <form id="astro-form" onSubmit={submit} className="space-y-3" noValidate>
        <div className="grid grid-cols-1 gap-3 sm:grid-cols-3">
          <Field label={t("astrology.provenance")} hint={t(`astrology.provHint.${d.provenance_kind}`)}>
            {(p) => (
              <Select {...p} value={d.provenance_kind} onChange={(e) => set({ provenance_kind: e.target.value as AstrologyProvenance })}>
                {PROVENANCES.map((x) => (
                  <option key={x} value={x}>
                    {t(`enum.astroProvenance.${x}`)}
                  </option>
                ))}
              </Select>
            )}
          </Field>
          <Field label={t("astrology.f.nakshatra")} hint={t("astrology.vocabHint")}>
            {(p) => (
              <Select {...p} value={d.nakshatra} onChange={(e) => set({ nakshatra: e.target.value })}>
                <option value="">—</option>
                {nakshatras.map((n) => (
                  <option key={n.id} value={n.name}>
                    {n.name} · {n.nameHindi}
                  </option>
                ))}
                {d.nakshatra && !nakshatras.some((n) => n.name === d.nakshatra) && <option value={d.nakshatra}>{d.nakshatra}</option>}
              </Select>
            )}
          </Field>
          <Field label={t("astrology.f.nakshatra_pada")}>
            {(p) => (
              <Select {...p} value={d.nakshatra_pada} onChange={(e) => set({ nakshatra_pada: e.target.value })}>
                <option value="">—</option>
                {[1, 2, 3, 4].map((n) => (
                  <option key={n} value={n}>
                    {n}
                  </option>
                ))}
              </Select>
            )}
          </Field>
          {(["rashi", "lagna"] as const).map((k) => (
            <Field key={k} label={t(`astrology.f.${k}`)}>
              {(p) => (
                <Select {...p} value={d[k]} onChange={(e) => set({ [k]: e.target.value })}>
                  <option value="">—</option>
                  {rashis.map((r) => (
                    <option key={r.id} value={r.name}>
                      {r.name} · {r.nameHindi} ({r.nameEnglish})
                    </option>
                  ))}
                </Select>
              )}
            </Field>
          ))}
          {text("tithi")}
          <Field label={t("astrology.f.paksha")}>
            {(p) => (
              <Select {...p} value={d.paksha} onChange={(e) => set({ paksha: e.target.value })}>
                <option value="">—</option>
                {PAKSHAS.map((x) => (
                  <option key={x} value={x}>
                    {x}
                  </option>
                ))}
              </Select>
            )}
          </Field>
          {text("lunar_month")}
          {text("ayanamsha", AYANAMSHAS)}
          {text("calculation_system")}
          {text("ephemeris_version")}
        </div>
        {submitted && calcMissing && (
          <p role="alert" className="field-error">
            {t("astrology.calcRequired")}
          </p>
        )}
        <GenealogicalDateEditor legend={t("astrology.chartBirthDate")} value={d.chart_birth_date} onChange={(chart_birth_date) => set({ chart_birth_date })} showErrors={submitted && hasDate(d.chart_birth_date)} />
        <div className="grid grid-cols-1 gap-3 lg:grid-cols-3">
          <div className="lg:col-span-2">
            <TimeEditor legend={t("astrology.chartBirthTime")} value={d.chart_birth_time} onChange={(chart_birth_time) => set({ chart_birth_time })} showErrors={submitted} />
          </div>
          <TimezoneSelect value={d.timezone_id} onChange={(timezone_id) => set({ timezone_id })} />
        </div>
        <div className="grid grid-cols-1 gap-3 sm:grid-cols-3">
          {text("chart_birth_place")}
          <Field label={t("names.evidence")}>
            {(p) => (
              <Select {...p} value={d.evidence_status} onChange={(e) => set({ evidence_status: e.target.value as EvidenceStatus })}>
                {EVIDENCE_STATUSES.map((s) => (
                  <option key={s} value={s}>
                    {t(`enum.evidence.${s}`)}
                  </option>
                ))}
              </Select>
            )}
          </Field>
          <Field label={t("privacy.level")} hint={t("astrology.privacyHint")}>
            {(p) => (
              <Select {...p} value={d.privacy_level} onChange={(e) => set({ privacy_level: e.target.value as PrivacyLevel | "" })}>
                <option value="">{t("heritage.inheritPrivacy")}</option>
                {PRIVACY_LEVELS.map((l) => (
                  <option key={l} value={l}>
                    {t(`enum.privacy.${l}`)}
                  </option>
                ))}
              </Select>
            )}
          </Field>
        </div>
        <Checkbox label={t("astrology.preferred")} checked={d.is_preferred} onChange={(is_preferred) => set({ is_preferred })} />
        <Field label={t("heritage.notes")}>{(p) => <TextArea {...p} rows={2} value={d.notes} onChange={(e) => set({ notes: e.target.value })} />}</Field>
        <ErrorAlert error={save.error} />
      </form>
    </Dialog>
  );
}
