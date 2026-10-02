import { useState } from "react";
import { useNavigate } from "react-router-dom";
import { useTranslation } from "react-i18next";
import { useGraph } from "../../api/hooks/people";
import { useTreeCtx } from "../../lib/tree-context";
import { TreeChart } from "../tree/TreeChart";
import { TreeList } from "../tree/TreeList";
import { EmptyState, ErrorAlert, Spinner } from "../ui/feedback";
import { Field, Select } from "../ui/form";
import { ChartFrame } from "./ChartFrame";
import { AnimatedExport } from "./AnimatedExport";

/** Ancestor / descendant family tree (the existing tree chart) with exports and an animated version. */
export function FamilyTreeView({ rootId }: { rootId: string }) {
  const { t } = useTranslation();
  const { treeId } = useTreeCtx();
  const navigate = useNavigate();
  const [direction, setDirection] = useState<"ancestors" | "descendants">("descendants");
  const [depth, setDepth] = useState(3);
  const [collapsed, setCollapsed] = useState<Set<string>>(new Set());
  const graph = useGraph(treeId, rootId, direction, depth, []);
  const controls = (
    <>
      <Field label={t("viz.mode")}>
        {(p) => (
          <Select {...p} value={direction} onChange={(e) => { setCollapsed(new Set()); setDirection(e.target.value as "ancestors" | "descendants"); }}>
            <option value="descendants">{t("treeView.descendants")}</option>
            <option value="ancestors">{t("treeView.ancestors")}</option>
          </Select>
        )}
      </Field>
      <Field label={t("viz.generations")}>
        {(p) => (
          <Select {...p} value={depth} onChange={(e) => setDepth(Number(e.target.value))}>
            {[1, 2, 3, 4, 5, 6].map((g) => (
              <option key={g} value={g}>
                {g}
              </option>
            ))}
          </Select>
        )}
      </Field>
    </>
  );
  if (graph.isLoading) return <Spinner />;
  if (graph.error || !graph.data) return <ErrorAlert error={graph.error} />;
  const people = graph.data.nodes.filter((n) => n.person).length;
  return (
    <div className="grid gap-4 lg:grid-cols-[1fr_18rem]">
      <ChartFrame
        title={t("viz.chart.family")}
        summary={t("viz.familySummary", { count: people, generations: depth })}
        filename={`family-tree-${direction}`}
        controls={controls}
        alternative={<TreeList graph={graph.data} personHref={(id) => `/t/${treeId}/people/${id}`} />}
      >
        {graph.data.nodes.length <= 1 ? (
          <EmptyState title={t(`treeView.none.${direction}`)}>{t("treeView.noneHint")}</EmptyState>
        ) : (
          <TreeChart
            graph={graph.data}
            onOpen={(id) => navigate(`/t/${treeId}/people/${id}`)}
            collapsed={collapsed}
            onToggleCollapse={(id) =>
              setCollapsed((prev) => {
                const n = new Set(prev);
                if (n.has(id)) n.delete(id);
                else n.add(id);
                return n;
              })
            }
          />
        )}
      </ChartFrame>
      <AnimatedExport chartType="family_tree" settings={{ root_person_id: rootId, direction, generations: Math.min(depth, 6) }} />
    </div>
  );
}
