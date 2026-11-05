import { describe, expect, it } from "vitest";
import { screen } from "@testing-library/react";
import { renderWithProviders } from "../../test/utils";
import { PersonBadges } from "./badges";
import type { PersonSummary } from "../../api/types";

const base = { id: "p1", display_name: "Unnamed", profile_status: "unknown", is_minor: false, is_protected: true } as PersonSummary;

describe("PersonBadges for provisional people", () => {
  it("shows “To complete” while a provisional person has no name", () => {
    renderWithProviders(<PersonBadges person={{ ...base, is_provisional: true, provisional_state: "needs_details" }} />);
    expect(screen.getByText("To complete")).toBeInTheDocument();
    expect(screen.queryByText("Not yet verified")).not.toBeInTheDocument();
  });

  it("shows “Not yet verified” once named: a name is not verification", () => {
    renderWithProviders(<PersonBadges person={{ ...base, display_name: "Sunita", is_provisional: true, provisional_state: "unverified" }} />);
    expect(screen.getByText("Not yet verified")).toBeInTheDocument();
    expect(screen.queryByText("To complete")).not.toBeInTheDocument();
  });

  it("shows neither once the relationships are supported, nor for ordinary people", () => {
    renderWithProviders(<PersonBadges person={{ ...base, is_provisional: true, provisional_state: "verified" }} />);
    expect(screen.queryByText("To complete")).not.toBeInTheDocument();
    expect(screen.queryByText("Not yet verified")).not.toBeInTheDocument();
  });
});
