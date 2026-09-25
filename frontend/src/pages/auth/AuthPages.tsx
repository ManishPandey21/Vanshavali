import { useState, type FormEvent, type ReactNode } from "react";
import { Link, Navigate, useLocation, useNavigate, useSearchParams } from "react-router-dom";
import { useTranslation } from "react-i18next";
import { useLogin, useMe, useRegister, useResendVerification } from "../../api/hooks/auth";
import { ApiError } from "../../api/client";
import { Button } from "../../components/ui/Button";
import { ErrorAlert, LiveRegion, Spinner } from "../../components/ui/feedback";
import { Field, TextInput } from "../../components/ui/form";
import { BrandMark } from "../../components/layout/AppShell";
import { LanguageSwitcher } from "../../components/layout/LanguageSwitcher";
import i18n, { normalizeLanguage } from "../../i18n";

/**
 * Only allow same-origin, path-only redirects after login (no open redirect).
 * Rejects protocol-relative ("//x"), backslash variants ("/\\x", which browsers normalise to "//x"),
 * control characters, and anything that resolves to another origin.
 */
export function safeNext(next: string | null): string {
  if (!next || !next.startsWith("/") || next.startsWith("//")) return "/";
  // eslint-disable-next-line no-control-regex
  if (/[\\\u0000-\u001f\u007f]/.test(next)) return "/";
  try {
    const base = typeof window !== "undefined" ? window.location.origin : "http://localhost";
    const url = new URL(next, base);
    if (url.origin !== base) return "/";
    return `${url.pathname}${url.search}${url.hash}`;
  } catch {
    return "/";
  }
}

function AuthFrame({ title, subtitle, children, footer }: { title: string; subtitle?: string; children: ReactNode; footer?: ReactNode }) {
  const { t } = useTranslation();
  return (
    <div className="flex min-h-dvh flex-col bg-[radial-gradient(ellipse_at_top,_#fbe3d6,_#fbf7ef_60%)]">
      <header className="flex items-center justify-between px-4 py-3">
        <BrandMark to="/login" />
        <LanguageSwitcher />
      </header>
      <main id="main" className="flex flex-1 items-start justify-center px-4 py-8 sm:items-center">
        <div className="w-full max-w-md">
          <div className="card p-6 sm:p-8">
            <h1 className="font-display text-2xl font-bold">{title}</h1>
            {subtitle && <p className="mt-1 text-sm text-ink-muted">{subtitle}</p>}
            <div className="mt-6">{children}</div>
          </div>
          {footer && <div className="mt-4 text-center text-sm">{footer}</div>}
          <p className="mt-6 text-center text-xs text-ink-muted">{t("auth.privacyPromise")}</p>
        </div>
      </main>
    </div>
  );
}

export function LoginPage() {
  const { t } = useTranslation();
  const [params] = useSearchParams();
  const next = safeNext(params.get("next"));
  const me = useMe();
  const login = useLogin();
  const navigate = useNavigate();
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  // Second step: the server answered 401 mfa_required, so ask for the authenticator code.
  const [mfaStep, setMfaStep] = useState(false);
  const [code, setCode] = useState("");
  const resend = useResendVerification();
  const location = useLocation();
  const passwordReset = (location.state as { passwordReset?: boolean } | null)?.passwordReset === true;

  if (me.isLoading) return <Spinner />;
  if (me.data) return <Navigate to={next} replace />;

  const submit = (e: FormEvent) => {
    e.preventDefault();
    resend.reset();
    login.mutate(
      { email, password, ...(mfaStep ? { mfa_code: code.replace(/\s+/g, "") } : {}) },
      {
        onSuccess: (u) => {
          void i18n.changeLanguage(normalizeLanguage(u.preferred_language));
          navigate(next, { replace: true });
        },
        onError: (err) => {
          if (err instanceof ApiError && err.code === "mfa_required") setMfaStep(true);
        },
      },
    );
  };
  const e = login.error;
  const notVerified = e instanceof ApiError && e.code === "email_not_verified";
  const err =
    (e instanceof ApiError && e.code === "mfa_required") || notVerified
      ? null
      : e instanceof ApiError && e.code === "mfa_invalid"
        ? new Error(t("auth.mfaInvalid"))
        : e instanceof ApiError && e.status === 401
          ? new Error(t("auth.invalidCredentials"))
          : e;
  return (
    <AuthFrame
      title={mfaStep ? t("auth.mfaTitle") : t("auth.loginTitle")}
      subtitle={mfaStep ? t("auth.mfaSubtitle") : t("auth.loginSubtitle")}
      footer={
        mfaStep ? (
          <button
            type="button"
            className="font-medium text-kumkum-800 underline"
            onClick={() => {
              setMfaStep(false);
              setCode("");
              login.reset();
            }}
          >
            {t("auth.mfaBack")}
          </button>
        ) : (
          <>
            {t("auth.noAccount")}{" "}
            <Link className="font-medium text-kumkum-800 underline" to={`/register${params.get("next") ? `?next=${encodeURIComponent(next)}` : ""}`}>
              {t("auth.createAccount")}
            </Link>
          </>
        )
      }
    >
      {passwordReset && (
        <p role="status" className="mb-4 rounded-lg border border-green-300 bg-green-50 px-3 py-2 text-sm text-green-900">
          {t("auth.resetDone")}
        </p>
      )}
      <form onSubmit={submit} className="space-y-4" noValidate>
        {mfaStep ? (
          <Field label={t("auth.mfaCode")} required hint={t("auth.mfaCodeHint")}>
            {(p) => (
              <TextInput
                {...p}
                autoFocus
                inputMode="numeric"
                autoComplete="one-time-code"
                pattern="[0-9]*"
                maxLength={10}
                value={code}
                onChange={(ev) => setCode(ev.target.value)}
              />
            )}
          </Field>
        ) : (
          <>
            <Field label={t("auth.email")} required>
              {(p) => <TextInput {...p} type="email" autoComplete="email" required value={email} onChange={(ev) => setEmail(ev.target.value)} />}
            </Field>
            <Field label={t("auth.password")} required>
              {(p) => <TextInput {...p} type="password" autoComplete="current-password" required value={password} onChange={(ev) => setPassword(ev.target.value)} />}
            </Field>
            <p className="-mt-2 text-right text-sm">
              <Link className="font-medium text-kumkum-800 underline" to="/forgot-password">
                {t("auth.forgotPassword")}
              </Link>
            </p>
          </>
        )}
        {notVerified && (
          <div role="alert" className="space-y-2 rounded-lg border border-amber-300 bg-amber-50 px-3 py-2 text-sm text-ink">
            <p>{t("auth.emailNotVerified")}</p>
            {resend.isSuccess ? (
              <p className="font-medium">{t("auth.resent")}</p>
            ) : (
              <Button type="button" variant="secondary" size="sm" loading={resend.isPending} onClick={() => resend.mutate(email)}>
                {t("auth.resendLink")}
              </Button>
            )}
            <ErrorAlert error={resend.error} />
          </div>
        )}
        <ErrorAlert error={err} />
        <Button type="submit" className="w-full" loading={login.isPending} disabled={mfaStep && code.replace(/\s+/g, "").length < 6}>
          {mfaStep ? t("auth.mfaVerify") : t("auth.login")}
        </Button>
      </form>
    </AuthFrame>
  );
}

