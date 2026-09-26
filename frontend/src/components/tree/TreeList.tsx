import { useMemo } from "react";
import { Link } from "react-router-dom";
import { useTranslation } from "react-i18next";
import type { GraphOut, GraphNode } from "../../api/types";
import { PrivatePersonPlaceholder } from "../person/badges";
import { lifespan } from "../../lib/dates";
import { dirOfText, langOfText } from "../../lib/names";

/**
 * Text alternative to the chart (PRS §50): generations as headed lists, each person linking to
 * their profile and naming the relatives that connect them to the next generation. Each entry states
 * living/deceased in words (the chart's side bar is not the only cue).
 * `headingLevel` keeps the outline unbroken: 2 directly under a page's h1, 3 inside an h2 section.
 */
export function TreeList({ graph, personHref, headingLevel = 2 }: { graph: GraphOut; personHref: (id: string) => string; headingLevel?: 2 | 3 }) {
  const Heading = headingLevel === 2 ? "h2" : "h3";
  const { t } = useTranslation();
  const byId = useMemo(() => new Map(graph.nodes.map((n) => [n.id, n])), [graph]);
  const gens = useMemo(() => {
    const m = new Map<number, GraphNode[]>();
    for (const n of graph.nodes) m.set(n.generation, [...(m.get(n.generation) ?? []), n]);
    return [...m.entries()].sort((a, b) => Math.abs(a[0]) - Math.abs(b[0]));
  }, [graph]);
  const linksFor = (id: string) => {
    const ancestors = graph.direction === "ancestors";
    const rel = graph.edges.filter((e) => (ancestors ? e.target === id : e.source === id)).map((e) => ({ id: ancestors ? e.source : e.target, type: e.type }));
    return rel.map((r) => ({ node: byId.get(r.id), type: r.type })).filter((r) => r.node);
  };
  const name = (n: GraphNode | undefined) => (n?.person ? n.person.display_name : t("person.privatePerson"));

  return (
    <div className="space-y-4">
      {gens.map(([g, nodes]) => (
        <section key={g} aria-labelledby={`gen-${g}`} className="card p-4">
          <Heading id={`gen-${g}`} className="font-display font-semibold">
            {g === 0 ? t("treeView.genRoot") : t(graph.direction === "ancestors" ? "treeView.genUp" : "treeView.genDown", { count: Math.abs(g) })}
          </Heading>
          <ul className="mt-2 space-y-2">
            {nodes.map((n) => {
              const links = linksFor(n.id);
              return (
                <li key={n.id} className="text-sm">
                  {n.person ? (
                    <Link
                      to={personHref(n.person.id)}
                      lang={langOfText(n.person.display_name)}
                      dir={dirOfText(n.person.display_name)}
                      className="font-medium text-kumkum-800 underline-offset-2 hover:underline"
                    >
                      {n.person.display_name}
                    </Link>
                  ) : (
                    <PrivatePersonPlaceholder />
                  )}
                  {n.person && lifespan(n.person, t) && <span className="ml-1 text-ink-muted">({lifespan(n.person, t)})</span>}
                  {n.person && n.person.profile_status !== "unknown" && (
                    <span className="ml-1 text-xs text-ink-muted">· {t(`enum.profileStatus.${n.person.profile_status}`)}</span>
                  )}
                  {n.partner && <span className="ml-1 text-xs text-ink-muted">· {t("treeView.partnerNode")}</span>}
                  {links.length > 0 && (
                    <p className="text-xs text-ink-muted">
                      {graph.direction === "ancestors" ? t("treeView.parentsAre") : t("treeView.childrenAre")}{" "}
                      {links.map((l) => `${name(l.node)} (${t(`enum.relType.${l.type}`)})`).join(", ")}
                    </p>
                  )}
                </li>
              );
            })}
          </ul>
        </section>
      ))}
    </div>
  );
}
