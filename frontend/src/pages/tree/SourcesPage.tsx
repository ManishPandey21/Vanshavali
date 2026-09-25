import { useState, type FormEvent } from "react";
import { useTranslation } from "react-i18next";
import { BookOpen, Plus, ScrollText } from "lucide-react";
import type { GenealogicalDate, PrivacyLevel, SourceIn, SourceOut, SourceType, TraditionIn } from "../../api/types";
import { useCreateSource, useSources, useUpdateSource } from "../../api/hooks/heritage";
import { useTreeCtx } from "../../lib/tree-context";
import { Perm } from "../../lib/permissions";
import { useDebounced } from "../../lib/useDebounced";
import { emptyDate, normalizeDate, validateDate } from "../../lib/dates";
import { SOURCE_TYPES } from "../../components/evidence/Citations";
import { GenealogicalDateEditor } from "../../components/dates/GenealogicalDateEditor";
import { DateText } from "../../components/dates/DateText";
import { PRIVACY_LEVELS, hasDate } from "../../components/person/PersonForm";
import { PrivacyBadge } from "../../components/person/badges";
import { Button } from "../../components/ui/Button";
import { Dialog } from "../../components/ui/Dialog";
import { EmptyState, ErrorAlert, PageHeader, Spinner } from "../../components/ui/feedback";
import { Field, Select, TextArea, TextInput } from "../../components/ui/form";
import { Badge } from "../../components/ui/Badge";

const TRADITION_TYPES = ["bahi", "panda_register", "temple_register", "community_register", "family_book", "other"] as const;

export function SourcesPage() {
  const { t } = useTranslation();
  const { treeId, can } = useTreeCtx();
  const [q, setQ] = useState("");
  const [type, setType] = useState<SourceType | "">("");
  const debounced = useDebounced(q.trim(), 250);
  const sources = useSources(treeId, debounced, type || undefined);
  const [creating, setCreating] = useState(false);
  const [editing, setEditing] = useState<SourceOut | null>(null);
  const items = sources.data?.pages.flatMap((p) => p.items) ?? [];
  return (
    <div>
      <PageHeader
        title={t("sources.title")}
        subtitle={t("sources.subtitle")}
        actions={
          can(Perm.SOURCE_WRITE) ? (
            <Button icon={<Plus className="size-4" aria-hidden />} onClick={() => setCreating(true)}>
              {t("sources.create")}
            </Button>
          ) : undefined
        }
      />
      <div className="mb-4 grid max-w-2xl grid-cols-1 gap-3 sm:grid-cols-2">
        <Field label={t("sources.search")}>{(p) => <TextInput {...p} type="search" value={q} onChange={(e) => setQ(e.target.value)} />}</Field>
        <Field label={t("sources.type")}>
          {(p) => (
            <Select {...p} value={type} onChange={(e) => setType(e.target.value as SourceType | "")}>
              <option value="">{t("common.all")}</option>
              {SOURCE_TYPES.map((s) => (
                <option key={s} value={s}>
                  {t(`enum.sourceType.${s}`)}
                </option>
              ))}
            </Select>
          )}
        </Field>
      </div>
      {sources.isLoading && <Spinner />}
      <ErrorAlert error={sources.error} />
      {sources.data && items.length === 0 && <EmptyState icon={<BookOpen className="size-10" aria-hidden />} title={t("sources.empty")}>{t("sources.emptyHint")}</EmptyState>}
      <ul className="space-y-3">
        {items.map((s) => (
          <SourceCard key={s.id} s={s} onEdit={can(Perm.SOURCE_WRITE) ? () => setEditing(s) : undefined} />
        ))}
      </ul>
      {sources.hasNextPage && (
        <div className="mt-4 flex justify-center">
          <Button variant="secondary" onClick={() => void sources.fetchNextPage()} loading={sources.isFetchingNextPage}>
            {t("common.loadMore")}
          </Button>
        </div>
      )}
      {creating && <SourceDialog onClose={() => setCreating(false)} />}
      {editing && <SourceDialog source={editing} onClose={() => setEditing(null)} />}
    </div>
  );
}

