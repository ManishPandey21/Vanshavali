import { describe, expect, it, vi } from "vitest";
import { screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import type { FamilyOut, PersonOut } from "../../../api/types";
import { jsonResponse, makeTree, renderWithProviders } from "../../../test/utils";
import { OverviewTab } from "./OverviewTab";
import { FamilyPanel, FamilyTab } from "./FamilyTab";
import { AddressesContactsTab } from "./AddressesContactsTab";

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

describe("private addresses and contacts", () => {
  it("shows address history data, masks contacts, and reveals only on request", async () => {
    const fetch = vi.fn().mockImplementation((input: RequestInfo | URL) => {
      const url = String(input);
      if (url.endsWith("/addresses")) {
        return Promise.resolve(
          jsonResponse({ items: [
            {
              id: "a1",
              person_id: "p1",
              purpose: "current_residence",
              status: "current",
              is_primary_current: true,
              place_id: null,
              building: "Nalanda House",
              street: "Temple Road",
              locality: "Mylapore",
              district: "Chennai",
              state: "Tamil Nadu",
              country_code: "IN",
              postal_code: "600004",
              landmark: null,
              notes: null,
              as_recorded: null,
              valid_from: null,
              valid_until: null,
              revision: 1,
              source: "manual",
              created_at: "2026-11-12T00:00:00Z",
              updated_at: "2026-11-12T00:00:00Z",
            },
          ], next_cursor: null }),
        );
      }
      if (url.endsWith("/contacts")) {
        return Promise.resolve(
          jsonResponse({ items: [
            {
              id: "c1",
              person_id: "p1",
              kind: "email",
              hint: "r***@example.com",
              purpose: "Personal",
              language: null,
              is_preferred: true,
              revision: 1,
              source: "manual",
              created_at: "2026-11-12T00:00:00Z",
              updated_at: "2026-11-12T00:00:00Z",
            },
            {
              id: "c2",
              person_id: "p1",
              kind: "telegram",
              hint: "@f***",
              purpose: null,
              language: null,
              is_preferred: false,
              revision: 1,
              source: "manual",
              created_at: "2026-11-12T00:00:00Z",
              updated_at: "2026-11-12T00:00:00Z",
            },
          ], next_cursor: null }),
        );
      }
      if (url.endsWith("/addresses/a1/history")) {
        return Promise.resolve(jsonResponse({ items: [{ revision: 1, operation: "created", reason: null, before: null, after: {}, created_at: "2026-11-12T00:00:00Z" }], next_cursor: null }));
      }
      if (url.endsWith("/contacts/c1/reveal")) {
        return Promise.resolve(jsonResponse({ id: "c1", value: "ravi@example.com" }));
      }
      if (url.endsWith("/contacts/c2/reveal")) {
        return Promise.resolve(jsonResponse({ id: "c2", value: "@family_builder", profile_url: "https://t.me/family_builder" }));
      }
      throw new Error(`Unexpected request ${url}`);
    });
    vi.stubGlobal("fetch", fetch);
    const user = userEvent.setup();
    renderWithProviders(<AddressesContactsTab personId="p1" canEdit />);
    expect(await screen.findByText("Nalanda House, Temple Road")).toBeInTheDocument();
    expect(screen.getByText("r***@example.com")).toBeInTheDocument();
    expect(screen.queryByText("ravi@example.com")).not.toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "Reveal Email" }));
    expect(await screen.findByText("ravi@example.com")).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "Reveal Telegram" }));
    expect(await screen.findByRole("link", { name: "@family_builder" })).toHaveAttribute("href", "https://t.me/family_builder");
    await user.click(screen.getByRole("button", { name: "History" }));
    const historyDialog = await screen.findByRole("dialog", { name: "Address history" });
    expect(screen.getByText(/Revision 1/)).toBeInTheDocument();
    await user.click(within(historyDialog).getAllByRole("button", { name: "Close" }).at(-1)!);
    await user.click(screen.getByRole("button", { name: "I moved" }));
    expect(screen.getByRole("dialog", { name: "Record a move" })).toBeInTheDocument();
    expect(screen.getByLabelText("Move date")).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "Cancel" }));
    await user.click(screen.getByRole("button", { name: "Add address" }));
    expect(screen.getByRole("dialog", { name: "Add address" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /Find in the Local Government Directory/i })).toBeInTheDocument();
  });

  it("reuses operation idempotency keys when a failed save is retried", async () => {
    const address = {
      id: "a1",
      person_id: "p1",
      purpose: "current_residence",
      status: "current",
      is_primary_current: true,
      place_id: null,
      building: "Existing House",
      street: null,
      locality: "Mylapore",
      sub_district: null,
      district: "Chennai",
      state: "Tamil Nadu",
      country_code: "IN",
      postal_code: null,
      landmark: null,
      gram_panchayat: null,
      post_office: null,
      notes: null,
      as_recorded: null,
      valid_from: null,
      valid_until: null,
      revision: 1,
      source: "manual",
      created_at: "2026-11-12T00:00:00Z",
      updated_at: "2026-11-12T00:00:00Z",
    };
    const attempts: Record<"address" | "move" | "contact", Array<Record<string, unknown>>> = {
      address: [],
      move: [],
      contact: [],
    };
    const fetch = vi.fn().mockImplementation((input: RequestInfo | URL, init?: RequestInit) => {
      const url = String(input);
      const method = init?.method ?? "GET";
      if (method === "GET" && url.endsWith("/addresses")) {
        return Promise.resolve(jsonResponse({ items: [address], next_cursor: null }));
      }
      if (method === "GET" && url.endsWith("/contacts")) {
        return Promise.resolve(jsonResponse({ items: [], next_cursor: null }));
      }
      const body = JSON.parse(String(init?.body)) as Record<string, unknown>;
      if (method === "POST" && url.endsWith("/addresses")) {
        attempts.address.push(body);
        return Promise.resolve(attempts.address.length === 1
          ? jsonResponse({ error: { code: "temporary", message: "Try again" } }, 503)
          : jsonResponse({ ...address, id: "a2", building: "New House" }, 201));
      }
      if (method === "POST" && url.endsWith("/addresses/a1/move")) {
        attempts.move.push(body);
        return Promise.resolve(attempts.move.length === 1
          ? jsonResponse({ error: { code: "temporary", message: "Try again" } }, 503)
          : jsonResponse({ former_address: { ...address, status: "former" }, new_address: { ...address, id: "a3", building: "Moved House" } }));
      }
      if (method === "POST" && url.endsWith("/contacts")) {
        attempts.contact.push(body);
        return Promise.resolve(attempts.contact.length === 1
          ? jsonResponse({ error: { code: "temporary", message: "Try again" } }, 503)
          : jsonResponse({ id: "c1", person_id: "p1", kind: "email", hint: "r***@example.com", purpose: null, language: null, is_preferred: false, copied_from_contact_id: null, copy_outdated: false, revision: 1, source: "manual", created_at: "2026-11-12T00:00:00Z", updated_at: "2026-11-12T00:00:00Z" }, 201));
      }
      throw new Error(`Unexpected request ${method} ${url}`);
    });
    vi.stubGlobal("fetch", fetch);
    const user = userEvent.setup();
    renderWithProviders(<AddressesContactsTab personId="p1" canEdit />);
    await screen.findByText("Existing House");

    await user.click(screen.getByRole("button", { name: "Add address" }));
    let dialog = screen.getByRole("dialog", { name: "Add address" });
    await user.type(within(dialog).getByLabelText("Building or house"), "New House");
    let save = within(dialog).getByRole("button", { name: "Save address" });
    await user.click(save);
    await waitFor(() => expect(attempts.address).toHaveLength(1));
    await waitFor(() => expect(save).not.toBeDisabled());
    await user.click(save);
    await waitFor(() => expect(screen.queryByRole("dialog", { name: "Add address" })).not.toBeInTheDocument());

    await user.click(screen.getByRole("button", { name: "I moved" }));
    dialog = screen.getByRole("dialog", { name: "Record a move" });
    await user.type(within(dialog).getByLabelText("Building or house"), "Moved House");
    save = within(dialog).getByRole("button", { name: "Record move" });
    await user.click(save);
    await waitFor(() => expect(attempts.move).toHaveLength(1));
    await waitFor(() => expect(save).not.toBeDisabled());
    await user.click(save);
    await waitFor(() => expect(screen.queryByRole("dialog", { name: "Record a move" })).not.toBeInTheDocument());

    await user.click(screen.getByRole("button", { name: "Add contact" }));
    dialog = screen.getByRole("dialog", { name: "Add contact method" });
    await user.type(within(dialog).getByLabelText(/Contact value/), "ravi@example.com");
    save = within(dialog).getByRole("button", { name: "Save contact" });
    await user.click(save);
    await waitFor(() => expect(attempts.contact).toHaveLength(1));
    await waitFor(() => expect(save).not.toBeDisabled());
    await user.click(save);
    await waitFor(() => expect(screen.queryByRole("dialog", { name: "Add contact method" })).not.toBeInTheDocument());

    expect(attempts.address[0].idempotency_key).toBe(attempts.address[1].idempotency_key);
    expect(attempts.move[0].idempotency_key).toBe(attempts.move[1].idempotency_key);
    expect(attempts.contact[0].idempotency_key).toBe(attempts.contact[1].idempotency_key);
  });
});
