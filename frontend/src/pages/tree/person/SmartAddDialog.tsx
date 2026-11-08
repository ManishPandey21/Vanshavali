import { DuplicatePanel } from "../../../components/review/ReviewParts";
import { useId, useMemo, useState, type FormEvent } from "react";
import { useTranslation } from "react-i18next";
import { ArrowLeft, Check, CircleDashed, Undo2, UserCheck, UserPlus } from "lucide-react";
import type {
  PersonCreate,
  PersonSummary,
  ProfileStatus,
  SexAtBirth,
  SmartAddCommitOut,
  SmartAddPlan,
  SmartAddPreviewItem,
  SmartAddStep,
  SmartAddTerm,
} from "../../../api/types";
import { useSmartAddCommit, useSmartAddPlan, useSmartAddTerms, useSmartAddUndo } from "../../../api/hooks/smartAdd";
import { useTreeCtx } from "../../../lib/tree-context";
import { Button, ButtonLink } from "../../../components/ui/Button";
import { Dialog } from "../../../components/ui/Dialog";
import { ErrorAlert, Spinner } from "../../../components/ui/feedback";
import { Field, Select, TextInput, focusFirstInvalid, intOrNull } from "../../../components/ui/form";
import { FamilyConsentGate } from "../../../components/consent/FamilyConsent";
import { cleanName, type NameDraft } from "../../../components/person/NameFields";
import { TransliterationSuggestion } from "../../../components/person/TransliterationSuggestion";

/** The eight relations offered first; everything else is under "More relations". */
const PRIMARY = ["father", "mother", "husband", "wife", "son", "daughter", "brother", "sister"];
const GROUP_ORDER = ["grandparents", "paternal", "maternal", "siblings", "children", "in_laws"];
const SEX_OPTIONS: SexAtBirth[] = ["male", "female", "intersex", "unknown"];

type Stage = "choose" | "steps" | "details" | "preview" | "done";

interface Details {
  given: string;
  surname: string;
  status: ProfileStatus;
  sex: SexAtBirth | "";
  birthYear: string;
  relativeAge: "" | "elder" | "younger";
  otherParentId: string;
  /** names accepted from a transliteration suggestion (ADR-0025), saved after the typed one */
  extraNames?: NameDraft[];
}

/** Devanagari typed in the name field is recorded as Hindi in Devanagari; anything else as typed. */
function scriptOf(text: string): { language: string; script: string } {
  return /[ऀ-ॿ]/.test(text) ? { language: "hi", script: "Deva" } : { language: "en", script: "Latn" };
}

export function buildSmartAddPerson(d: Details): PersonCreate {
  const { language, script } = scriptOf(`${d.given} ${d.surname}`);
  const year = intOrNull(d.birthYear);
  return {
    profile_status: d.status,
    sex_at_birth: d.sex || null,
    names: [{ given_name: d.given.trim() || null, surname: d.surname.trim() || null, language, script, is_preferred: true }, ...(d.extraNames ?? []).map(cleanName)],
    ...(year ? { birth: { date: { calendar: "gregorian", precision: "circa", year } } } : {}),
  } as PersonCreate;
}

/**
 * Smart Add Relative (ADR-0020): "Whom do you want to add?" → resolve each step through recorded
 * relatives (or add them as unknown for now) → a few details → a preview of every record → confirm.
 * Nothing is written before the user confirms; the result can be undone for 30 minutes.
 */
