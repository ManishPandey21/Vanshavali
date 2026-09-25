import { Link } from "react-router-dom";
import { useTranslation } from "react-i18next";
import { Home } from "lucide-react";
import type { PersonOut } from "../../../api/types";
import { usePersonHouseholds } from "../../../api/hooks/family";
import { useTreeCtx } from "../../../lib/tree-context";
import { DateText } from "../../../components/dates/DateText";
import { EmptyState, ErrorAlert, Spinner } from "../../../components/ui/feedback";
import { Badge } from "../../../components/ui/Badge";

export function HouseholdsTab({ person }: { person: PersonOut }) {
  const { t } = useTranslation();
  const { treeId } = useTreeCtx();
  const hh = usePersonHouseholds(treeId, person.id);
  return (
    <section aria-labelledby="hh-title">
      <h2 id="hh-title" className="mb-3 font-display text-lg font-semibold">
        {t("households.forPerson")}
      </h2>
      {hh.isLoading && <Spinner />}
      <ErrorAlert error={hh.error} />
      {hh.data && hh.data.length === 0 && (
        <EmptyState icon={<Home className="size-8" aria-hidden />} title={t("households.noneForPerson")}>
          <Link to={`/t/${treeId}/households`} className="text-kumkum-800 underline">
            {t("households.manage")}
          </Link>
        </EmptyState>
      )}
      <ul className="grid gap-3 md:grid-cols-2">
        {hh.data?.map((m, i) => (
          <li key={m.household.id + i} className="card p-4">
            <Link to={`/t/${treeId}/households?open=${m.household.id}`} className="font-display font-semibold text-kumkum-800 hover:underline">
              {m.household.name}
            </Link>
            {m.household.house_name && <p className="text-sm text-ink-muted">{m.household.house_name}</p>}
            <div className="mt-2 flex flex-wrap items-center gap-2 text-sm">
              <Badge tone={m.role === "karta" ? "saffron" : "neutral"}>{t(`enum.householdRole.${m.role}`)}</Badge>
              {m.end_date ? <Badge tone="stone">{t("households.former")}</Badge> : <Badge tone="green">{t("households.current")}</Badge>}
            </div>
            <p className="mt-1 text-xs text-ink-muted">
              {m.start_date && (
                <>
                  {t("households.from")} <DateText date={m.start_date} showOriginal={false} />{" "}
                </>
              )}
              {m.end_date && (
                <>
                  {t("households.until")} <DateText date={m.end_date} showOriginal={false} />
                </>
              )}
            </p>
          </li>
        ))}
      </ul>
    </section>
  );
}
