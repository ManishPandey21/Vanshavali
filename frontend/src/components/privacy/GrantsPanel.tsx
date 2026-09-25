import { useState } from "react";
import { useTranslation } from "react-i18next";
import { KeyRound, Trash2 } from "lucide-react";
import type { GrantPermission, GrantResource } from "../../api/types";
import { useCreateGrant, useDeleteGrant, useGrants } from "../../api/hooks/documents";
import { useMembers } from "../../api/hooks/trees";
import { useTreeCtx } from "../../lib/tree-context";
import { Perm } from "../../lib/permissions";
import { Button } from "../ui/Button";
import { ErrorAlert } from "../ui/feedback";
import { Field, Select, TextInput } from "../ui/form";
import { Badge } from "../ui/Badge";

/**
 * Explicit access grants for objects with CUSTOM privacy (ADR-0006: admins plus granted users).
 * Only rendered for members with privacy.manage; the server re-checks every call.
 */
export function GrantsPanel({ resourceType, resourceId, isCustom, allowDownload = false }: { resourceType: GrantResource; resourceId: string; isCustom: boolean; allowDownload?: boolean }) {
  const { t, i18n } = useTranslation();
  const { treeId, can } = useTreeCtx();
  const manage = can(Perm.PRIVACY_MANAGE);
  const grants = useGrants(treeId, manage);
  const members = useMembers(treeId);
  const create = useCreateGrant(treeId);
  const del = useDeleteGrant(treeId);
  const [userId, setUserId] = useState("");
  const [perm, setPerm] = useState<GrantPermission>("view");
  const [expires, setExpires] = useState("");
  if (!manage) return null;
  const mine = (grants.data ?? []).filter((g) => g.resource_type === resourceType && g.resource_id === resourceId);
  const nameOf = (uid: string) => members.data?.find((m) => m.user_id === uid)?.display_name ?? uid.slice(0, 8);
  return (
    <section className="card space-y-3 p-4" aria-labelledby={`grants-${resourceId}`}>
      <h3 id={`grants-${resourceId}`} className="flex items-center gap-2 font-display text-base font-semibold">
        <KeyRound className="size-4 text-haldi-700" aria-hidden /> {t("grants.title")}
      </h3>
      <p className="text-xs text-ink-muted">{isCustom ? t("grants.intro") : t("grants.notCustom")}</p>
      <ErrorAlert error={grants.error || del.error} />
      {mine.length === 0 ? (
        <p className="text-sm text-ink-muted">{t("grants.none")}</p>
      ) : (
        <ul className="divide-y divide-stone-100 text-sm">
          {mine.map((g) => (
            <li key={g.id} className="flex items-center justify-between gap-2 py-1.5">
              <span>
                {nameOf(g.user_id)} <Badge tone="blue">{t(`enum.grantPermission.${g.permission}`)}</Badge>
                {g.expires_at && <span className="ml-1 text-xs text-ink-muted">{t("grants.until", { date: new Date(g.expires_at).toLocaleDateString(i18n.language) })}</span>}
              </span>
              <button type="button" className="rounded p-1 text-red-800 hover:bg-red-50" onClick={() => del.mutate(g.id)} aria-label={t("grants.revoke", { name: nameOf(g.user_id) })}>
                <Trash2 className="size-4" aria-hidden />
              </button>
            </li>
          ))}
        </ul>
      )}
      <form
        className="grid grid-cols-1 items-end gap-2 sm:grid-cols-4"
        onSubmit={(e) => {
          e.preventDefault();
          if (!userId) return;
          create.mutate(
            { user_id: userId, resource_type: resourceType, resource_id: resourceId, permission: perm, expires_at: expires ? new Date(`${expires}T23:59:59`).toISOString() : null },
            { onSuccess: () => setUserId("") },
          );
        }}
      >
        <Field label={t("grants.member")}>
          {(p) => (
            <Select {...p} value={userId} onChange={(e) => setUserId(e.target.value)}>
              <option value="">—</option>
              {members.data?.map((m) => (
                <option key={m.user_id} value={m.user_id}>
                  {m.display_name}
                </option>
              ))}
            </Select>
          )}
        </Field>
        <Field label={t("grants.permission")}>
          {(p) => (
            <Select {...p} value={perm} onChange={(e) => setPerm(e.target.value as GrantPermission)}>
              <option value="view">{t("enum.grantPermission.view")}</option>
              {allowDownload && <option value="download">{t("enum.grantPermission.download")}</option>}
            </Select>
          )}
        </Field>
        <Field label={t("grants.expires")}>{(p) => <TextInput {...p} type="date" value={expires} onChange={(e) => setExpires(e.target.value)} />}</Field>
        <Button type="submit" size="sm" disabled={!userId} loading={create.isPending}>
          {t("grants.add")}
        </Button>
      </form>
      <ErrorAlert error={create.error} />
    </section>
  );
}
