"""Role → permission matrix (ADR-0006). Deny by default: anything not listed is refused."""

from __future__ import annotations

from enum import StrEnum

from app.models.enums import Role


class Permission(StrEnum):
    TREE_READ = "tree.read"
    TREE_MANAGE = "tree.manage"
    MEMBERS_MANAGE = "members.manage"
    PERSON_WRITE = "person.write"
    RELATIONSHIP_WRITE = "relationship.write"
    ASSERTION_WRITE = "assertion.write"
    SOURCE_WRITE = "source.write"
    FAMILY_WRITE = "family.write"  # households, branches
    PRIVACY_MANAGE = "privacy.manage"  # per-person privacy/field overrides, consent, grants
    DOCUMENT_UPLOAD = "document.upload"
    DOCUMENT_MANAGE = "document.manage"
    DOCUMENT_VAULT = "document.vault"  # read/download VAULT class content
    EXTRACTION_REVIEW = "extraction.review"
    ASTROLOGY_WRITE = "astrology.write"
    PROPERTY_READ = "property.read"
    PROPERTY_WRITE = "property.write"
    PROPERTY_DOCUMENTS = "property.documents"  # vault access limited to property categories
    GEDCOM_IMPORT = "gedcom.import"
    GEDCOM_EXPORT = "gedcom.export"
    AUDIT_READ = "audit.read"


P = Permission
_ALL = frozenset(Permission)

ROLE_PERMISSIONS: dict[Role, frozenset[Permission]] = {
    Role.OWNER: _ALL,
    Role.FAMILY_ADMIN: _ALL,
    Role.BRANCH_ADMIN: frozenset(
        {
            P.TREE_READ,
            P.MEMBERS_MANAGE,
            P.PERSON_WRITE,
            P.RELATIONSHIP_WRITE,
            P.ASSERTION_WRITE,
            P.SOURCE_WRITE,
            P.FAMILY_WRITE,
            P.DOCUMENT_UPLOAD,
            P.EXTRACTION_REVIEW,
            P.ASTROLOGY_WRITE,
        }
    ),
    Role.CONTRIBUTOR: frozenset(
        {
            P.TREE_READ,
            P.PERSON_WRITE,
            P.RELATIONSHIP_WRITE,
            P.ASSERTION_WRITE,
            P.SOURCE_WRITE,
            P.FAMILY_WRITE,
            P.DOCUMENT_UPLOAD,
            P.EXTRACTION_REVIEW,
            P.ASTROLOGY_WRITE,
            P.PROPERTY_READ,
            P.GEDCOM_EXPORT,
        }
    ),
    Role.RESEARCHER: frozenset({P.TREE_READ, P.SOURCE_WRITE, P.ASSERTION_WRITE}),
    Role.VIEWER: frozenset({P.TREE_READ}),
    Role.DOCUMENT_CUSTODIAN: frozenset(
        {
            P.TREE_READ,
            P.DOCUMENT_UPLOAD,
            P.DOCUMENT_MANAGE,
            P.DOCUMENT_VAULT,
            P.EXTRACTION_REVIEW,
            P.SOURCE_WRITE,
        }
    ),
    Role.PROPERTY_CUSTODIAN: frozenset(
        {
            P.TREE_READ,
            P.PROPERTY_READ,
            P.PROPERTY_WRITE,
            P.PROPERTY_DOCUMENTS,
            P.DOCUMENT_UPLOAD,
            P.EXTRACTION_REVIEW,
            P.SOURCE_WRITE,
        }
    ),
}

# Permissions that, for branch-scoped memberships, only apply to people inside the branch.
BRANCH_SCOPED_WRITES = frozenset({P.PERSON_WRITE, P.RELATIONSHIP_WRITE, P.ASSERTION_WRITE, P.ASTROLOGY_WRITE})

ADMIN_ROLES = frozenset({Role.OWNER, Role.FAMILY_ADMIN})


def permissions_for(roles: frozenset[Role]) -> frozenset[Permission]:
    perms: set[Permission] = set()
    for r in roles:
        perms |= ROLE_PERMISSIONS.get(r, frozenset())
    return frozenset(perms)
