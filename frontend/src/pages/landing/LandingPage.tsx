import { useState, type ReactNode } from "react";
import { useQuery } from "@tanstack/react-query";
import { api } from "../../api/client";
import type { SiteImpactOut } from "../../api/types";
import { DONATION_AMOUNTS, parseVoluntaryAmount, safeHostedDonationLink } from "./donations";
import { Link } from "react-router-dom";
import { useTranslation } from "react-i18next";
import { ArrowRight, BookOpenText, Download, EyeOff, Heart, Lock, Network, ScrollText, ShieldCheck, Sprout, UserCog, Users, type LucideIcon } from "lucide-react";
import "@fontsource/playfair-display/400.css";
import "@fontsource/playfair-display/400-italic.css";
import "@fontsource/playfair-display/600.css";
import "@fontsource/playfair-display/700.css";
import "@fontsource/playfair-display/700-italic.css";
import "@fontsource/eb-garamond/400.css";
import "@fontsource/eb-garamond/400-italic.css";
import "@fontsource/eb-garamond/500.css";
// Regular weight for Devanagari serif text (the app bundles only 600/700, which made Hindi body
// copy and the Sanskrit verses render semibold). unicode-range limits it to Devanagari glyphs:
// one ~51 KB woff2, fetched on the English page too because it shows Sanskrit verses.
import "@fontsource/noto-serif-devanagari/400.css";
import { useMe } from "../../api/hooks/auth";
import { BrandMark } from "../../components/layout/AppShell";
import { LanguageSwitcher } from "../../components/layout/LanguageSwitcher";
import { GrowingTree } from "./GrowingTree";
import { TreePlanter } from "./TreePlanter";
import { Reveal } from "./Reveal";

/**
 * Public landing page ("/" for signed-out visitors, "/about" for everyone). Static copy only — it
 * reads no family data, so nothing here can leak a person's details. Body copy is set in the app's
 * Noto Sans (with Noto Sans Devanagari for Hindi); Playfair and EB Garamond carry the headings,
 * quotations and heritage storytelling. The "plant your tree" builder
 * keeps what a visitor types in this tab only (lib/treeDraft.ts) and never sends it from here. Editorial heritage design:
 * Playfair Display headings, EB Garamond text, cream/cocoa/terracotta palette, scroll reveals.
 */

const HERO_IMAGE = "/landing/hero-tambool.webp";
const HERO_W = 2000;
const HERO_H = 848;

/** A region of the hero photograph, cropped with CSS so the page downloads one image only. */
function PhotoCrop({ x, y, w, h, label, className = "" }: { x: number; y: number; w: number; h: number; label: string; className?: string }) {
  return (
    <div
      role="img"
      aria-label={label}
      className={`w-full bg-sand bg-no-repeat ${className}`}
      style={{
        aspectRatio: `${w} / ${h}`,
        backgroundImage: `url(${HERO_IMAGE})`,
        backgroundSize: `${(HERO_W / w) * 100}% auto`,
        backgroundPosition: `${(x / (HERO_W - w)) * 100}% ${(y / (HERO_H - h)) * 100}%`,
      }}
    />
  );
}

/** Small label above a heading. Letter-spacing breaks Devanagari conjuncts and matras, so it is Latin-only. */
function Eyebrow({ children, tone = "rust", center = false }: { children: ReactNode; tone?: "rust" | "gold"; center?: boolean }) {
  const { i18n } = useTranslation();
  const latin = !i18n.language.startsWith("hi");
  const color = tone === "gold" ? "text-gold" : "text-rust";
  return (
    <p className={`flex items-center gap-3 ${center ? "justify-center" : ""} ${color} ${latin ? "text-[11px] font-semibold tracking-[0.28em] uppercase" : "text-sm font-semibold"}`}>
      <span className="h-px w-8 bg-current opacity-50" aria-hidden />
      {children}
      <span className="h-px w-8 bg-current opacity-50" aria-hidden />
    </p>
  );
}

/** Heading with one italic accent phrase, the signature of this design. */
function AccentHeading({
  id,
  before,
  accent,
  after,
  tone = "rust",
  className = "",
  as: Tag = "h2",
}: {
  id?: string;
  before: string;
  accent: string;
  after?: string;
  tone?: "rust" | "gold";
  className?: string;
  as?: "h1" | "h2" | "h3";
}) {
  return (
    <Tag id={id} className={`font-heritage leading-[1.08] font-bold text-balance ${className}`}>
      {before}{" "}
      <em className={`font-normal italic ${tone === "gold" ? "text-gold" : "text-rust"}`}>{accent}</em>
      {after ? <> {after}</> : null}
    </Tag>
  );
}

const PILLARS = ["educate", "preserve", "celebrate"] as const;
const NUMERALS = ["I", "II", "III"];

const CHAPTERS = [
  { key: "leaf", n: "01", crop: { x: 1110, y: 396, w: 256, h: 256 }, facts: ["offered", "heard"], imageLeft: true },
  { key: "petal", n: "02", crop: { x: 640, y: 580, w: 300, h: 170 }, facts: ["marigold", "jasmine", "lotus"], imageLeft: false },
  { key: "seed", n: "03", crop: { x: 1110, y: 586, w: 330, h: 165 }, facts: ["whole", "shared"], imageLeft: true },
] as const;

const KEEPERS = [
  { key: "elder", initial: "दा" },
  { key: "panda", initial: "ब" },
  { key: "grandchild", initial: "आ" },
] as const;

const STORIES = ["samskara", "gotra", "kuladevata", "nakshatra"] as const;
const TIMELINE = ["vedic", "shraddha", "puranic", "bahi", "partition", "today"] as const;

const ARCHIVE_POINTS = [
  { key: "kinship", icon: Network },
  { key: "heritage", icon: ScrollText },
  { key: "together", icon: Users },
  { key: "private", icon: Lock },
] as const;

