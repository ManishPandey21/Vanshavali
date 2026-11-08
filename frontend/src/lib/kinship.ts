/**
 * Rendering helpers for `/relationship-path` answers.
 *
 * The relationship words themselves (चाचा / ताऊ, मामा…) come from the API's `terms`, chosen from
 * reviewed regional packs on the server (ADR-0026 §6); their test matrix runs there for every pack.
 * This file only reads a chain literally in the UI language ("father's brother", "पिता के भाई").
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

export interface AgeOrder {
  chain_index: number;
  person_id: string;
  relative_to_id: string;
  order: "elder" | "younger" | "unknown";
  basis: "family_confirmed" | "birth_dates" | "unknown";
  record_id?: string | null;
  dates_disagree?: boolean;
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

const FEMININE = new Set(["mother", "daughter", "sister", "wife"]);

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
    // "भाई की पत्नी" but "पत्नी के भाई": the postposition agrees with the noun that follows
    return words.reduce((acc, w, i) => (i === 0 ? w : `${acc} ${FEMININE.has(chain[i]) ? "की" : "के"} ${w}`), "");
  }
  const words = chain.map((w, i) => {
    const age = known(i);
    const word = w.replace(/_/g, " ");
    return age && w in HI_AGED ? `${age} ${word}` : word;
  });
  return words.reduce((acc, w, i) => (i === 0 ? w : `${acc}'s ${w}`), "");
}
