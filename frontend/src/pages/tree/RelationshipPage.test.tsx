import { describe, expect, it, vi } from "vitest";
import { screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import i18n from "../../i18n";
import { jsonResponse, makeTree, renderWithProviders } from "../../test/utils";
import { RelationshipPage } from "./RelationshipPage";

const people: Record<string, { id: string; display_name: string; profile_status: string; sex_at_birth: string }> = {
  me: { id: "me", display_name: "Aarav Sharma", profile_status: "living", sex_at_birth: "male" },
  father: { id: "father", display_name: "Ramesh Sharma", profile_status: "deceased", sex_at_birth: "male" },
  uncle: { id: "uncle", display_name: "Suresh Sharma", profile_status: "deceased", sex_at_birth: "male" },
};

function server(order: "elder" | "younger" | "unknown", basis = order === "unknown" ? "unknown" : "family_confirmed") {
  return vi.fn((url: RequestInfo | URL, init?: RequestInit) => {
    const u = String(url);
    if (init?.method === "POST") return Promise.resolve(jsonResponse({ id: "rec", elder_person_id: "uncle", younger_person_id: "father" }, 201));
    if (u.includes("/relationship-path")) {
      const age = { chain_index: 1, person_id: "uncle", relative_to_id: "father", order, basis, record_id: null, dates_disagree: false };
      // the server picks the word (ADR-0026 §6); here only for a Hindi reader
      const word = { elder: ["ताऊ", "tau"], younger: ["चाचा", "chacha"], unknown: ["चाचा / ताऊ", "chacha / tau"] }[order];
      const terms = u.includes("lang=hi")
        ? [{ pack: "kinship-hi-north", lang: "hi", region: "north", term: word[0], transliteration: word[1], alternatives: [], basis, review_status: "unreviewed", family_word: false, pack_term: null, description: null }]
        : [];
      return Promise.resolve(
        jsonResponse({
          terms,
          age_decision: age,
          from_id: "me",
          to_id: "uncle",
          found: true,
          label: "uncle",
          chain: ["father", "brother"],
          path: ["me", "father", "uncle"],
          common_ancestor_ids: [],
          lineages: [],
          age_orders: [age],
        }),
      );
    }
    const id = u.match(/\/people\/([a-z]+)(?:\?|$)/)?.[1];
    if (id && people[id]) return Promise.resolve(jsonResponse(people[id]));
    return Promise.resolve(jsonResponse({}, 404));
  });
}

describe("RelationshipPage: age-aware terms", () => {
  it("shows ताऊ when the family confirmed the uncle is older than the father", async () => {
    await i18n.changeLanguage("hi");
    vi.stubGlobal("fetch", server("elder"));
    renderWithProviders(<RelationshipPage />, { route: "/?from=me&to=uncle" });
    expect(await screen.findByText("ताऊ")).toBeInTheDocument();
    expect(screen.getByText("पिता के बड़े भाई", { exact: false })).toBeInTheDocument();
    expect(screen.getByText(/परिवार ने पुष्टि की है/)).toBeInTheDocument();
    expect(screen.queryByRole("group", { name: /बड़े हैं या छोटे/ })).not.toBeInTheDocument();
    // a pack word not yet reviewed by a native speaker says so
    expect(screen.getByText("tau")).toBeInTheDocument();
    await i18n.changeLanguage("en");
  });

  it("shows a family's own word first, with the pack's word beside it", async () => {
    await i18n.changeLanguage("en");
    const base = server("elder");
    vi.stubGlobal("fetch", (url: RequestInfo | URL, init?: RequestInit) => {
      if (String(url).includes("/relationship-path"))
        return base(url, init).then(async (r: Response) => {
          const body = await r.json();
          body.terms = [{ pack: "kinship-hi-north", lang: "hi", region: "north", term: "बड़े बाबूजी", transliteration: null, alternatives: [], basis: "family_confirmed", review_status: "family", family_word: true, pack_term: "ताऊ", description: null }];
          return jsonResponse(body);
        });
      return base(url, init);
    });
    renderWithProviders(<RelationshipPage />, { route: "/?from=me&to=uncle" });
    expect(await screen.findByText("बड़े बाबूजी")).toBeInTheDocument();
    expect(screen.getByText("Your family's word")).toBeInTheDocument();
    expect(screen.getByText("ताऊ")).toBeInTheDocument();
  });

  it("asks an editor whether the uncle is older or younger than the father, and records the answer", async () => {
    await i18n.changeLanguage("en");
    document.cookie = "vsh_csrf=csrf-token";
    const fetchMock = server("unknown");
    vi.stubGlobal("fetch", fetchMock);
    renderWithProviders(<RelationshipPage />, { route: "/?from=me&to=uncle" });
    const group = await screen.findByRole("group", { name: "Is Suresh Sharma older or younger than Ramesh Sharma?" });
    await userEvent.click(screen.getByRole("button", { name: "Younger than Ramesh Sharma" }));
    await waitFor(() => expect(fetchMock.mock.calls.some(([, init]) => init?.method === "POST")).toBe(true));
    const [url, init] = fetchMock.mock.calls.find(([, i]) => i?.method === "POST")!;
    expect(String(url)).toBe("/api/v1/trees/tree-1/relative-age-orders");
    expect(JSON.parse(String(init!.body))).toEqual({ person_id: "uncle", relative_to_id: "father", order: "younger" });
    expect(group).toBeInTheDocument();
  });

  it("does not offer the question to a viewer", async () => {
    await i18n.changeLanguage("en");
    vi.stubGlobal("fetch", server("unknown"));
    renderWithProviders(<RelationshipPage />, { route: "/?from=me&to=uncle", tree: makeTree({ my_permissions: ["tree.read"] }) });
    expect(await screen.findByText(/father's brother/)).toBeInTheDocument();
    await waitFor(() => expect(screen.queryByRole("button", { name: /Younger than/ })).not.toBeInTheDocument());
  });
});
