import { useCallback, useEffect, useRef, useState, type CSSProperties } from "react";
import { useTranslation } from "react-i18next";
import { RotateCcw } from "lucide-react";

/**
 * The landing page's family tree, drawn the way a family builds one: the grandparents, their
 * marriage, the line down to their sons, the daughters-in-law, the grandchildren, and finally the
 * kinship the app can name, traced along the tree (Suresh is Aarav's dādā). It plays once when it scrolls into view and
 * can be replayed. Visitors who prefer reduced motion (or browsers without IntersectionObserver)
 * get the finished tree; the hiding CSS lives in index.css under .gt-* and only applies with
 * prefers-reduced-motion: no-preference.
 *
 * The family is the illustrative Sharma family also used by the demo seed data.
 */

const W = 150; // card width (SVG units)
const H = 64; // card height
const LAST_STAGE = 8;
/** When each stage starts, in ms after the tree comes into view (index = stage - 1). */
const STAGE_AT = [0, 600, 1300, 2100, 2800, 3500, 4300, 5400];

type Person = {
  id: string;
  en: string;
  hi: string;
  x: number;
  y: number;
  stage: number;
  years?: string; // shown only for those who have passed away; living relatives stay private
};

const PEOPLE: Person[] = [
  { id: "suresh", en: "Suresh Sharma", hi: "सुरेश शर्मा", x: 235, y: 30, stage: 1, years: "1938–2011" },
  { id: "kamala", en: "Kamala Sharma", hi: "कमला शर्मा", x: 415, y: 30, stage: 2, years: "1942–2019" },
  { id: "ramesh", en: "Ramesh Sharma", hi: "रमेश शर्मा", x: 20, y: 190, stage: 4 },
  { id: "mahesh", en: "Mahesh Sharma", hi: "महेश शर्मा", x: 450, y: 190, stage: 4 },
  { id: "sunita", en: "Sunita Sharma", hi: "सुनीता शर्मा", x: 200, y: 190, stage: 5 },
  { id: "geeta", en: "Geeta Sharma", hi: "गीता शर्मा", x: 630, y: 190, stage: 5 },
  { id: "aarav", en: "Aarav Sharma", hi: "आरव शर्मा", x: 30, y: 350, stage: 7 },
  { id: "anaya", en: "Anaya Sharma", hi: "अनया शर्मा", x: 190, y: 350, stage: 7 },
  { id: "kabir", en: "Kabir Sharma", hi: "कबीर शर्मा", x: 540, y: 350, stage: 7 },
];

/** Connecting lines; "marriage" lines are drawn double, as in the tree viewer. */
const LINES: { d: string; stage: number; marriage?: boolean }[] = [
  { d: "M385 62 H415", stage: 2, marriage: true },
  { d: "M400 62 V135", stage: 3 },
  { d: "M400 135 H95 V190", stage: 3 },
  { d: "M400 135 H525 V190", stage: 3 },
  { d: "M170 222 H200", stage: 5, marriage: true },
  { d: "M600 222 H630", stage: 5, marriage: true },
  { d: "M185 222 V310", stage: 6 },
  { d: "M185 310 H105 V350", stage: 6 },
  { d: "M185 310 H265 V350", stage: 6 },
  { d: "M615 222 V350", stage: 6 },
];

/** The line the kinship is traced along: Aarav, up through his father Ramesh, to Suresh. */
const KIN_PATH = "M105 350 V310 H185 V222 H170 M95 190 V135 H400 V62 H385";
const KIN = new Set(["suresh", "ramesh", "aarav"]);

function startsFinished() {
  return (
    typeof window === "undefined" ||
    typeof IntersectionObserver === "undefined" ||
    !!window.matchMedia?.("(prefers-reduced-motion: reduce)").matches
  );
}

