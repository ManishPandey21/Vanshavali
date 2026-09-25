import { useState, type FormEvent, type ReactNode } from "react";
import { Link, Navigate, useNavigate, useSearchParams } from "react-router-dom";
import { useTranslation } from "react-i18next";
import { useLogin, useMe, useRegister } from "../../api/hooks/auth";
import { ApiError } from "../../api/client";
import { Button } from "../../components/ui/Button";
import { ErrorAlert, Spinner } from "../../components/ui/feedback";
import { Field, TextInput } from "../../components/ui/form";
import { BrandMark } from "../../components/layout/AppShell";
import { LanguageSwitcher } from "../../components/layout/LanguageSwitcher";
import i18n, { normalizeLanguage } from "../../i18n";

/** Only allow same-origin, path-only redirects after login (no open redirect). */
export function safeNext(next: string | null): string {
  if (!next || !next.startsWith("/") || next.startsWith("//")) return "/";
  return next;
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

  if (me.isLoading) return <Spinner />;
  if (me.data) return <Navigate to={next} replace />;

  const submit = (e: FormEvent) => {
    e.preventDefault();
    login.mutate(
      { email, password },
      {
        onSuccess: (u) => {
          void i18n.changeLanguage(normalizeLanguage(u.preferred_language));
          navigate(next, { replace: true });
        },
      },
    );
  };
  const err = login.error instanceof ApiError && login.error.status === 401 ? new Error(t("auth.invalidCredentials")) : login.error;
  return (
    <AuthFrame
      title={t("auth.loginTitle")}
      subtitle={t("auth.loginSubtitle")}
      footer={
        <>
          {t("auth.noAccount")}{" "}
          <Link className="font-medium text-kumkum-800 underline" to={`/register${params.get("next") ? `?next=${encodeURIComponent(next)}` : ""}`}>
            {t("auth.createAccount")}
          </Link>
        </>
      }
    >
      <form onSubmit={submit} className="space-y-4" noValidate>
        <Field label={t("auth.email")} required>
          {(p) => <TextInput {...p} type="email" autoComplete="email" required value={email} onChange={(e) => setEmail(e.target.value)} />}
        </Field>
        <Field label={t("auth.password")} required>
          {(p) => <TextInput {...p} type="password" autoComplete="current-password" required value={password} onChange={(e) => setPassword(e.target.value)} />}
        </Field>
        <ErrorAlert error={err} />
        <Button type="submit" className="w-full" loading={login.isPending}>
          {t("auth.login")}
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
  const navigate = useNavigate();
  const [displayName, setDisplayName] = useState("");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [submitted, setSubmitted] = useState(false);

  if (me.isLoading) return <Spinner />;
  if (me.data) return <Navigate to={next} replace />;

  const pwTooShort = password.length < 10;
  const fieldErrors = register.error instanceof ApiError ? register.error.fieldErrors() : {};
  const submit = (e: FormEvent) => {
    e.preventDefault();
    setSubmitted(true);
    if (pwTooShort || !displayName.trim() || !email.trim()) return;
    register.mutate(
      { email, password, display_name: displayName.trim(), preferred_language: normalizeLanguage(inst.language) },
      { onSuccess: () => navigate(next, { replace: true }) },
    );
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
