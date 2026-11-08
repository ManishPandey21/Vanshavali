import { useState, type FormEvent } from "react";
import { useTranslation } from "react-i18next";
import { AlertTriangle, ChevronDown, ChevronRight, Edit3, Plus, Star, Trash2 } from "lucide-react";
import type { AssertionOut, EvidenceStatus, HeritageAttribute, HeritageAttributeView, PrivacyLevel, ValueStatus } from "../../api/types";
import { useAddAssertion, useDeleteAssertion, useHeritage, useUpdateAssertion, type HeritageSubject } from "../../api/hooks/heritage";
import { usePravaraSuggestions } from "../../api/hooks/vocabularies";
import { useCreatePlace } from "../../api/hooks/people";
import { useTreeCtx } from "../../lib/tree-context";
import { EvidenceBadge, PrivacyBadge, RedactionNotice } from "../person/badges";
import { EVIDENCE_STATUSES } from "../person/NameFields";
import { PRIVACY_LEVELS } from "../person/PersonForm";
import { PlacePicker, emptyPlace, type PlaceValue } from "../pickers";
import { CitationList } from "../evidence/Citations";
import { Button } from "../ui/Button";
import { ConfirmDialog, Dialog } from "../ui/Dialog";
import { ErrorAlert, Spinner } from "../ui/feedback";
import { Checkbox, Field, Select, TextArea, TextInput } from "../ui/form";
import { LinkedNote, SmartSelect, type VocabRef } from "../ui/SmartSelect";
import { Badge } from "../ui/Badge";

/** Heritage attributes that take suggestions from a master-data vocabulary (ADR-0018 §2). */
const VOCABULARY_FOR: Partial<Record<HeritageAttribute, string>> = {
  gotra: "gotra",
  pravara: "pravara",
  kula_or_vamsha: "kula",
  kuladevata: "kuladevata",
  kuladevi: "kuladevi",
  devak: "devak",
  ancestral_occupation: "occupation",
  family_language: "language",
};
/** A family deity may name the temple where the family worships it (ADR-0026 §5). */
const TEMPLE_ATTRS = new Set<HeritageAttribute>(["kuladevata", "kuladevi"]);

function refOf(value: unknown): VocabRef | null {
  if (value && typeof value === "object" && "vocabulary" in value && "code" in value) {
    const v = value as { vocabulary: unknown; code: unknown };
    if (typeof v.vocabulary === "string" && typeof v.code === "string") return { vocabulary: v.vocabulary, code: v.code };
  }
  return null;
}

export const HERITAGE_ATTRIBUTES: HeritageAttribute[] = [
  "gotra",
  "pravara",
  "kula_or_vamsha",
  "kuladevata",
  "kuladevi",
  "devak",
  "ancestral_village",
  "ancestral_house_name",
  "tharavad_or_equivalent",
  "temple",
  "community",
  "jati_or_subgroup",
  "religion",
  "ancestral_occupation",
  "family_language",
  "family_traditions",
  "language_traditions",
  "recorded_parent_name",
  "other",
];
const VALUE_STATUSES: ValueStatus[] = ["known", "unknown", "not_applicable", "withheld"];

function valueText(a: AssertionOut, t: (k: string) => string): string {
  if (a.value_status !== "known") return t(`enum.valueStatus.${a.value_status}`);
  return a.value_text || a.place_name || (a.value_json != null ? JSON.stringify(a.value_json) : "");
}

/**
 * Heritage profile (gotra, pravara, kula, kuladevata, ancestral village…) for a person or branch.
 * Every value is an explicit assertion with evidence status; nothing here is inferred or auto-filled.
 */
