import { describe, expect, it, vi } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { Route, Routes } from "react-router-dom";
import i18n from "../../i18n";
import { jsonResponse, renderWithProviders } from "../../test/utils";
import { FormattedText, TraditionDetailPage } from "../../pages/tree/TraditionsPage";
import { OffersCard } from "./OffersCard";
import { describePattern } from "./KinshipSettings";

const body = (init?: RequestInit) => JSON.parse(String(init?.body ?? "{}"));

describe("family traditions (ADR-0026 §7)", () => {
  it("renders light formatting as text only, never as HTML", () => {
    const { container } = render(<FormattedText text={"Maida, khoya.\n\n- Fry **slowly**\n- <img src=x onerror=alert(1)>"} />);
    expect(screen.getByText("slowly").tagName).toBe("STRONG");
    expect(screen.getAllByRole("listitem")).toHaveLength(2);
    expect(container.querySelector("img")).toBeNull();
    expect(screen.getByText("<img src=x onerror=alert(1)>")).toBeInTheDocument();
  });

  it("sends an edit to someone else's entry for review when the family reviews changes", async () => {
    await i18n.changeLanguage("en");
    document.cookie = "vsh_csrf=csrf-token";
    const entry = {
      id: "e1",
      kind: "recipe",
      title: "Dadi's gujiya",
      excerpt: "",
      body: "Fry slowly.",
      language: null,
      script: null,
      branch_id: null,
      privacy_level: "TREE_MEMBERS",
      author_name: "Dadi",
      updated_at: "2026-11-08T00:00:00Z",
      links: [{ target_type: "person", target_id: "p1", label: "Kamla Sharma" }],
      revision: 2,
      review_state: "unreviewed",
      created_at: "2026-11-08T00:00:00Z",
      created_by: "u2",
      can_edit: true,
      edit_needs_review: true,
      can_withdraw: false,
    };
    const fetchMock = vi.fn((url: RequestInfo | URL, init?: RequestInit) => {
      const u = String(url);
      if (init?.method === "POST" && u.endsWith("/proposals")) return Promise.resolve(jsonResponse({ id: "prop-1" }, 201));
      if (u.includes("/traditions/e1")) return Promise.resolve(jsonResponse(entry));
      if (u.includes("/branches")) return Promise.resolve(jsonResponse([]));
      if (u.includes("/people")) return Promise.resolve(jsonResponse({ items: [], next_cursor: null }));
      if (u.includes("/citations")) return Promise.resolve(jsonResponse([]));
      return Promise.resolve(jsonResponse({}));
    });
    vi.stubGlobal("fetch", fetchMock);
    renderWithProviders(
      <Routes>
        <Route path="/t/:treeId/traditions/:entryId" element={<TraditionDetailPage />} />
      </Routes>,
      { route: "/t/tree-1/traditions/e1" },
    );
    expect(await screen.findByRole("heading", { level: 1, name: "Dadi's gujiya" })).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Withdraw" })).not.toBeInTheDocument();
    await userEvent.click(screen.getByRole("button", { name: "Propose a change" }));
    const dialog = await screen.findByRole("dialog", { name: "Propose a change" });
    expect(dialog).toHaveTextContent("This change is sent for review");
    await userEvent.clear(screen.getByLabelText("Text", { exact: false }));
    await userEvent.type(screen.getByLabelText("Text", { exact: false }), "Fry on a low flame.");
    await userEvent.type(screen.getByLabelText(/Why this change is right/), "Dadi said so");
    await userEvent.click(screen.getByRole("button", { name: "Send for review" }));
    await waitFor(() => expect(fetchMock.mock.calls.some(([u, i]) => String(u).endsWith("/proposals") && i?.method === "POST")).toBe(true));
    const [, init] = fetchMock.mock.calls.find(([u, i]) => String(u).endsWith("/proposals") && i?.method === "POST")!;
    const sent = body(init);
    expect(sent.items[0]).toMatchObject({ target_type: "tradition", op: "update", target_id: "e1" });
    expect(sent.items[0].patch.body).toBe("Fry on a low flame.");
    // the linked person stays linked; who may read it is not part of someone else's edit
    expect(sent.items[0].patch.links).toEqual([{ target_type: "person", target_id: "p1" }]);
    expect(sent.items[0].patch).not.toHaveProperty("privacy_level");
    expect(await screen.findByText(/Sent for review/)).toBeInTheDocument();
  });
});

describe("offering a family entry to everyone (ADR-0026 §4)", () => {
  it("offers a kuladevata with a temple name and shows each entry's status", async () => {
    await i18n.changeLanguage("en");
    document.cookie = "vsh_csrf=csrf-token";
    const fam = (code: string, label: string, offer_status = "none") => ({ code, label, labels: {}, aliases: [], status: "reviewed", origin: "family", id: code, offer_status });
    const fetchMock = vi.fn((url: RequestInfo | URL, init?: RequestInit) => {
      const u = String(url);
      if (init?.method === "POST" && u.includes("/offer")) return Promise.resolve(jsonResponse({ code: "t:khandoba", offer_status: "offered" }));
      if (u.includes("/vocabulary-offers")) return Promise.resolve(jsonResponse([{ id: "x", vocabulary_key: "devak", code: "t:panch", label: "Panchpallav", aliases: [], offer_status: "declined" }]));
      const m = u.match(/\/vocabularies\/([a-z]+)(?:\?|$)/);
      if (m) {
        const items = m[1] === "kuladevata" ? [fam("t:khandoba", "Khandoba"), { code: "khandoba_global", label: "Global", labels: {}, aliases: [], status: "reviewed", origin: "global" }] : m[1] === "devak" ? [fam("t:panch", "Panchpallav", "declined")] : [];
        return Promise.resolve(jsonResponse({ vocabulary: { key: m[1], description: "", version: 1, allows_custom: true, term_count: 0 }, items }));
      }
      return Promise.resolve(jsonResponse({}));
    });
    vi.stubGlobal("fetch", fetchMock);
    renderWithProviders(<OffersCard />);
    expect(await screen.findByText("Khandoba")).toBeInTheDocument();
    expect(screen.queryByText("Global")).not.toBeInTheDocument(); // only the family's own entries
    expect(await screen.findByText("Not added")).toBeInTheDocument();
    await userEvent.click(screen.getAllByRole("button", { name: "Offer to everyone" })[0]);
    const dialog = await screen.findByRole("dialog", { name: "Offer “Khandoba” to everyone" });
    expect(dialog).toHaveTextContent("your family is never named");
    await userEvent.type(screen.getByLabelText(/Well-known temple/), "Jejuri");
    await userEvent.click(screen.getByRole("button", { name: "Send offer" }));
    await waitFor(() => expect(fetchMock.mock.calls.some(([u, i]) => String(u).includes("/offer") && i?.method === "POST")).toBe(true));
    const [url, init] = fetchMock.mock.calls.find(([u, i]) => String(u).includes("/offer") && i?.method === "POST")!;
    expect(String(url)).toBe("/api/v1/trees/tree-1/vocabularies/kuladevata/terms/t%3Akhandoba/offer");
    expect(body(init)).toEqual({ note: null, temple: "Jejuri" });
  });
});

describe("family words", () => {
  it("reads a pattern in the UI language", async () => {
    await i18n.changeLanguage("en");
    expect(describePattern("father.brother:elder", i18n.t.bind(i18n))).toBe("father's brother (elder)");
    await i18n.changeLanguage("hi");
    expect(describePattern("brother.wife", i18n.t.bind(i18n))).toBe("भाई की पत्नी");
    await i18n.changeLanguage("en");
  });
});