export function LandingPage() {
  const { t, i18n } = useTranslation();
  const me = useMe();
  const signedIn = !!me.data;
  const hindi = i18n.language.startsWith("hi");
  // Visitors start at sign-in, which also offers "Create account" (and Google, when configured).
  const startTo = signedIn ? "/" : "/login";
  const startLabel = signedIn ? t("landing.cta.goToTrees") : t("landing.cta.start");
  // Wide-tracked capitals suit the Latin design but pull Devanagari conjuncts and matras apart.
  const btnText = hindi ? "text-sm font-semibold" : "text-xs font-bold tracking-[0.16em] uppercase";

  const navLinks = [
    { href: "#archive", label: t("landing.nav.archive") },
    { href: "#traditions", label: t("landing.nav.traditions") },
    { href: "#keepers", label: t("landing.nav.keepers") },
    { href: "#stories", label: t("landing.nav.stories") },
    { href: "#timeline", label: t("landing.nav.timeline") },
  ];
  // The header row is full at five links (more wraps in English at 1024–1440 px), so the two
  // sections added for trust and getting started are listed in the footer instead.
  const footerLinks = [
    navLinks[0]!,
    { href: "#how", label: t("landing.nav.how") },
    { href: "#trust", label: t("landing.nav.trust") },
    { href: "#support", label: t("landing.support.nav") },
    ...navLinks.slice(1),
  ];

  return (
    <div className="heritage min-h-dvh overflow-x-hidden bg-cream font-sans text-cocoa">
      <a href="#main" className="sr-only-focusable absolute top-2 left-2 z-50 rounded bg-white px-3 py-2 font-sans text-sm font-medium">
        {t("nav.skipToContent")}
      </a>

      {/* ---------------------------------------------------------------- announcement + header */}
      <p className="bg-cocoa px-4 py-2 text-center font-sans text-[11px] text-cream/80 sm:text-xs">
        <span lang="sa" className="text-gold">
          ॥ वसुधैव कुटुम्बकम् ॥
        </span>
        <span className="mx-2 text-cream/40" aria-hidden>
          ·
        </span>
        <span className={hindi ? "" : "tracking-[0.2em] uppercase"}>{t("landing.announce")}</span>
      </p>
      <header className="sticky top-0 z-40 border-b border-cocoa/10 bg-cream/90 backdrop-blur">
        <div className="mx-auto flex max-w-6xl items-center justify-between gap-3 px-4 py-3">
          <BrandMark to="/" />
          <nav aria-label={t("landing.nav.label")} className="hidden lg:block">
            <ul className={`flex items-center gap-6 font-sans text-umber ${hindi ? "text-sm" : "text-[11px] font-semibold tracking-[0.18em] uppercase"}`}>
              {navLinks.map((l) => (
                <li key={l.href}>
                  <a href={l.href} className="rounded hover:text-rust">
                    {l.label}
                  </a>
                </li>
              ))}
            </ul>
          </nav>
          <div className="flex items-center gap-2 font-sans sm:gap-3">
            <LanguageSwitcher className="hidden sm:flex" />
            {!signedIn && (
              <Link to="/login" className="rounded px-3 py-2 text-sm font-semibold text-rust hover:bg-sand">
                {t("auth.login")}
              </Link>
            )}
            <Link
              to={startTo}
              className={`hidden items-center gap-2 bg-cocoa px-4 py-2.5 text-cream hover:bg-cocoa-soft ${hindi ? "text-sm font-semibold" : "text-xs font-semibold tracking-wide uppercase"} sm:inline-flex`}
            >
              {signedIn ? t("landing.cta.goToTrees") : t("landing.cta.startShort")}
              <ArrowRight className="size-3.5" aria-hidden />
            </Link>
          </div>
        </div>
      </header>

      <main id="main">
        {/* ---------------------------------------------------------------- hero */}
        <section aria-labelledby="hero-title" className="relative isolate overflow-hidden bg-cocoa text-cream">
          <figure className="absolute inset-0 -z-10 m-0">
            <img
              src={HERO_IMAGE}
              width={HERO_W}
              height={HERO_H}
              alt={t("landing.hero.sceneAlt")}
              fetchPriority="high"
              decoding="async"
              className="size-full object-cover object-center lg:object-left motion-safe:animate-kenburns"
            />
          </figure>
          <div
            className="absolute inset-0 -z-10 bg-gradient-to-b from-cocoa/80 via-cocoa/60 to-cocoa/90 lg:bg-gradient-to-r lg:from-cocoa/90 lg:from-15% lg:via-cocoa/50 lg:via-45% lg:to-transparent lg:to-75%"
            aria-hidden
          />
          <div className="mx-auto flex min-h-[620px] max-w-6xl flex-col justify-center px-4 pt-16 pb-24 lg:min-h-[min(88vh,840px)]">
            <div className="max-w-2xl">
              <p className="flex flex-wrap items-center gap-3 font-sans text-xs text-cream/80 motion-safe:animate-rise">
                <span className="border border-gold/60 px-3 py-1 text-gold" lang="sa">
                  ॥ परंपरा एवं श्रद्धा ॥
                </span>
                <span className="font-garamond text-sm italic">{t("landing.hero.eyebrow")}</span>
              </p>
              <h1 id="hero-title" className={`mt-6 font-heritage text-5xl font-bold sm:text-6xl lg:text-[5.2rem] ${hindi ? "leading-[1.3] [&>*]:leading-[1.3]" : "leading-[1.02]"}`}>
                <span className="block motion-safe:animate-rise [animation-delay:120ms]">{t("landing.hero.titleA")}</span>{" "}
                <em className="block font-normal text-gold italic motion-safe:animate-rise [animation-delay:240ms]">{t("landing.hero.titleB")}</em>{" "}
                <span className="block motion-safe:animate-rise [animation-delay:360ms]">{t("landing.hero.titleC")}</span>
              </h1>
              <p className="mt-6 max-w-xl text-lg leading-relaxed text-cream/85 motion-safe:animate-rise [animation-delay:480ms] sm:text-xl">
                {t("landing.hero.lead")}
              </p>
              <div className="mt-9 flex flex-col gap-3 font-sans motion-safe:animate-rise [animation-delay:600ms] sm:flex-row">
                <Link
                  to={startTo}
                  className={`inline-flex items-center justify-center gap-2 bg-cream px-7 py-3.5 ${btnText} text-cocoa hover:bg-white`}
                >
                  {startLabel}
                  <ArrowRight className="size-4" aria-hidden />
                </Link>
                <a
                  href="#plant"
                  className={`inline-flex items-center justify-center gap-2 border border-cream/50 px-7 py-3.5 ${btnText} text-cream hover:bg-cream/10`}
                >
                  <Sprout className="size-4 text-gold" aria-hidden />
                  {t("landing.cta.tryIt")}
                </a>
              </div>
            </div>
          </div>
          <div className="absolute inset-x-0 bottom-0 mx-auto flex max-w-6xl flex-wrap items-end justify-between gap-3 px-4 pb-5 font-sans text-xs">
            <span className="inline-flex items-center gap-2 rounded-full bg-cocoa/85 px-4 py-2 text-cream/90 backdrop-blur">
              <Lock className="size-3.5 text-gold" aria-hidden />
              {t("landing.hero.chipPrivate")}
            </span>
            <span className="hidden max-w-sm rounded-full bg-rust/90 px-4 py-2 text-cream italic sm:inline-flex">{t("landing.hero.sceneCaption")}</span>
          </div>
        </section>

        {/* ---------------------------------------------------------------- plant your tree (try before signing up) */}
        <section id="plant" className="relative z-10 scroll-mt-20 bg-gradient-to-b from-cocoa from-[3.5rem] to-cream to-[3.5rem] px-4 pb-4">
          <div className="mx-auto max-w-5xl">
            <TreePlanter signedIn={signedIn} />
          </div>
        </section>

        {/* ---------------------------------------------------------------- purpose */}
        <section aria-labelledby="purpose-title" className="px-4 py-24 sm:py-28">
          <div className="mx-auto max-w-3xl text-center">
            <Reveal>
              <Eyebrow center>{t("landing.purpose.kicker")}</Eyebrow>
              <h2 id="purpose-title" className="mt-6 font-heritage text-4xl leading-tight font-bold text-cocoa/90 sm:text-5xl">
                {t("landing.purpose.titleA")}{" "}
                <Heart className="inline size-10 -translate-y-1 fill-rust text-rust sm:size-12" aria-label={t("landing.purpose.love")} role="img" />{" "}
                {t("landing.purpose.titleB")}
                <span className="mt-3 block font-garamond text-2xl font-medium text-rust" lang="sa">
                  ॥ परंपरा एवं श्रद्धा ॥
                </span>
                <em className="mt-2 block font-normal text-umber italic">{t("landing.purpose.titleC")}</em>
              </h2>
            </Reveal>
            <Reveal delay={120}>
              <p className="mt-10 font-garamond text-xl leading-relaxed text-umber sm:text-2xl">
                {t("landing.purpose.p1a")} <em className="text-rust">{t("landing.purpose.p1em")}</em> {t("landing.purpose.p1b")}
              </p>
              <p className="mx-auto mt-6 max-w-2xl font-sans text-sm leading-relaxed text-umber">
                <strong className="font-semibold text-rust">{t("app.name")}</strong> {t("landing.purpose.p2")}
              </p>
            </Reveal>
          </div>
          <ol className="mx-auto mt-16 grid max-w-4xl gap-10 sm:grid-cols-3">
            {PILLARS.map((k, i) => (
              <Reveal as="li" key={k} delay={i * 140} className="text-left">
                <span className="font-heritage text-4xl text-rust/70" aria-hidden>
                  {NUMERALS[i]}
                </span>
                <h3 className="mt-3 font-heritage text-lg font-bold">{t(`landing.purpose.pillars.${k}.title`)}</h3>
                <p className="mt-2 font-sans text-sm leading-relaxed text-umber">{t(`landing.purpose.pillars.${k}.body`)}</p>
              </Reveal>
            ))}
          </ol>
        </section>

        {/* ---------------------------------------------------------------- the family tree (living archive) */}
        <section id="archive" aria-labelledby="archive-title" className="scroll-mt-20 overflow-hidden bg-sand px-4 py-24 sm:py-28">
          <div className="mx-auto max-w-6xl">
            <Reveal className="mx-auto max-w-2xl text-center">
              <Eyebrow center>{t("landing.archive.kicker")}</Eyebrow>
              <h2 id="archive-title" className="mt-5 font-heritage text-4xl leading-[1.08] font-bold sm:text-5xl">
                {t("landing.archive.titleA")}
                <em className="mt-1 block font-normal text-rust italic">{t("landing.archive.titleB")}</em>
              </h2>
              <p className="mt-5 text-lg leading-relaxed text-umber">{t("landing.archive.lead")}</p>
            </Reveal>

            <div className="mt-14 grid items-center gap-10 lg:grid-cols-[minmax(0,5fr)_minmax(0,7fr)]">
              <div>
                <Reveal className="relative border border-cocoa/10 bg-cream p-7 shadow-sm">
                  <span className="grid size-12 place-items-center rounded-full bg-leaf-50 text-leaf-700">
                    <Network className="size-6" aria-hidden />
                  </span>
                  <h3 className="mt-5 font-heritage text-2xl font-bold">{t("landing.archive.card.title")}</h3>
                  <p className="mt-3 leading-relaxed text-umber">{t("landing.archive.card.body")}</p>
                </Reveal>
                <ul className="mt-6 grid gap-3 font-sans text-sm">
                  {ARCHIVE_POINTS.map(({ key, icon: I }, i) => (
                    <Reveal as="li" key={key} delay={150 + i * 120} className="flex gap-3 border-b border-cocoa/10 pb-3">
                      <I className="mt-0.5 size-4 shrink-0 text-rust" aria-hidden />
                      <span>
                        <strong className="font-semibold text-cocoa">{t(`landing.archive.points.${key}.title`)}</strong>{" "}
                        <span className="text-umber">{t(`landing.archive.points.${key}.body`)}</span>
                      </span>
                    </Reveal>
                  ))}
                </ul>
              </div>

              <Reveal as="figure" delay={200} className="m-0 min-w-0">
                <GrowingTree />
                <figcaption className="mt-4 text-center font-garamond text-base text-umber italic">{t("landing.archive.caption")}</figcaption>
              </Reveal>
            </div>

            <Reveal className="mt-14 text-center font-sans" delay={100}>
              <Link
                to={startTo}
                className={`inline-flex items-center gap-2 bg-cocoa px-7 py-3.5 ${btnText} text-cream hover:bg-cocoa-soft`}
              >
                {startLabel}
                <ArrowRight className="size-4" aria-hidden />
              </Link>
              <p className="mt-3 text-xs text-umber">{t("landing.archive.note")}</p>
            </Reveal>
          </div>
        </section>

        <HowItWorks startTo={startTo} startLabel={startLabel} btnText={btnText} />
        <KeptInTrust startTo={startTo} startLabel={startLabel} btnText={btnText} />

        {/* ---------------------------------------------------------------- three traditions */}
        <div id="traditions" className="scroll-mt-20">
          {CHAPTERS.map((c, ci) => {
            const base = `landing.traditions.${c.key}`;
            return (
              <section
                key={c.key}
                aria-labelledby={`chapter-${c.key}`}
                className={`px-4 py-24 sm:py-28 ${ci % 2 === 1 ? "bg-sand/60" : "bg-cream"}`}
              >
                <div className="mx-auto grid max-w-6xl items-center gap-12 lg:grid-cols-12">
                  <Reveal className={`lg:col-span-5 ${c.imageLeft ? "" : "lg:order-2"}`}>
                    <div className="relative">
                      <PhotoCrop {...c.crop} label={t(`${base}.imgAlt`)} className="shadow-xl shadow-cocoa/10" />
                      <p className="absolute -bottom-6 left-6 bg-cream px-4 py-2 font-sans shadow-sm">
                        <span className="block text-xs font-semibold text-cocoa">{t(`${base}.imgCaption`)}</span>
                      </p>
                    </div>
                  </Reveal>
                  <div className={`lg:col-span-7 ${c.imageLeft ? "" : "lg:order-1"}`}>
                    <Reveal className="flex items-end gap-4">
                      <span className="font-heritage text-7xl leading-none text-rust/20" aria-hidden>
                        {c.n}
                      </span>
                      <span className="pb-2">
                        <Eyebrow>{t(`${base}.chapter`)}</Eyebrow>
                        <span className="mt-1 block font-garamond text-lg text-umber italic">{t(`${base}.subtitle`)}</span>
                      </span>
                    </Reveal>
                    <Reveal delay={100}>
                      <AccentHeading
                        id={`chapter-${c.key}`}
                        before={t(`${base}.titleA`)}
                        accent={t(`${base}.titleEm`)}
                        after={t(`${base}.titleB`)}
                        className="mt-6 text-4xl sm:text-5xl"
                      />
                    </Reveal>
                    <Reveal delay={180}>
                      <p className="mt-6 font-garamond text-lg leading-relaxed text-umber first-letter:float-left first-letter:mt-1 first-letter:mr-3 first-letter:font-heritage first-letter:text-6xl first-letter:leading-[0.8] first-letter:text-rust">
                        {t(`${base}.p1`)}
                      </p>
                      <p className="mt-4 font-garamond text-lg leading-relaxed text-umber">{t(`${base}.p2`)}</p>
                      <blockquote className="mt-7 border-l-2 border-rust/50 pl-5">
                        <p className="font-heritage text-xl text-rust italic" lang="sa">
                          {t(`${base}.quote`)}
                        </p>
                        <p className="mt-1 font-garamond text-lg text-umber italic">“{t(`${base}.quoteMeaning`)}”</p>
                        <footer className="mt-1 font-sans text-xs text-umber">— {t(`${base}.quoteSource`)}</footer>
                      </blockquote>
                    </Reveal>
                    <dl className={`mt-9 grid gap-6 font-sans ${c.facts.length === 3 ? "sm:grid-cols-3" : "sm:grid-cols-2"}`}>
                      {c.facts.map((f, fi) => (
                        <Reveal key={f} delay={240 + fi * 120} className="border-t border-cocoa/15 pt-3">
                          <dt className={`text-rust ${hindi ? "text-sm font-semibold" : "text-[11px] font-semibold tracking-[0.2em] uppercase"}`}>
                            {t(`${base}.facts.${f}.label`)}
                          </dt>
                          <dd className="mt-1 text-sm text-umber">{t(`${base}.facts.${f}.body`)}</dd>
                        </Reveal>
                      ))}
                    </dl>
                  </div>
                </div>
              </section>
            );
          })}
        </div>

        {/* ---------------------------------------------------------------- keepers of memory */}
        <section id="keepers" aria-labelledby="keepers-title" className="scroll-mt-20 bg-cocoa px-4 py-24 text-cream sm:py-28">
          <div className="mx-auto max-w-6xl">
            <Reveal className="mx-auto max-w-2xl text-center">
              <Eyebrow tone="gold" center>
                {t("landing.keepers.kicker")}
              </Eyebrow>
              <h2 id="keepers-title" className="mt-5 font-heritage text-4xl leading-[1.08] font-bold sm:text-5xl">
                {t("landing.keepers.titleA")}
                <em className="mt-1 block font-normal text-gold italic">{t("landing.keepers.titleB")}</em>
              </h2>
              <p className="mt-5 text-lg text-cream/75">{t("landing.keepers.lead")}</p>
            </Reveal>
            <ul className="mt-16 grid gap-10 border-t border-cream/10 pt-12 md:grid-cols-3">
              {KEEPERS.map((k, i) => (
                <Reveal as="li" key={k.key} delay={i * 150}>
                  <span className="font-heritage text-4xl leading-none text-gold/70" aria-hidden>
                    “
                  </span>
                  <p className="mt-2 font-garamond text-xl leading-relaxed text-cream/85 italic">{t(`landing.keepers.items.${k.key}.body`)}</p>
                  <p className="mt-6 flex items-center gap-3 font-sans">
                    <span className="grid size-10 place-items-center rounded-full border border-gold/40 bg-rust/30 text-sm text-gold" lang="hi" aria-hidden>
                      {k.initial}
                    </span>
                    <span>
                      <span className="block text-sm font-semibold text-cream">{t(`landing.keepers.items.${k.key}.title`)}</span>
                      <span className="block text-xs text-gold/80">{t(`landing.keepers.items.${k.key}.role`)}</span>
                    </span>
                  </p>
                </Reveal>
              ))}
            </ul>
          </div>
        </section>

        {/* ---------------------------------------------------------------- stories & guides */}
        <section id="stories" aria-labelledby="stories-title" className="scroll-mt-20 bg-sand/60 px-4 py-24 sm:py-28">
          <div className="mx-auto max-w-6xl">
            <Reveal className="max-w-2xl">
              <Eyebrow>{t("landing.stories.kicker")}</Eyebrow>
              <AccentHeading
                id="stories-title"
                before={t("landing.stories.titleA")}
                accent={t("landing.stories.titleEm")}
                after={t("landing.stories.titleB")}
                className="mt-5 text-4xl sm:text-5xl"
              />
            </Reveal>
            <ul className="mt-12 grid gap-6 md:grid-cols-2">
              {STORIES.map((k, i) => (
                <Reveal as="li" key={k} delay={(i % 2) * 140} className="flex flex-col border border-cocoa/10 bg-cream p-7 shadow-sm transition hover:-translate-y-1 hover:shadow-lg">
                  <span className="self-start rounded-sm bg-rust/10 px-2.5 py-1 font-sans text-[11px] font-semibold text-rust">{t(`landing.stories.items.${k}.tag`)}</span>
                  <h3 className="mt-4 font-heritage text-2xl leading-snug font-bold">{t(`landing.stories.items.${k}.title`)}</h3>
                  <p className="mt-3 flex-1 leading-relaxed text-umber">{t(`landing.stories.items.${k}.body`)}</p>
                  <p className="mt-5 font-sans text-xs font-semibold text-rust">{t(`landing.stories.items.${k}.inApp`)}</p>
                </Reveal>
              ))}
            </ul>
          </div>
        </section>

        {/* ---------------------------------------------------------------- timeline */}
        <section id="timeline" aria-labelledby="timeline-title" className="scroll-mt-20 px-4 py-24 sm:py-28">
          <div className="mx-auto max-w-5xl">
            <Reveal className="text-center">
              <Eyebrow center>{t("landing.timeline.kicker")}</Eyebrow>
              <AccentHeading
                id="timeline-title"
                before={t("landing.timeline.titleA")}
                accent={t("landing.timeline.titleEm")}
                className="mt-5 text-4xl sm:text-5xl"
              />
            </Reveal>
            <ol className="relative mt-16 before:absolute before:top-0 before:bottom-0 before:left-3 before:w-px before:bg-rust/25 md:before:left-1/2">
              {TIMELINE.map((k, i) => {
                const right = i % 2 === 1;
                return (
                  <Reveal as="li" key={k} delay={80} className="relative grid pb-14 pl-10 last:pb-0 md:grid-cols-2 md:pl-0">
                    <span className="absolute top-3 left-3 size-2.5 -translate-x-1/2 rotate-45 bg-rust md:left-1/2" aria-hidden />
                    <div className={right ? "md:col-start-2 md:pl-12" : "md:pr-12 md:text-right"}>
                      <p className="font-heritage text-4xl text-rust/45">{t(`landing.timeline.items.${k}.era`)}</p>
                      <h3 className="mt-1 font-heritage text-lg font-bold">{t(`landing.timeline.items.${k}.title`)}</h3>
                      <p className="mt-2 font-sans text-sm leading-relaxed text-umber">{t(`landing.timeline.items.${k}.body`)}</p>
                    </div>
                  </Reveal>
                );
              })}
            </ol>
          </div>
        </section>

        {/* ---------------------------------------------------------------- community impact + support */}
        <CommunityImpactAndSupport />

        {/* ---------------------------------------------------------------- join */}
        <section aria-labelledby="join-title" className="bg-terracotta px-4 py-24 text-center text-cream sm:py-28">
          <Reveal className="mx-auto max-w-2xl">
            <span className="font-heritage text-3xl text-gold" lang="sa" aria-hidden>
              ॐ
            </span>
            <h2 id="join-title" className="mt-4 font-heritage text-4xl leading-[1.08] font-bold sm:text-5xl">
              {t("landing.join.titleA")}
              <em className="mt-1 block font-normal text-gold italic">{t("landing.join.titleEm")}</em>
            </h2>
            <p className="mt-5 text-lg leading-relaxed text-cream/85">{t("landing.join.lead")}</p>
            <div className="mt-9 flex flex-col justify-center gap-3 font-sans sm:flex-row">
              <Link
                to={startTo}
                className={`inline-flex items-center justify-center gap-2 bg-mustard px-7 py-3.5 ${btnText} text-cocoa hover:bg-gold`}
              >
                {startLabel}
                <ArrowRight className="size-4" aria-hidden />
              </Link>
              {!signedIn && (
                <Link
                  to="/login"
                  className={`inline-flex items-center justify-center border border-cream/50 px-7 py-3.5 ${btnText} text-cream hover:bg-cream/10`}
                >
                  {t("auth.login")}
                </Link>
              )}
            </div>
            <p className="mt-4 font-sans text-xs text-cream/70">{t("landing.join.note")}</p>
          </Reveal>
        </section>
      </main>

      {/* ---------------------------------------------------------------- footer */}
      <footer className="bg-cocoa px-4 pt-16 pb-8 font-sans text-cream/75">
        <div className="mx-auto grid max-w-6xl gap-10 md:grid-cols-[2fr_1fr_1fr_1fr]">
          <div>
            <div className="[&_*]:!text-cream">
              <BrandMark to="/" />
            </div>
            <p className="mt-5 max-w-sm font-garamond text-lg text-cream/80 italic">“{t("landing.footer.tagline")}”</p>
            <p className="mt-2 text-xs text-gold" lang="sa">
              ॥ वसुधैव कुटुम्बकम् ॥
            </p>
          </div>
          <FooterColumn title={t("landing.footer.explore")}>
            {footerLinks.map((l) => (
              <a key={l.href} href={l.href} className="hover:text-gold">
                {l.label}
              </a>
            ))}
          </FooterColumn>
          <FooterColumn title={t("landing.footer.family")}>
            <Link to={startTo} className="hover:text-gold">
              {startLabel}
            </Link>
            <Link to="/privacy" className="hover:text-gold">
              {t("landing.footer.privacy")}
            </Link>
            {!signedIn && (
              <>
                <Link to="/login" className="hover:text-gold">
                  {t("auth.login")}
                </Link>
                <Link to="/register" className="hover:text-gold">
                  {t("auth.createAccount")}
                </Link>
              </>
            )}
          </FooterColumn>
          <FooterColumn title={t("landing.footer.language")}>
            <div className="[&_select]:border-cream/30 [&_select]:bg-cocoa-soft [&_select]:text-cream [&_svg]:text-cream/70">
              <LanguageSwitcher />
            </div>
          </FooterColumn>
        </div>
        <div className="mx-auto mt-14 flex max-w-6xl flex-col items-center justify-between gap-3 border-t border-cream/10 pt-6 text-xs sm:flex-row">
          <p className="flex items-center gap-1.5">
            {t("landing.footer.builtWithA")}
            <Heart className="size-3.5 fill-rust text-rust" aria-hidden />
            <span className="sr-only">{t("landing.footer.love")}</span>
            {t("landing.footer.builtWithB")}
          </p>
          <p className="text-gold/80" lang="sa">
            ॥ परंपरा एवं श्रद्धा ॥
          </p>
        </div>
        {/* GODL-India attribution for the place directory (ADR-0019 §9) */}
        <p className="mx-auto mt-4 max-w-6xl text-center text-xs sm:text-left">{t("landing.footer.dataCredit")}</p>
      </footer>
    </div>
  );
}

