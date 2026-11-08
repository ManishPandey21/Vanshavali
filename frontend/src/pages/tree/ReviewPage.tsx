import { useState } from "react";
import { useTranslation } from "react-i18next";
import { Link, useParams } from "react-router-dom";
import { AlertTriangle, ClipboardCheck, EyeOff } from "lucide-react";
import { ApiError } from "../../api/client";
import type { ChangeProposalOut } from "../../api/types";
import { useComment, useDecide, useProposal, useProposals, type Decision, type ProposalView } from "../../api/hooks/review";
import { useTreeCtx } from "../../lib/tree-context";
import { Badge, type Tone } from "../../components/ui/Badge";
import { Button } from "../../components/ui/Button";
import { EmptyState, ErrorAlert, PageHeader, Spinner } from "../../components/ui/feedback";
import { Field, TextArea } from "../../components/ui/form";
import { Tabs } from "../../components/ui/Tabs";
import { formatValue, useFieldLabel } from "../../components/review/ReviewParts";

const VIEWS: ProposalView[] = ["to_review", "mine", "closed"];

export function statusTone(s: string): Tone {
  if (s === "accepted") return "green";
  if (s === "rejected" || s === "stale") return "red";
  if (s === "awaiting_review") return "saffron";
  return "stone";
}

/** Proposed changes and challenges: to review, mine, closed (ADR-0021 §10). */
export function ReviewPage() {
  const { t } = useTranslation();
  const { treeId } = useTreeCtx();
  const { proposalId } = useParams();
  const [view, setView] = useState<ProposalView>("to_review");
  const list = useProposals(treeId, view);
  if (proposalId) return <ProposalDetail id={proposalId} />;
  return (
    <div>
      <PageHeader title={t("review.title")} subtitle={t("review.subtitle")} />
      <Tabs label={t("review.title")} tabs={VIEWS.map((v) => ({ id: v, label: t(`review.view.${v}`) }))} active={view} onChange={(id) => setView(id as ProposalView)}>
        {list.isLoading && <Spinner />}
        <ErrorAlert error={list.error} />
        {list.data?.items.length === 0 && <EmptyState icon={<ClipboardCheck className="size-10" aria-hidden />} title={t(`review.empty.${view}`)} />}
        <ul className="divide-y divide-stone-200">
          {list.data?.items.map((p) => (
            <li key={p.id} className="py-3">
              <Link to={`/t/${treeId}/review/${p.id}`} className="flex flex-wrap items-center justify-between gap-2 rounded hover:bg-parchment">
                <span>
                  <span className="font-medium">{p.kind === "challenge" ? t("review.challengeAbout", { person: p.person_label ?? (p.family_subject ? t(`review.familySubject.${p.family_subject}`) : t("review.someone")) }) : t("review.changesTo", { count: p.item_count, person: p.person_label ?? (p.family_subject ? t(`review.familySubject.${p.family_subject}`) : t("review.someone")) })}</span>
                  <span className="block text-xs text-ink-muted">
                    {p.proposer?.display_name ?? t("review.formerMember")} · {new Date(p.submitted_at ?? p.created_at).toLocaleDateString()}
                  </span>
                </span>
                <Badge tone={statusTone(p.status)}>{t(`review.status.${p.status}`)}</Badge>
              </Link>
            </li>
          ))}
        </ul>
      </Tabs>
    </div>
  );
}

