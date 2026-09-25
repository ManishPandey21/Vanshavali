import { useState } from "react";
import { describe, expect, it } from "vitest";
import { screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import type { GenealogicalDate, GenealogicalTime } from "../../api/types";
import { renderWithProviders } from "../../test/utils";
import { GenealogicalDateEditor } from "./GenealogicalDateEditor";
import { TimeEditor } from "./TimeEditor";

function DateHarness({ initial }: { initial: GenealogicalDate }) {
  const [v, setV] = useState(initial);
  return <GenealogicalDateEditor legend="Birth" value={v} onChange={setV} showErrors />;
}
function TimeHarness({ initial }: { initial: GenealogicalTime }) {
  const [v, setV] = useState(initial);
  return (
    <>
      <TimeEditor legend="Time" value={v} onChange={setV} showErrors />
      <output data-testid="state">{JSON.stringify(v)}</output>
    </>
  );
}

describe("GenealogicalDateEditor", () => {
  it("shows an error when an exact date has no day", async () => {
    renderWithProviders(<DateHarness initial={{ calendar: "gregorian", precision: "exact", year: 1970, month: 3 }} />, { tree: null });
    const group = screen.getByRole("group", { name: "Birth" });
    expect(within(group).getByLabelText(/^Day/)).toHaveAttribute("aria-invalid", "true");
    expect(within(group).getByText(/An exact date needs a day/)).toBeInTheDocument();
    await userEvent.type(within(group).getByLabelText(/^Day/), "12");
    expect(within(group).queryByText(/An exact date needs a day/)).not.toBeInTheDocument();
  });

  it("hides month and day inputs for year-only precision and clears them", async () => {
    renderWithProviders(<DateHarness initial={{ calendar: "gregorian", precision: "exact", year: 1970, month: 3, day: 2 }} />, { tree: null });
    await userEvent.selectOptions(screen.getByLabelText("How precise is this date?"), "year_only");
    expect(screen.queryByLabelText(/^Day/)).not.toBeInTheDocument();
    expect(screen.queryByLabelText(/^Month/)).not.toBeInTheDocument();
    expect(screen.getByLabelText(/^Year/)).toHaveValue(1970);
    expect(screen.getByText("1970", { selector: "span" })).toBeInTheDocument();
  });

  it("offers Hindu month names for Vikram Samvat", async () => {
    renderWithProviders(<DateHarness initial={{ calendar: "vikram_samvat", precision: "day_unknown", year: 2001 }} />, { tree: null });
    expect(within(screen.getByLabelText(/^Month/)).getByRole("option", { name: "Chaitra" })).toBeInTheDocument();
  });
});

describe("TimeEditor", () => {
  it("never lets a verbal time be exact and never previews it as exact", async () => {
    renderWithProviders(<TimeHarness initial={{ value: "06:30", precision: "exact", source: "birth_certificate" }} />, { tree: null });
    await userEvent.selectOptions(screen.getByLabelText("Where does this time come from?"), "verbal");
    const precision = screen.getByLabelText("Precision");
    expect(within(precision).getByRole("option", { name: "Exact" })).toBeDisabled();
    expect(precision).toHaveValue("approximate");
    expect(screen.getByText(/about 06:30/)).toBeInTheDocument();
    expect(JSON.parse(screen.getByTestId("state").textContent!)).toMatchObject({ precision: "approximate", source: "verbal" });
  });

  it("defaults a newly typed time to approximate, not exact", async () => {
    renderWithProviders(<TimeHarness initial={{ value: null, precision: "unknown", source: "unknown" }} />, { tree: null });
    await userEvent.type(screen.getByLabelText("Time (24-hour)"), "0545");
    expect(JSON.parse(screen.getByTestId("state").textContent!).precision).toBe("approximate");
  });
});
