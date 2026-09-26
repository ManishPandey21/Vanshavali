import type { ComponentType, ReactNode, SVGProps } from "react";
import { Link } from "react-router-dom";
import { useTranslation } from "react-i18next";
import {
  ArrowRight,
  Download,
  House,
  Landmark,
  Languages,
  Lock,
  ScrollText,
  ShieldCheck,
  Sprout,
  Users,
  MapPin,
  Heart,
} from "lucide-react";
import { useMe } from "../../api/hooks/auth";
import { BrandMark } from "../../components/layout/AppShell";
import { LanguageSwitcher } from "../../components/layout/LanguageSwitcher";

/**
 * Public landing page ("/" for signed-out visitors, "/about" for everyone). Static marketing
 * copy only — it reads no family data, so nothing here can leak a person's details.
 */

type Icon = ComponentType<SVGProps<SVGSVGElement>>;

const FEATURES: { key: string; icon: Icon }[] = [
  { key: "tree", icon: Sprout },
  { key: "kinship", icon: Languages },
  { key: "heritage", icon: Landmark },
  { key: "jointFamily", icon: House },
  { key: "documents", icon: ScrollText },
  { key: "property", icon: MapPin },
];

const STEPS = ["seed", "memories", "invite"] as const;

const TRUST: { key: string; icon: Icon }[] = [
  { key: "living", icon: Lock },
  { key: "public", icon: ShieldCheck },
  { key: "roles", icon: Users },
  { key: "export", icon: Download },
];

/** Kinship words are shown in Devanagari in every UI language; only the gloss is translated. */
const KIN_TERMS: { key: string; word: string }[] = [
  { key: "dada", word: "दादा" },
  { key: "nani", word: "नानी" },
  { key: "chacha", word: "चाचा" },
  { key: "tau", word: "ताऊ" },
  { key: "mama", word: "मामा" },
  { key: "bua", word: "बुआ" },
  { key: "mausi", word: "मौसी" },
  { key: "fufa", word: "फूफा" },
  { key: "bhabhi", word: "भाभी" },
  { key: "jija", word: "जीजा" },
];

const SHLOKA = "॥ वसुधैव कुटुम्बकम् ॥";

/** A lotus mandala drawn with rotated petals; purely decorative. */
function Mandala({ className = "" }: { className?: string }) {
  const ring = (count: number, rx: number, ry: number, cy: number, key: string) =>
    Array.from({ length: count }, (_, i) => (
      <ellipse key={`${key}${i}`} cx="200" cy={cy} rx={rx} ry={ry} transform={`rotate(${(360 / count) * i} 200 200)`} />
    ));
  return (
    <svg viewBox="0 0 400 400" className={className} aria-hidden focusable="false">
      <g fill="none" stroke="currentColor" strokeWidth="1.2">
        <circle cx="200" cy="200" r="196" strokeDasharray="2 6" />
        <circle cx="200" cy="200" r="178" />
        {ring(24, 14, 34, 52, "o")}
        <circle cx="200" cy="200" r="120" />
        {ring(16, 12, 28, 96, "m")}
        <circle cx="200" cy="200" r="64" strokeDasharray="3 5" />
        {ring(8, 10, 22, 160, "i")}
        <circle cx="200" cy="200" r="14" />
      </g>
    </svg>
  );
}

/** Toran: a festive garland of mango leaves and marigolds hung across the top of the page. */
function Toran() {
  return (
    <svg className="block h-7 w-full text-leaf-700" aria-hidden focusable="false" preserveAspectRatio="none" viewBox="0 0 400 28">
      <defs>
        <pattern id="toran" width="40" height="28" patternUnits="userSpaceOnUse">
          <path d="M0 3 Q20 9 40 3" fill="none" stroke="#8a5a00" strokeWidth="1.5" />
          <path d="M20 6 C14 12 15 21 20 27 C25 21 26 12 20 6 Z" fill="currentColor" opacity="0.85" />
          <circle cx="4" cy="6" r="4" fill="#d99a0b" />
          <circle cx="4" cy="6" r="1.6" fill="#b4441c" />
        </pattern>
      </defs>
      <rect width="400" height="28" fill="url(#toran)" />
    </svg>
  );
}

