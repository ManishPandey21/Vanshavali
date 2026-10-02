import { useState } from "react";
import { Link } from "react-router-dom";
import { useTranslation } from "react-i18next";
import { CalendarPlus, Camera, MapPin } from "lucide-react";
import type { EventOut, LifeEventCategory, PersonSummary } from "../../api/types";
import { useLifeEvents, type LifeEventFilters } from "../../api/hooks/lifeevents";
import { useTreeCtx } from "../../lib/tree-context";
import { Perm } from "../../lib/permissions";
import { useDebounced } from "../../lib/useDebounced";
import { CATEGORY_GROUPS, eventLabel } from "../../lib/lifeEvents";
import { DateText } from "../../components/dates/DateText";
import { PersonPicker } from "../../components/pickers";
import { Button } from "../../components/ui/Button";
import { Dialog } from "../../components/ui/Dialog";
import { EmptyState, ErrorAlert, PageHeader, Spinner } from "../../components/ui/feedback";
import { Checkbox, Field, Select, TextInput } from "../../components/ui/form";
import { Badge } from "../../components/ui/Badge";
import { EventAlbum } from "../../components/events/EventAlbum";
import { PhotoThumb } from "../../components/events/PhotoThumb";
import { ReminderControl } from "../../components/events/ReminderControl";
import { EventDialog } from "./person/EventDialog";

