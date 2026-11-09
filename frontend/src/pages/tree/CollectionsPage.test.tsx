import { describe, expect, it, vi } from "vitest";
import { screen } from "@testing-library/react";
import { Route, Routes } from "react-router-dom";
import type { CollectionOut } from "../../api/types";
import { jsonResponse, makeTree, renderWithProviders } from "../../test/utils";
import { CollectionDetailPage } from "./CollectionsPage";

function collection(over: Partial<CollectionOut>): CollectionOut {
  return {
    id: "c1",
    title: "Nani's village",
    description: null,
    privacy_level: "TREE_MEMBERS",
    item_count: 2,
    cover_document_id: "d1",
    is_owner: true,
    can_edit_sharing: false,
    updated_at: "2026-11-09T00:00:00Z",
    items: [
      { id: "i1", document_id: "d1", caption: "Well", is_cover: true, sort_order: 0, shared_with_collection_audience: true, document: { title: "Well", privacy_level: "TREE_MEMBERS" } as never },
      { id: "i2", document_id: "d2", caption: "Nani", is_cover: false, sort_order: 1, shared_with_collection_audience: false, document: { title: "Nani", privacy_level: "ONLY_ME" } as never },
    ],
    items_not_shared: 1,
    ...over,
  };
}

function render(c: CollectionOut) {
  vi.stubGlobal(
    "fetch",
    vi.fn(async (input: RequestInfo | URL) => (String(input).includes("/collections/c1") ? jsonResponse(c) : jsonResponse({}, 404))),
  );
  const tree = makeTree();
  return renderWithProviders(
    <Routes>
      <Route path="/t/:treeId/collections/:collectionId" element={<CollectionDetailPage />} />
    </Routes>,
    { tree, route: `/t/${tree.id}/collections/c1` },
  );
}

describe("CollectionDetailPage", () => {
  it("warns the owner which photos part of the collection's audience cannot see", async () => {
    render(collection({}));
    expect(await screen.findByRole("heading", { name: "Nani's village" })).toBeInTheDocument();
    expect(screen.getByRole("note")).toHaveTextContent("1 photo is kept more private than this collection");
    expect(screen.getByText("Not everyone who sees the collection can see this photo")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Add photos" })).toBeInTheDocument();
    vi.unstubAllGlobals();
  });

  it("gives a viewer no editing controls and no warning", async () => {
    render(collection({ is_owner: false, items_not_shared: null, items: [collection({}).items![0]], item_count: 1 }));
    expect(await screen.findByRole("heading", { name: "Nani's village" })).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Add photos" })).not.toBeInTheDocument();
    expect(screen.queryByRole("note")).not.toBeInTheDocument();
    expect(screen.getByText("1 photo")).toBeInTheDocument();
    vi.unstubAllGlobals();
  });
});
