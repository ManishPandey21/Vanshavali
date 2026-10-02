import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { useTranslation } from "react-i18next";
import { ChevronLeft, ChevronRight, MapPin, Pause, Play } from "lucide-react";
import type { StoryEvent } from "../../api/types";
import { useStory } from "../../api/hooks/viz";
import { useTreeCtx } from "../../lib/tree-context";
import { decadeOf } from "../../lib/lifeEvents";
import { Button } from "../ui/Button";
import { EmptyState, ErrorAlert, Spinner } from "../ui/feedback";
import { PhotoThumb } from "../events/PhotoThumb";
import { AnimatedExport } from "./AnimatedExport";

type Mode = "grouped" | "detailed" | "slideshow";

function usePrefersReducedMotion(): boolean {
  const [reduced, setReduced] = useState(() => typeof window !== "undefined" && !!window.matchMedia?.("(prefers-reduced-motion: reduce)").matches);
  useEffect(() => {
    const mq = window.matchMedia?.("(prefers-reduced-motion: reduce)");
    if (!mq) return;
    const on = () => setReduced(mq.matches);
    mq.addEventListener?.("change", on);
    return () => mq.removeEventListener?.("change", on);
  }, []);
  return reduced;
}

/** Lifetime event timeline: grouped by decade, detailed, or a slideshow — all keyboard accessible. */
export function StoryTimeline({ personId, showExport = true }: { personId: string; showExport?: boolean }) {
  const { t } = useTranslation();
  const { treeId } = useTreeCtx();
  const story = useStory(treeId, personId);
  const [mode, setMode] = useState<Mode>("grouped");
  if (story.isLoading) return <Spinner />;
  if (story.error || !story.data) return <ErrorAlert error={story.error} />;
  const events = story.data.events;
  return (
    <section aria-labelledby="story-title" className="space-y-4">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <div>
          <h2 id="story-title" className="font-display text-lg font-semibold">
            {t("story.title", { name: story.data.person.display_name })}
          </h2>
          <p className="text-sm text-ink-muted">{story.data.summary}</p>
        </div>
        <div role="radiogroup" aria-label={t("story.mode")} className="inline-flex rounded-lg border border-stone-300 p-0.5">
          {(["grouped", "detailed", "slideshow"] as Mode[]).map((m) => (
            <button
              key={m}
              type="button"
              role="radio"
              aria-checked={mode === m}
              className={`rounded-md px-3 py-1 text-sm ${mode === m ? "bg-kumkum-100 font-semibold text-kumkum-900" : "text-ink"}`}
              onClick={() => setMode(m)}
            >
              {t(`story.modes.${m}`)}
            </button>
          ))}
        </div>
      </div>
      {events.length === 0 && <EmptyState title={t("events.none")}>{t("events.noneHint")}</EmptyState>}
      {events.length > 0 && mode === "slideshow" && <Slideshow events={events} />}
      {events.length > 0 && mode !== "slideshow" && <EventList events={events} detailed={mode === "detailed"} />}
      {showExport && events.length > 0 && <AnimatedExport chartType="event_timeline" settings={{ root_person_id: personId }} />}
    </section>
  );
}

function Place({ e }: { e: StoryEvent }) {
  if (!e.place) return null;
  return (
    <p className="flex items-center gap-1 text-sm text-ink-muted">
      <MapPin className="size-3.5" aria-hidden />
      {[e.place.name, e.place.district, e.place.state].filter(Boolean).join(", ")}
    </p>
  );
}

