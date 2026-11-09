import { useState } from "react";
import { useTranslation } from "react-i18next";
import { Check, X } from "lucide-react";
import type { MemberOut, NominationOut } from "../../api/types";
import { useAdminNominations, useCreateNomination, useNominationStep } from "../../api/hooks/trees";
import { useTreeCtx } from "../../lib/tree-context";
import { Button } from "../ui/Button";
import { ConfirmDialog, Dialog } from "../ui/Dialog";
import { ErrorAlert } from "../ui/feedback";
import { Checkbox, Field, TextArea } from "../ui/form";
import { Badge } from "../ui/Badge";

const REASON_MAX = 500;

/**
 * Family Admin nominations (ADR-0006 amendment of 9 Nov 2026). A family admin puts a member
 * forward, the member accepts, and an owner approves. The server decides who sees what (owners and
 * family admins see every open nomination, the nominee sees their own) and re-checks every step;
 * the `can_*` flags only decide which buttons to show.
 */
export function AdminNominationsPanel() {
  const { t, i18n } = useTranslation();
  const { treeId } = useTreeCtx();
  const nominations = useAdminNominations(treeId);
  const step = useNominationStep(treeId);
  const [approving, setApproving] = useState<NominationOut | null>(null);
  const [rejecting, setRejecting] = useState<NominationOut | null>(null);
  const [done, setDone] = useState("");
  const items = nominations.data ?? [];
  // visible, and kept after the last open nomination closes (e.g. once an owner approves)
  const status = done ? (
    <p role="status" className="mb-4 rounded-lg bg-green-50 px-3 py-2 text-sm text-green-900">
      {done}
    </p>
  ) : null;
  if (!items.length)
    return (
      <>
        {status}
        <ErrorAlert error={nominations.error} />
      </>
    );
  const run = (n: NominationOut, s: "accept" | "decline" | "withdraw" | "reject", message: string) =>
    step.mutate({ id: n.id, step: s }, { onSuccess: () => setDone(message) });
  return (
    <section aria-labelledby="nominations-heading" className="card mb-4 p-4">
      <h2 id="nominations-heading" className="text-base font-semibold">
        {t("nominations.title")}
      </h2>
      <p className="mb-3 text-sm text-ink-muted">{t("nominations.subtitle")}</p>
      {status}
      <ErrorAlert error={nominations.error || step.error} />
      <ul className="space-y-3">
        {items.map((n) => (
          <li key={n.id} className="rounded-lg border border-stone-200 p-3" aria-label={t("nominations.itemLabel", { name: n.nominee_name })}>
            <p className="font-medium">
              {n.is_mine ? t("nominations.youWereNominated", { nominator: n.nominator_name }) : t("nominations.nominated", { name: n.nominee_name, nominator: n.nominator_name })}
            </p>
            <blockquote className="mt-1 border-l-2 border-saffron-300 pl-2 text-sm">{n.reason}</blockquote>
            <div className="mt-2 flex flex-wrap items-center gap-2 text-xs text-ink-muted">
              {n.nominee_accepted ? <Badge tone="green">{t("nominations.accepted")}</Badge> : <Badge tone="saffron">{t("nominations.awaitingNominee")}</Badge>}
              {n.nominee_branch_scoped && <Badge tone="violet">{t("members.branchScoped")}</Badge>}
              <span>{t("nominations.expires", { date: new Date(n.expires_at).toLocaleDateString(i18n.language) })}</span>
            </div>
            {n.is_mine && <p className="mt-2 text-sm">{t("nominations.whatItMeans")}</p>}
            <div className="mt-2 flex flex-wrap gap-2">
              {n.can_accept && (
                <Button size="sm" icon={<Check className="size-4" aria-hidden />} loading={step.isPending} onClick={() => run(n, "accept", t("nominations.acceptedDone"))}>
                  {t("nominations.accept")}
                </Button>
              )}
              {n.can_decline && (
                <Button size="sm" variant="secondary" onClick={() => run(n, "decline", t("nominations.declinedDone"))}>
                  {t("nominations.decline")}
                </Button>
              )}
              {n.can_decide && (
                <>
                  <Button size="sm" disabled={!n.nominee_accepted} onClick={() => setApproving(n)}>
                    {t("nominations.approve")}
                  </Button>
                  <Button size="sm" variant="secondary" icon={<X className="size-4" aria-hidden />} onClick={() => setRejecting(n)}>
                    {t("nominations.reject")}
                  </Button>
                </>
              )}
              {n.can_withdraw && (
                <Button size="sm" variant="ghost" onClick={() => run(n, "withdraw", t("nominations.withdrawnDone"))}>
                  {t("nominations.withdraw")}
                </Button>
              )}
            </div>
            {n.can_decide && !n.nominee_accepted && <p className="mt-1 text-xs text-ink-muted">{t("nominations.approveAfterAccept", { name: n.nominee_name })}</p>}
          </li>
        ))}
      </ul>
      {approving && <ApproveDialog nomination={approving} onClose={() => setApproving(null)} onDone={() => setDone(t("nominations.approvedDone", { name: approving.nominee_name }))} />}
      <ConfirmDialog
        open={!!rejecting}
        onClose={() => setRejecting(null)}
        title={t("nominations.rejectTitle", { name: rejecting?.nominee_name ?? "" })}
        body={t("nominations.rejectBody")}
        confirmLabel={t("nominations.reject")}
        loading={step.isPending}
        onConfirm={() => rejecting && step.mutate({ id: rejecting.id, step: "reject" }, { onSuccess: () => { setRejecting(null); setDone(t("nominations.rejectedDone")); } })}
      >
        <ErrorAlert error={step.error} />
      </ConfirmDialog>
    </section>
  );
}

