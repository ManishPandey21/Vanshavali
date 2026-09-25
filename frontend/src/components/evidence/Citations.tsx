import { useState, type FormEvent } from "react";
import { useTranslation } from "react-i18next";
import { BookOpen, Plus, Trash2 } from "lucide-react";
import type { CitationTarget, Confidence, SourceOut, SourceType } from "../../api/types";
import { useAddCitation, useCitations, useCreateSource, useDeleteCitation, useSources } from "../../api/hooks/heritage";
import { useTreeCtx } from "../../lib/tree-context";
import { Perm } from "../../lib/permissions";
import { useDebounced } from "../../lib/useDebounced";
import { Button } from "../ui/Button";
import { Dialog } from "../ui/Dialog";
import { ErrorAlert, Spinner } from "../ui/feedback";
import { Combobox } from "../ui/Combobox";
import { Field, Select, TextArea, TextInput } from "../ui/form";
import { Badge } from "../ui/Badge";

export const SOURCE_TYPES: SourceType[] = [
  "civil_record",
  "certificate",
  "kundli",
  "traditional_register",
  "family_book",
  "oral_history",
  "land_record",
  "deed",
  "court_record",
  "census",
  "letter",
  "photograph",
  "publication",
  "website",
  "gedcom_import",
  "other",
];
const CONFIDENCES: Confidence[] = ["high", "medium", "low", "unknown"];

export function CitationList({ targetType, targetId }: { targetType: CitationTarget; targetId: string }) {
  const { t } = useTranslation();
  const { treeId, can } = useTreeCtx();
  const cites = useCitations(treeId, targetType, targetId);
  const del = useDeleteCitation(treeId);
  const [adding, setAdding] = useState(false);
  return (
    <div className="mt-2 rounded-lg bg-parchment p-3">
      <div className="flex items-center justify-between">
        <p className="text-xs font-semibold uppercase tracking-wide text-ink-muted">{t("citations.title")}</p>
        {can(Perm.SOURCE_WRITE) && (
          <Button size="sm" variant="ghost" icon={<Plus className="size-3.5" aria-hidden />} onClick={() => setAdding(true)}>
            {t("citations.add")}
          </Button>
        )}
      </div>
      {cites.isLoading && <Spinner />}
      <ErrorAlert error={cites.error || del.error} />
      {cites.data && cites.data.length === 0 && <p className="text-xs text-ink-muted">{t("citations.none")}</p>}
      <ul className="space-y-1">
        {cites.data?.map((c) => (
          <li key={c.id} className="flex items-start justify-between gap-2 text-sm">
            <span>
              <BookOpen className="mr-1 inline size-3.5 text-haldi-700" aria-hidden />
              <span className="font-medium">{c.source_title ?? t("citations.untitled")}</span>
              {c.page_or_image && <span className="text-ink-muted"> · {c.page_or_image}</span>}
              {c.confidence && c.confidence !== "unknown" && (
                <span className="ml-1">
                  <Badge tone="stone">{t(`enum.confidence.${c.confidence}`)}</Badge>
                </span>
              )}
              {c.text_excerpt && <span className="block text-xs italic text-ink-muted">“{c.text_excerpt}”</span>}
            </span>
            {can(Perm.SOURCE_WRITE) && (
              <button type="button" className="rounded p-1 text-red-800 hover:bg-red-50" onClick={() => del.mutate(c.id)} aria-label={t("citations.remove", { title: c.source_title ?? "" })}>
                <Trash2 className="size-3.5" aria-hidden />
              </button>
            )}
          </li>
        ))}
      </ul>
      {adding && <AddCitationDialog targetType={targetType} targetId={targetId} onClose={() => setAdding(false)} />}
    </div>
  );
}

