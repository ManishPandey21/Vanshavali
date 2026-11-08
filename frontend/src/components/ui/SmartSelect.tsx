import { useContext, useMemo, type ReactNode } from "react";
import { useTranslation } from "react-i18next";
import { Link2, Plus } from "lucide-react";
import type { VocabularyTerm } from "../../api/types";
import { useAddVocabularyTerm, useVocabulary } from "../../api/hooks/vocabularies";
import { TreeContext } from "../../lib/tree-context";
import { Perm } from "../../lib/permissions";
import { useDebounced } from "../../lib/useDebounced";
import { Combobox, type ComboOption } from "./Combobox";
import { Field, TextInput } from "./form";
import { Badge } from "./Badge";

/** A value chosen from a vocabulary; stored next to the label as typed (ADR-0018 §6). */
export interface VocabRef {
  vocabulary: string;
  code: string;
}

type Choice = { kind: "term"; term: VocabularyTerm } | { kind: "add" };

const fold = (s: string) => s.normalize("NFKC").trim().toLocaleLowerCase();

/**
 * Text field with suggestions from a master-data vocabulary (ADR-0018). The text is always the
 * value: suggestions only help typing, and "Add as our family's own" saves a family entry for
 * reuse. Nothing is ever filled in automatically. If the vocabulary service is unavailable, the
 * field becomes a plain text input: no static list is kept (ADR-0026 §8).
 */
export function SmartSelect({
  vocabulary,
  label,
  hint,
  text,
  onChange,
  lang,
  dir,
  linkable = true,
}: {
  vocabulary: string;
  label: ReactNode;
  hint?: ReactNode;
  text: string;
  /** `ref` is set when the text came from a list entry, and cleared as soon as the user types. */
  onChange: (text: string, ref: VocabRef | null) => void;
  lang?: string;
  dir?: "rtl";
  /** false = suggestions only; the caller stores text and never a reference (e.g. occupation). */
  linkable?: boolean;
}) {
  const { t, i18n } = useTranslation();
  const tree = useContext(TreeContext);
  const treeId = tree?.treeId ?? null;
  const uiLang = i18n.language.startsWith("hi") ? "hi" : "en";
  const q = useDebounced(text.trim(), 200);
  const terms = useVocabulary(treeId, vocabulary, q, uiLang);
  const add = useAddVocabularyTerm(treeId ?? "", vocabulary);
  // anything but a well-formed answer (switched off, offline, unexpected body) means: plain field
  const usable = !terms.isError && (terms.isPending || (Array.isArray(terms.data?.items) && !!terms.data?.vocabulary));
  const canAdd = !!treeId && !!tree?.can(Perm.PERSON_WRITE) && !!terms.data?.vocabulary?.allows_custom;

  const options = useMemo<ComboOption<Choice>[]>(() => {
    const items = Array.isArray(terms.data?.items) ? terms.data.items : [];
    const opts: ComboOption<Choice>[] = items.map((term) => ({
      key: `${term.origin}:${term.code}`,
      value: { kind: "term", term },
      textValue: term.label,
      label: (
        <span className="flex flex-wrap items-center gap-2">
          <span lang={term.origin === "family" ? undefined : uiLang}>{term.label}</span>
          {term.origin === "global" && uiLang !== "en" && term.labels.en && term.labels.en !== term.label && (
            <span className="text-xs text-ink-muted">{term.labels.en}</span>
          )}
          {term.origin === "global" && uiLang === "en" && term.labels.hi && (
            <span className="text-xs text-ink-muted" lang="hi">
              {term.labels.hi}
            </span>
          )}
          {term.origin === "family" && <Badge tone="saffron">{t("smartSelect.family")}</Badge>}
        </span>
      ),
    }));
    const typed = text.trim();
    const exact = items.some((x) => [x.label, ...Object.values(x.labels), ...(x.aliases ?? [])].some((l) => fold(l) === fold(typed)));
    if (canAdd && typed && !exact) {
      opts.push({
        key: "add",
        value: { kind: "add" },
        textValue: typed,
        label: (
          <span className="flex items-center gap-2 font-medium text-kumkum-800">
            <Plus className="size-4" aria-hidden />
            {t("smartSelect.addOwn", { text: typed })}
          </span>
        ),
      });
    }
    return opts;
  }, [terms.data, text, canAdd, uiLang, t]);

  if (!usable) {
    // service switched off or unreachable: a plain field, as before the master-data service
    return (
      <Field label={label} hint={hint}>
        {(p) => (
          <TextInput {...p} lang={lang} dir={dir} value={text} onChange={(e) => onChange(e.target.value, null)} />
        )}
      </Field>
    );
  }

  const select = (c: Choice) => {
    const typed = text.trim();
    if (c.kind === "term") {
      onChange(c.term.label, linkable ? { vocabulary, code: c.term.code } : null);
      return;
    }
    // keep the spelling the user typed; link it to the (new or matching) family entry
    add.mutate({ label: typed }, { onSuccess: (r) => onChange(typed, linkable ? { vocabulary, code: r.term.code } : null) });
  };

  return (
    <div>
      <Combobox
        label={label}
        hint={hint}
        text={text}
        onTextChange={(s) => onChange(s, null)}
        options={options}
        onSelect={select}
        loading={terms.isFetching || add.isPending}
        inputProps={{ lang }}
      />
      {add.isError && (
        <p role="alert" className="field-error text-sm">
          {t("smartSelect.addFailed")}
        </p>
      )}
    </div>
  );
}

/** Small note shown next to a value that is linked to a list entry. */
export function LinkedNote() {
  const { t } = useTranslation();
  return (
    <p className="mt-1 flex items-center gap-1 text-xs text-ink-muted">
      <Link2 className="size-3" aria-hidden />
      {t("smartSelect.linked")}
    </p>
  );
}
