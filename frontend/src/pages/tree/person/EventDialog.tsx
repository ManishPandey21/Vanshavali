import { useState, type FormEvent } from "react";
import { useTranslation } from "react-i18next";
import type { EventIn, EventOut, EventType, EvidenceStatus, GenealogicalDate, GenealogicalTime, PersonSummary } from "../../../api/types";
import { useCreateEvent, useUpdateEvent } from "../../../api/hooks/people";
import { useTreeCtx } from "../../../lib/tree-context";
import { emptyDate, normalizeDate, validateDate, validateTime } from "../../../lib/dates";
import { GenealogicalDateEditor } from "../../../components/dates/GenealogicalDateEditor";
import { TimeEditor, TimezoneSelect } from "../../../components/dates/TimeEditor";
import { PersonPicker, PlacePicker, emptyPlace, type PlaceValue } from "../../../components/pickers";
import { EVIDENCE_STATUSES } from "../../../components/person/NameFields";
import { hasDate } from "../../../components/person/PersonForm";
import { Button } from "../../../components/ui/Button";
import { Dialog } from "../../../components/ui/Dialog";
import { ErrorAlert, RedactionNoticeBlock } from "./shared";
import { Checkbox, Field, Select, TextArea, TextInput } from "../../../components/ui/form";

export const EVENT_TYPES: EventType[] = [
  "birth",
  "death",
  "marriage",
  "divorce",
  "adoption",
  "residence",
  "migration",
  "education",
  "occupation",
  "religious_ceremony",
  "cremation",
  "burial",
  "memorial",
  "other",
];

interface Draft {
  type: EventType;
  subtype: string;
  date: GenealogicalDate;
  time: GenealogicalTime;
  timezone_id: string;
  place: PlaceValue;
  origin: PlaceValue;
  reason: string;
  description: string;
  evidence_status: EvidenceStatus;
  is_preferred: boolean;
  spouse: PersonSummary | null;
}

function fromEvent(e: EventOut): Draft {
  return {
    type: e.type,
    subtype: e.subtype ?? "",
    date: (e.date as GenealogicalDate | null) ?? emptyDate(),
    time: (e.time as GenealogicalTime | null) ?? { value: null, precision: "unknown", source: "unknown" },
    timezone_id: e.timezone_id ?? "",
    place: { place_id: e.place_id ?? null, place_label: e.place_name ?? null, place_as_recorded: e.place_as_recorded ?? "" },
    origin: { place_id: e.origin_place_id ?? null, place_label: e.origin_place_name ?? null, place_as_recorded: e.origin_place_as_recorded ?? "" },
    reason: e.reason ?? "",
    description: e.description ?? "",
    evidence_status: e.evidence_status,
    is_preferred: e.is_preferred,
    spouse: null,
  };
}

function emptyDraft(type: EventType): Draft {
  return {
    type,
    subtype: "",
    date: emptyDate(),
    time: { value: null, precision: "unknown", source: "unknown" },
    timezone_id: type === "birth" ? "Asia/Kolkata" : "",
    place: emptyPlace(),
    origin: emptyPlace(),
    reason: "",
    description: "",
    evidence_status: "USER_ASSERTION",
    is_preferred: true,
    spouse: null,
  };
}

