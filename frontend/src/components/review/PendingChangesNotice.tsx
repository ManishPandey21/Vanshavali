import { useTranslation } from "react-i18next";
import { Link } from "react-router-dom";
import { ClipboardCheck } from "lucide-react";
import { useProposals } from "../../api/hooks/review";

/** "2 changes to this person await review" (ADR-0021 §10): only proposals the reader may see. */
export function PendingChangesNotice({ treeId, personId }: { treeId: string; personId: string }) {
  const { t } = useTranslation();
  const q = useProposals(treeId, "all", personId);
  const open = (q.data?.items ?? []).filter((p) => p.status === "awaiting_review");
  if (!open.length) return null;
  return (
    <p className="mb-4 flex flex-wrap items-center gap-2 rounded-md border border-haldi-300 bg-haldi-100/60 px-3 py-2 text-sm" role="note">
      <ClipboardCheck className="size-4" aria-hidden />
      {t("review.pendingForPerson", { count: open.length })}
      <Link to={open.length === 1 ? `/t/${treeId}/review/${open[0].id}` : `/t/${treeId}/review`} className="text-kumkum-800 underline">
        {t("review.see")}
      </Link>
    </p>
  );
}