function FooterColumn({ title, children }: { title: string; children: ReactNode }) {
  const { i18n } = useTranslation();
  const latin = !i18n.language.startsWith("hi");
  return (
    <div>
      <p className={`font-semibold text-cream ${latin ? "text-[11px] tracking-[0.2em] uppercase" : "text-sm"}`}>{title}</p>
      <div className="mt-4 flex flex-col gap-2 text-sm">{children}</div>
    </div>
  );
}

/* ---------------------------------------------------------------- how it works
 * Three steps, each tied to something that works today: the "Plant your tree" card on this page,
 * sign-up (adding relatives from any profile, approximate dates, photos and documents), and the
 * privacy section below (email invitations with a role, private WhatsApp claim links).
 */
const STEPS: { key: "seed" | "memories" | "invite"; icon: LucideIcon; numeral: string }[] = [
  { key: "seed", icon: Sprout, numeral: "१" },
  { key: "memories", icon: BookOpenText, numeral: "२" },
  { key: "invite", icon: Users, numeral: "३" },
];

function HowItWorks({ startTo, startLabel, btnText }: { startTo: string; startLabel: string; btnText: string }) {
  const { t } = useTranslation();
  const actions = {
    seed: { href: "#plant", label: t("landing.how.steps.seed.action"), internal: false },
    memories: { href: startTo, label: startLabel, internal: true },
    invite: { href: "#trust", label: t("landing.how.steps.invite.action"), internal: false },
  } as const;
  return (
    <section id="how" aria-labelledby="how-title" className="paper-grain scroll-mt-20 bg-cream px-4 py-20 sm:py-24">
      <div className="mx-auto max-w-6xl">
        <Reveal className="mx-auto max-w-2xl text-center">
          <Eyebrow center>{t("landing.how.kicker")}</Eyebrow>
          <AccentHeading id="how-title" before={t("landing.how.titleA")} accent={t("landing.how.titleEm")} className="mt-5 text-4xl sm:text-5xl" />
          <p className="mt-5 text-lg leading-relaxed text-umber">{t("landing.how.lead")}</p>
        </Reveal>
        {/* The connecting thread: vertical on phones, horizontal through the medallions from md up. */}
        <ol className="relative mt-14 grid gap-12 before:absolute before:top-2 before:bottom-2 before:left-7 before:w-px before:bg-rust/30 md:grid-cols-3 md:gap-8 md:before:top-7 md:before:right-[16.66%] md:before:bottom-auto md:before:left-[16.66%] md:before:h-px md:before:w-auto">
          {STEPS.map(({ key, icon: Icon, numeral }, i) => {
            const a = actions[key];
            const linkClass = "mt-5 inline-flex items-center gap-1.5 rounded text-sm font-semibold text-rust underline-offset-4 hover:underline";
            return (
              <Reveal as="li" key={key} delay={i * 140} className="relative grid grid-cols-[3.5rem_1fr] content-start gap-x-5 md:grid-cols-1 md:text-center">
                <span className="relative z-10 grid size-14 place-items-center rounded-full border border-rust/40 bg-cream text-rust shadow-sm md:mx-auto" aria-hidden>
                  <Icon className="size-6" />
                  <span className="absolute -top-1.5 -right-1.5 grid size-7 place-items-center rounded-full bg-rust font-heritage text-sm leading-none text-cream" lang="hi">
                    {numeral}
                  </span>
                </span>
                <div className="md:mt-6">
                  <p className="text-xs font-semibold text-rust">{t("landing.how.stepN", { n: i + 1 })}</p>
                  <h3 className="mt-1 font-heritage text-2xl font-bold">{t(`landing.how.steps.${key}.title`)}</h3>
                  <p className="mx-auto mt-3 max-w-sm leading-relaxed text-umber">{t(`landing.how.steps.${key}.body`)}</p>
                  {a.internal ? (
                    <Link to={a.href} className={linkClass}>
                      {a.label}
                      <ArrowRight className="size-4" aria-hidden />
                    </Link>
                  ) : (
                    <a href={a.href} className={linkClass}>
                      {a.label}
                      <ArrowRight className="size-4" aria-hidden />
                    </a>
                  )}
                </div>
              </Reveal>
            );
          })}
        </ol>
        <Reveal className="mt-14 text-center" delay={100}>
          <Link to={startTo} className={`inline-flex items-center gap-2 bg-cocoa px-7 py-3.5 ${btnText} text-cream hover:bg-cocoa-soft`}>
            {startLabel}
            <ArrowRight className="size-4" aria-hidden />
          </Link>
        </Reveal>
      </div>
    </section>
  );
}

