import { useState, type FormEvent } from "react";
import { useTranslation } from "react-i18next";
import { ShieldCheck } from "lucide-react";
import type { ConsentBasis, PersonOut, PrivacyLevel } from "../../../api/types";
import { useSetPrivacy } from "../../../api/hooks/people";
import { useConsents, useRecordConsent, useWithdrawConsent } from "../../../api/hooks/heritage";
import { useTreeCtx } from "../../../lib/tree-context";
import { PRIVACY_LEVELS } from "../../../components/person/PersonForm";
import { PrivacyBadge } from "../../../components/person/badges";
import { GrantsPanel } from "../../../components/privacy/GrantsPanel";
import { ErasePanel } from "./ErasePanel";
import { Button } from "../../../components/ui/Button";
import { ErrorAlert, LiveRegion, Spinner } from "../../../components/ui/feedback";
import { Field, Select, TextArea, TextInput } from "../../../components/ui/form";
import { Badge } from "../../../components/ui/Badge";

/** Field groups from backend `app/authz/privacy.py` (FieldGroup.ALL). */
export const FIELD_GROUPS = [
  "birth_date_full",
  "birth_time",
  "birth_place_detail",
  "contact",
  "address",
  "gender_identity",
  "community",
  "jati",
  "religion",
  "heritage",
  "astrology",
  "notes",
] as const;

const CONSENT_BASES: ConsentBasis[] = ["self", "parent_guardian", "legal_representative", "tree_admin_attestation"];

