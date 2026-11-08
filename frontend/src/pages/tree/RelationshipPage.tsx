import { useState } from "react";
import { Link, useSearchParams } from "react-router-dom";
import { useTranslation } from "react-i18next";
import { ArrowLeftRight, ChevronRight } from "lucide-react";
import type { KinshipTermOut, Lineage, PersonSummary } from "../../api/types";
import { usePerson, useRecordAgeOrder, useRelationshipPath } from "../../api/hooks/people";
import { useTreeCtx } from "../../lib/tree-context";
import { describeChain, type AgeOrder } from "../../lib/kinship";
import { Perm } from "../../lib/permissions";
import { PersonPicker } from "../../components/pickers";
import { ErrorAlert, LiveRegion, PageHeader, Spinner } from "../../components/ui/feedback";
import { Button } from "../../components/ui/Button";
import { Badge } from "../../components/ui/Badge";
import { LineageToggle } from "./person/FamilyTab";

export function RelationshipPage() {
  const { t, i18n } = useTranslation();
  const { treeId, tree, can } = useTreeCtx();
  const [params, setParams] = useSearchParams();
  const fromId = params.get("from") ?? tree.my_linked_person_id ?? "";
  const toId = params.get("to") ?? "";
  const from = usePerson(treeId, fromId || undefined);
  const to = usePerson(treeId, toId || undefined);
  const [lineage, setLineage] = useState<Lineage[]>([]);
  const path = useRelationshipPath(treeId, fromId, toId, lineage, i18n.language.startsWith("hi") ? "hi" : "en");

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
  const ageOrders = (r?.age_orders ?? []) as AgeOrder[];
  // the reader's relationship word, chosen by the server from reviewed regional packs and the
  // family's own words (ADR-0026 §6); none means the English label and the literal reading
  const term = r?.found ? (r.terms?.[0] ?? null) : null;
  const regional = term?.term ?? null;
  const chainText = r?.found ? describeChain(r.chain ?? [], i18n.language, ageOrders) : "";
  // the age that decides Tau vs Chacha, in any language: asked once while it is unknown
  const decision = r?.found ? (r.age_decision ?? null) : null;
  const question = decision && decision.order === "unknown" ? { personId: decision.person_id, relativeToId: decision.relative_to_id } : null;
  const basis = decision && decision.order !== "unknown" ? decision.basis : null;
  // The API label is English-only; in Hindi, lead with the regional term or the literal chain.
  const isHindi = i18n.language.startsWith("hi");
  const pathPeople = r?.path ?? [];
  // A concise, always-mounted live region: a region inserted together with its content is often
  // not announced (WCAG 4.1.3 Status Messages).
  const announcement =
    r && from.data && to.data && !path.isFetching
      ? r.found
        ? `${t("relationship.resultLead", { a: to.data.display_name, b: from.data.display_name })} ${regional || (isHindi && chainText) || r.label}`
        : t("relationship.notFound")
      : "";

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
      <LiveRegion message={announcement} />
      {path.isFetching && <Spinner />}
      <ErrorAlert error={path.error} />
      {r && from.data && to.data && (
        <section className="card mt-4 p-5" aria-labelledby="rel-result">
          {r.found ? (
            <>
              <p className="text-sm text-ink-muted">{t("relationship.resultLead", { a: to.data.display_name, b: from.data.display_name })}</p>
              <h2 id="rel-result" className="mt-1 font-display text-3xl font-bold text-kumkum-900">
                {regional || (isHindi && chainText) ? (
                  <>
                    <span lang={term?.lang ?? "hi"}>{regional || chainText}</span>
                    <span className="ml-2 text-lg font-normal text-ink-muted" lang="en">
                      ({r.label})
                    </span>
                  </>
                ) : (
                  r.label
                )}
              </h2>
              {term && <TermNotes term={term} />}
              {chainText && (
                <p className="mt-2 text-sm">
                  <span className="font-medium">{t("relationship.chain")}:</span> {chainText}
                </p>
              )}
              {r.explanation && <p className="mt-1 text-xs text-ink-muted">{r.explanation}</p>}
              {basis === "family_confirmed" && <p className="mt-1 text-xs text-ink-muted">{t("relationship.basis.family_confirmed")}</p>}
              {basis === "birth_dates" && <p className="mt-1 text-xs text-ink-muted">{t("relationship.basis.birth_dates")}</p>}
              {decision?.dates_disagree && <p className="mt-1 text-xs text-ink-muted">{t("relationship.datesDisagree")}</p>}
              {question && (
                <AgeQuestion personId={question.personId} relativeToId={question.relativeToId} canAnswer={can(Perm.RELATIONSHIP_WRITE)} />
              )}
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

/** Where the word came from: the family's own word, a pack word not yet reviewed, a transliteration. */
function TermNotes({ term }: { term: KinshipTermOut }) {
  const { t } = useTranslation();
  return (
    <div className="mt-2 flex flex-wrap items-center gap-1.5 text-xs">
      {term.transliteration && (
        <span className="text-ink-muted" lang="en">
          {term.transliteration}
        </span>
      )}
      {term.family_word && <Badge tone="green">{t("kinship.familyWord")}</Badge>}
      {term.family_word && term.pack_term && (
        <span className="text-ink-muted">
          {t("kinship.packWord")}: <span lang={term.lang}>{term.pack_term}</span>
        </span>
      )}
      {term.review_status === "unreviewed" && <Badge tone="saffron">{t("kinship.unreviewed")}</Badge>}
    </div>
  );
}

/**
 * "Is Suresh older or younger than Ramesh?" — the answer is recorded as family knowledge and decides
 * age-dependent terms (Tau vs Chacha) from then on, over any birth dates (ADR-0020 §5).
 */
function AgeQuestion({ personId, relativeToId, canAnswer }: { personId: string; relativeToId: string; canAnswer: boolean }) {
  const { t } = useTranslation();
  const { treeId } = useTreeCtx();
  const person = usePerson(treeId, personId);
  const other = usePerson(treeId, relativeToId);
  const record = useRecordAgeOrder(treeId);
  if (!person.data || !other.data) return null;
  const names = { person: person.data.display_name, other: other.data.display_name };
  if (!canAnswer) return <p className="mt-1 text-xs text-ink-muted">{t("relationship.ageDependent")}</p>;
  return (
    <div className="mt-3 rounded-lg border border-haldi-300 bg-haldi-100 p-3" role="group" aria-labelledby="age-q">
      <p id="age-q" className="text-sm font-medium">
        {t("relationship.ageQuestion", names)}
      </p>
      <p className="text-xs text-ink-muted">{t("relationship.ageQuestionHint")}</p>
      <div className="mt-2 flex flex-wrap gap-2">
        {(["elder", "younger"] as const).map((order) => (
          <Button
            key={order}
            size="sm"
            variant="secondary"
            loading={record.isPending && record.variables?.order === order}
            onClick={() => record.mutate({ person_id: personId, relative_to_id: relativeToId, order })}
          >
            {t(`relationship.age.${order}`, names)}
          </Button>
        ))}
      </div>
      <ErrorAlert error={record.error} />
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
