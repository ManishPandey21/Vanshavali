import { useState } from "react";
import { useTranslation } from "react-i18next";
import { Download, Film, Trash2, X } from "lucide-react";
import type { ChartType, RenderJobOut, RenderSettings } from "../../api/types";
import { ApiError, saveBlob } from "../../api/client";
import { fetchRenderArtifact, useCancelRenderJob, useCreateRenderJob, useDeleteRenderJob, useRenderJobs, useRenderPoster } from "../../api/hooks/viz";
import { useTreeCtx } from "../../lib/tree-context";
import { Button } from "../ui/Button";
import { ErrorAlert, LiveRegion } from "../ui/feedback";
import { Field, Select, TextInput } from "../ui/form";
import { Badge } from "../ui/Badge";

type Theme = NonNullable<RenderSettings["theme"]>;
const THEMES: Theme[] = ["heritage", "dusk", "minimal"];

/**
 * Animated export (Remotion, rendered on the server's render worker). The video is built from
 * what *you* can see; it is an extra — the chart and its text alternative remain the accessible view.
 */
export function AnimatedExport({ chartType, settings, disabledReason }: { chartType: ChartType; settings: Partial<RenderSettings>; disabledReason?: string | null }) {
  const { t } = useTranslation();
  const { treeId } = useTreeCtx();
  const jobs = useRenderJobs(treeId);
  const create = useCreateRenderJob(treeId);
  const [theme, setTheme] = useState<Theme>("heritage");
  const [title, setTitle] = useState("");
  const [output, setOutput] = useState<"poster" | "mp4">("poster");
  const mine = (jobs.data ?? []).filter((j) => j.chart_type === chartType && j.mine).slice(0, 4);
  const unavailable = create.error instanceof ApiError && create.error.code === "render_unavailable";
  const submit = () =>
    create.mutate({ chart_type: chartType, output, settings: { ...settings, theme, title: title.trim() || null } as RenderSettings });
  return (
    <section className="card space-y-3 p-4" aria-labelledby={`anim-${chartType}`}>
      <h2 id={`anim-${chartType}`} className="flex items-center gap-2 font-semibold">
        <Film className="size-4" aria-hidden /> {t("render.title")}
      </h2>
      <p className="text-sm text-ink-muted">{t("render.hint")}</p>
      <div className="grid grid-cols-1 gap-3">
        <Field label={t("render.output")}>
          {(p) => (
            <Select {...p} value={output} onChange={(e) => setOutput(e.target.value as "poster" | "mp4")}>
              <option value="poster">{t("render.outputPoster")}</option>
              <option value="mp4">{t("render.outputMp4")}</option>
            </Select>
          )}
        </Field>
        <Field label={t("render.theme")}>
          {(p) => (
            <Select {...p} value={theme} onChange={(e) => setTheme(e.target.value as Theme)}>
              {THEMES.map((th) => (
                <option key={th} value={th}>
                  {t(`render.themes.${th}`)}
                </option>
              ))}
            </Select>
          )}
        </Field>
        <Field label={t("render.videoTitle")} hint={t("render.videoTitleHint")}>
          {(p) => <TextInput {...p} value={title} maxLength={120} onChange={(e) => setTitle(e.target.value)} />}
        </Field>
      </div>
      {disabledReason && <p className="text-sm text-ink-muted">{disabledReason}</p>}
      <Button icon={<Film className="size-4" aria-hidden />} onClick={submit} loading={create.isPending} disabled={!!disabledReason}>
        {output === "poster" ? t("render.createPreview") : t("render.createVideo")}
      </Button>
      {unavailable ? <p role="alert" className="text-sm text-ink-muted">{t("render.unavailable")}</p> : <ErrorAlert error={create.error} />}
      {mine.length > 0 && (
        <ul className="space-y-3" aria-label={t("render.recent")}>
          {mine.map((j) => (
            <RenderJobRow key={j.id} job={j} />
          ))}
        </ul>
      )}
    </section>
  );
}

function RenderJobRow({ job }: { job: RenderJobOut }) {
  const { t } = useTranslation();
  const { treeId } = useTreeCtx();
  const poster = (job.artifacts ?? []).find((a) => a.kind === "poster_png");
  const video = (job.artifacts ?? []).find((a) => a.kind === "video_mp4");
  const img = useRenderPoster(treeId, job.id, poster?.id);
  const cancel = useCancelRenderJob(treeId);
  const del = useDeleteRenderJob(treeId);
  const [downloading, setDownloading] = useState(false);
  const [err, setErr] = useState<unknown>(null);
  const active = job.status === "queued" || job.status === "running";
  const download = async () => {
    if (!video) return;
    setDownloading(true);
    setErr(null);
    try {
      const { blob, filename } = await fetchRenderArtifact(treeId, job.id, video.id);
      saveBlob(blob, filename ?? `vanshavali-${job.chart_type}.mp4`);
    } catch (e) {
      setErr(e);
    } finally {
      setDownloading(false);
    }
  };
  const tone = job.status === "succeeded" ? "green" : job.status === "failed" ? "red" : "stone";
  return (
    <li className="rounded-lg border border-stone-200 p-3">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <span className="flex items-center gap-2 text-sm">
          <Badge tone={tone}>{t(`enum.renderStatus.${job.status}`)}</Badge>
          {t(`render.output_${job.output}`)} · {new Date(job.created_at).toLocaleString()}
        </span>
        <span className="flex gap-1">
          {active && (
            <Button size="sm" variant="ghost" icon={<X className="size-3.5" aria-hidden />} onClick={() => cancel.mutate(job.id)}>
              {t("render.cancel")}
            </Button>
          )}
          {video && (
            <Button size="sm" variant="secondary" icon={<Download className="size-3.5" aria-hidden />} loading={downloading} onClick={download}>
              {t("render.downloadMp4")}
            </Button>
          )}
          {!active && (
            <button type="button" className="rounded p-1.5 text-red-800 hover:bg-red-50" aria-label={t("render.delete")} onClick={() => del.mutate(job.id)}>
              <Trash2 className="size-4" aria-hidden />
            </button>
          )}
        </span>
      </div>
      {active && (
        <div className="mt-2">
          <progress className="w-full" max={100} value={job.progress} aria-label={t("render.progress")} />
          <LiveRegion message={t("render.progressValue", { value: job.progress })} />
        </div>
      )}
      {job.status === "failed" && <p className="mt-1 text-sm text-red-800">{t("render.failed", { code: job.error_code ?? "" })}</p>}
      {img.data && <img src={img.data} alt={t("render.posterAlt")} className="mt-2 w-full max-w-md rounded border border-stone-200" />}
      <ErrorAlert error={err || cancel.error || del.error} />
    </li>
  );
}
