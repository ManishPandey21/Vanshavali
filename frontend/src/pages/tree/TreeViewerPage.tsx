import { useState } from "react";
import { useLocation, useNavigate, useParams, useSearchParams } from "react-router-dom";
import { useTranslation } from "react-i18next";
import { AlertTriangle, ChevronsDown, ChevronsUp, List, Network, Users } from "lucide-react";
import type { Lineage, PersonSummary } from "../../api/types";
import { useGraph, usePerson } from "../../api/hooks/people";
import { useTreeCtx } from "../../lib/tree-context";
import { recentPeople } from "../../lib/recent";
import { useFamilyApex } from "../../lib/apex";
import { PersonPicker } from "../../components/pickers";
import { TreeChart } from "../../components/tree/TreeChart";
import { FamilyView } from "../../components/tree/FamilyView";
import { TreePersonPanel } from "../../components/tree/TreePersonPanel";
import { TreeList } from "../../components/tree/TreeList";
import { Button } from "../../components/ui/Button";
import { EmptyState, ErrorAlert, PageHeader, Spinner } from "../../components/ui/feedback";
import { LineageToggle } from "./person/FamilyTab";

const MAX_DEPTH = 25;

export function TreeViewerPage() {
  const { personId } = useParams();
  const { t } = useTranslation();
  const { treeId, tree } = useTreeCtx();
  const navigate = useNavigate();
  const remembered = personId ?? tree.my_linked_person_id ?? recentPeople(treeId)[0] ?? "";
  // With nobody to start from, open on the family elder rather than an empty search box.
  const apex = useFamilyApex(treeId, tree.my_linked_person_id);
  const fallbackRoot = remembered || apex.apexId || "";
  const root = usePerson(treeId, fallbackRoot || undefined);

  if (!remembered && apex.isLoading) return <Spinner />;
  if (!fallbackRoot) {
    return (
      <div>
        <PageHeader title={t("treeView.title")} subtitle={t("treeView.pickRoot")} />
        <div className="card max-w-md p-4">
          <PersonPicker treeId={treeId} label={t("treeView.startFrom")} value={null} onChange={(p: PersonSummary | null) => p && navigate(`/t/${treeId}/tree/${p.id}`)} />
        </div>
      </div>
    );
  }
  if (root.isLoading) return <Spinner />;
  if (root.error || !root.data) return <ErrorAlert error={root.error} />;
  return (
    <TreeViewer
      key={root.data.id}
      rootId={root.data.id}
      rootName={root.data.display_name}
      defaultDirection={remembered ? "ancestors" : "descendants"}
    />
  );
}

