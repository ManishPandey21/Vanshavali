import { Link } from "react-router-dom";
import { useTranslation } from "react-i18next";
import type { EventOut } from "../../api/types";
import { useLifeEvents } from "../../api/hooks/lifeevents";
import { useTreeCtx } from "../../lib/tree-context";
import { decadeOf, eventLabel } from "../../lib/lifeEvents";
import { DateText } from "../../components/dates/DateText";
import { Button } from "../../components/ui/Button";
import { EmptyState, ErrorAlert, PageHeader, Spinner } from "../../components/ui/feedback";
import { LifespanChart } from "../../components/viz/LifespanChart";

/** The family across time: lifespans and a chronology of important events. */
export function TimelinePage() {
  const { t } = useTranslation();
  const { treeId } = useTreeCtx();
  const events = useLifeEvents(treeId, { important_only: true });
  const all: EventOut[] = events.data?.pages.flatMap((p) => p.items) ?? [];
  const groups = new Map<string, EventOut[]>();
  for (const e of all) {
    const d = decadeOf((e.date as { year?: number } | null)?.year);
    const key = d === null ? t("story.undated") : t("story.decade", { decade: d });
    groups.set(key, [...(groups.get(key) ?? []), e]);
  }
  return (
    <div className="space-y-8">
      <PageHeader title={t("timelinePage.title")} subtitle={t("timelinePage.subtitle")} />
      <LifespanChart />
      <section aria-labelledby="chrono-title" className="space-y-3">
        <h2 id="chrono-title" className="font-display text-xl font-semibold">
          {t("timelinePage.chronology")}
        </h2>
        {events.isLoading && <Spinner />}
        <ErrorAlert error={events.error} />
        {events.data && all.length === 0 && <EmptyState title={t("lifeEvents.none")}>{t("lifeEvents.noneHint")}</EmptyState>}
        {[...groups.entries()].map(([decade, list]) => (
          <div key={decade}>
            <h3 className="mb-1 text-sm font-semibold uppercase tracking-wide text-ink-muted">{decade}</h3>
            <ul className="space-y-1">
              {list.map((e) => {
                const who = (e.participants ?? []).find((p) => p.role === "principal");
                return (
                  <li key={e.id} className="text-sm">
                    {e.date ? <DateText date={e.date} showOriginal={false} /> : t("date.display.unknown")} —{" "}
                    <strong>{eventLabel(e, t)}</strong>
                    {who && (
                      <>
                        {" · "}
                        <Link className="text-kumkum-800 underline" to={`/t/${treeId}/people/${who.person_id}?tab=timeline`}>
                          {who.display_name}
                        </Link>
                      </>
                    )}
                    {(e.place_name || e.place_as_recorded) && <span className="text-ink-muted"> · {e.place_name || e.place_as_recorded}</span>}
                  </li>
                );
              })}
            </ul>
          </div>
        ))}
        {events.hasNextPage && (
          <Button variant="secondary" loading={events.isFetchingNextPage} onClick={() => void events.fetchNextPage()}>
            {t("common.loadMore")}
          </Button>
        )}
      </section>
    </div>
  );
}
