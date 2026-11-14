import { useId, useMemo, useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import { useTranslation } from "react-i18next";
import { AlertTriangle, CheckCircle2, LocateFixed, Search } from "lucide-react";
import type { FamilyGraphNode } from "../../api/types";
import { useFamilyGraph, type FamilyScope } from "../../api/hooks/familyGraph";
import { useTreeCtx } from "../../lib/tree-context";
import { layoutFamily } from "../../lib/familyLayout";
import { lifespan } from "../../lib/dates";
import { dirOfText, langOfText } from "../../lib/names";
import { PrivatePersonPlaceholder } from "../person/badges";
import { Button } from "../ui/Button";
import { EmptyState, ErrorAlert, Spinner } from "../ui/feedback";
import { TreeChart } from "./TreeChart";

const MAX_MATCHES = 8;

/**
 * The complete family (ADR-0034): everyone connected to one person, or every group of the tree.
 * It loads in pages and always says which of four states it is in: loading, partly loaded,
 * stopped before the end, or complete. Only "complete" is ever described as the whole family.
 */
export function FullFamilyTree({
  rootId,
  rootName,
  scope,
  onScope,
  view,
  selectedId,
  onSelect,
}: {
  rootId: string;
  rootName: string;
  scope: FamilyScope;
  onScope: (s: FamilyScope) => void;
  view: "chart" | "list";
  selectedId: string | null;
  onSelect: (personId: string) => void;
}) {
  const { t } = useTranslation();
  const { treeId, tree } = useTreeCtx();
  const navigate = useNavigate();
  const g = useFamilyGraph(treeId, scope, scope === "connected" ? rootId : null);
  const [centre, setCentre] = useState<{ id: string; seq: number } | null>(null);
  const [query, setQuery] = useState("");
  const searchId = useId();

  const layout = useMemo(
    () => layoutFamily({ nodes: g.nodes, edges: g.edges, links: g.links, rootId: scope === "connected" ? rootId : null }),
    [g.nodes, g.edges, g.links, scope, rootId],
  );
  const named = useMemo(() => g.nodes.filter((n) => n.person), [g.nodes]);
  const privateCount = g.nodes.length - named.length;
  const groups = g.components.length;
  const generations = useMemo(() => {
    if (!g.nodes.length) return 0;
    if (scope === "all") return Math.max(0, ...layout.groups!.map((b) => Math.round((b.height - 68) / 132) + 1));
    const gens = g.nodes.map((n) => n.generation);
    return Math.max(...gens) - Math.min(...gens) + 1;
  }, [g.nodes, layout, scope]);
  const matches = useMemo(() => {
    const q = query.trim().toLocaleLowerCase();
    if (!q) return [];
    return named.filter((n) => n.person!.display_name.toLocaleLowerCase().includes(q)).slice(0, MAX_MATCHES);
  }, [named, query]);
  const go = (n: FamilyGraphNode) => {
    setCentre((c) => ({ id: n.id, seq: (c?.seq ?? 0) + 1 }));
    if (n.person) onSelect(n.person.id);
    setQuery("");
  };

  return (
    <div>
      <div className="mb-3 flex flex-col gap-3 lg:flex-row lg:items-end lg:justify-between">
        <div role="group" aria-label={t("treeView.scope.label")} className="inline-flex self-start rounded-lg border border-stone-300 bg-white p-0.5">
          {(["connected", "all"] as const).map((s) => (
            <button
              key={s}
              type="button"
              aria-pressed={scope === s}
              onClick={() => onScope(s)}
              className={`rounded-md px-3 py-1.5 text-sm ${scope === s ? "bg-parchment-deep font-semibold" : ""}`}
            >
              {t(`treeView.scope.${s}`)}
            </button>
          ))}
        </div>
        <div className="relative w-full lg:w-80">
          <label htmlFor={searchId} className="mb-1 block text-sm font-medium">
            {t("treeView.full.search")}
          </label>
          <div className="relative">
            <Search className="pointer-events-none absolute left-2.5 top-1/2 size-4 -translate-y-1/2 text-ink-muted" aria-hidden />
            <input
              id={searchId}
              type="search"
              value={query}
              onChange={(e) => setQuery(e.target.value)}
              onKeyDown={(e) => {
                if (e.key === "Enter" && matches[0]) go(matches[0]);
              }}
              placeholder={t("treeView.full.searchPlaceholder")}
              autoComplete="off"
              className="h-10 w-full rounded-lg border border-stone-300 bg-white pl-8 pr-3 text-sm"
            />
          </div>
          {query.trim() && (
            <ul aria-label={t("treeView.full.searchResults")} className="absolute z-20 mt-1 max-h-72 w-full overflow-auto rounded-lg border border-stone-300 bg-white py-1 shadow-lg">
              {matches.map((n) => (
                <li key={n.id}>
                  <button type="button" onClick={() => go(n)} className="block w-full px-3 py-2 text-left text-sm hover:bg-parchment-deep" lang={langOfText(n.person!.display_name)}>
                    {n.person!.display_name}
                    {lifespan(n.person!, t) && <span className="ml-1 text-ink-muted">({lifespan(n.person!, t)})</span>}
                  </button>
                </li>
              ))}
              {!matches.length && <li className="px-3 py-2 text-sm text-ink-muted">{t(g.complete ? "treeView.full.noMatch" : "treeView.full.noMatchYet")}</li>}
            </ul>
          )}
        </div>
      </div>

      {/* One live region for the four states, so progress and completeness are announced, not only shown. */}
      <div role="status" aria-live="polite" className="mb-2" data-testid="family-status" data-status={g.status}>
        {g.status === "loading" && <Spinner />}
        {g.status === "partial" && (
          <p className="flex items-center gap-2 rounded-lg bg-haldi-100 px-3 py-2 text-sm text-haldi-700">
            <Spinner /> {t("treeView.full.partial", { loaded: g.loadedPeople, total: g.totalPeople })}
          </p>
        )}
        {g.status === "incomplete" && (
          <div className="flex flex-wrap items-center gap-3 rounded-lg bg-haldi-100 px-3 py-2 text-sm text-haldi-700">
            <AlertTriangle className="size-4 shrink-0" aria-hidden />
            <span>{g.nodes.length ? t("treeView.full.incomplete", { loaded: g.loadedPeople, total: g.totalPeople }) : t("treeView.full.failed")}</span>
            <Button size="sm" variant="secondary" onClick={() => void g.resume()}>
              {t("treeView.full.resume")}
            </Button>
          </div>
        )}
        {g.status === "complete" && g.nodes.length > 0 && (
          <p className="flex flex-wrap items-center gap-x-2 gap-y-1 text-sm text-ink-muted">
            <CheckCircle2 className="size-4 text-green-800" aria-hidden />
            <span>
              {scope === "connected"
                ? t("treeView.full.completeConnected", { name: rootName, count: g.totalPeople })
                : t("treeView.full.completeAll", { count: g.totalPeople })}
            </span>
            <span>· {t("home.generations", { count: generations })}</span>
            {scope === "all" && <span>· {t("treeView.full.groups", { count: groups })}</span>}
            {privateCount > 0 && <span>· {t("treeView.full.privateCount", { count: privateCount })}</span>}
          </p>
        )}
      </div>
      {g.status === "incomplete" && !g.nodes.length && <ErrorAlert error={g.error} />}

      {g.status === "complete" && scope === "connected" && g.nodes.length <= 1 && (
        <EmptyState title={t("treeView.full.alone", { name: rootName })}>{t("treeView.full.aloneHint")}</EmptyState>
      )}
      {g.nodes.length > (scope === "connected" ? 1 : 0) &&
        (view === "chart" ? (
          <>
            {scope === "connected" && (
              <div className="mb-2">
                <Button size="sm" variant="ghost" icon={<LocateFixed className="size-4" aria-hidden />} onClick={() => setCentre((c) => ({ id: rootId, seq: (c?.seq ?? 0) + 1 }))}>
                  {t("treeView.full.centreOnStart", { name: rootName })}
                </Button>
              </div>
            )}
            <div aria-busy={g.status === "partial"}>
              <TreeChart
                layout={layout}
                viewKey={`${scope}:${scope === "connected" ? rootId : ""}`}
                centreOn={centre}
                onOpen={(id) => navigate(`/t/${treeId}/people/${id}`)}
                onSelect={onSelect}
                selectedId={selectedId}
                collapsed={NONE}
                onToggleCollapse={noop}
                youId={tree.my_linked_person_id}
                minOpenScale={0.75}
              />
            </div>
            <p className="mt-1 text-xs text-ink-muted">{t("treeView.full.legend")}</p>
          </>
        ) : (
          <FamilyList nodes={g.nodes} edges={g.edges} links={g.links} treeId={treeId} grouped={scope === "all" && groups > 1} />
        ))}
      {scope === "all" && g.status === "complete" && groups > 1 && <p className="mt-2 text-xs text-ink-muted">{t("treeView.scope.allHint")}</p>}
    </div>
  );
}

const NONE: ReadonlySet<string> = new Set();
function noop() {}

/** Text alternative to the chart: each group, row by row, naming every person's parents and partners. */
function FamilyList({
  nodes,
  edges,
  links,
  treeId,
  grouped,
}: {
  nodes: readonly FamilyGraphNode[];
  edges: ReturnType<typeof useFamilyGraph>["edges"];
  links: ReturnType<typeof useFamilyGraph>["links"];
  treeId: string;
  grouped: boolean;
}) {
  const { t } = useTranslation();
  const byId = useMemo(() => new Map(nodes.map((n) => [n.id, n])), [nodes]);
  const parents = useMemo(() => {
    const m = new Map<string, string[]>();
    for (const e of edges) m.set(e.target, [...(m.get(e.target) ?? []), e.source]);
    return m;
  }, [edges]);
  const partners = useMemo(() => {
    const m = new Map<string, string[]>();
    for (const l of links) {
      if (l.kind !== "union") continue;
      m.set(l.a, [...(m.get(l.a) ?? []), l.b]);
      m.set(l.b, [...(m.get(l.b) ?? []), l.a]);
    }
    return m;
  }, [links]);
  const sections = useMemo(() => {
    const m = new Map<number, Map<number, FamilyGraphNode[]>>();
    for (const n of nodes) {
      const rows = m.get(n.component) ?? new Map<number, FamilyGraphNode[]>();
      rows.set(n.generation, [...(rows.get(n.generation) ?? []), n]);
      m.set(n.component, rows);
    }
    return [...m.entries()].sort((a, b) => a[0] - b[0]).map(([c, rows]) => ({ c, rows: [...rows.entries()].sort((a, b) => a[0] - b[0]) }));
  }, [nodes]);
  const name = (id: string) => byId.get(id)?.person?.display_name ?? t("person.privatePerson");

  return (
    <div className="space-y-4">
      {sections.map(({ c, rows }) => (
        <section key={c} className="card p-4" aria-label={grouped ? t("treeView.groupLabel", { n: c + 1, count: rows.reduce((s, [, r]) => s + r.filter((n) => n.person).length, 0) }) : undefined}>
          {grouped && (
            <h2 className="font-display text-lg font-semibold">
              {t("treeView.groupLabel", { n: c + 1, count: rows.reduce((s, [, r]) => s + r.filter((n) => n.person).length, 0) })}
            </h2>
          )}
          {rows.map(([gen, people], i) => (
            <div key={gen} className="mt-3 first:mt-0">
              {grouped ? (
                <h3 className="font-display font-semibold">{t("treeView.full.generationN", { n: i + 1 })}</h3>
              ) : (
                <h2 className="font-display font-semibold">{t("treeView.full.generationN", { n: i + 1 })}</h2>
              )}
              <ul className="mt-1 space-y-2">
                {people.map((n) => (
                  <li key={n.id} className="text-sm">
                    {n.person ? (
                      <Link to={`/t/${treeId}/people/${n.person.id}`} lang={langOfText(n.person.display_name)} dir={dirOfText(n.person.display_name)} className="font-medium text-kumkum-800 underline-offset-2 hover:underline">
                        {n.person.display_name}
                      </Link>
                    ) : (
                      <PrivatePersonPlaceholder />
                    )}
                    {n.person && lifespan(n.person, t) && <span className="ml-1 text-ink-muted">({lifespan(n.person, t)})</span>}
                    {n.person && n.person.profile_status !== "unknown" && <span className="ml-1 text-xs text-ink-muted">· {t(`enum.profileStatus.${n.person.profile_status}`)}</span>}
                    {(parents.get(n.id)?.length ?? 0) > 0 && (
                      <p className="text-xs text-ink-muted">
                        {t("treeView.parentsAre")} {parents.get(n.id)!.map(name).join(", ")}
                      </p>
                    )}
                    {(partners.get(n.id)?.length ?? 0) > 0 && (
                      <p className="text-xs text-ink-muted">
                        {t("treeView.full.partnersAre")} {partners.get(n.id)!.map(name).join(", ")}
                      </p>
                    )}
                  </li>
                ))}
              </ul>
            </div>
          ))}
        </section>
      ))}
    </div>
  );
}
