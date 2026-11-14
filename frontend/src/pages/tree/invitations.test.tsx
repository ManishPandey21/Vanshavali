import { useState } from "react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import i18n from "../../i18n";
import { jsonResponse, makeTree, renderWithProviders } from "../../test/utils";
import { ClaimInviteShare } from "../../components/consent/ClaimInviteShare";
import { InvitationsPage } from "./AdminPages";

function serve() {
  const createdAt = new Date().toISOString();
  const expiresAt = new Date(Date.now() + 7 * 86_400_000).toISOString();
  return vi.fn((input: RequestInfo | URL, init?: RequestInit) => {
    const url = String(input);
    const method = init?.method ?? "GET";
    if (url.endsWith("/invitations") && method === "GET") {
      return Promise.resolve(
        jsonResponse([
          {
            id: "membership-1",
            email: "relative@example.com",
            roles: ["VIEWER"],
            branch_id: null,
            expires_at: expiresAt,
            accepted_at: null,
            revoked_at: null,
            created_at: createdAt,
            invite_url: null,
            token: null,
          },
        ]),
      );
    }
    if (url.includes("/claim-invites") && method === "GET") {
      return Promise.resolve(
        jsonResponse([
          {
            id: "claim-1",
            person_id: "person-1",
            person_name: "Meera Iyer",
            offered_role: "VIEWER",
            expires_at: expiresAt,
            created_at: createdAt,
            created_by: "user-1",
            used_at: "2026-11-13T01:00:00Z",
            revoked_at: null,
            state: "used",
            claim_status: "requested",
          },
        ]),
      );
    }
    if (url.includes("/people?") && method === "GET") {
      return Promise.resolve(
        jsonResponse({
          items: [
            { id: "person-1", display_name: "Meera Iyer", profile_status: "living", sex_at_birth: "female" },
            { id: "person-2", display_name: "Kavita Iyer", profile_status: "living", sex_at_birth: "female" },
          ],
          next_cursor: null,
        }),
      );
    }
    if (url.includes("/people/") && url.endsWith("/claim-invites") && method === "POST") {
      return Promise.resolve(
        jsonResponse(
          {
            id: "new-claim",
            url: "https://vanshavali.example/claim/one-time-token",
            expires_at: expiresAt,
          },
          201,
        ),
      );
    }
    if (url.endsWith("/branches")) return Promise.resolve(jsonResponse([]));
    throw new Error(`unexpected ${method} ${url}`);
  });
}

afterEach(() => vi.unstubAllGlobals());

describe("invitation front door", () => {
  it("keeps email membership and profile-claim invitations distinct and shows only factual statuses", async () => {
    await i18n.changeLanguage("en");
    const fetchMock = serve();
    vi.stubGlobal("fetch", fetchMock);
    renderWithProviders(<InvitationsPage />, { tree: makeTree() });

    expect(await screen.findByRole("heading", { name: "Invite family member" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /Invite by verified email/ })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /Invite to claim a profile/ })).toBeInTheDocument();

    const emailItem = await screen.findByRole("listitem", { name: /Email invitation for relative@example.com/ });
    expect(within(emailItem).getByText("Created")).toBeInTheDocument();
    const claimItem = await screen.findByRole("listitem", { name: /Profile invitation for Meera Iyer/ });
    expect(within(claimItem).getByText("Claim requested")).toBeInTheDocument();
    expect(screen.queryByText("Sent")).not.toBeInTheDocument();
    expect(fetchMock.mock.calls.some(([input]) => String(input).includes("/people?"))).toBe(false);

    await userEvent.click(screen.getByRole("button", { name: /Invite to claim a profile/ }));
    expect(screen.getByLabelText("Relative's profile")).toBeInTheDocument();
    expect(screen.getByText(/A shared link never grants access/)).toBeInTheDocument();
  });

  it("derives available invitation modes from the tree permissions", async () => {
    await i18n.changeLanguage("en");
    vi.stubGlobal("fetch", serve());
    renderWithProviders(<InvitationsPage />, {
      tree: makeTree({ my_roles: ["CONTRIBUTOR"], my_permissions: ["tree.read", "person.write"] }),
    });

    expect(await screen.findByRole("heading", { name: "Invite a relative to claim their profile" })).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /Invite by verified email/ })).not.toBeInTheDocument();
    expect(screen.getByLabelText("Relative's profile")).toBeInTheDocument();
  });

  it("preserves a one-time claim link when checking the email mode", async () => {
    await i18n.changeLanguage("en");
    vi.stubGlobal("fetch", serve());
    renderWithProviders(<InvitationsPage />, { tree: makeTree() });

    await userEvent.click(await screen.findByRole("button", { name: /Invite to claim a profile/ }));
    await userEvent.type(screen.getByLabelText("Relative's profile"), "Meera");
    await userEvent.click(await screen.findByRole("option", { name: /Meera Iyer/ }));
    await userEvent.click(screen.getByRole("button", { name: /Create a private link for Meera Iyer/ }));
    expect(await screen.findByRole("link", { name: /Share on WhatsApp/ })).toBeInTheDocument();

    await userEvent.click(screen.getByRole("button", { name: /Invite by verified email/ }));
    await userEvent.click(screen.getByRole("button", { name: /Invite to claim a profile/ }));
    expect(screen.getByRole("link", { name: /Share on WhatsApp/ })).toBeInTheDocument();
  });

  it("resets a generated link when the selected relative changes", async () => {
    await i18n.changeLanguage("en");
    vi.stubGlobal("fetch", serve());
    function SwitchingRelative() {
      const [relative, setRelative] = useState({ id: "person-1", name: "Meera Iyer" });
      return (
        <>
          <button type="button" onClick={() => setRelative({ id: "person-2", name: "Kavita Iyer" })}>
            Choose Kavita
          </button>
          <ClaimInviteShare treeId="tree-1" personId={relative.id} personName={relative.name} canOfferContributor={false} />
        </>
      );
    }
    renderWithProviders(<SwitchingRelative />);

    await userEvent.click(screen.getByRole("button", { name: /Create a private link for Meera Iyer/ }));
    expect(await screen.findByRole("link", { name: /Share on WhatsApp/ })).toBeInTheDocument();
    await userEvent.click(screen.getByRole("button", { name: "Choose Kavita" }));

    expect(screen.queryByRole("link", { name: /Share on WhatsApp/ })).not.toBeInTheDocument();
    expect(screen.getByRole("button", { name: /Create a private link for Kavita Iyer/ })).toBeInTheDocument();
  });

  it("copies the generic invitation message rather than a bare private URL", async () => {
    await i18n.changeLanguage("en");
    vi.stubGlobal("fetch", serve());
    const writeText = vi.fn().mockResolvedValue(undefined);
    vi.stubGlobal("navigator", { ...navigator, clipboard: { writeText } });
    renderWithProviders(<ClaimInviteShare treeId="tree-1" personId="person-1" personName="Meera Iyer" canOfferContributor={false} />);

    await userEvent.click(screen.getByRole("button", { name: /Create a private link for Meera Iyer/ }));
    await userEvent.click(await screen.findByRole("button", { name: "Copy invitation" }));

    expect(writeText).toHaveBeenCalledWith(expect.stringContaining("I've started our family tree on Vanshavali"));
    expect(writeText).toHaveBeenCalledWith(expect.stringContaining("https://vanshavali.example/claim/one-time-token"));
  });
});
