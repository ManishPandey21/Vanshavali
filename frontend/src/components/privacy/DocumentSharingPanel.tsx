import { useEffect, useMemo, useState } from "react";
import { useTranslation } from "react-i18next";
import { Share2 } from "lucide-react";
import type { DocumentOut, SharingUpdate } from "../../api/types";
import { ApiError } from "../../api/client";
import { useSharing, useSharingPreview, useUpdateSharing } from "../../api/hooks/documents";
import { useMembers } from "../../api/hooks/trees";
import { useBranches } from "../../api/hooks/family";
import { useMe } from "../../api/hooks/auth";
import { useTreeCtx } from "../../lib/tree-context";
import { Button } from "../ui/Button";
import { ConfirmDialog } from "../ui/Dialog";
import { ErrorAlert, LiveRegion, Spinner } from "../ui/feedback";
import { RecordPrivacyBadge } from "../person/badges";
import { VisibilitySharing, draftFrom, draftProblem, type SharingDraft } from "./VisibilitySharing";

function toBody(d: SharingDraft, confirm = false): SharingUpdate {
  return {
    privacy_level: d.privacy_level,
    audience_branch_id: d.privacy_level === "FAMILY_BRANCH" ? d.audience_branch_id : null,
    allow_download: d.allow_download,
    members: d.privacy_level === "ONLY_ME" ? [] : d.members,
    confirm_wider: confirm,
  };
}

/**
 * Visibility & Sharing on a document page (ADR-0027 §9). The owner (or, for shared records, a
 * document manager narrowing it) edits a draft; the server previews exactly who would have access,
 * and asks for confirmation before anyone new can see or download the record.
 */
export function DocumentSharingPanel({ doc }: { doc: DocumentOut }) {
  const { t } = useTranslation();
  const { treeId } = useTreeCtx();
  const sharing = useSharing(treeId, doc.id);
  const members = useMembers(treeId);
  const branches = useBranches(treeId);
  const me = useMe();
  const save = useUpdateSharing(treeId, doc.id);
  const [draft, setDraft] = useState<SharingDraft | null>(null);
  const [confirmCount, setConfirmCount] = useState<number | null>(null);
  const [saved, setSaved] = useState(false);

  useEffect(() => {
    if (sharing.data && draft === null) setDraft(draftFrom(sharing.data));
  }, [sharing.data, draft]);

  const dirty = useMemo(
    () => !!draft && !!sharing.data && JSON.stringify(toBody(draft)) !== JSON.stringify(toBody(draftFrom(sharing.data))),
    [draft, sharing.data],
  );
  const valid = !!draft && draftProblem(draft) === null;
  const preview = useSharingPreview(treeId, doc.id, dirty && valid && draft ? toBody(draft) : null);

  if (sharing.isLoading || !draft) return sharing.error ? <ErrorAlert error={sharing.error} /> : <Spinner />;
  const s = sharing.data!;
  const ownMembershipId = members.data?.find((m) => m.user_id === me.data?.id)?.id ?? null;
  const audience = dirty && valid ? (preview.data?.audience ?? s.audience) : s.audience;

  const submit = (confirm: boolean) => {
    setSaved(false);
    save.mutate(toBody(draft, confirm), {
      onSuccess: (out) => {
        setConfirmCount(null);
        setDraft(draftFrom(out));
        setSaved(true);
      },
      onError: (e) => {
        if (e instanceof ApiError && e.code === "confirm_wider") {
          const d = (e.details ?? {}) as { viewers_added?: number; downloaders_added?: number };
          setConfirmCount(Math.max(d.viewers_added ?? 0, d.downloaders_added ?? 0, 1));
        }
      },
    });
  };
  const confirmError = save.error instanceof ApiError && save.error.code === "confirm_wider" ? null : save.error;

  return (
    <section className="card space-y-3 p-4" aria-labelledby={`sharing-${doc.id}`}>
      <h2 id={`sharing-${doc.id}`} className="flex flex-wrap items-center gap-2 font-display text-base font-semibold">
        <Share2 className="size-4 text-kumkum-700" aria-hidden /> {t("sharing.title")}
        <RecordPrivacyBadge level={s.privacy_level} />
      </h2>
      {s.legacy && <p className="rounded-lg bg-haldi-100 p-2 text-xs text-haldi-700">{t("sharing.legacy")}</p>}
      {!s.can_edit ? (
        <p className="text-sm text-ink-muted">{t("sharing.readOnly")}</p>
      ) : (
        <>
          <p className="text-xs text-ink-muted">{s.has_owner ? t("sharing.intro") : t("sharing.noOwner")}</p>
          <VisibilitySharing
            value={draft}
            onChange={(d) => {
              setSaved(false);
              setDraft(d);
            }}
            members={members.data ?? []}
            branches={branches.data ?? []}
            ownMembershipId={ownMembershipId}
            ceiling={s.ceiling}
            audience={audience}
            canWiden={s.can_widen}
            showProblems={dirty}
          />
          <ErrorAlert error={confirmError || (dirty && valid ? preview.error : null)} />
          <div className="flex justify-end">
            <Button disabled={!dirty || !valid} loading={save.isPending} onClick={() => submit(false)}>
              {t("sharing.save")}
            </Button>
          </div>
          <LiveRegion message={saved ? t("sharing.saved") : ""} />
        </>
      )}
      <ConfirmDialog
        open={confirmCount !== null}
        onClose={() => setConfirmCount(null)}
        title={t("sharing.confirmTitle")}
        body={t("sharing.confirmBody", { count: confirmCount ?? 1 })}
        confirmLabel={t("sharing.confirm")}
        loading={save.isPending}
        onConfirm={() => submit(true)}
      />
    </section>
  );
}
