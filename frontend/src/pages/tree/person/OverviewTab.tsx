import { ChallengeButton, ReviewBadge } from "../../../components/review/ReviewParts";
import { useState, type FormEvent } from "react";
import { useTranslation } from "react-i18next";
import { Edit3, Plus, Star, Trash2 } from "lucide-react";
import type { NameOut, PersonOut, ProfileStatus, SexAtBirth, VitalSummary } from "../../../api/types";
import { useAddName, useDeleteName, usePersonEvents, useUpdateName, useUpdatePerson } from "../../../api/hooks/people";
import { EventDialog } from "./EventDialog";
import { useTreeCtx } from "../../../lib/tree-context";
import { PersonTraditions } from "../TraditionsPage";
import { nameText } from "../../../lib/names";
import { DateText, TimeText } from "../../../components/dates/DateText";
import { EvidenceBadge, RedactionNotice } from "../../../components/person/badges";
import { NameFields, cleanName, nameHasContent, type NameDraft } from "../../../components/person/NameFields";
import { SEXES, STATUSES } from "../../../components/person/PersonForm";
import { Button } from "../../../components/ui/Button";
import { ConfirmDialog, Dialog } from "../../../components/ui/Dialog";
import { ErrorAlert, Spinner } from "../../../components/ui/feedback";
import { Field, Select, TextArea, TextInput } from "../../../components/ui/form";
import { Badge } from "../../../components/ui/Badge";

function Row({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <div className="grid grid-cols-1 gap-0.5 py-2 sm:grid-cols-[10rem_1fr] sm:gap-3">
      <dt className="text-xs font-semibold uppercase tracking-wide text-ink-muted">{label}</dt>
      <dd className="text-sm">{children}</dd>
    </div>
  );
}

export function VitalRows({
  vital,
  kind,
  redacted,
  onEdit,
}: {
  vital: VitalSummary | null | undefined;
  kind: "birth" | "death";
  redacted: string[];
  /** Present only for editors: opens the event editor for this vital. */
  onEdit?: () => void;
}) {
  const { t } = useTranslation();
  const r = new Set([...(vital?.redacted_fields ?? []), ...(kind === "birth" ? redacted : [])]);
  const place = vital?.place_as_recorded || vital?.place_name;
  return (
    <>
      <Row label={t(`person.${kind}Date`)}>
        <div className="flex flex-wrap items-center justify-between gap-2">
          <span>{vital?.date ? <DateText date={vital.date} /> : <span className="text-ink-muted">{t("person.notRecorded")}</span>}</span>
          {onEdit && (
            <button
              type="button"
              onClick={onEdit}
              className="inline-flex min-h-11 min-w-11 items-center rounded px-3 text-sm font-medium underline hover:bg-parchment-deep"
            >
              {t(vital?.event_id ? `person.vitalEdit.${kind}` : `person.vitalAdd.${kind}`)}
            </button>
          )}
        </div>
        {kind === "birth" && r.has("birth_date_full") && (
          <div>
            <RedactionNotice label={t("privacy.fullDateHidden")} />
          </div>
        )}
      </Row>
      {kind === "birth" && (
        <Row label={t("person.birthTime")}>
          {r.has("birth_time") ? (
            <RedactionNotice />
          ) : vital?.time && (vital.time as { value?: string }).value ? (
            <TimeText time={vital.time} />
          ) : (
            <span className="text-ink-muted">{t("person.notRecorded")}</span>
          )}
        </Row>
      )}
      <Row label={t(`person.${kind}Place`)}>
        {kind === "birth" && r.has("birth_place_detail") ? (
          <RedactionNotice />
        ) : place ? (
          <span>
            {place}
            {vital?.place_name && vital.place_as_recorded && vital.place_name !== vital.place_as_recorded && (
              <span className="ml-1 text-xs text-ink-muted">({t("person.linkedPlace", { place: vital.place_name })})</span>
            )}
          </span>
        ) : (
          <span className="text-ink-muted">{t("person.notRecorded")}</span>
        )}
      </Row>
    </>
  );
}