export function HeritageProfile({ subject, canWrite }: { subject: HeritageSubject; canWrite: boolean }) {
  const { t } = useTranslation();
  const { treeId } = useTreeCtx();
  const profile = useHeritage(treeId, subject);
  const [adding, setAdding] = useState<HeritageAttribute | "any" | null>(null);
  const [editing, setEditing] = useState<AssertionOut | null>(null);

  const byAttr = new Map<string, HeritageAttributeView>((profile.data?.attributes ?? []).map((a) => [a.attribute, a]));
  const withheld = new Set(profile.data?.withheld_attributes ?? []);
  const shown = HERITAGE_ATTRIBUTES.filter((a) => byAttr.has(a) || withheld.has(a));
  // the recorded (preferred) gotra, only when it names a list entry: pravara suggestions follow it
  const gotraRef = refOf(byAttr.get("gotra")?.preferred?.value_json);
  const gotraCode = gotraRef?.vocabulary === "gotra" ? gotraRef.code : null;
  const missing = HERITAGE_ATTRIBUTES.filter((a) => !byAttr.has(a) && !withheld.has(a));

  return (
    <section aria-labelledby="her-title" className="space-y-4">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <h2 id="her-title" className="font-display text-lg font-semibold">
          {t("heritage.title")}
        </h2>
        {canWrite && (
          <Button size="sm" icon={<Plus className="size-4" aria-hidden />} onClick={() => setAdding("any")}>
            {t("heritage.add")}
          </Button>
        )}
      </div>
      <p className="rounded-lg bg-parchment-deep p-3 text-xs text-ink-muted">{t("heritage.noInference")}</p>
      {profile.isLoading && <Spinner />}
      <ErrorAlert error={profile.error} />
      {profile.data && shown.length === 0 && <p className="text-sm text-ink-muted">{t("heritage.none")}</p>}
      <dl className="grid gap-3 md:grid-cols-2">
        {shown.map((attr) => (
          <AttributeCard key={attr} attr={attr} view={byAttr.get(attr)} withheld={withheld.has(attr)} canWrite={canWrite} onEdit={setEditing} onAdd={() => setAdding(attr)} />
        ))}
      </dl>
      {canWrite && missing.length > 0 && (
        <div>
          <p className="mb-1 text-xs font-semibold uppercase tracking-wide text-ink-muted">{t("heritage.notRecorded")}</p>
          <div className="flex flex-wrap gap-1">
            {missing.map((a) => (
              <button key={a} type="button" className="rounded-full border border-dashed border-stone-400 px-2.5 py-1 text-xs hover:bg-white" onClick={() => setAdding(a)}>
                + {t(`enum.heritage.${a}`)}
              </button>
            ))}
          </div>
        </div>
      )}
      {adding && <AssertionDialog subject={subject} attribute={adding === "any" ? null : adding} assertion={null} gotraCode={gotraCode} onClose={() => setAdding(null)} />}
      {editing && <AssertionDialog subject={subject} attribute={editing.attribute as HeritageAttribute} assertion={editing} gotraCode={gotraCode} onClose={() => setEditing(null)} />}
    </section>
  );
}

function AttributeCard({
  attr,
  view,
  withheld,
  canWrite,
  onEdit,
  onAdd,
}: {
  attr: HeritageAttribute;
  view?: HeritageAttributeView;
  withheld: boolean;
  canWrite: boolean;
  onEdit: (a: AssertionOut) => void;
  onAdd: () => void;
}) {
  const { t } = useTranslation();
  const [showAlt, setShowAlt] = useState(false);
  const [cites, setCites] = useState(false);
  const pref = view?.preferred;
  const alts = view?.alternatives ?? [];
  return (
    <div className="card p-4">
      <dt className="flex items-center justify-between gap-2">
        <span className="text-xs font-semibold uppercase tracking-wide text-ink-muted">{t(`enum.heritage.${attr}`)}</span>
        {view?.disputed && (
          <Badge tone="red" icon={<AlertTriangle className="size-3" aria-hidden />}>
            {t("heritage.disputed")}
          </Badge>
        )}
      </dt>
      <dd className="mt-1">
        {withheld && !pref ? (
          <RedactionNotice />
        ) : pref ? (
          <AssertionLine a={pref} preferred canWrite={canWrite} onEdit={onEdit} />
        ) : alts.length ? (
          <p className="text-sm text-ink-muted">{t("heritage.noPreferred")}</p>
        ) : null}
        {pref && (
          <button type="button" className="mt-1 text-xs text-kumkum-800 underline" aria-expanded={cites} onClick={() => setCites(!cites)}>
            {t("citations.count", { count: pref.citation_count ?? 0 })}
          </button>
        )}
        {pref && cites && <CitationList targetType="assertion" targetId={pref.id} canEditTarget={canWrite} />}
        {alts.length > 0 && (
          <div className="mt-2">
            <button type="button" className="inline-flex items-center gap-1 text-xs font-medium text-kumkum-800" aria-expanded={showAlt} onClick={() => setShowAlt(!showAlt)}>
              {showAlt ? <ChevronDown className="size-3.5" aria-hidden /> : <ChevronRight className="size-3.5" aria-hidden />}
              {t("heritage.alternatives", { count: alts.length })}
            </button>
            {showAlt && (
              <ul className="mt-1 space-y-1 border-l-2 border-stone-200 pl-3">
                {alts.map((a) => (
                  <li key={a.id}>
                    <AssertionLine a={a} canWrite={canWrite} onEdit={onEdit} />
                  </li>
                ))}
              </ul>
            )}
          </div>
        )}
        {canWrite && (
          <button type="button" className="mt-2 block text-xs text-kumkum-800 underline" onClick={onAdd}>
            {t("heritage.addAlternative")}
          </button>
        )}
      </dd>
    </div>
  );
}

