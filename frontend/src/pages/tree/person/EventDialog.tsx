import { useState, type FormEvent } from "react";
import { useTranslation } from "react-i18next";
import type {
  EventIn,
  EventOut,
  EventSignificance,
  EventType,
  EvidenceStatus,
  GenealogicalDate,
  GenealogicalTime,
  LifeEventCategory,
  LocationPrecision,
  PersonSummary,
  PrivacyLevel,
} from "../../../api/types";
import { CATEGORY_GROUPS, CATEGORY_TYPE } from "../../../lib/lifeEvents";
import { parseCoordinate } from "../../../lib/geo";
import { PRECISIONS } from "../../../components/geo/GeoFields";
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
  utc_offset_minutes: string;
  place: PlaceValue;
  origin: PlaceValue;
  reason: string;
  description: string;
  evidence_status: EvidenceStatus;
  is_preferred: boolean;
  spouse: PersonSummary | null;
  category: LifeEventCategory | "";
  title: string;
  significance: EventSignificance;
  privacy_level: PrivacyLevel | "";
  latitude: string;
  longitude: string;
  location_precision: LocationPrecision;
}

const SIGNIFICANCE: EventSignificance[] = ["standard", "important", "milestone"];
const EVENT_PRIVACY: (PrivacyLevel | "")[] = ["", "TREE_MEMBERS", "FAMILY_BRANCH", "PRIVATE_TREE_ADMINS"];

function fromEvent(e: EventOut): Draft {
  return {
    type: e.type,
    subtype: e.subtype ?? "",
    date: (e.date as GenealogicalDate | null) ?? emptyDate(),
    time: (e.time as GenealogicalTime | null) ?? { value: null, precision: "unknown", source: "unknown" },
    timezone_id: e.timezone_id ?? "",
    utc_offset_minutes: e.utc_offset_minutes == null ? "" : String(e.utc_offset_minutes),
    place: { place_id: e.place_id ?? null, place_label: e.place_name ?? null, place_as_recorded: e.place_as_recorded ?? "" },
    origin: { place_id: e.origin_place_id ?? null, place_label: e.origin_place_name ?? null, place_as_recorded: e.origin_place_as_recorded ?? "" },
    reason: e.reason ?? "",
    description: e.description ?? "",
    evidence_status: e.evidence_status,
    is_preferred: e.is_preferred,
    spouse: null,
    category: e.category ?? "",
    title: e.title ?? "",
    significance: e.significance ?? "standard",
    privacy_level: e.privacy_level ?? "",
    latitude: e.latitude != null ? String(e.latitude) : "",
    longitude: e.longitude != null ? String(e.longitude) : "",
    location_precision: e.location_precision ?? "approximate",
  };
}

function emptyDraft(type: EventType): Draft {
  return {
    type,
    subtype: "",
    date: emptyDate(),
    time: { value: null, precision: "unknown", source: "unknown" },
    timezone_id: "",
    utc_offset_minutes: "",
    place: emptyPlace(),
    origin: emptyPlace(),
    reason: "",
    description: "",
    evidence_status: "USER_ASSERTION",
    is_preferred: true,
    spouse: null,
    category: "",
    title: "",
    significance: "standard",
    privacy_level: "",
    latitude: "",
    longitude: "",
    location_precision: "approximate",
  };
}

