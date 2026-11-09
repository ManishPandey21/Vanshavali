import { useEffect, useState, type FormEvent } from "react";
import { Link, useNavigate, useParams } from "react-router-dom";
import { useTranslation } from "react-i18next";
import { ArchiveRestore, Download, Link2, RefreshCw, Trash2 } from "lucide-react";
import type { DocumentCategory, DocumentLinkOut, DocumentLinkTarget, DocumentOut, GenealogicalDate, PersonSummary } from "../../../api/types";
import { saveBlob } from "../../../api/client";
import {
  fetchDocumentFile,
  useAddDocumentLink,
  useDeleteDocument,
  useDocument,
  useDocumentPreview,
  useDocumentVersions,
  useOcrText,
  useRemoveDocumentLink,
  useReprocess,
  useRestoreDocument,
  useUpdateDocument,
} from "../../../api/hooks/documents";
import { usePerson, usePersonEvents, usePlace, usePlaces } from "../../../api/hooks/people";
import { useProperties, useProperty } from "../../../api/hooks/property";
import { useTreeCtx } from "../../../lib/tree-context";
import { Perm } from "../../../lib/permissions";
import { emptyDate, formatDate, normalizeDate, validateDate } from "../../../lib/dates";
import { DOCUMENT_CATEGORIES, formatBytes } from "../../../lib/documents";
import { PipelineBadges, StorageBadge } from "../../../components/documents/DocumentBits";
import { ExtractionReview } from "../../../components/documents/ExtractionReview";
import { DocumentSharingPanel } from "../../../components/privacy/RecordSharingPanel";
import { GenealogicalDateEditor } from "../../../components/dates/GenealogicalDateEditor";
import { PersonPicker } from "../../../components/pickers";
import { hasDate } from "../../../components/person/PersonForm";
import { RecordPrivacyBadge } from "../../../components/person/badges";
import { Button } from "../../../components/ui/Button";
import { ConfirmDialog } from "../../../components/ui/Dialog";
import { ErrorAlert, LiveRegion, PageHeader, Spinner } from "../../../components/ui/feedback";
import { Field, Select, TextArea, TextInput } from "../../../components/ui/form";
import { Tabs } from "../../../components/ui/Tabs";

export function DocumentDetailPage() {
  const { documentId = "" } = useParams();
  const { t } = useTranslation();
  const { treeId, can } = useTreeCtx();
  const doc = useDocument(treeId, documentId);
  const [tab, setTab] = useState("review");
  if (doc.isLoading) return <Spinner />;
  if (!doc.data) return <ErrorAlert error={doc.error} />;
  const d = doc.data;
  const tabs = [
    { id: "review", label: t("extraction.title"), count: d.pending_proposals ?? 0 },
    ...(d.has_ocr_text && d.can_access_content ? [{ id: "ocr", label: t("documents.ocrText") }] : []),
    { id: "details", label: t("documents.details") },
    { id: "links", label: t("documents.links"), count: d.links?.length ?? 0 },
    { id: "history", label: t("documents.history") },
  ];
  return (
    <div>
      <PageHeader
        eyebrow={t(`enum.docCategory.${d.category}`)}
        title={d.title}
        subtitle={`${d.original_filename} · ${formatBytes(d.size_bytes)}${d.page_count ? ` · ${t("documents.pages", { count: d.page_count })}` : ""}`}
        actions={<DocumentActions doc={d} />}
      />
      <div className="mb-4 flex flex-wrap items-center gap-1.5">
        <StorageBadge doc={d} />
        <RecordPrivacyBadge level={d.privacy_level} />
        <PipelineBadges doc={d} />
        {d.deleted_at && <span className="rounded-full bg-red-50 px-2 py-0.5 text-xs text-red-800">{t("documents.inRecycleBin")}</span>}
      </div>
      {!d.can_access_content && <p className="mb-4 rounded-lg bg-parchment-deep p-3 text-sm">{t("documents.noContentAccess")}</p>}
      <div className="grid gap-6 lg:grid-cols-[minmax(0,20rem)_1fr]">
        <Preview doc={d} />
        <Tabs label={t("documents.sections")} tabs={tabs} active={tabs.some((x) => x.id === tab) ? tab : "review"} onChange={setTab}>
          {tab === "review" && (
            <ExtractionReview documentId={d.id} canReview={can(Perm.EXTRACTION_REVIEW) && d.can_access_content === true && d.can_change !== false} needsTarget={!(d.links ?? []).some((l) => l.target_type === "person")} />
          )}
          {tab === "ocr" && <OcrPanel doc={d} />}
          {tab === "details" && <MetadataForm doc={d} />}
          {tab === "links" && <LinksPanel doc={d} />}
          {tab === "history" && <Versions doc={d} />}
        </Tabs>
      </div>
      {!d.deleted_at && (
        <div className="mt-6">
          <DocumentSharingPanel doc={d} />
        </div>
      )}
    </div>
  );
}

