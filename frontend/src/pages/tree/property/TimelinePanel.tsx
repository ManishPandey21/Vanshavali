import { useId, useState, type FormEvent } from "react";
import { Link } from "react-router-dom";
import { useTranslation } from "react-i18next";
import { ArrowRight, FileText, GitBranch, Plus, Scissors } from "lucide-react";
import type { GenealogicalDate, PropertyDetailOut, PropertyEventOut, PropertyEventType } from "../../../api/types";
import { useDocuments } from "../../../api/hooks/documents";
import { useInterests, usePropertyLineage, useRecordPropertyEvent, useTimeline } from "../../../api/hooks/property";
import { useTreeCtx } from "../../../lib/tree-context";
import { emptyDate, normalizeDate, validateDate } from "../../../lib/dates";
import { parseShare } from "../../../lib/fractions";
import { GenealogicalDateEditor } from "../../../components/dates/GenealogicalDateEditor";
import { HolderPicker, ShareInput, emptyHolder, holderPayload, holderValid, type HolderDraft } from "../../../components/property/ShareInput";
import { hasDate } from "../../../components/person/PersonForm";
import { Button } from "../../../components/ui/Button";
import { Dialog } from "../../../components/ui/Dialog";
import { EmptyState, ErrorAlert, Spinner } from "../../../components/ui/feedback";
import { Field, Select, TextArea, TextInput } from "../../../components/ui/form";
import { Badge } from "../../../components/ui/Badge";
import { EVENT_TYPES, HolderName, InterestLine } from "./common";
import { PartitionWizard } from "./PartitionWizard";

export function TimelinePanel({ property, canWrite }: { property: PropertyDetailOut; canWrite: boolean }) {
  const { t } = useTranslation();
  const { treeId } = useTreeCtx();
  const atId = useId();
  const [at, setAt] = useState("");
  const timeline = useTimeline(treeId, property.id, at);
  const [recording, setRecording] = useState(false);
  const [partition, setPartition] = useState(false);
  const tl = timeline.data;
  return (
    <section aria-labelledby="tl-title" className="space-y-4">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <h2 id="tl-title" className="font-display text-lg font-semibold">
          {t("property.timeline")}
        </h2>
        {canWrite && (
          <div className="flex flex-wrap gap-2">
            <Button size="sm" icon={<Scissors className="size-4" aria-hidden />} onClick={() => setPartition(true)}>
              {t("partition.open")}
            </Button>
            <Button size="sm" variant="secondary" icon={<Plus className="size-4" aria-hidden />} onClick={() => setRecording(true)}>
              {t("property.recordEvent")}
            </Button>
          </div>
        )}
      </div>
      <div className="card flex flex-col gap-3 p-3 sm:flex-row sm:items-end">
        <div>
          <label htmlFor={atId} className="label">
            {t("property.holdersAt")}
          </label>
          <input id={atId} type="date" className="input" value={at} onChange={(e) => setAt(e.target.value)} />
        </div>
        {at && (
          <Button size="sm" variant="ghost" onClick={() => setAt("")}>
            {t("property.clearDate")}
          </Button>
        )}
        <p className="text-xs text-ink-muted">{t("property.holdersAtHint")}</p>
      </div>
      {timeline.isLoading && <Spinner />}
      <ErrorAlert error={timeline.error} />
      {tl?.holders_at && (
        <div className="card p-3" aria-live="polite">
          <h3 className="text-sm font-semibold">{t("property.holdersOn", { date: tl.holders_at.at })}</h3>
          <p className="text-xs text-ink-muted">
            {t("property.documentedTotal")}: <span className="font-mono">{tl.holders_at.documented_share_total}</span>
            {tl.holders_at.has_overlapping_claims && <span className="ml-2 text-red-800">{t("property.overlapping")}</span>}
          </p>
          {(tl.holders_at.interests ?? []).length === 0 ? (
            <p className="text-sm text-ink-muted">{t("property.noHoldersAt")}</p>
          ) : (
            <ul className="divide-y divide-stone-100">
              {(tl.holders_at.interests ?? []).map((i) => (
                <li key={i.id} className="py-1.5">
                  <InterestLine i={i} />
                </li>
              ))}
            </ul>
          )}
        </div>
      )}
      {tl && (tl.events ?? []).length === 0 && <EmptyState title={t("property.noEvents")}>{t("property.noEventsHint")}</EmptyState>}
      <ol className="relative space-y-3 border-l-2 border-haldi-300 pl-5">
        {(tl?.events ?? []).map((ev) => (
          <EventCard key={ev.id} ev={ev} />
        ))}
      </ol>
      {tl && ((tl.documents ?? []).length > 0 || (tl.hidden_document_count ?? 0) > 0) && (
        <div className="card p-3">
          <h3 className="text-sm font-semibold">{t("property.propertyDocuments")}</h3>
          <ul className="text-sm">
            {(tl.documents ?? []).map((d) => (
              <li key={d.id}>
                <Link className="text-kumkum-800 underline" to={`/t/${treeId}/documents/${d.id}`}>
                  {d.title}
                </Link>{" "}
                <span className="text-xs text-ink-muted">({t(`enum.docCategory.${d.category}`)})</span>
              </li>
            ))}
          </ul>
          {(tl.hidden_document_count ?? 0) > 0 && <p className="text-xs text-ink-muted">{t("property.hiddenDocs", { count: tl.hidden_document_count })}</p>}
        </div>
      )}
      {recording && <RecordEventDialog property={property} onClose={() => setRecording(false)} />}
      {partition && <PartitionWizard property={property} onClose={() => setPartition(false)} />}
    </section>
  );
}

