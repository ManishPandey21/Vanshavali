import { DuplicatePanel, duplicateCheckFor } from "../../../components/review/ReviewParts";
import { useId, useState, type FormEvent } from "react";
import { useTranslation } from "react-i18next";
import type { GenealogicalDate, PersonSummary, RelationshipType, RelativeIn, SexAtBirth, UnionOut } from "../../../api/types";
import { useAddRelative } from "../../../api/hooks/people";
import { useTreeCtx } from "../../../lib/tree-context";
import { emptyDate, normalizeDate, validateDate } from "../../../lib/dates";
import { GenealogicalDateEditor } from "../../../components/dates/GenealogicalDateEditor";
import { PersonPicker } from "../../../components/pickers";
import {
  PersonForm,
  buildPersonCreate,
  emptyPersonDraft,
  hasDate,
  validatePersonDraft,
  type PersonDraft,
} from "../../../components/person/PersonForm";
import { Button } from "../../../components/ui/Button";
import { Dialog } from "../../../components/ui/Dialog";
import { ErrorAlert } from "../../../components/ui/feedback";
import { Field, Select, TextInput, focusFirstInvalid } from "../../../components/ui/form";
import { FamilyConsentGate } from "../../../components/consent/FamilyConsent";

export type RelationKind = "parent" | "spouse" | "child" | "sibling";

export const PARENT_TYPES: RelationshipType[] = ["biological_parent", "adoptive_parent", "step_parent", "foster_parent", "guardian"];
export const UNION_TYPES: RelationshipType[] = ["spouse", "partner", "divorced_spouse", "separated_spouse"];

/**
 * Link a new or existing person as parent / spouse / child / sibling of `anchor`
 * (POST /people/{id}/relatives). For a child, the user chooses which union it belongs to so
 * half-siblings and multiple marriages are modelled correctly.
 */