function AssertionLine({ a, preferred, canWrite, onEdit }: { a: AssertionOut; preferred?: boolean; canWrite: boolean; onEdit: (a: AssertionOut) => void }) {
  const { t } = useTranslation();
  const { treeId } = useTreeCtx();
  const update = useUpdateAssertion(treeId);
  const del = useDeleteAssertion(treeId);
  const [confirm, setConfirm] = useState(false);
  return (
    <div className="flex flex-wrap items-center gap-1.5">
      <span className={preferred ? "text-base font-semibold" : "text-sm"}>{valueText(a, t)}</span>
      <EvidenceBadge status={a.evidence_status} />
      {a.privacy_level && <PrivacyBadge level={a.privacy_level} />}
      {a.notes && <span className="w-full text-xs text-ink-muted">{a.notes}</span>}
      {canWrite && (
        <span className="ml-auto flex gap-1">
          {!preferred && (
            <button
              type="button"
              className="rounded p-1 hover:bg-haldi-100"
              onClick={() => update.mutate({ id: a.id, body: { is_preferred: true } })}
              aria-label={t("heritage.makePreferred", { value: valueText(a, t) })}
            >
              <Star className="size-3.5" aria-hidden />
            </button>
          )}
          <button type="button" className="rounded p-1 hover:bg-parchment-deep" onClick={() => onEdit(a)} aria-label={t("heritage.edit", { value: valueText(a, t) })}>
            <Edit3 className="size-3.5" aria-hidden />
          </button>
          <button type="button" className="rounded p-1 text-red-800 hover:bg-red-50" onClick={() => setConfirm(true)} aria-label={t("heritage.delete", { value: valueText(a, t) })}>
            <Trash2 className="size-3.5" aria-hidden />
          </button>
        </span>
      )}
      <ErrorAlert error={update.error} />
      <ConfirmDialog
        open={confirm}
        onClose={() => setConfirm(false)}
        title={t("heritage.deleteTitle")}
        body={valueText(a, t)}
        confirmLabel={t("common.delete")}
        danger
        loading={del.isPending}
        onConfirm={() => del.mutate(a.id, { onSuccess: () => setConfirm(false) })}
      >
        <ErrorAlert error={del.error} />
      </ConfirmDialog>
    </div>
  );
}

