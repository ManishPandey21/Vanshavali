import { useRef, type ReactNode, type RefObject } from "react";
import { useTranslation } from "react-i18next";
import { FileDown, Image as ImageIcon, Printer } from "lucide-react";
import { downloadPng, downloadSvg, printChart } from "../../lib/exportChart";
import { Button } from "../ui/Button";

export interface LegendItem {
  key: string;
  label: string;
  color: string;
  pattern?: "dashed" | "hidden";
}

/**
 * Shared frame for charts: title and text summary, static export (SVG / PNG / print-to-PDF),
 * a readable legend and the text alternative (a table or list). Charts are never visual-only.
 */
export function ChartFrame({
  title,
  summary,
  filename,
  legend = [],
  controls,
  alternative,
  children,
  svgRef,
}: {
  title: string;
  summary?: string;
  filename: string;
  legend?: LegendItem[];
  controls?: ReactNode;
  alternative?: ReactNode;
  children: ReactNode;
  svgRef?: RefObject<SVGSVGElement>;
}) {
  const { t } = useTranslation();
  const fallback = useRef<HTMLDivElement>(null);
  const svg = () => svgRef?.current ?? fallback.current?.querySelector("svg") ?? null;
  return (
    <section className="min-w-0 space-y-3 print:space-y-1" aria-label={title}>
      {controls && <div className="no-print flex flex-wrap items-end gap-3">{controls}</div>}
      {summary && (
        <p className="text-sm text-ink-muted" aria-live="polite">
          {summary}
        </p>
      )}
      <div ref={fallback} className="overflow-auto rounded-xl border border-stone-200 bg-white">
        {children}
      </div>
      {legend.length > 0 && (
        <ul className="flex flex-wrap gap-x-4 gap-y-1 text-sm" aria-label={t("viz.legend")}>
          {legend.map((l) => (
            <li key={l.key} className="inline-flex items-center gap-1.5">
              <span
                className="inline-block size-3.5 rounded-sm border"
                style={{ background: l.pattern === "dashed" ? "transparent" : l.color, borderColor: l.color, borderStyle: l.pattern === "dashed" ? "dashed" : "solid" }}
                aria-hidden
              />
              {l.label}
            </li>
          ))}
        </ul>
      )}
      <div className="no-print flex flex-wrap gap-2">
        <Button size="sm" variant="secondary" icon={<FileDown className="size-4" aria-hidden />} onClick={() => { const s = svg(); if (s) downloadSvg(s, filename); }}>
          {t("viz.export.svg")}
        </Button>
        <Button size="sm" variant="secondary" icon={<ImageIcon className="size-4" aria-hidden />} onClick={() => { const s = svg(); if (s) void downloadPng(s, filename); }}>
          {t("viz.export.png")}
        </Button>
        <Button size="sm" variant="secondary" icon={<Printer className="size-4" aria-hidden />} onClick={printChart}>
          {t("viz.export.print")}
        </Button>
      </div>
      {alternative && (
        <details className="no-print text-sm">
          <summary className="cursor-pointer text-kumkum-800">{t("viz.textAlternative")}</summary>
          <div className="mt-2 max-h-96 overflow-auto">{alternative}</div>
        </details>
      )}
    </section>
  );
}
