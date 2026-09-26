import { useId, useState } from "react";
import { Navigate } from "react-router-dom";
import { useTranslation } from "react-i18next";
import type { TFunction } from "i18next";
import { Archive, Download, FileUp, ShieldAlert } from "lucide-react";
import type { CommitIn, ImportJobOut, StagedPersonPreview } from "../../api/types";
import { apiBlob, saveBlob } from "../../api/client";
import { downloadGedcom, useCancelImport, useCommitImport, useImport, useImports, useUploadGedcom } from "../../api/hooks/property";
import { useTreeCtx } from "../../lib/tree-context";
import { Perm } from "../../lib/permissions";
import { Button } from "../../components/ui/Button";
import { ConfirmDialog } from "../../components/ui/Dialog";
import { ErrorAlert, PageHeader, Spinner } from "../../components/ui/feedback";
import { Checkbox } from "../../components/ui/form";
import { Badge } from "../../components/ui/Badge";
import { FamilyConsentGate } from "../../components/consent/FamilyConsent";

export type Decision = { kind: "create" } | { kind: "skip" } | { kind: "attach"; personId: string };

/** The commit body: every staged person gets an explicit decision (create / skip / attach to existing). */
export function buildCommitBody(decisions: Record<string, Decision>): CommitIn {
  const out: CommitIn["decisions"] = {};
  for (const [xref, d] of Object.entries(decisions)) {
    out[xref] = d.kind === "attach" ? { attach: d.personId } : d.kind;
  }
  return { decisions: out };
}

/** Default: create new people; never auto-attach, even to a probable duplicate (a person decides). */
export function defaultDecisions(preview: StagedPersonPreview[]): Record<string, Decision> {
  return Object.fromEntries(preview.map((p) => [p.xref, { kind: "create" } as Decision]));
}

export function ImportExportPage() {
  const { t } = useTranslation();
  const { treeId, can } = useTreeCtx();
  const canImport = can(Perm.GEDCOM_IMPORT);
  const canExport = can(Perm.GEDCOM_EXPORT);
  if (!canImport && !canExport) return <Navigate to={`/t/${treeId}`} replace />;
  return (
    <div className="space-y-8">
      <PageHeader title={t("gedcom.title")} subtitle={t("gedcom.subtitle")} />
      {canExport && (
        <div className="grid gap-6 lg:grid-cols-2">
          <GedcomExport />
          <ArchiveExport />
        </div>
      )}
      {canImport && <GedcomImport />}
    </div>
  );
}

function GedcomExport() {
  const { t } = useTranslation();
  const { treeId, can } = useTreeCtx();
  const admin = can(Perm.PRIVACY_MANAGE);
  const [excludeLiving, setExcludeLiving] = useState(true);
  const [sensitive, setSensitive] = useState(false);
  const [confirm, setConfirm] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<unknown>(null);
  const run = async () => {
    setBusy(true);
    setError(null);
    try {
      await downloadGedcom(treeId, { exclude_living: excludeLiving, include_sensitive: sensitive });
    } catch (e) {
      setError(e);
    } finally {
      setBusy(false);
    }
  };
  return (
    <section className="card space-y-3 p-4" aria-labelledby="exp-title">
      <h2 id="exp-title" className="flex items-center gap-2 font-display text-lg font-semibold">
        <Download className="size-5 text-haldi-700" aria-hidden /> {t("gedcom.exportTitle")}
      </h2>
      <p className="text-sm text-ink-muted">{t("gedcom.exportIntro")}</p>
      <Checkbox label={t("gedcom.excludeLiving")} hint={t("gedcom.excludeLivingHint")} checked={excludeLiving} onChange={setExcludeLiving} />
      {admin && <Checkbox label={t("gedcom.includeSensitive")} hint={t("gedcom.includeSensitiveHint")} checked={sensitive} onChange={setSensitive} />}
      <ErrorAlert error={error} />
      <Button icon={<Download className="size-4" aria-hidden />} loading={busy} onClick={() => (sensitive ? setConfirm(true) : void run())}>
        {t("gedcom.download")}
      </Button>
      <ConfirmDialog
        open={confirm}
        onClose={() => setConfirm(false)}
        title={t("gedcom.confirmSensitiveTitle")}
        body={t("gedcom.confirmSensitiveBody")}
        confirmLabel={t("gedcom.confirmSensitive")}
        danger
        onConfirm={() => {
          setConfirm(false);
          void run();
        }}
      />
    </section>
  );
}

