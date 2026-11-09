import { Fragment, useState, type FormEvent, type ReactNode } from "react";
import { Link, useNavigate, useParams } from "react-router-dom";
import { useTranslation } from "react-i18next";
import { History, NotebookPen, Pencil, Plus, Trash2, X } from "lucide-react";
import type { PersonSummary, RecordPrivacyLevel, SharingOut, SharingUpdate, TraditionKind, TraditionOut } from "../../api/types";
import { api } from "../../api/client";
import { useMembers } from "../../api/hooks/trees";
import { useMe } from "../../api/hooks/auth";
import {
  useCreateTradition,
  useTradition,
  useTraditionHistory,
  useTraditions,
  useUpdateTradition,
  useWithdrawTradition,
} from "../../api/hooks/culture";
import { useCreateProposal } from "../../api/hooks/review";
import { useBranches } from "../../api/hooks/family";
import { useTreeCtx } from "../../lib/tree-context";
import { Perm } from "../../lib/permissions";
import { useDebounced } from "../../lib/useDebounced";
import { PersonPicker } from "../../components/pickers";
import { CitationList } from "../../components/evidence/Citations";
import { RecordPrivacyBadge } from "../../components/person/badges";
import { RecordSharingPanel } from "../../components/privacy/RecordSharingPanel";
import { RECORD_AUDIENCES, VisibilitySharing, draftProblem, type SharingDraft } from "../../components/privacy/VisibilitySharing";
import { Button } from "../../components/ui/Button";
import { Badge } from "../../components/ui/Badge";
import { ConfirmDialog, Dialog } from "../../components/ui/Dialog";
import { EmptyState, ErrorAlert, PageHeader, Spinner } from "../../components/ui/feedback";
import { Field, Select, TextArea, TextInput } from "../../components/ui/form";

export const TRADITION_KINDS: TraditionKind[] = ["ritual_guide", "custom", "song", "recipe", "story", "other"];
const LANGUAGES = ["hi", "en", "mr", "bn", "gu", "pa", "ta", "te", "kn", "ml", "or", "ur", "sa", "bho", "mai", "awa"];

/**
 * Light formatting rendered as text nodes only (ADR-0026 §7): paragraphs, "- " lists and **bold**.
 * Nothing in an entry is ever interpreted as HTML.
 */
export function FormattedText({ text, lang }: { text: string; lang?: string | null }) {
  const blocks = text.split(/\n{2,}/);
  const inline = (line: string): ReactNode[] =>
    line.split(/(\*\*[^*]+\*\*)/g).map((part, i) =>
      part.startsWith("**") && part.endsWith("**") && part.length > 4 ? <strong key={i}>{part.slice(2, -2)}</strong> : <Fragment key={i}>{part}</Fragment>,
    );
  return (
    <div className="space-y-3 text-sm leading-relaxed" lang={lang ?? undefined}>
      {blocks.map((block, i) => {
        const lines = block.split("\n");
        if (lines.every((l) => /^\s*[-•]\s+/.test(l))) {
          return (
            <ul key={i} className="list-disc space-y-1 pl-5">
              {lines.map((l, j) => (
                <li key={j}>{inline(l.replace(/^\s*[-•]\s+/, ""))}</li>
              ))}
            </ul>
          );
        }
        return (
          <p key={i} className="whitespace-pre-line">
            {inline(block)}
          </p>
        );
      })}
    </div>
  );
}