function DocumentActions({ doc }: { doc: DocumentOut }) {
  const { t } = useTranslation();
  const { treeId, can } = useTreeCtx();
  const navigate = useNavigate();
  const reprocess = useReprocess(treeId, doc.id);
  const del = useDeleteDocument(treeId);
  const restore = useRestoreDocument(treeId);
  const [downloading, setDownloading] = useState(false);
  const [dlError, setDlError] = useState<unknown>(null);
  const [confirm, setConfirm] = useState(false);
  // a private record shared with this member is read-only to them (ADR-0027 §10; the server decides)
  const changeable = doc.can_change !== false;
  const manage = can(Perm.DOCUMENT_MANAGE) && changeable;
  const download = async () => {
    setDownloading(true);
    setDlError(null);
    try {
      const { blob, filename } = await fetchDocumentFile(treeId, doc.id, "original");
      saveBlob(blob, filename ?? doc.original_filename);
    } catch (e) {
      setDlError(e);
    } finally {
      setDownloading(false);
    }
  };
  return (
    <div className="flex flex-col items-end gap-2">
      <div className="flex flex-wrap gap-2">
        {doc.can_access_content && (doc.variants ?? []).includes("original") && (
          <Button variant="secondary" icon={<Download className="size-4" aria-hidden />} loading={downloading} onClick={() => void download()}>
            {t("documents.download")}
          </Button>
        )}
        {(can(Perm.DOCUMENT_UPLOAD) || manage) && changeable && !doc.deleted_at && (
          <Button variant="secondary" icon={<RefreshCw className="size-4" aria-hidden />} loading={reprocess.isPending} onClick={() => reprocess.mutate()}>
            {t("documents.reprocess")}
          </Button>
        )}
        {manage &&
          (doc.deleted_at ? (
            <Button variant="secondary" icon={<ArchiveRestore className="size-4" aria-hidden />} loading={restore.isPending} onClick={() => restore.mutate(doc.id)}>
              {t("documents.restore")}
            </Button>
          ) : (
            <Button variant="ghost" icon={<Trash2 className="size-4" aria-hidden />} onClick={() => setConfirm(true)}>
              {t("common.delete")}
            </Button>
          ))}
      </div>
      <ErrorAlert error={dlError || reprocess.error || restore.error} />
      <LiveRegion message={reprocess.data ? t("documents.reprocessed", { count: reprocess.data.pending_proposals }) : ""} />
      <ConfirmDialog
        open={confirm}
        onClose={() => setConfirm(false)}
        title={t("documents.deleteTitle")}
        body={t("documents.deleteBody")}
        confirmLabel={t("common.delete")}
        danger
        loading={del.isPending}
        onConfirm={() => del.mutate(doc.id, { onSuccess: () => navigate(`/t/${treeId}/documents`) })}
      >
        <ErrorAlert error={del.error} />
      </ConfirmDialog>
    </div>
  );
}

function Preview({ doc }: { doc: DocumentOut }) {
  const { t } = useTranslation();
  const { treeId } = useTreeCtx();
  const has = doc.can_access_content === true && (doc.variants ?? []).includes("preview");
  const preview = useDocumentPreview(treeId, doc.id, has);
  useEffect(() => {
    const url = preview.data;
    return () => {
      if (url) URL.revokeObjectURL(url);
    };
  }, [preview.data]);
  return (
    <figure className="card flex min-h-48 items-center justify-center overflow-hidden p-2">
      {!has ? (
        <figcaption className="p-6 text-center text-sm text-ink-muted">{t("documents.noPreview")}</figcaption>
      ) : preview.isLoading ? (
        <Spinner />
      ) : preview.data ? (
        <img src={preview.data} alt={t("documents.previewAlt", { title: doc.title })} className="max-h-[70vh] w-full object-contain" />
      ) : (
        <ErrorAlert error={preview.error} />
      )}
    </figure>
  );
}

