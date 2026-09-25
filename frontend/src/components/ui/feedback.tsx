import type { ReactNode } from "react";
import { useTranslation } from "react-i18next";
import { AlertTriangle, Loader2, Lock } from "lucide-react";
import { ApiError } from "../../api/client";

export function Spinner({ label }: { label?: string }) {
  const { t } = useTranslation();
  return (
    <div role="status" className="flex items-center gap-2 p-4 text-sm text-ink-muted">
      <Loader2 className="size-4 animate-spin" aria-hidden />
      <span>{label ?? t("common.loading")}</span>
    </div>
  );
}

/** Human message for an API error; 403/404 get calm, privacy-aware wording. */
export function useErrorMessage() {
  const { t } = useTranslation();
  return (error: unknown): string => {
    if (error instanceof ApiError) {
      // Keep specific server explanations; replace only the generic default with translated text.
      if (error.status === 403) return error.message && !/^You do not have permission/.test(error.message) ? error.message : t("errors.forbidden");
      if (error.status === 404) return t("errors.notFound");
      if (error.status === 0) return t("errors.network");
      if (error.status === 429) return t("errors.rateLimited");
      if (error.code === "validation_error") {
        const fe = error.fieldErrors();
        const first = Object.entries(fe)[0];
        return first ? `${t("errors.validation")}: ${first[0] ? `${first[0]} — ` : ""}${first[1]}` : t("errors.validation");
      }
      return error.message;
    }
    if (error instanceof Error) return error.message;
    return t("errors.generic");
  };
}

/** Announces async errors to assistive tech (role=alert is an implicit aria-live=assertive). */
export function ErrorAlert({ error, title }: { error: unknown; title?: string }) {
  const msg = useErrorMessage();
  if (!error) return null;
  const forbidden = error instanceof ApiError && error.status === 403;
  return (
    <div
      role="alert"
      className={`flex items-start gap-2 rounded-lg border px-3 py-2 text-sm ${
        forbidden ? "border-stone-300 bg-stone-50 text-ink" : "border-red-300 bg-red-50 text-red-900"
      }`}
    >
      {forbidden ? <Lock className="mt-0.5 size-4 shrink-0" aria-hidden /> : <AlertTriangle className="mt-0.5 size-4 shrink-0" aria-hidden />}
      <div>
        {title && <p className="font-semibold">{title}</p>}
        <p>{msg(error)}</p>
      </div>
    </div>
  );
}

export function LiveRegion({ message }: { message: string }) {
  return (
    <div aria-live="polite" role="status" className="sr-only">
      {message}
    </div>
  );
}

export function EmptyState({ icon, title, children, action }: { icon?: ReactNode; title: string; children?: ReactNode; action?: ReactNode }) {
  return (
    <div className="flex flex-col items-center gap-2 rounded-xl border border-dashed border-stone-300 bg-white/60 px-6 py-10 text-center">
      {icon && <div className="text-haldi-700">{icon}</div>}
      <p className="font-display text-lg font-semibold">{title}</p>
      {children && <div className="max-w-md text-sm text-ink-muted">{children}</div>}
      {action && <div className="mt-2">{action}</div>}
    </div>
  );
}

export function PageHeader({ title, subtitle, actions, eyebrow }: { title: ReactNode; subtitle?: ReactNode; actions?: ReactNode; eyebrow?: ReactNode }) {
  return (
    <header className="mb-5 flex flex-col gap-3 sm:flex-row sm:items-end sm:justify-between">
      <div className="min-w-0">
        {eyebrow && <p className="text-xs font-semibold uppercase tracking-wider text-kumkum-700">{eyebrow}</p>}
        <h1 className="font-display text-2xl font-bold text-ink sm:text-3xl">{title}</h1>
        {subtitle && <p className="mt-1 text-sm text-ink-muted">{subtitle}</p>}
      </div>
      {actions && <div className="flex flex-wrap gap-2">{actions}</div>}
    </header>
  );
}
