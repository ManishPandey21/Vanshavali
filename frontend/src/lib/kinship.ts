/**
 * Regional kinship terms for relationship chains returned by `/relationship-path`.
 *
 * The API returns a neutral English `label` (e.g. "uncle") plus a `chain` of kinship words
 * (e.g. ["father", "brother"]). Indian languages distinguish relatives the English label merges
 * (father's brother = चाचा/ताऊ vs mother's brother = मामा), so we map common chains to Hindi terms.
 * Where the Hindi term depends on relative age (चाचा younger / ताऊ elder), both are shown: the
 * API does not know birth order and we never guess it.
 */

export type KinWord =
  | "father"
  | "mother"
  | "parent"
  | "son"
  | "daughter"
  | "child"
  | "brother"
  | "sister"
  | "sibling"
  | "husband"
  | "wife"
  | "spouse";

const HI_TERMS: Record<string, string> = {
  father: "पिता",
  mother: "माता",
  son: "बेटा",
  daughter: "बेटी",
  brother: "भाई",
  sister: "बहन",
  husband: "पति",
  wife: "पत्नी",

  "father,father": "दादा",
  "father,mother": "दादी",
  "mother,father": "नाना",
  "mother,mother": "नानी",
  "father,father,father": "परदादा",
  "father,father,mother": "परदादी",
  "mother,father,father": "परनाना",
  "mother,father,mother": "परनानी",

  "father,brother": "चाचा / ताऊ",
  "father,sister": "बुआ",
  "mother,brother": "मामा",
  "mother,sister": "मौसी",
  "father,brother,wife": "चाची / ताई",
  "father,sister,husband": "फूफा",
  "mother,brother,wife": "मामी",
  "mother,sister,husband": "मौसा",

  "father,brother,son": "चचेरा भाई",
  "father,brother,daughter": "चचेरी बहन",
  "father,sister,son": "फुफेरा भाई",
  "father,sister,daughter": "फुफेरी बहन",
  "mother,brother,son": "ममेरा भाई",
  "mother,brother,daughter": "ममेरी बहन",
  "mother,sister,son": "मौसेरा भाई",
  "mother,sister,daughter": "मौसेरी बहन",

  "brother,son": "भतीजा",
  "brother,daughter": "भतीजी",
  "sister,son": "भांजा",
  "sister,daughter": "भांजी",
  "brother,wife": "भाभी",
  "sister,husband": "जीजा",

  "son,son": "पोता",
  "son,daughter": "पोती",
  "daughter,son": "नाती",
  "daughter,daughter": "नातिन",
  "son,wife": "बहू",
  "daughter,husband": "दामाद",

  "wife,father": "ससुर",
  "wife,mother": "सास",
  "husband,father": "ससुर",
  "husband,mother": "सास",
  "wife,brother": "साला",
  "wife,sister": "साली",
  "husband,brother": "देवर / जेठ",
  "husband,sister": "ननद",
  "wife,sister,husband": "साढ़ू",
  "wife,brother,wife": "सलहज",
  "husband,brother,wife": "देवरानी / जेठानी",
  "husband,sister,husband": "ननदोई",
  "son,wife,father": "समधी",
  "son,wife,mother": "समधन",
  "daughter,husband,father": "समधी",
  "daughter,husband,mother": "समधन",
};

/**
 * Terms that depend on relative age (ADR-0020 §5). `index` is the sibling word in the chain whose
 * age decides the term: for Tau/Chacha it is the uncle compared with the *father* (word 1), never
 * the viewer. `unknown` is shown when the age order is not known.
 */
const HI_AGE_TERMS: Record<string, { index: number; elder: string; younger: string; unknown: string }> = {
  brother: { index: 0, elder: "भैया", younger: "भाई", unknown: "भाई" },
  sister: { index: 0, elder: "दीदी", younger: "बहन", unknown: "बहन" },
  "father,brother": { index: 1, elder: "ताऊ", younger: "चाचा", unknown: "चाचा / ताऊ" },
  "father,brother,wife": { index: 1, elder: "ताई", younger: "चाची", unknown: "चाची / ताई" },
  "husband,brother": { index: 1, elder: "जेठ", younger: "देवर", unknown: "देवर / जेठ" },
  "husband,brother,wife": { index: 1, elder: "जेठानी", younger: "देवरानी", unknown: "देवरानी / जेठानी" },
  "wife,brother": { index: 1, elder: "भाई साहब", younger: "साला", unknown: "साला / भाई साहब" },
  "sister,husband": { index: 0, elder: "जीजा", younger: "बहनोई", unknown: "जीजा" },
};

