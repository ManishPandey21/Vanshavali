import { afterEach, describe, expect, it, vi } from "vitest";
import { act, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import type { EventOut, PersonOut } from "../../../api/types";
import { attested, jsonResponse, renderWithProviders } from "../../../test/utils";
import { OverviewTab } from "./OverviewTab";

const birthEvent = {
  id: "e1",
  type: "birth",
  date: { calendar: "gregorian", precision: "year_only", year: 1950 },
  time: null,
  place_as_recorded: "Kanpur",
  evidence_status: "USER_ASSERTION",
  is_preferred: true,
  redacted_fields: [],
} as unknown as EventOut;

const withBirth: PersonOut = {
  id: "p1",
  display_name: "Ramesh Sharma",
  profile_status: "living",
  sex_at_birth: "male",
  names: [],
  birth: { event_id: "e1", date: { calendar: "gregorian", precision: "year_only", year: 1950 }, date_display: "1950", time: null, place_name: null, place_as_recorded: "Kanpur", redacted_fields: [] },
  death: null,
  redacted_fields: [],
  can_edit: true,
} as unknown as PersonOut;

function mockFetch() {
  const fetchMock = vi.fn(
    attested(async (url) => {
      if (String(url).endsWith("/people/p1/events")) return jsonResponse([birthEvent]);
      return jsonResponse([]);
    }),
  );
  vi.stubGlobal("fetch", fetchMock);
  return fetchMock;
}
const eventsCalls = (m: ReturnType<typeof mockFetch>) => m.mock.calls.filter((c) => String(c[0]).endsWith("/people/p1/events"));

afterEach(() => vi.unstubAllGlobals());

describe("Overview birth/death actions", () => {
  it("keeps a draft bound to its original revision across background event refreshes", async () => {
    const calls: Record<string, unknown>[] = [];
    vi.stubGlobal("fetch", vi.fn(attested(async (url, init) => {
      if (init?.method === "PATCH") {
        calls.push(JSON.parse(String(init.body)));
        return jsonResponse({ error: { code: "stale_revision", message: "Reload before saving" } }, 409);
      }
      if (String(url).endsWith("/people/p1/events")) return jsonResponse([{ ...birthEvent, revision: 4 }]);
      return jsonResponse([]);
    })));
    const { qc } = renderWithProviders(<OverviewTab person={withBirth} />);
    await userEvent.click(await screen.findByRole("button", { name: "Edit date of birth" }));
    await screen.findByDisplayValue("1950");
    await act(async () => {
      qc.setQueryData(["tree", "tree-1", "person", "p1", "events"], [{ ...birthEvent, revision: 5, date: { precision: "year_only", year: 2000 } }]);
    });
    await userEvent.click(screen.getByRole("button", { name: "Save" }));
    await waitFor(() => expect(calls).toHaveLength(1));
    expect(calls[0].expected_revision).toBe(4);
    expect(await screen.findByDisplayValue("1950")).toBeInTheDocument();
    expect(screen.getByRole("dialog")).toHaveTextContent("Reload before saving");
  });

  it("hides birth actions for field groups that are hidden from this editor", async () => {
    mockFetch();
    renderWithProviders(<OverviewTab person={{ ...withBirth, redacted_fields: ["birth_date_full", "birth_time", "birth_place_detail"] }} />);
    expect(screen.queryByRole("button", { name: /Edit (date of birth|birth time|birthplace)/ })).not.toBeInTheDocument();
    expect(screen.queryByText("Kanpur")).not.toBeInTheDocument();
  });

  it("shows a recoverable missing-event state instead of a silent dead end", async () => {
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(jsonResponse([])));
    renderWithProviders(<OverviewTab person={withBirth} />);
    await userEvent.click(await screen.findByRole("button", { name: "Edit date of birth" }));
    expect(await screen.findByText(/This event could not be loaded/)).toBeInTheDocument();
    await userEvent.click(screen.getByRole("button", { name: "Cancel" }));
    expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
  });

  it("shows loading while the event request is pending", async () => {
    vi.stubGlobal("fetch", vi.fn(attested(async (url) => {
      if (String(url).endsWith("/people/p1/events")) return new Promise<Response>(() => {});
      return jsonResponse([]);
    })));
    renderWithProviders(<OverviewTab person={withBirth} />);
    await userEvent.click(await screen.findByRole("button", { name: "Edit date of birth" }));
    expect(await screen.findByRole("dialog")).toHaveTextContent("Loading");
  });

  it("offers a separate time edit that submits no date or place fields", async () => {
    const calls: Record<string, unknown>[] = [];
    vi.stubGlobal("fetch", vi.fn(attested(async (url, init) => {
      if (init?.method === "PATCH") {
        calls.push(JSON.parse(String(init.body)));
        return jsonResponse(birthEvent);
      }
      if (String(url).endsWith("/people/p1/events")) return jsonResponse([{ ...birthEvent, revision: 4 }]);
      return jsonResponse([]);
    })));
    renderWithProviders(<OverviewTab person={withBirth} />);
    await userEvent.click(await screen.findByRole("button", { name: "Edit birth time" }));
    await screen.findByRole("button", { name: "Save" });
    const dialog = screen.getByRole("dialog");
    expect(within(dialog).queryByLabelText("Year")).not.toBeInTheDocument();
    expect(within(dialog).queryByDisplayValue("Kanpur")).not.toBeInTheDocument();
    await userEvent.click(within(dialog).getByRole("button", { name: "Save" }));
    await waitFor(() => expect(calls).toHaveLength(1));
    expect(calls[0]).toEqual({ time: null, timezone_id: null, utc_offset_minutes: null, expected_revision: 4 });
  });

  it("offers 'Edit birth' and opens the saved birth event; no events request before use", async () => {
    const fetchMock = mockFetch();
    renderWithProviders(<OverviewTab person={withBirth} />);
    const btn = await screen.findByRole("button", { name: "Edit date of birth" });
    expect(eventsCalls(fetchMock)).toHaveLength(0);
    await userEvent.click(btn);
    await screen.findByDisplayValue("1950");
    const dialog = await screen.findByRole("dialog");
    expect(eventsCalls(fetchMock).length).toBeGreaterThan(0);
    expect(within(dialog).queryByDisplayValue("Kanpur")).not.toBeInTheDocument();
    expect(within(dialog).getByDisplayValue("1950")).toBeInTheDocument();
  });

  it("Cancel closes the dialog without writing", async () => {
    const fetchMock = mockFetch();
    renderWithProviders(<OverviewTab person={withBirth} />);
    await userEvent.click(await screen.findByRole("button", { name: "Edit date of birth" }));
    const dialog = await screen.findByRole("dialog");
    await userEvent.click(within(dialog).getByRole("button", { name: "Cancel" }));
    await waitFor(() => expect(screen.queryByRole("dialog")).not.toBeInTheDocument());
    expect(fetchMock.mock.calls.some((c) => (c[1] as RequestInit | undefined)?.method === "POST" || (c[1] as RequestInit | undefined)?.method === "PATCH")).toBe(false);
  });

  it("offers 'Add birth' for a person without a birth event and opens a new birth event", async () => {
    mockFetch();
    renderWithProviders(<OverviewTab person={{ ...withBirth, birth: null }} />);
    expect(screen.queryByRole("button", { name: "Edit date of birth" })).not.toBeInTheDocument();
    await userEvent.click(await screen.findByRole("button", { name: "Add birth" }));
    const dialog = await screen.findByRole("dialog");
    expect(within(dialog).getByLabelText("Event type")).toHaveValue("birth");
    expect(within(dialog).queryByDisplayValue("Kanpur")).not.toBeInTheDocument();
  });

  it("offers 'Add death' for a deceased person with no death event", async () => {
    mockFetch();
    renderWithProviders(<OverviewTab person={{ ...withBirth, profile_status: "deceased", birth: null, death: null }} />);
    expect(await screen.findByRole("button", { name: "Add death" })).toBeInTheDocument();
  });

  it("shows neither action when the person cannot be edited", async () => {
    mockFetch();
    renderWithProviders(<OverviewTab person={{ ...withBirth, can_edit: false }} />);
    await screen.findByText("Kanpur");
    expect(screen.queryByRole("button", { name: /^(Edit|Add) (date of birth|birth.*|death)$/ })).not.toBeInTheDocument();
  });
});
