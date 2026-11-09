import { describe, expect, it } from "vitest";
import { screen } from "@testing-library/react";
import { renderWithProviders } from "../../test/utils";
import { PersonBadges, PrivacyBadge } from "./badges";
import { PRIVACY_LEVELS, RECORD_PRIVACY_LEVELS } from "./PersonForm";
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

describe("record-only audiences (ADR-0027 §1)", () => {
  it("labels “Only me” and “Selected members”", () => {
    renderWithProviders(<PrivacyBadge level="ONLY_ME" />);
    expect(screen.getByText("Only me")).toBeInTheDocument();
    renderWithProviders(<PrivacyBadge level="SELECTED_MEMBERS" />);
    expect(screen.getByText("Selected members")).toBeInTheDocument();
  });

  it("offers them for documents, never for people or field groups", () => {
    expect(RECORD_PRIVACY_LEVELS).toEqual(expect.arrayContaining(["ONLY_ME", "SELECTED_MEMBERS"]));
    expect(PRIVACY_LEVELS).not.toContain("ONLY_ME");
    expect(PRIVACY_LEVELS).not.toContain("SELECTED_MEMBERS");
  });
});
