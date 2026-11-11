import { useMemo, useState } from "react";
import { Link } from "react-router-dom";
import { useTranslation } from "react-i18next";
import { ChevronLeft, ChevronRight, Copy, Moon, Sun } from "lucide-react";
import type { CalendarEntryOut } from "../../api/types";
import { useCalendarFeed, useCalendarSettings, useCreateCalendarFeed, useFamilyCalendar, useRevokeCalendarFeed } from "../../api/hooks/calendar";
import { useTreeCtx } from "../../lib/tree-context";
import { Perm } from "../../lib/permissions";
import { Button } from "../../components/ui/Button";
import { Badge } from "../../components/ui/Badge";
import { EmptyState, ErrorAlert, LiveRegion, PageHeader, Spinner } from "../../components/ui/feedback";
import { Checkbox } from "../../components/ui/form";

const iso = (d: Date) => `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}-${String(d.getDate()).padStart(2, "0")}`;

/** Three months from the first of a month, so a window never cuts an entry in half. */
function windowFrom(offset: number) {
  const now = new Date();
  const start = new Date(now.getFullYear(), now.getMonth() + offset * 3, 1);
  const end = new Date(start.getFullYear(), start.getMonth() + 3, 0);
  return { from: iso(start), to: iso(end), start };
}

/**
 * The family calendar (ADR-0022 §5): birthdays, anniversaries and remembrance days for the next
 * months, by the Gregorian date and, for an offered convention, by tithi. Only what you may see.
 */
export function CalendarPage() {
  const { t } = useTranslation();
  const [status, setStatus] = useState("");
  return (
    <div className="space-y-8">
      <PageHeader title={t("calendar.title")} subtitle={t("calendar.subtitle")} />
      <LiveRegion message={status} />
      <CalendarList />
      <FeedSection onStatus={setStatus} />
    </div>
  );
}

function CalendarList() {
  const { t, i18n } = useTranslation();
  const { treeId, can } = useTreeCtx();
  const [offset, setOffset] = useState(0);
  const w = windowFrom(offset);
  const cal = useFamilyCalendar(treeId, w.from, w.to);
  const settings = useCalendarSettings(treeId);
  const lang = i18n.language;
  const months = useMemo(() => {
    const groups = new Map<string, CalendarEntryOut[]>();
    for (const e of cal.data?.entries ?? []) {
      const key = e.day.slice(0, 7);
      groups.set(key, [...(groups.get(key) ?? []), e]);
    }
    return [...groups.entries()];
  }, [cal.data]);
  const range = `${w.start.toLocaleDateString(lang, { month: "long", year: "numeric" })} – ${new Date(w.to).toLocaleDateString(lang, { month: "long", year: "numeric" })}`;
  const reason = cal.data?.lunar_unavailable;
  const cityLabel = (key: string | null | undefined) => settings.data?.cities.find((c) => c.key === key)?.label ?? key;
  const convLabel = (key: string | null | undefined) => settings.data?.conventions.find((c) => c.key === key)?.label ?? key;
  return (
    <section aria-labelledby="cal-list" className="space-y-3">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <h2 id="cal-list" className="font-display text-xl font-semibold">
          {range}
        </h2>
        <div className="flex gap-2">
          <Button size="sm" variant="secondary" icon={<ChevronLeft className="size-4" aria-hidden />} onClick={() => setOffset(offset - 1)} disabled={offset <= 0}>
            {t("calendar.earlier")}
          </Button>
          <Button size="sm" variant="secondary" icon={<ChevronRight className="size-4" aria-hidden />} onClick={() => setOffset(offset + 1)} disabled={offset >= 3}>
            {t("calendar.later")}
          </Button>
        </div>
      </div>
      {reason && (
        <p className="rounded-lg bg-stone-100 p-3 text-sm text-ink-muted" role="note">
          {t(`calendar.unavailable.${reason}`)}
          {reason !== "disabled" && can(Perm.TREE_MANAGE) && (
            <>
              {" "}
              <Link className="text-kumkum-800 underline" to={`/t/${treeId}/admin/settings`}>
                {t("calendar.openSettings")}
              </Link>
            </>
          )}
        </p>
      )}
      {cal.isLoading && <Spinner />}
      <ErrorAlert error={cal.error} />
      {cal.data && months.length === 0 && <EmptyState title={t("calendar.empty")}>{t("calendar.emptyHint")}</EmptyState>}
      {months.map(([month, entries]) => (
        <div key={month} className="space-y-2">
          <h3 className="text-sm font-semibold uppercase tracking-wide text-ink-muted">
            {new Date(`${month}-01T00:00:00`).toLocaleDateString(lang, { month: "long", year: "numeric" })}
          </h3>
          <ul className="divide-y divide-stone-200 rounded-xl border border-stone-200 bg-white">
            {entries.map((e) => (
              <li key={`${e.event_id}-${e.day}-${e.basis}`} className="flex gap-3 p-3">
                <div className="w-12 shrink-0 text-center">
                  <p className="font-display text-xl font-semibold leading-none">{new Date(`${e.day}T00:00:00`).getDate()}</p>
                  <p className="text-xs text-ink-muted">{new Date(`${e.day}T00:00:00`).toLocaleDateString(lang, { weekday: "short" })}</p>
                </div>
                <div className="min-w-0 flex-1">
                  <p className="font-semibold">
                    {e.person_id ? (
                      <Link className="text-kumkum-900 hover:underline" to={`/t/${treeId}/people/${e.person_id}?tab=events`}>
                        {e.label}
                      </Link>
                    ) : (
                      e.label
                    )}
                    {e.anniversary ? <span className="ml-2 text-sm font-normal text-ink-muted">({t("reminders.nth", { count: e.anniversary })})</span> : null}
                  </p>
                  <div className="mt-1 flex flex-wrap items-center gap-2 text-sm text-ink-muted">
                    <span>{t(`enum.reminderKind.${e.kind}`)}</span>
                    {e.basis === "lunar" ? (
                      <Badge tone="violet" icon={<Moon className="size-3" aria-hidden />}>
                        {e.lunar_label}
                      </Badge>
                    ) : (
                      <Badge tone="stone" icon={<Sun className="size-3" aria-hidden />}>
                        {t("calendar.solar")}
                      </Badge>
                    )}
                  </div>
                  {e.basis === "lunar" && (
                    <p className="mt-1 text-xs text-ink-muted">
                      {t(`calendar.basis.${e.rule ?? "sunrise"}`, { convention: convLabel(e.convention), city: cityLabel(e.city) })}
                    </p>
                  )}
                </div>
              </li>
            ))}
          </ul>
        </div>
      ))}
    </section>
  );
}