function ArchiveExport() {
  const { t } = useTranslation();
  const { treeId, can } = useTreeCtx();
  const admin = can(Perm.PRIVACY_MANAGE);
  const [excludeLiving, setExcludeLiving] = useState(true);
  const [sensitive, setSensitive] = useState(false);
  const [vault, setVault] = useState(false);
  const [confirm, setConfirm] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<unknown>(null);
  const run = async () => {
    setBusy(true);
    setError(null);
    try {
      const { blob, filename } = await apiBlob(`/trees/${treeId}/exports/archive`, {
        exclude_living: excludeLiving,
        include_sensitive: sensitive,
        include_vault_documents: vault,
      });
      saveBlob(blob, filename ?? "family-archive.zip");
    } catch (e) {
      setError(e);
    } finally {
      setBusy(false);
    }
  };
  return (
    <section className="card space-y-3 p-4" aria-labelledby="arch-title">
      <h2 id="arch-title" className="flex items-center gap-2 font-display text-lg font-semibold">
        <Archive className="size-5 text-haldi-700" aria-hidden /> {t("archive.title")}
      </h2>
      <p className="text-sm text-ink-muted">{t("archive.intro")}</p>
      <p className="flex items-start gap-2 rounded-lg bg-haldi-100 p-2 text-xs text-haldi-700">
        <ShieldAlert className="mt-0.5 size-4 shrink-0" aria-hidden /> {t("archive.personalData")}
      </p>
      <Checkbox label={t("gedcom.excludeLiving")} hint={t("gedcom.excludeLivingHint")} checked={excludeLiving} onChange={setExcludeLiving} />
      {admin && (
        <>
          <Checkbox label={t("gedcom.includeSensitive")} hint={t("gedcom.includeSensitiveHint")} checked={sensitive} onChange={setSensitive} />
          <Checkbox label={t("archive.includeVault")} hint={t("archive.includeVaultHint")} checked={vault} onChange={setVault} />
        </>
      )}
      <ErrorAlert error={error} />
      <Button icon={<Archive className="size-4" aria-hidden />} loading={busy} onClick={() => (sensitive || vault ? setConfirm(true) : void run())}>
        {t("archive.download")}
      </Button>
      <ConfirmDialog
        open={confirm}
        onClose={() => setConfirm(false)}
        title={t("archive.confirmTitle")}
        body={t("archive.confirmBody")}
        confirmLabel={t("archive.confirm")}
        danger
        onConfirm={() => {
          setConfirm(false);
          void run();
        }}
      />
    </section>
  );
}

/**
 * A staged birth/death for the import preview. An event recorded without a date (common in
 * MyHeritage exports, e.g. only a place) reads "India, date unknown"; nothing is invented.
 */
export function vitalText(t: TFunction, date: string | null | undefined, recorded: boolean | undefined, place: string | null | undefined): string | null {
  if (date) return date;
  if (!recorded) return null;
  return place ? t("gedcom.placeDateUnknown", { place }) : t("gedcom.dateUnknown");
}

function GedcomImport() {
  const { t, i18n } = useTranslation();
  const { treeId } = useTreeCtx();
  const fileId = useId();
  const imports = useImports(treeId, true);
  const upload = useUploadGedcom(treeId);
  const [file, setFile] = useState<File | null>(null);
  const [selected, setSelected] = useState<string | null>(null);
  return (
    <section className="space-y-4" aria-labelledby="imp-title">
      <h2 id="imp-title" className="flex items-center gap-2 font-display text-xl font-semibold">
        <FileUp className="size-5 text-haldi-700" aria-hidden /> {t("gedcom.importTitle")}
      </h2>
      <FamilyConsentGate treeId={treeId}>
        <div className="card space-y-3 p-4">
          <p className="text-sm text-ink-muted">{t("gedcom.importIntro")}</p>
          <label htmlFor={fileId} className="label">
            {t("gedcom.file")}
          </label>
          <input id={fileId} type="file" accept=".ged,.gedcom,.zip,text/plain" className="block text-sm" onChange={(e) => setFile(e.target.files?.[0] ?? null)} />
          <ErrorAlert error={upload.error} />
          <Button disabled={!file} loading={upload.isPending} onClick={() => file && upload.mutate(file, { onSuccess: (j) => setSelected(j.id) })}>
            {t("gedcom.upload")}
          </Button>
        </div>
      </FamilyConsentGate>
      {imports.isLoading && <Spinner />}
      <ErrorAlert error={imports.error} />
      {(imports.data ?? []).length > 0 && (
        <div className="card p-3">
          <h3 className="text-xs font-semibold uppercase text-ink-muted">{t("gedcom.history")}</h3>
          <ul className="divide-y divide-stone-100 text-sm">
            {imports.data!.map((j) => (
              <li key={j.id} className="flex flex-wrap items-center justify-between gap-2 py-1.5">
                <span>
                  {j.original_filename ?? "—"} · {new Date(j.created_at).toLocaleString(i18n.language)}
                </span>
                <span className="flex items-center gap-2">
                  <Badge tone={j.status === "ready" ? "saffron" : j.status === "committed" || j.status === "completed" ? "green" : j.status === "failed" ? "red" : "stone"}>{t(`enum.jobStatus.${j.status}`)}</Badge>
                  <Button size="sm" variant="ghost" onClick={() => setSelected(j.id)} aria-pressed={selected === j.id}>
                    {t("gedcom.open")}
                  </Button>
                </span>
              </li>
            ))}
          </ul>
        </div>
      )}
      {selected && <ImportJob id={selected} />}
    </section>
  );
}

