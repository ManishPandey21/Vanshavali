import { useEffect, useRef, useState } from "react";
import { Link } from "react-router-dom";
import { useTranslation } from "react-i18next";
import { GitFork, IdCard, Plus, Route, Users, X } from "lucide-react";
import type { RelatedPerson, SexAtBirth } from "../../api/types";
import { useFamily, usePerson, useRelationshipPath } from "../../api/hooks/people";
import { usePersonPhotos } from "../../api/hooks/lifeevents";
import { useTreeCtx } from "../../lib/tree-context";
import { hasPerm, Perm } from "../../lib/permissions";
import { describeChain } from "../../lib/kinship";
import { formatDate } from "../../lib/dates";
import { AddRelativeDialog, type RelationKind } from "../../pages/tree/person/AddRelativeDialog";
import { PersonBadges } from "../person/badges";
import { PhotoThumb } from "../events/PhotoThumb";
import { Spinner } from "../ui/feedback";
import { lifeLine, PersonAvatar } from "./FamilyCards";

type Role = "parent" | "spouse" | "child" | "sibling";

/** "father" / "mother" / "parent", … from the relation and the relative's sex at birth. */
export function roleKey(role: Role, sex: SexAtBirth | null | undefined): string {
  const by: Record<Role, [string, string, string]> = {
    parent: ["father", "mother", "parent"],
    spouse: ["husband", "wife", "spouse"],
    child: ["son", "daughter", "child"],
    sibling: ["brother", "sister", "sibling"],
  };
  const [m, f, any] = by[role];
  return `treeView.role.${sex === "male" ? m : sex === "female" ? f : any}`;
}

/** Whole years between an exact date of birth and today; null unless the day is known. */
export function ageFrom(birth: Record<string, unknown> | null | undefined, today = new Date()): number | null {
  const y = birth?.year as number | undefined;
  const m = birth?.month as number | undefined;
  const d = birth?.day as number | undefined;
  if (!y || !m || !d || (birth?.calendar && birth.calendar !== "gregorian")) return null;
  let age = today.getFullYear() - y;
  if (today.getMonth() + 1 < m || (today.getMonth() + 1 === m && today.getDate() < d)) age -= 1;
  return age >= 0 && age < 130 ? age : null;
}

/**
 * The person selected in the tree: who they are to you, their dates, quick actions (profile, centre
 * the family view on them, add a relative, how are we related) and their immediate family, each of
 * whom can be selected in turn. Focus moves to the name so keyboard and screen-reader users land
 * here after choosing someone.
 */
