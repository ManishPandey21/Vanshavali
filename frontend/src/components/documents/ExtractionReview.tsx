import { useState } from "react";
import { useTranslation } from "react-i18next";
import { Check, Edit3, Info, X } from "lucide-react";
import type { GenealogicalDate, GenealogicalTime, PersonSummary, ProposalOut, ReviewIn } from "../../api/types";
import { ApiError } from "../../api/client";
import { useProposals, useReviewProposal } from "../../api/hooks/documents";
import { useTreeCtx } from "../../lib/tree-context";
import { emptyDate, normalizeDate, validateDate, validateTime } from "../../lib/dates";
import { fieldKind, valueLabel, type FieldKind, type ValueLabel } from "../../lib/documents";
import { GenealogicalDateEditor } from "../dates/GenealogicalDateEditor";
import { TimeEditor } from "../dates/TimeEditor";
import { PersonPicker } from "../pickers";
import { SEXES } from "../person/PersonForm";
import { Button } from "../ui/Button";
import { EmptyState, ErrorAlert, Spinner } from "../ui/feedback";
import { Field, Select, TextInput } from "../ui/form";
import { Badge, type Tone } from "../ui/Badge";

export interface EditDraft {
  text: string;
  date: GenealogicalDate;
  time: GenealogicalTime;
  number: string;
  unit: string;
}

export function draftFromProposal(p: Pick<ProposalOut, "field" | "proposed_value" | "display_value">): EditDraft {
  const kind = fieldKind(p.field);
  const v = p.proposed_value as unknown;
  const obj = v && typeof v === "object" ? (v as Record<string, unknown>) : null;
  return {
    text: typeof v === "string" ? v : p.display_value ?? "",
    date: kind === "date" && obj ? ({ calendar: "gregorian", precision: "exact", ...obj } as GenealogicalDate) : emptyDate(),
    time: kind === "time" && obj ? ({ precision: "unknown", source: "unknown", ...obj } as GenealogicalTime) : { value: null, precision: "unknown", source: "unknown" },
    number: kind === "pada" ? String(v ?? "") : kind === "area" && obj ? String(obj.value ?? "") : "",
    unit: kind === "area" && obj ? String(obj.unit ?? "") : "",
  };
}

/** Error key when the edited value is invalid client-side, else null. */
export function validateDraft(kind: FieldKind, d: EditDraft): string | null {
  if (kind === "date") return Object.keys(validateDate(d.date)).length ? "extraction.err.date" : null;
  if (kind === "time") return validateTime(d.time) ? "extraction.err.time" : null;
  if (kind === "pada") return /^[1-4]$/.test(d.number.trim()) ? null : "extraction.err.pada";
  if (kind === "area") return d.number.trim() && Number(d.number) >= 0 && !Number.isNaN(Number(d.number)) ? null : "extraction.err.area";
  return d.text.trim() ? null : "extraction.err.empty";
}

/**
 * The review request body. `accept` applies the extracted value as read; `edit` sends the corrected
 * value in the field's JSON shape; `reject` applies nothing. Only this endpoint creates facts.
 */
export function buildReviewBody(action: ReviewIn["action"], kind: FieldKind, draft: EditDraft | null, note: string, targetPersonId?: string | null): ReviewIn {
  const body: ReviewIn = { action };
  if (note.trim()) body.note = note.trim();
  if (targetPersonId) body.target_person_id = targetPersonId;
  if (action !== "edit" || !draft) return body;
  switch (kind) {
    case "date":
      body.value = normalizeDate(draft.date);
      break;
    case "time":
      body.value = { value: draft.time.value, precision: draft.time.precision, source: draft.time.source };
      break;
    case "pada":
      body.value = Number(draft.number);
      break;
    case "area":
      body.value = { value: Number(draft.number), unit: draft.unit.trim() || null };
      break;
    default:
      body.value = draft.text.trim();
  }
  return body;
}

const labelTone: Record<string, Tone> = { extracted: "saffron", "source-verified": "green", "user-confirmed": "blue", rejected: "stone" };