function ProposalDetail({ id }: { id: string }) {
  const { t } = useTranslation();
  const { treeId } = useTreeCtx();
  const q = useProposal(treeId, id);
  const decide = useDecide(treeId, id);
  const comment = useComment(treeId, id);
  const fieldLabel = useFieldLabel();
  const [note, setNote] = useState("");
  const [text, setText] = useState("");
  if (q.isLoading) return <Spinner />;
  if (q.error || !q.data) return <ErrorAlert error={q.error} />;
  const p: ChangeProposalOut = q.data;
  const items = p.items ?? [];
  const comments = p.comments ?? [];
  const challenge = p.kind === "challenge";
  const act = (action: Decision) => decide.mutate({ action, note: note.trim() || undefined }, { onSuccess: () => setNote("") });
  const stale = decide.error instanceof ApiError && decide.error.code === "proposal_stale";
  return (
    <div className="space-y-4">
      <PageHeader
        eyebrow={
          <Link to={`/t/${treeId}/review`} className="text-kumkum-800 underline">
            {t("review.title")}
          </Link>
        }
        title={challenge ? t("review.challengeAbout", { person: p.person_label ?? (p.family_subject ? t(`review.familySubject.${p.family_subject}`) : t("review.someone")) }) : t("review.changesTo", { count: items.length, person: p.person_label ?? (p.family_subject ? t(`review.familySubject.${p.family_subject}`) : t("review.someone")) })}
        subtitle={t("review.by", { name: p.proposer?.display_name ?? t("review.formerMember") })}
        actions={<Badge tone={statusTone(p.status)}>{t(`review.status.${p.status}`)}</Badge>}
      />
      {p.person_id && (
        <p className="text-sm">
          <Link to={`/t/${treeId}/people/${p.person_id}`} className="text-kumkum-800 underline">
            {t("review.openPerson")}
          </Link>
        </p>
      )}
      <section className="card p-4">
        <h2 className="font-semibold">{challenge ? t("review.challengeReason") : t("review.rationale")}</h2>
        <p className="mt-1 whitespace-pre-wrap">{p.rationale}</p>
        {p.stale_reason && (
          <p className="mt-2 flex items-start gap-1 text-sm text-red-800" role="note">
            <AlertTriangle className="mt-0.5 size-4 shrink-0" aria-hidden />
            {t("review.staleNotice")} {p.stale_reason}
          </p>
        )}
        {p.decision_note && (
          <p className="mt-2 text-sm">
            <span className="font-medium">{t("review.decisionNote", { name: p.decided_by?.display_name ?? "" })}</span> {p.decision_note}
          </p>
        )}
      </section>

      {items.length > 0 && (
        <section className="space-y-3" aria-labelledby="pd-changes">
          <h2 id="pd-changes" className="font-semibold">
            {challenge ? t("review.correction") : t("review.changes")}
          </h2>
          {items.map((i) => (
            <div key={i.id} className="card p-3">
              <p className="flex flex-wrap items-center gap-2 text-sm font-medium">
                {t(`review.op.${i.op}`)} · {t(`review.target.${i.target_type}`)}
                {i.outdated && <Badge tone="red">{t("review.outdated")}</Badge>}
              </p>
              <div className="mt-2 overflow-x-auto">
                <table className="w-full text-sm">
                  <thead>
                    <tr className="text-left text-xs text-ink-muted">
                      <th scope="col" className="py-1 pr-2 font-medium">
                        {t("review.field.label")}
                      </th>
                      <th scope="col" className="py-1 pr-2 font-medium">
                        {t("review.now")}
                      </th>
                      <th scope="col" className="py-1 font-medium">
                        {t("review.proposed")}
                      </th>
                    </tr>
                  </thead>
                  <tbody>
                    {(i.changes ?? []).map((c) => (
                      <tr key={c.field} className="border-t border-stone-100 align-top">
                        <th scope="row" className="py-1 pr-2 text-left font-normal text-ink-muted">
                          {fieldLabel(c.field)}
                        </th>
                        {c.hidden ? (
                          <td colSpan={2} className="py-1 text-ink-muted">
                            <EyeOff className="mr-1 inline size-3.5" aria-hidden />
                            {t("review.hiddenField")}
                          </td>
                        ) : (
                          <>
                            <td className="py-1 pr-2">
                              <del className="text-red-800">{formatValue(c.current)}</del>
                            </td>
                            <td className="py-1">
                              <ins className="text-leaf-700 no-underline">{formatValue(c.proposed)}</ins>
                            </td>
                          </>
                        )}
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </div>
          ))}
        </section>
      )}

      {(p.can_decide || p.cannot_decide_reason || p.can_withdraw || p.can_rebase) && (
        <section className="card space-y-3 p-4" aria-labelledby="pd-decide">
          <h2 id="pd-decide" className="font-semibold">
            {t("review.decide")}
          </h2>
          {p.cannot_decide_reason && !p.can_decide && <p className="text-sm text-ink-muted">{p.cannot_decide_reason}</p>}
          {p.can_decide && (
            <>
              <Field label={t("review.note")} hint={t("review.noteHint")}>
                {(f) => <TextArea {...f} rows={2} value={note} onChange={(e) => setNote(e.target.value)} maxLength={2000} />}
              </Field>
              <div className="flex flex-wrap gap-2">
                <Button loading={decide.isPending} onClick={() => act(challenge ? "uphold" : "approve")}>
                  {challenge ? t("review.uphold") : t("review.approve")}
                </Button>
                <Button variant="secondary" disabled={!note.trim()} onClick={() => act(challenge ? "dismiss" : "reject")}>
                  {challenge ? t("review.dismiss") : t("review.reject")}
                </Button>
              </div>
            </>
          )}
          <div className="flex flex-wrap gap-2">
            {p.can_rebase && (
              <Button variant="secondary" onClick={() => act("rebase")}>
                {t("review.rebase")}
              </Button>
            )}
            {p.can_withdraw && (
              <Button variant="ghost" onClick={() => act("withdraw")}>
                {t("review.withdraw")}
              </Button>
            )}
          </div>
          {!stale && <ErrorAlert error={decide.error} />}
        </section>
      )}
      {stale && (
        <p role="alert" className="rounded-md border border-red-200 bg-red-50 p-3 text-sm text-red-800">
          {t("review.becameStale")}
        </p>
      )}

      <section className="card space-y-3 p-4" aria-labelledby="pd-comments">
        <h2 id="pd-comments" className="font-semibold">
          {t("review.comments")}
        </h2>
        <ul className="space-y-2">
          {comments.map((c) => (
            <li key={c.id} className="text-sm">
              <span className="font-medium">{c.author?.display_name ?? t("review.formerMember")}</span>
              <span className="ml-1 text-xs text-ink-muted">{new Date(c.created_at).toLocaleString()}</span>
              <p className="whitespace-pre-wrap">{c.body}</p>
            </li>
          ))}
        </ul>
        <Field label={t("review.addComment")}>
          {(f) => <TextArea {...f} rows={2} value={text} onChange={(e) => setText(e.target.value)} maxLength={2000} />}
        </Field>
        <Button size="sm" variant="secondary" disabled={!text.trim()} loading={comment.isPending} onClick={() => comment.mutate(text.trim(), { onSuccess: () => setText("") })}>
          {t("review.postComment")}
        </Button>
        <ErrorAlert error={comment.error} />
      </section>
    </div>
  );
}