function EventCard({ ev }: { ev: PropertyEventOut }) {
  const { t } = useTranslation();
  const { treeId } = useTreeCtx();
  return (
    <li className="relative">
      <span className="absolute -left-[27px] top-4 size-3 rounded-full border-2 border-white bg-kumkum-700" aria-hidden />
      <article className="card p-3" aria-label={t(`enum.propertyEventType.${ev.type}`)}>
        <div className="flex flex-wrap items-start justify-between gap-2">
          <div>
            <h3 className="font-semibold">{t(`enum.propertyEventType.${ev.type}`)}</h3>
            <p className="text-sm text-ink-muted">
              {ev.date_display ?? t("date.display.unknown")}
              {ev.registration_number && ` · ${t("property.regNo", { n: ev.registration_number })}`}
              {ev.mutation_number && ` · ${t("property.mutationNo", { n: ev.mutation_number })}`}
            </p>
          </div>
          <Badge tone="neutral">{t(`enum.evidence.${ev.evidence_status}`)}</Badge>
        </div>
        {ev.description && <p className="mt-1 text-sm">{ev.description}</p>}
        {(ev.parcels ?? []).length > 0 && <p className="mt-1 text-xs text-ink-muted">{t("property.parcels")}: {(ev.parcels ?? []).map((p) => p.label).join(", ")}</p>}
        {((ev.interests_ended ?? []).length > 0 || (ev.interests_created ?? []).length > 0) && (
          <div className="mt-2 grid gap-2 text-sm sm:grid-cols-[1fr_auto_1fr]">
            <div>
              <p className="text-xs font-semibold uppercase text-ink-muted">{t("property.ended")}</p>
              <ul>
                {(ev.interests_ended ?? []).map((i) => (
                  <li key={i.id} className="flex flex-wrap gap-1">
                    <HolderName holder={i.holder} /> <span className="font-mono">{i.share}</span>
                  </li>
                ))}
              </ul>
            </div>
            <ArrowRight className="hidden size-4 self-center sm:block" aria-hidden />
            <div>
              <p className="text-xs font-semibold uppercase text-ink-muted">{t("property.created")}</p>
              <ul>
                {(ev.interests_created ?? []).map((i) => (
                  <li key={i.id} className="flex flex-wrap gap-1">
                    <HolderName holder={i.holder} /> <span className="font-mono">{i.share}</span>
                  </li>
                ))}
              </ul>
            </div>
          </div>
        )}
        {(ev.documents ?? []).length > 0 && (
          <ul className="mt-2 space-y-0.5 text-sm">
            {(ev.documents ?? []).map((d) => (
              <li key={d.id} className="flex items-center gap-1">
                <FileText className="size-3.5 text-haldi-700" aria-hidden />
                <Link className="text-kumkum-800 underline" to={`/t/${treeId}/documents/${d.id}`}>
                  {d.title}
                </Link>
                <span className="text-xs text-ink-muted">({t(`enum.docCategory.${d.category}`)})</span>
              </li>
            ))}
          </ul>
        )}
        {(ev.hidden_document_count ?? 0) > 0 && <p className="text-xs text-ink-muted">{t("property.hiddenDocs", { count: ev.hidden_document_count })}</p>}
      </article>
    </li>
  );
}

