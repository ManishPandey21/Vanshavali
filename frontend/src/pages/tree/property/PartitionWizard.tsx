import { useMemo, useState } from "react";
import { useTranslation } from "react-i18next";
import { AlertTriangle, Plus, Trash2, Upload } from "lucide-react";
import type { GenealogicalDate, InterestOut, PartitionIn, PropertyDetailOut } from "../../../api/types";
import { useDocuments } from "../../../api/hooks/documents";
import { useInterests, useRecordPartition } from "../../../api/hooks/property";
import { useTreeCtx } from "../../../lib/tree-context";
import { emptyDate, normalizeDate, validateDate } from "../../../lib/dates";
import { fromShare, parseShare } from "../../../lib/fractions";
import { checkPartition, describeTotals } from "../../../lib/partition";
import { PROPERTY_DOCUMENT_CATEGORIES } from "../../../lib/documents";
import { GenealogicalDateEditor } from "../../../components/dates/GenealogicalDateEditor";
import { HolderPicker, ShareInput, emptyHolder, holderPayload, holderValid, type HolderDraft } from "../../../components/property/ShareInput";
import { UploadDocumentDialog } from "../../../components/documents/UploadDocumentDialog";
import { hasDate } from "../../../components/person/PersonForm";
import { Button } from "../../../components/ui/Button";
import { Dialog } from "../../../components/ui/Dialog";
import { ErrorAlert } from "../../../components/ui/feedback";
import { Checkbox, Field, Select, TextArea, TextInput } from "../../../components/ui/form";
import { InterestLine, LegalNotice } from "./common";

interface Allocation {
  holder: HolderDraft;
  share: string;
}

const STEPS = ["details", "ending", "allocations", "documents"] as const;
type Step = (typeof STEPS)[number];

export function buildPartitionBody(args: {
  date: GenealogicalDate;
  description: string;
  registration: string;
  scope: string;
  ends: string[];
  allocations: Allocation[];
  documentIds: string[];
  allowPartial: boolean;
}): PartitionIn {
  return {
    date: normalizeDate(args.date),
    description: args.description.trim() || null,
    registration_number: args.registration.trim() || null,
    parcel_ids: args.scope ? [args.scope] : null,
    ends_interest_ids: args.ends,
    allocations: args.allocations.map((a) => {
      const s = parseShare(a.share);
      return {
        ...holderPayload(a.holder),
        parcel_id: args.scope || null,
        share_numerator: s.ok ? s.numerator : 0,
        share_denominator: s.ok ? s.denominator : 1,
      };
    }),
    document_ids: args.documentIds,
    allow_partial: args.allowPartial,
  };
}

