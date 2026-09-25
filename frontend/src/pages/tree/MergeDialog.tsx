import { useState } from "react";
import { useTranslation } from "react-i18next";
import { AlertTriangle, Undo2 } from "lucide-react";
import type { PersonOut, PersonSummary } from "../../api/types";
import { usePerson } from "../../api/hooks/people";
import { useMerge, useMergePreview, useMerges, useRevertMerge } from "../../api/hooks/property";
import { useTreeCtx } from "../../lib/tree-context";
import { Perm } from "../../lib/permissions";
import { DateText } from "../../components/dates/DateText";
import { PersonBadges } from "../../components/person/badges";
import { nameText } from "../../lib/names";
import { Button } from "../../components/ui/Button";
import { Dialog } from "../../components/ui/Dialog";
import { ErrorAlert, Spinner } from "../../components/ui/feedback";
import { Field, TextInput } from "../../components/ui/form";

function Side({ p, survivor }: { p: PersonOut | undefined; survivor: boolean }) {
  const { t } = useTranslation();
  if (!p) return <Spinner />;
  return (
    <div className={`rounded-lg border p-3 text-sm ${survivor ? "border-leaf-700 bg-leaf-50" : "border-stone-300"}`}>
      <p className="text-xs font-semibold uppercase text-ink-muted">{survivor ? t("merge.keeps") : t("merge.mergedInto")}</p>
      <p className="font-display text-lg font-semibold">{p.display_name}</p>
      <PersonBadges person={p} />
      <dl className="mt-2 space-y-1">
        <div>
          <dt className="text-xs text-ink-muted">{t("names.title")}</dt>
          <dd>{(p.names ?? []).map((n) => nameText(n)).join("; ") || "—"}</dd>
        </div>
        <div>
          <dt className="text-xs text-ink-muted">{t("person.birthDate")}</dt>
          <dd>{p.birth?.date ? <DateText date={p.birth.date} /> : "—"}</dd>
        </div>
        <div>
          <dt className="text-xs text-ink-muted">{t("person.birthPlace")}</dt>
          <dd>{p.birth?.place_as_recorded ?? p.birth?.place_name ?? "—"}</dd>
        </div>
        <div>
          <dt className="text-xs text-ink-muted">{t("person.deathDate")}</dt>
          <dd>{p.death?.date ? <DateText date={p.death.date} /> : "—"}</dd>
        </div>
        <div>
          <dt className="text-xs text-ink-muted">{t("person.sexAtBirth")}</dt>
          <dd>{p.sex_at_birth ? t(`enum.sex.${p.sex_at_birth}`) : "—"}</dd>
        </div>
      </dl>
    </div>
  );
}

