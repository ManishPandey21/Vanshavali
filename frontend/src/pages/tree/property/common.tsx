import { useTranslation } from "react-i18next";
import { Scale } from "lucide-react";
import { Link } from "react-router-dom";
import type { HolderOut, InterestOut, PropertyClassification, PropertyEventType, PropertyType, InterestType, InterestStatus, AreaUnit } from "../../../api/types";
import { useTreeCtx } from "../../../lib/tree-context";
import { PrivatePersonPlaceholder } from "../../../components/person/badges";
import { Badge } from "../../../components/ui/Badge";

export const PROPERTY_TYPES: PropertyType[] = ["agricultural_land", "residential_land", "house", "ancestral_home", "commercial", "estate", "other"];
export const CLASSIFICATIONS: PropertyClassification[] = ["ancestral", "joint_family", "self_acquired", "unknown"];
export const INTEREST_TYPES: InterestType[] = ["owner", "co_owner", "tenant", "cultivator", "life_interest", "claimant", "beneficiary", "mortgagee", "other"];
export const INTEREST_STATUSES: InterestStatus[] = ["asserted", "documented", "disputed", "unknown"];
export const EVENT_TYPES: PropertyEventType[] = [
  "acquisition",
  "purchase",
  "inheritance",
  "succession",
  "partition",
  "family_settlement",
  "relinquishment",
  "gift",
  "sale",
  "mutation",
  "court_order",
  "mortgage",
  "lease",
  "consolidation",
  "subdivision",
  "merger",
  "boundary_change",
  "dispute",
  "other",
];
export const AREA_UNITS: AreaUnit[] = ["bigha", "biswa", "kanal", "marla", "guntha", "cent", "acre", "hectare", "sq_m", "sq_ft", "ground", "other"];

/** Always shown prominently: property records are genealogical/documentary, never legal title opinions. */
export function LegalNotice({ text }: { text?: string | null }) {
  const { t } = useTranslation();
  return (
    <p role="note" className="flex items-start gap-2 rounded-lg border-2 border-haldi-300 bg-haldi-100 px-3 py-2 text-sm font-semibold text-haldi-700">
      <Scale className="mt-0.5 size-4 shrink-0" aria-hidden />
      {text || t("property.legalNoticeFallback")}
    </p>
  );
}

export function HolderName({ holder }: { holder: HolderOut }) {
  const { t } = useTranslation();
  const { treeId } = useTreeCtx();
  if (holder.hidden) return <PrivatePersonPlaceholder compact />;
  if (holder.type === "person" && holder.person_id)
    return (
      <Link to={`/t/${treeId}/people/${holder.person_id}`} className="font-medium text-kumkum-800 underline-offset-2 hover:underline">
        {holder.display_name ?? holder.person?.display_name ?? t("person.privatePerson")}
      </Link>
    );
  if (holder.type === "family_branch" && holder.branch_id)
    return (
      <Link to={`/t/${treeId}/branches/${holder.branch_id}`} className="font-medium text-kumkum-800 underline-offset-2 hover:underline">
        {holder.display_name ?? holder.name ?? t("enum.holderType.family_branch")}
      </Link>
    );
  return <span className="font-medium">{holder.display_name ?? holder.name ?? t(`enum.holderType.${holder.type}`)}</span>;
}

export function InterestLine({ i }: { i: InterestOut }) {
  const { t } = useTranslation();
  return (
    <span className="flex flex-wrap items-center gap-1.5 text-sm">
      <HolderName holder={i.holder} />
      {i.holder.person?.profile_status === "deceased" && <Badge tone="stone">{t("enum.profileStatus.deceased")}</Badge>}
      <span className="font-mono font-semibold">{i.share}</span>
      <span className="text-xs text-ink-muted">({i.share_percent.toLocaleString(undefined, { maximumFractionDigits: 2 })}%)</span>
      <Badge tone="neutral">{t(`enum.interestType.${i.interest_type}`)}</Badge>
      <Badge tone={i.status === "documented" ? "green" : i.status === "disputed" ? "red" : "stone"}>{t(`enum.interestStatus.${i.status}`)}</Badge>
      {(i.valid_from_display || i.valid_to_display) && (
        <span className="text-xs text-ink-muted">
          {i.valid_from_display ?? "?"} – {i.valid_to_display ?? (i.is_current ? t("property.present") : "?")}
        </span>
      )}
    </span>
  );
}
