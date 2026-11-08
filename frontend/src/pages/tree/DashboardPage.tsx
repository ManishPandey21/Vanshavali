import { useState } from "react";
import { useQueries, useQuery } from "@tanstack/react-query";
import { Link, useNavigate } from "react-router-dom";
import { useTranslation } from "react-i18next";
import { BookOpen, Landmark, MapPin, Maximize2, Network, Route, Sprout, Undo2, UserPlus, Users, UsersRound } from "lucide-react";
import { api } from "../../api/client";
import type { Page, PersonOut, PersonSummary } from "../../api/types";
import { useBranches, useHouseholds } from "../../api/hooks/family";
import { useGraph, usePlaces } from "../../api/hooks/people";
import { useSources } from "../../api/hooks/heritage";
import { useTreeCtx } from "../../lib/tree-context";
import { Perm } from "../../lib/permissions";
import { recentPeople } from "../../lib/recent";
import { useFamilyApex } from "../../lib/apex";
import { ButtonLink } from "../../components/ui/Button";
import { EmptyState, ErrorAlert, Spinner } from "../../components/ui/feedback";
import { PersonPicker } from "../../components/pickers";
import { PrivacyBadge } from "../../components/person/badges";
import { TreeChart } from "../../components/tree/TreeChart";
import { Badge } from "../../components/ui/Badge";

const COUNT_LIMIT = 200;
/** Generations drawn below the elder: a four-generation family fits, a bigger one says "truncated". */
const PANORAMA_DEPTH = 8;

/** People count per status, capped: the API has no count endpoint, so we show "200+" beyond one page. */
function usePeopleCount(treeId: string, status?: string) {
  return useQuery({
    queryKey: ["tree", treeId, "people-count", status ?? ""],
    queryFn: () => api.get<Page<PersonSummary>>(`/trees/${treeId}/people`, { status, limit: COUNT_LIMIT }),
    select: (p) => (p.next_cursor ? `${COUNT_LIMIT}+` : String(p.items.length)),
  });
}

/**
 * The tree's home: the family itself, not a dashboard. The whole line is drawn from the family
 * elder (branch founder or earliest-born person the viewer can see) with the viewer marked "You";
 * counts, recent people and shortcuts sit around it. Everything comes from the ordinary,
 * authorised API, so hidden relatives stay anonymous placeholders here as in the tree viewer.
 */
export function DashboardPage() {
  const { t } = useTranslation();
  const { tree, treeId, can } = useTreeCtx();
  const apex = useFamilyApex(treeId, tree.my_linked_person_id);
  const total = apex.people?.items.length ?? 0;

  return (
    <div className="space-y-5">
      <header className="flex flex-col gap-3 sm:flex-row sm:items-end sm:justify-between">
        <div className="min-w-0">
          <p className="text-xs font-semibold tracking-wider text-kumkum-700 uppercase">{t("dashboard.eyebrow")}</p>
          <h1 className="font-display text-2xl font-bold text-ink sm:text-3xl">{tree.name}</h1>
          {tree.description && <p className="mt-1 text-sm text-ink-muted">{tree.description}</p>}
        </div>
        <div className="flex flex-wrap gap-2">
          {can(Perm.PERSON_WRITE) && (
            <ButtonLink to={`/t/${treeId}/people/new`} icon={<UserPlus className="size-4" aria-hidden />}>
              {t("people.add")}
            </ButtonLink>
          )}
          {can(Perm.MEMBERS_MANAGE) && (
            <ButtonLink to={`/t/${treeId}/admin/invitations`} variant="secondary" icon={<Users className="size-4" aria-hidden />}>
              {t("home.invite")}
            </ButtonLink>
          )}
        </div>
      </header>

      {apex.isLoading ? (
        <Spinner />
      ) : apex.error ? (
        <ErrorAlert error={apex.error} />
      ) : total === 0 || !apex.apexId ? (
        <FirstLeaf canAdd={can(Perm.PERSON_WRITE)} />
      ) : (
        <Panorama apexId={apex.apexId} people={apex.people!.items} />
      )}

      <AtAGlance />
      <ContinueRow />
    </div>
  );
}

/** An empty tree: one invitation to plant the first name, instead of a row of zeros. */
function FirstLeaf({ canAdd }: { canAdd: boolean }) {
  const { t } = useTranslation();
  const { treeId } = useTreeCtx();
  return (
    <section aria-labelledby="home-empty" className="card flex flex-col items-center gap-3 px-6 py-14 text-center">
      <span className="grid size-14 place-items-center rounded-full bg-leaf-50 text-leaf-700">
        <Sprout className="size-7" aria-hidden />
      </span>
      <h2 id="home-empty" className="font-display text-xl font-semibold">
        {t("home.emptyTitle")}
      </h2>
      <p className="max-w-md text-sm text-ink-muted">{t("home.emptyBody")}</p>
      {canAdd && (
        <ButtonLink to={`/t/${treeId}/people/new`} icon={<UserPlus className="size-4" aria-hidden />}>
          {t("home.addFirst")}
        </ButtonLink>
      )}
    </section>
  );
}