export function SmartAddDialog({ anchor, onClose }: { anchor: PersonSummary; onClose: () => void }) {
  const { t } = useTranslation();
  const { treeId } = useTreeCtx();
  const terms = useSmartAddTerms(treeId);
  const [stage, setStage] = useState<Stage>("choose");
  const [term, setTerm] = useState<SmartAddTerm | null>(null);
  const [choices, setChoices] = useState<string[]>([]);
  const plan = useSmartAddPlan(treeId, anchor.id, term?.code ?? null, choices);
  const commit = useSmartAddCommit(treeId, anchor.id);
  const undo = useSmartAddUndo(treeId);
  const [details, setDetails] = useState<Details>({ given: "", surname: "", status: "unknown", sex: "", birthYear: "", relativeAge: "", otherParentId: "" });
  const [provisionalSex, setProvisionalSex] = useState<(SexAtBirth | "")[]>([]);
  const [detailsError, setDetailsError] = useState<string | null>(null);
  const [result, setResult] = useState<SmartAddCommitOut | null>(null);
  const [undone, setUndone] = useState(false);

  const termLabel = (code: string) => t(`smartAdd.terms.${code}.label`);
  const termMeaning = (code: string) => t(`smartAdd.terms.${code}.meaning`);

  const pick = (tm: SmartAddTerm) => {
    setTerm(tm);
    setChoices([]);
    // a kinship term never fills in sex at birth: it starts as "Not recorded" (ADR-0020 §6)
    setDetails((d) => ({ ...d, sex: "", relativeAge: "", otherParentId: "" }));
    setProvisionalSex(tm.hops.slice(0, -1).map(() => ""));
    setStage(tm.hops.length > 1 ? "steps" : "details");
  };

  const choose = (index: number, value: string) => {
    const next = [...choices.slice(0, index), value];
    setChoices(next);
    if (term && next.length === term.hops.length - 1) setStage("details");
  };

  const back = () => {
    if (stage === "preview") setStage("details");
    else if (stage === "details" && term && term.hops.length > 1) {
      setChoices((c) => c.slice(0, -1));
      setStage("steps");
    } else if (stage === "steps" && choices.length > 0) setChoices((c) => c.slice(0, -1));
    else {
      setTerm(null);
      setChoices([]);
      setStage("choose");
    }
  };

  const submitDetails = (e: FormEvent) => {
    e.preventDefault();
    if (!details.given.trim() && !details.surname.trim()) {
      setDetailsError(t("smartAdd.err.name"));
      focusFirstInvalid(e.currentTarget as HTMLFormElement);
      return;
    }
    const y = details.birthYear.trim();
    if (y && (!/^\d{3,4}$/.test(y) || Number(y) > new Date().getFullYear())) {
      setDetailsError(t("smartAdd.err.year"));
      return;
    }
    setDetailsError(null);
    setStage("preview");
  };

  const confirm = () => {
    if (!term) return;
    commit.mutate(
      {
        term: term.code,
        choices,
        new_person: buildSmartAddPerson(details),
        other_parent_id: details.otherParentId || null,
        relative_age: details.relativeAge || null,
        provisional_sex_at_birth: provisionalSex.map((s) => s || null),
      },
      { onSuccess: (r) => (setResult(r), setStage("done")) },
    );
  };

  const title = stage === "choose" || !term ? t("smartAdd.title", { name: anchor.display_name }) : t("smartAdd.titleTerm", { term: termLabel(term.code), name: anchor.display_name });

  return (
    <Dialog
      open
      onClose={onClose}
      size="lg"
      title={title}
      description={term && stage !== "choose" ? termMeaning(term.code) : t("smartAdd.desc")}
      footer={
        stage === "done" ? (
          <Button onClick={onClose}>{t("common.close")}</Button>
        ) : (
          <>
            {stage !== "choose" && (
              <Button variant="secondary" icon={<ArrowLeft className="size-4" aria-hidden />} onClick={back}>
                {t("smartAdd.back")}
              </Button>
            )}
            <Button variant="secondary" onClick={onClose}>
              {t("common.cancel")}
            </Button>
            {stage === "details" && (
              <Button type="submit" form="smart-add-details">
                {t("smartAdd.reviewButton")}
              </Button>
            )}
            {stage === "preview" && (
              <Button icon={<Check className="size-4" aria-hidden />} loading={commit.isPending} onClick={confirm}>
                {t("smartAdd.confirm")}
              </Button>
            )}
          </>
        )
      }
    >
      <FamilyConsentGate treeId={treeId}>
        {stage === "choose" && (terms.isLoading ? <Spinner /> : <TermChooser terms={terms.data ?? []} onPick={pick} label={termLabel} meaning={termMeaning} />)}
        <ErrorAlert error={terms.error} />

        {stage === "steps" && term && (
          <>
            {plan.isLoading && <Spinner />}
            <ErrorAlert error={plan.error} />
            {plan.data && plan.data.term === term.code && <StepChooser plan={plan.data} choices={choices} onChoose={choose} />}
          </>
        )}

        {stage === "details" && term && (
          <DetailsForm
            term={term}
            anchor={anchor}
            plan={plan.data?.complete ? plan.data : undefined}
            value={details}
            onChange={setDetails}
            onSubmit={submitDetails}
            error={detailsError}
          />
        )}

        {stage === "preview" && term && (
          <>
            {plan.isFetching && !plan.data?.complete && <Spinner />}
            <ErrorAlert error={plan.error} />
            {plan.data?.complete && (
              <Preview
                plan={plan.data}
                newName={[details.given, details.surname].filter((s) => s.trim()).join(" ")}
                relativeAge={details.relativeAge}
                provisionalSex={provisionalSex}
                onProvisionalSex={setProvisionalSex}
              />
            )}
            <ErrorAlert error={commit.error} />
          </>
        )}

        {stage === "done" && result && term && (
          <div className="space-y-3" role="status">
            <p className="flex items-center gap-2 text-sm">
              <UserCheck className="size-5 text-green-700" aria-hidden />
              {undone ? t("smartAdd.undone") : t("smartAdd.added", { name: result.person.display_name, term: termLabel(term.code), anchor: anchor.display_name })}
            </p>
            {!undone && (
              <div className="flex flex-wrap gap-2">
                <ButtonLink to={`/t/${treeId}/people/${result.person.id}`} variant="secondary" size="sm">
                  {t("smartAdd.openProfile", { name: result.person.display_name })}
                </ButtonLink>
                <Button size="sm" variant="secondary" icon={<Undo2 className="size-4" aria-hidden />} loading={undo.isPending} onClick={() => undo.mutate(result.operation_id, { onSuccess: () => setUndone(true) })}>
                  {t("smartAdd.undo")}
                </Button>
              </div>
            )}
            {!undone && result.created_people.some((p) => p.is_provisional) && <p className="text-xs text-ink-muted">{t("smartAdd.provisionalNote")}</p>}
            <ErrorAlert error={undo.error} />
          </div>
        )}
      </FamilyConsentGate>
    </Dialog>
  );
}

