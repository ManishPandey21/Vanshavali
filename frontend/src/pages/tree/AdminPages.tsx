import { useState, type FormEvent } from "react";
import { Link, Navigate } from "react-router-dom";
import { useTranslation } from "react-i18next";
import { AlertTriangle, Check, Copy, Globe2, Trash2, UserPlus, X } from "lucide-react";
import type { InvitationOut, MemberOut, MemberUpdate, PersonSummary, PrivacyLevel, PublicMode, Role } from "../../api/types";
import { PersonPicker } from "../../components/pickers";
import {
  useAudit,
  useClaims,
  useCreateInvitation,
  useInvitations,
  useMembers,
  useRemoveMember,
  useReviewClaim,
  useRevokeInvitation,
  useUpdateMember,
  useUpdateTree,
} from "../../api/hooks/trees";
import { useBranches } from "../../api/hooks/family";
import { useMe } from "../../api/hooks/auth";
import { useDeletedPeople, usePerson, useRestorePerson } from "../../api/hooks/people";
import { lifespan } from "../../lib/dates";
import { useTreeCtx } from "../../lib/tree-context";
import { Perm } from "../../lib/permissions";
import { PRIVACY_LEVELS } from "../../components/person/PersonForm";
import { Button } from "../../components/ui/Button";
import { ConfirmDialog, Dialog } from "../../components/ui/Dialog";
import { EmptyState, ErrorAlert, LiveRegion, PageHeader, Spinner } from "../../components/ui/feedback";
import { Checkbox, Field, Select, TextArea, TextInput } from "../../components/ui/form";
import { Badge } from "../../components/ui/Badge";

export const ROLES: Role[] = ["OWNER", "FAMILY_ADMIN", "BRANCH_ADMIN", "CONTRIBUTOR", "RESEARCHER", "VIEWER", "DOCUMENT_CUSTODIAN", "PROPERTY_CUSTODIAN"];

function RolePicker({ value, onChange, legend }: { value: Role[]; onChange: (r: Role[]) => void; legend: string }) {
  const { t } = useTranslation();
  return (
    <fieldset>
      <legend className="label">{legend}</legend>
      <div className="grid grid-cols-1 gap-1 sm:grid-cols-2">
        {ROLES.map((r) => (
          <Checkbox key={r} label={t(`enum.role.${r}`)} hint={t(`enum.roleHint.${r}`)} checked={value.includes(r)} onChange={(c) => onChange(c ? [...value, r] : value.filter((x) => x !== r))} />
        ))}
      </div>
    </fieldset>
  );
}