export function ExtractionReview({ documentId, canReview, needsTarget }: { documentId: string; canReview: boolean; needsTarget: boolean }) {
  const { t } = useTranslation();
  const { treeId } = useTreeCtx();
  const proposals = useProposals(treeId, documentId);
  const [target, setTarget] = useState<PersonSummary | null>(null);
  const items = proposals.data ?? [];
  const pending = items.filter((p) => p.status === "pending").length;
  return (
    <section aria-labelledby="review-title" className="space-y-3">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <h2 id="review-title" className="font-display text-lg font-semibold">
          {t("extraction.title")}
        </h2>
        {items.length > 0 && <span className="text-sm text-ink-muted">{t("extraction.pendingCount", { count: pending })}</span>}
      </div>
      <p className="flex items-start gap-2 rounded-lg bg-sky-50 p-3 text-sm text-sky-950">
        <Info className="mt-0.5 size-4 shrink-0" aria-hidden />
        {t("extraction.neverOverwrites")}
      </p>
      {canReview && needsTarget && pending > 0 && (
        <div className="max-w-md">
          <PersonPicker treeId={treeId} label={t("extraction.applyTo")} value={target} onChange={setTarget} hint={t("extraction.applyToHint")} />
        </div>
      )}
      {proposals.isLoading && <Spinner />}
      <ErrorAlert error={proposals.error} />
      {proposals.data && items.length === 0 && <EmptyState title={t("extraction.none")}>{t("extraction.noneHint")}</EmptyState>}
      <ul className="space-y-2">
        {items.map((p) => (
          <ProposalRow key={p.id} p={p} canReview={canReview} targetPersonId={target?.id ?? null} />
        ))}
      </ul>
    </section>
  );
}

function ProposalRow({ p, canReview, targetPersonId }: { p: ProposalOut; canReview: boolean; targetPersonId: string | null }) {
  const { t } = useTranslation();
  const { treeId } = useTreeCtx();
  const review = useReviewProposal(treeId);
  const kind = fieldKind(p.field);
  const [editing, setEditing] = useState(false);
  const [draft, setDraft] = useState<EditDraft>(() => draftFromProposal(p));
  const [note, setNote] = useState("");
  const [draftErr, setDraftErr] = useState<string | null>(null);
  // The server labels values: extracted | source-verified (accepted) | user-confirmed (edited) | rejected.
  const label = (p.value_label as ValueLabel | undefined) ?? valueLabel(p.status);
  const conflict = review.error instanceof ApiError && review.error.code === "conflicting_value";
  const loc = p.source_location as { page?: number; line?: number } | null;
  const send = (action: ReviewIn["action"]) => {
    if (action === "edit") {
      const e = validateDraft(kind, draft);
      setDraftErr(e);
      if (e) return;
    }
    review.mutate({ id: p.id, body: buildReviewBody(action, kind, action === "edit" ? draft : null, note, targetPersonId) }, { onSuccess: () => setEditing(false) });
  };
  const shown = p.status === "edited" || p.status === "accepted" ? p.final_value : p.proposed_value;

  return (
    <li className="card p-3" aria-label={p.label}>
      <div className="flex flex-col gap-2 sm:flex-row sm:items-start sm:justify-between">
        <div className="min-w-0">
          <p className="text-xs font-semibold uppercase tracking-wide text-ink-muted">{t(`extraction.field.${p.field}`, { defaultValue: p.label })}</p>
          <p className="text-base font-medium">{p.status === "edited" ? displayValue(shown) : p.display_value}</p>
          <div className="mt-1 flex flex-wrap items-center gap-1 text-xs text-ink-muted">
            <Badge tone={labelTone[label]}>{t(`extraction.label.${label}`)}</Badge>
            <span>{t("extraction.confidence", { pct: Math.round(p.confidence * 100) })}</span>
            {loc && (loc.page || loc.line) && <span>· {t("extraction.location", { page: loc.page ?? "?", line: loc.line ?? "?" })}</span>}
            <span>· {p.engine ?? p.extractor}</span>
            {p.applied_target_type && <span>· {t("extraction.appliedTo", { target: p.applied_target_type })}</span>}
          </div>
          {p.review_note && <p className="mt-1 text-xs italic">“{p.review_note}”</p>}
        </div>
        {canReview && p.status === "pending" && !editing && (
          <div className="flex shrink-0 flex-wrap gap-1">
            <Button size="sm" icon={<Check className="size-4" aria-hidden />} loading={review.isPending} onClick={() => send("accept")} aria-label={t("extraction.acceptNamed", { field: p.label })}>
              {t("extraction.accept")}
            </Button>
            <Button size="sm" variant="secondary" icon={<Edit3 className="size-4" aria-hidden />} onClick={() => setEditing(true)} aria-label={t("extraction.editNamed", { field: p.label })}>
              {t("extraction.edit")}
            </Button>
            <Button size="sm" variant="ghost" icon={<X className="size-4" aria-hidden />} loading={review.isPending} onClick={() => send("reject")} aria-label={t("extraction.rejectNamed", { field: p.label })}>
              {t("extraction.reject")}
            </Button>
          </div>
        )}
      </div>
      {editing && (
        <div className="mt-3 space-y-2 rounded-lg border border-stone-300 bg-parchment p-3">
          <ValueEditor kind={kind} draft={draft} onChange={setDraft} label={p.label} />
          <Field label={t("extraction.note")}>{(fp) => <TextInput {...fp} value={note} onChange={(e) => setNote(e.target.value)} />}</Field>
          {draftErr && (
            <p role="alert" className="field-error">
              {t(draftErr)}
            </p>
          )}
          <div className="flex gap-2">
            <Button size="sm" loading={review.isPending} onClick={() => send("edit")}>
              {t("extraction.saveAndAccept")}
            </Button>
            <Button size="sm" variant="secondary" onClick={() => setEditing(false)}>
              {t("common.cancel")}
            </Button>
          </div>
        </div>
      )}
      {conflict ? (
        <div role="alert" className="mt-2 rounded-lg border border-haldi-300 bg-haldi-100 p-3 text-sm text-haldi-700">
          <p className="font-semibold">{t("extraction.conflictTitle")}</p>
          <p>{t("extraction.conflictBody")}</p>
        </div>
      ) : (
        <div className="mt-2">
          <ErrorAlert error={review.error} />
        </div>
      )}
    </li>
  );
}

