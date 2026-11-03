import { useEffect, useId, useState, type ReactNode } from "react";
import { Link } from "react-router-dom";
import { useTranslation } from "react-i18next";
import { ArrowRight, Lock, Plus, Sprout, X } from "lucide-react";
import { EMPTY_DRAFT, clearDraft, loadDraft, saveDraft, splitFullName, type TreeDraft } from "../../lib/treeDraft";

/**
 * "Plant your tree": the landing page's try-before-you-sign-up builder. A visitor types four
 * names and watches three generations take root, then carries the sketch into sign-up and the
 * onboarding flow, which pre-fills it. The names stay in this tab's sessionStorage only (see
 * lib/treeDraft.ts); nothing reaches the server until the family-data statement is confirmed.
 */

type Role = keyof TreeDraft;
const ROLES: Role[] = ["self", "father", "mother", "grandfather"];
/** The Hindi kinship term shown under each card, whatever the page language. */
const KIN_HI: Record<Role, string> = { self: "स्वयं", father: "पिता", mother: "माता", grandfather: "दादा" };

export function TreePlanter({ signedIn }: { signedIn: boolean }) {
  const { t, i18n } = useTranslation();
  const hindi = i18n.language.startsWith("hi");
  const [draft, setDraft] = useState<TreeDraft>(() => loadDraft() ?? EMPTY_DRAFT);
  const uid = useId();

  useEffect(() => saveDraft(draft), [draft]);

  const surname = splitFullName(draft.self).surname;
  const named = ROLES.filter((r) => draft[r].trim()).length;
  const generations = (draft.self.trim() ? 1 : 0) + (draft.father.trim() || draft.mother.trim() ? 1 : 0) + (draft.grandfather.trim() ? 1 : 0);
  const status = named === 0 ? "empty" : named === ROLES.length ? "complete" : "started";
  const set = (r: Role) => (v: string) => setDraft((d) => ({ ...d, [r]: v }));
  const btnText = hindi ? "text-sm font-semibold" : "text-xs font-bold tracking-[0.16em] uppercase";

  return (
    <div className="grid overflow-hidden rounded-2xl border border-cocoa/10 bg-cream shadow-2xl shadow-cocoa/20 lg:grid-cols-[minmax(0,5fr)_minmax(0,6fr)]">
      {/* ------------------------------------------------ the four names */}
      <form className="p-6 sm:p-8" onSubmit={(e) => e.preventDefault()} aria-labelledby={`${uid}-title`}>
        <p className="inline-flex items-center gap-2 rounded-full bg-leaf-50 px-3 py-1 font-sans text-xs font-semibold text-leaf-700">
          <Sprout className="size-3.5" aria-hidden />
          {t("landing.plant.kicker")}
        </p>
        <h2 id={`${uid}-title`} className="mt-4 font-heritage text-3xl leading-[1.1] font-bold text-balance sm:text-4xl">
          {t("landing.plant.titleA")} <em className="font-normal text-rust italic">{t("landing.plant.titleEm")}</em>
        </h2>
        <p className="mt-3 leading-relaxed text-umber">{t("landing.plant.lead")}</p>

        <div className="mt-6 grid gap-4 font-sans">
          {ROLES.map((r) => (
            <div key={r}>
              <label htmlFor={`${uid}-${r}`} className="flex items-baseline justify-between gap-2 text-sm font-semibold text-cocoa">
                {t(`landing.plant.fields.${r}`)}
                <span className="text-xs font-normal text-umber" lang="hi">
                  {KIN_HI[r]}
                </span>
              </label>
              <input
                id={`${uid}-${r}`}
                value={draft[r]}
                onChange={(e) => set(r)(e.target.value)}
                maxLength={120}
                autoComplete={r === "self" ? "name" : "off"}
                placeholder={
                  r === "self" || !surname
                    ? t(`landing.plant.placeholders.${r}`, { surname: "" }).trim()
                    : t(`landing.plant.placeholders.${r}`, { surname })
                }
                className="mt-1.5 w-full rounded-lg border border-cocoa/20 bg-white px-3.5 py-2.5 text-base text-cocoa placeholder:text-umber/60 focus:border-rust focus:ring-2 focus:ring-rust/25 focus:outline-none"
              />
            </div>
          ))}
        </div>
      </form>

      {/* ------------------------------------------------ the live tree */}
      <div className="flex flex-col border-t border-cocoa/10 bg-white bg-[radial-gradient(circle,rgba(107,90,74,0.12)_1px,transparent_1px)] bg-[length:18px_18px] p-6 sm:p-8 lg:border-t-0 lg:border-l">
        <div className="flex flex-wrap items-baseline justify-between gap-2 font-sans">
          <p className="font-heritage text-xl font-bold text-cocoa">
            {surname ? t("landing.plant.treeTitle", { surname }) : t("landing.plant.treeTitleEmpty")}
          </p>
          <p className="text-xs text-umber tabular-nums">
            {t("landing.plant.named", { n: named, total: ROLES.length })} · {t("landing.plant.generations", { count: generations })}
          </p>
        </div>

        <ol className="mt-6 flex flex-1 flex-col items-center justify-center" aria-label={t("landing.plant.previewLabel")}>
          <Generation>
            <Card kin="grandfather" name={draft.grandfather} />
          </Generation>
          <Stem on={!!draft.grandfather.trim() && !!draft.father.trim()} />
          <Generation>
            <Card kin="father" name={draft.father} />
            <span
              className={`h-1.5 w-6 shrink-0 self-center border-y-2 transition-colors duration-500 sm:w-10 ${draft.father.trim() && draft.mother.trim() ? "border-rust/70" : "border-dashed border-cocoa/20"}`}
              aria-hidden
            />
            <Card kin="mother" name={draft.mother} />
          </Generation>
          <Stem on={!!draft.self.trim() && !!(draft.father.trim() || draft.mother.trim())} />
          <Generation>
            <Card kin="self" name={draft.self} highlight />
          </Generation>
        </ol>

        <p className="mt-6 text-center text-umber italic" aria-live="polite">
          {t(`landing.plant.status.${status}`, { surname: surname || t("landing.plant.yourFamily") })}
        </p>

        <div className="mt-5 flex flex-col items-center gap-3 font-sans">
          <Link
            to={signedIn ? "/welcome" : "/register"}
            className={`inline-flex w-full items-center justify-center gap-2 bg-rust px-7 py-3.5 ${btnText} text-cream shadow-lg shadow-rust/25 transition hover:bg-terracotta sm:w-auto`}
          >
            {signedIn ? t("landing.plant.ctaSignedIn") : t("landing.plant.cta")}
            <ArrowRight className="size-4" aria-hidden />
          </Link>
          <p className="flex max-w-sm items-start gap-1.5 text-center text-xs text-umber">
            <Lock className="mt-0.5 size-3 shrink-0 text-rust" aria-hidden />
            <span>{t("landing.plant.note")}</span>
          </p>
          {named > 0 && (
            <button
              type="button"
              onClick={() => {
                clearDraft();
                setDraft(EMPTY_DRAFT);
              }}
              className="inline-flex items-center gap-1 rounded px-2 py-1 text-xs font-semibold text-umber hover:bg-sand hover:text-cocoa"
            >
              <X className="size-3.5" aria-hidden />
              {t("landing.plant.clear")}
            </button>
          )}
        </div>
      </div>
    </div>
  );
}