export function MembersPage() {
  const { t, i18n } = useTranslation();
  const { treeId, can } = useTreeCtx();
  const members = useMembers(treeId);
  const me = useMe();
  const [editing, setEditing] = useState<MemberOut | null>(null);
  const [removing, setRemoving] = useState<MemberOut | null>(null);
  const remove = useRemoveMember(treeId);
  const manage = can(Perm.MEMBERS_MANAGE);
  return (
    <div>
      <PageHeader
        title={t("members.title")}
        subtitle={t("members.subtitle")}
        actions={
          manage ? (
            <Link to={`/t/${treeId}/admin/invitations`} className="inline-flex items-center gap-1.5 rounded-lg bg-kumkum-700 px-3.5 py-2 text-sm font-medium text-white hover:bg-kumkum-800">
              <UserPlus className="size-4" aria-hidden /> {t("invitations.create")}
            </Link>
          ) : undefined
        }
      />
      {members.isLoading && <Spinner />}
      <ErrorAlert error={members.error || remove.error} />
      <div className="card relative overflow-x-auto">
        <table className="w-full text-sm">
          <caption className="sr-only">{t("members.title")}</caption>
          <thead className="bg-parchment text-left text-xs uppercase tracking-wide text-ink-muted">
            <tr>
              <th scope="col" className="px-4 py-2">
                {t("members.name")}
              </th>
              <th scope="col" className="px-4 py-2">
                {t("members.roles")}
              </th>
              <th scope="col" className="px-4 py-2">
                {t("members.since")}
              </th>
              {manage && (
                <th scope="col" className="px-4 py-2">
                  <span className="sr-only">{t("common.actions")}</span>
                </th>
              )}
            </tr>
          </thead>
          <tbody className="divide-y divide-stone-100">
            {members.data?.map((m) => (
              <tr key={m.id}>
                <td className="px-4 py-2">
                  <p className="font-medium">
                    {m.display_name} {m.user_id === me.data?.id && <Badge tone="green">{t("members.you")}</Badge>}
                  </p>
                  {m.email && <p className="text-xs text-ink-muted">{m.email}</p>}
                  {m.linked_person_id && <LinkedPerson personId={m.linked_person_id} />}
                </td>
                <td className="px-4 py-2">
                  <div className="flex flex-wrap gap-1">
                    {m.roles.map((r) => (
                      <Badge key={r} tone="saffron">
                        {t(`enum.role.${r}`)}
                      </Badge>
                    ))}
                    {m.branch_id && <Badge tone="violet">{t("members.branchScoped")}</Badge>}
                  </div>
                </td>
                <td className="px-4 py-2 text-xs text-ink-muted">{new Date(m.created_at).toLocaleDateString(i18n.language)}</td>
                {manage && (
                  <td className="px-4 py-2 text-right">
                    <div className="flex justify-end gap-1">
                      <Button size="sm" variant="ghost" onClick={() => setEditing(m)}>
                        {t("members.changeRoles")}
                      </Button>
                      {m.user_id !== me.data?.id && (
                        <Button size="sm" variant="ghost" icon={<Trash2 className="size-4" aria-hidden />} onClick={() => setRemoving(m)} aria-label={t("members.removeNamed", { name: m.display_name })} />
                      )}
                    </div>
                  </td>
                )}
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      {editing && <EditMemberDialog member={editing} onClose={() => setEditing(null)} />}
      <ConfirmDialog
        open={!!removing}
        onClose={() => setRemoving(null)}
        title={t("members.removeTitle", { name: removing?.display_name ?? "" })}
        body={t("members.removeBody")}
        confirmLabel={t("members.remove")}
        danger
        loading={remove.isPending}
        onConfirm={() => removing && remove.mutate(removing.id, { onSuccess: () => setRemoving(null) })}
      >
        <ErrorAlert error={remove.error} />
      </ConfirmDialog>
    </div>
  );
}

function LinkedPerson({ personId }: { personId: string }) {
  const { t } = useTranslation();
  const { treeId } = useTreeCtx();
  const p = usePerson(treeId, personId);
  if (!p.data) return null;
  return (
    <p className="text-xs">
      {t("members.linkedTo")}{" "}
      <Link className="text-kumkum-800 underline" to={`/t/${treeId}/people/${personId}`}>
        {p.data.display_name}
      </Link>
    </p>
  );
}

function EditMemberDialog({ member, onClose }: { member: MemberOut; onClose: () => void }) {
  const { t } = useTranslation();
  const { treeId, isAdmin } = useTreeCtx();
  const me = useMe();
  const update = useUpdateMember(treeId);
  const branches = useBranches(treeId);
  const linked = usePerson(treeId, member.linked_person_id ?? undefined);
  const [roles, setRoles] = useState<Role[]>(member.roles);
  const [branch, setBranch] = useState(member.branch_id ?? "");
  const [person, setPerson] = useState<PersonSummary | null | undefined>(undefined);
  // Only admins may link a member to a person, and never on their own membership (self-linking
  // goes through a profile claim that another admin reviews).
  const canLink = isAdmin && member.user_id !== me.data?.id;
  const currentLinked = person === undefined ? (linked.data ?? null) : person;
  const submit = () => {
    if (!roles.length) return;
    const body: MemberUpdate = { roles, branch_id: branch || null, clear_branch: !branch && !!member.branch_id };
    if (canLink && person !== undefined) {
      if (person) body.linked_person_id = person.id;
      else body.clear_linked_person = true;
    }
    update.mutate({ id: member.id, body }, { onSuccess: onClose });
  };
  return (
    <Dialog
      open
      onClose={onClose}
      title={t("members.editTitle", { name: member.display_name })}
      footer={
        <>
          <Button variant="secondary" onClick={onClose}>
            {t("common.cancel")}
          </Button>
          <Button onClick={submit} loading={update.isPending} disabled={!roles.length}>
            {t("common.save")}
          </Button>
        </>
      }
    >
      <div className="space-y-3">
        <RolePicker value={roles} onChange={setRoles} legend={t("members.roles")} />
        {!roles.length && <p className="field-error">{t("members.atLeastOneRole")}</p>}
        <Field label={t("members.branchScope")} hint={t("members.branchScopeHint")}>
          {(p) => (
            <Select {...p} value={branch} onChange={(e) => setBranch(e.target.value)}>
              <option value="">{t("members.wholeTree")}</option>
              {branches.data?.map((b) => (
                <option key={b.id} value={b.id}>
                  {b.name}
                </option>
              ))}
            </Select>
          )}
        </Field>
        {canLink && <PersonPicker treeId={treeId} label={t("members.linkedPerson")} value={currentLinked} onChange={setPerson} hint={t("members.linkedPersonHint")} />}
        <ErrorAlert error={update.error} />
      </div>
    </Dialog>
  );
}

export function InvitationsPage() {
  const { t, i18n } = useTranslation();
  const { treeId, can } = useTreeCtx();
  const invites = useInvitations(treeId, can(Perm.MEMBERS_MANAGE));
  const create = useCreateInvitation(treeId);
  const revoke = useRevokeInvitation(treeId);
  const branches = useBranches(treeId);
  const [email, setEmail] = useState("");
  const [roles, setRoles] = useState<Role[]>(["VIEWER"]);
  const [branch, setBranch] = useState("");
  const [created, setCreated] = useState<InvitationOut | null>(null);
  const [copied, setCopied] = useState(false);
  if (!can(Perm.MEMBERS_MANAGE)) return <Navigate to={`/t/${treeId}/admin/members`} replace />;
  const submit = (e: FormEvent) => {
    e.preventDefault();
    if (!email.trim() || !roles.length) return;
    create.mutate(
      { email: email.trim(), roles, branch_id: branch || null },
      {
        onSuccess: (inv) => {
          setCreated(inv);
          setCopied(false);
          setEmail("");
        },
      },
    );
  };
  const status = (i: InvitationOut) =>
    i.accepted_at ? ["green", t("invitations.accepted")] : i.revoked_at ? ["stone", t("invitations.revoked")] : new Date(i.expires_at) < new Date() ? ["red", t("invitations.expired")] : ["saffron", t("invitations.pending")];
  return (
    <div>
      <PageHeader title={t("invitations.title")} subtitle={t("invitations.subtitle")} />
      <div className="grid gap-6 lg:grid-cols-2">
        <form onSubmit={submit} className="card space-y-3 p-4" noValidate>
          <h2 className="font-display text-lg font-semibold">{t("invitations.create")}</h2>
          <Field label={t("auth.email")} required>
            {(p) => <TextInput {...p} type="email" value={email} onChange={(e) => setEmail(e.target.value)} />}
          </Field>
          <RolePicker value={roles} onChange={setRoles} legend={t("members.roles")} />
          <Field label={t("members.branchScope")}>
            {(p) => (
              <Select {...p} value={branch} onChange={(e) => setBranch(e.target.value)}>
                <option value="">{t("members.wholeTree")}</option>
                {branches.data?.map((b) => (
                  <option key={b.id} value={b.id}>
                    {b.name}
                  </option>
                ))}
              </Select>
            )}
          </Field>
          <ErrorAlert error={create.error} />
          <Button type="submit" loading={create.isPending} disabled={!email.trim() || !roles.length}>
            {t("invitations.send")}
          </Button>
          {created?.invite_url && (
            <div role="status" className="rounded-lg border border-leaf-700/30 bg-leaf-50 p-3 text-sm">
              <p className="font-semibold text-leaf-700">{t("invitations.createdTitle", { email: created.email })}</p>
              <p className="mt-1 text-xs">{t("invitations.copyHint")}</p>
              <div className="mt-2 flex gap-2">
                <label className="sr-only" htmlFor="invite-url">
                  {t("invitations.link")}
                </label>
                <input id="invite-url" readOnly className="input font-mono text-xs" value={created.invite_url} onFocus={(e) => e.target.select()} />
                <Button
                  size="sm"
                  variant="secondary"
                  icon={copied ? <Check className="size-4" aria-hidden /> : <Copy className="size-4" aria-hidden />}
                  onClick={() => {
                    void navigator.clipboard?.writeText(created.invite_url!).then(() => setCopied(true));
                  }}
                >
                  {copied ? t("common.copied") : t("common.copy")}
                </Button>
              </div>
              <LiveRegion message={copied ? t("common.copied") : ""} />
            </div>
          )}
        </form>
        <section className="card p-4" aria-labelledby="inv-list">
          <h2 id="inv-list" className="font-display text-lg font-semibold">
            {t("invitations.list")}
          </h2>
          {invites.isLoading && <Spinner />}
          <ErrorAlert error={invites.error || revoke.error} />
          {invites.data?.length === 0 && <p className="text-sm text-ink-muted">{t("invitations.none")}</p>}
          <ul className="divide-y divide-stone-100">
            {invites.data?.map((i) => {
              const [tone, label] = status(i);
              const pending = !i.accepted_at && !i.revoked_at && new Date(i.expires_at) >= new Date();
              return (
                <li key={i.id} className="flex flex-wrap items-center justify-between gap-2 py-2">
                  <div>
                    <p className="text-sm font-medium">{i.email}</p>
                    <p className="text-xs text-ink-muted">
                      {i.roles.map((r) => t(`enum.role.${r}`)).join(", ")} · {t("invitations.expires", { date: new Date(i.expires_at).toLocaleDateString(i18n.language) })}
                    </p>
                  </div>
                  <div className="flex items-center gap-2">
                    <Badge tone={tone as "green"}>{label}</Badge>
                    {pending && (
                      <Button size="sm" variant="ghost" icon={<X className="size-4" aria-hidden />} loading={revoke.isPending && revoke.variables === i.id} onClick={() => revoke.mutate(i.id)}>
                        {t("invitations.revoke")}
                      </Button>
                    )}
                  </div>
                </li>
              );
            })}
          </ul>
        </section>
      </div>
    </div>
  );
}

export function AuditPage() {
  const { t, i18n } = useTranslation();
  const { treeId, can } = useTreeCtx();
  const [action, setAction] = useState("");
  const audit = useAudit(treeId, action || undefined);
  if (!can(Perm.AUDIT_READ)) return <Navigate to={`/t/${treeId}`} replace />;
  const items = audit.data?.pages.flatMap((p) => p.items) ?? [];
  return (
    <div>
      <PageHeader title={t("audit.title")} subtitle={t("audit.subtitle")} />
      <div className="mb-4 max-w-xs">
        <Field label={t("audit.filter")}>
          {(p) => (
            <Select {...p} value={action} onChange={(e) => setAction(e.target.value)}>
              <option value="">{t("common.all")}</option>
              {["person", "relationship", "event", "heritage", "household", "branch", "member", "tree", "consent", "profile", "citation", "source", "grant"].map((a) => (
                <option key={a} value={a}>
                  {a}.*
                </option>
              ))}
            </Select>
          )}
        </Field>
      </div>
      {audit.isLoading && <Spinner />}
      <ErrorAlert error={audit.error} />
      <ol className="card divide-y divide-stone-100">
        {items.map((e) => (
          <li key={e.id} className="flex flex-col gap-1 px-4 py-2 text-sm sm:flex-row sm:items-center sm:justify-between">
            <div>
              <code className="rounded bg-parchment px-1.5 py-0.5 text-xs">{e.action}</code>
              <span className="ml-2">{e.actor_name ?? t("audit.system")}</span>
              {e.summary && <span className="ml-2 text-ink-muted">{e.summary}</span>}
              {Object.keys(e.details ?? {}).length > 0 && <p className="mt-0.5 break-all font-mono text-[11px] text-ink-muted">{JSON.stringify(e.details)}</p>}
            </div>
            <time dateTime={e.created_at} className="shrink-0 text-xs text-ink-muted">
              {new Date(e.created_at).toLocaleString(i18n.language)}
            </time>
          </li>
        ))}
        {audit.data && items.length === 0 && <li className="px-4 py-3 text-sm text-ink-muted">{t("audit.none")}</li>}
      </ol>
      {audit.hasNextPage && (
        <div className="mt-4 flex justify-center">
          <Button variant="secondary" loading={audit.isFetchingNextPage} onClick={() => void audit.fetchNextPage()}>
            {t("common.loadMore")}
          </Button>
        </div>
      )}
    </div>
  );
}

export function SettingsPage() {
  const { t } = useTranslation();
  const { treeId, tree, can } = useTreeCtx();
  const update = useUpdateTree(treeId);
  const [name, setName] = useState(tree.name);
  const [description, setDescription] = useState(tree.description ?? "");
  const [privacy, setPrivacy] = useState<PrivacyLevel>(tree.default_person_privacy);
  const [publicMode, setPublicMode] = useState<PublicMode>(tree.public_mode);
  const [confirmPublic, setConfirmPublic] = useState(false);
  const [saved, setSaved] = useState("");
  if (!can(Perm.TREE_MANAGE)) return <Navigate to={`/t/${treeId}`} replace />;
  const save = (mode: PublicMode) =>
    update.mutate(
      { name: name.trim(), description: description.trim() || null, default_person_privacy: privacy, public_mode: mode },
      { onSuccess: () => setSaved(t("common.saved")) },
    );
  const submit = (e: FormEvent) => {
    e.preventDefault();
    if (!name.trim()) return;
    if (publicMode === "DECEASED_ONLY" && tree.public_mode !== "DECEASED_ONLY") setConfirmPublic(true);
    else save(publicMode);
  };
  return (
    <div className="mx-auto max-w-2xl">
      <PageHeader title={t("settings.title")} />
      <form onSubmit={submit} className="card space-y-4 p-5" noValidate>
        <Field label={t("trees.name")} required error={!name.trim() ? t("common.required") : null}>
          {(p) => <TextInput {...p} value={name} onChange={(e) => setName(e.target.value)} />}
        </Field>
        <Field label={t("trees.description")}>{(p) => <TextArea {...p} value={description} onChange={(e) => setDescription(e.target.value)} />}</Field>
        <Field label={t("settings.defaultPrivacy")} hint={t(`enum.privacyHint.${privacy}`)}>
          {(p) => (
            <Select {...p} value={privacy} onChange={(e) => setPrivacy(e.target.value as PrivacyLevel)}>
              {PRIVACY_LEVELS.map((l) => (
                <option key={l} value={l}>
                  {t(`enum.privacy.${l}`)}
                </option>
              ))}
            </Select>
          )}
        </Field>
        <fieldset className="rounded-lg border border-stone-300 p-3">
          <legend className="px-1 text-sm font-semibold">{t("settings.publicMode")}</legend>
          <div className="space-y-2 text-sm">
            <label className="flex items-start gap-2">
              <input type="radio" name="public_mode" className="mt-1 accent-kumkum-700" checked={publicMode === "OFF"} onChange={() => setPublicMode("OFF")} />
              <span>
                <span className="font-medium">{t("enum.publicMode.OFF")}</span>
                <span className="block text-xs text-ink-muted">{t("settings.publicOffHint")}</span>
              </span>
            </label>
            <label className="flex items-start gap-2">
              <input type="radio" name="public_mode" className="mt-1 accent-kumkum-700" checked={publicMode === "DECEASED_ONLY"} onChange={() => setPublicMode("DECEASED_ONLY")} />
              <span>
                <span className="font-medium">{t("enum.publicMode.DECEASED_ONLY")}</span>
                <span className="block text-xs text-ink-muted">{t("settings.publicDeceasedHint")}</span>
              </span>
            </label>
          </div>
          {publicMode === "DECEASED_ONLY" && (
            <p className="mt-3 flex items-start gap-2 rounded-lg bg-haldi-100 p-3 text-xs text-haldi-700">
              <AlertTriangle className="mt-0.5 size-4 shrink-0" aria-hidden />
              {t("settings.publicWarning")}
            </p>
          )}
          {tree.public_mode === "DECEASED_ONLY" && (
            <p className="mt-2 flex items-center gap-1 text-xs">
              <Globe2 className="size-3.5" aria-hidden />
              <Link to={`/p/${tree.slug}`} className="text-kumkum-800 underline">
                {t("settings.viewPublic", { slug: tree.slug })}
              </Link>
            </p>
          )}
        </fieldset>
        <ErrorAlert error={update.error} />
        <LiveRegion message={saved} />
        <Button type="submit" loading={update.isPending}>
          {t("common.save")}
        </Button>
      </form>
      <ConfirmDialog
        open={confirmPublic}
        onClose={() => setConfirmPublic(false)}
        title={t("settings.confirmPublicTitle")}
        body={t("settings.confirmPublicBody")}
        confirmLabel={t("settings.confirmPublic")}
        loading={update.isPending}
        onConfirm={() => {
          setConfirmPublic(false);
          save("DECEASED_ONLY");
        }}
      />
    </div>
  );
}

export function ClaimsPage() {
  const { t, i18n } = useTranslation();
  const { treeId, isAdmin } = useTreeCtx();
  const claims = useClaims(treeId);
  const review = useReviewClaim(treeId);
  const [notes, setNotes] = useState<Record<string, string>>({});
  return (
    <div>
      <PageHeader title={t("claims.title")} subtitle={isAdmin ? t("claims.subtitleAdmin") : t("claims.subtitleMine")} />
      {claims.isLoading && <Spinner />}
      <ErrorAlert error={claims.error || review.error} />
      {claims.data?.length === 0 && <EmptyState title={t("claims.none")} />}
      <ul className="space-y-3">
        {claims.data?.map((c) => (
          <li key={c.id} className="card p-4">
            <div className="flex flex-wrap items-center justify-between gap-2">
              <ClaimPerson personId={c.person_id} />
              <Badge tone={c.status === "approved" ? "green" : c.status === "rejected" ? "red" : "saffron"}>{t(`enum.claimStatus.${c.status}`)}</Badge>
            </div>
            <p className="mt-1 text-xs text-ink-muted">{new Date(c.created_at).toLocaleString(i18n.language)}</p>
            {c.message && <p className="mt-2 text-sm">“{c.message}”</p>}
            {c.review_note && (
              <p className="mt-1 text-xs text-ink-muted">
                {t("claims.reviewNote")}: {c.review_note}
              </p>
            )}
            {isAdmin && c.status === "requested" && (
              <div className="mt-3 flex flex-col gap-2 sm:flex-row sm:items-end">
                <Field label={t("claims.note")} className="flex-1">
                  {(p) => <TextInput {...p} value={notes[c.id] ?? ""} onChange={(e) => setNotes({ ...notes, [c.id]: e.target.value })} />}
                </Field>
                <Button icon={<Check className="size-4" aria-hidden />} loading={review.isPending} onClick={() => review.mutate({ id: c.id, approve: true, note: notes[c.id] })}>
                  {t("claims.approve")}
                </Button>
                <Button variant="secondary" icon={<X className="size-4" aria-hidden />} loading={review.isPending} onClick={() => review.mutate({ id: c.id, approve: false, note: notes[c.id] })}>
                  {t("claims.reject")}
                </Button>
              </div>
            )}
          </li>
        ))}
      </ul>
    </div>
  );
}

function ClaimPerson({ personId }: { personId: string }) {
  const { t } = useTranslation();
  const { treeId } = useTreeCtx();
  const p = usePerson(treeId, personId);
  return p.data ? (
    <Link className="font-medium text-kumkum-800 underline" to={`/t/${treeId}/people/${personId}`}>
      {p.data.display_name}
    </Link>
  ) : (
    <span className="italic text-ink-muted">{t("person.privatePerson")}</span>
  );
}

/** Recycle bin for people (tree admins): soft-deleted people, restorable with all their records. */
export function RestorePeoplePage() {
  const { t } = useTranslation();
  const { treeId, can } = useTreeCtx();
  const allowed = can(Perm.TREE_MANAGE);
  const deleted = useDeletedPeople(treeId, allowed);
  const restore = useRestorePerson(treeId);
  if (!allowed) return <Navigate to={`/t/${treeId}`} replace />;
  const items = deleted.data ?? [];
  return (
    <div className="mx-auto max-w-3xl">
      <PageHeader title={t("restore.title")} subtitle={t("restore.subtitle")} />
      {deleted.isLoading && <Spinner />}
      <ErrorAlert error={deleted.error || restore.error} />
      {deleted.data && items.length === 0 && <EmptyState title={t("restore.none")} />}
      {items.length > 0 && (
        <ul className="card divide-y divide-stone-100">
          {items.map((p) => (
            <li key={p.id} className="flex flex-wrap items-center justify-between gap-2 px-4 py-3 text-sm">
              <span>
                <span className="font-medium">{p.display_name}</span>
                {lifespan(p, t) && <span className="ml-1 text-xs text-ink-muted">({lifespan(p, t)})</span>}
              </span>
              <Button size="sm" loading={restore.isPending && restore.variables === p.id} onClick={() => restore.mutate(p.id)}>
                {t("restore.restore")}
              </Button>
            </li>
          ))}
        </ul>
      )}
      <LiveRegion message={restore.isSuccess ? t("restore.restored") : ""} />
    </div>
  );
}
