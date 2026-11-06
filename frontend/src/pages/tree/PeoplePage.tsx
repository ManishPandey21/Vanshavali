import { useId } from "react";
import { Link, useSearchParams } from "react-router-dom";
import { useTranslation } from "react-i18next";
import { CircleDashed, Search, UserPlus, Users } from "lucide-react";
import { TO_COMPLETE_STATES, usePeople } from "../../api/hooks/people";
import { useSearch } from "../../api/hooks/heritage";
import type { PersonSummary, ProfileStatus } from "../../api/types";
import { useTreeCtx } from "../../lib/tree-context";
import { Perm } from "../../lib/permissions";
import { useDebounced } from "../../lib/useDebounced";
import { Button, ButtonLink } from "../../components/ui/Button";
import { EmptyState, ErrorAlert, LiveRegion, PageHeader, Spinner } from "../../components/ui/feedback";
import { PersonBadges, PersonLink } from "../../components/person/badges";

export function PeoplePage() {
  const { t } = useTranslation();
  const { treeId, can } = useTreeCtx();
  const [params, setParams] = useSearchParams();
  const q = params.get("q") ?? "";
  const status = (params.get("status") as ProfileStatus | null) ?? undefined;
  // "To complete" (ADR-0020 §8): provisional people who still need a name or relationship evidence
  const toComplete = params.get("view") === "to-complete";
  const debounced = useDebounced(q.trim(), 300);
  const searchId = useId();
  const search = useSearch(treeId, debounced, ["person"]);
  const list = usePeople(treeId, "", status, toComplete ? TO_COMPLETE_STATES : undefined);
  const searching = debounced.length > 0;

  const setParam = (k: string, v: string | undefined) => {
    const next = new URLSearchParams(params);
    if (v) next.set(k, v);
    else next.delete(k);
    setParams(next, { replace: true });
  };

  const pending = (p: PersonSummary) => !!p.provisional_state && (TO_COMPLETE_STATES as readonly string[]).includes(p.provisional_state);
  const hits = (search.data?.hits ?? []).filter(
    (h) => h.kind === "person" && h.person && (!status || h.person.profile_status === status) && (!toComplete || pending(h.person)),
  );
  const people = list.data?.pages.flatMap((p) => p.items) ?? [];

  return (
    <div>
      <PageHeader
        title={t("people.title")}
        subtitle={t("people.subtitle")}
        actions={
          can(Perm.PERSON_WRITE) ? (
            <ButtonLink to={`/t/${treeId}/people/new`} icon={<UserPlus className="size-4" aria-hidden />}>
              {t("people.add")}
            </ButtonLink>
          ) : undefined
        }
      />
      <div className="mb-4 flex flex-col gap-3 sm:flex-row sm:items-center">
        <div className="relative flex-1">
          <label htmlFor={searchId} className="sr-only">
            {t("people.searchLabel")}
          </label>
          <Search className="pointer-events-none absolute left-3 top-2.5 size-4 text-ink-muted" aria-hidden />
          <input
            id={searchId}
            type="search"
            className="input pl-9"
            placeholder={t("people.searchPlaceholder")}
            value={q}
            onChange={(e) => setParam("q", e.target.value || undefined)}
          />
        </div>
        <div className="flex flex-wrap gap-2">
          <div role="group" aria-label={t("people.filterStatus")} className="flex gap-1">
            {([undefined, "living", "deceased", "unknown"] as const).map((s) => (
              <button
                key={s ?? "all"}
                type="button"
                aria-pressed={status === s}
                onClick={() => setParam("status", s)}
                className={`rounded-full border px-3 py-1 text-xs ${status === s ? "border-kumkum-700 bg-kumkum-700 text-white" : "border-stone-300 bg-white"}`}
              >
                {s ? t(`enum.profileStatus.${s}`) : t("common.all")}
              </button>
            ))}
          </div>
          <button
            type="button"
            aria-pressed={toComplete}
            onClick={() => setParam("view", toComplete ? undefined : "to-complete")}
            className={`inline-flex items-center gap-1 rounded-full border px-3 py-1 text-xs ${toComplete ? "border-haldi-700 bg-haldi-700 text-white" : "border-stone-300 bg-white"}`}
          >
            <CircleDashed className="size-3" aria-hidden />
            {t("people.toComplete.filter")}
          </button>
        </div>
      </div>
      {toComplete && <p className="mb-3 rounded-md bg-haldi-100 px-3 py-2 text-sm text-ink">{t("people.toComplete.intro")}</p>}
      <p className="mb-3 text-xs text-ink-muted">{t("people.searchHint")}</p>

      {searching ? (
        <section aria-labelledby="people-results">
          <h2 id="people-results" className="sr-only">
            {t("people.results")}
          </h2>
          {search.isFetching && <Spinner label={t("people.searching")} />}
          <ErrorAlert error={search.error} />
          <LiveRegion message={search.data ? t("people.resultCount", { count: hits.length }) : ""} />
          {search.data && hits.length === 0 && <EmptyState title={t("people.noResults", { q: debounced })}>{t("people.noResultsHint")}</EmptyState>}
          <ul className="card divide-y divide-stone-100">
            {hits.map((h) => (
              <li key={h.id} className="flex flex-col gap-1 px-4 py-3 sm:flex-row sm:items-center sm:justify-between">
                <div className="min-w-0">
                  <PersonLink treeId={treeId} person={h.person!} />
                  <p className="text-xs text-ink-muted">
                    <span className="font-medium">{t("search.matchReason")}:</span> {h.match_reason}
                  </p>
                </div>
                <PersonBadges person={h.person!} />
              </li>
            ))}
          </ul>
        </section>
      ) : (
        <section aria-labelledby="people-all">
          <h2 id="people-all" className="sr-only">
            {t("people.all")}
          </h2>
          {list.isLoading && <Spinner />}
          <ErrorAlert error={list.error} />
          {list.data && people.length === 0 && toComplete && (
            <EmptyState icon={<CircleDashed className="size-10" aria-hidden />} title={t("people.toComplete.emptyTitle")}>
              {t("people.toComplete.emptyBody")}
            </EmptyState>
          )}
          {list.data && people.length === 0 && !toComplete && (
            <EmptyState
              icon={<Users className="size-10" aria-hidden />}
              title={t("people.emptyTitle")}
              action={can(Perm.PERSON_WRITE) ? <ButtonLink to={`/t/${treeId}/people/new`}>{t("people.addFirst")}</ButtonLink> : undefined}
            >
              {t("people.emptyBody")}
            </EmptyState>
          )}
          {people.length > 0 && (
            <ul className="card divide-y divide-stone-100">
              {people.map((p) => (
                <li key={p.id} className="flex flex-col gap-1 px-4 py-3 sm:flex-row sm:items-center sm:justify-between">
                  <div className="min-w-0">
                    <PersonLink treeId={treeId} person={p} />
                    {toComplete && <ToCompleteAction treeId={treeId} person={p} />}
                  </div>
                  <PersonBadges person={p} showPrivacy />
                </li>
              ))}
            </ul>
          )}
          {list.hasNextPage && (
            <div className="mt-4 flex justify-center">
              <Button variant="secondary" onClick={() => void list.fetchNextPage()} loading={list.isFetchingNextPage}>
                {t("common.loadMore")}
              </Button>
            </div>
          )}
        </section>
      )}
    </div>
  );
}

/** What is missing for a provisional person, and where to fix it. */
function ToCompleteAction({ treeId, person }: { treeId: string; person: PersonSummary }) {
  const { t } = useTranslation();
  const needsName = person.provisional_state === "needs_details";
  return (
    <p className="text-xs text-ink-muted">
      {t(needsName ? "people.toComplete.needsDetails" : "people.toComplete.unverified")}{" "}
      <Link className="font-medium text-kumkum-800 underline" to={`/t/${treeId}/people/${person.id}?tab=${needsName ? "overview" : "family"}`}>
        {t(needsName ? "people.toComplete.addName" : "people.toComplete.reviewEvidence")}
        <span className="sr-only">: {person.display_name}</span>
      </Link>
    </p>
  );
}
