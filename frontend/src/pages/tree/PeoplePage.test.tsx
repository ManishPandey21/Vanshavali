import { describe, expect, it, vi } from "vitest";
import { screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { jsonResponse, renderWithProviders } from "../../test/utils";
import { PeoplePage } from "./PeoplePage";

const ordinary = { id: "p1", display_name: "Aarav Verma", profile_status: "living", is_provisional: false, provisional_state: null };
const unnamed = { id: "p2", display_name: "Unnamed", profile_status: "unknown", is_provisional: true, provisional_state: "needs_details" };
const unverified = { id: "p3", display_name: "Sunita Verma", profile_status: "unknown", is_provisional: true, provisional_state: "unverified" };

function server() {
  return vi.fn((url: RequestInfo | URL) => {
    const u = new URL(String(url), "http://x");
    if (u.pathname.endsWith("/people")) {
      const items = u.searchParams.getAll("provisional_state").length ? [unnamed, unverified] : [ordinary, unnamed, unverified];
      return Promise.resolve(jsonResponse({ items, next_cursor: null }));
    }
    return Promise.resolve(jsonResponse({ hits: [] }));
  });
}

const peopleCalls = (f: ReturnType<typeof server>) =>
  f.mock.calls.map(([u]) => new URL(String(u), "http://x")).filter((u) => u.pathname.endsWith("/people"));

describe("PeoplePage: To complete view", () => {
  it("asks the server for provisional people only, and says what each one is missing", async () => {
    const fetchMock = server();
    vi.stubGlobal("fetch", fetchMock);
    renderWithProviders(<PeoplePage />, { route: "/t/tree-1/people" });
    expect(await screen.findByText("Aarav Verma")).toBeInTheDocument();

    const toggle = screen.getByRole("button", { name: "To complete" });
    expect(toggle).toHaveAttribute("aria-pressed", "false");
    await userEvent.click(toggle);
    expect(toggle).toHaveAttribute("aria-pressed", "true");

    await waitFor(() => expect(screen.queryByText("Aarav Verma")).not.toBeInTheDocument());
    expect(peopleCalls(fetchMock).at(-1)!.searchParams.getAll("provisional_state")).toEqual(["needs_details", "unverified"]);
    expect(screen.getByText(/only you and the tree admins can see them/)).toBeInTheDocument();

    const rows = screen.getAllByRole("listitem");
    const unnamedRow = rows.find((r) => within(r).queryByText("Unnamed"))!;
    expect(within(unnamedRow).getByText("No name yet.")).toBeInTheDocument();
    expect(within(unnamedRow).getByRole("link", { name: /Add their name/ })).toHaveAttribute("href", "/t/tree-1/people/p2?tab=overview");
    expect(within(unnamedRow).getByText("To complete")).toBeInTheDocument(); // the badge

    const unverifiedRow = rows.find((r) => within(r).queryByText("Sunita Verma"))!;
    expect(within(unverifiedRow).getByText(/no supporting evidence yet/)).toBeInTheDocument();
    expect(within(unverifiedRow).getByRole("link", { name: /Review relationship evidence/ })).toHaveAttribute("href", "/t/tree-1/people/p3?tab=family");
    expect(within(unverifiedRow).getByText("Not yet verified")).toBeInTheDocument();
  });

  it("shows a calm empty state when nothing is left to complete", async () => {
    vi.stubGlobal("fetch", vi.fn(() => Promise.resolve(jsonResponse({ items: [], next_cursor: null }))));
    renderWithProviders(<PeoplePage />, { route: "/t/tree-1/people?view=to-complete" });
    expect(await screen.findByText("Nothing to complete")).toBeInTheDocument();
    expect(screen.queryByText(/No people yet|Add the first person/)).not.toBeInTheDocument();
  });
});
