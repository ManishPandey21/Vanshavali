import { useEffect, useState } from "react";
import { useTranslation } from "react-i18next";
import type { TFunction } from "i18next";
import { Copy, MessageCircle, Send, Share2, UserPlus } from "lucide-react";
import { useCreateClaimInvite } from "../../api/hooks/onboarding";
import type { ClaimInviteCreated } from "../../api/types";
import { Button, buttonClass } from "../ui/Button";
import { Dialog } from "../ui/Dialog";
import { ErrorAlert, LiveRegion } from "../ui/feedback";
import { Checkbox } from "../ui/form";

/**
 * The message a relative receives. It deliberately carries no names, dates or tree details: it
 * travels through WhatsApp (or any app) and may be forwarded, so it holds only the link (ADR-0011).
 */
export function inviteMessage(t: TFunction, url: string): string {
  return t("claimInvite.message", { url });
}

/** A WhatsApp share link without a phone number: the user picks the chat, and we never collect numbers. */
export function whatsappShareUrl(message: string): string {
  return `https://wa.me/?text=${encodeURIComponent(message)}`;
}

/** Telegram's generic share composer. No username or chat id is supplied or collected. */
export function telegramShareUrl(message: string, url: string): string {
  const params = new URLSearchParams({ url, text: message.replace(url, "").trim() });
  return `https://t.me/share/url?${params.toString()}`;
}

/**
 * Create a single-use claim link for one living relative and share it via WhatsApp, the
 * system share sheet or copy/paste. Accepting the link only sends a claim for admin review.
 */
export function ClaimInviteShare({
  treeId,
  personId,
  personName,
  canOfferContributor,
}: {
  treeId: string;
  personId: string;
  personName: string;
  canOfferContributor: boolean;
}) {
  const { t, i18n } = useTranslation();
  const create = useCreateClaimInvite(treeId);
  const [contributor, setContributor] = useState(false);
  const [invite, setInvite] = useState<ClaimInviteCreated | null>(null);
  const [copied, setCopied] = useState(false);

  // A one-time URL is bound to exactly one profile. Never carry it across a prop change.
  useEffect(() => {
    setContributor(false);
    setInvite(null);
    setCopied(false);
  }, [personId]);

  if (!invite) {
    return (
      <div className="space-y-3">
        {canOfferContributor && (
          <Checkbox label={t("claimInvite.letThemContribute")} hint={t("claimInvite.letThemContributeHint")} checked={contributor} onChange={setContributor} />
        )}
        <ErrorAlert error={create.error} />
        <Button
          icon={<UserPlus className="size-4" aria-hidden />}
          loading={create.isPending}
          onClick={() => create.mutate({ personId, offeredRole: contributor ? "CONTRIBUTOR" : "VIEWER" }, { onSuccess: setInvite })}
        >
          {t("claimInvite.create", { name: personName })}
        </Button>
      </div>
    );
  }

  const message = inviteMessage(t, invite.url);
  const canNativeShare = typeof navigator !== "undefined" && typeof navigator.share === "function";
  return (
    <div className="space-y-3">
      <div className="flex flex-wrap gap-2">
        <a
          href={whatsappShareUrl(message)}
          target="_blank"
          rel="noopener noreferrer"
          className={buttonClass("primary", "md", "bg-[#1f7a4d] hover:bg-[#17623d]")}
        >
          <MessageCircle className="size-4" aria-hidden />
          {t("claimInvite.whatsapp")}
          <span className="sr-only"> {t("common.opensInNewTab")}</span>
        </a>
        <a
          href={telegramShareUrl(message, invite.url)}
          target="_blank"
          rel="noopener noreferrer"
          className={buttonClass("secondary", "md")}
        >
          <Send className="size-4" aria-hidden />
          {t("claimInvite.telegram")}
          <span className="sr-only"> {t("common.opensInNewTab")}</span>
        </a>
        {canNativeShare && (
          <Button variant="secondary" icon={<Share2 className="size-4" aria-hidden />} onClick={() => void navigator.share({ text: message }).catch(() => undefined)}>
            {t("claimInvite.shareOther")}
          </Button>
        )}
        <Button
          variant="secondary"
          icon={<Copy className="size-4" aria-hidden />}
          onClick={() => void navigator.clipboard?.writeText(message).then(() => setCopied(true))}
        >
          {copied ? t("common.copied") : t("claimInvite.copyLink")}
        </Button>
      </div>
      <p className="text-xs text-ink-muted">
        {t("claimInvite.linkFacts", { date: new Date(invite.expires_at).toLocaleDateString(i18n.language) })}
      </p>
      <LiveRegion message={copied ? t("common.copied") : t("claimInvite.ready")} />
    </div>
  );
}

export function ClaimInviteDialog({
  treeId,
  personId,
  personName,
  canOfferContributor,
  onClose,
}: {
  treeId: string;
  personId: string;
  personName: string;
  canOfferContributor: boolean;
  onClose: () => void;
}) {
  const { t } = useTranslation();
  return (
    <Dialog
      open
      onClose={onClose}
      title={t("claimInvite.title", { name: personName })}
      description={t("claimInvite.description")}
      footer={
        <Button variant="secondary" onClick={onClose}>
          {t("common.close")}
        </Button>
      }
    >
      <ClaimInviteShare treeId={treeId} personId={personId} personName={personName} canOfferContributor={canOfferContributor} />
    </Dialog>
  );
}
