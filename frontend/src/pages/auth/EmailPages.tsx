import { useEffect, useRef, useState, type FormEvent } from "react";
import { Link, useNavigate, useParams, useSearchParams } from "react-router-dom";
import { useTranslation } from "react-i18next";
import { useConfirmPasswordReset, useRequestPasswordReset, useVerifyEmail } from "../../api/hooks/auth";
import { ApiError } from "../../api/client";
import { Button } from "../../components/ui/Button";
import { ErrorAlert, Spinner } from "../../components/ui/feedback";
import { Field, TextInput } from "../../components/ui/form";
import { AuthFrame, safeNext } from "./AuthPages";

const linkClass = "font-medium text-kumkum-800 underline";

/** Opened from the verification email: confirms the address, signs in, then continues (trees list by default). */
export function VerifyEmailPage() {
  const { t } = useTranslation();
  const { token = "" } = useParams();
  const [params] = useSearchParams();
  const next = safeNext(params.get("next"));
  const verify = useVerifyEmail();
  const { mutate } = verify;
  const navigate = useNavigate();
  const started = useRef(false);

  useEffect(() => {
    // the token is single use: never send it twice (StrictMode re-runs effects in development)
    if (started.current) return;
    started.current = true;
    mutate(token);
  }, [mutate, token]);

  useEffect(() => {
    if (verify.isSuccess) navigate(next, { replace: true });
  }, [verify.isSuccess, navigate, next]);

  const invalid = verify.error instanceof ApiError && verify.error.code === "token_invalid";
  return (
    <AuthFrame
      title={t("auth.verifyTitle")}
      footer={
        verify.isError ? (
          <Link className={linkClass} to="/login">
            {t("auth.backToLogin")}
          </Link>
        ) : undefined
      }
    >
      {verify.isError ? (
        <div className="space-y-3 text-sm">
          {invalid ? (
            <>
              <p role="alert" className="font-medium">
                {t("auth.linkInvalid")}
              </p>
              <p className="text-ink-muted">{t("auth.verifyFailedHint")}</p>
            </>
          ) : (
            <ErrorAlert error={verify.error} />
          )}
        </div>
      ) : (
        <Spinner label={t("auth.verifying")} />
      )}
    </AuthFrame>
  );
}

export function ForgotPasswordPage() {
  const { t } = useTranslation();
  const request = useRequestPasswordReset();
  const [email, setEmail] = useState("");
  const [submitted, setSubmitted] = useState(false);

  const submit = (e: FormEvent) => {
    e.preventDefault();
    setSubmitted(true);
    if (!email.trim()) return;
    request.mutate(email.trim());
  };
  const footer = (
    <Link className={linkClass} to="/login">
      {t("auth.backToLogin")}
    </Link>
  );
  if (request.isSuccess) {
    return (
      <AuthFrame title={t("auth.checkEmailTitle")} footer={footer}>
        <p role="status" className="text-sm">
          {t("auth.resetSent", { email: email.trim() })}
        </p>
      </AuthFrame>
    );
  }
  const fieldErrors = request.error instanceof ApiError ? request.error.fieldErrors() : {};
  return (
    <AuthFrame title={t("auth.forgotTitle")} subtitle={t("auth.forgotSubtitle")} footer={footer}>
      <form onSubmit={submit} className="space-y-4" noValidate>
        <Field label={t("auth.email")} required error={submitted && !email.trim() ? t("common.required") : fieldErrors.email}>
          {(p) => <TextInput {...p} type="email" autoComplete="email" value={email} onChange={(ev) => setEmail(ev.target.value)} />}
        </Field>
        <ErrorAlert error={request.error && !Object.keys(fieldErrors).length ? request.error : null} />
        <Button type="submit" className="w-full" loading={request.isPending}>
          {t("auth.sendResetLink")}
        </Button>
      </form>
    </AuthFrame>
  );
}

export function ResetPasswordPage() {
  const { t } = useTranslation();
  const { token = "" } = useParams();
  const confirm = useConfirmPasswordReset();
  const navigate = useNavigate();
  const [password, setPassword] = useState("");
  const [again, setAgain] = useState("");
  const [submitted, setSubmitted] = useState(false);

  const tooShort = password.length < 10;
  const mismatch = password !== again;
  const submit = (e: FormEvent) => {
    e.preventDefault();
    setSubmitted(true);
    if (tooShort || mismatch) return;
    confirm.mutate(
      { token, new_password: password },
      { onSuccess: () => navigate("/login", { replace: true, state: { passwordReset: true } }) },
    );
  };
  const invalid = confirm.error instanceof ApiError && confirm.error.code === "token_invalid";
  const fieldErrors = confirm.error instanceof ApiError ? confirm.error.fieldErrors() : {};
  return (
    <AuthFrame
      title={t("auth.resetTitle")}
      subtitle={t("auth.resetSubtitle")}
      footer={
        <Link className={linkClass} to="/login">
          {t("auth.backToLogin")}
        </Link>
      }
    >
      {invalid ? (
        <div className="space-y-3 text-sm">
          <p role="alert" className="font-medium">
            {t("auth.linkInvalid")}
          </p>
          <Link className={linkClass} to="/forgot-password">
            {t("auth.requestNewReset")}
          </Link>
        </div>
      ) : (
        <form onSubmit={submit} className="space-y-4" noValidate>
          <Field
            label={t("auth.newPassword")}
            required
            hint={t("auth.passwordHint")}
            error={submitted && tooShort ? t("auth.passwordTooShort") : fieldErrors.new_password}
          >
            {(p) => <TextInput {...p} type="password" autoComplete="new-password" value={password} onChange={(ev) => setPassword(ev.target.value)} />}
          </Field>
          <Field label={t("auth.confirmPassword")} required error={submitted && !tooShort && mismatch ? t("auth.passwordsDontMatch") : undefined}>
            {(p) => <TextInput {...p} type="password" autoComplete="new-password" value={again} onChange={(ev) => setAgain(ev.target.value)} />}
          </Field>
          <ErrorAlert error={confirm.error && !Object.keys(fieldErrors).length ? confirm.error : null} />
          <Button type="submit" className="w-full" loading={confirm.isPending}>
            {t("auth.resetSubmit")}
          </Button>
        </form>
      )}
    </AuthFrame>
  );
}
