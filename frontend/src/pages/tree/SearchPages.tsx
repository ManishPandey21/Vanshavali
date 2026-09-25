import { useId, useState } from "react";
import { Link, useSearchParams } from "react-router-dom";
import { useTranslation } from "react-i18next";
import { Copy, Search } from "lucide-react";
import { useDuplicates, useSearch } from "../../api/hooks/heritage";
import type { SearchHit } from "../../api/types";
import { useTreeCtx } from "../../lib/tree-context";
import { useDebounced } from "../../lib/useDebounced";
import { EmptyState, ErrorAlert, LiveRegion, PageHeader, Spinner } from "../../components/ui/feedback";
import { PersonBadges, PersonLink } from "../../components/person/badges";
import { Badge } from "../../components/ui/Badge";

const KINDS = ["person", "place", "branch", "household", "document", "property"] as const;

function hitHref(treeId: string, h: SearchHit): string | null {
  switch (h.kind) {
    case "person":
      return `/t/${treeId}/people/${h.id}`;
    case "branch":
      return `/t/${treeId}/branches/${h.id}`;
    case "household":
      return `/t/${treeId}/households?open=${h.id}`;
    case "place":
      return `/t/${treeId}/places`;
    default:
      return null; // documents / property screens are not part of this SPA release
  }
}

export function SearchPage() {
  const { t } = useTranslation();
  const { treeId } = useTreeCtx();
  const [params, setParams] = useSearchParams();
  const q = params.get("q") ?? "";
  const [kinds, setKinds] = useState<string[]>([]);
  const debounced = useDebounced(q.trim(), 300);
  const search = useSearch(treeId, debounced, kinds.length ? kinds : undefined);
  const inputId = useId();
  const hits = search.data?.hits ?? [];
  return (
    <div>
      <PageHeader title={t("search.title")} subtitle={t("search.subtitle")} />
      <div className="relative mb-3 max-w-2xl">
        <label htmlFor={inputId} className="sr-only">
          {t("search.label")}
        </label>
        <Search className="pointer-events-none absolute left-3 top-3 size-4 text-ink-muted" aria-hidden />
        <input
          id={inputId}
          type="search"
          className="input py-2.5 pl-9 text-base"
          placeholder={t("search.placeholder")}
          value={q}
          onChange={(e) => setParams(e.target.value ? { q: e.target.value } : {}, { replace: true })}
        />
      </div>
      <div role="group" aria-label={t("search.kinds")} className="mb-4 flex flex-wrap gap-1">
        {KINDS.map((k) => (
          <button
            key={k}
            type="button"
            aria-pressed={kinds.includes(k)}
            onClick={() => setKinds(kinds.includes(k) ? kinds.filter((x) => x !== k) : [...kinds, k])}
            className={`rounded-full border px-3 py-1 text-xs ${kinds.includes(k) ? "border-kumkum-700 bg-kumkum-700 text-white" : "border-stone-300 bg-white"}`}
          >
            {t(`enum.searchKind.${k}`)}
          </button>
        ))}
      </div>
      {search.isFetching && <Spinner label={t("people.searching")} />}
      <ErrorAlert error={search.error} />
      <LiveRegion message={search.data ? t("people.resultCount", { count: hits.length }) : ""} />
      {!debounced && <p className="text-sm text-ink-muted">{t("search.hint")}</p>}
      {search.data && hits.length === 0 && <EmptyState title={t("people.noResults", { q: debounced })}>{t("people.noResultsHint")}</EmptyState>}
      <ul className="card divide-y divide-stone-100">
        {hits.map((h) => {
          const href = hitHref(treeId, h);
          return (
            <li key={`${h.kind}-${h.id}`} className="flex flex-col gap-1 px-4 py-3 sm:flex-row sm:items-center sm:justify-between">
              <div className="min-w-0">
                <div className="flex flex-wrap items-center gap-2">
                  <Badge tone="stone">{t(`enum.searchKind.${h.kind}`, { defaultValue: h.kind })}</Badge>
                  {h.person ? (
                    <PersonLink treeId={treeId} person={h.person} />
                  ) : href ? (
                    <Link to={href} className="font-medium text-kumkum-800 hover:underline">
                      {h.title}
                    </Link>
                  ) : (
                    <span className="font-medium">{h.title}</span>
                  )}
                  {!h.person && h.subtitle && <span className="text-xs text-ink-muted">{h.subtitle}</span>}
                </div>
                <p className="text-xs text-ink-muted">
                  <span className="font-medium">{t("search.matchReason")}:</span> {h.match_reason}{" "}
                  <span className="text-stone-500">({t(`enum.matchTier.${h.match_tier}`, { defaultValue: h.match_tier })})</span>
                </p>
              </div>
              {h.person && <PersonBadges person={h.person} />}
            </li>
          );
        })}
      </ul>
    </div>
  );
}

export function DuplicatesPage() {
  const { t } = useTranslation();
  const { treeId } = useTreeCtx();
  const [minScore, setMinScore] = useState(0.55);
  const dups = useDuplicates(treeId, minScore);
  const sliderId = useId();
  return (
    <div>
      <PageHeader title={t("duplicates.title")} subtitle={t("duplicates.subtitle")} />
      <p className="mb-4 rounded-lg bg-parchment-deep p-3 text-sm">{t("duplicates.suggestionsOnly")}</p>
      <div className="mb-4 flex max-w-sm flex-col gap-1">
        <label htmlFor={sliderId} className="label">
          {t("duplicates.minScore", { score: Math.round(minScore * 100) })}
        </label>
        <input id={sliderId} type="range" min={0.3} max={0.95} step={0.05} value={minScore} onChange={(e) => setMinScore(Number(e.target.value))} className="accent-kumkum-700" />
      </div>
      {dups.isLoading && <Spinner />}
      <ErrorAlert error={dups.error} />
      {dups.data?.length === 0 && <EmptyState icon={<Copy className="size-10" aria-hidden />} title={t("duplicates.none")} />}
      <ul className="space-y-3">
        {dups.data?.map((d) => (
          <li key={`${d.person_a.id}-${d.person_b.id}`} className="card p-4">
            <div className="flex flex-wrap items-center justify-between gap-2">
              <Badge tone={d.outcome === "probable" ? "red" : "saffron"}>{t(`enum.dupOutcome.${d.outcome}`, { defaultValue: d.outcome })}</Badge>
              <span className="text-sm font-semibold">{t("duplicates.score", { score: Math.round(d.score * 100) })}</span>
            </div>
            <div className="mt-2 grid gap-2 sm:grid-cols-2">
              {[d.person_a, d.person_b].map((p) => (
                <div key={p.id} className="rounded-lg bg-parchment p-3">
                  <PersonLink treeId={treeId} person={p} />
                  <div className="mt-1">
                    <PersonBadges person={p} />
                  </div>
                </div>
              ))}
            </div>
            <ul className="mt-2 list-inside list-disc text-xs text-ink-muted">
              {d.reasons.map((r) => (
                <li key={r}>{r}</li>
              ))}
            </ul>
            <Link to={`/t/${treeId}/relationship?from=${d.person_a.id}&to=${d.person_b.id}`} className="mt-2 inline-block text-xs text-kumkum-800 underline">
              {t("duplicates.compare")}
            </Link>
          </li>
        ))}
      </ul>
    </div>
  );
}
