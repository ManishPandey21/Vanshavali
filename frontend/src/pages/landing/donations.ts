/** Validation and safe hosted-checkout URLs for voluntary donations.
 * The browser-entered amount is NOT forwarded to the payment provider.
 * A variable-amount hosted page must let the donor confirm the amount there.
 */
export const DONATION_AMOUNTS = [10, 50, 100, 1000, 10000] as const;
export const MAX_VOLUNTARY_DONATION = 100_000;

export function parseVoluntaryAmount(value: string): number | null {
  // Whole INR only. Do not accept fractions, exponent notation, signs, or empty input.
  if (!/^[0-9]{1,6}$/.test(value)) return null;
  const amount = Number(value);
  return Number.isSafeInteger(amount) && amount >= 1 && amount <= MAX_VOLUNTARY_DONATION
    ? amount
    : null;
}

export function safeHostedDonationLink(configured?: string): string | null {
  if (!configured) return null;
  try {
    const url = new URL(configured);
    return url.protocol === "https:" &&
      ["pages.razorpay.com", "rzp.io", "razorpay.me"].includes(url.hostname) &&
      !url.username && !url.password
      ? url.href
      : null;
  } catch {
    return null;
  }
}
