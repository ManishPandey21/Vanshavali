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

const nomination = (over: Record<string, unknown> = {}) => ({
  id: "nom-1",
  nominee_membership_id: "cousin",
  nominee_name: "Cousin",
  nominator_name: "Second admin",
  reason: "Keeps the Varanasi records",
  status: "open",
  created_at: "2026-11-09T00:00:00Z",
  expires_at: "2026-11-23T00:00:00Z",
  nominee_accepted: false,
  nominee_branch_scoped: false,
  is_mine: false,
  can_accept: false,
  can_decline: false,
  can_decide: false,
  can_withdraw: false,
  ...over,
});

function serve(nominations: unknown[] = []) {
  return vi.fn((url: RequestInfo | URL, init?: RequestInit) => {
    const u = String(url);
    if (u.includes("/admin-nominations/") && init?.method === "POST") return Promise.resolve(jsonResponse(nomination({ status: "approved" })));
    if (u.endsWith("/admin-nominations") && init?.method === "POST") return Promise.resolve(jsonResponse(nomination(), 201));
    if (u.endsWith("/admin-nominations")) return Promise.resolve(jsonResponse(nominations));
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

describe("family admin nominations (ADR-0006 amendment of 9 Nov 2026)", () => {
  const calls = (fetch: ReturnType<typeof serve>, part: string) =>
    fetch.mock.calls.filter(([u, init]) => String(u).includes(part) && (init as RequestInit | undefined)?.method === "POST");

  it("lets a family admin nominate an ordinary member, with a reason, but not an admin", async () => {
    await i18n.changeLanguage("en");
    const fetch = serve();
    vi.stubGlobal("fetch", fetch);
    renderWithProviders(<MembersPage />, { tree: makeTree({ my_roles: ["FAMILY_ADMIN"], my_grantable_roles: ["CONTRIBUTOR", "VIEWER"] }) });
    const cousinRow = (await screen.findByText("Cousin")).closest("tr")!;
    for (const name of ["Tree Owner", "Second admin"]) {
      expect(within(screen.getByText(name).closest("tr")!).queryByRole("button", { name: /Nominate/ })).not.toBeInTheDocument();
    }
    await userEvent.click(within(cousinRow).getByRole("button", { name: "Nominate Cousin for family admin" }));
    const dialog = await screen.findByRole("dialog");
    const submit = within(dialog).getByRole("button", { name: "Nominate" });
    expect(submit).toBeDisabled(); // a reason is required
    await userEvent.type(within(dialog).getByLabelText(/Why this member/), "Keeps the Varanasi records");
    await userEvent.click(submit);
    const [[, init]] = calls(fetch, "/admin-nominations");
    expect(JSON.parse(String((init as RequestInit).body))).toEqual({ membership_id: "cousin", reason: "Keeps the Varanasi records" });
  });

  it("offers no nominate button to an owner, who grants the role directly", async () => {
    await i18n.changeLanguage("en");
    vi.stubGlobal("fetch", serve());
    renderWithProviders(<MembersPage />, { tree: makeTree({ my_roles: ["OWNER"], my_grantable_roles: ["OWNER", "FAMILY_ADMIN", "CONTRIBUTOR"] }) });
    await screen.findByText("Cousin");
    expect(screen.queryByRole("button", { name: /Nominate/ })).not.toBeInTheDocument();
  });

  it("shows the nominee who nominated them and why, and lets them accept", async () => {
    await i18n.changeLanguage("en");
    const fetch = serve([nomination({ is_mine: true, can_accept: true, can_decline: true })]);
    vi.stubGlobal("fetch", fetch);
    renderWithProviders(<MembersPage />, { tree: makeTree({ my_roles: ["CONTRIBUTOR"], my_permissions: ["tree.read"], my_grantable_roles: [] }) });
    const item = await screen.findByRole("listitem", { name: "Nomination of Cousin" });
    expect(within(item).getByText("Second admin nominated you to be a family admin")).toBeInTheDocument();
    expect(within(item).getByText("Keeps the Varanasi records")).toBeInTheDocument();
    expect(within(item).queryByRole("button", { name: "Approve" })).not.toBeInTheDocument();
    await userEvent.click(within(item).getByRole("button", { name: "Accept nomination" }));
    expect(calls(fetch, "/admin-nominations/nom-1/accept")).toHaveLength(1);
  });

  it("makes an owner wait for the nominee and confirm removing a branch scope", async () => {
    await i18n.changeLanguage("en");
    const waiting = nomination({ can_decide: true });
    const fetch = serve([waiting, nomination({ id: "nom-2", nominee_name: "Branch cousin", nominee_membership_id: "x", can_decide: true, nominee_accepted: true, nominee_branch_scoped: true })]);
    vi.stubGlobal("fetch", fetch);
    renderWithProviders(<MembersPage />, { tree: makeTree({ my_roles: ["OWNER"] }) });
    const first = await screen.findByRole("listitem", { name: "Nomination of Cousin" });
    expect(within(first).getByRole("button", { name: "Approve" })).toBeDisabled();
    expect(within(first).getByText("You can approve once Cousin has accepted.")).toBeInTheDocument();
    const second = screen.getByRole("listitem", { name: "Nomination of Branch cousin" });
    await userEvent.click(within(second).getByRole("button", { name: "Approve" }));
    const dialog = await screen.findByRole("dialog");
    const approve = within(dialog).getByRole("button", { name: "Approve" });
    expect(approve).toBeDisabled();
    await userEvent.click(within(dialog).getByRole("checkbox", { name: /Remove Branch cousin's branch scope/ }));
    await userEvent.click(approve);
    const [[, init]] = calls(fetch, "/admin-nominations/nom-2/approve");
    expect(JSON.parse(String((init as RequestInit).body))).toEqual({ clear_branch: true });
  });
});
