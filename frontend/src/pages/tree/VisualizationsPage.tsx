import { useSearchParams } from "react-router-dom";
import { useTranslation } from "react-i18next";
import type { PersonSummary } from "../../api/types";
import { usePerson } from "../../api/hooks/people";
import { useTreeCtx } from "../../lib/tree-context";
import { recentPeople } from "../../lib/recent";
import { COLOR_BYS, type ColorBy } from "../../lib/vizColors";
import { PersonPicker } from "../../components/pickers";
import { PageHeader } from "../../components/ui/feedback";
import { Tabs } from "../../components/ui/Tabs";
import { AncestryChart, DEFAULT_ANCESTRY, type AncestrySettings } from "../../components/viz/AncestryChart";
import { NodeGraph } from "../../components/viz/NodeGraph";
import { LifespanChart } from "../../components/viz/LifespanChart";
import { StoryTimeline } from "../../components/viz/StoryTimeline";
import { GeoMapView } from "../../components/viz/GeoMapView";
import { FamilyTreeView } from "../../components/viz/FamilyTreeView";
import { PresetBar } from "../../components/viz/PresetBar";

export const CHARTS = ["fan", "graph", "pedigree", "family", "lifespan", "events", "map"] as const;
type ChartId = (typeof CHARTS)[number];
const NEEDS_ROOT = new Set<ChartId>(["fan", "graph", "pedigree", "family", "events"]);

/** Fan chart, dynamic graph, pedigree, family tree, lifespans, event timeline and map. */
export function VisualizationsPage() {
  const { t } = useTranslation();
  const { treeId, tree } = useTreeCtx();
  const [params, setParams] = useSearchParams();
  const chart = (CHARTS as readonly string[]).includes(params.get("chart") ?? "") ? (params.get("chart") as ChartId) : "fan";
  const rootId = params.get("root") ?? tree.my_linked_person_id ?? recentPeople(treeId)[0] ?? "";
  const root = usePerson(treeId, rootId || undefined);
  const settings: AncestrySettings = {
    generations: Number(params.get("gen")) || DEFAULT_ANCESTRY.generations,
    colorBy: (COLOR_BYS as string[]).includes(params.get("color") ?? "") ? (params.get("color") as ColorBy) : DEFAULT_ANCESTRY.colorBy,
    showMissing: params.get("gaps") !== "0",
  };
  const update = (patch: Record<string, string | null>) => {
    const next = new URLSearchParams(params);
    for (const [k, v] of Object.entries(patch)) {
      if (v === null) next.delete(k);
      else next.set(k, v);
    }
    setParams(next, { replace: true });
  };
  const setAncestry = (s: AncestrySettings) => update({ gen: String(s.generations), color: s.colorBy, gaps: s.showMissing ? "1" : "0" });
  const rootPicker = (
    <div className="w-full max-w-sm">
      <PersonPicker
        treeId={treeId}
        label={t("viz.rootPerson")}
        value={(root.data as PersonSummary | undefined) ?? null}
        onChange={(p) => update({ root: p ? p.id : null })}
      />
    </div>
  );
  return (
    <div>
      <PageHeader title={t("viz.title")} subtitle={t("viz.subtitle")} />
      <Tabs label={t("viz.charts")} tabs={CHARTS.map((id) => ({ id, label: t(`viz.chart.${id}`) }))} active={chart} onChange={(id) => update({ chart: id })}>
        <div className="space-y-4">
          <p className="text-sm text-ink-muted">{t(`viz.chartHint.${chart}`)}</p>
          {(NEEDS_ROOT.has(chart) || chart === "lifespan" || chart === "map") && rootPicker}
          {(chart === "fan" || chart === "pedigree") && (
            <PresetBar chartType={chart} settings={{ ...settings }} onApply={(s) => setAncestry({ ...settings, ...(s as Partial<AncestrySettings>) })} />
          )}
          {NEEDS_ROOT.has(chart) && !rootId && <p className="card p-4 text-sm">{t("viz.pickRoot")}</p>}
          {rootId && chart === "fan" && <AncestryChart key={`fan-${rootId}`} kind="fan" rootId={rootId} settings={settings} onSettings={setAncestry} />}
          {rootId && chart === "pedigree" && <AncestryChart key={`ped-${rootId}`} kind="pedigree" rootId={rootId} settings={settings} onSettings={setAncestry} />}
          {rootId && chart === "graph" && <NodeGraph rootId={rootId} />}
          {rootId && chart === "family" && <FamilyTreeView key={rootId} rootId={rootId} />}
          {rootId && chart === "events" && <StoryTimeline personId={rootId} />}
          {chart === "lifespan" && <LifespanChart rootId={rootId || undefined} />}
          {chart === "map" && <GeoMapView personId={params.get("root") ?? undefined} />}
        </div>
      </Tabs>
    </div>
  );
}
