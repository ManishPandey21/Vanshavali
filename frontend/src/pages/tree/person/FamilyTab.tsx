import { useState } from "react";
import { useTranslation } from "react-i18next";
import { HeartHandshake, Plus, Unlink, UserPlus } from "lucide-react";
import type { FamilyOut, Lineage, PersonOut, RelatedPerson, UnionOut } from "../../../api/types";
import { useDeleteRelationship, useFamily } from "../../../api/hooks/people";
import { useTreeCtx } from "../../../lib/tree-context";
import { Perm } from "../../../lib/permissions";
import { DateText } from "../../../components/dates/DateText";
import { EvidenceBadge, PersonBadges, PersonLink, PrivatePersonPlaceholder, RelTypeBadge } from "../../../components/person/badges";
import { Button } from "../../../components/ui/Button";
import { ConfirmDialog } from "../../../components/ui/Dialog";
import { EmptyState, ErrorAlert, Spinner } from "../../../components/ui/feedback";
import { Badge } from "../../../components/ui/Badge";
import { AddRelativeDialog, type RelationKind } from "./AddRelativeDialog";

export const LINEAGES: Lineage[] = ["biological", "legal", "ritual", "social"];

export function LineageToggle({ value, onChange }: { value: Lineage[]; onChange: (v: Lineage[]) => void }) {
  const { t } = useTranslation();
  const toggle = (l: Lineage) => onChange(value.includes(l) ? value.filter((x) => x !== l) : [...value, l]);
  return (
    <div role="group" aria-label={t("lineage.label")} className="flex flex-wrap items-center gap-1">
      <button
        type="button"
        aria-pressed={value.length === 0}
        onClick={() => onChange([])}
        className={`rounded-full border px-2.5 py-1 text-xs ${value.length === 0 ? "border-kumkum-700 bg-kumkum-700 text-white" : "border-stone-300 bg-white"}`}
      >
        {t("lineage.all")}
      </button>
      {LINEAGES.map((l) => (
        <button
          key={l}
          type="button"
          aria-pressed={value.includes(l)}
          onClick={() => toggle(l)}
          className={`rounded-full border px-2.5 py-1 text-xs ${value.includes(l) ? "border-kumkum-700 bg-kumkum-700 text-white" : "border-stone-300 bg-white"}`}
        >
          {t(`enum.lineage.${l}`)}
        </button>
      ))}
    </div>
  );
}

function RelativeRow({
  rel,
  extra,
  canUnlink,
  onUnlink,
}: {
  rel: RelatedPerson;
  extra?: React.ReactNode;
  canUnlink: boolean;
  onUnlink?: () => void;
}) {
  const { t } = useTranslation();
  const { treeId } = useTreeCtx();
  return (
    <li className="flex flex-col gap-1 py-2 sm:flex-row sm:items-center sm:justify-between">
      <div className="flex min-w-0 flex-wrap items-center gap-2">
        {rel.hidden || !rel.person ? <PrivatePersonPlaceholder /> : <PersonLink treeId={treeId} person={rel.person} />}
        {extra}
        {rel.relationship_type && <RelTypeBadge type={rel.relationship_type} subtype={rel.subtype} />}
        {rel.lineage && rel.lineage !== "biological" && <Badge tone="stone">{t(`enum.lineage.${rel.lineage}`)}</Badge>}
        {rel.evidence_status && rel.evidence_status !== "USER_ASSERTION" && <EvidenceBadge status={rel.evidence_status} />}
      </div>
      <div className="flex items-center gap-2">
        {rel.person && <PersonBadges person={rel.person} />}
        {canUnlink && rel.relationship_id && onUnlink && (
          <button type="button" className="rounded p-1 text-ink-muted hover:bg-red-50 hover:text-red-800" onClick={onUnlink} aria-label={t("family.unlink")}>
            <Unlink className="size-4" aria-hidden />
          </button>
        )}
      </div>
    </li>
  );
}

