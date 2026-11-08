import { useEffect, useRef, useState } from "react";
import { useTranslation } from "react-i18next";
import type { FamilyOut, Lineage, PersonSummary, RelatedPerson, SexAtBirth } from "../../api/types";
import { useFamily } from "../../api/hooks/people";
import { useTreeCtx } from "../../lib/tree-context";
import { hasPerm, Perm } from "../../lib/permissions";
import { AddRelativeDialog, type RelationKind } from "../../pages/tree/person/AddRelativeDialog";
import { ErrorAlert, Spinner } from "../ui/feedback";
import { AddSlot, FamilyCard, HiddenCard } from "./FamilyCards";

type Adding = { relation: RelationKind; sex?: SexAtBirth };

const byBirth = (a: PersonSummary, b: PersonSummary) => (a.birth_year ?? 9999) - (b.birth_year ?? 9999);

/** Everyone the family view shows, for the "N people" count. */
export function familyCount(f: FamilyOut): number {
  const kids = f.unions.flatMap((u) => u.children ?? []).concat(f.other_children ?? []);
  return 1 + f.parents.length + f.siblings.length + f.unions.length + kids.length;
}

/**
 * One person's immediate family, the way families describe it: parents above, the person among
 * their brothers and sisters (eldest first) with their spouse beside them, and their children below.
 * Empty places become "+ Add father / mother / spouse / child / sibling" slots for editors.
 * Every card selects that person for the side panel.
 */
