import { useState, type FormEvent } from "react";
import { Link, useLocation } from "react-router-dom";
import { useTranslation } from "react-i18next";
import { CheckCircle2, EyeOff, Lock, ShieldCheck, Trash2, UserX } from "lucide-react";
import { useMe } from "../../api/hooks/auth";
import { useAcceptClaimInvite, useClaimInvitePreview, useDeclineClaimInvite, useRequestRemoval } from "../../api/hooks/onboarding";
import { ApiError } from "../../api/client";
import type { ClaimKind, StatementOut } from "../../api/types";
import { StatementCheckbox } from "../../components/consent/FamilyConsent";
import { Button, ButtonLink } from "../../components/ui/Button";
import { ConfirmDialog, Dialog } from "../../components/ui/Dialog";
import { ErrorAlert, LiveRegion, Spinner } from "../../components/ui/feedback";
import { Checkbox, Field, TextArea } from "../../components/ui/form";
import { AuthFrame } from "../auth/AuthPages";

/** The token travels in the URL fragment, which browsers never send to any server (ADR-0011). */
export function tokenFromHash(hash: string): string {
  const raw = hash.startsWith("#") ? hash.slice(1) : hash;
  return /^[A-Za-z0-9_-]{16,200}$/.test(raw) ? raw : "";
}

/** Landing page for a claim link shared over WhatsApp: notice, the relative's own consent, then a claim for admin review. */
export function ClaimInvitePage() {
  const { t } = useTranslation();
  const location = useLocation();
  const token = tokenFromHash(location.hash);
  const me = useMe();
  const preview = useClaimInvitePreview(token, !!me.data);
  const decline = useDeclineClaimInvite(token);

  if (me.isLoading) return <Spinner />;
  if (!token) {
    return (
      <AuthFrame title={t("claimLink.title")}>
        <ErrorAlert error={new Error(t("claimLink.badLink"))} />
      </AuthFrame>
    );
  }
  if (!me.data) {
    // Keep the fragment across sign-in / sign-up so the link still works afterwards.
    const next = encodeURIComponent(`/claim#${token}`);
    return (
      <AuthFrame title={t("claimLink.title")} subtitle={t("claimLink.signInFirst")}>
        <div className="space-y-3">
          <ButtonLink to={`/register?next=${next}`} className="w-full">
            {t("auth.createAccount")}
          </ButtonLink>
          <ButtonLink to={`/login?next=${next}`} variant="secondary" className="w-full">
            {t("auth.login")}
          </ButtonLink>
        </div>
      </AuthFrame>
    );
  }

  if (decline.isSuccess) {
    return (
      <AuthFrame title={t("claimLink.title")}>
        <Outcome message={t("claimLink.declined")} />
      </AuthFrame>
    );
  }

  const err = preview.error;
  const gone =
    err instanceof ApiError && (err.code === "invite_used" || err.code === "invite_expired" || err.status === 404)
      ? new Error(err.code === "invite_used" ? t("claimLink.used") : err.code === "invite_expired" ? t("claimLink.expired") : t("claimLink.badLink"))
      : err;

  return (
    <AuthFrame title={t("claimLink.title")}>
      {preview.isLoading && <Spinner />}
      <ErrorAlert error={gone} />
      {preview.data &&
        (preview.data.state === "used" ? (
          <Submitted kind={preview.data.claim_kind ?? "claim"} />
        ) : (
          <>
            <ClaimForm token={token} tree={preview.data.tree_name} person={preview.data.person_name} inviter={preview.data.invited_by} />
            <NotMe token={token} person={preview.data.person_name} decline={decline} />
          </>
        ))}
    </AuthFrame>
  );
}

function Submitted({ kind }: { kind: ClaimKind }) {
  const { t } = useTranslation();
  return <Outcome message={kind === "removal" ? t("claimLink.removalRequested") : t("claimLink.submitted")} />;
}

function Outcome({ message }: { message: string }) {
  const { t } = useTranslation();
  return (
    <div className="space-y-4">
      <p className="flex items-start gap-2 text-sm">
        <CheckCircle2 className="mt-0.5 size-5 shrink-0 text-leaf-700" aria-hidden />
        {message}
      </p>
      <LiveRegion message={message} />
      <ButtonLink to="/" variant="secondary" className="w-full">
        {t("claimLink.home")}
      </ButtonLink>
    </div>
  );
}

