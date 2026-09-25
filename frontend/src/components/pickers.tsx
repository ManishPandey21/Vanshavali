import { useEffect, useId, useRef, useState } from "react";
import { useTranslation } from "react-i18next";
import { Link2, MapPin, X } from "lucide-react";
import { usePeople, usePlaces } from "../api/hooks/people";
import type { PersonSummary, PlaceOut } from "../api/types";
import { useDebounced } from "../lib/useDebounced";
import { Combobox } from "./ui/Combobox";
import { lifespan } from "../lib/dates";
import { langOfText } from "../lib/names";

/** Search-as-you-type picker over people the viewer can see (server-filtered). */
export function PersonPicker({
  treeId,
  label,
  value,
  onChange,
  excludeIds = [],
  hint,
}: {
  treeId: string;
  label: string;
  value: PersonSummary | null;
  onChange: (p: PersonSummary | null) => void;
  excludeIds?: string[];
  hint?: string;
}) {
  const { t } = useTranslation();
  const [text, setText] = useState("");
  const q = useDebounced(text.trim(), 250);
  const people = usePeople(treeId, q);
  const labelId = useId();
  const rootRef = useRef<HTMLDivElement>(null);
  // Choosing or clearing swaps the input for the chosen-person box (and back); move focus along so
  // it is not dropped on <body> (WCAG 2.4.3).
  const refocus = useRef<"clear" | "input" | null>(null);
  useEffect(() => {
    const target = refocus.current;
    refocus.current = null;
    if (target === "clear") rootRef.current?.querySelector<HTMLElement>("button")?.focus();
    else if (target === "input") rootRef.current?.querySelector<HTMLElement>("input")?.focus();
  }, [value]);
  const options = (people.data?.pages.flatMap((p) => p.items) ?? [])
    .filter((p) => !excludeIds.includes(p.id))
    .slice(0, 20)
    .map((p) => ({
      key: p.id,
      value: p,
      textValue: p.display_name,
      label: (
        <span className="flex items-center justify-between gap-2">
          <span lang={langOfText(p.display_name)}>{p.display_name}</span>
          <span className="text-xs text-ink-muted">
            {lifespan(p, t)}
          </span>
        </span>
      ),
    }));

  if (value) {
    return (
      <div ref={rootRef} role="group" aria-labelledby={labelId}>
        <p id={labelId} className="label">
          {label}
        </p>
        <div className="flex items-center justify-between gap-2 rounded-lg border border-kumkum-200 bg-kumkum-50 px-3 py-2 text-sm">
          <span className="font-medium" lang={langOfText(value.display_name)}>
            {value.display_name}
          </span>
          <button
            type="button"
            className="rounded p-1 hover:bg-white"
            onClick={() => {
              refocus.current = "input";
              onChange(null);
            }}
            aria-label={t("pickers.clearPerson", { name: value.display_name })}
          >
            <X className="size-4" aria-hidden />
          </button>
        </div>
      </div>
    );
  }
  return (
    <div ref={rootRef}>
      <Combobox
        label={label}
        text={text}
        onTextChange={setText}
        options={options}
        onSelect={(p) => {
          refocus.current = "clear";
          onChange(p);
          setText("");
        }}
        loading={people.isFetching}
        placeholder={t("pickers.personPlaceholder")}
        emptyText={t("pickers.noPeople")}
        hint={hint}
      />
    </div>
  );
}

export interface PlaceValue {
  place_id: string | null;
  place_label: string | null;
  place_as_recorded: string;
}

export const emptyPlace = (): PlaceValue => ({ place_id: null, place_label: null, place_as_recorded: "" });

export function placeLabel(p: PlaceOut): string {
  const h = p.hierarchy ?? [];
  return h.length > 1 ? h.join(", ") : p.canonical_name;
}

/**
 * Place as recorded (verbatim, never overwritten) + optional link to a normalised place in the
 * tree's gazetteer. Suggestions come from existing places; nothing is linked automatically.
 */
export function PlacePicker({ treeId, label, value, onChange }: { treeId: string; label: string; value: PlaceValue; onChange: (v: PlaceValue) => void }) {
  const { t } = useTranslation();
  const q = useDebounced(value.place_as_recorded.trim(), 250);
  const places = usePlaces(treeId, q, q.length > 0);
  const options = (places.data?.items ?? []).slice(0, 15).map((p) => ({
    key: p.id,
    value: p,
    textValue: p.canonical_name,
    label: (
      <span className="flex items-center gap-2">
        <MapPin className="size-3.5 text-ink-muted" aria-hidden />
        <span>{placeLabel(p)}</span>
        <span className="ml-auto text-xs text-ink-muted">{t(`enum.placeType.${p.place_type}`)}</span>
      </span>
    ),
  }));
  return (
    <div className="space-y-2">
      <Combobox
        label={label}
        text={value.place_as_recorded}
        onTextChange={(s) => onChange({ ...value, place_as_recorded: s })}
        options={value.place_id ? [] : options}
        onSelect={(p) =>
          onChange({ place_id: p.id, place_label: placeLabel(p), place_as_recorded: value.place_as_recorded || p.canonical_name })
        }
        loading={places.isFetching}
        placeholder={t("pickers.placePlaceholder")}
        hint={t("pickers.placeHint")}
      />
      {value.place_id && (
        <div className="flex items-center gap-2 text-xs">
          <span className="inline-flex items-center gap-1 rounded-full border border-leaf-700/30 bg-leaf-50 px-2 py-0.5 text-leaf-700">
            <Link2 className="size-3" aria-hidden />
            {t("pickers.linkedTo", { place: value.place_label })}
          </span>
          <button type="button" className="text-kumkum-800 underline" onClick={() => onChange({ ...value, place_id: null, place_label: null })}>
            {t("pickers.unlink")}
          </button>
        </div>
      )}
    </div>
  );
}
