import { useState } from "react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import type { AncestryOut, EventOut, RenderJobOut, StoryOut } from "../../api/types";
import { jsonResponse, renderWithProviders } from "../../test/utils";
import { EventDialog } from "../../pages/tree/person/EventDialog";
import { ReminderDialog } from "../events/ReminderControl";
import { StoryTimeline } from "./StoryTimeline";
import { AncestryChart, DEFAULT_ANCESTRY } from "./AncestryChart";
import { AnimatedExport } from "./AnimatedExport";

type Handler = (url: string, init?: RequestInit) => unknown;

function mockFetch(handler: Handler) {
  const fn = vi.fn((url: RequestInfo | URL, init?: RequestInit) => {
    const out = handler(String(url), init);
    return Promise.resolve(out instanceof Response ? out : jsonResponse(out ?? {}));
  });
  vi.stubGlobal("fetch", fn);
  return fn;
}

function bodyOf(fn: ReturnType<typeof mockFetch>, match: (url: string, init?: RequestInit) => boolean) {
  const call = fn.mock.calls.find(([u, i]) => match(String(u), i as RequestInit | undefined));
  return call ? JSON.parse(String((call[1] as RequestInit).body)) : undefined;
}

afterEach(() => vi.unstubAllGlobals());

const event: EventOut = {
  id: "e1",
  type: "religious_ceremony",
  category: "mundan",
  title: "Raju's mundan",
  significance: "milestone",
  subtype: null,
  date: { precision: "exact", year: 1993, month: 3, day: 4 },
  time: null,
  timezone_id: null,
  utc_offset_minutes: null,
  place_id: null,
  place_as_recorded: "Vindhyachal",
  origin_place_id: null,
  origin_place_as_recorded: null,
  latitude: 25.17,
  longitude: 82.51,
  location_precision: "locality",
  reason: null,
  description: null,
  is_preferred: true,
  evidence_status: "USER_ASSERTION",
  confidence: "unknown",
  participants: [{ person_id: "p1", role: "principal", display_name: "Raju Iyer" }],
  media_count: 0,
};

describe("life event form", () => {
  it("creates a categorised, geotagged event with the derived type", async () => {
    const fetch = mockFetch((_url, init) => (init?.method === "POST" ? { ...event, id: "new" } : { items: [] }));
    const onClose = vi.fn();
    renderWithProviders(<EventDialog personId="p1" event={null} onClose={onClose} />);
    const user = userEvent.setup();
    await user.selectOptions(screen.getByLabelText("What happened?"), "upanayana");
    expect(screen.getByLabelText("Event type")).toHaveValue("religious_ceremony");
    expect(screen.getByLabelText("Event type")).toBeDisabled();
    await user.type(screen.getByLabelText("Title"), "Thread ceremony at Kashi");
    await user.click(screen.getByText("Exact location (optional)"));
    await user.type(screen.getByLabelText("Latitude"), "25.31");
    await user.click(screen.getByRole("button", { name: "Save" }));
    // a lone latitude is refused before anything is sent
    expect(await screen.findByText("Enter both latitude and longitude, or neither.")).toBeInTheDocument();
    await user.type(screen.getByLabelText("Longitude"), "83.01");
    await user.selectOptions(screen.getByLabelText("How significant?"), "milestone");
    await user.selectOptions(screen.getByLabelText("Who can see this event?"), "PRIVATE_TREE_ADMINS");
    await user.click(screen.getByRole("button", { name: "Save" }));
    await waitFor(() => expect(onClose).toHaveBeenCalled());
    const body = bodyOf(fetch, (u, i) => u.includes("/events") && i?.method === "POST");
    expect(body).toMatchObject({
      type: "religious_ceremony",
      category: "upanayana",
      title: "Thread ceremony at Kashi",
      significance: "milestone",
      privacy_level: "PRIVATE_TREE_ADMINS",
      latitude: 25.31,
      longitude: 83.01,
      location_precision: "approximate",
    });
  });
});