function ImportJob({ id }: { id: string }) {
  const { t } = useTranslation();
  const { treeId } = useTreeCtx();
  const job = useImport(treeId, id);
  if (job.isLoading) return <Spinner />;
  if (!job.data) return <ErrorAlert error={job.error} />;
  return <ImportReview key={`${job.data.id}-${job.data.status}`} job={job.data} t={t} />;
}

function ImportReview({ job, t }: { job: ImportJobOut; t: ReturnType<typeof useTranslation>["t"] }) {
  const { treeId } = useTreeCtx();
  const commit = useCommitImport(treeId);
  const cancel = useCancelImport(treeId);
  const [decisions, setDecisions] = useState<Record<string, Decision>>(() => defaultDecisions(job.preview ?? []));
  const report = (job.report ?? {}) as {
    counts?: Record<string, number>;
    warnings?: { line?: number | null; code: string; message: string }[];
    errors?: { line?: number | null; code: string; message: string }[];
    unsupported_tags?: Record<string, number>;
    unknown_extension_tags?: Record<string, number>;
    extension_tags?: Record<string, number>;
  };
  const counts = { ...(report.counts ?? {}), ...(job.counts ?? {}) };
  const ready = job.status === "ready";
  const summary = Object.values(decisions).reduce<Record<string, number>>((a, d) => ({ ...a, [d.kind]: (a[d.kind] ?? 0) + 1 }), {});
  const tagList = (m?: Record<string, number>) =>
    Object.entries(m ?? {})
      .map(([k, v]) => `${k} ×${v}`)
      .join(", ");
  return (
    <article className="card space-y-4 p-4" aria-label={t("gedcom.report")}>
      <div className="flex flex-wrap items-center justify-between gap-2">
        <h3 className="font-display text-lg font-semibold">
          {t("gedcom.report")}: {job.original_filename}
        </h3>
        <span className="text-xs text-ink-muted">
          GEDCOM {job.detected_version ?? "?"} · {job.detected_encoding ?? "?"}
        </span>
      </div>
      {job.error && <p className="rounded bg-red-50 p-2 text-sm text-red-900">{job.error}</p>}
      <dl className="grid grid-cols-2 gap-2 text-sm sm:grid-cols-4">
        {Object.entries(counts).map(([k, v]) => (
          <div key={k} className="rounded-lg bg-parchment p-2">
            <dt className="text-xs text-ink-muted">{t(`gedcom.count.${k}`, { defaultValue: k.replace(/_/g, " ") })}</dt>
            <dd className="font-display text-xl font-bold">{v}</dd>
          </div>
        ))}
      </dl>
      {(report.errors ?? []).length > 0 && (
        <details open className="rounded-lg border border-red-300 p-2 text-sm">
          <summary className="cursor-pointer font-semibold text-red-900">{t("gedcom.errors", { count: report.errors!.length })}</summary>
          <ul className="mt-1 list-inside list-disc">
            {report.errors!.map((w, i) => (
              <li key={i}>
                {w.line ? `${t("gedcom.line", { n: w.line })}: ` : ""}
                {w.message}
              </li>
            ))}
          </ul>
        </details>
      )}
      {(report.warnings ?? []).length > 0 && (
        <details className="rounded-lg border border-haldi-300 p-2 text-sm">
          <summary className="cursor-pointer font-semibold text-haldi-700">{t("gedcom.warnings", { count: report.warnings!.length })}</summary>
          <ul className="mt-1 max-h-60 list-inside list-disc overflow-auto">
            {report.warnings!.map((w, i) => (
              <li key={i}>
                {w.line ? `${t("gedcom.line", { n: w.line })}: ` : ""}
                {w.message}
              </li>
            ))}
          </ul>
        </details>
      )}
      {tagList(report.unsupported_tags) && (
        <p className="text-sm">
          <span className="font-semibold">{t("gedcom.unsupportedTags")}:</span> <span className="font-mono text-xs">{tagList(report.unsupported_tags)}</span>
          <span className="block text-xs text-ink-muted">{t("gedcom.preservedHint")}</span>
        </p>
      )}
      {tagList(report.unknown_extension_tags) && (
        <p className="text-sm">
          <span className="font-semibold">{t("gedcom.unknownExtensions")}:</span> <span className="font-mono text-xs">{tagList(report.unknown_extension_tags)}</span>
        </p>
      )}
      {(job.preview ?? []).length > 0 && (
        <div>
          <h4 className="mb-2 font-semibold">{t("gedcom.preview", { shown: job.preview!.length, total: job.preview_total ?? job.preview!.length })}</h4>
          <div className="relative overflow-x-auto">
            <table className="w-full text-sm">
              <caption className="sr-only">{t("gedcom.previewCaption")}</caption>
              <thead className="text-left text-xs uppercase tracking-wide text-ink-muted">
                <tr>
                  <th scope="col" className="py-1 pr-3">
                    {t("gedcom.person")}
                  </th>
                  <th scope="col" className="py-1 pr-3">
                    {t("gedcom.lifeDates")}
                  </th>
                  <th scope="col" className="py-1 pr-3">
                    {t("gedcom.possibleDuplicates")}
                  </th>
                  <th scope="col" className="py-1 pr-3">
                    {t("gedcom.decision")}
                  </th>
                </tr>
              </thead>
              <tbody className="divide-y divide-stone-100">
                {job.preview!.map((p) => {
                  const d = decisions[p.xref] ?? { kind: "create" };
                  const value = d.kind === "attach" ? `attach:${d.personId}` : d.kind;
                  return (
                    <tr key={p.xref} className="align-top">
                      <td className="py-2 pr-3">
                        <p className="font-medium">{p.display_name}</p>
                        <p className="text-xs text-ink-muted">
                          {p.xref} · {t(`enum.profileStatus.${p.profile_status}`, { defaultValue: p.profile_status })}
                          {p.event_count ? ` · ${t("gedcom.events", { count: p.event_count })}` : ""}
                          {(p.heritage ?? []).length ? ` · ${(p.heritage ?? []).map((h) => t(`enum.heritage.${h}`, { defaultValue: h })).join(", ")}` : ""}
                        </p>
                      </td>
                      <td className="py-2 pr-3 text-xs">
                        {vitalText(t, p.birth, p.birth_recorded, p.birth_place) ?? "?"} – {vitalText(t, p.death, p.death_recorded, p.death_place) ?? ""}
                      </td>
                      <td className="py-2 pr-3 text-xs">
                        {(p.duplicates ?? []).length === 0
                          ? "—"
                          : p.duplicates!.map((m) => (
                              <p key={m.person.id}>
                                <Badge tone={m.outcome === "probable" ? "red" : "saffron"}>{t(`enum.dupOutcome.${m.outcome}`, { defaultValue: m.outcome })}</Badge> {m.person.display_name} ({Math.round(m.score * 100)}%)
                              </p>
                            ))}
                      </td>
                      <td className="py-2 pr-3">
                        <label className="sr-only" htmlFor={`dec-${p.xref}`}>
                          {t("gedcom.decisionFor", { name: p.display_name })}
                        </label>
                        <select
                          id={`dec-${p.xref}`}
                          className="input"
                          disabled={!ready}
                          value={value}
                          onChange={(e) => {
                            const v = e.target.value;
                            setDecisions({
                              ...decisions,
                              [p.xref]: v.startsWith("attach:") ? { kind: "attach", personId: v.slice(7) } : ({ kind: v } as Decision),
                            });
                          }}
                        >
                          <option value="create">{t("gedcom.create")}</option>
                          <option value="skip">{t("gedcom.skip")}</option>
                          {(p.duplicates ?? []).map((m) => (
                            <option key={m.person.id} value={`attach:${m.person.id}`}>
                              {t("gedcom.attachTo", { name: m.person.display_name })}
                            </option>
                          ))}
                        </select>
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
          {(job.preview_total ?? 0) > job.preview!.length && <p className="mt-1 text-xs text-ink-muted">{t("gedcom.previewLimited")}</p>}
        </div>
      )}
      {job.commit_result && (
        <div role="status" className="rounded-lg bg-leaf-50 p-3 text-sm text-leaf-700">
          <p className="font-semibold">{t("gedcom.committed")}</p>
          <p className="font-mono text-xs">{JSON.stringify(job.commit_result)}</p>
        </div>
      )}
      {ready && (
        <div className="flex flex-wrap items-center gap-2">
          <Button loading={commit.isPending} onClick={() => commit.mutate({ id: job.id, body: buildCommitBody(decisions) })}>
            {t("gedcom.commit", { create: summary.create ?? 0, skip: summary.skip ?? 0, attach: summary.attach ?? 0 })}
          </Button>
          <Button variant="secondary" loading={cancel.isPending} onClick={() => cancel.mutate(job.id)}>
            {t("gedcom.cancel")}
          </Button>
        </div>
      )}
      <ErrorAlert error={commit.error || cancel.error} />
    </article>
  );
}