function OcrPanel({ doc }: { doc: DocumentOut }) {
  const { t } = useTranslation();
  const { treeId } = useTreeCtx();
  const ocr = useOcrText(treeId, doc.id, true);
  if (ocr.isLoading) return <Spinner />;
  if (!ocr.data) return <ErrorAlert error={ocr.error} />;
  return (
    <section aria-labelledby="ocr-title" className="space-y-2">
      <h2 id="ocr-title" className="font-display text-lg font-semibold">
        {t("documents.ocrText")}
      </h2>
      <p className="rounded-lg bg-haldi-100 p-2 text-xs text-haldi-700">{t("documents.ocrNote")}</p>
      <p className="text-xs text-ink-muted">
        {ocr.data.engine}
        {ocr.data.confidence != null && ` · ${t("extraction.confidence", { pct: Math.round(ocr.data.confidence * (ocr.data.confidence <= 1 ? 100 : 1)) })}`}
      </p>
      {(ocr.data.pages ?? []).map((pg) => (
        <div key={pg.page} className="card p-3">
          <p className="mb-1 text-xs font-semibold text-ink-muted">{t("documents.pageN", { n: pg.page })}</p>
          <ol className="space-y-0.5 font-mono text-sm">
            {pg.lines.map((l) => (
              <li key={l.line_no} className="grid grid-cols-[2.5rem_1fr] gap-2">
                <span className="text-right text-xs text-ink-muted">{l.line_no}</span>
                <span className={l.confidence < 0.6 && l.confidence > 0 ? "bg-haldi-100" : ""}>{l.text}</span>
              </li>
            ))}
          </ol>
        </div>
      ))}
      {!(ocr.data.pages ?? []).length && ocr.data.text && <pre className="card whitespace-pre-wrap p-3 text-sm">{ocr.data.text}</pre>}
    </section>
  );
}

function MetadataForm({ doc }: { doc: DocumentOut }) {
  const { t } = useTranslation();
  const { treeId, can } = useTreeCtx();
  const update = useUpdateDocument(treeId, doc.id);
  const [title, setTitle] = useState(doc.title);
  const [description, setDescription] = useState(doc.description ?? "");
  const [category, setCategory] = useState<DocumentCategory>(doc.category);
  const [authority, setAuthority] = useState(doc.issuing_authority ?? "");
  const [date, setDate] = useState<GenealogicalDate>((doc.document_date as GenealogicalDate | null) ?? emptyDate());
  const [saved, setSaved] = useState("");
  const canEdit = (can(Perm.DOCUMENT_UPLOAD) || can(Perm.DOCUMENT_MANAGE)) && doc.can_change !== false;
  const submit = (e: FormEvent) => {
    e.preventDefault();
    if (!title.trim() || (hasDate(date) && Object.keys(validateDate(date)).length)) return;
    update.mutate(
      {
        title: title.trim(),
        description: description.trim() || null,
        category,
        issuing_authority: authority.trim() || null,
        document_date: hasDate(date) ? normalizeDate(date) : null,
      },
      { onSuccess: (d) => setSaved(t("documents.savedVersion", { v: d.metadata_version })) },
    );
  };
  return (
    <form onSubmit={submit} className="space-y-3" noValidate>
      <fieldset disabled={!canEdit} className="space-y-3">
        <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
          <Field label={t("documents.title")} required>
            {(p) => <TextInput {...p} value={title} onChange={(e) => setTitle(e.target.value)} />}
          </Field>
          <Field label={t("documents.category")} hint={t("documents.categoryChangeHint")}>
            {(p) => (
              <Select {...p} value={category} onChange={(e) => setCategory(e.target.value as DocumentCategory)}>
                {DOCUMENT_CATEGORIES.map((c) => (
                  <option key={c} value={c}>
                    {t(`enum.docCategory.${c}`)}
                  </option>
                ))}
              </Select>
            )}
          </Field>
          <Field label={t("documents.issuingAuthority")}>{(p) => <TextInput {...p} value={authority} onChange={(e) => setAuthority(e.target.value)} />}</Field>
        </div>
        <GenealogicalDateEditor legend={t("documents.date")} value={date} onChange={setDate} showErrors={hasDate(date)} />
        <Field label={t("documents.description")}>{(p) => <TextArea {...p} value={description} onChange={(e) => setDescription(e.target.value)} />}</Field>
      </fieldset>
      <p className="text-xs text-ink-muted">{t("documents.versionedHint", { v: doc.metadata_version })}</p>
      <ErrorAlert error={update.error} />
      <LiveRegion message={saved} />
      {canEdit && (
        <Button type="submit" loading={update.isPending}>
          {t("common.save")}
        </Button>
      )}
    </form>
  );
}