interface NewInterest {
  holder: HolderDraft;
  share: string;
}

function RecordEventDialog({ property, onClose }: { property: PropertyDetailOut; onClose: () => void }) {
  const { t } = useTranslation();
  const { treeId } = useTreeCtx();
  const record = useRecordPropertyEvent(treeId, property.id);
  const interests = useInterests(treeId, property.id);
  const docs = useDocuments(treeId, { target_type: "property", target_id: property.id });
  const [type, setType] = useState<PropertyEventType>("inheritance");
  const [date, setDate] = useState<GenealogicalDate>(emptyDate());
  const [description, setDescription] = useState("");
  const [reg, setReg] = useState("");
  const [mutation, setMutation] = useState("");
  const [ends, setEnds] = useState<string[]>([]);
  const [endStatus, setEndStatus] = useState<"transferred" | "relinquished">("transferred");
  const [creates, setCreates] = useState<NewInterest[]>([]);
  const [parcelIds, setParcelIds] = useState<string[]>([]);
  const [docIds, setDocIds] = useState<string[]>([]);
  const [submitted, setSubmitted] = useState(false);
  const current = (interests.data ?? []).filter((i) => i.is_current);
  const createsValid = creates.every((c) => holderValid(c.holder) && parseShare(c.share).ok);
  const dateBad = hasDate(date) && Object.keys(validateDate(date)).length > 0;
  const submit = (e: FormEvent) => {
    e.preventDefault();
    setSubmitted(true);
    if (!createsValid || dateBad) return;
    record.mutate(
      {
        type,
        date: hasDate(date) ? normalizeDate(date) : null,
        description: description.trim() || null,
        registration_number: reg.trim() || null,
        mutation_number: mutation.trim() || null,
        parcel_ids: parcelIds,
        ends_interest_ids: ends,
        end_status: ends.length ? endStatus : null,
        creates_interests: creates.map((c) => {
          const s = parseShare(c.share);
          return { ...holderPayload(c.holder), share_numerator: s.ok ? s.numerator : 1, share_denominator: s.ok ? s.denominator : 1 };
        }),
        document_ids: docIds,
      },
      { onSuccess: onClose },
    );
  };
  const toggle = (list: string[], set: (l: string[]) => void, id: string, on: boolean) => set(on ? [...list, id] : list.filter((x) => x !== id));
  return (
    <Dialog
      open
      onClose={onClose}
      size="lg"
      title={t("property.recordEvent")}
      footer={
        <>
          <Button variant="secondary" onClick={onClose}>
            {t("common.cancel")}
          </Button>
          <Button type="submit" form="pevent-form" loading={record.isPending}>
            {t("common.save")}
          </Button>
        </>
      }
    >
      <form id="pevent-form" onSubmit={submit} className="space-y-3" noValidate>
        <div className="grid grid-cols-1 gap-3 sm:grid-cols-3">
          <Field label={t("property.eventType")}>
            {(p) => (
              <Select {...p} value={type} onChange={(e) => setType(e.target.value as PropertyEventType)}>
                {EVENT_TYPES.filter((x) => x !== "partition" && x !== "subdivision").map((x) => (
                  <option key={x} value={x}>
                    {t(`enum.propertyEventType.${x}`)}
                  </option>
                ))}
              </Select>
            )}
          </Field>
          <Field label={t("partition.registration")}>{(p) => <TextInput {...p} value={reg} onChange={(e) => setReg(e.target.value)} />}</Field>
          <Field label={t("property.mutationNumber")}>{(p) => <TextInput {...p} value={mutation} onChange={(e) => setMutation(e.target.value)} />}</Field>
        </div>
        <GenealogicalDateEditor legend={t("property.eventDate")} value={date} onChange={setDate} showErrors={submitted && hasDate(date)} />
        <Field label={t("property.description")}>{(p) => <TextArea {...p} rows={2} value={description} onChange={(e) => setDescription(e.target.value)} />}</Field>
        {(property.parcels ?? []).length > 0 && (
          <fieldset>
            <legend className="label">{t("property.parcelsAffected")}</legend>
            <div className="flex flex-wrap gap-3">
              {(property.parcels ?? []).map((p) => (
                <label key={p.id} className="inline-flex items-center gap-2 text-sm">
                  <input type="checkbox" className="accent-kumkum-700" checked={parcelIds.includes(p.id)} onChange={(e) => toggle(parcelIds, setParcelIds, p.id, e.target.checked)} />
                  {p.label}
                </label>
              ))}
            </div>
          </fieldset>
        )}
        {current.length > 0 && (
          <fieldset className="space-y-1">
            <legend className="label">{t("property.endsInterests")}</legend>
            {current.map((i) => (
              <label key={i.id} className="flex items-start gap-2">
                <input type="checkbox" className="mt-1 accent-kumkum-700" checked={ends.includes(i.id)} onChange={(e) => toggle(ends, setEnds, i.id, e.target.checked)} />
                <InterestLine i={i} />
              </label>
            ))}
            {ends.length > 0 && (
              <Field label={t("property.status")}>
                {(p) => (
                  <Select {...p} value={endStatus} onChange={(e) => setEndStatus(e.target.value as "transferred" | "relinquished")}>
                    <option value="transferred">{t("enum.interestStatus.transferred")}</option>
                    <option value="relinquished">{t("enum.interestStatus.relinquished")}</option>
                  </Select>
                )}
              </Field>
            )}
          </fieldset>
        )}
        <fieldset className="space-y-2">
          <legend className="label">{t("property.createsInterests")}</legend>
          {creates.map((c, i) => (
            <div key={i} className="space-y-2 rounded-lg border border-stone-300 p-2">
              <HolderPicker value={c.holder} onChange={(holder) => setCreates(creates.map((x, j) => (j === i ? { ...x, holder } : x)))} legend={t("property.holder")} />
              <ShareInput label={t("property.share")} value={c.share} onChange={(share) => setCreates(creates.map((x, j) => (j === i ? { ...x, share } : x)))} showErrors={submitted} />
              <Button size="sm" variant="ghost" onClick={() => setCreates(creates.filter((_, j) => j !== i))}>
                {t("common.delete")}
              </Button>
            </div>
          ))}
          <Button size="sm" variant="secondary" icon={<Plus className="size-3.5" aria-hidden />} onClick={() => setCreates([...creates, { holder: emptyHolder(), share: "1" }])}>
            {t("property.addCreatedInterest")}
          </Button>
        </fieldset>
        {(docs.data?.items ?? []).length > 0 && (
          <fieldset>
            <legend className="label">{t("partition.documentsLegend")}</legend>
            {(docs.data?.items ?? []).map((d) => (
              <label key={d.id} className="flex items-center gap-2 text-sm">
                <input type="checkbox" className="accent-kumkum-700" checked={docIds.includes(d.id)} onChange={(e) => toggle(docIds, setDocIds, d.id, e.target.checked)} />
                {d.title}
              </label>
            ))}
          </fieldset>
        )}
        <ErrorAlert error={record.error} />
      </form>
    </Dialog>
  );
}

