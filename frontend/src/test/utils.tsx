import type { ReactElement, ReactNode } from "react";
import { render } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { MemoryRouter } from "react-router-dom";
import { I18nextProvider } from "react-i18next";
import i18n from "../i18n";
import type { TreeOut } from "../api/types";
import { TreeContext, makeTreeCtx } from "../lib/tree-context";

export const ALL_PERMS = [
  "document.upload",
  "document.manage",
  "extraction.review",
  "astrology.write",
  "property.read",
  "property.write",
  "gedcom.import",
  "gedcom.export",
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

/** An empty master-data vocabulary answer (ADR-0018), for forms whose fields fetch suggestions. */
export function emptyVocabulary(key: string) {
  return { vocabulary: { key, description: "", version: 1, allows_custom: true, term_count: 0 }, items: [] };
}

/**
 * Wraps a fetch mock so the family-data attestation check (ADR-0011) answers "already confirmed",
 * vocabulary suggestion lookups (ADR-0018) answer with an empty list and transliteration
 * suggestions (ADR-0025) offer nothing; every other request goes to `inner`.
 */
/** A transliteration answer with no suggestion (ADR-0025). */
export const noTransliteration = { candidates: [], engine: "vanshavali-translit", version: "hi-Latn/1", lexicon_version: "1" };

export function attested(inner: (...args: [RequestInfo | URL, RequestInit?]) => unknown) {
  return (url: RequestInfo | URL, init?: RequestInit) => {
    const u = String(url);
    if (u.includes("/attestation")) return Promise.resolve(jsonResponse({ attested: true, current_version: "v1", attestation: null }));
    const vocab = u.match(/\/vocabularies\/([a-z_]+)(?:\?|$)/);
    if (vocab && (!init?.method || init.method === "GET")) return Promise.resolve(jsonResponse(emptyVocabulary(vocab[1])));
    if (u.endsWith("/transliterate")) return Promise.resolve(jsonResponse(noTransliteration));
    return inner(url, init);
  };
}
