import { useId, useState } from "react";
import { useTranslation } from "react-i18next";
import { ChevronDown, ChevronRight, Star, Trash2 } from "lucide-react";
import type { EvidenceStatus, NameIn, NameType } from "../../api/types";
import { SCRIPTS, detectScript, isRtl } from "../../lib/names";
import { Field, Select, TextInput } from "../ui/form";
import { SmartSelect } from "../ui/SmartSelect";
import { TransliterationSuggestion } from "./TransliterationSuggestion";

export const NAME_TYPES: NameType[] = ["birth", "married", "alias", "religious", "professional", "nickname", "transliteration", "historical"];
export const EVIDENCE_STATUSES: EvidenceStatus[] = [
  "USER_ASSERTION",
  "FAMILY_RECOLLECTION",
  "SOURCED",
  "CORROBORATED",
  "DISPUTED",
  "SUPERSEDED",
  "DISPROVEN",
];

export type NameDraft = NameIn;

export function emptyName(preferred = false, language = "en", script = "Latn"): NameDraft {
  return { type: "birth", given_name: "", surname: "", language, script, is_preferred: preferred, evidence_status: "USER_ASSERTION" };
}

export function nameHasContent(n: NameDraft): boolean {
  return [n.given_name, n.surname, n.full_name_as_recorded, n.middle_names, n.patronymic, n.family_house_name].some((v) => !!v && v.trim());
}

/** Strip empty strings so the API receives nulls rather than "" for optional parts. */
export function cleanName(n: NameDraft): NameIn {
  const out: Record<string, unknown> = {};
  for (const [k, v] of Object.entries(n)) {
    if (typeof v === "string") {
      const s = v.trim();
      if (s) out[k] = s;
    } else if (v !== undefined && v !== null) out[k] = v;
  }
  return out as NameIn;
}