/** Add or edit a life event. Migration events carry an origin and destination place. */
export function EventDialog({
  personId,
  event,
  onClose,
  initialType = "residence",
  initialCategory,
  birthField,
}: {
  personId: string;
  event: EventOut | null;
  onClose: () => void;
  initialType?: EventType;
  initialCategory?: LifeEventCategory;
  birthField?: "date" | "time" | "place";
}) {
  const { t } = useTranslation();
  const { treeId } = useTreeCtx();
  const create = useCreateEvent(treeId);
  const update = useUpdateEvent(treeId);
  const [d, setD] = useState<Draft>(() => {
    if (event) return fromEvent(event);
    const draft = emptyDraft(initialCategory ? CATEGORY_TYPE[initialCategory] : initialType);
    return initialCategory ? { ...draft, category: initialCategory, significance: "important" } : draft;
  });
  const [submitted, setSubmitted] = useState(false);
  const redacted = new Set(event?.redacted_fields ?? []);
  const dateLocked = redacted.has("birth_date_full") || redacted.has("event_date_full") || (!!birthField && birthField !== "date");
  const timeLocked = redacted.has("birth_time") || (!!birthField && birthField !== "time");
  const placeLocked = redacted.has("birth_place_detail") || redacted.has("address") || (!!birthField && birthField !== "place");
  const withTime = d.type === "birth";
  const set = (patch: Partial<Draft>) => setD({ ...d, ...patch });
  const dateErrs = !dateLocked && hasDate(d.date) ? validateDate(d.date) : {};
  const timeErr = withTime && !timeLocked && (d.time.value || d.time.precision !== "unknown") ? validateTime(d.time) : null;
  const mutation = event ? update : create;
  const lat = parseCoordinate(d.latitude, "lat");
  const lng = parseCoordinate(d.longitude, "lng");
  const coordErr = placeLocked ? null : lat === "invalid" || lng === "invalid" ? "geo.latError" : (lat === null) !== (lng === null) ? "geo.pairError" : null;
  const offset = d.utc_offset_minutes.trim() === "" ? null : Number(d.utc_offset_minutes);
  const offsetError = !timeLocked && offset !== null && (!Number.isInteger(offset) || Math.abs(offset) > 840);

  const submit = (e: FormEvent) => {
    e.preventDefault();
    setSubmitted(true);
    if (Object.keys(dateErrs).length || timeErr || coordErr || offsetError) return;
    const common: Record<string, unknown> = birthField ? {} : {
      category: d.category || null,
      title: d.title.trim() || null,
      significance: d.significance,
      privacy_level: d.privacy_level || null,
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
      common.utc_offset_minutes = d.time.value ? offset : null;
    }
    if (!placeLocked) {
      common.place_id = d.place.place_id;
      common.place_as_recorded = d.place.place_as_recorded.trim() || null;
      common.latitude = typeof lat === "number" ? lat : null;
      common.longitude = typeof lng === "number" ? lng : null;
      common.location_precision = typeof lat === "number" ? d.location_precision : null;
    }
    if (d.type === "migration") {
      common.origin_place_id = d.origin.place_id;
      common.origin_place_as_recorded = d.origin.place_as_recorded.trim() || null;
    }
    if (event) {
      common.expected_revision = event.revision;
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
      title={birthField ? t(`person.birthEdit.${birthField}`) : event ? t("events.editTitle", { type: event.title || t(`enum.eventType.${event.type}`) }) : t("events.addTitle")}
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
        {!birthField && <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
          <Field label={t("lifeEvents.category")} hint={t("lifeEvents.categoryHint")}>
            {(p) => (
              <Select
                {...p}
                value={d.category}
                onChange={(e) => {
                  const category = e.target.value as LifeEventCategory | "";
                  set(category && !event ? { category, type: CATEGORY_TYPE[category] } : { category });
                }}
              >
                <option value="">{t("lifeEvents.noCategory")}</option>
                {CATEGORY_GROUPS.map((g) => (
                  <optgroup key={g.id} label={t(`lifeEvents.group.${g.id}`)}>
                    {g.categories.map((c) => (
                      <option key={c} value={c}>
                        {t(`enum.lifeEventCategory.${c}`)}
                      </option>
                    ))}
                  </optgroup>
                ))}
              </Select>
            )}
          </Field>
          <Field label={t("lifeEvents.title")} hint={t("lifeEvents.titleHint")}>
            {(p) => <TextInput {...p} value={d.title} maxLength={300} onChange={(e) => set({ title: e.target.value })} />}
          </Field>
          <Field label={t("events.type")}>
            {(p) => (
              <Select {...p} value={d.type} disabled={!!event || !!d.category} onChange={(e) => set({ type: e.target.value as EventType })}>
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
        </div>}
        {redacted.size > 0 && <RedactionNoticeBlock text={t("events.someHidden")} />}
        {!dateLocked && <GenealogicalDateEditor legend={t("events.date")} value={d.date} onChange={(date) => set({ date })} showErrors={submitted && hasDate(d.date)} />}
        {withTime && !timeLocked && (
          <div className="grid grid-cols-1 gap-3 lg:grid-cols-3">
            <div className="lg:col-span-2">
              <TimeEditor legend={t("person.form.birthTime")} value={d.time} onChange={(time) => set({ time })} showErrors={submitted} />
            </div>
            <TimezoneSelect value={d.timezone_id} onChange={(timezone_id) => set({ timezone_id })} />
            <Field label={t("time.utcOffset")} hint={t("time.utcOffsetHint")} error={submitted && offsetError ? t("time.utcOffsetError") : null}>
              {(p) => <TextInput {...p} inputMode="numeric" value={d.utc_offset_minutes} onChange={(e) => set({ utc_offset_minutes: e.target.value })} />}
            </Field>
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
        {!placeLocked && (
          <details className="rounded-lg border border-stone-200 p-3" open={!!d.latitude || !!coordErr}>
            <summary className="cursor-pointer text-sm font-semibold">{t("lifeEvents.coordinates")}</summary>
            <p className="mt-1 text-xs text-ink-muted">{t("lifeEvents.coordinatesHint")}</p>
            <div className="mt-2 grid grid-cols-1 gap-3 sm:grid-cols-3">
              <Field label={t("geo.latitude")} error={submitted && coordErr ? t(coordErr) : null}>
                {(p) => <TextInput {...p} inputMode="decimal" value={d.latitude} onChange={(e) => set({ latitude: e.target.value })} />}
              </Field>
              <Field label={t("geo.longitude")}>{(p) => <TextInput {...p} inputMode="decimal" value={d.longitude} onChange={(e) => set({ longitude: e.target.value })} />}</Field>
              <Field label={t("geo.precision")}>
                {(p) => (
                  <Select {...p} value={d.location_precision} onChange={(e) => set({ location_precision: e.target.value as LocationPrecision })}>
                    {PRECISIONS.map((x) => (
                      <option key={x} value={x}>
                        {t(`enum.locationPrecision.${x}`)}
                      </option>
                    ))}
                  </Select>
                )}
              </Field>
            </div>
          </details>
        )}
        {!birthField && <>
        <Field label={t("events.description")}>{(p) => <TextArea {...p} rows={2} value={d.description} onChange={(e) => set({ description: e.target.value })} />}</Field>
        <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
          <Field label={t("lifeEvents.significance")}>
            {(p) => (
              <Select {...p} value={d.significance} onChange={(e) => set({ significance: e.target.value as EventSignificance })}>
                {SIGNIFICANCE.map((x) => (
                  <option key={x} value={x}>
                    {t(`enum.significance.${x}`)}
                  </option>
                ))}
              </Select>
            )}
          </Field>
          <Field label={t("lifeEvents.visibility")} hint={t("lifeEvents.visibilityHint")}>
            {(p) => (
              <Select {...p} value={d.privacy_level} onChange={(e) => set({ privacy_level: e.target.value as PrivacyLevel | "" })}>
                {EVENT_PRIVACY.map((lv) => (
                  <option key={lv} value={lv}>
                    {lv ? t(`enum.privacy.${lv}`) : t("lifeEvents.inheritVisibility")}
                  </option>
                ))}
              </Select>
            )}
          </Field>
        </div>
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
        </>}
        <ErrorAlert error={mutation.error} />
      </form>
    </Dialog>
  );
}
