/**
 * Exact rational shares (ADR-0010). Shares are never floats: "1/3 + 1/3 + 1/3" must equal exactly 1.
 * BigInt keeps large denominators (e.g. 1/1680 after several generations of partition) exact.
 */
export interface Fraction {
  num: bigint;
  den: bigint;
}

function gcd(a: bigint, b: bigint): bigint {
  a = a < 0n ? -a : a;
  b = b < 0n ? -b : b;
  while (b) [a, b] = [b, a % b];
  return a || 1n;
}

export function frac(num: bigint | number, den: bigint | number = 1n): Fraction {
  let n = BigInt(num);
  let d = BigInt(den);
  if (d === 0n) throw new Error("zero denominator");
  if (d < 0n) {
    n = -n;
    d = -d;
  }
  const g = gcd(n, d);
  return { num: n / g, den: d / g };
}

export const ZERO = frac(0);
export const ONE = frac(1);

export function add(a: Fraction, b: Fraction): Fraction {
  return frac(a.num * b.den + b.num * a.den, a.den * b.den);
}

export function sub(a: Fraction, b: Fraction): Fraction {
  return frac(a.num * b.den - b.num * a.den, a.den * b.den);
}

export function cmp(a: Fraction, b: Fraction): number {
  const l = a.num * b.den;
  const r = b.num * a.den;
  return l === r ? 0 : l < r ? -1 : 1;
}

export function sum(list: Fraction[]): Fraction {
  return list.reduce(add, ZERO);
}

export function fmt(f: Fraction): string {
  return f.den === 1n ? String(f.num) : `${f.num}/${f.den}`;
}

/** Display-only percentage (never used for arithmetic). */
export function percent(f: Fraction): string {
  const scaled = Number((f.num * 10000n) / f.den) / 100;
  return `${scaled.toLocaleString(undefined, { maximumFractionDigits: 2 })}%`;
}

export const MAX_DENOMINATOR = 10n ** 15n;

export type ShareParse = { ok: true; value: Fraction; numerator: number; denominator: number } | { ok: false; error: string };

/**
 * Parse a share typed as "a/b", "1" (the whole) or "0". Rejects decimals, negatives, zero
 * denominators, shares above the whole and denominators beyond the API's limit.
 * Error values are i18n keys.
 */
export function parseShare(input: string): ShareParse {
  const s = input.replace(/\s+/g, "");
  if (!s) return { ok: false, error: "share.err.required" };
  const m = /^(\d+)(?:\/(\d+))?$/.exec(s);
  if (!m) return { ok: false, error: /[.,]/.test(s) ? "share.err.decimal" : "share.err.format" };
  const n = BigInt(m[1]);
  const d = BigInt(m[2] ?? "1");
  if (d === 0n) return { ok: false, error: "share.err.zeroDen" };
  if (d > MAX_DENOMINATOR || n > MAX_DENOMINATOR) return { ok: false, error: "share.err.tooLarge" };
  if (n > d) return { ok: false, error: "share.err.overWhole" };
  // Send the share as entered (the server reduces it); 2/6 and 1/3 are the same share.
  return { ok: true, value: frac(n, d), numerator: Number(n), denominator: Number(d) };
}

export function fromShare(numerator: number, denominator: number): Fraction {
  return frac(BigInt(numerator), BigInt(denominator));
}

export function parseFractionString(s: string): Fraction {
  const [n, d] = s.split("/");
  return frac(BigInt(n), BigInt(d ?? "1"));
}
