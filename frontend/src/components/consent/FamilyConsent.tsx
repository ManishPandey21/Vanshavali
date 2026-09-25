import { useId, useState, type ReactNode } from "react";
import { useTranslation } from "react-i18next";
import { ShieldCheck } from "lucide-react";
import { useAttest, useAttestation, useStatement } from "../../api/hooks/onboarding";
import type { StatementKind, StatementOut } from "../../api/types";
import { Button } from "../ui/Button";
import { ErrorAlert, Spinner } from "../ui/feedback";

/**
 * A consent checkbox whose label is the server-owned statement (ADR-0011). It is never pre-ticked.
 * The text comes from the API so that what the user reads is exactly what the server records.
 */
export function StatementCheckbox({
  kind,
  checked,
  onChange,
  error,
  onStatement,
}: {
  kind: StatementKind;
  checked: boolean;
  onChange: (v: boolean) => void;
  error?: string | null;
  onStatement?: (s: StatementOut) => void;
}) {
  const { i18n } = useTranslation();
  const statement = useStatement(kind, i18n.language);
  const id = useId();
  const errId = `${id}-err`;
  if (statement.isLoading) return <Spinner />;
  if (!statement.data) return <ErrorAlert error={statement.error} />;
  const s = statement.data;
  return (
    <div>
      <div className="flex items-start gap-3 rounded-lg border border-kumkum-200 bg-kumkum-50/50 p-3">
        <input
          id={id}
          type="checkbox"
          className="mt-0.5 size-5 shrink-0 accent-kumkum-700"
          checked={checked}
          aria-invalid={error ? true : undefined}
          aria-describedby={error ? errId : undefined}
          onChange={(e) => {
            onChange(e.target.checked);
            onStatement?.(s);
          }}
        />
        <label htmlFor={id} lang={s.language} className="text-sm font-medium leading-relaxed">
          {s.text}
        </label>
      </div>
      {error && (
        <p id={errId} className="field-error">
          {error}
        </p>
      )}
    </div>
  );
}

/** Shows `children` (e.g. an add-person form) only once the user has confirmed the family-data statement for this tree. */
export function FamilyConsentGate({ treeId, children }: { treeId: string; children: ReactNode }) {
  const status = useAttestation(treeId);
  if (status.isLoading) return <Spinner />;
  if (status.data?.attested) return <>{children}</>;
  return <FamilyConsentCard treeId={treeId} error={status.error} />;
}

function FamilyConsentCard({ treeId, error }: { treeId: string; error: unknown }) {
  const { t, i18n } = useTranslation();
  const statement = useStatement("family_data", i18n.language);
  const attest = useAttest();
  const [checked, setChecked] = useState(false);
  const [missing, setMissing] = useState(false);
  const confirm = () => {
    if (!checked || !statement.data) {
      setMissing(true);
      return;
    }
    setMissing(false);
    attest.mutate({ treeId, statement: statement.data });
  };
  return (
    <section className="card space-y-3 p-4" aria-labelledby={`${treeId}-consent-title`}>
      <h2 id={`${treeId}-consent-title`} className="flex items-center gap-2 font-display text-lg font-semibold">
        <ShieldCheck className="size-5 text-leaf-700" aria-hidden />
        {t("onboarding.consent.gateTitle")}
      </h2>
      <p className="text-sm text-ink-muted">{t("onboarding.consent.gateBody")}</p>
      <StatementCheckbox kind="family_data" checked={checked} onChange={setChecked} error={missing ? t("onboarding.consent.required") : null} />
      <p className="text-xs text-ink-muted">{t("onboarding.consent.why")}</p>
      <ErrorAlert error={error || attest.error} />
      <div className="flex justify-end">
        <Button onClick={confirm} loading={attest.isPending}>
          {t("onboarding.consent.confirm")}
        </Button>
      </div>
    </section>
  );
}
