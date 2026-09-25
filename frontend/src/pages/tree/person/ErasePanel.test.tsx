import { describe, expect, it, vi } from "vitest";
import { screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import type { PersonOut } from "../../../api/types";
import { jsonResponse, makeTree, renderWithProviders } from "../../../test/utils";
import { ErasePanel, eraseAllowed } from "./ErasePanel";

const person: PersonOut = { id: "p1", display_name: "Kamala Devi", profile_status: "living", sex_at_birth: "female", can_edit: true };

describe("erase confirmation gate", () => {
  it("requires the exact name and a reason", () => {
    expect(eraseAllowed("Kamala Devi", "Kamala Devi", "own request")).toBe(true);
    expect(eraseAllowed("Kamala Devi", "kamala devi", "own request")).toBe(false);
    expect(eraseAllowed("Kamala Devi", "Kamala", "own request")).toBe(false);
    expect(eraseAllowed("Kamala Devi", "Kamala Devi", "ok")).toBe(false);
  });

  it("keeps the button disabled until confirmed, then posts confirm=true with the reason", async () => {
    const fetchMock = vi.fn(async () => jsonResponse({ message: "erased" }));
    vi.stubGlobal("fetch", fetchMock);
    renderWithProviders(<ErasePanel person={person} />);
    await userEvent.click(screen.getByRole("button", { name: /Erase this person's data/ }));
    const dialog = screen.getByRole("dialog");
    expect(within(dialog).getByText(/anonymous placeholder/)).toBeInTheDocument();
    const submit = within(dialog).getByRole("button", { name: "Erase permanently" });
    expect(submit).toBeDisabled();
    await userEvent.type(within(dialog).getByLabelText(/^Reason/), "Her own erasure request");
    await userEvent.type(within(dialog).getByLabelText(/Type the name/), "Kamala Dev");
    expect(submit).toBeDisabled();
    await userEvent.type(within(dialog).getByLabelText(/Type the name/), "i");
    expect(submit).toBeEnabled();
    expect(fetchMock).not.toHaveBeenCalled();
    await userEvent.click(submit);
    await waitFor(() => expect(fetchMock).toHaveBeenCalled());
    const [url, init] = fetchMock.mock.calls[0] as unknown as [string, RequestInit];
    expect(url).toBe("/api/v1/trees/tree-1/people/p1/erase");
    expect(JSON.parse(String(init.body))).toEqual({ reason: "Her own erasure request", confirm: true });
  });

  it("is not offered to members without tree.manage", () => {
    renderWithProviders(<ErasePanel person={person} />, { tree: makeTree({ my_roles: ["CONTRIBUTOR"], my_permissions: ["tree.read", "person.write"] }) });
    expect(screen.queryByRole("button", { name: /Erase/ })).not.toBeInTheDocument();
  });
});
