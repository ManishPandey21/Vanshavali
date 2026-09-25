import { useState, type FormEvent } from "react";
import { useTranslation } from "react-i18next";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useMe, useUpdateProfile } from "../api/hooks/auth";
import { api } from "../api/client";
import type { components } from "../api/schema";
import type { Message } from "../api/types";
import { Button } from "../components/ui/Button";
import { ErrorAlert, LiveRegion, PageHeader, Spinner } from "../components/ui/feedback";
import { Field, TextInput } from "../components/ui/form";
import { Badge } from "../components/ui/Badge";
import { LanguageSwitcher } from "../components/layout/LanguageSwitcher";

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
    </div>
  );
}