export function OverviewTab({ person }: { person: PersonOut }) {
  const { t } = useTranslation();
  const redacted = person.redacted_fields ?? [];
  const [editing, setEditing] = useState(false);
  const [vitalAction, setVitalAction] = useState<"birth" | "death" | null>(null);
  const gated = (value: string | null | undefined, group: string) =>
    redacted.includes(group) ? <RedactionNotice /> : value ? <span className="whitespace-pre-wrap">{value}</span> : <span className="text-ink-muted">{t("person.notRecorded")}</span>;

  return (
    <div className="grid gap-5 lg:grid-cols-2">
      <section className="card p-4" aria-labelledby="ov-vitals">
        <div className="flex items-center justify-between">
          <h2 id="ov-vitals" className="font-display text-lg font-semibold">
            {t("person.vitals")}
          </h2>
          {person.can_edit && (
            <Button size="sm" variant="ghost" icon={<Edit3 className="size-4" aria-hidden />} onClick={() => setEditing(true)}>
              {t("person.editDetails")}
            </Button>
          )}
        </div>
        <dl className="divide-y divide-stone-100">
          <VitalRows vital={person.birth} kind="birth" redacted={redacted} onEdit={person.can_edit ? () => setVitalAction("birth") : undefined} />
          {(person.profile_status === "deceased" || person.death) && (
            <VitalRows vital={person.death} kind="death" redacted={redacted} onEdit={person.can_edit ? () => setVitalAction("death") : undefined} />
          )}
          <Row label={t("person.sexAtBirth")}>{person.sex_at_birth ? t(`enum.sex.${person.sex_at_birth}`) : <span className="text-ink-muted">{t("person.notRecorded")}</span>}</Row>
          {(person.gender_identity || redacted.includes("gender_identity")) && <Row label={t("person.genderIdentity")}>{gated(person.gender_identity, "gender_identity")}</Row>}
          <Row label={t("person.occupation")}>{person.occupation || <span className="text-ink-muted">{t("person.notRecorded")}</span>}</Row>
          {(person.contact_info || redacted.includes("contact")) && <Row label={t("person.contact")}>{gated(person.contact_info, "contact")}</Row>}
          {(person.residential_address || redacted.includes("address")) && <Row label={t("person.address")}>{gated(person.residential_address, "address")}</Row>}
          {(person.notes || redacted.includes("notes")) && <Row label={t("person.notes")}>{gated(person.notes, "notes")}</Row>}
        </dl>
      </section>
      <NamesSection person={person} />
      <SurnameTimeline person={person} />
      <div className="lg:col-span-2">
        <PersonTraditions personId={person.id} />
      </div>
      {vitalAction && <VitalEventDialog person={person} kind={vitalAction} onClose={() => setVitalAction(null)} />}
      {editing && <EditDetailsDialog person={person} onClose={() => setEditing(false)} />}
    </div>
  );
}

/** Opens the canonical event editor for a birth/death; the person's events are fetched only once an action is used. */
function VitalEventDialog({ person, kind, onClose }: { person: PersonOut; kind: "birth" | "death"; onClose: () => void }) {
  const { t } = useTranslation();
  const { treeId } = useTreeCtx();
  const eventId = (kind === "birth" ? person.birth : person.death)?.event_id;
  const events = usePersonEvents(treeId, person.id, !!eventId);
  if (!eventId) return <EventDialog personId={person.id} event={null} initialType={kind} onClose={onClose} />;
  const event = events.data?.find((e) => e.id === eventId);
  if (event) return <EventDialog personId={person.id} event={event} onClose={onClose} />;
  // Never render nothing: while loading, on error, or when the saved event is not in the list
  // (removed elsewhere, or hidden from this viewer), show a dialog the user can close.
  const missing = events.isSuccess ? new Error(t("errors.notFound")) : null;
  return (
    <Dialog
      open
      onClose={onClose}
      title={t(`person.vitalEdit.${kind}`)}
      footer={
        <Button variant="secondary" onClick={onClose}>
          {t("common.cancel")}
        </Button>
      }
    >
      {events.error || missing ? <ErrorAlert error={events.error ?? missing} /> : <Spinner />}
    </Dialog>
  );
}

const rangeYear = (r: unknown, key: "from" | "to"): number | null => {
  const d = r && typeof r === "object" ? (r as Record<string, unknown>)[key] : null;
  const y = d && typeof d === "object" ? (d as { year?: number | null }).year : null;
  return typeof y === "number" ? y : null;
};