/** Section label. Letter-spacing breaks Devanagari conjuncts and matras, so it is Latin-only. */
function Kicker({ children }: { children: ReactNode }) {
  const { i18n } = useTranslation();
  const latin = !i18n.language.startsWith("hi");
  return <p className={`font-semibold text-kumkum-700 ${latin ? "text-xs tracking-[0.18em] uppercase" : "text-sm"}`}>{children}</p>;
}

function SectionHeading({ id, kicker, title, lead }: { id: string; kicker: string; title: string; lead?: string }) {
  return (
    <div className="mx-auto max-w-2xl text-center">
      <Kicker>{kicker}</Kicker>
      <h2 id={id} className="mt-2 font-display text-3xl font-bold text-balance text-kumkum-900 sm:text-4xl">
        {title}
      </h2>
      {lead && <p className="mt-4 text-base text-ink-muted sm:text-lg">{lead}</p>}
    </div>
  );
}

export function LandingPage() {
  const { t } = useTranslation();
  const me = useMe();
  const signedIn = !!me.data;
  // Visitors start at sign-in, which also offers "Create account" (and Google, when configured).
  const startTo = signedIn ? "/" : "/login";
  const startLabel = signedIn ? t("landing.cta.goToTrees") : t("landing.cta.start");

  const navLinks = [
    { href: "#story", label: t("landing.nav.story") },
    { href: "#features", label: t("landing.nav.features") },
    { href: "#how", label: t("landing.nav.how") },
    { href: "#trust", label: t("landing.nav.trust") },
  ];

  return (
    <div className="min-h-dvh overflow-x-hidden bg-parchment text-ink">
      <a href="#main" className="sr-only-focusable absolute top-2 left-2 z-50 rounded bg-white px-3 py-2 text-sm font-medium">
        {t("nav.skipToContent")}
      </a>
      <Toran />
      <header className="sticky top-0 z-40 border-b border-haldi-300/50 bg-parchment/90 backdrop-blur">
        <div className="mx-auto flex max-w-6xl items-center justify-between gap-3 px-4 py-3">
          <BrandMark to="/" />
          <nav aria-label={t("landing.nav.label")} className="hidden md:block">
            <ul className="flex items-center gap-6 text-sm font-medium text-ink-muted">
              {navLinks.map((l) => (
                <li key={l.href}>
                  <a href={l.href} className="rounded hover:text-kumkum-800">
                    {l.label}
                  </a>
                </li>
              ))}
            </ul>
          </nav>
          <div className="flex items-center gap-2 sm:gap-3">
            <LanguageSwitcher className="hidden sm:flex" />
            {!signedIn && (
              <Link to="/login" className="rounded-lg px-3 py-2 text-sm font-medium text-kumkum-800 hover:bg-kumkum-50">
                {t("auth.login")}
              </Link>
            )}
            <Link to={startTo} className="hidden rounded-lg bg-kumkum-700 px-4 py-2 text-sm font-semibold text-white shadow-sm hover:bg-kumkum-800 sm:inline-flex">
              {signedIn ? t("landing.cta.goToTrees") : t("landing.cta.startShort")}
            </Link>
          </div>
        </div>
      </header>

      <main id="main">
        {/* ---------------------------------------------------------------- hero */}
        <section aria-labelledby="hero-title" className="relative isolate overflow-hidden bg-[#1c0b05] text-parchment">
          <figure className="absolute inset-0 -z-10 m-0">
            <img
              src="/landing/hero-tambool.webp"
              width={2000}
              height={848}
              alt={t("landing.hero.sceneAlt")}
              fetchPriority="high"
              decoding="async"
              className="size-full object-cover object-center lg:object-left motion-safe:animate-kenburns"
            />
            <figcaption className="absolute right-4 bottom-3 hidden max-w-xs rounded-md bg-[#1c0b05]/70 px-2.5 py-1.5 text-right text-xs text-parchment/85 italic backdrop-blur-sm sm:block">{t("landing.hero.sceneCaption")}</figcaption>
          </figure>
          {/* Legibility scrim: dark behind the text column, fading out before the offering on the right. */}
          <div className="absolute inset-0 -z-10 bg-gradient-to-b from-[#1c0b05]/80 via-[#1c0b05]/65 to-[#1c0b05]/90 lg:bg-gradient-to-r lg:from-[#1c0b05]/90 lg:from-15% lg:via-[#1c0b05]/55 lg:via-45% lg:to-transparent lg:to-75%" aria-hidden />
          <div className="mx-auto flex min-h-[640px] max-w-6xl items-center px-4 py-16 sm:py-20 lg:min-h-[min(86vh,820px)]">
            <div className="max-w-2xl text-center lg:text-left">
              <p className="font-display text-xl text-haldi-300 sm:text-2xl" lang="sa">
                {SHLOKA}
              </p>
              <p className="mt-1 text-sm text-parchment/80 italic">{t("landing.hero.shlokaMeaning")}</p>
              <h1 id="hero-title" className="mt-6 font-display text-4xl leading-tight font-bold text-parchment sm:text-5xl lg:text-[3.6rem]">
                {t("landing.hero.titleA")} <span className="text-haldi-300">{t("landing.hero.titleB")}</span>
              </h1>
              <p className="mx-auto mt-5 max-w-xl text-base text-parchment/85 sm:text-lg lg:mx-0">{t("landing.hero.lead")}</p>
              <div className="mt-8 flex flex-col items-center gap-3 sm:flex-row sm:justify-center lg:justify-start">
                <Link
                  to={startTo}
                  className="inline-flex w-full items-center justify-center gap-2 rounded-xl bg-haldi-100 px-6 py-3 text-base font-semibold text-kumkum-900 shadow-lg shadow-black/30 hover:bg-white sm:w-auto"
                >
                  {startLabel}
                  <ArrowRight className="size-4" aria-hidden />
                </Link>
                <a
                  href="#showcase"
                  className="inline-flex w-full items-center justify-center rounded-xl border border-parchment/40 px-6 py-3 text-base font-semibold text-parchment hover:bg-white/10 sm:w-auto"
                >
                  {t("landing.cta.seeTree")}
                </a>
              </div>
              <ul className="mt-8 flex flex-wrap justify-center gap-x-5 gap-y-2 text-sm text-parchment/80 lg:justify-start">
                {(["private", "languages", "yours"] as const).map((k) => (
                  <li key={k} className="flex items-center gap-1.5">
                    <span className="size-1.5 rounded-full bg-haldi-300" aria-hidden />
                    {t(`landing.hero.points.${k}`)}
                  </li>
                ))}
              </ul>
            </div>
          </div>
        </section>

        {/* ---------------------------------------------------------------- showcase */}
        <section id="showcase" aria-labelledby="showcase-title" className="scroll-mt-20 bg-[radial-gradient(ellipse_at_top,_#fbe3d6,_#fbf7ef_60%)] px-4 py-20 sm:py-24">
          <div className="mx-auto max-w-6xl">
            <SectionHeading id="showcase-title" kicker={t("landing.showcase.kicker")} title={t("landing.showcase.title")} lead={t("landing.showcase.lead")} />
            <figure className="mx-auto mt-12 max-w-5xl">
              <div className="overflow-hidden rounded-2xl border border-haldi-300/70 bg-white shadow-2xl shadow-kumkum-900/15">
                <div className="flex items-center gap-2 border-b border-stone-200 bg-parchment-deep/70 px-4 py-2.5" aria-hidden>
                  <span className="size-3 rounded-full bg-kumkum-200" />
                  <span className="size-3 rounded-full bg-haldi-300" />
                  <span className="size-3 rounded-full bg-leaf-50 ring-1 ring-leaf-700/30" />
                  <span className="ml-3 truncate rounded-md bg-white px-3 py-0.5 text-xs text-ink-muted" lang="hi">
                    वंशावली · शर्मा परिवार · वंशवृक्ष
                  </span>
                </div>
                <img
                  src="/landing/tree-viewer-hi.png"
                  width={2256}
                  height={1472}
                  loading="lazy"
                  decoding="async"
                  alt={t("landing.showcase.alt")}
                  className="block h-auto w-full"
                />
              </div>
              <figcaption className="mx-auto mt-4 max-w-2xl text-center text-sm text-ink-muted">{t("landing.showcase.caption")}</figcaption>
            </figure>
          </div>
        </section>

        {/* ---------------------------------------------------------------- story */}
        <section id="story" aria-labelledby="story-title" className="scroll-mt-20 px-4 py-20 sm:py-24">
          <div className="mx-auto grid max-w-6xl gap-12 lg:grid-cols-[1fr_1fr] lg:items-center">
            <div>
              <Kicker>{t("landing.story.kicker")}</Kicker>
              <h2 id="story-title" className="mt-2 font-display text-3xl font-bold text-kumkum-900 sm:text-4xl">
                {t("landing.story.title")}
              </h2>
              <div className="mt-6 space-y-4 text-base leading-relaxed text-ink-muted sm:text-lg">
                <p>{t("landing.story.p1")}</p>
                <p>{t("landing.story.p2")}</p>
                <p className="font-medium text-ink">{t("landing.story.p3")}</p>
              </div>
            </div>
            <figure className="relative overflow-hidden rounded-3xl bg-kumkum-900 px-6 py-10 text-center text-parchment shadow-xl sm:px-10">
              <Mandala className="pointer-events-none absolute -top-24 -right-24 size-72 text-haldi-300 opacity-20" />
              <Mandala className="pointer-events-none absolute -bottom-28 -left-28 size-72 text-haldi-300 opacity-20" />
              <blockquote className="relative">
                <p className="font-display text-xl leading-relaxed text-haldi-100 sm:text-2xl" lang="sa">
                  अयं निजः परो वेति गणना लघुचेतसाम्।
                  <br />
                  उदारचरितानां तु वसुधैव कुटुम्बकम्॥
                </p>
                <p className="mx-auto mt-6 max-w-sm text-sm leading-relaxed text-parchment/90 sm:text-base">{t("landing.story.shlokaTranslation")}</p>
              </blockquote>
              <figcaption className="relative mt-4 text-xs text-haldi-300">{t("landing.story.shlokaSource")}</figcaption>
            </figure>
          </div>
        </section>

        {/* ---------------------------------------------------------------- features */}
        <section id="features" aria-labelledby="features-title" className="scroll-mt-20 bg-parchment-deep/60 px-4 py-20 sm:py-24">
          <div className="mx-auto max-w-6xl">
            <SectionHeading id="features-title" kicker={t("landing.features.kicker")} title={t("landing.features.title")} lead={t("landing.features.lead")} />
            <ul className="mt-12 grid gap-5 sm:grid-cols-2 lg:grid-cols-3">
              {FEATURES.map(({ key, icon: I }) => (
                <li key={key} className="group rounded-2xl border border-stone-200 bg-white p-6 shadow-sm transition hover:-translate-y-0.5 hover:border-haldi-300 hover:shadow-md">
                  <span className="grid size-11 place-items-center rounded-xl bg-kumkum-50 text-kumkum-700 group-hover:bg-kumkum-700 group-hover:text-white">
                    <I className="size-5" aria-hidden />
                  </span>
                  <h3 className="mt-4 font-display text-lg font-bold text-ink">{t(`landing.features.items.${key}.title`)}</h3>
                  <p className="mt-2 text-sm leading-relaxed text-ink-muted">{t(`landing.features.items.${key}.body`)}</p>
                </li>
              ))}
            </ul>
          </div>
        </section>

        {/* ---------------------------------------------------------------- kinship words */}
        <section aria-labelledby="kin-title" className="px-4 py-20 sm:py-24">
          <div className="mx-auto max-w-5xl text-center">
            <Kicker>{t("landing.kin.kicker")}</Kicker>
            <h2 id="kin-title" className="mt-2 font-display text-3xl font-bold text-kumkum-900 sm:text-4xl">
              {t("landing.kin.title")}
            </h2>
            <p className="mx-auto mt-4 max-w-2xl text-base text-ink-muted sm:text-lg">{t("landing.kin.lead")}</p>
            <ul className="mt-10 grid grid-cols-2 gap-3 sm:grid-cols-3 lg:grid-cols-5">
              {KIN_TERMS.map(({ key, word }) => (
                <li key={key} className="rounded-xl border border-haldi-300/60 bg-gradient-to-b from-white to-haldi-100/40 px-3 py-4">
                  <p className="font-display text-2xl font-bold text-kumkum-800" lang="hi">
                    {word}
                  </p>
                  <p className="mt-1 text-xs leading-snug text-ink-muted">{t(`landing.kin.terms.${key}`)}</p>
                </li>
              ))}
            </ul>
          </div>
        </section>

        {/* ---------------------------------------------------------------- how it works */}
        <section id="how" aria-labelledby="how-title" className="scroll-mt-20 bg-parchment-deep/60 px-4 py-20 sm:py-24">
          <div className="mx-auto max-w-6xl">
            <SectionHeading id="how-title" kicker={t("landing.how.kicker")} title={t("landing.how.title")} />
            <ol className="relative mt-12 grid gap-8 md:grid-cols-3">
              <span className="absolute top-7 right-[16%] left-[16%] hidden border-t-2 border-dashed border-haldi-300 md:block" aria-hidden />
              {STEPS.map((key, i) => (
                <li key={key} className="relative text-center">
                  <span className="relative mx-auto grid size-14 place-items-center rounded-full border-4 border-parchment bg-kumkum-700 font-display text-xl font-bold text-white shadow-md">
                    {i + 1}
                  </span>
                  <h3 className="mt-4 font-display text-xl font-bold text-ink">{t(`landing.how.steps.${key}.title`)}</h3>
                  <p className="mx-auto mt-2 max-w-xs text-sm leading-relaxed text-ink-muted">{t(`landing.how.steps.${key}.body`)}</p>
                </li>
              ))}
            </ol>
          </div>
        </section>

        {/* ---------------------------------------------------------------- trust */}
        <section id="trust" aria-labelledby="trust-title" className="scroll-mt-20 px-4 py-20 sm:py-24">
          <div className="mx-auto max-w-6xl">
            <SectionHeading id="trust-title" kicker={t("landing.trust.kicker")} title={t("landing.trust.title")} lead={t("landing.trust.lead")} />
            <ul className="mt-12 grid gap-5 sm:grid-cols-2">
              {TRUST.map(({ key, icon: I }) => (
                <li key={key} className="flex gap-4 rounded-2xl border border-stone-200 bg-white p-6 shadow-sm">
                  <span className="grid size-10 shrink-0 place-items-center rounded-full bg-leaf-50 text-leaf-700">
                    <I className="size-5" aria-hidden />
                  </span>
                  <div>
                    <h3 className="font-display text-lg font-bold text-ink">{t(`landing.trust.items.${key}.title`)}</h3>
                    <p className="mt-1 text-sm leading-relaxed text-ink-muted">{t(`landing.trust.items.${key}.body`)}</p>
                  </div>
                </li>
              ))}
            </ul>
          </div>
        </section>

        {/* ---------------------------------------------------------------- closing */}
        <section aria-labelledby="closing-title" className="px-4 pb-20 sm:pb-24">
          <div className="relative mx-auto max-w-5xl overflow-hidden rounded-3xl bg-gradient-to-br from-kumkum-800 via-kumkum-700 to-kumkum-900 px-6 py-14 text-center text-white shadow-xl sm:px-12">
            <Mandala className="pointer-events-none absolute top-1/2 left-1/2 size-[36rem] -translate-x-1/2 -translate-y-1/2 text-haldi-300 opacity-15" />
            <div className="relative">
              <p className="font-display text-2xl text-haldi-100 sm:text-3xl" lang="sa">
                ॥ परंपरा एवं श्रद्धा ॥
              </p>
              <p className="mt-1 text-sm text-kumkum-100 italic">{t("landing.closing.mottoMeaning")}</p>
              <h2 id="closing-title" className="mx-auto mt-6 max-w-2xl font-display text-3xl font-bold sm:text-4xl">
                {t("landing.closing.title")}
              </h2>
              <p className="mx-auto mt-4 max-w-xl text-base text-kumkum-50/90">{t("landing.closing.lead")}</p>
              <Link
                to={startTo}
                className="mt-8 inline-flex items-center gap-2 rounded-xl bg-haldi-100 px-6 py-3 text-base font-semibold text-kumkum-900 shadow-md hover:bg-white"
              >
                {signedIn ? t("landing.cta.goToTrees") : t("landing.closing.cta")}
                <ArrowRight className="size-4" aria-hidden />
              </Link>
            </div>
          </div>
        </section>
      </main>

      <footer className="border-t border-haldi-300/60 bg-parchment-deep/70 px-4 py-10">
        <div className="mx-auto flex max-w-6xl flex-col items-center gap-4 text-center">
          <BrandMark to="/" />
          <p className="flex items-center gap-1.5 text-sm text-ink">
            {t("landing.footer.builtWithA")}
            <Heart className="size-4 fill-kumkum-600 text-kumkum-600" aria-hidden />
            <span className="sr-only">{t("landing.footer.love")}</span>
            {t("landing.footer.builtWithB")}
          </p>
          <p className="font-display text-kumkum-800" lang="sa">
            {SHLOKA} · ॥ परंपरा एवं श्रद्धा ॥
          </p>
          <LanguageSwitcher className="sm:hidden" />
        </div>
      </footer>
    </div>
  );
}
