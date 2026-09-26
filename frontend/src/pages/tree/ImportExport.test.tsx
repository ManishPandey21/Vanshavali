import { describe, expect, it, vi } from "vitest";
import { screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import type { ImportJobOut } from "../../api/types";
import { jsonResponse, renderWithProviders } from "../../test/utils";
import i18n from "../../i18n";
import { ImportExportPage, PhotosSummary, buildCommitBody, defaultDecisions, photosImportedText, vitalText } from "./ImportExportPage";

describe("GEDCOM preview dates", () => {
  const t = i18n.t.bind(i18n);
  it("says 'date unknown' for an event recorded without a date, and invents nothing", () => {
    expect(vitalText(t, "3 Mar 1980", true, "Lucknow")).toBe("3 Mar 1980");
    expect(vitalText(t, null, true, "India")).toBe("India, date unknown");
    expect(vitalText(t, null, true, null)).toBe("date unknown");
    expect(vitalText(t, null, false, null)).toBeNull();
    expect(vitalText(t, undefined, undefined, undefined)).toBeNull();
  });
});

describe("GEDCOM photos (ADR-0013)", () => {
  const t = i18n.t.bind(i18n);
  it("explains how to include photos when only a .ged was uploaded", () => {
    renderWithProviders(<PhotosSummary t={t} photos={{ package: false, referenced: 24, matched: 0, missing: 0, ambiguous: 0 }} />);
    expect(screen.getByText(/refers to 24 photos, but they weren't uploaded/)).toBeInTheDocument();
  });

  it("reports what the zip matched and lists the photos it will skip", async () => {
    renderWithProviders(
      <PhotosSummary t={t} photos={{ package: true, referenced: 5, matched: 4, missing: 1, ambiguous: 0, people_with_photos: 3, missing_files: ["P404_missing.jpg"] }} />,
    );
    expect(screen.getByText(/Photos: 4 of 5 found in the zip, for 3 people/)).toBeInTheDocument();
    await userEvent.click(screen.getByText(/1 photo will be skipped/));
    expect(screen.getByText("P404_missing.jpg")).toBeInTheDocument();
  });

  it("summarises imported and rejected photos after the import", () => {
    renderWithProviders(<>{photosImportedText(t, { counts: { photos_imported: 3, photos_rejected: 1 } })}</>);
    expect(screen.getByText(/3 photos imported and linked to people\. 1 file was rejected by the safety checks\./)).toBeInTheDocument();
    expect(photosImportedText(t, { counts: { people_created: 2 } })).toBeNull();
  });
});

describe("GEDCOM decisions", () => {
  it("builds create / skip / attach payloads", () => {
    expect(
      buildCommitBody({
        "@I1@": { kind: "create" },
        "@I2@": { kind: "skip" },
        "@I3@": { kind: "attach", personId: "person-7" },
      }),
    ).toEqual({ decisions: { "@I1@": "create", "@I2@": "skip", "@I3@": { attach: "person-7" } } });
  });

  it("never auto-attaches, even to a probable duplicate", () => {
    const d = defaultDecisions([
      { xref: "@I1@", display_name: "A", profile_status: "deceased", duplicates: [{ person: { id: "x", display_name: "A", profile_status: "deceased", sex_at_birth: null }, score: 0.97, outcome: "probable", reasons: [] }] },
    ]);
    expect(d["@I1@"]).toEqual({ kind: "create" });
  });

  it("commits the chosen decision per person", async () => {
    const job: ImportJobOut = {
      id: "job-1",
      status: "ready",
      original_filename: "family.ged",
      detected_version: "7.0",
      detected_encoding: "UTF-8",
      counts: { people: 2 },
      created_at: "2026-09-25T00:00:00Z",
      report: { counts: { people: 2, families: 1 }, warnings: [{ line: 12, code: "x", message: "Unknown date format" }], unsupported_tags: { _FOO: 2 } },
      preview: [
        { xref: "@I1@", display_name: "Ram Lal", profile_status: "deceased", duplicates: [] },
        {
          xref: "@I2@",
          display_name: "Sita Devi",
          profile_status: "deceased",
          duplicates: [{ person: { id: "p-sita", display_name: "Sita Devi", profile_status: "deceased", sex_at_birth: "female" }, score: 0.9, outcome: "probable", reasons: ["same name"] }],
        },
      ],
      preview_total: 2,
    };
    const calls: { url: string; init?: RequestInit }[] = [];
    vi.stubGlobal(
      "fetch",
      vi.fn(async (url: string, init?: RequestInit) => {
        calls.push({ url, init });
        if (url.includes("/imports/job-1/commit")) return jsonResponse({ ...job, status: "committed", commit_result: { created: 1, attached: 1 } });
        if (url.includes("/imports/job-1")) return jsonResponse(job);
        if (url.endsWith("/imports")) return jsonResponse([{ id: "job-1", status: "ready", original_filename: "family.ged", created_at: job.created_at }]);
        return jsonResponse([]);
      }),
    );
    renderWithProviders(<ImportExportPage />);
    await userEvent.click(await screen.findByRole("button", { name: "Open" }));
    expect(await screen.findByText(/Unknown date format/)).toBeInTheDocument();
    expect(screen.getByText(/_FOO ×2/)).toBeInTheDocument();
    await userEvent.selectOptions(screen.getByLabelText("Decision for Sita Devi"), "attach:p-sita");
    await userEvent.selectOptions(screen.getByLabelText("Decision for Ram Lal"), "skip");
    await userEvent.click(screen.getByRole("button", { name: /Import: 0 new, 1 matched, 1 skipped/ }));
    await waitFor(() => expect(calls.some((c) => c.url.includes("/commit"))).toBe(true));
    const body = JSON.parse(String(calls.find((c) => c.url.includes("/commit"))!.init?.body));
    expect(body).toEqual({ decisions: { "@I1@": "skip", "@I2@": { attach: "p-sita" } } });
  });

  it("shows sensitive export options only to admins", async () => {
    vi.stubGlobal("fetch", vi.fn(async () => jsonResponse([])));
    const { unmount } = renderWithProviders(<ImportExportPage />);
    expect(screen.getAllByLabelText(/Include sensitive details/).length).toBe(2);
    expect(screen.getByLabelText(/Include vault documents/)).toBeInTheDocument();
    unmount();
    renderWithProviders(<ImportExportPage />, {
      tree: { id: "tree-1", name: "T", description: null, slug: "t", public_mode: "OFF", default_person_privacy: "TREE_MEMBERS", created_at: "", my_roles: ["CONTRIBUTOR"], my_permissions: ["tree.read", "gedcom.export"] },
    });
    expect(screen.queryByLabelText(/Include sensitive details/)).not.toBeInTheDocument();
    expect(screen.queryByLabelText(/Include vault documents/)).not.toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Download archive" })).toBeInTheDocument();
  });
});