/** Important life events across the tree, with filters, photos and reminders. */
export function EventsPage() {
  const { t } = useTranslation();
  const { treeId, can } = useTreeCtx();
  const [category, setCategory] = useState<LifeEventCategory | "">("");
  const [importantOnly, setImportantOnly] = useState(true);
  const [geotagged, setGeotagged] = useState(false);
  const [from, setFrom] = useState("");
  const [to, setTo] = useState("");
  const [q, setQ] = useState("");
  const dq = useDebounced(q.trim(), 300);
  const filters: LifeEventFilters = {
    category: category ? [category] : undefined,
    important_only: importantOnly,
    geotagged: geotagged || undefined,
    from_year: Number(from) || undefined,
    to_year: Number(to) || undefined,
    q: dq || undefined,
  };
  const events = useLifeEvents(treeId, filters);
  const items: EventOut[] = events.data?.pages.flatMap((p) => p.items) ?? [];
  const [adding, setAdding] = useState(false);
  const [person, setPerson] = useState<PersonSummary | null>(null);
  const [album, setAlbum] = useState<EventOut | null>(null);
  return (
    <div>
      <PageHeader
        title={t("lifeEvents.pageTitle")}
        subtitle={t("lifeEvents.pageSubtitle")}
        actions={
          can(Perm.PERSON_WRITE) ? (
            <Button icon={<CalendarPlus className="size-4" aria-hidden />} onClick={() => setAdding(true)}>
              {t("events.add")}
            </Button>
          ) : undefined
        }
      />
      <form className="card mb-4 grid grid-cols-1 gap-3 p-3 sm:grid-cols-2 lg:grid-cols-6" onSubmit={(e) => e.preventDefault()} aria-label={t("lifeEvents.filters")}>
        <Field label={t("lifeEvents.search")}>{(p) => <TextInput {...p} type="search" value={q} onChange={(e) => setQ(e.target.value)} />}</Field>
        <Field label={t("lifeEvents.category")}>
          {(p) => (
            <Select {...p} value={category} onChange={(e) => setCategory(e.target.value as LifeEventCategory | "")}>
              <option value="">{t("viz.all")}</option>
              {CATEGORY_GROUPS.map((g) => (
                <optgroup key={g.id} label={t(`lifeEvents.group.${g.id}`)}>
                  {g.categories.map((c) => (
                    <option key={c} value={c}>
                      {t(`enum.lifeEventCategory.${c}`)}
                    </option>
                  ))}
                </optgroup>
              ))}
            </Select>
          )}
        </Field>
        <Field label={t("lifeEvents.fromYear")}>{(p) => <TextInput {...p} inputMode="numeric" value={from} onChange={(e) => setFrom(e.target.value)} />}</Field>
        <Field label={t("lifeEvents.toYear")}>{(p) => <TextInput {...p} inputMode="numeric" value={to} onChange={(e) => setTo(e.target.value)} />}</Field>
        <div className="flex flex-col justify-end gap-1 pb-1 lg:col-span-2">
          <Checkbox label={t("lifeEvents.importantOnly")} checked={importantOnly} onChange={setImportantOnly} />
          <Checkbox label={t("lifeEvents.geotaggedOnly")} checked={geotagged} onChange={setGeotagged} />
        </div>
      </form>
      {events.isLoading && <Spinner />}
      <ErrorAlert error={events.error} />
      {events.data && items.length === 0 && <EmptyState title={t("lifeEvents.none")}>{t("lifeEvents.noneHint")}</EmptyState>}
      <ul className="grid gap-3 md:grid-cols-2" aria-label={t("lifeEvents.pageTitle")}>
        {items.map((e) => {
          const who = (e.participants ?? []).find((p) => p.role === "principal");
          return (
            <li key={e.id} className="card flex gap-3 p-3">
              {e.cover_document_id ? (
                <button type="button" onClick={() => setAlbum(e)} aria-label={t("photos.openAlbum", { event: eventLabel(e, t) })} className="shrink-0">
                  <PhotoThumb treeId={treeId} documentId={e.cover_document_id} alt="" className="size-20 rounded-md" />
                </button>
              ) : null}
              <div className="min-w-0 flex-1 space-y-1">
                <p className="text-sm font-semibold text-kumkum-800">{e.date ? <DateText date={e.date} showOriginal={false} /> : t("date.display.unknown")}</p>
                <h2 className="font-semibold">
                  {eventLabel(e, t)}
                  {e.significance && e.significance !== "standard" && (
                    <span className="ml-2">
                      <Badge tone="saffron">{t(`enum.significance.${e.significance}`)}</Badge>
                    </span>
                  )}
                </h2>
                {who && (
                  <Link className="text-sm text-kumkum-800 underline" to={`/t/${treeId}/people/${who.person_id}?tab=events`}>
                    {who.display_name}
                  </Link>
                )}
                {(e.place_name || e.place_as_recorded) && (
                  <p className="flex items-center gap-1 text-sm text-ink-muted">
                    <MapPin className="size-3.5" aria-hidden /> {e.place_name || e.place_as_recorded}
                  </p>
                )}
                <div className="flex flex-wrap items-center gap-1">
                  <button type="button" className="inline-flex items-center gap-1 rounded px-1.5 py-1 text-xs text-kumkum-800 hover:bg-kumkum-50" onClick={() => setAlbum(e)}>
                    <Camera className="size-3.5" aria-hidden /> {t("photos.count", { count: e.media_count ?? 0 })}
                  </button>
                  <ReminderControl treeId={treeId} event={e} />
                </div>
              </div>
            </li>
          );
        })}
      </ul>
      {events.hasNextPage && (
        <div className="mt-4">
          <Button variant="secondary" loading={events.isFetchingNextPage} onClick={() => void events.fetchNextPage()}>
            {t("common.loadMore")}
          </Button>
        </div>
      )}
      {album && <EventAlbum treeId={treeId} event={album} canEdit={can(Perm.PERSON_WRITE)} onClose={() => setAlbum(null)} />}
      {adding && !person && (
        <Dialog open onClose={() => setAdding(false)} title={t("lifeEvents.whoTitle")} description={t("lifeEvents.whoHint")}>
          <PersonPicker treeId={treeId} label={t("lifeEvents.whose")} value={null} onChange={(p) => p && setPerson(p)} />
        </Dialog>
      )}
      {adding && person && (
        <EventDialog
          personId={person.id}
          event={null}
          initialCategory="custom"
          onClose={() => {
            setAdding(false);
            setPerson(null);
          }}
        />
      )}
    </div>
  );
}