export function FamilyView({
  focusId,
  lineage,
  selectedId,
  onSelect,
}: {
  focusId: string;
  lineage: Lineage[];
  selectedId: string | null;
  onSelect: (id: string) => void;
}) {
  const { t } = useTranslation();
  const { treeId, tree } = useTreeCtx();
  const family = useFamily(treeId, focusId, lineage);
  const [adding, setAdding] = useState<Adding | null>(null);
  const scroller = useRef<HTMLElement>(null);
  // Wide families scroll sideways: centre the whole family, or the person if that would hide them.
  useEffect(() => {
    const el = scroller.current;
    const card = el?.querySelector<HTMLElement>("[data-focus]");
    if (!el || !card) return;
    el.scrollLeft = (el.scrollWidth - el.clientWidth) / 2;
    const box = el.getBoundingClientRect();
    const c = card.getBoundingClientRect();
    if (c.left < box.left || c.right > box.right) el.scrollLeft += c.left - box.left + c.width / 2 - el.clientWidth / 2;
  }, [family.data, focusId]);
  const canEdit = hasPerm(tree, Perm.PERSON_WRITE) && hasPerm(tree, Perm.RELATIONSHIP_WRITE);

  if (family.isLoading) return <Spinner />;
  if (family.error || !family.data) return <ErrorAlert error={family.error} />;
  const f = family.data;
  const me = f.person;

  const card = (r: Pick<RelatedPerson, "person" | "relationship_type">, key: string) =>
    r.person ? (
      <FamilyCard key={key} person={r.person} relType={r.relationship_type} selected={selectedId === r.person.id} onSelect={onSelect} />
    ) : (
      <HiddenCard key={key} />
    );

  // Parents: known ones, then a slot for each missing father / mother.
  const parents = f.parents;
  const hasFather = parents.some((p) => p.person?.sex_at_birth === "male");
  const hasMother = parents.some((p) => p.person?.sex_at_birth === "female");
  const parentSlots: Adding[] = [];
  if (canEdit && parents.length < 2) {
    if (!hasFather) parentSlots.push({ relation: "parent", sex: "male" });
    if (!hasMother) parentSlots.push({ relation: "parent", sex: "female" });
    parentSlots.splice(2 - parents.length);
  }

  // The person's own row: siblings in birth order with the person in their place.
  const siblings = f.siblings.filter((s) => s.person);
  const hiddenSiblings = f.siblings.length - siblings.length;
  const row = [...siblings.map((s) => s.person!), me].sort(byBirth);
  const children = f.unions.flatMap((u) => u.children ?? []).concat(f.other_children ?? []);
  const kids = [...children.filter((c) => c.person).sort((a, b) => byBirth(a.person!, b.person!)), ...children.filter((c) => !c.person)];
  const hasParentsRow = parents.length > 0 || parentSlots.length > 0;

  const meBlock = (
    <div className="grid grid-cols-[1fr_auto_1fr] items-center">
      <span aria-hidden />
      <FamilyCard person={me} focus selected={selectedId === me.id} onSelect={onSelect} />
      <div className="flex items-center">
        {f.unions.map((u, i) => (
          <div key={u.relationship?.id ?? i} className="flex items-center">
            <Marriage divorced={u.relationship?.type === "divorced_spouse" || u.relationship?.type === "separated_spouse"} />
            {card(u.partner, `spouse-${i}`)}
          </div>
        ))}
        {canEdit && f.unions.length === 0 && (
          <div className="flex items-center">
            <span aria-hidden className="w-6 border-t-2 border-dashed border-stone-300" />
            <AddSlot compact label={t("treeView.family.addSpouse")} onClick={() => setAdding({ relation: "spouse" })} />
          </div>
        )}
      </div>
    </div>
  );

  const childrenRow =
    kids.length > 0 || canEdit ? (
      <ul>
        {kids.map((c, i) => (
          <li key={c.person?.id ?? `hidden-child-${i}`}>{card(c, `child-${i}`)}</li>
        ))}
        {canEdit && (
          <li>
            <AddSlot compact label={t("treeView.family.addChild")} onClick={() => setAdding({ relation: "child" })} />
          </li>
        )}
      </ul>
    ) : null;

  const siblingRow = (
    <ul>
      {row.map((p) =>
        p.id === me.id ? (
          <li key={p.id}>
            {meBlock}
            {childrenRow}
          </li>
        ) : (
          <li key={p.id}>
            <FamilyCard person={p} selected={selectedId === p.id} onSelect={onSelect} />
          </li>
        ),
      )}
      {Array.from({ length: hiddenSiblings }, (_, i) => (
        <li key={`hidden-sib-${i}`}>
          <HiddenCard />
        </li>
      ))}
      {canEdit && (
        <li>
          <AddSlot compact label={t("treeView.family.addSibling")} onClick={() => setAdding({ relation: "sibling" })} />
        </li>
      )}
    </ul>
  );

  return (
    <section ref={scroller} aria-label={t("treeView.family.label", { name: me.display_name })} className="overflow-x-auto rounded-xl border border-stone-200 bg-[radial-gradient(circle,_#efe3cc_1px,_transparent_1px)] [background-size:18px_18px] px-4 py-8">
      <div className="family-tree mx-auto w-max min-w-full">
        {hasParentsRow ? (
          <ul>
            <li>
              <div className="flex items-center justify-center">
                {parents.map((p, i) => (
                  <div key={p.relationship_id ?? `parent-${i}`} className="flex items-center">
                    {i > 0 && <Marriage />}
                    {card(p, `parent-${i}`)}
                  </div>
                ))}
                {parentSlots.map((s, i) => (
                  <div key={`slot-${s.sex}`} className="flex items-center">
                    {(parents.length > 0 || i > 0) && <span aria-hidden className="w-6 border-t-2 border-dashed border-stone-300" />}
                    <AddSlot label={t(s.sex === "male" ? "treeView.family.addFather" : "treeView.family.addMother")} onClick={() => setAdding(s)} />
                  </div>
                ))}
              </div>
              {siblingRow}
            </li>
          </ul>
        ) : (
          siblingRow
        )}
      </div>
      {adding && (
        <AddRelativeDialog
          anchor={me}
          relation={adding.relation}
          unions={f.unions}
          initialSex={adding.sex}
          onClose={() => setAdding(null)}
          onAdded={(p) => onSelect(p.id)}
        />
      )}
    </section>
  );
}

/** The double "married" line between two partners (dashed when divorced or separated). */
function Marriage({ divorced }: { divorced?: boolean }) {
  return (
    <span aria-hidden className="flex w-6 flex-col gap-[3px]">
      <span className={`border-t-2 border-kumkum-600 ${divorced ? "border-dashed" : ""}`} />
      <span className={`border-t-2 border-kumkum-600 ${divorced ? "border-dashed" : ""}`} />
    </span>
  );
}
