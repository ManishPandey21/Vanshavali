import { describe, expect, it, vi } from "vitest";
import { screen } from "@testing-library/react";
import { Route, Routes } from "react-router-dom";
import { jsonResponse, makeTree, renderWithProviders } from "../../test/utils";
import { TreeLayout } from "./TreeLayout";

function renderAt(path: string) {
  vi.stubGlobal(
    "fetch",
    vi.fn(async (url: string) => (String(url).includes("/trees/tree-1") ? jsonResponse(makeTree()) : jsonResponse({}))),
  );
  renderWithProviders(
    <Routes>
      <Route path="/t/:treeId" element={<TreeLayout />}>
        <Route path="*" element={<p>page content</p>} />
        <Route index element={<p>page content</p>} />
      </Route>
    </Routes>,
    { tree: null, route: path },
  );
}

describe("mobile bottom navigation", () => {
  it("marks “More” as the current item when the page lives behind it (audit-2026-09: known issue)", async () => {
    renderAt("/t/tree-1/places");
    await screen.findByText("page content");
    const bar = screen.getByRole("navigation", { name: "Main sections" });
    const more = bar.querySelector("button[aria-haspopup='dialog']");
    expect(more).toHaveAttribute("aria-current", "true");
    expect(bar.querySelector("a[aria-current='page']")).toBeNull();
  });

  it("leaves “More” alone when a main tab is current", async () => {
    renderAt("/t/tree-1/people/p-1");
    await screen.findByText("page content");
    const bar = screen.getByRole("navigation", { name: "Main sections" });
    expect(bar.querySelector("button[aria-haspopup='dialog']")).not.toHaveAttribute("aria-current");
    expect(bar.querySelector("a[aria-current='page']")).toHaveTextContent("People");
  });
});
