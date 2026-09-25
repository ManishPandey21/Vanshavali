/**
 * Client-side mirror of the partition balance rule (backend property/service.record_partition):
 * the allocated shares must add up exactly to the ownership shares being ended, unless the deed is
 * partial (allow_partial). The server re-validates; this only gives early, precise feedback.
 */
import { ONE, ZERO, add, cmp, fmt, parseShare, sum, type Fraction } from "./fractions";

export interface AllocationDraft {
  holderOk: boolean;
  share: string;
}

export interface PartitionCheck {
  ended: Fraction;
  allocated: Fraction;
  balanced: boolean;
  /** i18n keys for blocking problems (submit disabled). */
  errors: string[];
  /** i18n key for a non-blocking warning (partial deed). */
  warning: string | null;
}

export function checkPartition(endedShares: Fraction[], allocations: AllocationDraft[], allowPartial: boolean, hasDate: boolean): PartitionCheck {
  const errors: string[] = [];
  const ended = sum(endedShares);
  let allocated = ZERO;
  if (!hasDate) errors.push("partition.err.date");
  if (allocations.length === 0) errors.push("partition.err.noAllocations");
  allocations.forEach((a) => {
    const p = parseShare(a.share);
    if (!a.holderOk) errors.push("partition.err.holder");
    if (!p.ok) errors.push("partition.err.share");
    else if (p.value.num === 0n) errors.push("partition.err.zeroShare");
    else allocated = add(allocated, p.value);
  });
  if (cmp(allocated, ONE) > 0) errors.push("partition.err.overWhole");
  const balanced = cmp(allocated, ended) === 0;
  let warning: string | null = null;
  if (!allowPartial) {
    if (cmp(ended, ZERO) === 0) errors.push("partition.err.nothingEnded");
    else if (!balanced && errors.length === 0) errors.push("partition.err.unbalanced");
  } else if (!balanced) {
    warning = "partition.warnPartial";
  }
  return { ended, allocated, balanced, errors: [...new Set(errors)], warning };
}

export function describeTotals(c: PartitionCheck): { allocated: string; ended: string } {
  return { allocated: fmt(c.allocated), ended: fmt(c.ended) };
}
