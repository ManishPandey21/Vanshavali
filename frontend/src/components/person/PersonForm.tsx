import { useState } from "react";
import { useTranslation } from "react-i18next";
import { ChevronDown, ChevronRight, Plus } from "lucide-react";
import type {
  GenealogicalDate,
  GenealogicalTime,
  PersonCreate,
  PrivacyLevel,
  ProfileStatus,
  SexAtBirth,
  VitalIn,
} from "../../api/types";
import { emptyDate, normalizeDate, validateDate, validateTime } from "../../lib/dates";
import { GenealogicalDateEditor } from "../dates/GenealogicalDateEditor";
import { TimeEditor, TimezoneSelect } from "../dates/TimeEditor";
import { PlacePicker, emptyPlace, type PlaceSuggestion, type PlaceValue } from "../pickers";
import { useBranches } from "../../api/hooks/family";
import { useHeritage } from "../../api/hooks/heritage";
import { SmartSelect } from "../ui/SmartSelect";
import { Field, Select } from "../ui/form";
import { Button } from "../ui/Button";
import { NameFields, cleanName, emptyName, nameHasContent, type NameDraft } from "./NameFields";

export const PRIVACY_LEVELS: PrivacyLevel[] = [
  "PRIVATE_SELF",
  "PRIVATE_TREE_ADMINS",
  "FAMILY_BRANCH",
  "TREE_MEMBERS",
  "INVITED_RESEARCHER",
  "PUBLIC_DECEASED_ONLY",
  "CUSTOM",
];
export const SEXES: SexAtBirth[] = ["male", "female", "intersex", "unknown"];
export const STATUSES: ProfileStatus[] = ["living", "deceased", "unknown"];

export interface VitalDraft {
  date: GenealogicalDate;
  time: GenealogicalTime;
  timezone_id: string;
  place: PlaceValue;
  description: string;
}

export function emptyVital(): VitalDraft {
  return {
    date: emptyDate(),
    time: { value: null, precision: "unknown", source: "unknown" },
    timezone_id: "",
    place: emptyPlace(),
    description: "",
  };
}

export interface PersonDraft {
  names: NameDraft[];
  profile_status: ProfileStatus;
  sex_at_birth: SexAtBirth | "";
  privacy_level: PrivacyLevel | "";
  occupation: string;
  birth: VitalDraft;
  death: VitalDraft;
  /** optional family branch to add the person to ("" = none) */
  branch_id: string;
}

export function emptyPersonDraft(uiLang = "en"): PersonDraft {
  return {
    names: [emptyName(true, uiLang === "hi" ? "hi" : "en", uiLang === "hi" ? "Deva" : "Latn")],
    profile_status: "unknown",
    sex_at_birth: "",
    privacy_level: "",
    occupation: "",
    birth: emptyVital(),
    death: emptyVital(),
    branch_id: "",
  };
}

/** A date counts as entered once any part (or the original text) is filled in. */
export function hasDate(d: GenealogicalDate) {
  return d.year != null || d.month != null || d.day != null || d.end_year != null || !!d.original_text?.trim();
}

export function vitalHasContent(v: VitalDraft, withTime: boolean): boolean {
  return (
    hasDate(v.date) ||
    (withTime && (!!v.time.value || v.time.precision !== "unknown")) ||
    !!v.place.place_id ||
    !!v.place.place_as_recorded.trim() ||
    !!v.description.trim()
  );
}

export function buildVital(v: VitalDraft, withTime: boolean): VitalIn {
  const out: VitalIn = {};
  if (hasDate(v.date)) out.date = normalizeDate(v.date);
  if (withTime && v.time.value) {
    out.time = { value: v.time.value, precision: v.time.precision, source: v.time.source };
    if (v.timezone_id) out.timezone_id = v.timezone_id;
  }
  if (v.place.place_id) out.place_id = v.place.place_id;
  if (v.place.place_as_recorded.trim()) out.place_as_recorded = v.place.place_as_recorded.trim();
  if (v.description.trim()) out.description = v.description.trim();
  return out;
}

export interface PersonFormErrors {
  names?: string;
  birthDate?: boolean;
  birthTime?: boolean;
  deathDate?: boolean;
}

/** Client-side validation mirroring the API's rules. Returns an empty object when valid. */
export function validatePersonDraft(d: PersonDraft): PersonFormErrors {
  const e: PersonFormErrors = {};
  if (!d.names.some(nameHasContent)) e.names = "person.err.nameRequired";
  if (hasDate(d.birth.date) && Object.keys(validateDate(d.birth.date)).length) e.birthDate = true;
  if (d.birth.time.value || d.birth.time.precision !== "unknown") if (validateTime(d.birth.time)) e.birthTime = true;
  if (d.profile_status === "deceased" && hasDate(d.death.date) && Object.keys(validateDate(d.death.date)).length) e.deathDate = true;
  return e;
}