export function TraditionsPage() {
  const { t } = useTranslation();
  const { treeId, can } = useTreeCtx();
  const [kind, setKind] = useState<TraditionKind | "">("");
  const [q, setQ] = useState("");
  const dq = useDebounced(q.trim(), 250);
  const list = useTraditions(treeId, { kind, q: dq });
  const [adding, setAdding] = useState(false);
  const navigate = useNavigate();
  const items = list.data?.items ?? [];
  return (
    <div className="mx-auto max-w-3xl">
      <PageHeader
        title={t("traditions.title")}
        subtitle={t("traditions.subtitle")}
        actions={
          can(Perm.FAMILY_WRITE) && (
            <Button icon={<Plus className="size-4" aria-hidden />} onClick={() => setAdding(true)}>
              {t("traditions.add")}
            </Button>
          )
        }
      />
      <div className="card mb-4 grid grid-cols-1 gap-3 p-4 sm:grid-cols-2">
        <Field label={t("traditions.search")}>{(p) => <TextInput {...p} type="search" value={q} onChange={(e) => setQ(e.target.value)} />}</Field>
        <Field label={t("traditions.kind")}>
          {(p) => (
            <Select {...p} value={kind} onChange={(e) => setKind(e.target.value as TraditionKind | "")}>
              <option value="">{t("traditions.allKinds")}</option>
              {TRADITION_KINDS.map((k) => (
                <option key={k} value={k}>
                  {t(`traditions.kinds.${k}`)}
                </option>
              ))}
            </Select>
          )}
        </Field>
      </div>
      {list.isLoading && <Spinner />}
      <ErrorAlert error={list.error} />
      {list.isSuccess && items.length === 0 && (
        <EmptyState icon={<NotebookPen className="size-8" aria-hidden />} title={dq || kind ? t("traditions.noMatch") : t("traditions.empty")}>
          <p className="text-sm text-ink-muted">{t("traditions.emptyHint")}</p>
        </EmptyState>
      )}
      <TraditionList items={items} />
      {adding && <TraditionEditor entry={null} onClose={() => setAdding(false)} onSaved={(e) => navigate(`/t/${treeId}/traditions/${e.id}`)} />}
    </div>
  );
}

function TraditionList({ items }: { items: { id: string; title: string; kind: TraditionKind; excerpt: string; language?: string | null; author_name?: string | null; privacy_level: RecordPrivacyLevel }[] }) {
  const { t } = useTranslation();
  const { treeId } = useTreeCtx();
  return (
    <ul className="space-y-3">
      {items.map((e) => (
        <li key={e.id} className="card p-4">
          <div className="flex flex-wrap items-center gap-2">
            <Link to={`/t/${treeId}/traditions/${e.id}`} className="font-display text-lg font-semibold text-kumkum-900 underline-offset-2 hover:underline" lang={e.language ?? undefined}>
              {e.title}
            </Link>
            <Badge tone="saffron">{t(`traditions.kinds.${e.kind}`)}</Badge>
            {e.privacy_level !== "TREE_MEMBERS" && <RecordPrivacyBadge level={e.privacy_level} />}
          </div>
          {e.excerpt && (
            <p className="mt-1 text-sm text-ink-muted" lang={e.language ?? undefined}>
              {e.excerpt}
            </p>
          )}
          {e.author_name && <p className="mt-1 text-xs text-ink-muted">{t("traditions.by", { name: e.author_name })}</p>}
        </li>
      ))}
    </ul>
  );
}

/** Traditions that mention one person, on their profile. */
export function PersonTraditions({ personId }: { personId: string }) {
  const { t } = useTranslation();
  const { treeId } = useTreeCtx();
  const list = useTraditions(treeId, { person_id: personId });
  const items = list.data?.items ?? [];
  if (!items.length) return null;
  return (
    <section aria-labelledby="person-traditions" className="space-y-2">
      <h2 id="person-traditions" className="font-display text-lg font-semibold">
        {t("traditions.forPerson")}
      </h2>
      <TraditionList items={items} />
    </section>
  );
}