/**
 * Former surnames over time ("Sharma until 1950, then Upadhyay"), from historical names with the
 * years they were used (ADR-0026 §2). Nothing is inferred: only recorded names and years.
 */
function SurnameTimeline({ person }: { person: PersonOut }) {
  const { t } = useTranslation();
  const former = (person.names ?? [])
    .filter((n) => n.type === "historical" && (n.surname || n.full_name_as_recorded))
    .sort((a, b) => (rangeYear(a.date_range, "from") ?? rangeYear(a.date_range, "to") ?? 0) - (rangeYear(b.date_range, "from") ?? rangeYear(b.date_range, "to") ?? 0));
  if (!former.length) return null;
  const current = (person.names ?? []).find((n) => n.is_preferred);
  return (
    <section className="card p-4" aria-labelledby="ov-surnames">
      <h2 id="ov-surnames" className="font-display text-lg font-semibold">
        {t("names.surnameTimeline")}
      </h2>
      <ol className="mt-2 space-y-2 border-l-2 border-haldi-300 pl-4">
        {former.map((n) => {
          const from = rangeYear(n.date_range, "from");
          const to = rangeYear(n.date_range, "to");
          return (
            <li key={n.id} className="text-sm">
              <span className="font-medium" lang={n.language ?? undefined}>
                {n.surname || n.full_name_as_recorded}
              </span>{" "}
              <span className="text-ink-muted">
                {from && to ? t("names.yearsFromTo", { from, to }) : to ? t("names.yearsUntil", { to }) : from ? t("names.yearsFrom", { from }) : t("names.yearsUnknown")}
              </span>
            </li>
          );
        })}
        {current?.surname && (
          <li className="text-sm">
            <span className="font-medium" lang={current.language ?? undefined}>
              {current.surname}
            </span>{" "}
            <span className="text-ink-muted">{t("names.now")}</span>
          </li>
        )}
      </ol>
    </section>
  );
}

