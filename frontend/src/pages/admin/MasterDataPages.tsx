import { useState, type ReactNode } from "react";
import { Link, NavLink, Navigate, Outlet, useParams, useSearchParams } from "react-router-dom";
import { useTranslation } from "react-i18next";
import { BookOpen, Clock3, History, Languages, Lock, MapPinned, Moon, Pencil, Plus, ShieldCheck, Sparkles, Users } from "lucide-react";
import { ApiError } from "../../api/client";
import { useMe } from "../../api/hooks/auth";
import { useAdminChanges, useAdminTerm, useAdminTerms, useAdminVocabularies, useDecideChange } from "../../api/hooks/masterDataAdmin";
import type { AdminTerm, AdminVocabulary, MasterDataChange } from "../../api/types";
import { Badge, type Tone } from "../../components/ui/Badge";
import { Button, ButtonLink } from "../../components/ui/Button";
import { Dialog } from "../../components/ui/Dialog";
import { EmptyState, ErrorAlert, LiveRegion, PageHeader, Spinner } from "../../components/ui/feedback";
import { Field, Select, TextArea, TextInput } from "../../components/ui/form";
import { useDebounced } from "../../lib/useDebounced";
import { ChangeDiff, LifecycleDialog, TermEditorDialog } from "./TermEditor";

const BASE = "/admin/master-data";
const STATUS_TONE: Record<string, Tone> = { draft: "saffron", reviewed: "green", retired: "stone" };
const CHANGE_TONE: Record<string, Tone> = { pending: "saffron", published: "green", rejected: "red", withdrawn: "stone" };
const CATEGORY_ORDER = ["heritage", "languages_terminology", "other", "astrology", "religion_community", "geography"];

/** Shown only to system admins (UI only: the server refuses everyone else with 404). */
export function MasterDataLayout() {
  const { t } = useTranslation();
  const me = useMe();
  if (me.isLoading) return <Spinner />;
  if (!me.data?.is_system_admin) return <Navigate to="/" replace />;
  const link = ({ isActive }: { isActive: boolean }) =>
    `inline-flex items-center gap-1.5 rounded-md px-3 py-1.5 text-sm ${isActive ? "bg-kumkum-50 font-semibold text-kumkum-900" : "text-ink hover:bg-parchment-deep"}`;
  return (
    <div>
      <PageHeader eyebrow={t("mdAdmin.eyebrow")} title={t("mdAdmin.title")} subtitle={t("mdAdmin.subtitle")} />
      <p className="mb-4 flex items-start gap-2 rounded-lg border border-sky-200 bg-sky-50 px-3 py-2 text-sm text-sky-950">
        <ShieldCheck className="mt-0.5 size-4 shrink-0" aria-hidden />
        {t("mdAdmin.boundary")}
      </p>
      {!me.data.mfa_enabled ? (
        <div role="alert" className="rounded-xl border border-haldi-300 bg-haldi-100/60 p-4">
          <p className="flex items-center gap-2 font-semibold">
            <Lock className="size-4" aria-hidden />
            {t("mdAdmin.mfaTitle")}
          </p>
          <p className="mt-1 text-sm">{t("mdAdmin.mfaBody")}</p>
          <ButtonLink to="/account" className="mt-3">
            {t("mdAdmin.mfaAction")}
          </ButtonLink>
        </div>
      ) : (
        <>
          <nav aria-label={t("mdAdmin.navLabel")} className="mb-5 flex flex-wrap gap-1 border-b border-stone-200 pb-2">
            <NavLink to={BASE} end className={link}>
              <BookOpen className="size-4" aria-hidden />
              {t("mdAdmin.nav.dashboard")}
            </NavLink>
            <NavLink to={`${BASE}/geography`} className={link}>
              <MapPinned className="size-4" aria-hidden />
              {t("mdAdmin.nav.geography")}
            </NavLink>
            <NavLink to={`${BASE}/reviews`} className={link}>
              <Clock3 className="size-4" aria-hidden />
              {t("mdAdmin.nav.reviews")}
            </NavLink>
            <NavLink to={`${BASE}/history`} className={link}>
              <History className="size-4" aria-hidden />
              {t("mdAdmin.nav.history")}
            </NavLink>
          </nav>
          <Outlet />
        </>
      )}
    </div>
  );
}

function vocabName(t: (k: string, o?: Record<string, unknown>) => string, v: { key: string; description?: string }) {
  return t(`mdAdmin.vocab.${v.key}`, { defaultValue: v.key });
}