function Versions({ doc }: { doc: DocumentOut }) {
  const { t, i18n } = useTranslation();
  const { treeId } = useTreeCtx();
  const versions = useDocumentVersions(treeId, doc.id);
  if (versions.isLoading) return <Spinner />;
  return (
    <section aria-labelledby="ver-title">
      <h2 id="ver-title" className="mb-2 font-display text-lg font-semibold">
        {t("documents.history")}
      </h2>
      <ErrorAlert error={versions.error} />
      <ol className="space-y-2">
        {versions.data?.map((v) => {
          const s = v.snapshot as Record<string, unknown>;
          return (
            <li key={v.version} className="card p-3 text-sm">
              <p className="font-semibold">
                {t("documents.versionN", { v: v.version })} {v.current && <span className="ml-1 rounded-full bg-leaf-50 px-2 text-xs text-leaf-700">{t("documents.current")}</span>}
                <time className="ml-2 text-xs font-normal text-ink-muted" dateTime={v.created_at}>
                  {new Date(v.created_at).toLocaleString(i18n.language)}
                </time>
              </p>
              <dl className="mt-1 grid grid-cols-1 gap-x-3 text-xs sm:grid-cols-2">
                {["title", "category", "privacy_level", "issuing_authority", "document_date"].map((k) =>
                  s[k] != null ? (
                    <div key={k} className="flex gap-1">
                      <dt className="text-ink-muted">{t(`documents.field.${k}`)}:</dt>
                      <dd>{k === "document_date" ? formatDate(s[k] as GenealogicalDate, t, i18n.language) : k === "category" ? t(`enum.docCategory.${String(s[k])}`) : k === "privacy_level" ? t(`enum.recordPrivacy.${String(s[k])}`) : String(s[k])}</dd>
                    </div>
                  ) : null,
                )}
              </dl>
            </li>
          );
        })}
      </ol>
    </section>
  );
}

function LinkLabel({ link }: { link: DocumentLinkOut }) {
  const { t } = useTranslation();
  const { treeId } = useTreeCtx();
  const person = usePerson(treeId, link.target_type === "person" ? link.target_id : undefined);
  const place = usePlace(treeId, link.target_type === "place" ? link.target_id : undefined);
  const prop = useProperty(treeId, link.target_type === "property" ? link.target_id : undefined);
  const kind = t(`enum.linkTarget.${link.target_type}`);
  if (link.target_type === "person")
    return (
      <span>
        {kind}:{" "}
        {person.data ? (
          <Link className="text-kumkum-800 underline" to={`/t/${treeId}/people/${link.target_id}`}>
            {person.data.display_name}
          </Link>
        ) : (
          <em>{t("person.privatePerson")}</em>
        )}
      </span>
    );
  if (link.target_type === "property")
    return (
      <span>
        {kind}:{" "}
        {prop.data ? (
          <Link className="text-kumkum-800 underline" to={`/t/${treeId}/property/${link.target_id}`}>
            {prop.data.display_name}
          </Link>
        ) : (
          <em>{t("common.unknown")}</em>
        )}
      </span>
    );
  if (link.target_type === "place") return <span>{kind}: {place.data?.canonical_name ?? "…"}</span>;
  return <span>{kind}</span>;
}