function NamesSection({ person }: { person: PersonOut }) {
  const { t } = useTranslation();
  const { treeId } = useTreeCtx();
  const [editing, setEditing] = useState<NameOut | "new" | null>(null);
  const [deleting, setDeleting] = useState<NameOut | null>(null);
  const del = useDeleteName(treeId, person.id);
  const names = person.names ?? [];
  return (
    <section className="card p-4" aria-labelledby="ov-names">
      <div className="flex items-center justify-between">
        <h2 id="ov-names" className="font-display text-lg font-semibold">
          {t("names.title")}
        </h2>
        {person.can_edit && (
          <Button size="sm" variant="ghost" icon={<Plus className="size-4" aria-hidden />} onClick={() => setEditing("new")}>
            {t("names.add")}
          </Button>
        )}
      </div>
      <ul className="mt-2 divide-y divide-stone-100">
        {names.map((n) => (
          <li key={n.id} className="flex items-start justify-between gap-2 py-2">
            <div className="min-w-0">
              <p className="text-base font-medium" lang={n.language ?? undefined} dir={n.script === "Arab" ? "rtl" : undefined}>
                {nameText(n)}
                {n.is_preferred && <Star className="ml-1 inline size-3.5 fill-haldi-500 text-haldi-500" aria-label={t("names.preferred")} />}
              </p>
              {n.romanized_value && <p className="text-xs text-ink-muted">{n.romanized_value}</p>}
              <div className="mt-1 flex flex-wrap gap-1">
                <Badge tone="stone">{t(`enum.nameType.${n.type}`)}</Badge>
                {n.language && (
                  <Badge tone="stone">
                    {n.language}
                    {n.script ? ` · ${n.script}` : ""}
                  </Badge>
                )}
                <EvidenceBadge status={n.evidence_status} />
                <ReviewBadge state={n.review_state} />
              </div>
              {n.full_name_as_recorded && n.full_name_as_recorded !== nameText(n) && (
                <p className="mt-1 text-xs text-ink-muted" lang={n.language ?? undefined}>
                  {t("names.asRecorded")}: “{n.full_name_as_recorded}”
                </p>
              )}
            </div>
            <div className="flex shrink-0 gap-1">
              <ChallengeButton treeId={treeId} targetType="name" targetId={n.id} label={nameText(n)} />
            </div>
            {person.can_edit && (
              <div className="flex shrink-0 gap-1">
                <button type="button" className="rounded p-1.5 hover:bg-parchment-deep" onClick={() => setEditing(n)} aria-label={t("names.editName", { name: nameText(n) })}>
                  <Edit3 className="size-4" aria-hidden />
                </button>
                {names.length > 1 && (
                  <button type="button" className="rounded p-1.5 text-red-800 hover:bg-red-50" onClick={() => setDeleting(n)} aria-label={t("names.deleteName", { name: nameText(n) })}>
                    <Trash2 className="size-4" aria-hidden />
                  </button>
                )}
              </div>
            )}
          </li>
        ))}
      </ul>
      {editing && <NameDialog personId={person.id} name={editing === "new" ? null : editing} onClose={() => setEditing(null)} />}
      <ConfirmDialog
        open={!!deleting}
        onClose={() => setDeleting(null)}
        title={t("names.deleteTitle")}
        body={deleting ? t("names.deleteBody", { name: nameText(deleting) }) : ""}
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

function toDraft(n: NameOut): NameDraft {
  return {
    type: n.type,
    given_name: n.given_name ?? "",
    middle_names: n.middle_names ?? "",
    patronymic: n.patronymic ?? "",
    matronymic: n.matronymic ?? "",
    surname: n.surname ?? "",
    family_house_name: n.family_house_name ?? "",
    village_prefix: n.village_prefix ?? "",
    honorific_prefix: n.honorific_prefix ?? "",
    honorific_suffix: n.honorific_suffix ?? "",
    full_name_as_recorded: n.full_name_as_recorded ?? "",
    language: n.language,
    script: n.script,
    romanized_value: n.romanized_value ?? "",
    date_range: (n.date_range as NameDraft["date_range"]) ?? null,
    is_preferred: n.is_preferred,
    evidence_status: n.evidence_status,
    confidence: n.confidence,
  };
}

function NameDialog({ personId, name, onClose }: { personId: string; name: NameOut | null; onClose: () => void }) {
  const { t } = useTranslation();
  const { treeId } = useTreeCtx();
  const add = useAddName(treeId, personId);
  const update = useUpdateName(treeId, personId);
  const [draft, setDraft] = useState<NameDraft>(() =>
    name ? toDraft(name) : { type: "transliteration", language: "hi", script: "Deva", given_name: "", surname: "", is_preferred: false, evidence_status: "USER_ASSERTION" },
  );
  const [err, setErr] = useState<string | null>(null);
  // names accepted from a transliteration suggestion (ADR-0025), saved with this one
  const [extra, setExtra] = useState<NameDraft[]>([]);
  const mutation = name ? update : add;
  const saveExtra = async () => {
    for (const n of extra) await add.mutateAsync(cleanName(n));
    onClose();
  };
  const submit = (e: FormEvent) => {
    e.preventDefault();
    if (!nameHasContent(draft)) {
      setErr(t("person.err.nameRequired"));
      return;
    }
    setErr(null);
    if (name) {
      // PATCH: send every editable part so cleared fields become null.
      const body: Record<string, unknown> = {};
      for (const [k, v] of Object.entries(draft)) body[k] = typeof v === "string" ? v.trim() || null : v;
      update.mutate({ id: name.id, body }, { onSuccess: () => void saveExtra() });
    } else add.mutate(cleanName(draft), { onSuccess: () => void saveExtra() });
  };
  return (
    <Dialog
      open
      onClose={onClose}
      title={name ? t("names.editTitle") : t("names.addTitle")}
      size="lg"
      footer={
        <>
          <Button variant="secondary" onClick={onClose}>
            {t("common.cancel")}
          </Button>
          <Button type="submit" form="name-form" loading={mutation.isPending}>
            {t("common.save")}
          </Button>
        </>
      }
    >
      <form id="name-form" onSubmit={submit} noValidate className="space-y-3">
        <NameFields index={0} value={draft} onChange={setDraft} error={err} onAddName={(n) => setExtra((xs) => [...xs, n])} />
        {extra.length > 0 && (
          <p className="text-xs text-ink-muted">
            {t("translit.addedNote")}{" "}
            {extra.map((n) => (
              <span key={`${n.given_name}|${n.surname}`} lang={n.language ?? undefined} className="mr-2 font-medium text-ink">
                {[n.given_name, n.surname].filter(Boolean).join(" ")}
              </span>
            ))}
          </p>
        )}
        <ErrorAlert error={mutation.error} />
      </form>
    </Dialog>
  );
}

function EditDetailsDialog({ person, onClose }: { person: PersonOut; onClose: () => void }) {
  const { t } = useTranslation();
  const { treeId } = useTreeCtx();
  const update = useUpdatePerson(treeId, person.id);
  const redacted = person.redacted_fields ?? [];
  const [d, setD] = useState({
    profile_status: person.profile_status,
    sex_at_birth: (person.sex_at_birth ?? "") as SexAtBirth | "",
    occupation: person.occupation ?? "",
    gender_identity: person.gender_identity ?? "",
    contact_info: person.contact_info ?? "",
    residential_address: person.residential_address ?? "",
    notes: person.notes ?? "",
  });
  const submit = (e: FormEvent) => {
    e.preventDefault();
    const body: Record<string, unknown> = {
      profile_status: d.profile_status,
      occupation: d.occupation.trim() || null,
    };
    if (d.sex_at_birth) body.sex_at_birth = d.sex_at_birth;
    // Never overwrite a field the viewer can't see (it arrived redacted as null).
    if (!redacted.includes("gender_identity")) body.gender_identity = d.gender_identity.trim() || null;
    if (!redacted.includes("contact")) body.contact_info = d.contact_info.trim() || null;
    if (!redacted.includes("address")) body.residential_address = d.residential_address.trim() || null;
    if (!redacted.includes("notes")) body.notes = d.notes.trim() || null;
    update.mutate(body, { onSuccess: onClose });
  };
  return (
    <Dialog
      open
      onClose={onClose}
      title={t("person.editDetails")}
      footer={
        <>
          <Button variant="secondary" onClick={onClose}>
            {t("common.cancel")}
          </Button>
          <Button type="submit" form="details-form" loading={update.isPending}>
            {t("common.save")}
          </Button>
        </>
      }
    >
      <form id="details-form" onSubmit={submit} className="grid grid-cols-1 gap-3 sm:grid-cols-2" noValidate>
        <Field label={t("person.status")}>
          {(p) => (
            <Select {...p} value={d.profile_status} onChange={(e) => setD({ ...d, profile_status: e.target.value as ProfileStatus })}>
              {STATUSES.map((s) => (
                <option key={s} value={s}>
                  {t(`enum.profileStatus.${s}`)}
                </option>
              ))}
            </Select>
          )}
        </Field>
        <Field label={t("person.sexAtBirth")}>
          {(p) => (
            <Select {...p} value={d.sex_at_birth} onChange={(e) => setD({ ...d, sex_at_birth: e.target.value as SexAtBirth | "" })}>
              <option value="">{t("person.notRecorded")}</option>
              {SEXES.map((s) => (
                <option key={s} value={s}>
                  {t(`enum.sex.${s}`)}
                </option>
              ))}
            </Select>
          )}
        </Field>
        <Field label={t("person.occupation")}>{(p) => <TextInput {...p} value={d.occupation} onChange={(e) => setD({ ...d, occupation: e.target.value })} />}</Field>
        {!redacted.includes("gender_identity") && (
          <Field label={t("person.genderIdentity")} hint={t("person.genderIdentityHint")}>
            {(p) => <TextInput {...p} value={d.gender_identity} onChange={(e) => setD({ ...d, gender_identity: e.target.value })} />}
          </Field>
        )}
        {!redacted.includes("contact") && (
          <Field label={t("person.contact")} className="sm:col-span-2">
            {(p) => <TextArea {...p} rows={2} value={d.contact_info} onChange={(e) => setD({ ...d, contact_info: e.target.value })} />}
          </Field>
        )}
        {!redacted.includes("address") && (
          <Field label={t("person.address")} className="sm:col-span-2">
            {(p) => <TextArea {...p} rows={2} value={d.residential_address} onChange={(e) => setD({ ...d, residential_address: e.target.value })} />}
          </Field>
        )}
        {!redacted.includes("notes") && (
          <Field label={t("person.notes")} className="sm:col-span-2">
            {(p) => <TextArea {...p} value={d.notes} onChange={(e) => setD({ ...d, notes: e.target.value })} />}
          </Field>
        )}
        <div className="sm:col-span-2">
          <ErrorAlert error={update.error} />
        </div>
      </form>
    </Dialog>
  );
}
