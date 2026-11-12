# Landing-page community impact and voluntary support

Status: implementation proposal (12 November 2026). This is not approval to collect funds.

## Visitor statistics

- `GET /api/v1/public/site-impact` reports `family_trees`: the count of non-deleted tree rows, **not** deduplicated households or people.
- `unique_visitors_30d` is an **approximate 30-day count of distinct browsers**, never an assertion of unique people. It is `null` if measurement is disabled or storage fails, never an invented zero.
- To enable this, set `VSH_VISITOR_STATS_ENABLED=true` and provide working Redis. The setting is **off by default**, pending notice/privacy review.
- The server issues a random, signed first-party HttpOnly cookie under `/api/v1/public`, expiring after 90 days. The browser identifier is HMAC-hashed before Redis. Daily HyperLogLog buckets expire after 35 days. Neither IP addresses, user agents, family names, tree identifiers, or profiles are submitted to the impact store.
- Reading the counter also records a visit; repeated reads by a browser with a valid cookie count once. Incognito windows, deleted cookies, multiple devices and disabled cookies can count separately. HyperLogLog counts are estimates and bots may affect them. This is **not** verified human traffic or a lifetime visitor count.
- The counter is entirely aggregate and does not query the `person`, `relationship`, `document` or `tree_membership` tables.
- Before activation, review retention and visitor privacy disclosures, bot mitigation, API rate limiting and possible abuse of the public endpoint. The release may show the family-tree count while leaving unique visitors unavailable.

## Donations

- The landing page offers five choices: ₹10, ₹50, ₹100, ₹1,000 and ₹10,000.
- Each choice needs its **own** hosted Razorpay checkout page/payment link configured for the correct fixed amount. Set `VITE_DONATION_LINK_10`, `VITE_DONATION_LINK_50`, `VITE_DONATION_LINK_100`, `VITE_DONATION_LINK_1000`, and `VITE_DONATION_LINK_10000` in the **frontend build environment**. Links must use HTTPS on an allowlisted Razorpay domain.
- An unconfigured choice displays an unavailable message; the interface never simulates a successful payment.
- Vanshavali handles no card credentials, payment identifiers or webhook receipts in this increment. The provider is responsible for secure checkout and receipts. Payment verification, refund policy, bookkeeping, tax treatment and beneficiary disclosures must be reviewed before enabling.
- Donation is voluntary and does not confer access to private family records.
- Never claim 80G tax deductibility or charitable status without formal verification. Label the activity “Support Vanshavali” until its legal and financial arrangements are confirmed.

## Verification and release

- Check that the API returns active trees only and contains no private family data.
- Check that repeat visits with the same cookie do not increase the 30-day browser estimate, that a separate cookie does increase it, and that Redis outages produce `null` without breaking the landing page.
- Check English and Hindi translations, keyboard/radio focus, mobile layout, the disabled checkout state, and safe fixed-amount checkout URLs.
- Run backend lint, typing, pytest, frontend lint/typecheck/Vitest/build and Playwright accessibility/visual E2E tests. No deployment or payment activation without CI and a human checkout review.