describe("reminder settings", () => {
  it("saves lead times, custom days, yearly repeat and only available channels", async () => {
    const fetch = mockFetch((url, init) => {
      if (url.includes("/notification-channels")) return { email: true, sms: false, whatsapp: true };
      if (init?.method === "POST") return { id: "r1" };
      return [];
    });
    const onClose = vi.fn();
    renderWithProviders(<ReminderDialog treeId="tree-1" event={{ ...event, type: "birth", category: "birth", title: null }} existing={null} onClose={onClose} />);
    const user = userEvent.setup();
    await waitFor(() => expect(screen.getByRole("checkbox", { name: /SMS/ })).toBeDisabled());
    expect(screen.getByRole("checkbox", { name: /Every year/ })).toBeChecked(); // birthdays repeat
    await user.click(screen.getByRole("checkbox", { name: "A week before" }));
    await user.type(screen.getByLabelText(/Other days before/), "30, 400");
    expect(screen.getByText(/whole days from 0 to 365/)).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Save" })).toBeDisabled();
    await user.clear(screen.getByLabelText(/Other days before/));
    await user.type(screen.getByLabelText(/Other days before/), "30");
    await user.click(screen.getByRole("checkbox", { name: "WhatsApp" }));
    await user.click(screen.getByRole("button", { name: "Save" }));
    await waitFor(() => expect(onClose).toHaveBeenCalled());
    expect(bodyOf(fetch, (u, i) => u.endsWith("/reminders") && i?.method === "POST")).toEqual({
      event_id: "e1",
      lead_days: [0, 7, 30],
      channels: ["email", "whatsapp"],
      note: null,
      recurrence: "annual",
    });
  });
});

const story: StoryOut = {
  person: { id: "p1", display_name: "Mohan Iyer", profile_status: "deceased", event_count: 3 },
  summary: "Mohan Iyer: 3 life events, from 1955 to 2015.",
  events: [
    { id: "a", type: "birth", label: "Birth", year: 1955, date_display: "2 Jan 1955", sort_key: "1955-01-02", significance: "standard", relatives: [], photos: [], place: { name: "Bhadohi", state: "Uttar Pradesh" } },
    { id: "b", type: "marriage", category: "marriage", label: "Wedding at Bhadohi", year: 1985, date_display: "10 Feb 1985", sort_key: "1985-02-10", significance: "milestone", description: "A three-day wedding.", relatives: [{ person_id: "p2", display_name: "Sita Iyer", role: "spouse" }], photos: [] },
    { id: "c", type: "death", label: "Death", year: 2015, date_display: "4 Mar 2015", sort_key: "2015-03-04", significance: "standard", relatives: [], photos: [] },
  ],
};

describe("lifetime event timeline", () => {
  it("groups by decade, shows details and steps through a slideshow", async () => {
    mockFetch((url) => (url.includes("/story") ? story : url.includes("render-jobs") ? [] : {}));
    renderWithProviders(<StoryTimeline personId="p1" showExport={false} />);
    const user = userEvent.setup();
    expect(await screen.findByText("The life of Mohan Iyer")).toBeInTheDocument();
    expect(screen.getByRole("region", { name: "1950s" })).toBeInTheDocument();
    expect(screen.getByRole("region", { name: "1980s" })).toHaveTextContent("Wedding at Bhadohi");
    expect(screen.queryByText("A three-day wedding.")).not.toBeInTheDocument();
    await user.click(screen.getByRole("radio", { name: "Detailed" }));
    expect(screen.getByText("A three-day wedding.")).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Sita Iyer" })).toHaveAttribute("href", "/t/tree-1/people/p2");
    await user.click(screen.getByRole("radio", { name: "Slideshow" }));
    expect(screen.getByText("1 of 3")).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "Next" }));
    expect(screen.getByRole("heading", { name: "Wedding at Bhadohi" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Previous" })).toBeEnabled();
  });
});

const ancestry: AncestryOut = {
  root_id: "p1",
  generations: 2,
  summary: "Ancestors of Raju Iyer over 2 generations: 2 known, 1 private, 2 not yet recorded.",
  missing_slots: [4, 5],
  nodes: [
    { slot: 1, generation: 0, side: "self", hidden: false, person: { id: "p1", display_name: "Raju Iyer", profile_status: "living", birth_display: "1990", birth_place: { name: "Varanasi" } } },
    { slot: 2, generation: 1, side: "paternal", hidden: false, person: { id: "p2", display_name: "Mohan Iyer", profile_status: "deceased", birth_display: "1955", death_display: "2015", birth_place: { name: "Bhadohi" }, village: "Bhadohi" } },
    { slot: 3, generation: 1, side: "maternal", hidden: true, person: null },
  ],
};