/* ---------------------------------------------------------------- kept in trust
 * Every promise here is enforced by the server today (backend/app/authz/privacy.py and
 * permissions.py; docs/security/privacy-model.md). Change the copy only together with the code.
 */
const PROMISES: { key: "private" | "living" | "control" | "yours"; icon: LucideIcon }[] = [
  { key: "private", icon: Lock },
  { key: "living", icon: EyeOff },
  { key: "control", icon: UserCog },
  { key: "yours", icon: Download },
];

function KeptInTrust({ startTo, startLabel, btnText }: { startTo: string; startLabel: string; btnText: string }) {
  const { t, i18n } = useTranslation();
  const hindi = i18n.language.startsWith("hi");
  return (
    <section id="trust" aria-labelledby="trust-title" className="scroll-mt-20 bg-cream px-4 pb-20 sm:pb-24">
      <div className="paper-grain-dark mx-auto max-w-6xl overflow-hidden rounded-3xl bg-cocoa px-6 py-14 text-cream shadow-2xl shadow-cocoa/20 sm:px-12 sm:py-16">
        <Reveal className="mx-auto max-w-2xl text-center">
          <span className="mx-auto grid size-14 place-items-center rounded-full border border-gold/40 bg-cocoa-soft text-gold" aria-hidden>
            <ShieldCheck className="size-7" />
          </span>
          {/* In Hindi the kicker below already says विश्वास; the word would only repeat. */}
          {!hindi && (
            <p className="mt-4 font-heritage text-2xl text-gold" lang="hi">
              ॥ विश्वास ॥
            </p>
          )}
          <div className="mt-3">
            <Eyebrow tone="gold" center>
              {t("landing.trust.kicker")}
            </Eyebrow>
          </div>
          <AccentHeading id="trust-title" before={t("landing.trust.titleA")} accent={t("landing.trust.titleEm")} tone="gold" className="mt-5 text-4xl sm:text-5xl" />
          <p className="mt-5 text-lg leading-relaxed text-cream/80">{t("landing.trust.lead")}</p>
        </Reveal>
        <ul className="mt-12 grid gap-x-10 gap-y-8 md:grid-cols-2">
          {PROMISES.map(({ key, icon: Icon }, i) => (
            <Reveal as="li" key={key} delay={(i % 2) * 120} className="flex gap-4 border-t border-cream/10 pt-6">
              <span className="grid size-11 shrink-0 place-items-center rounded-full bg-cream/10 text-gold" aria-hidden>
                <Icon className="size-5" />
              </span>
              <div>
                <h3 className="font-heritage text-xl font-bold text-cream">{t(`landing.trust.items.${key}.title`)}</h3>
                <p className="mt-2 leading-relaxed text-cream/75">{t(`landing.trust.items.${key}.body`)}</p>
              </div>
            </Reveal>
          ))}
        </ul>
        <Reveal className="mt-12 text-center" delay={80}>
          <Link to={startTo} className={`inline-flex items-center gap-2 bg-cream px-7 py-3.5 ${btnText} text-cocoa hover:bg-white`}>
            {startLabel}
            <ArrowRight className="size-4" aria-hidden />
          </Link>
        </Reveal>
      </div>
    </section>
  );
}