export function GrowingTree() {
  const { t, i18n } = useTranslation();
  const hindi = i18n.language.startsWith("hi");
  const ref = useRef<HTMLDivElement>(null);
  const timers = useRef<{ ids: number[] }>({ ids: [] });
  const [stage, setStage] = useState(() => (startsFinished() ? LAST_STAGE : 0));

  const play = useCallback(() => {
    timers.current.ids.forEach(window.clearTimeout);
    setStage(0);
    timers.current.ids = STAGE_AT.map((at, i) => window.setTimeout(() => setStage(i + 1), at + 120));
  }, []);

  useEffect(() => {
    const el = ref.current;
    if (!el || startsFinished()) return;
    const io = new IntersectionObserver(
      (entries) => {
        if (entries.some((e) => e.isIntersecting)) {
          io.disconnect();
          play();
        }
      },
      { threshold: 0.35 },
    );
    io.observe(el);
    const pending = timers.current;
    return () => {
      io.disconnect();
      pending.ids.forEach(window.clearTimeout);
    };
  }, [play]);

  const on = (s: number) => (stage >= s ? " is-on" : "");
  const shown = PEOPLE.filter((p) => stage >= p.stage).length;
  const generations = stage >= 7 ? 3 : stage >= 4 ? 2 : stage >= 1 ? 1 : 0;
  const kin = stage >= LAST_STAGE;

  return (
    <div className="overflow-hidden rounded-2xl border border-cocoa/10 bg-white shadow-2xl shadow-cocoa/15">
      <div className="flex items-center gap-2 border-b border-cocoa/10 bg-cream px-4 py-2.5" aria-hidden>
        <span className="size-2.5 rounded-full bg-rust/40" />
        <span className="size-2.5 rounded-full bg-gold/60" />
        <span className="size-2.5 rounded-full bg-leaf-700/30" />
        <span className="ml-3 truncate font-sans text-xs text-umber">{t("landing.archive.tree.chrome")}</span>
      </div>

      <div className="flex flex-wrap items-center justify-between gap-x-4 gap-y-2 border-b border-cocoa/10 px-4 py-3 font-sans">
        <p className="font-heritage text-lg font-bold text-cocoa">{t("landing.archive.tree.title")}</p>
        <div className="flex items-center gap-4 text-xs text-umber">
          <span aria-hidden className="tabular-nums">
            <strong className="text-sm text-cocoa">{shown}</strong> {t("landing.archive.tree.people", { count: shown })} ·{" "}
            <strong className="text-sm text-cocoa">{generations}</strong> {t("landing.archive.tree.generations", { count: generations })}
          </span>
          <button
            type="button"
            onClick={play}
            className="inline-flex items-center gap-1.5 rounded-full border border-cocoa/20 px-3 py-1.5 font-semibold text-cocoa hover:bg-sand"
          >
            <RotateCcw className="size-3.5" aria-hidden />
            {t("landing.archive.tree.replay")}
          </button>
        </div>
      </div>

      {/* narrow screens scroll the tree sideways rather than shrinking names past legibility */}
      <div className="overflow-x-auto bg-[radial-gradient(circle,rgba(107,90,74,0.12)_1px,transparent_1px)] bg-[length:18px_18px]">
        <div ref={ref} role="img" aria-label={t("landing.archive.alt")} className="min-w-[560px] px-2 py-3">
          <svg viewBox="0 0 800 430" className="block h-auto w-full font-sans" aria-hidden>
            {LINES.map((l, i) => (
              <path
                key={i}
                d={l.d}
                pathLength={1}
                fill="none"
                stroke="#a08868"
                strokeWidth={l.marriage ? 5 : 2}
                className={`gt-line${on(l.stage)}`}
                style={{ transitionDelay: `${(i % 3) * 120}ms` } as CSSProperties}
              />
            ))}
            {LINES.filter((l) => l.marriage).map((l, i) => (
              // the inner white stroke turns the thick line into a double "married" line
              <path key={`m${i}`} d={l.d} pathLength={1} fill="none" stroke="#fff" strokeWidth={1.5} className={`gt-line${on(l.stage)}`} />
            ))}

            <path
              d={KIN_PATH}
              pathLength={1}
              fill="none"
              stroke="#a8482a"
              strokeWidth={4}
              strokeLinecap="round"
              strokeLinejoin="round"
              className={`gt-kin${kin ? " is-on" : ""}`}
            />

            {PEOPLE.map((p, i) => {
              const primary = hindi ? p.hi : p.en;
              const secondary = hindi ? p.en : p.hi;
              const lit = kin && KIN.has(p.id);
              return (
                <g
                  key={p.id}
                  className={`gt-node${on(p.stage)}`}
                  style={{ transitionDelay: `${(i % 2) * 140}ms` } as CSSProperties}
                >
                  <rect
                    x={p.x}
                    y={p.y}
                    width={W}
                    height={H}
                    rx={8}
                    fill={lit ? "#fbe3d6" : "#fffdf8"}
                    stroke={lit ? "#a8482a" : "#d9cbb4"}
                    strokeWidth={lit ? 2.5 : 1.5}
                    className="gt-card"
                  />
                  <rect x={p.x} y={p.y + 8} width={4} height={H - 16} rx={2} fill={p.years ? "#6b5a4a" : "#a8482a"} />
                  <text x={p.x + 14} y={p.y + 24} fontSize={hindi ? 17 : 15.5} fontWeight={700} fill="#2b231c" lang={hindi ? "hi" : "en"}>
                    {primary}
                  </text>
                  <text x={p.x + 14} y={p.y + 41} fontSize={12.5} fill="#6b5a4a" lang={hindi ? "en" : "hi"}>
                    {secondary}
                  </text>
                  {p.years ? (
                    <text x={p.x + 14} y={p.y + 56} fontSize={12} fill="#6b5a4a">
                      {p.years}
                    </text>
                  ) : (
                    <g fill="#a8482a">
                      {/* a small padlock: living relatives' details stay within the family */}
                      <rect x={p.x + 14} y={p.y + 49} width={8} height={7} rx={1.5} />
                      <path d={`M${p.x + 15.5} ${p.y + 49.5} v-2 a2.5 2.5 0 0 1 5 0 v2`} fill="none" stroke="#a8482a" strokeWidth={1.4} />
                      <text x={p.x + 27} y={p.y + 56} fontSize={12}>
                        {t("landing.archive.tree.living")}
                      </text>
                    </g>
                  )}
                </g>
              );
            })}
          </svg>
        </div>
      </div>
      <p
        className={`gt-node mx-auto my-4 w-fit max-w-[90%] rounded-full bg-rust px-4 py-1.5 text-center font-sans text-sm text-cream${kin ? " is-on" : ""}`}
        aria-hidden
      >
        {t("landing.archive.tree.kin")}
      </p>
    </div>
  );
}