describe("fan and pedigree charts", () => {
  it("colours by the chosen attribute, lists gaps, and opens an accessible detail panel", async () => {
    mockFetch((url) => (url.includes("/viz/ancestry") ? ancestry : url.includes("/branches") ? [] : url.includes("render-jobs") ? [] : {}));
    function Harness() {
      const [settings, setSettings] = useState(DEFAULT_ANCESTRY);
      return <AncestryChart kind="fan" rootId="p1" settings={settings} onSettings={setSettings} />;
    }
    renderWithProviders(<Harness />);
    const user = userEvent.setup();
    expect((await screen.findAllByText(ancestry.summary!)).length).toBeGreaterThan(0);
    const legend = screen.getByRole("list", { name: "Legend" });
    expect(within(legend).getByText(/Paternal side/)).toBeInTheDocument();
    expect(within(legend).getByText("Private")).toBeInTheDocument();
    expect(within(legend).getByText("Not recorded")).toBeInTheDocument();
    await user.selectOptions(screen.getByLabelText("Colour by"), "birthplace");
    expect(within(screen.getByRole("list", { name: "Legend" })).getByText(/Bhadohi/)).toBeInTheDocument();
    // keyboard: focus a person and open the detail panel
    const mohan = screen.getByRole("button", { name: /Mohan Iyer, 1955–2015, Paternal side/ });
    mohan.focus();
    await user.keyboard("{Enter}");
    const panel = await screen.findByRole("complementary");
    expect(within(panel).getByRole("heading", { name: "Mohan Iyer" })).toHaveFocus();
    expect(within(panel).getAllByText("Bhadohi", { selector: "dd" })).toHaveLength(2); // birthplace and village
    // the private parent has no name anywhere and is not a button
    expect(screen.queryByRole("button", { name: /Private/ })).not.toBeInTheDocument();
    // text alternative
    await user.click(screen.getByText("Show as a table / list"));
    expect(screen.getAllByRole("row").length).toBeGreaterThanOrEqual(6);
  });
});

describe("animated export", () => {
  const job = (over: Partial<RenderJobOut>): RenderJobOut => ({
    id: "j1",
    chart_type: "fan",
    output: "poster",
    status: "running",
    progress: 40,
    settings: {},
    renderer: null,
    error_code: null,
    error_message: null,
    created_at: "2026-10-02T10:00:00Z",
    started_at: null,
    finished_at: null,
    artifacts: [],
    mine: true,
    ...over,
  });

  it("queues a render with the chosen output, shows progress and failures", async () => {
    const fetch = mockFetch((url, init) => {
      if (url.includes("/render-jobs") && init?.method === "POST") return job({ status: "queued", progress: 0 });
      if (url.includes("/render-jobs")) return [job({}), job({ id: "j2", status: "failed", error_code: "render_timeout" })];
      return {};
    });
    renderWithProviders(<AnimatedExport chartType="fan" settings={{ root_person_id: "p1", generations: 4 }} />);
    const user = userEvent.setup();
    expect(await screen.findByRole("progressbar", { name: "Rendering progress" })).toHaveAttribute("value", "40");
    expect(screen.getByText("Rendering failed (render_timeout).")).toBeInTheDocument();
    await user.selectOptions(screen.getByLabelText("Make"), "mp4");
    await user.selectOptions(screen.getByLabelText("Style"), "dusk");
    await user.click(screen.getByRole("button", { name: "Create video" }));
    await waitFor(() =>
      expect(bodyOf(fetch, (u, i) => u.endsWith("/render-jobs") && i?.method === "POST")).toEqual({
        chart_type: "fan",
        output: "mp4",
        settings: { root_person_id: "p1", generations: 4, theme: "dusk", title: null },
      }),
    );
  });

  it("explains when rendering is not enabled on the server", async () => {
    mockFetch((url, init) =>
      url.includes("/render-jobs") && init?.method === "POST"
        ? jsonResponse({ error: { code: "render_unavailable", message: "x" } }, 503)
        : [],
    );
    renderWithProviders(<AnimatedExport chartType="lifespan" settings={{}} />);
    await userEvent.setup().click(await screen.findByRole("button", { name: "Create preview" }));
    expect(await screen.findByText("Animated exports are not enabled on this server.")).toBeInTheDocument();
  });
});
