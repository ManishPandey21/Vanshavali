import { describe, expect, it, vi } from "vitest";
import { screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import type { UnionOut } from "../../../api/types";
import { jsonResponse, renderWithProviders } from "../../../test/utils";
import { AddRelativeDialog } from "./AddRelativeDialog";

const anchor = { id: "anchor-1", display_name: "Ramesh Sharma", profile_status: "living" as const, sex_at_birth: "male" as const };
const unions: UnionOut[] = [
  {
    relationship: {
      id: "union-1",
      person_a_id: "anchor-1",
      person_b_id: "wife-1",
      type: "spouse",
      subtype: null,
      lineage: null,
      union_id: null,
      start_date: null,
      end_date: null,
      union_order: 1,
      legal_status: null,
      notes: null,
      evidence_status: "USER_ASSERTION",
      confidence: "unknown",
    },
    partner: { person: { id: "wife-1", display_name: "Sunita Sharma", profile_status: "living", sex_at_birth: "female" } },
    children: [],
  },
];

describe("AddRelativeDialog", () => {
  it("posts a new child linked to the chosen union", async () => {
    document.cookie = "vsh_csrf=csrf-token";
    const fetchMock = vi.fn().mockResolvedValue(
      jsonResponse({ person: { id: "c1", display_name: "Aarav Sharma", profile_status: "living", sex_at_birth: "male" }, relationships: [] }, 201),
    );
    vi.stubGlobal("fetch", fetchMock);
    const onClose = vi.fn();
    renderWithProviders(<AddRelativeDialog anchor={anchor} relation="child" unions={unions} onClose={onClose} />);
    const dialog = screen.getByRole("dialog");
    expect(within(dialog).getByLabelText("Which union?")).toHaveValue("union-1");
    const name1 = within(dialog).getByRole("group", { name: "Name 1" });
    await userEvent.type(within(name1).getByLabelText("Given name"), "Aarav");
    await userEvent.type(within(name1).getByLabelText("Surname / family name"), "Sharma");
    await userEvent.selectOptions(within(dialog).getByLabelText("Sex at birth"), "male");
    await userEvent.selectOptions(within(dialog).getByLabelText("Living status"), "living");
    await userEvent.click(within(dialog).getByRole("button", { name: "Add child" }));

    await waitFor(() => expect(fetchMock).toHaveBeenCalled());
    const [url, init] = fetchMock.mock.calls.find(([u]) => String(u).includes("/relatives"))!;
    expect(url).toBe("/api/v1/trees/tree-1/people/anchor-1/relatives");
    expect(init.method).toBe("POST");
    expect(init.headers["X-CSRF-Token"]).toBe("csrf-token");
    const body = JSON.parse(init.body);
    expect(body).toMatchObject({
      relation: "child",
      relationship_type: "biological_parent",
      union_id: "union-1",
      new_person: {
        profile_status: "living",
        sex_at_birth: "male",
        names: [{ given_name: "Aarav", surname: "Sharma", is_preferred: true, type: "birth" }],
      },
    });
    expect(body.existing_person_id).toBeUndefined();
    // No birth details were entered, so none are sent (nothing invented).
    expect(body.new_person.birth).toBeUndefined();
    await waitFor(() => expect(onClose).toHaveBeenCalled());
  });

  it("does not submit a new person without any name", async () => {
    const fetchMock = vi.fn();
    vi.stubGlobal("fetch", fetchMock);
    renderWithProviders(<AddRelativeDialog anchor={anchor} relation="parent" unions={[]} onClose={() => undefined} />);
    await userEvent.click(within(screen.getByRole("dialog")).getByRole("button", { name: "Add parent" }));
    expect(await screen.findByText(/Enter at least a given name/)).toBeInTheDocument();
    expect(fetchMock).not.toHaveBeenCalled();
  });

  it("posts a spouse with a year-only marriage date", async () => {
    const fetchMock = vi.fn().mockResolvedValue(jsonResponse({ person: anchor, relationships: [] }, 201));
    vi.stubGlobal("fetch", fetchMock);
    renderWithProviders(<AddRelativeDialog anchor={anchor} relation="spouse" unions={[]} onClose={() => undefined} />);
    const dialog = screen.getByRole("dialog");
    await userEvent.type(within(within(dialog).getByRole("group", { name: "Name 1" })).getByLabelText("Given name"), "Sunita");
    const marriage = within(dialog).getByRole("group", { name: "Date of marriage / start of union" });
    await userEvent.selectOptions(within(marriage).getByLabelText("How precise is this date?"), "year_only");
    await userEvent.type(within(marriage).getByLabelText(/^Year/), "1995");
    await userEvent.click(within(dialog).getByRole("button", { name: "Add spouse" }));
    await waitFor(() => expect(fetchMock).toHaveBeenCalled());
    const body = JSON.parse(fetchMock.mock.calls[0][1].body);
    expect(body).toMatchObject({ relation: "spouse", relationship_type: "spouse", start_date: { calendar: "gregorian", precision: "year_only", year: 1995 } });
  });
});
