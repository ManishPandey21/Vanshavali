import { useState, type FormEvent } from "react";
import { useTranslation } from "react-i18next";
import { AlertTriangle, Plus, Trash2 } from "lucide-react";
import type { EvidenceStatus, GenealogicalDate, InterestOut, InterestStatus, InterestType, PropertyDetailOut } from "../../../api/types";
import { useCreateInterest, useDeleteInterest, useEndInterest, useInterests } from "../../../api/hooks/property";
import { useTreeCtx } from "../../../lib/tree-context";
import { emptyDate, normalizeDate, validateDate } from "../../../lib/dates";
import { parseShare } from "../../../lib/fractions";
import { GenealogicalDateEditor } from "../../../components/dates/GenealogicalDateEditor";
import { HolderPicker, ShareInput, emptyHolder, holderPayload, holderValid, type HolderDraft } from "../../../components/property/ShareInput";
import { EVIDENCE_STATUSES } from "../../../components/person/NameFields";
import { hasDate } from "../../../components/person/PersonForm";
import { Button } from "../../../components/ui/Button";
import { ConfirmDialog, Dialog } from "../../../components/ui/Dialog";
import { EmptyState, ErrorAlert, Spinner } from "../../../components/ui/feedback";
import { Field, Select, TextArea } from "../../../components/ui/form";
import { INTEREST_STATUSES, INTEREST_TYPES, InterestLine } from "./common";

export function InterestsPanel({ property, canWrite }: { property: PropertyDetailOut; canWrite: boolean }) {
  const { t } = useTranslation();
  const { treeId } = useTreeCtx();
  const interests = useInterests(treeId, property.id);
  const del = useDeleteInterest(treeId, property.id);
  const [adding, setAdding] = useState(false);
  const [ending, setEnding] = useState<InterestOut | null>(null);
  const [deleting, setDeleting] = useState<InterestOut | null>(null);
  const all = interests.data ?? [];
  const current = all.filter((i) => i.is_current);
  const past = all.filter((i) => !i.is_current);
  const parcelLabel = (id: string | null | undefined) => (id ? (property.parcels ?? []).find((p) => p.id === id)?.label ?? "" : t("property.wholeProperty"));
  const row = (i: InterestOut) => (
    <li key={i.id} className="flex flex-col gap-1 py-2 sm:flex-row sm:items-center sm:justify-between">
      <div>
        <InterestLine i={i} />
        <p className="text-xs text-ink-muted">{parcelLabel(i.parcel_id)}</p>
      </div>
      {canWrite && (
        <div className="flex gap-1">
          {i.is_current && (
            <Button size="sm" variant="ghost" onClick={() => setEnding(i)}>
              {t("property.endInterest")}
            </Button>
          )}
          <Button size="sm" variant="ghost" icon={<Trash2 className="size-4" aria-hidden />} onClick={() => setDeleting(i)} aria-label={t("property.deleteInterest")} />
        </div>
      )}
    </li>
  );
  return (
    <section aria-labelledby="int-title" className="space-y-3">
      <div className="flex items-center justify-between">
        <h2 id="int-title" className="font-display text-lg font-semibold">
          {t("property.interests")}
        </h2>
        {canWrite && (
          <Button size="sm" icon={<Plus className="size-4" aria-hidden />} onClick={() => setAdding(true)}>
            {t("property.addInterest")}
          </Button>
        )}
      </div>
      <p className="text-sm">
        {t("property.documentedTotal")}: <strong className="font-mono">{property.documented_share_total}</strong>
      </p>
      {property.has_overlapping_claims && (
        <p role="status" className="flex items-center gap-2 rounded-lg bg-red-50 p-2 text-sm text-red-900">
          <AlertTriangle className="size-4" aria-hidden /> {t("property.overlapping")}
        </p>
      )}
      {interests.isLoading && <Spinner />}
      <ErrorAlert error={interests.error || del.error} />
      {interests.data && all.length === 0 && <EmptyState title={t("property.noInterests")} />}
      {current.length > 0 && (
        <div className="card p-3">
          <h3 className="text-xs font-semibold uppercase text-ink-muted">{t("property.currentHolders")}</h3>
          <ul className="divide-y divide-stone-100">{current.map(row)}</ul>
        </div>
      )}
      {past.length > 0 && (
        <details className="card p-3">
          <summary className="cursor-pointer text-xs font-semibold uppercase text-ink-muted">{t("property.pastHolders", { count: past.length })}</summary>
          <ul className="divide-y divide-stone-100">{past.map(row)}</ul>
        </details>
      )}
      {adding && <InterestDialog property={property} onClose={() => setAdding(false)} />}
      {ending && <EndInterestDialog propertyId={property.id} interest={ending} onClose={() => setEnding(null)} />}
      <ConfirmDialog
        open={!!deleting}
        onClose={() => setDeleting(null)}
        title={t("property.deleteInterestTitle")}
        body={t("property.deleteInterestBody")}
        confirmLabel={t("common.delete")}
        danger
        loading={del.isPending}
        onConfirm={() => deleting && del.mutate(deleting.id, { onSuccess: () => setDeleting(null) })}
      />
    </section>
  );
}

