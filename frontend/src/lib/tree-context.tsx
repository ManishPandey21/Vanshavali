import { createContext, useContext } from "react";
import type { TreeOut } from "../api/types";
import { hasPerm, isTreeAdmin, type PermValue } from "./permissions";

export interface TreeCtxValue {
  tree: TreeOut;
  treeId: string;
  can: (p: PermValue) => boolean;
  isAdmin: boolean;
}

export const TreeContext = createContext<TreeCtxValue | null>(null);

export function makeTreeCtx(tree: TreeOut): TreeCtxValue {
  return { tree, treeId: tree.id, can: (p) => hasPerm(tree, p), isAdmin: isTreeAdmin(tree) };
}

export function useTreeCtx(): TreeCtxValue {
  const v = useContext(TreeContext);
  if (!v) throw new Error("useTreeCtx must be used inside a tree route");
  return v;
}
