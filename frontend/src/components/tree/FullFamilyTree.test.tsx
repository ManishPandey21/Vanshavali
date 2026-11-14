import { afterEach, describe, expect, it, vi } from "vitest";
import { screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import type { FamilyGraphOut } from "../../api/types";
import { jsonResponse, renderWithProviders } from "../../test/utils";
import { FullFamilyTree } from "./FullFamilyTree";

const person = (id: string, name: string) => ({ id, display_name: name, profile_status: "deceased" as const, sex_at_birth: null });
const base = { scope: "connected" as const, root_id: "anita", revision: "r1", total_nodes: 4, total_people: 3, components: [], offset: 0 };
const page1: FamilyGraphOut = {
  ...base,
  components: [{ index: 0, size: 4, people: 3 }],
  nodes: [
    { id: "anita", person: person("anita", "Anita Pandey"), generation: 0, component: 0 },
    { id: "ramesh", person: person("ramesh", "Ramesh Pandey"), generation: 0, component: 0 },
  ],
  edges: [],
  links: [{ a: "anita", b: "ramesh", kind: "union", type: "spouse" }],
  complete: false,
  next_cursor: "CURSOR-2",
};
const page2: FamilyGraphOut = {
  ...base,
  offset: 2,
  nodes: [
    { id: "nana", person: person("nana", "Nana Mishra"), generation: -1, component: 0 },
    { id: "hidden-0-3", person: null, hidden: true, generation: 1, component: 0 },
  ],
  edges: [
    { source: "nana", target: "anita", type: "biological_parent", lineage: "biological" },
    { source: "anita", target: "hidden-0-3", type: "biological_parent", lineage: "biological" },
  ],
  links: [],
  complete: true,
  next_cursor: null,
};
const error = (status: number, code: string) => jsonResponse({ error: { code, message: code, details: null } }, status);

function setup(fetchMock: ReturnType<typeof vi.fn>, props: Partial<Parameters<typeof FullFamilyTree>[0]> = {}) {
  vi.stubGlobal("fetch", fetchMock);
  const onSelect = vi.fn();
  const onScope = vi.fn();
  renderWithProviders(
    <FullFamilyTree rootId="anita" rootName="Anita Pandey" scope="connected" onScope={onScope} view="list" selectedId={null} onSelect={onSelect} {...props} />,
  );
  return { onSelect, onScope };
}
const urls = (m: ReturnType<typeof vi.fn>) => m.mock.calls.map((c) => String(c[0]));
const status = () => screen.getByTestId("family-status");

afterEach(() => vi.unstubAllGlobals());

describe("the complete family view", () => {
  it("loads every page and only then says it shows everyone", async () => {
    let release!: () => void;
    const gate = new Promise<void>((r) => (release = r));
    const fetchMock = vi.fn(async (url: string) => {
      if (String(url).includes("cursor=CURSOR-2")) {
        await gate;
        return jsonResponse(page2);
      }
      return jsonResponse(page1);
    });
    setup(fetchMock);
    // first page in: partly loaded, and it says so
    await waitFor(() => expect(status()).toHaveAttribute("data-status", "partial"));
    expect(status()).toHaveTextContent("Loading the family: 2 of 3 people so far. This is not everyone yet.");
    expect(screen.queryByText(/Everyone connected to/)).not.toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Anita Pandey" })).toBeInTheDocument();
    release();
    await waitFor(() => expect(status()).toHaveAttribute("data-status", "complete"));
    expect(status()).toHaveTextContent("Everyone connected to Anita Pandey that you are allowed to see: 3 people");
    expect(status()).toHaveTextContent("3 generations");
    expect(status()).toHaveTextContent("1 private relative shown without a name");
    expect(urls(fetchMock)[0]).toContain("/api/v1/trees/tree-1/family-graph?scope=connected&person_id=anita");
    expect(urls(fetchMock)[0]).not.toContain("cursor");
    expect(fetchMock).toHaveBeenCalledTimes(2);
    // a hidden relative is an unnamed, unlinked entry; the people it sits between are named
    expect(screen.getByText("Private person")).toBeInTheDocument();
    expect(screen.getAllByRole("link").map((a) => a.textContent)).toEqual(["Nana Mishra", "Anita Pandey", "Ramesh Pandey"]);
    expect(screen.getByText(/Spouse \/ partner: Ramesh Pandey/)).toBeInTheDocument();
  });

  it("says the family is incomplete when loading stops, and can continue", async () => {
    let fail = true;
    const fetchMock = vi.fn(async (url: string) => {
      if (!String(url).includes("cursor=")) return jsonResponse(page1);
      return fail ? error(422, "invalid_cursor") : jsonResponse(page2);
    });
    setup(fetchMock);
    await waitFor(() => expect(status()).toHaveAttribute("data-status", "incomplete"));
    expect(status()).toHaveTextContent("Loading stopped. 2 of 3 people are shown, so this is not the whole family.");
    expect(screen.queryByText(/Everyone connected to/)).not.toBeInTheDocument();
    fail = false;
    await userEvent.click(within(status()).getByRole("button", { name: "Continue loading" }));
    await waitFor(() => expect(status()).toHaveAttribute("data-status", "complete"));
  });

  it("starts again when the tree changed between pages, so a removed person cannot linger", async () => {
    let changed = false;
    const after: FamilyGraphOut = { ...page1, revision: "r2", total_nodes: 1, total_people: 1, nodes: [page1.nodes[0]], links: [], complete: true, next_cursor: null };
    const fetchMock = vi.fn(async (url: string) => {
      if (String(url).includes("cursor=")) {
        changed = true;
        return error(409, "graph_changed");
      }
      return jsonResponse(changed ? after : page1);
    });
    setup(fetchMock);
    await waitFor(() => expect(status()).toHaveAttribute("data-status", "complete"));
    expect(screen.queryByRole("link", { name: "Ramesh Pandey" })).not.toBeInTheDocument();
    expect(fetchMock).toHaveBeenCalledTimes(3);
  });

  it("finds a loaded person by name and selects them", async () => {
    const { onSelect } = setup(vi.fn(async (url: string) => jsonResponse(String(url).includes("cursor=") ? page2 : page1)), { view: "chart" });
    await waitFor(() => expect(status()).toHaveAttribute("data-status", "complete"));
    await userEvent.type(screen.getByLabelText("Find a person in this view"), "nana");
    await userEvent.click(within(screen.getByRole("list", { name: "Matching people" })).getByRole("button", { name: /Nana Mishra/ }));
    expect(onSelect).toHaveBeenCalledWith("nana");
    await userEvent.type(screen.getByLabelText("Find a person in this view"), "zzz");
    expect(screen.getByText("Nobody in this view has that name")).toBeInTheDocument();
    // the chart has the standard controls and one card per returned node, the hidden one unnamed
    for (const name of ["Zoom in", "Zoom out", "Fit to screen", "Reset view", "Move view left"]) {
      expect(screen.getByRole("button", { name })).toBeInTheDocument();
    }
    expect(screen.getByRole("button", { name: /^Anita Pandey,/ })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /^Private person, generation 1/ })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Centre on Anita Pandey" })).toBeInTheDocument();
  });

  it("offers the whole tree as separate groups", async () => {
    const all: FamilyGraphOut = {
      ...page1,
      scope: "all",
      root_id: null,
      total_nodes: 3,
      total_people: 3,
      components: [
        { index: 0, size: 2, people: 2 },
        { index: 1, size: 1, people: 1 },
      ],
      nodes: [...page1.nodes, { id: "loner", person: person("loner", "Loner Rao"), generation: 0, component: 1 }],
      complete: true,
      next_cursor: null,
    };
    const fetchMock = vi.fn(async () => jsonResponse(all));
    const { onScope } = setup(fetchMock, { scope: "all" });
    await waitFor(() => expect(status()).toHaveAttribute("data-status", "complete"));
    expect(urls(fetchMock)[0]).toContain("scope=all");
    expect(urls(fetchMock)[0]).not.toContain("person_id");
    expect(status()).toHaveTextContent("Everyone in this tree that you are allowed to see: 3 people");
    expect(status()).toHaveTextContent("2 separate groups");
    expect(screen.getByRole("heading", { name: "Group 1 · 2 people" })).toBeInTheDocument();
    expect(screen.getByRole("heading", { name: "Group 2 · 1 person" })).toBeInTheDocument();
    expect(screen.getByText(/no link is assumed/)).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "All groups in this tree" })).toHaveAttribute("aria-pressed", "true");
    await userEvent.click(screen.getByRole("button", { name: "Connected family" }));
    expect(onScope).toHaveBeenCalledWith("connected");
  });

  it("stops calling the family complete while it is being reloaded after a change, or if that fails", async () => {
    // found by the independent review: the old pages must not keep their "complete" label
    let phase: "first" | "hold" | "fail" = "first";
    let release!: () => void;
    const gate = new Promise<void>((r) => (release = r));
    const whole: FamilyGraphOut = { ...page1, total_nodes: 2, total_people: 2, complete: true, next_cursor: null };
    const fetchMock = vi.fn(async () => {
      if (phase === "hold") await gate;
      if (phase !== "first") return error(422, "unprocessable");
      return jsonResponse(whole);
    });
    vi.stubGlobal("fetch", fetchMock);
    const { qc } = renderWithProviders(
      <FullFamilyTree rootId="anita" rootName="Anita Pandey" scope="connected" onScope={vi.fn()} view="list" selectedId={null} onSelect={vi.fn()} />,
    );
    await waitFor(() => expect(status()).toHaveAttribute("data-status", "complete"));
    phase = "hold";
    void qc.invalidateQueries({ queryKey: ["tree", "tree-1"] }); // what removing a person does
    await waitFor(() => expect(status()).not.toHaveAttribute("data-status", "complete"));
    expect(screen.queryByText(/Everyone connected to/)).not.toBeInTheDocument();
    phase = "fail";
    release();
    await waitFor(() => expect(status()).toHaveAttribute("data-status", "incomplete"));
    expect(screen.queryByText(/Everyone connected to/)).not.toBeInTheDocument();
    expect(within(status()).getByRole("button", { name: "Continue loading" })).toBeInTheDocument();
  });

  it("shows a refusal as a failure, never as an empty family", async () => {
    setup(vi.fn(async () => error(403, "forbidden")));
    await waitFor(() => expect(status()).toHaveAttribute("data-status", "incomplete"));
    expect(status()).toHaveTextContent("The family could not be loaded.");
    expect(screen.queryByText(/Everyone/)).not.toBeInTheDocument();
    expect(screen.queryByText(/No relatives are recorded/)).not.toBeInTheDocument();
  });
});