function TermChooser({
  terms,
  onPick,
  label,
  meaning,
}: {
  terms: SmartAddTerm[];
  onPick: (t: SmartAddTerm) => void;
  label: (code: string) => string;
  meaning: (code: string) => string;
}) {
  const { t } = useTranslation();
  const byCode = new Map(terms.map((x) => [x.code, x]));
  const primary = PRIMARY.map((c) => byCode.get(c)).filter((x): x is SmartAddTerm => !!x);
  const button = (tm: SmartAddTerm) => (
    <li key={tm.code}>
      <button
        type="button"
        onClick={() => onPick(tm)}
        className="flex w-full flex-col items-start rounded-lg border border-stone-300 bg-white px-3 py-2 text-left hover:border-kumkum-700 focus-visible:outline-2 focus-visible:outline-kumkum-700"
      >
        <span className="font-medium">{label(tm.code)}</span>
        <span className="text-xs text-ink-muted">{meaning(tm.code)}</span>
      </button>
    </li>
  );
  return (
    <div className="space-y-4">
      <p className="text-sm font-medium">{t("smartAdd.whom")}</p>
      <ul className="grid grid-cols-2 gap-2 sm:grid-cols-4">{primary.map(button)}</ul>
      <details className="rounded-lg border border-stone-200 p-3">
        <summary className="cursor-pointer text-sm font-medium">{t("smartAdd.more")}</summary>
        <div className="mt-3 space-y-3">
          {GROUP_ORDER.map((g) => {
            const items = terms.filter((x) => x.group === g);
            if (!items.length) return null;
            return (
              <section key={g} aria-label={t(`smartAdd.group.${g}`)}>
                <h3 className="mb-1 text-xs font-semibold uppercase tracking-wide text-ink-muted">{t(`smartAdd.group.${g}`)}</h3>
                <ul className="grid grid-cols-2 gap-2 sm:grid-cols-3">{items.map(button)}</ul>
              </section>
            );
          })}
        </div>
      </details>
    </div>
  );
}

