import { afterEach, describe, expect, it, vi } from "vitest";
import { screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import i18n from "../../i18n";
import { jsonResponse, makeTree, renderWithProviders } from "../../test/utils";
import { MembersPage } from "./AdminPages";

const member = (id: string, name: string, roles: string[], can_manage: boolean) => ({
  id,
  user_id: `u-${id}`,
  email: `${id}@example.com`,
  display_name: name,
  roles,
  branch_id: null,
  linked_person_id: null,
  created_at: "2026-11-01T00:00:00Z",
  can_manage,
});

function serve() {
  return vi.fn((url: RequestInfo | URL) => {
    const u = String(url);
    if (u.endsWith("/auth/me")) return Promise.resolve(jsonResponse({ id: "u-me", email: "me@example.com", display_name: "Me" }));
    if (u.endsWith("/members"))
      return Promise.resolve(
        jsonResponse([
          member("owner", "Tree Owner", ["OWNER"], false),
          member("admin2", "Second admin", ["FAMILY_ADMIN"], false),
          member("cousin", "Cousin", ["CONTRIBUTOR"], true),
        ]),
      );
    if (u.endsWith("/branches")) return Promise.resolve(jsonResponse([]));
    if (u.includes("/people")) return Promise.resolve(jsonResponse({ items: [], next_cursor: null }));
    return Promise.resolve(jsonResponse({}));
  });
}

afterEach(() => vi.unstubAllGlobals());

describe("members page (role management)", () => {
  it("offers a family admin only the roles it may grant, and no controls for other admins", async () => {
    await i18n.changeLanguage("en");
    vi.stubGlobal("fetch", serve());
    const tree = makeTree({
      my_roles: ["FAMILY_ADMIN"],
      my_grantable_roles: ["BRANCH_ADMIN", "CONTRIBUTOR", "DOCUMENT_CUSTODIAN", "PROPERTY_CUSTODIAN", "RESEARCHER", "REVIEWER", "VIEWER"],
    });
    renderWithProviders(<MembersPage />, { tree });
    const cousinRow = (await screen.findByText("Cousin")).closest("tr")!;
    const ownerRow = screen.getByText("Tree Owner").closest("tr")!;
    const adminRow = screen.getByText("Second admin").closest("tr")!;
    // no change or remove for members whose roles this admin could not grant
    for (const row of [ownerRow, adminRow]) {
      expect(within(row).queryByRole("button", { name: "Change roles" })).not.toBeInTheDocument();
      expect(within(row).queryByRole("button", { name: /Remove/ })).not.toBeInTheDocument();
    }
    expect(within(cousinRow).getByRole("button", { name: "Remove Cousin" })).toBeInTheDocument();
    await userEvent.click(within(cousinRow).getByRole("button", { name: "Change roles" }));
    const dialog = await screen.findByRole("dialog");
    expect(within(dialog).queryByRole("checkbox", { name: /Owner/ })).not.toBeInTheDocument();
    expect(within(dialog).queryByRole("checkbox", { name: /Family admin/i })).not.toBeInTheDocument();
    expect(within(dialog).getByRole("checkbox", { name: /Contributor/ })).toBeChecked();
    expect(within(dialog).getByRole("checkbox", { name: /Viewer/ })).toBeEnabled();
  });
});