function Panorama({ apexId, people }: { apexId: string; people: readonly PersonSummary[] }) {
  const { t } = useTranslation();
  const { tree, treeId } = useTreeCtx();
  const navigate = useNavigate();
  const [chosen, setChosen] = useState<PersonSummary | null>(null);
  const [collapsed, setCollapsed] = useState<Set<string>>(new Set());
  const rootId = chosen?.id ?? apexId;
  const elder = people.find((p) => p.id === apexId);
  const rootName = chosen?.display_name ?? elder?.display_name ?? "";
  const graph = useGraph(treeId, rootId, "descendants", PANORAMA_DEPTH, []);
  const nodes = graph.data?.nodes ?? [];
  const shown = nodes.filter((n) => n.person).length;
  const gens = nodes.length ? Math.max(...nodes.map((n) => n.generation)) - Math.min(...nodes.map((n) => n.generation)) + 1 : 0;
  const toggle = (id: string) =>
    setCollapsed((prev) => {
      const n = new Set(prev);
      if (n.has(id)) n.delete(id);
      else n.add(id);
      return n;
    });

  return (
    <section aria-labelledby="home-panorama" className="card overflow-hidden">
      <div className="flex flex-col gap-3 border-b border-stone-200 bg-parchment-deep/60 px-4 py-3 lg:flex-row lg:items-end lg:justify-between">
        <div className="min-w-0">
          <h2 id="home-panorama" className="font-display text-xl font-semibold">
            {t("home.panoramaTitle", { name: rootName })}
          </h2>
          <p className="text-sm text-ink-muted">
            {graph.data ? (
              <>
                {t("home.generations", { count: gens })} · {t("home.inView", { count: shown })} · {t("home.clickHint")}
              </>
            ) : (
              t("home.clickHint")
            )}
          </p>
        </div>
        <div className="flex flex-wrap items-end gap-2">
          <div className="w-60">
            <PersonPicker
              treeId={treeId}
              label={t("home.startFrom")}
              value={null}
              onChange={(p) => {
                if (!p) return;
                setCollapsed(new Set());
                setChosen(p);
              }}
            />
          </div>
          {chosen && elder && (
            <button
              type="button"
              onClick={() => {
                setCollapsed(new Set());
                setChosen(null);
              }}
              className="inline-flex h-10 items-center gap-1.5 rounded-lg border border-stone-300 bg-white px-3 text-sm font-medium hover:bg-parchment-deep"
            >
              <Undo2 className="size-4" aria-hidden />
              {t("home.backTo", { name: elder.display_name })}
            </button>
          )}
          <Link
            to={`/t/${treeId}/tree/${rootId}?dir=descendants`}
            className="inline-flex h-10 items-center gap-1.5 rounded-lg border border-stone-300 bg-white px-3 text-sm font-medium hover:bg-parchment-deep"
          >
            <Maximize2 className="size-4" aria-hidden />
            {t("home.openFull")}
          </Link>
        </div>
      </div>
      <div className="p-3">
        {graph.isLoading && <Spinner />}
        <ErrorAlert error={graph.error} />
        {graph.data?.truncated && (
          <p role="status" className="mb-2 rounded-lg bg-haldi-100 px-3 py-2 text-sm text-haldi-700">
            {t("treeView.truncated")}
          </p>
        )}
        {graph.data && nodes.length <= 1 && (
          <EmptyState title={t("home.onlyOne", { name: rootName })}>
            <Link to={`/t/${treeId}/people/${rootId}?tab=family`} className="text-kumkum-800 underline">
              {t("home.addRelatives")}
            </Link>
          </EmptyState>
        )}
        {graph.data && nodes.length > 1 && (
          <div aria-busy={graph.isFetching}>
            <TreeChart
              graph={graph.data}
              onOpen={(id) => navigate(`/t/${treeId}/people/${id}`)}
              collapsed={collapsed}
              onToggleCollapse={toggle}
              youId={tree.my_linked_person_id}
              heightClass="h-[58dvh] min-h-[380px]"
              minOpenScale={0.8}
            />
          </div>
        )}
      </div>
    </section>
  );
}