export interface AgeOrder {
  chain_index: number;
  person_id: string;
  relative_to_id: string;
  order: "elder" | "younger" | "unknown";
  basis: "family_confirmed" | "birth_dates" | "unknown";
  record_id?: string | null;
  dates_disagree?: boolean;
}

export interface KinshipResult {
  /** The regional term, or null when there is no well-known one (caller falls back). */
  term: string | null;
  /** How the age-dependent part was decided; null when the term does not depend on age. */
  basis: AgeOrder["basis"] | null;
  /** The family could answer "older or younger?" to decide the term (both people visible). */
  ageQuestion: { personId: string; relativeToId: string } | null;
  dates_disagree: boolean;
}

/**
 * Regional term for a chain with the API's age orders: elder/younger decides Tau vs Chacha only
 * when the family confirmed it or the visible birth dates do; otherwise both words are shown.
 */
export function resolveKinship(chain: readonly string[], ageOrders: readonly AgeOrder[], lang: string): KinshipResult {
  const key = chain.join(",");
  const hindi = lang.startsWith("hi");
  const rule = HI_AGE_TERMS[key];
  if (!rule) return { term: hindi && chain.length ? (HI_TERMS[key] ?? null) : null, basis: null, ageQuestion: null, dates_disagree: false };
  // basis, question and disagreement do not depend on the UI language; only the word does
  const age = ageOrders.find((a) => a.chain_index === rule.index);
  if (!age || age.order === "unknown") {
    return { term: hindi ? rule.unknown : null, basis: age ? "unknown" : null, ageQuestion: ageQuestionFor(chain, ageOrders), dates_disagree: false };
  }
  return { term: hindi ? rule[age.order] : null, basis: age.basis, ageQuestion: null, dates_disagree: !!age.dates_disagree };
}

/** The age question that would decide an age-dependent term (any language), if it is still open. */
export function ageQuestionFor(chain: readonly string[], ageOrders: readonly AgeOrder[]): KinshipResult["ageQuestion"] {
  const rule = HI_AGE_TERMS[chain.join(",")];
  if (!rule) return null;
  const age = ageOrders.find((a) => a.chain_index === rule.index);
  return age && age.order === "unknown" ? { personId: age.person_id, relativeToId: age.relative_to_id } : null;
}

const HI_WORDS: Record<string, string> = {
  father: "पिता",
  mother: "माता",
  parent: "माता-पिता",
  son: "बेटा",
  daughter: "बेटी",
  child: "संतान",
  brother: "भाई",
  sister: "बहन",
  sibling: "भाई-बहन",
  husband: "पति",
  wife: "पत्नी",
  spouse: "जीवनसाथी",
};

/** Hindi kinship term for a chain, or null when there is no well-known term (caller falls back). */
export function hindiKinshipTerm(chain: readonly string[]): string | null {
  if (!chain.length) return null;
  return HI_TERMS[chain.join(",")] ?? null;
}

/** Regional term for the UI language (Hindi only for now); null for English, where the API label is used. */
export function regionalKinshipTerm(chain: readonly string[], lang: string): string | null {
  if (lang.startsWith("hi")) return hindiKinshipTerm(chain);
  return null;
}

const HI_AGED: Record<string, Record<"elder" | "younger", string>> = {
  brother: { elder: "बड़े भाई", younger: "छोटे भाई" },
  sister: { elder: "बड़ी बहन", younger: "छोटी बहन" },
  sibling: { elder: "बड़े भाई-बहन", younger: "छोटे भाई-बहन" },
};

/**
 * "father's brother" / "पिता के भाई" — a literal reading of the chain, always available. With age
 * orders it says "father's elder brother" / "पिता के बड़े भाई" where the order is known.
 */
export function describeChain(chain: readonly string[], lang: string, ageOrders: readonly AgeOrder[] = []): string {
  if (!chain.length) return "";
  const known = (i: number) => {
    const a = ageOrders.find((x) => x.chain_index === i);
    return a && a.order !== "unknown" ? a.order : null;
  };
  if (lang.startsWith("hi")) {
    const words = chain.map((w, i) => {
      const age = known(i);
      return (age && HI_AGED[w]?.[age]) || HI_WORDS[w] || w.replace(/_/g, " ");
    });
    return words.reduce((acc, w, i) => (i === 0 ? w : `${acc} के ${w}`), "");
  }
  const words = chain.map((w, i) => {
    const age = known(i);
    const word = w.replace(/_/g, " ");
    return age && w in HI_AGED ? `${age} ${word}` : word;
  });
  return words.reduce((acc, w, i) => (i === 0 ? w : `${acc}'s ${w}`), "");
}
