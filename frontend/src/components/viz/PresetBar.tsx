import { useState } from "react";
import { useTranslation } from "react-i18next";
import { Bookmark, Trash2 } from "lucide-react";
import type { ChartType } from "../../api/types";
import { useDeletePreset, usePresets, useSavePreset } from "../../api/hooks/viz";
import { useTreeCtx } from "../../lib/tree-context";
import { Button } from "../ui/Button";
import { ErrorAlert } from "../ui/feedback";
import { Checkbox, Field, Select, TextInput } from "../ui/form";

/** Save and load chart settings (only ids and display options are stored, never people's data). */
export function PresetBar({ chartType, settings, onApply }: { chartType: ChartType; settings: Record<string, unknown>; onApply: (s: Record<string, unknown>) => void }) {
  const { t } = useTranslation();
  const { treeId } = useTreeCtx();
  const presets = usePresets(treeId, chartType);
  const save = useSavePreset(treeId);
  const del = useDeletePreset(treeId);
  const [name, setName] = useState("");
  const [shared, setShared] = useState(false);
  const [chosen, setChosen] = useState("");
  const current = presets.data?.find((p) => p.id === chosen);
  return (
    <details className="no-print card p-3 text-sm">
      <summary className="flex cursor-pointer items-center gap-2 font-semibold">
        <Bookmark className="size-4" aria-hidden /> {t("viz.presets.title")}
      </summary>
      <div className="mt-3 flex flex-wrap items-end gap-3">
        <Field label={t("viz.presets.load")}>
          {(p) => (
            <Select
              {...p}
              value={chosen}
              onChange={(e) => {
                setChosen(e.target.value);
                const preset = presets.data?.find((x) => x.id === e.target.value);
                if (preset) onApply(preset.settings);
              }}
            >
              <option value="">{t("viz.presets.choose")}</option>
              {presets.data?.map((p) => (
                <option key={p.id} value={p.id}>
                  {p.name}
                  {p.mine ? "" : ` (${t("viz.presets.shared")})`}
                </option>
              ))}
            </Select>
          )}
        </Field>
        {current?.mine && (
          <Button size="sm" variant="ghost" icon={<Trash2 className="size-4" aria-hidden />} onClick={() => del.mutate(current.id, { onSuccess: () => setChosen("") })}>
            {t("viz.presets.delete")}
          </Button>
        )}
        <Field label={t("viz.presets.name")}>{(p) => <TextInput {...p} value={name} maxLength={120} onChange={(e) => setName(e.target.value)} />}</Field>
        <div className="pb-2">
          <Checkbox label={t("viz.presets.shareWithTree")} checked={shared} onChange={setShared} />
        </div>
        <Button
          size="sm"
          disabled={!name.trim()}
          loading={save.isPending}
          onClick={() => save.mutate({ name: name.trim(), chart_type: chartType, settings, shared }, { onSuccess: (p) => { setName(""); setChosen(p.id); } })}
        >
          {t("viz.presets.save")}
        </Button>
      </div>
      <ErrorAlert error={save.error || del.error} />
    </details>
  );
}