/** Side-by-side comparison and privileged, reversible merge (admins only; the server re-checks). */
export function MergeDialog({ a, b, onClose }: { a: PersonSummary; b: PersonSummary; onClose: () => void }) {
  const { t } = useTranslation();
  const { treeId } = useTreeCtx();
  const [survivor, setSurvivor] = useState<"a" | "b">("a");
  const [reason, setReason] = useState("");
  const keep = survivor === "a" ? a : b;
  const drop = survivor === "a" ? b : a;
  const pk = usePerson(treeId, keep.id);
  const pd = usePerson(treeId, drop.id);
  const preview = useMergePreview(treeId, keep.id, drop.id);
  const merge = useMerge(treeId);
  return (
    <Dialog
      open
      onClose={onClose}
      size="lg"
      title={t("merge.title")}
      description={t("merge.description")}
      footer={
        merge.isSuccess ? (
          <Button onClick={onClose}>{t("common.close")}</Button>
        ) : (
          <>
            <Button variant="secondary" onClick={onClose}>
              {t("common.cancel")}
            </Button>
            <Button variant="danger" loading={merge.isPending} disabled={!preview.data} onClick={() => merge.mutate({ survivor_id: keep.id, merged_id: drop.id, reason: reason.trim() || null })}>
              {t("merge.confirm")}
            </Button>
          </>
        )
      }
    >
      {merge.isSuccess ? (
        <p role="status" className="text-sm">
          {t("merge.done", { name: keep.display_name })}
        </p>
      ) : (
        <div className="space-y-3">
          <fieldset>
            <legend className="label">{t("merge.whichKeeps")}</legend>
            <div className="flex flex-wrap gap-4 text-sm">
              {(["a", "b"] as const).map((k) => (
                <label key={k} className="inline-flex items-center gap-2">
                  <input type="radio" name="survivor" className="accent-kumkum-700" checked={survivor === k} onChange={() => setSurvivor(k)} />
                  {(k === "a" ? a : b).display_name}
                </label>
              ))}
            </div>
          </fieldset>
          <div className="grid gap-3 sm:grid-cols-2">
            <Side p={pk.data} survivor />
            <Side p={pd.data} survivor={false} />
          </div>
          {preview.isLoading && <Spinner />}
          <ErrorAlert error={preview.error} />
          {preview.data && (
            <div className="rounded-lg bg-parchment p-3 text-sm">
              <p className="font-semibold">{t("merge.whatMoves")}</p>
              <ul className="list-inside list-disc">
                {Object.entries(preview.data.references_to_move).map(([k, v]) => (
                  <li key={k}>{t("merge.refs", { count: v, kind: t(`merge.table.${k}`, { defaultValue: k.replace(/_/g, " ") }) })}</li>
                ))}
                <li>{t("merge.relsMoved", { count: preview.data.relationships_to_move })}</li>
                {preview.data.relationships_between_them_removed > 0 && <li>{t("merge.relsRemoved", { count: preview.data.relationships_between_them_removed })}</li>}
              </ul>
              {preview.data.warnings.map((w) => (
                <p key={w} className="mt-1 flex items-center gap-1 text-haldi-700">
                  <AlertTriangle className="size-4" aria-hidden /> {w}
                </p>
              ))}
              <p className="mt-2 text-xs text-ink-muted">{t("merge.reversible")}</p>
            </div>
          )}
          <Field label={t("merge.reason")}>{(p) => <TextInput {...p} value={reason} onChange={(e) => setReason(e.target.value)} />}</Field>
          <ErrorAlert error={merge.error} />
        </div>
      )}
    </Dialog>
  );
}

export function MergeHistory() {
  const { t, i18n } = useTranslation();
  const { treeId, can } = useTreeCtx();
  const admin = can(Perm.TREE_MANAGE);
  const merges = useMerges(treeId, admin);
  const revert = useRevertMerge(treeId);
  if (!admin) return null;
  return (
    <section className="card mt-6 p-4" aria-labelledby="merge-hist">
      <h2 id="merge-hist" className="font-display text-lg font-semibold">
        {t("merge.history")}
      </h2>
      {merges.isLoading && <Spinner />}
      <ErrorAlert error={merges.error || revert.error} />
      {merges.data?.length === 0 && <p className="text-sm text-ink-muted">{t("merge.noHistory")}</p>}
      <ul className="divide-y divide-stone-100 text-sm">
        {merges.data?.map((m) => (
          <li key={m.id} className="flex flex-wrap items-center justify-between gap-2 py-2">
            <span>
              <MergeName id={m.survivor_id} /> ← <span className="text-ink-muted">{m.merged_id.slice(0, 8)}</span>
              <span className="ml-2 text-xs text-ink-muted">
                {new Date(m.created_at).toLocaleString(i18n.language)} · {t("merge.changes", { count: m.change_count })}
                {m.reason ? ` · “${m.reason}”` : ""}
              </span>
            </span>
            {m.reverted_at ? (
              <span className="text-xs text-ink-muted">{t("merge.reverted", { date: new Date(m.reverted_at).toLocaleDateString(i18n.language) })}</span>
            ) : (
              <Button size="sm" variant="secondary" icon={<Undo2 className="size-4" aria-hidden />} loading={revert.isPending && revert.variables === m.id} onClick={() => revert.mutate(m.id)}>
                {t("merge.undo")}
              </Button>
            )}
          </li>
        ))}
      </ul>
    </section>
  );
}

function MergeName({ id }: { id: string }) {
  const { t } = useTranslation();
  const { treeId } = useTreeCtx();
  const p = usePerson(treeId, id);
  return <span className="font-medium">{p.data?.display_name ?? t("person.privatePerson")}</span>;
}