export function TraditionDetailPage() {
  const { t } = useTranslation();
  const { entryId = "" } = useParams();
  const { treeId, can } = useTreeCtx();
  const entry = useTradition(treeId, entryId);
  const withdraw = useWithdrawTradition(treeId);
  const [editing, setEditing] = useState(false);
  const [confirm, setConfirm] = useState(false);
  const [showHistory, setShowHistory] = useState(false);
  const navigate = useNavigate();
  if (entry.isLoading) return <Spinner />;
  if (!entry.data) return <ErrorAlert error={entry.error} />;
  const e = entry.data;
  const links = e.links ?? [];
  return (
    <article className="mx-auto max-w-3xl" aria-labelledby="tradition-title">
      <p className="mb-2 text-sm">
        <Link to={`/t/${treeId}/traditions`} className="text-kumkum-800 underline">
          {t("traditions.back")}
        </Link>
      </p>
      <header className="mb-4">
        <div className="flex flex-wrap items-center gap-2">
          <Badge tone="saffron">{t(`traditions.kinds.${e.kind}`)}</Badge>
          <RecordPrivacyBadge level={e.privacy_level} />
          {e.review_state === "family_reviewed" && <Badge tone="green">{t("review.state.family_reviewed")}</Badge>}
        </div>
        <h1 id="tradition-title" className="mt-2 font-display text-2xl font-bold sm:text-3xl" lang={e.language ?? undefined}>
          {e.title}
        </h1>
        {e.author_name && <p className="mt-1 text-xs text-ink-muted">{t("traditions.by", { name: e.author_name })}</p>}
      </header>
      <div className="card p-5">
        {e.body ? <FormattedText text={e.body} lang={e.language} /> : <p className="text-sm text-ink-muted">{t("traditions.noText")}</p>}
      </div>
      {links.length > 0 && (
        <section className="mt-4" aria-labelledby="tradition-links">
          <h2 id="tradition-links" className="text-sm font-semibold">
            {t("traditions.links")}
          </h2>
          <ul className="mt-1 flex flex-wrap gap-2">
            {links.map((l) => (
              <li key={`${l.target_type}-${l.target_id}`}>
                {l.target_type === "person" ? (
                  <Link className="rounded-full border border-stone-300 px-2.5 py-1 text-sm hover:bg-white" to={`/t/${treeId}/people/${l.target_id}`}>
                    {l.label}
                  </Link>
                ) : (
                  <span className="rounded-full border border-stone-300 px-2.5 py-1 text-sm">{l.label}</span>
                )}
              </li>
            ))}
          </ul>
        </section>
      )}
      <div className="mt-4 flex flex-wrap gap-2">
        {e.can_edit && (
          <Button variant="secondary" icon={<Pencil className="size-4" aria-hidden />} onClick={() => setEditing(true)}>
            {e.edit_needs_review ? t("traditions.proposeEdit") : t("common.edit")}
          </Button>
        )}
        <Button variant="ghost" icon={<History className="size-4" aria-hidden />} aria-expanded={showHistory} onClick={() => setShowHistory(!showHistory)}>
          {t("traditions.history")}
        </Button>
        {e.can_withdraw && (
          <Button variant="ghost" icon={<Trash2 className="size-4" aria-hidden />} onClick={() => setConfirm(true)}>
            {t("traditions.withdraw")}
          </Button>
        )}
      </div>
      {showHistory && <TraditionHistory id={e.id} />}
      {e.can_edit_sharing && (
        <div className="mt-6">
          <RecordSharingPanel path={`traditions/${e.id}`} downloads={false} />
        </div>
      )}
      <section className="mt-6" aria-labelledby="tradition-sources">
        <h2 id="tradition-sources" className="text-sm font-semibold">
          {t("traditions.sources")}
        </h2>
        <CitationList targetType="tradition" targetId={e.id} canEditTarget={can(Perm.FAMILY_WRITE)} />
      </section>
      {editing && <TraditionEditor entry={e} onClose={() => setEditing(false)} onSaved={() => setEditing(false)} />}
      <ConfirmDialog
        open={confirm}
        onClose={() => setConfirm(false)}
        title={t("traditions.withdrawTitle")}
        body={t("traditions.withdrawBody")}
        confirmLabel={t("traditions.withdraw")}
        danger
        loading={withdraw.isPending}
        onConfirm={() => withdraw.mutate(e.id, { onSuccess: () => navigate(`/t/${treeId}/traditions`) })}
      >
        <ErrorAlert error={withdraw.error} />
      </ConfirmDialog>
    </article>
  );
}

function TraditionHistory({ id }: { id: string }) {
  const { t, i18n } = useTranslation();
  const { treeId } = useTreeCtx();
  const history = useTraditionHistory(treeId, id, true);
  if (history.isLoading) return <Spinner />;
  return (
    <section className="card mt-3 p-4" aria-label={t("traditions.history")}>
      <ErrorAlert error={history.error} />
      <ol className="space-y-2 text-sm">
        {(history.data ?? []).map((r) => (
          <li key={r.id}>
            <span className="font-medium">{t(`traditions.op.${r.op}`, { defaultValue: r.op })}</span>{" "}
            <span className="text-ink-muted">
              {new Date(r.created_at).toLocaleString(i18n.language)}
              {r.actor_name && ` · ${r.actor_name}`}
              {r.reviewer_name && ` · ${t("review.reviewedBy", { name: r.reviewer_name })}`}
            </span>
            {r.op === "update" && r.changed.length > 0 && (
              <span className="block text-xs text-ink-muted">{r.changed.map((f) => t(`traditions.field.${f}`, { defaultValue: f })).join(", ")}</span>
            )}
          </li>
        ))}
      </ol>
    </section>
  );
}

