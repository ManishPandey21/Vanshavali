import { useState } from "react";
import { useNavigate } from "react-router-dom";
import { useTranslation } from "react-i18next";
import { FileText, Upload } from "lucide-react";
import type { DocumentCategory, PersonSummary } from "../../../api/types";
import { useDocuments } from "../../../api/hooks/documents";
import { useProperties } from "../../../api/hooks/property";
import { useTreeCtx } from "../../../lib/tree-context";
import { Perm } from "../../../lib/permissions";
import { useDebounced } from "../../../lib/useDebounced";
import { DOCUMENT_CATEGORIES } from "../../../lib/documents";
import { DocumentRow } from "../../../components/documents/DocumentBits";
import { UploadDocumentDialog } from "../../../components/documents/UploadDocumentDialog";
import { PersonPicker } from "../../../components/pickers";
import { Button } from "../../../components/ui/Button";
import { EmptyState, ErrorAlert, PageHeader, Spinner } from "../../../components/ui/feedback";
import { Checkbox, Field, Select, TextInput } from "../../../components/ui/form";

export function DocumentsPage() {
  const { t } = useTranslation();
  const { treeId, can } = useTreeCtx();
  const navigate = useNavigate();
  const [category, setCategory] = useState<DocumentCategory | "">("");
  const [person, setPerson] = useState<PersonSummary | null>(null);
  const [propertyId, setPropertyId] = useState("");
  const [deleted, setDeleted] = useState(false);
  const [q, setQ] = useState("");
  const [uploading, setUploading] = useState(false);
  const debounced = useDebounced(q.trim(), 300);
  const canProperty = can(Perm.PROPERTY_READ) || can(Perm.PROPERTY_WRITE);
  const properties = useProperties(treeId, "", canProperty);
  const target = person ? { target_type: "person" as const, target_id: person.id } : propertyId ? { target_type: "property" as const, target_id: propertyId } : {};
  const docs = useDocuments(treeId, { category: category || undefined, q: debounced || undefined, deleted, ...target });
  const items = docs.data?.items ?? [];
  const canUpload = can(Perm.DOCUMENT_UPLOAD);

  return (
    <div>
      <PageHeader
        title={t("documents.title")}
        subtitle={t("documents.subtitle")}
        actions={
          canUpload ? (
            <Button icon={<Upload className="size-4" aria-hidden />} onClick={() => setUploading(true)}>
              {t("documents.upload")}
            </Button>
          ) : undefined
        }
      />
      <div className="card mb-4 grid grid-cols-1 gap-3 p-4 sm:grid-cols-2 lg:grid-cols-4">
        <Field label={t("documents.search")}>{(p) => <TextInput {...p} type="search" value={q} onChange={(e) => setQ(e.target.value)} />}</Field>
        <Field label={t("documents.category")}>
          {(p) => (
            <Select {...p} value={category} onChange={(e) => setCategory(e.target.value as DocumentCategory | "")}>
              <option value="">{t("common.all")}</option>
              {DOCUMENT_CATEGORIES.map((c) => (
                <option key={c} value={c}>
                  {t(`enum.docCategory.${c}`)}
                </option>
              ))}
            </Select>
          )}
        </Field>
        <PersonPicker
          treeId={treeId}
          label={t("documents.aboutPerson")}
          value={person}
          onChange={(p) => {
            setPerson(p);
            if (p) setPropertyId("");
          }}
        />
        {canProperty && (
          <Field label={t("documents.aboutProperty")}>
            {(p) => (
              <Select
                {...p}
                value={propertyId}
                onChange={(e) => {
                  setPropertyId(e.target.value);
                  if (e.target.value) setPerson(null);
                }}
              >
                <option value="">{t("common.all")}</option>
                {properties.data?.map((pr) => (
                  <option key={pr.id} value={pr.id}>
                    {pr.display_name}
                  </option>
                ))}
              </Select>
            )}
          </Field>
        )}
        {can(Perm.DOCUMENT_MANAGE) && <Checkbox label={t("documents.showDeleted")} checked={deleted} onChange={setDeleted} />}
      </div>
      {docs.isLoading && <Spinner />}
      <ErrorAlert error={docs.error} />
      {docs.data && items.length === 0 && (
        <EmptyState icon={<FileText className="size-10" aria-hidden />} title={t("documents.empty")}>
          {t("documents.emptyHint")}
        </EmptyState>
      )}
      {items.length > 0 && (
        <ul className="card divide-y divide-stone-100">
          {items.map((d) => (
            <DocumentRow key={d.id} treeId={treeId} doc={d} />
          ))}
        </ul>
      )}
      {uploading && <UploadDocumentDialog onClose={() => setUploading(false)} onUploaded={(d) => navigate(`/t/${treeId}/documents/${d.id}`)} />}
    </div>
  );
}
