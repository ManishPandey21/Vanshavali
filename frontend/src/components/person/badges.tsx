import { useTranslation } from "react-i18next";
import { Baby, CircleDashed, EyeOff, Flower2, HeartPulse, HelpCircle, Lock, ShieldCheck, UserX } from "lucide-react";
import { Link } from "react-router-dom";
import type { EvidenceStatus, GenealogicalDate, PersonSummary, PrivacyLevel, RelationshipType } from "../../api/types";
import { Badge, type Tone } from "../ui/Badge";
import { dateQualifier } from "../../lib/dates";
import { lifespan } from "../../lib/dates";
import { dirOfText, langOfText } from "../../lib/names";

export function StatusBadge({ status }: { status: PersonSummary["profile_status"] }) {
  const { t } = useTranslation();
  if (status === "living")
    return (
      <Badge tone="green" icon={<HeartPulse className="size-3" aria-hidden />}>
        {t("enum.profileStatus.living")}
      </Badge>
    );
  if (status === "deceased")
    return (
      <Badge tone="stone" icon={<Flower2 className="size-3" aria-hidden />}>
        {t("enum.profileStatus.deceased")}
      </Badge>
    );
  return (
    <Badge tone="neutral" icon={<HelpCircle className="size-3" aria-hidden />}>
      {t("enum.profileStatus.unknown")}
    </Badge>
  );
}

export function PersonBadges({ person, showPrivacy = false }: { person: PersonSummary; showPrivacy?: boolean }) {
  const { t } = useTranslation();
  return (
    <span className="inline-flex flex-wrap items-center gap-1">
      <StatusBadge status={person.profile_status} />
      {person.is_minor && (
        <Badge tone="violet" icon={<Baby className="size-3" aria-hidden />}>
          {t("person.badge.minor")}
        </Badge>
      )}
      {person.is_protected && (
        <Badge tone="blue" icon={<ShieldCheck className="size-3" aria-hidden />} title={t("person.badge.protectedHint")}>
          {t("person.badge.protected")}
        </Badge>
      )}
      {person.is_provisional && person.provisional_state === "needs_details" && (
        <Badge tone="saffron" icon={<CircleDashed className="size-3" aria-hidden />} title={t("person.badge.provisionalHint")}>
          {t("person.badge.provisional")}
        </Badge>
      )}
      {person.is_provisional && person.provisional_state === "unverified" && (
        <Badge tone="saffron" icon={<CircleDashed className="size-3" aria-hidden />} title={t("person.badge.unverifiedHint")}>
          {t("person.badge.unverified")}
        </Badge>
      )}
      {showPrivacy && person.privacy_level && <PrivacyBadge level={person.privacy_level} />}
    </span>
  );
}

const privacyTone: Record<PrivacyLevel, Tone> = {
  PRIVATE_SELF: "red",
  PRIVATE_TREE_ADMINS: "red",
  FAMILY_BRANCH: "saffron",
  TREE_MEMBERS: "neutral",
  INVITED_RESEARCHER: "blue",
  PUBLIC_DECEASED_ONLY: "green",
  CUSTOM: "violet",
  ONLY_ME: "red",
  SELECTED_MEMBERS: "violet",
};

export function PrivacyBadge({ level }: { level: PrivacyLevel }) {
  const { t } = useTranslation();
  return (
    <Badge tone={privacyTone[level]} icon={<Lock className="size-3" aria-hidden />} title={t(`enum.privacyHint.${level}`)}>
      <span className="sr-only">{t("privacy.label")}: </span>
      {t(`enum.privacy.${level}`)}
    </Badge>
  );
}

const evidenceTone: Record<EvidenceStatus, Tone> = {
  USER_ASSERTION: "neutral",
  FAMILY_RECOLLECTION: "saffron",
  SOURCED: "blue",
  CORROBORATED: "green",
  DISPUTED: "red",
  SUPERSEDED: "stone",
  DISPROVEN: "red",
};

export function EvidenceBadge({ status }: { status: EvidenceStatus | null | undefined }) {
  const { t } = useTranslation();
  if (!status) return null;
  return (
    <Badge tone={evidenceTone[status]} title={t("evidence.label")}>
      <span className="sr-only">{t("evidence.label")}: </span>
      {t(`enum.evidence.${status}`)}
    </Badge>
  );
}

const relTone: Partial<Record<RelationshipType, Tone>> = {
  biological_parent: "neutral",
  adoptive_parent: "blue",
  step_parent: "violet",
  foster_parent: "saffron",
  guardian: "green",
  divorced_spouse: "stone",
  separated_spouse: "stone",
};

export function RelTypeBadge({ type, subtype }: { type: RelationshipType | null | undefined; subtype?: string | null }) {
  const { t } = useTranslation();
  if (!type) return null;
  return (
    <Badge tone={relTone[type] ?? "neutral"}>
      {t(`enum.relType.${type}`)}
      {subtype ? ` · ${subtype}` : ""}
    </Badge>
  );
}

/** Precision qualifier ("circa", "year only"…) so an approximate date is never mistaken for exact. */
export function DateQualifierBadge({ date }: { date: GenealogicalDate | Record<string, unknown> | null | undefined }) {
  const { t } = useTranslation();
  const q = dateQualifier(date);
  const redacted = !!(date as GenealogicalDate | null)?.redacted;
  return (
    <>
      {q && !(redacted && q === "year_only") && <Badge tone="saffron">{t(`enum.datePrecision.${q}`)}</Badge>}
      {redacted && (
        <Badge tone="blue" icon={<EyeOff className="size-3" aria-hidden />}>
          {t("privacy.yearOnly")}
        </Badge>
      )}
    </>
  );
}

/** Stand-in for a relative the viewer may not see. Never links, never shows a name. */
export function PrivatePersonPlaceholder({ compact }: { compact?: boolean }) {
  const { t } = useTranslation();
  return (
    <span className={`inline-flex items-center gap-2 text-ink-muted ${compact ? "text-xs" : "text-sm"}`}>
      <UserX className="size-4" aria-hidden />
      <span className="italic">{t("person.privatePerson")}</span>
    </span>
  );
}

export function RedactionNotice({ label }: { label?: string }) {
  const { t } = useTranslation();
  return (
    <span className="inline-flex items-center gap-1 text-xs italic text-ink-muted">
      <EyeOff className="size-3.5" aria-hidden />
      {label ?? t("privacy.hiddenBySettings")}
    </span>
  );
}

export function PersonLink({ treeId, person, className = "" }: { treeId: string; person: PersonSummary; className?: string }) {
  const { t } = useTranslation();
  const years = lifespan(person, t);
  return (
    <Link to={`/t/${treeId}/people/${person.id}`} className={`font-medium text-kumkum-800 underline-offset-2 hover:underline ${className}`}>
      <span lang={langOfText(person.display_name)} dir={dirOfText(person.display_name)}>
        {person.display_name}
      </span>
      {years && (
        <span className="ml-1 text-xs font-normal text-ink-muted">
          <span className="sr-only">{t("person.lifespan")} </span>({years})
        </span>
      )}
    </Link>
  );
}
