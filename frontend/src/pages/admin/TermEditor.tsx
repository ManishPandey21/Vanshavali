import { useEffect, useId, useMemo, useState, type FormEvent } from "react";
import { useTranslation } from "react-i18next";
import { AlertTriangle, Plus, Trash2 } from "lucide-react";
import { ApiError } from "../../api/client";
import { checkDuplicates, useProposeChange } from "../../api/hooks/masterDataAdmin";
import type { AdminTerm, ChangeIn, VocabularyDuplicate, MasterDataChange, TermFieldsIn } from "../../api/types";
import { Dialog } from "../../components/ui/Dialog";
import { Button } from "../../components/ui/Button";
import { Badge } from "../../components/ui/Badge";
import { ErrorAlert } from "../../components/ui/feedback";
import { Checkbox, Field, Select, TextArea, TextInput, focusFirstInvalid } from "../../components/ui/form";
import { useDebounced } from "../../lib/useDebounced";

const CODE_RE = /^[a-z0-9][a-z0-9_]{0,79}$/;
const LANG_RE = /^[a-z]{2,3}(-[A-Za-z]{2,4})?$/;

/** A code suggestion from the English label: lower case, ASCII, underscores. Always editable. */
export function suggestCode(label: string): string {
  return label
    .normalize("NFKD")
    .replace(/[^\x20-\x7e]/g, "")
    .toLowerCase()
    .replace(/[^a-z0-9]+/g, "_")
    .replace(/^_+|_+$/g, "")
    .slice(0, 60);
}

const lines = (s: string) =>
  s
    .split(/\n|,/)
    .map((x) => x.trim())
    .filter(Boolean);

interface ExtraLabel {
  lang: string;
  text: string;
}

/**
 * Create or edit one global term (ADR-0025). Every field is shown, a duplicate check runs while
 * typing, and the admin chooses "Save as draft" or "Publish". The server re-validates everything.
 */
