# ADR-0006: Authorisation and privacy evaluation

- Status: Accepted · Date: 2026-09-25

## Decision
**Deny by default**, centralised in `app/authz`:

1. **Resolve the context**: `AuthzContext(user, tree, membership?, is_public)`. A tree the caller
   is not a member of (and that is not public) → **404**.
2. **Action check**: `require(ctx, Permission.X, resource?)`, driven by the role matrix (below).
   Branch-scoped roles (`BRANCH_ADMIN`, or any membership with `branch_id`) only get write access to
   people in that branch's membership.
3. **Visibility check** (read): `can_view(ctx, obj)`, driven by the object's `privacy_level`:
   - `PRIVATE_SELF`: the claimed profile owner, plus the tree OWNER (who is responsible for the archive).
   - `PRIVATE_TREE_ADMINS`: OWNER and FAMILY_ADMIN (and the claimant).
   - `FAMILY_BRANCH`: admins, plus members whose branch scope or linked person belongs to one of
     the subject's branches.
   - `TREE_MEMBERS`: any member except RESEARCHER.
   - `INVITED_RESEARCHER`: any member, including RESEARCHER.
   - `PUBLIC_DECEASED_ONLY`: like TREE_MEMBERS, and also public if the tree has public mode on
     **and** the subject is deceased (never living, unknown or a minor).
   - `CUSTOM`: admins plus explicit `access_grant` rows.
4. **Field redaction** (`redact_person`): sensitive field groups (`birth_date_full`, `birth_time`,
   `birth_place_detail`, `contact`, `address`, `gender_identity`, `community`, `jati`, `astrology`,
   `notes`) are evaluated against a per-person override, else a default that depends on
   living/minor status. Living and unknown people, and minors, default `birth_date_full`,
   `birth_time`, `contact` and `address` to `PRIVATE_TREE_ADMINS`. Redacted date values are cut
   down to the year and flagged `redacted: true`. Public contexts always get the minimum.
5. **Documents**: `can_view` on the document, plus `DOCUMENT_DOWNLOAD` for bytes. VAULT documents
   also require OWNER, FAMILY_ADMIN or DOCUMENT_CUSTODIAN, or an explicit grant. Property documents
   also allow PROPERTY_CUSTODIAN.
6. **SYSTEM_ADMIN** has platform endpoints only (health, metrics) and **no implicit tree access**.

### Role → permission matrix (summary)
| Permission | Owner | FamAdmin | BranchAdmin | Contributor | Researcher | Viewer | DocCustodian | PropCustodian |
|---|---|---|---|---|---|---|---|---|
| tree.read | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ |
| tree.manage (settings, public mode) | ✓ | ✓ | | | | | | |
| members.manage / invite | ✓ | ✓ | branch | | | | | |
| person.write / relationship.write | ✓ | ✓ | branch | ✓ | | | | |
| assertion.propose | ✓ | ✓ | ✓ | ✓ | ✓ | | | |
| source.write | ✓ | ✓ | ✓ | ✓ | ✓ | | | |
| document.upload | ✓ | ✓ | ✓ | ✓ | | | ✓ | ✓ |
| document.manage (vault, delete) | ✓ | ✓ | | | | | ✓ | |
| extraction.review | ✓ | ✓ | ✓ | ✓ | | | ✓ | ✓ |
| property.read / write | ✓ | ✓ | | read | | | | ✓ |
| gedcom.import | ✓ | ✓ | | | | | | |
| gedcom.export | ✓ | ✓ | | ✓ | | | | |
| audit.read | ✓ | ✓ | | | | | | |

Researchers' writes go in as `USER_ASSERTION` proposals that need admin acceptance. The full
proposal workflow is **DEFERRED** to post-MVP collaboration, so for now researchers can add sources
and assertions but can't edit people.

## Consequences
Every router uses a `tree_ctx` dependency and a `require()` call. A parametrised test checks that
every route under `/trees/{tree_id}` rejects non-members and returns 404 across trees.
