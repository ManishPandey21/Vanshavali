/**
 * Fitting a person's name into a fan-chart sector. SVG text cannot be measured before render (and
 * not at all in exports), so this uses a conservative average glyph width: a label that "fits" here
 * is never wider than its sector. The chart also clips each label to its sector as a safety net.
 */

/** Average advance of a semibold glyph, in em; deliberately generous (wide capitals, Indic marks). */
export const GLYPH_EM = 0.62;

export interface FanLabelSpace {
  /** Room along the text's baseline, in px. */
  length: number;
  /** Room across the baseline (the sector's narrowest extent), in px. */
  thickness: number;
  maxFont: number;
  minFont: number;
}

export interface FanLabel {
  text: string;
  fontSize: number;
}

// width is estimated per code point (an Indic vowel sign counts as a glyph: conservative), but text is
// only ever cut between grapheme clusters so a consonant never loses its vowel sign
const chars = (s: string) => [...s].length;
const segmenter = typeof Intl !== "undefined" && "Segmenter" in Intl ? new Intl.Segmenter(undefined, { granularity: "grapheme" }) : null;
const graphemes = (s: string): string[] => (segmenter ? [...segmenter.segment(s)].map((g) => g.segment) : [...s]);
const widthOf = (s: string, fontSize: number) => chars(s) * GLYPH_EM * fontSize;

/** "Ram Prasad Pandey" → "Ram Prasad P."; single-word names are left alone. */
export function abbreviateSurname(name: string): string {
  const parts = name.trim().split(/\s+/);
  if (parts.length < 2) return name.trim();
  const last = parts[parts.length - 1];
  return `${parts.slice(0, -1).join(" ")} ${graphemes(last)[0]}.`;
}

/**
 * The largest readable label for a sector: the full name if it fits at any size down to minFont,
 * then the name with the surname abbreviated, then that name cut with an ellipsis. Returns an empty
 * label when the sector is too small for even two characters (the name is still in the accessible
 * name and the table view).
 */
export function fitFanLabel(name: string, space: FanLabelSpace): FanLabel {
  const cap = Math.min(space.maxFont, Math.floor(space.thickness * 0.75));
  if (cap < space.minFont || space.length <= 0) return { text: "", fontSize: 0 };
  const full = name.trim();
  const candidates = [...new Set([full, abbreviateSurname(full)])];
  for (const text of candidates) {
    for (let fs = cap; fs >= space.minFont; fs -= 1) {
      if (widthOf(text, fs) <= space.length) return { text, fontSize: fs };
    }
  }
  const fs = space.minFont;
  const room = Math.floor(space.length / (GLYPH_EM * fs));
  if (room < 2) return { text: "", fontSize: 0 };
  let text = "";
  for (const g of graphemes(candidates[candidates.length - 1])) {
    if (chars(text + g) > room - 1) break;
    text += g;
  }
  text = text.trimEnd();
  return text ? { text: `${text}…`, fontSize: fs } : { text: "", fontSize: 0 };
}
