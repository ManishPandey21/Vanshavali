import { useState } from "react";
import { useNavigate } from "react-router-dom";
import { useTranslation } from "react-i18next";
import { Eraser } from "lucide-react";
import type { PersonOut } from "../../../api/types";
import { useErasePerson } from "../../../api/hooks/people";
import { useTreeCtx } from "../../../lib/tree-context";
import { Perm } from "../../../lib/permissions";
import { Button } from "../../../components/ui/Button";
import { Dialog } from "../../../components/ui/Dialog";
import { ErrorAlert } from "../../../components/ui/feedback";
import { Field, TextArea, TextInput } from "../../../components/ui/form";

/** The erase gate: the exact display name must be typed and a reason of ≥ 3 characters given. */
export function eraseAllowed(displayName: string, typed: string, reason: string): boolean {
  return typed.trim() === displayName.trim() && reason.trim().length >= 3;
}

/**
 * Irreversible privacy erasure (admins). Personal data is deleted; an anonymous placeholder keeps
 * the tree's structure (relationships) so descendants stay connected.
 */
export function ErasePanel({ person }: { person: PersonOut }) {
  const { t } = useTranslation();
  const { treeId, can } = useTreeCtx();
  const erase = useErasePerson(treeId);
  const navigate = useNavigate();
  const [open, setOpen] = useState(false);
  const [typed, setTyped] = useState("");
  const [reason, setReason] = useState("");
  if (!can(Perm.TREE_MANAGE)) return null;
  const ok = eraseAllowed(person.display_name, typed, reason);
  return (
    <section className="card space-y-2 border-red-300 p-4" aria-labelledby="erase-title">
      <h2 id="erase-title" className="flex items-center gap-2 font-display text-lg font-semibold text-red-900">
        <Eraser className="size-5" aria-hidden /> {t("erase.title")}
      </h2>
      <p className="text-sm">{t("erase.intro")}</p>
      <Button variant="danger" onClick={() => setOpen(true)}>
        {t("erase.open")}
      </Button>
      {open && (
        <Dialog
          open
          onClose={() => setOpen(false)}
          title={t("erase.confirmTitle", { name: person.display_name })}
          description={t("erase.confirmDescription")}
          footer={
            <>
              <Button variant="secondary" onClick={() => setOpen(false)}>
                {t("common.cancel")}
              </Button>
              <Button
                variant="danger"
                disabled={!ok}
                loading={erase.isPending}
                onClick={() => erase.mutate({ id: person.id, reason: reason.trim() }, { onSuccess: () => navigate(`/t/${treeId}/people`) })}
              >
                {t("erase.submit")}
              </Button>
            </>
          }
        >
          <div className="space-y-3">
            <ul className="list-inside list-disc text-sm">
              <li>{t("erase.point1")}</li>
              <li>{t("erase.point2")}</li>
              <li>{t("erase.point3")}</li>
            </ul>
            <Field label={t("erase.reason")} hint={t("erase.reasonHint")}>
              {(p) => <TextArea {...p} rows={2} value={reason} onChange={(e) => setReason(e.target.value)} />}
            </Field>
            <Field label={t("erase.typeName", { name: person.display_name })}>
              {(p) => <TextInput {...p} autoComplete="off" value={typed} onChange={(e) => setTyped(e.target.value)} />}
            </Field>
            <ErrorAlert error={erase.error} />
          </div>
        </Dialog>
      )}
    </section>
  );
}
