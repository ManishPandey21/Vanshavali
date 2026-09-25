/**
 * Client-side permission hints. The server is the authority (every write is re-checked there);
 * these only hide controls the user can't use. Values match `app/authz/permissions.py`.
 */
import type { TreeOut } from "../api/types";

export const Perm = {
  TREE_READ: "tree.read",
  TREE_MANAGE: "tree.manage",
  MEMBERS_MANAGE: "members.manage",
  PERSON_WRITE: "person.write",
  RELATIONSHIP_WRITE: "relationship.write",
  ASSERTION_WRITE: "assertion.write",
  SOURCE_WRITE: "source.write",
  FAMILY_WRITE: "family.write",
  PRIVACY_MANAGE: "privacy.manage",
  AUDIT_READ: "audit.read",
} as const;

export type PermValue = (typeof Perm)[keyof typeof Perm];

export function hasPerm(tree: Pick<TreeOut, "my_permissions"> | null | undefined, perm: PermValue): boolean {
  return !!tree?.my_permissions?.includes(perm);
}

export function isTreeAdmin(tree: Pick<TreeOut, "my_roles"> | null | undefined): boolean {
  return !!tree?.my_roles?.some((r) => r === "OWNER" || r === "FAMILY_ADMIN");
}

export function isOwner(tree: Pick<TreeOut, "my_roles"> | null | undefined): boolean {
  return !!tree?.my_roles?.includes("OWNER");
}