function FeedSection({ onStatus }: { onStatus: (s: string) => void }) {
  const { t } = useTranslation();
  const { treeId } = useTreeCtx();
  const feed = useCalendarFeed(treeId);
  const create = useCreateCalendarFeed(treeId);
  const revoke = useRevokeCalendarFeed(treeId);
  const [names, setNames] = useState(false);
  const [url, setUrl] = useState<string | null>(null);
  const f = feed.data;
  const make = () =>
    create.mutate(names, {
      onSuccess: (r) => {
        setUrl(r.url ?? null);
        onStatus(t("calendar.feedCreated"));
      },
    });
  const copy = async () => {
    if (!url) return;
    try {
      await navigator.clipboard.writeText(url);
      onStatus(t("calendar.copied"));
    } catch {
      onStatus(t("calendar.copyFailed"));
    }
  };
  return (
    <section aria-labelledby="feed-title" className="card space-y-3 p-5">
      <h2 id="feed-title" className="font-display text-xl font-semibold">
        {t("calendar.feedTitle")}
      </h2>
      <p className="text-sm text-ink-muted">{t("calendar.feedHint")}</p>
      {feed.isLoading && <Spinner />}
      <ErrorAlert error={feed.error || create.error || revoke.error} />
      {f?.active && (
        <p className="text-sm">
          {t("calendar.feedActive", {
            date: f.created_at ? new Date(f.created_at).toLocaleDateString() : "",
          })}{" "}
          {f.include_names ? t("calendar.feedWithNames") : t("calendar.feedMinimal")}
        </p>
      )}
      {url && (
        <div className="space-y-2 rounded-lg bg-haldi-100 p-3">
          <label htmlFor="feed-url" className="text-sm font-medium">
            {t("calendar.feedUrl")}
          </label>
          <div className="flex flex-wrap gap-2">
            <input id="feed-url" className="input min-w-0 flex-1 font-mono text-xs" readOnly value={url} onFocus={(e) => e.currentTarget.select()} />
            <Button size="sm" variant="secondary" icon={<Copy className="size-3.5" aria-hidden />} onClick={copy}>
              {t("calendar.copy")}
            </Button>
          </div>
          <p className="text-xs text-ink-muted">{t("calendar.feedUrlOnce")}</p>
        </div>
      )}
      <Checkbox label={t("calendar.includeNames")} hint={t("calendar.includeNamesHint")} checked={names} onChange={setNames} />
      <div className="flex flex-wrap gap-2">
        <Button loading={create.isPending} onClick={make}>
          {f?.active ? t("calendar.replaceFeed") : t("calendar.createFeed")}
        </Button>
        {f?.active && (
          <Button
            variant="ghost"
            loading={revoke.isPending}
            onClick={() =>
              revoke.mutate(undefined, {
                onSuccess: () => {
                  setUrl(null);
                  onStatus(t("calendar.feedRevoked"));
                },
              })
            }
          >
            {t("calendar.revokeFeed")}
          </Button>
        )}
      </div>
    </section>
  );
}