export function FamilyTab({ person }: { person: PersonOut }) {
  const { t } = useTranslation();
  const { treeId, can } = useTreeCtx();
  const [lineage, setLineage] = useState<Lineage[]>([]);
  const family = useFamily(treeId, person.id, lineage);
  const [adding, setAdding] = useState<{ relation: RelationKind; unionId?: string | null } | null>(null);
  const [unlinking, setUnlinking] = useState<string | null>(null);
  const del = useDeleteRelationship(treeId);
  const canWrite = !!person.can_edit && can(Perm.RELATIONSHIP_WRITE);

  return (
    <section aria-labelledby="fam-title" className="space-y-4">
      <div className="flex flex-col gap-2 sm:flex-row sm:items-center sm:justify-between">
        <h2 id="fam-title" className="font-display text-lg font-semibold">
          {t("family.title")}
        </h2>
        <LineageToggle value={lineage} onChange={setLineage} />
      </div>
      {canWrite && (
        <div className="flex flex-wrap gap-2">
          {(["parent", "spouse", "child", "sibling"] as const).map((r) => (
            <Button key={r} size="sm" variant="secondary" icon={<UserPlus className="size-4" aria-hidden />} onClick={() => setAdding({ relation: r })}>
              {t(`relatives.add.${r}`)}
            </Button>
          ))}
        </div>
      )}
      {family.isLoading && <Spinner />}
      <ErrorAlert error={family.error} />
      {family.data && <FamilyPanel family={family.data} canWrite={canWrite} onAddChild={(unionId) => setAdding({ relation: "child", unionId })} onUnlink={setUnlinking} />}
      {adding && family.data && (
        <AddRelativeDialog
          anchor={person}
          relation={adding.relation}
          unions={family.data.unions}
          initialUnionId={adding.unionId}
          onClose={() => setAdding(null)}
        />
      )}
      <ConfirmDialog
        open={!!unlinking}
        onClose={() => setUnlinking(null)}
        title={t("family.unlinkTitle")}
        body={t("family.unlinkBody")}
        confirmLabel={t("family.unlink")}
        danger
        loading={del.isPending}
        onConfirm={() => unlinking && del.mutate(unlinking, { onSuccess: () => setUnlinking(null) })}
      >
        <ErrorAlert error={del.error} />
      </ConfirmDialog>
    </section>
  );
}

export function FamilyPanel({
  family,
  canWrite,
  onAddChild,
  onUnlink,
}: {
  family: FamilyOut;
  canWrite: boolean;
  onAddChild?: (unionId: string) => void;
  onUnlink?: (relationshipId: string) => void;
}) {
  const { t } = useTranslation();
  // A union whose partner is hidden from the viewer has relationship=null (no details at all).
  const unions = [...family.unions].sort((a, b) => (a.relationship?.union_order ?? 99) - (b.relationship?.union_order ?? 99));
  const empty = !family.parents.length && !unions.length && !family.other_children.length && !family.siblings.length;
  if (empty) return <EmptyState title={t("family.empty")}>{t("family.emptyHint")}</EmptyState>;
  return (
    <div className="grid gap-4 lg:grid-cols-2">
      <div className="card p-4">
        <h3 className="font-display font-semibold">{t("family.parents")}</h3>
        {family.parents.length === 0 ? (
          <p className="text-sm text-ink-muted">{t("family.noneRecorded")}</p>
        ) : (
          <ul className="divide-y divide-stone-100">
            {family.parents.map((p, i) => (
              <RelativeRow key={p.relationship_id ?? i} rel={p} canUnlink={canWrite} onUnlink={() => p.relationship_id && onUnlink?.(p.relationship_id)} />
            ))}
          </ul>
        )}
      </div>
      <div className="card p-4">
        <h3 className="font-display font-semibold">{t("family.siblings")}</h3>
        {family.siblings.length === 0 ? (
          <p className="text-sm text-ink-muted">{t("family.noneRecorded")}</p>
        ) : (
          <ul className="divide-y divide-stone-100">
            {family.siblings.map((s, i) => (
              <RelativeRow
                key={(s.person?.id ?? "h") + i}
                rel={{ ...s, relationship_type: s.kind === "explicit" ? s.relationship_type : null }}
                extra={<Badge tone={s.kind === "full" ? "neutral" : "violet"}>{t(`enum.siblingKind.${s.kind}`)}</Badge>}
                canUnlink={canWrite && s.kind === "explicit"}
                onUnlink={() => s.relationship_id && onUnlink?.(s.relationship_id)}
              />
            ))}
          </ul>
        )}
      </div>
      <div className="space-y-3 lg:col-span-2">
        <h3 className="font-display font-semibold">{t("family.unions")}</h3>
        {unions.length === 0 && <p className="text-sm text-ink-muted">{t("family.noneRecorded")}</p>}
        {unions.map((u, i) => (
          <UnionCard key={u.relationship?.id ?? `hidden-${i}`} union={u} index={i} canWrite={canWrite} onAddChild={onAddChild} onUnlink={onUnlink} />
        ))}
        {family.other_children.length > 0 && (
          <div className="card p-4">
            <h4 className="text-sm font-semibold">{t("family.otherChildren")}</h4>
            <ul className="divide-y divide-stone-100">
              {family.other_children.map((c, i) => (
                <RelativeRow key={c.relationship_id ?? i} rel={c} canUnlink={canWrite} onUnlink={() => c.relationship_id && onUnlink?.(c.relationship_id)} />
              ))}
            </ul>
          </div>
        )}
      </div>
    </div>
  );
}