export function buildPersonCreate(d: PersonDraft): PersonCreate {
  const names = d.names.filter(nameHasContent).map(cleanName);
  if (!names.some((n) => n.is_preferred) && names.length) names[0] = { ...names[0], is_preferred: true };
  const body: PersonCreate = {
    names,
    profile_status: d.profile_status,
  };
  if (d.sex_at_birth) body.sex_at_birth = d.sex_at_birth;
  if (d.privacy_level) body.privacy_level = d.privacy_level;
  if (d.occupation.trim()) body.occupation = d.occupation.trim();
  if (vitalHasContent(d.birth, true)) body.birth = buildVital(d.birth, true);
  if (d.profile_status === "deceased" && vitalHasContent(d.death, false)) body.death = buildVital(d.death, false);
  if (d.branch_id) body.branch_ids = [d.branch_id];
  return body;
}

/**
 * The ancestral village recorded on a branch's heritage profile, offered (never filled) as the
 * birth place of someone added to that branch (ADR-0019 §8). Only a village linked to a tree place
 * is offered; accepting it is the user's own choice for this person.
 */
function useAncestralVillage(treeId: string, branchId: string, branchName: string | undefined): PlaceSuggestion | null {
  const { t } = useTranslation();
  const heritage = useHeritage(treeId, { kind: "branch", id: branchId }, !!branchId);
  if (!branchId) return null;
  const a = heritage.data?.attributes.find((x) => x.attribute === "ancestral_village")?.preferred;
  if (!a?.place_id) return null;
  const label = a.place_name ?? a.value_text ?? "";
  return { place_id: a.place_id, place_label: label, reason: t("lgd.ancestral.offer", { branch: branchName ?? "" }) };
}

