/// <reference types="vite/client" />

/** Build-time settings read by the SPA. Every value is public: never put a secret here. */
interface ImportMetaEnv {
  /** Hosted fixed-amount checkout pages for the landing-page support presets (Razorpay only). */
  readonly VITE_DONATION_LINK_10?: string;
  readonly VITE_DONATION_LINK_50?: string;
  readonly VITE_DONATION_LINK_100?: string;
  readonly VITE_DONATION_LINK_1000?: string;
  readonly VITE_DONATION_LINK_10000?: string;
  /** Hosted page on which the donor enters and confirms their own amount. */
  readonly VITE_DONATION_LINK_CUSTOM?: string;
}

interface ImportMeta {
  readonly env: ImportMetaEnv;
}