function Generation({ children }: { children: ReactNode }) {
  return <li className="flex w-full items-stretch justify-center">{children}</li>;
}

function Stem({ on }: { on: boolean }) {
  return (
    <li aria-hidden className="flex h-8 justify-center">
      <span className={`w-0.5 transition-colors duration-500 ${on ? "bg-rust/70" : "bg-cocoa/15"}`} />
    </li>
  );
}

function Card({ kin, name, highlight = false }: { kin: Role; name: string; highlight?: boolean }) {
  const { t } = useTranslation();
  const filled = name.trim() !== "";
  const roleLabel = t(`landing.plant.roles.${kin}`);
  return (
    <div
      className={`flex min-h-[4.5rem] w-full max-w-[12rem] flex-col justify-center rounded-xl px-3.5 py-2.5 transition-all duration-500 motion-safe:ease-out ${
        filled
          ? highlight
            ? "scale-100 border-2 border-rust bg-[#fbe3d6] opacity-100 shadow-md"
            : "scale-100 border border-[#d9cbb4] bg-[#fffdf8] opacity-100 shadow-md"
          : "scale-95 border border-dashed border-cocoa/25 bg-white/70 opacity-80"
      }`}
    >
      {filled ? (
        <>
          <span className="truncate font-heritage text-base leading-tight font-bold text-cocoa sm:text-lg" title={name}>
            {name}
          </span>
          <span className="mt-0.5 font-sans text-xs text-umber">
            {roleLabel} · <span lang="hi">{KIN_HI[kin]}</span>
          </span>
        </>
      ) : (
        <span className="inline-flex items-center gap-1.5 font-sans text-xs font-semibold text-umber/80">
          <Plus className="size-3.5" aria-hidden />
          {roleLabel}
        </span>
      )}
    </div>
  );
}
