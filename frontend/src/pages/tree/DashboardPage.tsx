import { useQueries, useQuery } from "@tanstack/react-query";
import { Link } from "react-router-dom";
import { useTranslation } from "react-i18next";
import { BookOpen, Landmark, MapPin, Network, Route, UserPlus, Users, UsersRound } from "lucide-react";
import { api } from "../../api/client";
import type { Page, PersonOut, PersonSummary } from "../../api/types";
import { useBranches, useHouseholds } from "../../api/hooks/family";
import { usePlaces } from "../../api/hooks/people";
import { useSources } from "../../api/hooks/heritage";
import { useTreeCtx } from "../../lib/tree-context";
import { Perm } from "../../lib/permissions";
import { recentPeople } from "../../lib/recent";
import { ButtonLink } from "../../components/ui/Button";
import { EmptyState, PageHeader } from "../../components/ui/feedback";
import { PersonBadges, PersonLink, PrivacyBadge } from "../../components/person/badges";
import { Badge } from "../../components/ui/Badge";

const COUNT_LIMIT = 200;

/** People count per status, capped: the API has no count endpoint, so we show "200+" beyond one page. */
function usePeopleCount(treeId: string, status?: string) {
  return useQuery({
    queryKey: ["tree", treeId, "people-count", status ?? ""],
    queryFn: () => api.get<Page<PersonSummary>>(`/trees/${treeId}/people`, { status, limit: COUNT_LIMIT }),
    select: (p) => (p.next_cursor ? `${COUNT_LIMIT}+` : String(p.items.length)),
  });
}