export function AddRelativeDialog({
  anchor,
  relation,
  unions,
  initialUnionId,
  initialSex,
  onClose,
  onAdded,
}: {
  anchor: PersonSummary;
  relation: RelationKind;
  unions: UnionOut[];
  initialUnionId?: string | null;
  /** Pre-selects sex at birth for a new person ("Add father" / "Add mother"); still editable. */
  initialSex?: SexAtBirth;
  onClose: () => void;
  onAdded?: (p: PersonSummary) => void;
}) {
  const { t, i18n } = useTranslation();
  const { treeId, tree } = useTreeCtx();
  const add = useAddRelative(treeId, anchor.id);
  const modeName = useId();
  const [mode, setMode] = useState<"new" | "existing">("new");
  const [existing, setExisting] = useState<PersonSummary | null>(null);
  const [draft, setDraft] = useState<PersonDraft>(() => {
    const d = emptyPersonDraft(i18n.language);
    if (relation === "parent" || relation === "spouse") d.profile_status = "unknown";
    if (initialSex) d.sex_at_birth = initialSex;
    return d;
  });
  const [relType, setRelType] = useState<RelationshipType>(relation === "spouse" ? "spouse" : "biological_parent");
  const [subtype, setSubtype] = useState("");
  // Unions with a hidden partner carry no relationship id and cannot be chosen.
  const visibleUnions = unions.filter((u): u is UnionOut & { relationship: NonNullable<UnionOut["relationship"]> } => !!u.relationship);
  const [unionId, setUnionId] = useState<string>(initialUnionId ?? visibleUnions[0]?.relationship.id ?? "");
  const [startDate, setStartDate] = useState<GenealogicalDate>(emptyDate());
  const [submitted, setSubmitted] = useState(false);
  const [err, setErr] = useState<string | null>(null);

  const submit = (e: FormEvent) => {
    e.preventDefault();
    setSubmitted(true);
    const form = e.currentTarget as HTMLFormElement;
    const body: RelativeIn = { relation };
    if (mode === "existing") {
      if (!existing) {
        setErr(t("relatives.pickPerson"));
        return;
      }
      body.existing_person_id = existing.id;
    } else {
      if (Object.keys(validatePersonDraft(draft)).length) {
        setErr(t("person.err.fixErrors"));
        focusFirstInvalid(form);
        return;
      }
      body.new_person = buildPersonCreate(draft);
    }
    if (relation === "parent" || relation === "child" || relation === "spouse") body.relationship_type = relType;
    if (relation === "child" && unionId) body.union_id = unionId;
    if ((relation === "parent" || relation === "spouse") && subtype.trim()) body.subtype = subtype.trim();
    if (relation === "spouse" && hasDate(startDate)) {
      if (Object.keys(validateDate(startDate)).length) {
        setErr(t("person.err.fixErrors"));
        focusFirstInvalid(form);
        return;
      }
      body.start_date = normalizeDate(startDate);
    }
    setErr(null);
    add.mutate(body, {
      onSuccess: (res) => {
        onAdded?.(res.person);
        onClose();
      },
    });
  };

  const typeOptions = relation === "spouse" ? UNION_TYPES : PARENT_TYPES;
  const partnerName = (u: UnionOut) => (u.partner.person ? u.partner.person.display_name : t("person.privatePerson"));

  return (
    <Dialog
      open
      onClose={onClose}
      size="lg"
      title={t(`relatives.title.${relation}`, { name: anchor.display_name })}
      description={t(`relatives.desc.${relation}`)}
      footer={
        <>
          <Button variant="secondary" onClick={onClose}>
            {t("common.cancel")}
          </Button>
          <Button type="submit" form="relative-form" loading={add.isPending}>
            {t(`relatives.submit.${relation}`)}
          </Button>
        </>
      }
    >
      <form id="relative-form" onSubmit={submit} noValidate className="space-y-4">
        <fieldset>
          <legend className="label">{t("relatives.who")}</legend>
          <div className="flex flex-wrap gap-4 text-sm">
            <label className="inline-flex items-center gap-2">
              <input type="radio" name={modeName} className="accent-kumkum-700" checked={mode === "new"} onChange={() => setMode("new")} />
              {t("relatives.newPerson")}
            </label>
            <label className="inline-flex items-center gap-2">
              <input type="radio" name={modeName} className="accent-kumkum-700" checked={mode === "existing"} onChange={() => setMode("existing")} />
              {t("relatives.existingPerson")}
            </label>
          </div>
        </fieldset>

        {relation !== "sibling" && (
          <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
            <Field label={t("relatives.relType")}>
              {(p) => (
                <Select {...p} value={relType} onChange={(e) => setRelType(e.target.value as RelationshipType)}>
                  {typeOptions.map((rt) => (
                    <option key={rt} value={rt}>
                      {t(`enum.relType.${rt}`)}
                    </option>
                  ))}
                </Select>
              )}
            </Field>
            {relation === "child" ? (
              <Field label={t("relatives.union")} hint={t("relatives.unionHint")}>
                {(p) => (
                  <Select {...p} value={unionId} onChange={(e) => setUnionId(e.target.value)}>
                    {visibleUnions.map((u) => (
                      <option key={u.relationship.id} value={u.relationship.id}>
                        {t("relatives.withPartner", { name: partnerName(u) })}
                      </option>
                    ))}
                    <option value="">{t("relatives.noUnion")}</option>
                  </Select>
                )}
              </Field>
            ) : (
              <Field label={t("relatives.subtype")} hint={t("relatives.subtypeHint")}>
                {(p) => <TextInput {...p} value={subtype} onChange={(e) => setSubtype(e.target.value)} />}
              </Field>
            )}
          </div>
        )}

        {relation === "spouse" && <GenealogicalDateEditor legend={t("relatives.unionStart")} value={startDate} onChange={setStartDate} showErrors={submitted && hasDate(startDate)} />}

        {mode === "existing" ? (
          <PersonPicker treeId={treeId} label={t("relatives.findPerson")} value={existing} onChange={setExisting} excludeIds={[anchor.id]} />
        ) : (
          <FamilyConsentGate treeId={treeId}>
            <PersonForm treeId={treeId} draft={draft} onChange={setDraft} showErrors={submitted} compact treeDefaultPrivacy={tree.default_person_privacy} />
            <DuplicatePanel
              treeId={treeId}
              check={duplicateCheckFor(draft, {
                parentIds: relation === "child" ? [anchor.id] : [],
                spouseIds: relation === "spouse" ? [anchor.id] : [],
                excludeIds: [anchor.id],
              })}
              onUse={(p) => {
                setExisting({ id: p.id, display_name: p.display_name } as PersonSummary);
                setMode("existing");
              }}
            />
          </FamilyConsentGate>
        )}
        {err && (
          <p role="alert" className="field-error text-sm">
            {err}
          </p>
        )}
        <ErrorAlert error={add.error} />
      </form>
    </Dialog>
  );
}
