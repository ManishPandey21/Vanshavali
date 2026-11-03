import { afterEach, describe, expect, it, vi } from "vitest";
import { screen, within } from "@testing-library/react";
import type { GraphOut, PersonSummary } from "../../api/types";
import { jsonResponse, makeTree, renderWithProviders } from "../../test/utils";
import { DashboardPage } from "./DashboardPage";
import { TreeViewerPage } from "./TreeViewerPage";

const p = (id: string, name: string, extra: Partial<PersonSummary> = {}): PersonSummary =>
  ({ id, display_name: name, profile_status: "deceased", sex_at_birth: "male", ...extra }) as PersonSummary;
// Dates are mostly missing, as in a typical imported tree: the elder is found by climbing, not by age.
const gopal = p("p-gp", "Gopal Rao");
const ravi = p("p-dad", "Ravi Rao");
const asha = p("p-me", "Asha Rao", { profile_status: "living", sex_at_birth: "female", birth_year: 1990 });
const cousin = p("p-c", "Kiran Rao", { birth_year: 1950 });

const ancestorsOfMe: GraphOut = {
  root_id: "p-me", direction: "ancestors", depth: 25, truncated: false,
  nodes: [
    { id: "p-me", person: asha, generation: 0 },
    { id: "p-dad", person: ravi, generation: -1 },
    { id: "p-gp", person: gopal, generation: -2 },
  ],
  edges: [],
};
const descendantsOf = (root: PersonSummary): GraphOut => ({
  root_id: root.id, direction: "descendants", depth: 8, truncated: false,
  nodes: [
    { id: "p-gp", person: gopal, generation: 0 },
    { id: "p-dad", person: ravi, generation: 1 },
    { id: "p-me", person: asha, generation: 2 },
  ],
  edges: [
    { source: "p-gp", target: "p-dad", type: "biological_parent" },
    { source: "p-dad", target: "p-me", type: "biological_parent" },
  ] as GraphOut["edges"],
});

function stub(people: PersonSummary[]) {
  const calls: string[] = [];
  vi.stubGlobal(
    "fetch",
    vi.fn(async (input: RequestInfo | URL) => {
      const url = new URL(String(input), "http://x");
      calls.push(url.pathname + url.search);
      const path = url.pathname.replace("/api/v1/trees/tree-1", "");
      const page = (items: unknown[]) => jsonResponse({ items, next_cursor: null });
      if (path === "/people") return page(people);
      if (path === "/branches" || path === "/households") return jsonResponse([]);
      if (path === "/places" || path === "/sources") return page([]);
      if (path === "/people/p-me/ancestors") return jsonResponse(ancestorsOfMe);
      if (path === "/people/p-gp/descendants") return jsonResponse(descendantsOf(gopal));
      const one = people.find((x) => path === `/people/${x.id}`);
      if (one) return jsonResponse({ ...one, names: [] });
      if (/\/people\/[^/]+\/(ancestors|descendants)$/.test(path)) return jsonResponse({ ...ancestorsOfMe, root_id: path.split("/")[2], nodes: [] });
      return jsonResponse({ error: { code: "not_found", message: path } }, 404);
    }),
  );
  return calls;
}

afterEach(() => {
  vi.unstubAllGlobals();
  window.localStorage.clear();
});

describe("family home", () => {
  it("opens on the whole family, grown down from the eldest ancestor above you, with you marked", async () => {
    const calls = stub([asha, cousin, ravi, gopal]);
    renderWithProviders(<DashboardPage />, { tree: makeTree({ my_linked_person_id: "p-me" }) });

    expect(await screen.findByRole("heading", { level: 2, name: "The family of Gopal Rao" })).toBeInTheDocument();
    expect(await screen.findByText(/3 generations · 3 people in view/)).toBeInTheDocument();
    const chart = screen.getByRole("group", { name: "Family tree chart" });
    expect(within(chart).getByRole("button", { name: /^Asha Rao.*This is you\.$/ })).toBeInTheDocument();
    expect(within(chart).getByRole("button", { name: /^Gopal Rao/ })).toBeInTheDocument();
    // it climbed from the viewer, not from the earliest recorded birth (Kiran, 1950)
    expect(calls.some((c) => c.startsWith("/api/v1/trees/tree-1/people/p-me/ancestors"))).toBe(true);
    expect(screen.getByRole("link", { name: /Open full tree/ })).toHaveAttribute("href", "/t/tree-1/tree/p-gp?dir=descendants");
    // the old stat tiles are still one click away
    expect(screen.getByRole("link", { name: /4 People/ })).toHaveAttribute("href", "/t/tree-1/people");
  });

  it("greets an empty tree with one way to plant the first name", async () => {
    stub([]);
    renderWithProviders(<DashboardPage />);
    expect(await screen.findByRole("heading", { name: "Your vanshavali starts with one name" })).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Add the first person" })).toHaveAttribute("href", "/t/tree-1/people/new");
    expect(screen.queryByRole("group", { name: "Family tree chart" })).not.toBeInTheDocument();
  });

  it("does not offer adding people to a viewer who may not", async () => {
    stub([]);
    renderWithProviders(<DashboardPage />, { tree: makeTree({ my_roles: ["VIEWER"], my_permissions: ["tree.read"] }) });
    expect(await screen.findByRole("heading", { name: "Your vanshavali starts with one name" })).toBeInTheDocument();
    expect(screen.queryByRole("link", { name: /Add the first person|Add person/ })).not.toBeInTheDocument();
    expect(screen.queryByRole("link", { name: "Invite family" })).not.toBeInTheDocument();
  });
});

describe("tree viewer with nobody to start from", () => {
  it("opens on the family elder's descendants instead of an empty search box", async () => {
    stub([asha, cousin, ravi, gopal]);
    // No linked profile and nothing recently viewed: the climb starts from the earliest-born
    // person (Kiran, 1950), who has no recorded ancestors, so Kiran is the elder.
    renderWithProviders(<TreeViewerPage />, { tree: makeTree({ my_linked_person_id: null }), route: "/t/tree-1/tree" });
    expect(await screen.findByRole("heading", { level: 1, name: /Family tree of Kiran Rao/ })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /Descendants/ })).toHaveAttribute("aria-pressed", "true");
  });
});