/** Add an entry, edit one, or propose an edit to someone else's when the family reviews changes. */
function TraditionEditor({ entry, onClose, onSaved }: { entry: TraditionOut | null; onClose: () => void; onSaved: (e: TraditionOut) => void }) {
  const { t } = useTranslation();
  const { treeId } = useTreeCtx();
  const create = useCreateTradition(treeId);
  const update = useUpdateTradition(treeId, entry?.id ?? "");
  const propose = useCreateProposal(treeId);
  const branches = useBranches(treeId);
  const [kind, setKind] = useState<TraditionKind>(entry?.kind ?? "custom");
  const [title, setTitle] = useState(entry?.title ?? "");
  const [body, setBody] = useState(entry?.body ?? "");
  const [language, setLanguage] = useState(entry?.language ?? "");
  const { tree } = useTreeCtx();
  const members = useMembers(treeId);
  const me = useMe();
  // ADR-0027: a new entry chooses its audience here; an existing one changes it in Visibility & Sharing
  const [sharing, setSharing] = useState<SharingDraft>({
    privacy_level: RECORD_AUDIENCES.includes(tree.default_person_privacy as RecordPrivacyLevel) ? (tree.default_person_privacy as RecordPrivacyLevel) : "TREE_MEMBERS",
    audience_branch_id: null,
    allow_download: false,
    members: [],
  });
  const [shareError, setShareError] = useState<unknown>(null);
  const [branch, setBranch] = useState(entry?.branch_id ?? "");
  const [people, setPeople] = useState<{ id: string; label: string }[]>(
    (entry?.links ?? []).filter((l) => l.target_type === "person").map((l) => ({ id: l.target_id, label: l.label })),
  );
  const [rationale, setRationale] = useState("");
  const [err, setErr] = useState<string | null>(null);
  const [sent, setSent] = useState(false);
  const asProposal = !!entry?.edit_needs_review;
  const otherLinks = (entry?.links ?? []).filter((l) => l.target_type !== "person").map((l) => ({ target_type: l.target_type, target_id: l.target_id }));
  const links = [...people.map((p) => ({ target_type: "person" as const, target_id: p.id })), ...otherLinks];
  const busy = create.isPending || update.isPending || propose.isPending;

  const submit = (ev: FormEvent) => {
    ev.preventDefault();
    if (!title.trim()) {
      setErr(t("traditions.titleRequired"));
      return;
    }
    if (body.length > 50_000) {
      setErr(t("traditions.tooLong"));
      return;
    }
    if (!entry && draftProblem(sharing)) {
      setErr(sharing.privacy_level === "FAMILY_BRANCH" ? t("sharing.chooseBranch") : t("sharing.membersRequired"));
      return;
    }
    setErr(null);
    setShareError(null);
    const values = { kind, title: title.trim(), body, language: language || null, branch_id: branch || null, links };
    if (!entry) {
      const level = sharing.privacy_level === "SELECTED_MEMBERS" ? "ONLY_ME" : sharing.privacy_level; // members are attached next
      const branchId = sharing.privacy_level === "FAMILY_BRANCH" ? sharing.audience_branch_id : values.branch_id;
      create.mutate(
        { ...values, branch_id: branchId, privacy_level: level },
        {
          onSuccess: async (created) => {
            if (sharing.privacy_level === "SELECTED_MEMBERS") {
              const share: SharingUpdate = { privacy_level: "SELECTED_MEMBERS", allow_download: false, members: sharing.members, confirm_wider: true };
              try {
                await api.put<SharingOut>(`/trees/${treeId}/traditions/${created.id}/sharing`, share);
              } catch (e) {
                setShareError(e); // the entry stays Only me: safe; its owner can share it from its page
                return;
              }
            }
            onSaved(created);
          },
        },
      );
    } else if (asProposal) {
      if (!rationale.trim()) {
        setErr(t("traditions.rationaleRequired"));
        return;
      }
      propose.mutate(
        { rationale: rationale.trim(), submit: true, items: [{ target_type: "tradition", op: "update", target_id: entry.id, patch: values }] },
        { onSuccess: () => setSent(true) },
      );
    } else {
      update.mutate(values, { onSuccess: onSaved });
    }
  };

  return (
    <Dialog
      open
      onClose={onClose}
      title={entry ? (asProposal ? t("traditions.proposeEdit") : t("traditions.editTitle")) : t("traditions.addTitle")}
      footer={
        sent ? (
          <Button onClick={onClose}>{t("common.close")}</Button>
        ) : (
          <>
            <Button variant="secondary" onClick={onClose}>
              {t("common.cancel")}
            </Button>
            <Button type="submit" form="tradition-form" loading={busy}>
              {asProposal ? t("review.sendForReview") : t("common.save")}
            </Button>
          </>
        )
      }
    >
      {sent ? (
        <p role="status" className="text-sm">
          {t("traditions.sent")}
        </p>
      ) : (
        <form id="tradition-form" onSubmit={submit} noValidate className="space-y-3">
          {asProposal && <p className="rounded-lg bg-haldi-100 p-3 text-xs">{t("traditions.reviewNotice")}</p>}
          <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
            <Field label={t("traditions.kind")}>
              {(p) => (
                <Select {...p} value={kind} onChange={(e) => setKind(e.target.value as TraditionKind)}>
                  {TRADITION_KINDS.map((k) => (
                    <option key={k} value={k}>
                      {t(`traditions.kinds.${k}`)}
                    </option>
                  ))}
                </Select>
              )}
            </Field>
            <Field label={t("traditions.language")}>
              {(p) => (
                <Select {...p} value={language} onChange={(e) => setLanguage(e.target.value)}>
                  <option value="">{t("traditions.languageUnset")}</option>
                  {LANGUAGES.map((l) => (
                    <option key={l} value={l}>
                      {t(`traditions.languages.${l}`, { defaultValue: l })}
                    </option>
                  ))}
                </Select>
              )}
            </Field>
          </div>
          <Field label={t("traditions.titleLabel")} required>
            {(p) => <TextInput {...p} lang={language || undefined} value={title} maxLength={300} onChange={(e) => setTitle(e.target.value)} />}
          </Field>
          <Field label={t("traditions.body")} hint={t("traditions.bodyHint")}>
            {(p) => <TextArea {...p} lang={language || undefined} rows={10} value={body} onChange={(e) => setBody(e.target.value)} />}
          </Field>
          <fieldset className="space-y-2">
            <legend className="text-sm font-medium">{t("traditions.people")}</legend>
            {people.length > 0 && (
              <ul className="flex flex-wrap gap-1">
                {people.map((p) => (
                  <li key={p.id} className="flex items-center gap-1 rounded-full border border-stone-300 py-0.5 pl-2.5 pr-1 text-sm">
                    {p.label}
                    <button type="button" className="rounded-full p-0.5 hover:bg-red-50" aria-label={t("traditions.unlink", { name: p.label })} onClick={() => setPeople(people.filter((x) => x.id !== p.id))}>
                      <X className="size-3.5" aria-hidden />
                    </button>
                  </li>
                ))}
              </ul>
            )}
            <PersonPicker
              treeId={treeId}
              label={t("traditions.linkPerson")}
              value={null}
              excludeIds={people.map((p) => p.id)}
              onChange={(p: PersonSummary | null) => p && setPeople([...people, { id: p.id, label: p.display_name }])}
            />
            <p className="text-xs text-ink-muted">{t("traditions.peopleHint")}</p>
          </fieldset>
          <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
            <Field label={t("traditions.branch")} hint={entry?.privacy_level === "FAMILY_BRANCH" ? t("traditions.branchIsAudience") : undefined}>
              {(p) => (
                <Select {...p} value={branch} disabled={entry?.privacy_level === "FAMILY_BRANCH"} onChange={(e) => setBranch(e.target.value)}>
                  <option value="">{t("traditions.noBranch")}</option>
                  {(branches.data ?? []).map((b) => (
                    <option key={b.id} value={b.id}>
                      {b.name}
                    </option>
                  ))}
                </Select>
              )}
            </Field>
          </div>
          {!entry && (
            <fieldset className="space-y-2 rounded-lg border border-stone-200 p-3">
              <legend className="px-1 text-sm font-semibold">{t("sharing.title")}</legend>
              <p className="text-xs text-ink-muted">{t("sharing.uploadNote")}</p>
              <VisibilitySharing
                value={sharing}
                onChange={setSharing}
                members={members.data ?? []}
                branches={branches.data ?? []}
                ownMembershipId={members.data?.find((m) => m.user_id === me.data?.id)?.id ?? null}
                downloads={false}
              />
            </fieldset>
          )}
          {asProposal && (
            <Field label={t("review.rationale")} required>
              {(p) => <TextArea {...p} rows={2} value={rationale} onChange={(e) => setRationale(e.target.value)} />}
            </Field>
          )}
          {err && (
            <p role="alert" className="field-error">
              {err}
            </p>
          )}
          <ErrorAlert error={create.error ?? update.error ?? propose.error ?? shareError} />
        </form>
      )}
    </Dialog>
  );
}
