import { useState } from "react";
import { useTranslation } from "react-i18next";
import { FileCheck2, MapPinned } from "lucide-react";
import { useGeoDecision, useGeoSnapshots, type SnapshotDecision } from "../../api/hooks/geo";
import type { GeoSnapshot } from "../../api/types";
import { Badge, type Tone } from "../../components/ui/Badge";
import { Button } from "../../components/ui/Button";
import { Dialog } from "../../components/ui/Dialog";
import { EmptyState, ErrorAlert, LiveRegion, Spinner } from "../../components/ui/feedback";
import { Field, TextArea } from "../../components/ui/form";

const TONE: Record<string, Tone> = {
  staged: "neutral",
  validated: "blue",
  failed: "red",
  approved: "saffron",
  active: "green",
  superseded: "stone",
};

type Counts = Record<string, number>;
interface Report {
  counts?: Counts;
  error_count?: number;
  errors?: string[];
  warning_count?: number;
  warnings?: string[];
  diff?: { previous: string | null; added?: Counts; retired?: Counts; renamed?: Counts; moved?: Counts; samples?: Record<string, string[]> } | null;
}

function CountList({ counts }: { counts?: Counts }) {
  const entries = Object.entries(counts ?? {});
  if (!entries.length) return <span className="text-ink-muted">0</span>;
  return <span>{entries.map(([k, v]) => `${k} ${v.toLocaleString()}`).join(" · ")}</span>;
}

/** What a snapshot would change, so an admin can decide before anyone sees it (ADR-0019 §3). */
function ReportView({ snap }: { snap: GeoSnapshot }) {
  const { t } = useTranslation();
  const r = snap.report as Report;
  return (
    <div className="space-y-2 text-sm">
      <p>
        <span className="text-ink-muted">{t("geoAdmin.rows")}:</span> <CountList counts={r.counts} />
      </p>
      {r.diff && (
        <table className="w-full text-left text-xs">
          <caption className="sr-only">{t("geoAdmin.diffCaption")}</caption>
          <tbody>
            {(["added", "retired", "renamed", "moved"] as const).map((k) =>
              r.diff?.[k] !== undefined ? (
                <tr key={k} className="border-t border-stone-100 align-top">
                  <th scope="row" className="py-1 pr-2 font-medium">
                    {t(`geoAdmin.diff.${k}`)}
                  </th>
                  <td className="py-1">
                    <CountList counts={r.diff[k]} />
                    {(r.diff.samples?.[k] ?? []).length > 0 && (
                      <details>
                        <summary className="cursor-pointer text-ink-muted">{t("geoAdmin.examples")}</summary>
                        <ul className="list-disc pl-5">
                          {r.diff.samples?.[k]?.map((x) => (
                            <li key={x}>{x}</li>
                          ))}
                        </ul>
                      </details>
                    )}
                  </td>
                </tr>
              ) : null,
            )}
          </tbody>
        </table>
      )}
      {r.diff && <p className="text-xs text-ink-muted">{r.diff.previous ? t("geoAdmin.comparedWith", { label: r.diff.previous }) : t("geoAdmin.firstSnapshot")}</p>}
      {(r.error_count ?? 0) > 0 && (
        <div className="rounded-md border border-red-300 bg-red-50 p-2">
          <p className="font-semibold text-red-900">{t("geoAdmin.errors", { count: r.error_count })}</p>
          <ul className="list-disc pl-5 text-xs">
            {r.errors?.map((e) => (
              <li key={e}>{e}</li>
            ))}
          </ul>
        </div>
      )}
      {(r.warning_count ?? 0) > 0 && (
        <details className="rounded-md border border-haldi-300 bg-haldi-100/50 p-2">
          <summary className="cursor-pointer font-semibold">{t("geoAdmin.warnings", { count: r.warning_count })}</summary>
          <ul className="list-disc pl-5 text-xs">
            {r.warnings?.map((w) => (
              <li key={w}>{w}</li>
            ))}
          </ul>
        </details>
      )}
    </div>
  );
}

const ACTIONS: Record<string, SnapshotDecision[]> = {
  validated: ["approve", "discard"],
  approved: ["activate", "discard"],
  failed: ["discard"],
  staged: ["discard"],
  superseded: ["rollback"],
  active: [],
};

