import { useState, type FormEvent } from "react";
import { Link, useNavigate, useParams } from "react-router-dom";
import { useTranslation } from "react-i18next";
import { Landmark, Plus, Trash2, Users, Wand2 } from "lucide-react";
import type { DescentRule, PersonSummary } from "../../api/types";
import { useAddBranchMembers, useBranch, useBranches, useCreateBranch, useDeleteBranch, useDeriveBranch, useRemoveBranchMember } from "../../api/hooks/family";
import { usePerson } from "../../api/hooks/people";
import { useTreeCtx } from "../../lib/tree-context";
import { Perm } from "../../lib/permissions";
import { PersonPicker } from "../../components/pickers";
import { PersonBadges, PersonLink, PrivatePersonPlaceholder } from "../../components/person/badges";
import { HeritageProfile } from "../../components/heritage/HeritageProfile";
import { Button } from "../../components/ui/Button";
import { ConfirmDialog, Dialog } from "../../components/ui/Dialog";
import { EmptyState, ErrorAlert, LiveRegion, PageHeader, Spinner } from "../../components/ui/feedback";
import { Field, Select, TextArea, TextInput } from "../../components/ui/form";
import { Badge } from "../../components/ui/Badge";
import { Tabs } from "../../components/ui/Tabs";

export const DESCENT_RULES: DescentRule[] = ["patrilineal", "matrilineal", "bilateral", "custom"];

export function BranchesPage() {
  const { t } = useTranslation();
  const { treeId, can } = useTreeCtx();
  const branches = useBranches(treeId);
  const [creating, setCreating] = useState(false);
  return (
    <div>
      <PageHeader
        title={t("branches.title")}
        subtitle={t("branches.subtitle")}
        actions={
          can(Perm.FAMILY_WRITE) ? (
            <Button icon={<Plus className="size-4" aria-hidden />} onClick={() => setCreating(true)}>
              {t("branches.create")}
            </Button>
          ) : undefined
        }
      />
      {branches.isLoading && <Spinner />}
      <ErrorAlert error={branches.error} />
      {branches.data?.length === 0 && <EmptyState icon={<Landmark className="size-10" aria-hidden />} title={t("branches.empty")}>{t("branches.emptyHint")}</EmptyState>}
      <ul className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
        {branches.data?.map((b) => (
          <li key={b.id}>
            <Link to={`/t/${treeId}/branches/${b.id}`} className="card block h-full p-4 hover:border-kumkum-200">
              <h2 className="font-display text-lg font-semibold text-kumkum-900">{b.name}</h2>
              {b.description && <p className="line-clamp-2 text-sm text-ink-muted">{b.description}</p>}
              <div className="mt-2 flex flex-wrap gap-1">
                <Badge tone="saffron">{t(`enum.descentRule.${b.descent_rule}`)}</Badge>
                <Badge tone="stone" icon={<Users className="size-3" aria-hidden />}>
                  {t("branches.memberCount", { count: b.member_count ?? 0 })}
                </Badge>
              </div>
            </Link>
          </li>
        ))}
      </ul>
      {creating && <CreateBranchDialog onClose={() => setCreating(false)} />}
    </div>
  );
}

function CreateBranchDialog({ onClose }: { onClose: () => void }) {
  const { t } = useTranslation();
  const { treeId } = useTreeCtx();
  const branches = useBranches(treeId);
  const create = useCreateBranch(treeId);
  const navigate = useNavigate();
  const [name, setName] = useState("");
  const [description, setDescription] = useState("");
  const [rule, setRule] = useState<DescentRule>("patrilineal");
  const [founder, setFounder] = useState<PersonSummary | null>(null);
  const [parent, setParent] = useState("");
  const [submitted, setSubmitted] = useState(false);
  const submit = (e: FormEvent) => {
    e.preventDefault();
    setSubmitted(true);
    if (!name.trim()) return;
    create.mutate(
      { name: name.trim(), description: description.trim() || null, descent_rule: rule, founder_person_id: founder?.id ?? null, parent_branch_id: parent || null },
      { onSuccess: (b) => navigate(`/t/${treeId}/branches/${b.id}`) },
    );
  };
  return (
    <Dialog
      open
      onClose={onClose}
      title={t("branches.create")}
      footer={
        <>
          <Button variant="secondary" onClick={onClose}>
            {t("common.cancel")}
          </Button>
          <Button type="submit" form="branch-form" loading={create.isPending}>
            {t("common.create")}
          </Button>
        </>
      }
    >
      <form id="branch-form" onSubmit={submit} className="space-y-3" noValidate>
        <Field label={t("branches.name")} required error={submitted && !name.trim() ? t("common.required") : null}>
          {(p) => <TextInput {...p} value={name} onChange={(e) => setName(e.target.value)} />}
        </Field>
        <Field label={t("branches.descentRule")} hint={t(`branches.ruleHint.${rule}`)}>
          {(p) => (
            <Select {...p} value={rule} onChange={(e) => setRule(e.target.value as DescentRule)}>
              {DESCENT_RULES.map((r) => (
                <option key={r} value={r}>
                  {t(`enum.descentRule.${r}`)}
                </option>
              ))}
            </Select>
          )}
        </Field>
        <PersonPicker treeId={treeId} label={t("branches.founder")} value={founder} onChange={setFounder} hint={t("branches.founderHint")} />
        <Field label={t("branches.parentBranch")}>
          {(p) => (
            <Select {...p} value={parent} onChange={(e) => setParent(e.target.value)}>
              <option value="">{t("common.none")}</option>
              {branches.data?.map((b) => (
                <option key={b.id} value={b.id}>
                  {b.name}
                </option>
              ))}
            </Select>
          )}
        </Field>
        <Field label={t("branches.description")}>{(p) => <TextArea {...p} value={description} onChange={(e) => setDescription(e.target.value)} />}</Field>
        <ErrorAlert error={create.error} />
      </form>
    </Dialog>
  );
}