export function DashboardPage() {
  const { t } = useTranslation();
  const { tree, treeId, can } = useTreeCtx();
  const all = usePeopleCount(treeId);
  const living = usePeopleCount(treeId, "living");
  const deceased = usePeopleCount(treeId, "deceased");
  const branches = useBranches(treeId);
  const households = useHouseholds(treeId);
  const places = usePlaces(treeId, "");
  const sources = useSources(treeId, "");
  const recentIds = recentPeople(treeId);
  const recent = useQueries({
    queries: recentIds.map((id) => ({
      queryKey: ["tree", treeId, "person", id],
      queryFn: () => api.get<PersonOut>(`/trees/${treeId}/people/${id}`),
      retry: false,
    })),
  });
  const recentPeopleList = recent.map((q) => q.data).filter((p): p is PersonOut => !!p);
  const linkedPerson = tree.my_linked_person_id;
  const placesCount = places.data ? `${places.data.items.length}${places.data.next_cursor ? "+" : ""}` : "…";
  const sourcesCount = sources.data ? `${sources.data.pages[0]?.items.length ?? 0}${sources.data.pages[0]?.next_cursor ? "+" : ""}` : "…";

  const stats = [
    { label: t("dashboard.people"), value: all.data ?? "…", icon: Users, to: "people" },
    { label: t("enum.profileStatus.living"), value: living.data ?? "…", icon: Users, to: "people?status=living" },
    { label: t("enum.profileStatus.deceased"), value: deceased.data ?? "…", icon: Users, to: "people?status=deceased" },
    { label: t("nav.branches"), value: branches.data ? String(branches.data.length) : "…", icon: Landmark, to: "branches" },
    { label: t("nav.households"), value: households.data ? String(households.data.length) : "…", icon: UsersRound, to: "households" },
    { label: t("nav.places"), value: placesCount, icon: MapPin, to: "places" },
    { label: t("nav.sources"), value: sourcesCount, icon: BookOpen, to: "sources" },
  ];

  return (
    <div className="space-y-6">
      <PageHeader
        eyebrow={t("dashboard.eyebrow")}
        title={tree.name}
        subtitle={tree.description ?? undefined}
        actions={
          <>
            {can(Perm.PERSON_WRITE) && (
              <ButtonLink to={`/t/${treeId}/people/new`} icon={<UserPlus className="size-4" aria-hidden />}>
                {t("people.add")}
              </ButtonLink>
            )}
            <ButtonLink to={`/t/${treeId}/tree${linkedPerson ? `/${linkedPerson}` : ""}`} variant="secondary" icon={<Network className="size-4" aria-hidden />}>
              {t("nav.treeView")}
            </ButtonLink>
          </>
        }
      />
      <div className="flex flex-wrap items-center gap-2 text-xs text-ink-muted">
        {(tree.my_roles ?? []).map((r) => (
          <Badge key={r} tone="saffron">
            {t(`enum.role.${r}`)}
          </Badge>
        ))}
        <span>
          {t("settings.defaultPrivacy")}: <PrivacyBadge level={tree.default_person_privacy} />
        </span>
        {tree.public_mode === "DECEASED_ONLY" && (
          <Link to={`/p/${tree.slug}`} className="text-kumkum-800 underline">
            {t("dashboard.publicPage")}
          </Link>
        )}
      </div>

      <section aria-labelledby="dash-stats">
        <h2 id="dash-stats" className="sr-only">
          {t("dashboard.stats")}
        </h2>
        <ul className="grid grid-cols-2 gap-3 sm:grid-cols-4 lg:grid-cols-7">
          {stats.map((s) => (
            <li key={s.label}>
              <Link to={`/t/${treeId}/${s.to}`} className="card flex h-full flex-col gap-1 p-3 hover:border-kumkum-200">
                <s.icon className="size-4 text-haldi-700" aria-hidden />
                <span className="font-display text-2xl font-bold">{s.value}</span>
                <span className="text-xs text-ink-muted">{s.label}</span>
              </Link>
            </li>
          ))}
        </ul>
        <p className="mt-2 text-xs text-ink-muted">{t("dashboard.countsNote")}</p>
      </section>

      <div className="grid gap-6 lg:grid-cols-3">
        <section className="card p-5 lg:col-span-2" aria-labelledby="dash-recent">
          <h2 id="dash-recent" className="font-display text-lg font-semibold">
            {t("dashboard.recent")}
          </h2>
          {recentPeopleList.length === 0 ? (
            <EmptyState title={t("dashboard.recentEmpty")}>
              <Link to={`/t/${treeId}/people`} className="text-kumkum-800 underline">
                {t("dashboard.browsePeople")}
              </Link>
            </EmptyState>
          ) : (
            <ul className="mt-3 divide-y divide-stone-100">
              {recentPeopleList.map((p) => (
                <li key={p.id} className="flex flex-wrap items-center justify-between gap-2 py-2">
                  <PersonLink treeId={treeId} person={p} />
                  <PersonBadges person={p} />
                </li>
              ))}
            </ul>
          )}
        </section>
        <section className="card p-5" aria-labelledby="dash-actions">
          <h2 id="dash-actions" className="font-display text-lg font-semibold">
            {t("dashboard.quickActions")}
          </h2>
          <ul className="mt-3 space-y-2 text-sm">
            {can(Perm.PERSON_WRITE) && (
              <li>
                <Link className="flex items-center gap-2 text-kumkum-800 hover:underline" to={`/t/${treeId}/people/new`}>
                  <UserPlus className="size-4" aria-hidden /> {t("people.add")}
                </Link>
              </li>
            )}
            <li>
              <Link className="flex items-center gap-2 text-kumkum-800 hover:underline" to={`/t/${treeId}/relationship`}>
                <Route className="size-4" aria-hidden /> {t("nav.relationship")}
              </Link>
            </li>
            <li>
              <Link className="flex items-center gap-2 text-kumkum-800 hover:underline" to={`/t/${treeId}/joint-family`}>
                <Landmark className="size-4" aria-hidden /> {t("nav.jointFamily")}
              </Link>
            </li>
            {can(Perm.MEMBERS_MANAGE) && (
              <li>
                <Link className="flex items-center gap-2 text-kumkum-800 hover:underline" to={`/t/${treeId}/admin/invitations`}>
                  <UserPlus className="size-4" aria-hidden /> {t("nav.invitations")}
                </Link>
              </li>
            )}
            {linkedPerson && (
              <li>
                <Link className="flex items-center gap-2 text-kumkum-800 hover:underline" to={`/t/${treeId}/people/${linkedPerson}`}>
                  <Users className="size-4" aria-hidden /> {t("dashboard.myProfile")}
                </Link>
              </li>
            )}
          </ul>
        </section>
      </div>
    </div>
  );
}