function hopWord(t: (k: string, o?: Record<string, unknown>) => string, relation: string, sex: string | null | undefined) {
  return t(`smartAdd.hop.${relation}.${sex ?? "any"}`);
}

function StepChooser({ plan, choices, onChoose }: { plan: SmartAddPlan; choices: string[]; onChoose: (i: number, v: string) => void }) {
  const { t } = useTranslation();
  const step = plan.steps[choices.length];
  const name = useId();
  // selecting is not choosing: arrow keys move through a radio group, so the user confirms with Continue
  const [selected, setSelected] = useState<string | null>(null);
  if (!step) return null;
  const from = step.from_person?.display_name ?? t("smartAdd.thatPerson");
  const who = hopWord(t, step.relation, step.sex);
  return (
    <form
      onSubmit={(e) => {
        e.preventDefault();
        if (selected) {
          setSelected(null);
          onChoose(step.index, selected);
        }
      }}
      className="space-y-3"
    >
      <fieldset className="space-y-3">
        <legend className="text-sm font-medium">{t("smartAdd.stepQuestion", { who, name: from })}</legend>
        {step.age && <p className="text-xs text-ink-muted">{t(`smartAdd.ageNote.${step.age}`, { name: from })}</p>}
        <ul className="space-y-2">
          {(step.candidates ?? []).map((c) => (
            <li key={c.id}>
              <label className="flex items-center gap-2 rounded-lg border border-stone-300 bg-white px-3 py-2">
                <input type="radio" name={name} className="accent-kumkum-700" checked={selected === c.id} onChange={() => setSelected(c.id)} />
                <span>{c.display_name}</span>
                {c.birth_display && <span className="text-xs text-ink-muted">{c.birth_display}</span>}
              </label>
            </li>
          ))}
          {step.allow_new && (
            <li>
              <label className="flex items-center gap-2 rounded-lg border border-dashed border-stone-400 bg-white px-3 py-2">
                <input type="radio" name={name} className="accent-kumkum-700" checked={selected === "new"} onChange={() => setSelected("new")} />
                <CircleDashed className="size-4 text-ink-muted" aria-hidden />
                <span>{t("smartAdd.addUnknown", { who })}</span>
              </label>
            </li>
          )}
        </ul>
      </fieldset>
      {(step.hidden_candidates ?? 0) > 0 && <p className="text-xs text-ink-muted">{t("smartAdd.hiddenNote", { count: step.hidden_candidates })}</p>}
      {!step.allow_new && !step.candidates?.length && <p className="text-sm">{t("smartAdd.noOptions")}</p>}
      <Button type="submit" size="sm" disabled={!selected}>
        {t("smartAdd.continue")}
      </Button>
    </form>
  );
}

