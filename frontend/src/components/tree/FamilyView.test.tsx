import { describe, expect, it, vi } from "vitest";
import { screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import type { FamilyOut, PersonSummary, RelatedPerson } from "../../api/types";
import { attested, jsonResponse, makeTree, renderWithProviders } from "../../test/utils";
import { FamilyView } from "./FamilyView";
import { TreePersonPanel, ageFrom, roleKey } from "./TreePersonPanel";
import { initials } from "./FamilyCards";

const person = (id: string, name: string, sex: PersonSummary["sex_at_birth"], birth_year: number | null, status: PersonSummary["profile_status"] = "living"): PersonSummary => ({
  id,
  display_name: name,
  profile_status: status,
  sex_at_birth: sex,
  birth_year,
  death_year: null,
  birth_date: birth_year ? { precision: "year_only", year: birth_year } : null,
  birth_display: null,
  death_date: null,
  death_display: null,
  is_minor: false,
  is_protected: false,
  privacy_level: null,
});
const rel = (p: PersonSummary | null, type: RelatedPerson["relationship_type"] = "biological_parent"): RelatedPerson => ({
  person: p,
  hidden: !p,
  relationship_id: p ? `r-${p.id}` : null,
  relationship_type: type,
  lineage: "biological" as const,
  subtype: null,
  evidence_status: null,
});

const anand = person("anand", "Anand Iyer", "male", 1975);
const family = (over: Partial<FamilyOut> = {}): FamilyOut =>
  ({
    person: anand,
    parents: [rel(person("krishnan", "Krishnan Iyer", "male", 1945, "deceased"))],
    unions: [{ relationship: { id: "u1", type: "spouse" }, partner: rel(person("priya", "Priya Iyer", "female", 1978), "spouse"), children: [rel(person("arjun", "Arjun Iyer", "male", 2012))] }],
    other_children: [],
    siblings: [rel(person("ravi", "Ravi Iyer", "male", 1972), null), rel(null, null)],
    ...over,
  }) as unknown as FamilyOut;

function stub(f: FamilyOut) {
  vi.stubGlobal(
    "fetch",
    vi.fn(attested(async () => jsonResponse(f))),
  );
}

describe("family view", () => {
  it("puts parents above, the person among their siblings (eldest first) beside their spouse, and children below", async () => {
    stub(family());
    const onSelect = vi.fn();
    renderWithProviders(<FamilyView focusId="anand" lineage={[]} selectedId={null} onSelect={onSelect} />);
    const view = await screen.findByRole("region", { name: "Immediate family of Anand Iyer" });
    const names = within(view)
      .getAllByRole("button")
      .map((b) => b.getAttribute("aria-label")?.split(",")[0] ?? b.textContent);
    // reading order follows the drawing: parents, then the sibling row (Ravi 1972 before Anand 1975), spouse, children
    expect(names.filter((n) => /Iyer/.test(n ?? ""))).toEqual(["Krishnan Iyer", "Ravi Iyer", "Anand Iyer", "Priya Iyer", "Arjun Iyer"]);
    expect(within(view).getByRole("button", { name: /^Anand Iyer, .*centre of this view/ })).toBeInTheDocument();
    // a sibling the viewer may not see is shown, never named
    expect(within(view).getByText("Private person")).toBeInTheDocument();
    await userEvent.click(within(view).getByRole("button", { name: /^Arjun Iyer/ }));
    expect(onSelect).toHaveBeenCalledWith("arjun");
  });

  it("offers a slot for each missing parent, and nothing to add for a viewer who cannot edit", async () => {
    stub(family());
    const { unmount } = renderWithProviders(<FamilyView focusId="anand" lineage={[]} selectedId={null} onSelect={() => {}} />);
    expect(await screen.findByRole("button", { name: "Add mother" })).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Add father" })).not.toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Add child" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Add brother or sister" })).toBeInTheDocument();
    unmount();

    stub(family());
    renderWithProviders(<FamilyView focusId="anand" lineage={[]} selectedId={null} onSelect={() => {}} />, { tree: makeTree({ my_roles: ["VIEWER"], my_permissions: ["tree.read"] }) });
    await screen.findByRole("region", { name: "Immediate family of Anand Iyer" });
    expect(screen.queryByRole("button", { name: /^Add / })).not.toBeInTheDocument();
  });

  it("opens the add-relative dialog with the sex preset for “Add mother”", async () => {
    stub(family());
    renderWithProviders(<FamilyView focusId="anand" lineage={[]} selectedId={null} onSelect={() => {}} />);
    await userEvent.click(await screen.findByRole("button", { name: "Add mother" }));
    const dialog = await screen.findByRole("dialog");
    expect(within(dialog).getByRole("heading", { name: /Anand Iyer/ })).toBeInTheDocument();
    expect(within(dialog).getByLabelText(/Sex at birth/)).toHaveValue("female");
  });
});

describe("person panel", () => {
  it("says who the person is to you and lists their immediate family with family words", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn(
        attested(async (url) => {
          const u = String(url);
          if (u.includes("/relationship-path")) return jsonResponse({ from_id: "anand", to_id: "arjun", found: true, label: "son", chain: ["son"], path: [], common_ancestor_ids: [], lineages: [], explanation: null });
          if (u.includes("/family")) return jsonResponse(family({ person: person("arjun", "Arjun Iyer", "male", 2012), parents: [rel(anand), rel(person("priya", "Priya Iyer", "female", 1978))], unions: [], siblings: [] }));
          if (u.includes("/photos")) return jsonResponse([]);
          return jsonResponse({ ...person("arjun", "Arjun Iyer", "male", 2012), birth: { date: { precision: "exact", year: 2012, month: 10, day: 10 }, date_display: null, place_name: "Chennai" }, death: null, names: [], can_edit: true });
        }),
      ),
    );
    const onSelect = vi.fn();
    renderWithProviders(<TreePersonPanel personId="arjun" isFocus={false} onSelect={onSelect} onCentre={() => {}} onClose={() => {}} />, {
      tree: makeTree({ my_linked_person_id: "anand" }),
    });
    expect(await screen.findByRole("heading", { name: "Arjun Iyer" })).toHaveFocus();
    expect(await screen.findByText("Your son")).toBeInTheDocument();
    expect(screen.getByText(/Born 10 October 2012/)).toHaveTextContent("Chennai");
    expect(screen.getByRole("link", { name: "Profile" })).toHaveAttribute("href", "/t/tree-1/people/arjun");
    expect(screen.getByRole("link", { name: "How related?" })).toHaveAttribute("href", "/t/tree-1/relationship?from=anand&to=arjun");
    await userEvent.click(await screen.findByRole("button", { name: /Anand Iyer.*Father/ }));
    expect(onSelect).toHaveBeenCalledWith("anand");
    expect(screen.getByRole("button", { name: /Priya Iyer.*Mother/ })).toBeInTheDocument();
  });
});

