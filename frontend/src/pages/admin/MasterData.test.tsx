import { afterEach, describe, expect, it, vi } from "vitest";
import { screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { Route, Routes } from "react-router-dom";
import { jsonResponse, renderWithProviders } from "../../test/utils";
import { MasterDataDashboard, MasterDataLayout, VocabularyAdminPage } from "./MasterDataPages";
import { suggestCode } from "./TermEditor";

const me = (extra: object = {}) => ({
  id: "u1",
  email: "admin@example.com",
  display_name: "Platform Admin",
  preferred_language: "en",
  created_at: "2026-01-01T00:00:00Z",
  mfa_enabled: true,
  email_verified: true,
  must_change_password: false,
  is_system_admin: true,
  ...extra,
});

const vocab = {
  key: "gotra",
  description: "Gotra suggestions",
  category: "heritage",
  version: 1,
  revision: 3,
  source: "Pack",
  licence: "CC0",
  allows_custom: true,
  fixed_membership: false,
  counts: { draft: 2, reviewed: 1, retired: 0 },
  pending_changes: 1,
};
const term = (code: string, en: string, hi: string, extra: object = {}) => ({
  code,
  labels: { en, hi },
  aliases: [],
  scope: [],
  parent_code: null,
  attributes: {},
  source_url: null,
  status: "draft",
  sort_order: 0,
  successor_code: null,
  managed_by: "pack",
  revision: 1,
  updated_at: "2026-11-05T00:00:00Z",
  pending_change_id: null,
  ...extra,
});

function route(handlers: Record<string, unknown>) {
  const calls: { url: string; init?: RequestInit }[] = [];
  const fetchMock = vi.fn((input: RequestInfo | URL, init?: RequestInit) => {
    const url = String(input);
    calls.push({ url, init });
    const hit = Object.entries(handlers).find(([k]) => url.includes(k));
    return Promise.resolve(hit ? jsonResponse(hit[1]) : jsonResponse({ error: { code: "not_found", message: "Not found" } }, 404));
  });
  vi.stubGlobal("fetch", fetchMock);
  return calls;
}

function Console({ child }: { child: React.ReactNode }) {
  return (
    <Routes>
      <Route path="/" element={<p>Home page</p>} />
      <Route path="/admin/master-data" element={<MasterDataLayout />}>
        <Route index element={child} />
        <Route path="v/:key" element={child} />
      </Route>
    </Routes>
  );
}

afterEach(() => vi.unstubAllGlobals());

describe("Master data console", () => {
  it("is not shown to ordinary users (the server refuses them anyway)", async () => {
    route({ "/auth/me": me({ is_system_admin: false }) });
    renderWithProviders(<Console child={<MasterDataDashboard />} />, { tree: null, route: "/admin/master-data" });
    expect(await screen.findByText("Home page")).toBeInTheDocument();
  });

  it("asks a system admin without MFA to turn it on first", async () => {
    const calls = route({ "/auth/me": me({ mfa_enabled: false }) });
    renderWithProviders(<Console child={<MasterDataDashboard />} />, { tree: null, route: "/admin/master-data" });
    expect(await screen.findByRole("alert")).toHaveTextContent("Turn on two-step sign-in first");
    expect(screen.getByRole("link", { name: "Open account settings" })).toHaveAttribute("href", "/account");
    expect(calls.some((c) => c.url.includes("/admin/master-data/vocabularies"))).toBe(false);
  });

  it("groups vocabularies and says what is not managed here", async () => {
    route({ "/auth/me": me(), "/admin/master-data/vocabularies": [vocab] });
    renderWithProviders(<Console child={<MasterDataDashboard />} />, { tree: null, route: "/admin/master-data" });
    const heritage = await screen.findByRole("region", { name: "Cultural & heritage" });
    expect(within(heritage).getByRole("link", { name: /Gotra/ })).toHaveAttribute("href", "/admin/master-data/v/gotra");
    expect(within(heritage).getByText("1 pending change")).toBeInTheDocument();
    expect(screen.getByText(/no access to any family's tree/)).toBeInTheDocument();
    expect(screen.getByText("Code-controlled")).toBeInTheDocument();
  });

  it("lists terms in a table and opens the editor with keyboard-reachable controls", async () => {
    const calls = route({
      "/auth/me": me(),
      "/duplicates": [{ code: "bharadwaja", label: "Bharadwaja", status: "draft", matched: "Bhardwaj" }],
      "/admin/master-data/vocabularies/gotra/terms": {
        vocabulary: vocab,
        items: [term("bharadwaja", "Bharadwaja", "भरद्वाज", { aliases: ["Bhardwaj"] })],
        total: 1,
        next_cursor: null,
      },
    });
    renderWithProviders(<Console child={<VocabularyAdminPage />} />, { tree: null, route: "/admin/master-data/v/gotra" });
    const table = await screen.findByRole("table", { name: "Terms in Gotra" });
    expect(within(table).getByRole("rowheader", { name: /Bharadwaja · भरद्वाज/ })).toBeInTheDocument();
    await userEvent.click(screen.getByRole("button", { name: "Add new" }));
    const dialog = await screen.findByRole("dialog", { name: "Add a term" });
    await userEvent.type(within(dialog).getByLabelText(/English label/), "Bhardwaj Rishi");
    expect(within(dialog).getByLabelText(/^Code/)).toHaveValue("bhardwaj_rishi");
    // duplicate warning appears while typing
    expect(await within(dialog).findByText("This may already exist")).toBeInTheDocument();
    // client-side checks before anything is sent: Hindi label and reason are required
    await userEvent.click(within(dialog).getByRole("button", { name: "Publish now" }));
    expect(within(dialog).getByLabelText(/Hindi label/)).toHaveAttribute("aria-invalid", "true");
    await waitFor(() => expect(calls.some((c) => c.url.endsWith("/changes"))).toBe(false));
  });

  it("suggests ASCII codes from labels", () => {
    expect(suggestCode("Tulja Bhavani")).toBe("tulja_bhavani");
    expect(suggestCode("Kāśyapa")).toBe("kasyapa");
    expect(suggestCode("कश्यप")).toBe("");
  });
});
