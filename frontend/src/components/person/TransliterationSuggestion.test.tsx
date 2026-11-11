import { describe, expect, it, vi } from "vitest";
import { screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { useState } from "react";
import { jsonResponse, renderWithProviders } from "../../test/utils";
import { NameFields, emptyName, type NameDraft } from "./NameFields";

const answers: Record<string, { text: string; method: "lexicon" | "rules" }[]> = {
  "Deva|Sunita": [{ text: "सुनीता", method: "lexicon" }],
  "Deva|Sharma": [{ text: "शर्मा", method: "lexicon" }],
  "Deva|Vinita": [
    { text: "विनिता", method: "rules" },
    { text: "विनीता", method: "rules" },
  ],
};

// Each name part is debounced (400 ms, useDebounced in TransliterationSuggestion) before it is
// transliterated. When typing is slow (a busy CPU), the given name's suggestion can show before the
// surname has settled, and it disappears while the surname's answer is fetched. So the tests wait for
// the final suggestion, not the first one, and allow time for both debounces; the assertions are the
// same as before. (Reproduced: 2 failures in 16 full runs with the backend suite running alongside.)
const AFTER_DEBOUNCE = { timeout: 3000 };

function server() {
  return vi.fn((url: RequestInfo | URL, init?: RequestInit) => {
    if (String(url).endsWith("/transliterate")) {
      const body = JSON.parse(String(init?.body));
      const candidates = answers[`${body.target_script}|${body.text}`] ?? [];
      return Promise.resolve(jsonResponse({ candidates, engine: "vanshavali-translit", version: "hi-Latn/1", lexicon_version: "1" }));
    }
    return Promise.resolve(jsonResponse({}, 404));
  });
}

function Harness({ onAdd }: { onAdd: (n: NameDraft) => void }) {
  const [v, setV] = useState<NameDraft>(emptyName(true));
  return <NameFields index={0} value={v} onChange={setV} onAddName={onAdd} />;
}

describe("TransliterationSuggestion", () => {
  it("suggests the name in Devanagari and adds it only on an explicit click, typed name unchanged", async () => {
    const fetchMock = server();
    vi.stubGlobal("fetch", fetchMock);
    const onAdd = vi.fn();
    renderWithProviders(<Harness onAdd={onAdd} />);
    const given = screen.getByLabelText("Given name");
    await userEvent.type(given, "Sunita");
    await userEvent.type(screen.getByLabelText("Surname / family name"), "Sharma");

    // the final suggestion, for both parts; then everything else is checked against that state
    expect(await screen.findByText("सुनीता शर्मा", {}, AFTER_DEBOUNCE)).toHaveAttribute("lang", "hi");
    expect(screen.getByText("In Devanagari:")).toBeInTheDocument();
    expect(screen.getByRole("status")).toHaveAttribute("aria-live", "polite");
    expect(onAdd).not.toHaveBeenCalled();
    expect(given).toHaveValue("Sunita");

    await userEvent.click(screen.getByRole("button", { name: /Add as another name: सुनीता शर्मा/ }));
    expect(onAdd).toHaveBeenCalledWith({
      type: "transliteration",
      given_name: "सुनीता",
      surname: "शर्मा",
      language: "hi",
      script: "Deva",
      is_preferred: false,
      evidence_status: "USER_ASSERTION",
      suggestion: { method: "lexicon" },
    });
    expect(given).toHaveValue("Sunita");
    // the request carries only the text and the target script
    const body = JSON.parse(String(fetchMock.mock.calls.find(([u]) => String(u).endsWith("/transliterate"))![1]!.body));
    expect(Object.keys(body).sort()).toEqual(["target_script", "text"]);
  });

  it("labels rule-based candidates as possible spellings and can be dismissed", async () => {
    vi.stubGlobal("fetch", server());
    renderWithProviders(<Harness onAdd={vi.fn()} />);
    await userEvent.type(screen.getByLabelText("Given name"), "Vinita");
    expect(await screen.findByText("विनिता", {}, AFTER_DEBOUNCE)).toBeInTheDocument();
    expect(screen.getByText("विनीता")).toBeInTheDocument();
    expect(screen.getAllByText("(possible spelling)")).toHaveLength(2);
    await userEvent.click(screen.getByRole("button", { name: "Dismiss" }));
    await waitFor(() => expect(screen.queryByText("विनिता")).not.toBeInTheDocument());
  });

  it("offers nothing for scripts outside v1, or when the service has no answer", async () => {
    const fetchMock = server();
    vi.stubGlobal("fetch", fetchMock);
    function Tamil() {
      const [v, setV] = useState<NameDraft>(emptyName(true, "ta", "Taml"));
      return <NameFields index={0} value={v} onChange={setV} onAddName={vi.fn()} />;
    }
    renderWithProviders(<Tamil />);
    await userEvent.type(screen.getByLabelText("Given name"), "சுனிதா");
    await new Promise((r) => setTimeout(r, 600));
    expect(fetchMock.mock.calls.some(([u]) => String(u).endsWith("/transliterate"))).toBe(false);
    expect(screen.queryByText("In Devanagari:")).not.toBeInTheDocument();
  });
});