function TreeViewer({
  rootId,
  rootName,
  defaultDirection,
}: {
  rootId: string;
  rootName: string;
  defaultDirection: "ancestors" | "descendants";
}) {
  const { t } = useTranslation();
  const { treeId } = useTreeCtx();
  const navigate = useNavigate();
  const [params, setParams] = useSearchParams();
  const dirParam = params.get("dir");
  const direction = dirParam === "descendants" || dirParam === "ancestors" ? dirParam : defaultDirection;
  const viewParam = params.get("view");
  const view = viewParam === "list" ? "list" : viewParam === "family" ? "family" : "chart";
  const location = useLocation();
  // "Centre here" re-mounts the viewer on the new person; the selection travels in history state.
  const [selected, setSelected] = useState<string | null>(() => (location.state as { select?: string } | null)?.select ?? null);
  const [depth, setDepth] = useState(3);
  const [lineage, setLineage] = useState<Lineage[]>([]);
  const [collapsed, setCollapsed] = useState<Set<string>>(new Set());
  const graph = useGraph(treeId, rootId, direction, depth, lineage);
  const centre = (id: string) => {
    navigate(`/t/${treeId}/tree/${id}?${params.toString()}`, { state: { select: id } });
  };

  const setParam = (k: string, v: string) => {
    const next = new URLSearchParams(params);
    next.set(k, v);
    setParams(next, { replace: true });
  };
  const toggleCollapse = (id: string) =>
    setCollapsed((prev) => {
      const n = new Set(prev);
      if (n.has(id)) n.delete(id);
      else n.add(id);
      return n;
    });
  const maxGen = graph.data ? Math.max(0, ...graph.data.nodes.map((n) => Math.abs(n.generation))) : 0;
  const mayHaveMore = !!graph.data && maxGen >= depth && depth < MAX_DEPTH;

  return (
    <div>
      <PageHeader
        title={t("treeView.titleFor", { name: rootName })}
        subtitle={t("treeView.subtitle")}
        actions={
          <div className="w-64">
            <PersonPicker treeId={treeId} label={t("treeView.changeRoot")} value={null} onChange={(p) => p && navigate(`/t/${treeId}/tree/${p.id}?${params.toString()}`)} />
          </div>
        }
      />
      <div className="mb-3 flex flex-col gap-3 lg:flex-row lg:items-center lg:justify-between">
        <div className="flex flex-wrap items-center gap-2">
          {view !== "family" && (
            <div role="group" aria-label={t("treeView.direction")} className="inline-flex rounded-lg border border-stone-300 bg-white p-0.5">
              {(["ancestors", "descendants"] as const).map((d) => (
                <button
                  key={d}
                  type="button"
                  aria-pressed={direction === d}
                  onClick={() => {
                    setCollapsed(new Set());
                    setParam("dir", d);
                  }}
                  className={`inline-flex items-center gap-1 rounded-md px-3 py-1.5 text-sm ${direction === d ? "bg-kumkum-700 text-white" : ""}`}
                >
                  {d === "ancestors" ? <ChevronsUp className="size-4" aria-hidden /> : <ChevronsDown className="size-4" aria-hidden />}
                  {t(`treeView.${d}`)}
                </button>
              ))}
            </div>
          )}
          <div role="group" aria-label={t("treeView.viewMode")} className="inline-flex rounded-lg border border-stone-300 bg-white p-0.5">
            <button type="button" aria-pressed={view === "family"} onClick={() => setParam("view", "family")} className={`inline-flex items-center gap-1 rounded-md px-3 py-1.5 text-sm ${view === "family" ? "bg-parchment-deep font-semibold" : ""}`}>
              <Users className="size-4" aria-hidden /> {t("treeView.family.tab")}
            </button>
            <button type="button" aria-pressed={view === "chart"} onClick={() => setParam("view", "chart")} className={`inline-flex items-center gap-1 rounded-md px-3 py-1.5 text-sm ${view === "chart" ? "bg-parchment-deep font-semibold" : ""}`}>
              <Network className="size-4" aria-hidden /> {t("treeView.chart")}
            </button>
            <button type="button" aria-pressed={view === "list"} onClick={() => setParam("view", "list")} className={`inline-flex items-center gap-1 rounded-md px-3 py-1.5 text-sm ${view === "list" ? "bg-parchment-deep font-semibold" : ""}`}>
              <List className="size-4" aria-hidden /> {t("treeView.list")}
            </button>
          </div>
        </div>
        <LineageToggle value={lineage} onChange={setLineage} />
      </div>

      <div className={selected ? "grid items-start gap-4 lg:grid-cols-[minmax(0,1fr)_20rem]" : ""}>
        <div className="min-w-0">
          {view === "family" ? (
            <FamilyView focusId={rootId} lineage={lineage} selectedId={selected} onSelect={setSelected} />
          ) : (
            <>
              {graph.isLoading && <Spinner />}
              <ErrorAlert error={graph.error} />
              {graph.data && graph.data.truncated && (
                <p role="status" className="mb-2 flex items-center gap-2 rounded-lg bg-haldi-100 px-3 py-2 text-sm text-haldi-700">
                  <AlertTriangle className="size-4" aria-hidden /> {t("treeView.truncated")}
                </p>
              )}
              {graph.data && graph.data.nodes.length <= 1 && (
                <EmptyState title={t(`treeView.none.${direction}`)}>{t("treeView.noneHint")}</EmptyState>
              )}
              {graph.data && graph.data.nodes.length > 1 && (
                <div aria-busy={graph.isFetching}>
                  {view === "chart" ? (
                    <TreeChart
                      graph={graph.data}
                      onOpen={(id) => navigate(`/t/${treeId}/people/${id}`)}
                      onSelect={setSelected}
                      selectedId={selected}
                      collapsed={collapsed}
                      onToggleCollapse={toggleCollapse}
                    />
                  ) : (
                    <TreeList graph={graph.data} personHref={(id) => `/t/${treeId}/people/${id}`} />
                  )}
                </div>
              )}
            </>
          )}
        </div>
        {selected && (
          <div className="lg:sticky lg:top-4">
            <TreePersonPanel
              personId={selected}
              isFocus={view === "family" && selected === rootId}
              onSelect={setSelected}
              onCentre={centre}
              onClose={() => setSelected(null)}
            />
          </div>
        )}
      </div>
      {view === "family" ? (
        <p className="mt-3 text-xs text-ink-muted">{t("treeView.family.hint")}</p>
      ) : (
        <div className="mt-3 flex flex-wrap items-center gap-3 text-sm">
          <span className="text-ink-muted">{t("treeView.showingGenerations", { count: depth })}</span>
          {graph.data && <span className="text-ink-muted">· {t("treeView.peopleShown", { count: graph.data.nodes.filter((n) => n.person).length })}</span>}
          {mayHaveMore && (
            <Button size="sm" variant="secondary" loading={graph.isFetching} onClick={() => setDepth((d) => Math.min(MAX_DEPTH, d + 2))}>
              {t("treeView.loadMore")}
            </Button>
          )}
          {depth > 3 && (
            <Button size="sm" variant="ghost" onClick={() => setDepth(3)}>
              {t("treeView.reset")}
            </Button>
          )}
          <span className="text-xs text-ink-muted">{t("treeView.legend")}</span>
        </div>
      )}
    </div>
  );
}
