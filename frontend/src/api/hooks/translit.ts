import { useQuery } from "@tanstack/react-query";
import { api } from "../client";
import type { TransliterateOut } from "../types";

export type TranslitScript = "Deva" | "Latn";

/**
 * Spelling suggestions for a name in the other script (ADR-0025). The engine is deterministic, so
 * answers are cached for the session; errors (offline, rate limit) simply mean no suggestion.
 */
export function useTransliteration(text: string, target: TranslitScript | null) {
  const t = text.trim();
  return useQuery({
    queryKey: ["transliterate", target, t],
    queryFn: () => api.post<TransliterateOut>("/transliterate", { text: t, target_script: target }),
    enabled: !!target && t.length >= 2 && t.length <= 200,
    staleTime: Infinity,
    gcTime: 30 * 60_000,
    retry: false,
  });
}
