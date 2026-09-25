import { useId } from "react";
import { useTranslation } from "react-i18next";
import type { HolderType, PersonSummary } from "../../api/types";
import { useBranches } from "../../api/hooks/family";
import { useTreeCtx } from "../../lib/tree-context";
import { parseShare, percent } from "../../lib/fractions";
import { PersonPicker } from "../pickers";
import { Field, Select, TextInput } from "../ui/form";

/** Exact share entry as "a/b" (e.g. 1/3). Shows the reduced value and a display-only percentage. */
export function ShareInput({ value, onChange, label, showErrors = false }: { value: string; onChange: (v: string) => void; label: string; showErrors?: boolean }) {
  const { t } = useTranslation();
  const id = useId();
  const parsed = parseShare(value);
  const err = !parsed.ok && (showErrors || value.trim() !== "") ? t(parsed.error) : null;
  return (
    <div>
      <label htmlFor={id} className="label">
        {label}
      </label>
      <input
        id={id}
        className="input font-mono"
        inputMode="numeric"
        placeholder="1/3"
        value={value}
        aria-invalid={err ? true : undefined}
        aria-describedby={`${id}-hint`}
        onChange={(e) => onChange(e.target.value)}
      />
      <p id={`${id}-hint`} className={err ? "field-error" : "hint"} aria-live="polite">
        {err ?? (parsed.ok ? t("share.preview", { value: `${parsed.value.num}/${parsed.value.den}`, pct: percent(parsed.value) }) : t("share.hint"))}
      </p>
    </div>
  );
}

export interface HolderDraft {
  holder_type: HolderType;
  person: PersonSummary | null;
  branch_id: string;
  name: string;
}

export const emptyHolder = (): HolderDraft => ({ holder_type: "person", person: null, branch_id: "", name: "" });

export function holderValid(h: HolderDraft): boolean {
  if (h.holder_type === "person") return !!h.person;
  if (h.holder_type === "family_branch") return !!h.branch_id;
  if (h.holder_type === "trust" || h.holder_type === "entity") return !!h.name.trim();
  return true;
}

export function holderPayload(h: HolderDraft) {
  return {
    holder_type: h.holder_type,
    holder_person_id: h.holder_type === "person" ? (h.person?.id ?? null) : null,
    holder_branch_id: h.holder_type === "family_branch" ? h.branch_id || null : null,
    holder_name: h.holder_type !== "person" && h.holder_type !== "family_branch" ? h.name.trim() || null : null,
  };
}

const HOLDER_TYPES: HolderType[] = ["person", "family_branch", "trust", "entity", "unknown"];

/** Who holds an interest: a person in the tree, a family branch (joint holding), or a named trust/entity. */
export function HolderPicker({ value, onChange, legend }: { value: HolderDraft; onChange: (h: HolderDraft) => void; legend: string }) {
  const { t } = useTranslation();
  const { treeId } = useTreeCtx();
  const branches = useBranches(treeId);
  return (
    <fieldset className="grid grid-cols-1 gap-2 sm:grid-cols-[12rem_1fr]">
      <legend className="sr-only">{legend}</legend>
      <Field label={t("property.holderType")}>
        {(p) => (
          <Select {...p} value={value.holder_type} onChange={(e) => onChange({ ...emptyHolder(), holder_type: e.target.value as HolderType })}>
            {HOLDER_TYPES.map((h) => (
              <option key={h} value={h}>
                {t(`enum.holderType.${h}`)}
              </option>
            ))}
          </Select>
        )}
      </Field>
      {value.holder_type === "person" && <PersonPicker treeId={treeId} label={legend} value={value.person} onChange={(person) => onChange({ ...value, person })} />}
      {value.holder_type === "family_branch" && (
        <Field label={legend}>
          {(p) => (
            <Select {...p} value={value.branch_id} onChange={(e) => onChange({ ...value, branch_id: e.target.value })}>
              <option value="">—</option>
              {branches.data?.map((b) => (
                <option key={b.id} value={b.id}>
                  {b.name}
                </option>
              ))}
            </Select>
          )}
        </Field>
      )}
      {(value.holder_type === "trust" || value.holder_type === "entity" || value.holder_type === "unknown") && (
        <Field label={t("property.holderName")}>{(p) => <TextInput {...p} value={value.name} onChange={(e) => onChange({ ...value, name: e.target.value })} />}</Field>
      )}
    </fieldset>
  );
}