export function AddCitationDialog({ targetType, targetId, onClose }: { targetType: CitationTarget; targetId: string; onClose: () => void }) {
  const { t } = useTranslation();
  const { treeId } = useTreeCtx();
  const [text, setText] = useState("");
  const q = useDebounced(text.trim(), 250);
  const sources = useSources(treeId, q);
  const [source, setSource] = useState<SourceOut | null>(null);
  const [newSource, setNewSource] = useState<{ title: string; type: SourceType } | null>(null);
  const [page, setPage] = useState("");
  const [excerpt, setExcerpt] = useState("");
  const [confidence, setConfidence] = useState<Confidence>("unknown");
  const [err, setErr] = useState<string | null>(null);
  const add = useAddCitation(treeId);
  const createSource = useCreateSource(treeId);
  const options = (sources.data?.pages.flatMap((p) => p.items) ?? []).slice(0, 15).map((s) => ({
    key: s.id,
    value: s,
    textValue: s.title,
    label: (
      <span className="flex justify-between gap-2">
        <span>{s.title}</span>
        <span className="text-xs text-ink-muted">{t(`enum.sourceType.${s.source_type}`)}</span>
      </span>
    ),
  }));

  const submit = async (e: FormEvent) => {
    e.preventDefault();
    let src = source;
    if (!src && newSource?.title.trim()) {
      try {
        src = await createSource.mutateAsync({ title: newSource.title.trim(), source_type: newSource.type });
      } catch {
        return;
      }
    }
    if (!src) {
      setErr(t("citations.pickSource"));
      return;
    }
    setErr(null);
    add.mutate(
      {
        source_id: src.id,
        target_type: targetType,
        target_id: targetId,
        page_or_image: page.trim() || null,
        text_excerpt: excerpt.trim() || null,
        confidence,
      },
      { onSuccess: onClose },
    );
  };

  return (
    <Dialog
      open
      onClose={onClose}
      title={t("citations.addTitle")}
      footer={
        <>
          <Button variant="secondary" onClick={onClose}>
            {t("common.cancel")}
          </Button>
          <Button type="submit" form="cite-form" loading={add.isPending || createSource.isPending}>
            {t("citations.add")}
          </Button>
        </>
      }
    >
      <form id="cite-form" onSubmit={(e) => void submit(e)} className="space-y-3" noValidate>
        {source ? (
          <div className="flex items-center justify-between rounded-lg border border-kumkum-200 bg-kumkum-50 px-3 py-2 text-sm">
            <span className="font-medium">{source.title}</span>
            <button type="button" className="text-xs underline" onClick={() => setSource(null)}>
              {t("common.change")}
            </button>
          </div>
        ) : newSource ? (
          <div className="grid grid-cols-1 gap-3 rounded-lg border border-stone-300 p-3 sm:grid-cols-2">
            <Field label={t("sources.titleField")} required>
              {(p) => <TextInput {...p} value={newSource.title} onChange={(e) => setNewSource({ ...newSource, title: e.target.value })} />}
            </Field>
            <Field label={t("sources.type")}>
              {(p) => (
                <Select {...p} value={newSource.type} onChange={(e) => setNewSource({ ...newSource, type: e.target.value as SourceType })}>
                  {SOURCE_TYPES.map((s) => (
                    <option key={s} value={s}>
                      {t(`enum.sourceType.${s}`)}
                    </option>
                  ))}
                </Select>
              )}
            </Field>
            <button type="button" className="text-left text-xs text-kumkum-800 underline" onClick={() => setNewSource(null)}>
              {t("citations.pickExisting")}
            </button>
          </div>
        ) : (
          <>
            <Combobox label={t("citations.source")} text={text} onTextChange={setText} options={options} onSelect={setSource} loading={sources.isFetching} emptyText={t("citations.noSources")} />
            <button type="button" className="text-xs text-kumkum-800 underline" onClick={() => setNewSource({ title: text, type: "other" })}>
              {t("citations.newSource")}
            </button>
          </>
        )}
        <Field label={t("citations.page")}>{(p) => <TextInput {...p} value={page} onChange={(e) => setPage(e.target.value)} />}</Field>
        <Field label={t("citations.excerpt")}>{(p) => <TextArea {...p} rows={2} value={excerpt} onChange={(e) => setExcerpt(e.target.value)} />}</Field>
        <Field label={t("citations.confidence")}>
          {(p) => (
            <Select {...p} value={confidence} onChange={(e) => setConfidence(e.target.value as Confidence)}>
              {CONFIDENCES.map((c) => (
                <option key={c} value={c}>
                  {t(`enum.confidence.${c}`)}
                </option>
              ))}
            </Select>
          )}
        </Field>
        {err && (
          <p role="alert" className="field-error">
            {err}
          </p>
        )}
        <ErrorAlert error={add.error || createSource.error} />
      </form>
    </Dialog>
  );
}
