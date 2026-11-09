import { afterEach, describe, expect, it, vi } from "vitest";
import { screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { Route, Routes } from "react-router-dom";
import i18n from "../../../i18n";
import { jsonResponse, makeTree, renderWithProviders } from "../../../test/utils";
import { DocumentDetailPage } from "./DocumentDetailPage";

const doc = (over: Record<string, unknown>) => ({
  id: "doc-1",
  category: "photo",
  storage_class: "standard",
  title: "Nani's wedding",
  description: null,
  original_filename: "nani.png",
  mime_type: "image/png",
  size_bytes: 2048,
  checksum_sha256: "x",
  document_date: null,
  language: null,
  script: null,
  issuing_authority: null,
  privacy_level: "SELECTED_MEMBERS",
  scan_status: "clean",
  page_count: null,
  ocr_status: "skipped",
  extraction_status: "skipped",
  preview_status: "completed",
  metadata_version: 1,
  created_by: "u-owner",
  created_at: "2026-11-09T00:00:00Z",
  updated_at: "2026-11-09T00:00:00Z",
  deleted_at: null,
  links: [],
  can_access_content: true,
  can_download: false,
  variants: [],
  pending_proposals: 0,
  ...over,
});

function serve(d: ReturnType<typeof doc>) {
  return vi.fn((url: RequestInfo | URL) => {
    const u = String(url);
    if (u.endsWith("/documents/doc-1")) return Promise.resolve(jsonResponse(d));
    if (u.includes("/people")) return Promise.resolve(jsonResponse({ items: [], next_cursor: null }));
    if (u.includes("/sharing")) return Promise.resolve(jsonResponse({ privacy_level: d.privacy_level, audience: [], editable: false, members: [] }));
    return Promise.resolve(jsonResponse([]));
  });
}

function renderPage() {
  return renderWithProviders(
    <Routes>
      <Route path="/t/:treeId/documents/:documentId" element={<DocumentDetailPage />} />
    </Routes>,
    // a family admin: by role they could manage every document
    { tree: makeTree({ my_roles: ["FAMILY_ADMIN"] }), route: "/t/tree-1/documents/doc-1" },
  );
}

afterEach(() => vi.unstubAllGlobals());

describe("a private document shared with a member (ADR-0027 §10)", () => {
  it("is read-only to a grantee, whatever their role", async () => {
    await i18n.changeLanguage("en");
    vi.stubGlobal("fetch", serve(doc({ is_owner: false, can_change: false })));
    renderPage();
    expect(await screen.findByRole("heading", { name: "Nani's wedding" })).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Delete" })).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /Re-run OCR/ })).not.toBeInTheDocument();
    await userEvent.click(screen.getByRole("tab", { name: /Details/ }));
    expect(screen.queryByRole("button", { name: "Save" })).not.toBeInTheDocument();
    await userEvent.click(screen.getByRole("tab", { name: /Linked to/ }));
    expect(screen.queryByRole("button", { name: /Add link/ })).not.toBeInTheDocument();
  });

  it("keeps the controls for the owner", async () => {
    await i18n.changeLanguage("en");
    vi.stubGlobal("fetch", serve(doc({ is_owner: true, can_change: true })));
    renderPage();
    expect(await screen.findByRole("button", { name: "Delete" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /Re-run OCR/ })).toBeInTheDocument();
    await userEvent.click(screen.getByRole("tab", { name: /Details/ }));
    expect(screen.getByRole("button", { name: "Save" })).toBeInTheDocument();
    await userEvent.click(screen.getByRole("tab", { name: /Linked to/ }));
    expect(screen.getByRole("button", { name: /Add link/ })).toBeInTheDocument();
  });
});
