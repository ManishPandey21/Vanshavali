import { useState } from "react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import i18n from "../../i18n";
import type { CalendarSettingsOut, GenealogicalDate } from "../../api/types";
import { jsonResponse, renderWithProviders } from "../../test/utils";
import { GenealogicalDateEditor } from "../../components/dates/GenealogicalDateEditor";
import { CalendarPage } from "./CalendarPage";

const body = (init?: RequestInit) => JSON.parse(String(init?.body ?? "{}"));

function settings(offered: boolean): CalendarSettingsOut {
  return {
    convention: "purnimanta",
    observance_city: "varanasi",
    conventions: [
      { key: "purnimanta", label: "Purnimanta", golden_verified: offered, offered },
      { key: "amanta", label: "Amanta", golden_verified: false, offered: false },
    ],
    cities: [{ key: "varanasi", label: "Varanasi", timezone: "Asia/Kolkata" }],
    lunar_enabled: offered,
  };
}

function DateHarness({ initial }: { initial: GenealogicalDate }) {
  const [v, setV] = useState(initial);
  return (
    <>
      <GenealogicalDateEditor legend="Death" value={v} onChange={setV} />
      <output data-testid="state">{JSON.stringify(v)}</output>
    </>
  );
}
const state = () => JSON.parse(screen.getByTestId("state").textContent ?? "{}") as GenealogicalDate;

afterEach(() => vi.unstubAllGlobals());

describe("tithi dates (ADR-0022 §2)", () => {
  it("keeps the tithi as written and never fills the Gregorian date on its own", async () => {
    await i18n.changeLanguage("en");
    vi.stubGlobal("fetch", vi.fn(() => Promise.resolve(jsonResponse(settings(false)))));
    renderWithProviders(<DateHarness initial={{ calendar: "gregorian", precision: "unknown" }} />);
    await userEvent.click(screen.getByRole("button", { name: /Add the tithi/ }));
    const group = screen.getByRole("group", { name: "Tithi date" });
    await userEvent.selectOptions(within(group).getByLabelText("Month (masa)"), "bhadrapada");
    await userEvent.selectOptions(within(group).getByLabelText("Fortnight (paksha)"), "krishna");
    await userEvent.selectOptions(within(group).getByLabelText("Tithi"), "8");
    const s = state();
    expect(s.lunar).toMatchObject({ masa: "bhadrapada", paksha: "krishna", tithi: 8, month_convention: "purnimanta" });
    expect(s.year ?? null).toBeNull();
    expect(s.day ?? null).toBeNull();
    // no convention has passed its checks: no conversion is offered
    expect(screen.queryByRole("button", { name: "Find the Gregorian date" })).not.toBeInTheDocument();
    await userEvent.click(within(group).getByRole("button", { name: "Remove the tithi" }));
    expect(state().lunar).toBeNull();
  });

  it("offers a conversion only as a suggestion, recorded as derived when accepted", async () => {
    await i18n.changeLanguage("en");
    document.cookie = "vsh_csrf=csrf-token";
    const fetchMock = vi.fn((url: RequestInfo | URL, _init?: RequestInit) => {
      const u = String(url);
      if (u.includes("/calendar/convert"))
        return Promise.resolve(jsonResponse({ suggestion: "1988-09-03", convention: "purnimanta", rule: "sunrise", city: "varanasi", engine_version: "test/1" }));
      return Promise.resolve(jsonResponse(settings(true)));
    });
    vi.stubGlobal("fetch", fetchMock);
    renderWithProviders(
      <DateHarness
        initial={{
          calendar: "gregorian",
          precision: "unknown",
          lunar: { masa: "bhadrapada", paksha: "krishna", tithi: 8, month_convention: "purnimanta", is_adhik: false, samvat: "vikram", year: 2045 },
        }}
      />,
    );
    await userEvent.click(await screen.findByRole("button", { name: "Find the Gregorian date" }));
    const convertCall = fetchMock.mock.calls.find(([u]) => String(u).includes("/calendar/convert"));
    expect(body(convertCall?.[1]).lunar).toMatchObject({ masa: "bhadrapada", samvat: "vikram", year: 2045 });
    expect(await screen.findByText(/Suggested: .*1988.*Check it/)).toBeInTheDocument();
    // nothing is stored until the user accepts it
    expect(state().year ?? null).toBeNull();
    await userEvent.click(screen.getByRole("button", { name: "Use this date" }));
    const s = state();
    expect(s).toMatchObject({ precision: "exact", year: 1988, month: 9, day: 3, derived: { source: "lunar", convention: "purnimanta", city: "varanasi" } });
    expect(s.lunar).toMatchObject({ masa: "bhadrapada", tithi: 8 });
  });
});

describe("family calendar page (ADR-0022 §5-§6)", () => {
  it("lists entries by month, says why tithi days are missing, and shows the feed link once", async () => {
    await i18n.changeLanguage("en");
    document.cookie = "vsh_csrf=csrf-token";
    const today = new Date();
    const day = `${today.getFullYear()}-${String(today.getMonth() + 1).padStart(2, "0")}-15`;
    const fetchMock = vi.fn((url: RequestInfo | URL, init?: RequestInit) => {
      const u = String(url);
      if (u.includes("/calendar-feed") && init?.method === "POST")
        return Promise.resolve(jsonResponse({ active: true, include_names: body(init).include_names, created_at: "2026-11-08T00:00:00Z", url: "https://example.test/api/v1/calendar-feeds/secret.ics" }, 201));
      if (u.includes("/calendar-feed")) return Promise.resolve(jsonResponse({ active: false, include_names: false }));
      if (u.includes("/calendar-settings")) return Promise.resolve(jsonResponse(settings(false)));
      if (u.includes("/calendar"))
        return Promise.resolve(
          jsonResponse({
            start: day,
            end: day,
            entries: [{ day, kind: "birthday", event_id: "e1", person_id: "p1", label: "Kamla Sharma", anniversary: 80, basis: "solar" }],
            lunar_unavailable: "convention_not_offered",
          }),
        );
      return Promise.resolve(jsonResponse({}));
    });
    vi.stubGlobal("fetch", fetchMock);
    renderWithProviders(<CalendarPage />, { route: "/t/tree-1/calendar" });
    expect(await screen.findByRole("link", { name: "Kamla Sharma" })).toHaveAttribute("href", "/t/tree-1/people/p1?tab=events");
    expect(screen.getByText(/not passed its accuracy checks/)).toBeInTheDocument();
    expect(screen.getByText("By date")).toBeInTheDocument();
    // names stay out of the feed unless chosen
    await userEvent.click(screen.getByRole("button", { name: "Make a calendar link" }));
    const post = fetchMock.mock.calls.find(([u, i]) => String(u).includes("/calendar-feed") && i?.method === "POST");
    expect(body(post?.[1])).toEqual({ include_names: false });
    expect(await screen.findByLabelText("Your calendar link")).toHaveValue("https://example.test/api/v1/calendar-feeds/secret.ics");
    expect(screen.getByText(/shown only once/)).toBeInTheDocument();
  });
});
