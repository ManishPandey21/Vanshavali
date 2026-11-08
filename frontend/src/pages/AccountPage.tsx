import { useState, type FormEvent } from "react";
import { useTranslation } from "react-i18next";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Link, useNavigate } from "react-router-dom";
import { ShieldCheck } from "lucide-react";
import { authKeys, useMe, useUpdateProfile } from "../api/hooks/auth";
import { ApiError, api } from "../api/client";
import type { components } from "../api/schema";
import type { Message, UserOut } from "../api/types";
import { Button } from "../components/ui/Button";
import { ErrorAlert, LiveRegion, PageHeader, Spinner } from "../components/ui/feedback";
import { Field, TextInput } from "../components/ui/form";
import { Badge } from "../components/ui/Badge";
import { LanguageSwitcher } from "../components/layout/LanguageSwitcher";
import { KinshipPreferenceCard } from "../components/culture/KinshipSettings";

type SessionOut = components["schemas"]["SessionOut"];

export function AccountPage() {
  const { t, i18n } = useTranslation();
  const me = useMe();
  const update = useUpdateProfile();
  const qc = useQueryClient();
  const [name, setName] = useState<string | null>(null);
  const sessions = useQuery({ queryKey: ["auth", "sessions"], queryFn: () => api.get<SessionOut[]>("/auth/sessions") });
  const revoke = useMutation({
    mutationFn: () => api.post<Message>("/auth/sessions/revoke-others"),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["auth", "sessions"] }),
  });
  const [pw, setPw] = useState({ current: "", next: "" });
  const changePw = useMutation({
    mutationFn: () => api.post<Message>("/auth/password", { current_password: pw.current, new_password: pw.next }),
    onSuccess: () => {
      setPw({ current: "", next: "" });
      qc.invalidateQueries({ queryKey: ["auth", "sessions"] });
    },
  });
  if (me.isLoading || !me.data) return <Spinner />;
  const displayName = name ?? me.data.display_name;
  const fmt = (d: string) => new Date(d).toLocaleString(i18n.language);

  return (
    <div className="mx-auto max-w-2xl space-y-6">
      <PageHeader title={t("account.title")} subtitle={me.data.email} />
      <section className="card space-y-4 p-5" aria-labelledby="acc-profile">
        <h2 id="acc-profile" className="font-display text-lg font-semibold">
          {t("account.profile")}
        </h2>
        <form
          className="flex flex-col gap-3 sm:flex-row sm:items-end"
          onSubmit={(e: FormEvent) => {
            e.preventDefault();
            if (displayName.trim()) update.mutate({ display_name: displayName.trim() });
          }}
        >
          <Field label={t("auth.displayName")} className="flex-1">
            {(p) => <TextInput {...p} value={displayName} onChange={(e) => setName(e.target.value)} />}
          </Field>
          <Button type="submit" loading={update.isPending}>
            {t("common.save")}
          </Button>
        </form>
        <div>
          <p className="label">{t("account.language")}</p>
          <LanguageSwitcher />
          <p className="hint">{t("account.languageHint")}</p>
        </div>
        <ErrorAlert error={update.error} />
        <LiveRegion message={update.isSuccess ? t("common.saved") : ""} />
      </section>
      <KinshipPreferenceCard />

      <MfaSection mfaEnabled={!!me.data.mfa_enabled} />

      <section className="card space-y-3 p-5" aria-labelledby="acc-sessions">
        <h2 id="acc-sessions" className="font-display text-lg font-semibold">
          {t("account.sessions")}
        </h2>
        {sessions.isLoading && <Spinner />}
        <ul className="divide-y divide-stone-200 text-sm">
          {sessions.data?.map((s) => (
            <li key={s.id} className="flex flex-wrap items-center justify-between gap-2 py-2">
              <span className="min-w-0 truncate">{s.user_agent ?? t("account.unknownDevice")}</span>
              <span className="text-xs text-ink-muted">
                {t("account.lastSeen")}: {fmt(s.last_seen_at)} {s.current && <Badge tone="green">{t("account.thisDevice")}</Badge>}
              </span>
            </li>
          ))}
        </ul>
        <Button variant="secondary" onClick={() => revoke.mutate()} loading={revoke.isPending}>
          {t("account.revokeOthers")}
        </Button>
        <ErrorAlert error={revoke.error} />
        <LiveRegion message={revoke.data?.message ?? ""} />
      </section>

      <section className="card space-y-3 p-5" aria-labelledby="acc-pw">
        <h2 id="acc-pw" className="font-display text-lg font-semibold">
          {t("account.changePassword")}
        </h2>
        <form
          className="space-y-3"
          onSubmit={(e) => {
            e.preventDefault();
            if (pw.next.length >= 10) changePw.mutate();
          }}
        >
          <Field label={t("account.currentPassword")}>
            {(p) => <TextInput {...p} type="password" autoComplete="current-password" value={pw.current} onChange={(e) => setPw({ ...pw, current: e.target.value })} />}
          </Field>
          <Field label={t("account.newPassword")} hint={t("auth.passwordHint")}>
            {(p) => <TextInput {...p} type="password" autoComplete="new-password" value={pw.next} onChange={(e) => setPw({ ...pw, next: e.target.value })} />}
          </Field>
          <ErrorAlert error={changePw.error} />
          <LiveRegion message={changePw.data?.message ?? ""} />
          <Button type="submit" loading={changePw.isPending} disabled={pw.next.length < 10 || !pw.current}>
            {t("account.changePassword")}
          </Button>
        </form>
      </section>
      <CloseAccountSection />
    </div>
  );
}

