import type { GeoLevel, GeoUnitBrief, GeoUnitOut, PlaceType } from "../api/types";

/** BCP 47 language for an LGD local-script name, so it renders with the right font (ADR-0019 §7). */
const SCRIPT_LANG: Record<string, string> = {
  Deva: "hi",
  Beng: "bn",
  Guru: "pa",
  Gujr: "gu",
  Orya: "or",
  Taml: "ta",
  Telu: "te",
  Knda: "kn",
  Mlym: "ml",
};

export function langOfScript(script: string | null | undefined): string | undefined {
  return script ? SCRIPT_LANG[script] : undefined;
}

export function placeTypeFor(u: Pick<GeoUnitOut, "level" | "category">): PlaceType {
  switch (u.level) {
    case "state":
      return "state";
    case "district":
      return "district";
    case "sub_district":
      return "tehsil";
    case "urban_body":
      return /corporation/i.test(u.category ?? "") ? "city" : "town";
    default:
      return "village";
  }
}

/** "Phulpur, Prayagraj, Uttar Pradesh": the unit's ancestors, nearest first. */
export function ancestryLabel(u: Pick<GeoUnitOut, "ancestors">): string {
  return [...(u.ancestors ?? [])].reverse().map((a) => a.name_en).join(", ");
}

function ancestor(u: GeoUnitOut, level: GeoLevel): GeoUnitBrief | undefined {
  if (u.level === level) return u;
  return (u.ancestors ?? []).find((a) => a.level === level);
}

/**
 * Place fields filled from a picked unit (ADR-0019 §4). Everything except the code stays editable
 * in the form: the family's spelling wins.
 */
export function placeFieldsFor(u: GeoUnitOut) {
  const local = u.name_local ? [{ name: u.name_local, language: langOfScript(u.local_script) ?? null, script: u.local_script ?? null }] : [];
  return {
    canonical_name: u.name_en,
    place_type: placeTypeFor(u),
    lgd_code: u.lgd_code,
    lgd_level: u.level,
    district: ancestor(u, "district")?.name_en ?? null,
    state: ancestor(u, "state")?.name_en ?? null,
    country: "India",
    local_names: local,
  };
}
