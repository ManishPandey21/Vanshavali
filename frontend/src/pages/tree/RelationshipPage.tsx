import { useState } from "react";
import { Link, useSearchParams } from "react-router-dom";
import { useTranslation } from "react-i18next";
import { ArrowLeftRight, ChevronRight } from "lucide-react";
import type { Lineage, PersonSummary } from "../../api/types";
import { usePerson, useRelationshipPath } from "../../api/hooks/people";
import { useTreeCtx } from "../../lib/tree-context";
import { describeChain, regionalKinshipTerm } from "../../lib/kinship";
import { PersonPicker } from "../../components/pickers";
import { ErrorAlert, PageHeader, Spinner } from "../../components/ui/feedback";
import { Button } from "../../components/ui/Button";
import { LineageToggle } from "./person/FamilyTab";

export function RelationshipPage() {
  const { t, i18n } = useTranslation();
  const { treeId, tree } = useTreeCtx();
  const [params, setParams] = useSearchParams();
  const fromId = params.get("from") ?? tree.my_linked_person_id ?? "";
  const toId = params.get("to") ?? "";
  const from = usePerson(treeId, fromId || undefined);
  const to = usePerson(treeId, toId || undefined);
  const [lineage, setLineage] = useState<Lineage[]>([]);
  const path = useRelationshipPath(treeId, fromId, toId, lineage);

  const setPerson = (k: "from" | "to", p: PersonSummary | null) => {
    const next = new URLSearchParams(params);
    if (p) next.set(k, p.id);
    else next.delete(k);
    setParams(next, { replace: true });
  };
  const swap = () => {
    const next = new URLSearchParams(params);
    next.set("from", toId);
    next.set("to", fromId);
    setParams(next, { replace: true });
  };

  const r = path.data;
  const regional = r?.found ? regionalKinshipTerm(r.chain ?? [], i18n.language) : null;
  const chainText = r?.found ? describeChain(r.chain ?? [], i18n.language) : "";
  // The API label is English-only; in Hindi, lead with the regional term or the literal chain.
  const isHindi = i18n.language.startsWith("hi");
  const pathPeople = r?.path ?? [];

  return (
    <div className="mx-auto max-w-3xl">
      <PageHeader title={t("relationship.title")} subtitle={t("relationship.subtitle")} />
      <div className="card grid grid-cols-1 items-end gap-3 p-4 sm:grid-cols-[1fr_auto_1fr]">
        <PersonPicker treeId={treeId} label={t("relationship.from")} value={from.data ?? null} onChange={(p) => setPerson("from", p)} />
        <Button variant="ghost" onClick={swap} disabled={!fromId || !toId} aria-label={t("relationship.swap")} icon={<ArrowLeftRight className="size-4" aria-hidden />} />
        <PersonPicker treeId={treeId} label={t("relationship.to")} value={to.data ?? null} onChange={(p) => setPerson("to", p)} excludeIds={fromId ? [fromId] : []} />
      </div>
      <div className="mt-3">
        <LineageToggle value={lineage} onChange={setLineage} />
      </div>
      {path.isFetching && <Spinner />}
      <ErrorAlert error={path.error} />
      {r && from.data && to.data && (
        <section className="card mt-4 p-5" aria-live="polite" aria-labelledby="rel-result">
          {r.found ? (
            <>
              <p className="text-sm text-ink-muted">{t("relationship.resultLead", { a: to.data.display_name, b: from.data.display_name })}</p>
              <h2 id="rel-result" className="mt-1 font-display text-3xl font-bold text-kumkum-900">
                {regional || (isHindi && chainText) ? (
                  <>
                    <span lang="hi">{regional || chainText}</span>
                    <span className="ml-2 text-lg font-normal text-ink-muted" lang="en">
                      ({r.label})
                    </span>
                  </>
                ) : (
                  r.label
                )}
              </h2>
              {chainText && (
                <p className="mt-2 text-sm">
                  <span className="font-medium">{t("relationship.chain")}:</span> {chainText}
                </p>
              )}
              {r.explanation && <p className="mt-1 text-xs text-ink-muted">{r.explanation}</p>}
              {regional?.includes("/") && <p className="mt-1 text-xs text-ink-muted">{t("relationship.ageDependent")}</p>}
              {pathPeople.length > 1 && (
                <ol className="mt-4 flex flex-wrap items-center gap-1 text-sm" aria-label={t("relationship.path")}>
                  {pathPeople.map((id, i) => (
                    <li key={`${id ?? "hidden"}-${i}`} className="flex items-center gap-1">
                      <PathPerson id={id} />
                      {i < pathPeople.length - 1 && (
                        <span className="flex items-center gap-1 text-xs text-ink-muted">
                          <ChevronRight className="size-3.5" aria-hidden />
                          {r.chain && r.chain.length === pathPeople.length - 1 ? t(`kin.${r.chain[i]}`, { defaultValue: r.chain[i] }) : null}
                        </span>
                      )}
                    </li>
                  ))}
                </ol>
              )}
            </>
          ) : (
            <p id="rel-result">{t("relationship.notFound")}</p>
          )}
        </section>
      )}
    </div>
  );
}

/** A person on the path; `null` = someone the viewer may not see (the API withholds the id). */
function PathPerson({ id }: { id: string | null }) {
  const { t } = useTranslation();
  const { treeId } = useTreeCtx();
  const p = usePerson(treeId, id ?? undefined);
  if (!id || p.error) return <span className="italic text-ink-muted">{t("person.privatePerson")}</span>;
  return (
    <Link to={`/t/${treeId}/people/${id}`} className="rounded-full bg-parchment-deep px-2 py-0.5 text-kumkum-800 hover:underline">
      {p.data?.display_name ?? "…"}
    </Link>
  );
}
