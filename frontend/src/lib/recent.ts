/**
 * "Recently viewed" people, per tree, kept in this browser only. Stores IDs (never names or other
 * family data) so nothing sensitive is left in localStorage; names are re-fetched with privacy applied.
 */
const KEY = (treeId: string) => `vsh_recent_${treeId}`;

export function recentPeople(treeId: string): string[] {
  try {
    const raw = localStorage.getItem(KEY(treeId));
    const v = raw ? (JSON.parse(raw) as unknown) : [];
    return Array.isArray(v) ? v.filter((x): x is string => typeof x === "string").slice(0, 8) : [];
  } catch {
    return [];
  }
}

export function rememberPerson(treeId: string, personId: string) {
  try {
    const list = [personId, ...recentPeople(treeId).filter((x) => x !== personId)].slice(0, 8);
    localStorage.setItem(KEY(treeId), JSON.stringify(list));
  } catch {
    /* ignore */
  }
}

export function forgetPerson(treeId: string, personId: string) {
  try {
    localStorage.setItem(KEY(treeId), JSON.stringify(recentPeople(treeId).filter((x) => x !== personId)));
  } catch {
    /* ignore */
  }
}
