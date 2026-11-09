import { useState } from "react";
import { describe, expect, it, vi } from "vitest";
import { screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import type { DocumentOut, MemberOut, SharingOut } from "../../api/types";
import { jsonResponse, renderWithProviders } from "../../test/utils";
import { VisibilitySharing, draftProblem, type SharingDraft } from "./VisibilitySharing";
import { DocumentSharingPanel } from "./RecordSharingPanel";

function member(id: string, name: string): MemberOut {
  return { id, user_id: `u-${id}`, email: "", display_name: name, roles: ["VIEWER"], branch_id: null, linked_person_id: null, created_at: "2026-11-01T00:00:00Z" };
}
const MEMBERS = [member("m-me", "Me"), member("m-asha", "Asha Iyer"), member("m-bhola", "Bhola Iyer"), member("m-kamla", "कमला देवी")];

function Harness({ initial, onDraft, ceiling }: { initial: SharingDraft; onDraft: (d: SharingDraft) => void; ceiling?: SharingOut["ceiling"] }) {
  const [d, setD] = useState(initial);
  return (
    <VisibilitySharing
      value={d}
      onChange={(n) => {
        setD(n);
        onDraft(n);
      }}
      members={MEMBERS}
      branches={[{ id: "b-pune", name: "Pune" } as never]}
      ownMembershipId="m-me"
      ceiling={ceiling}
    />
  );
}

const onlyMe: SharingDraft = { privacy_level: "ONLY_ME", audience_branch_id: null, allow_download: false, members: [] };

describe("VisibilitySharing", () => {
  it("offers the four audiences and a searchable member checklist with separate view and download", async () => {
    const user = userEvent.setup();
    const onDraft = vi.fn();
    renderWithProviders(<Harness initial={onlyMe} onDraft={onDraft} />);
    for (const label of ["Only me", "Selected members", "Selected branch", "All family members"]) {
      expect(screen.getByRole("radio", { name: label })).toBeInTheDocument();
    }
    expect(screen.queryByRole("radio", { name: /Public/ })).not.toBeInTheDocument();
    await user.click(screen.getByRole("radio", { name: "Selected members" }));
    const list = screen.getByRole("list", { name: "Family members to share with" });
    expect(within(list).queryByText("Me")).not.toBeInTheDocument(); // the owner needs no grant
    await user.type(screen.getByLabelText(/Search family members/), "कमला");
    expect(within(list).getByText("कमला देवी")).toBeInTheDocument();
    expect(within(list).queryByText("Asha Iyer")).not.toBeInTheDocument();
    await user.clear(screen.getByLabelText(/Search family members/));
    const asha = within(list).getByText("Asha Iyer").closest("li")!;
    await user.click(within(asha).getByRole("checkbox", { name: "Can view" }));
    expect(onDraft).toHaveBeenLastCalledWith(expect.objectContaining({ privacy_level: "SELECTED_MEMBERS", members: [{ membership_id: "m-asha", can_download: false }] }));
    await user.click(within(asha).getByRole("checkbox", { name: "Can download" }));
    expect(onDraft).toHaveBeenLastCalledWith(expect.objectContaining({ members: [{ membership_id: "m-asha", can_download: true }] }));
  });

  it("disables audiences wider than a tagged person allows, and says why", () => {
    renderWithProviders(<Harness initial={onlyMe} onDraft={() => undefined} ceiling={{ max_level: "SELECTED_MEMBERS", branch_ids: [] }} />);
    expect(screen.getByRole("radio", { name: "All family members" })).toBeDisabled();
    expect(screen.getByRole("radio", { name: "Selected branch" })).toBeDisabled();
    expect(screen.getByRole("radio", { name: "Selected members" })).toBeEnabled();
    expect(screen.getAllByText(/Someone tagged in this record is kept private/).length).toBeGreaterThan(0);
  });

  it("hides every download control for records without a download right (traditions)", () => {
    const selected: SharingDraft = { ...onlyMe, privacy_level: "SELECTED_MEMBERS", members: [{ membership_id: "m-asha", can_download: false }] };
    const { rerender } = renderWithProviders(
      <VisibilitySharing value={selected} onChange={() => undefined} members={MEMBERS} branches={[]} ownMembershipId="m-me" downloads={false} />,
    );
    expect(screen.getAllByRole("checkbox", { name: "Can view" }).length).toBe(3); // the checklist is there
    expect(screen.queryByRole("checkbox", { name: "Can download" })).not.toBeInTheDocument();
    rerender(<VisibilitySharing value={{ ...onlyMe, privacy_level: "TREE_MEMBERS" }} onChange={() => undefined} members={MEMBERS} branches={[]} downloads={false} />);
    expect(screen.queryByText(/download the original/)).not.toBeInTheDocument();
  });

  it("flags drafts that cannot be saved", () => {
    expect(draftProblem({ ...onlyMe, privacy_level: "SELECTED_MEMBERS" })).toBe("members");
    expect(draftProblem({ ...onlyMe, privacy_level: "FAMILY_BRANCH" })).toBe("branch");
    expect(draftProblem(onlyMe)).toBeNull();
  });
});

describe("DocumentSharingPanel", () => {
  const sharing: SharingOut = {
    privacy_level: "ONLY_ME",
    audience_branch_id: null,
    allow_download: false,
    is_owner: true,
    has_owner: true,
    can_edit: true,
    can_widen: true,
    legacy: false,
    ceiling: null,
    members: [],
    audience: [{ membership_id: "m-me", display_name: "Me", access: "owner", can_download: true }],
  };

  it("shows who has access and asks before sharing more widely", async () => {
    const user = userEvent.setup();
    const puts: unknown[] = [];
    vi.stubGlobal(
      "fetch",
      vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
        const url = String(input);
        if (url.includes("/auth/me")) return jsonResponse({ id: "u-m-me", email: "me@example.com", display_name: "Me" });
        if (url.endsWith("/members")) return jsonResponse(MEMBERS);
        if (url.endsWith("/branches")) return jsonResponse([]);
        if (url.endsWith("/sharing/preview"))
          return jsonResponse({ ...sharing, privacy_level: "TREE_MEMBERS", audience: [...sharing.audience, { membership_id: "m-asha", display_name: "Asha Iyer", access: "family", can_download: false }] });
        if (url.endsWith("/sharing") && init?.method === "PUT") {
          const body = JSON.parse(String(init.body));
          puts.push(body);
          if (!body.confirm_wider) return jsonResponse({ error: { code: "confirm_wider", message: "confirm", details: { viewers_added: 3, downloaders_added: 0 } } }, 409);
          return jsonResponse({ ...sharing, privacy_level: "TREE_MEMBERS" });
        }
        if (url.endsWith("/sharing")) return jsonResponse(sharing);
        return jsonResponse({});
      }),
    );
    renderWithProviders(<DocumentSharingPanel doc={{ id: "d1" } as DocumentOut} />);
    expect(await screen.findByText(/1 person can see this/)).toBeInTheDocument();
    await user.click(screen.getByRole("radio", { name: "All family members" }));
    expect(await screen.findByText(/Asha Iyer · Family member/)).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "Save sharing" }));
    const dialog = await screen.findByRole("dialog", { name: /Share more widely/ });
    expect(within(dialog).getByText(/3 more people/)).toBeInTheDocument();
    await user.click(within(dialog).getByRole("button", { name: "Yes, share" }));
    await waitFor(() => expect(puts).toHaveLength(2));
    expect(puts[0]).toMatchObject({ privacy_level: "TREE_MEMBERS", confirm_wider: false });
    expect(puts[1]).toMatchObject({ privacy_level: "TREE_MEMBERS", confirm_wider: true });
    vi.unstubAllGlobals();
  });
});