/** First acquirers → partitions/transfers → current holders. */
export function LineagePanel({ property }: { property: PropertyDetailOut }) {
  const { t } = useTranslation();
  const { treeId } = useTreeCtx();
  const q = usePropertyLineage(treeId, property.id);
  if (q.isLoading) return <Spinner />;
  if (!q.data) return <ErrorAlert error={q.error} />;
  const l = q.data;
  return (
    <section aria-labelledby="lin-title" className="space-y-4">
      <h2 id="lin-title" className="flex items-center gap-2 font-display text-lg font-semibold">
        <GitBranch className="size-5 text-haldi-700" aria-hidden /> {t("property.lineage")}
      </h2>
      <div className="card p-3">
        <h3 className="text-xs font-semibold uppercase text-ink-muted">{t("property.firstAcquirers")}</h3>
        {(l.first_acquirers ?? []).length === 0 ? (
          <p className="text-sm text-ink-muted">{t("property.noneRecorded")}</p>
        ) : (
          <ul className="flex flex-wrap gap-3 text-sm">
            {(l.first_acquirers ?? []).map((h, i) => (
              <li key={i}>
                <HolderName holder={h} />
              </li>
            ))}
          </ul>
        )}
        {(l.first_acquisition_events ?? []).map((e) => (
          <p key={e.id} className="text-xs text-ink-muted">
            {t(`enum.propertyEventType.${e.type}`)} · {e.date_display ?? "?"}
          </p>
        ))}
      </div>
      {(l.chains ?? []).length > 0 && (
        <div className="space-y-3">
          <h3 className="text-xs font-semibold uppercase text-ink-muted">{t("property.chainsToCurrent")}</h3>
          {(l.chains ?? []).map((c) => (
            <article key={c.interest.id} className="card p-3">
              <ol className="flex flex-wrap items-center gap-2 text-sm">
                {(c.first_acquirers ?? []).map((h, i) => (
                  <li key={`fa-${i}`} className="rounded-full bg-parchment-deep px-2 py-0.5">
                    <HolderName holder={h} />
                  </li>
                ))}
                {[...(c.steps ?? [])].reverse().map((s) => (
                  <li key={s.id} className="flex items-center gap-1 text-xs text-ink-muted">
                    <ArrowRight className="size-3.5" aria-hidden />
                    {t(`enum.propertyEventType.${s.type}`)} ({s.date_display ?? "?"})
                  </li>
                ))}
                <li className="flex items-center gap-1">
                  <ArrowRight className="size-3.5" aria-hidden />
                  <InterestLine i={c.interest} />
                </li>
              </ol>
            </article>
          ))}
        </div>
      )}
      {(l.transfers_out ?? []).length > 0 && (
        <div className="card p-3">
          <h3 className="text-xs font-semibold uppercase text-ink-muted">{t("property.transfersOut")}</h3>
          <ul className="text-sm">
            {(l.transfers_out ?? []).map((tr) => (
              <li key={tr.event.id} className="flex flex-wrap items-center gap-1">
                {t(`enum.propertyEventType.${tr.event.type}`)}:{" "}
                {(tr.from_holders ?? []).map((h, i) => (
                  <HolderName key={i} holder={h} />
                ))}
                <ArrowRight className="size-3.5" aria-hidden />
                {(tr.to_holders ?? []).map((h, i) => (
                  <HolderName key={i} holder={h} />
                ))}
              </li>
            ))}
          </ul>
        </div>
      )}
      {(l.parcel_groups ?? []).length > 0 && (
        <div className="card p-3">
          <h3 className="text-xs font-semibold uppercase text-ink-muted">{t("property.parcelGroups")}</h3>
          <ul className="text-sm">
            {(l.parcel_groups ?? []).map((g) => (
              <li key={g.parent.id}>
                {g.parent.label} → {(g.children ?? []).map((c) => c.label).join(", ")}
              </li>
            ))}
          </ul>
        </div>
      )}
    </section>
  );
}
