import { useId } from "react";
import { useTranslation } from "react-i18next";
import { Languages } from "lucide-react";
import { useMe, useUpdateProfile } from "../../api/hooks/auth";
import { SUPPORTED_LANGUAGES, rememberLanguage } from "../../i18n";

/** Switches UI language; for signed-in users the choice is saved to the profile (PATCH /auth/me). */
export function LanguageSwitcher({ className = "" }: { className?: string }) {
  const { t, i18n } = useTranslation();
  const id = useId();
  const me = useMe();
  const update = useUpdateProfile();
  const change = async (lang: string) => {
    rememberLanguage(lang);
    await i18n.changeLanguage(lang);
    if (me.data && me.data.preferred_language !== lang) update.mutate({ preferred_language: lang });
  };
  return (
    <div className={`flex items-center gap-1.5 ${className}`}>
      <Languages className="size-4 text-ink-muted" aria-hidden />
      <label htmlFor={id} className="sr-only">
        {t("nav.language")}
      </label>
      <select
        id={id}
        value={i18n.language.startsWith("hi") ? "hi" : "en"}
        onChange={(e) => void change(e.target.value)}
        className="rounded-md border border-stone-300 bg-white px-2 py-1 text-sm"
      >
        {SUPPORTED_LANGUAGES.map((l) => (
          <option key={l.code} value={l.code} lang={l.code}>
            {l.label}
          </option>
        ))}
      </select>
    </div>
  );
}
