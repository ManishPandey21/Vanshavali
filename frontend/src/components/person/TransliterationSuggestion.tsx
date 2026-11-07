import { useMemo, useState } from "react";
import { useTranslation } from "react-i18next";
import { Languages, Plus, X } from "lucide-react";
import { useTransliteration, type TranslitScript } from "../../api/hooks/translit";
import type { TransliterationCandidate } from "../../api/types";
import { useDebounced } from "../../lib/useDebounced";
import type { NameDraft } from "./NameFields";

/** Hindi in Devanagari ⇄ Latin only (ADR-0025 §3): any other script gets no suggestion. */
function targetFor(script: string | null | undefined): TranslitScript | null {
  if (script === "Deva") return "Latn";
  if (!script || script === "Latn") return "Deva";
  return null;
}

interface Combined {
  given: string | null;
  surname: string | null;
  method: TransliterationCandidate["method"];
}

/** Combine per-part candidates index by index (given[k] + surname[k]), at most three, distinct. */
function combine(given: TransliterationCandidate[], surname: TransliterationCandidate[], hasGiven: boolean, hasSurname: boolean): Combined[] {
  const n = Math.max(hasGiven ? given.length : 0, hasSurname ? surname.length : 0);
  const out: Combined[] = [];
  for (let k = 0; k < Math.min(n, 3); k++) {
    const g = hasGiven ? given[Math.min(k, given.length - 1)] : undefined;
    const s = hasSurname ? surname[Math.min(k, surname.length - 1)] : undefined;
    if ((hasGiven && !g) || (hasSurname && !s)) return out;
    const c: Combined = { given: g?.text ?? null, surname: s?.text ?? null, method: g?.method === "rules" || s?.method === "rules" ? "rules" : "lexicon" };
    if (!out.some((o) => o.given === c.given && o.surname === c.surname)) out.push(c);
  }
  return out;
}

/**
 * "In Devanagari: सुनीता शर्मा — Add as another name" (ADR-0025 §7). A suggestion is never applied
 * on its own: the typed name stays as typed, and accepting adds a separate transliteration name
 * that the server records as calculated and confirmed by this user.
 */
export function TransliterationSuggestion({ name, onAdd }: { name: NameDraft; onAdd: (n: NameDraft) => void }) {
  const { t } = useTranslation();
  const target = targetFor(name.script);
  const given = useDebounced((name.given_name ?? "").trim(), 400);
  const surname = useDebounced((name.surname ?? "").trim(), 400);
  const g = useTransliteration(given, target);
  const s = useTransliteration(surname, target);
  const [dismissed, setDismissed] = useState<string | null>(null);
  const [added, setAdded] = useState<string[]>([]);

  const key = `${target}|${given}|${surname}`;
  const hasGiven = given.length >= 2;
  const hasSurname = surname.length >= 2;
  const candidates = useMemo(
    () => combine(g.data?.candidates ?? [], s.data?.candidates ?? [], hasGiven, hasSurname),
    [g.data, s.data, hasGiven, hasSurname],
  );
  if (!target || (!hasGiven && !hasSurname) || dismissed === key) return null;
  const visible = candidates.filter((c) => !added.includes(`${c.given}|${c.surname}`));
  if (visible.length === 0) return null;

  const lang = target === "Deva" ? "hi" : "en";
  const label = (c: Combined) => [c.given, c.surname].filter(Boolean).join(" ");
  const add = (c: Combined) => {
    onAdd({
      type: "transliteration",
      given_name: c.given,
      surname: c.surname,
      language: lang,
      script: target,
      is_preferred: false,
      evidence_status: "USER_ASSERTION",
      suggestion: { method: c.method },
    });
    setAdded((a) => [...a, `${c.given}|${c.surname}`]);
  };

  return (
    <div className="mt-3 rounded-md border border-haldi-300 bg-haldi-100/60 px-3 py-2 text-sm" role="status" aria-live="polite">
      <p className="flex items-center gap-1 font-medium">
        <Languages className="size-4" aria-hidden />
        {t(target === "Deva" ? "translit.inDevanagari" : "translit.inLatin")}
      </p>
      <ul className="mt-1 flex flex-wrap gap-2">
        {visible.map((c) => (
          <li key={label(c)} className="flex items-center gap-1">
            <span lang={lang} className="font-display text-base">
              {label(c)}
            </span>
            {c.method === "rules" && <span className="text-xs text-ink-muted">({t("translit.possible")})</span>}
            <button
              type="button"
              onClick={() => add(c)}
              aria-label={`${t("translit.add")}: ${label(c)}`}
              className="ml-1 inline-flex items-center gap-0.5 rounded-full border border-kumkum-700 px-2 py-0.5 text-xs font-medium text-kumkum-800 hover:bg-kumkum-50"
            >
              <Plus className="size-3" aria-hidden />
              {t("translit.add")}
            </button>
          </li>
        ))}
      </ul>
      <div className="mt-1 flex items-center justify-between gap-2">
        <p className="text-xs text-ink-muted">{t("translit.hint")}</p>
        <button type="button" onClick={() => setDismissed(key)} className="inline-flex items-center gap-0.5 text-xs text-ink-muted underline">
          <X className="size-3" aria-hidden />
          {t("translit.dismiss")}
        </button>
      </div>
    </div>
  );
}
