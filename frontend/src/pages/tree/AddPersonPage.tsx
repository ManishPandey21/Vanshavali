import { useState, type FormEvent } from "react";
import { Navigate, useNavigate } from "react-router-dom";
import { useTranslation } from "react-i18next";
import { useCreatePerson } from "../../api/hooks/people";
import { useTreeCtx } from "../../lib/tree-context";
import { Perm } from "../../lib/permissions";
import { PersonForm, buildPersonCreate, emptyPersonDraft, validatePersonDraft, type PersonDraft } from "../../components/person/PersonForm";
import { focusFirstInvalid } from "../../components/ui/form";
import { Button, ButtonLink } from "../../components/ui/Button";
import { ErrorAlert, PageHeader } from "../../components/ui/feedback";

export function AddPersonPage() {
  const { t, i18n } = useTranslation();
  const { treeId, tree, can } = useTreeCtx();
  const create = useCreatePerson(treeId);
  const navigate = useNavigate();
  const [draft, setDraft] = useState<PersonDraft>(() => emptyPersonDraft(i18n.language));
  const [submitted, setSubmitted] = useState(false);
  const [clientError, setClientError] = useState<string | null>(null);

  if (!can(Perm.PERSON_WRITE)) return <Navigate to={`/t/${treeId}/people`} replace />;

  const submit = (e: FormEvent) => {
    e.preventDefault();
    setSubmitted(true);
    const errs = validatePersonDraft(draft);
    if (Object.keys(errs).length) {
      setClientError(t("person.err.fixErrors"));
      focusFirstInvalid(e.currentTarget as HTMLFormElement);
      return;
    }
    setClientError(null);
    create.mutate(buildPersonCreate(draft), { onSuccess: (p) => navigate(`/t/${treeId}/people/${p.id}`) });
  };

  return (
    <div className="mx-auto max-w-3xl">
      <PageHeader title={t("people.addTitle")} subtitle={t("people.addSubtitle")} />
      <form onSubmit={submit} noValidate className="card space-y-5 p-5">
        <PersonForm treeId={treeId} draft={draft} onChange={setDraft} showErrors={submitted} treeDefaultPrivacy={tree.default_person_privacy} headingLevel={2} />
        {clientError && (
          <p role="alert" className="field-error text-sm">
            {clientError}
          </p>
        )}
        <ErrorAlert error={create.error} />
        <div className="flex justify-end gap-2 border-t border-stone-200 pt-4">
          <ButtonLink to={`/t/${treeId}/people`} variant="secondary">
            {t("common.cancel")}
          </ButtonLink>
          <Button type="submit" loading={create.isPending}>
            {t("people.save")}
          </Button>
        </div>
      </form>
    </div>
  );
}