function displayValue(v: unknown): string {
  if (v == null) return "";
  if (typeof v === "string" || typeof v === "number") return String(v);
  return JSON.stringify(v);
}

function ValueEditor({ kind, draft, onChange, label }: { kind: FieldKind; draft: EditDraft; onChange: (d: EditDraft) => void; label: string }) {
  const { t } = useTranslation();
  if (kind === "date") return <GenealogicalDateEditor legend={label} value={draft.date} onChange={(date) => onChange({ ...draft, date })} showErrors />;
  if (kind === "time") return <TimeEditor legend={label} value={draft.time} onChange={(time) => onChange({ ...draft, time })} showErrors />;
  if (kind === "sex")
    return (
      <Field label={label}>
        {(p) => (
          <Select {...p} value={draft.text} onChange={(e) => onChange({ ...draft, text: e.target.value })}>
            <option value="">—</option>
            {SEXES.map((s) => (
              <option key={s} value={s}>
                {t(`enum.sex.${s}`)}
              </option>
            ))}
          </Select>
        )}
      </Field>
    );
  if (kind === "pada")
    return (
      <Field label={label}>
        {(p) => <TextInput {...p} type="number" min={1} max={4} value={draft.number} onChange={(e) => onChange({ ...draft, number: e.target.value })} />}
      </Field>
    );
  if (kind === "area")
    return (
      <div className="grid grid-cols-2 gap-2">
        <Field label={label}>{(p) => <TextInput {...p} inputMode="decimal" value={draft.number} onChange={(e) => onChange({ ...draft, number: e.target.value })} />}</Field>
        <Field label={t("property.parcel.areaUnit")}>{(p) => <TextInput {...p} value={draft.unit} onChange={(e) => onChange({ ...draft, unit: e.target.value })} />}</Field>
      </div>
    );
  return <Field label={label}>{(p) => <TextInput {...p} value={draft.text} onChange={(e) => onChange({ ...draft, text: e.target.value })} />}</Field>;
}
