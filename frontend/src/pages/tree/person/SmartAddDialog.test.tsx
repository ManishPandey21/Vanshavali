import { describe, expect, it, vi } from "vitest";
import { screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { attested, jsonResponse, renderWithProviders } from "../../../test/utils";
import { SmartAddDialog } from "./SmartAddDialog";

const anchor = { id: "a1", display_name: "Aarav Sharma", profile_status: "living" as const, sex_at_birth: "male" as const };
const mother = { id: "m1", display_name: "Sunita Sharma", profile_status: "deceased" as const, sex_at_birth: "female" as const };
const nana = { id: "g1", display_name: "Gopal Verma", profile_status: "deceased" as const, sex_at_birth: "male" as const };

const terms = [
  { code: "brother", group: "direct", hops: [{ relation: "sibling", sex: "male", age: null }], asks_relative_age: true },
  { code: "mama", group: "maternal", hops: [{ relation: "parent", sex: "female", age: null }, { relation: "sibling", sex: "male", age: null }], asks_relative_age: false },
];

const stepBase = { index: 0, relation: "parent", sex: "female", age: null, from_person: anchor, hidden_candidates: 0, allow_new: false };

function planFor(term: string, choices: string[]) {
  if (term === "brother") {
    return {
      term,
      anchor,
      steps: [],
      complete: true,
      target: { relation: "sibling", sex: "male", age: null, from_person: anchor, link: "explicit_sibling", shared_parents: [], other_parent_options: [] },
      preview: [
        { kind: "existing", person: anchor },
        { kind: "new", relation: "sibling", link: "explicit_sibling", age: null },
      ],
    };
  }
  if (!choices.length) return { term, anchor, steps: [{ ...stepBase, candidates: [mother] }], complete: false, preview: [] };
  return {
    term,
    anchor,
    steps: [{ ...stepBase, candidates: [mother], chosen: mother }],
    complete: true,
    target: { relation: "sibling", sex: "male", age: null, from_person: mother, link: "shared_parents", shared_parents: [nana], other_parent_options: [] },
    preview: [
      { kind: "existing", person: anchor },
      { kind: "existing", person: mother, relation: "parent", link: "parent" },
      { kind: "new", relation: "sibling", link: "shared_parents", age: null },
    ],
  };
}

function server() {
  return vi.fn((url: RequestInfo | URL, init?: RequestInit) => {
    const u = String(url);
    if (u.endsWith("/smart-add/terms")) return Promise.resolve(jsonResponse(terms));
    if (u.endsWith("/smart-add/plan")) {
      const body = JSON.parse(String(init?.body));
      return Promise.resolve(jsonResponse(planFor(body.term, body.choices)));
    }
    if (u.endsWith("/smart-add")) {
      const person = { id: "new-1", display_name: "Mohan Verma", profile_status: "unknown", sex_at_birth: "male" };
      return Promise.resolve(
        jsonResponse({ operation_id: "op-1", person, created_people: [person], relationships: [], relative_age_order_ids: [], undo_expires_in_seconds: 1800 }, 201),
      );
    }
    if (u.endsWith("/undo")) return Promise.resolve(jsonResponse({ message: "Undone" }));
    return Promise.resolve(jsonResponse({}, 404));
  });
}

const commits = (fetchMock: ReturnType<typeof server>) => fetchMock.mock.calls.filter(([u]) => String(u).endsWith("/smart-add"));

describe("SmartAddDialog", () => {
  it("adds a Mama through the recorded mother, previewing before anything is saved", async () => {
    document.cookie = "vsh_csrf=csrf-token";
    const fetchMock = server();
    vi.stubGlobal("fetch", vi.fn(attested(fetchMock)));
    renderWithProviders(<SmartAddDialog anchor={anchor} onClose={() => undefined} />);
    const dialog = screen.getByRole("dialog");

    await userEvent.click(await within(dialog).findByText("More relations"));
    await userEvent.click(within(dialog).getByRole("button", { name: /Mama · मामा/ }));
    // step: whose mother? the recorded one is offered; no "add as unknown" because one is recorded
    const continueBtn = await within(dialog).findByRole("button", { name: "Continue" });
    expect(continueBtn).toBeDisabled();
    await userEvent.click(within(dialog).getByRole("radio", { name: /Sunita Sharma/ }));
    expect(within(dialog).queryByText(/as unknown for now/)).not.toBeInTheDocument();
    await userEvent.click(continueBtn);

    // details: sex at birth is offered from the term, not imposed
    const sex = await within(dialog).findByLabelText("Sex at birth");
    expect(sex).toHaveValue("male");
    await userEvent.type(within(dialog).getByLabelText("Given name"), "Mohan");
    await userEvent.type(within(dialog).getByLabelText("Surname"), "Verma");
    await userEvent.type(within(dialog).getByLabelText("Born about (year)"), "1962");
    await userEvent.click(within(dialog).getByRole("button", { name: "Review" }));

    // preview: every record, and nothing saved yet
    expect(await within(dialog).findByText(/Sunita Sharma \(already in the tree\)/)).toBeInTheDocument();
    expect(within(dialog).getByText(/Mohan Verma \(new\)/)).toBeInTheDocument();
    expect(within(dialog).getByText(/Linked as a child of Gopal Verma/)).toBeInTheDocument();
    expect(commits(fetchMock)).toHaveLength(0);

    await userEvent.click(within(dialog).getByRole("button", { name: "Confirm and add" }));
    await waitFor(() => expect(commits(fetchMock)).toHaveLength(1));
    const [url, init] = commits(fetchMock)[0];
    expect(url).toBe("/api/v1/trees/tree-1/people/a1/smart-add");
    expect((init!.headers as Record<string, string>)["X-CSRF-Token"]).toBe("csrf-token");
    const body = JSON.parse(String(init!.body));
    expect(body).toMatchObject({
      term: "mama",
      choices: ["m1"],
      provisional_sex_at_birth: ["female"],
      new_person: {
        sex_at_birth: "male",
        names: [{ given_name: "Mohan", surname: "Verma", language: "en", script: "Latn", is_preferred: true }],
        birth: { date: { precision: "circa", year: 1962 } },
      },
    });

    expect(await within(dialog).findByText(/Mohan Verma was added as Aarav Sharma's Mama/)).toBeInTheDocument();
    await userEvent.click(within(dialog).getByRole("button", { name: "Undo" }));
    expect(await within(dialog).findByText(/Undone/)).toBeInTheDocument();
    expect(fetchMock.mock.calls.some(([u]) => String(u).endsWith("/smart-add/op-1/undo"))).toBe(true);
  });

  it("lets the user clear the suggested sex and record an elder brother; Devanagari names are tagged", async () => {
    const fetchMock = server();
    vi.stubGlobal("fetch", vi.fn(attested(fetchMock)));
    renderWithProviders(<SmartAddDialog anchor={anchor} onClose={() => undefined} />);
    const dialog = screen.getByRole("dialog");
    await userEvent.click(await within(dialog).findByRole("button", { name: /^Brother/ }));
    await userEvent.selectOptions(await within(dialog).findByLabelText("Sex at birth"), "");
    await userEvent.type(within(dialog).getByLabelText("Given name"), "विक्रम");
    await userEvent.click(within(dialog).getByRole("radio", { name: "Older" }));
    await userEvent.click(within(dialog).getByRole("button", { name: "Review" }));
    expect(await within(dialog).findByText(/Recorded as older than Aarav Sharma/)).toBeInTheDocument();
    await userEvent.click(within(dialog).getByRole("button", { name: "Confirm and add" }));
    await waitFor(() => expect(commits(fetchMock)).toHaveLength(1));
    const body = JSON.parse(String(commits(fetchMock)[0][1]!.body));
    expect(body.term).toBe("brother");
    expect(body.relative_age).toBe("elder");
    expect(body.new_person.sex_at_birth).toBeNull();
    expect(body.new_person.names[0]).toMatchObject({ given_name: "विक्रम", language: "hi", script: "Deva" });
    expect(body.new_person.birth).toBeUndefined();
  });

  it("refuses to review without any name", async () => {
    const fetchMock = server();
    vi.stubGlobal("fetch", vi.fn(attested(fetchMock)));
    renderWithProviders(<SmartAddDialog anchor={anchor} onClose={() => undefined} />);
    const dialog = screen.getByRole("dialog");
    await userEvent.click(await within(dialog).findByRole("button", { name: /^Brother/ }));
    await userEvent.click(await within(dialog).findByRole("button", { name: "Review" }));
    expect(await within(dialog).findByText(/Enter at least a given name or a surname/)).toBeInTheDocument();
    expect(commits(fetchMock)).toHaveLength(0);
  });
});