function ClaimForm({ token, tree, person, inviter }: { token: string; tree: string; person: string; inviter: string | null | undefined }) {
  const { t } = useTranslation();
  const accept = useAcceptClaimInvite(token);
  const [consent, setConsent] = useState(false);
  const [statement, setStatement] = useState<StatementOut | null>(null);
  const [adult, setAdult] = useState(false);
  const [message, setMessage] = useState("");
  const [submitted, setSubmitted] = useState(false);

  if (accept.isSuccess) return <Submitted kind="claim" />;

  const submit = (e: FormEvent) => {
    e.preventDefault();
    setSubmitted(true);
    if (!consent || !adult || !statement) return;
    accept.mutate({ consent_version: statement.version, language: statement.language, confirm_adult: true, message: message.trim() || null });
  };

  return (
    <form onSubmit={submit} noValidate className="space-y-4">
      <p className="text-sm">{inviter ? t("claimLink.invitedBy", { inviter, person, tree }) : t("claimLink.invited", { person, tree })}</p>
      <div className="rounded-lg bg-parchment-deep p-3">
        <h2 className="mb-2 text-sm font-semibold">{t("claimLink.noticeTitle")}</h2>
        <ul className="space-y-2 text-sm">
          {(
            [
              [Lock, "noticePrivate"],
              [EyeOff, "noticeReview"],
              [ShieldCheck, "noticeControl"],
              [Trash2, "noticeErase"],
            ] as const
          ).map(([Icon, key]) => (
            <li key={key} className="flex gap-2">
              <Icon className="mt-0.5 size-4 shrink-0 text-kumkum-700" aria-hidden />
              <span>{t(`claimLink.${key}`)}</span>
            </li>
          ))}
        </ul>
      </div>
      <StatementCheckbox kind="profile_claim" checked={consent} onChange={setConsent} onStatement={setStatement} error={submitted && !consent ? t("onboarding.consent.required") : null} />
      <Checkbox label={t("claimLink.adult")} hint={t("claimLink.adultHint")} checked={adult} onChange={setAdult} />
      {submitted && !adult && <p className="field-error">{t("claimLink.adultRequired")}</p>}
      <Field label={t("claim.message")} hint={t("claim.messageHint")}>
        {(p) => <TextArea {...p} value={message} maxLength={2000} onChange={(e) => setMessage(e.target.value)} />}
      </Field>
      <ErrorAlert error={accept.error} />
      <Button type="submit" className="w-full" loading={accept.isPending}>
        {t("claimLink.submit")}
      </Button>
    </form>
  );
}

/**
 * "This isn't me" cancels the link; "this is me, remove me" hides the profile and asks an admin to
 * erase it. Neither needs consent or an age check: they only ever reduce what is stored or shown.
 */
function NotMe({ token, person, decline }: { token: string; person: string; decline: ReturnType<typeof useDeclineClaimInvite> }) {
  const { t } = useTranslation();
  const removal = useRequestRemoval(token);
  const [open, setOpen] = useState<"decline" | "remove" | null>(null);
  const [isMe, setIsMe] = useState(false);
  const [message, setMessage] = useState("");
  const [tried, setTried] = useState(false);

  if (removal.isSuccess) return null; // the preview refetches and shows the outcome

  const remove = () => {
    setTried(true);
    if (!isMe) return;
    removal.mutate({ confirm_is_me: true, message: message.trim() || null });
  };

  return (
    <section className="mt-6 border-t border-stone-200 pt-4" aria-labelledby="not-me-title">
      <h2 id="not-me-title" className="text-sm font-semibold">
        {t("claimLink.notMeTitle")}
      </h2>
      <div className="mt-2 flex flex-col gap-2 sm:flex-row">
        <Button variant="secondary" size="sm" icon={<UserX className="size-4" aria-hidden />} onClick={() => setOpen("decline")}>
          {t("claimLink.notMe")}
        </Button>
        <Button variant="secondary" size="sm" icon={<Trash2 className="size-4" aria-hidden />} onClick={() => setOpen("remove")}>
          {t("claimLink.removeMe")}
        </Button>
      </div>
      <p className="mt-2 text-xs text-ink-muted">
        {t("claimLink.orLeave")}{" "}
        <Link to="/" className="underline">
          {t("claimLink.leave")}
        </Link>
      </p>

      <ConfirmDialog
        open={open === "decline"}
        onClose={() => setOpen(null)}
        onConfirm={() => decline.mutate()}
        loading={decline.isPending}
        title={t("claimLink.notMeConfirmTitle", { person })}
        body={t("claimLink.notMeConfirmBody")}
        confirmLabel={t("claimLink.notMeConfirm")}
      >
        <ErrorAlert error={decline.error} />
      </ConfirmDialog>

      <Dialog
        open={open === "remove"}
        onClose={() => setOpen(null)}
        title={t("claimLink.removeTitle")}
        description={t("claimLink.removeBody")}
        footer={
          <>
            <Button variant="secondary" onClick={() => setOpen(null)}>
              {t("common.cancel")}
            </Button>
            <Button variant="danger" loading={removal.isPending} onClick={remove}>
              {t("claimLink.removeConfirm")}
            </Button>
          </>
        }
      >
        <div className="space-y-3">
          <Checkbox label={t("claimLink.removeIsMe", { person })} checked={isMe} onChange={setIsMe} />
          {tried && !isMe && <p className="field-error">{t("claimLink.removeIsMeRequired")}</p>}
          <Field label={t("claimLink.removeMessage")} hint={t("claimLink.removeMessageHint")}>
            {(p) => <TextArea {...p} value={message} maxLength={2000} onChange={(e) => setMessage(e.target.value)} />}
          </Field>
          <ErrorAlert error={removal.error} />
        </div>
      </Dialog>
    </section>
  );
}
