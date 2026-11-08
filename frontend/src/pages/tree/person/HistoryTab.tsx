import { useTranslation } from "react-i18next";
import { Link } from "react-router-dom";
import { EyeOff, History, RotateCcw } from "lucide-react";
import type { PersonOut } from "../../../api/types";
import { useHistory, useRevert } from "../../../api/hooks/review";
import { useTreeCtx } from "../../../lib/tree-context";
import { Button } from "../../../components/ui/Button";
import { EmptyState, ErrorAlert, Spinner } from "../../../components/ui/feedback";
import { formatValue, useFieldLabel } from "../../../components/review/ReviewParts";

/**
 * Every change to this person's facts, newest first (ADR-0021 §3). Fields the reader may not see
 * are listed as changed without their values. Revert creates a new change, never rewrites history.
 */
export function HistoryTab({ person }: { person: PersonOut }) {
  const { t } = useTranslation();
  const { treeId } = useTreeCtx();
  const q = useHistory(treeId, person.id);
  const revert = useRevert(treeId);
  const fieldLabel = useFieldLabel();
  if (q.isLoading) return <Spinner />;
  if (q.error) return <ErrorAlert error={q.error} />;
  const items = q.data?.items ?? [];
  if (!items.length) return <EmptyState icon={<History className="size-10" aria-hidden />} title={t("review.historyEmpty")} />;
  return (
    <div className="space-y-3">
      {revert.data && (
        <p role="status" className="rounded-md bg-leaf-50 p-2 text-sm">
          {revert.data.outcome === "applied" ? t("review.reverted") : t("review.revertProposed")}
          {revert.data.proposal_id && (
            <Link to={`/t/${treeId}/review/${revert.data.proposal_id}`} className="ml-1 text-kumkum-800 underline">
              {t("review.openProposal")}
            </Link>
          )}
        </p>
      )}
      <ErrorAlert error={revert.error} />
      <ol className="space-y-2">
        {items.map((r) => (
          <li key={r.id} className="card p-3">
            <div className="flex flex-wrap items-start justify-between gap-2">
              <p className="text-sm">
                <span className="font-medium">
                  {t(`review.op.${r.op}`)} · {t(`review.target.${r.record_type}`)}
                </span>
                <span className="block text-xs text-ink-muted">
                  {new Date(r.created_at).toLocaleString()} · {r.actor?.display_name ?? t("review.system")}
                  {r.reviewer && ` · ${t("review.reviewedBy", { name: r.reviewer.display_name ?? "" })}`}
                </span>
              </p>
              {r.revertible && person.can_edit && (
                <Button size="sm" variant="ghost" icon={<RotateCcw className="size-3.5" aria-hidden />} loading={revert.isPending && revert.variables === r.id} onClick={() => revert.mutate(r.id)}>
                  {t("review.revert")}
                </Button>
              )}
            </div>
            {r.op === "update" && r.changes.length > 0 && (
              <ul className="mt-1 text-sm">
                {r.changes.map((c) => (
                  <li key={c.field}>
                    <span className="text-ink-muted">{fieldLabel(c.field)}:</span>{" "}
                    {c.hidden ? (
                      <span className="text-ink-muted">
                        <EyeOff className="mr-1 inline size-3.5" aria-hidden />
                        {t("review.hiddenField")}
                      </span>
                    ) : (
                      <>
                        <del className="text-red-800">{formatValue(c.before)}</del> → <ins className="text-leaf-700 no-underline">{formatValue(c.after)}</ins>
                      </>
                    )}
                  </li>
                ))}
              </ul>
            )}
          </li>
        ))}
      </ol>
    </div>
  );
}
