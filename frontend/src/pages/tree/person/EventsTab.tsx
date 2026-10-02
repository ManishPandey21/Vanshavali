import { useState } from "react";
import { useTranslation } from "react-i18next";
import { ArrowRight, BookOpen, CalendarPlus, Camera, Edit3, MapPin, Trash2 } from "lucide-react";
import type { EventOut, PersonOut } from "../../../api/types";
import { useDeleteEvent, usePersonEvents } from "../../../api/hooks/people";
import { useTreeCtx } from "../../../lib/tree-context";
import { DateText, TimeText } from "../../../components/dates/DateText";
import { EvidenceBadge, RedactionNotice } from "../../../components/person/badges";
import { CitationList } from "../../../components/evidence/Citations";
import { Button } from "../../../components/ui/Button";
import { ConfirmDialog } from "../../../components/ui/Dialog";
import { EmptyState, ErrorAlert, Spinner } from "../../../components/ui/feedback";
import { Badge } from "../../../components/ui/Badge";
import { EventDialog } from "./EventDialog";
import { Checkbox } from "../../../components/ui/form";
import { EventAlbum } from "../../../components/events/EventAlbum";
import { PhotoThumb } from "../../../components/events/PhotoThumb";
import { ReminderControl } from "../../../components/events/ReminderControl";
import { eventLabel, isImportant } from "../../../lib/lifeEvents";
import { formatCoords } from "../../../lib/geo";

