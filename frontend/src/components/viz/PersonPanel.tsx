import { useEffect, useRef } from "react";
import { Link } from "react-router-dom";
import { useTranslation } from "react-i18next";
import { X } from "lucide-react";
import type { VizPerson } from "../../api/types";
import { useTreeCtx } from "../../lib/tree-context";
import { yearsLabel } from "../../lib/vizColors";

/** Keyboard-reachable detail panel for the person selected in a chart (focus moves to it). */
export function PersonPanel({ person, onClose, extra }: { person: VizPerson; onClose: () => void; extra?: React.ReactNode }) {
  const { t } = useTranslation();
  const { treeId } = useTreeCtx();
  const ref = useRef<HTMLHeadingElement>(null);
  useEffect(() => ref.current?.focus(), [person.id]);
  return (
    <aside className="card no-print space-y-2 p-4" aria-labelledby="viz-panel-name">
      <div className="flex items-start justify-between gap-2">
        <h3 id="viz-panel-name" ref={ref} tabIndex={-1} className="font-display text-lg font-semibold focus:outline-none">
          {person.display_name}
        </h3>
        <button type="button" onClick={onClose} className="rounded p-1 hover:bg-parchment-deep" aria-label={t("common.close")}>
          <X className="size-4" aria-hidden />
        </button>
      </div>
      <dl className="grid grid-cols-[auto_1fr] gap-x-3 gap-y-1 text-sm">
        {yearsLabel(person) && (
          <>
            <dt className="text-ink-muted">{t("viz.panel.life")}</dt>
            <dd>{yearsLabel(person)}</dd>
          </>
        )}
        <dt className="text-ink-muted">{t("viz.panel.status")}</dt>
        <dd>{t(`enum.profileStatus.${person.profile_status}`)}</dd>
        {person.birth_place && (
          <>
            <dt className="text-ink-muted">{t("viz.panel.birthPlace")}</dt>
            <dd>{[person.birth_place.name, person.birth_place.district, person.birth_place.state].filter(Boolean).join(", ")}</dd>
          </>
        )}
        {person.village && (
          <>
            <dt className="text-ink-muted">{t("viz.panel.village")}</dt>
            <dd>{person.village}</dd>
          </>
        )}
        <dt className="text-ink-muted">{t("viz.panel.events")}</dt>
        <dd>{person.event_count ?? 0}</dd>
        {person.completeness && (
          <>
            <dt className="text-ink-muted">{t("viz.panel.completeness")}</dt>
            <dd>
              {Math.round(person.completeness.score * 100)}%
              {(person.completeness.missing ?? []).length > 0 && (
                <span className="block text-xs text-ink-muted">
                  {t("viz.panel.missing")}: {(person.completeness.missing ?? []).map((m) => t(`viz.missing.${m}`)).join(", ")}
                </span>
              )}
            </dd>
          </>
        )}
      </dl>
      {extra}
      <Link className="inline-block text-sm text-kumkum-800 underline" to={`/t/${treeId}/people/${person.id}`}>
        {t("viz.panel.openProfile")}
      </Link>
    </aside>
  );
}