/**
 * Each environment variable must point to a hosted checkout with that amount already
 * configured server-side. This site never collects card or UPI credentials. Do not
 * supply a generic payment link that accepts arbitrary client-selected amounts.
 */
const DONATION_LINKS: Record<number, string | undefined> = {
  10: import.meta.env.VITE_DONATION_LINK_10,
  50: import.meta.env.VITE_DONATION_LINK_50,
  100: import.meta.env.VITE_DONATION_LINK_100,
  1000: import.meta.env.VITE_DONATION_LINK_1000,
  10000: import.meta.env.VITE_DONATION_LINK_10000,
};

function safeDonationLink(amount: number): string | null {
  return safeHostedDonationLink(DONATION_LINKS[amount]);
}

function CommunityImpactAndSupport() {
  const { t, i18n } = useTranslation();
  const hindi = i18n.language.startsWith("hi");
  const [amount, setAmount] = useState<number>(100);
  const [isOtherAmount, setIsOtherAmount] = useState(false);
  const [otherAmountText, setOtherAmountText] = useState("");
  const impact = useQuery({
    queryKey: ["public", "site-impact"],
    queryFn: () => api.get<SiteImpactOut>("/public/site-impact"),
    staleTime: 5 * 60_000,
    retry: false,
  });
  const enteredAmount = parseVoluntaryAmount(otherAmountText);
  // A variable-amount hosted page must ask donors to enter and confirm the amount again.
  // We do not send an untrusted number through URL parameters or declare a payment successful.
  const checkout = isOtherAmount
    ? enteredAmount !== null ? safeHostedDonationLink(import.meta.env.VITE_DONATION_LINK_CUSTOM) : null
    : safeDonationLink(amount);
  const number = (value: number) => new Intl.NumberFormat(hindi ? "hi-IN" : "en-IN").format(value);

  return (
    <section id="support" aria-labelledby="support-title" className="scroll-mt-20 bg-sand px-4 py-20 sm:py-24">
      <div className="mx-auto max-w-6xl">
        <Reveal className="text-center">
          <Eyebrow center>{t("landing.support.kicker")}</Eyebrow>
          <h2 id="support-title" className="mt-5 font-heritage text-4xl font-bold sm:text-5xl">
            {t("landing.support.heading")}
          </h2>
          <p className="mx-auto mt-4 max-w-2xl text-umber">{t("landing.support.intro")}</p>
        </Reveal>
        <div className="mt-10 grid gap-5 md:grid-cols-2">
          <div className="border border-cocoa/10 bg-cream p-7 sm:p-9">
            <h3 className="font-heritage text-2xl font-bold">{t("landing.support.impactTitle")}</h3>
            <dl className="mt-6 grid grid-cols-2 gap-4">
              <div>
                <dt className="text-sm text-umber">{t("landing.support.families")}</dt>
                <dd className="mt-1 font-heritage text-4xl text-rust">
                  {impact.data ? number(impact.data.family_trees) : "—"}
                </dd>
              </div>
              {/* Null means measurement is off or unavailable: show nothing rather than a dash or a false zero. */}
              {impact.data?.unique_visitors_30d != null && (
                <div>
                  <dt className="text-sm text-umber">{t("landing.support.visitors")}</dt>
                  <dd className="mt-1 font-heritage text-4xl text-rust">{number(impact.data.unique_visitors_30d)}</dd>
                </div>
              )}
            </dl>
            <p className="mt-5 text-xs leading-relaxed text-umber">{t("landing.support.countNote")}</p>
          </div>
          <div className="border border-cocoa/10 bg-cream p-7 sm:p-9">
            <h3 className="font-heritage text-2xl font-bold">{t("landing.support.donateTitle")}</h3>
            <p className="mt-2 text-sm text-umber">{t("landing.support.donateLead")}</p>
            <fieldset className="mt-6">
              <legend className="mb-3 text-sm font-semibold">{t("landing.support.chooseAmount")}</legend>
              <div className="flex flex-wrap gap-2">
                {DONATION_AMOUNTS.map((option) => (
                  <label key={option} className={`cursor-pointer border px-3 py-2 text-sm font-semibold transition has-[:focus-visible]:outline-2 has-[:focus-visible]:outline-offset-2 has-[:focus-visible]:outline-rust ${!isOtherAmount && amount === option ? "border-rust bg-rust text-white" : "border-cocoa/20 hover:border-rust"}`}>
                    <input
                      type="radio"
                      name="donation-amount"
                      value={option}
                      checked={!isOtherAmount && amount === option}
                      onChange={() => { setAmount(option); setIsOtherAmount(false); }}
                      className="sr-only"
                    />
                    ₹{number(option)}
                  </label>
                ))}
                <label className={`cursor-pointer border px-3 py-2 text-sm font-semibold transition has-[:focus-visible]:outline-2 has-[:focus-visible]:outline-offset-2 has-[:focus-visible]:outline-rust ${isOtherAmount ? "border-rust bg-rust text-white" : "border-cocoa/20 hover:border-rust"}`}>
                  <input
                    type="radio"
                    name="donation-amount"
                    checked={isOtherAmount}
                    onChange={() => setIsOtherAmount(true)}
                    className="sr-only"
                  />
                  {t("landing.support.otherAmount")}
                </label>
              </div>
              {isOtherAmount && (
                <div className="mt-4">
                  <label htmlFor="voluntary-donation-amount" className="block text-sm font-semibold">
                    {t("landing.support.enterAmount")}
                  </label>
                  <div className="mt-2 flex max-w-xs items-center border border-cocoa/30 bg-white focus-within:border-rust">
                    <span className="px-3 text-lg text-umber" aria-hidden>₹</span>
                    <input
                      id="voluntary-donation-amount"
                      type="text"
                      inputMode="numeric"
                      autoComplete="off"
                      maxLength={6}
                      value={otherAmountText}
                      onChange={(event) => setOtherAmountText(event.target.value)}
                      aria-invalid={otherAmountText.length > 0 && enteredAmount === null}
                      aria-describedby="voluntary-donation-note"
                      placeholder="250"
                      className="w-full min-w-0 bg-transparent px-2 py-3 outline-none"
                    />
                  </div>
                  <p id="voluntary-donation-note" className="mt-2 text-xs text-umber" role="status">
                    {otherAmountText && enteredAmount === null
                      ? t("landing.support.invalidAmount")
                      : t("landing.support.otherAmountNote")}
                  </p>
                </div>
              )}
            </fieldset>
            {checkout ? (
              <a
                href={checkout}
                target="_blank"
                rel="noopener noreferrer"
                className="mt-6 inline-flex items-center justify-center gap-2 bg-cocoa px-6 py-3 text-sm font-semibold text-cream hover:bg-cocoa-soft"
              >
                <Heart className="size-4" aria-hidden />
                {isOtherAmount ? t("landing.support.continueCustom") : t("landing.support.donateAmount", { amount: number(amount) })}
              </a>
            ) : (
              <p className="mt-6 text-sm text-umber" role="status">
                {isOtherAmount && enteredAmount === null
                  ? t("landing.support.enterValidAmount")
                  : t("landing.support.notConfigured")}
              </p>
            )}
            {checkout && isOtherAmount && enteredAmount !== null && (
              <p className="mt-3 text-xs font-medium text-umber">
                {t("landing.support.confirmCustom", { amount: number(enteredAmount) })}
              </p>
            )}
            <p className="mt-3 text-xs text-umber">{t("landing.support.paymentNote")}</p>
          </div>
        </div>
      </div>
    </section>
  );
}