function AssertionDialog({
  subject,
  attribute,
  assertion,
  gotraCode,
  onClose,
}: {
  subject: HeritageSubject;
  attribute: HeritageAttribute | null;
  assertion: AssertionOut | null;
  gotraCode: string | null;
  onClose: () => void;
}) {
  const { t } = useTranslation();
  const { treeId } = useTreeCtx();
  const add = useAddAssertion(treeId, subject);
  const update = useUpdateAssertion(treeId);
  const createPlace = useCreatePlace(treeId);
  const [attr, setAttr] = useState<HeritageAttribute>(attribute ?? "gotra");
  const [status, setStatus] = useState<ValueStatus>(assertion?.value_status ?? "known");
  const [text, setText] = useState(assertion?.value_text ?? "");
  const [ref, setRef] = useState<VocabRef | null>(refOf(assertion?.value_json));
  const [place, setPlace] = useState<PlaceValue>(
    assertion?.place_id ? { place_id: assertion.place_id, place_label: assertion.place_name ?? null, place_as_recorded: assertion.place_name ?? "" } : emptyPlace(),
  );
  const [evidence, setEvidence] = useState<EvidenceStatus>(assertion?.evidence_status ?? "USER_ASSERTION");
  const [privacy, setPrivacy] = useState<PrivacyLevel | "">(assertion?.privacy_level ?? "");
  const [preferred, setPreferred] = useState<boolean>(assertion?.is_preferred ?? true);
  const [notes, setNotes] = useState(assertion?.notes ?? "");
  const [err, setErr] = useState<string | null>(null);
  const mutation = assertion ? update : add;
  const isPlace = attr === "ancestral_village";
  const takesTemple = TEMPLE_ATTRS.has(attr);

  const submit = async (e: FormEvent) => {
    e.preventDefault();
    const known = status === "known";
    // For a place attribute, a linked place is the value; unlinked typed text is kept as value_text.
    const valueTextOut = known ? (isPlace ? (place.place_id ? null : place.place_as_recorded.trim() || null) : text.trim() || null) : null;
    let placeId = known && (isPlace || takesTemple) ? place.place_id : null;
    if (known && takesTemple && !placeId && place.place_as_recorded.trim()) {
      // a temple typed by name becomes a place of type temple in this tree (the deity stays its own fact)
      try {
        placeId = (await createPlace.mutateAsync({ canonical_name: place.place_as_recorded.trim(), place_type: "temple" })).id;
      } catch {
        return; // the error is shown below
      }
    }
    if (known && !valueTextOut && !placeId) {
      setErr(t("heritage.valueRequired"));
      return;
    }
    setErr(null);
    const vocabulary = VOCABULARY_FOR[attr];
    // a value picked from a list keeps its label as typed and names the entry (ADR-0018 §6);
    // other attributes never have their value_json touched here
    const vocabValue = vocabulary ? { value_json: known && ref && ref.vocabulary === vocabulary ? ref : null } : {};
    const body = {
      value_status: status,
      value_text: valueTextOut,
      ...vocabValue,
      place_id: placeId,
      evidence_status: evidence,
      privacy_level: privacy || null,
      is_preferred: preferred,
      notes: notes.trim() || null,
    };
    if (assertion) {
      // Only send is_preferred when it changes: researchers may edit their own proposals but not mark them preferred.
      const { is_preferred, ...rest } = body;
      update.mutate({ id: assertion.id, body: is_preferred !== assertion.is_preferred ? body : rest }, { onSuccess: onClose });
    }
    else add.mutate({ attribute: attr, ...body }, { onSuccess: onClose });
  };

  return (
    <Dialog
      open
      onClose={onClose}
      title={assertion ? t("heritage.editTitle", { attr: t(`enum.heritage.${attr}`) }) : t("heritage.addTitle")}
      footer={
        <>
          <Button variant="secondary" onClick={onClose}>
            {t("common.cancel")}
          </Button>
          <Button type="submit" form="assertion-form" loading={mutation.isPending}>
            {t("common.save")}
          </Button>
        </>
      }
    >
      <form id="assertion-form" onSubmit={submit} noValidate className="space-y-3">
        <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
          <Field label={t("heritage.attribute")}>
            {(p) => (
              <Select {...p} value={attr} disabled={!!assertion || !!attribute} onChange={(e) => setAttr(e.target.value as HeritageAttribute)}>
                {HERITAGE_ATTRIBUTES.map((a) => (
                  <option key={a} value={a}>
                    {t(`enum.heritage.${a}`)}
                  </option>
                ))}
              </Select>
            )}
          </Field>
          <Field label={t("heritage.valueStatus")}>
            {(p) => (
              <Select {...p} value={status} onChange={(e) => setStatus(e.target.value as ValueStatus)}>
                {VALUE_STATUSES.map((s) => (
                  <option key={s} value={s}>
                    {t(`enum.valueStatus.${s}`)}
                  </option>
                ))}
              </Select>
            )}
          </Field>
        </div>
        {status === "known" &&
          (isPlace ? (
            <PlacePicker treeId={treeId} label={t("heritage.value")} value={place} onChange={setPlace} />
          ) : (
            VOCABULARY_FOR[attr] ? (
              <div>
                <SmartSelect
                  key={attr}
                  vocabulary={VOCABULARY_FOR[attr]!}
                  label={t("heritage.value")}
                  hint={attr === "gotra" ? t("heritage.gotraHint") : t("smartSelect.hint")}
                  text={text}
                  onChange={(v, r) => {
                    setText(v);
                    setRef(r);
                  }}
                />
                {ref && <LinkedNote />}
                {attr === "pravara" && (
                  <PravaraSuggestions
                    gotraCode={gotraCode}
                    onPick={(label, code) => {
                      setText(label);
                      setRef({ vocabulary: "pravara", code });
                    }}
                  />
                )}
              </div>
            ) : (
              <Field label={t("heritage.value")}>{(p) => <TextInput {...p} value={text} onChange={(e) => setText(e.target.value)} />}</Field>
            )
          ))}
        {status === "known" && takesTemple && (
          <div>
            <PlacePicker treeId={treeId} label={t("heritage.temple")} value={place} onChange={setPlace} />
            <p className="mt-1 text-xs text-ink-muted">{t("heritage.templeHint")}</p>
          </div>
        )}
        <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
          <Field label={t("names.evidence")}>
            {(p) => (
              <Select {...p} value={evidence} onChange={(e) => setEvidence(e.target.value as EvidenceStatus)}>
                {EVIDENCE_STATUSES.map((s) => (
                  <option key={s} value={s}>
                    {t(`enum.evidence.${s}`)}
                  </option>
                ))}
              </Select>
            )}
          </Field>
          <Field label={t("privacy.level")}>
            {(p) => (
              <Select {...p} value={privacy} onChange={(e) => setPrivacy(e.target.value as PrivacyLevel | "")}>
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
        <Checkbox label={t("heritage.preferred")} hint={t("heritage.preferredHint")} checked={preferred} onChange={setPreferred} />
        <Field label={t("heritage.notes")}>{(p) => <TextArea {...p} rows={2} value={notes} onChange={(e) => setNotes(e.target.value)} />}</Field>
        {err && (
          <p role="alert" className="field-error">
            {err}
          </p>
        )}
        <ErrorAlert error={createPlace.error ?? mutation.error} />
      </form>
    </Dialog>
  );
}

/**
 * Pravaras often associated with the recorded gotra, from reviewed links only (ADR-0026 §3). A
 * suggestion is never filled in: the person picks one, or types their own.
 */
function PravaraSuggestions({ gotraCode, onPick }: { gotraCode: string | null; onPick: (label: string, code: string) => void }) {
  const { t, i18n } = useTranslation();
  const lang = i18n.language.startsWith("hi") ? "hi" : "en";
  const sugg = usePravaraSuggestions(gotraCode, lang);
  if (!gotraCode) return <p className="mt-1 text-xs text-ink-muted">{t("heritage.pravaraNoGotra")}</p>;
  const items = sugg.data?.items ?? [];
  return (
    <div className="mt-2 rounded-lg border border-stone-200 p-2" role="group" aria-label={t("heritage.pravaraSuggestions")}>
      <p className="text-xs text-ink-muted">{t("heritage.pravaraDiffer")}</p>
      {sugg.isSuccess && items.length === 0 && <p className="mt-1 text-xs text-ink-muted">{t("heritage.pravaraNoneReviewed")}</p>}
      {items.length > 0 && (
        <ul className="mt-1 flex flex-wrap gap-1">
          {items.map((p) => (
            <li key={p.code}>
              <button type="button" className="rounded-full border border-stone-300 px-2.5 py-1 text-xs hover:bg-haldi-100" onClick={() => onPick(p.label, p.code)}>
                {p.label}
              </button>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}