function DetailsForm({
  term,
  anchor,
  plan,
  value,
  onChange,
  onSubmit,
  error,
}: {
  term: SmartAddTerm;
  anchor: PersonSummary;
  plan?: SmartAddPlan;
  value: Details;
  onChange: (d: Details) => void;
  onSubmit: (e: FormEvent) => void;
  error: string | null;
}) {
  const { t } = useTranslation();
  const { treeId } = useTreeCtx();
  const set = (patch: Partial<Details>) => onChange({ ...value, ...patch });
  const ageName = useId();
  const blocked = plan?.target?.blocked;
  const otherParents = plan?.target?.other_parent_options ?? [];
  return (
    <form id="smart-add-details" onSubmit={onSubmit} noValidate className="space-y-4">
      {blocked && (
        <p role="alert" className="rounded-lg bg-red-50 p-3 text-sm text-red-900">
          {t(`smartAdd.blocked.${blocked}`)}
        </p>
      )}
      <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
        <Field label={t("smartAdd.givenName")}>{(p) => <TextInput {...p} value={value.given} onChange={(e) => set({ given: e.target.value })} autoComplete="off" />}</Field>
        <Field label={t("smartAdd.surname")}>{(p) => <TextInput {...p} value={value.surname} onChange={(e) => set({ surname: e.target.value })} autoComplete="off" />}</Field>
        <div className="sm:col-span-2">
          <TransliterationSuggestion
            name={{ given_name: value.given, surname: value.surname, ...scriptOf(`${value.given} ${value.surname}`) }}
            onAdd={(n) => set({ extraNames: [...(value.extraNames ?? []), n] })}
          />
          {/* duplicates at entry (ADR-0021 §8): people already visible in the tree, never hidden ones */}
          <div className="mt-2">
            <DuplicatePanel
              treeId={treeId}
              check={
                value.given.trim().length >= 2
                  ? {
                      names: [{ given_name: value.given.trim(), surname: value.surname.trim() || null }],
                      birth_year: /^\d{3,4}$/.test(value.birthYear.trim()) ? Number(value.birthYear.trim()) : null,
                      exclude_ids: [anchor.id],
                    }
                  : null
              }
            />
          </div>
          {(value.extraNames ?? []).length > 0 && (
            <ul className="mt-2 space-y-1 text-xs text-ink-muted">
              {(value.extraNames ?? []).map((n, i) => (
                <li key={i} className="flex items-center gap-2">
                  {t("translit.addedNote")}{" "}
                  <span lang={n.language ?? undefined} className="font-medium text-ink">
                    {[n.given_name, n.surname].filter(Boolean).join(" ")}
                  </span>
                  <button
                    type="button"
                    className="underline"
                    onClick={() => set({ extraNames: (value.extraNames ?? []).filter((_, j) => j !== i) })}
                  >
                    {t("common.remove")}
                  </button>
                </li>
              ))}
            </ul>
          )}
        </div>
        <Field label={t("person.status")}>
          {(p) => (
            <Select {...p} value={value.status} onChange={(e) => set({ status: e.target.value as ProfileStatus })}>
              {(["living", "deceased", "unknown"] as const).map((s) => (
                <option key={s} value={s}>
                  {t(`enum.profileStatus.${s}`)}
                </option>
              ))}
            </Select>
          )}
        </Field>
        <Field label={t("smartAdd.birthYear")} hint={t("smartAdd.birthYearHint")}>
          {(p) => <TextInput {...p} inputMode="numeric" value={value.birthYear} onChange={(e) => set({ birthYear: e.target.value })} />}
        </Field>
        <Field label={t("person.sexAtBirth")} hint={t("smartAdd.sexHint")}>
          {(p) => (
            <Select {...p} value={value.sex} onChange={(e) => set({ sex: e.target.value as SexAtBirth | "" })}>
              <option value="">{t("person.notRecorded")}</option>
              {SEX_OPTIONS.map((s) => (
                <option key={s} value={s}>
                  {t(`enum.sex.${s}`)}
                </option>
              ))}
            </Select>
          )}
        </Field>
        {otherParents.length > 0 && (
          <Field label={t("smartAdd.otherParent")}>
            {(p) => (
              <Select {...p} value={value.otherParentId} onChange={(e) => set({ otherParentId: e.target.value })}>
                <option value="">{t("smartAdd.otherParentNone")}</option>
                {otherParents.map((o) => (
                  <option key={o.id} value={o.id}>
                    {o.display_name}
                  </option>
                ))}
              </Select>
            )}
          </Field>
        )}
      </div>
      {term.asks_relative_age && (
        <fieldset>
          <legend className="label">{t("smartAdd.relativeAge", { name: anchor.display_name })}</legend>
          <div className="flex flex-wrap gap-4 text-sm">
            {(["elder", "younger", ""] as const).map((a) => (
              <label key={a || "unknown"} className="inline-flex items-center gap-2">
                <input type="radio" name={ageName} className="accent-kumkum-700" checked={value.relativeAge === a} onChange={() => set({ relativeAge: a })} />
                {t(`smartAdd.age.${a || "unknown"}`)}
              </label>
            ))}
          </div>
        </fieldset>
      )}
      <p className="text-xs text-ink-muted">{t("smartAdd.moreLater")}</p>
      {error && (
        <p role="alert" className="field-error text-sm">
          {error}
        </p>
      )}
    </form>
  );
}