export function PrivacyTab({ person, isClaimant }: { person: PersonOut; isClaimant: boolean }) {
  const { t } = useTranslation();
  const { treeId, isAdmin } = useTreeCtx();
  const setPrivacy = useSetPrivacy(treeId, person.id);
  const [level, setLevel] = useState<PrivacyLevel | "">(person.privacy_level ?? "");
  const current = person.field_privacy ?? null; // only returned to admins
  const [overrides, setOverrides] = useState<Record<string, PrivacyLevel | "">>(() =>
    Object.fromEntries(FIELD_GROUPS.map((g) => [g, ((current ?? {})[g] as PrivacyLevel | undefined) ?? ""])),
  );
  const [saved, setSaved] = useState("");

  const save = (e: FormEvent) => {
    e.preventDefault();
    const field_privacy: Record<string, PrivacyLevel | null> = {};
    for (const g of FIELD_GROUPS) {
      const before = ((current ?? {})[g] as string | undefined) ?? "";
      const after = overrides[g];
      if (current === null ? after !== "" : before !== after) field_privacy[g] = after || null;
    }
    setPrivacy.mutate(
      { privacy_level: level || null, field_privacy: Object.keys(field_privacy).length ? field_privacy : null },
      { onSuccess: () => setSaved(t("common.saved")) },
    );
  };

  return (
    <div className="space-y-6">
      <section className="card p-4" aria-labelledby="priv-title">
        <h2 id="priv-title" className="flex items-center gap-2 font-display text-lg font-semibold">
          <ShieldCheck className="size-5 text-leaf-700" aria-hidden />
          {t("privacy.settingsTitle")}
        </h2>
        <p className="mt-1 text-sm text-ink-muted">{t("privacy.settingsIntro")}</p>
        {person.is_protected && <p className="mt-2 rounded-lg bg-sky-50 p-2 text-xs text-sky-950">{t("privacy.protectedDefaults")}</p>}
        <form onSubmit={save} className="mt-4 space-y-4">
          <Field label={t("privacy.personLevel")} hint={level ? t(`enum.privacyHint.${level}`) : undefined}>
            {(p) => (
              <Select {...p} value={level} onChange={(e) => setLevel(e.target.value as PrivacyLevel)}>
                {PRIVACY_LEVELS.map((l) => (
                  <option key={l} value={l}>
                    {t(`enum.privacy.${l}`)}
                  </option>
                ))}
              </Select>
            )}
          </Field>
          <fieldset>
            <legend className="label">{t("privacy.fieldOverrides")}</legend>
            <p className="hint mb-2">{current === null && !isAdmin ? t("privacy.claimantCantSeeOverrides") : t("privacy.fieldOverridesHint")}</p>
            <div className="overflow-x-auto">
              <table className="w-full text-sm">
                <caption className="sr-only">{t("privacy.fieldOverrides")}</caption>
                <thead>
                  <tr className="text-left text-xs uppercase tracking-wide text-ink-muted">
                    <th scope="col" className="py-1 pr-3">
                      {t("privacy.fieldGroup")}
                    </th>
                    <th scope="col" className="py-1">
                      {t("privacy.visibleTo")}
                    </th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-stone-100">
                  {FIELD_GROUPS.map((g) => (
                    <tr key={g}>
                      <th scope="row" className="py-1.5 pr-3 font-normal">
                        {t(`enum.fieldGroup.${g}`)}
                      </th>
                      <td className="py-1.5">
                        <label className="sr-only" htmlFor={`fg-${g}`}>
                          {t(`enum.fieldGroup.${g}`)}
                        </label>
                        <select id={`fg-${g}`} className="input" value={overrides[g]} onChange={(e) => setOverrides({ ...overrides, [g]: e.target.value as PrivacyLevel | "" })}>
                          <option value="">{t("privacy.useDefault")}</option>
                          {PRIVACY_LEVELS.map((l) => (
                            <option key={l} value={l}>
                              {t(`enum.privacy.${l}`)}
                            </option>
                          ))}
                        </select>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </fieldset>
          <ErrorAlert error={setPrivacy.error} />
          <LiveRegion message={saved} />
          <Button type="submit" loading={setPrivacy.isPending}>
            {t("privacy.save")}
          </Button>
        </form>
      </section>
      {person.privacy_level === "CUSTOM" && <GrantsPanel resourceType="person" resourceId={person.id} isCustom />}
      {(isAdmin || isClaimant) && <ConsentSection personId={person.id} />}
      <ErasePanel person={person} />
    </div>
  );
}

function ConsentSection({ personId }: { personId: string }) {
  const { t, i18n } = useTranslation();
  const { treeId } = useTreeCtx();
  const consents = useConsents(treeId, personId, true);
  const record = useRecordConsent(treeId, personId);
  const withdraw = useWithdrawConsent(treeId);
  const [open, setOpen] = useState(false);
  const [d, setD] = useState({ granted_by_name: "", authority_basis: "self" as ConsentBasis, purpose: "", categories: [] as string[], notes: "" });
  const [err, setErr] = useState<string | null>(null);
  const submit = (e: FormEvent) => {
    e.preventDefault();
    if (!d.granted_by_name.trim() || !d.purpose.trim() || d.categories.length === 0) {
      setErr(t("consent.required"));
      return;
    }
    setErr(null);
    record.mutate(
      { granted_by_name: d.granted_by_name.trim(), authority_basis: d.authority_basis, purpose: d.purpose.trim(), data_categories: d.categories, notes: d.notes.trim() || null },
      {
        onSuccess: () => {
          setOpen(false);
          setD({ granted_by_name: "", authority_basis: "self", purpose: "", categories: [], notes: "" });
        },
      },
    );
  };
  return (
    <section className="card p-4" aria-labelledby="consent-title">
      <div className="flex items-center justify-between">
        <h2 id="consent-title" className="font-display text-lg font-semibold">
          {t("consent.title")}
        </h2>
        <Button size="sm" variant="secondary" onClick={() => setOpen(!open)} aria-expanded={open}>
          {t("consent.record")}
        </Button>
      </div>
      <p className="mt-1 text-xs text-ink-muted">{t("consent.intro")}</p>
      {open && (
        <form onSubmit={submit} className="mt-3 grid grid-cols-1 gap-3 rounded-lg border border-stone-300 p-3 sm:grid-cols-2" noValidate>
          <Field label={t("consent.grantedBy")} required>
            {(p) => <TextInput {...p} value={d.granted_by_name} onChange={(e) => setD({ ...d, granted_by_name: e.target.value })} />}
          </Field>
          <Field label={t("consent.basis")}>
            {(p) => (
              <Select {...p} value={d.authority_basis} onChange={(e) => setD({ ...d, authority_basis: e.target.value as ConsentBasis })}>
                {CONSENT_BASES.map((b) => (
                  <option key={b} value={b}>
                    {t(`enum.consentBasis.${b}`)}
                  </option>
                ))}
              </Select>
            )}
          </Field>
          <Field label={t("consent.purpose")} required className="sm:col-span-2">
            {(p) => <TextInput {...p} value={d.purpose} onChange={(e) => setD({ ...d, purpose: e.target.value })} />}
          </Field>
          <fieldset className="sm:col-span-2">
            <legend className="label">{t("consent.categories")}</legend>
            <div className="grid grid-cols-2 gap-1 sm:grid-cols-3">
              {["profile", ...FIELD_GROUPS, "photos", "documents"].map((c) => (
                <label key={c} className="inline-flex items-center gap-2 text-sm">
                  <input
                    type="checkbox"
                    className="accent-kumkum-700"
                    checked={d.categories.includes(c)}
                    onChange={(e) => setD({ ...d, categories: e.target.checked ? [...d.categories, c] : d.categories.filter((x) => x !== c) })}
                  />
                  {t(`enum.consentCategory.${c}`)}
                </label>
              ))}
            </div>
          </fieldset>
          <Field label={t("consent.notes")} className="sm:col-span-2">
            {(p) => <TextArea {...p} rows={2} value={d.notes} onChange={(e) => setD({ ...d, notes: e.target.value })} />}
          </Field>
          {err && (
            <p role="alert" className="field-error sm:col-span-2">
              {err}
            </p>
          )}
          <div className="sm:col-span-2">
            <ErrorAlert error={record.error} />
            <Button type="submit" loading={record.isPending}>
              {t("consent.save")}
            </Button>
          </div>
        </form>
      )}
      {consents.isLoading && <Spinner />}
      <ErrorAlert error={consents.error || withdraw.error} />
      {consents.data && consents.data.length === 0 && <p className="mt-2 text-sm text-ink-muted">{t("consent.none")}</p>}
      <ul className="mt-3 divide-y divide-stone-100">
        {consents.data?.map((c) => (
          <li key={c.id} className="flex flex-col gap-1 py-2 sm:flex-row sm:items-start sm:justify-between">
            <div className="text-sm">
              <p className="font-medium">
                {c.purpose} {c.active ? <Badge tone="green">{t("consent.active")}</Badge> : <Badge tone="stone">{t("consent.inactive")}</Badge>}
              </p>
              <p className="text-xs text-ink-muted">
                {t("consent.by", { name: c.granted_by_name, basis: t(`enum.consentBasis.${c.authority_basis}`) })} ·{" "}
                {new Date(c.granted_at).toLocaleDateString(i18n.language)}
                {c.withdrawn_at && ` · ${t("consent.withdrawnOn", { date: new Date(c.withdrawn_at).toLocaleDateString(i18n.language) })}`}
              </p>
              <p className="text-xs">{c.data_categories.map((x) => t(`enum.consentCategory.${x}`, { defaultValue: x })).join(", ")}</p>
            </div>
            {c.active && (
              <Button size="sm" variant="secondary" loading={withdraw.isPending && withdraw.variables === c.id} onClick={() => withdraw.mutate(c.id)}>
                {t("consent.withdraw")}
              </Button>
            )}
          </li>
        ))}
      </ul>
    </section>
  );
}

export { PrivacyBadge };
