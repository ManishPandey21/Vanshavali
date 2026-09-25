import { useState, type FormEvent } from "react";
import { Link, Navigate, useNavigate, useParams } from "react-router-dom";
import { useTranslation } from "react-i18next";
import { Globe2, Plus, TreePine } from "lucide-react";
import { useAcceptInvitation, useCreateTree, useInvitationPreview, useTrees } from "../../api/hooks/trees";
import { useMe } from "../../api/hooks/auth";
import { ApiError } from "../../api/client";
import { Button, ButtonLink } from "../../components/ui/Button";
import { EmptyState, ErrorAlert, PageHeader, Spinner } from "../../components/ui/feedback";
import { Field, TextArea, TextInput } from "../../components/ui/form";
import { Badge } from "../../components/ui/Badge";
import { AuthFrame } from "../auth/AuthPages";

export function TreesListPage() {
  const { t } = useTranslation();
  const trees = useTrees();
  return (
    <div>
      <PageHeader
        title={t("trees.title")}
        subtitle={t("trees.subtitle")}
        actions={
          <ButtonLink to="/trees/new" icon={<Plus className="size-4" aria-hidden />}>
            {t("trees.create")}
          </ButtonLink>
        }
      />
      {trees.isLoading && <Spinner />}
      <ErrorAlert error={trees.error} />
      {trees.data && trees.data.length === 0 && (
        <EmptyState icon={<TreePine className="size-10" aria-hidden />} title={t("trees.emptyTitle")} action={<ButtonLink to="/welcome">{t("onboarding.start")}</ButtonLink>}>
          {t("trees.emptyBody")}
        </EmptyState>
      )}
      <ul className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
        {trees.data?.map((tree) => (
          <li key={tree.id}>
            <Link to={`/t/${tree.id}`} className="card block h-full p-5 transition hover:border-kumkum-200 hover:shadow-md">
              <div className="flex items-start justify-between gap-2">
                <h2 className="font-display text-lg font-semibold text-kumkum-900">{tree.name}</h2>
                {tree.public_mode === "DECEASED_ONLY" && (
                  <Badge tone="green" icon={<Globe2 className="size-3" aria-hidden />}>
                    {t("trees.publicBadge")}
                  </Badge>
                )}
              </div>
              {tree.description && <p className="mt-1 line-clamp-2 text-sm text-ink-muted">{tree.description}</p>}
              <div className="mt-3 flex flex-wrap gap-1">
                {(tree.my_roles ?? []).map((r) => (
                  <Badge key={r} tone="saffron">
                    {t(`enum.role.${r}`)}
                  </Badge>
                ))}
              </div>
            </Link>
          </li>
        ))}
      </ul>
    </div>
  );
}

export function CreateTreePage() {
  const { t } = useTranslation();
  const create = useCreateTree();
  const navigate = useNavigate();
  const [name, setName] = useState("");
  const [description, setDescription] = useState("");
  const [submitted, setSubmitted] = useState(false);
  const submit = (e: FormEvent) => {
    e.preventDefault();
    setSubmitted(true);
    if (!name.trim()) return;
    create.mutate({ name: name.trim(), description: description.trim() || null }, { onSuccess: (tree) => navigate(`/t/${tree.id}`) });
  };
  return (
    <div className="mx-auto max-w-xl">
      <PageHeader title={t("trees.createTitle")} subtitle={t("trees.createSubtitle")} />
      <form onSubmit={submit} className="card space-y-4 p-5" noValidate>
        <Field label={t("trees.name")} required error={submitted && !name.trim() ? t("common.required") : null} hint={t("trees.nameHint")}>
          {(p) => <TextInput {...p} value={name} onChange={(e) => setName(e.target.value)} maxLength={200} />}
        </Field>
        <Field label={t("trees.description")}>{(p) => <TextArea {...p} value={description} onChange={(e) => setDescription(e.target.value)} />}</Field>
        <p className="rounded-lg bg-parchment-deep p-3 text-xs text-ink-muted">{t("trees.privateByDefault")}</p>
        <ErrorAlert error={create.error} />
        <div className="flex justify-end gap-2">
          <ButtonLink to="/" variant="secondary">
            {t("common.cancel")}
          </ButtonLink>
          <Button type="submit" loading={create.isPending}>
            {t("trees.create")}
          </Button>
        </div>
      </form>
    </div>
  );
}

export function AcceptInvitePage() {
  const { token = "" } = useParams();
  const { t } = useTranslation();
  const me = useMe();
  const preview = useInvitationPreview(token, !!me.data);
  const accept = useAcceptInvitation();
  const navigate = useNavigate();
  if (me.isLoading) return <Spinner />;
  if (!me.data) return <Navigate to={`/login?next=${encodeURIComponent(`/invite/${token}`)}`} replace />;
  return (
    <AuthFrame title={t("invite.title")}>
      {preview.isLoading && <Spinner />}
      <ErrorAlert error={preview.error} />
      {preview.data && (
        <div className="space-y-4">
          <p className="text-sm">{t("invite.body", { tree: preview.data.tree_name })}</p>
          <div className="flex flex-wrap gap-1">
            {preview.data.roles.map((r) => (
              <Badge key={r} tone="saffron">
                {t(`enum.role.${r}`)}
              </Badge>
            ))}
          </div>
          <p className="text-xs text-ink-muted">{t("invite.sentTo", { email: preview.data.email })}</p>
          {me.data && preview.data.email.toLowerCase() !== me.data.email.toLowerCase() && (
            <p role="alert" className="rounded-lg border border-haldi-300 bg-haldi-100 p-3 text-sm text-haldi-700">
              {t("invite.otherEmail", { invited: preview.data.email, me: me.data.email })}
            </p>
          )}
          {preview.data.expired ? (
            <ErrorAlert error={new Error(t("invite.expired"))} />
          ) : (
            <>
              {accept.error instanceof ApiError && (accept.error.code === "scope_conflict" || accept.error.code === "invitation_email_mismatch") ? (
                <p role="alert" className="rounded-lg border border-haldi-300 bg-haldi-100 p-3 text-sm text-haldi-700">
                  {accept.error.code === "scope_conflict" ? t("invite.scopeConflict") : t("invite.otherEmail", { invited: preview.data.email, me: me.data.email })}
                </p>
              ) : (
                <ErrorAlert error={accept.error} />
              )}
              <Button className="w-full" loading={accept.isPending} onClick={() => accept.mutate(token, { onSuccess: (tree) => navigate(`/t/${tree.id}`) })}>
                {t("invite.accept")}
              </Button>
            </>
          )}
        </div>
      )}
    </AuthFrame>
  );
}