function InterestDialog({ property, onClose }: { property: PropertyDetailOut; onClose: () => void }) {
  const { t } = useTranslation();
  const { treeId } = useTreeCtx();
  const create = useCreateInterest(treeId, property.id);
  const [holder, setHolder] = useState<HolderDraft>(emptyHolder());
  const [share, setShare] = useState("1");
  const [type, setType] = useState<InterestType>("owner");
  const [status, setStatus] = useState<InterestStatus>("asserted");
  const [evidence, setEvidence] = useState<EvidenceStatus>("USER_ASSERTION");
  const [parcel, setParcel] = useState("");
  const [from, setFrom] = useState<GenealogicalDate>(emptyDate());
  const [notes, setNotes] = useState("");
  const [submitted, setSubmitted] = useState(false);
  const submit = (e: FormEvent) => {
    e.preventDefault();
    setSubmitted(true);
    const s = parseShare(share);
    if (!s.ok || !holderValid(holder) || (hasDate(from) && Object.keys(validateDate(from)).length)) return;
    create.mutate(
      {
        ...holderPayload(holder),
        share_numerator: s.numerator,
        share_denominator: s.denominator,
        interest_type: type,
        status,
        evidence_status: evidence,
        parcel_id: parcel || null,
        valid_from: hasDate(from) ? normalizeDate(from) : null,
        notes: notes.trim() || null,
      },
      { onSuccess: onClose },
    );
  };
  return (
    <Dialog
      open
      onClose={onClose}
      size="lg"
      title={t("property.addInterest")}
      footer={
        <>
          <Button variant="secondary" onClick={onClose}>
            {t("common.cancel")}
          </Button>
          <Button type="submit" form="interest-form" loading={create.isPending}>
            {t("common.save")}
          </Button>
        </>
      }
    >
      <form id="interest-form" onSubmit={submit} className="space-y-3" noValidate>
        <HolderPicker value={holder} onChange={setHolder} legend={t("property.holder")} />
        {submitted && !holderValid(holder) && <p className="field-error">{t("property.holderRequired")}</p>}
        <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
          <ShareInput label={t("property.share")} value={share} onChange={setShare} showErrors={submitted} />
          <Field label={t("property.interestType")}>
            {(p) => (
              <Select {...p} value={type} onChange={(e) => setType(e.target.value as InterestType)}>
                {INTEREST_TYPES.map((x) => (
                  <option key={x} value={x}>
                    {t(`enum.interestType.${x}`)}
                  </option>
                ))}
              </Select>
            )}
          </Field>
          <Field label={t("property.status")} hint={t("property.statusHint")}>
            {(p) => (
              <Select {...p} value={status} onChange={(e) => setStatus(e.target.value as InterestStatus)}>
                {INTEREST_STATUSES.map((x) => (
                  <option key={x} value={x}>
                    {t(`enum.interestStatus.${x}`)}
                  </option>
                ))}
              </Select>
            )}
          </Field>
          <Field label={t("names.evidence")}>
            {(p) => (
              <Select {...p} value={evidence} onChange={(e) => setEvidence(e.target.value as EvidenceStatus)}>
                {EVIDENCE_STATUSES.map((x) => (
                  <option key={x} value={x}>
                    {t(`enum.evidence.${x}`)}
                  </option>
                ))}
              </Select>
            )}
          </Field>
          <Field label={t("property.parcelScope")}>
            {(p) => (
              <Select {...p} value={parcel} onChange={(e) => setParcel(e.target.value)}>
                <option value="">{t("property.wholeProperty")}</option>
                {(property.parcels ?? []).map((x) => (
                  <option key={x.id} value={x.id}>
                    {x.label}
                  </option>
                ))}
              </Select>
            )}
          </Field>
        </div>
        <GenealogicalDateEditor legend={t("property.heldFrom")} value={from} onChange={setFrom} showErrors={submitted && hasDate(from)} />
        <Field label={t("heritage.notes")}>{(p) => <TextArea {...p} rows={2} value={notes} onChange={(e) => setNotes(e.target.value)} />}</Field>
        <ErrorAlert error={create.error} />
      </form>
    </Dialog>
  );
}

function EndInterestDialog({ propertyId, interest, onClose }: { propertyId: string; interest: InterestOut; onClose: () => void }) {
  const { t } = useTranslation();
  const { treeId } = useTreeCtx();
  const end = useEndInterest(treeId, propertyId);
  const [date, setDate] = useState<GenealogicalDate>({ calendar: "gregorian", precision: "year_only", year: new Date().getFullYear() });
  const [status, setStatus] = useState<"transferred" | "relinquished">("transferred");
  const [notes, setNotes] = useState("");
  return (
    <Dialog
      open
      onClose={onClose}
      title={t("property.endInterest")}
      footer={
        <>
          <Button variant="secondary" onClick={onClose}>
            {t("common.cancel")}
          </Button>
          <Button
            loading={end.isPending}
            onClick={() => {
              if (Object.keys(validateDate(date)).length) return;
              end.mutate({ id: interest.id, body: { valid_to: normalizeDate(date), status, notes: notes.trim() || null } }, { onSuccess: onClose });
            }}
          >
            {t("property.endInterest")}
          </Button>
        </>
      }
    >
      <div className="space-y-3">
        <InterestLine i={interest} />
        <GenealogicalDateEditor legend={t("property.heldUntil")} value={date} onChange={setDate} showErrors />
        <Field label={t("property.status")}>
          {(p) => (
            <Select {...p} value={status} onChange={(e) => setStatus(e.target.value as "transferred" | "relinquished")}>
              <option value="transferred">{t("enum.interestStatus.transferred")}</option>
              <option value="relinquished">{t("enum.interestStatus.relinquished")}</option>
            </Select>
          )}
        </Field>
        <Field label={t("heritage.notes")}>{(p) => <TextArea {...p} rows={2} value={notes} onChange={(e) => setNotes(e.target.value)} />}</Field>
        <ErrorAlert error={end.error} />
      </div>
    </Dialog>
  );
}