export function TreePersonPanel({
  personId,
  onSelect,
  onCentre,
  onClose,
  isFocus,
}: {
  personId: string;
  onSelect: (id: string) => void;
  onCentre: (id: string) => void;
  onClose: () => void;
  isFocus: boolean;
}) {
  const { t, i18n } = useTranslation();
  const { treeId, tree } = useTreeCtx();
  const person = usePerson(treeId, personId);
  const family = useFamily(treeId, personId);
  const photos = usePersonPhotos(treeId, personId);
  const me = tree.my_linked_person_id ?? "";
  const path = useRelationshipPath(treeId, me && me !== personId ? me : "", personId, []);
  const [menu, setMenu] = useState(false);
  const [adding, setAdding] = useState<RelationKind | null>(null);
  const heading = useRef<HTMLHeadingElement>(null);
  const canEdit = hasPerm(tree, Perm.PERSON_WRITE) && hasPerm(tree, Perm.RELATIONSHIP_WRITE);

  useEffect(() => {
    if (person.data) heading.current?.focus();
  }, [person.data?.id]); // eslint-disable-line react-hooks/exhaustive-deps

  if (person.isLoading || !person.data) {
    return (
      <aside className="card p-4" aria-busy>
        <Spinner />
      </aside>
    );
  }
  const p = person.data;
  const cover = photos.data?.find((x) => x.is_cover) ?? photos.data?.[0];

  let relation: string | null = null;
  if (me && me === p.id) relation = t("treeView.panel.thisIsYou");
  else if (path.data?.found) {
    const chain = path.data.chain ?? [];
    // the reader's word comes from the server's reviewed packs and the family's own words
    // (ADR-0026 §6), as on the relationship page; otherwise the literal reading or the label
    const regional = path.data.terms?.[0]?.term ?? null;
    const term = regional || (i18n.language.startsWith("hi") ? describeChain(chain, i18n.language) : path.data.label);
    if (term) relation = t("treeView.panel.yourRelation", { relation: term });
  }
  const age = p.profile_status === "living" ? ageFrom(p.birth?.date as Record<string, unknown> | undefined) : null;

  const f = family.data;
  const relatives: { role: Role; r: Pick<RelatedPerson, "person"> }[] = f
    ? [
        ...f.parents.map((r) => ({ role: "parent" as const, r })),
        ...f.unions.map((u) => ({ role: "spouse" as const, r: u.partner })),
        ...f.unions
          .flatMap((u) => u.children ?? [])
          .concat(f.other_children ?? [])
          .map((r) => ({ role: "child" as const, r })),
        ...f.siblings.map((r) => ({ role: "sibling" as const, r })),
      ]
    : [];

  const action = "flex flex-col items-center gap-1 rounded-lg px-2 py-2 text-xs font-medium text-ink hover:bg-parchment-deep";
  const actionIcon = "grid size-10 place-items-center rounded-full border border-stone-300 bg-white text-kumkum-700";

  return (
    <aside className="card no-print overflow-hidden" aria-labelledby="tree-panel-name">
      <div className="flex items-start gap-3 border-b border-stone-200 bg-parchment p-4">
        {cover ? (
          <PhotoThumb treeId={treeId} documentId={cover.document_id} alt="" className="size-16 shrink-0 rounded-full" />
        ) : (
          <PersonAvatar name={p.display_name} sex={p.sex_at_birth} size="lg" />
        )}
        <div className="min-w-0 flex-1">
          <h2 id="tree-panel-name" ref={heading} tabIndex={-1} className="font-display text-lg leading-snug font-semibold focus:outline-none">
            {p.display_name}
          </h2>
          {relation && <p className="text-sm font-medium text-kumkum-700">{relation}</p>}
          <p className="mt-0.5 text-sm text-ink-muted">
            {p.birth?.date || p.birth?.date_display
              ? t("treeView.panel.born", { date: p.birth.date ? formatDate(p.birth.date, t, i18n.language) : p.birth.date_display })
              : lifeLine(p, t)}
            {age !== null && ` (${t("treeView.panel.age", { count: age })})`}
            {p.birth?.place_name && ` · ${p.birth.place_name}`}
          </p>
          {(p.death?.date || p.death?.date_display) && (
            <p className="text-sm text-ink-muted">
              {t("treeView.panel.died", { date: p.death.date ? formatDate(p.death.date, t, i18n.language) : p.death.date_display })}
            </p>
          )}
        </div>
        <button type="button" onClick={onClose} className="rounded p-1 hover:bg-parchment-deep" aria-label={t("common.close")}>
          <X className="size-4" aria-hidden />
        </button>
      </div>

      <div className="space-y-4 p-4">
        <PersonBadges person={p} />
        <div className="grid grid-cols-4 gap-1">
          <Link to={`/t/${treeId}/people/${p.id}`} className={action}>
            <span className={actionIcon}>
              <IdCard className="size-4" aria-hidden />
            </span>
            {t("treeView.panel.profile")}
          </Link>
          <button type="button" className={`${action} disabled:opacity-50`} onClick={() => onCentre(p.id)} disabled={isFocus}>
            <span className={actionIcon}>
              <Users className="size-4" aria-hidden />
            </span>
            {t("treeView.panel.centre")}
          </button>
          {canEdit && (
            <div className="relative">
              <button type="button" className={`${action} w-full`} aria-expanded={menu} aria-haspopup="true" onClick={() => setMenu((v) => !v)}>
                <span className={actionIcon}>
                  <Plus className="size-4" aria-hidden />
                </span>
                {t("treeView.panel.add")}
              </button>
              {menu && (
                <ul className="absolute top-full left-1/2 z-20 mt-1 w-40 -translate-x-1/2 rounded-lg border border-stone-200 bg-white p-1 text-sm shadow-lg">
                  {(["parent", "spouse", "child", "sibling"] as const).map((k) => (
                    <li key={k}>
                      <button
                        type="button"
                        className="w-full rounded px-3 py-1.5 text-left hover:bg-parchment-deep"
                        onClick={() => {
                          setMenu(false);
                          setAdding(k);
                        }}
                      >
                        {t(`treeView.family.add.${k}`)}
                      </button>
                    </li>
                  ))}
                </ul>
              )}
            </div>
          )}
          {me && me !== p.id && (
            <Link to={`/t/${treeId}/relationship?from=${me}&to=${p.id}`} className={action}>
              <span className={actionIcon}>
                <Route className="size-4" aria-hidden />
              </span>
              {t("treeView.panel.related")}
            </Link>
          )}
        </div>

        <section aria-labelledby="tree-panel-family">
          <h3 id="tree-panel-family" className="mb-2 flex items-center gap-1.5 text-xs font-semibold tracking-wide text-ink-muted uppercase">
            <GitFork className="size-3.5" aria-hidden />
            {t("treeView.panel.immediateFamily")}
          </h3>
          {family.isLoading && <Spinner />}
          {f && relatives.length === 0 && <p className="text-sm text-ink-muted">{t("treeView.panel.noFamily")}</p>}
          <ul className="divide-y divide-stone-100">
            {relatives.map(({ role, r }, i) =>
              r.person ? (
                <li key={`${role}-${r.person.id}`}>
                  <button type="button" onClick={() => onSelect(r.person!.id)} className="flex w-full items-center gap-3 rounded-lg px-1 py-2 text-left hover:bg-parchment-deep">
                    <PersonAvatar name={r.person.display_name} sex={r.person.sex_at_birth} size="sm" />
                    <span className="min-w-0">
                      <span className="block truncate text-sm font-semibold">{r.person.display_name}</span>
                      <span className="block text-xs text-ink-muted">
                        {t(roleKey(role, r.person.sex_at_birth))} · {lifeLine(r.person, t)}
                      </span>
                    </span>
                  </button>
                </li>
              ) : (
                <li key={`${role}-hidden-${i}`} className="px-1 py-2 text-sm text-stone-600 italic">
                  {t(roleKey(role, null))} · {t("person.privatePerson")}
                </li>
              ),
            )}
          </ul>
        </section>

        {!!photos.data?.length && (
          <section aria-labelledby="tree-panel-photos">
            <h3 id="tree-panel-photos" className="mb-2 text-xs font-semibold tracking-wide text-ink-muted uppercase">
              {t("treeView.panel.photos", { count: photos.data.length })}
            </h3>
            <div className="grid grid-cols-3 gap-2">
              {photos.data.slice(0, 3).map((ph) => (
                <PhotoThumb key={ph.id} treeId={treeId} documentId={ph.document_id} alt={ph.caption ?? ""} className="aspect-square w-full rounded-lg" />
              ))}
            </div>
            <Link to={`/t/${treeId}/people/${p.id}?tab=photos`} className="mt-2 inline-block text-sm font-medium text-kumkum-700 underline">
              {t("treeView.panel.allPhotos")}
            </Link>
          </section>
        )}
      </div>

      {adding && f && (
        <AddRelativeDialog anchor={p} relation={adding} unions={f.unions} onClose={() => setAdding(null)} onAdded={(np) => onSelect(np.id)} />
      )}
    </aside>
  );
}