function Preview({
  plan,
  newName,
  relativeAge,
  provisionalSex,
  onProvisionalSex,
}: {
  plan: SmartAddPlan;
  newName: string;
  relativeAge: Details["relativeAge"];
  provisionalSex: (SexAtBirth | "")[];
  onProvisionalSex: (v: (SexAtBirth | "")[]) => void;
}) {
  const { t } = useTranslation();
  const rows = useMemo(() => (plan.preview ?? []).slice(1), [plan.preview]);
  const target = plan.target;
  const line = (item: SmartAddPreviewItem, i: number) => {
    const prev = i === 0 ? plan.anchor.display_name : (rows[i - 1].person?.display_name ?? t("smartAdd.unknownPerson"));
    const who = hopWord(t, item.relation ?? "", i < plan.steps.length ? (plan.steps[i] as SmartAddStep).sex : target?.sex);
    const role = t("smartAdd.preview.role", { who, name: prev });
    if (item.kind === "existing") return t("smartAdd.preview.existing", { role, name: item.person?.display_name });
    if (item.kind === "provisional") return t("smartAdd.preview.provisional", { role });
    return t("smartAdd.preview.new", { role, name: newName });
  };
  return (
    <div className="space-y-3">
      <p className="text-sm font-medium">{t("smartAdd.previewIntro")}</p>
      <ol className="space-y-2">
        {rows.map((item, i) => (
          <li key={i} className={`rounded-lg border px-3 py-2 text-sm ${item.kind === "existing" ? "border-stone-200 bg-parchment-deep" : "border-kumkum-700/40 bg-white"}`}>
            <span className="flex items-center gap-2">
              {item.kind === "existing" ? <UserCheck className="size-4" aria-hidden /> : item.kind === "provisional" ? <CircleDashed className="size-4" aria-hidden /> : <UserPlus className="size-4" aria-hidden />}
              {line(item, i)}
            </span>
            {item.kind === "provisional" && (
              <Field label={t("smartAdd.provisionalSex")} className="mt-2 max-w-xs">
                {(p) => (
                  <Select
                    {...p}
                    value={provisionalSex[i] ?? ""}
                    onChange={(e) => onProvisionalSex(provisionalSex.map((s, j) => (j === i ? (e.target.value as SexAtBirth | "") : s)))}
                  >
                    <option value="">{t("person.notRecorded")}</option>
                    {SEX_OPTIONS.map((s) => (
                      <option key={s} value={s}>
                        {t(`enum.sex.${s}`)}
                      </option>
                    ))}
                  </Select>
                )}
              </Field>
            )}
            {item.kind === "new" && target?.link === "shared_parents" && (
              <p className="mt-1 text-xs text-ink-muted">{t("smartAdd.preview.sharedParents", { names: (target.shared_parents ?? []).map((p) => p.display_name).join(", ") })}</p>
            )}
            {item.kind === "new" && target?.link === "explicit_sibling" && <p className="mt-1 text-xs text-ink-muted">{t("smartAdd.preview.explicitSibling")}</p>}
            {item.kind === "new" && !item.age && relativeAge && (
              <p className="mt-1 text-xs text-ink-muted">{t(`smartAdd.preview.age.${relativeAge}`, { name: plan.anchor.display_name })}</p>
            )}
            {item.age && <p className="mt-1 text-xs text-ink-muted">{t(`smartAdd.preview.age.${item.age}`, { name: i === 0 ? plan.anchor.display_name : (rows[i - 1].person?.display_name ?? t("smartAdd.unknownPerson")) })}</p>}
          </li>
        ))}
      </ol>
      <p className="text-xs text-ink-muted">{t("smartAdd.previewFooter")}</p>
    </div>
  );
}