function LinksPanel({ doc }: { doc: DocumentOut }) {
  const { t } = useTranslation();
  const { treeId, can } = useTreeCtx();
  const add = useAddDocumentLink(treeId, doc.id);
  const remove = useRemoveDocumentLink(treeId, doc.id);
  const canEdit = (can(Perm.DOCUMENT_UPLOAD) || can(Perm.DOCUMENT_MANAGE)) && doc.can_change !== false && !doc.deleted_at;
  const [type, setType] = useState<DocumentLinkTarget>("person");
  const [person, setPerson] = useState<PersonSummary | null>(null);
  const [targetId, setTargetId] = useState("");
  const [note, setNote] = useState("");
  const places = usePlaces(treeId, "", type === "place");
  const properties = useProperties(treeId, "", type === "property" && (can(Perm.PROPERTY_READ) || can(Perm.PROPERTY_WRITE)));
  const events = usePersonEventsMaybe(treeId, type === "event" ? person?.id : undefined);
  const id = type === "person" ? person?.id : targetId;
  return (
    <section aria-labelledby="links-title" className="space-y-3">
      <h2 id="links-title" className="font-display text-lg font-semibold">
        {t("documents.links")}
      </h2>
      {(doc.links ?? []).length === 0 && <p className="text-sm text-ink-muted">{t("documents.noLinks")}</p>}
      <ul className="divide-y divide-stone-100 text-sm">
        {(doc.links ?? []).map((l) => (
          <li key={l.id} className="flex items-center justify-between gap-2 py-1.5">
            <span className="flex items-center gap-1.5">
              <Link2 className="size-3.5 text-ink-muted" aria-hidden />
              <LinkLabel link={l} />
              {l.note && <span className="text-xs text-ink-muted">— {l.note}</span>}
            </span>
            {canEdit && (
              <Button size="sm" variant="ghost" onClick={() => remove.mutate(l.id)} aria-label={t("documents.removeLink")}>
                <Trash2 className="size-4" aria-hidden />
              </Button>
            )}
          </li>
        ))}
      </ul>
      <ErrorAlert error={remove.error} />
      {canEdit && (
        <form
          className="space-y-2 rounded-lg border border-dashed border-stone-300 p-3"
          onSubmit={(e) => {
            e.preventDefault();
            if (!id) return;
            add.mutate(
              { target_type: type, target_id: id, note: note.trim() || null },
              {
                onSuccess: () => {
                  setPerson(null);
                  setTargetId("");
                  setNote("");
                },
              },
            );
          }}
        >
          <p className="text-sm font-semibold">{t("documents.addLink")}</p>
          <div className="grid grid-cols-1 gap-2 sm:grid-cols-2">
            <Field label={t("documents.linkType")}>
              {(p) => (
                <Select
                  {...p}
                  value={type}
                  onChange={(e) => {
                    setType(e.target.value as DocumentLinkTarget);
                    setTargetId("");
                  }}
                >
                  {(["person", "event", "place", "property"] as const)
                    .filter((x) => x !== "property" || can(Perm.PROPERTY_READ) || can(Perm.PROPERTY_WRITE))
                    .map((x) => (
                      <option key={x} value={x}>
                        {t(`enum.linkTarget.${x}`)}
                      </option>
                    ))}
                </Select>
              )}
            </Field>
            {(type === "person" || type === "event") && <PersonPicker treeId={treeId} label={t("documents.linkPerson")} value={person} onChange={setPerson} />}
            {type === "event" && person && (
              <Field label={t("documents.linkEvent")}>
                {(p) => (
                  <Select {...p} value={targetId} onChange={(e) => setTargetId(e.target.value)}>
                    <option value="">—</option>
                    {events.data?.map((ev) => (
                      <option key={ev.id} value={ev.id}>
                        {t(`enum.eventType.${ev.type}`)}
                        {ev.date ? ` · ${formatDate(ev.date, t)}` : ""}
                      </option>
                    ))}
                  </Select>
                )}
              </Field>
            )}
            {type === "place" && (
              <Field label={t("enum.linkTarget.place")}>
                {(p) => (
                  <Select {...p} value={targetId} onChange={(e) => setTargetId(e.target.value)}>
                    <option value="">—</option>
                    {places.data?.items.map((pl) => (
                      <option key={pl.id} value={pl.id}>
                        {pl.canonical_name}
                      </option>
                    ))}
                  </Select>
                )}
              </Field>
            )}
            {type === "property" && (
              <Field label={t("enum.linkTarget.property")}>
                {(p) => (
                  <Select {...p} value={targetId} onChange={(e) => setTargetId(e.target.value)}>
                    <option value="">—</option>
                    {properties.data?.map((pr) => (
                      <option key={pr.id} value={pr.id}>
                        {pr.display_name}
                      </option>
                    ))}
                  </Select>
                )}
              </Field>
            )}
            <Field label={t("documents.linkNote")}>{(p) => <TextInput {...p} value={note} onChange={(e) => setNote(e.target.value)} />}</Field>
          </div>
          <ErrorAlert error={add.error} />
          <Button type="submit" size="sm" disabled={!id} loading={add.isPending}>
            {t("documents.addLink")}
          </Button>
        </form>
      )}
    </section>
  );
}

function usePersonEventsMaybe(treeId: string, personId: string | undefined) {
  return usePersonEvents(treeId, personId ?? "", !!personId);
}
