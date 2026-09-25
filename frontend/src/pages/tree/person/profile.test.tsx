import { describe, expect, it, vi } from "vitest";
import { screen, waitFor } from "@testing-library/react";
import type { FamilyOut, PersonOut } from "../../../api/types";
import { jsonResponse, makeTree, renderWithProviders } from "../../../test/utils";
import { OverviewTab } from "./OverviewTab";
import { FamilyPanel, FamilyTab } from "./FamilyTab";

const livingPerson: PersonOut = {
  id: "p1",
  display_name: "Krishnan Iyer",
  profile_status: "living",
  sex_at_birth: "male",
  birth_year: 1950,
  is_protected: true,
  privacy_level: "TREE_MEMBERS",
  names: [],
  birth: {
    event_id: "e1",
    date: { calendar: "gregorian", precision: "year_only", year: 1950, redacted: true },
    date_display: "1950",
    time: null,
    place_name: null,
    place_as_recorded: null,
    redacted_fields: ["birth_date_full", "birth_time", "birth_place_detail"],
  },
  redacted_fields: ["birth_date_full", "birth_time", "birth_place_detail", "contact"],
  can_edit: false,
};

const family: FamilyOut = {
  person: { id: "p1", display_name: "Krishnan Iyer", profile_status: "living", sex_at_birth: "male" },
  parents: [
    { person: null, hidden: true, relationship_type: "biological_parent" },
    {
      person: { id: "p2", display_name: "Lakshmi Iyer", profile_status: "deceased", sex_at_birth: "female" },
      relationship_id: "r2",
      relationship_type: "adoptive_parent",
      lineage: "legal",
    },
  ],
  unions: [],
  other_children: [],
  siblings: [{ person: null, hidden: true, kind: "half" }],
};

describe("person profile privacy", () => {
  it("shows redaction notices instead of hidden values", () => {
    renderWithProviders(<OverviewTab person={livingPerson} />);
    expect(screen.getByText(/Full date hidden by privacy settings/)).toBeInTheDocument();
    // birth time, birth place and contact are all hidden
    expect(screen.getAllByText("Hidden by privacy settings").length).toBeGreaterThanOrEqual(3);
    expect(screen.getByText("Year only")).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /Edit details/ })).not.toBeInTheDocument();
  });

  it("renders hidden relatives as a non-linked 'Private person' placeholder", () => {
    renderWithProviders(<FamilyPanel family={family} canWrite={false} />);
    expect(screen.getAllByText("Private person")).toHaveLength(2);
    expect(screen.getByRole("link", { name: /Lakshmi Iyer/ })).toBeInTheDocument();
    expect(screen.getAllByRole("link")).toHaveLength(1);
    expect(screen.getByText("Adoptive")).toBeInTheDocument();
    expect(screen.getByText("Half-sibling")).toBeInTheDocument();
  });
});

describe("permission-based hiding", () => {
  it("hides add-relative actions when the person is not editable", async () => {
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(jsonResponse(family)));
    renderWithProviders(<FamilyTab person={{ ...livingPerson, can_edit: false }} />);
    await screen.findByText("Lakshmi Iyer");
    expect(screen.queryByRole("button", { name: "Add parent" })).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Remove relationship" })).not.toBeInTheDocument();
  });

  it("hides them when the tree role lacks relationship.write even if can_edit", async () => {
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(jsonResponse(family)));
    renderWithProviders(<FamilyTab person={{ ...livingPerson, can_edit: true }} />, { tree: makeTree({ my_roles: ["VIEWER"], my_permissions: ["tree.read"] }) });
    await screen.findByText("Lakshmi Iyer");
    expect(screen.queryByRole("button", { name: "Add parent" })).not.toBeInTheDocument();
  });

  it("shows them for editors", async () => {
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(jsonResponse(family)));
    renderWithProviders(<FamilyTab person={{ ...livingPerson, can_edit: true }} />);
    await waitFor(() => expect(screen.getByRole("button", { name: "Add parent" })).toBeInTheDocument());
  });
});