function EventList({ events, detailed }: { events: StoryEvent[]; detailed: boolean }) {
  const { t } = useTranslation();
  const { treeId } = useTreeCtx();
  const groups = new Map<string, StoryEvent[]>();
  for (const e of events) {
    const d = decadeOf(e.year);
    const key = d === null ? t("story.undated") : t("story.decade", { decade: d });
    groups.set(key, [...(groups.get(key) ?? []), e]);
  }
  return (
    <div className="space-y-5">
      {[...groups.entries()].map(([decade, list]) => (
        <section key={decade} aria-label={decade}>
          <h3 className="mb-2 text-sm font-semibold uppercase tracking-wide text-ink-muted">{decade}</h3>
          <ol className="relative space-y-3 border-l-2 border-haldi-300 pl-5">
            {list.map((e) => {
              const cover = e.photos?.find((p) => p.is_cover) ?? e.photos?.[0];
              return (
                <li key={e.id} className="relative">
                  <span className={`absolute -left-[27px] top-3 size-3 rounded-full border-2 border-white ${e.significance === "milestone" ? "bg-haldi-600" : "bg-kumkum-700"}`} aria-hidden />
                  <article className="card flex gap-3 p-3">
                    {cover?.has_thumbnail && <PhotoThumb treeId={treeId} documentId={cover.document_id} alt={cover.caption || e.label} className="size-20 shrink-0 rounded-md" />}
                    <div className="min-w-0">
                      <p className="text-sm font-semibold text-kumkum-800">{e.date_display ?? t("date.display.unknown")}</p>
                      <h4 className="font-semibold">{e.label}</h4>
                      <Place e={e} />
                      {detailed && e.description && <p className="mt-1 text-sm">{e.description}</p>}
                      {detailed && (e.relatives ?? []).length > 0 && (
                        <p className="mt-1 text-sm">
                          {t("events.with")}:{" "}
                          {(e.relatives ?? []).map((r, i) => (
                            <span key={r.person_id}>
                              {i > 0 && ", "}
                              <Link className="text-kumkum-800 underline" to={`/t/${treeId}/people/${r.person_id}`}>
                                {r.display_name}
                              </Link>
                            </span>
                          ))}
                        </p>
                      )}
                      {detailed && (e.photos ?? []).length > 1 && (
                        <ul className="mt-2 flex gap-2" aria-label={t("photos.listLabel")}>
                          {(e.photos ?? []).slice(1, 5).map((p) => (
                            <li key={p.media_id}>{p.has_thumbnail && <PhotoThumb treeId={treeId} documentId={p.document_id} alt={p.caption || e.label} className="size-14 rounded" />}</li>
                          ))}
                        </ul>
                      )}
                    </div>
                  </article>
                </li>
              );
            })}
          </ol>
        </section>
      ))}
    </div>
  );
}

function Slideshow({ events }: { events: StoryEvent[] }) {
  const { t } = useTranslation();
  const { treeId } = useTreeCtx();
  const reduced = usePrefersReducedMotion();
  const [i, setI] = useState(0);
  const [playing, setPlaying] = useState(false);
  useEffect(() => {
    if (!playing) return;
    const id = window.setInterval(() => setI((x) => (x + 1) % events.length), 5000);
    return () => window.clearInterval(id);
  }, [playing, events.length]);
  const e = events[Math.min(i, events.length - 1)];
  const photo = e.photos?.find((p) => p.has_thumbnail);
  return (
    <div
      className="card space-y-3 p-4"
      role="group"
      aria-roledescription={t("story.slideshow")}
      aria-label={t("story.slideOf", { n: i + 1, total: events.length })}
    >
      <div className="grid gap-4 md:grid-cols-2">
        {photo ? (
          <PhotoThumb treeId={treeId} documentId={photo.document_id} alt={photo.caption || e.label} variant="preview" className="aspect-[4/3] w-full rounded-lg" />
        ) : (
          <div className="flex aspect-[4/3] items-center justify-center rounded-lg bg-parchment-deep font-display text-4xl text-kumkum-800" aria-hidden>
            {e.year ?? "—"}
          </div>
        )}
        <div aria-live={playing ? "off" : "polite"}>
          <p className="text-lg font-semibold text-kumkum-800">{e.date_display ?? t("date.display.unknown")}</p>
          <h3 className="font-display text-2xl font-bold">{e.label}</h3>
          <Place e={e} />
          {e.description && <p className="mt-2">{e.description}</p>}
          {(e.relatives ?? []).length > 0 && <p className="mt-2 text-sm text-ink-muted">{(e.relatives ?? []).map((r) => r.display_name).join(", ")}</p>}
          {photo?.caption && <p className="mt-2 text-sm italic text-ink-muted">{photo.caption}</p>}
        </div>
      </div>
      <div className="flex items-center justify-between gap-2">
        <Button size="sm" variant="secondary" icon={<ChevronLeft className="size-4" aria-hidden />} disabled={i === 0} onClick={() => setI(i - 1)}>
          {t("story.previous")}
        </Button>
        <span className="text-sm text-ink-muted">{t("story.slideOf", { n: i + 1, total: events.length })}</span>
        {!reduced && (
          <Button size="sm" variant="ghost" icon={playing ? <Pause className="size-4" aria-hidden /> : <Play className="size-4" aria-hidden />} onClick={() => setPlaying(!playing)}>
            {playing ? t("story.pause") : t("story.play")}
          </Button>
        )}
        <Button size="sm" variant="secondary" icon={<ChevronRight className="size-4" aria-hidden />} disabled={i === events.length - 1} onClick={() => setI(i + 1)}>
          {t("story.next")}
        </Button>
      </div>
    </div>
  );
}
