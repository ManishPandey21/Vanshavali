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
};

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

/** "father's brother" / "पिता के भाई" — a literal reading of the chain, always available. */
export function describeChain(chain: readonly string[], lang: string): string {
  if (!chain.length) return "";
  if (lang.startsWith("hi")) {
    const words = chain.map((w) => HI_WORDS[w] ?? w.replace(/_/g, " "));
    return words.reduce((acc, w, i) => (i === 0 ? w : `${acc} के ${w}`), "");
  }
  const words = chain.map((w) => w.replace(/_/g, " "));
  return words.reduce((acc, w, i) => (i === 0 ? w : `${acc}'s ${w}`), "");
}
