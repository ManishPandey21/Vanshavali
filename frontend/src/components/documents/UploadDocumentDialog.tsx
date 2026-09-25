import { useId, useState, type FormEvent } from "react";
import { useTranslation } from "react-i18next";
import { Upload } from "lucide-react";
import type { DocumentCategory, DocumentLinkTarget, DocumentOut, GenealogicalDate, PersonSummary, PrivacyLevel } from "../../api/types";
import { useUploadDocument } from "../../api/hooks/documents";
import { useTreeCtx } from "../../lib/tree-context";
import { emptyDate, normalizeDate, validateDate } from "../../lib/dates";
import { DOCUMENT_CATEGORIES, VAULT_CATEGORIES } from "../../lib/documents";
import { GenealogicalDateEditor } from "../dates/GenealogicalDateEditor";
import { PersonPicker } from "../pickers";
import { PRIVACY_LEVELS, hasDate } from "../person/PersonForm";
import { Button } from "../ui/Button";
import { Dialog } from "../ui/Dialog";
import { ErrorAlert } from "../ui/feedback";
import { Field, Select, TextArea, TextInput } from "../ui/form";
import { uploadErrorMessage } from "./DocumentBits";

export interface LinkTarget {
  type: DocumentLinkTarget;
  id: string;
  label: string;
}

/**
 * Upload a document into the vault. The server validates type by magic bytes, scans for malware,
 * rejects duplicates by checksum and then (for supported categories) runs OCR and extraction.
 */
export function UploadDocumentDialog({
  onClose,
  onUploaded,
  initialCategory = "other",
  linkTarget,
  categories = DOCUMENT_CATEGORIES,
  title: dialogTitle,
}: {
  onClose: () => void;
  onUploaded?: (d: DocumentOut) => void;
  initialCategory?: DocumentCategory;
  linkTarget?: LinkTarget;
  categories?: DocumentCategory[];
  title?: string;
}) {
  const { t } = useTranslation();
  const { treeId } = useTreeCtx();
  const upload = useUploadDocument(treeId);
  const fileId = useId();
  const [file, setFile] = useState<File | null>(null);
  const [category, setCategory] = useState<DocumentCategory>(initialCategory);
  const [title, setTitle] = useState("");
  const [description, setDescription] = useState("");
  const [authority, setAuthority] = useState("");
  const [privacy, setPrivacy] = useState<PrivacyLevel | "">("");
  const [date, setDate] = useState<GenealogicalDate>(emptyDate());
  const [person, setPerson] = useState<PersonSummary | null>(null);
  const [submitted, setSubmitted] = useState(false);
  const titleMissing = !title.trim();
  const dateInvalid = hasDate(date) && Object.keys(validateDate(date)).length > 0;

  const submit = (e: FormEvent) => {
    e.preventDefault();
    setSubmitted(true);
    if (!file || titleMissing || dateInvalid) return;
    const link = linkTarget ?? (person ? { type: "person" as const, id: person.id } : null);
    upload.mutate(
      {
        file,
        category,
        title: title.trim(),
        description: description.trim() || undefined,
        issuing_authority: authority.trim() || undefined,
        privacy_level: privacy || undefined,
        document_date: hasDate(date) ? normalizeDate(date) : undefined,
        link_target_type: link?.type,
        link_target_id: link?.id,
      },
      {
        onSuccess: (d) => {
          onUploaded?.(d);
          onClose();
        },
      },
    );
  };
  const specific = uploadErrorMessage(upload.error, t);

  return (
    <Dialog
      open
      onClose={onClose}
      size="lg"
      title={dialogTitle ?? t("documents.uploadTitle")}
      description={t("documents.uploadIntro")}
      footer={
        <>
          <Button variant="secondary" onClick={onClose}>
            {t("common.cancel")}
          </Button>
          <Button type="submit" form="upload-form" loading={upload.isPending} icon={<Upload className="size-4" aria-hidden />}>
            {t("documents.upload")}
          </Button>
        </>
      }
    >
      <form id="upload-form" onSubmit={submit} className="space-y-3" noValidate>
        <div>
          <label htmlFor={fileId} className="label">
            {t("documents.file")} <span aria-hidden>*</span>
          </label>
          <input
            id={fileId}
            type="file"
            className="block w-full text-sm file:mr-3 file:rounded-md file:border-0 file:bg-kumkum-100 file:px-3 file:py-2 file:text-kumkum-900"
            aria-invalid={submitted && !file ? true : undefined}
            aria-describedby={`${fileId}-hint`}
            onChange={(e) => {
              const f = e.target.files?.[0] ?? null;
              setFile(f);
              if (f && !title) setTitle(f.name.replace(/\.[^.]+$/, ""));
            }}
          />
          <p id={`${fileId}-hint`} className="hint">
            {t("documents.fileHint")}
          </p>
          {submitted && !file && <p className="field-error">{t("documents.fileRequired")}</p>}
        </div>
        <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
          <Field label={t("documents.category")} hint={VAULT_CATEGORIES.has(category) ? t("documents.vaultHint") : undefined}>
            {(p) => (
              <Select {...p} value={category} onChange={(e) => setCategory(e.target.value as DocumentCategory)}>
                {categories.map((c) => (
                  <option key={c} value={c}>
                    {t(`enum.docCategory.${c}`)}
                  </option>
                ))}
              </Select>
            )}
          </Field>
          <Field label={t("documents.title")} required error={submitted && titleMissing ? t("common.required") : null}>
            {(p) => <TextInput {...p} value={title} onChange={(e) => setTitle(e.target.value)} />}
          </Field>
          <Field label={t("privacy.level")} hint={t("documents.privacyHint")}>
            {(p) => (
              <Select {...p} value={privacy} onChange={(e) => setPrivacy(e.target.value as PrivacyLevel | "")}>
                <option value="">{t("documents.privacyDefault")}</option>
                {PRIVACY_LEVELS.map((l) => (
                  <option key={l} value={l}>
                    {t(`enum.privacy.${l}`)}
                  </option>
                ))}
              </Select>
            )}
          </Field>
          <Field label={t("documents.issuingAuthority")}>{(p) => <TextInput {...p} value={authority} onChange={(e) => setAuthority(e.target.value)} />}</Field>
        </div>
        <GenealogicalDateEditor legend={t("documents.date")} value={date} onChange={setDate} showErrors={submitted && hasDate(date)} />
        <Field label={t("documents.description")}>{(p) => <TextArea {...p} rows={2} value={description} onChange={(e) => setDescription(e.target.value)} />}</Field>
        {linkTarget ? (
          <p className="rounded-lg bg-parchment-deep px-3 py-2 text-sm">
            {t("documents.willLinkTo", { target: linkTarget.label })}
          </p>
        ) : (
          <PersonPicker treeId={treeId} label={t("documents.linkPersonOptional")} value={person} onChange={setPerson} />
        )}
        {specific && (
          <p role="alert" className="rounded-lg border border-red-300 bg-red-50 px-3 py-2 text-sm text-red-900">
            {specific}
          </p>
        )}
        {!specific && <ErrorAlert error={upload.error} />}
      </form>
    </Dialog>
  );
}
