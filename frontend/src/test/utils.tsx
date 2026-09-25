import type { ReactElement, ReactNode } from "react";
import { render } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { MemoryRouter } from "react-router-dom";
import { I18nextProvider } from "react-i18next";
import i18n from "../i18n";
import type { TreeOut } from "../api/types";
import { TreeContext, makeTreeCtx } from "../lib/tree-context";

export const ALL_PERMS = [
  "tree.read",
  "tree.manage",
  "members.manage",
  "person.write",
  "relationship.write",
  "assertion.write",
  "source.write",
  "family.write",
  "privacy.manage",
  "audit.read",
];

export function makeTree(overrides: Partial<TreeOut> = {}): TreeOut {
  return {
    id: "tree-1",
    name: "Test tree",
    description: null,
    slug: "test-tree",
    public_mode: "OFF",
    default_person_privacy: "TREE_MEMBERS",
    created_at: "2026-01-01T00:00:00Z",
    my_roles: ["OWNER"],
    my_permissions: ALL_PERMS,
    ...overrides,
  };
}

export function renderWithProviders(ui: ReactElement, { tree = makeTree(), route = "/" }: { tree?: TreeOut | null; route?: string } = {}) {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false }, mutations: { retry: false } } });
  const wrap = (children: ReactNode) => (
    <I18nextProvider i18n={i18n}>
      <QueryClientProvider client={qc}>
        <MemoryRouter initialEntries={[route]}>{tree ? <TreeContext.Provider value={makeTreeCtx(tree)}>{children}</TreeContext.Provider> : children}</MemoryRouter>
      </QueryClientProvider>
    </I18nextProvider>
  );
  return { ...render(wrap(ui)), qc };
}

export function jsonResponse(body: unknown, status = 200): Response {
  return new Response(JSON.stringify(body), { status, headers: { "Content-Type": "application/json" } });
}
