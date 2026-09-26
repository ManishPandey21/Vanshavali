import { afterEach, describe, expect, it, vi } from "vitest";
import { screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { jsonResponse, renderWithProviders } from "../../test/utils";
import { ClaimsPage } from "./AdminPages";

const removal = {
  id: "c1",
  person_id: "p1",
  user_id: "u2",
  kind: "removal",
  status: "requested",
  message: "Please take me out",
  reviewed_by: null,
  reviewed_at: null,
  review_note: null,
  created_at: "2026-09-26T00:00:00Z",
  via_invite: true,
  claimant_name: "Meera Iyer",
  claimant_email: "meera@example.com",
};

afterEach(() => vi.unstubAllGlobals());

describe("ClaimsPage removal requests", () => {
  it("erases only after an explicit confirmation", async () => {
    document.cookie = "vsh_csrf=csrf-token";
    const fetchMock = vi.fn((input: RequestInfo | URL, init?: RequestInit) => {
      const url = String(input);
      if (init?.method === "POST") return Promise.resolve(jsonResponse({ ...removal, status: "approved", message: null }));
      if (url.includes("/claims")) return Promise.resolve(jsonResponse([removal]));
      return Promise.resolve(jsonResponse({ id: "p1", display_name: "Meera Iyer" }));
    });
    vi.stubGlobal("fetch", fetchMock);
    renderWithProviders(<ClaimsPage />);
    expect(await screen.findByText("Removal request")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Keep profile" })).toBeInTheDocument();
    await userEvent.click(screen.getByRole("button", { name: "Erase profile" }));
    const dialog = await screen.findByRole("dialog", { name: "Erase this profile permanently?" });
    expect(fetchMock.mock.calls.some(([, i]) => i?.method === "POST")).toBe(false);
    await userEvent.click(within(dialog).getByRole("button", { name: "Erase profile" }));
    await waitFor(() => expect(fetchMock.mock.calls.some(([u, i]) => i?.method === "POST" && String(u).endsWith("/claims/c1/approve"))).toBe(true));
  });
});
