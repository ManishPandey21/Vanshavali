import { Link } from "react-router-dom";
import { useTranslation } from "react-i18next";
import { BrandMark } from "../../components/layout/AppShell";
import { LanguageSwitcher } from "../../components/layout/LanguageSwitcher";

/**
 * Public privacy notice (ADR-0032 activation condition 1). Every statement must stay true of the
 * code: when a behaviour named here changes, change `privacyNotice.*` in both locales in the same PR.
 * Sources: docs/security/privacy-model.md, ADR-0005, ADR-0009, ADR-0032.
 */
type Section = { id: string; lead?: true; points?: readonly string[]; body?: true; after?: string };

export const PRIVACY_SECTIONS: readonly Section[] = [
  { id: "collect", points: ["account", "google", "sessions", "family", "reminders", "audit"] },
  { id: "protect", points: ["private", "living", "minors", "public", "encrypted"] },
  { id: "never", points: ["sell", "analytics", "email", "ai", "inference", "search"] },
  { id: "sharing", lead: true, points: ["hosting", "email", "messaging", "google", "payment"], after: "law" },
  { id: "storage", lead: true, points: ["session", "csrf", "visitor", "language", "recent", "draft"] },
  { id: "visitors", points: ["what", "how", "signals", "estimate"] },
  { id: "retention", points: ["family", "links", "logs", "records", "backups"] },
  { id: "rights", points: ["control", "remove", "correct", "export", "attestation", "close", "grievance"] },
  { id: "children", body: true },
  { id: "donations", body: true },
  { id: "changes", body: true },
];

/** Every translation key the page reads, for the locale completeness test. */
export function privacyNoticeKeys(): string[] {
  const keys = ["title", "updated", "intro", "contents", "backHome", "sections.contact.title", "sections.contact.withEmail", "sections.contact.withoutEmail"];
  for (const s of PRIVACY_SECTIONS) {
    const base = `sections.${s.id}`;
    keys.push(`${base}.title`);
    if (s.lead) keys.push(`${base}.lead`);
    if (s.body) keys.push(`${base}.body`);
    if (s.after) keys.push(`${base}.${s.after}`);
    for (const p of s.points ?? []) keys.push(`${base}.points.${p}`);
  }
  return keys.map((k) => `privacyNotice.${k}`);
}

/** A build-time address for privacy requests; anything that is not a plain email address is ignored. */
export function privacyContactEmail(configured = import.meta.env.VITE_PRIVACY_CONTACT_EMAIL): string | null {
  const value = configured?.trim();
  // Letters, digits and . _ % + - only: no "?", "&" or spaces that could add mailto headers.
  return value && /^[A-Za-z0-9._%+-]+@[A-Za-z0-9-]+(\.[A-Za-z0-9-]+)*\.[A-Za-z]{2,}$/.test(value) ? value : null;
}

export function PrivacyPage() {
  const { t } = useTranslation();
  const email = privacyContactEmail();
  const k = (key: string) => t(`privacyNotice.${key}`);
  // Translate the sentence around a marker, then put a real link where the marker was.
  const MARK = "\u2063";
  const [contactBefore = "", contactAfter = ""] = t("privacyNotice.sections.contact.withEmail", { email: MARK }).split(MARK);

  return (
    <div className="min-h-dvh bg-cream">
      <a href="#main" className="sr-only-focusable absolute top-2 left-2 z-50 rounded bg-white px-3 py-2 text-sm font-medium">
        {t("nav.skipToContent")}
      </a>
      <header className="flex items-center justify-between border-b border-cocoa/10 px-4 py-3">
        <BrandMark to="/" />
        <LanguageSwitcher />
      </header>
      <main id="main" className="mx-auto max-w-3xl px-4 py-10 sm:py-14">
        <h1 className="font-display text-3xl font-bold sm:text-4xl">{k("title")}</h1>
        <p className="mt-2 text-sm text-ink-muted">{k("updated")}</p>
        <p className="mt-6 leading-relaxed">{k("intro")}</p>

        <nav aria-labelledby="privacy-contents" className="mt-8 rounded border border-cocoa/10 bg-white/60 p-5">
          <h2 id="privacy-contents" className="text-sm font-semibold">
            {k("contents")}
          </h2>
          <ol className="mt-3 grid gap-1.5 text-sm sm:grid-cols-2">
            {[...PRIVACY_SECTIONS.map((s) => s.id), "contact"].map((id) => (
              <li key={id}>
                <a href={`#privacy-${id}`} className="text-kumkum-800 underline-offset-2 hover:underline">
                  {k(`sections.${id}.title`)}
                </a>
              </li>
            ))}
          </ol>
        </nav>

        {PRIVACY_SECTIONS.map((s) => {
          const base = `sections.${s.id}`;
          return (
            <section key={s.id} id={`privacy-${s.id}`} aria-labelledby={`privacy-${s.id}-title`} className="mt-10 scroll-mt-6">
              <h2 id={`privacy-${s.id}-title`} className="font-display text-xl font-bold sm:text-2xl">
                {k(`${base}.title`)}
              </h2>
              {s.lead && <p className="mt-3 leading-relaxed">{k(`${base}.lead`)}</p>}
              {s.body && <p className="mt-3 leading-relaxed">{k(`${base}.body`)}</p>}
              {s.points && (
                <ul className="mt-3 list-disc space-y-2 pl-5 leading-relaxed">
                  {s.points.map((p) => (
                    <li key={p}>{k(`${base}.points.${p}`)}</li>
                  ))}
                </ul>
              )}
              {s.after && <p className="mt-3 leading-relaxed">{k(`${base}.${s.after}`)}</p>}
            </section>
          );
        })}

        <section id="privacy-contact" aria-labelledby="privacy-contact-title" className="mt-10 scroll-mt-6">
          <h2 id="privacy-contact-title" className="font-display text-xl font-bold sm:text-2xl">
            {k("sections.contact.title")}
          </h2>
          <p className="mt-3 leading-relaxed">
            {email ? (
              <>
                {contactBefore}
                <a href={`mailto:${email}`} className="font-medium text-kumkum-800 underline">
                  {email}
                </a>
                {contactAfter}
              </>
            ) : (
              k("sections.contact.withoutEmail")
            )}
          </p>
        </section>

        <p className="mt-12">
          <Link to="/" className="font-medium text-kumkum-800 underline">
            {k("backHome")}
          </Link>
        </p>
      </main>
    </div>
  );
}