/** A person's life events: add, edit, photos (album), reminders and sources. */
export function EventsTab({ person }: { person: PersonOut }) {
  const { t } = useTranslation();
  const { treeId } = useTreeCtx();
  const events = usePersonEvents(treeId, person.id);
  const [importantOnly, setImportantOnly] = useState(false);
  const [album, setAlbum] = useState<EventOut | null>(null);
  const shown = (events.data ?? []).filter((e) => !importantOnly || isImportant(e));
  const del = useDeleteEvent(treeId);
  const [editing, setEditing] = useState<EventOut | "new" | null>(null);
  const [deleting, setDeleting] = useState<EventOut | null>(null);
  const [openCites, setOpenCites] = useState<string | null>(null);

  return (
    <section aria-labelledby="tl-title">
      <div className="mb-3 flex flex-wrap items-center justify-between gap-2">
        <h2 id="tl-title" className="font-display text-lg font-semibold">
          {t("lifeEvents.heading")}
        </h2>
        <Checkbox label={t("lifeEvents.importantOnly")} checked={importantOnly} onChange={setImportantOnly} />
        {person.can_edit && (
          <Button size="sm" icon={<CalendarPlus className="size-4" aria-hidden />} onClick={() => setEditing("new")}>
            {t("events.add")}
          </Button>
        )}
      </div>
      {events.isLoading && <Spinner />}
      <ErrorAlert error={events.error} />
      {events.data && events.data.length === 0 && <EmptyState title={t("events.none")}>{t("events.noneHint")}</EmptyState>}
      <ol className="relative space-y-3 border-l-2 border-haldi-300 pl-5">
        {shown.map((e) => {
          const principal = e.participants?.find((p) => p.role === "principal");
          const isOwn = principal?.person_id === person.id;
          return (
            <li key={e.id} className="relative">
              <span className="absolute -left-[27px] top-4 size-3 rounded-full border-2 border-white bg-kumkum-700" aria-hidden />
              <article className="card p-3" aria-label={eventLabel(e, t)}>
                <div className="flex flex-wrap items-start justify-between gap-2">
                  {e.cover_document_id && (
                    <button type="button" className="shrink-0" onClick={() => setAlbum(e)} aria-label={t("photos.openAlbum", { event: eventLabel(e, t) })}>
                      <PhotoThumb treeId={treeId} documentId={e.cover_document_id} alt="" className="size-16 rounded-md" />
                    </button>
                  )}
                  <div className="min-w-0 flex-1">
                    <h3 className="font-semibold">
                      {eventLabel(e, t)}
                      {(e.title || e.category) && <span className="font-normal text-ink-muted"> · {e.category ? t(`enum.lifeEventCategory.${e.category}`) : t(`enum.eventType.${e.type}`)}</span>}
                      {e.subtype && <span className="font-normal text-ink-muted"> · {e.subtype}</span>}
                      {e.significance && e.significance !== "standard" && (
                        <span className="ml-2">
                          <Badge tone="saffron">{t(`enum.significance.${e.significance}`)}</Badge>
                        </span>
                      )}
                      {e.privacy_level && (
                        <span className="ml-2">
                          <Badge tone="stone">{t(`enum.privacy.${e.privacy_level}`)}</Badge>
                        </span>
                      )}
                      {!e.is_preferred && (
                        <span className="ml-2">
                          <Badge tone="stone">{t("events.alternative")}</Badge>
                        </span>
                      )}
                    </h3>
                    <div className="mt-1 text-sm">{e.date ? <DateText date={e.date} /> : <span className="text-ink-muted">{t("date.display.unknown")}</span>}</div>
                    {e.type === "birth" && (e.time as { value?: string } | null)?.value && (
                      <div className="text-sm">
                        <TimeText time={e.time} />
                        {e.timezone_id && <span className="ml-1 text-xs text-ink-muted">({e.timezone_id})</span>}
                      </div>
                    )}
                    {e.type === "migration" && (e.origin_place_as_recorded || e.origin_place_name) ? (
                      <p className="mt-1 flex flex-wrap items-center gap-1 text-sm">
                        <MapPin className="size-3.5 text-ink-muted" aria-hidden />
                        <span>{e.origin_place_as_recorded || e.origin_place_name}</span>
                        <ArrowRight className="size-3.5" aria-label={t("events.to")} />
                        <span>{e.place_as_recorded || e.place_name || t("common.unknown")}</span>
                      </p>
                    ) : (
                      (e.place_as_recorded || e.place_name) && (
                        <p className="mt-1 flex items-center gap-1 text-sm">
                          <MapPin className="size-3.5 text-ink-muted" aria-hidden />
                          {e.place_as_recorded || e.place_name}
                        </p>
                      )
                    )}
                    {e.latitude != null && e.longitude != null && (
                      <p className="mt-1 text-xs text-ink-muted">
                        {formatCoords({ latitude: e.latitude, longitude: e.longitude })}
                        {e.location_precision ? ` · ${t(`enum.locationPrecision.${e.location_precision}`)}` : ""}
                      </p>
                    )}
                    {e.reason && <p className="mt-1 text-sm text-ink-muted">{t("events.reason")}: {e.reason}</p>}
                    {e.description && <p className="mt-1 text-sm">{e.description}</p>}
                    {!isOwn && e.participants && e.participants.length > 0 && (
                      <p className="mt-1 text-xs text-ink-muted">
                        {t("events.with")}: {e.participants.map((p) => p.display_name ?? t("person.privatePerson")).join(", ")}
                      </p>
                    )}
                    {(e.redacted_fields ?? []).length > 0 && (
                      <div className="mt-1">
                        <RedactionNotice />
                      </div>
                    )}
                  </div>
                  <div className="flex flex-wrap items-center gap-1">
                    <EvidenceBadge status={e.evidence_status} />
                    <button
                      type="button"
                      className="inline-flex items-center gap-1 rounded px-1.5 py-1 text-xs text-kumkum-800 hover:bg-kumkum-50"
                      onClick={() => setAlbum(e)}
                      aria-label={t("photos.openAlbum", { event: eventLabel(e, t) })}
                    >
                      <Camera className="size-3.5" aria-hidden />
                      {t("photos.count", { count: e.media_count ?? 0 })}
                    </button>
                    <ReminderControl treeId={treeId} event={e} />
                    <button
                      type="button"
                      className="inline-flex items-center gap-1 rounded px-1.5 py-1 text-xs text-kumkum-800 hover:bg-kumkum-50"
                      aria-expanded={openCites === e.id}
                      onClick={() => setOpenCites(openCites === e.id ? null : e.id)}
                    >
                      <BookOpen className="size-3.5" aria-hidden />
                      {t("citations.count", { count: e.citation_count ?? 0 })}
                    </button>
                    {person.can_edit && (
                      <>
                        <button type="button" className="rounded p-1.5 hover:bg-parchment-deep" onClick={() => setEditing(e)} aria-label={t("events.edit", { type: eventLabel(e, t) })}>
                          <Edit3 className="size-4" aria-hidden />
                        </button>
                        <button type="button" className="rounded p-1.5 text-red-800 hover:bg-red-50" onClick={() => setDeleting(e)} aria-label={t("events.delete", { type: eventLabel(e, t) })}>
                          <Trash2 className="size-4" aria-hidden />
                        </button>
                      </>
                    )}
                  </div>
                </div>
                {openCites === e.id && <CitationList targetType="event" targetId={e.id} canEditTarget={!!person.can_edit} />}
              </article>
            </li>
          );
        })}
      </ol>
      {album && <EventAlbum treeId={treeId} event={album} canEdit={!!person.can_edit} onClose={() => setAlbum(null)} />}
      {editing && <EventDialog personId={person.id} event={editing === "new" ? null : editing} onClose={() => setEditing(null)} />}
      <ConfirmDialog
        open={!!deleting}
        onClose={() => setDeleting(null)}
        title={t("events.deleteTitle")}
        body={t("events.deleteBody")}
        confirmLabel={t("common.delete")}
        danger
        loading={del.isPending}
        onConfirm={() => deleting && del.mutate(deleting.id, { onSuccess: () => setDeleting(null) })}
      >
        <ErrorAlert error={del.error} />
      </ConfirmDialog>
    </section>
  );
}