type MfaSetupOut = components["schemas"]["MfaSetupOut"];

/** TOTP two-factor: set up (secret + otpauth URI shown as text), verify to enable, or disable. */
export function MfaSection({ mfaEnabled }: { mfaEnabled: boolean }) {
  const { t } = useTranslation();
  const qc = useQueryClient();
  const [setup, setSetup] = useState<MfaSetupOut | null>(null);
  const [code, setCode] = useState("");
  const [password, setPassword] = useState("");
  const onUser = (u: UserOut) => {
    qc.setQueryData(authKeys.me, u);
    setSetup(null);
    setCode("");
    setPassword("");
  };
  const begin = useMutation({ mutationFn: () => api.post<MfaSetupOut>("/auth/mfa/setup"), onSuccess: setSetup });
  const enable = useMutation({ mutationFn: () => api.post<UserOut>("/auth/mfa/enable", { code: code.replace(/\s+/g, "") }), onSuccess: onUser });
  const disable = useMutation({ mutationFn: () => api.post<UserOut>("/auth/mfa/disable", { password, code: code.replace(/\s+/g, "") }), onSuccess: onUser });
  const codeOk = /^\d{6,10}$/.test(code.replace(/\s+/g, ""));
  const errMsg = (e: unknown) => (e instanceof ApiError && e.code === "mfa_invalid" ? new Error(t("auth.mfaInvalid")) : e);
  return (
    <section className="card space-y-3 p-5" aria-labelledby="acc-mfa">
      <h2 id="acc-mfa" className="flex items-center gap-2 font-display text-lg font-semibold">
        <ShieldCheck className="size-5 text-leaf-700" aria-hidden /> {t("account.mfa.title")}
        {mfaEnabled ? <Badge tone="green">{t("account.mfa.on")}</Badge> : <Badge tone="stone">{t("account.mfa.off")}</Badge>}
      </h2>
      <p className="text-sm text-ink-muted">{t("account.mfa.intro")}</p>
      {!mfaEnabled && !setup && (
        <Button variant="secondary" loading={begin.isPending} onClick={() => begin.mutate()}>
          {t("account.mfa.setUp")}
        </Button>
      )}
      <ErrorAlert error={begin.error} />
      {!mfaEnabled && setup && (
        <form
          className="space-y-3"
          onSubmit={(e) => {
            e.preventDefault();
            if (codeOk) enable.mutate();
          }}
        >
          <ol className="list-inside list-decimal space-y-2 text-sm">
            <li>{t("account.mfa.step1")}</li>
            <li>
              {t("account.mfa.step2")}
              <div className="mt-1 break-all rounded-lg bg-parchment-deep p-2 font-mono text-sm" data-testid="mfa-secret">
                {setup.secret}
              </div>
              <details className="mt-1 text-xs">
                <summary className="cursor-pointer text-kumkum-800">{t("account.mfa.showUri")}</summary>
                <code className="block break-all p-1" data-testid="mfa-uri">
                  {setup.otpauth_uri}
                </code>
              </details>
            </li>
            <li>{t("account.mfa.step3")}</li>
          </ol>
          <Field label={t("auth.mfaCode")}>
            {(p) => <TextInput {...p} inputMode="numeric" autoComplete="one-time-code" maxLength={10} value={code} onChange={(e) => setCode(e.target.value)} />}
          </Field>
          <ErrorAlert error={errMsg(enable.error)} />
          <div className="flex gap-2">
            <Button type="submit" loading={enable.isPending} disabled={!codeOk}>
              {t("account.mfa.enable")}
            </Button>
            <Button variant="secondary" onClick={() => setSetup(null)}>
              {t("common.cancel")}
            </Button>
          </div>
        </form>
      )}
      {mfaEnabled && (
        <form
          className="space-y-3"
          onSubmit={(e) => {
            e.preventDefault();
            if (codeOk && password) disable.mutate();
          }}
        >
          <p className="text-sm">{t("account.mfa.disableIntro")}</p>
          <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
            <Field label={t("account.currentPassword")}>
              {(p) => <TextInput {...p} type="password" autoComplete="current-password" value={password} onChange={(e) => setPassword(e.target.value)} />}
            </Field>
            <Field label={t("auth.mfaCode")}>
              {(p) => <TextInput {...p} inputMode="numeric" autoComplete="one-time-code" maxLength={10} value={code} onChange={(e) => setCode(e.target.value)} />}
            </Field>
          </div>
          <ErrorAlert error={errMsg(disable.error)} />
          <Button type="submit" variant="secondary" loading={disable.isPending} disabled={!codeOk || !password}>
            {t("account.mfa.disable")}
          </Button>
        </form>
      )}
      <LiveRegion message={enable.isSuccess ? t("account.mfa.enabled") : disable.isSuccess ? t("account.mfa.disabled") : ""} />
    </section>
  );
}

