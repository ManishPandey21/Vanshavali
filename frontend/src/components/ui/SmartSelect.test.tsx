import { describe, expect, it, vi } from "vitest";
import { useState } from "react";
import { screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { jsonResponse, makeTree, renderWithProviders } from "../../test/utils";
import { SmartSelect, type VocabRef } from "./SmartSelect";

const gotra = (items: unknown[], allows_custom = true) => ({
  vocabulary: { key: "gotra", description: "", version: 1, allows_custom, term_count: items.length },
  items,
});
const bharadwaja = { code: "bharadwaja", label: "Bharadwaja", labels: { en: "Bharadwaja", hi: "भरद्वाज" }, aliases: ["Bhardwaj"], status: "draft", origin: "global" };
const khandoba = { code: "t:khandoba", label: "Khandoba", labels: {}, aliases: [], status: "reviewed", origin: "family", id: "f1" };

function Harness({ onChange, vocabulary = "gotra", linkable }: { onChange: (t: string, r: VocabRef | null) => void; vocabulary?: string; linkable?: boolean }) {
  const [text, setText] = useState("");
  return (
    <SmartSelect
      vocabulary={vocabulary}
      label="Gotra"
      text={text}
      linkable={linkable}
      fallback={["Kashyapa"]}
      onChange={(t, r) => {
        setText(t);
        onChange(t, r);
      }}
    />
  );
}

describe("SmartSelect", () => {
  it("suggests terms in any script and links the chosen one, keeping its label", async () => {
    const fetchMock = vi.fn((url: RequestInfo | URL) =>
      Promise.resolve(jsonResponse(gotra(String(url).includes("q=%E0%A4%AD") || String(url).includes("q=Bhar") ? [bharadwaja] : [bharadwaja, khandoba]))),
    );
    vi.stubGlobal("fetch", fetchMock);
    const onChange = vi.fn();
    renderWithProviders(<Harness onChange={onChange} />);
    const box = screen.getByRole("combobox", { name: "Gotra" });
    await userEvent.type(box, "भ");
    await waitFor(() => expect(fetchMock.mock.calls.some(([u]) => String(u).includes("/trees/tree-1/vocabularies/gotra?q=%E0%A4%AD"))).toBe(true));
    await userEvent.click(await screen.findByRole("option", { name: /Bharadwaja/ }));
    expect(onChange).toHaveBeenLastCalledWith("Bharadwaja", { vocabulary: "gotra", code: "bharadwaja" });
    // editing the text drops the link: the value is whatever the user typed
    await userEvent.type(box, "x");
    expect(onChange).toHaveBeenLastCalledWith("Bharadwajax", null);
  });

  it("adds the typed spelling as the family's own entry and links it", async () => {
    document.cookie = "vsh_csrf=csrf-token";
    const fetchMock = vi.fn((_url: RequestInfo | URL, init?: RequestInit) => {
      if (init?.method === "POST") return Promise.resolve(jsonResponse({ term: { ...khandoba, label: "Khandoba" }, created: true }, 201));
      return Promise.resolve(jsonResponse(gotra([])));
    });
    vi.stubGlobal("fetch", fetchMock);
    const onChange = vi.fn();
    renderWithProviders(<Harness vocabulary="kuladevata" onChange={onChange} />);
    await userEvent.type(screen.getByRole("combobox", { name: "Gotra" }), "खंडोबा");
    await userEvent.click(await screen.findByRole("option", { name: /Add “खंडोबा” as your family's own entry/ }));
    await waitFor(() => expect(onChange).toHaveBeenLastCalledWith("खंडोबा", { vocabulary: "kuladevata", code: "t:khandoba" }));
    const post = fetchMock.mock.calls.find(([, init]) => init?.method === "POST")!;
    expect(String(post[0])).toBe("/api/v1/trees/tree-1/vocabularies/kuladevata/terms");
    expect(JSON.parse(String(post[1]!.body))).toEqual({ label: "खंडोबा" });
  });

  it("offers no 'add' to a viewer or for a closed list, and suggestions-only fields never link", async () => {
    vi.stubGlobal("fetch", vi.fn(() => Promise.resolve(jsonResponse(gotra([bharadwaja])))));
    const onChange = vi.fn();
    renderWithProviders(<Harness onChange={onChange} linkable={false} />, { tree: makeTree({ my_permissions: ["tree.read"] }) });
    await userEvent.type(screen.getByRole("combobox", { name: "Gotra" }), "Zzz");
    await screen.findByRole("option", { name: /Bharadwaja/ });
    expect(screen.queryByRole("option", { name: /family's own/ })).not.toBeInTheDocument();
    await userEvent.click(screen.getByRole("option", { name: /Bharadwaja/ }));
    expect(onChange).toHaveBeenLastCalledWith("Bharadwaja", null);
  });

  it("falls back to a plain text field when the service is switched off", async () => {
    vi.stubGlobal("fetch", vi.fn(() => Promise.resolve(jsonResponse({ error: { code: "not_found", message: "Not found" } }, 404))));
    const onChange = vi.fn();
    renderWithProviders(<Harness onChange={onChange} />);
    // once the 404 arrives: a plain input with the static fallback list, not the ARIA combobox
    await waitFor(() => expect(document.querySelector("datalist option[value='Kashyapa']")).not.toBeNull());
    expect(screen.getByLabelText("Gotra")).not.toHaveAttribute("aria-controls");
    await userEvent.type(screen.getByLabelText("Gotra"), "Atri");
    expect(onChange).toHaveBeenLastCalledWith("Atri", null);
  });
});