function SourceCard({ s, onEdit }: { s: SourceOut; onEdit?: () => void }) {
  const { t } = useTranslation();
  const tradition = s.tradition as Record<string, string | null> | null;
  return (
    <li className="card p-4">
      <div className="flex flex-wrap items-start justify-between gap-2">
        <div className="min-w-0">
          <h2 className="font-display text-lg font-semibold">{s.title}</h2>
          <p className="text-sm text-ink-muted">
            {[s.issuing_authority, s.repository, s.record_number && `#${s.record_number}`, s.place_text].filter(Boolean).join(" · ")}
          </p>
        </div>
        <div className="flex flex-wrap gap-1">
          <Badge tone="saffron">{t(`enum.sourceType.${s.source_type}`)}</Badge>
          <PrivacyBadge level={s.privacy_level} />
          <Badge tone="stone">{t("citations.count", { count: s.citation_count ?? 0 })}</Badge>
        </div>
      </div>
      {s.date && (
        <p className="mt-1 text-sm">
          <DateText date={s.date} />
        </p>
      )}
      {tradition && (
        <div className="mt-2 rounded-lg bg-parchment-deep p-3 text-sm">
          <p className="flex items-center gap-1 font-semibold">
            <ScrollText className="size-4 text-haldi-700" aria-hidden /> {t(`enum.tradition.${tradition.tradition_type}`, { defaultValue: tradition.tradition_type ?? "" })}
          </p>
          <dl className="mt-1 grid grid-cols-2 gap-x-3 gap-y-0.5 text-xs sm:grid-cols-3">
            {(["custodian", "pilgrimage_place", "volume", "page", "family_origin_place", "verification_status"] as const).map((k) =>
              tradition[k] ? (
                <div key={k}>
                  <dt className="text-ink-muted">{t(`sources.tradition.${k}`)}</dt>
                  <dd>{tradition[k]}</dd>
                </div>
              ) : null,
            )}
          </dl>
        </div>
      )}
      {s.url && (
        <a href={s.url} target="_blank" rel="noopener noreferrer nofollow" className="mt-1 inline-block text-sm text-kumkum-800 underline">
          {s.url}
        </a>
      )}
      {s.transcription && (
        <details className="mt-2 text-sm">
          <summary className="cursor-pointer text-kumkum-800">{t("sources.transcription")}</summary>
          <p className="mt-1 whitespace-pre-wrap">{s.transcription}</p>
          {s.translation && <p className="mt-1 whitespace-pre-wrap text-ink-muted">{s.translation}</p>}
        </details>
      )}
      {s.notes && <p className="mt-1 text-xs text-ink-muted">{s.notes}</p>}
      {onEdit && (
        <Button size="sm" variant="ghost" className="mt-2" onClick={onEdit}>
          {t("common.edit")}
        </Button>
      )}
    </li>
  );
}