export function TermEditorDialog({
  vocabulary,
  term,
  onClose,
  onDone,
}: {
  vocabulary: string;
  term: AdminTerm | null;
  onClose: () => void;
  onDone: (change: MasterDataChange) => void;
}) {
  const { t } = useTranslation();
  const formId = useId();
  const editing = term !== null;
  const [en, setEn] = useState(term?.labels.en ?? "");
  const [hi, setHi] = useState(term?.labels.hi ?? "");
  const [extra, setExtra] = useState<ExtraLabel[]>(
    Object.entries(term?.labels ?? {})
      .filter(([k]) => k !== "en" && k !== "hi")
      .map(([lang, text]) => ({ lang, text })),
  );
  const [code, setCode] = useState(term?.code ?? "");
  const [codeTouched, setCodeTouched] = useState(editing);
  const [aliases, setAliases] = useState((term?.aliases ?? []).join("\n"));
  const [scope, setScope] = useState((term?.scope ?? []).join(", "));
  const [sourceUrl, setSourceUrl] = useState(term?.source_url ?? "");
  const [status, setStatus] = useState<"draft" | "reviewed">(term?.status === "reviewed" ? "reviewed" : "draft");
  const [sortOrder, setSortOrder] = useState(String(term?.sort_order ?? 0));
  const [reason, setReason] = useState("");
  const [sourceRef, setSourceRef] = useState("");
  const [allowSimilar, setAllowSimilar] = useState(false);
  const [errors, setErrors] = useState<Record<string, string>>({});
  const [similar, setSimilar] = useState<VocabularyDuplicate[]>([]);
  const propose = useProposeChange(vocabulary);

  useEffect(() => {
    if (!codeTouched) setCode(suggestCode(en));
  }, [en, codeTouched]);

  // live duplicate check (same word in another spelling or script, retired terms included)
  const probe = useDebounced(JSON.stringify({ en, hi, aliases }), 400);
  useEffect(() => {
    const { en: e, hi: h, aliases: a } = JSON.parse(probe) as { en: string; hi: string; aliases: string };
    if (!e.trim() && !h.trim()) {
      setSimilar([]);
      return;
    }
    let live = true;
    checkDuplicates(vocabulary, { en: e, hi: h }, lines(a), term?.code)
      .then((r) => live && setSimilar(r))
      .catch(() => live && setSimilar([]));
    return () => {
      live = false;
    };
  }, [probe, vocabulary, term?.code]);

  const fields = useMemo<TermFieldsIn>(() => {
    const labels: Record<string, string> = { en: en.trim(), hi: hi.trim() };
    for (const x of extra) if (x.lang.trim() && x.text.trim()) labels[x.lang.trim()] = x.text.trim();
    return {
      labels,
      aliases: lines(aliases),
      scope: lines(scope),
      parent_code: term?.parent_code ?? null,
      attributes: (term?.attributes ?? {}) as TermFieldsIn["attributes"],
      source_url: sourceUrl.trim() || null,
      status,
      sort_order: Number.parseInt(sortOrder, 10) || 0,
    };
  }, [en, hi, extra, aliases, scope, sourceUrl, status, sortOrder, term]);

  const submit = (publish: boolean) => (e?: FormEvent) => {
    e?.preventDefault();
    const errs: Record<string, string> = {};
    if (!en.trim()) errs.en = t("common.required");
    if (!hi.trim()) errs.hi = t("common.required");
    if (!CODE_RE.test(code)) errs.code = t("mdAdmin.editor.codeInvalid");
    extra.forEach((x, i) => {
      if (x.text.trim() && !LANG_RE.test(x.lang.trim())) errs[`lang${i}`] = t("mdAdmin.editor.langInvalid");
    });
    if (sourceUrl.trim() && !/^https?:\/\//i.test(sourceUrl.trim())) errs.source = t("mdAdmin.editor.urlInvalid");
    if (reason.trim().length < 3) errs.reason = t("mdAdmin.editor.reasonRequired");
    setErrors(errs);
    if (Object.keys(errs).length) {
      focusFirstInvalid(document.getElementById(formId));
      return;
    }
    const body: ChangeIn = {
      action: editing ? "update" : "create",
      code,
      base_revision: editing ? term.revision : null,
      term: fields,
      reason: reason.trim(),
      source_reference: sourceRef.trim() || null,
      allow_similar: allowSimilar,
      publish,
      reactivate_as: "draft",
    };
    propose.mutate(body, { onSuccess: onDone });
  };

  const serverDupes =
    propose.error instanceof ApiError && propose.error.code === "possible_duplicate"
      ? ((propose.error.details as { matches?: VocabularyDuplicate[] })?.matches ?? [])
      : [];
  const shown = serverDupes.length ? serverDupes : similar;

  return (
    <Dialog
      open
      onClose={onClose}
      size="lg"
      title={editing ? t("mdAdmin.editor.editTitle", { code: term.code }) : t("mdAdmin.editor.newTitle")}
      description={t("mdAdmin.editor.description")}
      footer={
        <>
          <Button variant="secondary" onClick={onClose}>
            {t("common.cancel")}
          </Button>
          <Button variant="secondary" loading={propose.isPending} onClick={() => submit(false)()}>
            {t("mdAdmin.editor.saveDraft")}
          </Button>
          <Button loading={propose.isPending} onClick={() => submit(true)()}>
            {t("mdAdmin.editor.publish")}
          </Button>
        </>
      }
    >
      <form id={formId} className="grid gap-3 sm:grid-cols-2" onSubmit={submit(false)} noValidate>
        <Field label={t("mdAdmin.editor.labelEn")} required error={errors.en}>
          {(p) => <TextInput {...p} value={en} onChange={(e) => setEn(e.target.value)} maxLength={200} lang="en" />}
        </Field>
        <Field label={t("mdAdmin.editor.labelHi")} required error={errors.hi}>
          {(p) => <TextInput {...p} value={hi} onChange={(e) => setHi(e.target.value)} maxLength={200} lang="hi" />}
        </Field>
        <Field label={t("mdAdmin.editor.code")} hint={editing ? t("mdAdmin.editor.codeFixed") : t("mdAdmin.editor.codeHint")} error={errors.code}>
          {(p) => (
            <TextInput
              {...p}
              value={code}
              readOnly={editing}
              onChange={(e) => {
                setCodeTouched(true);
                setCode(e.target.value);
              }}
              className="font-mono"
              maxLength={80}
            />
          )}
        </Field>
        <Field label={t("mdAdmin.editor.status")} hint={t("mdAdmin.editor.statusHint")}>
          {(p) => (
            <Select {...p} value={status} onChange={(e) => setStatus(e.target.value as "draft" | "reviewed")}>
              <option value="draft">{t("mdAdmin.status.draft")}</option>
              <option value="reviewed">{t("mdAdmin.status.reviewed")}</option>
            </Select>
          )}
        </Field>

        <div className="sm:col-span-2">
          <p className="label">{t("mdAdmin.editor.otherLabels")}</p>
          <ul className="space-y-2">
            {extra.map((x, i) => (
              <li key={i} className="flex flex-wrap items-end gap-2">
                <Field label={t("mdAdmin.editor.langCode")} error={errors[`lang${i}`]} className="w-28">
                  {(p) => (
                    <TextInput
                      {...p}
                      value={x.lang}
                      placeholder="mr"
                      onChange={(e) => setExtra(extra.map((y, j) => (j === i ? { ...y, lang: e.target.value } : y)))}
                    />
                  )}
                </Field>
                <Field label={t("mdAdmin.editor.labelIn", { lang: x.lang || "…" })} className="min-w-0 flex-1">
                  {(p) => (
                    <TextInput
                      {...p}
                      value={x.text}
                      lang={x.lang || undefined}
                      maxLength={200}
                      onChange={(e) => setExtra(extra.map((y, j) => (j === i ? { ...y, text: e.target.value } : y)))}
                    />
                  )}
                </Field>
                <Button
                  variant="ghost"
                  size="sm"
                  icon={<Trash2 className="size-4" aria-hidden />}
                  onClick={() => setExtra(extra.filter((_, j) => j !== i))}
                >
                  <span className="sr-only">{t("mdAdmin.editor.removeLabel", { lang: x.lang || "…" })}</span>
                </Button>
              </li>
            ))}
          </ul>
          {extra.length < 10 && (
            <Button variant="ghost" size="sm" className="mt-1" icon={<Plus className="size-4" aria-hidden />} onClick={() => setExtra([...extra, { lang: "", text: "" }])}>
              {t("mdAdmin.editor.addLabel")}
            </Button>
          )}
        </div>

        <Field label={t("mdAdmin.editor.aliases")} hint={t("mdAdmin.editor.aliasesHint")} className="sm:col-span-2">
          {(p) => <TextArea {...p} value={aliases} onChange={(e) => setAliases(e.target.value)} rows={3} />}
        </Field>
        <Field label={t("mdAdmin.editor.scope")} hint={t("mdAdmin.editor.scopeHint")}>
          {(p) => <TextInput {...p} value={scope} onChange={(e) => setScope(e.target.value)} placeholder="maharashtra, smarta" />}
        </Field>
        <Field label={t("mdAdmin.editor.sortOrder")}>
          {(p) => <TextInput {...p} type="number" min={0} max={100000} value={sortOrder} onChange={(e) => setSortOrder(e.target.value)} />}
        </Field>
        <Field label={t("mdAdmin.editor.sourceUrl")} error={errors.source} className="sm:col-span-2">
          {(p) => <TextInput {...p} type="url" value={sourceUrl} onChange={(e) => setSourceUrl(e.target.value)} placeholder="https://" maxLength={500} />}
        </Field>

        {shown.length > 0 && (
          <div role="status" className="rounded-lg border border-haldi-300 bg-haldi-100/60 p-3 text-sm sm:col-span-2">
            <p className="flex items-center gap-1.5 font-semibold">
              <AlertTriangle className="size-4" aria-hidden />
              {t("mdAdmin.editor.similarTitle")}
            </p>
            <ul className="mt-1 list-disc pl-5">
              {shown.map((m) => (
                <li key={m.code}>
                  <span className="font-medium">{m.label}</span> <code className="text-xs">{m.code}</code>{" "}
                  {t("mdAdmin.editor.similarMatched", { text: m.matched })}{" "}
                  {m.status === "retired" && <Badge tone="stone">{t("mdAdmin.status.retired")}</Badge>}
                </li>
              ))}
            </ul>
            <p className="mt-1 text-xs text-ink-muted">{t("mdAdmin.editor.similarHint")}</p>
            <div className="mt-2">
              <Checkbox label={t("mdAdmin.editor.allowSimilar")} checked={allowSimilar} onChange={setAllowSimilar} />
            </div>
          </div>
        )}

        <Field label={t("mdAdmin.editor.reason")} required error={errors.reason} hint={t("mdAdmin.editor.reasonHint")} className="sm:col-span-2">
          {(p) => <TextArea {...p} value={reason} onChange={(e) => setReason(e.target.value)} rows={2} maxLength={2000} />}
        </Field>
        <Field label={t("mdAdmin.editor.sourceRef")} hint={t("mdAdmin.editor.sourceRefHint")} className="sm:col-span-2">
          {(p) => <TextInput {...p} value={sourceRef} onChange={(e) => setSourceRef(e.target.value)} maxLength={1000} />}
        </Field>

        <section aria-label={t("mdAdmin.editor.preview")} className="rounded-lg border border-stone-200 bg-parchment-deep/40 p-3 text-sm sm:col-span-2">
          <p className="text-xs font-semibold uppercase tracking-wide text-ink-muted">{t("mdAdmin.editor.preview")}</p>
          <p className="mt-1">
            <span className="font-semibold">{en || "—"}</span> · <span lang="hi">{hi || "—"}</span>{" "}
            <code className="text-xs text-ink-muted">{code || "—"}</code>
          </p>
          {(fields.aliases ?? []).length > 0 && <p className="text-xs text-ink-muted">{(fields.aliases ?? []).join(" · ")}</p>}
        </section>
        {propose.error && !serverDupes.length && (
          <div className="sm:col-span-2">
            <ErrorAlert error={propose.error} />
          </div>
        )}
        <button type="submit" className="hidden" aria-hidden tabIndex={-1} />
      </form>
    </Dialog>
  );
}

/** Retire a term (it stays resolvable for stored values) or bring a retired one back. */
export function LifecycleDialog({
  vocabulary,
  term,
  activeTerms,
  onClose,
  onDone,
}: {
  vocabulary: string;
  term: AdminTerm;
  activeTerms: AdminTerm[];
  onClose: () => void;
  onDone: (change: MasterDataChange) => void;
}) {
  const { t } = useTranslation();
  const retiring = term.status !== "retired";
  const [reason, setReason] = useState("");
  const [successor, setSuccessor] = useState("");
  const [as, setAs] = useState<"draft" | "reviewed">("reviewed");
  const [error, setError] = useState<string | null>(null);
  const propose = useProposeChange(vocabulary);
  const send = (publish: boolean) => {
    if (reason.trim().length < 3) {
      setError(t("mdAdmin.editor.reasonRequired"));
      return;
    }
    setError(null);
    propose.mutate(
      {
        action: retiring ? "retire" : "reactivate",
        code: term.code,
        base_revision: term.revision,
        successor_code: retiring ? successor || null : null,
        reactivate_as: as,
        reason: reason.trim(),
        publish,
        allow_similar: false,
      },
      { onSuccess: onDone },
    );
  };
  return (
    <Dialog
      open
      onClose={onClose}
      title={retiring ? t("mdAdmin.lifecycle.retireTitle", { label: term.labels.en }) : t("mdAdmin.lifecycle.reactivateTitle", { label: term.labels.en })}
      description={retiring ? t("mdAdmin.lifecycle.retireHint") : t("mdAdmin.lifecycle.reactivateHint")}
      footer={
        <>
          <Button variant="secondary" onClick={onClose}>
            {t("common.cancel")}
          </Button>
          <Button variant="secondary" loading={propose.isPending} onClick={() => send(false)}>
            {t("mdAdmin.editor.saveDraft")}
          </Button>
          <Button variant={retiring ? "danger" : "primary"} loading={propose.isPending} onClick={() => send(true)}>
            {retiring ? t("mdAdmin.lifecycle.retireNow") : t("mdAdmin.lifecycle.reactivateNow")}
          </Button>
        </>
      }
    >
      <div className="space-y-3">
        {retiring ? (
          <Field label={t("mdAdmin.lifecycle.successor")} hint={t("mdAdmin.lifecycle.successorHint")}>
            {(p) => (
              <Select {...p} value={successor} onChange={(e) => setSuccessor(e.target.value)}>
                <option value="">{t("mdAdmin.lifecycle.noSuccessor")}</option>
                {activeTerms
                  .filter((x) => x.code !== term.code && x.status !== "retired")
                  .map((x) => (
                    <option key={x.code} value={x.code}>
                      {x.labels.en} ({x.code})
                    </option>
                  ))}
              </Select>
            )}
          </Field>
        ) : (
          <Field label={t("mdAdmin.lifecycle.reactivateAs")}>
            {(p) => (
              <Select {...p} value={as} onChange={(e) => setAs(e.target.value as "draft" | "reviewed")}>
                <option value="reviewed">{t("mdAdmin.status.reviewed")}</option>
                <option value="draft">{t("mdAdmin.status.draft")}</option>
              </Select>
            )}
          </Field>
        )}
        <Field label={t("mdAdmin.editor.reason")} required error={error}>
          {(p) => <TextArea {...p} value={reason} onChange={(e) => setReason(e.target.value)} rows={2} maxLength={2000} />}
        </Field>
        <ErrorAlert error={propose.error} />
      </div>
    </Dialog>
  );
}

const DIFF_FIELDS = ["labels", "aliases", "scope", "parent_code", "source_url", "status", "sort_order", "successor_code"] as const;

function show(v: unknown): string {
  if (v === null || v === undefined || v === "") return "—";
  if (Array.isArray(v)) return v.length ? v.join(", ") : "—";
  if (typeof v === "object") return Object.entries(v as Record<string, unknown>).map(([k, x]) => `${k}: ${String(x)}`).join(" · ");
  return String(v);
}

/** Previous → proposed, field by field (only what changes). Values are rendered as text. */
export function ChangeDiff({ change }: { change: MasterDataChange }) {
  const { t } = useTranslation();
  const rows = DIFF_FIELDS.filter((f) => JSON.stringify(change.previous?.[f] ?? null) !== JSON.stringify(change.proposed?.[f] ?? null));
  if (!rows.length) return <p className="text-xs text-ink-muted">{t("mdAdmin.diff.none")}</p>;
  return (
    <table className="w-full text-left text-xs">
      <caption className="sr-only">{t("mdAdmin.diff.caption")}</caption>
      <thead>
        <tr className="text-ink-muted">
          <th scope="col" className="py-1 pr-2 font-medium">{t("mdAdmin.diff.field")}</th>
          <th scope="col" className="py-1 pr-2 font-medium">{t("mdAdmin.diff.before")}</th>
          <th scope="col" className="py-1 font-medium">{t("mdAdmin.diff.after")}</th>
        </tr>
      </thead>
      <tbody>
        {rows.map((f) => (
          <tr key={f} className="border-t border-stone-100 align-top">
            <th scope="row" className="py-1 pr-2 font-medium">{t(`mdAdmin.field.${f}`)}</th>
            <td className="py-1 pr-2 text-ink-muted line-through decoration-red-400/70">{show(change.previous?.[f])}</td>
            <td className="py-1">{show(change.proposed?.[f])}</td>
          </tr>
        ))}
      </tbody>
    </table>
  );
}
