/**
 * The family a signed-out visitor sketches on the landing page ("plant your tree"), carried into
 * onboarding after they create an account. It lives only in this browser tab's sessionStorage —
 * nothing is sent to the server until the user confirms the family-data statement in onboarding
 * (ADR-0011) — and it is erased once onboarding saves it, when the tab closes, or on "Clear".
 */

export interface TreeDraft {
  self: string;
  father: string;
  mother: string;
  grandfather: string;
}

export const EMPTY_DRAFT: TreeDraft = { self: "", father: "", mother: "", grandfather: "" };

const KEY = "vsh.treeDraft";
const MAX = 120;

function clean(v: unknown): string {
  return typeof v === "string" ? v.slice(0, MAX) : "";
}

export function hasDraft(d: TreeDraft | null): d is TreeDraft {
  return !!d && Object.values(d).some((v) => v.trim() !== "");
}

export function loadDraft(): TreeDraft | null {
  try {
    const raw = window.sessionStorage.getItem(KEY);
    if (!raw) return null;
    const v = JSON.parse(raw) as Record<string, unknown>;
    const d = { self: clean(v.self), father: clean(v.father), mother: clean(v.mother), grandfather: clean(v.grandfather) };
    return hasDraft(d) ? d : null;
  } catch {
    return null;
  }
}

export function saveDraft(d: TreeDraft): void {
  try {
    if (hasDraft(d)) window.sessionStorage.setItem(KEY, JSON.stringify(d));
    else window.sessionStorage.removeItem(KEY);
  } catch {
    /* storage unavailable (private mode, blocked): the draft simply isn't carried over */
  }
}

export function clearDraft(): void {
  try {
    window.sessionStorage.removeItem(KEY);
  } catch {
    /* ignore */
  }
}

/** "Aarav Kumar Sharma" → { given: "Aarav Kumar", surname: "Sharma" }. */
export function splitFullName(full: string | undefined): { given: string; surname: string } {
  const parts = (full ?? "").trim().split(/\s+/).filter(Boolean);
  if (parts.length < 2) return { given: parts[0] ?? "", surname: "" };
  return { given: parts.slice(0, -1).join(" "), surname: parts[parts.length - 1] ?? "" };
}