/** One name record: type, parts, language/script (with native-script input), preferred flag. */
export function NameFields({
  value,
  onChange,
  onRemove,
  index,
  error,
  onAddName,
}: {
  value: NameDraft;
  onChange: (n: NameDraft) => void;
  onRemove?: () => void;
  index: number;
  error?: string | null;
  /** When given, offers the name in the other script as a separate name (ADR-0025). */
  onAddName?: (n: NameDraft) => void;
}) {
  const { t } = useTranslation();
  const [more, setMore] = useState(false);
  // The "a name needs a given name or surname" error belongs to both inputs (WCAG 3.3.1 / 1.3.1).
  const errId = useId();
  const withNameError = (p: { "aria-describedby"?: string; "aria-invalid"?: boolean }) =>
    error ? { "aria-invalid": true, "aria-describedby": [p["aria-describedby"], errId].filter(Boolean).join(" ") } : {};
  const lang = value.language ?? undefined;
  const dir = isRtl(value.script) ? "rtl" : undefined;
  const set = (patch: Partial<NameDraft>) => onChange({ ...value, ...patch });

  /** When the user types in an Indic script, suggest that script (only if still Latin/default). */
  const onTextInput = (patch: Partial<NameDraft>, text: string) => {
    const det = detectScript(text);
    if (det && det.script !== "Latn" && (value.script ?? "Latn") === "Latn") {
      set({ ...patch, script: det.script, language: det.language });
    } else set(patch);
  };

  const scriptValue = `${value.language ?? ""}|${value.script ?? ""}`;
  const knownScript = SCRIPTS.some((s) => `${s.language}|${s.script}` === scriptValue);

  return (
    <div className="rounded-lg border border-stone-300 bg-parchment/50 p-3" role="group" aria-label={t("names.recordN", { n: index + 1 })}>
      <div className="mb-2 flex flex-wrap items-center justify-between gap-2">
        <p className="text-sm font-semibold">
          {t("names.recordN", { n: index + 1 })}
          {value.is_preferred && (
            <span className="ml-2 inline-flex items-center gap-1 text-xs font-medium text-haldi-700">
              <Star className="size-3 fill-current" aria-hidden /> {t("names.preferred")}
            </span>
          )}
        </p>
        <div className="flex items-center gap-2">
          {!value.is_preferred && (
            <button type="button" className="text-xs font-medium text-kumkum-800 underline" onClick={() => set({ is_preferred: true })}>
              {t("names.makePreferred")}
            </button>
          )}
          {onRemove && (
            <button type="button" onClick={onRemove} className="rounded p-1 text-red-800 hover:bg-red-50" aria-label={t("names.remove", { n: index + 1 })}>
              <Trash2 className="size-4" aria-hidden />
            </button>
          )}
        </div>
      </div>
      <div className="grid grid-cols-1 gap-3 sm:grid-cols-3">
        <Field label={t("names.type")}>
          {(p) => (
            <Select {...p} value={value.type ?? "birth"} onChange={(e) => set({ type: e.target.value as NameType })}>
              {NAME_TYPES.map((nt) => (
                <option key={nt} value={nt}>
                  {t(`enum.nameType.${nt}`)}
                </option>
              ))}
            </Select>
          )}
        </Field>
        <Field label={t("names.script")} hint={t("names.scriptHint")}>
          {(p) => (
            <Select
              {...p}
              value={scriptValue}
              onChange={(e) => {
                const [language, script] = e.target.value.split("|");
                set({ language: language || null, script: script || null });
              }}
            >
              {!knownScript && <option value={scriptValue}>{`${value.language ?? "?"} / ${value.script ?? "?"}`}</option>}
              {SCRIPTS.map((s) => (
                <option key={`${s.language}|${s.script}`} value={`${s.language}|${s.script}`}>
                  {s.label}
                </option>
              ))}
            </Select>
          )}
        </Field>
        <Field label={t("names.evidence")}>
          {(p) => (
            <Select {...p} value={value.evidence_status ?? "USER_ASSERTION"} onChange={(e) => set({ evidence_status: e.target.value as EvidenceStatus })}>
              {EVIDENCE_STATUSES.map((s) => (
                <option key={s} value={s}>
                  {t(`enum.evidence.${s}`)}
                </option>
              ))}
            </Select>
          )}
        </Field>
        <Field label={t("names.given")}>
          {(p) => <TextInput {...p} {...withNameError(p)} lang={lang} dir={dir} value={value.given_name ?? ""} onChange={(e) => onTextInput({ given_name: e.target.value }, e.target.value)} />}
        </Field>
        <Field label={t("names.middle")}>
          {(p) => <TextInput {...p} lang={lang} dir={dir} value={value.middle_names ?? ""} onChange={(e) => onTextInput({ middle_names: e.target.value }, e.target.value)} />}
        </Field>
        <Field label={t("names.surname")}>
          {(p) => <TextInput {...p} {...withNameError(p)} lang={lang} dir={dir} value={value.surname ?? ""} onChange={(e) => onTextInput({ surname: e.target.value }, e.target.value)} />}
        </Field>
        <Field label={t("names.fullAsRecorded")} hint={t("names.fullAsRecordedHint")} className="sm:col-span-2">
          {(p) => (
            <TextInput {...p} lang={lang} dir={dir} value={value.full_name_as_recorded ?? ""} onChange={(e) => onTextInput({ full_name_as_recorded: e.target.value }, e.target.value)} />
          )}
        </Field>
        <Field label={t("names.romanized")} hint={t("names.romanizedHint")}>
          {(p) => <TextInput {...p} lang="en" value={value.romanized_value ?? ""} onChange={(e) => set({ romanized_value: e.target.value })} />}
        </Field>
      </div>
      {onAddName && !value.suggestion && <TransliterationSuggestion name={value} onAdd={onAddName} />}
      {value.suggestion && <p className="mt-2 text-xs text-ink-muted">{t("translit.suggestedConfirmed")}</p>}
      <button type="button" className="mt-3 inline-flex items-center gap-1 text-xs font-medium text-kumkum-800" aria-expanded={more} onClick={() => setMore(!more)}>
        {more ? <ChevronDown className="size-3.5" aria-hidden /> : <ChevronRight className="size-3.5" aria-hidden />}
        {t("names.moreParts")}
      </button>
      {more && (
        <div className="mt-3 grid grid-cols-1 gap-3 sm:grid-cols-3">
          {(
            [
              ["patronymic", "names.patronymic"],
              ["matronymic", "names.matronymic"],
              ["family_house_name", "names.familyHouse"],
              ["village_prefix", "names.villagePrefix"],
              ["honorific_prefix", "names.honorificPrefix"],
              ["honorific_suffix", "names.honorificSuffix"],
            ] as const
          ).map(([k, label]) =>
            k === "honorific_prefix" ? (
              <SmartSelect
                key={k}
                vocabulary="honorific"
                linkable={false}
                label={t(label)}
                lang={lang}
                dir={dir}
                text={value.honorific_prefix ?? ""}
                onChange={(v) => onTextInput({ honorific_prefix: v }, v)}
              />
            ) : (
            <Field key={k} label={t(label)}>
              {(p) => <TextInput {...p} lang={lang} dir={dir} value={(value[k] as string | null | undefined) ?? ""} onChange={(e) => onTextInput({ [k]: e.target.value }, e.target.value)} />}
            </Field>
            ),
          )}
        </div>
      )}
      {error && (
        <p id={errId} className="field-error" role="alert">
          {error}
        </p>
      )}
    </div>
  );
}
