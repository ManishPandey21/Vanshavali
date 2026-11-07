import { useTranslation } from "react-i18next";
import { Info } from "lucide-react";
import type { GeoUnitOut, PlaceOut } from "../../api/types";
import { useUpdatePlace } from "../../api/hooks/people";
import { ancestryLabel } from "../../lib/lgd";
import { Button } from "../ui/Button";
import { ErrorAlert } from "../ui/feedback";

/**
 * "LGD now lists this village under Prayagraj district (since 2026-05)" (ADR-0019 §4). The place is
 * unchanged until the user chooses to update it; a retired unit is re-picked in the editor.
 */
export function LgdNote({ treeId, place, canWrite, onChoose }: { treeId: string; place: PlaceOut; canWrite: boolean; onChoose: () => void }) {
  const { t } = useTranslation();
  const update = useUpdatePlace(treeId);
  const note = place.lgd_note;
  if (!note || !place.lgd_level) return null;
  const level = t(`lgd.level.${place.lgd_level}`);
  const since = note.since ?? "";
  const unit = note.unit as GeoUnitOut;
  const kinds = note.kind.split("+");
  let text: string;
  if (note.kind === "retired") text = t("lgd.note.retired", { level, since });
  else if (kinds.includes("moved") || kinds.includes("ancestor_renamed"))
    text = t("lgd.note.under", { level, path: ancestryLabel(unit), since }) + (kinds.includes("renamed") ? " " + t("lgd.note.renamed", { level, name: unit.name_en, since }) : "");
  else text = t("lgd.note.renamed", { level, name: unit.name_en, since });

  const accept = () => {
    const district = unit.level === "district" ? unit.name_en : (unit.ancestors ?? []).find((a) => a.level === "district")?.name_en;
    const state = unit.level === "state" ? unit.name_en : (unit.ancestors ?? []).find((a) => a.level === "state")?.name_en;
    update.mutate({
      id: place.id,
      body: {
        lgd_accept_current: true,
        ...(kinds.includes("renamed") ? { canonical_name: unit.name_en } : {}),
        ...(district ? { district } : {}),
        ...(state ? { state } : {}),
      },
    });
  };

  return (
    <div className="mt-2 rounded-md border border-sky-200 bg-sky-50 p-2 text-sm" role="note">
      <p className="flex items-start gap-1.5">
        <Info className="mt-0.5 size-4 shrink-0 text-sky-800" aria-hidden />
        <span>
          {text}
          {note.successors?.length ? " " + t("lgd.note.successors", { names: note.successors.map((s) => s.name_en).join(", ") }) : ""}{" "}
          <span className="text-ink-muted">{t("lgd.note.unchanged")}</span>
        </span>
      </p>
      {canWrite && (
        <div className="mt-1">
          {note.kind === "retired" ? (
            <Button size="sm" variant="secondary" onClick={onChoose}>
              {t("lgd.note.choose")}
            </Button>
          ) : (
            <Button size="sm" variant="secondary" onClick={accept} loading={update.isPending}>
              {t("lgd.note.update")}
            </Button>
          )}
        </div>
      )}
      <ErrorAlert error={update.error} />
    </div>
  );
}