/** Full new-person form: names, status, sex, privacy, birth details and (if deceased) death details. */
export function PersonForm({
  treeId,
  draft,
  onChange,
  showErrors,
  compact = false,
  headingLevel = 3,
  treeDefaultPrivacy,
}: {
  treeId: string;
  draft: PersonDraft;
  onChange: (d: PersonDraft) => void;
  showErrors: boolean;
  compact?: boolean;
  /** 2 when the form sits directly under a page h1; 3 inside a dialog (whose title is an h2). */
  headingLevel?: 2 | 3;
  treeDefaultPrivacy?: PrivacyLevel;
}) {
  const { t } = useTranslation();
  const H = headingLevel === 2 ? "h2" : "h3";
  const [birthOpen, setBirthOpen] = useState(!compact);
  const errors = showErrors ? validatePersonDraft(draft) : {};
  const set = (patch: Partial<PersonDraft>) => onChange({ ...draft, ...patch });
  const branches = useBranches(treeId);
  const branchList = Array.isArray(branches.data) ? branches.data : [];
  const ancestral = useAncestralVillage(treeId, draft.branch_id, branchList.find((b) => b.id === draft.branch_id)?.name);

  const setName = (i: number, n: NameDraft) => {
    let names = draft.names.map((x, j) => (j === i ? n : x));
    if (n.is_preferred && !draft.names[i].is_preferred) names = names.map((x, j) => (j === i ? x : { ...x, is_preferred: false }));
    set({ names });
  };

  return (
    <div className="space-y-5">
      <section aria-labelledby="pf-names" className="space-y-3">
        <H id="pf-names" className="font-display text-base font-semibold">
          {t("person.form.names")}
        </H>
        <p className="text-xs text-ink-muted">{t("person.form.namesHint")}</p>
        {draft.names.map((n, i) => (
          <NameFields
            key={i}
            index={i}
            value={n}
            onChange={(v) => setName(i, v)}
            onRemove={draft.names.length > 1 ? () => set({ names: draft.names.filter((_, j) => j !== i).map((x, j, arr) => (arr.some((y) => y.is_preferred) ? x : { ...x, is_preferred: j === 0 })) }) : undefined}
            error={i === 0 && errors.names ? t(errors.names) : null}
            onAddName={(extra) => set({ names: [...draft.names, extra] })}
          />
        ))}
        <Button
          variant="secondary"
          size="sm"
          icon={<Plus className="size-4" aria-hidden />}
          onClick={() => set({ names: [...draft.names, { ...emptyName(false, "hi", "Deva"), type: "transliteration" }] })}
        >
          {t("names.addAnother")}
        </Button>
      </section>

      <section aria-labelledby="pf-basic" className="grid grid-cols-1 gap-3 sm:grid-cols-2">
        <H id="pf-basic" className="font-display text-base font-semibold sm:col-span-2">
          {t("person.form.basics")}
        </H>
        <Field label={t("person.status")}>
          {(p) => (
            <Select {...p} value={draft.profile_status} onChange={(e) => set({ profile_status: e.target.value as ProfileStatus })}>
              {STATUSES.map((s) => (
                <option key={s} value={s}>
                  {t(`enum.profileStatus.${s}`)}
                </option>
              ))}
            </Select>
          )}
        </Field>
        <Field label={t("person.sexAtBirth")} hint={t("person.sexHint")}>
          {(p) => (
            <Select {...p} value={draft.sex_at_birth} onChange={(e) => set({ sex_at_birth: e.target.value as SexAtBirth | "" })}>
              <option value="">{t("person.notRecorded")}</option>
              {SEXES.map((s) => (
                <option key={s} value={s}>
                  {t(`enum.sex.${s}`)}
                </option>
              ))}
            </Select>
          )}
        </Field>
        <Field label={t("privacy.level")} hint={draft.privacy_level ? t(`enum.privacyHint.${draft.privacy_level}`) : t("privacy.treeDefaultHint")}>
          {(p) => (
            <Select {...p} value={draft.privacy_level} onChange={(e) => set({ privacy_level: e.target.value as PrivacyLevel | "" })}>
              <option value="">
                {t("privacy.treeDefault")}
                {treeDefaultPrivacy ? ` (${t(`enum.privacy.${treeDefaultPrivacy}`)})` : ""}
              </option>
              {PRIVACY_LEVELS.map((l) => (
                <option key={l} value={l}>
                  {t(`enum.privacy.${l}`)}
                </option>
              ))}
            </Select>
          )}
        </Field>
        {branchList.length > 0 && (
          <Field label={t("person.form.branch")} hint={t("person.form.branchHint")}>
            {(p) => (
              <Select {...p} value={draft.branch_id} onChange={(e) => set({ branch_id: e.target.value })}>
                <option value="">{t("common.none")}</option>
                {branchList.map((b) => (
                  <option key={b.id} value={b.id}>
                    {b.name}
                  </option>
                ))}
              </Select>
            )}
          </Field>
        )}
        {/* suggestions only: occupation stays free text (ADR-0018 §6) */}
        <SmartSelect vocabulary="occupation" linkable={false} label={t("person.occupation")} text={draft.occupation} onChange={(v) => set({ occupation: v })} />
        {draft.profile_status !== "deceased" && <p className="text-xs text-ink-muted sm:col-span-2">{t("person.form.livingNotice")}</p>}
      </section>

      <section aria-labelledby="pf-birth" className="space-y-3">
        <H id="pf-birth" className="font-display text-base font-semibold">
          <button type="button" className="inline-flex items-center gap-1" aria-expanded={birthOpen} onClick={() => setBirthOpen(!birthOpen)}>
            {birthOpen ? <ChevronDown className="size-4" aria-hidden /> : <ChevronRight className="size-4" aria-hidden />}
            {t("person.form.birthDetails")}
          </button>
        </H>
        {birthOpen && (
          <VitalFields treeId={treeId} value={draft.birth} onChange={(birth) => set({ birth })} withTime showErrors={showErrors} kind="birth" suggestion={ancestral} />
        )}
      </section>

      {draft.profile_status === "deceased" && (
        <section aria-labelledby="pf-death" className="space-y-3">
          <H id="pf-death" className="font-display text-base font-semibold">
            {t("person.form.deathDetails")}
          </H>
          <VitalFields treeId={treeId} value={draft.death} onChange={(death) => set({ death })} withTime={false} showErrors={showErrors} kind="death" />
        </section>
      )}
    </div>
  );
}

export function VitalFields({
  treeId,
  value,
  onChange,
  withTime,
  showErrors,
  kind,
  suggestion,
}: {
  treeId: string;
  suggestion?: PlaceSuggestion | null;
  value: VitalDraft;
  onChange: (v: VitalDraft) => void;
  withTime: boolean;
  showErrors: boolean;
  kind: "birth" | "death" | "event";
}) {
  const { t } = useTranslation();
  const set = (patch: Partial<VitalDraft>) => onChange({ ...value, ...patch });
  return (
    <div className="space-y-3">
      <GenealogicalDateEditor
        legend={t(`person.form.${kind}Date`)}
        value={value.date}
        onChange={(date) => set({ date })}
        showErrors={showErrors && hasDate(value.date)}
      />
      {withTime && (
        <div className="grid grid-cols-1 gap-3 lg:grid-cols-3">
          <div className="lg:col-span-2">
            <TimeEditor legend={t("person.form.birthTime")} value={value.time} onChange={(time) => set({ time })} showErrors={showErrors} />
          </div>
          <TimezoneSelect value={value.timezone_id} onChange={(timezone_id) => set({ timezone_id })} />
        </div>
      )}
      <PlacePicker treeId={treeId} label={t(`person.form.${kind}Place`)} value={value.place} onChange={(place) => set({ place })} suggestion={suggestion} />
    </div>
  );
}
