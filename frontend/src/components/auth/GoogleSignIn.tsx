import { useTranslation } from "react-i18next";
import { API_BASE } from "../../api/client";
import { useAuthProviders } from "../../api/hooks/auth";

/** Google's four-colour "G" (brand asset drawn inline; no external request). */
function GoogleMark() {
  return (
    <svg viewBox="0 0 48 48" className="size-5" aria-hidden focusable="false">
      <path fill="#EA4335" d="M24 9.5c3.54 0 6.71 1.22 9.21 3.6l6.85-6.85C35.9 2.38 30.47 0 24 0 14.62 0 6.51 5.38 2.56 13.22l7.98 6.19C12.43 13.72 17.74 9.5 24 9.5z" />
      <path fill="#4285F4" d="M46.98 24.55c0-1.57-.15-3.09-.38-4.55H24v9.02h12.94c-.58 2.96-2.26 5.48-4.78 7.18l7.73 6c4.51-4.18 7.09-10.36 7.09-17.65z" />
      <path fill="#FBBC05" d="M10.53 28.59c-.48-1.45-.76-2.99-.76-4.59s.27-3.14.76-4.59l-7.98-6.19C.92 16.46 0 20.12 0 24c0 3.88.92 7.54 2.56 10.78l7.97-6.19z" />
      <path fill="#34A853" d="M24 48c6.48 0 11.93-2.13 15.89-5.81l-7.73-6c-2.15 1.45-4.92 2.3-8.16 2.3-6.26 0-11.57-4.22-13.47-9.91l-7.98 6.19C6.51 42.62 14.62 48 24 48z" />
    </svg>
  );
}

/**
 * "Continue with Google", shown only when the server has Google sign-in configured. It is a plain
 * link: the backend runs the whole OpenID Connect flow and comes back with a normal session.
 */
export function GoogleSignIn({ next }: { next: string }) {
  const { t } = useTranslation();
  const providers = useAuthProviders();
  if (!providers.data?.google) return null;
  const href = `${API_BASE}/auth/google/start?next=${encodeURIComponent(next)}`;
  return (
    <div className="mt-6">
      <div className="flex items-center gap-3 text-xs text-ink-muted" aria-hidden>
        <span className="h-px flex-1 bg-stone-200" />
        {t("auth.orDivider")}
        <span className="h-px flex-1 bg-stone-200" />
      </div>
      <a
        href={href}
        className="mt-4 flex w-full items-center justify-center gap-3 rounded-lg border border-stone-300 bg-white px-4 py-2.5 text-sm font-semibold text-ink shadow-sm hover:bg-stone-50"
      >
        <GoogleMark />
        {t("auth.continueWithGoogle")}
      </a>
    </div>
  );
}

const OAUTH_ERRORS = ["oauth_failed", "oauth_state", "email_unverified", "link_requires_password", "mfa_enabled", "account_inactive"] as const;

/** Explains why a Google sign-in came back to the sign-in page (`?oauth_error=`). */
export function OAuthErrorNotice({ code }: { code: string | null }) {
  const { t } = useTranslation();
  if (!code) return null;
  const known = (OAUTH_ERRORS as readonly string[]).includes(code) ? code : "oauth_failed";
  return (
    <p role="alert" className="mb-4 rounded-lg border border-red-300 bg-red-50 px-3 py-2 text-sm text-red-900">
      {t(`auth.oauthError.${known}`)}
    </p>
  );
}