function SourceDialog({ onClose, source }: { onClose: () => void; source?: SourceOut }) {
  const { t } = useTranslation();
  const { treeId } = useTreeCtx();
  const create = useCreateSource(treeId);
  const update = useUpdateSource(treeId);
  const mutation = source ? update : create;
  const [d, setD] = useState({
    source_type: (source?.source_type ?? "traditional_register") as SourceType,
    title: source?.title ?? "",
    issuing_authority: source?.issuing_authority ?? "",
    repository: source?.repository ?? "",
    record_number: source?.record_number ?? "",
    place_text: source?.place_text ?? "",
    url: source?.url ?? "",
    transcription: source?.transcription ?? "",
    translation: source?.translation ?? "",
    notes: source?.notes ?? "",
    privacy_level: (source?.privacy_level ?? "TREE_MEMBERS") as PrivacyLevel,
  });
  const [date, setDate] = useState<GenealogicalDate>((source?.date as GenealogicalDate | null) ?? emptyDate());
  const [tradition, setTradition] = useState<TraditionIn>((source?.tradition as TraditionIn | null) ?? { tradition_type: "bahi" });
  const [submitted, setSubmitted] = useState(false);
  const isTraditional = d.source_type === "traditional_register" || d.source_type === "family_book";
  const urlInvalid = !!d.url.trim() && !/^https?:\/\//.test(d.url.trim());
  const submit = (e: FormEvent) => {
    e.preventDefault();
    setSubmitted(true);
    if (!d.title.trim() || urlInvalid || (hasDate(date) && Object.keys(validateDate(date)).length)) return;
    const body: SourceIn = { source_type: d.source_type, title: d.title.trim(), privacy_level: d.privacy_level };
    for (const k of ["issuing_authority", "repository", "record_number", "place_text", "url", "transcription", "translation", "notes"] as const) {
      const v = d[k].trim();
      // On edit, send null so a cleared field is actually cleared.
      if (v) body[k] = v;
      else if (source) body[k] = null;
    }
    if (hasDate(date)) body.date = normalizeDate(date);
    if (isTraditional) {
      const tr: TraditionIn = { tradition_type: tradition.tradition_type };
      for (const k of ["custodian", "pilgrimage_place", "volume", "page", "family_origin_place", "verification_status"] as const) {
        const v = (tradition[k] ?? "").trim();
        if (v) tr[k] = v;
      }
      body.tradition = tr;
    }
    if (source) update.mutate({ id: source.id, body }, { onSuccess: onClose });
    else create.mutate(body, { onSuccess: onClose });
  };
  const text = (k: keyof typeof d, label: string, area = false) => (
    <Field label={label} className={area ? "sm:col-span-2" : ""}>
      {(p) =>
        area ? (
          <TextArea {...p} rows={3} value={d[k]} onChange={(e) => setD({ ...d, [k]: e.target.value })} />
        ) : (
          <TextInput {...p} value={d[k]} onChange={(e) => setD({ ...d, [k]: e.target.value })} />
        )
      }
    </Field>
  );
  return (
    <Dialog
      open
      onClose={onClose}
      size="lg"
      title={source ? t("sources.editTitle") : t("sources.create")}
      footer={
        <>
          <Button variant="secondary" onClick={onClose}>
            {t("common.cancel")}
          </Button>
          <Button type="submit" form="source-form" loading={mutation.isPending}>
            {t("common.save")}
          </Button>
        </>
      }
    >
      <form id="source-form" onSubmit={submit} className="space-y-3" noValidate>
        <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
          <Field label={t("sources.titleField")} required error={submitted && !d.title.trim() ? t("common.required") : null} className="sm:col-span-2">
            {(p) => <TextInput {...p} value={d.title} onChange={(e) => setD({ ...d, title: e.target.value })} />}
          </Field>
          <Field label={t("sources.type")}>
            {(p) => (
              <Select {...p} value={d.source_type} onChange={(e) => setD({ ...d, source_type: e.target.value as SourceType })}>
                {SOURCE_TYPES.map((s) => (
                  <option key={s} value={s}>
                    {t(`enum.sourceType.${s}`)}
                  </option>
                ))}
              </Select>
            )}
          </Field>
          <Field label={t("privacy.level")}>
            {(p) => (
              <Select {...p} value={d.privacy_level} onChange={(e) => setD({ ...d, privacy_level: e.target.value as PrivacyLevel })}>
                {PRIVACY_LEVELS.map((l) => (
                  <option key={l} value={l}>
                    {t(`enum.privacy.${l}`)}
                  </option>
                ))}
              </Select>
            )}
          </Field>
          {text("issuing_authority", t("sources.authority"))}
          {text("repository", t("sources.repository"))}
          {text("record_number", t("sources.recordNumber"))}
          {text("place_text", t("sources.place"))}
          <Field label={t("sources.url")} error={submitted && urlInvalid ? t("sources.urlInvalid") : null} className="sm:col-span-2">
            {(p) => <TextInput {...p} type="url" value={d.url} onChange={(e) => setD({ ...d, url: e.target.value })} />}
          </Field>
        </div>
        <GenealogicalDateEditor legend={t("sources.date")} value={date} onChange={setDate} showErrors={submitted && hasDate(date)} />
        {isTraditional && (
          <fieldset className="grid grid-cols-1 gap-3 rounded-lg border border-haldi-300 bg-haldi-100/40 p-3 sm:grid-cols-2">
            <legend className="px-1 text-sm font-semibold">{t("sources.traditionTitle")}</legend>
            <p className="text-xs text-ink-muted sm:col-span-2">{t("sources.traditionHint")}</p>
            <Field label={t("sources.tradition.tradition_type")}>
              {(p) => (
                <Select {...p} value={tradition.tradition_type} onChange={(e) => setTradition({ ...tradition, tradition_type: e.target.value })}>
                  {TRADITION_TYPES.map((tt) => (
                    <option key={tt} value={tt}>
                      {t(`enum.tradition.${tt}`)}
                    </option>
                  ))}
                </Select>
              )}
            </Field>
            {(["custodian", "pilgrimage_place", "volume", "page", "family_origin_place", "verification_status"] as const).map((k) => (
              <Field key={k} label={t(`sources.tradition.${k}`)}>
                {(p) => <TextInput {...p} value={tradition[k] ?? ""} onChange={(e) => setTradition({ ...tradition, [k]: e.target.value })} />}
              </Field>
            ))}
          </fieldset>
        )}
        <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
          {text("transcription", t("sources.transcription"), true)}
          {text("translation", t("sources.translation"), true)}
          {text("notes", t("sources.notes"), true)}
        </div>
        <ErrorAlert error={mutation.error} />
      </form>
    </Dialog>
  );
}