function ApproveDialog({ nomination, onClose, onDone }: { nomination: NominationOut; onClose: () => void; onDone: () => void }) {
  const { t } = useTranslation();
  const { treeId } = useTreeCtx();
  const step = useNominationStep(treeId);
  const [clearBranch, setClearBranch] = useState(false);
  const blocked = nomination.nominee_branch_scoped && !clearBranch;
  return (
    <Dialog
      open
      onClose={onClose}
      title={t("nominations.approveTitle", { name: nomination.nominee_name })}
      footer={
        <>
          <Button variant="secondary" onClick={onClose}>
            {t("common.cancel")}
          </Button>
          <Button
            disabled={blocked}
            loading={step.isPending}
            onClick={() =>
              step.mutate(
                { id: nomination.id, step: "approve", clearBranch },
                {
                  onSuccess: () => {
                    onDone();
                    onClose();
                  },
                },
              )
            }
          >
            {t("nominations.approve")}
          </Button>
        </>
      }
    >
      <div className="space-y-3 text-sm">
        <p>{t("nominations.approveBody")}</p>
        {nomination.nominee_branch_scoped && (
          <Checkbox label={t("nominations.clearBranch", { name: nomination.nominee_name })} hint={t("nominations.clearBranchHint")} checked={clearBranch} onChange={setClearBranch} />
        )}
        <ErrorAlert error={step.error} />
      </div>
    </Dialog>
  );
}

export function NominateDialog({ member, onClose }: { member: MemberOut; onClose: () => void }) {
  const { t } = useTranslation();
  const { treeId } = useTreeCtx();
  const create = useCreateNomination(treeId);
  const [reason, setReason] = useState("");
  const trimmed = reason.trim();
  return (
    <Dialog
      open
      onClose={onClose}
      title={t("nominations.nominateTitle", { name: member.display_name })}
      description={t("nominations.nominateHelp")}
      footer={
        <>
          <Button variant="secondary" onClick={onClose}>
            {t("common.cancel")}
          </Button>
          <Button
            disabled={!trimmed || reason.length > REASON_MAX}
            loading={create.isPending}
            onClick={() => create.mutate({ membership_id: member.id, reason: trimmed }, { onSuccess: onClose })}
          >
            {t("nominations.nominate")}
          </Button>
        </>
      }
    >
      <div className="space-y-3">
        <Field label={t("nominations.reason")} hint={t("nominations.reasonHint", { count: REASON_MAX - reason.length })}>
          {(p) => <TextArea {...p} value={reason} maxLength={REASON_MAX} onChange={(e) => setReason(e.target.value)} />}
        </Field>
        <ErrorAlert error={create.error} />
      </div>
    </Dialog>
  );
}
