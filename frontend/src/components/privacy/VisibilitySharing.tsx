import { useId, useMemo, useState } from "react";
import { useTranslation } from "react-i18next";
import { Search, Users } from "lucide-react";
import type { BranchOut, MemberOut, RecordPrivacyLevel, SharingMemberIn, SharingMemberOut, SharingOut } from "../../api/types";
import { Checkbox, Select } from "../ui/form";
import { Badge } from "../ui/Badge";
import { RecordPrivacyBadge } from "../person/badges";

/** The four audiences a member can choose (ADR-0027 §1). Public records are not offered in v1. */
export const RECORD_AUDIENCES: RecordPrivacyLevel[] = ["ONLY_ME", "SELECTED_MEMBERS", "FAMILY_BRANCH", "TREE_MEMBERS"];

// higher = more restricted; mirrors the server's RECORD_RANK
const RANK: Record<RecordPrivacyLevel, number> = {
  PUBLIC_DECEASED_ONLY: 0,
  INVITED_RESEARCHER: 1,
  TREE_MEMBERS: 2,
  FAMILY_BRANCH: 3,
  PRIVATE_TREE_ADMINS: 4,
  CUSTOM: 4,
  SELECTED_MEMBERS: 4,
  PRIVATE_SELF: 5,
  ONLY_ME: 6,
};

export interface SharingDraft {
  privacy_level: RecordPrivacyLevel;
  audience_branch_id: string | null;
  allow_download: boolean;
  members: SharingMemberIn[];
}

export function draftFrom(s: SharingOut): SharingDraft {
  return {
    privacy_level: s.privacy_level,
    audience_branch_id: s.audience_branch_id ?? null,
    allow_download: s.allow_download,
    members: (s.members ?? []).map((m) => ({ membership_id: m.membership_id, can_download: m.can_download })),
  };
}

/** Problems that stop a draft from being saved (shown inline; the server re-checks everything). */
export function draftProblem(d: SharingDraft): "branch" | "members" | null {
  if (d.privacy_level === "FAMILY_BRANCH" && !d.audience_branch_id) return "branch";
  if (d.privacy_level === "SELECTED_MEMBERS" && d.members.length === 0) return "members";
  return null;
}

/**
 * Visibility & Sharing (ADR-0027 §9): one control for every shareable record.
 *
 * Controlled and presentational. The parent loads members and branches and, where the record exists,
 * asks the server who would have access (`audience`); this component never decides access itself.
 */