function UnionCard({
  union,
  index,
  canWrite,
  onAddChild,
  onUnlink,
}: {
  union: UnionOut;
  index: number;
  canWrite: boolean;
  onAddChild?: (unionId: string) => void;
  onUnlink?: (id: string) => void;
}) {
  const { t } = useTranslation();
  const r = union.relationship;
  if (!r) {
    return (
      <article className="card border-l-4 border-l-stone-300 p-4" aria-label={t("family.unionN", { n: index + 1 })}>
        <p className="flex items-center gap-2 text-xs font-semibold uppercase tracking-wide text-ink-muted">
          <HeartHandshake className="size-4" aria-hidden />
          {t("family.unionN", { n: index + 1 })}
        </p>
        <div className="py-2">
          <PrivatePersonPlaceholder />
        </div>
        {(union.children ?? []).length > 0 && (
          <ul className="mt-2 divide-y divide-stone-200 rounded-lg bg-parchment p-3">
            {union.children!.map((c, i) => (
              <RelativeRow key={c.relationship_id ?? i} rel={c} canUnlink={false} />
            ))}
          </ul>
        )}
      </article>
    );
  }
  return (
    <article className="card border-l-4 border-l-haldi-500 p-4" aria-label={t("family.unionN", { n: index + 1 })}>
      <div className="flex flex-wrap items-center justify-between gap-2">
        <p className="flex items-center gap-2 text-xs font-semibold uppercase tracking-wide text-ink-muted">
          <HeartHandshake className="size-4 text-kumkum-700" aria-hidden />
          {t("family.unionN", { n: r.union_order ?? index + 1 })}
          <RelTypeBadge type={r.type} subtype={r.subtype} />
        </p>
        {r.start_date && (
          <span className="text-xs text-ink-muted">
            {t("family.since")} <DateText date={r.start_date} showOriginal={false} />
          </span>
        )}
      </div>
      <ul className="divide-y divide-stone-100">
        <RelativeRow rel={{ ...union.partner, relationship_type: null }} canUnlink={canWrite} onUnlink={() => onUnlink?.(r.id)} />
      </ul>
      <div className="mt-2 rounded-lg bg-parchment p-3">
        <div className="flex items-center justify-between">
          <p className="text-xs font-semibold uppercase tracking-wide text-ink-muted">{t("family.childrenOfUnion", { count: union.children?.length ?? 0 })}</p>
          {canWrite && onAddChild && (
            <Button size="sm" variant="ghost" icon={<Plus className="size-3.5" aria-hidden />} onClick={() => onAddChild(r.id)}>
              {t("relatives.add.child")}
            </Button>
          )}
        </div>
        {(union.children ?? []).length > 0 && (
          <ul className="divide-y divide-stone-200">
            {union.children!.map((c, i) => (
              <RelativeRow key={c.relationship_id ?? i} rel={c} canUnlink={canWrite} onUnlink={() => c.relationship_id && onUnlink?.(c.relationship_id)} />
            ))}
          </ul>
        )}
      </div>
    </article>
  );
}