describe("person panel relationship word", () => {
  it("uses the server's word for the reader (ADR-0026 §6), not a local table", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn(
        attested(async (url) => {
          const u = String(url);
          if (u.includes("/relationship-path"))
            return jsonResponse({
              from_id: "anand",
              to_id: "arjun",
              found: true,
              label: "uncle",
              chain: ["father", "brother"],
              path: [],
              common_ancestor_ids: [],
              lineages: [],
              explanation: null,
              terms: [{ lang: "hi", term: "ताऊ जी", review_status: "draft", family_word: true }],
            });
          if (u.includes("/family")) return jsonResponse(family({ person: person("arjun", "Arjun Iyer", "male", 1960), parents: [], unions: [], siblings: [] }));
          if (u.includes("/photos")) return jsonResponse([]);
          return jsonResponse({ ...person("arjun", "Arjun Iyer", "male", 1960), birth: null, death: null, names: [], can_edit: true });
        }),
      ),
    );
    renderWithProviders(<TreePersonPanel personId="arjun" isFocus={false} onSelect={() => {}} onCentre={() => {}} onClose={() => {}} />, {
      tree: makeTree({ my_linked_person_id: "anand" }),
    });
    expect(await screen.findByText("Your ताऊ जी")).toBeInTheDocument();
  });
});

describe("helpers", () => {
  it("names relatives by role and sex", () => {
    expect(roleKey("parent", "female")).toBe("treeView.role.mother");
    expect(roleKey("child", "male")).toBe("treeView.role.son");
    expect(roleKey("sibling", null)).toBe("treeView.role.sibling");
  });

  it("gives an age only for an exact Gregorian date of birth", () => {
    const today = new Date(2026, 9, 13);
    expect(ageFrom({ year: 1979, month: 11, day: 21 }, today)).toBe(46);
    expect(ageFrom({ year: 1979, month: 10, day: 13 }, today)).toBe(47);
    expect(ageFrom({ year: 1979 }, today)).toBeNull();
    expect(ageFrom({ year: 1979, month: 11, day: 21, calendar: "vikram_samvat" }, today)).toBeNull();
  });

  it("makes initials from the first two words, in any script", () => {
    expect(initials("Anand Iyer")).toBe("AI");
    expect(initials("सुरेश शर्मा")).toBe("सश");
  });
});
