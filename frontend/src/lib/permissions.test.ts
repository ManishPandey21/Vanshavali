import { describe, expect, it } from "vitest";
import { hasPerm, isTreeAdmin, Perm } from "./permissions";

describe("permission hints", () => {
  it("reads my_permissions from the tree", () => {
    expect(hasPerm({ my_permissions: ["tree.read"] }, Perm.PERSON_WRITE)).toBe(false);
    expect(hasPerm({ my_permissions: ["person.write"] }, Perm.PERSON_WRITE)).toBe(true);
    expect(hasPerm(null, Perm.TREE_READ)).toBe(false);
    expect(isTreeAdmin({ my_roles: ["FAMILY_ADMIN"] })).toBe(true);
    expect(isTreeAdmin({ my_roles: ["BRANCH_ADMIN"] })).toBe(false);
  });
});
