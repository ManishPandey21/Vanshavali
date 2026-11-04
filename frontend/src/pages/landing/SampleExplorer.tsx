import { useMemo, useState } from "react";
import { Link } from "react-router-dom";
import { useTranslation } from "react-i18next";
import { ArrowRight, Hand, Lock, ShieldCheck, Sparkles } from "lucide-react";
import { TreeChart } from "../../components/tree/TreeChart";
import { describeChain, hindiKinshipTerm } from "../../lib/kinship";
import { lifespan } from "../../lib/dates";
import { GrowingTree } from "./GrowingTree";
import { SAMPLE_PEOPLE, VIEWER_ID, sampleGraph } from "./sampleFamily";

/**
 * The family-tree figure on the landing page: watch the Sharma family grow (the animation), or
 * explore it yourself in the same tree viewer families use, as Aarav. Static, fictional data only:
 * this never calls the API.
 */
export function FamilyShowcase({ startTo, startLabel }: { startTo: string; startLabel: string }) {
  const { t } = useTranslation();
  const [mode, setMode] = useState<"watch" | "explore">("watch");
  const tab = (m: typeof mode, label: string, Icon: typeof Sparkles) => (
    <button
      type="button"
      aria-pressed={mode === m}
      onClick={() => setMode(m)}
      className={`inline-flex min-h-10 items-center gap-1.5 rounded-full px-4 py-2 text-sm font-semibold transition-colors ${
        mode === m ? "bg-cocoa text-cream" : "text-cocoa hover:bg-cream"
      }`}
    >
      <Icon className="size-4" aria-hidden />
      {label}
    </button>
  );
  return (
    <div>
      <div role="group" aria-label={t("landing.sample.modeLabel")} className="mx-auto mb-4 flex w-fit gap-1 rounded-full border border-cocoa/15 bg-white/70 p-1 font-sans">
        {tab("watch", t("landing.sample.watch"), Sparkles)}
        {tab("explore", t("landing.sample.explore"), Hand)}
      </div>
      {mode === "watch" ? <GrowingTree /> : <SampleExplorer startTo={startTo} startLabel={startLabel} />}
    </div>
  );
}

function SampleExplorer({ startTo, startLabel }: { startTo: string; startLabel: string }) {
  const { t, i18n } = useTranslation();
  const hindi = i18n.language.startsWith("hi");
  const graph = useMemo(() => sampleGraph(hindi), [hindi]);
  const [collapsed, setCollapsed] = useState<Set<string>>(new Set());
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const selected = SAMPLE_PEOPLE.find((p) => p.id === selectedId) ?? null;
  const viewer = SAMPLE_PEOPLE.find((p) => p.id === VIEWER_ID)!;
  const viewerName = hindi ? viewer.hi : viewer.en;

  return (
    <div className="overflow-hidden rounded-2xl border border-cocoa/10 bg-white font-sans shadow-2xl shadow-cocoa/15">
      <div className="flex flex-wrap items-center justify-between gap-2 border-b border-cocoa/10 bg-cream px-4 py-3">
        <p className="font-heritage text-lg font-bold text-cocoa">{t("landing.archive.tree.title")}</p>
        <p className="inline-flex items-center gap-1.5 rounded-full bg-sand px-3 py-1 text-xs font-semibold text-cocoa">
          <ShieldCheck className="size-3.5 text-rust" aria-hidden />
          {t("landing.sample.viewingAs", { name: viewerName })}
        </p>
      </div>

      <div className="p-3">
        <TreeChart
          graph={graph}
          onOpen={setSelectedId}
          collapsed={collapsed}
          onToggleCollapse={(id) =>
            setCollapsed((prev) => {
              const n = new Set(prev);
              if (n.has(id)) n.delete(id);
              else n.add(id);
              return n;
            })
          }
          youId={VIEWER_ID}
          selectedId={selectedId}
          heightClass="h-[400px] sm:h-[440px]"
          minOpenScale={0.72}
        />
      </div>

      {/* What the visitor learns about the person they chose, announced to screen readers. */}
      <section aria-live="polite" aria-label={t("landing.sample.panelLabel")} className="border-t border-cocoa/10 bg-cream/60 px-5 py-5">
        {!selected ? (
          <p className="flex items-start gap-2 text-umber">
            <Hand className="mt-0.5 size-4 shrink-0 text-rust" aria-hidden />
            {t("landing.sample.prompt", { name: viewerName })}
          </p>
        ) : (
          <PersonPanel personId={selected.id} viewerName={viewerName} />
        )}
        <p className="mt-4 flex items-start gap-2 text-xs text-umber">
          <Lock className="mt-0.5 size-3.5 shrink-0 text-rust" aria-hidden />
          {t("landing.sample.privateNote")}
        </p>
        <Link to={startTo} className="mt-4 inline-flex items-center gap-1.5 text-sm font-semibold text-rust underline-offset-4 hover:underline">
          {startLabel}
          <ArrowRight className="size-4" aria-hidden />
        </Link>
      </section>
    </div>
  );
}

function PersonPanel({ personId, viewerName }: { personId: string; viewerName: string }) {
  const { t, i18n } = useTranslation();
  const lang = i18n.language;
  const hindi = lang.startsWith("hi");
  const p = SAMPLE_PEOPLE.find((x) => x.id === personId)!;
  const name = hindi ? p.hi : p.en;
  const other = hindi ? p.en : p.hi;
  const isViewer = p.id === VIEWER_ID;
  const term = hindiKinshipTerm(p.kin);
  const reading = describeChain(p.kin, lang);
  const years = lifespan(
    {
      birth_date: p.born ? { precision: p.born.circa ? "circa" : "exact", year: p.born.year } : null,
      death_date: p.died ? { precision: p.died.circa ? "circa" : "exact", year: p.died.year } : null,
      profile_status: p.status,
    },
    t,
  );

  return (
    <div>
      <h3 className="font-heritage text-2xl font-bold text-cocoa">
        {name}{" "}
        <span className="font-sans text-base font-normal text-umber" lang={hindi ? "en" : "hi"}>
          {other}
        </span>
      </h3>
      {isViewer ? (
        <p className="mt-2 text-cocoa">{t("landing.sample.self", { name: viewerName })}</p>
      ) : (
        <p className="mt-2 text-cocoa">
          <span className="text-umber">{t("landing.sample.relationTo", { name: viewerName })}</span>{" "}
          {term && (
            <strong className="font-heritage text-xl text-rust" lang="hi">
              {term}
            </strong>
          )}{" "}
          {reading && <span className="text-umber">({reading})</span>}
        </p>
      )}
      {p.status === "deceased" ? (
        <>
          {years && <p className="mt-2 text-sm font-semibold text-umber">{years}</p>}
          {p.story && <p className="mt-1 font-garamond text-lg text-cocoa italic">{hindi ? p.story.hi : p.story.en}</p>}
        </>
      ) : isViewer ? (
        <p className="mt-2 text-sm text-umber">
          {years && <span className="font-semibold">{years} · </span>}
          {t("landing.sample.selfNote")}
        </p>
      ) : (
        <p className="mt-2 flex items-start gap-2 text-sm text-umber">
          <Lock className="mt-0.5 size-3.5 shrink-0 text-rust" aria-hidden />
          {t("landing.sample.livingNote", { name })}
        </p>
      )}
    </div>
  );
}
