import { useTranslation } from "react-i18next";
import { Lock, Plus } from "lucide-react";
import type { PersonSummary, RelationshipType, SexAtBirth } from "../../api/types";
import { lifespan } from "../../lib/dates";

/** Initials for an avatar: first letters of the first two words ("Anand Iyer" → "AI", "आनंद" → "आ"). */
export function initials(name: string): string {
  const words = name.trim().split(/\s+/).filter(Boolean);
  // Array.from keeps a Devanagari letter together with nothing after it; good enough for a badge.
  return words
    .slice(0, 2)
    .map((w) => Array.from(w)[0] ?? "")
    .join("")
    .toUpperCase();
}

const AVATAR_TONE: Record<string, string> = {
  male: "bg-indigo-deep/10 text-indigo-deep",
  female: "bg-kumkum-100 text-kumkum-800",
};

/** A round initials badge, tinted by sex at birth (decorative: the name is always next to it). */
export function PersonAvatar({ name, sex, size = "md" }: { name: string; sex?: SexAtBirth | null; size?: "sm" | "md" | "lg" }) {
  const dims = size === "sm" ? "size-8 text-xs" : size === "lg" ? "size-16 text-xl" : "size-9 text-xs sm:size-11 sm:text-sm";
  return (
    <span aria-hidden className={`grid shrink-0 place-items-center rounded-full font-semibold ${dims} ${AVATAR_TONE[sex ?? ""] ?? "bg-stone-200 text-stone-700"}`}>
      {initials(name)}
    </span>
  );
}

/** Short status line under a name: lifespan, or "Deceased" / "Living" when no dates are known. */
export function lifeLine(p: PersonSummary, t: (k: string, o?: Record<string, unknown>) => string): string {
  const years = lifespan(p, t as never);
  if (years) return years;
  return p.profile_status === "unknown" ? t("treeView.datesUnknown") : t(`enum.profileStatus.${p.profile_status}`);
}

/**
 * One person in the family view. A real button: clicking (or Enter/Space) selects the person and
 * shows them in the side panel. Status is shown by shape as well as colour (solid bar = living,
 * broken = deceased, outline = unknown), as in the generation chart.
 */
export function FamilyCard({
  person,
  focus,
  selected,
  relType,
  onSelect,
}: {
  person: PersonSummary;
  focus?: boolean;
  selected?: boolean;
  relType?: RelationshipType | null;
  onSelect: (id: string) => void;
}) {
  const { t } = useTranslation();
  const nonBio = relType && relType !== "biological_parent" && relType !== "spouse" ? t(`enum.relType.${relType}`) : null;
  const line = lifeLine(person, t);
  return (
    <button
      type="button"
      data-focus={focus || undefined}
      onClick={() => onSelect(person.id)}
      aria-pressed={selected}
      aria-label={[
        person.display_name,
        line,
        person.profile_status !== "unknown" ? t(`enum.profileStatus.${person.profile_status}`) : null,
        nonBio,
        person.is_protected ? t("person.badge.protected") : null,
        focus ? t("treeView.family.focusMark") : null,
      ]
        .filter(Boolean)
        .join(", ")}
      className={`relative flex w-44 items-center sm:w-52 gap-3 rounded-xl border bg-white py-2.5 pr-3 pl-4 text-left shadow-sm transition hover:-translate-y-0.5 hover:shadow-md ${
        focus ? "border-kumkum-700 bg-kumkum-50 ring-1 ring-kumkum-700" : "border-stone-300"
      } ${selected ? "outline-3 outline-offset-2 outline-haldi-500" : ""}`}
    >
      <StatusBar status={person.profile_status} />
      <PersonAvatar name={person.display_name} sex={person.sex_at_birth} />
      <span className="min-w-0">
        <span className="line-clamp-2 text-sm leading-snug font-semibold text-ink">{person.display_name}</span>
        <span className="mt-0.5 flex items-center gap-1 text-xs text-ink-muted">
          {line}
          {person.is_protected && <Lock className="size-3" aria-hidden />}
        </span>
        {nonBio && <span className="mt-0.5 block text-[11px] font-medium text-haldi-700">{nonBio}</span>}
      </span>
    </button>
  );
}

function StatusBar({ status }: { status: PersonSummary["profile_status"] }) {
  if (status === "living") return <span aria-hidden className="absolute top-2 bottom-2 left-0 w-1.5 rounded-r bg-leaf-700" />;
  if (status === "deceased")
    return <span aria-hidden className="absolute top-2 bottom-2 left-0 w-1.5 rounded-r bg-[repeating-linear-gradient(to_bottom,#6b5d4d_0_6px,transparent_6px_10px)]" />;
  return <span aria-hidden className="absolute top-2 bottom-2 left-0.5 w-1 rounded border border-stone-500" />;
}

/** A relative the viewer may not see: shown, never named. */
export function HiddenCard() {
  const { t } = useTranslation();
  return (
    <div className="flex w-44 items-center gap-3 rounded-xl border border-dashed sm:w-52 border-stone-400 bg-stone-50 px-4 py-3 text-sm text-stone-600 italic">
      <Lock className="size-4 shrink-0" aria-hidden />
      {t("person.privatePerson")}
    </div>
  );
}

/** A dashed "+ Add father" style slot where a relative could go. */
export function AddSlot({ label, onClick, compact }: { label: string; onClick: () => void; compact?: boolean }) {
  return (
    <button
      type="button"
      onClick={onClick}
      className={`flex items-center justify-center gap-1.5 border-2 border-dashed border-stone-300 bg-white/70 font-medium whitespace-nowrap text-ink-muted hover:border-kumkum-600 hover:text-kumkum-700 ${
        compact ? "rounded-full px-3 py-1.5 text-xs" : "w-44 rounded-xl px-4 py-4 text-sm sm:w-52"
      }`}
    >
      <Plus className="size-4" aria-hidden />
      {label}
    </button>
  );
}