/** Records a partition: ends the chosen ownership interests and creates the allocated ones atomically. */
export function PartitionWizard({ property, onClose }: { property: PropertyDetailOut; onClose: () => void }) {
  const { t } = useTranslation();
  const { treeId } = useTreeCtx();
  const interests = useInterests(treeId, property.id);
  const docs = useDocuments(treeId, { target_type: "property", target_id: property.id });
  const record = useRecordPartition(treeId, property.id);
  const [step, setStep] = useState<Step>("details");
  const [date, setDate] = useState<GenealogicalDate>(emptyDate());
  const [description, setDescription] = useState("");
  const [registration, setRegistration] = useState("");
  const [scope, setScope] = useState("");
  const [ends, setEnds] = useState<string[] | null>(null);
  const [allocations, setAllocations] = useState<Allocation[]>([{ holder: emptyHolder(), share: "" }]);
  const [allowPartial, setAllowPartial] = useState(false);
  const [documentIds, setDocumentIds] = useState<string[]>([]);
  const [uploading, setUploading] = useState(false);

  const eligible: InterestOut[] = useMemo(
    () => (interests.data ?? []).filter((i) => i.is_current && (i.interest_type === "owner" || i.interest_type === "co_owner") && (i.parcel_id == null || i.parcel_id === scope)),
    [interests.data, scope],
  );
  const selectedEnds = ends ?? eligible.map((i) => i.id);
  const endedShares = eligible.filter((i) => selectedEnds.includes(i.id)).map((i) => fromShare(i.share_numerator, i.share_denominator));
  const dateOk = hasDate(date) && Object.keys(validateDate(date)).length === 0 && date.precision !== "unknown";
  const check = checkPartition(
    endedShares,
    allocations.map((a) => ({ holderOk: holderValid(a.holder), share: a.share })),
    allowPartial,
    dateOk,
  );
  const totals = describeTotals(check);
  const idx = STEPS.indexOf(step);
  const canNext = step === "details" ? dateOk : step === "allocations" ? check.errors.length === 0 : true;

  const submit = () => {
    record.mutate(buildPartitionBody({ date, description, registration, scope, ends: selectedEnds, allocations, documentIds, allowPartial }), { onSuccess: onClose });
  };

  return (
    <Dialog
      open
      onClose={onClose}
      size="lg"
      title={t("partition.title", { name: property.display_name })}
      footer={
        <>
          <Button variant="secondary" onClick={idx === 0 ? onClose : () => setStep(STEPS[idx - 1])}>
            {idx === 0 ? t("common.cancel") : t("partition.back")}
          </Button>
          {idx < STEPS.length - 1 ? (
            <Button disabled={!canNext} onClick={() => setStep(STEPS[idx + 1])}>
              {t("partition.next")}
            </Button>
          ) : (
            <Button loading={record.isPending} disabled={check.errors.length > 0} onClick={submit}>
              {t("partition.record")}
            </Button>
          )}
        </>
      }
    >
      <div className="space-y-4">
        <LegalNotice text={property.legal_notice} />
        <ol className="flex flex-wrap gap-2 text-xs" aria-label={t("partition.steps")}>
          {STEPS.map((s, i) => (
            <li key={s} aria-current={s === step ? "step" : undefined} className={`rounded-full px-2.5 py-1 ${s === step ? "bg-kumkum-700 text-white" : i < idx ? "bg-leaf-50 text-leaf-700" : "bg-stone-100 text-ink-muted"}`}>
              {i + 1}. {t(`partition.step.${s}`)}
            </li>
          ))}
        </ol>

        {step === "details" && (
          <div className="space-y-3">
            <GenealogicalDateEditor legend={t("partition.date")} value={date} onChange={setDate} showErrors={hasDate(date)} />
            {!dateOk && <p className="hint">{t("partition.dateHint")}</p>}
            <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
              <Field label={t("partition.scope")} hint={t("partition.scopeHint")}>
                {(p) => (
                  <Select
                    {...p}
                    value={scope}
                    onChange={(e) => {
                      setScope(e.target.value);
                      setEnds(null);
                    }}
                  >
                    <option value="">{t("property.wholeProperty")}</option>
                    {(property.parcels ?? []).map((x) => (
                      <option key={x.id} value={x.id}>
                        {x.label}
                      </option>
                    ))}
                  </Select>
                )}
              </Field>
              <Field label={t("partition.registration")}>{(p) => <TextInput {...p} value={registration} onChange={(e) => setRegistration(e.target.value)} />}</Field>
            </div>
            <Field label={t("property.description")}>{(p) => <TextArea {...p} rows={2} value={description} onChange={(e) => setDescription(e.target.value)} />}</Field>
          </div>
        )}

        {step === "ending" && (
          <fieldset className="space-y-2">
            <legend className="label">{t("partition.endingLegend")}</legend>
            {eligible.length === 0 && <p className="text-sm text-ink-muted">{t("partition.noneEligible")}</p>}
            {eligible.map((i) => (
              <label key={i.id} className="flex items-start gap-2 rounded-lg border border-stone-200 p-2">
                <input
                  type="checkbox"
                  className="mt-1 accent-kumkum-700"
                  checked={selectedEnds.includes(i.id)}
                  onChange={(e) => setEnds(e.target.checked ? [...selectedEnds, i.id] : selectedEnds.filter((x) => x !== i.id))}
                />
                <InterestLine i={i} />
              </label>
            ))}
            <p className="text-sm">
              {t("partition.endedTotal")}: <strong className="font-mono">{totals.ended}</strong>
            </p>
          </fieldset>
        )}

        {step === "allocations" && (
          <div className="space-y-3">
            <p className="text-sm text-ink-muted">{t("partition.allocIntro", { ended: totals.ended })}</p>
            {allocations.map((a, i) => (
              <div key={i} className="space-y-2 rounded-lg border border-stone-300 p-3" role="group" aria-label={t("partition.allocationN", { n: i + 1 })}>
                <div className="flex items-center justify-between">
                  <p className="text-sm font-semibold">{t("partition.allocationN", { n: i + 1 })}</p>
                  <Button size="sm" variant="ghost" disabled={allocations.length <= 1} onClick={() => setAllocations(allocations.filter((_, j) => j !== i))} aria-label={t("partition.removeAllocation", { n: i + 1 })}>
                    <Trash2 className="size-4" aria-hidden />
                  </Button>
                </div>
                <HolderPicker value={a.holder} onChange={(holder) => setAllocations(allocations.map((x, j) => (j === i ? { ...x, holder } : x)))} legend={t("property.holder")} />
                <ShareInput label={t("property.share")} value={a.share} onChange={(share) => setAllocations(allocations.map((x, j) => (j === i ? { ...x, share } : x)))} />
              </div>
            ))}
            <Button size="sm" variant="secondary" icon={<Plus className="size-3.5" aria-hidden />} onClick={() => setAllocations([...allocations, { holder: emptyHolder(), share: "" }])}>
              {t("partition.addAllocation")}
            </Button>
            <p className={`rounded-lg p-2 text-sm ${check.balanced ? "bg-leaf-50 text-leaf-700" : "bg-parchment-deep"}`} aria-live="polite">
              {t("partition.totals", totals)}
            </p>
            <Checkbox label={t("partition.allowPartial")} hint={t("partition.allowPartialHint")} checked={allowPartial} onChange={setAllowPartial} />
            {check.warning && (
              <p role="status" className="flex items-start gap-2 rounded-lg bg-haldi-100 p-2 text-sm text-haldi-700">
                <AlertTriangle className="mt-0.5 size-4" aria-hidden /> {t(check.warning, totals)}
              </p>
            )}
            {check.errors.length > 0 && (
              <ul className="list-inside list-disc text-sm text-red-800" aria-live="polite">
                {check.errors.map((e) => (
                  <li key={e}>{t(e, totals)}</li>
                ))}
              </ul>
            )}
          </div>
        )}

        {step === "documents" && (
          <fieldset className="space-y-2">
            <legend className="label">{t("partition.documentsLegend")}</legend>
            {(docs.data?.items ?? []).length === 0 && <p className="text-sm text-ink-muted">{t("partition.noDocuments")}</p>}
            {(docs.data?.items ?? []).map((d) => (
              <label key={d.id} className="flex items-center gap-2 text-sm">
                <input type="checkbox" className="accent-kumkum-700" checked={documentIds.includes(d.id)} onChange={(e) => setDocumentIds(e.target.checked ? [...documentIds, d.id] : documentIds.filter((x) => x !== d.id))} />
                {d.title} <span className="text-xs text-ink-muted">({t(`enum.docCategory.${d.category}`)})</span>
              </label>
            ))}
            <Button size="sm" variant="secondary" icon={<Upload className="size-4" aria-hidden />} onClick={() => setUploading(true)}>
              {t("partition.uploadDeed")}
            </Button>
            <div className="rounded-lg bg-parchment p-3 text-sm">
              <p className="font-semibold">{t("partition.summary")}</p>
              <p>{t("partition.summaryBody", { count: allocations.length, allocated: totals.allocated, ended: totals.ended, docs: documentIds.length })}</p>
            </div>
            <ErrorAlert error={record.error} />
          </fieldset>
        )}
      </div>
      {uploading && (
        <UploadDocumentDialog
          initialCategory="partition_deed"
          categories={PROPERTY_DOCUMENT_CATEGORIES}
          linkTarget={{ type: "property", id: property.id, label: property.display_name }}
          onClose={() => setUploading(false)}
          onUploaded={(d) => setDocumentIds((ids) => [...ids, d.id])}
        />
      )}
    </Dialog>
  );
}