const CATEGORY_ICON: Record<string, ReactNode> = {
  heritage: <Sparkles className="size-5" aria-hidden />,
  languages_terminology: <Languages className="size-5" aria-hidden />,
  other: <BookOpen className="size-5" aria-hidden />,
};

/** Areas that are planned or deliberately not catalogues, so admins know where they stand. */
function PlannedCard({ icon, title, body, badge }: { icon: ReactNode; title: string; body: string; badge: string }) {
  return (
    <li className="rounded-xl border border-dashed border-stone-300 bg-white/60 p-4">
      <p className="flex items-center gap-2 font-display text-base font-semibold text-ink-muted">
        {icon}
        {title}
      </p>
      <p className="mt-1 text-sm text-ink-muted">{body}</p>
      <div className="mt-2">
        <Badge tone="stone">{badge}</Badge>
      </div>
    </li>
  );
}

export function MasterDataDashboard() {
  const { t } = useTranslation();
  const q = useAdminVocabularies();
  if (q.isLoading) return <Spinner />;
  if (q.error) return <ErrorAlert error={q.error} />;
  const groups = new Map<string, AdminVocabulary[]>();
  for (const v of q.data ?? []) groups.set(v.category, [...(groups.get(v.category) ?? []), v]);
  const ordered = [...groups.keys()].sort((a, b) => CATEGORY_ORDER.indexOf(a) - CATEGORY_ORDER.indexOf(b));
  return (
    <div className="space-y-6">
      {ordered.map((cat) => (
        <section key={cat} aria-labelledby={`cat-${cat}`}>
          <h2 id={`cat-${cat}`} className="mb-2 flex items-center gap-2 font-display text-lg font-semibold">
            {CATEGORY_ICON[cat]}
            {t(`mdAdmin.category.${cat}`, { defaultValue: cat })}
          </h2>
          <ul className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
            {(groups.get(cat) ?? []).map((v) => {
              const active = (v.counts.draft ?? 0) + (v.counts.reviewed ?? 0);
              return (
                <li key={v.key}>
                  <Link to={`${BASE}/v/${v.key}`} className="block h-full rounded-xl border border-stone-200 bg-white p-4 shadow-sm hover:border-kumkum-300 hover:shadow">
                    <p className="font-display text-base font-semibold">{vocabName(t, v)}</p>
                    <p className="mt-0.5 line-clamp-2 text-xs text-ink-muted">{v.description}</p>
                    <div className="mt-2 flex flex-wrap gap-1.5">
                      <Badge tone="neutral">{t("mdAdmin.dash.active", { count: active })}</Badge>
                      {(v.counts.reviewed ?? 0) > 0 && <Badge tone="green">{t("mdAdmin.dash.reviewed", { count: v.counts.reviewed })}</Badge>}
                      {(v.counts.retired ?? 0) > 0 && <Badge tone="stone">{t("mdAdmin.dash.retired", { count: v.counts.retired })}</Badge>}
                      {(v.pending_changes ?? 0) > 0 && <Badge tone="saffron">{t("mdAdmin.dash.pending", { count: v.pending_changes })}</Badge>}
                      {v.fixed_membership && <Badge tone="blue">{t("mdAdmin.fixedSet")}</Badge>}
                    </div>
                  </Link>
                </li>
              );
            })}
          </ul>
        </section>
      ))}
      <section aria-labelledby="cat-geography">
        <h2 id="cat-geography" className="mb-2 flex items-center gap-2 font-display text-lg font-semibold">
          <MapPinned className="size-5" aria-hidden />
          {t("mdAdmin.category.geography")}
        </h2>
        <Link to={`${BASE}/geography`} className="block rounded-xl border border-stone-200 bg-white p-4 shadow-sm hover:border-kumkum-300 hover:shadow sm:max-w-sm">
          <p className="font-display text-base font-semibold">{t("mdAdmin.geoCard.title")}</p>
          <p className="mt-0.5 text-xs text-ink-muted">{t("mdAdmin.geoCard.body")}</p>
        </Link>
      </section>
      <section aria-labelledby="cat-planned">
        <h2 id="cat-planned" className="mb-2 font-display text-lg font-semibold">
          {t("mdAdmin.planned.title")}
        </h2>
        <ul className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
          <PlannedCard icon={<Moon className="size-5" aria-hidden />} title={t("mdAdmin.planned.astroTitle")} body={t("mdAdmin.planned.astroBody")} badge={t("mdAdmin.planned.astroBadge")} />
          <PlannedCard icon={<Users className="size-5" aria-hidden />} title={t("mdAdmin.planned.religionTitle")} body={t("mdAdmin.planned.religionBody")} badge={t("mdAdmin.planned.religionBadge")} />
        </ul>
      </section>
    </div>
  );
}