/** The old stat tiles, demoted to one line of links under the family. */
function AtAGlance() {
  const { t } = useTranslation();
  const { tree, treeId } = useTreeCtx();
  const all = usePeopleCount(treeId);
  const living = usePeopleCount(treeId, "living");
  const deceased = usePeopleCount(treeId, "deceased");
  const branches = useBranches(treeId);
  const households = useHouseholds(treeId);
  const places = usePlaces(treeId, "");
  const sources = useSources(treeId, "");
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
    <section aria-labelledby="dash-stats" className="flex flex-col gap-2">
      <h2 id="dash-stats" className="sr-only">
        {t("dashboard.stats")}
      </h2>
      <ul className="flex flex-wrap gap-2">
        {stats.map((s) => (
          <li key={s.label}>
            <Link
              to={`/t/${treeId}/${s.to}`}
              className="inline-flex items-center gap-1.5 rounded-full border border-stone-200 bg-white px-3 py-1.5 text-sm hover:border-kumkum-200"
            >
              <s.icon className="size-3.5 text-haldi-700" aria-hidden />
              <strong className="font-semibold tabular-nums">{s.value}</strong>{" "}
              <span className="text-ink-muted">{s.label}</span>
            </Link>
          </li>
        ))}
      </ul>
      <p className="flex flex-wrap items-center gap-2 text-xs text-ink-muted">
        {(tree.my_roles ?? []).map((r) => (
          <Badge key={r} tone="saffron">
            {t(`enum.role.${r}`)}
          </Badge>
        ))}
        <span>
          {t("settings.defaultPrivacy")}: <PrivacyBadge level={tree.default_person_privacy} />
        </span>
        <span>{t("dashboard.countsNote")}</span>
        {tree.public_mode === "DECEASED_ONLY" && (
          <Link to={`/p/${tree.slug}`} className="text-kumkum-800 underline">
            {t("dashboard.publicPage")}
          </Link>
        )}
      </p>
    </section>
  );
}

/** Recently opened people and the main shortcuts, as one row of chips. */
function ContinueRow() {
  const { t } = useTranslation();
  const { tree, treeId } = useTreeCtx();
  const recentIds = recentPeople(treeId);
  const recent = useQueries({
    queries: recentIds.map((id) => ({
      queryKey: ["tree", treeId, "person", id],
      queryFn: () => api.get<PersonOut>(`/trees/${treeId}/people/${id}`),
      retry: false,
    })),
  });
  const recentList = recent.map((q) => q.data).filter((p): p is PersonOut => !!p);
  const linked = tree.my_linked_person_id;
  const chip = "inline-flex items-center gap-1.5 rounded-full bg-parchment-deep px-3 py-1.5 text-sm text-kumkum-800 hover:bg-kumkum-50";
  return (
    <div className="grid gap-4 lg:grid-cols-2">
      <section aria-labelledby="dash-recent">
        <h2 id="dash-recent" className="mb-2 font-display text-base font-semibold">
          {t("dashboard.recent")}
        </h2>
        {recentList.length === 0 ? (
          <p className="text-sm text-ink-muted">
            {t("dashboard.recentEmpty")}{" "}
            <Link to={`/t/${treeId}/people`} className="text-kumkum-800 underline">
              {t("dashboard.browsePeople")}
            </Link>
          </p>
        ) : (
          <ul className="flex flex-wrap gap-2">
            {recentList.map((p) => (
              <li key={p.id}>
                <Link to={`/t/${treeId}/people/${p.id}`} className={chip}>
                  {p.display_name}
                </Link>
              </li>
            ))}
          </ul>
        )}
      </section>
      <section aria-labelledby="dash-actions">
        <h2 id="dash-actions" className="mb-2 font-display text-base font-semibold">
          {t("dashboard.quickActions")}
        </h2>
        <ul className="flex flex-wrap gap-2">
          {linked && (
            <li>
              <Link className={chip} to={`/t/${treeId}/people/${linked}`}>
                <Users className="size-4" aria-hidden /> {t("dashboard.myProfile")}
              </Link>
            </li>
          )}
          <li>
            <Link className={chip} to={`/t/${treeId}/relationship`}>
              <Route className="size-4" aria-hidden /> {t("nav.relationship")}
            </Link>
          </li>
          <li>
            <Link className={chip} to={`/t/${treeId}/tree${linked ? `/${linked}` : ""}`}>
              <Network className="size-4" aria-hidden /> {t("nav.treeView")}
            </Link>
          </li>
          <li>
            <Link className={chip} to={`/t/${treeId}/joint-family`}>
              <Landmark className="size-4" aria-hidden /> {t("nav.jointFamily")}
            </Link>
          </li>
        </ul>
      </section>
    </div>
  );
}