/** Add or edit a life event. Migration events carry an origin and destination place. */
export function EventDialog({ personId, event, onClose, initialType = "residence" }: { personId: string; event: EventOut | null; onClose: () => void; initialType?: EventType }) {
  const { t } = useTranslation();
  const { treeId } = useTreeCtx();
  const create = useCreateEvent(treeId);
  const update = useUpdateEvent(treeId);
  const [d, setD] = useState<Draft>(() => (event ? fromEvent(event) : emptyDraft(initialType)));
  const [submitted, setSubmitted] = useState(false);
  const redacted = new Set(event?.redacted_fields ?? []);
  const dateLocked = redacted.has("birth_date_full") || redacted.has("event_date_full");
  const timeLocked = redacted.has("birth_time");
  const placeLocked = redacted.has("birth_place_detail") || redacted.has("address");
  const withTime = d.type === "birth";
  const set = (patch: Partial<Draft>) => setD({ ...d, ...patch });
  const dateErrs = hasDate(d.date) ? validateDate(d.date) : {};
  const timeErr = withTime && (d.time.value || d.time.precision !== "unknown") ? validateTime(d.time) : null;
  const mutation = event ? update : create;

  const submit = (e: FormEvent) => {
    e.preventDefault();
    setSubmitted(true);
    if (Object.keys(dateErrs).length || timeErr) return;
    const common: Record<string, unknown> = {
      subtype: d.subtype.trim() || null,
      reason: d.reason.trim() || null,
      description: d.description.trim() || null,
      evidence_status: d.evidence_status,
      is_preferred: d.is_preferred,
    };
    if (!dateLocked) common.date = hasDate(d.date) ? normalizeDate(d.date) : null;
    if (withTime && !timeLocked) {
      common.time = d.time.value ? { value: d.time.value, precision: d.time.precision, source: d.time.source } : null;
      common.timezone_id = d.time.value && d.timezone_id ? d.timezone_id : null;
    }
    if (!placeLocked) {
      common.place_id = d.place.place_id;
      common.place_as_recorded = d.place.place_as_recorded.trim() || null;
    }
    if (d.type === "migration") {
      common.origin_place_id = d.origin.place_id;
      common.origin_place_as_recorded = d.origin.place_as_recorded.trim() || null;
    }
    if (event) {
      update.mutate({ id: event.id, body: common }, { onSuccess: onClose });
    } else {
      const participants: EventIn["participants"] = [{ person_id: personId, role: "principal" }];
      if ((d.type === "marriage" || d.type === "divorce") && d.spouse) participants.push({ person_id: d.spouse.id, role: "spouse" });
      const body = { ...common, type: d.type, participants } as EventIn;
      for (const k of Object.keys(body) as (keyof EventIn)[]) if (body[k] === null) delete body[k];
      create.mutate(body, { onSuccess: onClose });
    }
  };

  return (
    <Dialog
      open
      onClose={onClose}
      size="lg"
      title={event ? t("events.editTitle", { type: t(`enum.eventType.${event.type}`) }) : t("events.addTitle")}
      footer={
        <>
          <Button variant="secondary" onClick={onClose}>
            {t("common.cancel")}
          </Button>
          <Button type="submit" form="event-form" loading={mutation.isPending}>
            {t("common.save")}
          </Button>
        </>
      }
    >
      <form id="event-form" onSubmit={submit} noValidate className="space-y-4">
        <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
          <Field label={t("events.type")}>
            {(p) => (
              <Select {...p} value={d.type} disabled={!!event} onChange={(e) => set({ type: e.target.value as EventType })}>
                {EVENT_TYPES.map((et) => (
                  <option key={et} value={et}>
                    {t(`enum.eventType.${et}`)}
                  </option>
                ))}
              </Select>
            )}
          </Field>
          <Field label={t("events.subtype")} hint={t("events.subtypeHint")}>
            {(p) => <TextInput {...p} value={d.subtype} onChange={(e) => set({ subtype: e.target.value })} />}
          </Field>
        </div>
        {(dateLocked || timeLocked || placeLocked) && <RedactionNoticeBlock text={t("events.someHidden")} />}
        {!dateLocked && <GenealogicalDateEditor legend={t("events.date")} value={d.date} onChange={(date) => set({ date })} showErrors={submitted && hasDate(d.date)} />}
        {withTime && !timeLocked && (
          <div className="grid grid-cols-1 gap-3 lg:grid-cols-3">
            <div className="lg:col-span-2">
              <TimeEditor legend={t("person.form.birthTime")} value={d.time} onChange={(time) => set({ time })} showErrors={submitted} />
            </div>
            <TimezoneSelect value={d.timezone_id} onChange={(timezone_id) => set({ timezone_id })} />
          </div>
        )}
        {d.type === "migration" && <PlacePicker treeId={treeId} label={t("events.origin")} value={d.origin} onChange={(origin) => set({ origin })} />}
        {!placeLocked && (
          <PlacePicker treeId={treeId} label={d.type === "migration" ? t("events.destination") : t("events.place")} value={d.place} onChange={(place) => set({ place })} />
        )}
        {!event && (d.type === "marriage" || d.type === "divorce") && (
          <PersonPicker treeId={treeId} label={t("events.spouseParticipant")} value={d.spouse} onChange={(spouse) => set({ spouse })} excludeIds={[personId]} />
        )}
        {(d.type === "migration" || d.type === "residence") && (
          <Field label={t("events.reason")}>{(p) => <TextArea {...p} rows={2} value={d.reason} onChange={(e) => set({ reason: e.target.value })} />}</Field>
        )}
        <Field label={t("events.description")}>{(p) => <TextArea {...p} rows={2} value={d.description} onChange={(e) => set({ description: e.target.value })} />}</Field>
        <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
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
          <div className="pt-6">
            <Checkbox label={t("events.preferred")} hint={t("events.preferredHint")} checked={d.is_preferred} onChange={(is_preferred) => set({ is_preferred })} />
          </div>
        </div>
        <ErrorAlert error={mutation.error} />
      </form>
    </Dialog>
  );
}