export function RegisterPage() {
  const { t, i18n: inst } = useTranslation();
  const [params] = useSearchParams();
  const next = safeNext(params.get("next"));
  const me = useMe();
  const register = useRegister();
  const [displayName, setDisplayName] = useState("");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [submitted, setSubmitted] = useState(false);
  const resend = useResendVerification();

  if (me.isLoading) return <Spinner />;
  if (me.data) return <Navigate to={next} replace />;

  if (register.isSuccess) {
    return (
      <AuthFrame
        title={t("auth.checkEmailTitle")}
        footer={
          <Link className="font-medium text-kumkum-800 underline" to={`/login${params.get("next") ? `?next=${encodeURIComponent(next)}` : ""}`}>
            {t("auth.backToLogin")}
          </Link>
        }
      >
        <div className="space-y-4 text-sm">
          <p>{t("auth.checkEmailBody", { email: email.trim() })}</p>
          <p className="text-ink-muted">{t("auth.checkEmailHint")}</p>
          <LiveRegion message={resend.isSuccess ? t("auth.resent") : ""} />
          {resend.isSuccess && <p className="font-medium">{t("auth.resent")}</p>}
          <ErrorAlert error={resend.error} />
          <div className="flex flex-wrap gap-2">
            <Button type="button" variant="secondary" loading={resend.isPending} disabled={resend.isSuccess} onClick={() => resend.mutate(email.trim())}>
              {t("auth.resendLink")}
            </Button>
            <Button
              type="button"
              variant="ghost"
              onClick={() => {
                register.reset();
                resend.reset();
                setPassword("");
                setSubmitted(false);
              }}
            >
              {t("auth.useDifferentEmail")}
            </Button>
          </div>
        </div>
      </AuthFrame>
    );
  }

  const pwTooShort = password.length < 10;
  const fieldErrors = register.error instanceof ApiError ? register.error.fieldErrors() : {};
  const submit = (e: FormEvent) => {
    e.preventDefault();
    setSubmitted(true);
    if (pwTooShort || !displayName.trim() || !email.trim()) return;
    register.mutate({
      email: email.trim(),
      password,
      display_name: displayName.trim(),
      preferred_language: normalizeLanguage(inst.language),
      // carried in the emailed link so an invitation continues after verification
      ...(next !== "/" ? { next } : {}),
    });
  };
  return (
    <AuthFrame
      title={t("auth.registerTitle")}
      subtitle={t("auth.registerSubtitle")}
      footer={
        <>
          {t("auth.haveAccount")}{" "}
          <Link className="font-medium text-kumkum-800 underline" to={`/login${params.get("next") ? `?next=${encodeURIComponent(next)}` : ""}`}>
            {t("auth.login")}
          </Link>
        </>
      }
    >
      <form onSubmit={submit} className="space-y-4" noValidate>
        <Field label={t("auth.displayName")} required error={submitted && !displayName.trim() ? t("common.required") : fieldErrors.display_name}>
          {(p) => <TextInput {...p} autoComplete="name" value={displayName} onChange={(e) => setDisplayName(e.target.value)} />}
        </Field>
        <Field label={t("auth.email")} required error={submitted && !email.trim() ? t("common.required") : fieldErrors.email}>
          {(p) => <TextInput {...p} type="email" autoComplete="email" value={email} onChange={(e) => setEmail(e.target.value)} />}
        </Field>
        <Field
          label={t("auth.password")}
          required
          hint={t("auth.passwordHint")}
          error={submitted && pwTooShort ? t("auth.passwordTooShort") : fieldErrors.password}
        >
          {(p) => <TextInput {...p} type="password" autoComplete="new-password" value={password} onChange={(e) => setPassword(e.target.value)} />}
        </Field>
        <ErrorAlert error={register.error && !Object.keys(fieldErrors).length ? register.error : null} />
        <Button type="submit" className="w-full" loading={register.isPending}>
          {t("auth.createAccount")}
        </Button>
      </form>
    </AuthFrame>
  );
}

export { AuthFrame };
