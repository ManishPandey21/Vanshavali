import { describe, expect, it, vi } from "vitest";
import { screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import type { ProposalOut } from "../../api/types";
import { jsonResponse, makeTree, renderWithProviders } from "../../test/utils";
import { ExtractionReview, buildReviewBody, draftFromProposal, validateDraft } from "./ExtractionReview";

function proposal(over: Partial<ProposalOut>): ProposalOut {
  return {
    id: "p1",
    document_id: "d1",
    subject_person_id: "person-1",
    subject_property_id: null,
    extractor: "birth_certificate_rules",
    extractor_version: "1.0.0",
    engine: "tesseract",
    field: "date_of_birth",
    label: "Date of birth",
    proposed_value: { calendar: "gregorian", precision: "exact", year: 1985, month: 3, day: 12, original_text: "12/03/1985" },
    display_value: "1985-03-12",
    confidence: 0.91,
    source_location: { page: 1, line: 3 },
    status: "pending",
    final_value: null,
    reviewed_by: null,
    reviewed_at: null,
    review_note: null,
    applied_target_type: null,
    applied_target_id: null,
    created_at: "2026-09-25T00:00:00Z",
    ...over,
  };
}

describe("review payloads", () => {
  it("accept and reject send no value", () => {
    expect(buildReviewBody("accept", "date", null, "")).toEqual({ action: "accept" });
    expect(buildReviewBody("reject", "text", null, "  wrong line ")).toEqual({ action: "reject", note: "wrong line" });
  });

  it("edit sends the corrected value in the field's shape", () => {
    const d = draftFromProposal(proposal({}));
    d.date = { ...d.date, day: 13 };
    expect(buildReviewBody("edit", "date", d, "", "person-9")).toEqual({
      action: "edit",
      target_person_id: "person-9",
      value: { calendar: "gregorian", precision: "exact", year: 1985, month: 3, day: 13, original_text: "12/03/1985" },
    });
    const tDraft = draftFromProposal(proposal({ field: "time_of_birth", proposed_value: { value: "05:45", precision: "document_recorded", source: "birth_certificate" } }));
    expect(buildReviewBody("edit", "time", tDraft, "").value).toEqual({ value: "05:45", precision: "document_recorded", source: "birth_certificate" });
    const pada = draftFromProposal(proposal({ field: "nakshatra_pada", proposed_value: 2, display_value: "2" }));
    pada.number = "3";
    expect(buildReviewBody("edit", "pada", pada, "").value).toBe(3);
    const name = draftFromProposal(proposal({ field: "father_name", proposed_value: "Suresh  Kumar", display_value: "Suresh Kumar" }));
    name.text = " Suresh Kumar Sharma ";
    expect(buildReviewBody("edit", "name", name, "").value).toBe("Suresh Kumar Sharma");
  });

  it("validates edited values before sending", () => {
    const d = draftFromProposal(proposal({}));
    expect(validateDraft("date", { ...d, date: { calendar: "gregorian", precision: "exact", year: 1985, month: 3 } })).toBe("extraction.err.date");
    expect(validateDraft("pada", { ...d, number: "5" })).toBe("extraction.err.pada");
    expect(validateDraft("time", { ...d, time: { value: "06:00", precision: "exact", source: "verbal" } })).toBe("extraction.err.time");
    expect(validateDraft("text", { ...d, text: "  " })).toBe("extraction.err.empty");
  });
});

describe("ExtractionReview", () => {
  const setup = (proposals: ProposalOut[], reviewResponse?: Response) => {
    const calls: { url: string; init?: RequestInit }[] = [];
    vi.stubGlobal(
      "fetch",
      vi.fn(async (url: string, init?: RequestInit) => {
        calls.push({ url, init });
        if (url.includes("/review")) return reviewResponse ?? jsonResponse({ ...proposals[0], status: "accepted" });
        return jsonResponse(proposals);
      }),
    );
    renderWithProviders(<ExtractionReview documentId="d1" canReview needsTarget={false} />);
    return calls;
  };

  it("posts accept for a pending value and labels values honestly", async () => {
    const calls = setup([proposal({})]);
    const row = await screen.findByRole("listitem", { name: "Date of birth" });
    expect(within(row).getByText("Extracted")).toBeInTheDocument();
    expect(within(row).getByText(/91% confidence/)).toBeInTheDocument();
    expect(within(row).getByText(/page 1, line 3/)).toBeInTheDocument();
    await userEvent.click(within(row).getByRole("button", { name: "Accept Date of birth" }));
    await waitFor(() => expect(calls.some((c) => c.url.endsWith("/extraction-proposals/p1/review"))).toBe(true));
    const review = calls.find((c) => c.url.endsWith("/review"))!;
    expect(review.init?.method).toBe("POST");
    expect(JSON.parse(String(review.init?.body))).toEqual({ action: "accept" });
  });

  it("edit-then-accept sends action edit with the corrected value", async () => {
    const calls = setup([proposal({ field: "place_of_birth", label: "Place of birth", proposed_value: "Kanpr", display_value: "Kanpr" })]);
    const row = await screen.findByRole("listitem", { name: "Place of birth" });
    await userEvent.click(within(row).getByRole("button", { name: "Edit Place of birth before accepting" }));
    const input = within(row).getByLabelText("Place of birth");
    await userEvent.clear(input);
    await userEvent.type(input, "Kanpur");
    await userEvent.click(within(row).getByRole("button", { name: "Save & accept" }));
    await waitFor(() => expect(calls.some((c) => c.url.endsWith("/review"))).toBe(true));
    expect(JSON.parse(String(calls.find((c) => c.url.endsWith("/review"))!.init?.body))).toEqual({ action: "edit", value: "Kanpur" });
  });

  it("explains a 409 conflicting_value without claiming anything was changed", async () => {
    setup(
      [proposal({})],
      jsonResponse({ error: { code: "conflicting_value", message: "The record already holds a different Date of birth; it was not overwritten." } }, 409),
    );
    const row = await screen.findByRole("listitem", { name: "Date of birth" });
    await userEvent.click(within(row).getByRole("button", { name: "Accept Date of birth" }));
    expect(await within(row).findByText(/Not applied: the record already holds a different value/)).toBeInTheDocument();
    expect(within(row).getByText(/Nothing was overwritten/)).toBeInTheDocument();
  });

  it("hides review actions for members without extraction.review", async () => {
    vi.stubGlobal("fetch", vi.fn(async () => jsonResponse([proposal({})])));
    renderWithProviders(<ExtractionReview documentId="d1" canReview={false} needsTarget={false} />, { tree: makeTree({ my_permissions: ["tree.read"] }) });
    const row = await screen.findByRole("listitem", { name: "Date of birth" });
    expect(within(row).queryByRole("button")).not.toBeInTheDocument();
  });

  it("shows reviewed values as source-verified / user-confirmed / rejected", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn(async () =>
        jsonResponse([
          proposal({ id: "a", status: "accepted", label: "Name", field: "name" }),
          proposal({ id: "b", status: "edited", label: "Sex", field: "sex", final_value: "male" }),
          proposal({ id: "c", status: "rejected", label: "Place of birth", field: "place_of_birth" }),
        ]),
      ),
    );
    renderWithProviders(<ExtractionReview documentId="d1" canReview needsTarget={false} />);
    expect(await within(await screen.findByRole("listitem", { name: "Name" })).findByText("Source-verified")).toBeInTheDocument();
    expect(within(screen.getByRole("listitem", { name: "Sex" })).getByText("User-confirmed")).toBeInTheDocument();
    expect(within(screen.getByRole("listitem", { name: "Place of birth" })).getByText("Rejected")).toBeInTheDocument();
  });
});
