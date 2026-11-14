# ADR-0034 evidence: before and after

Captured with Playwright against the real stack (local PostgreSQL, API and SPA) on 14 Nov 2026,
using the same fictional ten-person family each time. "Before" is `main` at `666d6e5`; "after" is
the ADR-0034 branch (`e2e/tests/full-tree-and-removal.spec.ts` with `VSH_E2E_SHOTS` set).

| Report | Before | After |
|---|---|---|
| A removed person comes back as "Private person" | [before](before-removed-person-shown-as-private-person.png) | [after](after-removed-person-leaves-no-placeholder.png) |
| "Open full tree" shows a descendant slice | [before: 5 of 10 relatives](before-open-full-tree-shows-5-of-10.png) | [after: the whole connected family](after-open-full-tree-whole-connected-family.png) |

Also after:

- [Removing the person who links two sides leaves separate groups, with no line between them](after-removed-linking-person-separate-groups.png)
- [A relative hidden by privacy still has a placeholder (viewer's view)](after-privacy-hidden-relative-keeps-placeholder.png)
- [A family that stopped loading is labelled incomplete](after-incomplete-state-is-labelled.png)