export function VocabularyAdminPage() {
  const { t } = useTranslation();
  const { key = "" } = useParams();
  const [params, setParams] = useSearchParams();
  const [q, setQ] = useState(params.get("q") ?? "");
  const status = params.get("status") ?? "";
  const sort = params.get("sort") ?? "order";
  const [cursors, setCursors] = useState<(string | null)[]>([null]);
  const debounced = useDebounced(q, 300);
  const terms = useAdminTerms(key, { q: debounced, status, sort, cursor: cursors[cursors.length - 1] });
  const [editing, setEditing] = useState<AdminTerm | null | "new">(null);
  const [lifecycle, setLifecycle] = useState<AdminTerm | null>(null);
  const [historyOf, setHistoryOf] = useState<string | null>(null);
  const [announce, setAnnounce] = useState("");
  const setParam = (k: string, v: string) => {
    const next = new URLSearchParams(params);
    if (v) next.set(k, v);
    else next.delete(k);
    setParams(next, { replace: true });
    setCursors([null]);
  };
  if (terms.error instanceof ApiError && terms.error.status === 404) return <ErrorAlert error={terms.error} />;
  const vocab = terms.data?.vocabulary;
  const done = (c: MasterDataChange) => {
    setEditing(null);
    setLifecycle(null);
    setAnnounce(c.status === "published" ? t("mdAdmin.announce.published", { code: c.term_code }) : t("mdAdmin.announce.draft", { code: c.term_code }));
  };
  return (
    <div>
      <LiveRegion message={announce} />
      <div className="mb-4 flex flex-col gap-2 sm:flex-row sm:items-end sm:justify-between">
        <div>
          <Link to={BASE} className="text-sm text-kumkum-800 underline-offset-2 hover:underline">
            ← {t("mdAdmin.nav.dashboard")}
          </Link>
          <h2 className="font-display text-xl font-semibold">{vocab ? vocabName(t, vocab) : key}</h2>
          {vocab && (
            <p className="text-xs text-ink-muted">
              {vocab.description} · {t("mdAdmin.revision", { n: vocab.revision })}
              {vocab.source && <> · {t("mdAdmin.source")}: {vocab.source}</>}
              {vocab.licence && <> · {vocab.licence}</>}
            </p>
          )}
        </div>
        {vocab && !vocab.fixed_membership && (
          <Button icon={<Plus className="size-4" aria-hidden />} onClick={() => setEditing("new")}>
            {t("mdAdmin.addTerm")}
          </Button>
        )}
      </div>
      {vocab?.fixed_membership && <p className="mb-3 rounded-lg border border-sky-200 bg-sky-50 px-3 py-2 text-sm">{t("mdAdmin.fixedSetHint")}</p>}

      <div className="mb-3 grid gap-2 sm:grid-cols-[1fr_auto_auto]">
        <Field label={t("mdAdmin.search")} hint={t("mdAdmin.searchHint")}>
          {(p) => (
            <TextInput
              {...p}
              type="search"
              value={q}
              onChange={(e) => {
                setQ(e.target.value);
                setCursors([null]);
              }}
            />
          )}
        </Field>
        <Field label={t("mdAdmin.filterStatus")}>
          {(p) => (
            <Select {...p} value={status} onChange={(e) => setParam("status", e.target.value)}>
              <option value="">{t("common.all")}</option>
              <option value="draft">{t("mdAdmin.status.draft")}</option>
              <option value="reviewed">{t("mdAdmin.status.reviewed")}</option>
              <option value="retired">{t("mdAdmin.status.retired")}</option>
            </Select>
          )}
        </Field>
        <Field label={t("mdAdmin.sort")}>
          {(p) => (
            <Select {...p} value={sort} onChange={(e) => setParam("sort", e.target.value)}>
              <option value="order">{t("mdAdmin.sortOrder")}</option>
              <option value="code">{t("mdAdmin.sortCode")}</option>
              <option value="updated">{t("mdAdmin.sortUpdated")}</option>
            </Select>
          )}
        </Field>
      </div>

      {terms.isLoading ? (
        <Spinner />
      ) : terms.error ? (
        <ErrorAlert error={terms.error} />
      ) : !terms.data?.items.length ? (
        <EmptyState title={t("mdAdmin.emptyTitle")}>{q ? t("mdAdmin.emptySearch") : t("mdAdmin.emptyList")}</EmptyState>
      ) : (
        <>
          <p className="mb-1 text-xs text-ink-muted" aria-live="polite">
            {t("mdAdmin.total", { count: terms.data.total })}
          </p>
          <div className="overflow-x-auto rounded-xl border border-stone-200 bg-white">
            <table className="w-full min-w-[40rem] text-left text-sm">
              <caption className="sr-only">{t("mdAdmin.tableCaption", { name: vocab ? vocabName(t, vocab) : key })}</caption>
              <thead className="bg-parchment-deep/60 text-xs text-ink-muted">
                <tr>
                  <th scope="col" className="px-3 py-2 font-medium">{t("mdAdmin.col.label")}</th>
                  <th scope="col" className="px-3 py-2 font-medium">{t("mdAdmin.col.aliases")}</th>
                  <th scope="col" className="px-3 py-2 font-medium">{t("mdAdmin.col.status")}</th>
                  <th scope="col" className="px-3 py-2 font-medium">{t("mdAdmin.col.origin")}</th>
                  <th scope="col" className="px-3 py-2 font-medium"><span className="sr-only">{t("common.actions")}</span></th>
                </tr>
              </thead>
              <tbody>
                {terms.data.items.map((term) => (
                  <tr key={term.code} className="border-t border-stone-100 align-top">
                    <th scope="row" className="px-3 py-2 font-normal">
                      <span className="font-semibold">{term.labels.en}</span> · <span lang="hi">{term.labels.hi}</span>
                      <code className="block text-xs text-ink-muted">{term.code}</code>
                      {term.successor_code && <span className="text-xs text-ink-muted">→ {term.successor_code}</span>}
                    </th>
                    <td className="px-3 py-2 text-xs text-ink-muted">{term.aliases.join(", ") || "—"}</td>
                    <td className="px-3 py-2">
                      <Badge tone={STATUS_TONE[term.status]}>{t(`mdAdmin.status.${term.status}`)}</Badge>
                      {term.pending_change_id && (
                        <span className="mt-1 block">
                          <Badge tone="saffron">{t("mdAdmin.pendingChange")}</Badge>
                        </span>
                      )}
                    </td>
                    <td className="px-3 py-2 text-xs">{t(`mdAdmin.managedBy.${term.managed_by}`)}</td>
                    <td className="px-3 py-2">
                      <div className="flex flex-wrap justify-end gap-1">
                        {term.status !== "retired" && (
                          <Button size="sm" variant="secondary" disabled={!!term.pending_change_id} icon={<Pencil className="size-3.5" aria-hidden />} onClick={() => setEditing(term)}>
                            {t("common.edit")}
                            <span className="sr-only"> {term.labels.en}</span>
                          </Button>
                        )}
                        {!vocab?.fixed_membership && (
                          <Button size="sm" variant="ghost" disabled={!!term.pending_change_id} onClick={() => setLifecycle(term)}>
                            {term.status === "retired" ? t("mdAdmin.reactivate") : t("mdAdmin.retire")}
                            <span className="sr-only"> {term.labels.en}</span>
                          </Button>
                        )}
                        <Button size="sm" variant="ghost" onClick={() => setHistoryOf(term.code)}>
                          {t("mdAdmin.history")}
                          <span className="sr-only"> {term.labels.en}</span>
                        </Button>
                      </div>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          <div className="mt-3 flex justify-between">
            <Button variant="secondary" size="sm" disabled={cursors.length < 2} onClick={() => setCursors(cursors.slice(0, -1))}>
              {t("mdAdmin.prev")}
            </Button>
            <Button variant="secondary" size="sm" disabled={!terms.data.next_cursor} onClick={() => setCursors([...cursors, terms.data?.next_cursor ?? null])}>
              {t("mdAdmin.next")}
            </Button>
          </div>
        </>
      )}

      {editing !== null && <TermEditorDialog vocabulary={key} term={editing === "new" ? null : editing} onClose={() => setEditing(null)} onDone={done} />}
      {lifecycle && <LifecycleDialog vocabulary={key} term={lifecycle} activeTerms={terms.data?.items ?? []} onClose={() => setLifecycle(null)} onDone={done} />}
      {historyOf && <TermHistoryDialog vocabulary={key} code={historyOf} onClose={() => setHistoryOf(null)} />}
    </div>
  );
}

function TermHistoryDialog({ vocabulary, code, onClose }: { vocabulary: string; code: string; onClose: () => void }) {
  const { t } = useTranslation();
  const q = useAdminTerm(vocabulary, code);
  return (
    <Dialog open onClose={onClose} size="lg" title={t("mdAdmin.historyTitle", { code })}>
      {q.isLoading ? (
        <Spinner />
      ) : q.error ? (
        <ErrorAlert error={q.error} />
      ) : q.data?.history.length ? (
        <ol className="space-y-3">
          {q.data.history.map((c) => (
            <li key={c.id}>
              <ChangeCard change={c} />
            </li>
          ))}
        </ol>
      ) : (
        <p className="text-sm text-ink-muted">{t("mdAdmin.historyEmpty")}</p>
      )}
    </Dialog>
  );
}

function ChangeCard({ change, actions }: { change: MasterDataChange; actions?: ReactNode }) {
  const { t, i18n } = useTranslation();
  const when = (iso: string) => new Date(iso).toLocaleString(i18n.language);
  return (
    <article className="rounded-xl border border-stone-200 bg-white p-3" aria-label={t("mdAdmin.changeLabel", { action: t(`mdAdmin.action.${change.action}`), code: change.term_code })}>
      <div className="flex flex-wrap items-center gap-2">
        <Badge tone={CHANGE_TONE[change.status]}>{t(`mdAdmin.changeStatus.${change.status}`)}</Badge>
        <span className="font-semibold">{t(`mdAdmin.action.${change.action}`)}</span>
        <code className="text-xs">
          {change.vocabulary_key}:{change.term_code}
        </code>
        {change.stale && <Badge tone="red">{t("mdAdmin.stale")}</Badge>}
      </div>
      <p className="mt-1 text-sm">
        <span className="text-ink-muted">{t("mdAdmin.reasonLabel")}:</span> {change.reason}
      </p>
      {change.source_reference && (
        <p className="text-xs text-ink-muted">
          {t("mdAdmin.sourceRefLabel")}: {change.source_reference}
        </p>
      )}
      <p className="text-xs text-ink-muted">
        {t("mdAdmin.proposedBy", { name: change.proposed_by_name ?? "—", when: when(change.proposed_at) })}
        {change.decided_at && <> · {t("mdAdmin.decidedBy", { name: change.decided_by_name ?? "—", when: when(change.decided_at) })}</>}
      </p>
      {change.decision_note && <p className="text-xs">“{change.decision_note}”</p>}
      <div className="mt-2">
        <ChangeDiff change={change} />
      </div>
      {actions && <div className="mt-2 flex flex-wrap gap-2">{actions}</div>}
    </article>
  );
}

export function PendingReviewsPage() {
  const { t } = useTranslation();
  const [cursors, setCursors] = useState<(string | null)[]>([null]);
  const q = useAdminChanges({ status: "pending", cursor: cursors[cursors.length - 1] });
  const decide = useDecideChange();
  const [rejecting, setRejecting] = useState<MasterDataChange | null>(null);
  const [note, setNote] = useState("");
  const [announce, setAnnounce] = useState("");
  if (q.isLoading) return <Spinner />;
  if (q.error) return <ErrorAlert error={q.error} />;
  const items = q.data?.items ?? [];
  return (
    <div>
      <LiveRegion message={announce} />
      <h2 className="mb-1 font-display text-xl font-semibold">{t("mdAdmin.nav.reviews")}</h2>
      <p className="mb-3 text-sm text-ink-muted">{t("mdAdmin.reviewsHint")}</p>
      <ErrorAlert error={decide.error} />
      {!items.length ? (
        <EmptyState title={t("mdAdmin.reviewsEmpty")} />
      ) : (
        <ul className="space-y-3">
          {items.map((c) => (
            <li key={c.id}>
              <ChangeCard
                change={c}
                actions={
                  <>
                    <Button size="sm" disabled={c.stale} loading={decide.isPending} onClick={() => decide.mutate({ id: c.id, decision: "publish" }, { onSuccess: () => setAnnounce(t("mdAdmin.announce.published", { code: c.term_code })) })}>
                      {t("mdAdmin.publish")}
                    </Button>
                    <Button size="sm" variant="secondary" onClick={() => setRejecting(c)}>
                      {t("mdAdmin.reject")}
                    </Button>
                    {c.proposed_by_me && (
                      <Button size="sm" variant="ghost" onClick={() => decide.mutate({ id: c.id, decision: "withdraw" })}>
                        {t("mdAdmin.withdraw")}
                      </Button>
                    )}
                  </>
                }
              />
            </li>
          ))}
        </ul>
      )}
      <Pager cursors={cursors} setCursors={setCursors} next={q.data?.next_cursor ?? null} />
      {rejecting && (
        <Dialog
          open
          onClose={() => setRejecting(null)}
          title={t("mdAdmin.rejectTitle", { code: rejecting.term_code })}
          footer={
            <>
              <Button variant="secondary" onClick={() => setRejecting(null)}>
                {t("common.cancel")}
              </Button>
              <Button
                variant="danger"
                disabled={note.trim().length < 3}
                loading={decide.isPending}
                onClick={() =>
                  decide.mutate(
                    { id: rejecting.id, decision: "reject", note: note.trim() },
                    {
                      onSuccess: () => {
                        setRejecting(null);
                        setNote("");
                      },
                    },
                  )
                }
              >
                {t("mdAdmin.reject")}
              </Button>
            </>
          }
        >
          <Field label={t("mdAdmin.rejectNote")} required>
            {(p) => <TextArea {...p} value={note} onChange={(e) => setNote(e.target.value)} rows={3} maxLength={2000} />}
          </Field>
        </Dialog>
      )}
    </div>
  );
}

function Pager({ cursors, setCursors, next }: { cursors: (string | null)[]; setCursors: (c: (string | null)[]) => void; next: string | null }) {
  const { t } = useTranslation();
  if (cursors.length < 2 && !next) return null;
  return (
    <div className="mt-3 flex justify-between">
      <Button variant="secondary" size="sm" disabled={cursors.length < 2} onClick={() => setCursors(cursors.slice(0, -1))}>
        {t("mdAdmin.prev")}
      </Button>
      <Button variant="secondary" size="sm" disabled={!next} onClick={() => setCursors([...cursors, next])}>
        {t("mdAdmin.next")}
      </Button>
    </div>
  );
}

export function ChangeHistoryPage() {
  const { t } = useTranslation();
  const [status, setStatus] = useState("");
  const [vocabulary, setVocabulary] = useState("");
  const [cursors, setCursors] = useState<(string | null)[]>([null]);
  const vocabs = useAdminVocabularies();
  const q = useAdminChanges({ status, vocabulary, cursor: cursors[cursors.length - 1] });
  return (
    <div>
      <h2 className="mb-3 font-display text-xl font-semibold">{t("mdAdmin.nav.history")}</h2>
      <div className="mb-3 grid gap-2 sm:grid-cols-2">
        <Field label={t("mdAdmin.filterStatus")}>
          {(p) => (
            <Select
              {...p}
              value={status}
              onChange={(e) => {
                setStatus(e.target.value);
                setCursors([null]);
              }}
            >
              <option value="">{t("common.all")}</option>
              {["pending", "published", "rejected", "withdrawn"].map((s) => (
                <option key={s} value={s}>
                  {t(`mdAdmin.changeStatus.${s}`)}
                </option>
              ))}
            </Select>
          )}
        </Field>
        <Field label={t("mdAdmin.filterVocabulary")}>
          {(p) => (
            <Select
              {...p}
              value={vocabulary}
              onChange={(e) => {
                setVocabulary(e.target.value);
                setCursors([null]);
              }}
            >
              <option value="">{t("common.all")}</option>
              {(vocabs.data ?? []).map((v) => (
                <option key={v.key} value={v.key}>
                  {vocabName(t, v)}
                </option>
              ))}
            </Select>
          )}
        </Field>
      </div>
      {q.isLoading ? (
        <Spinner />
      ) : q.error ? (
        <ErrorAlert error={q.error} />
      ) : !q.data?.items.length ? (
        <EmptyState title={t("mdAdmin.historyEmpty")} />
      ) : (
        <ol className="space-y-3">
          {q.data.items.map((c) => (
            <li key={c.id}>
              <ChangeCard change={c} />
            </li>
          ))}
        </ol>
      )}
      <Pager cursors={cursors} setCursors={setCursors} next={q.data?.next_cursor ?? null} />
    </div>
  );
}