export function BranchDetailPage() {
  const { branchId = "" } = useParams();
  const { t } = useTranslation();
  const { treeId, can } = useTreeCtx();
  const branch = useBranch(treeId, branchId);
  const founder = usePerson(treeId, branch.data?.founder_person_id ?? undefined);
  const derive = useDeriveBranch(treeId, branchId);
  const addMembers = useAddBranchMembers(treeId, branchId);
  const remove = useRemoveBranchMember(treeId, branchId);
  const del = useDeleteBranch(treeId);
  const navigate = useNavigate();
  const [tab, setTab] = useState("members");
  const [adding, setAdding] = useState<PersonSummary | null>(null);
  const [confirmDelete, setConfirmDelete] = useState(false);
  const canWrite = can(Perm.FAMILY_WRITE);
  if (branch.isLoading) return <Spinner />;
  if (!branch.data) return <ErrorAlert error={branch.error} />;
  const b = branch.data;
  return (
    <div>
      <PageHeader
        eyebrow={t("branches.eyebrow")}
        title={b.name}
        subtitle={b.description ?? undefined}
        actions={
          canWrite ? (
            <>
              {b.founder_person_id && (
                <Button variant="secondary" icon={<Wand2 className="size-4" aria-hidden />} loading={derive.isPending} onClick={() => derive.mutate()}>
                  {t("branches.derive")}
                </Button>
              )}
              <Button variant="ghost" icon={<Trash2 className="size-4" aria-hidden />} onClick={() => setConfirmDelete(true)}>
                {t("common.delete")}
              </Button>
            </>
          ) : undefined
        }
      />
      <div className="mb-4 flex flex-wrap gap-2 text-sm">
        <Badge tone="saffron">{t(`enum.descentRule.${b.descent_rule}`)}</Badge>
        {founder.data && (
          <span>
            {t("branches.founder")}: <PersonLink treeId={treeId} person={founder.data} />
          </span>
        )}
      </div>
      <ErrorAlert error={derive.error} />
      <LiveRegion message={derive.data ? t("branches.derived", { added: derive.data.added, total: derive.data.total }) : ""} />
      {derive.data && <p className="mb-3 rounded-lg bg-leaf-50 px-3 py-2 text-sm text-leaf-700">{t("branches.derived", { added: derive.data.added, total: derive.data.total })}</p>}
      <Tabs label={t("branches.sections")} tabs={[{ id: "members", label: t("branches.members"), count: b.members?.length ?? 0 }, { id: "heritage", label: t("heritage.title") }]} active={tab} onChange={setTab}>
        {tab === "members" ? (
          <section>
            <p className="mb-2 text-xs text-ink-muted">{t("branches.deriveHint", { rule: t(`enum.descentRule.${b.descent_rule}`) })}</p>
            {canWrite && (
              <div className="mb-3 flex flex-col gap-2 sm:flex-row sm:items-end">
                <div className="flex-1">
                  <PersonPicker treeId={treeId} label={t("branches.addMember")} value={adding} onChange={setAdding} />
                </div>
                <Button disabled={!adding} loading={addMembers.isPending} onClick={() => adding && addMembers.mutate([adding.id], { onSuccess: () => setAdding(null) })}>
                  {t("common.add")}
                </Button>
              </div>
            )}
            <ErrorAlert error={addMembers.error || remove.error} />
            <ul className="card divide-y divide-stone-100">
              {(b.members ?? []).map((m, i) => (
                <li key={m.person?.id ?? i} className="flex flex-col gap-1 px-4 py-2 sm:flex-row sm:items-center sm:justify-between">
                  <div className="flex items-center gap-2">
                    {m.person ? <PersonLink treeId={treeId} person={m.person} /> : <PrivatePersonPlaceholder />}
                    <Badge tone={m.basis === "founder" ? "saffron" : "stone"}>{t(`enum.branchBasis.${m.basis}`, { defaultValue: m.basis })}</Badge>
                  </div>
                  <div className="flex items-center gap-2">
                    {m.person && <PersonBadges person={m.person} />}
                    {canWrite && m.person && (
                      <button type="button" className="rounded p-1 text-red-800 hover:bg-red-50" onClick={() => remove.mutate(m.person!.id)} aria-label={t("branches.removeMember", { name: m.person.display_name })}>
                        <Trash2 className="size-4" aria-hidden />
                      </button>
                    )}
                  </div>
                </li>
              ))}
              {(b.hidden_member_count ?? 0) > 0 && (
                <li className="px-4 py-2">
                  <PrivatePersonPlaceholder /> <span className="text-xs text-ink-muted">× {b.hidden_member_count}</span>
                </li>
              )}
            </ul>
          </section>
        ) : (
          <HeritageProfile subject={{ kind: "branch", id: b.id }} canWrite={canWrite} />
        )}
      </Tabs>
      <ConfirmDialog
        open={confirmDelete}
        onClose={() => setConfirmDelete(false)}
        title={t("branches.deleteTitle", { name: b.name })}
        body={t("branches.deleteBody")}
        confirmLabel={t("common.delete")}
        danger
        loading={del.isPending}
        onConfirm={() => del.mutate(b.id, { onSuccess: () => navigate(`/t/${treeId}/branches`) })}
      >
        <ErrorAlert error={del.error} />
      </ConfirmDialog>
    </div>
  );
}
