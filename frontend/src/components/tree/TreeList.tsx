import { useMemo } from "react";
import { Link } from "react-router-dom";
import { useTranslation } from "react-i18next";
import type { GraphOut, GraphNode } from "../../api/types";
import { PrivatePersonPlaceholder } from "../person/badges";

/**
 * Text alternative to the chart (PRS §50): generations as headed lists, each person linking to
 * their profile and naming the relatives that connect them to the next generation.
 */
export function TreeList({ graph, personHref }: { graph: GraphOut; personHref: (id: string) => string }) {
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
          <h3 id={`gen-${g}`} className="font-display font-semibold">
            {g === 0 ? t("treeView.genRoot") : t(graph.direction === "ancestors" ? "treeView.genUp" : "treeView.genDown", { count: Math.abs(g) })}
          </h3>
          <ul className="mt-2 space-y-2">
            {nodes.map((n) => {
              const links = linksFor(n.id);
              return (
                <li key={n.id} className="text-sm">
                  {n.person ? (
                    <Link to={personHref(n.person.id)} className="font-medium text-kumkum-800 underline-offset-2 hover:underline">
                      {n.person.display_name}
                    </Link>
                  ) : (
                    <PrivatePersonPlaceholder />
                  )}
                  {n.person && (n.person.birth_year || n.person.death_year) && (
                    <span className="ml-1 text-ink-muted">
                      ({n.person.birth_year ?? "?"}–{n.person.death_year ?? ""})
                    </span>
                  )}
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
