import { ApiError } from "../api/client";
import type { ProposalItemIn } from "../api/types";

/**
 * When the family reviews a kind of change (ADR-0021 §1), a direct edit answers 409
 * review_required. The edit hooks hand the attempted change here, and the tree layout's
 * <ProposeChangeHost> offers to send it as a proposed change. The server stays the authority.
 */
type Listener = (item: ProposalItemIn) => void;
const listeners = new Set<Listener>();

export const reviewBus = {
  subscribe(fn: Listener): () => void {
    listeners.add(fn);
    return () => listeners.delete(fn);
  },
  offer(item: ProposalItemIn): void {
    listeners.forEach((fn) => fn(item));
  },
};

export function isReviewRequired(e: unknown): boolean {
  return e instanceof ApiError && e.status === 409 && e.code === "review_required";
}

/** Run a direct edit; if the family reviews such changes, offer it as a proposal and rethrow. */
export async function orPropose<T>(item: ProposalItemIn, run: () => Promise<T>): Promise<T> {
  try {
    return await run();
  } catch (e) {
    if (isReviewRequired(e)) reviewBus.offer(item);
    throw e;
  }
}