const CLOSE_PHRASE = "CLOSE";

/** Close the account: password + typed confirmation. Sole owners get a link to the tree to fix. */
export function CloseAccountSection() {
  const { t } = useTranslation();
  const qc = useQueryClient();
  const navigate = useNavigate();
  const [password, setPassword] = useState("");
  const [phrase, setPhrase] = useState("");
  const close = useMutation({
    mutationFn: () => api.post<Message>("/auth/close-account", { password }),
    onSuccess: () => {
      qc.clear();
      qc.setQueryData(authKeys.me, null);
      navigate("/login", { replace: true });
    },
  });
  const soleOwner = close.error instanceof ApiError && close.error.code === "sole_owner" ? close.error : null;
  const soleTree = soleOwner ? ((soleOwner.details as { tree_id?: string } | null)?.tree_id ?? null) : null;
  const ready = !!password && phrase.trim() === CLOSE_PHRASE;
  return (
    <section className="card space-y-3 border-red-300 p-5" aria-labelledby="acc-close">
      <h2 id="acc-close" className="font-display text-lg font-semibold text-red-900">
        {t("account.close.title")}
      </h2>
      <p className="text-sm">{t("account.close.intro")}</p>
      <form
        className="space-y-3"
        onSubmit={(e) => {
          e.preventDefault();
          if (ready) close.mutate();
        }}
      >
        <Field label={t("account.currentPassword")}>
          {(p) => <TextInput {...p} type="password" autoComplete="current-password" value={password} onChange={(e) => setPassword(e.target.value)} />}
        </Field>
        <Field label={t("account.close.typeToConfirm", { phrase: CLOSE_PHRASE })}>
          {(p) => <TextInput {...p} value={phrase} onChange={(e) => setPhrase(e.target.value)} autoComplete="off" />}
        </Field>
        {soleOwner ? (
          <p role="alert" className="rounded-lg border border-haldi-300 bg-haldi-100 p-3 text-sm text-haldi-700">
            {t("account.close.soleOwner")}{" "}
            {soleTree && (
              <Link className="font-medium underline" to={`/t/${soleTree}/admin/members`}>
                {t("account.close.openTree")}
              </Link>
            )}
          </p>
        ) : (
          <ErrorAlert error={close.error} />
        )}
        <Button type="submit" variant="danger" loading={close.isPending} disabled={!ready}>
          {t("account.close.submit")}
        </Button>
      </form>
    </section>
  );
}