export function GeoSnapshotsPage() {
  const { t, i18n } = useTranslation();
  const q = useGeoSnapshots();
  const decide = useGeoDecision();
  const [pending, setPending] = useState<{ snap: GeoSnapshot; decision: SnapshotDecision } | null>(null);
  const [reason, setReason] = useState("");
  const [announce, setAnnounce] = useState("");
  if (q.isLoading) return <Spinner />;
  if (q.error) return <ErrorAlert error={q.error} />;
  const when = (iso?: string | null) => (iso ? new Date(iso).toLocaleString(i18n.language) : "");
  const confirm = () => {
    if (!pending || reason.trim().length < 3) return;
    decide.mutate(
      { id: pending.snap.id, decision: pending.decision, reason: reason.trim() },
      {
        onSuccess: () => {
          setAnnounce(t(`geoAdmin.done.${pending.decision}`, { label: pending.snap.label }));
          setPending(null);
          setReason("");
        },
      },
    );
  };
  return (
    <div>
      <LiveRegion message={announce} />
      <h2 className="mb-1 flex items-center gap-2 font-display text-xl font-semibold">
        <MapPinned className="size-5" aria-hidden />
        {t("geoAdmin.title")}
      </h2>
      <p className="mb-2 text-sm text-ink-muted">{t("geoAdmin.intro")}</p>
      <p className="mb-4 rounded-lg border border-stone-200 bg-white px-3 py-2 text-xs">
        {t("geoAdmin.howToStage")} <code className="break-all">python -m app.cli.geo stage --source lgd --label 2026-10 --file units.csv …</code>
      </p>
      {!q.data?.length ? (
        <EmptyState icon={<FileCheck2 className="size-6" />} title={t("geoAdmin.empty")}>
          {t("geoAdmin.emptyHint")}
        </EmptyState>
      ) : (
        <ul className="space-y-3">
          {q.data.map((s) => (
            <li key={s.id}>
              <article className="rounded-xl border border-stone-200 bg-white p-4" aria-labelledby={`snap-${s.id}`}>
                <div className="flex flex-wrap items-center gap-2">
                  <h3 id={`snap-${s.id}`} className="font-display text-base font-semibold">
                    {t(`geoAdmin.source.${s.source}`)} · {s.label}
                  </h3>
                  <Badge tone={TONE[s.status]}>{t(`geoAdmin.status.${s.status}`)}</Badge>
                </div>
                <p className="mt-1 text-xs text-ink-muted">
                  {s.licence} · {s.attribution}
                  {s.downloaded_on && <> · {t("geoAdmin.downloaded", { date: s.downloaded_on })}</>}
                </p>
                {s.files.map((f) => (
                  <p key={String(f.sha256)} className="text-xs text-ink-muted">
                    {String(f.name)} · {Number(f.bytes ?? 0).toLocaleString()} B · SHA-256 <code className="break-all">{String(f.sha256)}</code>
                  </p>
                ))}
                <p className="text-xs text-ink-muted">
                  {t("geoAdmin.staged", { who: s.staged_by ?? "—", when: when(s.created_at) })}
                  {s.approved_at && <> · {t("geoAdmin.approvedBy", { who: s.approved_by_name ?? "—", when: when(s.approved_at) })}</>}
                  {s.activated_at && <> · {t("geoAdmin.activatedBy", { who: s.activated_by_name ?? t("geoAdmin.operator"), when: when(s.activated_at) })}</>}
                </p>
                <div className="mt-2">
                  <ReportView snap={s} />
                </div>
                {s.status === "approved" && s.approved_by_me && <p className="mt-2 text-xs text-ink-muted">{t("geoAdmin.needsSecond")}</p>}
                <div className="mt-3 flex flex-wrap gap-2">
                  {(ACTIONS[s.status] ?? []).map((d) => (
                    <Button
                      key={d}
                      size="sm"
                      variant={d === "discard" ? "ghost" : d === "activate" ? "primary" : "secondary"}
                      disabled={d === "activate" && s.approved_by_me}
                      aria-label={`${t(`geoAdmin.action.${d}`)} ${s.label}`}
                      onClick={() => setPending({ snap: s, decision: d })}
                    >
                      {t(`geoAdmin.action.${d}`)}
                    </Button>
                  ))}
                </div>
              </article>
            </li>
          ))}
        </ul>
      )}
      {pending && (
        <Dialog
          open
          onClose={() => setPending(null)}
          title={t(`geoAdmin.confirm.${pending.decision}`, { label: `${t(`geoAdmin.source.${pending.snap.source}`)} ${pending.snap.label}` })}
          description={t(`geoAdmin.confirmHint.${pending.decision}`)}
          footer={
            <>
              <Button variant="secondary" onClick={() => setPending(null)}>
                {t("common.cancel")}
              </Button>
              <Button variant={pending.decision === "discard" ? "danger" : "primary"} disabled={reason.trim().length < 3} loading={decide.isPending} onClick={confirm}>
                {t(`geoAdmin.action.${pending.decision}`)}
              </Button>
            </>
          }
        >
          <Field label={t("geoAdmin.reason")} required>
            {(p) => <TextArea {...p} value={reason} onChange={(e) => setReason(e.target.value)} rows={2} maxLength={2000} />}
          </Field>
          <div className="mt-2">
            <ErrorAlert error={decide.error} />
          </div>
        </Dialog>
      )}
    </div>
  );
}
