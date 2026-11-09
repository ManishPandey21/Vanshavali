import { useId, useState, type FormEvent } from "react";
import { useTranslation } from "react-i18next";
import { Upload } from "lucide-react";
import type { DocumentCategory, DocumentLinkTarget, DocumentOut, GenealogicalDate, PersonSummary, RecordPrivacyLevel, SharingOut, SharingUpdate } from "../../api/types";
import { api } from "../../api/client";
import { useUploadDocument } from "../../api/hooks/documents";
import { useMembers } from "../../api/hooks/trees";
import { useBranches } from "../../api/hooks/family";
import { useMe } from "../../api/hooks/auth";
import { RECORD_AUDIENCES, VisibilitySharing, draftProblem, type SharingDraft } from "../privacy/VisibilitySharing";
import { useTreeCtx } from "../../lib/tree-context";
import { emptyDate, normalizeDate, validateDate } from "../../lib/dates";
import { DOCUMENT_CATEGORIES, VAULT_CATEGORIES } from "../../lib/documents";
import { GenealogicalDateEditor } from "../dates/GenealogicalDateEditor";
import { PersonPicker } from "../pickers";
import { hasDate } from "../person/PersonForm";
import { Button } from "../ui/Button";
import { Dialog } from "../ui/Dialog";
import { ErrorAlert } from "../ui/feedback";
import { Fieldset, Field, Select, TextArea, TextInput } from "../ui/form";
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
  const { treeId, tree } = useTreeCtx();
  const upload = useUploadDocument(treeId);
  const members = useMembers(treeId);
  const branches = useBranches(treeId);
  const me = useMe();
  const fileId = useId();
  const [file, setFile] = useState<File | null>(null);
  const [category, setCategory] = useState<DocumentCategory>(initialCategory);
  const [title, setTitle] = useState("");
  const [description, setDescription] = useState("");
  const [authority, setAuthority] = useState("");
  // ADR-0027 §9: Only me for vault categories and records about a person; else the tree default
  const [sharing, setSharing] = useState<SharingDraft | null>(null);
  const [shareError, setShareError] = useState<unknown>(null);
  const [date, setDate] = useState<GenealogicalDate>(emptyDate());
  const [person, setPerson] = useState<PersonSummary | null>(null);
  const [submitted, setSubmitted] = useState(false);
  const treeDefault = tree.default_person_privacy as RecordPrivacyLevel;
  const sensitive = VAULT_CATEGORIES.has(category) || !!person || linkTarget?.type === "person";
  const draft: SharingDraft = sharing ?? {
    privacy_level: sensitive || !RECORD_AUDIENCES.includes(treeDefault) ? "ONLY_ME" : treeDefault,
    audience_branch_id: null,
    allow_download: !sensitive,
    members: [],
  };
  const sharingProblem = draftProblem(draft);
  const titleMissing = !title.trim();
  const dateInvalid = hasDate(date) && Object.keys(validateDate(date)).length > 0;

  const submit = (e: FormEvent) => {
    e.preventDefault();
    setSubmitted(true);
    if (!file || titleMissing || dateInvalid || sharingProblem) return;
    setShareError(null);
    const link = linkTarget ?? (person ? { type: "person" as const, id: person.id } : null);
    upload.mutate(
      {
        file,
        category,
        title: title.trim(),
        description: description.trim() || undefined,
        issuing_authority: authority.trim() || undefined,
        // Selected members are attached right after the upload; until then it is Only me
        privacy_level: draft.privacy_level === "SELECTED_MEMBERS" ? "ONLY_ME" : draft.privacy_level,
        audience_branch_id: draft.privacy_level === "FAMILY_BRANCH" ? (draft.audience_branch_id ?? undefined) : undefined,
        allow_download: draft.allow_download,
        document_date: hasDate(date) ? normalizeDate(date) : undefined,
        link_target_type: link?.type,
        link_target_id: link?.id,
      },
      {
        onSuccess: async (d) => {
          if (draft.privacy_level === "SELECTED_MEMBERS") {
            const body: SharingUpdate = { privacy_level: "SELECTED_MEMBERS", allow_download: false, members: draft.members, confirm_wider: true };
            try {
              await api.put<SharingOut>(`/trees/${treeId}/documents/${d.id}/sharing`, body);
            } catch (e) {
              setShareError(e); // the upload stays Only me: safe; the owner can share from its page
              return;
            }
          }
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
          <Field label={t("documents.issuingAuthority")}>{(p) => <TextInput {...p} value={authority} onChange={(e) => setAuthority(e.target.value)} />}</Field>
        </div>
        <Fieldset legend={t("sharing.title")} description={`${t("documents.privacyHint")} ${t("sharing.uploadNote")}`}>
          <VisibilitySharing
            value={draft}
            onChange={setSharing}
            members={members.data ?? []}
            branches={branches.data ?? []}
            ownMembershipId={members.data?.find((m) => m.user_id === me.data?.id)?.id ?? null}
            showProblems={submitted}
          />
        </Fieldset>
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
        {!specific && <ErrorAlert error={upload.error || shareError} />}
      </form>
    </Dialog>
  );
}