export function VisibilitySharing({
  value,
  onChange,
  members,
  branches,
  ownMembershipId,
  ceiling,
  audience,
  canWiden = true,
  disabled = false,
  showProblems = false,
}: {
  value: SharingDraft;
  onChange: (d: SharingDraft) => void;
  members: MemberOut[];
  branches: BranchOut[];
  ownMembershipId?: string | null;
  ceiling?: SharingOut["ceiling"];
  audience?: SharingMemberOut[];
  canWiden?: boolean;
  disabled?: boolean;
  showProblems?: boolean;
}) {
  const { t } = useTranslation();
  const name = useId();
  const searchId = useId();
  const [q, setQ] = useState("");
  const others = useMemo(() => members.filter((m) => m.id !== ownMembershipId), [members, ownMembershipId]);
  const matches = useMemo(() => {
    const needle = q.trim().toLocaleLowerCase();
    return needle ? others.filter((m) => m.display_name.toLocaleLowerCase().includes(needle)) : others;
  }, [others, q]);
  const chosen = new Map(value.members.map((m) => [m.membership_id, m.can_download]));
  const problem = showProblems ? draftProblem(value) : null;

  const tooOpen = (level: RecordPrivacyLevel) => !!ceiling && RANK[level] < RANK[ceiling.max_level];
  const setMember = (id: string, view: boolean, download: boolean) => {
    const rest = value.members.filter((m) => m.membership_id !== id);
    onChange({ ...value, members: view ? [...rest, { membership_id: id, can_download: download }] : rest });
  };

  return (
    <div className="space-y-3">
      <fieldset disabled={disabled} className="space-y-1.5">
        <legend className="label">{t("sharing.legend")}</legend>
        {RECORD_AUDIENCES.map((level) => {
          const blocked = tooOpen(level);
          return (
            <label key={level} className={`flex items-start gap-2 rounded-lg border p-2 text-sm ${value.privacy_level === level ? "border-kumkum-600 bg-kumkum-50" : "border-stone-200"} ${blocked ? "opacity-60" : ""}`}>
              <input
                type="radio"
                name={name}
                className="mt-1"
                value={level}
                checked={value.privacy_level === level}
                disabled={blocked}
                aria-labelledby={`${name}-${level}-title`}
                aria-describedby={`${name}-${level}-hint`}
                onChange={() => onChange({ ...value, privacy_level: level, members: level === "ONLY_ME" ? [] : value.members })}
              />
              <span>
                <span id={`${name}-${level}-title`} className="font-medium">
                  {t(`enum.recordPrivacy.${level}`)}
                </span>
                <span id={`${name}-${level}-hint`} className="block text-xs text-ink-muted">
                  {blocked && ceiling ? t("sharing.ceiling", { level: t(`enum.recordPrivacy.${ceiling.max_level}`) }) : t(`enum.recordPrivacyHint.${level}`)}
                </span>
              </span>
            </label>
          );
        })}
        {!RECORD_AUDIENCES.includes(value.privacy_level) && (
          <p className="text-xs text-ink-muted">
            <RecordPrivacyBadge level={value.privacy_level} />
          </p>
        )}
      </fieldset>

      {value.privacy_level === "FAMILY_BRANCH" && (
        <div>
          <label htmlFor={`${name}-branch`} className="label">
            {t("sharing.branch")}
          </label>
          <Select
            id={`${name}-branch`}
            value={value.audience_branch_id ?? ""}
            disabled={disabled}
            aria-invalid={problem === "branch" ? true : undefined}
            onChange={(e) => onChange({ ...value, audience_branch_id: e.target.value || null })}
          >
            <option value="">{t("sharing.chooseBranch")}</option>
            {branches
              .filter((b) => !ceiling?.branch_ids?.length || ceiling.branch_ids.includes(b.id))
              .map((b) => (
                <option key={b.id} value={b.id}>
                  {b.name}
                </option>
              ))}
          </Select>
          {problem === "branch" && <p className="field-error">{t("sharing.chooseBranch")}</p>}
        </div>
      )}

      {value.privacy_level === "SELECTED_MEMBERS" && (
        <div className="space-y-2">
          <label htmlFor={searchId} className="label">
            {t("sharing.searchMembers")}
          </label>
          <div className="relative">
            <Search className="pointer-events-none absolute left-2 top-2.5 size-4 text-ink-muted" aria-hidden />
            <input id={searchId} type="search" className="input pl-8" value={q} onChange={(e) => setQ(e.target.value)} disabled={disabled} />
          </div>
          <ul className="max-h-64 divide-y divide-stone-100 overflow-y-auto rounded-lg border border-stone-200" aria-label={t("sharing.membersList")}>
            {matches.map((m) => {
              const view = chosen.has(m.id);
              const dl = chosen.get(m.id) ?? false;
              return (
                <li key={m.id} className="flex flex-wrap items-center justify-between gap-2 px-2 py-1.5 text-sm">
                  <span className="min-w-0 font-medium">{m.display_name}</span>
                  <span className="flex gap-3">
                    <Checkbox label={t("sharing.canView")} checked={view} disabled={disabled || (!view && !canWiden)} onChange={(v) => setMember(m.id, v, v && dl)} />
                    <Checkbox label={t("sharing.canDownload")} checked={dl} disabled={disabled || (!dl && !canWiden)} onChange={(v) => setMember(m.id, view || v, v)} />
                  </span>
                </li>
              );
            })}
            {matches.length === 0 && <li className="px-2 py-2 text-sm text-ink-muted">{t("sharing.noMatches", { q })}</li>}
          </ul>
          {problem === "members" && <p className="field-error">{t("sharing.membersRequired")}</p>}
        </div>
      )}

      {(value.privacy_level === "FAMILY_BRANCH" || value.privacy_level === "TREE_MEMBERS") && (
        <Checkbox
          label={t("sharing.allowDownload")}
          hint={t("sharing.downloadHint")}
          checked={value.allow_download}
          disabled={disabled || (!value.allow_download && !canWiden)}
          onChange={(v) => onChange({ ...value, allow_download: v })}
        />
      )}

      {audience && (
        <section aria-labelledby={`${name}-who`} className="rounded-lg bg-parchment-deep p-3">
          <h3 id={`${name}-who`} className="flex items-center gap-2 text-sm font-semibold">
            <Users className="size-4" aria-hidden /> {t("sharing.whoHasAccess")}
          </h3>
          <p className="text-xs text-ink-muted" aria-live="polite">
            {t("sharing.whoHasAccessCount", { count: audience.length })}
          </p>
          <ul className="mt-1 flex flex-wrap gap-1.5" data-testid="sharing-audience">
            {audience.map((a) => (
              <li key={a.membership_id}>
                <Badge tone={a.access === "owner" ? "violet" : a.access === "role" ? "saffron" : "neutral"}>
                  {a.display_name} · {t(`sharing.access.${a.access}`)}
                  {a.can_download ? " ⤓" : ""}
                </Badge>
              </li>
            ))}
          </ul>
        </section>
      )}
    </div>
  );
}
